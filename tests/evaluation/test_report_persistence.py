"""Synthetic integration tests for the V1.3 report persistence chain."""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from knowledge_pilot.evaluation.case_evidence import build_case_record
from knowledge_pilot.evaluation.json_writer import write_json_exclusive
from knowledge_pilot.evaluation.run_provenance import collect_run_provenance
from knowledge_pilot.evaluation.run_report import build_run_report


class ReportPersistenceTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="knowledgepilot-report-integration-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "synthetic-project"
        self.corpus_directory = self.root / "fixtures" / "corpus"
        self.code_directory = self.root / "fixtures" / "code"
        self.corpus_directory.mkdir(parents=True)
        self.code_directory.mkdir(parents=True)

        self.dataset_path = self.root / "fixtures" / "cases.json"
        self.dataset_path.write_text(
            json.dumps({"dataset_version": "synthetic-dataset-v1"}),
            encoding="utf-8",
            newline="\n",
        )
        self.corpus_path = self.corpus_directory / "knowledge.txt"
        self.corpus_path.write_text("知识检索合成语料\n", encoding="utf-8", newline="\n")
        self.code_path = self.code_directory / "retriever.py"
        self.code_path.write_bytes(b"STRATEGY = 'synthetic'\n")
        self.manifest_path = self.root / "fixtures" / "manifest.json"
        self.manifest_path.write_text(
            json.dumps({
                "manifest_schema_version": "synthetic-v1",
                "corpus_files": [{
                    "path": "fixtures/corpus/knowledge.txt",
                    "document_id": "synthetic_doc",
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
            newline="\n",
        )

    def build_inputs(self):
        first = build_case_record(
            "case_中文",
            "什么是知识检索？",
            [("合成候选一", 0.875, {"document_id": "synthetic_doc", "chunk_index": 0})],
        )
        second = build_case_record(
            "case_second",
            "second synthetic query",
            [("synthetic candidate two", -0.25,
              {"document_id": "synthetic_doc", "chunk_index": 1})],
        )
        with patch(
            "knowledge_pilot.evaluation.run_provenance.subprocess.run",
            side_effect=FileNotFoundError("synthetic git unavailable"),
        ):
            provenance = collect_run_provenance(
                project_root=self.root,
                dataset_path=self.dataset_path,
                manifest_path=self.manifest_path,
                code_paths=[self.code_path],
            )
        return {
            "run_id": "synthetic-run",
            "strategy": "synthetic-vector",
            "strategy_config": {"fixture": {"language": "中文"}},
            "k": 2,
            "started_at_utc": "2026-01-01T00:00:00Z",
            "finished_at_utc": "2026-01-01T00:00:01Z",
            "dataset_version": "synthetic-dataset-v1",
            "corpus_version": "synthetic-corpus-v1",
            "provenance": provenance,
            "cases": [first, second],
            "summary": None,
        }

    def test_case_to_report_to_json_round_trip_preserves_contract(self):
        inputs = self.build_inputs()
        report = build_run_report(**inputs)
        target = self.root / "synthetic-run-report.json"

        write_json_exclusive(target, report)
        loaded = json.loads(target.read_text(encoding="utf-8"))

        self.assertEqual(loaded, report)
        self.assertEqual(loaded["schema_version"], "retrieval_run_report_v1")
        self.assertEqual(
            [case["case_id"] for case in loaded["cases"]],
            ["case_中文", "case_second"],
        )
        self.assertEqual(loaded["cases"][0]["query"], "什么是知识检索？")
        self.assertEqual(loaded["cases"][0]["candidates"][0]["text"], "合成候选一")
        self.assertEqual(loaded["strategy_config"], {"fixture": {"language": "中文"}})
        self.assertIsNone(loaded["provenance"]["git_commit"])
        self.assertTrue(loaded["provenance"]["observation_errors"])
        self.assertEqual(
            loaded["provenance"]["dataset"]["path"],
            "fixtures/cases.json",
        )
        self.assertEqual(
            loaded["provenance"]["corpus_files"][0]["document_id"],
            "synthetic_doc",
        )
        self.assertEqual(
            loaded["provenance"]["code_files"][0]["path"],
            "fixtures/code/retriever.py",
        )

    def test_build_and_write_do_not_modify_integration_inputs(self):
        inputs = self.build_inputs()
        before = deepcopy(inputs)
        report = build_run_report(**inputs)

        write_json_exclusive(self.root / "immutable-input-report.json", report)

        self.assertEqual(inputs, before)
        self.assertEqual(report, build_run_report(**before))


if __name__ == "__main__":
    unittest.main()
