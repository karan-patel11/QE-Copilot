"""Security helpers: secret redaction and input-safety utilities.

Phase 0 ships a small, dependency-free redaction helper used by logging and
error rendering so secrets never leak. Heavier controls (rate limiting, secret
scanning integration, signature verification) arrive in later phases.
"""

from __future__ import annotations

import re

# Best-effort patterns for values that must never appear in logs or responses.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization|api[_-]?key|secret|password|token)\s*[:=]\s*\S+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
)

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Return ``text`` with obvious secrets masked."""
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


# TODO(phase-6): request signing / webhook signature verification.
# TODO(phase-6): centralized rate-limiting policy.

__all__ = ["redact"]
