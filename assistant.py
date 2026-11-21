"""Routes each message to the existing RAG pipeline or the Refund Agent and keeps session history."""

from dataclasses import dataclass, field

from chain import stream_answer
from config import HISTORY_EXCHANGES, get_logger
from intent import REFUND_REQUEST, REQUIREMENT_INQUIRY, classify
from refund_agent import RefundAgent
from refund_data import RefundStore


@dataclass
class Reply:
    route: str
    text: str | None = None
    stream: object = None
    docs: list = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    confirm_amount: float | None = None


class Assistant:
    def __init__(self, store: RefundStore | None = None):
        self.logger = get_logger()
        self.agent = RefundAgent(store or RefundStore())
        self.history: list[dict] = []

    def recent_history(self) -> list[dict]:
        return self.history[-2 * HISTORY_EXCHANGES:]

    def remember(self, user_text: str, assistant_text: str):
        self.history += [{"role": "user", "content": user_text},
                         {"role": "assistant", "content": assistant_text}]

    def reset(self):
        self.history = []
        self.agent.reset()

    def handle(self, message: str) -> Reply:
        history = self.recent_history()
        if self.agent.is_active:
            intent = REFUND_REQUEST
            self.logger.info(f"[Intent] {intent} (continuing {self.agent.state})")
        else:
            intent = classify(message, history)
            self.logger.info(f"[Intent] {intent}")

        if intent == REQUIREMENT_INQUIRY:
            docs, stream = stream_answer(message, history)
            return Reply(route="rag", stream=stream, docs=docs, steps=[f"[Intent] {intent}"])

        reply = self.agent.handle(message, history)
        return Reply(route="agent", text=reply.text, confirm_amount=reply.confirm_amount,
                     steps=[f"[Intent] {intent}"] + reply.steps)

    def confirm(self) -> Reply:
        reply = self.agent.confirm()
        return Reply(route="agent", text=reply.text, steps=reply.steps)

    def cancel(self) -> Reply:
        reply = self.agent.cancel()
        return Reply(route="agent", text=reply.text, steps=reply.steps)
