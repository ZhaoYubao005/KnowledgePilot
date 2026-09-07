import requests

from knowledge_pilot.config import OLLAMA_URL, MODEL_NAME, SYSTEM_PROMPT


url = OLLAMA_URL


def chat_with_ollama(messages):
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
    }
    response = requests.post(url, json=payload)
    data = response.json()

    return data["message"]["content"]


if __name__ == "__main__":
    history = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    while True:
        user_input = input("你:")

        if user_input == "exit":
            break

        history.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        assistant_reply = chat_with_ollama(history)

        history.append(
            {
                "role": "assistant",
                "content": assistant_reply,
            }
        )

        print(assistant_reply)
