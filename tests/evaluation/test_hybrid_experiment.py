"""Script safety and frozen export contracts; synthetic collection only."""
import hashlib
import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
sys.path.insert(0,str(SCRIPTS))
try:
    spec=importlib.util.spec_from_file_location('hybrid_experiment',SCRIPTS/'run_hybrid_baseline_v13.py')
    experiment=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(experiment)
finally:
    sys.path.remove(str(SCRIPTS))


class ExperimentTests(unittest.TestCase):
    def fixture(self):
        docs=[f'中文 {i}' for i in range(19)]
        metadata=[dict(document_id='doc',chunk_index=i,source='synthetic') for i in range(19)]
        collection=Mock()
        collection.get.return_value=dict(documents=docs,metadatas=metadata)
        manifest=dict(chunks=[dict(document_id='doc',chunk_index=i,sha256=hashlib.sha256(text.encode()).hexdigest())
                              for i,text in enumerate(docs)])
        return collection,manifest

    def test_all_19_text_hashes_and_numeric_identities_preserved(self):
        collection,manifest=self.fixture()
        result=experiment._export_verified_chunks(collection,manifest)
        self.assertEqual(len(result),19)
        self.assertEqual([x['chunk_index'] for x in result],list(range(19)))
        self.assertEqual(result[0]['text'],'中文 0')

    def test_changed_text_rejected(self):
        collection,manifest=self.fixture(); collection.get.return_value['documents'][0]='changed'
        with self.assertRaises(RuntimeError): experiment._export_verified_chunks(collection,manifest)

    def test_missing_chunk_rejected(self):
        collection,manifest=self.fixture()
        collection.get.return_value['documents'].pop(); collection.get.return_value['metadatas'].pop()
        with self.assertRaises(RuntimeError): experiment._export_verified_chunks(collection,manifest)

    def test_duplicate_identity_rejected(self):
        collection,manifest=self.fixture()
        collection.get.return_value['documents'][1]=collection.get.return_value['documents'][0]
        collection.get.return_value['metadatas'][1]=collection.get.return_value['metadatas'][0]
        with self.assertRaises(RuntimeError): experiment._export_verified_chunks(collection,manifest)

    def test_original_runtime_rejected_before_chroma_import(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); frozen=root/'original'; frozen.mkdir()
            args=SimpleNamespace(runtime_copy=str(frozen),temporary_root=str(root))
            with patch.object(experiment,'FROZEN',frozen):
                with self.assertRaises(ValueError): experiment._worker(args)

    def test_fingerprinting_only_reads_bytes(self):
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/'frozen.txt'; raw='冻结\n'.encode(); file.write_bytes(raw)
            expected=hashlib.sha256(raw).hexdigest()
            self.assertEqual(experiment._fingerprints([file]),{file.as_posix():expected})
            self.assertEqual(file.read_bytes(),raw)


if __name__=='__main__': unittest.main()
