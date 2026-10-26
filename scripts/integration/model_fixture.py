"""Deterministic simulated Ollama HTTP protocol; never presented as a real model."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time

MARKER = 'STEP4_SYNTHETIC_PRIVATE_NEVER_LOG'
OLD_TEXT = 'STEP4_OLD red orchard synthetic document.'
NEW_TEXT = 'STEP4_NEW blue harbor synthetic document.'


class ModelFixture:
    def __init__(self):
        self.mode = 'direct'
        self.document_id = None
        self.thread = None
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                mode = owner.mode
                if mode == 'slow':
                    time.sleep(0.6)
                status = 500 if mode == 'http_error' else 200
                if mode == 'invalid_json':
                    body = MARKER.encode()
                elif mode == 'schema_error':
                    body = json.dumps({'private': MARKER}).encode()
                elif self.path == '/api/embed':
                    text = str(payload['input']).lower()
                    index = 1 if 'blue' in text else 0
                    vector = [0.0] * 1024
                    vector[index] = 1.0
                    body = json.dumps({'embeddings': [vector]}).encode()
                else:
                    observations = [m for m in payload['messages'] if m.get('role') == 'tool']
                    if mode == 'tool_loop' and len(observations) < 2:
                        function = ({'name': 'calculator', 'arguments': {'a': 7, 'b': 5, 'operation': 'add'}}
                                    if not observations else {'name': 'search_knowledge_base',
                                        'arguments': {'query': 'blue', 'top_k': 1, 'document_id': owner.document_id}})
                        message = {'role': 'assistant', 'content': '', 'tool_calls': [{'function': function}]}
                    else:
                        message = {'role': 'assistant', 'content': 'simulated upstream final answer'}
                    body = json.dumps({'message': message}).encode()
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = False  # server_close joins bounded fixture handlers.
        self.origin = f'http://127.0.0.1:{self.server.server_port}'

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        if not self.closed:
            self.closed = True
            if self.thread is not None:
                self.server.shutdown()
                self.thread.join(timeout=5)
            self.server.server_close()
