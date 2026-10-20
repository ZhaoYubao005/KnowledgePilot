"""Synthetic tests for the V1.3 dense baseline orchestration."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from knowledge_pilot.evaluation.dense_baseline import (
    load_retrieval_cases,
    make_dense_search,
    run_dense_cases,
    summarize_dense_cases,
)
from knowledge_pilot.evaluation.json_writer import write_json_exclusive
from knowledge_pilot.evaluation.run_report import build_run_report


def retrieval_case(case_id="rag_001"):
    return {
        "id": case_id,
        "case_type": "retrieval",
        "query": f"query {case_id}",
        "relevant_chunks": [{"document_id": "doc", "chunk_index": 1}],
    }


class DenseBaselineTests(unittest.TestCase):
    def test_dataset_loader_filters_retrieval_cases_and_preserves_ids(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps({
                "dataset_version": "fixture-v1", "corpus_version": "corpus-v1",
                "cases": [retrieval_case(), {"id": "agent_001", "case_type": "agent"}],
            }), encoding="utf-8")
            metadata, cases = load_retrieval_cases(path)
        self.assertEqual(metadata, {"dataset_version": "fixture-v1", "corpus_version": "corpus-v1"})
        self.assertEqual([case["id"] for case in cases], ["rag_001"])

    def test_dense_adapter_uses_collection_and_top_k(self):
        calls = []
        collection = object()
        def search(query, supplied_collection, top_k=3):
            calls.append((query, supplied_collection, top_k))
            return [("text", 0.7, {"document_id": "doc", "chunk_index": 1})]
        result = make_dense_search(search, collection)("question", 5)
        self.assertEqual(calls, [("question", collection, 5)])
        self.assertEqual(result[0][1], 0.7)

    def test_success_preserves_candidate_order_scores_and_metrics(self):
        case = retrieval_case()
        results = [
            ("first", -0.2, {"document_id": "other", "chunk_index": 0}),
            ("second", 1.25, {"document_id": "doc", "chunk_index": 1}),
        ]
        records = run_dense_cases([case], lambda query, k: results, k=3)
        record = records[0]
        self.assertEqual(record["status"], "success")
        self.assertEqual([item["text"] for item in record["candidates"]], ["first", "second"])
        self.assertEqual([item["similarity"] for item in record["candidates"]], [-0.2, 1.25])
        self.assertEqual(record["metrics"]["hit"], 1)
        self.assertEqual(record["metrics"]["recall"], 1.0)
        self.assertEqual(record["metrics"]["rr"], 0.5)

    def test_retrieval_failure_is_recorded_and_other_cases_continue(self):
        cases = [retrieval_case("bad"), retrieval_case("good")]
        def search(query, k):
            if query.endswith("bad"):
                raise RuntimeError("offline")
            return [("ok", 0.8, {"document_id": "doc", "chunk_index": 1})]
        records = run_dense_cases(cases, search)
        self.assertEqual([item["status"] for item in records], ["retrieval_failed", "success"])
        self.assertEqual(records[0]["error_stage"], "retrieval")
        self.assertIn("RuntimeError", records[0]["error"])

    def test_scoring_failure_keeps_candidates(self):
        case = retrieval_case()
        case["relevant_chunks"] = [{"document_id": "doc"}]
        result = [("kept", 0.5, {"document_id": "doc", "chunk_index": 1})]
        record = run_dense_cases([case], lambda query, k: result)[0]
        self.assertEqual(record["status"], "scoring_failed")
        self.assertEqual(record["error_stage"], "scoring")
        self.assertEqual(record["candidates"][0]["text"], "kept")

    def test_summary_uses_successful_metric_denominators_and_all_query_latencies(self):
        cases = [retrieval_case("one"), retrieval_case("two"), retrieval_case("bad")]
        def search(query, k):
            if query.endswith("bad"):
                raise OSError("failure")
            chunk = 1 if query.endswith("one") else 9
            return [("text", 0.4, {"document_id": "doc", "chunk_index": chunk})]
        summary = summarize_dense_cases(run_dense_cases(cases, search))
        self.assertEqual(summary["case_counts"], {"total": 3, "success": 2, "retrieval_failed": 1, "scoring_failed": 0})
        self.assertEqual(summary["metric_denominators"], {"hit_rate": 2, "mean_recall": 2, "mrr": 2})
        self.assertEqual(summary["hit_rate"], 0.5)
        self.assertEqual(summary["mean_recall"], 0.5)
        self.assertEqual(summary["mrr"], 0.5)
        self.assertEqual(summary["latency_ms"]["count"], 3)

    def test_report_and_json_round_trip_do_not_mutate_inputs(self):
        records = run_dense_cases([retrieval_case()], lambda query, k: [
            ("中文证据", 0.9, {"document_id": "doc", "chunk_index": 1})
        ])
        provenance = {
            "git_commit": None, "git_worktree_dirty": None,
            "dataset": {"path": "fixture", "sha256": "a" * 64, "bytes": 1},
            "manifest": {"path": "fixture", "sha256": "b" * 64, "bytes": 1},
            "corpus_files": [], "code_files": [], "python_version": None,
            "observation_errors": ["synthetic fixture"],
        }
        inputs = {"run_id": "fixture", "strategy": "dense", "strategy_config": {}, "k": 3,
                  "started_at_utc": "2026-01-01T00:00:00Z", "finished_at_utc": "2026-01-01T00:00:01Z",
                  "dataset_version": "v1", "corpus_version": "corpus_v1",
                  "provenance": provenance, "cases": records, "summary": summarize_dense_cases(records)}
        before = deepcopy(inputs)
        with TemporaryDirectory() as directory:
            target = Path(directory) / "report.json"
            report = build_run_report(**inputs)
            write_json_exclusive(target, report)
            loaded = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(loaded, report)
        self.assertEqual(inputs, before)
        self.assertEqual(loaded["schema_version"], "retrieval_run_report_v1")


if __name__ == "__main__":
    unittest.main()
