"""Finalize an Agent report from existing JSON only; never runs an Agent."""
import argparse
import hashlib
import json
from importlib import metadata
import platform
import subprocess
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from knowledge_pilot.evaluation.agent_report import (  # noqa: E402
    build_agent_report,
    extract_historical_agent_batch,
    normalize_historical_run,
)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def _read_json(path):
    content = path.read_bytes()
    return json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_object,
                      parse_constant=_invalid_constant), hashlib.sha256(content).hexdigest()


def _check_manifest(dataset, dataset_path, digest):
    manifest_name = dataset.get("version_manifest")
    if manifest_name is None:
        return None
    if not isinstance(manifest_name, str):
        raise ValueError("version_manifest must be a path string")
    manifest_path = (dataset_path.parent / manifest_name).resolve()
    manifest, manifest_digest = _read_json(manifest_path)
    recorded = manifest.get("dataset", {})
    if recorded.get("sha256") != digest:
        raise ValueError("Frozen manifest dataset SHA-256 mismatch")
    if recorded.get("dataset_version") != dataset.get("dataset_version"):
        raise ValueError("Frozen manifest dataset version mismatch")
    return {"path": str(manifest_path), "sha256": manifest_digest,
            "dataset_hash_match": True}



def _rescore_environment():
    package_versions = {}
    for name in ("chromadb", "requests", "pytest"):
        try:
            package_versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            package_versions[name] = None
    code_sha256 = {}
    for name in ("agent_evaluator.py", "agent_report.py"):
        path = PROJECT_ROOT / "src" / "knowledge_pilot" / "evaluation" / name
        code_sha256[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    code_sha256["finalize_agent_report.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    git = {"head": None, "working_tree_dirty": None,
           "identity_note": "Git HEAD does not identify uncommitted working code; use code_sha256."}
    try:
        head = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        status = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        git.update(head=head.stdout.strip(), working_tree_dirty=bool(status.stdout.strip()))
    except (OSError, subprocess.SubprocessError):
        git["observation_error"] = "Current Git metadata could not be read."
    return {"python_executable": sys.executable, "python_version": platform.python_version(),
            "package_versions": package_versions, "code_sha256": code_sha256, "git": git,
            "scope": "current_offline_rescore_process; not historical Agent runtime"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-run", type=Path, required=True, help="Existing raw run JSON")
    parser.add_argument("--reviews", type=Path, help="Explicit provenance-bound review JSON")
    parser.add_argument("--dataset", type=Path,
                        default=PROJECT_ROOT / "data" / "evaluation" / "cases_v1.json")
    parser.add_argument("--output", type=Path, required=True, help="New report JSON; never overwritten")
    parser.add_argument("--historical", action="store_true",
                        help="Import legacy terminal batch JSON; historical runtime stays unknown")
    parser.add_argument("--markdown", action="store_true",
                        help="Extract one exact historical JSON batch from Markdown")
    parser.add_argument("--save-raw", type=Path, help="New exact raw JSON file; required with --markdown")
    args = parser.parse_args(argv)
    try:
        if args.markdown != (args.save_raw is not None):
            raise ValueError("--markdown and --save-raw must be used together")
        if args.save_raw is not None:
            if args.save_raw.exists():
                raise ValueError(f"Raw output already exists: {args.save_raw}")
            if args.save_raw.resolve() == args.output.resolve():
                raise ValueError("Raw and report output paths must differ")
        if args.output.exists():
            raise ValueError(f"Output already exists: {args.output}")
        dataset_path = args.dataset.resolve()
        dataset, dataset_digest = _read_json(dataset_path)
        manifest = _check_manifest(dataset, dataset_path, dataset_digest)
        markdown_digest = None
        exact_raw_bytes = None
        if args.markdown:
            markdown_bytes = args.raw_run.read_bytes()
            markdown_digest = hashlib.sha256(markdown_bytes).hexdigest()
            raw, exact_raw = extract_historical_agent_batch(markdown_bytes.decode("utf-8-sig"))
            exact_raw_bytes = exact_raw.encode("utf-8")
            source_digest = hashlib.sha256(exact_raw_bytes).hexdigest()
        else:
            raw, source_digest = _read_json(args.raw_run)
        historical = args.historical or args.markdown
        run = normalize_historical_run(
            raw, dataset_sha256=dataset_digest, source_sha256=source_digest,
        ) if historical else raw
        reviews, reviews_digest = _read_json(args.reviews) if args.reviews else (None, None)
        report = build_agent_report(dataset, run, reviews, dataset_sha256=dataset_digest)
        report["rescore_environment"] = _rescore_environment()
        report["offline_inputs"] = {
            "raw_run_path": str((args.save_raw if args.markdown else args.raw_run).resolve()),
            "raw_run_sha256": source_digest,
            "markdown_path": str(args.raw_run.resolve()) if args.markdown else None,
            "markdown_sha256": markdown_digest,
            "dataset_path": str(dataset_path),
            "reviews_path": str(args.reviews.resolve()) if args.reviews else None,
            "reviews_sha256": reviews_digest, "frozen_manifest": manifest,
            "historical_import": historical, "agent_executed": False,
        }
        # Serialize before exclusive creation, so invalid JSON cannot leave a
        # partially written report. Original source files are never rewritten.
        serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.markdown:
            with args.save_raw.open("xb") as stream:
                stream.write(exact_raw_bytes)
        with args.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(serialized)
        print(f"Offline report saved: {args.output.resolve()}")
        print(f"Status: {report['baseline_status']}; Pending: {report['counts']['pending']}; "
              f"Run errors: {report['counts']['run_error']}")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Cannot finalize Agent report: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
