"""Select complete conversation turns without promoting caller-supplied roles."""
from typing import Any


def _validate_limits(max_turns: int, max_chars: int) -> None:
    if any(type(value) is not int or value < 0 for value in (max_turns, max_chars)):
        raise ValueError('Session limits must be non-negative integers.')


def _valid_turn(turn: Any) -> bool:
    return (isinstance(turn, dict) and set(turn) == {'query', 'answer'}
            and all(isinstance(turn[key], str) and bool(turn[key].strip())
                    for key in ('query', 'answer')))


def select_turns(turns: list[dict], max_turns: int = 10, max_chars: int = 12000) -> list[dict]:
    """Return recent valid whole pairs in original order within both limits.

    The budget counts query and answer characters. A pair that cannot fit is
    skipped; older usable pairs may still fit. No string or record is mutated.
    """
    _validate_limits(max_turns, max_chars)
    if not isinstance(turns, (list, tuple)) or not max_turns or not max_chars:
        return []
    selected = []
    used = 0
    for turn in reversed(turns):
        if not _valid_turn(turn):
            continue
        size = len(turn['query']) + len(turn['answer'])
        if used + size > max_chars:
            continue
        selected.append({'query': turn['query'], 'answer': turn['answer']})
        used += size
        if len(selected) == max_turns:
            break
    selected.reverse()
    return selected


def history_messages(turns: list[dict]) -> list[dict]:
    """Convert valid pairs into alternating user/assistant messages only."""
    messages = []
    if not isinstance(turns, (list, tuple)):
        return messages
    for turn in turns:
        if _valid_turn(turn):
            messages.extend(({'role': 'user', 'content': turn['query']},
                             {'role': 'assistant', 'content': turn['answer']}))
    return messages
