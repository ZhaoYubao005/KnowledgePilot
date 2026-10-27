"""Actual subprocess HTTP acceptance; upstream model explicitly simulated."""
import json
import os
from pathlib import Path
import importlib.util
import sys


def test_workflow_http_acceptance(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / 'scripts/verify_v15_workflow.py'
    assert script.is_file(), 'V1.5 acceptance script missing'
    spec = importlib.util.spec_from_file_location('workflow_owned_process', root / 'scripts/integration/processes.py')
    processes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processes)
    result = processes.run_owned([sys.executable, '-B', str(script), '--evidence', str(tmp_path / 'evidence.json')],
        cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads((tmp_path / 'evidence.json').read_text(encoding='utf-8'))
    assert evidence['status'] == 'passed'
    assert evidence['upstream'] == 'deterministic_local_http_fixture'
    assert evidence['cleanup']['temporary_data_removed']
    assert evidence['cleanup']['children_exited']
    assert {'direct', 'auto_tool', 'auto_rag', 'no_results', 'tool_failure',
            'invalid_route', 'model_timeout', 'model_schema', 'model_connection',
            'chat_compatibility', 'input_validation', 'log_privacy'} <= set(evidence['checks'])
