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

    # AI gateway / provider (ADR-0201, ADR-0209). These values are also written
    # verbatim to ``model_runs.error_code``, so they are part of the persisted
    # audit record — never renumber or repurpose one.
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PROVIDER_REFUSED = "PROVIDER_REFUSED"
    PROVIDER_RESPONSE_INVALID = "PROVIDER_RESPONSE_INVALID"

    # Prompt registry (ADR-0209)
    PROMPT_VERSION_NOT_FOUND = "PROMPT_VERSION_NOT_FOUND"
    PROMPT_VERSION_INVALID_STATE = "PROMPT_VERSION_INVALID_STATE"
    PROMPT_VERSION_FORMAT_INVALID = "PROMPT_VERSION_FORMAT_INVALID"
    PROMPT_TEMPLATE_DRIFT = "PROMPT_TEMPLATE_DRIFT"

    # Prompt rendering (ADR-0211)
    PROMPT_RENDER_FAILED = "PROMPT_RENDER_FAILED"

    # Test generation (ADR-0205, ADR-0208, ADR-0211)
    TEST_CONFIG_INVALID = "TEST_CONFIG_INVALID"
    TEST_CONFIG_UNSUPPORTED = "TEST_CONFIG_UNSUPPORTED"
    TEST_GENERATION_FAILED = "TEST_GENERATION_FAILED"

    # TODO(phase-3): RAG / knowledge-base error codes
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


class JobNotFoundError(AppError):
    code = ErrorCode.JOB_NOT_FOUND
    http_status = 404


class JobInvalidStateError(AppError):
    """A transition the job state machine does not permit."""

    code = ErrorCode.JOB_INVALID_STATE
    http_status = 409


class ProviderError(AppError):
    """Base for every failure originating at an AI provider (ADR-0201).

    Carries ``error_code`` separately from :attr:`code` because the value
    persisted to ``model_runs.error_code`` is the audit record, and it must stay
    stable even if the HTTP mapping changes.
    """

    code = ErrorCode.PROVIDER_ERROR
    http_status = 502


class RetryableProviderError(ProviderError):
    """A transient provider failure worth retrying — 429s and 5xx.

    Retryability is expressed as a *type* rather than a flag so the retry policy
    is decided by whoever raises the error (the adapter, which knows what the
    status code meant) instead of by a status-code check in the retry loop.
    A plain :class:`ProviderError` is never retried.
    """

    code = ErrorCode.PROVIDER_ERROR
    http_status = 502


class ProviderTimeoutError(RetryableProviderError):
    """The provider did not respond within the configured timeout."""

    code = ErrorCode.PROVIDER_TIMEOUT
    http_status = 504


class ProviderRefusalError(ProviderError):
    """The provider's safety classifiers declined the request.

    Arrives as a successful HTTP 200 with ``stop_reason == "refusal"`` and empty
    or partial content, so it must be detected before the response body is read.
    """

    code = ErrorCode.PROVIDER_REFUSED
    http_status = 502


class ProviderResponseInvalidError(ProviderError):
    """The provider returned content that does not satisfy the output schema."""

    code = ErrorCode.PROVIDER_RESPONSE_INVALID
    http_status = 502


class PromptVersionNotFoundError(AppError):
    """No prompt version matched the requested name/version."""

    code = ErrorCode.PROMPT_VERSION_NOT_FOUND
    http_status = 404


class PromptVersionInvalidStateError(AppError):
    """A transition the prompt lifecycle does not permit (§19 L1791-1807)."""

    code = ErrorCode.PROMPT_VERSION_INVALID_STATE
    http_status = 409


class PromptVersionFormatError(AppError):
    """A version string that is not ``{prompt_name}-v{n}``."""

    code = ErrorCode.PROMPT_VERSION_FORMAT_INVALID
    http_status = 422


class PromptRenderError(AppError):
    """A template variable was missing at render time.

    Raised rather than rendering the section empty: a prompt with a silently
    blank requirement block still produces confident-looking output, which is
    the worst available failure mode (ADR-0202).
    """

    code = ErrorCode.PROMPT_RENDER_FAILED
    http_status = 500


class TestConfigInvalidError(AppError):
    """The generator configuration is malformed or out of range (ADR-0208)."""

    code = ErrorCode.TEST_CONFIG_INVALID
    http_status = 422


class TestConfigUnsupportedError(AppError):
    """A configuration option this phase cannot honour was requested.

    Phase 2's one case is ``include_accessibility_cases``: accepting it and
    returning ordinary tests would label them as covering accessibility when
    they do not, so the request is refused instead (ADR-0208).
    """

    code = ErrorCode.TEST_CONFIG_UNSUPPORTED
    http_status = 422


class TestGenerationError(AppError):
    """The generation pipeline could not complete (ADR-0211)."""

    code = ErrorCode.TEST_GENERATION_FAILED
    http_status = 500


class PromptTemplateDriftError(AppError):
    """A registered version's stored template no longer matches its source.

    ``prompt_versions`` is a mirror of git-versioned source templates (ADR-0202,
    preserved by ADR-0209); a checksum mismatch means the two have diverged and
    the row can no longer be trusted to describe what actually ran.
    """

    code = ErrorCode.PROMPT_TEMPLATE_DRIFT
    http_status = 500
