"""Synthetic behavior contracts; enable after the learner implements the builder."""

from copy import deepcopy
import unittest

from knowledge_pilot.evaluation.run_report import build_run_report


def sample_inputs():
    """All identities, timestamps, and data below are synthetic fixtures."""
    file_identity = {"path": "fixtures/dataset.json", "sha256": "a" * 64, "bytes": 10}
    case = {
        "case_id": "case_b", "query": "synthetic query",
        "candidates": [{"document_id": "doc_a", "chunk_index": 0, "rank": 1,
                        "text": "synthetic text", "similarity": -0.2}],
        "metrics": {"hit": 1}, "latency_ms": 2.5, "status": "success",
        "error_stage": None, "error": None,
    }
    second = deepcopy(case)
    second["case_id"] = "case_a"
    return {
        "run_id": "synthetic-run", "strategy": "vector",
        "strategy_config": {"embedding": {"model": None}, "flags": ["fixture"]},
        "k": 3, "started_at_utc": "2026-01-01T00:00:00Z",
        "finished_at_utc": "2026-01-01T00:00:01Z",
        "dataset_version": "dataset-fixture-v7", "corpus_version": "corpus-fixture-v9",
        "provenance": {
            "git_commit": None, "git_worktree_dirty": None,
            "dataset": file_identity,
            "manifest": {"path": "fixtures/manifest.json", "sha256": "b" * 64, "bytes": 11},
            "corpus_files": [{"path": "fixtures/doc.txt", "sha256": "c" * 64,
                              "bytes": 12, "document_id": "doc_a"}],
            "code_files": [{"path": "fixtures/code.py", "sha256": "d" * 64, "bytes": 13}],
            "python_version": None, "observation_errors": ["synthetic unavailable metadata"],
        },
        "cases": [case, second], "summary": None,
    }


class RunReportTests(unittest.TestCase):
    def test_complete_fields_and_explicit_values(self):
        inputs = sample_inputs()
        report = build_run_report(**inputs)
        self.assertEqual(set(report), set(inputs) | {"schema_version"})
        for name, value in inputs.items():
            self.assertEqual(report[name], value)

    def test_case_order_is_preserved(self):
        report = build_run_report(**sample_inputs())
        self.assertEqual([case["case_id"] for case in report["cases"]], ["case_b", "case_a"])

    def test_schema_version_is_fixed_and_distinct_from_dataset_version(self):
        report = build_run_report(**sample_inputs())
        self.assertEqual(report["schema_version"], "retrieval_run_report_v1")
        self.assertNotEqual(report["schema_version"], report["dataset_version"])

    def test_strategy_config_is_preserved(self):
        inputs = sample_inputs()
        self.assertEqual(build_run_report(**inputs)["strategy_config"], inputs["strategy_config"])

    def test_provenance_and_missing_observations_are_preserved(self):
        inputs = sample_inputs()
        report = build_run_report(**inputs)
        self.assertEqual(report["provenance"], inputs["provenance"])
        self.assertIsNone(report["provenance"]["git_commit"])
        self.assertIsNone(report["provenance"]["git_worktree_dirty"])

    def test_summary_none_is_valid_when_omitted(self):
        inputs = sample_inputs()
        inputs.pop("summary")
        self.assertIsNone(build_run_report(**inputs)["summary"])

    def test_builder_does_not_mutate_inputs(self):
        inputs = sample_inputs()
        before = deepcopy(inputs)
        build_run_report(**inputs)
        self.assertEqual(inputs, before)

    def test_output_nested_data_is_independent(self):
        inputs = sample_inputs()
        before = deepcopy(inputs)
        report = build_run_report(**inputs)
        report["cases"][0]["candidates"][0]["text"] = "changed"
        report["cases"][0]["metrics"]["hit"] = 0
        report["cases"].reverse()
        report["strategy_config"]["embedding"]["model"] = "changed"
        report["strategy_config"]["flags"].append("changed")
        report["provenance"]["dataset"]["sha256"] = "e" * 64
        report["provenance"]["manifest"]["path"] = "changed"
        report["provenance"]["corpus_files"][0]["document_id"] = "changed"
        report["provenance"]["code_files"][0]["sha256"] = "f" * 64
        report["provenance"]["observation_errors"].append("changed")
        self.assertEqual(inputs, before)

    def test_input_mutation_does_not_change_output(self):
        inputs = sample_inputs()
        report = build_run_report(**inputs)
        before = deepcopy(report)
        inputs["cases"][0]["candidates"][0]["text"] = "changed"
        inputs["provenance"]["corpus_files"].clear()
        inputs["strategy_config"]["flags"].append("changed")
        self.assertEqual(report, before)

    def test_supplied_summary_is_independently_preserved(self):
        inputs = sample_inputs()
        inputs["summary"] = {"fixture": {"values": [1]}}
        report = build_run_report(**inputs)
        self.assertEqual(report["summary"], inputs["summary"])
        report["summary"]["fixture"]["values"].append(2)
        self.assertEqual(inputs["summary"], {"fixture": {"values": [1]}})
