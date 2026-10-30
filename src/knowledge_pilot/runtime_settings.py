"""Bounded V1.6 settings, evaluated without modifying historical defaults."""
import os
from knowledge_pilot.errors import ConfigurationError


def bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise ConfigurationError('invalid reliability configuration') from None
    if not minimum <= value <= maximum:
        raise ConfigurationError('invalid reliability configuration')
    return value


def recovery_attempts() -> int:
    return bounded_integer('KP_TOOL_MAX_ATTEMPTS', 2, 1, 3)
