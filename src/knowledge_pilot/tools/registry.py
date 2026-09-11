import json
from knowledge_pilot.tools.calculator import calculator
from knowledge_pilot.tools.knowledge_base_tool import search_knowledge_base
TOOL_REGISTRY = {
    "calculator": calculator,
    "search_knowledge_base": search_knowledge_base
}
def execute_tool(name,arguments):
    if name not in TOOL_REGISTRY:
        raise ValueError("工具不存在")
    tool = TOOL_REGISTRY[name]
    return tool(**arguments)
def execute_tool_call(tool_call):
    function = tool_call["function"]
    name = function["name"]
    arguments = function["arguments"]

    if isinstance(arguments,str):
        arguments = json.loads(arguments)

    return execute_tool(name, arguments)

#测试
if __name__ == "__main__":
    tool_call = {
        "function": {
            "name": "search_knowledge_base",
            "arguments": {
                "query": "什么是机器学习",
                "top_k": 3
            }
        }
    }

    result = execute_tool_call(tool_call)

    print(result)
