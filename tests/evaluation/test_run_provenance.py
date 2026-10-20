"""Synthetic file hashing contracts; enable after sha256_file is implemented."""

import hashlib
import json
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from knowledge_pilot.evaluation.run_provenance import (
    build_file_identity,
    collect_corpus_identities,
    collect_run_provenance,
    sha256_file,
)


class Sha256FileTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="knowledgepilot-sha256-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / "synthetic.bin"

    def test_known_content_digest(self):
        self.path.write_bytes(b"abc")
        self.assertEqual(
            sha256_file(self.path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )

    def test_empty_file_digest(self):
        self.path.write_bytes(b"")
        self.assertEqual(
            sha256_file(self.path),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )

    def test_utf8_chinese_raw_bytes(self):
        content = "知识检索\r\n中文样例\n".encode("utf-8")
        self.path.write_bytes(content)
        self.assertEqual(sha256_file(self.path), hashlib.sha256(content).hexdigest())

    def test_changed_content_changes_digest(self):
        self.path.write_bytes(b"before")
        original = sha256_file(self.path)
        self.path.write_bytes(b"after")
        changed = sha256_file(self.path)
        self.assertEqual(original, hashlib.sha256(b"before").hexdigest())
        self.assertEqual(changed, hashlib.sha256(b"after").hexdigest())
        self.assertNotEqual(original, changed)

    def test_missing_file_raises(self):
        missing = self.directory / "missing.bin"
        with self.assertRaises(FileNotFoundError):
            sha256_file(missing)
        self.assertFalse(missing.exists())

    def test_hashing_preserves_original_bytes(self):
        content = bytes(range(256)) * 8192 + b"\r\n\x00\xff"
        self.path.write_bytes(content)
        self.assertEqual(sha256_file(self.path), hashlib.sha256(content).hexdigest())
        self.assertEqual(self.path.read_bytes(), content)


class FileIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="knowledgepilot-identity-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.corpus = self.root / "data" / "evaluation" / "corpus"
        self.corpus.mkdir(parents=True)

    def write_fixture(self, name, content):
        path = self.corpus / name
        path.write_bytes(content)
        return path

    def manifest(self, entries):
        return {"manifest_schema_version": "synthetic-v1", "corpus_files": entries}

    def entry(self, name, document_id):
        return {
            "path": f"data/evaluation/corpus/{name}",
            "document_id": document_id,
            "sha256": "manifest-value-is-not-trusted",
            "bytes": -1,
        }

    def test_build_file_identity_uses_actual_raw_bytes(self):
        content = b"raw\r\nbytes\x00\xff"
        path = self.write_fixture("raw.bin", content)
        self.assertEqual(build_file_identity(path, self.root), {
            "path": "data/evaluation/corpus/raw.bin",
            "sha256": hashlib.sha256(content).hexdigest(),
            "bytes": len(content),
        })

    def test_build_file_identity_normalizes_to_relative_posix_path(self):
        path = self.write_fixture("nested.txt", b"fixture")
        identity = build_file_identity(path, self.root)
        self.assertEqual(identity["path"], "data/evaluation/corpus/nested.txt")
        self.assertNotIn("\\", identity["path"])
        self.assertFalse(Path(identity["path"]).is_absolute())

    def test_build_file_identity_rejects_outside_project_root(self):
        outside = self.root.parent / "outside.txt"
        outside.write_bytes(b"outside")
        with self.assertRaises(ValueError):
            build_file_identity(outside, self.root)

    def test_build_file_identity_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            build_file_identity(self.corpus / "missing.txt", self.root)

    def test_collect_uses_manifest_document_ids_and_sorts_by_path(self):
        self.write_fixture("zeta.txt", b"z")
        self.write_fixture("alpha.txt", b"a")
        manifest = self.manifest([
            self.entry("zeta.txt", "doc_z"),
            self.entry("alpha.txt", "doc_a"),
        ])
        identities = collect_corpus_identities(manifest, self.root)
        self.assertEqual([item["path"] for item in identities], [
            "data/evaluation/corpus/alpha.txt",
            "data/evaluation/corpus/zeta.txt",
        ])
        self.assertEqual([item["document_id"] for item in identities], ["doc_a", "doc_z"])

    def test_collect_missing_corpus_file_raises(self):
        manifest = self.manifest([self.entry("missing.txt", "doc_missing")])
        with self.assertRaises(FileNotFoundError):
            collect_corpus_identities(manifest, self.root)

    def test_collect_rejects_manifest_path_outside_project_root(self):
        outside = self.root.parent / "outside.txt"
        outside.write_bytes(b"outside")
        manifest = self.manifest([{
            "path": "../outside.txt", "document_id": "doc_outside",
            "sha256": "manifest-value-is-not-trusted", "bytes": -1,
        }])
        with self.assertRaises(ValueError):
            collect_corpus_identities(manifest, self.root)

    def test_collect_rejects_duplicate_document_id(self):
        self.write_fixture("a.txt", b"a")
        self.write_fixture("b.txt", b"b")
        manifest = self.manifest([
            self.entry("a.txt", "duplicate"),
            self.entry("b.txt", "duplicate"),
        ])
        with self.assertRaises(ValueError):
            collect_corpus_identities(manifest, self.root)

    def test_collect_rejects_duplicate_path(self):
        self.write_fixture("same.txt", b"same")
        manifest = self.manifest([
            self.entry("same.txt", "doc_a"),
            self.entry("same.txt", "doc_b"),
        ])
        with self.assertRaises(ValueError):
            collect_corpus_identities(manifest, self.root)

    def test_collect_does_not_modify_manifest_or_files(self):
        from copy import deepcopy

        content = "冻结语料\r\n".encode("utf-8")
        path = self.write_fixture("frozen.txt", content)
        manifest = self.manifest([self.entry("frozen.txt", "doc_frozen")])
        before = deepcopy(manifest)
        collect_corpus_identities(manifest, self.root)
        self.assertEqual(manifest, before)
        self.assertEqual(path.read_bytes(), content)


class RunProvenanceCollectorTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix="knowledgepilot-run-provenance-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "project"
        self.corpus = self.root / "data" / "evaluation" / "corpus"
        self.code = self.root / "src" / "knowledge_pilot"
        self.corpus.mkdir(parents=True)
        self.code.mkdir(parents=True)

        self.dataset_path = self.root / "data" / "evaluation" / "cases.json"
        self.dataset_path.write_bytes(b'{"dataset_version":"synthetic"}\n')
        (self.corpus / "zeta.txt").write_bytes(b"zeta")
        (self.corpus / "alpha.txt").write_bytes("中文语料".encode("utf-8"))
        self.code_a = self.code / "a.py"
        self.code_z = self.code / "z.py"
        self.code_a.write_bytes(b"A = 1\n")
        self.code_z.write_bytes(b"Z = 1\n")

        self.manifest = {
            "manifest_schema_version": "synthetic-v1",
            "corpus_files": [
                {"path": "data/evaluation/corpus/zeta.txt", "document_id": "doc_z"},
                {"path": "data/evaluation/corpus/alpha.txt", "document_id": "doc_a"},
            ],
        }
        self.manifest_path = self.root / "data" / "evaluation" / "manifest.json"
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False), encoding="utf-8", newline="\n"
        )

    def collect(self, code_paths=None):
        return collect_run_provenance(
            project_root=self.root,
            dataset_path=self.dataset_path,
            manifest_path=self.manifest_path,
            code_paths=[self.code_z, self.code_a] if code_paths is None else code_paths,
        )

    @staticmethod
    def git_result(command, **kwargs):
        if "rev-parse" in command:
            return subprocess.CompletedProcess(command, 0, stdout="1" * 40 + "\n", stderr="")
        if "status" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected Git command: {command}")

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_dataset_manifest_and_corpus_identities_are_bound(self, run):
        run.side_effect = self.git_result
        result = self.collect()
        self.assertEqual(result["dataset"], build_file_identity(self.dataset_path, self.root))
        self.assertEqual(result["manifest"], build_file_identity(self.manifest_path, self.root))
        self.assertEqual(result["corpus_files"], collect_corpus_identities(self.manifest, self.root))

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_corpus_order_is_deterministic(self, run):
        run.side_effect = self.git_result
        paths = [item["path"] for item in self.collect()["corpus_files"]]
        self.assertEqual(paths, sorted(paths))

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_code_identities_are_complete_and_path_sorted(self, run):
        run.side_effect = self.git_result
        result = self.collect()
        self.assertEqual(result["code_files"], [
            build_file_identity(self.code_a, self.root),
            build_file_identity(self.code_z, self.root),
        ])

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_source_change_changes_recorded_code_identity(self, run):
        run.side_effect = self.git_result
        before = self.collect()["code_files"]
        self.code_a.write_bytes(b"A = 2\n")
        after = self.collect()["code_files"]
        self.assertNotEqual(before, after)
        self.assertNotEqual(before[0]["sha256"], after[0]["sha256"])

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_git_commit_is_recorded(self, run):
        run.side_effect = self.git_result
        result = self.collect()
        self.assertEqual(result["git_commit"], "1" * 40)
        self.assertFalse(result["git_worktree_dirty"])
        self.assertEqual(result["observation_errors"], [])

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_untracked_git_output_marks_worktree_dirty(self, run):
        def dirty_git(command, **kwargs):
            if "rev-parse" in command:
                return subprocess.CompletedProcess(command, 0, stdout="2" * 40 + "\n", stderr="")
            return subprocess.CompletedProcess(command, 0, stdout="?? untracked.txt\n", stderr="")

        run.side_effect = dirty_git
        self.assertTrue(self.collect()["git_worktree_dirty"])

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_git_unavailable_records_explicit_observation_error(self, run):
        run.side_effect = FileNotFoundError("git executable unavailable")
        result = self.collect()
        self.assertIsNone(result["git_commit"])
        self.assertIsNone(result["git_worktree_dirty"])
        self.assertTrue(result["observation_errors"])
        self.assertTrue(any("git" in message.lower() for message in result["observation_errors"]))

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_python_version_is_recorded_from_runtime(self, run):
        run.side_effect = self.git_result
        self.assertEqual(self.collect()["python_version"], platform.python_version())

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_missing_required_dataset_fails(self, run):
        run.side_effect = self.git_result
        self.dataset_path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.collect()

    @patch("knowledge_pilot.evaluation.run_provenance.subprocess.run")
    def test_inputs_and_required_files_are_not_modified(self, run):
        from copy import deepcopy

        run.side_effect = self.git_result
        code_paths = [self.code_z, self.code_a]
        paths_before = deepcopy(code_paths)
        bytes_before = {
            path: path.read_bytes()
            for path in [self.dataset_path, self.manifest_path, self.code_a, self.code_z,
                         self.corpus / "alpha.txt", self.corpus / "zeta.txt"]
        }
        self.collect(code_paths)
        self.assertEqual(code_paths, paths_before)
        self.assertEqual({path: path.read_bytes() for path in bytes_before}, bytes_before)
