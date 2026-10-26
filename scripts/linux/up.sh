#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
: "${KP_HOST_DATA_DIR:?Set KP_HOST_DATA_DIR to an existing absolute data directory}"
: "${KP_OLLAMA_BASE_URL:?Set KP_OLLAMA_BASE_URL to a reachable host Ollama origin}"
case "$KP_HOST_DATA_DIR" in /*) ;; *) echo 'KP_HOST_DATA_DIR must be absolute' >&2; exit 1 ;; esac
export KP_HOST_DATA_DIR KP_OLLAMA_BASE_URL
python3 "$SCRIPT_DIR/preflight.py" --data-dir "$KP_HOST_DATA_DIR" --ollama-url "$KP_OLLAMA_BASE_URL"
# Ignore ambient .env files: all deployment inputs are explicitly exported.
set -- docker compose --env-file /dev/null -f "$ROOT/compose.yaml" -p knowledgepilot-v14
"$@" config --quiet
# Use the same image and bind mount as the service. No host chown/chmod is performed.
"$@" run --rm --no-deps -T --user 10001:10001 --entrypoint python api -c '
import os, pathlib, tempfile
if os.getuid() != 10001:
    raise RuntimeError("container UID is not 10001")
root = pathlib.Path("/app/data")
fd, name = tempfile.mkstemp(prefix=".kp-uid-probe-", dir=root)
path = pathlib.Path(name)
try:
    with os.fdopen(fd, "wb") as stream:
        stream.write(b"uid10001")
    if path.read_bytes() != b"uid10001":
        raise RuntimeError("UID probe read-back mismatch")
finally:
    path.unlink(missing_ok=True)
print("container UID 10001 create/read/delete: PASS")
'
"$@" up -d --no-build api
