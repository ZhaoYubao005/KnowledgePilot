"""Real graph execution; only model replies are deterministic test doubles."""
import importlib.util
import pytest


def test_workflow_is_implemented():
    assert importlib.util.find_spec('knowledge_pilot.workflow') is not None


def run(request, replies, executor=None):
    from knowledge_pilot.workflow.graph import run_workflow
    iterator = iter(replies)
    def model(messages, schema=None):
        return next(iterator)
    return run_workflow(request, model=model, executor=executor)


def test_direct_and_state_order():
    result = run({'query': 'hello'}, [{'route': 'direct'}, 'hello back'])
    assert result['answer'] == 'hello back'
    assert result['status'] == 'completed'
    assert result['trace'] == ['initialize', 'decide', 'generate', 'finish']


def test_real_calculator_executor():
    from knowledge_pilot.tools.calculator import calculator
    result = run({'query': '23 * 17', 'route': 'tool',
                  'tool': {'name': 'calculator', 'arguments': {'a': 23, 'b': 17, 'operation': 'multiply'}}},
                 ['391'], lambda name, args: calculator(**args))
    assert result['tool_result'] == 391
    assert result['trace'] == ['initialize', 'decide', 'tool', 'generate', 'finish']


def test_retrieval_uses_registry_contract():
    calls = []
    def executor(name, arguments):
        calls.append((name, arguments))
        return [{'content': 'evidence', 'source': 'owned.txt'}]
    result = run({'query': 'our notes', 'route': 'rag', 'top_k': 2}, ['grounded'], executor)
    assert calls == [('search_knowledge_base', {'query': 'our notes', 'top_k': 2, 'document_id': None})]
    assert result['evidence'][0]['content'] == 'evidence'
    assert result['trace'] == ['initialize', 'decide', 'retrieve', 'generate', 'finish']


def test_empty_retrieval_stops_before_generation():
    result = run({'query': 'missing', 'route': 'rag'}, [], lambda n, a: [])
    assert result['status'] == 'no_results'
    assert 'generate' not in result['trace']


@pytest.mark.parametrize('decision', [{'route': 'unknown'}, {'route': 'tool'},
    {'route': 'tool', 'tool': {'name': 'shell', 'arguments': {}}},
    {'route': 'direct', 'tool': {'name': 'calculator', 'arguments': {'a': 1, 'b': 2, 'operation': 'add'}}},
    {'route': 'tool', 'tool': {'name': 'calculator', 'arguments': {'a': 'secret', 'b': 2, 'operation': 'add'}}}])
def test_bad_model_decision_is_not_success(decision):
    result = run({'query': 'query'}, [decision])
    assert result['status'] == 'failed'
    assert result['error'] == 'invalid_route'
    assert 'generate' not in result['trace']


def test_tool_failure_is_safe_and_terminal():
    from knowledge_pilot.tools.calculator import calculator
    result = run({'query': 'divide', 'route': 'tool', 'tool': {'name': 'calculator',
        'arguments': {'a': 1, 'b': 0, 'operation': 'divide'}}}, [], lambda name, args: calculator(**args))
    assert result['status'] == 'failed'
    assert result['error'] == 'tool_failed'
    assert 'generate' not in result['trace']


@pytest.mark.parametrize('error_name', ['ModelTimeout', 'ModelUnavailable', 'ModelResponseError'])
def test_model_errors_preserve_existing_types(error_name):
    from knowledge_pilot import errors
    from knowledge_pilot.workflow.graph import run_workflow
    error = getattr(errors, error_name)
    def model(messages, schema=None):
        raise error('llm')
    with pytest.raises(error):
        run_workflow({'query': 'hello'}, model=model)


@pytest.mark.parametrize('payload', [{'query': ' '}, {'query': 'x', 'route': 'unknown'},
    {'query': 'x', 'route': 'tool'}, {'query': 'x', 'top_k': 0},
    {'query': 'x', 'route': 'direct', 'tool': {'name': 'calculator', 'arguments': {'a': 1, 'b': 2, 'operation': 'add'}}}])
def test_invalid_request_rejected(payload):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        run(payload, [])


def test_calls_do_not_share_state():
    first = run({'query': 'one', 'route': 'direct'}, ['one'])
    second = run({'query': 'two', 'route': 'direct'}, ['two'])
    assert first['query'] == 'one' and second['query'] == 'two'
    assert len(first['trace']) == len(second['trace']) == 4


@pytest.mark.parametrize('result', [None, {'content': 'wrong shape'}, [{'source': '/private/path'}]])
def test_bad_retrieval_is_terminal(result):
    value = run({'query': 'notes', 'route': 'rag'}, [], lambda n, a: result)
    assert value['status'] == 'failed' and value['error'] == 'retrieval_failed'


def test_retrieval_exception_does_not_disclose_value():
    def executor(n, a):
        raise RuntimeError('PRIVATE_SECRET')
    result = run({'query': 'notes', 'route': 'rag'}, [], executor)
    assert result['error'] == 'retrieval_failed'
    assert 'PRIVATE_SECRET' not in str(result)


def test_graph_reuse_resets_supplied_state():
    from knowledge_pilot.workflow.graph import build_workflow
    graph = build_workflow(model=lambda m, schema=None: 'ok')
    result = graph.invoke({'request': {'query': 'hi', 'route': 'direct'},
        'error': 'injected', 'trace': ['old'], 'evidence': [{'content': 'old'}], 'status': 'failed'})
    assert result['status'] == 'completed' and result['evidence'] == [] and result['error'] is None
    assert result['trace'] == ['initialize', 'decide', 'generate', 'finish']


def test_python_entry_disables_external_tracing():
    from langsmith.run_helpers import get_tracing_context
    from langsmith import tracing_context
    from knowledge_pilot.workflow.graph import run_workflow
    seen = []
    def model(messages, schema=None):
        seen.append(get_tracing_context()['enabled'])
        return 'ok'
    with tracing_context(enabled=True):
        run_workflow({'query': 'private', 'route': 'direct'}, model=model)
    assert seen == [False]
