"""Refund Agent: the LLM gathers facts with tools; code decides eligibility, approval and execution."""

import json
import re
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from config import get_llm, get_logger
from refund_data import APPROVAL_LIMIT, CURRENT_USER_ID, RefundStore
from refund_tools import (
    eligible_recharges,
    get_user_account,
    process_refund,
    rupees,
    submit_to_support,
    validate_refund,
)

AGENT_PROMPT = """You are the refund agent for a telecom company. The customer is already signed in and their account is available through your tools, so never ask for a user ID or account details.

Do this:
1. Call get_user_account.
2. If the customer's latest message states a refund amount, call validate_refund with exactly that amount.
3. If no amount is stated, do not call validate_refund and never guess an amount.

You do not decide eligibility, approve, or process refunds; the system does that after your tool calls. When you have finished calling tools, reply with the single word DONE."""

# Workflow states (PRD section 10).
REFUND_REQUESTED = "refund_requested"
REFUND_VALIDATED = "refund_validated"
AWAITING_CONFIRMATION = "awaiting_confirmation"
AWAITING_AMOUNT = "awaiting_amount"
REFUND_CONFIRMED = "refund_confirmed"
REFUND_PROCESSED = "refund_processed"
REFUND_REJECTED = "refund_rejected"
REFUND_CANCELLED = "refund_cancelled"
REFUND_SUBMITTED_FOR_REVIEW = "refund_submitted_for_review"

_CURRENCY_AMOUNT = re.compile(r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]*(?:\.\d+)?)", re.I)
_PLAIN_AMOUNT = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?![\w])")
_NO = re.compile(r"\b(no|nope|nah|cancel|stop|don'?t|do not|never ?mind|abort)\b")
_YES = re.compile(
    r"(yes|yeah|yep|yup|y|sure|confirm(ed)?|proceed|go ahead|ok(ay)? proceed|please proceed)"
    r"(,? (please|proceed|go ahead|confirm|do it|refund it|process it))*( please)?"
)


def extract_amounts(text: str) -> list[float]:
    matches = _CURRENCY_AMOUNT.findall(text) or _PLAIN_AMOUNT.findall(text)
    amounts = []
    for m in matches:
        try:
            amounts.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return amounts


def _number(amount: float):
    return int(amount) if float(amount).is_integer() else amount


def parse_confirmation(text: str) -> str:
    """'yes' only for an explicit confirmation; anything unclear is 'ambiguous'."""
    t = re.sub(r"[^\w\s,']", "", text.lower()).strip()
    if _NO.search(t):
        return "no"
    if _YES.fullmatch(t):
        return "yes"
    return "ambiguous"


@dataclass
class AgentReply:
    text: str
    confirm_amount: float | None = None
    steps: list[str] = field(default_factory=list)


class RefundAgent:
    def __init__(self, store: RefundStore, user_id: str = CURRENT_USER_ID):
        self.store = store
        self.user_id = user_id
        self.logger = get_logger()
        self.reset()

    def reset(self):
        self.state = None
        self.pending_amount = None
        self.suggested_amount = None
        self._steps = []

    @property
    def is_active(self) -> bool:
        return self.state in (AWAITING_CONFIRMATION, AWAITING_AMOUNT)

    def _log(self, line: str):
        self.logger.info(line)
        self._steps.append(line)

    def _reply(self, text: str, confirm_amount=None) -> AgentReply:
        reply = AgentReply(text, confirm_amount, self._steps)
        self._steps = []
        return reply

    # ---- entry points ----

    def handle(self, message: str, history=()) -> AgentReply:
        if self.state == AWAITING_CONFIRMATION:
            amounts = extract_amounts(message)
            if amounts and amounts[0] != self.pending_amount:
                self._log(f"[Agent] new amount in reply, restarting with {rupees(amounts[0])}")
                return self._run_with_amount(amounts[0])
            decision = parse_confirmation(message)
            if decision == "yes":
                return self.confirm()
            if decision == "no":
                return self.cancel()
            self._log("[User] ambiguous confirmation")
            return self._reply(
                f"Just to be sure: do you want me to refund {rupees(self.pending_amount)}? "
                "Please reply \"Yes, proceed\" or \"No\".",
                confirm_amount=self.pending_amount,
            )

        if self.state == AWAITING_AMOUNT:
            amounts = extract_amounts(message)
            if amounts:
                return self._run_with_amount(amounts[0])
            decision = parse_confirmation(message)
            if decision == "yes" and self.suggested_amount is not None:
                return self._run_with_amount(self.suggested_amount)
            if decision == "no":
                return self.cancel()
            return self._reply(self._amount_question())

        self.reset()
        self.state = REFUND_REQUESTED
        self._log("[Agent] refund_requested")
        validation = self._agent_loop(message, history)
        if validation is not None:
            return self._apply_validation(validation)
        return self._missing_amount()

    def confirm(self) -> AgentReply:
        if self.state != AWAITING_CONFIRMATION:
            return self._reply("There is no refund waiting for confirmation.")
        self._log("[User] confirmed")
        self.state = REFUND_CONFIRMED
        amount = self.pending_amount
        self._log(f"[Agent] process_refund(amount={_number(amount)})")
        result = process_refund(self.store, self.user_id, amount)
        self.pending_amount = None
        if not result["success"]:
            self.state = REFUND_REJECTED
            self._log(f"[Refund] failed: {result['reason']}")
            return self._reply(f"I couldn't process the refund: {result['reason']}")
        self.state = REFUND_PROCESSED
        self._log(f"[Refund] success refund_id={result['refund_id']}")
        return self._reply(
            f"Your refund of {rupees(amount)} for recharge {result['recharge_id']} has been processed. "
            f"Refund reference: **{result['refund_id']}**.\n\n"
            "_This is a simulated refund; no real payment was made._"
        )

    def cancel(self) -> AgentReply:
        self._log("[User] cancelled")
        self.state = REFUND_CANCELLED
        self.pending_amount = None
        self.suggested_amount = None
        return self._reply("Okay, I've cancelled this refund request. No refund has been made.")

    # ---- internals ----

    def _agent_loop(self, message: str, history) -> dict | None:
        stated_in_order = extract_amounts(message)
        stated = set(stated_in_order)
        account_fetched = False
        validation = None

        @tool
        def get_user_account_tool() -> dict:
            """Get the signed-in customer's account and recharge details."""
            return get_user_account(self.store, self.user_id)

        @tool
        def validate_refund_tool(amount: float) -> dict:
            """Check whether a refund of this amount is eligible."""
            return validate_refund(self.store, self.user_id, amount)

        get_user_account_tool.name = "get_user_account"
        validate_refund_tool.name = "validate_refund"

        try:
            llm = get_llm(max_tokens=150).bind_tools([get_user_account_tool, validate_refund_tool])
            messages = [SystemMessage(AGENT_PROMPT)]
            for m in list(history):
                messages.append(HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"]))
            messages.append(HumanMessage(message))
            for _ in range(3):
                ai = llm.invoke(messages)
                messages.append(ai)
                if not ai.tool_calls:
                    break
                for call in ai.tool_calls:
                    if call["name"] == "get_user_account":
                        self._log("[Agent] get_user_account")
                        result = get_user_account(self.store, self.user_id)
                        account_fetched = True
                    elif call["name"] == "validate_refund":
                        amount = call["args"].get("amount")
                        if not isinstance(amount, (int, float)) or float(amount) not in stated:
                            self._log(f"[Guardrail] ignored validate_refund(amount={amount}): not stated by the customer")
                            result = {"error": "That amount was not stated by the customer. Do not guess."}
                        else:
                            result = self._validate(float(amount))
                            validation = result
                    else:
                        result = {"error": f"Unknown tool {call['name']}"}
                    messages.append(ToolMessage(json.dumps(result), tool_call_id=call["id"]))
                if validation is not None:
                    break
        except Exception as e:
            self._log(f"[Agent] LLM unavailable ({type(e).__name__}); using deterministic steps")

        if not account_fetched:
            self._log("[Agent] get_user_account")
        if validation is None and stated:
            validation = self._validate(stated_in_order[0])
        return validation

    def _validate(self, amount: float) -> dict:
        self._log(f"[Agent] validate_refund(amount={_number(amount)})")
        result = validate_refund(self.store, self.user_id, amount)
        self._log(f"[Validation] eligible={result['eligible']}"
                  + ("" if result["eligible"] else f" reason={result['reason']}"))
        return result

    def _run_with_amount(self, amount: float) -> AgentReply:
        self.pending_amount = None
        self.suggested_amount = None
        return self._apply_validation(self._validate(amount))

    def _apply_validation(self, validation: dict) -> AgentReply:
        amount = validation["requested_amount"]
        if not validation["eligible"]:
            self.state = REFUND_REJECTED
            return self._reply(
                f"I'm sorry, I can't refund {rupees(amount)}. {validation['reason']}\n\n"
                "Refunds are possible for completed recharges made in the last 7 days, "
                "up to the recharge amount, and only once per recharge."
            )

        self.state = REFUND_VALIDATED
        if amount <= APPROVAL_LIMIT:
            self.state = AWAITING_CONFIRMATION
            self.pending_amount = amount
            self._log("[Agent] awaiting_user_confirmation")
            return self._reply(
                f"**Refund eligible: {rupees(amount)}** (recharge {validation['recharge_id']})\n\n"
                "Do you want to proceed with this refund?",
                confirm_amount=amount,
            )

        self._log(f"[Agent] submit_to_support(amount={_number(amount)})")
        result = submit_to_support(self.store, self.user_id, amount)
        self.state = REFUND_SUBMITTED_FOR_REVIEW
        self._log(f"[Support] submitted request_id={result.get('request_id')}")
        return self._reply(
            f"Your refund request for {rupees(amount)} has been submitted to our Support Team "
            f"(request {result.get('request_id')}). They will review the request and process it "
            "or take the necessary action."
        )

    def _missing_amount(self) -> AgentReply:
        eligible = eligible_recharges(self.store, self.user_id)
        self._log(f"[Agent] no amount stated; eligible recharges={len(eligible)}")
        if not eligible:
            self.state = REFUND_REJECTED
            return self._reply(
                "I couldn't find any recharge that is eligible for a refund. Refunds are possible for "
                "completed recharges made in the last 7 days that haven't already been refunded."
            )
        if len(eligible) == 1:
            amount = eligible[0]["recharge_amount"]
            if amount <= APPROVAL_LIMIT:
                return self._run_with_amount(amount)
            self.state = AWAITING_AMOUNT
            self.suggested_amount = amount
            self._log("[Agent] awaiting_amount")
            return self._reply(self._amount_question())
        self.state = AWAITING_AMOUNT
        self._log("[Agent] awaiting_amount")
        return self._reply(self._amount_question())

    def _amount_question(self) -> str:
        if self.suggested_amount is not None:
            return (f"Your recent eligible recharge is {rupees(self.suggested_amount)}. "
                    f"Would you like to request a refund of {rupees(self.suggested_amount)}?")
        amounts = [rupees(r["recharge_amount"]) for r in eligible_recharges(self.store, self.user_id)]
        if len(amounts) < 2:
            return "How much would you like refunded?"
        return (f"I can see more than one recent recharge - {' and '.join(amounts)}. "
                "Which amount would you like refunded?")
