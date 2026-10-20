"""Independent V1.3 rank fusion; imports no model or database client."""
from collections.abc import Callable, Sequence
from copy import deepcopy
import math
import time
from typing import Literal, TypedDict

from knowledge_pilot.evaluation.bm25 import BM25Candidate
from knowledge_pilot.evaluation.evidence_collector import SearchResult


class RetrievalError(RuntimeError):
    """Expected service failure, explicitly raised by a retrieval adapter."""
    def __init__(self, message: str, *, stage: str = 'retrieval'):
        super().__init__(message)
        self.stage = stage


class BranchCandidate(TypedDict):
    document_id: str
    chunk_index: int
    text: str
    source: str | None
    rank: int
    score: float
    score_type: str


class HybridCandidate(TypedDict):
    document_id: str
    chunk_index: int
    text: str
    source: str | None
    rank: int
    score: float
    score_type: Literal['rrf']
    sources: list[str]
    dense_similarity: float | None
    dense_score_type: str | None
    dense_rank: int | None
    bm25_score: float | None
    bm25_score_type: str | None
    bm25_rank: int | None
    dense_rrf_contribution: float
    bm25_rrf_contribution: float


class BranchEvidence(TypedDict):
    status: Literal['success', 'empty', 'failed']
    latency_ms: float
    error_stage: str | None
    error: str | None
    candidates: list[BranchCandidate]


class HybridResult(TypedDict):
    mode: Literal['full_hybrid', 'fallback_dense', 'fallback_bm25', 'retrieval_failed']
    branches: dict[str, BranchEvidence]
    candidates: list[HybridCandidate]


def adapt_dense_results(results: Sequence[SearchResult]) -> list[BranchCandidate]:
    """Preserve actual Dense order and raw similarity, including negative values."""
    return [dict(document_id=metadata['document_id'], chunk_index=metadata['chunk_index'],
                 text=text, source=metadata.get('source'), rank=rank,
                 score=similarity, score_type='cosine_similarity')
            for rank, (text, similarity, metadata) in enumerate(results, 1)]


def _validate(candidates: Sequence[BranchCandidate] | Sequence[BM25Candidate]) -> None:
    seen: set[tuple[str, int]] = set()
    for rank, item in enumerate(candidates, 1):
        identity = (item['document_id'], item['chunk_index'])
        if not isinstance(identity[0], str) or type(identity[1]) is not int:
            raise ValueError('Invalid chunk identity')
        if identity in seen:
            raise ValueError(f'Duplicate identity in one branch: {identity}')
        if item['rank'] != rank:
            raise ValueError('Branch ranks must be contiguous and start at 1')
        if not math.isfinite(item['score']) or not isinstance(item['text'], str):
            raise ValueError('Invalid candidate score or text')
        seen.add(identity)


def fuse_rrf(
    dense: Sequence[BranchCandidate], bm25: Sequence[BM25Candidate] | Sequence[BranchCandidate],
    *, rrf_constant: int = 60, k: int = 3,
) -> list[HybridCandidate]:
    """Deduplicate identities and sum ranks only; raw score scales never interact."""
    if rrf_constant < 0 or k < 0:
        raise ValueError('RRF constant and k must be non-negative')
    _validate(dense)
    _validate(bm25)
    merged: dict[tuple[str, int], HybridCandidate] = {}
    for name, items in (('dense', dense), ('bm25', bm25)):
        expected_type = 'cosine_similarity' if name == 'dense' else 'bm25_okapi'
        for item in items:
            if item['score_type'] != expected_type:
                raise ValueError(f'Unexpected {name} score type: {item["score_type"]}')
            identity = (item['document_id'], item['chunk_index'])
            if identity not in merged:
                merged[identity] = dict(
                    document_id=identity[0], chunk_index=identity[1], text=item['text'],
                    source=item.get('source'), rank=0, score=0.0, score_type='rrf',
                    sources=[], dense_similarity=None, dense_score_type=None, dense_rank=None,
                    bm25_score=None, bm25_score_type=None, bm25_rank=None,
                    dense_rrf_contribution=0.0, bm25_rrf_contribution=0.0,
                )
            hit = merged[identity]
            if hit['text'] != item['text']:
                raise ValueError(f'Conflicting text for frozen chunk: {identity}')
            contribution = 1.0 / (rrf_constant + item['rank'])
            hit['sources'].append(name)
            if name == 'dense':
                hit['dense_similarity'] = item['score']
                hit['dense_score_type'] = item['score_type']
                hit['dense_rank'] = item['rank']
                hit['dense_rrf_contribution'] = contribution
            else:
                hit['bm25_score'] = item['score']
                hit['bm25_score_type'] = item['score_type']
                hit['bm25_rank'] = item['rank']
                hit['bm25_rrf_contribution'] = contribution
            hit['score'] += contribution
    ordered = sorted(merged.values(), key=lambda x: (-x['score'], x['document_id'], x['chunk_index']))
    for rank, hit in enumerate(ordered[:k], 1):
        hit['rank'] = rank
    return ordered[:k]


def retrieve_hybrid(
    query: str,
    dense_search: Callable[[str, int], Sequence[SearchResult]],
    bm25_search: Callable[[str, int], Sequence[BM25Candidate]],
    *, branch_k: int = 5, k: int = 3, rrf_constant: int = 60,
    clock: Callable[[], float] = time.perf_counter,
) -> HybridResult:
    """Sequential retrieval, explicit expected failures, successful empty is normal.

    Adapters must wrap only expected transport/service errors in RetrievalError.
    Parsing/validation/fusion happens outside that catch so program defects surface.
    """
    if branch_k < 1 or k < 0 or rrf_constant < 0:
        raise ValueError('Invalid retrieval parameters')
    def dense_call(query: str, depth: int) -> list[BranchCandidate]:
        return adapt_dense_results(list(dense_search(query, depth)))

    def bm25_call(query: str, depth: int) -> list[BranchCandidate]:
        return [dict(document_id=x['document_id'], chunk_index=x['chunk_index'],
                     text=x['text'], source=x.get('source'), rank=x['rank'],
                     score=x['score'], score_type=x['score_type'])
                for x in bm25_search(query, depth)]

    branches: dict[str, BranchEvidence] = {}
    for name, search in (('dense', dense_call), ('bm25', bm25_call)):
        started = clock()
        try:
            candidates = search(query, branch_k)
        except RetrievalError as error:
            branches[name] = dict(status='failed', latency_ms=(clock()-started)*1000,
                                  error_stage=error.stage, error=f'{type(error).__name__}: {error}',
                                  candidates=[])
            continue
        elapsed = (clock()-started)*1000
        if len(candidates) > branch_k:
            raise ValueError('Retriever returned more candidates than requested')
        _validate(candidates)
        branches[name] = dict(status='success' if candidates else 'empty', latency_ms=elapsed,
                              error_stage=None, error=None, candidates=candidates)
    dense_failed = branches['dense']['status'] == 'failed'
    bm25_failed = branches['bm25']['status'] == 'failed'
    mode: Literal['full_hybrid', 'fallback_dense', 'fallback_bm25', 'retrieval_failed']
    if dense_failed and bm25_failed:
        mode = 'retrieval_failed'
    elif dense_failed:
        mode = 'fallback_bm25'
    elif bm25_failed:
        mode = 'fallback_dense'
    else:
        mode = 'full_hybrid'
    candidates = fuse_rrf(branches['dense']['candidates'], branches['bm25']['candidates'],
                          rrf_constant=rrf_constant, k=k)
    return dict(mode=mode, branches=branches, candidates=candidates)
