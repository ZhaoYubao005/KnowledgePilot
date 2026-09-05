import requests
from knowledge_pilot.config import OLLAMA_URL, MODEL_NAME, SYSTEM_PROMPT

url = OLLAMA_URL

history = [{
    'role': 'system',
    'content': SYSTEM_PROMPT
}]

while True:
    user_input = input('你:')

    if user_input == 'exit':
        break

    history.append({
        'role': 'user',
        'content': user_input
    })

    payload = {
        'model': MODEL_NAME,
        'messages': history,
        'stream': False
    }

    response = requests.post(url, json=payload)
    data = response.json()
    assistant_reply = data['message']['content']

    history.append({
        'role': 'assistant',
        'content': assistant_reply
    })
    print(assistant_reply)
