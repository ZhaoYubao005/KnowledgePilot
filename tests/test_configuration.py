"""Configuration checks in fresh interpreters, without opening the real store."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ConfigurationTests(unittest.TestCase):
    def probe(self, overrides=None, code=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('KP_')}
        env.update(overrides or {})
        return subprocess.run(
            [sys.executable, '-B', '-c', code or (
                'import json; import knowledge_pilot.config as c; '
                'print(json.dumps([c.OLLAMA_URL,c.EMBEDDING_URL,c.MODEL_NAME,'
                'c.EMBEDDING_MODEL,str(c.DATA_DIR)]))'
            )], env=env, capture_output=True, text=True, timeout=20,
        )

    def test_defaults_preserve_local_and_evaluation_paths(self):
        result = self.probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            'http://localhost:11434/api/chat', 'http://localhost:11434/api/embed',
            'gemma4:e2b', 'bge-m3', 'data',
        ])

    def test_environment_overrides(self):
        result = self.probe({'KP_OLLAMA_BASE_URL': 'http://host.docker.internal:11434/',
                             'KP_CHAT_MODEL': 'chat-test', 'KP_EMBED_MODEL': 'embed-test',
                             'KP_DATA_DIR': str(Path.cwd() / 'isolated-data')})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            'http://host.docker.internal:11434/api/chat',
            'http://host.docker.internal:11434/api/embed', 'chat-test', 'embed-test',
            str(Path.cwd() / 'isolated-data'),
        ])

    def test_invalid_environment_fails_without_fallback(self):
        for overrides in ({'KP_CHAT_MODEL': ' '}, {'KP_EMBED_MODEL': ''},
                          {'KP_DATA_DIR': ''}, {'KP_DATA_DIR': 'relative-data'},
                          {'KP_OLLAMA_BASE_URL': 'ftp://host'},
                          {'KP_OLLAMA_BASE_URL': 'http://host/api/chat'},
                          {'KP_OLLAMA_BASE_URL': 'http://host:bad'}):
            with self.subTest(overrides=overrides):
                result = self.probe(overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ConfigurationError', result.stderr)

    def test_configuration_error_remains_a_value_error(self):
        from knowledge_pilot.errors import ConfigurationError
        self.assertTrue(issubclass(ConfigurationError, ValueError))

    def test_reliability_settings_are_validated_and_overridable(self):
        code = ('import json; from knowledge_pilot import config as c; '
                'print(json.dumps([c.LOG_LEVEL,c.OLLAMA_CONNECT_TIMEOUT,c.OLLAMA_READ_TIMEOUT]))')
        result = self.probe({'KP_LOG_LEVEL': 'warning', 'KP_OLLAMA_CONNECT_TIMEOUT_SECONDS': '0.5',
                             'KP_OLLAMA_READ_TIMEOUT_SECONDS': '30'}, code=code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ['WARNING', 0.5, 30.0])
        for settings in ({'KP_LOG_LEVEL': 'private-level'}, {'KP_OLLAMA_READ_TIMEOUT_SECONDS': 'NaN'},
                         {'KP_OLLAMA_CONNECT_TIMEOUT_SECONDS': '0'}, {'KP_OLLAMA_READ_TIMEOUT_SECONDS': '-1'},
                         {'KP_OLLAMA_READ_TIMEOUT_SECONDS': 'inf'}):
            with self.subTest(settings=settings):
                result = self.probe(settings, code=code)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('ConfigurationError', result.stderr)

    def test_embedding_uses_environment_address_and_model(self):
        result = self.probe({'KP_OLLAMA_BASE_URL': 'http://example.invalid:11434',
                             'KP_EMBED_MODEL': 'embedding-test'}, code='''
from unittest.mock import patch, Mock
from knowledge_pilot.retrieval.embedding import embed_text
with patch('knowledge_pilot.retrieval.embedding.requests.post') as post:
    post.return_value = Mock()
    post.return_value.json.return_value = {'embeddings': [[1.0, 2.0]]}
    assert embed_text('test') == [1.0, 2.0]
    assert post.call_args.args == ('http://example.invalid:11434/api/embed',)
    assert post.call_args.kwargs['json']['model'] == 'embedding-test'
''')
        self.assertEqual(result.returncode, 0, result.stderr)
