"""Offline deployment contract tests; real stores and daemons are not opened."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    path = ROOT / 'scripts' / 'linux' / f'{name}.py'
    if not path.is_file():
        raise AssertionError(f'Missing implementation: {path.name}')
    spec = importlib.util.spec_from_file_location(f'linux_{name}', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class PreflightTests(unittest.TestCase):
    def test_valid_directory_leaves_no_probe_or_database(self):
        module = load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(module.validate_data_dir(Path(folder)), [])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_missing_relative_and_file_paths_rejected_without_creation(self):
        module = load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            file = root / 'file'
            file.write_text('retain')
            for path in (Path('relative'), root / 'missing', file):
                with self.subTest(path=path):
                    self.assertTrue(module.validate_data_dir(path))
            self.assertFalse((root / 'missing').exists())
            self.assertEqual(file.read_text(), 'retain')

    def test_actual_write_failure_is_reported(self):
        module = load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module.tempfile, 'mkstemp', side_effect=PermissionError('denied')):
                self.assertTrue(module.validate_data_dir(Path(folder)))

    def test_probe_cleanup_even_when_write_fails(self):
        module = load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module.os, 'fdopen', side_effect=OSError('write failure')):
                self.assertTrue(module.validate_data_dir(Path(folder)))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_cleanup_denial_is_a_preflight_failure(self):
        module = load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module.Path, 'unlink', side_effect=PermissionError('denied')):
                self.assertTrue(module.validate_data_dir(Path(folder)))

    def test_origin_validation(self):
        module = load_script('preflight')
        for url in ('http://host.docker.internal:11434', 'https://example.org/', 'http://[::1]:11434'):
            self.assertEqual(module.validate_ollama_origin(url), [])
        for url in ('', 'http://', 'ftp://host', 'http://host/api/chat', 'http://user:secret@host',
                    'http://host?query=1', 'http://host#fragment', 'http://host:abc',
                    'http://host:0', 'http://host:65536', 'http://bad host', 'http://host\n'):
            with self.subTest(url=url):
                self.assertTrue(module.validate_ollama_origin(url))

    def test_cli_json_and_failure_exit_do_not_leak_credentials(self):
        load_script('preflight')
        with tempfile.TemporaryDirectory() as folder:
            command = [sys.executable, '-B', str(ROOT / 'scripts/linux/preflight.py'),
                       '--data-dir', folder, '--ollama-url', 'http://user:secret@host']
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn('secret', result.stdout)
            payload = json.loads(result.stdout)
            self.assertTrue(payload['errors'])
            self.assertIn('platform', payload)
            self.assertIn('data_dir', payload)
            self.assertIn('writable', payload)
            self.assertIn('ollama_url', payload)
            self.assertEqual(list(Path(folder).iterdir()), [])


class ShellTests(unittest.TestCase):
    def run_shell(self, script, data, uid_failure=False):
        shell = shutil.which('sh')
        if not shell and os.name == 'nt':
            git = shutil.which('git')
            shell = str(Path(git).resolve().parents[1] / 'usr/bin/sh.exe') if git else None
        self.assertTrue(shell and Path(shell).is_file(), 'A POSIX shell is required for script checks')
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            helper = temp / 'docker_helper.py'
            log = temp / 'calls.jsonl'
            helper.write_text(
                'import sys,os,json\n'
                'with open(os.environ["KP_TEST_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\n'
                'sys.exit(17 if "run" in sys.argv and os.environ.get("KP_TEST_FAIL")=="1" else 0)\n')
            for name, contents in {
                # Isolate shell orchestration from Python host-path semantics.
                # The real preflight CLI is independently exercised above.
                'python3': '#!/bin/sh\nexit 0\n',
                'docker': '#!/bin/sh\nexec "$KP_TEST_PYTHON" "$KP_TEST_HELPER" "$@"\n',
            }.items():
                path = temp / name
                path.write_text(contents, newline='\n')
                path.chmod(0o755)
            env = dict(os.environ, KP_HOST_DATA_DIR=str(data), KP_OLLAMA_BASE_URL='http://host:11434',
                       KP_TEST_PYTHON=sys.executable.replace('\\', '/'),
                       KP_TEST_HELPER=str(helper).replace('\\', '/'), KP_TEST_LOG=str(log),
                       KP_TEST_FAIL='1' if uid_failure else '0')
            if os.name == 'nt' and Path(data).is_absolute():
                env['KP_HOST_DATA_DIR'] = '/c/test-data'
            def shell_path(path):
                value = str(path).replace('\\', '/')
                if os.name == 'nt' and len(value) > 1 and value[1] == ':':
                    value = '/' + value[0].lower() + value[2:]
                return value
            result = subprocess.run([shell, '-c', 'PATH="$1:$3:$PATH"; export PATH; "$4" "$2"',
                                     'test', shell_path(temp),
                                     shell_path(ROOT / 'scripts/linux' / script),
                                     shell_path(Path(shell).parent), shell_path(shell)],
                                    cwd=folder, env=env, capture_output=True, text=True, timeout=20)
            calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
            return result, calls

    def test_up_from_other_cwd_checks_uid_before_start(self):
        with tempfile.TemporaryDirectory() as folder:
            result, calls = self.run_shell('up.sh', folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            run_index = next(i for i, args in enumerate(calls) if 'run' in args)
            up_index = next(i for i, args in enumerate(calls) if 'up' in args)
            self.assertLess(run_index, up_index)
            self.assertIn('10001:10001', calls[run_index])
            self.assertIn('--no-build', calls[up_index])

    def test_failed_uid_probe_prevents_start(self):
        with tempfile.TemporaryDirectory() as folder:
            result, calls = self.run_shell('up.sh', folder, uid_failure=True)
            self.assertEqual(result.returncode, 17, result.stderr)
            self.assertTrue(any('run' in args for args in calls))
            self.assertFalse(any('up' in args for args in calls))

    def test_invalid_data_root_never_calls_docker(self):
        result, calls = self.run_shell('up.sh', 'relative')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must be absolute', result.stderr)
        self.assertEqual(calls, [])

    def test_down_uses_same_project_without_removing_volumes(self):
        with tempfile.TemporaryDirectory() as folder:
            result, calls = self.run_shell('down.sh', folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 1)
            self.assertIn('knowledgepilot-v14', calls[0])
            self.assertEqual(calls[0][-1], 'down')
            self.assertNotIn('-v', calls[0])
            self.assertNotIn('--volumes', calls[0])


class PersistenceContractTests(unittest.TestCase):
    def test_failed_host_probe_cannot_be_reported_as_pass(self):
        module = load_script('verify_persistence')
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module, 'validate_data_dir', return_value=['cleanup denied']):
                with self.assertRaises(RuntimeError):
                    module.host_probe(Path(folder))

    def test_fresh_run_is_exclusive_and_cannot_escape_root(self):
        module = load_script('verify_persistence')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = module.create_run_dir(root, '20261024T000000Z-abcdef')
            self.assertTrue(run_dir.is_relative_to(root.resolve()))
            with self.assertRaises(FileExistsError):
                module.create_run_dir(root, '20261024T000000Z-abcdef')
            for run_id in ('../../outside', '', '/tmp/other'):
                with self.assertRaises(ValueError):
                    module.create_run_dir(root, run_id)

    def test_cleanup_command_is_scoped_and_preserves_data(self):
        module = load_script('verify_persistence')
        command = module.compose_prefix('docker', ['compose'], 'kp-step2-test', ROOT / 'compose.yaml')
        self.assertEqual(command[-2:], ['-p', 'kp-step2-test'])
        self.assertNotIn('--volumes', command + ['down'])
        with self.assertRaises(ValueError):
            module.compose_prefix('docker', ['compose'], 'knowledgepilot-v14', ROOT / 'compose.yaml')

    def test_desktop_engine_cannot_be_marked_native_linux(self):
        module = load_script('verify_persistence')
        self.assertFalse(module.native_linux('Linux', {'OperatingSystem': 'Docker Desktop',
                                                       'KernelVersion': '6.6-microsoft-standard-WSL2'}))
        self.assertFalse(module.native_linux('Windows', {'OperatingSystem': 'Ubuntu'}))
        self.assertTrue(module.native_linux('Linux', {'OperatingSystem': 'Ubuntu 24.04',
                                                      'KernelVersion': '6.8.0-generic'}))

    def test_unavailable_engine_produces_failed_evidence_without_cleanup(self):
        load_script('verify_persistence')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = subprocess.run([
                sys.executable, '-B', str(ROOT / 'scripts/linux/verify_persistence.py'),
                '--test-root', str(root), '--ollama-url', 'http://localhost:11434',
                '--docker', str(root / 'nonexistent-docker'), '--evidence-root', str(root),
            ], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1, result.stderr)
            paths = list(root.glob('linux-evidence-*.json'))
            self.assertEqual(len(paths), 1)
            evidence = json.loads(paths[0].read_text(encoding='utf-8'))
            self.assertEqual(evidence['status'], 'failed')
            self.assertEqual(evidence['native_linux_acceptance'], 'BLOCKED_NOT_RUN')
            self.assertFalse(any('down' in c['argv'] for c in evidence['commands']))
            self.assertEqual(evidence['commands'][-1]['exit_code'], None)
