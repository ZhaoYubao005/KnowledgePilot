"""Retrieval Evidence Collector 最小脚手架。

仅定义候选记录契约；核心转换由用户实现。本模块只依赖标准库。
"""

from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias, TypedDict


# chroma_store.search() 的单条有序结果；metadata 至少包含 Chunk 身份。
SearchResult: TypeAlias = tuple[str, float, Mapping[str, Any]]


class CandidateRecord(TypedDict):
    """独立候选记录；rank 从 1 开始，chunk_index 沿用原值。"""

    document_id: str
    chunk_index: int
    rank: int
    text: str
    similarity: float


def collect_candidates(
    results: Sequence[SearchResult]
) -> list[CandidateRecord]:

    records: list[CandidateRecord] = []

    for rank, (text, similarity, metadata) in enumerate(results, start=1):

        record: CandidateRecord = {
            "document_id": metadata["document_id"],
            "chunk_index": metadata["chunk_index"],
            "rank": rank,
            "text": text,
            "similarity": similarity
        }

        records.append(record)

    return records
