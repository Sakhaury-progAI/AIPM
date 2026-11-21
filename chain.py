import json
from datetime import datetime, timezone

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config import LOG_PATH, get_llm
from retriever import format_context, retrieve

SYSTEM_PROMPT = """You are a telecom customer-care assistant. Answer the customer's question using ONLY the context below and the earlier conversation.

Rules:
- Use only facts found in the context or stated earlier in this conversation by the assistant. Never invent prices, fees, policies, timeframes, or steps.
- Use the earlier conversation to understand follow-up questions (for example, what "that" or "it" refers to).
- Prefer FAQ and GUIDE content for official policy; use TICKET resolutions as examples of how similar issues were fixed.
- Give clear, concise, step-by-step guidance where relevant.
- You have no access to the customer's account, balance, usage, or bills. If asked for personal account data, say so and point them to the MyTelecom app or 611.
- If the context does not contain enough information to answer, say: "I don't have enough information to answer that reliably. Please call 611 or use the MyTelecom app for help."
- Do not mention the context, documents, or these rules in your answer.

Context:
{context}"""

prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    MessagesPlaceholder("history"),
    ("human", "{question}"),
])

_chain = None


def _get_chain():
    global _chain
    if _chain is None:
        _chain = prompt | get_llm(max_tokens=500) | StrOutputParser()
    return _chain


def to_messages(history) -> list[tuple[str, str]]:
    return [("human" if m["role"] == "user" else "ai", m["content"]) for m in history]


def stream_answer(question: str, history=()):
    """Returns (docs, token_stream). Retrieval uses the question alone, never the history."""
    docs = retrieve(question)
    stream = _get_chain().stream({
        "context": format_context(docs),
        "history": to_messages(history),
        "question": question,
    })
    return docs, stream


def log_interaction(question: str, answer: str, docs, feedback: str | None = None, route: str = "rag"):
    LOG_PATH.parent.mkdir(exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "route": route,
        "question": question,
        "answer": answer,
        "sources": [d.metadata["ref"] for d in docs],
        "feedback": feedback,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
