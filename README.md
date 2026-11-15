# Telecom Support RAG Chatbot

Answers Tier-1 telecom questions grounded only in `data/faq.csv`, `data/tickets.db` and `data/*.pdf`. See `PRD.md`.

## Setup

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env   # then add your GROQ_API_KEY
.venv/bin/python ingest_all.py
```

## Run

```bash
.venv/bin/streamlit run app.py   # browser UI
.venv/bin/python main.py         # CLI (type quit to exit)
```

## Updating knowledge

Edit the source file, then re-run its ingest script (`ingest_faq.py`, `ingest_tickets.py`, `ingest_guides.py`). Re-runs replace the collection, so they are idempotent. To add a new source, write an `ingest_*.py` and add its collection name to `COLLECTIONS` in `retriever.py`.

Interactions and 👍/👎 feedback are logged to `logs/interactions.jsonl`.
