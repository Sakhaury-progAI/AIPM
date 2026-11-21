import streamlit as st

from assistant import Assistant
from chain import log_interaction

SAMPLE_QUESTIONS = [
    "Why is my mobile internet so slow?",
    "How do I activate roaming before travelling abroad?",
    "My eSIM won't activate. How do I fix it?",
    "I want a refund of ₹499.",
    "I want a refund of ₹999.",
    "I want a refund.",
]

SOURCE_ICONS = {"FAQ": "📘", "TICKET": "🎫", "GUIDE": "📄"}

st.set_page_config(page_title="Telecom Support Assistant", page_icon="📶")

if "assistant" not in st.session_state:
    st.session_state.assistant = Assistant()
if "messages" not in st.session_state:
    st.session_state.messages = []

assistant: Assistant = st.session_state.assistant


def add_exchange(user_text, reply, answer):
    assistant.remember(user_text, answer)
    log_interaction(user_text, answer, reply.docs, route=reply.route)
    st.session_state.messages += [
        {"role": "user", "content": user_text},
        {"role": "assistant", "content": answer, "question": user_text, "route": reply.route,
         "sources": [{"source": d.metadata["source"], "ref": d.metadata["ref"], "content": d.page_content}
                     for d in reply.docs],
         "steps": reply.steps, "confirm_amount": reply.confirm_amount, "feedback": None},
    ]


def render_sources(sources):
    with st.expander(f"Sources ({len(sources)})"):
        for d in sources:
            st.markdown(f"**{SOURCE_ICONS.get(d['source'], '')} {d['source']} · {d['ref']}**")
            st.caption(d["content"])


def render_feedback(idx):
    msg = st.session_state.messages[idx]
    choice = st.feedback("thumbs", key=f"fb_{idx}")
    if choice is not None and msg.get("feedback") is None:
        msg["feedback"] = "up" if choice == 1 else "down"
        log_interaction(msg["question"], msg["content"], [], msg["feedback"], route=msg["route"])


def on_button(action):
    reply = assistant.confirm() if action == "confirm" else assistant.cancel()
    add_exchange("Yes, proceed." if action == "confirm" else "No, cancel.", reply, reply.text)


with st.sidebar:
    st.header("Try a question")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state.pending = q
    st.divider()
    if st.button("Clear conversation", type="primary", use_container_width=True):
        st.session_state.messages = []
        assistant.reset()
        st.rerun()
    st.caption("Answers come only from our FAQ, resolved tickets and guides. "
               "Refunds in this demo are simulated for the signed-in demo account.")

st.title("📶 Telecom Support Assistant")

messages = st.session_state.messages
for i, m in enumerate(messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] != "assistant":
            continue
        if m["sources"]:
            render_sources(m["sources"])
        if m["route"] == "agent" and m["steps"]:
            with st.expander("Agent steps"):
                st.code("\n".join(m["steps"]), language=None)
        is_last = i == len(messages) - 1
        if is_last and m["confirm_amount"] is not None and assistant.agent.state == "awaiting_confirmation":
            left, right = st.columns(2)
            left.button("Confirm Refund", type="primary", use_container_width=True,
                        on_click=on_button, args=("confirm",), key=f"confirm_{i}")
            right.button("Cancel", use_container_width=True,
                         on_click=on_button, args=("cancel",), key=f"cancel_{i}")
        render_feedback(i)

question = st.chat_input("Ask about data, billing, SIM, roaming, or request a refund…")
question = question or st.session_state.pop("pending", None)

if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Working on it…"):
                reply = assistant.handle(question)
            if reply.stream is not None:
                answer = st.write_stream(reply.stream)
            else:
                answer = reply.text
                st.markdown(answer)
        except Exception as e:
            st.error(f"Sorry, something went wrong: {e}")
            st.stop()
    add_exchange(question, reply, answer)
    st.rerun()
