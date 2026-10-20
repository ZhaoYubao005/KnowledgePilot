"""Real paired RRF depth-3/depth-5 evaluation; frozen runtime is only copied."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from run_bm25_baseline_v13 import _export_verified_chunks
from run_dense_baseline_v13 import _verify_embedding_model

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT/'data/evaluation/cases_v1.json'
MANIFEST = PROJECT_ROOT/'data/evaluation/manifests/evaluation_v1.json'
FROZEN = PROJECT_ROOT/'data/evaluation/runtime/corpus_v1'


def _fingerprints(paths):
    return {p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def _protected_files():
    return sorted(p for p in (PROJECT_ROOT/'data').rglob('*') if p.is_file())


def _worker(args):
    from knowledge_pilot.evaluation.hybrid_runtime import make_dense_search, validate_isolated_runtime
    runtime = validate_isolated_runtime(Path(args.runtime_copy),Path(args.temporary_root),FROZEN)
    if runtime.is_relative_to(PROJECT_ROOT):
        raise ValueError('Runtime copy must be outside the project')
    os.chdir(runtime)
    opened=time.perf_counter()
    import requests
    from chromadb.errors import ChromaError
    from knowledge_pilot.vector_store.chroma_store import collection
    open_ms=(time.perf_counter()-opened)*1000
    from knowledge_pilot.evaluation.bm25 import BM25Index, TOKENIZER_NAME, TOKENIZER_VERSION, IDF_FORMULA
    from knowledge_pilot.evaluation.dense_baseline import load_retrieval_cases
    from knowledge_pilot.evaluation.hybrid_evaluation import run_hybrid_cases, summarize_hybrid_cases
    from knowledge_pilot.evaluation.run_provenance import collect_run_provenance
    from knowledge_pilot.evaluation.run_report import build_run_report
    from knowledge_pilot.evaluation.json_writer import write_json_exclusive
    from knowledge_pilot.evaluation.rag_evaluator import evaluate_retrieval_case
    from statistics import mean

    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    model=_verify_embedding_model(manifest)
    if collection.name != manifest['collection']['name'] or collection.count()!=19:
        raise RuntimeError('Frozen collection identity/count mismatch')
    configuration=collection.configuration
    if configuration['hnsw']['space'] != manifest['collection']['distance_metric']:
        raise RuntimeError('Frozen collection metric mismatch')
    chunks=_export_verified_chunks(collection,manifest)
    indexed=time.perf_counter(); index=BM25Index(chunks,k1=1.2,b=0.75)
    index_ms=(time.perf_counter()-indexed)*1000
    versions,cases=load_retrieval_cases(DATASET)
    if len(cases)!=16 or versions!={'dataset_version':'v1','corpus_version':'corpus_v1'}:
        raise RuntimeError('Frozen dataset identity/count mismatch')
    dense=make_dense_search(collection,post=requests.post,
                            service_errors=(requests.RequestException,ChromaError),
                            model=manifest['embedding']['model_identifier'],
                            dimensions=manifest['embedding']['dimensions'])
    code_paths=[PROJECT_ROOT/('src/knowledge_pilot/evaluation/'+name+'.py') for name in
                ('hybrid','hybrid_evaluation','hybrid_runtime','bm25','bm25_baseline','dense_baseline',
                 'case_evidence','evidence_collector','run_report','run_provenance','json_writer','rag_evaluator','rag_metrics')]
    code_paths += [Path(__file__).resolve(),PROJECT_ROOT/'scripts/run_bm25_baseline_v13.py',
                   PROJECT_ROOT/'scripts/run_dense_baseline_v13.py',
                   PROJECT_ROOT/'src/knowledge_pilot/vector_store/chroma_store.py',
                   PROJECT_ROOT/'src/knowledge_pilot/retrieval/embedding.py']
    for depth in (3,5):
        started=datetime.now(timezone.utc)
        records=run_hybrid_cases(cases,dense,index.search,branch_k=depth,k=3,rrf_constant=60)
        finished=datetime.now(timezone.utc)
        _verify_embedding_model(manifest)  # Reject model changes during the paired run.
        summary=summarize_hybrid_cases(records)
        # Fresh component Top-3 values from this run's actual branch lists; no old report reuse.
        component_summaries={}
        for name in ('dense','bm25'):
            scores=[]
            for case,record in zip(cases,records):
                branch=record['branches'][name]
                if branch['status']=='failed':
                    continue
                results=[(x['text'],x['score'],dict(document_id=x['document_id'],chunk_index=x['chunk_index']))
                         for x in branch['candidates'][:3]]
                scores.append(evaluate_retrieval_case(case,results,3))
            component_summaries[name]={key:mean(x[metric] for x in scores) if scores else None
                                     for key,metric in (('hit_rate','hit'),('mean_recall','recall'),('mrr','rr'))}
            component_summaries[name]['denominator']=len(scores)
        summary['fresh_component_top3']=component_summaries
        provenance=collect_run_provenance(project_root=PROJECT_ROOT,dataset_path=DATASET,
                                          manifest_path=MANIFEST,code_paths=code_paths)
        config=dict(branch_top_k=depth,final_top_k=3,rrf_constant=60,
                    rrf_formula='sum(1 / (60 + one_based_rank)); missing branch contribution = 0',
                    deduplication_key=['document_id','chunk_index'],
                    tie_break=['score descending','document_id ascending','chunk_index numeric ascending'],
                    embedding=model,collection=dict(name=collection.name,configuration=configuration),
                    dense_similarity='1 - cosine_distance',
                    bm25=dict(k1=1.2,b=0.75,idf_formula=IDF_FORMULA,
                              tokenizer=dict(name=TOKENIZER_NAME,version=TOKENIZER_VERSION)),
                    index=dict(chunk_count=len(chunks),average_document_length_tokens=index.average_document_length,
                               all_chunk_text_hashes_verified=True,index_build_ms=index_ms),
                    initialization_ms=dict(runtime_copy=args.copy_ms,chroma_open=open_ms),
                    runtime_isolation='temporary byte-for-byte frozen runtime copy; no ingestion',
                    frozen_runtime_files={Path(path).relative_to(PROJECT_ROOT).as_posix():digest
                                          for path,digest in _fingerprints(sorted(p for p in FROZEN.rglob('*') if p.is_file())).items()},
                    execution='sequential Dense then BM25; depth 3 arm before depth 5; fresh retrieval per arm',
                    latency_boundary=summary['latency_ms']['boundary'])
        stamp=started.strftime('%Y%m%dT%H%M%S_%fZ')
        report=build_run_report(run_id=f'hybrid-rrf-depth{depth}-{stamp}',strategy='hybrid_rrf',
                               strategy_config=config,k=3,started_at_utc=started.isoformat(),
                               finished_at_utc=finished.isoformat(),dataset_version=versions['dataset_version'],
                               corpus_version=versions['corpus_version'],provenance=provenance,cases=records,summary=summary)
        output=Path(args.output_dir)/f'hybrid_rrf_v13_depth{depth}_k3_{stamp}.json'
        write_json_exclusive(output,report)
        print(json.dumps(dict(report=str(output),summary=summary),ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,default=PROJECT_ROOT/'data/evaluation/reports')
    parser.add_argument('--runtime-copy',help=argparse.SUPPRESS)
    parser.add_argument('--temporary-root',help=argparse.SUPPRESS)
    parser.add_argument('--copy-ms',type=float,help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.runtime_copy:
        _worker(args)
        return
    if not args.output_dir.is_dir():
        raise FileNotFoundError(args.output_dir)
    manifest=json.loads(MANIFEST.read_text(encoding='utf-8'))
    _verify_embedding_model(manifest)
    for item in manifest['corpus_files']:
        if hashlib.sha256((PROJECT_ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:
            raise RuntimeError(f'Frozen corpus hash mismatch: {item["path"]}')
    protected=_protected_files(); before=_fingerprints(protected)
    try:
        with TemporaryDirectory(prefix='knowledgepilot-hybrid-') as tmp:
            runtime=Path(tmp)/'corpus_v1'
            copied=time.perf_counter(); shutil.copytree(FROZEN,runtime); copy_ms=(time.perf_counter()-copied)*1000
            env=os.environ.copy()
            env.update(PYTHONPATH=str(PROJECT_ROOT/'src'),PYTHONDONTWRITEBYTECODE='1',ANONYMIZED_TELEMETRY='False')
            subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--runtime-copy',str(runtime),
                            '--temporary-root',tmp,'--copy-ms',str(copy_ms),'--output-dir',str(args.output_dir.resolve())],
                           cwd=runtime,env=env,check=True)
    finally:
        if _fingerprints(protected)!=before:
            raise RuntimeError('Protected original data changed during experiment')


if __name__=='__main__': main()
