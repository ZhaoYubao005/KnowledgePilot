from unittest.mock import Mock, call

from knowledge_pilot.evaluation.rag_runner import run_rag_evaluation

def test_rag_runner_with_mock_search():
    from knowledge_pilot.evaluation.rag_runner import (
        run_rag_evaluation,
    )

    cases = [
        {
            "id": "rag_demo",
            "case_type": "retrieval",
            "category": "single_chunk",
            "query": "什么是 RAG？",
            "relevant_chunks": [
                {"document_id": "eval_rag", "chunk_index": 2}
            ]
        },
        {
            "id": "agent_demo",
            "case_type": "agent",
            "query": "计算 2 + 3"
        }
    ]

    def mock_search(query, k):
        return [
            ("文本A", 0.91, {
                "document_id": "eval_tools",
                "chunk_index": 0
            }),
            ("文本B", 0.85, {
                "document_id": "eval_rag",
                "chunk_index": 2
            })
        ][:k]

    results = run_rag_evaluation(cases, mock_search, k=2)

    assert len(results) == 1
    assert results[0]["case_id"] == "rag_demo"
    assert results[0]["hit"] == 1
    assert results[0]["recall"] == 1.0
    assert results[0]["rr"] == 0.5


def _retrieval_case(case_id, query, chunk_index=0):
    return {
        "id": case_id,
        "case_type": "retrieval",
        "category": "single_chunk",
        "query": query,
        "relevant_chunks": [
            {"document_id": "eval_rag", "chunk_index": chunk_index}
        ],
    }


def test_multiple_retrieval_cases_are_evaluated():
    cases = [
        _retrieval_case("rag_first", "第一个检索问题", chunk_index=0),
        _retrieval_case("rag_second", "第二个检索问题", chunk_index=1),
    ]
    search_fn = Mock(side_effect=[
        [("第一块", 0.9, {"document_id": "eval_rag", "chunk_index": 0})],
        [
            ("干扰块", 0.8, {"document_id": "eval_tools", "chunk_index": 0}),
            ("第二块", 0.7, {"document_id": "eval_rag", "chunk_index": 1}),
        ],
    ])

    results = run_rag_evaluation(cases, search_fn, k=2)

    assert len(results) == 2
    assert results[0]["case_id"] == "rag_first"
    assert results[0]["hit"] == 1
    assert results[0]["recall"] == 1.0
    assert results[0]["rr"] == 1.0
    assert results[1]["case_id"] == "rag_second"
    assert results[1]["hit"] == 1
    assert results[1]["recall"] == 1.0
    assert results[1]["rr"] == 0.5
    assert search_fn.call_count == 2


def test_agent_cases_are_skipped_without_search():
    cases = [
        {"id": "agent_first", "case_type": "agent", "query": "计算 2 + 3"},
        {"id": "agent_second", "case_type": "agent", "query": "计算 4 * 5"},
    ]
    search_fn = Mock(side_effect=AssertionError("Agent Case 不应触发检索"))

    results = run_rag_evaluation(cases, search_fn, k=3)

    assert results == []
    search_fn.assert_not_called()


def test_empty_search_results_return_zero_retrieval_scores():
    case = _retrieval_case("rag_empty", "没有命中的检索问题")
    search_fn = Mock(return_value=[])

    results = run_rag_evaluation([case], search_fn, k=3)

    assert len(results) == 1
    result = results[0]
    assert result["case_id"] == "rag_empty"
    assert result["hit"] == 0
    assert result["recall"] == 0.0
    assert result["rr"] == 0.0
    assert result["fact_coverage"] is None
    assert result["evidence_sufficient"] is None


def test_case_query_and_custom_k_are_passed_to_search():
    case = _retrieval_case("rag_arguments", "需要原样传递的 Query")
    search_fn = Mock(return_value=[])

    results = run_rag_evaluation([case], search_fn, k=7)

    search_fn.assert_called_once_with("需要原样传递的 Query", 7)
    assert results[0]["case_id"] == "rag_arguments"


def test_result_order_matches_retrieval_case_order():
    cases = [
        _retrieval_case("rag_z", "问题 Z"),
        {"id": "agent_middle", "case_type": "agent", "query": "计算 1 + 1"},
        _retrieval_case("rag_a", "问题 A"),
        _retrieval_case("rag_m", "问题 M"),
    ]
    search_fn = Mock(return_value=[])

    results = run_rag_evaluation(cases, search_fn, k=3)

    assert [result["case_id"] for result in results] == ["rag_z", "rag_a", "rag_m"]
    assert search_fn.call_args_list == [
        call("问题 Z", 3),
        call("问题 A", 3),
        call("问题 M", 3),
    ]

def test_rag_runner_latency():
    cases = [
        {
            "id": "rag_latency_test",
            "case_type": "retrieval",
            "category": "single_chunk",
            "query": "什么是 RAG？",
            "relevant_chunks": [
                {"document_id": "eval_rag", "chunk_index": 0}
            ]
        }
    ]

    def mock_search(query, k):
        return [
            ("测试文本", 0.9, {
                "document_id": "eval_rag",
                "chunk_index": 0
            })
        ]

    results = run_rag_evaluation(cases, mock_search, k=1)

    assert len(results) == 1
    assert "latency_ms" in results[0]
    assert isinstance(results[0]["latency_ms"], float)
    assert results[0]["latency_ms"] >= 0

def test_runner_continues_after_search_failure():
    cases = [
        _retrieval_case("rag_error", "故障查询"),
        _retrieval_case("rag_after", "正常查询"),
    ]

    search_fn = Mock(
        side_effect=[
            ConnectionError("Ollama unavailable"),
            [],
        ]
    )

    results = run_rag_evaluation(
        cases,
        search_fn,
        k=3,
    )

    # 两条 Case 都应该有结果记录
    assert len(results) == 2

    # 第一条：记录检索错误
    assert results[0]["case_id"] == "rag_error"
    assert results[0]["error"]["stage"] == "search"
    assert results[0]["error"]["type"] == "ConnectionError"

    # 第二条：仍然正常执行
    assert results[1]["case_id"] == "rag_after"
    assert results[1]["hit"] == 0
    assert "error" not in results[1]

    # 搜索函数确实调用了两次
    assert search_fn.call_count == 2
