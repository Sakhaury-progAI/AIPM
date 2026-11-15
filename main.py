from chain import log_interaction, stream_answer


def main():
    print("Telecom Support Assistant (type 'quit' to exit)\n")
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() == "quit":
            break
        if not question:
            continue
        docs, stream = stream_answer(question)
        print("Bot: ", end="", flush=True)
        answer = ""
        for token in stream:
            answer += token
            print(token, end="", flush=True)
        print("\nSources: " + ", ".join(d.metadata["ref"] for d in docs) + "\n")
        log_interaction(question, answer, docs)


if __name__ == "__main__":
    main()
