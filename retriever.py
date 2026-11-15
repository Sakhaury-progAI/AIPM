from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document

from config import TOP_K, get_store

COLLECTIONS = ["faq", "tickets", "guides"]

_retrievers = None


def _get_retrievers():
    global _retrievers
    if _retrievers is None:
        _retrievers = {
            name: get_store(name).as_retriever(search_kwargs={"k": TOP_K})
            for name in COLLECTIONS
        }
    return _retrievers


def retrieve(question: str) -> list[Document]:
    retrievers = _get_retrievers()
    with ThreadPoolExecutor(len(retrievers)) as pool:
        results = pool.map(lambda r: r.invoke(question), retrievers.values())
    return [doc for docs in results for doc in docs]


def format_context(docs: list[Document]) -> str:
    return "\n\n".join(
        f"[{d.metadata['source']} | {d.metadata['ref']}]\n{d.page_content}" for d in docs
    )
