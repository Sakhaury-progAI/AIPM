import sqlite3

from langchain_core.documents import Document

from config import DATA_DIR, get_store


def main():
    con = sqlite3.connect(DATA_DIR / "tickets.db")
    rows = con.execute(
        "SELECT ticket_id, category, issue_type, description, resolution "
        "FROM tickets WHERE status = 'resolved'"
    ).fetchall()
    con.close()
    docs = [
        Document(
            page_content=f"Issue ({cat} / {issue}): {desc}\nResolution: {res}",
            metadata={"source": "TICKET", "ref": tid, "category": cat},
        )
        for tid, cat, issue, desc, res in rows
    ]
    store = get_store("tickets")
    store.reset_collection()
    store.add_documents(docs, ids=[d.metadata["ref"] for d in docs])
    print(f"Ingested {len(docs)} resolved tickets")


if __name__ == "__main__":
    main()
