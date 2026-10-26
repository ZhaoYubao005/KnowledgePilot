"""Bounded deployment checks; never imports the application or opens Chroma."""
import argparse
import json
import os
from pathlib import Path
import platform
import tempfile
from urllib.parse import urlsplit


def validate_data_dir(path: Path) -> list[str]:
    if not path.is_absolute():
        return ['data directory must be absolute']
    if not path.is_dir():
        return ['data directory must already exist and be a directory']
    descriptor = None
    probe = None
    errors = []
    try:
        descriptor, name = tempfile.mkstemp(prefix='.kp-preflight-', dir=path)
        probe = Path(name)
        stream = os.fdopen(descriptor, 'wb')
        descriptor = None
        with stream:
            stream.write(b'KnowledgePilot preflight\n')
            stream.flush()
        if probe.read_bytes() != b'KnowledgePilot preflight\n':
            errors.append('data directory probe read-back failed')
    except OSError:
        errors.append('data directory create/write/read probe failed for the current user')
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                errors.append('data directory probe cleanup failed')
    return errors


def validate_ollama_origin(value: str) -> list[str]:
    try:
        url = urlsplit(value)
        if (not value or any(c.isspace() for c in value) or url.scheme not in {'http', 'https'}
                or not url.hostname or url.username is not None or url.password is not None
                or url.path not in {'', '/'} or url.query or url.fragment
                or (url.port is not None and not 1 <= url.port <= 65535)):
            return ['Ollama URL must be an HTTP(S) origin without credentials, path or query']
    except ValueError:
        return ['Ollama URL has an invalid host or port']
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--ollama-url', required=True)
    args = parser.parse_args()
    path = Path(args.data_dir)
    path_errors = validate_data_dir(path)
    url_errors = validate_ollama_origin(args.ollama_url)
    print(json.dumps({'platform': platform.system(), 'data_dir': str(path),
                      'writable': not path_errors,
                      'ollama_url': None if url_errors else args.ollama_url.rstrip('/'),
                      'errors': path_errors + url_errors,
                      'scope': 'host current-user probe; does not prove container UID 10001 access'}))
    return int(bool(path_errors or url_errors))


if __name__ == '__main__':
    raise SystemExit(main())
