"""Actual local HTTP subprocess tests, with real app modules and a simulated model."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_runner():
    path = ROOT / 'scripts/verify_step4_api.py'
    if not path.is_file():
        raise AssertionError('Step 4 integration runner is not implemented')
    spec = importlib.util.spec_from_file_location('step4_runner_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class HarnessSafetyTests(unittest.TestCase):
    def test_store_probe_refuses_unowned_directory(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                runner.validate_owned_root(Path(folder), 'not-owned')

    def test_wrong_expected_status_cannot_be_recorded_as_pass(self):
        runner = load_runner()
        records = []
        with self.assertRaises(AssertionError):
            runner.record_request(records, 'negative', 'GET', '/health', 500, 200, 'a' * 32)
        self.assertEqual(records[0]['status'], 'failed')
        self.assertEqual(records[0]['actual_status'], 500)
        self.assertEqual(records[0]['expected_status'], 200)

    def test_environment_does_not_inherit_real_store_or_model_settings(self):
        runner = load_runner()
        with tempfile.TemporaryDirectory() as folder:
            env = runner.api_environment(Path(folder), 'http://127.0.0.1:12345',
                                         inherited={'KP_DATA_DIR': 'DO_NOT_OPEN', 'KP_CHAT_MODEL': 'other'})
            self.assertEqual(env['KP_DATA_DIR'], str(Path(folder) / 'data'))
            self.assertNotEqual(env.get('KP_CHAT_MODEL'), 'other')


class RealHttpIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        load_runner()
        with tempfile.TemporaryDirectory(prefix='kp-step4-test-') as folder:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
            spec = importlib.util.spec_from_file_location('owned_step4_process', ROOT / 'scripts/integration/processes.py')
            processes = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(processes)
            result = processes.run_owned([sys.executable, '-B', str(ROOT / 'scripts/verify_step4_api.py'),
                '--test-root', folder, '--evidence-root', folder], cwd=ROOT, env=env, timeout=180)
            paths = list(Path(folder).glob('step4-evidence-*.json'))
            if len(paths) != 1:
                raise AssertionError('Runner did not write exactly one evidence file: ' + result.stderr[-1000:])
            cls.evidence = json.loads(paths[0].read_text(encoding='utf-8'))
            if result.returncode:
                raise AssertionError(json.dumps(cls.evidence, ensure_ascii=True)[-4000:] + result.stderr[-1000:])

    def test_crud_and_actual_store_queries(self):
        evidence = self.evidence
        self.assertEqual(evidence['status'], 'passed')
        for name in ('store_after_upload', 'store_after_update', 'store_after_delete', 'raw_files'):
            self.assertEqual(evidence['checks'][name]['status'], 'passed')

    def test_agent_tool_loop_and_error_contracts(self):
        self.assertEqual(self.evidence['checks']['agent_tool_loop']['status'], 'passed')
        records = self.evidence['requests']
        statuses = {item['actual_status'] for item in records}
        self.assertTrue({200, 201, 400, 404, 422, 500, 502, 503, 504}.issubset(statuses))
        self.assertTrue(all(item['status'] == 'passed' for item in records))

    def test_logs_ids_cleanup_and_upstream_provenance(self):
        self.assertEqual(self.evidence['checks']['logs']['status'], 'passed')
        self.assertTrue(self.evidence['cleanup']['temporary_data_removed'])
        self.assertTrue(self.evidence['cleanup']['children_exited'])
        self.assertEqual(self.evidence['upstream'], 'deterministic_local_http_fixture')
        self.assertEqual(self.evidence['optional']['real_ollama']['status'], 'NOT_RUN')
