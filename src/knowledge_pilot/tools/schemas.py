calculator_schema = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "执行基础数学计算",
        "parameters": {
            "type": "object",
            "properties": {
                "a": {
                    "type": "number"
                },
                "b": {
                    "type": "number"
                },
                "operation": {
                    "type": "string",
                    "enum": [
                        "add",
                        "subtract",
                        "multiply",
                        "divide"
                    ]
                }
            },
            "required": [
                "a",
                "b",
                "operation"
            ]
        }
    }
}
search_knowledge_base_schema = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": "从本地知识库中检索与用户问题相关的内容",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要在知识库中检索的用户问题或查询内容"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回相似度最高的前 K 个知识库片段"
                },
                "document_id": {
                    "type": "string",
                    "description": "可选，指定只在某个文档中进行检索的唯一文档标识"
                }
            },
            "required": ["query"]
        }
    }
}