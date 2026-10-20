"""Run V1.3 BM25 against the exact 19 chunks in an isolated Chroma copy."""

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
from typing import cast


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data/evaluation/cases_v1.json"
MANIFEST_PATH = PROJECT_ROOT / "data/evaluation/manifests/evaluation_v1.json"
FROZEN_RUNTIME = PROJECT_ROOT / "data/evaluation/runtime/corpus_v1"
REPORT_DIRECTORY = PROJECT_ROOT / "data/evaluation/reports"


def _load_manifest():
    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _default_output():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return REPORT_DIRECTORY / f"bm25_v13_k3_{stamp}.json"


def _export_verified_chunks(collection, manifest):
    exported = collection.get(include=["documents", "metadatas"])
    documents = exported["documents"]
    metadatas = exported["metadatas"]
    expected = {
        (item["document_id"], item["chunk_index"]): item["sha256"]
        for item in manifest["chunks"]
    }
    chunks = []
    for text, metadata in zip(documents, metadatas):
        identity = (metadata["document_id"], metadata["chunk_index"])
        if identity not in expected:
            raise RuntimeError(f"Unexpected chunk identity: {identity}")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest != expected[identity]:
            raise RuntimeError(f"Chunk byte identity mismatch: {identity}")
        chunks.append({
            "document_id": identity[0], "chunk_index": identity[1],
            "text": text, "source": metadata.get("source"),
        })
    chunks.sort(key=lambda item: (item["document_id"], item["chunk_index"]))
    if len(chunks) != 19 or set((c["document_id"], c["chunk_index"]) for c in chunks) != set(expected):
        raise RuntimeError("Frozen chunk set must contain exactly the 19 manifest identities")
    return chunks


def _run_worker(args):
    runtime_root = Path(args.runtime_copy).resolve()
    os.chdir(runtime_root)
    open_started = time.perf_counter()
    from knowledge_pilot.vector_store.chroma_store import collection
    collection_open_ms = (time.perf_counter() - open_started) * 1000

    from knowledge_pilot.evaluation.bm25 import (
        BM25Index, BM25_SCORE_TYPE, IDF_FORMULA, TOKENIZER_NAME, TOKENIZER_VERSION,
    )
    from knowledge_pilot.evaluation.bm25_baseline import run_bm25_cases, summarize_bm25_cases
    from knowledge_pilot.evaluation.case_evidence import CaseEvidence
    from knowledge_pilot.evaluation.dense_baseline import load_retrieval_cases
    from knowledge_pilot.evaluation.json_writer import write_json_exclusive
    from knowledge_pilot.evaluation.run_provenance import collect_run_provenance
    from knowledge_pilot.evaluation.run_report import build_run_report

    manifest = _load_manifest()
    chunks = _export_verified_chunks(collection, manifest)
    index_started = time.perf_counter()
    index = BM25Index(chunks, k1=1.2, b=0.75)
    index_build_ms = (time.perf_counter() - index_started) * 1000
    metadata, cases = load_retrieval_cases(DATASET_PATH)
    if len(cases) != 16:
        raise RuntimeError(f"Expected 16 retrieval cases, got {len(cases)}")

    started = datetime.now(timezone.utc)
    records = run_bm25_cases(cases, index.search, k=3)
    finished = datetime.now(timezone.utc)
    summary = summarize_bm25_cases(records)
    code_paths = [
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/bm25.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/bm25_baseline.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/dense_baseline.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/run_report.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/run_provenance.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/json_writer.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/rag_evaluator.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/rag_metrics.py",
        PROJECT_ROOT / "src/knowledge_pilot/vector_store/chroma_store.py",
        Path(__file__).resolve(),
    ]
    provenance = collect_run_provenance(
        project_root=PROJECT_ROOT, dataset_path=DATASET_PATH,
        manifest_path=MANIFEST_PATH, code_paths=code_paths,
    )
    strategy_config = {
        "algorithm": "Okapi BM25",
        "k1": 1.2, "b": 0.75, "idf_formula": IDF_FORMULA,
        "score_type": BM25_SCORE_TYPE,
        "tokenizer": {
            "name": TOKENIZER_NAME, "version": TOKENIZER_VERSION,
            "language_model": "none",
            "cjk": "contiguous CJK emits character unigrams and adjacent bigrams",
            "technical_identifiers": "lowercased whole Python identifiers, API paths, alphanumeric and hyphenated terms",
        },
        "top_k": 3,
        "index": {
            "document_count": len(chunks),
            "average_document_length_tokens": index.average_document_length,
            "unique_terms": len(index.idf),
            "build_ms": index_build_ms,
        },
        "runtime_isolation": "temporary byte-for-byte copy of frozen Chroma runtime",
        "chunk_export": "collection.get documents+metadatas; all 19 text hashes verified against manifest",
        "runtime_copy_ms": args.copy_ms,
        "chroma_open_ms": collection_open_ms,
        "query_latency_boundary": summary["latency_ms"]["boundary"],
    }
    report = build_run_report(
        run_id=started.strftime("bm25-v13-%Y%m%dT%H%M%S-%fZ"),
        strategy="bm25_okapi",
        strategy_config=strategy_config,
        k=3,
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        finished_at_utc=finished.isoformat().replace("+00:00", "Z"),
        dataset_version=metadata["dataset_version"],
        corpus_version=metadata["corpus_version"],
        provenance=provenance,
        cases=cast(list[CaseEvidence], records),
        summary=summary,
    )
    output = write_json_exclusive(Path(args.output).resolve(), report)
    print(json.dumps({"report": str(output), "summary": summary,
                      "index": strategy_config["index"]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--runtime-copy", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--copy-ms", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.runtime_copy:
        _run_worker(args)
        return
    output = (args.output or _default_output()).resolve()
    if not output.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output.parent}")
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(prefix="knowledgepilot-bm25-runtime-", ignore_cleanup_errors=True) as temporary:
        runtime_copy = Path(temporary) / "corpus_v1"
        copy_started = time.perf_counter()
        shutil.copytree(FROZEN_RUNTIME, runtime_copy)
        copy_ms = (time.perf_counter() - copy_started) * 1000
        command = [sys.executable, "-B", str(Path(__file__).resolve()),
                   "--runtime-copy", str(runtime_copy), "--copy-ms", str(copy_ms),
                   "--output", str(output)]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["ANONYMIZED_TELEMETRY"] = "False"
        subprocess.run(command, cwd=runtime_copy, env=environment, check=True)


if __name__ == "__main__":
    main()
