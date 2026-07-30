"""T2 PASS: the standard error envelope has the mandated shape."""

from __future__ import annotations

from qe_common.errors import (
    AppError,
    ErrorCode,
    ErrorResponse,
    NotFoundError,
)


def test_error_response_shape() -> None:
    err = NotFoundError("thing missing")
    payload = err.to_response(request_id="req-123").model_dump(mode="json")

    assert set(payload.keys()) == {"error"}
    inner = payload["error"]
    assert set(inner.keys()) == {"code", "message", "request_id", "details"}
    assert inner["code"] == ErrorCode.NOT_FOUND.value
    assert inner["message"] == "thing missing"
    assert inner["request_id"] == "req-123"
    assert inner["details"] == []


def test_error_codes_are_stable_strings() -> None:
    # Codes are string-valued and namespaced; guards against accidental renames.
    assert ErrorCode.INTERNAL_ERROR.value == "INTERNAL_ERROR"
    assert ErrorCode.VALIDATION_ERROR.value == "VALIDATION_ERROR"
    assert ErrorCode.JOB_INVALID_STATE.value == "JOB_INVALID_STATE"


def test_app_error_defaults() -> None:
    err = AppError("boom")
    assert err.code is ErrorCode.INTERNAL_ERROR
    assert err.http_status == 500
    parsed = ErrorResponse.model_validate(err.to_response().model_dump())
    assert parsed.error.code is ErrorCode.INTERNAL_ERROR
