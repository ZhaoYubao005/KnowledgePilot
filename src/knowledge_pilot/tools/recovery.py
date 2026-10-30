"""Bounded recovery for explicitly read-only tools, with safe public events."""
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

from knowledge_pilot.errors import (
    ModelError,
    ModelResponseError,
    ModelTimeout,
    ModelUnavailable,
)


@dataclass
class RecoveryResult:
    """Execution outcome; ``exception`` is internal and must not be serialized.

    ``error`` is ``exhausted`` after retryable failures consume the attempt bound.
    The last event retains the underlying failure category. Other failures expose
    their category directly. ``retryable`` records policy eligibility, including
    the final failed attempt; it does not promise another attempt will occur.
    """

    value: Any = None
    error: str | None = None
    events: list[dict] = field(default_factory=list)
    exception: Exception | None = field(default=None, repr=False, compare=False)


def _classify(error: Exception) -> str:
    if isinstance(error, ModelTimeout):
        return 'model_timeout'
    if isinstance(error, ModelUnavailable):
        return 'model_unavailable'
    if isinstance(error, ModelResponseError):
        return 'model_response_error'
    if isinstance(error, ModelError):
        return 'model_error'
    if isinstance(error, requests.Timeout):
        return 'network_timeout'
    if isinstance(error, requests.ConnectionError):
        return 'network_unavailable'
    if isinstance(error, (TypeError, ValueError)):
        return 'invalid_arguments'
    return 'tool_failed'


def execute_with_recovery(
    name: str,
    arguments: dict,
    *,
    executor: Callable[[str, dict], Any],
    max_attempts: int = 2,
) -> RecoveryResult:
    """Execute once, retrying only known transient read-only retrieval failures.

    Bounds are strict (1 through 3, excluding booleans). There are no graph loops,
    implicit executor imports, sleeps, or writes. Events contain only fixed safe
    categories and execution counters, never inputs or exception messages.
    """
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError('max_attempts must be an integer from 1 to 3')

    stage = 'retrieve' if name == 'search_knowledge_base' else 'tool'
    events = []
    if not isinstance(arguments, dict):
        events.append({'stage': stage, 'attempt': 1, 'status': 'failed',
                       'category': 'invalid_arguments', 'retryable': False})
        return RecoveryResult(error='invalid_arguments', events=events)

    for attempt in range(1, max_attempts + 1):
        try:
            value = executor(name, arguments)
        except Exception as error:
            category = _classify(error)
            transient_model = (isinstance(error, (ModelTimeout, ModelUnavailable))
                               and error.operation == 'embedding')
            transient_network = isinstance(error, (requests.Timeout,
                                                   requests.ConnectionError))
            retryable = (name == 'search_knowledge_base'
                         and (transient_model or transient_network))
            events.append({'stage': stage, 'attempt': attempt, 'status': 'failed',
                           'category': category, 'retryable': retryable})
            if retryable and attempt < max_attempts:
                continue
            return RecoveryResult(error='exhausted' if retryable else category,
                                  events=events, exception=error)

        events.append({'stage': stage, 'attempt': attempt, 'status': 'succeeded',
                       'category': None, 'retryable': False})
        return RecoveryResult(value=value, events=events)

    raise AssertionError('validated recovery bound must execute at least once')
