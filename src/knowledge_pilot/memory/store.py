"""SQLite session persistence with atomic revision checks and bounded history."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Iterator

from .context import _valid_turn, _validate_limits, select_turns


class SessionError(Exception):
    """Base class for safe session errors."""


class SessionNotFound(SessionError):
    def __init__(self) -> None:
        super().__init__('Session not found.')


class SessionConflict(SessionError):
    def __init__(self) -> None:
        super().__init__('Session changed. Please retry.')


class SessionDataError(SessionError):
    def __init__(self) -> None:
        super().__init__('Session data unavailable.')


class SessionStore:
    """Keep sessions in a local file, opening a connection for each operation.

    A caller reads the revision before running its model, then supplies that
    revision to append. No database connection or lock spans the model call.
    """

    def __init__(self, path: Path, *, max_turns: int = 10, max_chars: int = 12000) -> None:
        _validate_limits(max_turns, max_chars)
        self.max_turns = max_turns
        self.max_chars = max_chars
        try:
            self.path = Path(path).resolve()
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, ValueError):
            raise SessionDataError() from None
        with self._connection() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL CHECK(revision >= 0),
                turns TEXT NOT NULL
            )''')

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=2.0)
            connection.execute('PRAGMA busy_timeout = 2000')
            with connection:
                yield connection
        except sqlite3.Error:
            raise SessionDataError() from None
        finally:
            if connection is not None:
                connection.close()

    @staticmethod
    def _validate_id(session_id: str) -> None:
        if not isinstance(session_id, str) or re.fullmatch(r'[A-Za-z0-9_-]{43}', session_id) is None:
            raise SessionNotFound()

    @staticmethod
    def _revision(value: object) -> int:
        if type(value) is not int or value < 0:
            raise SessionDataError()
        return value

    def _snapshot(self, session_id: str, row: tuple | None) -> dict:
        if row is None:
            raise SessionNotFound()
        revision = self._revision(row[0])
        try:
            turns = json.loads(row[1])
        except (TypeError, ValueError, RecursionError):
            raise SessionDataError() from None
        if not isinstance(turns, list):
            raise SessionDataError()
        return {'session_id': session_id, 'revision': revision, 'turns': turns}

    def create(self) -> dict:
        """Create an empty session with an unguessable 256-bit opaque ID."""
        session_id = secrets.token_urlsafe(32)
        with self._connection() as connection:
            connection.execute('INSERT INTO sessions (session_id, revision, turns) VALUES (?, 0, ?)',
                               (session_id, '[]'))
        return {'session_id': session_id, 'revision': 0, 'turns': []}

    def read(self, session_id: str) -> dict:
        self._validate_id(session_id)
        with self._connection() as connection:
            row = connection.execute('SELECT revision, turns FROM sessions WHERE session_id = ?',
                                     (session_id,)).fetchone()
        snapshot = self._snapshot(session_id, row)
        snapshot['turns'] = select_turns(snapshot['turns'], self.max_turns, self.max_chars)
        return snapshot

    def append(self, session_id: str, query: str, answer: str, *, expected_revision: int) -> dict:
        """Atomically append a successful pair only if the version is current."""
        self._validate_id(session_id)
        turn = {'query': query, 'answer': answer}
        if not _valid_turn(turn):
            raise ValueError('Session turns require non-empty query and answer strings.')
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError('Expected revision must be a non-negative integer.')
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT revision, turns FROM sessions WHERE session_id = ?',
                                     (session_id,)).fetchone()
            current = self._snapshot(session_id, row)
            if current['revision'] != expected_revision:
                raise SessionConflict()
            turns = select_turns(current['turns'] + [turn], self.max_turns, self.max_chars)
            revision = current['revision'] + 1
            connection.execute('UPDATE sessions SET revision = ?, turns = ? WHERE session_id = ?',
                               (revision, json.dumps(turns, ensure_ascii=False), session_id))
        return {'session_id': session_id, 'revision': revision, 'turns': turns}

    def clear(self, session_id: str) -> dict:
        """Clear content and advance the version, invalidating in-flight work."""
        self._validate_id(session_id)
        with self._connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT revision FROM sessions WHERE session_id = ?',
                                     (session_id,)).fetchone()
            if row is None:
                raise SessionNotFound()
            revision = self._revision(row[0]) + 1
            connection.execute('UPDATE sessions SET revision = ?, turns = ? WHERE session_id = ?',
                               (revision, '[]', session_id))
        return {'session_id': session_id, 'revision': revision, 'turns': []}
