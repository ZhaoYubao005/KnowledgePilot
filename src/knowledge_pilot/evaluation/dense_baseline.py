"""V1.3 dense-retrieval experiment orchestration without runtime side effects."""

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path
from statistics import mean
import time
from typing import Any

from knowledge_pilot.evaluation.case_evidence import (
    CaseEvidence,
    mark_case_failure,
    mark_case_success,
    build_case_record,
)
from knowledge_pilot.evaluation.evidence_collector import SearchResult
from knowledge_pilot.evaluation.rag_evaluator import evaluate_retrieval_case


SearchFunction = Callable[[str, int], Sequence[SearchResult]]


def load_retrieval_cases(path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Load frozen dataset metadata and retrieval cases without modifying input."""
    with path.open("r", encoding="utf-8") as file:
        dataset = json.load(file)
    cases = [deepcopy(case) for case in dataset["cases"] if case["case_type"] == "retrieval"]
    metadata = {
        "dataset_version": dataset["dataset_version"],
        "corpus_version": dataset["corpus_version"],
    }
    return metadata, cases


def make_dense_search(search_function, collection) -> SearchFunction:
    """Adapt the existing Chroma search signature to the injectable evaluator shape."""
    def dense_search(query: str, k: int) -> Sequence[SearchResult]:
        return search_function(query, collection, top_k=k)
    return dense_search


def run_dense_cases(
    cases: Sequence[Mapping[str, Any]],
    search_fn: SearchFunction,
    k: int = 3,
    clock: Callable[[], float] = time.perf_counter,
) -> list[CaseEvidence]:
    """Run retrieval cases with query-only latency and case-level isolation."""
    records: list[CaseEvidence] = []
    for case in cases:
        if case["case_type"] != "retrieval":
            continue
        started = clock()
        try:
            results = list(search_fn(case["query"], k))
        except Exception as error:
            latency_ms = (clock() - started) * 1000
            pending = build_case_record(case["id"], case["query"], [])
            records.append(mark_case_failure(
                pending, "retrieval", f"{type(error).__name__}: {error}", latency_ms,
            ))
            continue

        latency_ms = (clock() - started) * 1000
        pending = build_case_record(case["id"], case["query"], results)
        try:
            metrics = evaluate_retrieval_case(case, results, k)
            metrics.pop("case_id", None)
        except Exception as error:
            records.append(mark_case_failure(
                pending, "scoring", f"{type(error).__name__}: {error}", latency_ms,
            ))
            continue
        records.append(mark_case_success(pending, metrics, latency_ms))
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


def summarize_dense_cases(records: Sequence[CaseEvidence]) -> dict[str, Any]:
    """Summarize successful metrics with explicit denominators and all query latencies."""
    statuses = [record["status"] for record in records]
    successful = [record for record in records if record["status"] == "success"]
    metric_keys = {"hit_rate": "hit", "mean_recall": "recall", "mrr": "rr"}
    summary: dict[str, Any] = {
        "case_counts": {
            "total": len(records),
            "success": statuses.count("success"),
            "retrieval_failed": statuses.count("retrieval_failed"),
            "scoring_failed": statuses.count("scoring_failed"),
        },
        "metric_denominators": {},
    }
    for output_name, metric_name in metric_keys.items():
        values = [record["metrics"][metric_name] for record in successful
                  if record["metrics"] is not None and record["metrics"].get(metric_name) is not None]
        summary["metric_denominators"][output_name] = len(values)
        summary[output_name] = mean(values) if values else None

    latencies = [record["latency_ms"] for record in records if record["latency_ms"] is not None]
    summary["latency_ms"] = {
        "count": len(latencies),
        "mean": mean(latencies) if latencies else None,
        "min": min(latencies) if latencies else None,
        "p50": _percentile(latencies, 0.50),
        "p95": _percentile(latencies, 0.95),
        "max": max(latencies) if latencies else None,
        "boundary": "search_fn(query, k) only; excludes dataset load, index copy/open, provenance, and JSON write",
        "first_query_may_include_embedding_model_cold_start": True,
    }
    return summary
