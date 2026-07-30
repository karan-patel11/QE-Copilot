"""Global exception handlers rendering the standard error envelope (ADR-0006)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from qe_api.middleware import get_request_id
from qe_common.errors import AppError, ErrorBody, ErrorCode, ErrorDetail, ErrorResponse
from qe_observability import get_logger

logger = get_logger("qe_api.errors")


def _render(response: ErrorResponse, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = get_request_id(request)
    logger.warning(exc.message, extra={"error_code": exc.code.value, "event_type": "app_error"})
    return _render(exc.to_response(request_id), exc.http_status)


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = get_request_id(request)
    details = [
        ErrorDetail(field=".".join(str(p) for p in err.get("loc", [])), message=err.get("msg", ""))
        for err in exc.errors()
    ]
    body = ErrorResponse(
        error=ErrorBody(
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            request_id=request_id,
            details=details,
        )
    )
    return _render(body, 422)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = get_request_id(request)
    code = {
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        409: ErrorCode.CONFLICT,
        429: ErrorCode.RATE_LIMITED,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
    body = ErrorResponse(error=ErrorBody(code=code, message=str(exc.detail), request_id=request_id))
    return _render(body, exc.status_code)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = get_request_id(request)
    logger.error(
        "unhandled exception",
        exc_info=exc,
        extra={"error_code": ErrorCode.INTERNAL_ERROR.value},
    )
    body = ErrorResponse(
        error=ErrorBody(
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred.",
            request_id=request_id,
        )
    )
    return _render(body, 500)


def register_error_handlers(app: FastAPI) -> None:
    """Attach all standard-format exception handlers to the app."""
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)


__all__ = ["register_error_handlers"]
