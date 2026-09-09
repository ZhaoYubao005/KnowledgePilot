import chromadb
from chromadb.api.collection_configuration import (
    CreateCollectionConfiguration,
    CreateHNSWConfiguration,
)

from knowledge_pilot.document.text_loader import load_text, chunk_text
from knowledge_pilot.retrieval.embedding import embed_chunks, embed_text

# 使用余弦距离配置 HNSW 索引
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

# V0.8 文档入库
def ingest_document(file_path, document_id, collection):
    text = load_text(file_path)
    chunks = chunk_text(
        text,
        chunk_size=500,
        overlap=100,
    )
    chunk_embeddings = embed_chunks(chunks)
    ids = []
    metadatas = []
    for i, chunk in enumerate(chunks):
        ids.append(f"{document_id}_chunk_{i}")
        metadatas.append(
            {
                "document_id": document_id,
                "source": file_path,
                "chunk_index": i,
            }
        )
    # 批量写入 Chroma
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=chunk_embeddings,
        metadatas=metadatas,
    )


# V0.8 删除文档
def delete_document(document_id, collection):
    collection.delete(
        where={"document_id": document_id}
    )


# V0.8 更新文档
def update_document(file_path, document_id, collection):
    delete_document(document_id, collection)
    ingest_document(file_path, document_id, collection)


# 构建函数搜索；匹配用户向量
def search(query, collection, top_k=3, document_id=None):
    query_vector = embed_text(query)
    # V0.8 按 document_id 过滤检索范围
    where_filter = None

    if document_id is not None:
        where_filter = {
            "document_id": document_id
        }

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
        where=where_filter,
    )
    documents = results["documents"][0]
    distances = results["distances"][0]
    metadatas = results["metadatas"][0]
    top_results = []
    for document, distance, metadata in zip(
        documents,
        distances,
        metadatas,
    ):
        similarity = 1 - distance
        top_results.append((document, similarity, metadata))

    return top_results


# 使用真实文档做最小检索验证
if __name__ == "__main__":
    results = search(
        "什么是反向传播？",
        collection,
        top_k=3,
        document_id="v08_second_test",
    )

    print(results)
