"""Native transport payload and malformed reply checks, without model/network mocks elsewhere."""
import pytest
from knowledge_pilot.errors import ModelResponseError
from knowledge_pilot.workflow import model


@pytest.mark.parametrize('data', [{}, {'message': None}, {'message': {'content': ' '}},
    {'message': {'content': 42}}, {'message': {'content': 'ok', 'tool_calls': [{}]}}])
def test_bad_model_envelope(monkeypatch, data):
    monkeypatch.setattr(model, 'post_json', lambda *a, **k: data)
    with pytest.raises(ModelResponseError):
        model.ollama_message([])


def test_structured_router_payload(monkeypatch):
    seen = []
    def post(url, payload, **kwargs):
        seen.append(payload)
        return {'message': {'content': '{"route":"rag"}'}}
    monkeypatch.setattr(model, 'post_json', post)
    schema = {'type': 'object'}
    assert model.ollama_message([{'role': 'user', 'content': 'hi'}], schema) == {'route': 'rag'}
    assert seen[0]['format'] == schema and seen[0]['stream'] is False
    assert 'tools' not in seen[0]


def test_invalid_json_router_fails(monkeypatch):
    monkeypatch.setattr(model, 'post_json', lambda *a, **k: {'message': {'content': 'not json'}})
    with pytest.raises(ModelResponseError):
        model.ollama_message([], {'type': 'object'})
