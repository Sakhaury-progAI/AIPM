import streamlit as st

from chain import log_interaction, stream_answer

SAMPLE_QUESTIONS = [
    "Why is my mobile internet so slow?",
    "I was charged twice on my bill. What should I do?",
    "How do I activate roaming before travelling abroad?",
    "My eSIM won't activate. How do I fix it?",
    "My calls keep dropping. What should I do?",
    "I can't log in to the MyTelecom app.",
]

SOURCE_ICONS = {"FAQ": "📘", "TICKET": "🎫", "GUIDE": "📄"}

st.set_page_config(page_title="Telecom Support Assistant", page_icon="📶")

if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(docs):
    with st.expander(f"Sources ({len(docs)})"):
        for d in docs:
            src = d["source"]
            st.markdown(f"**{SOURCE_ICONS.get(src, '')} {src} · {d['ref']}**")
            st.caption(d["content"])


def render_feedback(idx):
    msg = st.session_state.messages[idx]
    choice = st.feedback("thumbs", key=f"fb_{idx}")
    if choice is not None and msg.get("feedback") is None:
        msg["feedback"] = "up" if choice == 1 else "down"
        log_interaction(msg["question"], msg["content"], msg["docs_raw"], msg["feedback"])


with st.sidebar:
    st.header("Try a question")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state.pending = q
    st.divider()
    if st.button("Clear conversation", type="primary", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption("Answers come only from our FAQ, resolved tickets and guides. "
               "For account-specific help, call 611 or use the MyTelecom app.")

st.title("📶 Telecom Support Assistant")

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            render_sources(m["sources"])
            render_feedback(i)

question = st.chat_input("Ask about data, billing, SIM, roaming, calls…")
question = question or st.session_state.pop("pending", None)

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching knowledge base…"):
                docs, stream = stream_answer(question)
            answer = st.write_stream(stream)
        except Exception as e:
            st.error(f"Sorry, something went wrong: {e}")
            st.stop()
        sources = [{"source": d.metadata["source"], "ref": d.metadata["ref"], "content": d.page_content}
                   for d in docs]
        log_interaction(question, answer, docs)
    st.session_state.messages.append({
        "role": "assistant", "content": answer, "sources": sources,
        "question": question, "docs_raw": docs, "feedback": None,
    })
    st.rerun()
