
from collections.abc import Mapping
import json
import math
import re
from decimal import Decimal, InvalidOperation


# Frozen scoring_policy.numeric_answers.fullmatch_pattern (v1).
_NUMERIC_ANSWER_PATTERN = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)


def numeric_exact_match(actual: str, expected: str) -> bool:
    """Compare complete finite ASCII numbers with Decimal semantics."""
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False

    actual = actual.strip()
    expected = expected.strip()
    # Rejecting malformed expected values is a defensive input policy added here;
    # frozen v1 explicitly prescribes the format of the final answer only.
    if (
        _NUMERIC_ANSWER_PATTERN.fullmatch(actual) is None
        or _NUMERIC_ANSWER_PATTERN.fullmatch(expected) is None
    ):
        return False

    try:
        actual_number = Decimal(actual)
        expected_number = Decimal(expected)

    except (InvalidOperation, ValueError):
        return False

    return (
        actual_number.is_finite()
        and expected_number.is_finite()
        and actual_number == expected_number
    )

def extract_trace_stats(trace, stop_reason):
    # Step 1：提取全部工具名称
    tool_names = [
        item["tool"]
        for item in trace
    ]

    # Step 2：统计工具调用次数
    tool_call_count = len(tool_names)

    # Step 3：最后一次工具调用的决策轮次
    last_tool_step = max(
        (item["step"] for item in trace),
        default=0,
    )

    # Step 4：计算总决策轮数
    if stop_reason == "completed":
        decision_steps = last_tool_step + 1

    elif stop_reason == "max_steps":
        # 预算耗尽后直接返回固定提示，没有额外的模型回答轮次。
        decision_steps = last_tool_step

    else:
        decision_steps = last_tool_step

    return {
        "tool_names": tool_names,
        "tool_call_count": tool_call_count,
        "decision_steps": decision_steps,
    }

def evaluate_tool_usage(case, trace, registered_tools):
    called_tools = [
        item["tool"]
        for item in trace
    ]

    called_set = set(called_tools)

    required = set(case.get("required_tools", []))
    forbidden = set(case.get("forbidden_tools", []))

    # 从外部接收已注册的工具名称
    registered = set(registered_tools)

    required_hit_rate = (
        len(required & called_set) / len(required)
        if required else None
    )

    forbidden_violation = bool(
        forbidden & called_set
    )

    invalid_count = sum(
        tool not in registered
        for tool in called_tools
    )

    invalid_tool_rate = (
        invalid_count / len(called_tools)
        if called_tools else 0.0
    )

    return {
        "required_tool_hit_rate": required_hit_rate,
        "forbidden_violation": forbidden_violation,
        "invalid_tool_rate": invalid_tool_rate,
    }

def _is_finite_number(value: object) -> bool:
    """Accept finite native numeric values, excluding bool and numeric strings."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Decimal):
        return value.is_finite()
    return False


def _tool_execution_succeeded(item: dict) -> bool:
    """Check the observable v1 execution contract without re-running the tool."""
    result = item.get("result")
    if isinstance(result, str) and result.startswith("Tool execution failed:"):
        return False

    arguments = item.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (ValueError, TypeError):
            return False
    if not isinstance(arguments, dict):
        return False

    if item["tool"] == "calculator":
        return (
            set(arguments) == {"a", "b", "operation"}
            and _is_finite_number(arguments["a"])
            and _is_finite_number(arguments["b"])
            and arguments["operation"] in ("add", "subtract", "multiply", "divide")
            and (arguments["operation"] != "divide" or arguments["b"] != 0)
            and _is_finite_number(result)
        )

    if item["tool"] == "search_knowledge_base":
        if (
            not set(arguments) <= {"query", "top_k", "document_id"}
            or not isinstance(arguments.get("query"), str)
        ):
            return False
        if "top_k" in arguments and (
            isinstance(arguments["top_k"], bool)
            or not isinstance(arguments["top_k"], int)
        ):
            return False
        if (
            "document_id" in arguments
            and arguments["document_id"] is not None
            and not isinstance(arguments["document_id"], str)
        ):
            return False
        return isinstance(result, list) and all(
            isinstance(record, dict)
            and set(record) == {"content", "source"}
            and isinstance(record["content"], str)
            and (record["source"] is None or isinstance(record["source"], str))
            for record in result
        )

    # An externally registered name alone does not supply an execution contract.
    return False


def evaluate_agent_case(
    case,
    agent_result,
    registered_tools,
    manual_answer_correct: bool | None = None,
    *,
    task_relevance_by_trace: Mapping[int, bool | None] | None = None,
):
    """Combine answer, observable contracts, and explicit per-attempt review.

    Review keys are zero-based trace indexes, not decision steps. Missing verdicts
    remain unknown; this function does not infer relevance from natural language.
    A True verdict certifies that this execution's inputs and result support the
    declared task behavior in the context of the full run.
    """
    if manual_answer_correct is not None and type(manual_answer_correct) is not bool:
        raise ValueError("manual_answer_correct must be True, False, or None")

    trace = agent_result.get("trace")
    if not isinstance(trace, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("tool"), str)
        or not item["tool"]
        or type(item.get("step")) is not int
        or item["step"] < 1
        or "arguments" not in item
        or "result" not in item
        for item in trace
    ):
        raise ValueError("Agent trace is missing or invalid")

    if task_relevance_by_trace is not None:
        if not isinstance(task_relevance_by_trace, Mapping) or any(
            type(index) is not int or not 0 <= index < len(trace)
            or (verdict is not None and type(verdict) is not bool)
            for index, verdict in task_relevance_by_trace.items()
        ):
            raise ValueError(
                "task_relevance_by_trace requires trace indexes and True/False/None"
            )
    relevance_reviews = (
        {} if task_relevance_by_trace is None else task_relevance_by_trace
    )
    answer = agent_result.get("answer", "")
    stop_reason = agent_result.get("stop_reason")

    # Step 1：答案匹配
    match_type = case["answer_match_type"]

    if match_type == "exact":
        answer_correct = numeric_exact_match(
            answer,
            case["expected_answer"],
        )

    elif match_type == "manual":
        answer_correct = manual_answer_correct

    else:
        raise ValueError(
            f"Unsupported answer_match_type: {match_type}"
        )

    # Step 2：提取 Trace 统计信息
    trace_stats = extract_trace_stats(
        trace,
        stop_reason,
    )

    # Step 3：评价工具使用情况
    tool_scores = evaluate_tool_usage(
        case,
        trace,
        registered_tools,
    )

    # Step 4：检查工具约束
    required_rate = tool_scores["required_tool_hit_rate"]

    required_ok = (
        required_rate is None
        or required_rate == 1.0
    )

    tools_ok = (
        required_ok
        and not tool_scores["forbidden_violation"]
        and tool_scores["invalid_tool_rate"] == 0.0
    )

    # Step 5：检查执行轮数
    decision_steps = trace_stats["decision_steps"]

    steps_ok = (
        decision_steps is not None
        and decision_steps <= case["max_steps"]
    )

    # Execution success and task relevance are separate observable/review inputs.
    execution_success = [_tool_execution_succeeded(item) for item in trace]
    successful_tools = {
        item["tool"]
        for item, succeeded in zip(trace, execution_success)
        if succeeded
    }
    required_tools = set(case.get("required_tools", []))
    required_execution_ok = required_tools <= successful_tools

    # Frozen v1 allows recovery: each required tool needs at least one relevant
    # successful attempt, rather than requiring every attempt to succeed.
    per_tool_relevance = []
    for tool in required_tools:
        verdicts = [
            relevance_reviews.get(index)
            for index, item in enumerate(trace)
            if item["tool"] == tool and execution_success[index]
        ]
        if any(verdict is True for verdict in verdicts):
            per_tool_relevance.append(True)
        elif any(verdict is None for verdict in verdicts):
            per_tool_relevance.append(None)
        else:
            per_tool_relevance.append(False)

    task_relevance = (
        False if any(verdict is False for verdict in per_tool_relevance)
        else None if any(verdict is None for verdict in per_tool_relevance)
        else True
    )

    process_ok = (
        stop_reason == "completed"
        and tools_ok
        and steps_ok
        and required_execution_ok
    )

    # Step 6：综合判断任务成功
    if not process_ok or answer_correct is False or task_relevance is False:
        task_success = False

    elif answer_correct is None or task_relevance is None:
        task_success = None

    else:
        task_success = answer_correct

    return {
        "case_id": case["id"],
        "answer_correct": answer_correct,
        "task_success": task_success,
        "stop_reason": stop_reason,
        "tool_call_count": trace_stats["tool_call_count"],
        "decision_steps": decision_steps,
        "all_required_tools_hit": required_ok,
        "required_tool_execution_success": required_execution_ok,
        "tool_execution_success": execution_success,
        "task_relevance": task_relevance,
        **tool_scores,
    }
