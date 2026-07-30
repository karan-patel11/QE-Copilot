"""Shared domain primitives: error codes, error envelope, and app exceptions."""

from qe_common.errors import (
    AppError,
    ConflictError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)

__all__ = [
    "AppError",
    "ConflictError",
    "ErrorCode",
    "ErrorDetail",
    "ErrorResponse",
    "NotFoundError",
    "UnauthorizedError",
    "ValidationAppError",
]
