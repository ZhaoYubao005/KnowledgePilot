"""Boundary error types. Public messages never contain upstream or user content."""


class ConfigurationError(ValueError):
    """Invalid process configuration; compatible with existing ValueError callers."""


class InputError(ValueError):
    """Explicit service input validation (not arbitrary internal ValueError)."""


class InternalServiceError(Exception):
    """An internal boundary failed; clients receive a fixed generic message."""


class ModelError(Exception):
    def __init__(self, operation: str):
        self.operation = operation if operation in {'llm', 'embedding'} else 'llm'
        super().__init__('model service failure')


class ModelUnavailable(ModelError):
    """Connection to the model service could not be established."""


class ModelTimeout(ModelError):
    """Model connect/read deadline exceeded; no automatic retry."""


class ModelResponseError(ModelError):
    """Non-success HTTP, invalid JSON or malformed model response."""
