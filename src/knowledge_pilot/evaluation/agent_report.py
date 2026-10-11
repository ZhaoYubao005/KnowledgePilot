"""Offline, provenance-bound Agent evaluation reports. No model or tool execution."""
from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re

from knowledge_pilot.evaluation.agent_evaluator import evaluate_agent_case


_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
_INDEX = re.compile(r"0|[1-9][0-9]*")
_UNOBSERVABLE = (
    "tool_call_count", "decision_steps", "required_tool_hit_rate",
    "forbidden_violation", "invalid_tool_rate", "task_relevance",
    "required_tool_execution_success", "tool_execution_success",
    "all_required_tools_hit",
)


def sha256_json(value: object) -> str:
    """SHA-256 of canonical compact UTF-8 JSON; non-finite JSON is rejected."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, name: str) -> None:
    _require(isinstance(value, str) and bool(value.strip()), f"{name} must be nonempty text")


def _digest(value: object, name: str) -> None:
    _require(isinstance(value, str) and _HEX_DIGEST.fullmatch(value) is not None,
             f"{name} must be a lowercase SHA-256 digest")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _utc_timestamp(value: object, name: str) -> None:
    _text(value, name)
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO UTC timestamp") from error
    _require(timestamp.utcoffset() is not None and timestamp.utcoffset().total_seconds() == 0,
             f"{name} must include the UTC offset")


def _rows(run: dict) -> dict:
    _require(isinstance(run, dict), "run must be an object")
    _text(run.get("run_id"), "run_id")
    _digest(run.get("dataset_sha256"), "dataset_sha256")
    _require(isinstance(run.get("cases"), list), "run.cases must be a list")
    rows = {}
    for row in run["cases"]:
        _require(isinstance(row, dict), "each run case must be an object")
        case_id = row.get("case_id")
        _text(case_id, "case_id")
        _require(case_id not in rows, f"duplicate run case_id: {case_id}")
        rows[case_id] = row
    return rows


def _result_payload(row: dict) -> dict:
    return {name: deepcopy(row[name]) for name in ("answer", "trace", "stop_reason", "error")
            if name in row}


def _answer_digest(row: dict) -> str | None:
    answer = row.get("answer")
    return hashlib.sha256(answer.encode("utf-8")).hexdigest() if isinstance(answer, str) else None


def _verdict(value: object, name: str) -> None:
    _require(value is None or type(value) is bool, f"{name} must be true, false or null")


def _relevance(value: object, row: dict, *, json_keys: bool) -> dict:
    if value is None:
        return {}
    _require(isinstance(value, Mapping), "task_relevance_by_trace must be an object")
    trace = row.get("trace")
    _require(isinstance(trace, list), "reviewed trace must be a list")
    normalized = {}
    for key, verdict in value.items():
        if json_keys:
            _require(isinstance(key, str) and _INDEX.fullmatch(key) is not None,
                     "task relevance index must be a canonical nonnegative integer string")
            index = int(key)
        else:
            _require(type(key) is int and key >= 0,
                     "task relevance index must be a nonnegative integer")
            index = key
        _require(index < len(trace), f"task relevance index out of range: {index}")
        _verdict(verdict, "task relevance verdict")
        normalized[str(index)] = verdict
    return normalized


def make_review_record(
    run: dict, case_id: str, *, reviewer: str, rationale: str,
    answer_correct: bool | None = None,
    task_relevance_by_trace: Mapping[int, bool | None] | None = None,
    reviewed_at_utc: str | None = None,
) -> dict:
    """Bind an explicitly supplied human judgment to one exact observed result.

    This creates a record in memory only. It does not infer a judgment, claim
    that review occurred, or write a reviews file.
    """
    rows = _rows(run)
    _require(case_id in rows, f"unknown review case_id: {case_id}")
    _text(reviewer, "reviewer")
    _text(rationale, "rationale")
    _verdict(answer_correct, "answer_correct")
    reviewed_at_utc = _utc_now() if reviewed_at_utc is None else reviewed_at_utc
    _utc_timestamp(reviewed_at_utc, "reviewed_at_utc")
    row = rows[case_id]
    return {
        "run_id": run["run_id"], "dataset_sha256": run["dataset_sha256"],
        "case_id": case_id, "answer_sha256": _answer_digest(row),
        "agent_result_sha256": sha256_json(_result_payload(row)),
        "answer_correct": answer_correct,
        "task_relevance_by_trace": _relevance(task_relevance_by_trace, row, json_keys=False),
        "reviewer": reviewer, "rationale": rationale, "reviewed_at_utc": reviewed_at_utc,
    }



def extract_historical_agent_batch(markdown: str) -> tuple[dict, str]:
    """Extract one complete legacy batch and return its unchanged JSON substring."""
    _require(isinstance(markdown, str), "Markdown source must be text")
    markers = list(re.finditer(r'"agent_case_count"\s*:', markdown))
    _require(len(markers) == 1, "Expected exactly one complete historical Agent batch")
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result, f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    decoder = json.JSONDecoder(object_pairs_hook=unique_object, parse_constant=invalid_constant)
    candidates = []
    for match in re.finditer(r"\{", markdown):
        try:
            value, end = decoder.raw_decode(markdown, match.start())
        except ValueError:
            continue
        if not isinstance(value, dict) or "agent_case_count" not in value:
            continue
        cases = value.get("cases")
        _require(type(value["agent_case_count"]) is int and value["agent_case_count"] == 8
                 and isinstance(cases, list) and len(cases) == 8,
                 "Historical Agent batch must contain exactly eight case records")
        ids = [case.get("case_id") if isinstance(case, dict) else None for case in cases]
        _require(all(isinstance(case_id, str) and case_id.strip() for case_id in ids)
                 and len(set(ids)) == 8, "Historical batch case IDs must be unique")
        _text(value.get("dataset_version"), "dataset_version")
        _require(isinstance(value.get("registered_tools"), list),
                 "Historical registered_tools must be a list")
        candidates.append((value, markdown[match.start():end]))
    _require(len(candidates) == 1, "Missing, incomplete or ambiguous historical Agent batch")
    return candidates[0]


def normalize_historical_run(raw: dict, *, dataset_sha256: str, source_sha256: str) -> dict:
    """Wrap a legacy terminal report without inventing its original run metadata.

    The identity is a source-content identity, not the historical execution ID.
    dataset_sha256 binds this offline rescore to the supplied dataset bytes; it
    does not prove which bytes were used by the historical execution.
    """
    _require(isinstance(raw, dict), "historical raw report must be an object")
    _digest(dataset_sha256, "dataset_sha256")
    _digest(source_sha256, "source_sha256")
    _text(raw.get("dataset_version"), "dataset_version")
    _require(isinstance(raw.get("cases"), list), "historical cases must be a list")
    _require(type(raw.get("agent_case_count")) is int
             and raw["agent_case_count"] == len(raw["cases"]),
             "historical agent_case_count does not match cases")
    return {
        "schema_version": "agent_raw_run_v1",
        "run_id": "historical-agent-v1-" + source_sha256,
        "dataset_version": raw["dataset_version"], "dataset_sha256": dataset_sha256,
        "registered_tools": deepcopy(raw.get("registered_tools")),
        "started_at_utc": None, "finished_at_utc": None, "environment": None,
        "cases": deepcopy(raw["cases"]), "source_raw_report": deepcopy(raw),
        "source_provenance": {
            "kind": "historical_terminal_report", "source_sha256": source_sha256,
            "source_canonical_json_sha256": sha256_json(raw),
            "run_identity_kind": "source_content_identity",
            "original_run_id_known": False,
            "original_dataset_sha256_known": False,
            "dataset_binding_scope": "offline_rescore_input",
        },
    }


def _matched_reviews(run: dict, rows: dict, reviews: dict | None) -> dict:
    if reviews is None:
        return {}
    _require(isinstance(reviews, dict), "reviews must be an object")
    _require(reviews.get("schema_version") == "agent_manual_reviews_v1",
             "unsupported reviews schema_version")
    for name in ("run_id", "dataset_sha256"):
        _require(reviews.get(name) == run[name], f"reviews {name} mismatch")
    _require(isinstance(reviews.get("records"), list), "reviews.records must be a list")
    matched = {}
    for record in reviews["records"]:
        _require(isinstance(record, dict), "review record must be an object")
        case_id = record.get("case_id")
        _require(isinstance(case_id, str) and case_id in rows,
                 f"unknown review case_id: {case_id}")
        _require(case_id not in matched, f"duplicate review case_id: {case_id}")
        row = rows[case_id]
        for name, expected in (
            ("run_id", run["run_id"]), ("dataset_sha256", run["dataset_sha256"]),
            ("answer_sha256", _answer_digest(row)),
            ("agent_result_sha256", sha256_json(_result_payload(row))),
        ):
            _require(name in record and record[name] == expected,
                     f"review {case_id} {name} mismatch")
        _require("answer_correct" in record, "review answer_correct is required")
        _verdict(record["answer_correct"], "answer_correct")
        for name in ("reviewer", "rationale"):
            _text(record.get(name), name)
        _utc_timestamp(record.get("reviewed_at_utc"), "reviewed_at_utc")
        _relevance(record.get("task_relevance_by_trace"), row, json_keys=True)
        matched[case_id] = deepcopy(record)
    return matched


def _trace_problem(row: dict) -> str | None:
    if not isinstance(row.get("answer"), str):
        return "Missing or invalid answer observation."
    if not isinstance(row.get("stop_reason"), str) or not row["stop_reason"].strip():
        return "Missing or invalid stop_reason observation."
    if "trace" not in row or not isinstance(row["trace"], list):
        return "Missing or invalid trace; attempts and decision steps are unobservable."
    for index, item in enumerate(row["trace"]):
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("tool"), str) or not item["tool"].strip()
            or type(item.get("step")) is not int or item["step"] < 1
            or "arguments" not in item or "result" not in item
        ):
            return f"Invalid trace record at index {index}; tool metrics are unobservable."
    return None


def _metric(numerator: int | float, denominator: int, definition: str) -> dict:
    return {"value": numerator / denominator if denominator else None,
            "numerator": numerator, "denominator": denominator, "definition": definition}


def _aggregate(cases: list[dict], dataset_cases: dict, registered_tools: list[str]) -> tuple[dict, dict, dict]:
    observed = [case for case in cases if case["status"] != "RUN_ERROR"]
    decided = [case for case in cases if type(case["task_success"]) is bool]
    answered = [case for case in cases if type(case["answer_correct"]) is bool]
    required_numerator = required_denominator = invalid_calls = calls = 0
    for case in observed:
        required = set(dataset_cases[case["case_id"]].get("required_tools", []))
        names = [item["tool"] for item in case["trace"]]
        required_numerator += len(required & set(names))
        required_denominator += len(required)
        invalid_calls += sum(name not in registered_tools for name in names)
        calls += len(names)
    required_cases = [case for case in observed
                      if dataset_cases[case["case_id"]].get("required_tools")]
    steps = [case["decision_steps"] for case in observed if case["decision_steps"] is not None]
    errors = sum(case["status"] == "RUN_ERROR" for case in cases)
    counts = {
        "total": len(cases), "pass": sum(case["status"] == "PASS" for case in cases),
        "fail": sum(case["status"] == "FAIL" for case in cases),
        "pending": sum(case["status"] == "PENDING" for case in cases), "run_error": errors,
        "cases_with_pending_review": sum(bool(case["pending_fields"]) for case in cases),
        "tool_execution_failures": sum(
            verdict is False for case in observed for verdict in case["tool_execution_success"]
        ),
    }
    aggregates = {
        "task_success_rate": _metric(
            sum(case["task_success"] is True for case in decided), len(decided),
            "True Task Success / boolean Task Success verdicts; Pending excluded; RUN_ERROR=False included."),
        "answer_accuracy": _metric(
            sum(case["answer_correct"] is True for case in answered), len(answered),
            "Correct answers / boolean answer verdicts; Pending and unobservable answers excluded."),
        "required_tool_hit_rate": _metric(
            required_numerator, required_denominator,
            "Micro: distinct required names attempted per observable case / distinct required names per observable case."),
        "all_required_tools_hit_rate": _metric(
            sum(case["all_required_tools_hit"] is True for case in required_cases), len(required_cases),
            "Macro: all required tools attempted / observable cases with required tools."),
        "invalid_tool_rate": _metric(
            invalid_calls, calls, "Micro: unregistered tool attempts / all observable tool attempts."),
        "average_decision_steps": _metric(sum(steps), len(steps), "Observed decision-step sum / cases with observable steps."),
        "error_rate": _metric(errors, len(cases), "RUN_ERROR cases / all Agent cases."),
    }
    reasons = [case["stop_reason"] for case in observed if isinstance(case["stop_reason"], str)]
    distribution = {"counts": dict(sorted(Counter(reasons).items())),
                    "denominator": len(reasons),
                    "definition": "Counts among non-RUN_ERROR cases with an observed string stop_reason.",
                    "unobserved_count": len(cases) - len(reasons)}
    return aggregates, counts, distribution


def _provenance_gaps(run: dict) -> list[str]:
    gaps = []
    for name in ("started_at_utc", "finished_at_utc"):
        if run.get(name) is None:
            gaps.append(name)
        else:
            _utc_timestamp(run[name], name)
    environment = run.get("environment")
    if not isinstance(environment, dict):
        _require(environment is None, "environment must be an object or null")
        gaps.append("environment")
    else:
        for name in ("model", "prompt_sha256", "cwd"):
            if not isinstance(environment.get(name), str) or not environment[name].strip():
                gaps.append("environment." + name)
    provenance = run.get("source_provenance") or {}
    _require(isinstance(provenance, dict), "source_provenance must be an object or null")
    if provenance.get("kind") == "historical_terminal_report":
        gaps.extend(("historical_original_run_id", "historical_original_dataset_sha256"))
    return gaps


def build_agent_report(
    dataset: dict, run: dict, reviews: dict | None = None, *, dataset_sha256: str,
) -> dict:
    """Rescore exactly eight dataset Agent cases using only recorded observations.

    dataset_sha256 must be the digest of the actual dataset bytes supplied by the
    caller. The CLI computes it before parsing the dataset.
    """
    _require(isinstance(dataset, dict), "dataset must be an object")
    _require(dataset.get("frozen") is True, "dataset must be frozen")
    _require(dataset.get("dataset_status", "FROZEN") == "FROZEN", "dataset_status must be FROZEN")
    policy_version = dataset.get("scoring_policy_version", dataset.get("scoring_policy", {}).get("version"))
    _require(policy_version in (None, "v1"), "unsupported scoring_policy_version")
    _require(dataset.get("schema_version") in (None, "v1"), "unsupported dataset schema_version")
    _digest(dataset_sha256, "dataset_sha256")
    rows = _rows(run)
    _require(run["dataset_sha256"] == dataset_sha256, "dataset_sha256 mismatch")
    _require(run.get("dataset_version") == dataset.get("dataset_version"), "dataset_version mismatch")
    _text(dataset.get("dataset_version"), "dataset_version")
    _require(isinstance(dataset.get("cases"), list), "dataset.cases must be a list")
    agents = [case for case in dataset["cases"] if case.get("case_type") == "agent"]
    _require(len(agents) == 8, "dataset must contain exactly eight Agent cases")
    ids = [case.get("id") for case in agents]
    _require(all(isinstance(case_id, str) and case_id.strip() for case_id in ids)
             and len(set(ids)) == 8, "dataset Agent IDs must be unique")
    _require(set(rows) == set(ids), "run must contain exactly the eight dataset Agent IDs")
    registered = run.get("registered_tools")
    _require(isinstance(registered, list)
             and all(isinstance(name, str) and name.strip() for name in registered),
             "registered_tools must be a list of nonempty strings")
    _require(len(registered) == len(set(registered)), "registered_tools must not contain duplicates")
    gaps = _provenance_gaps(run)
    matched = _matched_reviews(run, rows, reviews)
    results = []
    for case in agents:
        row = rows[case["id"]]
        review = matched.get(case["id"])
        problem = _trace_problem(row)
        if "error" in row or problem is not None:
            score = {
                "case_id": case["id"], "answer_correct": None, "task_success": False,
                "stop_reason": row.get("stop_reason"),
                **{name: None for name in _UNOBSERVABLE},
                "error": deepcopy(row.get("error")) if "error" in row else {
                    "type": "ObservationError", "message": problem,
                },
            }
            status = "RUN_ERROR"
        else:
            relevance = {} if review is None else _relevance(
                review.get("task_relevance_by_trace"), row, json_keys=True
            )
            score = evaluate_agent_case(
                case, row, registered,
                manual_answer_correct=None if review is None else review["answer_correct"],
                task_relevance_by_trace={int(index): verdict for index, verdict in relevance.items()},
            )
            status = "PENDING" if score["task_success"] is None else (
                "PASS" if score["task_success"] is True else "FAIL"
            )
        pending = [name for name in ("answer_correct", "task_relevance")
                   if score[name] is None] if status != "RUN_ERROR" else []
        tools = None if status == "RUN_ERROR" else [item["tool"] for item in row["trace"]]
        failures = None if status == "RUN_ERROR" else [
            {"trace_index": index, "tool": item["tool"],
             "kind": "execution_or_contract_failure", "result": deepcopy(item["result"])}
            for index, item in enumerate(row["trace"])
            if score["tool_execution_success"][index] is False
        ]
        results.append({
            **score, "status": status, "answer": deepcopy(row.get("answer")),
            "trace": deepcopy(row.get("trace")), "raw_result": deepcopy(row),
            "matched_review": review, "pending_fields": pending,
            "tools": tools, "tool_failures": failures,
        })
    aggregates, counts, stops = _aggregate(results, dict(zip(ids, agents)), registered)
    historical = (run.get("source_provenance") or {}).get("kind") == "historical_terminal_report"
    if historical:
        baseline_status = "PENDING_REVIEW" if counts["cases_with_pending_review"] else "HISTORICAL_RESCORED_WITH_PROVENANCE_GAPS"
    else:
        baseline_status = "BASELINE_PENDING" if gaps or counts["cases_with_pending_review"] else "RESCORED"
    return {
        "schema_version": "agent_evaluation_report_v1",
        "run_id": run["run_id"], "dataset_version": dataset["dataset_version"],
        "dataset_sha256": dataset_sha256, "scoring_policy_version": policy_version,
        "generated_at_utc": _utc_now(),
        "started_at_utc": run.get("started_at_utc"), "finished_at_utc": run.get("finished_at_utc"),
        "evaluation_environment": deepcopy(run.get("environment")),
        "registered_tools": deepcopy(registered), "provenance_gaps": gaps,
        "source_provenance": deepcopy(run.get("source_provenance")),
        "source_raw_report": deepcopy(run.get("source_raw_report")),
        "baseline_status": baseline_status, "agent_case_count": len(results),
        "cases": results, "aggregates": aggregates, "counts": counts,
        "stop_reason_distribution": stops,
        "aggregation_policy": "agent_report_v1_explicit_denominators",
    }
