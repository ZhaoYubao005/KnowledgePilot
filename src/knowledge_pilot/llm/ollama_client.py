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


def chat_with_ollama(messages,max_steps=5):
    trace=[]
    for step in range(max_steps):

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
        assistant_message = data["message"]
        tool_calls = assistant_message.get("tool_calls")


        #stop condition(停止条件):
        #模型没有继续请求tool,说明可以直接返回最终答案
        if not tool_calls:
            stop_reason = "completed"

            return {
                "answer": assistant_message["content"],
                "trace": trace,
                "stop_reason": stop_reason
            }
        #保存本轮模型产生的tool call
        messages.append(assistant_message)
        # 处理当前这一轮的所有 Tool Call
        for tool_call in tool_calls:
            function = tool_call.get("function", {})

            tool_name = function.get("name")
            arguments = function.get("arguments")

            safe_tool_name = tool_name or "unknown_tool"
            # Action（动作）：
            # 模型决定执行的 Tool，并由 Python 真正执行
            try:
                if not tool_name:
                    raise ValueError("Tool call missing function.name")

                if arguments is None:
                    raise ValueError("Tool call missing function.arguments")

                result = execute_tool_call(tool_call)

            except Exception as e:
                result = f"Tool execution failed: {e}"

            trace.append({
                "step": step + 1,
                "tool": safe_tool_name,
                "arguments": arguments,
                "result": result
            })

            # Observation（观察结果）：
            # Tool 执行后得到的结果，写回 messages 给下一轮模型参考
            messages.append({
                "role": "tool",
                "tool_name": safe_tool_name,
                "content": str(result)
            })

        # 当前轮完成，回到 Agent Loop 进行下一次 Decision


        # max_steps（最大步数）：
        # 超过最大 Agent 决策轮数仍未结束，强制终止
    stop_reason = "max_steps"

    return {
        "answer": "Agent 达到最大步骤限制，任务未能在规定步骤内完成。",
        "trace": trace,
        "stop_reason": stop_reason
    }




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

        agent_result = chat_with_ollama(history)


        assistant_reply = str(agent_result["answer"])

        history.append({
            "role": "assistant",
            "content": assistant_reply,
        })

        print(assistant_reply)