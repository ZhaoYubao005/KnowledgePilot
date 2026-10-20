"""Synthetic behavior tests for exclusive JSON report persistence."""

import builtins
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from knowledge_pilot.evaluation.json_writer import write_json_exclusive


class JsonWriterTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="knowledgepilot-json-writer-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "synthetic-report.json"

    def test_writes_json_and_returns_target_path(self):
        payload = {"schema_version": "synthetic-v1", "value": 3}

        result = write_json_exclusive(self.path, payload)

        self.assertEqual(result, self.path)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), payload)

    def test_preserves_chinese_content(self):
        payload = {"query": "知识检索", "answer": "中文证据"}

        write_json_exclusive(self.path, payload)

        text = self.path.read_text(encoding="utf-8")
        self.assertIn("知识检索", text)
        self.assertIn("中文证据", text)
        self.assertEqual(json.loads(text), payload)

    def test_writes_nested_run_report_style_payload(self):
        payload = {
            "schema_version": "retrieval_run_report_v1",
            "run_id": "synthetic-run",
            "provenance": {
                "git_commit": None,
                "dataset": {"path": "fixtures/cases.json", "sha256": "a" * 64, "bytes": 10},
                "observation_errors": ["synthetic unavailable observation"],
            },
            "cases": [{
                "case_id": "case_001",
                "candidates": [{"rank": 1, "text": "合成候选", "similarity": -0.25}],
                "metrics": None,
            }],
            "summary": None,
        }

        write_json_exclusive(self.path, payload)

        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), payload)

    def test_existing_file_is_not_overwritten(self):
        original = b"frozen historical report\n"
        self.path.write_bytes(original)

        with self.assertRaises(FileExistsError):
            write_json_exclusive(self.path, {"replacement": True})

        self.assertEqual(self.path.read_bytes(), original)

    def test_rejects_nan_and_infinity(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                target = self.directory / f"invalid-{len(list(self.directory.iterdir()))}.json"
                with self.assertRaises(ValueError):
                    write_json_exclusive(target, {"metric": value})
                self.assertFalse(target.exists())

    def test_rejects_non_serializable_object(self):
        with self.assertRaises(TypeError):
            write_json_exclusive(self.path, {"invalid": object()})

        self.assertFalse(self.path.exists())

    def test_invalid_payload_does_not_create_target(self):
        with self.assertRaises((TypeError, ValueError)):
            write_json_exclusive(self.path, {"nested": {"invalid": {1, 2, 3}}})

        self.assertFalse(self.path.exists())

    def test_output_is_utf8_lf_indented_and_ends_with_newline(self):
        write_json_exclusive(self.path, {"message": "第一行\r\n第二行", "nested": {"value": 1}})

        raw = self.path.read_bytes()
        expected = (
            json.dumps(
                {"message": "第一行\r\n第二行", "nested": {"value": 1}},
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        self.assertEqual(raw, expected)
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"\n"))

    def test_payload_is_not_modified(self):
        payload = {"nested": {"values": [1, "中文", None]}, "flags": [True, False]}
        before = deepcopy(payload)

        write_json_exclusive(self.path, payload)

        self.assertEqual(payload, before)

    def test_missing_parent_directory_fails_without_creating_it(self):
        missing_parent = self.directory / "missing" / "nested"
        target = missing_parent / "report.json"

        with self.assertRaises(FileNotFoundError):
            write_json_exclusive(target, {"value": 1})

        self.assertFalse(missing_parent.exists())
        self.assertFalse(target.exists())

    def test_write_failure_removes_partial_target(self):
        target = self.path

        class FailingWriter:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def write(self, text):
                with builtins.open(target, "w", encoding="utf-8", newline="\n") as file:
                    file.write(text[:1])
                raise OSError("synthetic write failure")

        with patch(
            "knowledge_pilot.evaluation.json_writer.Path.open",
            return_value=FailingWriter(),
        ):
            with self.assertRaisesRegex(OSError, "synthetic write failure"):
                write_json_exclusive(target, {"value": "synthetic"})

        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
