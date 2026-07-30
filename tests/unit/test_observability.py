"""T2 PASS: JSON logs carry every mandated field."""

from __future__ import annotations

import json
import logging

from qe_observability import LOG_FIELDS, JsonLogFormatter, bind_log_context

MANDATED_FIELDS = {
    "timestamp",
    "service",
    "environment",
    "severity",
    "message",
    "request_id",
    "trace_id",
    "user_id",
    "project_id",
    "job_id",
    "event_type",
    "error_code",
}


def _format(record: logging.LogRecord) -> dict[str, object]:
    data: dict[str, object] = json.loads(JsonLogFormatter().format(record))
    return data


def test_log_fields_constant_matches_spec() -> None:
    assert set(LOG_FIELDS) == MANDATED_FIELDS


def test_every_record_has_all_fields() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = _format(record)
    assert MANDATED_FIELDS.issubset(payload.keys())
    assert payload["severity"] == "INFO"
    assert payload["message"] == "hello"


def test_context_fields_are_merged() -> None:
    bind_log_context(request_id="r1", user_id="u1", project_id="p1", trace_id="t1")
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="ctx",
        args=(),
        exc_info=None,
    )
    payload = _format(record)
    assert payload["request_id"] == "r1"
    assert payload["user_id"] == "u1"
    assert payload["project_id"] == "p1"
    assert payload["trace_id"] == "t1"
    # reset so other tests are not affected
    bind_log_context(request_id=None, user_id=None, project_id=None, trace_id=None)
