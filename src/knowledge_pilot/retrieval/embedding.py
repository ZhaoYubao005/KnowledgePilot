import requests
import math
from knowledge_pilot.errors import ModelResponseError
from knowledge_pilot.llm.transport import post_json
from knowledge_pilot.config import EMBEDDING_URL, EMBEDDING_MODEL
from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.similarity import cosine_similarity
def embed_text(text):
    url = EMBEDDING_URL

    payload = {
        "model": EMBEDDING_MODEL,
        "input": text
    }
    data = post_json(url, payload, operation='embedding', post=requests.post)
    vectors = data.get('embeddings')
    try:
        valid = (isinstance(vectors, list) and len(vectors) == 1
                 and isinstance(vectors[0], list) and bool(vectors[0])
                 and all(not isinstance(value, bool) and isinstance(value, (int, float))
                         and math.isfinite(value) for value in vectors[0]))
    except OverflowError:
        valid = False
    if not valid:
        raise ModelResponseError('embedding')
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
