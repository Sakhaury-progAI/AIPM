"""Deterministic refund tools. Eligibility is decided here, never by the LLM."""

from copy import deepcopy

from refund_data import APPROVAL_LIMIT, REFUND_WINDOW_DAYS, RefundStore


def rupees(amount) -> str:
    return f"₹{amount:,.0f}" if float(amount).is_integer() else f"₹{amount:,.2f}"


def get_user_account(store: RefundStore, user_id: str) -> dict:
    user = store.users.get(user_id)
    if user is None:
        return {"found": False, "user_id": user_id}
    return {"found": True, "user_id": user_id, **deepcopy(user)}


def _ineligibility_reason(recharge: dict, amount) -> str | None:
    if recharge["recharge_status"] != "completed":
        return f"the recharge is {recharge['recharge_status']}, not completed"
    if recharge["recharge_age_days"] > REFUND_WINDOW_DAYS:
        return f"the recharge is outside the {REFUND_WINDOW_DAYS}-day refund window"
    if recharge["refund_status"] == "refunded":
        return "the recharge has already been refunded"
    if amount > recharge["recharge_amount"]:
        return "the requested amount exceeds the recharge amount"
    return None


def _most_recent(recharges: list[dict]) -> dict:
    return min(recharges, key=lambda r: (r["recharge_age_days"], r["recharge_id"]))


def select_recharge(recharges: list[dict], amount) -> dict | None:
    """An exact amount match wins; otherwise the most recent eligible recharge that covers it."""
    exact = [r for r in recharges if r["recharge_amount"] == amount]
    if exact:
        return _most_recent(exact)
    covering = [r for r in recharges if r["recharge_amount"] >= amount]
    if not covering:
        return None
    eligible = [r for r in covering if _ineligibility_reason(r, amount) is None]
    return _most_recent(eligible or covering)


def eligible_recharges(store: RefundStore, user_id: str) -> list[dict]:
    user = store.users.get(user_id)
    if user is None:
        return []
    return [r for r in user["recharges"]
            if _ineligibility_reason(r, r["recharge_amount"]) is None]


def validate_refund(store: RefundStore, user_id: str, amount) -> dict:
    result = {"eligible": False, "requested_amount": amount,
              "recharge_amount": None, "recharge_id": None}
    user = store.users.get(user_id)
    if user is None:
        return {**result, "reason": "No account was found for this user."}
    if not isinstance(amount, (int, float)) or amount <= 0:
        return {**result, "reason": "The refund amount must be greater than zero."}

    recharge = select_recharge(user["recharges"], amount)
    if recharge is None:
        largest = max((r["recharge_amount"] for r in user["recharges"]), default=None)
        return {**result, "recharge_amount": largest,
                "reason": f"The requested amount {rupees(amount)} exceeds the recharge amount."}

    result.update(recharge_amount=recharge["recharge_amount"], recharge_id=recharge["recharge_id"])
    reason = _ineligibility_reason(recharge, amount)
    if reason:
        return {**result, "reason": reason[0].upper() + reason[1:] + "."}
    return {**result, "eligible": True, "reason": "Refund is eligible."}


def process_refund(store: RefundStore, user_id: str, amount) -> dict:
    """Simulated refund. Re-validates so it can never run on an ineligible or over-limit request."""
    validation = validate_refund(store, user_id, amount)
    if not validation["eligible"]:
        return {"success": False, "amount": amount, "reason": validation["reason"]}
    if amount > APPROVAL_LIMIT:
        return {"success": False, "amount": amount,
                "reason": f"Refunds above {rupees(APPROVAL_LIMIT)} cannot be processed here."}
    recharge = next(r for r in store.users[user_id]["recharges"]
                    if r["recharge_id"] == validation["recharge_id"])
    recharge["refund_status"] = "refunded"
    refund_id = f"ref_{789 + len(store.refunds)}"
    store.refunds.append({"refund_id": refund_id, "user_id": user_id,
                          "recharge_id": recharge["recharge_id"], "amount": amount})
    return {"success": True, "refund_id": refund_id, "amount": amount,
            "recharge_id": recharge["recharge_id"], "status": "refunded"}


def submit_to_support(store: RefundStore, user_id: str, amount) -> dict:
    """Queues the request for Support Team review. Does not change the refund status."""
    validation = validate_refund(store, user_id, amount)
    if not validation["eligible"]:
        return {"submitted": False, "amount": amount, "reason": validation["reason"]}
    request_id = f"sup_{101 + len(store.support_requests)}"
    store.support_requests.append({"request_id": request_id, "user_id": user_id,
                                   "recharge_id": validation["recharge_id"], "amount": amount})
    return {"submitted": True, "request_id": request_id, "amount": amount,
            "recharge_id": validation["recharge_id"], "status": "submitted_for_review"}
