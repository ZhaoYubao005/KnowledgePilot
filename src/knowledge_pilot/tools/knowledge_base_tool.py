from knowledge_pilot.vector_store.chroma_store import collection, search


def search_knowledge_base(query, top_k=3, document_id=None):
    results = search(
        query,
        collection,
        top_k=top_k,
        document_id=document_id
    )

    formatted_results = []

    for chunk, score, metadata in results:
        # 这里整理每一条检索结果
        formatted_results.append({
            "content":chunk,
            "source":metadata.get("source")
        })

    return formatted_results
if __name__ == "__main__":
    results = search_knowledge_base(
        query="什么是机器学习",
        top_k=3
    )

    print(results)
