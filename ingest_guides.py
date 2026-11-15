from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from config import DATA_DIR, get_store


def main():
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    docs = []
    for pdf in sorted(DATA_DIR.glob("*.pdf")):
        for page_no, page in enumerate(PdfReader(pdf).pages, start=1):
            text = page.extract_text() or ""
            for i, chunk in enumerate(splitter.split_text(text)):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={"source": "GUIDE", "ref": f"{pdf.stem} p{page_no} #{i + 1}"},
                    )
                )
    store = get_store("guides")
    store.reset_collection()
    store.add_documents(docs, ids=[d.metadata["ref"] for d in docs])
    print(f"Ingested {len(docs)} guide chunks")


if __name__ == "__main__":
    main()
