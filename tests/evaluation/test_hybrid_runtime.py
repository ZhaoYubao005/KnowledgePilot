"""Transport adapter and runtime guard tests with synthetic services only."""
import unittest
from unittest.mock import Mock

from knowledge_pilot.evaluation.hybrid import RetrievalError
from knowledge_pilot.evaluation.hybrid_runtime import make_dense_search, validate_isolated_runtime


class RuntimeTests(unittest.TestCase):
    def fixture(self):
        response=Mock(); response.json.return_value={'embeddings':[[0.1,0.2]]}
        post=Mock(return_value=response)
        collection=Mock(); collection.query.return_value={
            'documents':[['中文']], 'distances':[[1.25]],
            'metadatas':[[dict(document_id='a',chunk_index=0)]]}
        return collection,post

    def test_dense_adapter_real_top_k_raw_similarity_and_timeout(self):
        c,p=self.fixture(); search=make_dense_search(c,post=p,service_errors=(OSError,),dimensions=2)
        result=search('query',5)
        self.assertEqual(result,[('中文',-0.25,dict(document_id='a',chunk_index=0))])
        self.assertEqual(c.query.call_args.kwargs['n_results'],5)
        self.assertEqual(p.call_args.kwargs['json'],{'model':'bge-m3','input':'query'})
        self.assertEqual(p.call_args.kwargs['timeout'],(5,120))

    def test_embedding_transport_error_has_stage(self):
        c,p=self.fixture(); p.side_effect=OSError('offline')
        with self.assertRaises(RetrievalError) as ctx:
            make_dense_search(c,post=p,service_errors=(OSError,),dimensions=2)('q',5)
        self.assertEqual(ctx.exception.stage,'embedding')

    def test_chroma_service_error_has_stage(self):
        c,p=self.fixture(); c.query.side_effect=OSError('unavailable')
        with self.assertRaises(RetrievalError) as ctx:
            make_dense_search(c,post=p,service_errors=(OSError,),dimensions=2)('q',5)
        self.assertEqual(ctx.exception.stage,'dense_query')

    def test_bad_embedding_response_explicit_failure(self):
        c,p=self.fixture(); p.return_value.json.return_value={'error':'model unavailable'}
        with self.assertRaises(RetrievalError):
            make_dense_search(c,post=p,service_errors=(OSError,),dimensions=2)('q',5)

    def test_programming_error_propagates(self):
        c,p=self.fixture(); c.query.side_effect=TypeError('defect')
        with self.assertRaises(TypeError):
            make_dense_search(c,post=p,service_errors=(OSError,),dimensions=2)('q',5)

    def test_original_runtime_and_external_runtime_rejected(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            root=Path(tmp); frozen=root/'original'; frozen.mkdir()
            copied=root/'copied'; copied.mkdir()
            with self.assertRaises(ValueError): validate_isolated_runtime(frozen,root,frozen)
            with self.assertRaises(ValueError): validate_isolated_runtime(copied,frozen,frozen)
            self.assertEqual(validate_isolated_runtime(copied,root,frozen),copied.resolve())


if __name__=='__main__': unittest.main()
