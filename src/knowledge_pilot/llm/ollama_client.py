import requests


url = 'http://localhost:11434/api/chat'

history = [{
    'role': 'system',
    'content': '你的应用身份叫“智库”。当用户询问“你是谁、你叫什么名字”时，应以“智库”的身份回答。底层模型只是实现技术，不作为默认身份主动介绍。'
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
        'model': 'gemma4:e2b',
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
