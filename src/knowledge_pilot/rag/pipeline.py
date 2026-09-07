from knowledge_pilot.retrieval.retriever import retrieve
from knowledge_pilot.rag.prompt_builder import build_prompt, build_context
from knowledge_pilot.llm.ollama_client import chat_with_ollama
from knowledge_pilot.config import SYSTEM_PROMPT
from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.embedding import embed_chunks


# 定义函数
def answer_with_rag(
    query,
    chunks,
    chunk_embeddings,
    top_k=3,
    threshold=0.4,
):
    top_results = retrieve(query, chunks, chunk_embeddings, top_k)
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
    file_path = "data/v04_long_test.txt"

    text = load_text(file_path)
    chunks = chunk_text(text, 500, 100)
    chunk_embeddings = embed_chunks(chunks)

    query = "爱因斯坦出生在哪里？"

    answer = answer_with_rag(
        query,
        chunks,
        chunk_embeddings,
        top_k=3,
    )

    print(answer)
