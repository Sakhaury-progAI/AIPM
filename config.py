import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
CHROMA_DIR = ROOT / "chroma_store"
LOG_PATH = ROOT / "logs" / "interactions.jsonl"
AGENT_LOG_PATH = ROOT / "logs" / "agent.log"

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "qwen/qwen3.8-27b"
TOP_K = 3
HISTORY_EXCHANGES = 4

_embeddings = None


def get_llm(max_tokens: int = 500):
    from langchain_groq import ChatGroq

    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
    return ChatGroq(model=LLM_MODEL, temperature=0, reasoning_effort="none", max_tokens=max_tokens)


def get_logger():
    logger = logging.getLogger("telecom")
    if not logger.handlers:
        AGENT_LOG_PATH.parent.mkdir(exist_ok=True)
        fmt = logging.Formatter("%(asctime)s %(message)s")
        for handler in (logging.FileHandler(AGENT_LOG_PATH, encoding="utf-8"), logging.StreamHandler()):
            handler.setFormatter(fmt)
            logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        from langchain_huggingface import HuggingFaceEmbeddings

        _embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return _embeddings


def get_store(collection: str):
    from langchain_chroma import Chroma

    return Chroma(
        collection_name=collection,
        embedding_function=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )
