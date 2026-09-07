"""Similarity helpers for retrieval."""
import math
def cosine_similarity(a,b):
    #加入限制条件
    if len(a) != len(b):
        raise ValueError("Vectors must have the same dimension")

    #计算点积

    sum_squares = 0

    for i in a:
        sum_squares += i ** 2

    norm_a = math.sqrt(sum_squares)
    dot_product = sum(x*y for x,y in zip(a,b))
    # print(dot_product)
    sum_squares_b = 0

    for m in b:
        sum_squares_b += m ** 2

    norm_b = math.sqrt(sum_squares_b)
    #计算
    return dot_product / (norm_a * norm_b)
#测试
if __name__ == "__main__":
    # a = [1, 0]
    # b = [2, 0]
    #
    # result = cosine_similarity(a, b)
    # print(result)

    query = [1, 0]

    chunks = [
        ("Chunk C", [0, 1]),
        ("Chunk A", [1, 0]),
        ("Chunk B", [1, 1]),
    ]
    results = []

    for name, vector in chunks:
        score = cosine_similarity(query, vector)
        results.append((name, score))

    print(results)
    results.sort(key=lambda x: x[1], reverse=True)
    print(results)
    top_k = 2
    top_results = results[:top_k]
    print(top_results)