"""纯 Retrieval 指标骨架，不依赖模型、Chroma 或 Agent。

ChunkId 为 (document_id, chunk_index)，检索序列保留实际排名。
重复检索项仍占 Top-K 位置，相关 Chunk 与事实 ID 按唯一值计数。
空 Relevant 返回 None，优先于 K=0；k 应为非负整数。
"""

from collections.abc import Collection, Mapping, Sequence
from typing import TypeAlias


ChunkId: TypeAlias = tuple[str, int]


def hit_at_k(
    retrieved_chunks: Sequence[ChunkId],
    relevant_chunks: Collection[ChunkId],
    k: int,
) -> int | None:
    """返回前 K 位是否命中（1/0）；空 Relevant 返回 None。"""
    if k < 0:
        raise ValueError("k must be non-negative")
    if len(relevant_chunks) == 0:
        return None

    if k == 0:
        return 0

    for chunk in retrieved_chunks[:k]:
        if chunk in relevant_chunks:
            return 1

    return 0


def recall_at_k(
    retrieved_chunks: Sequence[ChunkId],
    relevant_chunks: Collection[ChunkId],
    k: int,
) -> float | None:
    """返回前 K 位对不同 Relevant 的覆盖比例；空 Relevant 返回 None。"""
    if k < 0:
        raise ValueError("k must be non-negative")
    if len(relevant_chunks) == 0:
        return None

    top_k = set(retrieved_chunks[:k])
    unique_relevant = set(relevant_chunks)

    hit_count = 0

    for chunk in top_k:
        if chunk in unique_relevant:
            hit_count += 1

    return hit_count/len(unique_relevant)


def reciprocal_rank_at_k(
    retrieved_chunks: Sequence[ChunkId],
    relevant_chunks: Collection[ChunkId],
    k: int,
) -> float | None:
    """返回前 K 位首次相关命中的排名倒数；未命中为 0，空 Relevant 为 None。"""
    if k < 0:
        raise ValueError("k must be non-negative")
    if len(relevant_chunks) == 0:
        return None

    for rank, chunk in enumerate(retrieved_chunks[:k], start=1):
        if chunk in relevant_chunks:
            return 1/rank

    return 0.0


def mean_reciprocal_rank(
    reciprocal_ranks: Sequence[float | None],
) -> float | None:
    """返回 RR 的均值，跳过 None；空输入或全部为 None 时返回 None。"""
    valid_scores = []

    for score in reciprocal_ranks:
        if score is not None:
            valid_scores.append(score)

    if len(valid_scores) == 0:
        return None

    return sum(valid_scores)/len(valid_scores)


def fact_coverage_at_k(
    retrieved_chunks: Sequence[ChunkId],
    required_facts: Collection[str],
    coverage_by_chunk: Mapping[ChunkId, Collection[str]],
    k: int,
) -> float | None:
    """返回前 K 位覆盖的必需事实比例；缺失映射无覆盖，空必需事实为 None。"""
    if k < 0:
        raise ValueError("k must be non-negative")
    if len(required_facts) == 0:
        return None

    covered_facts = set()

    for chunk in retrieved_chunks[:k]:
        facts = coverage_by_chunk.get(chunk, set())

        covered_facts.update(facts)

    return len(covered_facts & set(required_facts)) / len(set(required_facts))


def evidence_sufficient_at_k(
    retrieved_chunks: Sequence[ChunkId],
    required_facts: Collection[str],
    coverage_by_chunk: Mapping[ChunkId, Collection[str]],
    k: int,
) -> int | None:
    """返回前 K 位是否覆盖全部必需事实（1/0）；空必需事实返回 None。"""
    coverage = fact_coverage_at_k(
        retrieved_chunks,
        required_facts,
        coverage_by_chunk,
        k
    )

    if coverage is None:
        return None

    if coverage == 1.0:
        return 1

    return 0
