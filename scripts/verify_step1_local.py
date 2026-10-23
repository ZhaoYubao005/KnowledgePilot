"""Explicit local HTTP/Chroma smoke; writes only a newly-created temporary store.

Uses the existing Python environment and running host Ollama. This does NOT test Docker.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import requests


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='kp-step1-') as directory:
        data_root = Path(directory) / 'data'
        env = {k: v for k, v in os.environ.items() if not k.startswith('KP_')}
        env.update(PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1',
                   KP_DATA_DIR=str(data_root), KP_OLLAMA_BASE_URL='http://localhost:11434')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        base = f'http://127.0.0.1:{port}'

        def start(log):
            process = subprocess.Popen(
                [sys.executable, '-B', '-m', 'uvicorn', 'knowledge_pilot.api.app:app',
                 '--host', '127.0.0.1', '--port', str(port)],
                cwd=directory, env=env, stdout=log, stderr=log,
            )
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('API exited during startup; inspect probe log')
                    try:
                        response = requests.get(base + '/health', timeout=1)
                        if response.status_code == 200:
                            assert response.json() == {'status': 'ok'}
                            return process
                    except requests.ConnectionError:
                        pass
                    time.sleep(0.2)
                raise RuntimeError('API startup exceeded 30 seconds')
            except BaseException:
                stop(process)
                raise

        def stop(process):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

        log_path = Path(directory) / 'uvicorn.log'
        try:
            with log_path.open('w', encoding='utf-8') as log:
                process = start(log)
                try:
                    print('PASS actual Uvicorn GET /health 200', flush=True)
                    response = requests.post(base + '/documents', files={
                        'file': ('step1.txt', b'KnowledgePilot Step 1 persistence probe.', 'text/plain')
                    }, timeout=120)
                    assert response.status_code == 201, response.text
                    document = response.json()
                    assert document['chunk_count'] == 1
                    document_id = document['document_id']
                    assert (data_root / 'vector_store' / 'chroma.sqlite3').is_file()
                    assert (data_root / 'raw_documents' / document_id / 'step1.txt').is_file()
                    print('PASS real Ollama embedding + configured Chroma/raw paths', flush=True)
                finally:
                    stop(process)
                process = start(log)
                try:
                    response = requests.get(base + '/documents', timeout=10)
                    assert response.status_code == 200
                    assert document in response.json(), response.text
                    response = requests.put(base + '/documents/' + document_id, files={
                        'file': ('updated.txt', b'Updated Step 1 probe.', 'text/plain')
                    }, timeout=120)
                    assert response.status_code == 200, response.text
                    assert response.json()['chunk_count'] == 1
                    response = requests.delete(base + '/documents/' + document_id, timeout=10)
                    assert response.status_code == 200, response.text
                    assert not (data_root / 'raw_documents' / document_id).exists()
                    print('PASS process restart persistence + update/delete', flush=True)
                finally:
                    stop(process)
        except BaseException:
            print(log_path.read_text(encoding='utf-8', errors='replace')[-5000:])
            raise
    print(json.dumps({'scope': 'local HTTP + real Ollama/Chroma, NOT Docker', 'status': 'passed'}))


if __name__ == '__main__':
    main()
