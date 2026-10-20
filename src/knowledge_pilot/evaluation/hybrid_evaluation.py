"""V1.3 Hybrid case scoring and explicit success/fallback denominators."""
from collections.abc import Callable, Mapping, Sequence
from statistics import mean
import time
from typing import Any, Literal, TypedDict

from knowledge_pilot.evaluation.bm25 import BM25Candidate
from knowledge_pilot.evaluation.bm25_baseline import _percentile
from knowledge_pilot.evaluation.evidence_collector import SearchResult
from knowledge_pilot.evaluation.hybrid import BranchEvidence, HybridCandidate, retrieve_hybrid
from knowledge_pilot.evaluation.rag_evaluator import evaluate_retrieval_case


class HybridCaseEvidence(TypedDict):
    case_id: str
    query: str
    candidates: list[HybridCandidate]
    metrics: dict[str, int | float | None] | None
    latency_ms: float | None
    status: Literal['success', 'retrieval_failed', 'scoring_failed']
    error_stage: Literal['retrieval', 'scoring'] | None
    error: str | None
    mode: Literal['full_hybrid', 'fallback_dense', 'fallback_bm25', 'retrieval_failed']
    branches: dict[str, BranchEvidence]


def run_hybrid_cases(
    cases: Sequence[Mapping[str, Any]],
    dense_search: Callable[[str, int], Sequence[SearchResult]],
    bm25_search: Callable[[str, int], Sequence[BM25Candidate]],
    *, branch_k: int = 5, k: int = 3, rrf_constant: int = 60,
    clock: Callable[[], float] = time.perf_counter,
) -> list[HybridCaseEvidence]:
    records: list[HybridCaseEvidence] = []
    for case in cases:
        if case['case_type'] != 'retrieval':
            continue
        started = clock()
        result = retrieve_hybrid(case['query'], dense_search, bm25_search,
                                 branch_k=branch_k, k=k, rrf_constant=rrf_constant, clock=clock)
        record: HybridCaseEvidence = dict(
            case_id=case['id'], query=case['query'], candidates=result['candidates'],
            metrics=None, latency_ms=(clock()-started)*1000, status='success',
            error_stage=None, error=None, mode=result['mode'], branches=result['branches'],
        )
        if result['mode'] == 'retrieval_failed':
            record.update(status='retrieval_failed', error_stage='retrieval',
                          error='; '.join(f'{name}: {branch["error"]}' for name, branch in result['branches'].items()))
        else:
            # The stable scorer only uses identities/order; score is ignored.
            scorer_input = [(x['text'], x['score'], dict(document_id=x['document_id'],
                             chunk_index=x['chunk_index'])) for x in result['candidates']]
            try:
                metrics = evaluate_retrieval_case(case, scorer_input, k)
            except ValueError as error:
                record.update(status='scoring_failed', error_stage='scoring',
                              error=f'{type(error).__name__}: {error}')
            else:
                record['metrics'] = {name: metrics[name] for name in ('hit','recall','rr')}
        records.append(record)
    return records


def summarize_hybrid_cases(records: Sequence[HybridCaseEvidence]) -> dict[str, Any]:
    summary: dict[str, Any] = dict(
        case_counts={'total': len(records), **{s: sum(r['status']==s for r in records)
                    for s in ('success','retrieval_failed','scoring_failed')}},
        mode_counts={m:sum(r['mode']==m for r in records) for m in
                     ('full_hybrid','fallback_dense','fallback_bm25','retrieval_failed')},
        metric_denominators={},
    )
    summary['fallback_count'] = sum(r['mode'].startswith('fallback_') for r in records)
    summary['branch_status_counts'] = {
        name: {status:sum(r['branches'][name]['status']==status for r in records)
               for status in ('success','empty','failed')} for name in ('dense','bm25')
    }
    successful = [r for r in records if r['status']=='success']
    for output, metric in (('hit_rate','hit'),('mean_recall','recall'),('mrr','rr')):
        values = [r['metrics'][metric] for r in successful
                  if r['metrics'] is not None and r['metrics'].get(metric) is not None]
        summary['metric_denominators'][output] = len(values)
        summary[output] = mean(values) if values else None
    latencies = [r['latency_ms'] for r in records if r['latency_ms'] is not None]
    summary['latency_ms'] = dict(
        count=len(latencies), mean=mean(latencies) if latencies else None,
        min=min(latencies) if latencies else None, max=max(latencies) if latencies else None,
        p50=_percentile(latencies,0.5), p95=_percentile(latencies,0.95),
        boundary='sequential Dense retrieval (embedding + Chroma), BM25 retrieval, validation and RRF; excludes scoring, runtime copy/open, index build, provenance and JSON write',
        first_query_may_include_embedding_model_cold_start=True,
    )
    summary['zero_candidate_success_count'] = sum(not r['candidates'] for r in successful)
    return summary
