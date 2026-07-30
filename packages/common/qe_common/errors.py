"""Standard error taxonomy and response envelope.

ADR-0006: every error the platform returns uses a single envelope shape with a
structured, stable error code. Clients switch on ``error.code`` (an enum value),
never on the human-readable ``message``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """Structured, stable error codes.

    Values are namespaced ``AREA_REASON`` strings so they read well in logs and
    are safe to expose to API clients. Add new members per phase; never renumber
    or repurpose an existing value.
    """

    # Generic / transport
    INTERNAL_ERROR = "INTERNAL_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    RATE_LIMITED = "RATE_LIMITED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # Job lifecycle (worker/scheduler)
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_INVALID_STATE = "JOB_INVALID_STATE"

    # TODO(phase-2): AI gateway / provider error codes (PROVIDER_TIMEOUT, ...)
    # TODO(phase-3): RAG / knowledge-base error codes
    # TODO(phase-4): test-generation error codes
    # TODO(phase-5): defect-triage error codes


class ErrorDetail(BaseModel):
    """A single field-level or contextual detail attached to an error."""

    field: str | None = Field(
        default=None, description="Dotted path to the offending field, if any."
    )
    message: str = Field(description="Human-readable explanation of this detail.")


class ErrorBody(BaseModel):
    """Inner error object of :class:`ErrorResponse`."""

    code: ErrorCode = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable summary safe to surface to callers.")
    request_id: str | None = Field(default=None, description="Correlation id for this request.")
    details: list[ErrorDetail] = Field(
        default_factory=list, description="Optional per-field details."
    )


class ErrorResponse(BaseModel):
    """The one and only error envelope returned by every service.

    Shape: ``{"error": {"code", "message", "request_id", "details": [...]}}``.
    """

    error: ErrorBody


class AppError(Exception):
    """Base application exception carrying a structured code and HTTP status.

    Raise subclasses (or this directly) anywhere in the stack; the API's global
    handler renders them into an :class:`ErrorResponse`.
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        http_status: int | None = None,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if http_status is not None:
            self.http_status = http_status
        self.details: list[ErrorDetail] = details or []

    def to_response(self, request_id: str | None = None) -> ErrorResponse:
        """Render this exception into the standard error envelope."""
        return ErrorResponse(
            error=ErrorBody(
                code=self.code,
                message=self.message,
                request_id=request_id,
                details=self.details,
            )
        )


class ValidationAppError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 422


class NotFoundError(AppError):
    code = ErrorCode.NOT_FOUND
    http_status = 404


class ConflictError(AppError):
    code = ErrorCode.CONFLICT
    http_status = 409


class UnauthorizedError(AppError):
    code = ErrorCode.UNAUTHORIZED
    http_status = 401


class ForbiddenError(AppError):
    code = ErrorCode.FORBIDDEN
    http_status = 403


class ServiceUnavailableError(AppError):
    code = ErrorCode.SERVICE_UNAVAILABLE
    http_status = 503
