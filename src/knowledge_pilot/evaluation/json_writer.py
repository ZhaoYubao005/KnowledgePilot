"""Exclusive JSON report persistence utilities."""

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any


def write_json_exclusive(
    path: Path,
    payload: Mapping[str, Any],
) -> Path:
    """Write one UTF-8 JSON report without replacing an existing file.

    The completed implementation must serialize before creating ``path`` using
    ``ensure_ascii=False``, ``indent=2``, and ``allow_nan=False``. It must then
    create the file exclusively, write LF text with a final newline, and remove
    any partial file if writing fails. Missing parent directories must remain
    missing, and serialization errors must propagate without creating a file.
    """
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    ) + "\n"

    created = False
    try:
        with path.open("x", encoding="utf-8", newline="\n") as file:
            created = True
            file.write(serialized)
    except BaseException:
        if created:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise

    return path
