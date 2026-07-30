"""Correlation-id middleware.

Assigns (or propagates) a request id, binds it to the logging context, and
echoes it back on the response so clients and logs share one identifier.

Implemented as pure-ASGI (not ``BaseHTTPMiddleware``) so the ``contextvar`` set
here propagates into the endpoint coroutine.
"""

from __future__ import annotations

import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from qe_observability import bind_log_context

REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIdMiddleware:
    """Guarantee every HTTP request carries a request id, echoed on the response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        bind_log_context(request_id=request_id)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
            await send(message)

        await self.app(scope, receive, send_with_header)


def get_request_id(request: Request) -> str | None:
    """Return the request id bound to the current request, if any."""
    state = request.scope.get("state") or {}
    rid = state.get("request_id")
    return rid if isinstance(rid, str) else None


__all__ = ["REQUEST_ID_HEADER", "CorrelationIdMiddleware", "get_request_id"]
