#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
# Compose must interpolate the same inputs, even when the service is already down.
: "${KP_HOST_DATA_DIR:?Set the same KP_HOST_DATA_DIR used by up.sh}"
: "${KP_OLLAMA_BASE_URL:?Set the same KP_OLLAMA_BASE_URL used by up.sh}"
case "$KP_HOST_DATA_DIR" in /*) ;; *) echo 'KP_HOST_DATA_DIR must be absolute' >&2; exit 1 ;; esac
export KP_HOST_DATA_DIR KP_OLLAMA_BASE_URL
docker compose --env-file /dev/null -f "$ROOT/compose.yaml" -p knowledgepilot-v14 down
