# 将 chunk 封装进 context

def build_context(top_results):
    context = ""
    for chunk, score in top_results:
        context += chunk + "\n\n"

    return context


# RAG 检索以及回复用户问题
def build_prompt(context, query):
    prompt = f"""
    【参考资料】
    {context}

    【用户问题】
    {query}

    请根据参考资料回答。
    如果参考资料不足以回答，请明确说明资料不足。
"""
    return prompt
