"""Synthetic tests: no real model or database is imported."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from knowledge_pilot.evaluation.hybrid import (
    RetrievalError, adapt_dense_results, fuse_rrf, retrieve_hybrid,
)
from knowledge_pilot.evaluation.hybrid_evaluation import run_hybrid_cases, summarize_hybrid_cases
from knowledge_pilot.evaluation.run_report import build_run_report
from knowledge_pilot.evaluation.run_provenance import collect_run_provenance
from knowledge_pilot.evaluation.json_writer import write_json_exclusive


def dense(ids):
    return [(f'文本{i}', 0.9 - n * 0.1, {'document_id': i, 'chunk_index': 0, 'source': '合成'})
            for n, i in enumerate(ids)]


def lexical(ids):
    return [dict(document_id=i, chunk_index=0, text=f'文本{i}', rank=n,
                 score=20.0 / n, score_type='bm25_okapi', source='合成')
            for n, i in enumerate(ids, 1)]


def case(id='q', relevant='a'):
    return dict(id=id, case_type='retrieval', query='中文 query',
                relevant_chunks=[dict(document_id=relevant, chunk_index=0)])


class RRFTests(unittest.TestCase):
    def test_manual_rrf_sum_and_identity_deduplication(self):
        hits = fuse_rrf(adapt_dense_results(dense(['a', 'b'])), lexical(['b', 'a']))
        self.assertEqual(len(hits), 2)
        self.assertAlmostEqual(hits[0]['score'], 1/61 + 1/62)
        self.assertEqual([x['document_id'] for x in hits], ['a', 'b'])

    def test_top_five_to_final_three(self):
        result = retrieve_hybrid('q', lambda q,k: dense(['a','b','c','d','e']),
                                 lambda q,k: lexical(['e','d','c','b','a']))
        self.assertEqual(len(result['candidates']), 3)
        self.assertEqual([x['document_id'] for x in result['candidates']], ['a','e','b'])
        self.assertEqual(len(result['branches']['dense']['candidates']), 5)

    def test_raw_scores_ranks_and_contributions_are_separate(self):
        item = fuse_rrf(adapt_dense_results(dense(['a'])), lexical(['a']))[0]
        self.assertEqual(item['score_type'], 'rrf')
        self.assertNotIn('similarity', item)
        self.assertEqual(item['dense_similarity'], 0.9)
        self.assertEqual(item['bm25_score'], 20)
        self.assertEqual((item['dense_rank'], item['bm25_rank'], item['rank']), (1,1,1))
        self.assertAlmostEqual(item['dense_rrf_contribution'], 1/61)
        self.assertAlmostEqual(item['bm25_rrf_contribution'], 1/61)
        self.assertEqual(item['sources'], ['dense','bm25'])

    def test_missing_branch_has_zero_contribution_and_null_rank_score(self):
        hit = fuse_rrf([], lexical(['a']))[0]
        self.assertEqual(hit['dense_rrf_contribution'], 0)
        self.assertIsNone(hit['dense_similarity'])
        self.assertIsNone(hit['dense_rank'])

    def test_tie_break_uses_numeric_chunk_index(self):
        a, b = lexical(['doc','other'])
        a['chunk_index']=10; b['document_id']='doc'; b['chunk_index']=2
        a['rank']=1; b['rank']=2
        d=[dict(b,rank=1,score_type='cosine_similarity'),
           dict(a,rank=2,score_type='cosine_similarity')]
        hits=fuse_rrf(d,[a,b])
        self.assertEqual([h['chunk_index'] for h in hits],[2,10])

    def test_same_branch_duplicate_identity_is_rejected(self):
        with self.assertRaises(ValueError):
            fuse_rrf([], lexical(['a','a']))

    def test_disagreeing_text_for_same_identity_is_rejected(self):
        b=lexical(['a']); b[0]['text']='changed'
        with self.assertRaises(ValueError):
            fuse_rrf(adapt_dense_results(dense(['a'])),b)

    def test_inputs_and_nested_metadata_are_not_modified(self):
        d=dense(['a']); b=lexical(['a']); before=deepcopy((d,b))
        result=fuse_rrf(adapt_dense_results(d),b)
        result[0]['sources'].append('changed')
        self.assertEqual((d,b),before)

    def test_non_contiguous_rank_rejected(self):
        b=lexical(['a']); b[0]['rank']=0
        with self.assertRaises(ValueError): fuse_rrf([],b)

    def test_invalid_parameters_rejected(self):
        for c,k in [(-1,3),(60,-1)]:
            with self.assertRaises(ValueError): fuse_rrf([],[],rrf_constant=c,k=k)

    def test_dense_negative_similarity_is_preserved(self):
        d=[('text',-0.25,dict(document_id='a',chunk_index=7))]
        h=fuse_rrf(adapt_dense_results(d),[])[0]
        self.assertEqual(h['dense_similarity'],-0.25)


class BranchTests(unittest.TestCase):
    def fail(self,q,k): raise RetrievalError('synthetic service failure',stage='embedding')

    def test_full_hybrid_calls_both_at_five(self):
        calls=[]
        def ds(q,k): calls.append(('dense',q,k)); return dense(['a'])
        def bs(q,k): calls.append(('bm25',q,k)); return lexical(['a'])
        r=retrieve_hybrid('q',ds,bs)
        self.assertEqual(calls,[('dense','q',5),('bm25','q',5)])
        self.assertEqual(r['mode'],'full_hybrid')
        self.assertTrue(all(x['latency_ms']>=0 for x in r['branches'].values()))

    def test_dense_failure_falls_back_bm25_order_and_records_error(self):
        r=retrieve_hybrid('q',self.fail,lambda q,k:lexical(['z','a','b','c']))
        self.assertEqual(r['mode'],'fallback_bm25')
        self.assertEqual([x['document_id'] for x in r['candidates']],['z','a','b'])
        self.assertEqual(r['branches']['dense']['error_stage'],'embedding')
        self.assertIn('synthetic service failure',r['branches']['dense']['error'])

    def test_bm25_failure_falls_back_dense(self):
        r=retrieve_hybrid('q',lambda q,k:dense(['z','a']),self.fail)
        self.assertEqual(r['mode'],'fallback_dense')
        self.assertEqual(r['candidates'][0]['document_id'],'z')
        self.assertAlmostEqual(r['candidates'][0]['score'],1/61)

    def test_both_failure_is_retrieval_failed(self):
        r=retrieve_hybrid('q',self.fail,self.fail)
        self.assertEqual(r['mode'],'retrieval_failed')
        self.assertEqual(r['candidates'],[])

    def test_empty_is_normal_not_failure(self):
        r=retrieve_hybrid('q',lambda q,k:[],lambda q,k:lexical(['a']))
        self.assertEqual(r['mode'],'full_hybrid')
        self.assertEqual(r['branches']['dense']['status'],'empty')
        self.assertIsNone(r['branches']['dense']['error'])

    def test_both_empty_is_successful_empty(self):
        r=retrieve_hybrid('q',lambda q,k:[],lambda q,k:[])
        self.assertEqual(r['mode'],'full_hybrid')
        self.assertEqual(r['candidates'],[])

    def test_failed_plus_empty_is_fallback_empty(self):
        r=retrieve_hybrid('q',self.fail,lambda q,k:[])
        self.assertEqual(r['mode'],'fallback_bm25')
        self.assertEqual(r['candidates'],[])

    def test_programming_error_is_not_swallowed(self):
        def bug(q,k): raise TypeError('program defect')
        with self.assertRaises(TypeError): retrieve_hybrid('q',bug,lambda q,k:[])

    def test_malformed_output_is_not_service_failure(self):
        with self.assertRaises(KeyError):
            retrieve_hybrid('q',lambda q,k:[('text',0.5,{})],lambda q,k:[])

    def test_over_depth_branch_result_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_hybrid('q',lambda q,k:dense(list('abcdef')),lambda q,k:[])


class EvaluationTests(unittest.TestCase):
    def test_case_filter_mapping_and_success_metrics(self):
        cases=[case('first'),dict(id='skip',case_type='agent'),case('second','b')]
        r=run_hybrid_cases(cases,lambda q,k:dense(['a','b']),lambda q,k:lexical(['a']))
        self.assertEqual([x['case_id'] for x in r],['first','second'])
        self.assertEqual(r[0]['metrics'],dict(hit=1,recall=1.0,rr=1.0))
        self.assertEqual(r[1]['metrics']['rr'],0.5)

    def test_failures_empty_and_denominators(self):
        def bad(q,k): raise RetrievalError('down')
        failed=run_hybrid_cases([case()],bad,bad)
        empty=run_hybrid_cases([case('empty')],lambda q,k:[],lambda q,k:[])
        s=summarize_hybrid_cases(failed+empty)
        self.assertEqual(s['case_counts'],dict(total=2,success=1,retrieval_failed=1,scoring_failed=0))
        self.assertEqual(s['metric_denominators'],dict(hit_rate=1,mean_recall=1,mrr=1))
        self.assertEqual(s['hit_rate'],0)
        self.assertEqual(s['zero_candidate_success_count'],1)

    def test_fallback_counted_and_candidates_preserved_on_scoring_failure(self):
        def bad(q,k): raise RetrievalError('down')
        r=run_hybrid_cases([case()],bad,lambda q,k:lexical(['a']))
        self.assertEqual(summarize_hybrid_cases(r)['fallback_count'],1)
        with patch('knowledge_pilot.evaluation.hybrid_evaluation.evaluate_retrieval_case',side_effect=ValueError('bad annotation')):
            r=run_hybrid_cases([case()],bad,lambda q,k:lexical(['a']))
        self.assertEqual(r[0]['status'],'scoring_failed')
        self.assertEqual(len(r[0]['candidates']),1)
        self.assertEqual(r[0]['error_stage'],'scoring')

    def test_case_inputs_unchanged(self):
        cases=[case()]; before=deepcopy(cases)
        run_hybrid_cases(cases,lambda q,k:dense(['a']),lambda q,k:[])
        self.assertEqual(cases,before)

    def test_report_json_provenance_round_trip_and_no_overwrite(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); dataset=root/'cases.json'; manifest=root/'manifest.json'; corpus=root/'doc.txt'; code=root/'code.py'
            dataset.write_text('{}',encoding='utf-8'); corpus.write_text('中文冻结合成资料',encoding='utf-8'); code.write_text('x=1',encoding='utf-8')
            manifest.write_text(json.dumps(dict(corpus_files=[dict(path='doc.txt',document_id='a')])),encoding='utf-8')
            with patch('knowledge_pilot.evaluation.run_provenance.subprocess.run',side_effect=FileNotFoundError('synthetic git unavailable')):
                provenance=collect_run_provenance(project_root=root,dataset_path=dataset,manifest_path=manifest,code_paths=[code])
            records=run_hybrid_cases([case()],lambda q,k:dense(['a']),lambda q,k:lexical(['a']))
            before=deepcopy((records,provenance))
            report=build_run_report(run_id='synthetic',strategy='hybrid_rrf',strategy_config={'rrf_constant':60},k=3,started_at_utc='2026-01-01T00:00:00Z',finished_at_utc='2026-01-01T00:00:01Z',dataset_version='synthetic',corpus_version='synthetic',provenance=provenance,cases=records,summary=summarize_hybrid_cases(records))
            target=root/'report.json'; write_json_exclusive(target,report)
            self.assertEqual(json.loads(target.read_text(encoding='utf-8')),report)
            self.assertEqual(report['schema_version'],'retrieval_run_report_v1')
            report['cases'][0]['branches']['dense']['candidates'][0]['text']='changed'
            self.assertEqual((records,provenance),before)
            with self.assertRaises(FileExistsError): write_json_exclusive(target,{})


if __name__=='__main__': unittest.main()
