from assistant import Assistant
from chain import log_interaction


def main():
    assistant = Assistant()
    print("Telecom Support Assistant (type 'quit' to exit, 'clear' to reset)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() == "quit":
            break
        if question.lower() == "clear":
            assistant.reset()
            print("Conversation cleared.\n")
            continue
        if not question:
            continue
        reply = assistant.handle(question)
        print("Bot: ", end="", flush=True)
        if reply.stream is not None:
            answer = ""
            for token in reply.stream:
                answer += token
                print(token, end="", flush=True)
            print("\nSources: " + ", ".join(d.metadata["ref"] for d in reply.docs))
        else:
            answer = reply.text
            print(answer)
            if reply.confirm_amount is not None:
                print('(Reply "Yes, proceed" to confirm or "No" to cancel.)')
        print()
        assistant.remember(question, answer)
        log_interaction(question, answer, reply.docs, route=reply.route)


if __name__ == "__main__":
    main()
