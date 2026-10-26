"""Real API/Chroma in a temporary directory, controlled HTTP model fault fixture.

This is NOT real Ollama, Docker or Linux deployment acceptance.
"""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import requests

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'synthetic-private-value-DO-NOT-LOG'


def main():
    state = {'mode': 'ok'}

    class ModelFixture(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            mode = state['mode']
            if mode == 'slow':
                time.sleep(0.6)
            status = 500 if mode == 'http_error' else 200
            if mode == 'invalid_json':
                body = MARKER.encode()
            elif mode == 'bad_schema':
                body = json.dumps({'private': MARKER}).encode()
            elif self.path == '/api/embed':
                body = json.dumps({'embeddings': [[1.0] + [0.0] * 1023]}).encode()
            else:
                body = json.dumps({'message': {'role': 'assistant', 'content': 'controlled fixture answer'}}).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    upstream = ThreadingHTTPServer(('127.0.0.1', 0), ModelFixture)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    evidence = {'run_id': run_id, 'scope': 'real local API/Chroma with controlled HTTP upstream fixture',
                'real_ollama': False, 'docker_linux_deployment': 'NOT_RUN', 'checks': {}, 'status': 'failed'}
    try:
        with tempfile.TemporaryDirectory(prefix='kp-step3-') as temp:
            root = Path(temp)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {key: value for key, value in os.environ.items() if not key.startswith('KP_')}
            env.update(PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1',
                       KP_DATA_DIR=str(root / 'data'), KP_OLLAMA_BASE_URL=f'http://127.0.0.1:{upstream.server_port}',
                       KP_OLLAMA_READ_TIMEOUT_SECONDS='0.2', KP_OLLAMA_CONNECT_TIMEOUT_SECONDS='5')
            base = f'http://127.0.0.1:{port}'
            log_path = root / 'server.log'
            with log_path.open('w', encoding='utf-8') as log:
                process = subprocess.Popen([sys.executable, '-B', '-m', 'uvicorn',
                    'knowledge_pilot.api.app:app', '--host', '127.0.0.1', '--port', str(port)],
                    cwd=root, env=env, stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 30
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError('real API process exited during startup')
                        try:
                            health = requests.get(base + '/health', timeout=1)
                            if health.status_code == 200:
                                break
                        except requests.ConnectionError:
                            pass
                        if time.monotonic() >= deadline:
                            raise RuntimeError('real API startup timeout')
                        time.sleep(0.2)
                    evidence['checks']['health'] = health.status_code
                    ids = set()
                    for mode, expected in [('ok', 200), ('http_error', 502), ('invalid_json', 502),
                                           ('bad_schema', 502), ('slow', 504)]:
                        state['mode'] = mode
                        response = requests.post(base + '/chat', json={'query': MARKER}, timeout=10)
                        if response.status_code != expected or MARKER in response.text:
                            raise RuntimeError('unexpected API outcome for ' + mode)
                        ids.add(response.headers['x-request-id'])
                        evidence['checks'][mode] = response.status_code
                    state['mode'] = 'ok'
                    uploaded = requests.post(base + '/documents', files={
                        'file': ('probe.txt', b'controlled synthetic document', 'text/plain')}, timeout=10)
                    if uploaded.status_code != 201 or uploaded.json()['chunk_count'] != 1:
                        raise RuntimeError('real temporary Chroma upload failed')
                    evidence['checks']['temporary_chroma_upload'] = uploaded.status_code
                    invalid = requests.post(base + '/chat', json={'query': {'private': MARKER}}, timeout=10)
                    if invalid.status_code != 422 or MARKER in invalid.text:
                        raise RuntimeError('validation input reflected')
                    evidence['checks']['redacted_validation'] = invalid.status_code
                    missing = requests.delete(base + '/documents/' + MARKER + '?token=' + MARKER, timeout=10)
                    if missing.status_code != 404:
                        raise RuntimeError('document not-found contract failed')
                    upstream.shutdown()
                    upstream.server_close()
                    response = requests.post(base + '/chat', json={'query': MARKER}, timeout=10)
                    evidence['checks']['connection_observed_status'] = response.status_code
                    if response.status_code != 503 or MARKER in response.text:
                        raise RuntimeError('connection failure mapping failed')
                    evidence['checks']['connection_failure'] = response.status_code
                    evidence['checks']['unique_request_ids'] = len(ids) == 5
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            text = log_path.read_text(encoding='utf-8', errors='replace')
            if MARKER in text or 'controlled synthetic document' in text or 'controlled fixture answer' in text:
                raise RuntimeError('sensitive fixture content leaked to real process logs')
            events = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
            if not any(event.get('exception', {}).get('frames') for event in events):
                raise RuntimeError('safe diagnostic traceback frames missing')
            evidence['checks']['real_process_log_redaction'] = True
            evidence['checks']['safe_traceback_frames'] = True
            evidence['status'] = 'passed'
    except Exception as error:
        evidence['error_type'] = type(error).__name__
        raise
    finally:
        upstream.shutdown()
        upstream.server_close()
        path = ROOT / 'docs/engineering' / f'step3-evidence-{run_id}.json'
        with path.open('x', encoding='utf-8') as output:
            json.dump(evidence, output, indent=2)
            output.write('\n')
        print(json.dumps(evidence, indent=2))
        print('Evidence: ' + str(path))


if __name__ == '__main__':
    main()
