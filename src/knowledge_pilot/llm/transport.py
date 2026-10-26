"""Bounded upstream JSON boundary, independent of Agent and retrieval algorithms."""
import logging
from time import perf_counter

import requests
from knowledge_pilot.config import OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT
from knowledge_pilot.errors import ModelUnavailable, ModelTimeout, ModelResponseError

logger = logging.getLogger(__name__)


def post_json(url: str, payload: dict, *, operation: str, post) -> dict:
    started = perf_counter()
    try:
        try:
            response = post(url, json=payload, timeout=(OLLAMA_CONNECT_TIMEOUT, OLLAMA_READ_TIMEOUT))
            response.raise_for_status()
        except requests.Timeout as error:
            raise ModelTimeout(operation) from error
        except requests.ConnectionError as error:
            raise ModelUnavailable(operation) from error
        except requests.RequestException as error:
            raise ModelResponseError(operation) from error
        try:
            data = response.json()
        except ValueError as error:
            raise ModelResponseError(operation) from error
        if not isinstance(data, dict):
            raise ModelResponseError(operation)
    except (ModelUnavailable, ModelTimeout, ModelResponseError):
        logger.warning('upstream_failed', extra={'operation': operation})
        raise
    logger.info('upstream_complete', extra={'operation': operation,
                'duration_ms': round((perf_counter() - started) * 1000, 3)})
    return data
