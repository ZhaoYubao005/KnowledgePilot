"""Actual HTTP + production graph/tools/Chroma. Optional real Ollama, owned data only."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from urllib.parse import urlsplit

from verify_step4_api import ApiProcess, ROOT

PRIVATE = 'V15_PRIVATE_SENTINEL_NEVER_LOG'
DOCUMENT = 'The project codename is Blue Harbor. ' + PRIVATE


class WorkflowFixture:
    """Only the model/embedding upstream is simulated, never the application."""
    def __init__(self):
        self.route = 'direct'
        self.fault = None
        self.calls = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.calls.append({'path': self.path, 'structured': 'format' in data})
                if owner.fault == 'slow':
                    time.sleep(0.6)
                if owner.fault == 'schema':
                    result = {'private': PRIVATE}
                elif self.path == '/api/embed':
                    result = {'embeddings': [[1.0] + [0.0] * 1023]}
                elif 'format' in data:
                    decision = {'route': owner.route}
                    if owner.route == 'tool':
                        decision['tool'] = {'name': 'calculator', 'arguments': {
                            'a': 6, 'b': 7, 'operation': 'multiply'}}
                    result = {'message': {'role': 'assistant', 'content': json.dumps(decision)}}
                else:
                    result = {'message': {'role': 'assistant', 'content': '42; Blue Harbor (simulated model).'}}
                body = json.dumps(result).encode()
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.closed = False

    def start(self):
        self.thread.start()

    def close(self):
        if not self.closed:
            self.server.shutdown()
            self.thread.join(timeout=5)
            self.server.server_close()
            self.closed = True


def verify(evidence_path: Path, real_origin: str | None = None):
    if real_origin:
        parsed = urlsplit(real_origin)
        if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
                or parsed.username or parsed.password or parsed.path not in {'', '/'}
                or parsed.query or parsed.fragment):
            raise ValueError('real Ollama must be a credential-free loopback HTTP origin')
    evidence = {'status': 'failed', 'upstream': 'real_host_ollama' if real_origin else
                'deterministic_local_http_fixture', 'requests': [], 'checks': {},
                'time_utc': datetime.now(timezone.utc).isoformat(),
                'versions': {name: importlib.metadata.version(name) for name in
                             ['langgraph', 'pydantic', 'fastapi', 'chromadb']}}
    sha = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    evidence['source_head'] = sha.stdout.strip() if sha.returncode == 0 else 'unknown'
    evidence['source_dirty'] = bool(subprocess.run(['git', 'status', '--porcelain'],
        cwd=ROOT, capture_output=True, text=True).stdout.strip())
    fixture = None if real_origin else WorkflowFixture()
    api = None
    owned = None
    try:
        with tempfile.TemporaryDirectory(prefix='kp-v15-') as folder:
            owned = Path(folder)
            nonce = uuid.uuid4().hex
            (owned / '.step4-owned').write_text(nonce, encoding='utf-8')
            if fixture:
                fixture.start()
            api = ApiProcess(owned, nonce, real_origin or fixture.origin,
                             evidence['requests'], real=bool(real_origin))
            try:
                api.start()
                def call(label, payload, expected=200):
                    return api.request(label, 'POST', '/workflow/chat', expected,
                                       json=payload, timeout=300 if real_origin else 20)

                direct = call('direct', {'query': 'Reply briefly with OK. ' + PRIVATE, 'route': 'direct'})
                assert direct['status'] == 'completed' and direct['answer'].strip()
                assert direct['trace'] == ['initialize', 'decide', 'generate', 'finish']
                evidence['checks']['direct'] = 'passed'

                if fixture:
                    fixture.route = 'tool'
                tool = call('auto_tool', {'query': 'Calculate 6 multiplied by 7. Use calculator.'})
                assert tool['status'] == 'completed' and tool['route'] == 'tool' and tool['tool_result'] == 42
                assert '42' in tool['answer']
                assert tool['trace'] == ['initialize', 'decide', 'tool', 'generate', 'finish']
                evidence['checks']['auto_tool'] = 'passed'

                doc = api.request('upload', 'POST', '/documents', 201,
                    files={'file': ('v15-probe.txt', DOCUMENT.encode(), 'text/plain')}, timeout=150)
                if fixture:
                    fixture.route = 'rag'
                rag = call('auto_rag', {'query': 'What is the project codename in my uploaded document?',
                                      'document_id': doc['document_id'], 'top_k': 1})
                assert rag['status'] == 'completed' and rag['route'] == 'rag'
                assert 'blue harbor' in rag['answer'].lower()
                assert rag['evidence'] == [{'content': DOCUMENT, 'source': 'v15-probe.txt'}]
                assert rag['trace'] == ['initialize', 'decide', 'retrieve', 'generate', 'finish']
                evidence['checks']['auto_rag'] = 'passed'
                evidence['workflow_results'] = {
                    'tool': {'route': tool['route'], 'value': tool['tool_result'], 'trace': tool['trace'],
                             'answer_contains_expected_value': True},
                    'rag': {'route': rag['route'], 'evidence_count': len(rag['evidence']),
                            'trace': rag['trace'], 'answer_contains_document_fact': True}}
                evidence['retrieval'] = {'embedding': 'real_bge_m3' if real_origin else 'deterministic_1024_vector',
                                         'store': 'real_isolated_persistent_chroma', 'tool': 'production_registry'}
                api.request('delete', 'DELETE', '/documents/' + doc['document_id'], 200)
                empty = call('no_results', {'query': 'missing', 'route': 'rag', 'document_id': doc['document_id']})
                assert empty['status'] == 'no_results' and 'generate' not in empty['trace']
                evidence['checks']['no_results'] = 'passed'

                failed = call('tool_failure', {'query': 'divide', 'route': 'tool', 'tool': {
                    'name': 'calculator', 'arguments': {'a': 1, 'b': 0, 'operation': 'divide'}}})
                assert failed['status'] == 'failed' and failed['error'] == 'tool_failed'
                evidence['checks']['tool_failure'] = 'passed'
                call('input_validation', {'query': PRIVATE, 'route': 'shell'}, 422)
                evidence['checks']['input_validation'] = 'passed'

                old = api.request('chat_compatibility', 'POST', '/chat', 200,
                    json={'query': 'Reply OK without tools.', 'max_steps': 2}, timeout=300 if real_origin else 20)
                assert old['stop_reason'] == 'completed' and set(old) == {'answer', 'trace', 'stop_reason'}
                evidence['checks']['chat_compatibility'] = 'passed'

                if fixture:
                    fixture.route = 'shell'
                    invalid = call('invalid_route', {'query': PRIVATE})
                    assert invalid['status'] == 'failed' and invalid['error'] == 'invalid_route'
                    evidence['checks']['invalid_route'] = 'passed'
                    fixture.fault = 'schema'
                    call('model_schema', {'query': PRIVATE}, 502)
                    evidence['checks']['model_schema'] = 'passed'
                    fixture.fault = 'slow'
                    call('model_timeout', {'query': PRIVATE}, 504)
                    evidence['checks']['model_timeout'] = 'passed'
                    fixture.close()
                    call('model_connection', {'query': PRIVATE}, 503)
                    evidence['checks']['model_connection'] = 'passed'
                    evidence['upstream_calls'] = fixture.calls
            finally:
                api.stop()
                api.session.close()
            logs = api.log_path.read_text(encoding='utf-8')
            assert PRIVATE not in logs and DOCUMENT not in logs
            evidence['checks']['log_privacy'] = 'passed'
        evidence['status'] = 'passed'
    except Exception as error:
        evidence['error_type'] = type(error).__name__
        raise
    finally:
        if fixture:
            fixture.close()
        evidence['cleanup'] = {'temporary_data_removed': owned is None or not owned.exists(),
            'children_exited': api is None or all(child.poll() is not None for child in api.children)}
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--real-ollama', help='Explicit host Ollama origin, no downloads')
    args = parser.parse_args()
    evidence = verify(args.evidence.resolve(), args.real_ollama)
    print(json.dumps({'status': evidence['status'], 'checks': len(evidence['checks']),
                      'requests': len(evidence['requests']), 'upstream': evidence['upstream']}))


if __name__ == '__main__':
    main()
