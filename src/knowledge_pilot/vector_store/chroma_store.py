import chromadb

from knowledge_pilot.retrieval.embedding import embed_text
from chromadb.api.collection_configuration import (
    CreateCollectionConfiguration,
    CreateHNSWConfiguration,
)
from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.embedding import embed_chunks

# 解决警报
hnsw_config = CreateHNSWConfiguration(
    space="cosine"
)

collection_config = CreateCollectionConfiguration(
    hnsw=hnsw_config
)

# 将数据保存在磁盘
client = chromadb.PersistentClient(
    path="data/vector_store"
)

# 创建 collection
collection = client.get_or_create_collection(
    name="knowledge_pilot_docs",
    embedding_function=None,
    configuration=collection_config,
)


# 构建函数文档更新
def build_index(file_path, collection):
    text = load_text(file_path)

    chunks = chunk_text(
        text,
        chunk_size=500,
        overlap=100,
    )

    chunk_embeddings = embed_chunks(chunks)
    metadatas = []
    ids = []

    for i, chunk in enumerate(chunks):
        ids.append(f"v04_long_test_chunk_{i}")

        metadatas.append({
            "document_id": "v04_long_test",
            "source": "v04_long_test.txt",
            "chunk_index": i,
        })
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=chunk_embeddings,
        metadatas=metadatas,
    )


# 构建函数搜索；匹配用户向量
def search(query, collection, top_k=3):
    query_vector = embed_text(query)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
    documents = results["documents"][0]
    distances = results["distances"][0]
    top_results = []
    for document, distance in zip(documents, distances):
        similarity = 1 - distance
        top_results.append((document, similarity))

    return top_results


# 使用真实文档验证索引构建
if __name__ == "__main__":
    file_path = "data/v04_long_test.txt"

    build_index(
        file_path,
        collection,
    )

    print("Collection 数量:", collection.count())
