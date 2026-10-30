"""Safe HTTP errors and per-request observability, without service/Agent rewrites."""
import logging
from time import perf_counter
from uuid import uuid4

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from knowledge_pilot.errors import (ConfigurationError, InputError, InternalServiceError,
                                    ModelError, ModelUnavailable, ModelTimeout)
from knowledge_pilot.logging_config import request_id

logger = logging.getLogger(__name__)
INPUT_DETAILS = {'only txt files are supported', 'file cannot be empty',
                 'file content cannot be blank', 'invalid document', 'invalid session query'}


def safe_input_detail(error: ValueError) -> str:
    """Allow only existing fixed validation strings, never arbitrary exception text."""
    detail = str(error)
    return detail if detail in INPUT_DETAILS else 'invalid document'


async def service_error_handler(request, error: Exception) -> JSONResponse:
    if isinstance(error, InputError):
        status, detail, category = 400, safe_input_detail(error), 'input'
    elif isinstance(error, ModelError):
        embedding = error.operation == 'embedding'
        if isinstance(error, ModelTimeout):
            status, detail, category = 504, ('embedding service timed out' if embedding else 'LLM service timed out'), 'model_timeout'
        elif isinstance(error, ModelUnavailable):
            status, detail, category = 503, ('embedding service is unavailable' if embedding else 'LLM service is unavailable'), 'model_connection'
        else:
            status, detail, category = 502, ('embedding service returned an invalid response' if embedding else 'LLM service returned an invalid response'), 'model_response'
    else:
        status, detail = 500, 'internal service error'
        category = 'configuration' if isinstance(error, ConfigurationError) else 'internal'
    logger.log(logging.WARNING if status < 500 else logging.ERROR, 'service_error',
               extra={'category': category, 'status': status},
               exc_info=(type(error), error, error.__traceback__) if status >= 500 else None)
    content = {'detail': detail}
    if isinstance(error, ModelError) and getattr(error, 'diagnostics', None):
        content['diagnostics'] = error.diagnostics
    return JSONResponse(status_code=status, content=content)


async def validation_error_handler(request, error: RequestValidationError) -> JSONResponse:
    logger.warning('input_rejected', extra={'category': 'input', 'status': 422})
    fields = {'body', 'path', 'query', 'header', 'file', 'max_steps'}
    detail = [{'loc': [part if isinstance(part, int) or part in fields else 'field'
                       for part in item['loc']],
               'type': item['type'], 'msg': 'Invalid request input'} for item in error.errors()]
    return JSONResponse(status_code=422, content={'detail': detail})


async def http_error_handler(request, error: HTTPException) -> JSONResponse:
    # Existing route catches retain compatibility; inspect only their exception types/frames.
    if error.__context__ is not None:
        cause = error.__context__
        logger.log(logging.ERROR if error.status_code >= 500 else logging.WARNING, 'service_error',
                   extra={'status': error.status_code, 'category': 'http'},
                   exc_info=(type(cause), cause, cause.__traceback__) if error.status_code >= 500 else None)
    return JSONResponse(status_code=error.status_code, content={'detail': error.detail}, headers=error.headers)


class RequestLoggingMiddleware:
    """Pure ASGI boundary: sync worker threads inherit the request ContextVar."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        token = request_id.set(uuid4().hex)
        started = perf_counter()
        response_started = False
        status = 500

        async def send_with_id(message):
            nonlocal response_started, status
            if message['type'] == 'http.response.start':
                status = message['status']
                headers = [(name, value) for name, value in message.get('headers', [])
                           if name.lower() != b'x-request-id']
                message = {**message, 'headers': headers + [(b'x-request-id', request_id.get().encode('ascii'))]}
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as error:
            logger.exception('response_started_failure' if response_started else 'request_failed',
                             extra={'category': 'internal'})
            if not response_started:
                await JSONResponse(status_code=500, content={'detail': 'internal service error'})(scope, receive, send_with_id)
            # After response start, a second HTTP response would corrupt the protocol.
            # Preserve failure signalling with a value-free exception for the ASGI server.
            else:
                raise InternalServiceError('response failed after headers') from None
        finally:
            route = getattr(scope.get('route'), 'path', '__unmatched__')
            method = scope.get('method')
            logger.info('request_complete', extra={
                'route': route, 'method': method if method in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'} else 'OTHER',
                'status': status, 'duration_ms': round((perf_counter() - started) * 1000, 3)})
            request_id.reset(token)


def install_reliability(app) -> None:
    app.add_middleware(RequestLoggingMiddleware)
    for error_type in (ModelError, InputError, ConfigurationError, InternalServiceError):
        app.add_exception_handler(error_type, service_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
