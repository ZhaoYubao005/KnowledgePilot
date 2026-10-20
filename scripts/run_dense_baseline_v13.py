"""Run the V1.3 dense baseline against an isolated copy of the frozen Chroma runtime."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "data" / "evaluation" / "cases_v1.json"
MANIFEST_PATH = PROJECT_ROOT / "data" / "evaluation" / "manifests" / "evaluation_v1.json"
FROZEN_RUNTIME = PROJECT_ROOT / "data" / "evaluation" / "runtime" / "corpus_v1"
REPORT_DIRECTORY = PROJECT_ROOT / "data" / "evaluation" / "reports"


def _load_manifest():
    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _verify_embedding_model(manifest):
    response = requests.get("http://localhost:11434/api/tags", timeout=5)
    response.raise_for_status()
    expected_name = manifest["embedding"]["resolved_model"]
    expected_digest = manifest["embedding"]["digest"]
    for model in response.json().get("models", []):
        if model.get("name") == expected_name or model.get("model") == expected_name:
            actual_digest = model.get("digest")
            if actual_digest != expected_digest:
                raise RuntimeError(
                    f"Embedding digest mismatch for {expected_name}: "
                    f"expected {expected_digest}, got {actual_digest}"
                )
            return {"resolved_model": expected_name, "digest": actual_digest}
    raise RuntimeError(f"Required embedding model is unavailable: {expected_name}")


def _default_output():
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return REPORT_DIRECTORY / f"dense_v13_k3_{timestamp}.json"


def _run_worker(args):
    runtime_root = Path(args.runtime_copy).resolve()
    os.chdir(runtime_root)
    initialization_started = time.perf_counter()
    from knowledge_pilot.vector_store.chroma_store import collection, search
    initialization_ms = (time.perf_counter() - initialization_started) * 1000

    if collection.count() != 19:
        raise RuntimeError(f"Isolated collection count must be 19, got {collection.count()}")

    from knowledge_pilot.evaluation.dense_baseline import (
        load_retrieval_cases, make_dense_search, run_dense_cases, summarize_dense_cases,
    )
    from knowledge_pilot.evaluation.json_writer import write_json_exclusive
    from knowledge_pilot.evaluation.run_provenance import collect_run_provenance
    from knowledge_pilot.evaluation.run_report import build_run_report

    manifest = _load_manifest()
    metadata, cases = load_retrieval_cases(DATASET_PATH)
    if len(cases) != 16:
        raise RuntimeError(f"Expected 16 retrieval cases, got {len(cases)}")

    started = datetime.now(timezone.utc)
    records = run_dense_cases(cases, make_dense_search(search, collection), k=3)
    finished = datetime.now(timezone.utc)
    summary = summarize_dense_cases(records)

    code_paths = [
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/dense_baseline.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/evidence_collector.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/case_evidence.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/run_report.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/run_provenance.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/json_writer.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/rag_evaluator.py",
        PROJECT_ROOT / "src/knowledge_pilot/evaluation/rag_metrics.py",
        PROJECT_ROOT / "src/knowledge_pilot/vector_store/chroma_store.py",
        PROJECT_ROOT / "src/knowledge_pilot/retrieval/embedding.py",
        Path(__file__).resolve(),
    ]
    provenance = collect_run_provenance(
        project_root=PROJECT_ROOT,
        dataset_path=DATASET_PATH,
        manifest_path=MANIFEST_PATH,
        code_paths=code_paths,
    )
    run_id = started.strftime("dense-v13-%Y%m%dT%H%M%S-%fZ")
    strategy_config = {
        "embedding": manifest["embedding"],
        "collection": manifest["collection"],
        "top_k": 3,
        "similarity": "1 - cosine_distance",
        "runtime_isolation": "temporary byte-for-byte copy of frozen runtime",
        "frozen_runtime_source": FROZEN_RUNTIME.relative_to(PROJECT_ROOT).as_posix(),
        "collection_record_count": 19,
        "initialization_ms": {
            "runtime_copy": args.copy_ms,
            "chroma_import_and_collection_open": initialization_ms,
        },
        "latency_boundary": summary["latency_ms"]["boundary"],
        "first_query_may_include_embedding_model_cold_start": True,
    }
    report = build_run_report(
        run_id=run_id,
        strategy="dense_chroma_cosine",
        strategy_config=strategy_config,
        k=3,
        started_at_utc=started.isoformat().replace("+00:00", "Z"),
        finished_at_utc=finished.isoformat().replace("+00:00", "Z"),
        dataset_version=metadata["dataset_version"],
        corpus_version=metadata["corpus_version"],
        provenance=provenance,
        cases=records,
        summary=summary,
    )
    output = write_json_exclusive(Path(args.output).resolve(), report)
    print(json.dumps({"report": str(output), "summary": summary}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--runtime-copy", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--copy-ms", type=float, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.runtime_copy:
        _run_worker(args)
        return

    manifest = _load_manifest()
    _verify_embedding_model(manifest)
    output = (args.output or _default_output()).resolve()
    if not output.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {output.parent}")
    if output.exists():
        raise FileExistsError(output)

    with TemporaryDirectory(prefix="knowledgepilot-dense-runtime-", ignore_cleanup_errors=True) as temporary:
        runtime_copy = Path(temporary) / "corpus_v1"
        copy_started = time.perf_counter()
        shutil.copytree(FROZEN_RUNTIME, runtime_copy)
        copy_ms = (time.perf_counter() - copy_started) * 1000
        command = [
            sys.executable, "-B", str(Path(__file__).resolve()),
            "--runtime-copy", str(runtime_copy), "--copy-ms", str(copy_ms),
            "--output", str(output),
        ]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["ANONYMIZED_TELEMETRY"] = "False"
        subprocess.run(command, cwd=runtime_copy, env=environment, check=True)


if __name__ == "__main__":
    main()
