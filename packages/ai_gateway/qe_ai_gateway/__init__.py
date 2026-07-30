"""AI gateway — provider-agnostic interface to LLM/embedding backends.

Phase 0 ships only the abstract interface; no provider SDKs are pulled in and no
network calls are made. Concrete providers arrive in later phases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CompletionRequest:
    """A single completion request routed through the gateway."""

    prompt: str
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass(frozen=True)
class CompletionResult:
    """The result of a completion request."""

    text: str
    model: str
    usage_tokens: int


class AIGateway(ABC):
    """Abstract provider gateway. Concrete implementations land in later phases."""

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResult:
        """Run a completion. TODO(phase-2): implement real provider routing."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return an embedding vector. TODO(phase-3): implement for RAG."""
        raise NotImplementedError


__all__ = ["AIGateway", "CompletionRequest", "CompletionResult"]
