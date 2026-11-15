import csv

from langchain_core.documents import Document

from config import DATA_DIR, get_store


def main():
    with open(DATA_DIR / "faq.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    docs = [
        Document(
            page_content=f"Q: {r['question']}\nA: {r['answer']}",
            metadata={"source": "FAQ", "ref": f"FAQ-{r['id']}", "category": r["category"]},
        )
        for r in rows
    ]
    ids = [d.metadata["ref"] for d in docs]
    store = get_store("faq")
    store.reset_collection()
    store.add_documents(docs, ids=ids)
    print(f"Ingested {len(docs)} FAQ entries")


if __name__ == "__main__":
    main()
