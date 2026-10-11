"""Pure unit tests for Agent evaluation and the frozen v1 scoring contract.

All traces are constructed data. Importing the real Tool Registry would initialize
Chroma, so registered tool names are supplied explicitly instead.
"""

from copy import deepcopy

import pytest

from knowledge_pilot.evaluation.agent_evaluator import (
    evaluate_agent_case,
    evaluate_tool_usage,
    extract_trace_stats,
    numeric_exact_match,
)


REGISTERED_TOOLS = ("calculator", "search_knowledge_base")


def _case(**overrides):
    case = {
        "id": "agent_numeric",
        "case_type": "agent",
        "query": "Use calculator to compute 144 / 12. Output only the number.",
        "answer_match_type": "exact",
        "expected_answer": "12",
        "required_tools": ["calculator"],
        "forbidden_tools": [],
        "max_steps": 5,
    }
    case.update(overrides)
    return case


def _calculator_call(step=1, result=12):
    return {
        "step": step,
        "tool": "calculator",
        "arguments": {"a": 144, "b": 12, "operation": "divide"},
        "result": result,
    }


def _knowledge_call(step=1):
    return {
        "step": step,
        "tool": "search_knowledge_base",
        "arguments": {"query": "Why is /chat stateless?", "top_k": 3},
        "result": [
            {
                "content": "Each HTTP request builds its own messages.",
                "source": "eval_api.txt",
            }
        ],
    }


def _agent_result(trace=None, answer="12", stop_reason="completed"):
    return {
        "answer": answer,
        "trace": [_calculator_call()] if trace is None else trace,
        "stop_reason": stop_reason,
    }


class TestNumericExactMatch:
    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            pytest.param("12", "12.0", id="decimal-equivalence"),
            pytest.param(" \t12.00\n", "\n12\t ", id="trim-both-sides"),
            pytest.param("+12.00", "1.2e1", id="positive-scientific"),
            pytest.param("-12", "-1.2E+1", id="negative-scientific"),
            pytest.param("-0.000", "0", id="negative-zero"),
            pytest.param(".5", "0.50", id="leading-decimal-point"),
            pytest.param("12.", "12.0", id="trailing-decimal-point"),
            pytest.param("1e-30", "0.000000000000000000000000000001",
                         id="small-exact-decimal"),
            pytest.param("9007199254740993", "9.007199254740993e15",
                         id="beyond-float-integer-precision"),
            pytest.param("1e1000", "10e999", id="large-finite-exponent"),
        ],
    )
    def test_equal_finite_numbers(self, actual, expected):
        assert numeric_exact_match(actual, expected) is True

    @pytest.mark.parametrize(
        ("actual", "expected"),
        [
            ("12", "13"),
            ("12", "12.0000000000000000000000000001"),
            ("9007199254740992", "9007199254740993"),
            ("-12", "12"),
        ],
    )
    def test_unequal_numbers_have_no_float_tolerance(self, actual, expected):
        assert numeric_exact_match(actual, expected) is False

    @pytest.mark.parametrize("side", ["actual", "expected"])
    @pytest.mark.parametrize(
        "invalid",
        [
            pytest.param("", id="empty"),
            pytest.param("   ", id="whitespace-only"),
            pytest.param("The answer is 12", id="explanation"),
            pytest.param("12 kg", id="unit"),
            pytest.param("```\n12\n```", id="code-fence"),
            pytest.param("1 2", id="internal-whitespace"),
            pytest.param("1,000", id="thousands-separator"),
            pytest.param("0xC", id="hexadecimal"),
        ],
    )
    def test_rejects_non_numeric_full_answers(self, side, invalid):
        actual, expected = (invalid, "12") if side == "actual" else ("12", invalid)
        assert numeric_exact_match(actual, expected) is False

    @pytest.mark.parametrize("side", ["actual", "expected"])
    @pytest.mark.parametrize(
        "non_finite",
        ["NaN", "sNaN", "NaN123", "Infinity", "-Infinity", "+Inf"],
    )
    def test_rejects_non_finite_values_without_raising(self, side, non_finite):
        actual, expected = (
            (non_finite, "12") if side == "actual" else ("12", non_finite)
        )
        assert numeric_exact_match(actual, expected) is False

    @pytest.mark.parametrize("side", ["actual", "expected"])
    @pytest.mark.parametrize(
        "invalid",
        [
            pytest.param("1_2", id="underscore"),
            pytest.param("１２", id="fullwidth-digits"),
            pytest.param("١٢", id="arabic-indic-digits"),
        ],
    )
    def test_rejects_formats_outside_frozen_ascii_contract(self, side, invalid):
        # Decimal can parse these, but scoring_policy.numeric_answers forbids them.
        actual, expected = (invalid, "12") if side == "actual" else ("12", invalid)
        assert numeric_exact_match(actual, expected) is False

    @pytest.mark.parametrize("actual", [None, 12, 12.0])
    def test_non_string_actual_is_not_a_numeric_answer(self, actual):
        assert numeric_exact_match(actual, "12") is False


class TestExtractTraceStats:
    def test_completed_without_tools_is_one_decision(self):
        assert extract_trace_stats([], "completed") == {
            "tool_names": [],
            "tool_call_count": 0,
            "decision_steps": 1,
        }

    def test_completed_includes_final_answer_decision(self):
        trace = [_knowledge_call(step=1), _calculator_call(step=2)]

        assert extract_trace_stats(trace, "completed") == {
            "tool_names": ["search_knowledge_base", "calculator"],
            "tool_call_count": 2,
            "decision_steps": 3,
        }

    def test_multiple_calls_in_one_round_do_not_add_decision_steps(self):
        trace = [
            _knowledge_call(step=1),
            _calculator_call(step=1),
            _calculator_call(step=1),
        ]

        assert extract_trace_stats(trace, "completed") == {
            "tool_names": ["search_knowledge_base", "calculator", "calculator"],
            "tool_call_count": 3,
            "decision_steps": 2,
        }

    @pytest.mark.parametrize(
        ("trace", "expected_steps"),
        [
            pytest.param([], 0, id="zero-decision-budget"),
            pytest.param([_calculator_call(step=1)], 1, id="one-round-exhausted"),
            pytest.param(
                [_knowledge_call(step=1), _calculator_call(step=2),
                 _calculator_call(step=3)],
                3,
                id="last-decision-three",
            ),
        ],
    )
    def test_max_steps_does_not_invent_a_final_answer_round(
        self, trace, expected_steps
    ):
        # The real Loop returns immediately when its Decision budget is exhausted.
        stats = extract_trace_stats(trace, "max_steps")

        assert stats["decision_steps"] == expected_steps
        assert stats["tool_call_count"] == len(trace)
        assert stats["tool_names"] == [item["tool"] for item in trace]

    def test_uses_highest_step_and_preserves_tool_attempt_order(self):
        trace = [
            _calculator_call(step=3),
            _knowledge_call(step=1),
            _calculator_call(step=2),
        ]

        assert extract_trace_stats(trace, "completed") == {
            "tool_names": ["calculator", "search_knowledge_base", "calculator"],
            "tool_call_count": 3,
            "decision_steps": 4,
        }


class TestEvaluateToolUsage:
    @pytest.mark.parametrize(
        ("required", "called", "expected_rate"),
        [
            (["calculator", "search_knowledge_base"],
             ["search_knowledge_base", "calculator"], 1.0),
            (["calculator", "search_knowledge_base"], ["calculator"], 0.5),
            (["calculator"], ["search_knowledge_base"], 0.0),
            (["calculator"], [], 0.0),
            ([], ["calculator"], None),
        ],
    )
    def test_required_tool_attempt_coverage(self, required, called, expected_rate):
        trace = [{"tool": name} for name in called]

        scores = evaluate_tool_usage(
            _case(required_tools=required), trace, REGISTERED_TOOLS
        )

        assert scores["required_tool_hit_rate"] == expected_rate
        assert scores["forbidden_violation"] is False
        assert scores["invalid_tool_rate"] == 0.0

    def test_missing_optional_constraints_and_empty_trace(self):
        assert evaluate_tool_usage({}, [], REGISTERED_TOOLS) == {
            "required_tool_hit_rate": None,
            "forbidden_violation": False,
            "invalid_tool_rate": 0.0,
        }

    def test_repeated_required_names_and_calls_do_not_inflate_coverage(self):
        scores = evaluate_tool_usage(
            _case(required_tools=["calculator", "calculator", "search_knowledge_base"]),
            [_calculator_call(), _calculator_call(step=2)],
            REGISTERED_TOOLS,
        )

        assert scores["required_tool_hit_rate"] == 0.5

    @pytest.mark.parametrize(
        "result", [12, "Tool execution failed: invalid operation"],
        ids=["executed", "failed"],
    )
    def test_forbidden_attempt_is_a_violation_even_if_execution_fails(self, result):
        scores = evaluate_tool_usage(
            _case(required_tools=[], forbidden_tools=["calculator"]),
            [_calculator_call(result=result)],
            REGISTERED_TOOLS,
        )

        assert scores["forbidden_violation"] is True
        assert scores["invalid_tool_rate"] == 0.0

    def test_absent_forbidden_tool_is_not_a_violation(self):
        scores = evaluate_tool_usage(
            _case(forbidden_tools=["search_knowledge_base"]),
            [_calculator_call()],
            REGISTERED_TOOLS,
        )

        assert scores["forbidden_violation"] is False

    def test_invalid_tool_rate_counts_attempts_including_duplicates(self):
        trace = [
            {"tool": "unknown_tool"},
            _calculator_call(),
            {"tool": "unknown_tool"},
        ]

        scores = evaluate_tool_usage(_case(), trace, REGISTERED_TOOLS)

        assert scores["invalid_tool_rate"] == pytest.approx(2 / 3)
        assert scores["required_tool_hit_rate"] == 1.0
        assert scores["forbidden_violation"] is False

    def test_empty_registry_makes_every_attempt_invalid(self):
        scores = evaluate_tool_usage(_case(), [_calculator_call()], [])

        assert scores["invalid_tool_rate"] == 1.0
        assert scores["required_tool_hit_rate"] == 1.0

    def test_registered_names_are_supplied_by_the_caller(self):
        trace = [{"tool": "custom_tool"}]
        case = _case(required_tools=["custom_tool"])

        scores = evaluate_tool_usage(case, trace, ["custom_tool"])

        assert scores["required_tool_hit_rate"] == 1.0
        assert scores["invalid_tool_rate"] == 0.0

    def test_failed_required_tool_still_counts_as_an_attempt(self):
        scores = evaluate_tool_usage(
            _case(),
            [_calculator_call(result="Tool execution failed: division by zero")],
            REGISTERED_TOOLS,
        )

        assert scores["required_tool_hit_rate"] == 1.0
        assert scores["invalid_tool_rate"] == 0.0

    def test_required_forbidden_and_invalid_are_independent(self):
        case = _case(
            required_tools=["unknown_tool"], forbidden_tools=["unknown_tool"]
        )

        assert evaluate_tool_usage(
            case, [{"tool": "unknown_tool"}], REGISTERED_TOOLS
        ) == {
            "required_tool_hit_rate": 1.0,
            "forbidden_violation": True,
            "invalid_tool_rate": 1.0,
        }


class TestEvaluateAgentCase:
    """Combine explicit review verdicts with observable scores, not a classifier."""

    def test_successful_numeric_task_returns_all_score_fields(self):
        score = evaluate_agent_case(
            _case(), _agent_result(answer=" \n12.0\t"), REGISTERED_TOOLS, task_relevance_by_trace={0: True}
        )

        assert score == {
            "case_id": "agent_numeric",
            "answer_correct": True,
            "task_success": True,
            "stop_reason": "completed",
            "tool_call_count": 1,
            "decision_steps": 2,
            "required_tool_hit_rate": 1.0,
            "forbidden_violation": False,
            "invalid_tool_rate": 0.0,
            "all_required_tools_hit": True,
            "required_tool_execution_success": True,
            "tool_execution_success": [True],
            "task_relevance": True,
        }

    @pytest.mark.parametrize("answer", ["13", "The answer is 12", "Infinity"])
    def test_completed_does_not_make_an_incorrect_answer_successful(self, answer):
        score = evaluate_agent_case(
            _case(), _agent_result(answer=answer), REGISTERED_TOOLS
        )

        assert score["answer_correct"] is False
        assert score["task_success"] is False
        assert score["required_tool_hit_rate"] == 1.0

    @pytest.mark.parametrize("verdict", [True, False, None])
    def test_manual_answer_and_task_success_preserve_three_states(self, verdict):
        case = _case(
            query="Why is /chat stateless?",
            answer_match_type="manual",
            expected_answer="Each request builds its own messages.",
            required_tools=["search_knowledge_base"],
            forbidden_tools=["calculator"],
        )
        agent_result = _agent_result(
            trace=[_knowledge_call()], answer=case["expected_answer"]
        )

        score = evaluate_agent_case(
            case, agent_result, REGISTERED_TOOLS, task_relevance_by_trace={0: True}, manual_answer_correct=verdict
        )

        assert score["answer_correct"] is verdict
        assert score["task_success"] is verdict

    def test_manual_defaults_to_pending_even_when_answer_text_matches(self):
        case = _case(answer_match_type="manual")
        score = evaluate_agent_case(case, _agent_result(), REGISTERED_TOOLS)

        assert score["answer_correct"] is None
        assert score["task_success"] is None

    @pytest.mark.parametrize("verdict", [True, None])
    @pytest.mark.parametrize(
        ("trace", "stop_reason", "max_steps"),
        [
            pytest.param([], "completed", 5, id="missing-required-tool"),
            pytest.param([_calculator_call(), _knowledge_call()], "completed", 5,
                         id="forbidden-tool"),
            pytest.param([_calculator_call(), {"tool": "unknown_tool", "step": 1, "arguments": {},
                                      "result": "Tool execution failed: unknown tool"}],
                         "completed", 5, id="invalid-tool"),
            pytest.param([_calculator_call()], "max_steps", 5, id="budget-stop"),
            pytest.param(
                [_calculator_call(result="Tool execution failed: bad arguments")],
                "completed", 5, id="execution-failure",
            ),
            pytest.param([_calculator_call(step=5)], "completed", 5,
                         id="too-many-decisions"),
        ],
    )
    def test_process_failure_overrides_manual_true_or_pending(
        self, verdict, trace, stop_reason, max_steps
    ):
        case = _case(
            answer_match_type="manual",
            forbidden_tools=["search_knowledge_base"],
            max_steps=max_steps,
        )
        score = evaluate_agent_case(
            case,
            _agent_result(trace=trace, stop_reason=stop_reason),
            REGISTERED_TOOLS,
            manual_answer_correct=verdict,
        )

        assert score["answer_correct"] is verdict
        assert score["task_success"] is False

    def test_correct_answer_without_required_tool_is_not_task_success(self):
        score = evaluate_agent_case(
            _case(), _agent_result(trace=[]), REGISTERED_TOOLS
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 0.0
        assert score["task_success"] is False

    def test_partial_required_tool_coverage_is_not_task_success(self):
        score = evaluate_agent_case(
            _case(required_tools=["calculator", "search_knowledge_base"]),
            _agent_result(),
            REGISTERED_TOOLS,
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 0.5
        assert score["task_success"] is False

    def test_no_required_tools_does_not_block_a_direct_answer(self):
        score = evaluate_agent_case(
            _case(query="Return the number 12.", required_tools=[]),
            _agent_result(trace=[]),
            REGISTERED_TOOLS,
        )

        assert score["required_tool_hit_rate"] is None
        assert score["decision_steps"] == 1
        assert score["task_success"] is True

    @pytest.mark.parametrize(
        ("last_tool_step", "expected_steps", "expected_success"),
        [(4, 5, True), (5, 6, False)],
        ids=["exactly-at-budget", "over-budget"],
    )
    def test_completed_decision_budget_boundary(
        self, last_tool_step, expected_steps, expected_success
    ):
        score = evaluate_agent_case(
            _case(max_steps=5),
            _agent_result(trace=[
                _calculator_call(step=step)
                for step in range(1, last_tool_step + 1)
            ]),
            REGISTERED_TOOLS, task_relevance_by_trace={last_tool_step - 1: True},
        )

        assert score["decision_steps"] == expected_steps
        assert score["task_success"] is expected_success

    @pytest.mark.parametrize("stop_reason", ["max_steps", None, "error"])
    def test_non_completed_stop_prevents_task_success(self, stop_reason):
        score = evaluate_agent_case(
            _case(), _agent_result(stop_reason=stop_reason), REGISTERED_TOOLS
        )

        assert score["answer_correct"] is True
        assert score["stop_reason"] == stop_reason
        assert score["task_success"] is False

    @pytest.mark.parametrize(
        ("knowledge_step", "calculator_step", "expected_steps"),
        [(1, 1, 2), (1, 2, 3)],
        ids=["same-decision", "separate-decisions"],
    )
    def test_successful_multiple_tools_in_same_or_different_rounds(
        self, knowledge_step, calculator_step, expected_steps
    ):
        case = _case(
            query="Look up result field count, then use calculator to multiply by 7.",
            expected_answer="14",
            required_tools=["search_knowledge_base", "calculator"],
        )
        knowledge_call = _knowledge_call(step=knowledge_step)
        knowledge_call["arguments"]["query"] = "search_knowledge_base result fields"
        knowledge_call["result"][0]["content"] = (
            "Each result contains exactly two fields: content and source."
        )
        calculator_call = _calculator_call(step=calculator_step, result=14)
        calculator_call["arguments"] = {"a": 2, "b": 7, "operation": "multiply"}

        score = evaluate_agent_case(
            case,
            _agent_result(trace=[knowledge_call, calculator_call], answer="14"),
            REGISTERED_TOOLS, task_relevance_by_trace={0: True, 1: True},
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["tool_call_count"] == 2
        assert score["decision_steps"] == expected_steps
        assert score["task_success"] is True

    def test_failed_execution_is_not_success_despite_required_attempt(self):
        score = evaluate_agent_case(
            _case(),
            _agent_result(
                trace=[_calculator_call(result="Tool execution failed: bad inputs")]
            ),
            REGISTERED_TOOLS,
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["invalid_tool_rate"] == 0.0
        assert score["task_success"] is False

    def test_failure_followed_by_task_relevant_success_can_recover(self):
        failed = _calculator_call(result="Tool execution failed: division by zero")
        failed["arguments"] = {"a": 1, "b": 0, "operation": "divide"}
        trace = [failed, _calculator_call(step=2)]

        score = evaluate_agent_case(
            _case(), _agent_result(trace=trace), REGISTERED_TOOLS, task_relevance_by_trace={1: True}
        )

        # Frozen v1 allows failed attempts before a later successful required call.
        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["tool_call_count"] == 2
        assert score["decision_steps"] == 3
        assert score["task_success"] is True

    @pytest.mark.parametrize(
        "tool_result",
        [
            pytest.param("12", id="numeric-string"),
            pytest.param(True, id="boolean"),
            pytest.param(float("inf"), id="infinity"),
            pytest.param(float("nan"), id="nan"),
            pytest.param(None, id="missing-native-value"),
        ],
    )
    def test_calculator_return_contract_failure_blocks_task_success(
        self, tool_result
    ):
        score = evaluate_agent_case(
            _case(),
            _agent_result(trace=[_calculator_call(result=tool_result)]),
            REGISTERED_TOOLS,
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["task_success"] is False

    @pytest.mark.parametrize(
        "tool_result",
        [
            pytest.param("retrieved text", id="not-a-list"),
            pytest.param([{"content": "text"}], id="missing-source"),
            pytest.param([{"content": 12, "source": None}], id="non-string-content"),
            pytest.param([{"content": "text", "source": "eval_api.txt", "score": 0.9}],
                         id="extra-result-field"),
        ],
    )
    def test_knowledge_tool_return_contract_failure_blocks_manual_success(
        self, tool_result
    ):
        case = _case(
            query="Why is /chat stateless?",
            answer_match_type="manual",
            expected_answer="Each HTTP request builds its own messages.",
            required_tools=["search_knowledge_base"],
        )
        trace_item = _knowledge_call()
        trace_item["result"] = tool_result

        score = evaluate_agent_case(
            case,
            _agent_result(trace=[trace_item], answer="Each request is independent."),
            REGISTERED_TOOLS,
            manual_answer_correct=True,
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["task_success"] is False

    def test_empty_knowledge_result_is_a_successful_execution_not_a_tool_error(self):
        case = _case(
            category="no_answer",
            query="On which date will KnowledgePilot migrate to PostgreSQL?",
            answer_match_type="manual",
            expected_answer="The corpus does not provide the requested information.",
            required_tools=["search_knowledge_base"],
            forbidden_tools=["calculator"],
        )
        trace_item = _knowledge_call()
        trace_item["arguments"]["query"] = case["query"]
        trace_item["result"] = []

        score = evaluate_agent_case(
            case,
            _agent_result(trace=[trace_item], answer=case["expected_answer"]),
            REGISTERED_TOOLS, task_relevance_by_trace={0: True},
            manual_answer_correct=True,
        )

        assert score["required_tool_hit_rate"] == 1.0
        assert score["task_success"] is True

    def test_json_string_arguments_can_represent_a_successful_tool_call(self):
        trace_item = _calculator_call()
        # The real Loop retains raw arguments; Registry also accepts JSON strings.
        trace_item["arguments"] = '{"a": 144, "b": 12, "operation": "divide"}'

        score = evaluate_agent_case(
            _case(), _agent_result(trace=[trace_item]), REGISTERED_TOOLS, task_relevance_by_trace={0: True}
        )

        assert score["task_success"] is True

    def test_successful_irrelevant_calculation_does_not_satisfy_required_behavior(self):
        trace_item = _calculator_call(result=2)
        trace_item["arguments"] = {"a": 1, "b": 1, "operation": "add"}

        score = evaluate_agent_case(
            _case(), _agent_result(trace=[trace_item], answer="12"), REGISTERED_TOOLS, task_relevance_by_trace={0: False}
        )

        assert score["answer_correct"] is True
        assert score["required_tool_hit_rate"] == 1.0
        assert score["task_success"] is False

    def test_unsupported_answer_match_type_raises_clear_error(self):
        with pytest.raises(ValueError, match="Unsupported answer_match_type: unknown"):
            evaluate_agent_case(
                _case(answer_match_type="unknown"), _agent_result(), REGISTERED_TOOLS
            )

    def test_evaluation_does_not_mutate_case_or_agent_result(self):
        case = _case()
        agent_result = _agent_result()
        before = deepcopy((case, agent_result))

        evaluate_agent_case(case, agent_result, REGISTERED_TOOLS)

        assert (case, agent_result) == before


class TestExplicitTaskRelevance:
    """Unknown relevance is not an automatic natural-language judgment."""

    @pytest.mark.parametrize(
        ("verdict", "expected"), [(True, True), (False, False), (None, None)]
    )
    def test_explicit_review_controls_task_success(self, verdict, expected):
        score = evaluate_agent_case(
            _case(), _agent_result(), REGISTERED_TOOLS,
            task_relevance_by_trace={0: verdict},
        )
        assert score["answer_correct"] is True
        assert score["required_tool_execution_success"] is True
        assert score["tool_execution_success"] == [True]
        assert score["task_relevance"] is expected
        assert score["task_success"] is expected

    def test_omitted_review_does_not_automatically_verify_a_plausible_call(self):
        score = evaluate_agent_case(_case(), _agent_result(), REGISTERED_TOOLS)
        assert score["answer_correct"] is True
        assert score["required_tool_execution_success"] is True
        assert score["task_relevance"] is None
        assert score["task_success"] is None

    @pytest.mark.parametrize("relevance", [True, False, None])
    def test_wrong_answer_is_failure_even_if_review_is_pending(self, relevance):
        score = evaluate_agent_case(
            _case(), _agent_result(answer="13"), REGISTERED_TOOLS,
            task_relevance_by_trace={0: relevance},
        )
        assert score["answer_correct"] is False
        assert score["task_success"] is False

    @pytest.mark.parametrize("answer_review", [True, False, None])
    @pytest.mark.parametrize("relevance", [True, False, None])
    def test_answer_review_and_behavior_review_are_independent(
        self, answer_review, relevance
    ):
        score = evaluate_agent_case(
            _case(answer_match_type="manual"), _agent_result(), REGISTERED_TOOLS,
            manual_answer_correct=answer_review,
            task_relevance_by_trace={0: relevance},
        )
        expected = (
            False if answer_review is False or relevance is False
            else None if answer_review is None or relevance is None
            else True
        )
        assert score["answer_correct"] is answer_review
        assert score["task_relevance"] is relevance
        assert score["task_success"] is expected

    @pytest.mark.parametrize(
        ("reviews", "expected"),
        [
            ({0: False, 1: True}, True),
            ({0: False, 1: None}, None),
            ({0: False, 1: False}, False),
            ({0: True}, True),
        ],
    )
    def test_same_tool_attempts_use_existential_success(self, reviews, expected):
        trace = [_calculator_call(step=1), _calculator_call(step=1)]
        score = evaluate_agent_case(
            _case(), _agent_result(trace=trace), REGISTERED_TOOLS,
            task_relevance_by_trace=reviews,
        )
        assert score["tool_call_count"] == 2
        assert score["decision_steps"] == 2
        assert score["task_relevance"] is expected
        assert score["task_success"] is expected

    @pytest.mark.parametrize(
        ("reviews", "expected"),
        [
            ({0: True, 1: True}, True),
            ({0: True}, None),
            ({0: True, 1: False}, False),
            ({0: None, 1: False}, False),
        ],
    )
    def test_each_required_tool_needs_its_own_review(self, reviews, expected):
        score = evaluate_agent_case(
            _case(required_tools=["calculator", "search_knowledge_base"]),
            _agent_result(trace=[_calculator_call(), _knowledge_call()]),
            REGISTERED_TOOLS,
            task_relevance_by_trace=reviews,
        )
        assert score["required_tool_execution_success"] is True
        assert score["task_relevance"] is expected
        assert score["task_success"] is expected

    def test_failed_execution_cannot_be_promoted_by_positive_review(self):
        score = evaluate_agent_case(
            _case(),
            _agent_result(trace=[
                _calculator_call(result="Tool execution failed: bad inputs")
            ]),
            REGISTERED_TOOLS, task_relevance_by_trace={0: True},
        )
        assert score["required_tool_hit_rate"] == 1.0
        assert score["required_tool_execution_success"] is False
        assert score["tool_execution_success"] == [False]
        assert score["task_success"] is False

    def test_false_review_of_a_failure_does_not_prevent_later_recovery(self):
        score = evaluate_agent_case(
            _case(), _agent_result(trace=[
                _calculator_call(result="Tool execution failed: unavailable"),
                _calculator_call(step=2),
            ]), REGISTERED_TOOLS, task_relevance_by_trace={0: False, 1: True},
        )
        assert score["tool_execution_success"] == [False, True]
        assert score["task_relevance"] is True
        assert score["task_success"] is True

    @pytest.mark.parametrize(
        "reviews",
        [{0: 1}, {0: 0}, {0: "true"}, {0: []}, {True: True},
         {-1: True}, {1: True}, {"0": True}, [True]],
    )
    def test_malformed_review_input_is_rejected(self, reviews):
        with pytest.raises(ValueError, match="task_relevance_by_trace"):
            evaluate_agent_case(
                _case(), _agent_result(), REGISTERED_TOOLS,
                task_relevance_by_trace=reviews,
            )

    @pytest.mark.parametrize("verdict", [1, 0, "true"])
    def test_manual_answer_review_requires_literal_tristate(self, verdict):
        with pytest.raises(ValueError, match="manual_answer_correct"):
            evaluate_agent_case(
                _case(answer_match_type="manual"), _agent_result(),
                REGISTERED_TOOLS, manual_answer_correct=verdict,
            )

    def test_explicit_review_input_is_not_mutated(self):
        case, result, reviews = _case(), _agent_result(), {0: True}
        before = deepcopy((case, result, reviews))
        evaluate_agent_case(
            case, result, REGISTERED_TOOLS, task_relevance_by_trace=reviews
        )
        assert (case, result, reviews) == before

    @pytest.mark.parametrize(
        "trace",
        [None, "not a trace", {}, [None], [{"tool": "calculator", "step": True}],
         [{"tool": "", "step": 1}], [{"tool": "calculator", "step": 0}]],
    )
    def test_invalid_trace_is_not_silently_treated_as_empty(self, trace):
        result = _agent_result()
        result["trace"] = trace
        with pytest.raises(ValueError, match="trace"):
            evaluate_agent_case(_case(), result, REGISTERED_TOOLS)

    def test_missing_trace_is_not_silently_treated_as_empty(self):
        result = _agent_result()
        del result["trace"]
        with pytest.raises(ValueError, match="trace"):
            evaluate_agent_case(_case(), result, REGISTERED_TOOLS)

    @pytest.mark.parametrize("field", ["arguments", "result"])
    def test_missing_observed_fields_are_not_silently_counted_as_attempts(self, field):
        result = _agent_result()
        del result["trace"][0][field]
        with pytest.raises(ValueError, match="trace"):
            evaluate_agent_case(_case(), result, REGISTERED_TOOLS)
