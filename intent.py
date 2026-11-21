import re

from langchain_core.prompts import ChatPromptTemplate

from config import get_llm

REQUIREMENT_INQUIRY = "requirement_inquiry"
REFUND_REQUEST = "refund_request"

CLASSIFIER_PROMPT = """Classify the customer's latest message for a telecom support assistant.

Reply with exactly one label and nothing else:
- refund_request: the customer is asking us to refund, cancel, or reverse a recharge or payment they made (they want the action done).
- requirement_inquiry: any other question, including questions about HOW refunds or cancellations work.

Examples:
"Why is my internet slow?" -> requirement_inquiry
"I want a refund of ₹999." -> refund_request
"I want a refund." -> refund_request
"Please reverse my last recharge." -> refund_request
"Cancel my recharge, I did it by mistake." -> refund_request
"How do I cancel a recharge?" -> requirement_inquiry
"What is your refund policy?" -> requirement_inquiry
"Should I do that before I travel?" -> requirement_inquiry"""

_prompt = ChatPromptTemplate.from_messages([
    ("system", CLASSIFIER_PROMPT),
    ("human", "Earlier conversation (for context only):\n{history}\n\nLatest message:\n{message}"),
])

_chain = None

_REFUND_HINT = re.compile(r"\b(refund|money back|reverse|reversal)\b", re.I)
_HOW_QUESTION = re.compile(r"^\s*(how|what|when|why|can i|is it|do you)\b", re.I)


def _fallback(message: str) -> str:
    if _REFUND_HINT.search(message) and not _HOW_QUESTION.search(message):
        return REFUND_REQUEST
    return REQUIREMENT_INQUIRY


def classify(message: str, history=()) -> str:
    global _chain
    try:
        if _chain is None:
            _chain = _prompt | get_llm(max_tokens=10)
        recent = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in list(history)[-2:]) or "(none)"
        label = _chain.invoke({"history": recent, "message": message}).content.strip().lower()
    except Exception:
        return _fallback(message)
    if REFUND_REQUEST in label:
        return REFUND_REQUEST
    if REQUIREMENT_INQUIRY in label:
        return REQUIREMENT_INQUIRY
    return _fallback(message)
