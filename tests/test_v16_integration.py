"""Session/Workflow wiring exercises actual graph and durable store."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def memory(tmp_path, monkeypatch):
    from knowledge_pilot.memory.store import SessionStore
    from knowledge_pilot.memory import service
    store = SessionStore(tmp_path / 'sessions.db')
    monkeypatch.setattr(service, 'get_session_store', lambda: store)
    return store


def test_workflow_history_reaches_router_and_generator(memory):
    from knowledge_pilot.workflow.graph import run_workflow
    sid = memory.create()['session_id']
    seen = []
    def model(messages, schema=None):
        seen.append(messages)
        return {'route': 'direct'} if schema else 'bge-m3 uses 1024 dimensions'
    run_workflow({'query': 'My model is bge-m3', 'session_id': sid}, model=model)
    run_workflow({'query': 'What dimension is that model?', 'session_id': sid}, model=model)
    assert all(any(m['content'] == 'My model is bge-m3' for m in messages) for messages in seen[2:])
    assert all(messages[0]['role'] == 'system' for messages in seen)
    assert memory.read(sid)['revision'] == 2
    assert len(memory.read(sid)['turns']) == 2


def test_session_failed_workflow_is_not_saved(memory):
    from knowledge_pilot.workflow.graph import run_workflow
    sid = memory.create()['session_id']
    result = run_workflow({'query': 'x', 'session_id': sid}, model=lambda *a: {'route': 'shell'})
    assert result['status'] == 'failed' and memory.read(sid)['turns'] == []


def test_session_chat_uses_original_agent_with_history(memory, monkeypatch):
    from knowledge_pilot.memory import service
    sid = memory.create()['session_id']
    memory.append(sid, 'My model is bge-m3', 'noted', expected_revision=0)
    seen = []
    def agent(messages, max_steps):
        seen.extend(messages)
        return {'answer': '1024', 'trace': [], 'stop_reason': 'completed'}
    result = service.session_chat('What dimension?', sid, max_steps=2, agent=agent)
    assert result['answer'] == '1024'
    assert [m['role'] for m in seen] == ['system','user','assistant','user']
    assert seen[-1]['content'] == 'What dimension?'


def test_recovery_preserves_node_trace():
    from knowledge_pilot.workflow.graph import run_workflow
    from knowledge_pilot.errors import ModelTimeout
    calls = []
    def executor(name, arguments):
        calls.append(name)
        if len(calls) == 1:
            raise ModelTimeout('embedding')
        return [{'content': 'evidence', 'source': 'notes.txt'}]
    result = run_workflow({'query': 'notes', 'route': 'rag'}, model=lambda *a: 'grounded', executor=executor)
    assert result['status'] == 'completed' and len(calls) == 2
    assert result['trace'] == ['initialize','decide','retrieve','generate','finish']
    assert [e['status'] for e in result['diagnostics']] == ['failed','succeeded']


def test_sessions_http(memory):
    from knowledge_pilot.api.sessions import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post('/sessions')
        assert response.status_code == 201
        sid = response.json()['session_id']
        assert client.get('/sessions/' + sid).json()['turns'] == []
        assert client.delete('/sessions/' + sid).json()['revision'] == 1
        assert client.get('/sessions/not-valid').status_code == 404


def test_invalid_tool_result_diagnostic_is_failure():
    from knowledge_pilot.workflow.graph import run_workflow
    result = run_workflow({'query': '1+1', 'route': 'tool', 'tool': {
        'name': 'calculator', 'arguments': {'a': 1, 'b': 1, 'operation': 'add'}}},
        executor=lambda *a: float('inf'))
    assert result['status'] == 'failed'
    assert result['diagnostics'][-1]['status'] == 'failed'
    assert result['diagnostics'][-1]['category'] == 'invalid_result'


def test_bad_recovery_configuration_is_not_tool_failure(monkeypatch):
    from knowledge_pilot.workflow.graph import run_workflow
    from knowledge_pilot.errors import ConfigurationError
    monkeypatch.setenv('KP_TOOL_MAX_ATTEMPTS', '0')
    with pytest.raises(ConfigurationError):
        run_workflow({'query': 'notes', 'route': 'rag'})


def test_simultaneous_session_inference_returns_one_conflict(memory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from knowledge_pilot.memory.service import session_chat
    from knowledge_pilot.memory.store import SessionConflict
    sid = memory.create()['session_id']
    gate = Barrier(2)
    def agent(messages, max_steps):
        gate.wait(timeout=5)
        return {'answer': 'ok', 'stop_reason': 'completed', 'trace': []}
    def invoke(query):
        try:
            return session_chat(query, sid, agent=agent)['stop_reason']
        except SessionConflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(invoke, ['first', 'second'])) == ['completed', 'conflict']
    assert memory.read(sid)['revision'] == 1


def test_current_query_survives_context_budget(tmp_path, monkeypatch):
    from knowledge_pilot.memory.store import SessionStore
    from knowledge_pilot.memory import service
    store = SessionStore(tmp_path / 'bounded.db', max_turns=1, max_chars=10)
    monkeypatch.setattr(service, 'get_session_store', lambda: store)
    sid = store.create()['session_id']
    store.append(sid, 'old', 'ok', expected_revision=0)
    query = 'current question larger than historical budget'
    seen = []
    def agent(messages, max_steps):
        seen.extend(messages)
        return {'answer': 'ok', 'stop_reason': 'completed', 'trace': []}
    service.session_chat(query, sid, agent=agent)
    assert seen[-1]['content'] == query and seen[0]['role'] == 'system'


def test_session_model_error_and_max_steps_do_not_commit(memory):
    from knowledge_pilot.memory.service import session_chat
    from knowledge_pilot.errors import ModelUnavailable
    sid = memory.create()['session_id']
    def unavailable(messages, max_steps):
        raise ModelUnavailable('llm')
    with pytest.raises(ModelUnavailable):
        session_chat('question', sid, agent=unavailable)
    session_chat('question', sid, agent=lambda *a, **k: {'answer': 'incomplete', 'stop_reason': 'max_steps'})
    assert memory.read(sid)['revision'] == 0


def test_recovery_exhaustion_http_has_safe_diagnostics(monkeypatch):
    from knowledge_pilot.api.workflow import router
    from knowledge_pilot.api.reliability import install_reliability
    from knowledge_pilot.errors import ModelTimeout
    from knowledge_pilot.workflow import graph
    def unavailable(*a):
        raise ModelTimeout('embedding')
    monkeypatch.setattr(graph, 'production_executor', unavailable)
    app = FastAPI()
    install_reliability(app)
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post('/workflow/chat', json={'query': 'PRIVATE_TEXT', 'route': 'rag'})
    assert response.status_code == 504
    assert len(response.json()['diagnostics']) == 2
    assert 'PRIVATE_TEXT' not in response.text


def test_blank_completed_agent_answer_is_model_error(memory):
    from knowledge_pilot.memory.service import session_chat
    from knowledge_pilot.errors import ModelResponseError
    sid = memory.create()['session_id']
    with pytest.raises(ModelResponseError):
        session_chat('question', sid, agent=lambda *a, **k: {'answer': ' ', 'stop_reason': 'completed'})
    assert memory.read(sid)['revision'] == 0


def test_session_query_error_has_correct_safe_message():
    from knowledge_pilot.api.reliability import safe_input_detail
    from knowledge_pilot.errors import InputError
    assert safe_input_detail(InputError('invalid session query')) == 'invalid session query'


def test_session_direct_generation_ends_with_current_query(memory):
    from knowledge_pilot.workflow.graph import run_workflow
    sid = memory.create()['session_id']
    memory.append(sid, 'My model is bge-m3', 'noted', expected_revision=0)
    seen = []
    def model(messages, schema=None):
        seen.extend(messages)
        return '1024'
    run_workflow({'query': 'What dimensions?', 'route': 'direct', 'session_id': sid}, model=model)
    assert seen[-1] == {'role': 'user', 'content': 'What dimensions?'}
    assert 'conversation history' in seen[0]['content']
