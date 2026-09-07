import requests
from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.similarity import cosine_similarity
def embed_text(text):
    url = "http://localhost:11434/api/embed"

    payload = {
        "model": "bge-m3",
        "input": text
    }
    response = requests.post(url, json=payload)
    data = response.json()
    return data["embeddings"][0]

def embed_chunks(chunks):
    chunk_embeddings = []

    for chunk in chunks:
        vector = embed_text(chunk)
        chunk_embeddings.append(vector)

    return chunk_embeddings

# #测试
# if __name__ == "__main__":
#     vector = embed_text("机器学习是什么")
#
#     print(vector)
#     print(len(vector))

if __name__ == "__main__":
    file_path = "data/v04_long_test.txt"

    text = load_text(file_path)

    chunks = chunk_text(text, 500, 100)

    vectors = embed_chunks(chunks)
    query = "什么是机器学习？"

    query_vector = embed_text(query)


    print(len(chunks))
    print(len(vectors))
    print(len(query_vector))
    print(len(vectors[0]))
    results = []

    for chunk, vector in zip(chunks, vectors):
        score = cosine_similarity(query_vector, vector)
        results.append((chunk, score))
    results.sort(key=lambda x: x[1], reverse=True)

    top_k = 3
    top_results = results[:top_k]
    for chunk, score in top_results:
        print(score)
        print(chunk)
        print("-" * 50)