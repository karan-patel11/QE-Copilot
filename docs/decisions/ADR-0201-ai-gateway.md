# ADR-0201 — AI gateway: provider interfaces, real adapter, and MockProvider

**Status:** Accepted (Phase 2, N1) — **corrected against `docs/architecture/design-spec.md` (N0.5)**
**Supersedes:** the Phase 0 `qe_ai_gateway` stub.

## Sources

| Claim | Spec |
|---|---|
| Domain logic must not couple to one provider | §8.5 L465, §18 L1766 |
| Interface names and signatures | §18 L1732–1748 |
| Gateway responsibilities | §18 L1750–1764 |
| Provider-neutral LLM + embedding interface, token/cost tracking | §10.3 L591–599 |
| Model fallback is P1 | §39 L2905 |

## Decision

### Interfaces — taken from §18, not invented

§18 L1732–1748 specifies these signatures verbatim. **The gateway implements them
as written**; an earlier revision of this ADR proposed `complete()` /
`complete_structured()` and synchronous methods, which did not match the spec and
has been corrected:

```python
class LanguageModelProvider:
    async def generate_structured(
        self,
        request: StructuredGenerationRequest,
    ) -> StructuredGenerationResponse: ...


class EmbeddingProvider:
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Both are **async** (§18). `EmbeddingProvider` has no real adapter in Phase 2 —
RAG is Phase 5 (§38 L2827) — only the mock; `TODO(phase-5)`.

### Gateway responsibilities (§18 L1750–1764)

All thirteen are listed here so an omission is visible rather than accidental.

| Responsibility | Phase 2 |
|---|---|
| Authentication | implemented — key from `Settings`, never logged |
| Request formatting | implemented |
| Timeout handling | implemented — explicit per-call timeout |
| Retry handling | implemented — bounded, with backoff; non-retryable 4xx never retried |
| Structured-output validation | implemented — response validated against the Pydantic output schema |
| Token counting | implemented — persisted to `model_runs` |
| Cost estimation | implemented — per-model rate table → `model_runs.estimated_cost` |
| Logging | implemented — structured, plus a `model_runs` row per call |
| Metrics | implemented — counters/latency via the Phase 0 observability package |
| **Model fallback** | **deferred — P1 (§39 L2905)**; the seam exists (provider is injected), the fallback chain is not built |
| **Provider-health checks** | **deferred — `TODO(phase-7)`**, pairs with circuit breaking |
| **Circuit breaking** | **deferred — `TODO(phase-7)`**; §29 reliability work |
| **Rate limiting** | **deferred — `TODO(phase-7)`**; the SDK's own 429 backoff covers Phase 2 |

The four deferrals are scope decisions, not omissions from the spec: only model
fallback carries an explicit priority (P1), and the remaining three belong with
the §29 reliability hardening in Phase 7 (§38 L2851).

### Chosen provider — an inference, not a sourced fact

**`design-spec.md` never names a vendor or model.** §10.3 L591–592 requires a
"provider-neutral LLM interface" and a "provider-neutral embedding interface";
§18 L1728 says the gateway "will isolate the application from a specific vendor".
Selecting a concrete provider is therefore *left to implementation*.

**Decision (inference):** Anthropic, model `claude-opus-5`, via the official
`anthropic` Python SDK — because the repository already reserved
`ANTHROPIC_API_KEY` in `.env.example` and no other provider appears anywhere in
the codebase. The model id is configurable (`AI_MODEL`), so this choice is an env
change, not a code change, which is exactly what provider-neutrality requires.

Provider-specific handling, contained entirely within the adapter:

- Structured generation uses the SDK's schema-constrained parse, which makes
  §18's "structured-output validation" a provider-enforced guarantee rather than
  a hopeful `json.loads`.
- `temperature`, `top_p`, `top_k` and `thinking.budget_tokens` are **not** sent —
  all four are rejected with a 400 on this model. Output variance therefore
  cannot be reduced by request parameters, which is an independent reason the
  deterministic suite runs on the mock (ADR-0206).
- `stop_reason == "refusal"` arrives as HTTP 200 with empty or partial content.
  The adapter checks it **before** reading content and raises a typed error;
  N10 turns that into a clean `FAILED` job rather than fabricated output.

### MockProvider

Implements both protocols with no network access: deterministic, validates its
canned payload against the caller's schema (so a drifted fixture fails the test),
and can be programmed to raise timeouts, return malformed JSON, or exhaust
retries — which is what makes N10's reliability tests possible offline.

`MockProvider` is **not** in `design-spec.md`; it is an inference from §32
(ADR-0206).

## Consequences

- Only `packages/ai_gateway` imports a vendor SDK — mechanically checkable, and
  the direct expression of §8.5 and §18 L1766.
- Every call is metered to `model_runs` (§15.8) including failures and refusals.
- The four deferred responsibilities are tracked, priority-tagged, and have a
  seam to land in.
