"""Fresh-store Docker acceptance. Native Linux PASS is distinct from Desktop PASS.

No model downloads, daemon changes, old-store migration or host data removal.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

from preflight import validate_data_dir, validate_ollama_origin

ROOT = Path(__file__).resolve().parents[2]


def create_run_dir(root, run_id):
    root = Path(root)
    if not root.is_absolute() or not root.is_dir():
        raise ValueError('test root must be an existing absolute directory')
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{6}', run_id):
        raise ValueError('invalid generated run id')
    result = root.resolve() / ('step2-' + run_id)
    result.mkdir(mode=0o770, exist_ok=False)
    if os.name == 'posix':
        # Only the new empty run directory. A setgid test-root can supply GID 10001.
        result.chmod(0o770)
    return result


def compose_prefix(docker, compose_args, project, compose_file):
    if not re.fullmatch(r'kp-step2-[a-z0-9-]+', project):
        raise ValueError('acceptance requires a unique kp-step2- project')
    return [docker, *compose_args, '--env-file', os.devnull,
            '-f', str(compose_file), '-p', project]


def native_linux(host_platform, engine):
    identity = (str(engine.get('OperatingSystem', '')) + ' ' +
                str(engine.get('KernelVersion', ''))).lower()
    return (host_platform == 'Linux' and engine.get('OSType', 'linux') == 'linux'
            and bool(engine.get('OperatingSystem'))
            and not any(marker in identity for marker in ('desktop', 'microsoft', 'wsl', 'docker-in-docker')))


def host_probe(path):
    errors = validate_data_dir(path)
    if errors:
        raise RuntimeError('; '.join(errors))
    return {'current_uid': os.getuid() if hasattr(os, 'getuid') else None,
            'scope': 'host only', 'writable': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-root', type=Path, required=True)
    parser.add_argument('--ollama-url', required=True)
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--compose-plugin', help='Direct Compose executable when not found as a CLI plugin')
    parser.add_argument('--chat-model', default='gemma4:e2b')
    parser.add_argument('--embed-model', default='bge-m3')
    parser.add_argument('--dimensions', type=int, default=1024)
    parser.add_argument('--evidence-root', type=Path, default=ROOT / 'docs/deployment')
    parser.add_argument('--require-native-linux', action='store_true')
    args = parser.parse_args()
    errors = validate_data_dir(args.test_root) + validate_ollama_origin(args.ollama_url)
    if not args.evidence_root.is_absolute() or not args.evidence_root.is_dir():
        errors.append('evidence root must be an existing absolute directory')
    if errors:
        parser.error('; '.join(errors))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
    data_root = create_run_dir(args.test_root, run_id)
    project = 'kp-step2-' + run_id.lower()
    evidence_path = args.evidence_root / f'linux-evidence-{run_id}.json'
    evidence = {'schema': 'kp_linux_runtime_v1', 'run_id': run_id,
                'started_at_utc': datetime.now(timezone.utc).isoformat(),
                'host_platform': platform.system(), 'project': project,
                'data_root': str(data_root), 'checks': {}, 'commands': [],
                'models': {'chat': args.chat_model, 'embedding': args.embed_model,
                           'expected_dimensions': args.dimensions},
                'status': 'failed', 'native_linux_acceptance': 'BLOCKED_NOT_RUN'}
    data_stat = data_root.stat()
    evidence['data_stat'] = {'uid': data_stat.st_uid, 'gid': data_stat.st_gid,
                             'mode': oct(data_stat.st_mode & 0o7777)}
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith('KP_')}
    env['PATH'] = str(Path(args.docker).parent) + os.pathsep + env.get('PATH', '')
    env.update(KP_HOST_DATA_DIR=data_root.as_posix(), KP_API_PORT=str(port),
               KP_OLLAMA_BASE_URL=args.ollama_url.rstrip('/'), KP_CHAT_MODEL=args.chat_model,
               KP_EMBED_MODEL=args.embed_model)
    prefix = ([args.compose_plugin] if args.compose_plugin else [args.docker, 'compose'])
    compose = compose_prefix(prefix[0], prefix[1:], project, ROOT / 'compose.yaml')
    base = f'http://127.0.0.1:{port}'
    evidence['api_base'] = base
    resources_attempted = False

    def command(argv, timeout=120):
        record = {'argv': argv}
        evidence['commands'].append(record)
        try:
            result = subprocess.run(argv, cwd=ROOT, env=env, text=True, encoding='utf-8',
                                    errors='replace', capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            record.update(exit_code=None, error=type(error).__name__)
            for field in ('stdout', 'stderr'):
                partial = getattr(error, field, None)
                if partial is not None:
                    record[field] = partial.decode('utf-8', errors='replace') if isinstance(partial, bytes) else partial
            raise
        record.update(exit_code=result.returncode, stdout=result.stdout.strip(), stderr=result.stderr.strip())
        if result.returncode:
            raise RuntimeError(f'Command exit {result.returncode}: {result.stderr[-1500:]}')
        return result.stdout.strip()

    def check(name, value):
        evidence['checks'][name] = value
        print('PASS ' + name + ': ' + json.dumps(value, ensure_ascii=True), flush=True)

    def container_python(code):
        return json.loads(command(compose + ['exec', '-T', 'api', 'python', '-c', code]))

    def api(path, method='GET', data=None, content_type=None, timeout=120):
        request = urllib.request.Request(base + path, data=data, method=method,
                                         headers={'Content-Type': content_type} if content_type else {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.load(response)

    def health():
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                status, body = api('/health', timeout=2)
                if status == 200 and body == {'status': 'ok'}:
                    return
            except (OSError, ValueError):
                pass
            time.sleep(0.5)
        raise RuntimeError('container health startup deadline exceeded')

    try:
        evidence['git_commit'] = command(['git', 'rev-parse', 'HEAD'])
        evidence['git_status'] = command(['git', 'status', '--porcelain=v1', '--untracked-files=all'])
        evidence['source_sha256'] = {
            str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT / 'compose.yaml', ROOT / 'Dockerfile', *sorted((ROOT / 'scripts/linux').glob('*.*'))]
            if path.is_file()}
        engine = json.loads(command([args.docker, 'info', '--format',
            '{"OperatingSystem":{{json .OperatingSystem}},"OSType":{{json .OSType}},'
            '"KernelVersion":{{json .KernelVersion}},"ServerVersion":{{json .ServerVersion}}}']))
        evidence['engine'] = engine
        evidence['native_linux_environment'] = native_linux(platform.system(), engine)
        evidence['docker_version'] = command([args.docker, 'version', '--format', '{{.Client.Version}}/{{.Server.Version}}'])
        evidence['compose_version'] = command(prefix + ['version', '--short'])
        if args.require_native_linux and not evidence['native_linux_environment']:
            raise RuntimeError('native Linux required; Desktop/Windows/WSL cannot satisfy this acceptance')
        check('host_data_probe', host_probe(data_root))
        check('compose_config', command(compose + ['config', '--quiet']) or 'exit 0')
        config = json.loads(command(compose + ['config', '--format', 'json']))
        image_tag = config['services']['api']['image']
        image = json.loads(command([args.docker, 'image', 'inspect', image_tag, '--format',
            '{"id":{{json .Id}},"user":{{json .Config.User}},"cmd":{{json .Config.Cmd}}}']))
        check('image', image)
        resources_attempted = True
        probe_code = '''import os,pathlib,tempfile,json
if os.getuid()!=10001: raise RuntimeError('UID is not 10001')
fd,name=tempfile.mkstemp(prefix='.kp-uid-probe-',dir='/app/data')
p=pathlib.Path(name)
try:
    with os.fdopen(fd,'wb') as f: f.write(b'uid10001')
    if p.read_bytes()!=b'uid10001': raise RuntimeError('probe mismatch')
finally: p.unlink(missing_ok=True)
print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),'write_read_delete':True}))'''
        check('container_uid_probe', json.loads(command(compose + ['run', '--rm', '--no-deps', '-T',
              '--user', '10001:10001', '--entrypoint', 'python', 'api', '-c', probe_code])))
        command(compose + ['up', '-d', '--no-build', 'api'])
        health()
        first_id = command(compose + ['ps', '-q', 'api'])
        check('health', {'status': 200, 'container': first_id})
        identity = container_python('import os,json; print(json.dumps({"uid":os.getuid(),"gid":os.getgid()}))')
        if identity['uid'] != 10001:
            raise RuntimeError('actual service UID is not 10001')
        check('service_identity', identity)
        ollama = container_python('import json,urllib.request; from knowledge_pilot.config import OLLAMA_BASE_URL; '
            'r=urllib.request.urlopen(OLLAMA_BASE_URL+"/api/tags",timeout=10); '
            'print(json.dumps({"status":r.status,"models":[m["name"] for m in json.load(r)["models"]]}))')
        check('ollama', ollama)
        embedding = container_python('import json; from knowledge_pilot.retrieval.embedding import embed_text; '
            'v=embed_text("Step 2 isolated probe"); print(json.dumps({"dimensions":len(v)}))')
        if embedding['dimensions'] != args.dimensions:
            raise RuntimeError('unexpected embedding dimensions')
        check('embedding', embedding)
        boundary = 'kp-' + uuid.uuid4().hex
        content = b'KnowledgePilot Linux Step 2 persistent document.'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="linux-probe.txt"\r\n'
                'Content-Type: text/plain\r\n\r\n').encode() + content + f'\r\n--{boundary}--\r\n'.encode()
        status, document = api('/documents', 'POST', body, 'multipart/form-data; boundary=' + boundary)
        if status != 201 or document['chunk_count'] != 1:
            raise RuntimeError('upload did not return one chunk')
        raw = data_root / 'raw_documents' / document['document_id'] / 'linux-probe.txt'
        if raw.read_bytes() != content or not (data_root / 'vector_store/chroma.sqlite3').is_file():
            raise RuntimeError('host raw/database persistence failed')
        check('upload', document)
        mounts = json.loads(command([args.docker, 'inspect', first_id, '--format', '{{json .Mounts}}']))
        mount = next(m for m in mounts if m['Destination'] == '/app/data')
        if mount['Type'] != 'bind' or not mount['RW']:
            raise RuntimeError('wrong mount type or access')
        check('mount', mount)
        command(compose + ['stop', 'api'])
        command(compose + ['rm', '-f', 'api'])
        command(compose + ['up', '-d', '--no-build', 'api'])
        health()
        second_id = command(compose + ['ps', '-q', 'api'])
        status, documents = api('/documents')
        store = container_python('import json; from knowledge_pilot.vector_store.chroma_store import collection; '
            'r=collection.get(include=["documents"]); print(json.dumps({"count":len(r["ids"]),"documents":r["documents"]}))')
        if (first_id == second_id or status != 200 or document not in documents
                or raw.read_bytes() != content or store != {'count': 1, 'documents': [content.decode()]}):
            raise RuntimeError('container delete/recreate lost persisted state')
        check('recreate_persistence', {'old_container': first_id, 'new_container': second_id,
                                       'document': document, 'store': store,
                                       'raw_sha256': hashlib.sha256(content).hexdigest()})
        evidence['status'] = 'passed'
    except Exception as error:
        evidence['error'] = type(error).__name__ + ': ' + str(error)
        print('FAIL ' + evidence['error'], flush=True)
        if resources_attempted:
            try:
                command(compose + ['logs', '--tail', '40', 'api'])
            except Exception:
                pass
    finally:
        evidence['cleanup'] = 'not needed; no container resources attempted'
        if resources_attempted:
            try:
                command(compose + ['down'])
                evidence['cleanup'] = 'own containers/network removed; test data retained'
            except Exception as error:
                evidence['cleanup'] = 'failed: ' + type(error).__name__
                evidence['status'] = 'failed'
        evidence['native_linux_acceptance'] = (
            'PASS' if evidence.get('native_linux_environment') and evidence['status'] == 'passed'
            else 'FAIL' if evidence.get('native_linux_environment') else 'BLOCKED_NOT_RUN')
        evidence['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        with evidence_path.open('x', encoding='utf-8') as output:
            output.write(json.dumps(evidence, indent=2, ensure_ascii=False) + '\n')
        print('Evidence: ' + str(evidence_path), flush=True)
    return int(evidence['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
