"""RunReport schema and learner-owned assembly placeholder; no I/O."""

from collections.abc import Sequence
from typing import Any, Final, TypedDict
from copy import deepcopy
from knowledge_pilot.evaluation.case_evidence import CaseEvidence
from knowledge_pilot.evaluation.bm25_baseline import BM25CaseEvidence
from knowledge_pilot.evaluation.hybrid_evaluation import HybridCaseEvidence
from knowledge_pilot.evaluation.run_provenance import RunProvenance


RUN_REPORT_SCHEMA_VERSION: Final[str] = "retrieval_run_report_v1"


class RunReport(TypedDict):
    schema_version: str
    run_id: str
    strategy: str
    strategy_config: dict[str, Any]
    k: int
    started_at_utc: str
    finished_at_utc: str
    dataset_version: str
    corpus_version: str
    provenance: RunProvenance
    cases: list[CaseEvidence | BM25CaseEvidence | HybridCaseEvidence]
    summary: dict[str, Any] | None


def build_run_report(
    *,
    run_id: str,
    strategy: str,
    strategy_config: dict[str, Any],
    k: int,
    started_at_utc: str,
    finished_at_utc: str,
    dataset_version: str,
    corpus_version: str,
    provenance: RunProvenance,
    cases: Sequence[CaseEvidence | BM25CaseEvidence | HybridCaseEvidence],
    summary: dict[str, Any] | None = None,
) -> RunReport:

    report: RunReport = {
        "schema_version": "retrieval_run_report_v1",
        "run_id": run_id,
        "strategy": strategy,
        "strategy_config": deepcopy(strategy_config),
        "k": k,
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "dataset_version": dataset_version,
        "corpus_version": corpus_version,
        "provenance": deepcopy(provenance),
        "cases": deepcopy(list(cases)),
        "summary": deepcopy(summary),
    }

    return report