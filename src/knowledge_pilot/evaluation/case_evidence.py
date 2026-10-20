"""Case-level retrieval evidence contract; the learner completes data transitions."""

from collections.abc import Sequence
from typing import Literal, TypeAlias, TypedDict

from knowledge_pilot.evaluation.evidence_collector import (
    CandidateRecord,
    SearchResult,
    collect_candidates,
)

MetricValue: TypeAlias = int | float | None
Metrics: TypeAlias = dict[str, MetricValue]
CaseStatus: TypeAlias = Literal["pending", "success", "retrieval_failed", "scoring_failed"]
ErrorStage: TypeAlias = Literal["retrieval", "scoring"] | None


class CaseEvidence(TypedDict):
    """One case's candidates, optional scores, timing, and state."""

    case_id: str
    query: str
    candidates: list[CandidateRecord]
    metrics: Metrics | None
    latency_ms: float | None
    status: CaseStatus
    error_stage: ErrorStage
    error: str | None


def build_case_record(
    case_id: str, query: str, results: Sequence[SearchResult]
) -> CaseEvidence:

    record: CaseEvidence = {
        "case_id": case_id,
        "query": query,
        "candidates": collect_candidates(results),
        "metrics": None,
        "latency_ms": None,
        "status": "pending",
        "error_stage": None,
        "error": None,
    }

    return record


def mark_case_success(
    record: CaseEvidence,
    metrics: Metrics,
    latency_ms: float
) -> CaseEvidence:
    new_record = record.copy()

    new_record["candidates"] = [
        candidate.copy()
        for candidate in record["candidates"]
    ]

    new_record["metrics"] = metrics.copy()
    new_record["latency_ms"] = latency_ms
    new_record["status"] = "success"
    new_record["error_stage"] = None
    new_record["error"] = None

    return new_record


def mark_case_failure(
    record: CaseEvidence,
    stage: Literal["retrieval", "scoring"],
    error: str,
    latency_ms: float | None = None,
) -> CaseEvidence:

    new_record = record.copy()

    # 新增：独立复制 Candidates 列表及内部字典
    new_record["candidates"] = [
        candidate.copy()
        for candidate in record["candidates"]
    ]

    if stage == "retrieval":
        new_record["status"] = "retrieval_failed"
    else:
        new_record["status"] = "scoring_failed"

    new_record["error_stage"] = stage
    new_record["error"] = error
    new_record["metrics"] = None
    new_record["latency_ms"] = latency_ms

    return new_record
