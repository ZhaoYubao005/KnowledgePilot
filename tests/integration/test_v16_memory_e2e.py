"""Actual API subprocess, SQLite and Chroma; only model HTTP is simulated."""
import importlib.util
import json
import os
from pathlib import Path
import sys


def test_v16_memory_actual_http_acceptance(tmp_path):
    root = Path(__file__).resolve().parents[2]
    script = root / 'scripts/verify_v16_memory.py'
    assert script.is_file(), 'V1.6 actual HTTP acceptance script missing'
    spec = importlib.util.spec_from_file_location(
        'v16_owned_process', root / 'scripts/integration/processes.py')
    processes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(processes)
    evidence_path = tmp_path / 'v16-evidence.json'
    result = processes.run_owned(
        [sys.executable, '-B', str(script), '--evidence', str(evidence_path)],
        cwd=root, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), timeout=150)

    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    assert evidence['status'] == 'passed'
    assert evidence['upstream'] == 'deterministic_local_http_fixture'
    assert evidence['acceptance_scope'] == 'actual_http_sqlite_chroma_simulated_model'
    assert all(evidence['cleanup'].values())
    assert {'session_create_read', 'workflow_multiturn', 'session_isolation',
            'restart_persistence', 'clear_history', 'bounded_history_current_query',
            'chat_multiturn', 'no_session_compatibility', 'retrieval_recovered',
            'retrieval_exhausted', 'failed_turn_not_saved', 'calculator_no_retry',
            'log_privacy', 'request_log_correlation'} <= set(evidence['checks'])
    assert all(item['status'] == 'passed' for item in evidence['checks'].values())
    assert all(item['status'] == 'passed' for item in evidence['requests'])
    assert evidence['provenance']['source_sha256']['scripts/verify_v16_memory.py']
    assert evidence['model_fixture']['answers_derived_from_received_messages'] is True
    assert evidence['model_fixture']['history_recall_observed'] is True
    assert evidence['model_fixture']['empty_history_unknown_observed'] is True
    recovered = evidence['recovery']['recovered']
    assert recovered['embedding_http_calls'] == 2
    assert [event['status'] for event in recovered['diagnostics']] == ['failed', 'succeeded']
    exhausted = evidence['recovery']['exhausted']
    assert exhausted['embedding_http_calls'] == 2
    assert exhausted['actual_status'] == 504
    assert len(evidence['upstream_requests']) > 5
    assert all('messages' not in item and 'query' not in item for item in evidence['upstream_requests'])
