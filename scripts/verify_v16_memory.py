"""Actual V1.6 HTTP/SQLite/Chroma acceptance with isolated, owned temporary data."""
import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid

import requests

from integration.model_fixture import MARKER
from verify_step4_api import ApiProcess, ROOT


PRIVATE = 'V16_PRIVATE_HISTORY_NEVER_LOG'
CODE = 'CEDAR731'
REMEMBER = 'Remember: my project code is ' + CODE + '. Reply briefly with ACK. ' + PRIVATE
RECALL = 'What project code did I mention? Reply exactly the code, or NONE if unknown.'
CURRENT = 'Reply exactly CURRENT_QUERY_SURVIVES'
DOCUMENT = 'The uploaded project status is GREEN123. ' + PRIVATE


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def conversational_messages(messages):
    """Workflow execution context is a separate current-turn data envelope."""
    return [message for message in messages
            if message.get('role') in {'user', 'assistant'}
            and not str(message.get('content', '')).startswith('Execution context: ')]


def snapshot_diagnostics(snapshot):
    """Fixed metadata distinguishes retained memory from model recall behavior."""
    turns = snapshot['turns']
    return {'revision': snapshot['revision'], 'stored_turns': len(turns),
        'history_chars': sum(len(turn['query']) + len(turn['answer']) for turn in turns),
        'source_note_retained': any(turn['query'] == REMEMBER for turn in turns),
        'query_fact_present': any(CODE in turn['query'] for turn in turns),
        'answer_fact_present': any(CODE in turn['answer'] for turn in turns),
        'history_sha256': digest(turns),
        'turns': [{'query_chars': len(turn['query']), 'answer_chars': len(turn['answer']),
                   'query_fact_present': CODE in turn['query'],
                   'answer_fact_present': CODE in turn['answer'],
                   'query_sha256': digest(turn['query']),
                   'answer_sha256': digest(turn['answer'])} for turn in turns]}


def answer_diagnostics(result):
    return {'completed': result.get('status') == 'completed'
                         or result.get('stop_reason') == 'completed',
            'answer_chars': len(result.get('answer', '')),
            'answer_fact_present': CODE in result.get('answer', ''),
            'answer_sha256': digest(result.get('answer', ''))}


class MemoryFixture:
    """A stateless answer function of each real received HTTP message payload.

    It never consults CODE or a session cache. A recalled fact must occur in the
    supplied user history; a retrieved fact must occur in supplied evidence.
    """

    def __init__(self):
        self.calls = []
        self.messages = []
        self.embed_calls = 0
        self.slow_embeddings = 0
        self.lock = threading.Lock()
        self.thread = None
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/embed':
                    with owner.lock:
                        owner.embed_calls += 1
                        slow = owner.slow_embeddings > 0
                        owner.slow_embeddings = max(0, owner.slow_embeddings - 1)
                        owner.calls.append({'path': self.path, 'input_sha256': digest(payload.get('input')),
                                            'delayed_past_timeout': slow})
                    if slow:
                        time.sleep(0.65)  # API read deadline is 0.2 seconds.
                    result = {'embeddings': [[1.0] + [0.0] * 1023]}
                else:
                    messages = payload.get('messages', [])
                    conversation = conversational_messages(messages)
                    users = [item for item in conversation if item['role'] == 'user']
                    current = users[-1]['content'] if users else ''
                    history = users[:-1]
                    match = next((match for message in reversed(history)
                                  if (match := re.search(r'my project code is ([A-Z0-9]+)',
                                                       message['content']))), None)
                    if 'format' in payload:
                        answer = json.dumps({'route': 'direct'})
                        derivation = 'explicit_direct_decision'
                    elif 'What project code' in current:
                        answer = match.group(1) if match else 'NONE'
                        derivation = 'received_user_history' if match else 'received_history_unknown'
                    elif current.startswith('Reply exactly '):
                        answer = current.removeprefix('Reply exactly ')
                        derivation = 'received_current_query'
                    else:
                        context = [message['content'] for message in messages
                                   if str(message.get('content', '')).startswith('Execution context: ')]
                        evidence_match = re.search(r'project status is ([A-Z0-9]+)', '\n'.join(context))
                        answer = evidence_match.group(1) if evidence_match else 'ACK'
                        derivation = 'received_evidence' if evidence_match else 'acknowledgement'
                    with owner.lock:
                        owner.messages.append(messages)
                        owner.calls.append({'path': self.path, 'structured': 'format' in payload,
                            'message_roles': [item.get('role') for item in messages],
                            'message_count': len(messages), 'history_user_count': len(history),
                            'current_query_sha256': digest(current), 'messages_sha256': digest(messages),
                            'answer_derivation': derivation, 'history_fact_present': match is not None})
                    result = {'message': {'role': 'assistant', 'content': answer}}
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
        self.server.daemon_threads = False
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def arm_timeouts(self, count):
        with self.lock:
            self.slow_embeddings = count
            return self.embed_calls

    def close(self):
        if not self.closed:
            if self.thread is not None:
                self.server.shutdown()
                self.thread.join(timeout=5)
            self.server.server_close()
            self.closed = True


def real_preflight(origin):
    parsed = urlsplit(origin)
    if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}
            or parsed.username or parsed.password or parsed.path not in {'', '/'}
            or parsed.query or parsed.fragment):
        raise ValueError('real Ollama must be a credential-free loopback HTTP origin')
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(origin.rstrip('/') + '/api/tags', timeout=5)
        response.raise_for_status()
        names = {item['name'].removesuffix(':latest') for item in response.json()['models']}
    if not {'gemma4:e2b', 'bge-m3'} <= names:
        raise RuntimeError('required existing models absent; no downloads attempted')
    return {'chat_model': 'gemma4:e2b', 'embedding_model': 'bge-m3',
            'models_present': True, 'downloads': False}


def provenance():
    def git(*arguments):
        result = subprocess.run(['git', *arguments], cwd=ROOT, text=True,
                                capture_output=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    files = ['scripts/verify_v16_memory.py', 'scripts/verify_step4_api.py',
             'src/knowledge_pilot/api/app.py', 'src/knowledge_pilot/api/sessions.py',
             'src/knowledge_pilot/memory/store.py', 'src/knowledge_pilot/memory/service.py',
             'src/knowledge_pilot/memory/context.py', 'src/knowledge_pilot/tools/recovery.py',
             'src/knowledge_pilot/workflow/graph.py', 'src/knowledge_pilot/api/reliability.py']
    return {'source_head': git('rev-parse', 'HEAD'),
            'source_dirty': bool(git('status', '--porcelain')),
            'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in files},
            'versions': {name: importlib.metadata.version(name) for name in
                         ['langgraph', 'pydantic', 'fastapi', 'chromadb', 'requests']}}


def verify(evidence_path: Path, real_origin: str | None = None):
    evidence = {'schema': 'kp_v16_memory_http_v1', 'status': 'failed',
        'upstream': 'real_host_ollama' if real_origin else 'deterministic_local_http_fixture',
        'acceptance_scope': ('actual_http_sqlite_chroma_real_host_ollama' if real_origin else
                             'actual_http_sqlite_chroma_simulated_model'),
        'time_utc': datetime.now(timezone.utc).isoformat(), 'requests': [], 'checks': {},
        'recovery': {}, 'upstream_requests': [], 'memory_stages': {}}
    fixture = None if real_origin else MemoryFixture()
    api = None
    owned = None
    phase = 'provenance'

    def require(name, condition, **details):
        nonlocal phase
        phase = name
        evidence['checks'][name] = {'status': 'passed' if condition else 'failed', **details}
        if not condition:
            raise AssertionError('acceptance assertion failed')

    try:
        evidence['provenance'] = provenance()
        if real_origin:
            phase = 'real_ollama_preflight'
            evidence['real_models'] = real_preflight(real_origin)
        with tempfile.TemporaryDirectory(prefix='kp-v16-memory-') as folder:
            owned = Path(folder)
            nonce = uuid.uuid4().hex
            (owned / '.step4-owned').write_text(nonce, encoding='utf-8')
            if fixture:
                fixture.start()
            api = ApiProcess(owned, nonce, real_origin or fixture.origin,
                             evidence['requests'], real=bool(real_origin))
            api.env.update(KP_SESSION_MAX_TURNS='2', KP_SESSION_MAX_CHARS='512',
                           KP_TOOL_MAX_ATTEMPTS='2')
            evidence['isolation'] = {'store': 'owned_temporary_data_directory',
                'database': 'data/sessions.sqlite3', 'max_turns': 2, 'max_chars': 512,
                'tool_max_attempts': 2, 'normal_user_store_accessed': False}

            def send(label, method, path, expected=200, **kwargs):
                nonlocal phase
                phase = label
                try:
                    return api.request(label, method, path, expected,
                                       timeout=300 if real_origin else 20, **kwargs)
                finally:
                    if evidence['requests'] and path.startswith('/sessions/'):
                        evidence['requests'][-1]['route'] = '/sessions/{session_id}'

            def chat(label, query, session_id=None, *, legacy=False, expected=200, **kwargs):
                payload = {'query': query}
                if session_id is not None:
                    payload['session_id'] = session_id
                if not legacy:
                    payload['route'] = 'direct'
                payload.update(kwargs)
                return send(label, 'POST', '/chat' if legacy else '/workflow/chat',
                            expected, json=payload)

            try:
                phase = 'api_startup'
                api.start()
                first = send('session_create_a', 'POST', '/sessions', 201)
                second = send('session_create_b', 'POST', '/sessions', 201)
                sid, other = first['session_id'], second['session_id']
                require('session_create_read', sid != other and len(sid) == len(other) == 43
                    and first['revision'] == second['revision'] == 0
                    and first['turns'] == second['turns'] == []
                    and send('session_initial_read', 'GET', '/sessions/' + sid) == first)

                remembered = chat('workflow_remember', REMEMBER, sid)
                note_snapshot = send('session_after_remember', 'GET', '/sessions/' + sid)
                evidence['memory_stages']['workflow_remember'] = {
                    'response': answer_diagnostics(remembered),
                    'submitted_pair_chars': len(REMEMBER) + len(remembered['answer']),
                    'store': snapshot_diagnostics(note_snapshot)}
                recall = chat('workflow_recall', RECALL, sid)
                evidence['memory_stages']['workflow_recall'] = answer_diagnostics(recall)
                require('workflow_multiturn', CODE in recall['answer'] and recall['status'] == 'completed',
                        **answer_diagnostics(recall))
                isolated = chat('workflow_other_session', RECALL, other)
                require('session_isolation', CODE not in isolated['answer'],
                        **answer_diagnostics(isolated))
                snapshot = send('session_before_restart', 'GET', '/sessions/' + sid)
                evidence['memory_stages']['before_restart'] = snapshot_diagnostics(snapshot)
                database = owned / 'data/sessions.sqlite3'
                require('sqlite_persistence_file', database.is_file()
                        and database.read_bytes().startswith(b'SQLite format 3\x00'))
                api.stop()
                api.start()
                persisted = send('session_after_restart', 'GET', '/sessions/' + sid)
                evidence['memory_stages']['after_restart'] = snapshot_diagnostics(persisted)
                require('restart_persistence', persisted == snapshot,
                        snapshot_equal=persisted == snapshot,
                        source_note_retained=any(turn['query'] == REMEMBER for turn in persisted['turns']),
                        history_chars=evidence['memory_stages']['after_restart']['history_chars'],
                        api_processes_started=len(api.children), revision=snapshot['revision'])
                after_restart = chat('workflow_recall_after_restart', RECALL, sid)
                evidence['memory_stages']['restart_recall'] = answer_diagnostics(after_restart)
                require('restart_recall', after_restart['status'] == 'completed'
                        and CODE in after_restart['answer'], **answer_diagnostics(after_restart),
                        source_note_retained=evidence['memory_stages']['after_restart']['source_note_retained'],
                        query_fact_present=evidence['memory_stages']['after_restart']['query_fact_present'],
                        answer_fact_in_history=evidence['memory_stages']['after_restart']['answer_fact_present'])

                before_clear = send('session_before_clear', 'GET', '/sessions/' + sid)
                cleared = send('session_clear', 'DELETE', '/sessions/' + sid)
                forgotten = chat('workflow_after_clear', RECALL, sid)
                evidence['memory_stages']['after_clear'] = {
                    'store': snapshot_diagnostics(cleared), 'response': answer_diagnostics(forgotten)}
                require('clear_history', cleared['turns'] == []
                        and cleared['revision'] == before_clear['revision'] + 1
                        and CODE not in forgotten['answer'])
                for index in range(3):
                    chat('workflow_bound_fill_' + str(index), 'Reply briefly with ACK ' + str(index), sid)
                current = chat('workflow_current_query', CURRENT, sid)
                bounded = send('session_bounded_read', 'GET', '/sessions/' + sid)
                current_preserved = ('CURRENT_QUERY_SURVIVES' in current['answer']
                    and len(bounded['turns']) == 2 and bounded['turns'][-1]['query'] == CURRENT)
                if fixture:
                    received = conversational_messages(fixture.messages[-1])
                    current_preserved = (current_preserved and received[-1]['role'] == 'user'
                                         and received[-1]['content'] == CURRENT)
                require('bounded_history_current_query', current_preserved,
                        stored_turns=len(bounded['turns']), answer_chars=len(current['answer']),
                        current_marker_present='CURRENT_QUERY_SURVIVES' in current['answer'],
                        current_query_stored=bool(bounded['turns'])
                            and bounded['turns'][-1]['query'] == CURRENT)
                evidence['memory_stages']['bounded_current_query'] = snapshot_diagnostics(bounded)

                send('legacy_session_clear', 'DELETE', '/sessions/' + other)
                legacy_remembered = chat('chat_remember', REMEMBER, other, legacy=True)
                evidence['memory_stages']['chat_remember'] = answer_diagnostics(legacy_remembered)
                old_recall = chat('chat_recall', RECALL, other, legacy=True)
                evidence['memory_stages']['chat_recall'] = answer_diagnostics(old_recall)
                legacy_order = True
                if fixture:
                    legacy_order = fixture.messages[-1][-1] == {'role': 'user', 'content': RECALL}
                require('chat_multiturn', CODE in old_recall['answer']
                        and old_recall['stop_reason'] == 'completed' and legacy_order,
                        **answer_diagnostics(old_recall), current_query_last=legacy_order)
                no_session_workflow = chat('workflow_without_session', RECALL)
                no_session_chat = chat('chat_without_session', RECALL, legacy=True)
                require('no_session_compatibility', CODE not in no_session_workflow['answer']
                        and CODE not in no_session_chat['answer']
                        and set(no_session_chat) == {'answer', 'trace', 'stop_reason'}
                        and 'diagnostics' not in no_session_workflow)

                failed_calculator = chat('calculator_deterministic_failure', 'Divide one by zero.',
                    route='tool', tool={'name': 'calculator',
                        'arguments': {'a': 1, 'b': 0, 'operation': 'divide'}})
                require('calculator_no_retry', failed_calculator['status'] == 'failed'
                        and len(failed_calculator['diagnostics']) == 1
                        and failed_calculator['diagnostics'][0]['retryable'] is False)
                doc = send('upload_retrieval_document', 'POST', '/documents', 201,
                    files={'file': ('v16-memory-probe.txt', DOCUMENT.encode(), 'text/plain')})
                start_count = fixture.arm_timeouts(1) if fixture else None
                rag = chat('retrieval_after_one_timeout' if fixture else 'real_retrieval',
                           'What is the uploaded project status?', route='rag',
                           document_id=doc['document_id'], top_k=1)
                require('retrieval_evidence', rag['status'] == 'completed'
                    and rag['evidence'] == [{'content': DOCUMENT, 'source': 'v16-memory-probe.txt'}]
                    and 'GREEN123' in rag['answer'])
                if fixture:
                    require('retrieval_recovered', fixture.embed_calls - start_count == 2
                        and [event['status'] for event in rag['diagnostics']] == ['failed', 'succeeded']
                        and rag['diagnostics'][0]['category'] == 'model_timeout')
                    evidence['recovery']['recovered'] = {'embedding_http_calls': fixture.embed_calls - start_count,
                        'diagnostics': rag['diagnostics'], 'actual_evidence_count': len(rag['evidence'])}
                    before_failure = send('session_before_failed_turn', 'GET', '/sessions/' + sid)
                    start_count = fixture.arm_timeouts(2)
                    exhausted = chat('retrieval_timeout_exhausted', 'Read the uploaded project status.',
                        sid, route='rag', document_id=doc['document_id'], expected=504)
                    require('retrieval_exhausted', fixture.embed_calls - start_count == 2
                        and exhausted['detail'] == 'embedding service timed out'
                        and len(exhausted['diagnostics']) == 2
                        and all(event['status'] == 'failed' and event['category'] == 'model_timeout'
                                for event in exhausted['diagnostics']))
                    evidence['recovery']['exhausted'] = {'embedding_http_calls': fixture.embed_calls - start_count,
                        'actual_status': 504, 'diagnostics': exhausted['diagnostics']}
                    require('failed_turn_not_saved', before_failure ==
                            send('session_after_failed_turn', 'GET', '/sessions/' + sid))
                else:
                    evidence['recovery']['transient_fault_injection'] = {
                        'status': 'NOT_RUN', 'reason': 'real model calls have no injected faults'}
                send('delete_retrieval_document', 'DELETE', '/documents/' + doc['document_id'])
            finally:
                api.stop()
                api.session.close()

            logs = api.log_path.read_text(encoding='utf-8', errors='replace')
            require('log_privacy', all(value not in logs for value in
                    (PRIVATE, CODE, DOCUMENT, REMEMBER, RECALL, MARKER, sid, other)))
            events = [json.loads(line) for line in logs.splitlines() if line.startswith('{')]
            completed = {item['request_id']: item for item in events
                         if item.get('event') == 'request_complete'}
            require('request_log_correlation', all(item['request_id'] in completed
                and completed[item['request_id']]['status'] == item['actual_status']
                and completed[item['request_id']]['route'] == item['route']
                for item in evidence['requests']), requests_correlated=len(evidence['requests']))
        evidence['status'] = 'passed'
    except Exception as error:
        evidence.update(error_type=type(error).__name__, failure_phase=phase)
    finally:
        if fixture:
            fixture.close()
            evidence['upstream_requests'] = fixture.calls
            evidence['model_fixture'] = {'answers_derived_from_received_messages': True,
                'history_recall_observed': any(item.get('answer_derivation') == 'received_user_history'
                                               for item in fixture.calls),
                'empty_history_unknown_observed': any(item.get('answer_derivation') == 'received_history_unknown'
                                                      for item in fixture.calls)}
        evidence['cleanup'] = {'temporary_data_removed': owned is None or not owned.exists(),
            'children_exited': api is None or all(child.poll() is not None for child in api.children),
            'fixture_stopped': fixture is None or fixture.thread is None or not fixture.thread.is_alive()}
        if not all(evidence['cleanup'].values()):
            evidence['status'] = 'failed'
            evidence['failure_phase'] = 'cleanup'
        evidence['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--real-ollama', help='Explicit loopback host Ollama; no downloads or repairs')
    arguments = parser.parse_args()
    evidence = verify(arguments.evidence.resolve(), arguments.real_ollama)
    print(json.dumps({'status': evidence['status'], 'checks': len(evidence['checks']),
                      'requests': len(evidence['requests']), 'upstream': evidence['upstream'],
                      'failure_phase': evidence.get('failure_phase')}))
    return int(evidence['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
