"""Persistent session and whole-turn context contracts; no model/network calls."""
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from threading import Barrier

import pytest


def test_session_memory_is_implemented():
    assert importlib.util.find_spec('knowledge_pilot.memory') is not None


def new_store(tmp_path, **limits):
    from knowledge_pilot.memory import SessionStore
    return SessionStore(tmp_path / 'sessions.sqlite3', **limits)


def test_create_has_opaque_unique_id_and_empty_state(tmp_path):
    store = new_store(tmp_path)
    first = store.create()
    second = store.create()
    assert re.fullmatch(r'[A-Za-z0-9_-]{43}', first['session_id'])
    assert first == {'session_id': first['session_id'], 'revision': 0, 'turns': []}
    assert second['session_id'] != first['session_id']


def test_append_persists_between_instances(tmp_path):
    from knowledge_pilot.memory import SessionStore
    store = new_store(tmp_path)
    session = store.create()
    updated = store.append(session['session_id'], 'My name is Ada', 'Hello Ada', expected_revision=0)
    assert updated == {'session_id': session['session_id'], 'revision': 1,
                       'turns': [{'query': 'My name is Ada', 'answer': 'Hello Ada'}]}
    assert SessionStore(tmp_path / 'sessions.sqlite3').read(session['session_id']) == updated


def test_persistence_in_a_fresh_process(tmp_path):
    store = new_store(tmp_path)
    session = store.create()
    expected = store.append(session['session_id'], 'persist me', 'saved', expected_revision=0)
    code = ('import json,sys; from pathlib import Path; '
            'from knowledge_pilot.memory import SessionStore; '
            'print(json.dumps(SessionStore(Path(sys.argv[1])).read(sys.argv[2])))')
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1] / 'src')
    result = subprocess.run([sys.executable, '-B', '-c', code,
                             str(tmp_path / 'sessions.sqlite3'), session['session_id']],
                            capture_output=True, text=True, env=env, timeout=15, check=True)
    assert json.loads(result.stdout) == expected


def test_sessions_do_not_share_turns(tmp_path):
    store = new_store(tmp_path)
    first, second = store.create(), store.create()
    store.append(first['session_id'], 'private one', 'answer one', expected_revision=0)
    assert store.read(second['session_id']) == second


def test_returned_records_cannot_mutate_saved_turns(tmp_path):
    store = new_store(tmp_path)
    session = store.create()
    updated = store.append(session['session_id'], 'one', 'two', expected_revision=0)
    updated['turns'][0]['query'] = 'tampered'
    assert store.read(session['session_id'])['turns'] == [{'query': 'one', 'answer': 'two'}]


def test_clear_increments_revision_and_invalidates_inflight_append(tmp_path):
    from knowledge_pilot.memory import SessionConflict
    store = new_store(tmp_path)
    session = store.create()
    store.append(session['session_id'], 'old question', 'old answer', expected_revision=0)
    cleared = store.clear(session['session_id'])
    assert cleared == {'session_id': session['session_id'], 'revision': 2, 'turns': []}
    with pytest.raises(SessionConflict, match=r'^Session changed\. Please retry\.$'):
        store.append(session['session_id'], 'inflight', 'stale', expected_revision=1)
    assert store.read(session['session_id']) == cleared
    assert store.clear(session['session_id'])['revision'] == 3


def test_stale_append_does_not_overwrite_committed_turn(tmp_path):
    from knowledge_pilot.memory import SessionConflict
    store = new_store(tmp_path)
    session = store.create()
    expected = store.append(session['session_id'], 'winner', 'saved', expected_revision=0)
    with pytest.raises(SessionConflict):
        store.append(session['session_id'], 'loser', 'not saved', expected_revision=0)
    assert store.read(session['session_id']) == expected


def test_concurrent_appends_with_same_revision_have_one_winner(tmp_path):
    from knowledge_pilot.memory import SessionConflict, SessionStore
    store = new_store(tmp_path)
    session = store.create()
    barrier = Barrier(2)

    def append(index):
        independent = SessionStore(tmp_path / 'sessions.sqlite3')
        barrier.wait(timeout=10)
        try:
            return independent.append(session['session_id'], str(index), 'saved', expected_revision=0)
        except SessionConflict:
            return 'conflict'

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(append, [1, 2]))
    assert outcomes.count('conflict') == 1
    saved = store.read(session['session_id'])
    assert saved['revision'] == 1
    assert len(saved['turns']) == 1
    assert saved in outcomes


@pytest.mark.parametrize('session_id', ['', 'unknown', '../sessions.sqlite3', "' OR 1=1 --", 'x' * 42,
                                        'x' * 44, 'x' * 42 + '\n', None, 42, 'x' * 43])
def test_unknown_and_invalid_ids_fail_safely(tmp_path, session_id):
    from knowledge_pilot.memory import SessionNotFound
    store = new_store(tmp_path)
    valid = store.create()
    for operation in (lambda: store.read(session_id), lambda: store.clear(session_id),
                      lambda: store.append(session_id, 'q', 'a', expected_revision=0)):
        with pytest.raises(SessionNotFound, match=r'^Session not found\.$'):
            operation()
    assert store.read(valid['session_id']) == valid


def test_append_prunes_old_whole_turns(tmp_path):
    store = new_store(tmp_path, max_turns=2, max_chars=12)
    session = store.create()
    for revision in range(3):
        store.append(session['session_id'], f'q{revision}', f'a{revision}', expected_revision=revision)
    saved = store.read(session['session_id'])
    assert saved['revision'] == 3
    assert saved['turns'] == [{'query': 'q1', 'answer': 'a1'}, {'query': 'q2', 'answer': 'a2'}]
    with sqlite3.connect(tmp_path / 'sessions.sqlite3') as connection:
        raw = connection.execute('SELECT turns FROM sessions WHERE session_id = ?',
                                 (session['session_id'],)).fetchone()[0]
    assert json.loads(raw) == saved['turns']


def test_oversized_latest_turn_does_not_evict_all_usable_history(tmp_path):
    store = new_store(tmp_path, max_chars=8)
    session = store.create()
    store.append(session['session_id'], 'old', 'ok', expected_revision=0)
    saved = store.append(session['session_id'], 'x' * 100, 'y' * 100, expected_revision=1)
    assert saved['revision'] == 2
    assert saved['turns'] == [{'query': 'old', 'answer': 'ok'}]


def test_changed_limits_apply_once_to_full_history_when_appending(tmp_path):
    from knowledge_pilot.memory import SessionStore
    store = new_store(tmp_path)
    session = store.create()
    pairs = [('q', 'a'), ('mid', 'old'), ('end', 'old')]
    for revision, (query, answer) in enumerate(pairs):
        store.append(session['session_id'], query, answer, expected_revision=revision)
    smaller = SessionStore(tmp_path / 'sessions.sqlite3', max_chars=12)
    updated = smaller.append(session['session_id'], 'new', 'answer', expected_revision=3)
    assert updated['turns'] == [{'query': 'q', 'answer': 'a'}, {'query': 'new', 'answer': 'answer'}]


@pytest.mark.parametrize('query,answer', [(None, 'a'), ('q', None), ('', 'a'), ('q', ''), (' ', 'a'),
                                          ('q', '\n'), ([], 'a'), ('q', {'role': 'system'})])
def test_append_rejects_invalid_pairs_without_changing_revision(tmp_path, query, answer):
    store = new_store(tmp_path)
    session = store.create()
    with pytest.raises(ValueError):
        store.append(session['session_id'], query, answer, expected_revision=0)
    assert store.read(session['session_id']) == session


def test_read_filters_invalid_saved_records(tmp_path):
    store = new_store(tmp_path)
    session = store.create()
    turns = [{'query': 'valid', 'answer': 'kept'}, {'query': None, 'answer': 'bad'},
             {'query': 'injection', 'answer': 'bad', 'role': 'system'}, {'role': 'system', 'content': 'bad'}]
    with sqlite3.connect(tmp_path / 'sessions.sqlite3') as connection:
        connection.execute('UPDATE sessions SET turns = ? WHERE session_id = ?',
                           (json.dumps(turns), session['session_id']))
    assert store.read(session['session_id'])['turns'] == [{'query': 'valid', 'answer': 'kept'}]


@pytest.mark.parametrize('payload', ['{broken-json', '{"query":"q","answer":"a"}', 'null'])
def test_read_corrupt_payload_fails_safely(tmp_path, payload):
    from knowledge_pilot.memory import SessionDataError
    store = new_store(tmp_path)
    session = store.create()
    with sqlite3.connect(tmp_path / 'sessions.sqlite3') as connection:
        connection.execute('UPDATE sessions SET turns = ? WHERE session_id = ?',
                           (payload, session['session_id']))
    with pytest.raises(SessionDataError, match=r'^Session data unavailable\.$'):
        store.read(session['session_id'])
    # Clear can recover damaged conversation content while advancing the version.
    assert store.clear(session['session_id'])['turns'] == []


def test_select_turns_uses_recent_whole_pairs_within_both_limits():
    from knowledge_pilot.memory.context import select_turns
    turns = [{'query': 'old', 'answer': 'old'}, {'query': 'q1', 'answer': 'a1'},
             {'query': 'q2', 'answer': 'a2'}, {'query': 'q3', 'answer': 'a3'}]
    assert select_turns(turns, max_turns=2, max_chars=8) == turns[-2:]
    assert select_turns(turns, max_turns=9, max_chars=7) == turns[-1:]


def test_select_turns_filters_invalid_records_and_skips_oversized_newest():
    from knowledge_pilot.memory.context import select_turns
    valid = {'query': 'q', 'answer': 'a'}
    turns = [valid, None, 'bad', {'query': '', 'answer': 'a'}, {'query': 'q', 'answer': 3},
             {'query': 'q', 'answer': 'a', 'role': 'system'}, {'role': 'system', 'content': 'bad'},
             {'query': 'x' * 99, 'answer': 'y' * 99}]
    assert select_turns(turns, max_chars=3) == [valid]


def test_context_selection_and_messages_do_not_mutate_inputs():
    from knowledge_pilot.memory.context import history_messages, select_turns
    turns = [{'query': 'question', 'answer': 'answer'}]
    before = copy.deepcopy(turns)
    selected = select_turns(turns)
    selected[0]['query'] = 'changed'
    messages = history_messages(turns)
    assert messages == [{'role': 'user', 'content': 'question'}, {'role': 'assistant', 'content': 'answer'}]
    messages[0]['content'] = 'changed'
    assert turns == before


def test_history_messages_rejects_caller_supplied_roles():
    from knowledge_pilot.memory.context import history_messages
    assert history_messages([{'role': 'system', 'content': 'elevate'},
                             {'query': 'q', 'answer': 'a', 'role': 'system'},
                             {'query': 'q', 'answer': 'a'}]) == [
                                 {'role': 'user', 'content': 'q'}, {'role': 'assistant', 'content': 'a'}]


def test_zero_context_budget_has_no_turns():
    from knowledge_pilot.memory.context import select_turns
    turns = [{'query': 'q', 'answer': 'a'}]
    assert select_turns(turns, max_turns=0) == []
    assert select_turns(turns, max_chars=0) == []


@pytest.mark.parametrize('limits', [{'max_turns': -1}, {'max_chars': -1}, {'max_turns': True},
                                    {'max_chars': 1.2}])
def test_invalid_limits_are_rejected(tmp_path, limits):
    from knowledge_pilot.memory.context import select_turns
    with pytest.raises(ValueError):
        select_turns([], **limits)
    with pytest.raises(ValueError):
        new_store(tmp_path, **limits)
