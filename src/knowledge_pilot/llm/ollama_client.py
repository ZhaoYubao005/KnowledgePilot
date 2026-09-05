import requests


url = 'http://localhost:11434/api/chat'

history = [{
    'role': 'system',
    'content': '你是智库，一个结合生活与学习知识的助手。回答应清晰、简洁。对于不确定的信息要明确说明，不要编造。当用户询问你的身份或名字时，以“智库”的身份回答。'
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
