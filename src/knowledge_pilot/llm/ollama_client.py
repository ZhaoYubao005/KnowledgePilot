import requests
from knowledge_pilot.config import (
    OLLAMA_URL,
    MODEL_NAME,
    SYSTEM_PROMPT
)
from knowledge_pilot.tools.schemas import (
    calculator_schema,
    search_knowledge_base_schema
)
from knowledge_pilot.tools.registry import execute_tool_call

url = OLLAMA_URL


def chat_with_ollama(messages):
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools":[calculator_schema,
                 search_knowledge_base_schema
                 ],
        "stream": False,
    }
    response = requests.post(url, json=payload)
    data = response.json()

    tool_calls = data["message"].get("tool_calls")

    if tool_calls:
        tool_call = tool_calls[0]
        result = execute_tool_call(tool_call)


        messages.append(data["message"])

        messages.append({
            "role": "tool",
            "tool_name": tool_call["function"]["name"],
            "content": str(result)
        })

        final_payload = {
            "model": MODEL_NAME,
            "messages": messages,
            "stream": False
        }

        final_response = requests.post(url, json=final_payload)
        final_data = final_response.json()

        return final_data["message"]["content"]

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