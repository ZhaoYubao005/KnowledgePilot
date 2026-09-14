from knowledge_pilot.vector_store.chroma_store import search, collection
from knowledge_pilot.rag.prompt_builder import build_prompt, build_context
from knowledge_pilot.llm.ollama_client import chat_with_ollama
from knowledge_pilot.config import SYSTEM_PROMPT


# 定义函数
def answer_with_rag(
    query,
    collection,
    top_k=3,
    threshold=0.4,
    document_id=None,
):
    top_results = search(
        query,
        collection,
        top_k,
        document_id=document_id,
    )
    filtered_results = []
    for chunk, score, metadata in top_results:
        if score >= threshold:
            filtered_results.append((chunk, score, metadata))

    if not filtered_results:
        return "参考资料不足，无法根据当前知识库回答这个问题。", []

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
    agent_result = chat_with_ollama(messages)
    answer = agent_result["answer"]
    sources = build_sources(filtered_results)
    return answer, sources


# 定义来源函数
def build_sources(results):
    sources = []
    for _chunk, _score, metadata in results:
        sources.append(metadata)
    return sources


if __name__ == "__main__":
    answer, sources = answer_with_rag(
        "什么是机器学习？",
        collection,
        top_k=3,
        document_id="v08_second_test",
    )

    print("answer:", answer)
    print("sources:", sources)
