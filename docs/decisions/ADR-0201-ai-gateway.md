# ADR-0201 — AI gateway: provider interfaces, real adapter, and MockProvider

**Status:** Accepted (Phase 2, N1)
**Supersedes:** the Phase 0 `qe_ai_gateway` stub (`AIGateway`, `CompletionRequest`,
`CompletionResult`), which was an interface sketch with no provider.

> **Derivation note.** `docs/architecture/` contains only `.gitkeep` — the design
> spec cited as §8.5 / §18 is not in this repository and was not available to
> read. Every decision below is therefore *derived* from Phase 0/1 conventions
> plus mainstream defaults, not transcribed from a spec. Recorded per the Phase 2
> rule: where the design is silent, decide and write an ADR.

## Context

Phase 2 needs to call a real language model. Two constraints shape the design:

1. **No domain code touches a vendor SDK directly.** Only the gateway package may
   import `anthropic`. `qe_test_generation`, the API, and the worker depend on an
   interface, so swapping or adding a provider is a one-package change and the
   test suite never needs network access.
2. **Deterministic tests.** LLM output is non-deterministic. Every test outside
   the explicitly-marked evaluation suite must run against a stub.

## Decision

### Interfaces

`packages/ai_gateway/qe_ai_gateway/` defines two `typing.Protocol`s:

- **`LanguageModelProvider`** — `complete(request) -> CompletionResult` and
  `complete_structured(request, schema) -> StructuredResult[T]`, where `schema`
  is a Pydantic model class and the result carries a validated instance.
- **`EmbeddingProvider`** — `embed(texts) -> list[list[float]]`. Declared now so
  Phase 3's RAG work has a stable seam; the only Phase 2 implementation is the
  mock. `TODO(phase-3)` marks the real adapter.

Both are `Protocol`s rather than ABCs so a test double satisfies the type without
inheriting, and neither leaks a provider type into its signature.

### Chosen real provider

**Anthropic, model `claude-opus-5`, via the official `anthropic` Python SDK.**

- The repo already reserved `ANTHROPIC_API_KEY` in `.env.example`
  (`# TODO(phase-2): AI provider credentials`); no other provider is referenced
  anywhere in the codebase.
- `claude-opus-5` is the current default Opus. The model id is configurable
  (`AI_MODEL`), so pinning a different model is an env change, not a code change.
- Structured generation uses the SDK's `messages.parse(output_format=...)`,
  which constrains the response to a JSON schema and returns a validated Pydantic
  instance. This is what makes "structured-output validation against Pydantic
  schemas" a provider-enforced guarantee rather than a hopeful `json.loads`.
- Adaptive thinking is left at the model default (on for `claude-opus-5`).
  `temperature`/`top_p`/`top_k` and `thinking.budget_tokens` are **not** sent —
  all four are rejected with a 400 on this model. Determinism is therefore not
  available as a request parameter, which is a further reason the deterministic
  suite runs on the mock (ADR-0206).

### MockProvider

`MockProvider` implements both protocols with **no network access**:

- Deterministic: responses are keyed off the request, so the same input always
  yields the same output. Fixture responses are declared in the test, not
  guessed by the mock.
- Satisfies the same structured-output contract — it validates its canned payload
  against the caller's Pydantic schema, so a fixture that drifts from the schema
  fails the test instead of silently passing.
- Programmable failure: it can be told to raise a timeout, return malformed JSON,
  or exhaust retries, which is what makes N10's reliability tests possible
  without touching a real provider.

### Cross-cutting gateway behaviour

- **Retry with backoff.** The SDK retries connection errors, 408/409/429 and 5xx
  with exponential backoff (`max_retries`, default 2). The gateway sets it
  explicitly rather than inheriting a default, and adds its own bounded retry for
  the one case the SDK cannot see: a structurally invalid response body that
  fails schema validation. Non-retryable 4xx are never retried.
- **Per-call timeout.** Set explicitly on the client (seconds). Wall-clock worst
  case is `timeout × (max_retries + 1)`; the job framework's own bound is what
  ultimately protects the worker.
- **Refusals are handled before content is read.** `claude-opus-5` can return
  HTTP 200 with `stop_reason == "refusal"` and an empty/partial `content`.
  Reading `content[0]` unconditionally would crash. The gateway checks
  `stop_reason` first and raises a typed error, which N10 turns into a clean
  `FAILED` job rather than fabricated output.
- **Typed errors.** Provider exceptions are translated into `qe_common.errors`
  types at the gateway boundary, so callers never catch `anthropic.*`.
- **Every call is recorded.** Token counts, computed cost, latency, model,
  provider, purpose, stop reason and outcome are persisted to `model_runs`
  (ADR-0203) — including failed and refused calls, which are exactly the ones
  worth having a record of.

## Consequences

- Adding a second provider means one new adapter and one config value.
- The deterministic test suite needs no API key and makes no network call.
- Cost is attributable per organisation, per job, and per purpose from day one.
- The gateway is the only place that knows a vendor SDK exists — a rule that is
  mechanically checkable (`git grep -l anthropic` outside `packages/ai_gateway`
  must be empty apart from config and docs).
