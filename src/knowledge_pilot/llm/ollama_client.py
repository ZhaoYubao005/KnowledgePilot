#代码实现
import requests
#接口
url = 'http://localhost:11434/api/chat'
#进入对话

#构建历史对话
history = []


#建造循环

while True:

    #修改问答方式,让用户直接输入来对话
    user_input = input('你:')
    #建造循环
    if user_input == 'exit':
        break
    #保存用户对话
    history.append({
        'role': 'user',
        'content': user_input
    })

    payload = {
        'model': 'gemma4:e2b',
        'messages': history,
        'stream': False
    }

    #计入对话
    response = requests.post(url,json=payload)

    #提取json格式
    data = response.json()

    #提取对话
    assistant_reply = data['message']['content']
    # 问题加入history

    history.append({
        'role': 'assistant',
        'content': assistant_reply
    })
    #显示对话
    print(assistant_reply)


