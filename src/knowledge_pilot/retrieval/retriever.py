#封装

#导入包
from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.embedding import embed_chunks
from knowledge_pilot.retrieval.embedding import embed_text
from knowledge_pilot.retrieval.similarity import cosine_similarity

def retrieve(query, chunks, chunk_embeddings, top_k=3):
    query_vector = embed_text(query)
    results = []
    #相似度对比
    for chunk,vector in zip(chunks,chunk_embeddings):
        score = cosine_similarity(query_vector,vector)
        results.append((chunk,score))
        #取向量,排序
    results.sort(key=lambda x: x[1],reverse=True)
    top_results = results[:top_k]
    return top_results

#测试
if __name__ == "__main__":
    file_path = "data/v04_long_test.txt"

    text = load_text(file_path)
    chunks = chunk_text(text, 500, 100)
    chunk_embeddings = embed_chunks(chunks)

    top_results = retrieve(
        "什么是机器学习？",
        chunks,
        chunk_embeddings,
        top_k=3
    )

    for chunk, score in top_results:
        print(score)
        print(chunk)
        print("-" * 50)