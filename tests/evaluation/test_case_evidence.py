"""Synthetic CaseEvidence contract tests; enable after the learner fills TODOs."""

from copy import deepcopy
import unittest

from knowledge_pilot.evaluation.case_evidence import (
    build_case_record,
    mark_case_failure,
    mark_case_success,
)
from knowledge_pilot.evaluation.evidence_collector import collect_candidates


RESULTS = [
    ("片段 A", 0.8, {"document_id": "doc-a", "chunk_index": 1}),
    ("片段 B", -0.2, {"document_id": "doc-b", "chunk_index": 0}),
]


def pending_record():
    return {
        "case_id": "rag_001",
        "query": "测试问题",
        "candidates": collect_candidates(deepcopy(RESULTS)),
        "metrics": None,
        "latency_ms": None,
        "status": "pending",
        "error_stage": None,
        "error": None,
    }


class CaseEvidenceTests(unittest.TestCase):
    def test_create_case_evidence_with_exact_fields(self):
        record = build_case_record("rag_001", "测试问题", deepcopy(RESULTS))
        self.assertEqual(set(record), {
            "case_id", "query", "candidates", "metrics", "latency_ms",
            "status", "error_stage", "error",
        })

    def test_case_id_and_query_are_preserved(self):
        record = build_case_record("rag_001", "测试问题", deepcopy(RESULTS))
        self.assertEqual((record["case_id"], record["query"]), ("rag_001", "测试问题"))

    def test_candidates_reuse_collector(self):
        record = build_case_record("rag_001", "测试问题", deepcopy(RESULTS))
        self.assertEqual(record["candidates"], collect_candidates(RESULTS))
        self.assertIsNot(record["candidates"], RESULTS)

    def test_initial_state_is_pending(self):
        record = build_case_record("rag_001", "测试问题", [])
        self.assertEqual(record["candidates"], [])
        self.assertIsNone(record["metrics"])
        self.assertIsNone(record["latency_ms"])
        self.assertEqual(record["status"], "pending")
        self.assertIsNone(record["error_stage"])
        self.assertIsNone(record["error"])

    def test_scoring_success_updates_state(self):
        source = pending_record()
        result = mark_case_success(source, {"hit": 1, "recall": 0.5}, 12.5)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["metrics"], {"hit": 1, "recall": 0.5})
        self.assertEqual(result["latency_ms"], 12.5)
        self.assertIsNone(result["error_stage"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["candidates"], source["candidates"])

    def test_retrieval_failure_updates_state(self):
        source = pending_record()
        source["candidates"] = []
        result = mark_case_failure(source, "retrieval", "retrieval error")
        self.assertEqual(result["status"], "retrieval_failed")
        self.assertEqual(result["error_stage"], "retrieval")
        self.assertEqual(result["error"], "retrieval error")
        self.assertEqual(result["candidates"], [])
        self.assertIsNone(result["metrics"])

    def test_scoring_failure_updates_state(self):
        result = mark_case_failure(
            pending_record(), "scoring", "scoring error", latency_ms=9.0
        )
        self.assertEqual(result["status"], "scoring_failed")
        self.assertEqual(result["error_stage"], "scoring")
        self.assertEqual(result["error"], "scoring error")
        self.assertEqual(result["latency_ms"], 9.0)
        self.assertIsNone(result["metrics"])

    def test_scoring_failure_keeps_candidates(self):
        source = pending_record()
        result = mark_case_failure(source, "scoring", "scoring error")
        self.assertEqual(result["candidates"], source["candidates"])
        self.assertIsNot(result["candidates"], source["candidates"])

    def test_inputs_are_not_mutated(self):
        results = deepcopy(RESULTS)
        results_before = deepcopy(results)
        build_case_record("rag_001", "测试问题", results)
        self.assertEqual(results, results_before)

        source = pending_record()
        source_before = deepcopy(source)
        metrics = {"hit": 1}
        metrics_before = deepcopy(metrics)
        mark_case_success(source, metrics, 5.0)
        mark_case_failure(source, "scoring", "scoring error")
        self.assertEqual(source, source_before)
        self.assertEqual(metrics, metrics_before)
    def test_success_metrics_are_not_shared(self):
        source = pending_record()
        metrics = {"hit": 1, "recall": 0.5}
        result = mark_case_success(source, metrics, 5.0)
        self.assertIsNot(result["metrics"], metrics)
        result["metrics"]["hit"] = 0
        self.assertEqual(metrics, {"hit": 1, "recall": 0.5})
        self.assertIsNone(source["metrics"])

    def test_success_candidates_are_not_shared(self):
        source = pending_record()
        result = mark_case_success(source, {"hit": 1}, 5.0)
        self.assertIsNot(result["candidates"], source["candidates"])
        self.assertIsNot(result["candidates"][0], source["candidates"][0])
        result["candidates"][0]["text"] = "changed"
        self.assertEqual(source["candidates"][0]["text"], "片段 A")

    def test_scoring_failure_candidate_dicts_are_not_shared(self):
        source = pending_record()
        result = mark_case_failure(source, "scoring", "scoring error")
        self.assertIsNot(result["candidates"][0], source["candidates"][0])
        result["candidates"][0]["text"] = "changed"
        self.assertEqual(source["candidates"][0]["text"], "片段 A")
