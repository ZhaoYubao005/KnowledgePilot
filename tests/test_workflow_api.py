"""Isolated workflow router executes the real graph with only the model replaced."""
import importlib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from knowledge_pilot.api.reliability import install_reliability


def client(monkeypatch, model):
    module = importlib.import_module('knowledge_pilot.api.workflow')
    monkeypatch.setattr('knowledge_pilot.workflow.graph.ollama_message', model)
    app = FastAPI()
    install_reliability(app)
    app.include_router(module.router)
    return TestClient(app, raise_server_exceptions=False)


def test_api_tool_path(monkeypatch):
    from knowledge_pilot.tools.calculator import calculator
    monkeypatch.setattr('knowledge_pilot.workflow.graph.production_executor',
                        lambda name, args: calculator(**args))
    with client(monkeypatch, lambda m, schema=None: '42') as api:
        response = api.post('/workflow/chat', json={'query': '6*7', 'route': 'tool',
            'tool': {'name': 'calculator', 'arguments': {'a': 6, 'b': 7, 'operation': 'multiply'}}})
    assert response.status_code == 200
    assert response.json()['tool_result'] == 42
    assert response.json()['status'] == 'completed'
    assert response.headers['x-request-id']


@pytest.mark.parametrize('body', [{'query': ''}, {'query': 'x', 'route': 'tool'},
    {'query': 'x', 'route': 'shell'}, {'query': 'x', 'top_k': 999}])
def test_api_rejects_bad_input(monkeypatch, body):
    with client(monkeypatch, lambda *a: None) as api:
        response = api.post('/workflow/chat', json=body)
    assert response.status_code == 422


@pytest.mark.parametrize('error_name,status', [('ModelTimeout', 504), ('ModelUnavailable', 503),
                                               ('ModelResponseError', 502)])
def test_api_model_error_mapping(monkeypatch, error_name, status):
    from knowledge_pilot import errors
    def model(messages, schema=None):
        raise getattr(errors, error_name)('llm')
    with client(monkeypatch, model) as api:
        response = api.post('/workflow/chat', json={'query': 'private-data'})
    assert response.status_code == status
    assert 'private-data' not in response.text


def test_invalid_route_returns_failed_contract(monkeypatch):
    with client(monkeypatch, lambda m, schema=None: {'route': 'shell'}) as api:
        response = api.post('/workflow/chat', json={'query': 'hi'})
    assert response.status_code == 200
    assert response.json()['status'] == 'failed'
    assert response.json()['error'] == 'invalid_route'
