"""Real API integration on owned temporary stores. Simulated/real upstreams are separate."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit

import requests
from integration.model_fixture import ModelFixture, MARKER, OLD_TEXT, NEW_TEXT

ROOT = Path(__file__).resolve().parents[1]


def validate_owned_root(root: Path, nonce: str) -> None:
    if (not root.is_absolute() or not (root / '.step4-owned').is_file()
            or (root / '.step4-owned').read_text(encoding='utf-8') != nonce):
        raise ValueError('refuse unowned test directory')


def api_environment(root: Path, origin: str, *, inherited=None, real=False) -> dict:
    env = {key: value for key, value in (os.environ if inherited is None else inherited).items()
           if not key.startswith('KP_')}
    env.update(PYTHONPATH=str(ROOT / 'src'), PYTHONDONTWRITEBYTECODE='1',
               KP_DATA_DIR=str(root / 'data'), KP_OLLAMA_BASE_URL=origin,
               KP_CHAT_MODEL='gemma4:e2b', KP_EMBED_MODEL='bge-m3',
               KP_OLLAMA_CONNECT_TIMEOUT_SECONDS='5',
               KP_OLLAMA_READ_TIMEOUT_SECONDS='120' if real else '0.2', KP_LOG_LEVEL='INFO')
    env['ANONYMIZED_TELEMETRY'] = 'False'
    for name in ('NO_PROXY', 'no_proxy'):
        env[name] = env.get(name, '') + ',127.0.0.1,localhost,::1'
    return env


def record_request(records: list, label: str, method: str, route: str,
                   actual: int | None, expected: int, request_id: str) -> None:
    valid = actual == expected and bool(re.fullmatch(r'[a-f0-9]{32}', request_id or ''))
    records.append({'label': label, 'method': method, 'route': route,
                    'actual_status': actual, 'expected_status': expected,
                    'request_id': request_id, 'status': 'passed' if valid else 'failed'})
    if not valid:
        raise AssertionError('HTTP contract failed: ' + label)


class ApiProcess:
    def __init__(self, root: Path, nonce: str, origin: str, records: list, *, real=False):
        validate_owned_root(root, nonce)
        self.root, self.nonce, self.records = root, nonce, records
        self.env = api_environment(root, origin, real=real)
        self.process = None
        self.children = []
        self.log = None
        self.log_path = root / 'api.log'
        self.session = requests.Session()
        self.session.trust_env = False  # Loopback test traffic must stay local.
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.base = f'http://127.0.0.1:{self.port}'

    def start(self):
        validate_owned_root(self.root, self.nonce)
        if self.process is not None:
            raise RuntimeError('API already running')
        self.log = self.log_path.open('a', encoding='utf-8')
        self.process = subprocess.Popen([sys.executable, '-B', '-m', 'uvicorn',
            'knowledge_pilot.api.app:app', '--host', '127.0.0.1', '--port', str(self.port)],
            cwd=self.root, env=self.env, stdout=self.log, stderr=self.log)
        self.children.append(self.process)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('API exited during startup')
            try:
                response = self.session.get(self.base + '/health', timeout=1)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(0.2)
        raise RuntimeError('API startup deadline exceeded')

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process = None
        if self.log is not None:
            self.log.close()
            self.log = None

    def request(self, label, method, path, expected, **kwargs):
        route = path.split('?')[0]
        if route.startswith('/documents/'):
            route = '/documents/{document_id}'
        try:
            response = self.session.request(method, self.base + path, timeout=kwargs.pop('timeout', 15),
                headers={'Authorization': 'Bearer ' + MARKER, 'X-Request-ID': MARKER}, **kwargs)
        except requests.RequestException as error:
            self.records.append({'label': label, 'method': method, 'route': route,
                'actual_status': None, 'expected_status': expected, 'request_id': None,
                'status': 'failed', 'error_type': type(error).__name__})
            raise
        record_request(self.records, label, method, route, response.status_code, expected,
                       response.headers.get('x-request-id', ''))
        return response.json()

    def inspect_store(self, query='blue', document_id=None):
        self.stop()  # Never open a second embedded Chroma client while API is alive.
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--probe-store',
                   str(self.root), '--nonce', self.nonce, '--query', query]
        if document_id:
            command += ['--document-id', document_id]
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True,
                                text=True, encoding='utf-8',
                                timeout=max(40, float(self.env['KP_OLLAMA_READ_TIMEOUT_SECONDS']) + 30))
        if result.returncode:
            raise RuntimeError('isolated store inspection failed')
        lines = [line[len('STEP4_STORE='):] for line in result.stdout.splitlines() if line.startswith('STEP4_STORE=')]
        if len(lines) != 1:
            raise RuntimeError('store probe did not return one result')
        return json.loads(lines[0])


def probe_store(root, nonce, query, document_id):
    validate_owned_root(root, nonce)
    if Path(os.environ.get('KP_DATA_DIR', '')).resolve() != (root / 'data').resolve():
        raise ValueError('unexpected store location')
    from knowledge_pilot.vector_store.chroma_store import collection, search
    records = collection.get(include=['documents', 'metadatas', 'embeddings'])
    results = search(query, collection, top_k=1, document_id=document_id)
    print('STEP4_STORE=' + json.dumps({'ids': records['ids'], 'documents': records['documents'],
        'metadatas': records['metadatas'], 'results': results,
        'embedding_dimensions': len(records['embeddings'][0]) if records['ids'] else None}, ensure_ascii=True))


def require(evidence, name, condition, **details):
    evidence['checks'][name] = {'status': 'passed' if condition else 'failed', **details}
    if not condition:
        raise AssertionError('integration assertion failed: ' + name)


def check_logs(evidence, api):
    api.stop()
    text = api.log_path.read_text(encoding='utf-8', errors='replace')
    events = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
    complete = {event['request_id']: event for event in events if event.get('event') == 'request_complete'}
    ids = [item['request_id'] for item in api.records]
    matched = all(item['request_id'] in complete and
                  complete[item['request_id']]['status'] == item['actual_status'] and
                  complete[item['request_id']]['route'] == item['route'] for item in api.records)
    require(evidence, 'logs', all(value not in text for value in
            (MARKER, OLD_TEXT, NEW_TEXT, 'simulated upstream final answer'))
            and matched and len(set(ids)) == len(ids)
            and any(event.get('exception', {}).get('frames') for event in events),
            requests_correlated=len(ids), json_events=len(events))


def core_scenarios(evidence, api, fixture):
    api.start()
    require(evidence, 'health_contract', api.request('health', 'GET', '/health', 200) == {'status': 'ok'})
    require(evidence, 'empty_store', api.request('initial_list', 'GET', '/documents', 200) == [])
    doc = api.request('upload', 'POST', '/documents', 201,
                      files={'file': ('original.txt', OLD_TEXT.encode(), 'text/plain')})
    doc_id = doc['document_id']
    fixture.document_id = doc_id
    require(evidence, 'upload_contract', set(doc) == {'document_id', 'source', 'chunk_count'} and doc['chunk_count'] == 1)
    require(evidence, 'list_after_upload', api.request('list_upload', 'GET', '/documents', 200) == [doc])
    store = api.inspect_store('red', doc_id)
    require(evidence, 'store_after_upload', len(store['ids']) == 1 and store['documents'] == [OLD_TEXT]
            and store['embedding_dimensions'] == 1024
            and store['results'][0][0] == OLD_TEXT and store['results'][0][1] > 0.99)
    api.start()
    updated = api.request('update', 'PUT', '/documents/' + doc_id, 200,
                         files={'file': ('updated.txt', NEW_TEXT.encode(), 'text/plain')})
    require(evidence, 'update_contract', updated['document_id'] == doc_id and updated['source'] == 'updated.txt'
            and updated['chunk_count'] == 1 and api.request('list_updated', 'GET', '/documents', 200) == [updated])
    store = api.inspect_store('blue', doc_id)
    require(evidence, 'store_after_update', store['documents'] == [NEW_TEXT]
            and store['results'][0][0] == NEW_TEXT and store['results'][0][1] > 0.99
            and store['metadatas'][0]['document_id'] == doc_id)
    raw = api.root / 'data/raw_documents' / doc_id
    require(evidence, 'raw_files', not (raw / 'original.txt').exists()
            and (raw / 'updated.txt').read_bytes() == NEW_TEXT.encode())
    api.start()
    direct = api.request('chat_direct', 'POST', '/chat', 200, json={'query': MARKER})
    require(evidence, 'chat_contract', set(direct) == {'answer', 'trace', 'stop_reason'}
            and direct['trace'] == [] and direct['stop_reason'] == 'completed')
    fixture.mode = 'tool_loop'
    result = api.request('chat_tools', 'POST', '/chat', 200, json={'query': MARKER, 'max_steps': 3})
    trace = result['trace']
    require(evidence, 'agent_tool_loop', result['stop_reason'] == 'completed' and len(trace) == 2
            and [(item['step'], item['tool']) for item in trace] == [(1, 'calculator'), (2, 'search_knowledge_base')]
            and trace[0]['result'] == 12 and trace[1]['result'][0]['content'] == NEW_TEXT
            and all(set(item) == {'step', 'tool', 'arguments', 'result'} for item in trace))
    limited = api.request('chat_step_limit', 'POST', '/chat', 200, json={'query': MARKER, 'max_steps': 1})
    require(evidence, 'agent_step_limit', limited['stop_reason'] == 'max_steps' and len(limited['trace']) == 1)
    fixture.mode = 'direct'
    for label, filename, content in [('bad_extension', 'bad.bin', b'bad'), ('empty_file', 'empty.txt', b''),
                                      ('blank_file', 'blank.txt', b'   '), ('bad_utf8', 'bad.txt', b'\xff')]:
        api.request(label, 'POST', '/documents', 400, files={'file': (filename, content)})
    for label, payload in [('blank_query', {'query': ' '}), ('bad_steps', {'query': MARKER, 'max_steps': 0}),
                           ('private_invalid_input', {'query': {'secret': MARKER}})]:
        body = api.request(label, 'POST', '/chat', 422, json=payload)
        require(evidence, label + '_redacted', MARKER not in json.dumps(body))
    api.request('missing_file', 'POST', '/documents', 422)
    api.request('missing_delete', 'DELETE', '/documents/' + MARKER + '?token=' + MARKER, 404)
    api.request('missing_update', 'PUT', '/documents/missing', 404, files={'file': ('test.txt', b'test')})
    for mode, expected in [('http_error', 502), ('invalid_json', 502), ('schema_error', 502), ('slow', 504)]:
        fixture.mode = mode
        body = api.request(mode, 'POST', '/chat', expected, json={'query': MARKER})
        require(evidence, mode + '_safe', MARKER not in json.dumps(body))
    fixture.mode = 'schema_error'
    api.request('embedding_failure', 'POST', '/documents', 502, files={'file': ('rollback.txt', b'rollback probe')})
    fixture.mode = 'direct'
    api.stop()
    # Real filesystem fault, only inside this owned temp store; no Service mock.
    raw_root = api.root / 'data/raw_documents'
    backup = api.root / 'data/raw_documents.saved'
    raw_root.rename(backup)
    try:
        raw_root.write_bytes(b'controlled obstruction')
        api.start()
        body = api.request('internal_filesystem_error', 'POST', '/documents', 500,
                           files={'file': ('fault.txt', b'controlled fault')})
        require(evidence, 'internal_error_safe', body == {'detail': 'internal service error'})
    finally:
        api.stop()
        raw_root.unlink(missing_ok=True)
        backup.rename(raw_root)
    api.start()
    deleted = api.request('delete', 'DELETE', '/documents/' + doc_id, 200)
    require(evidence, 'delete_contract', deleted == {'document_id': doc_id, 'status': 'deleted'}
            and api.request('list_deleted', 'GET', '/documents', 200) == [])
    api.request('delete_again', 'DELETE', '/documents/' + doc_id, 404)
    store = api.inspect_store('blue', doc_id)
    require(evidence, 'store_after_delete', store['ids'] == [] and store['results'] == [] and not raw.exists())
    require(evidence, 'failed_upload_rollback', list(raw_root.iterdir()) == [])
    api.start()
    fixture.close()
    api.request('connection_failure', 'POST', '/chat', 503, json={'query': MARKER}, timeout=15)
    check_logs(evidence, api)


def run_suite(test_root: Path, evidence_root: Path, *, real_ollama=None,
              docker=None, compose_plugin=None) -> tuple[dict, Path]:
    for path in (test_root, evidence_root):
        if not path.is_absolute() or not path.is_dir():
            raise ValueError('test/evidence roots must be existing absolute directories')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    evidence = {'schema': 'kp_step4_api_v1', 'run_id': run_id, 'status': 'failed',
        'acceptance_scope': 'mandatory_local_api',
        'upstream': 'deterministic_local_http_fixture', 'requests': [], 'checks': {},
        'environment': {'python': sys.version.split()[0], 'platform': platform.platform(),
            'dependencies': {name: importlib.metadata.version(name) for name in ('fastapi', 'requests', 'chromadb', 'pydantic', 'uvicorn')}},
        'optional': {'real_ollama': {'status': 'NOT_RUN', 'reason': 'not requested'},
                     'docker': {'status': 'NOT_RUN', 'reason': 'separate bounded environment check'},
                     'native_linux': {'status': 'DEFERRED_DEBT'}},
        'cleanup': {'children_exited': False, 'temporary_data_removed': False}}
    fixture = ModelFixture()
    api = None
    owned = None
    try:
        evidence['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        evidence['git_status'] = subprocess.check_output(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=ROOT, text=True).strip()
        evidence['source_sha256'] = {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [Path(__file__).resolve(), ROOT / 'scripts/integration/model_fixture.py',
                         ROOT / 'src/knowledge_pilot/api/app.py', ROOT / 'src/knowledge_pilot/api/services.py',
                         ROOT / 'src/knowledge_pilot/llm/ollama_client.py', ROOT / 'src/knowledge_pilot/retrieval/embedding.py',
                         ROOT / 'src/knowledge_pilot/vector_store/chroma_store.py']}
        fixture.start()
        with tempfile.TemporaryDirectory(prefix='kp-step4-', dir=test_root) as folder:
            owned = Path(folder)
            (owned / '.step4-owned').write_text(run_id, encoding='utf-8')
            api = ApiProcess(owned, run_id, fixture.origin, evidence['requests'])
            try:
                core_scenarios(evidence, api, fixture)
            finally:
                api.stop()
                api.session.close()
                fixture.close()
        evidence['cleanup'] = {'children_exited': all(child.poll() is not None for child in api.children),
                                'temporary_data_removed': not owned.exists()}
        if not all(evidence['cleanup'].values()):
            raise RuntimeError('temporary resource cleanup failed')
        evidence['status'] = 'passed'
        if real_ollama:
            evidence['optional']['real_ollama'] = run_real_ollama(test_root, real_ollama, run_id)
    except Exception as error:
        evidence['error_type'] = type(error).__name__
        evidence['failure_phase'] = 'core_or_cleanup'
        evidence['cleanup'] = {'children_exited': api is None or all(child.poll() is not None for child in api.children),
                                'temporary_data_removed': owned is None or not owned.exists()}
    finally:
        fixture.close()
    if docker:
        evidence['optional']['docker'] = check_docker(docker, compose_plugin)
    evidence['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    path = evidence_root / f'step4-evidence-{run_id}.json'
    with path.open('x', encoding='utf-8') as output:
        json.dump(evidence, output, indent=2, ensure_ascii=True)
        output.write('\n')
    return evidence, path


def check_docker(docker, compose_plugin=None):
    """One bounded, non-mutating Engine/config check; never attempts host repairs."""
    result = {'status': 'BLOCKED', 'commands': [], 'container_validation': 'NOT_RUN'}
    prefix = [compose_plugin] if compose_plugin else [docker, 'compose']
    for name, command in [('engine', [docker, 'version', '--format', '{{json .Server}}']),
                          ('compose_config', prefix + ['--env-file', os.devnull, '-f', str(ROOT / 'compose.yaml'),
                                                       '-p', 'kp-step4-config-check', 'config', '--quiet'])]:
        try:
            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=15)
            result['commands'].append({'check': name, 'exit_code': completed.returncode,
                                       'stdout': completed.stdout.strip(), 'stderr': completed.stderr.strip()})
        except (OSError, subprocess.TimeoutExpired) as error:
            result['commands'].append({'check': name, 'exit_code': None, 'error_type': type(error).__name__})
    if all(item['exit_code'] == 0 for item in result['commands']):
        result.update(status='AVAILABLE_NOT_VALIDATED', reason='engine/config available; container build/test not executed by this read-only check')
    else:
        result['reason'] = 'Engine or Compose check unavailable; no Docker repair attempted'
    return result


def run_real_ollama(test_root, origin, nonce):
    result = {'status': 'NOT_RUN', 'upstream': 'real_host_ollama', 'requests': []}
    parsed = urlsplit(origin)
    if (parsed.scheme not in {'http', 'https'} or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
        result['reason'] = 'only a credential-free loopback Ollama origin is allowed'
        return result
    origin = origin.rstrip('/')
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.get(origin + '/api/tags', timeout=5)
        response.raise_for_status()
        names = {model['name'] for model in response.json()['models']}
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        result['reason'] = 'Ollama tags unavailable: ' + type(error).__name__
        return result
    finally:
        session.close()
    if not {'gemma4:e2b', 'bge-m3'}.issubset({name.removesuffix(':latest') for name in names}):
        result['reason'] = 'required existing gemma4:e2b/bge-m3 models absent; no downloads attempted'
        return result
    result.update(status='failed', models=sorted(names))
    api = None
    owned = None
    phase = 'startup'
    try:
        with tempfile.TemporaryDirectory(prefix='kp-step4-real-', dir=test_root) as folder:
            owned = Path(folder)
            real_nonce = nonce + '-real'
            (owned / '.step4-owned').write_text(real_nonce, encoding='utf-8')
            api = ApiProcess(owned, real_nonce, origin, result['requests'], real=True)
            try:
                api.start()
                phase = 'chat'
                chat = api.request('real_chat', 'POST', '/chat', 200,
                    json={'query': 'Reply with OK. Do not use tools.', 'max_steps': 2}, timeout=150)
                if not isinstance(chat.get('answer'), str) or not chat['answer'] or chat.get('stop_reason') != 'completed':
                    raise AssertionError('real chat did not complete')
                phase = 'embedding_upload'
                text = 'KnowledgePilot Step 4 real Ollama isolated retrieval probe.'
                doc = api.request('real_upload', 'POST', '/documents', 201,
                                   files={'file': ('real-probe.txt', text.encode(), 'text/plain')}, timeout=150)
                phase = 'retrieval'
                store = api.inspect_store(text, doc['document_id'])
                if (store['documents'] != [text] or store['results'][0][0] != text
                        or store['results'][0][1] < 0.99):
                    raise AssertionError('real document retrieval mismatch')
                # Direct vector metadata is read by the isolated store worker, not inferred from tags.
                result['chat_completed'] = True
                result['real_embedding_upload'] = True
                result['embedding_dimensions'] = store['embedding_dimensions']
                result['real_document_retrieval'] = True
                api.start()
                phase = 'delete'
                api.request('real_delete', 'DELETE', '/documents/' + doc['document_id'], 200)
            finally:
                api.stop()
                api.session.close()
        result['cleanup'] = {'children_exited': all(child.poll() is not None for child in api.children),
                             'temporary_data_removed': not owned.exists()}
        if not all(result['cleanup'].values()):
            raise RuntimeError('real test cleanup failed')
        result['status'] = 'passed'
    except Exception as error:
        result.update(error_type=type(error).__name__, failure_phase=phase,
                      cleanup={'children_exited': api is None or all(child.poll() is not None for child in api.children),
                               'temporary_data_removed': owned is None or not owned.exists()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-root', type=Path)
    parser.add_argument('--evidence-root', type=Path, default=ROOT / 'docs/engineering')
    parser.add_argument('--real-ollama')
    parser.add_argument('--docker', help='Optional bounded Docker environment check')
    parser.add_argument('--compose-plugin')
    parser.add_argument('--probe-store', type=Path)
    parser.add_argument('--nonce')
    parser.add_argument('--query', default='blue')
    parser.add_argument('--document-id')
    args = parser.parse_args()
    if args.probe_store:
        probe_store(args.probe_store, args.nonce, args.query, args.document_id)
        return 0
    if args.test_root is None:
        parser.error('--test-root is required')
    evidence, path = run_suite(args.test_root, args.evidence_root, real_ollama=args.real_ollama,
                               docker=args.docker, compose_plugin=args.compose_plugin)
    print(json.dumps({'status': evidence['status'], 'requests': len(evidence['requests']),
                      'checks': len(evidence['checks']), 'evidence': str(path)}))
    return int(evidence['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
