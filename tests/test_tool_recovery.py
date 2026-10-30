"""Recovery policy tests use real calculator code and injected boundary failures."""
import json

import pytest
import requests

from knowledge_pilot.errors import ModelResponseError, ModelTimeout, ModelUnavailable
from knowledge_pilot.tools.calculator import calculator
from knowledge_pilot.tools.recovery import execute_with_recovery


def test_real_calculator_success_preserves_value():
    result = execute_with_recovery(
        'calculator', {'a': 17, 'b': 5, 'operation': 'multiply'},
        executor=lambda name, arguments: calculator(**arguments))

    assert result.value == 85
    assert result.error is None
    assert result.exception is None
    assert result.events == [{'stage': 'tool', 'attempt': 1, 'status': 'succeeded',
                              'category': None, 'retryable': False}]


@pytest.mark.parametrize('failure', [ModelTimeout('embedding'),
    ModelUnavailable('embedding'), requests.Timeout('private upstream address'),
    requests.ConnectionError('private token')])
def test_transient_readonly_retrieval_recovers_and_preserves_result(failure):
    calls = []
    evidence = [{'text': 'document evidence', 'score': 0.7}]

    def executor(name, arguments):
        calls.append((name, arguments))
        if len(calls) == 1:
            raise failure
        return evidence

    result = execute_with_recovery('search_knowledge_base', {'query': 'private query'},
                                   executor=executor)

    assert result.value is evidence
    assert result.error is None
    assert result.exception is None
    assert len(calls) == 2
    assert [event['status'] for event in result.events] == ['failed', 'succeeded']
    assert [event['attempt'] for event in result.events] == [1, 2]
    assert result.events[0]['stage'] == 'retrieve'
    assert result.events[0]['retryable'] is True
    assert result.events[1]['retryable'] is False
    assert 'private' not in json.dumps(result.events)


@pytest.mark.parametrize('max_attempts', [1, 2, 3])
def test_transient_retrieval_stops_at_exact_attempt_bound(max_attempts):
    calls = []
    failure = ModelTimeout('embedding')

    def executor(name, arguments):
        calls.append(name)
        raise failure

    result = execute_with_recovery('search_knowledge_base', {}, executor=executor,
                                   max_attempts=max_attempts)

    assert len(calls) == max_attempts
    assert result.value is None
    assert result.error == 'exhausted'
    assert result.exception is failure
    assert len(result.events) == max_attempts
    assert all(event['category'] == 'model_timeout' for event in result.events)
    assert all(event['retryable'] for event in result.events)


@pytest.mark.parametrize('max_attempts', [0, 4, -1, True, False, 2.0, '2', None])
def test_invalid_attempt_limit_is_rejected_before_execution(max_attempts):
    calls = []

    with pytest.raises(ValueError, match='max_attempts must be an integer from 1 to 3'):
        execute_with_recovery('search_knowledge_base', {},
                              executor=lambda *args: calls.append(args),
                              max_attempts=max_attempts)
    assert calls == []


@pytest.mark.parametrize('failure,category', [
    (ModelTimeout('embedding'), 'model_timeout'),
    (ModelUnavailable('embedding'), 'model_unavailable'),
    (requests.Timeout('secret'), 'network_timeout'),
    (requests.ConnectionError('secret'), 'network_unavailable')])
@pytest.mark.parametrize('name', ['calculator', 'send_email', 'delete_document'])
def test_other_tools_are_never_retried_even_for_transient_failures(name, failure, category):
    calls = []

    def executor(name, arguments):
        calls.append(name)
        raise failure

    result = execute_with_recovery(name, {}, executor=executor, max_attempts=3)

    assert calls == [name]
    assert result.error == category
    assert result.exception is failure
    assert result.events == [{'stage': 'tool', 'attempt': 1, 'status': 'failed',
                              'category': category, 'retryable': False}]


@pytest.mark.parametrize('failure,category', [
    (ModelResponseError('embedding'), 'model_response_error'),
    (ModelTimeout('llm'), 'model_timeout'),
    (ModelUnavailable('llm'), 'model_unavailable'),
    (RuntimeError('private path and token'), 'tool_failed'),
    (TypeError('private argument'), 'invalid_arguments'),
    (ValueError('private argument'), 'invalid_arguments')])
def test_nontransient_retrieval_failure_is_safe_and_not_retried(failure, category):
    calls = []

    def executor(name, arguments):
        calls.append(name)
        raise failure

    result = execute_with_recovery('search_knowledge_base', {'query': 'private'},
                                   executor=executor)

    assert calls == ['search_knowledge_base']
    assert result.error == category
    assert result.exception is failure
    assert result.events == [{'stage': 'retrieve', 'attempt': 1, 'status': 'failed',
                              'category': category, 'retryable': False}]
    assert 'private' not in json.dumps(result.events)
    assert 'private' not in repr(result)


def test_calculator_deterministic_failure_is_not_retried():
    calls = []

    def executor(name, arguments):
        calls.append(name)
        return calculator(**arguments)

    result = execute_with_recovery('calculator', {'a': 1, 'b': 0, 'operation': 'divide'},
                                   executor=executor, max_attempts=3)

    assert calls == ['calculator']
    assert result.value is None
    assert result.error == 'invalid_arguments'
    assert result.events[0]['retryable'] is False


@pytest.mark.parametrize('arguments', [None, [], 'private input'])
def test_invalid_argument_container_never_reaches_executor(arguments):
    calls = []
    result = execute_with_recovery('calculator', arguments,
                                   executor=lambda *args: calls.append(args))

    assert calls == []
    assert result.error == 'invalid_arguments'
    assert result.value is None
    assert result.events == [{'stage': 'tool', 'attempt': 1, 'status': 'failed',
                              'category': 'invalid_arguments', 'retryable': False}]


def test_later_deterministic_failure_stops_retrieval_before_remaining_budget():
    calls = []
    final_failure = ValueError('private invalid query')

    def executor(name, arguments):
        calls.append(name)
        if len(calls) == 1:
            raise requests.Timeout('private endpoint')
        raise final_failure

    result = execute_with_recovery('search_knowledge_base', {}, executor=executor,
                                   max_attempts=3)

    assert len(calls) == 2
    assert result.error == 'invalid_arguments'
    assert result.exception is final_failure
    assert [event['category'] for event in result.events] == [
        'network_timeout', 'invalid_arguments']
