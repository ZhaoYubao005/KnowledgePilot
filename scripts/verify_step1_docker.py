"""Explicit Docker acceptance with a fresh store; never mounts the main checkout.

Build the image first. Uses existing Docker/Compose and host Ollama, preserves its
new test data and writes a JSON evidence file. Removes only its own containers.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--compose-plugin', help='Optional full docker-compose executable path')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    data_root = root / 'data' / ('docker-step1-' + run_id)
    data_root.mkdir(parents=True)
    project = 'kp-step1-' + run_id.lower()
    evidence_path = root / 'docs' / 'deployment' / ('docker-evidence-' + run_id + '.json')
    evidence = {'run_id': run_id, 'scope': 'real Docker, host Ollama, fresh Chroma',
                'project': project, 'data_root': str(data_root), 'checks': {}, 'commands': []}
    env = {k: v for k, v in os.environ.items() if not k.startswith('KP_')}
    env['PATH'] = str(Path(args.docker).parent) + os.pathsep + env.get('PATH', '')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env.update(KP_HOST_DATA_DIR=data_root.as_posix(), KP_API_PORT=str(port),
               KP_OLLAMA_BASE_URL='http://host.docker.internal:11434',
               KP_CHAT_MODEL='gemma4:e2b', KP_EMBED_MODEL='bge-m3')
    compose = ([args.compose_plugin] if args.compose_plugin else [args.docker, 'compose'])
    compose += ['-p', project, '-f', str(root / 'compose.yaml')]
    base = f'http://127.0.0.1:{port}'
    evidence['api_base'] = base

    def run(command, timeout=120):
        result = subprocess.run(command, cwd=root, env=env, text=True,
                                encoding='utf-8', errors='replace', capture_output=True, timeout=timeout)
        evidence['commands'].append({'argv': command, 'exit_code': result.returncode,
                                     'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()})
        if result.returncode:
            raise RuntimeError(f'Command failed ({result.returncode}): {command}\n{result.stderr[-2000:]}')
        return result.stdout.strip()

    def check(name, value):
        evidence['checks'][name] = value
        print('PASS ' + name + ': ' + json.dumps(value, ensure_ascii=True), flush=True)

    def health():
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(base + '/health', timeout=2) as response:
                    assert response.status == 200
                    assert json.load(response) == {'status': 'ok'}
                    return
            except (OSError, AssertionError):
                time.sleep(0.5)
        raise RuntimeError('Container /health did not become ready in 60 seconds')

    def api(path, method='GET', body=None, content_type=None):
        headers = {'Content-Type': content_type} if content_type else {}
        request = urllib.request.Request(base + path, data=body, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.load(response)

    def container_python(code):
        return run(compose + ['exec', '-T', 'api', 'python', '-c', code])

    try:
        check('compose_config', run(compose + ['config', '--quiet']) or 'exit 0')
        check('image', json.loads(run([args.docker, 'image', 'inspect',
                                      'knowledgepilot:v1.4-step1', '--format', '{{json .}}']))['Id'])
        run(compose + ['up', '-d', '--no-build', 'api'])
        health()
        first_id = run(compose + ['ps', '-q', 'api'])
        check('health', {'status': 200, 'container_id': first_id})
        config = json.loads(container_python(
            'import json; from knowledge_pilot import config as c; '
            'print(json.dumps([c.OLLAMA_URL,c.EMBEDDING_URL,c.MODEL_NAME,c.EMBEDDING_MODEL,str(c.DATA_DIR)]))'))
        assert config == ['http://host.docker.internal:11434/api/chat',
                          'http://host.docker.internal:11434/api/embed', 'gemma4:e2b', 'bge-m3', '/app/data']
        check('container_config', config)
        check('container_ollama_tags', json.loads(container_python(
            'import json,urllib.request; '
            'r=urllib.request.urlopen("http://host.docker.internal:11434/api/tags",timeout=10); '
            'print(json.dumps({"status":r.status,"models":[m["name"] for m in json.load(r)["models"]]}))')))
        embedding = json.loads(container_python(
            'import json,urllib.request; '
            'q=urllib.request.Request("http://host.docker.internal:11434/api/embed",'
            'data=json.dumps({"model":"bge-m3","input":"Step 1 Docker probe"}).encode(),'
            'headers={"Content-Type":"application/json"}); '
            'r=urllib.request.urlopen(q,timeout=120); d=json.load(r); '
            'print(json.dumps({"status":r.status,"dimensions":len(d["embeddings"][0])}))'))
        assert embedding['status'] == 200 and embedding['dimensions'] > 0
        check('container_real_embedding', embedding)
        boundary = 'kp-' + uuid.uuid4().hex
        content = b'KnowledgePilot Docker persistence acceptance document.'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="docker-probe.txt"\r\n'
                'Content-Type: text/plain\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        status, document = api('/documents', 'POST', body, 'multipart/form-data; boundary=' + boundary)
        assert status == 201 and document['chunk_count'] == 1
        document_id = document['document_id']
        raw_file = data_root / 'raw_documents' / document_id / 'docker-probe.txt'
        assert raw_file.read_bytes() == content
        assert (data_root / 'vector_store' / 'chroma.sqlite3').is_file()
        check('upload_and_host_files', document)
        mounts = json.loads(run([args.docker, 'inspect', first_id, '--format', '{{json .Mounts}}']))
        mount = next(m for m in mounts if m['Destination'] == '/app/data')
        assert mount['Type'] == 'bind' and mount['RW']
        check('mount', mount)
        run(compose + ['stop', 'api'])
        run(compose + ['rm', '-f', 'api'])
        run(compose + ['up', '-d', '--no-build', 'api'])
        health()
        second_id = run(compose + ['ps', '-q', 'api'])
        assert first_id != second_id
        status, documents = api('/documents')
        assert status == 200 and document in documents
        assert raw_file.read_bytes() == content
        persisted = json.loads(container_python(
            'import json; from knowledge_pilot.vector_store.chroma_store import collection; '
            'd=collection.get(include=["documents"]); '
            'print(json.dumps({"count":len(d["ids"]),"documents":d["documents"]}))'))
        assert persisted['count'] == 1 and persisted['documents'] == [content.decode()]
        check('delete_recreate_persistence', {'old_container': first_id, 'new_container': second_id,
                                              'document': document, 'store': persisted})
        evidence['status'] = 'passed'
    except BaseException as error:
        evidence['status'] = 'failed'
        evidence['error'] = f'{type(error).__name__}: {error}'
        try:
            run(compose + ['logs', '--tail', '80', 'api'])
        except Exception:
            pass
        raise
    finally:
        try:
            run(compose + ['down'])
            evidence['cleanup'] = 'own project containers/network removed; fresh test data retained'
        finally:
            evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            print('Evidence: ' + str(evidence_path), flush=True)


if __name__ == '__main__':
    main()
