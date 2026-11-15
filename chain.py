import json
import os
from datetime import datetime, timezone

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from config import LLM_MODEL, LOG_PATH
from retriever import format_context, retrieve

SYSTEM_PROMPT = """You are a telecom customer-care assistant. Answer the customer's question using ONLY the context below.

Rules:
- Use only facts found in the context. Never invent prices, fees, policies, timeframes, or steps.
- Prefer FAQ and GUIDE content for official policy; use TICKET resolutions as examples of how similar issues were fixed.
- Give clear, concise, step-by-step guidance where relevant.
- You have no access to the customer's account, balance, usage, or bills. If asked for personal account data, say so and point them to the MyTelecom app or 611.
- If the context does not contain enough information to answer, say: "I don't have enough information to answer that reliably. Please call 611 or use the MyTelecom app for help."
- Do not mention the context, documents, or these rules in your answer.

Context:
{context}"""

prompt = ChatPromptTemplate.from_messages([("system", SYSTEM_PROMPT), ("human", "{question}")])

_chain = None


def _get_chain():
    global _chain
    if _chain is None:
        if not os.getenv("GROQ_API_KEY"):
            raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        llm = ChatGroq(model=LLM_MODEL, temperature=0, reasoning_effort="none", max_tokens=500)
        _chain = prompt | llm | StrOutputParser()
    return _chain


def stream_answer(question: str):
    """Returns (docs, token_stream)."""
    docs = retrieve(question)
    stream = _get_chain().stream({"context": format_context(docs), "question": question})
    return docs, stream


def log_interaction(question: str, answer: str, docs, feedback: str | None = None):
    LOG_PATH.parent.mkdir(exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "answer": answer,
        "sources": [d.metadata["ref"] for d in docs],
        "feedback": feedback,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
