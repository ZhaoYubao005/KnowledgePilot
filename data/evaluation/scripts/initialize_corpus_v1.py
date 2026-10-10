"""One-shot corpus_v1 initialization; --verify-only never ingests or scores cases.

Run in a fresh Python process with CWD=data/evaluation/runtime/corpus_v1,
absolute PYTHONPATH pointing to this project's src, and Python -B.
No database deletion, overwrite cleanup, Agent execution, or Dataset edits.
"""
import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import urlopen

PROJECT = Path(__file__).resolve().parents[3]
RUNTIME = PROJECT / "data/evaluation/runtime/corpus_v1"
STORE = RUNTIME / "data/vector_store"
MANIFEST = RUNTIME / "initialization_manifest.json"
SCRIPT = PROJECT / "data/evaluation/scripts/initialize_corpus_v1.py"
EXPECTED = {
    "eval_rag": 4, "eval_agent": 4, "eval_tools": 3,
    "eval_api": 3, "eval_memory": 1, "eval_engineering": 4,
}
COLLECTION_NAME = "knowledge_pilot_docs"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dataset_path_for_manifest(manifest=None):
    if manifest is not None:
        relative = manifest.get("dataset_relative_path", "data/evaluation/cases_draft.json")
        path = (PROJECT / relative).resolve()
        require(path.is_relative_to(PROJECT / "data/evaluation"),
                "Dataset manifest path is outside the Evaluation directory.")
        return path
    formal = PROJECT / "data/evaluation/cases_v1.json"
    return formal if formal.is_file() else PROJECT / "data/evaluation/cases_draft.json"


def timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def git(*args):
    return subprocess.check_output(
        ["git", "--no-optional-locks", "-C", str(PROJECT), *args],
        text=True, encoding="utf-8"
    ).strip()


def protected_files():
    records = {}
    for current, dirs, files in os.walk(PROJECT):
        base = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name not in (".git", ".idea")
            and base / name not in (
                PROJECT / "data/evaluation/runtime",
                PROJECT / "data/evaluation/scripts",
            )
        )
        for name in sorted(files):
            path = base / name
            stat = path.stat()
            records[path.relative_to(PROJECT).as_posix()] = {
                "sha256": sha(path.read_bytes()),
                "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            }
    return records


def development_snapshot():
    snapshots = []
    for path in sorted(PROJECT.rglob("chroma.sqlite3")):
        if path.is_relative_to(RUNTIME):
            continue
        wal = Path(str(path) + "-wal")
        require(not wal.exists() or wal.stat().st_size == 0,
                "Development WAL present; do not infer a stale count or open its client.")
        with sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True
        ) as conn:
            conn.execute("PRAGMA query_only=ON")
            counts = conn.execute(
                "SELECT c.id,c.name,COUNT(DISTINCT e.id),"
                "COUNT(DISTINCT m.string_value) FROM collections c "
                "LEFT JOIN segments s ON s.collection=c.id AND s.scope='METADATA' "
                "LEFT JOIN embeddings e ON e.segment_id=s.id "
                "LEFT JOIN embedding_metadata m ON m.id=e.id AND m.key='document_id' "
                "GROUP BY c.id,c.name ORDER BY c.id"
            ).fetchall()
            queue = conn.execute(
                "SELECT COUNT(*),MAX(seq_id) FROM embeddings_queue"
            ).fetchone()
            consumed = conn.execute(
                "SELECT segment_id,seq_id FROM max_seq_id ORDER BY segment_id"
            ).fetchall()
            pending = conn.execute(
                "SELECT c.name,s.id,COUNT(q.seq_id) FROM collections c "
                "JOIN segments s ON s.collection=c.id AND s.scope='METADATA' "
                "LEFT JOIN max_seq_id m ON m.segment_id=s.id "
                "LEFT JOIN embeddings_queue q ON q.topic="
                "('persistent://default/default/' || c.id) "
                "AND q.seq_id>COALESCE(m.seq_id,-1) "
                "GROUP BY c.id,c.name,s.id ORDER BY c.id"
            ).fetchall()
            require(all(row[2] == 0 for row in pending),
                    "Development operations pending; cannot infer its live count safely.")
        files = {}
        for item in sorted(path.parent.rglob("*")):
            if item.is_file():
                stat = item.stat()
                files[item.relative_to(path.parent).as_posix()] = {
                    "sha256": sha(item.read_bytes()),
                    "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                }
        snapshots.append({
            "path": str(path.parent), "collections": [
                {"id": row[0], "name": row[1], "chunks": row[2], "documents": row[3]}
                for row in counts
            ],
            "queue_rows_not_live_record_count": queue[0],
            "queue_max_seq_id": queue[1],
            "consumed_seq_ids": [list(row) for row in consumed],
            "pending_operations": [list(row) for row in pending],
            "files": files,
            "count_method": "SQLite mode=ro&immutable=1; no nonempty WAL",
        })
    return snapshots


def get_json(url):
    with urlopen(url, timeout=15) as response:
        return json.load(response)


def specs_from_source(loader):
    require({p.stem for p in (PROJECT / "data/evaluation/corpus").glob("*.txt")}
            == set(EXPECTED), "Corpus must contain exactly the six declared TXT files.")
    documents = []
    for document_id, count in EXPECTED.items():
        path = PROJECT / "data/evaluation/corpus" / (document_id + ".txt")
        raw = path.read_bytes()
        text = loader.load_text(str(path))
        chunks = loader.chunk_text(text, chunk_size=500, overlap=100)
        require(len(chunks) == count, "Unexpected chunk count: " + document_id)
        documents.append({
            "document_id": document_id, "source": str(path),
            "source_sha256": sha(raw), "source_bytes": len(raw),
            "characters": len(text), "chunk_count": len(chunks),
            "chunks": [
                {"id": f"{document_id}_chunk_{index}", "chunk_index": index,
                 "start_character_inclusive": index * 400,
                 "end_character_exclusive": index * 400 + len(chunk),
                 "characters": len(chunk), "sha256": sha(chunk.encode("utf-8"))}
                for index, chunk in enumerate(chunks)
            ],
        })
    return documents


def verify_collection(collection, documents, loader):
    records = collection.get(include=["documents", "metadatas", "embeddings"])
    ids = records["ids"]
    expected_ids = {c["id"] for doc in documents for c in doc["chunks"]}
    require(len(ids) == len(set(ids)) == 19, "Expected 19 unique records.")
    require(set(ids) == expected_ids, "Unexpected or missing record IDs.")
    observed = {record_id: index for index, record_id in enumerate(ids)}
    results = []
    dimensions = set()
    for doc in documents:
        chunks = loader.chunk_text(loader.load_text(doc["source"]), 500, 100)
        require(sha(Path(doc["source"]).read_bytes()) == doc["source_sha256"],
                "Corpus changed during ingestion.")
        for spec, text in zip(doc["chunks"], chunks):
            index = observed[spec["id"]]
            metadata = records["metadatas"][index]
            stored = records["documents"][index]
            require(stored == text, "Stored body differs: " + spec["id"])
            require(set(metadata) == {"document_id", "source", "chunk_index"},
                    "Unexpected metadata keys: " + spec["id"])
            require(metadata["document_id"] == doc["document_id"], "Wrong document_id.")
            require(metadata["source"] == doc["source"], "Wrong source.")
            require(type(metadata["chunk_index"]) is int
                    and metadata["chunk_index"] == spec["chunk_index"], "Wrong chunk_index.")
            require(sha(stored.encode("utf-8")) == spec["sha256"], "Chunk hash differs.")
            vector = records["embeddings"][index]
            require(len(vector) > 0 and all(math.isfinite(float(x)) for x in vector),
                    "Invalid stored embedding.")
            dimensions.add(len(vector))
            results.append({
                "id": spec["id"], "document_id": doc["document_id"],
                "chunk_index": spec["chunk_index"], "sha256": spec["sha256"],
                "body_equal": True, "metadata_equal": True,
            })
    require(collection.count() == 19, "Collection count differs.")
    require(len(dimensions) == 1, "Embedding dimensions differ.")
    return {
        "documents": 6, "chunks": 19, "no_extra_records": True,
        "all_bodies_equal": True, "all_metadata_equal": True,
        "continuous_zero_based_indexes": True,
        "embedding_dimensions": next(iter(dimensions)), "records": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    require(Path.cwd().resolve() == RUNTIME, "CWD mismatch: stop before project import.")
    require(Path(os.environ.get("PYTHONPATH", "")).resolve() == PROJECT / "src",
            "PYTHONPATH must be exactly the absolute project src path.")
    require(sys.dont_write_bytecode, "Use Python -B.")
    require(not any(n == "knowledge_pilot" or n.startswith("knowledge_pilot.")
                    for n in sys.modules), "Use a fresh process before project imports.")
    require(Path(git("rev-parse", "--show-toplevel")).resolve() == PROJECT,
            "Wrong Git root.")
    require((Path.cwd() / "data/vector_store").resolve() == STORE,
            "Expected path mismatch: stop before any database initialization.")
    require(STORE != (PROJECT / "data/vector_store").resolve(), "Development path selected.")
    if args.verify_only:
        require((STORE / "chroma.sqlite3").is_file() and MANIFEST.is_file(),
                "No initialized Evaluation database and manifest to verify.")
    else:
        require(not MANIFEST.exists(), "Initialization manifest exists; no automatic retry.")
        if (STORE / "chroma.sqlite3").exists():
            with sqlite3.connect((STORE / "chroma.sqlite3").as_uri()+"?mode=ro", uri=True) as conn:
                require(conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] == 0,
                        "Existing records: stop without deleting or ingesting.")
                require(conn.execute("SELECT COUNT(*) FROM embeddings_queue").fetchone()[0] == 0,
                        "Existing operation history: stop without clearing or replaying it.")

    protected_before = protected_files()
    development_before = development_snapshot()
    manifest = {}
    if args.verify_only:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        dataset_path = dataset_path_for_manifest(manifest)
    else:
        dataset_path = dataset_path_for_manifest()
        dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        manifest = {
            "corpus_version": "corpus_v1", "dataset_status": dataset["dataset_status"],
            "frozen": dataset["frozen"], "dataset_version": dataset.get("dataset_version"),
            "dataset_relative_path": dataset_path.relative_to(PROJECT).as_posix(),
            "status": "STARTED", "started_at": timestamp(),
            "git_head": git("rev-parse", "HEAD"), "git_status_before": git("status", "--short", "--branch"),
            "cwd": str(Path.cwd()), "pythonpath": os.environ["PYTHONPATH"],
            "expected_chroma_path": str(STORE), "collection_name": COLLECTION_NAME,
            "chunk_size": 500, "overlap": 100, "document_id_map": {
                name: str(PROJECT / "data/evaluation/corpus" / (name + ".txt"))
                for name in EXPECTED
            },
            "python_executable": sys.executable, "python_version": sys.version,
            "chroma_version": importlib.metadata.version("chromadb"),
            "requests_version": importlib.metadata.version("requests"),
            "script_sha256": sha(SCRIPT.read_bytes()),
            "dataset_sha256": sha(dataset_path.read_bytes()),
            "development_before": development_before,
            "protected_files_before": protected_before,
            "no_agent_evaluation": True, "no_baseline_scores": True,
        }
        with MANIFEST.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")

    try:
        from knowledge_pilot.document import text_loader as loader
        documents = specs_from_source(loader)
        if not args.verify_only:
            models = get_json("http://localhost:11434/api/tags")
            model = next(m for m in models["models"] if m["name"] == "bge-m3:latest")
            require("embedding" in model["capabilities"], "bge-m3 embedding capability unavailable.")
            manifest["embedding"] = {
                "core_model_identifier": "bge-m3",
                "resolved_model": model["name"], "digest": model["digest"],
                "details": model["details"],
                "endpoint": "http://localhost:11434/api/embed",
                "ollama_version": get_json("http://localhost:11434/api/version")["version"],
            }
            manifest["documents"] = documents
        else:
            require(documents == manifest["documents"], "Corpus version/hash no longer matches manifest.")
            require(sha(dataset_path.read_bytes())
                    == manifest["dataset_sha256"], "Dataset changed since initialization.")

        from knowledge_pilot.vector_store import chroma_store as store
        settings = store.client.get_settings()
        actual_path = Path(settings.persist_directory).resolve()
        require(settings.is_persistent and actual_path == STORE, "Actual Chroma path mismatch: no ingest.")
        require(Path.cwd().resolve() == RUNTIME, "CWD changed after import: no ingest.")
        require(Path(store.__file__).resolve()
                == PROJECT / "src/knowledge_pilot/vector_store/chroma_store.py",
                "Imported a different project.")
        same_file_modules = [
            m for m in sys.modules.values()
            if getattr(m, "__file__", None) and Path(m.__file__).resolve() == Path(store.__file__).resolve()
        ]
        require(len({id(m) for m in same_file_modules}) == 1, "Duplicate chroma_store module objects.")
        require(store.collection.name == COLLECTION_NAME, "Unexpected Collection name.")
        require([c.name for c in store.client.list_collections()] == [COLLECTION_NAME],
                "Unexpected additional collections.")
        with sqlite3.connect((STORE / "chroma.sqlite3").as_uri()+"?mode=ro", uri=True) as conn:
            require(conn.execute("SELECT id,name FROM collections").fetchall()
                    == [(str(store.collection.id), COLLECTION_NAME)],
                    "SQLite path/catalog does not match actual Collection.")

        from knowledge_pilot.tools import knowledge_base_tool as kb
        from knowledge_pilot.tools import registry
        from knowledge_pilot.llm import ollama_client as agent
        from knowledge_pilot.rag import pipeline
        evaluation_collection = store.collection
        require(evaluation_collection is kb.collection is pipeline.collection,
                "Retrieval/Tool/Pipeline collections differ.")
        require(store.search is kb.search is pipeline.search, "Search function bindings differ.")
        require(registry.TOOL_REGISTRY["search_knowledge_base"] is kb.search_knowledge_base,
                "Registry Tool binding differs.")
        require(kb.search_knowledge_base.__globals__["collection"] is evaluation_collection,
                "Tool actual globals select a different collection.")
        require(agent.execute_tool_call is registry.execute_tool_call, "Agent executor differs.")
        identities = {
            "store_is_tool_is_retrieval_is_pipeline": True,
            "registry_function_is_tool_function": True,
            "tool_globals_collection_is_evaluation_collection": True,
            "agent_executor_is_registry_executor": True,
            "single_chroma_store_module_object": True,
        }
        if not args.verify_only:
            initial_count = evaluation_collection.count()
            require(initial_count == 0, "Collection is nonempty: stop without any ingestion.")
            manifest["initial_collection_count"] = initial_count
            manifest["actual_chroma_path"] = str(actual_path)
            manifest["persist_directory_setting"] = settings.persist_directory
            manifest["collection_id"] = str(evaluation_collection.id)
            manifest["collection_configuration"] = evaluation_collection.configuration
            manifest["identity_checks"] = identities
            print("PRE_INGEST_PATH_AND_EMPTY_CHECK_PASSED " + str(actual_path), flush=True)
            for document in documents:
                require(evaluation_collection.count() == sum(
                    EXPECTED[d["document_id"]] for d in manifest.get("ingested_documents", [])
                ), "Unexpected records appeared before next document.")
                store.ingest_document(
                    document["source"], document["document_id"], evaluation_collection
                )
                manifest.setdefault("ingested_documents", []).append({
                    "document_id": document["document_id"], "chunks": document["chunk_count"]
                })
                print("INGESTED " + document["document_id"], flush=True)

        verification = verify_collection(evaluation_collection, documents, loader)
        require(str(evaluation_collection.id) == manifest["collection_id"], "Collection identity changed.")
        if not args.verify_only:
            query = "answer_with_rag 的 threshold 是否作用于 search_knowledge_base？"
            retrieved = store.search(query, evaluation_collection, top_k=3)
            tool_results = kb.search_knowledge_base(query, top_k=3)
            expected_sources = set(EXPECTED)
            require(len(retrieved) == 3 and len(tool_results) == 3, "Smoke retrieval count differs.")
            for text, score, metadata in retrieved:
                require(metadata["document_id"] in expected_sources and math.isfinite(score),
                        "Smoke retrieval escaped the Evaluation Corpus.")
            require(tool_results == [
                {"content": text, "source": metadata["source"]}
                for text, _, metadata in retrieved
            ], "Retrieval and Tool smoke results differ.")
            manifest["smoke_test"] = {
                "status": "PASSED", "top_k": 3, "query": query,
                "retrieval_and_tool_outputs_agree": True,
                "retrieved_chunks": [
                    {"document_id": meta["document_id"], "chunk_index": meta["chunk_index"]}
                    for _, _, meta in retrieved
                ], "not_a_dataset_evaluation_or_ranking_difficulty_validation": True,
            }
            manifest["verification"] = verification
            manifest["status"] = "SUCCESS"
        else:
            require(verification == manifest["verification"], "Reopened database differs from manifest.")
            manifest["reopen_verification"] = {
                "status": "PASSED", "verified_at": timestamp(),
                "documents": 6, "chunks": 19,
                "all_bodies_and_metadata_equal": True, "identity_checks": identities,
                "no_ingest_performed": True,
            }
        print(json.dumps({
            "status": "SUCCESS", "verify_only": args.verify_only,
            "documents": 6, "chunks": 19, "actual_chroma_path": str(actual_path),
            "collection_id": str(evaluation_collection.id), "identity_checks": identities
        }, ensure_ascii=False), flush=True)
    except Exception as error:
        manifest["status"] = "FAILED"
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        after_dev = development_snapshot()
        after_protected = protected_files()
        manifest["development_after"] = after_dev
        manifest["development_unchanged"] = development_before == after_dev
        manifest["protected_files_unchanged"] = protected_before == after_protected
        manifest["finished_at"] = timestamp()
        if not manifest["development_unchanged"] or not manifest["protected_files_unchanged"]:
            manifest["status"] = "FAILED"
            manifest["protection_error"] = "Protected files or development database changed."
        with MANIFEST.open("w", encoding="utf-8", newline="\n") as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write("\n")
        require(manifest["development_unchanged"] and manifest["protected_files_unchanged"],
                "Development database or protected files changed; do not auto-repair.")


if __name__ == "__main__":
    main()
