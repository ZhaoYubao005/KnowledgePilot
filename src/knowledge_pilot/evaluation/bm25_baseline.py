"""Case-level orchestration and summaries for the V1.3 BM25 baseline."""

from collections.abc import Callable, Mapping, Sequence
from statistics import mean
import time
from typing import Any, Literal, TypedDict

from knowledge_pilot.evaluation.bm25 import BM25Candidate
from knowledge_pilot.evaluation.rag_evaluator import evaluate_retrieval_case


class BM25CaseEvidence(TypedDict):
    case_id: str
    query: str
    candidates: list[BM25Candidate]
    metrics: dict[str, int | float | None] | None
    latency_ms: float | None
    status: Literal["success", "retrieval_failed", "scoring_failed"]
    error_stage: Literal["retrieval", "scoring"] | None
    error: str | None


def run_bm25_cases(
    cases: Sequence[Mapping[str, Any]],
    search_fn: Callable[[str, int], Sequence[BM25Candidate]],
    k: int = 3,
    clock: Callable[[], float] = time.perf_counter,
) -> list[BM25CaseEvidence]:
    records: list[BM25CaseEvidence] = []
    for case in cases:
        if case["case_type"] != "retrieval":
            continue
        started = clock()
        try:
            candidates = [dict(item) for item in search_fn(case["query"], k)]
        except Exception as error:
            records.append({
                "case_id": case["id"], "query": case["query"], "candidates": [],
                "metrics": None, "latency_ms": (clock() - started) * 1000,
                "status": "retrieval_failed", "error_stage": "retrieval",
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        latency_ms = (clock() - started) * 1000
        evaluator_results = [
            (item["text"], item["score"], {
                "document_id": item["document_id"], "chunk_index": item["chunk_index"]
            }) for item in candidates
        ]
        try:
            scored = evaluate_retrieval_case(case, evaluator_results, k)
            metrics = {name: scored[name] for name in ("hit", "recall", "rr")}
        except Exception as error:
            records.append({
                "case_id": case["id"], "query": case["query"],
                "candidates": candidates, "metrics": None, "latency_ms": latency_ms,
                "status": "scoring_failed", "error_stage": "scoring",
                "error": f"{type(error).__name__}: {error}",
            })
            continue
        records.append({
            "case_id": case["id"], "query": case["query"],
            "candidates": candidates, "metrics": metrics, "latency_ms": latency_ms,
            "status": "success", "error_stage": None, "error": None,
        })
    return records


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize_bm25_cases(records: Sequence[BM25CaseEvidence]) -> dict[str, Any]:
    statuses = [record["status"] for record in records]
    successful = [record for record in records if record["status"] == "success"]
    summary: dict[str, Any] = {
        "case_counts": {"total": len(records), "success": statuses.count("success"),
                        "retrieval_failed": statuses.count("retrieval_failed"),
                        "scoring_failed": statuses.count("scoring_failed")},
        "metric_denominators": {},
    }
    for output, metric in (("hit_rate", "hit"), ("mean_recall", "recall"), ("mrr", "rr")):
        values = [record["metrics"][metric] for record in successful
                  if record["metrics"] is not None and record["metrics"].get(metric) is not None]
        summary["metric_denominators"][output] = len(values)
        summary[output] = mean(values) if values else None
    latencies = [record["latency_ms"] for record in records if record["latency_ms"] is not None]
    summary["latency_ms"] = {
        "count": len(latencies), "mean": mean(latencies) if latencies else None,
        "min": min(latencies) if latencies else None, "p50": _percentile(latencies, 0.5),
        "p95": _percentile(latencies, 0.95), "max": max(latencies) if latencies else None,
        "boundary": "BM25 tokenization and in-memory scoring only; excludes chunk export, index build, provenance, and JSON write",
    }
    summary["zero_candidate_success_count"] = sum(
        1 for record in successful if not record["candidates"]
    )
    return summary
