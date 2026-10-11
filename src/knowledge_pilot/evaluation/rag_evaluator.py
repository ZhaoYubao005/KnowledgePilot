
from knowledge_pilot.evaluation.rag_metrics import (
    hit_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
    fact_coverage_at_k,
    evidence_sufficient_at_k,
)


def evaluate_retrieval_case(case, results, k):
    # Step 1：转换 Chroma 检索结果
    retrieved_chunks = []

    for chunk_text, similarity, metadata in results:
        chunk_id = (
            metadata["document_id"],
            metadata["chunk_index"]
        )
        retrieved_chunks.append(chunk_id)

    # Step 2：转换 Dataset Ground Truth
    relevant_chunks = set()

    for item in case["relevant_chunks"]:
        chunk_id = (
            item["document_id"],
            item["chunk_index"]
        )
        relevant_chunks.add(chunk_id)

    # Step 3：计算三个基础指标
    hit = hit_at_k(retrieved_chunks, relevant_chunks, k)
    recall = recall_at_k(retrieved_chunks, relevant_chunks, k)
    rr = reciprocal_rank_at_k(retrieved_chunks, relevant_chunks, k)

    # Step 4：Multi-Chunk 评分
    fact_coverage = None
    evidence_sufficient = None

    if case.get("category") == "multi_chunk":
        required_facts = set(case["required_facts"].keys())

        coverage_by_chunk = {}

        for item in case["coverage_by_chunk"]:
            chunk_id = (
                item["document_id"],
                item["chunk_index"]
            )
            coverage_by_chunk[chunk_id] = set(item["covered_facts"])

        fact_coverage = fact_coverage_at_k(
            retrieved_chunks,
            required_facts,
            coverage_by_chunk,
            k
        )

        evidence_sufficient = evidence_sufficient_at_k(
            retrieved_chunks,
            required_facts,
            coverage_by_chunk,
            k
        )

    # Step 5：返回评测结果
    return {
        "case_id": case["id"],
        "hit": hit,
        "recall": recall,
        "rr": rr,
        "fact_coverage": fact_coverage,
        "evidence_sufficient": evidence_sufficient,
    }
