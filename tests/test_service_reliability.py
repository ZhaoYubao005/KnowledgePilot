"""Real boundary code with isolated services; no developer database/network calls."""
import contextlib
import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib
import io
import json
import logging
import math
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import requests

SECRET = 'private-token-user-document-NEVER-LOG'


@contextlib.contextmanager
def api_module():
    names = ('chat_service', 'create_document', 'list_documents',
             'delete_document_service', 'update_document_service')
    stub = types.ModuleType('knowledge_pilot.api.services')
    for name in names:
        setattr(stub, name, Mock(name=name))
    package = importlib.import_module('knowledge_pilot.api')
    previous_attr = vars(package).get('app')
    previous = sys.modules.pop('knowledge_pilot.api.app', None)
    try:
        with patch.dict(sys.modules, {'knowledge_pilot.api.services': stub}):
            module = importlib.import_module('knowledge_pilot.api.app')
            yield module
    finally:
        sys.modules.pop('knowledge_pilot.api.app', None)
        if previous is not None:
            sys.modules['knowledge_pilot.api.app'] = previous
        if previous_attr is None:
            vars(package).pop('app', None)
        else:
            package.app = previous_attr


class LoggingTests(unittest.TestCase):
    def test_default_uvicorn_access_log_is_replaced_by_safe_request_log(self):
        from knowledge_pilot.logging_config import configure_logging
        configure_logging('INFO')
        self.assertTrue(logging.getLogger('uvicorn.access').disabled)

    def test_formatter_keeps_frames_but_no_exception_values_or_extras(self):
        from knowledge_pilot.logging_config import SafeJSONFormatter
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(SafeJSONFormatter())
        logger = logging.getLogger('step3-isolated-test')
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        try:
            try:
                raise ValueError(SECRET)
            except ValueError:
                logger.exception('internal_error', extra={'body': SECRET})
        finally:
            logger.removeHandler(handler)
        text = output.getvalue()
        self.assertNotIn(SECRET, text)
        payload = json.loads(text)
        self.assertEqual(payload['exception']['type'], 'ValueError')
        self.assertTrue(payload['exception']['frames'])
        self.assertIn('function', payload['exception']['frames'][-1])
        self.assertNotIn('body', payload)

    def test_configure_is_idempotent_and_does_not_change_root(self):
        from knowledge_pilot.logging_config import configure_logging
        output = io.StringIO()
        root_handlers = list(logging.getLogger().handlers)
        try:
            configure_logging('WARNING', stream=output)
            configure_logging('WARNING', stream=output)
            logger = logging.getLogger('knowledge_pilot.test')
            logger.info('request_complete')
            logger.warning('internal_error')
            self.assertEqual(len(output.getvalue().splitlines()), 1)
            self.assertEqual(logging.getLogger().handlers, root_handlers)
        finally:
            configure_logging('INFO')


class TransportTests(unittest.TestCase):
    def response(self, data):
        response = Mock()
        response.json.return_value = data
        return response

    def test_success_uses_bounded_transport_and_original_payload(self):
        from knowledge_pilot.llm.transport import post_json
        post = Mock(return_value=self.response({'message': {'content': 'ok'}}))
        payload = {'messages': [{'content': SECRET}]}
        result = post_json('http://example.invalid/api/chat', payload, operation='llm', post=post)
        self.assertEqual(result, {'message': {'content': 'ok'}})
        self.assertEqual(post.call_args.kwargs['json'], payload)
        self.assertEqual(post.call_args.kwargs['timeout'], (5.0, 120.0))
        post.return_value.raise_for_status.assert_called_once()

    def test_connection_timeout_http_json_and_structure_classification(self):
        from knowledge_pilot.errors import ModelUnavailable, ModelTimeout, ModelResponseError
        from knowledge_pilot.llm.transport import post_json
        cases = [(requests.ConnectionError(SECRET), ModelUnavailable),
                 (requests.Timeout(SECRET), ModelTimeout)]
        for source, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(expected) as raised:
                    post_json('http://example.invalid', {}, operation='llm', post=Mock(side_effect=source))
                self.assertIs(raised.exception.__cause__, source)
        for data in ([], None, 'not object'):
            with self.assertRaises(ModelResponseError):
                post_json('http://example.invalid', {}, operation='embedding', post=Mock(return_value=self.response(data)))
        response = self.response({})
        response.raise_for_status.side_effect = requests.HTTPError(SECRET)
        with self.assertRaises(ModelResponseError):
            post_json('http://example.invalid', {}, operation='llm', post=Mock(return_value=response))
        response = self.response({})
        response.json.side_effect = ValueError(SECRET)
        with self.assertRaises(ModelResponseError):
            post_json('http://example.invalid', {}, operation='llm', post=Mock(return_value=response))

    def test_embedding_rejects_missing_empty_boolean_and_nonfinite_vectors(self):
        from knowledge_pilot.errors import ModelResponseError
        from knowledge_pilot.retrieval.embedding import embed_text
        for data in ({}, {'embeddings': []}, {'embeddings': [[]]},
                     {'embeddings': [[True]]}, {'embeddings': [[math.nan]]},
                     {'embeddings': [['bad']]}, {'embeddings': [[1], [2]]},
                     {'embeddings': [[10 ** 400]]}):
            with self.subTest(data=data):
                with patch('knowledge_pilot.retrieval.embedding.requests.post', return_value=self.response(data)):
                    with self.assertRaises(ModelResponseError):
                        embed_text(SECRET)

    def test_chat_response_schema_is_checked_without_changing_tool_loop(self):
        from knowledge_pilot.errors import ModelResponseError
        # Stub only the registry import; no real Chroma can be initialized.
        registry = types.ModuleType('knowledge_pilot.tools.registry')
        registry.execute_tool_call = Mock()
        old_module = sys.modules.pop('knowledge_pilot.llm.ollama_client', None)
        try:
            with patch.dict(sys.modules, {'knowledge_pilot.tools.registry': registry}):
                module = importlib.import_module('knowledge_pilot.llm.ollama_client')
                for data in ({}, {'message': None}, {'message': {'content': 1}},
                             {'message': {'content': '', 'tool_calls': 'bad'}},
                             {'message': {'content': '', 'tool_calls': [None]}}):
                    with self.subTest(data=data):
                        with patch.object(module.requests, 'post', return_value=self.response(data)):
                            with self.assertRaises(ModelResponseError):
                                module.chat_with_ollama([{'role': 'user', 'content': SECRET}])
                tool = {'function': {'name': 'calculator', 'arguments': {'a': 1, 'b': 2, 'operation': 'add'}}}
                registry.execute_tool_call.return_value = 3
                with patch.object(module.requests, 'post', side_effect=[
                    self.response({'message': {'role': 'assistant', 'tool_calls': [tool]}}),
                    self.response({'message': {'content': 'done'}}),
                ]):
                    result = module.chat_with_ollama([{'role': 'user', 'content': 'calculate'}])
                self.assertEqual(result['answer'], 'done')
                self.assertEqual(result['trace'][0]['result'], 3)
        finally:
            sys.modules.pop('knowledge_pilot.llm.ollama_client', None)
            if old_module is not None:
                sys.modules['knowledge_pilot.llm.ollama_client'] = old_module


class HttpReliabilityTests(unittest.TestCase):
    def test_concurrent_sync_workers_receive_their_own_request_id(self):
        from knowledge_pilot.logging_config import request_id
        with api_module() as module:
            def service(query, max_steps):
                return {'answer': request_id.get(), 'trace': [], 'stop_reason': 'completed'}
            def call(index):
                with TestClient(module.app) as client:
                    response = client.post('/chat', json={'query': SECRET})
                    return response.headers['x-request-id'], response.json()['answer']
            with patch.object(module, 'chat_service', side_effect=service):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    pairs = list(pool.map(call, range(8)))
            self.assertTrue(all(header == answer for header, answer in pairs))
            self.assertEqual(len({header for header, answer in pairs}), 8)
            self.assertIsNone(request_id.get())

    def test_after_headers_failure_is_signalled_without_exposing_original_value(self):
        from knowledge_pilot.api.reliability import RequestLoggingMiddleware
        from knowledge_pilot.errors import InternalServiceError
        from knowledge_pilot.logging_config import request_id
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            raise RuntimeError(SECRET)
        messages = []
        async def send(message):
            messages.append(message)
        with self.assertRaises(InternalServiceError) as caught:
            asyncio.run(RequestLoggingMiddleware(app)({'type': 'http', 'method': 'GET'}, None, send))
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(len(messages), 1)
        self.assertIsNone(request_id.get())

    def test_openapi_declares_reliability_errors(self):
        with api_module() as module, TestClient(module.app) as client:
            schema = client.get('/openapi.json').json()
            self.assertIn('504', schema['paths']['/chat']['post']['responses'])
            self.assertIn('500', schema['paths']['/documents']['get']['responses'])

    def test_safe_status_mapping_and_request_id(self):
        from knowledge_pilot.errors import ModelUnavailable, ModelTimeout, ModelResponseError, ConfigurationError
        with api_module() as module, TestClient(module.app) as client:
            for error, status in ((ModelUnavailable('llm'), 503), (ModelTimeout('llm'), 504),
                                  (ModelResponseError('llm'), 502), (RuntimeError(SECRET), 500),
                                  (ConfigurationError(SECRET), 500)):
                with patch.object(module, 'chat_service', side_effect=error):
                    response = client.post('/chat', json={'query': SECRET})
                self.assertEqual(response.status_code, status)
                self.assertNotIn(SECRET, response.text)
                self.assertRegex(response.headers['x-request-id'], r'^[a-f0-9]{32}$')

    def test_validation_never_echoes_input_or_credentials(self):
        with api_module() as module, TestClient(module.app) as client:
            response = client.post('/chat', json={'query': {'private': SECRET}})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(SECRET, response.text)
            self.assertIsInstance(response.json()['detail'], list)

    def test_unknown_value_error_is_internal_not_reflected(self):
        with api_module() as module, TestClient(module.app) as client:
            with patch.object(module, 'create_document', side_effect=ValueError(SECRET)):
                response = client.post('/documents', files={'file': ('test.txt', b'private document')})
            self.assertEqual(response.status_code, 500)
            self.assertNotIn(SECRET, response.text)

    def test_internal_key_error_is_not_mistaken_for_missing_document(self):
        with api_module() as module, TestClient(module.app) as client:
            with patch.object(module, 'delete_document_service', side_effect=KeyError(SECRET)):
                response = client.delete('/documents/known-id')
            self.assertEqual(response.status_code, 500)
            self.assertNotIn(SECRET, response.text)

    def test_request_logs_route_template_and_context_without_sensitive_values(self):
        from knowledge_pilot.logging_config import SafeJSONFormatter, request_id
        with api_module() as module:
            output = io.StringIO()
            handler = logging.StreamHandler(output)
            handler.setFormatter(SafeJSONFormatter())
            logger = logging.getLogger('knowledge_pilot')
            logger.addHandler(handler)
            try:
                with TestClient(module.app) as client:
                    with patch.object(module, 'delete_document_service', side_effect=RuntimeError(SECRET)):
                        response = client.delete('/documents/' + SECRET + '?token=' + SECRET,
                                                 headers={'authorization': 'Bearer ' + SECRET})
                    next_response = client.get('/health')
                logs = output.getvalue()
                self.assertNotIn(SECRET, logs)
                events = [json.loads(line) for line in logs.splitlines()]
                complete = [item for item in events if item['event'] == 'request_complete']
                self.assertEqual(len(complete), 2)
                self.assertEqual(complete[0]['route'], '/documents/{document_id}')
                self.assertEqual(complete[0]['request_id'], response.headers['x-request-id'])
                self.assertNotEqual(response.headers['x-request-id'], next_response.headers['x-request-id'])
                self.assertIsNone(request_id.get())
                self.assertTrue(any(event.get('exception', {}).get('frames') for event in events))
            finally:
                logger.removeHandler(handler)
