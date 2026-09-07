from knowledge_pilot.vector_store.chroma_store import search, collection
from knowledge_pilot.rag.prompt_builder import build_prompt, build_context
from knowledge_pilot.llm.ollama_client import chat_with_ollama
from knowledge_pilot.config import SYSTEM_PROMPT


# 定义函数
def answer_with_rag(query, collection, top_k=3, threshold=0.4):
    top_results = search(
        query,
        collection,
        top_k,
    )
    filtered_results = []
    for chunk, score in top_results:
        if score >= threshold:
            filtered_results.append((chunk, score))
        if not filtered_results:
            return "参考资料不足，无法根据当前知识库回答这个问题。"
    context = build_context(filtered_results)
    prompt = build_prompt(context, query)
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": prompt,
        },
    ]
    answer = chat_with_ollama(messages)
    return answer


if __name__ == "__main__":
    query = "什么是机器学习？"

    answer = answer_with_rag(
        query,
        collection,
        top_k=3,
    )

    print(answer)
