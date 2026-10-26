"""Structured application logs with a metadata allowlist and value-free tracebacks."""
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
import traceback

request_id: ContextVar[str | None] = ContextVar('knowledge_pilot_request_id', default=None)


class SafeJSONFormatter(logging.Formatter):
    """Never formats arbitrary record.msg, arguments, exception values or locals."""

    EVENTS = {'request_complete', 'request_failed', 'service_error', 'input_rejected',
              'upstream_complete', 'upstream_failed', 'tool_failed', 'internal_error',
              'response_started_failure'}

    def format(self, record: logging.LogRecord) -> str:
        event = record.msg if isinstance(record.msg, str) and record.msg in self.EVENTS else 'application_event'
        result = {'time_utc': datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                  'level': record.levelname, 'event': event, 'request_id': request_id.get()}
        for name in ('route', 'method', 'status', 'duration_ms', 'category', 'operation'):
            if name in record.__dict__:
                result[name] = record.__dict__[name]
        if record.exc_info and record.exc_info[1] is not None:
            error = record.exc_info[1]
            chain = []
            seen = set()
            while error is not None and id(error) not in seen and len(chain) < 8:
                seen.add(id(error))
                chain.append({'type': type(error).__name__, 'frames': [
                    {'module': frame.f_globals.get('__name__', 'unknown'),
                     'function': frame.f_code.co_name, 'line': line}
                    for frame, line in traceback.walk_tb(error.__traceback__)]})
                error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
            result['exception'] = chain[0]
            if len(chain) > 1:
                result['causes'] = chain[1:]
        return json.dumps(result, ensure_ascii=False, allow_nan=False)


def configure_logging(level: str = 'INFO', *, stream=None) -> None:
    """Configure only our logger; replace only the handler owned by this function."""
    if level not in {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}:
        from knowledge_pilot.errors import ConfigurationError
        raise ConfigurationError('KP_LOG_LEVEL is invalid')
    logger = logging.getLogger('knowledge_pilot')
    for handler in list(logger.handlers):
        if getattr(handler, '_knowledge_pilot_owned', False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.__stderr__)
    handler._knowledge_pilot_owned = True
    handler.setFormatter(SafeJSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    # Uvicorn's default access line contains raw paths/query strings. Our route
    # template log replaces it; leave uvicorn.error and other host loggers alone.
    logging.getLogger('uvicorn.access').disabled = True
