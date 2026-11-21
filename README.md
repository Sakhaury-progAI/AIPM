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

## Refund agent (see `agent_PRD.md`)

Each message is classified as `requirement_inquiry` (answered by the RAG pipeline) or `refund_request` (handled by the Refund Agent).

- `intent.py`: LLM intent classifier, with a keyword fallback if the LLM is unavailable.
- `refund_data.py`: hard-coded demo account `user_123` with ₹999 and ₹499 recharges. Each chat session gets its own copy.
- `refund_tools.py`: `get_user_account`, `validate_refund`, `process_refund` (simulated) and `submit_to_support`. All eligibility rules live here.
- `refund_agent.py`: the LLM can only call `get_user_account` and `validate_refund`. Code decides what happens next: refunds of ₹499 or less wait for **Confirm Refund**; larger ones go to the Support Team.
- `assistant.py`: routes messages and keeps the last 4 exchanges of history for both routes.

Workflow steps are logged to `logs/agent.log` and shown under **Agent steps** in the UI. Run the rule tests with `.venv/bin/python tests/test_refund.py`.

## Updating knowledge

Edit the source file, then re-run its ingest script (`ingest_faq.py`, `ingest_tickets.py`, `ingest_guides.py`). Re-runs replace the collection, so they are idempotent. To add a new source, write an `ingest_*.py` and add its collection name to `COLLECTIONS` in `retriever.py`.

Interactions and 👍/👎 feedback are logged to `logs/interactions.jsonl`.
