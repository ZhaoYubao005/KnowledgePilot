"""Offline report tests; every run/review fixture below is constructed test data."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


def _api():
    return importlib.import_module("knowledge_pilot.evaluation.agent_report")


def _dataset():
    return {
        "dataset_version": "unit-test-v1", "frozen": True,
        "cases": [
            {"id": f"unit_{i}", "case_type": "agent", "query": "Test fixture",
             "answer_match_type": "manual" if i == 0 else "exact",
             "expected_answer": "12", "required_tools": ["calculator"],
             "forbidden_tools": [], "max_steps": 5}
            for i in range(8)
        ],
    }


def _row(i, **changes):
    value = {
        "case_id": f"unit_{i}", "answer": "12", "stop_reason": "completed",
        "trace": [{"step": 1, "tool": "calculator",
                   "arguments": {"a": 144, "b": 12, "operation": "divide"},
                   "result": 12}],
        "task_success": True, "old_extra": "preserve me",
    }
    value.update(changes)
    return value


def _run(**changes):
    value = {
        "run_id": "unit-run", "dataset_version": "unit-test-v1",
        "dataset_sha256": "a" * 64,
        "registered_tools": ["calculator", "search_knowledge_base"],
        "started_at_utc": "2026-01-01T00:00:00Z",
        "finished_at_utc": "2026-01-01T00:01:00Z",
        "environment": {"model": "test-only", "prompt_sha256": "b" * 64,
                        "cwd": "test-only"},
        "cases": [_row(i) for i in range(8)],
    }
    value.update(changes)
    return value


def _review(run, case_id="unit_0", **changes):
    return _api().make_review_record(
        run, case_id, reviewer="unit-test reviewer", rationale="Constructed fixture",
        reviewed_at_utc="2026-01-01T01:00:00Z", **changes,
    )


def _reviews(run, records):
    return {"schema_version": "agent_manual_reviews_v1",
            "run_id": run["run_id"], "dataset_sha256": run["dataset_sha256"],
            "records": records}


def _build(run=None, reviews=None):
    return _api().build_agent_report(
        _dataset(), _run() if run is None else run, reviews,
        dataset_sha256="a" * 64,
    )


def test_canonical_hash_is_stable_utf8_and_rejects_nonfinite_json():
    api = _api()
    data = {"z": "中文", "a": [1, True, None]}
    expected = hashlib.sha256(
        '{"a":[1,true,null],"z":"中文"}'.encode("utf-8")
    ).hexdigest()
    assert api.sha256_json(data) == expected
    assert api.sha256_json({"a": [1, True, None], "z": "中文"}) == expected
    with pytest.raises(ValueError):
        api.sha256_json({"bad": float("nan")})


def test_old_scores_are_preserved_but_not_trusted_without_reviews():
    run = _run()
    before = deepcopy(run)
    report = _build(run)
    row = report["cases"][0]
    assert row["raw_result"] == run["cases"][0]
    assert row["raw_result"]["task_success"] is True
    assert row["answer_correct"] is None
    assert row["task_success"] is None
    assert row["status"] == "PENDING"
    assert set(row["pending_fields"]) == {"answer_correct", "task_relevance"}
    assert report["aggregates"]["task_success_rate"]["value"] is None
    assert report["aggregates"]["task_success_rate"]["denominator"] == 0
    assert report["counts"]["pending"] == 8
    assert run == before


def test_review_is_bound_to_run_answer_trace_and_raw_answer_whitespace():
    api = _api()
    run = _run()
    record = _review(run, answer_correct=True, task_relevance_by_trace={0: True})
    assert record["task_relevance_by_trace"] == {"0": True}
    assert record["answer_sha256"] == hashlib.sha256(b"12").hexdigest()
    assert record["agent_result_sha256"] == api.sha256_json(
        {key: run["cases"][0][key] for key in ("answer", "trace", "stop_reason")}
    )
    report = _build(run, _reviews(run, [record]))
    assert report["cases"][0]["status"] == "PASS"
    assert report["cases"][0]["matched_review"] == record
    assert report["aggregates"]["task_success_rate"]["numerator"] == 1
    assert report["aggregates"]["task_success_rate"]["denominator"] == 1
    stale = deepcopy(run)
    stale["cases"][0]["answer"] = " 12"
    with pytest.raises(ValueError, match="answer_sha256"):
        _build(stale, _reviews(run, [record]))
    stale = deepcopy(run)
    stale["cases"][0]["trace"][0]["result"] = 99
    with pytest.raises(ValueError, match="agent_result_sha256"):
        _build(stale, _reviews(run, [record]))


@pytest.mark.parametrize("field,value", [
    ("run_id", "other-run"), ("dataset_sha256", "f" * 64),
    ("case_id", "unknown-case"), ("answer_correct", 1),
    ("task_relevance_by_trace", {"0": "true"}),
    ("task_relevance_by_trace", {"-1": True}),
    ("task_relevance_by_trace", {"01": True}),
    ("task_relevance_by_trace", {"9": True}),
    ("reviewer", ""), ("rationale", ""), ("reviewed_at_utc", "yesterday"),
])
def test_rejects_stale_or_invalid_review_record(field, value):
    run = _run()
    record = _review(run)
    record[field] = value
    with pytest.raises(ValueError):
        _build(run, _reviews(run, [record]))


def test_rejects_duplicate_reviews_and_mismatched_envelopes():
    run = _run()
    record = _review(run)
    with pytest.raises(ValueError, match="duplicate"):
        _build(run, _reviews(run, [record, record]))
    reviews = _reviews(run, [record])
    reviews["run_id"] = "different"
    with pytest.raises(ValueError, match="run_id"):
        _build(run, reviews)


@pytest.mark.parametrize("change", [
    {"dataset_version": "wrong"},
    {"dataset_sha256": "d" * 64},
    {"cases": [_row(i) for i in range(7)]},
    {"cases": [_row(i) for i in range(7)] + [_row(0)]},
    {"registered_tools": ["calculator", 1]},
])
def test_rejects_run_dataset_or_registry_mismatch(change):
    with pytest.raises(ValueError):
        _build(_run(**change))


@pytest.mark.parametrize("invalid_trace", [None, "not a trace", [{}], [{"tool": "calculator", "step": True}]])
def test_invalid_trace_becomes_run_error_with_unobservable_metrics(invalid_trace):
    run = _run()
    run["cases"][0]["trace"] = invalid_trace
    report = _build(run)
    row = report["cases"][0]
    assert row["status"] == "RUN_ERROR"
    assert row["task_success"] is False
    for field in ("tool_call_count", "decision_steps", "required_tool_hit_rate",
                  "invalid_tool_rate", "forbidden_violation"):
        assert row[field] is None
    assert row["raw_result"]["trace"] == invalid_trace
    assert report["counts"]["run_error"] == 1
    metric = report["aggregates"]["task_success_rate"]
    assert metric["denominator"] == 1 and metric["numerator"] == 0


def test_missing_trace_is_distinct_from_valid_empty_trace():
    run = _run()
    del run["cases"][0]["trace"]
    run["cases"][1]["trace"] = []
    report = _build(run)
    assert report["cases"][0]["status"] == "RUN_ERROR"
    assert report["cases"][1]["status"] == "FAIL"
    assert report["cases"][1]["tool_call_count"] == 0
    assert report["cases"][1]["decision_steps"] == 1
    assert report["cases"][1]["required_tool_hit_rate"] == 0.0


def test_runner_error_and_failed_tool_attempt_are_reported_separately():
    run = _run()
    run["cases"][0] = {"case_id": "unit_0",
                       "error": {"type": "RuntimeError", "message": "test error"}}
    run["cases"][1]["trace"][0]["result"] = "Tool execution failed: test-only"
    report = _build(run)
    assert report["counts"]["run_error"] == 1
    assert report["counts"]["tool_execution_failures"] == 1
    assert report["cases"][0]["status"] == "RUN_ERROR"
    assert report["cases"][1]["status"] == "FAIL"
    assert report["aggregates"]["error_rate"]["value"] == 1 / 8
    assert report["aggregates"]["task_success_rate"]["denominator"] == 2


def test_micro_denominators_do_not_average_case_rates():
    run = _run()
    run["cases"][0]["trace"] = [
        {"step": 1, "tool": "unregistered", "arguments": {}, "result": 0}
    ]
    run["cases"][1]["trace"] *= 3
    report = _build(run)
    invalid = report["aggregates"]["invalid_tool_rate"]
    assert invalid["numerator"] == 1
    assert invalid["denominator"] == 10
    assert invalid["value"] == 0.1
    required = report["aggregates"]["required_tool_hit_rate"]
    assert required["numerator"] == 7 and required["denominator"] == 8
    assert report["aggregates"]["average_decision_steps"]["denominator"] == 8
    assert report["stop_reason_distribution"]["denominator"] == 8


def test_all_empty_observable_traces_have_null_invalid_call_rate():
    run = _run(cases=[_row(i, trace=[]) for i in range(8)])
    report = _build(run)
    assert report["aggregates"]["invalid_tool_rate"]["value"] is None
    assert report["aggregates"]["invalid_tool_rate"]["denominator"] == 0


def test_unknown_environment_is_explicit_and_never_invented():
    run = _run(environment=None, started_at_utc=None, finished_at_utc=None)
    report = _build(run)
    assert report["evaluation_environment"] is None
    assert "environment" in report["provenance_gaps"]
    assert "started_at_utc" in report["provenance_gaps"]
    assert report["baseline_status"] == "BASELINE_PENDING"


def test_historical_normalization_preserves_legacy_report_and_unknown_runtime():
    api = _api()
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    before = deepcopy(legacy)
    run = api.normalize_historical_run(
        legacy, dataset_sha256="a" * 64, source_sha256="c" * 64,
    )
    assert run["run_id"] == "historical-agent-v1-" + "c" * 64
    assert run["source_raw_report"] == legacy
    assert run["cases"] == legacy["cases"]
    assert run["started_at_utc"] is None
    assert run["finished_at_utc"] is None
    assert run["environment"] is None
    assert run["source_provenance"]["original_run_id_known"] is False
    report = _build(run)
    assert report["source_provenance"]["source_sha256"] == "c" * 64
    assert report["source_raw_report"] == legacy
    assert report["baseline_status"] == "PENDING_REVIEW"
    assert legacy == before


def test_build_does_not_import_model_database_or_registry(tmp_path):
    # Other tests can preload tools during collection. Check the real offline
    # import/build contract in a fresh interpreter without mutating their cache.
    script = """
import runpy
import sys

sys.path.insert(0, sys.argv[1])
forbidden = (
    "knowledge_pilot.tools.registry",
    "knowledge_pilot.vector_store.chroma_store",
    "knowledge_pilot.llm.ollama_client",
)

def assert_isolated(stage):
    loaded = [name for name in forbidden if name in sys.modules]
    assert not loaded, f"{stage}: unexpected runtime imports: {loaded}"

assert_isolated("before fixture loading")
fixtures = runpy.run_path(sys.argv[2])
assert_isolated("before report import")
assert "knowledge_pilot.evaluation.agent_report" not in sys.modules
fixtures["_api"]()
assert_isolated("after report import")
fixtures["_build"]()
assert_isolated("after report build")
"""
    test_path = Path(__file__).resolve()
    source_root = test_path.parents[2] / "src"
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script, str(source_root), str(test_path)],
        cwd=tmp_path, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert completed.returncode == 0, (
        f"Offline report import/build check exited {completed.returncode}"
        f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )


def test_offline_cli_supports_historical_input_and_refuses_overwrite(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    raw_path = tmp_path / "raw.json"
    output = tmp_path / "report.json"
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    raw_path.write_text(json.dumps(legacy), encoding="utf-8")
    source_bytes = raw_path.read_bytes()
    script = Path(__file__).resolve().parents[2] / "scripts" / "finalize_agent_report.py"
    command = [sys.executable, "-B", str(script), "--historical", "--raw-run", str(raw_path),
               "--dataset", str(dataset_path), "--output", str(output)]
    completed = subprocess.run(command, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["baseline_status"] == "PENDING_REVIEW"
    assert report["source_provenance"]["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert raw_path.read_bytes() == source_bytes
    again = subprocess.run(command, text=True, capture_output=True)
    assert again.returncode != 0
    assert "already exists" in again.stderr.lower()


def test_review_error_payload_binds_every_available_observation():
    run = _run()
    run["cases"][0]["error"] = {"type": "RuntimeError", "message": "test error"}
    record = _review(run)
    changed = deepcopy(run)
    changed["cases"][0]["trace"][0]["result"] = 999
    with pytest.raises(ValueError, match="agent_result_sha256"):
        _build(changed, _reviews(run, [record]))


@pytest.mark.parametrize("field", ["arguments", "result"])
def test_missing_observed_tool_fields_are_run_errors(field):
    run = _run()
    del run["cases"][0]["trace"][0][field]
    assert _build(run)["cases"][0]["status"] == "RUN_ERROR"


@pytest.mark.parametrize("field,value", [
    ("answer", None), ("answer", 12), ("stop_reason", None),
])
def test_invalid_answer_or_stop_reason_is_run_error(field, value):
    run = _run()
    run["cases"][0][field] = value
    assert _build(run)["cases"][0]["status"] == "RUN_ERROR"


@pytest.mark.parametrize("field", ["answer", "stop_reason"])
def test_missing_answer_or_stop_reason_is_run_error(field):
    run = _run()
    del run["cases"][0][field]
    assert _build(run)["cases"][0]["status"] == "RUN_ERROR"


def test_present_unfrozen_status_is_rejected_and_scoring_version_is_reported():
    api = _api()
    dataset = _dataset()
    dataset["dataset_status"] = "DRAFT"
    with pytest.raises(ValueError, match="FROZEN"):
        api.build_agent_report(dataset, _run(), dataset_sha256="a" * 64)
    dataset["dataset_status"] = "FROZEN"
    dataset["scoring_policy_version"] = "v1"
    report = api.build_agent_report(dataset, _run(), dataset_sha256="a" * 64)
    assert report["scoring_policy_version"] == "v1"


def test_offline_cli_records_current_rescore_provenance_separately(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    raw_path = tmp_path / "raw.json"
    output = tmp_path / "report.json"
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    raw_path.write_text(json.dumps(legacy), encoding="utf-8")
    script = Path(__file__).resolve().parents[2] / "scripts" / "finalize_agent_report.py"
    completed = subprocess.run(
        [sys.executable, "-B", str(script), "--historical", "--raw-run", str(raw_path),
         "--dataset", str(dataset_path), "--output", str(output)],
        text=True, capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evaluation_environment"] is None
    current = report["rescore_environment"]
    assert current["python_executable"] == sys.executable
    assert current["python_version"]
    assert current["code_sha256"]["agent_evaluator.py"]
    assert current["code_sha256"]["agent_report.py"]
    assert "chromadb" in current["package_versions"]
    assert "working_tree_dirty" in current["git"]


def test_per_case_tools_and_failures_are_observable_without_guessed_causes():
    run = _run()
    run["cases"][0]["trace"][0]["result"] = "Tool execution failed: test-only"
    report = _build(run)
    row = report["cases"][0]
    assert row["tools"] == ["calculator"]
    assert row["tool_failures"] == [{
        "trace_index": 0, "tool": "calculator",
        "kind": "execution_or_contract_failure",
        "result": "Tool execution failed: test-only",
    }]
    run["cases"][0]["trace"] = None
    row = _build(run)["cases"][0]
    assert row["tools"] is None
    assert row["tool_failures"] is None


def test_markdown_extraction_preserves_exact_json_and_all_legacy_scores():
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    exact = json.dumps(legacy, ensure_ascii=False, indent=3)
    raw, extracted = _api().extract_historical_agent_batch("Terminal log\n```json\n" + exact + "\n```\n")
    assert extracted == exact
    assert raw == legacy
    assert raw["cases"][0]["task_success"] is True


@pytest.mark.parametrize("suffix", ["", "\n{\"agent_case_count\": 8,"])
def test_markdown_extraction_rejects_multiple_or_incomplete_reports(suffix):
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    exact = json.dumps(legacy)
    source = exact + (suffix if suffix else "\n" + exact)
    with pytest.raises(ValueError):
        _api().extract_historical_agent_batch(source)


@pytest.mark.parametrize("source", [
    '{"agent_case_count":8,"cases":[',
    '{"agent_case_count":8,"agent_case_count":8,"cases":[]}',
    '{"agent_case_count":8,"cases":[],"extra":NaN}',
    "There is no uploaded run here.",
])
def test_markdown_extraction_rejects_missing_or_invalid_json(source):
    with pytest.raises(ValueError):
        _api().extract_historical_agent_batch(source)


def test_markdown_cli_saves_exact_raw_substring_and_reuses_content_identity(tmp_path):
    dataset_path = tmp_path / "dataset.json"
    markdown_path = tmp_path / "terminal.md"
    raw_path = tmp_path / "raw.json"
    output = tmp_path / "report.json"
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    legacy = {"dataset_version": "unit-test-v1", "agent_case_count": 8,
              "registered_tools": ["calculator"], "cases": [_row(i) for i in range(8)]}
    exact = json.dumps(legacy, ensure_ascii=False, indent=3)
    markdown_bytes = ("Log\n```json\n" + exact + "\n```\n").encode("utf-8")
    markdown_path.write_bytes(markdown_bytes)
    script = Path(__file__).resolve().parents[2] / "scripts" / "finalize_agent_report.py"
    completed = subprocess.run(
        [sys.executable, "-B", str(script), "--markdown", "--raw-run", str(markdown_path),
         "--save-raw", str(raw_path), "--dataset", str(dataset_path), "--output", str(output)],
        text=True, capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert raw_path.read_bytes() == exact.encode("utf-8")
    assert markdown_path.read_bytes() == markdown_bytes
    report = json.loads(output.read_text(encoding="utf-8"))
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    assert report["run_id"] == "historical-agent-v1-" + digest
    assert report["offline_inputs"]["markdown_sha256"] == hashlib.sha256(markdown_bytes).hexdigest()
    assert report["rescore_environment"]["code_sha256"]["finalize_agent_report.py"]
