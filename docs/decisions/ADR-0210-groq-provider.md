# ADR-0210 — Groq replaces Anthropic as the concrete provider

**Status:** Accepted (Phase 2, N4 patch)
**Amends:** ADR-0201 (provider choice), ADR-0209 (Decision 4)
**Unchanged:** the §18 interfaces, the `model_runs` schema, `MockProvider`, and
every boundary rule in ADR-0209 Decision 5

## Context

ADR-0201 selected Anthropic and `claude-opus-5` and was explicit that this was
an **inference, not a sourced fact** — `design-spec.md` never names a vendor;
§10.3 L591-592 requires only a *provider-neutral* interface and §18 L1728 says
the gateway "will isolate the application from a specific vendor". Swapping the
vendor is therefore the design working as specified, not a deviation from it.

`AnthropicProvider` and the `anthropic` dependency are **removed**. `GroqProvider`
is the only real adapter. This is the first real test of the provider-neutrality
claim, and it holds: no interface, no contract, and no table changed. What did
change is contained entirely in the adapter, and is recorded below because two
of the differences are semantic rather than mechanical.

All findings below were verified against the installed SDK and Groq's live
documentation, not assumed from the Anthropic adapter.

## Verified SDK surface — `groq==1.6.0`

| Question | Finding |
|---|---|
| Is there a `.parse()` equivalent? | **No.** `chat.completions.parse` does not exist; there is no `beta` namespace. |
| Structured-output mechanism | `response_format={"type": "json_schema", "json_schema": {"name", "schema", "strict"}}` |
| Client retry default | **`max_retries=2`** (`groq._constants.DEFAULT_MAX_RETRIES`) |
| Refusal signal | **None.** `finish_reason` is `Literal["stop","length","tool_calls","function_call"]`; `ChatCompletionMessage` has no `refusal` field. |
| Token fields | `prompt_tokens`, `completion_tokens`, `total_tokens`, `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens` |

## Decision 1 — Structured output: `json_schema` with `strict: true`

Groq offers three `response_format` types: `text`, `json_object`, and
`json_schema`. Only `json_schema` with `strict: true` uses **constrained
decoding**, which the documentation describes as guaranteeing "that the output
will always match your schema exactly". `json_object` mode enforces nothing
beyond "probably valid JSON".

**Decision: `json_schema` + `strict: true`.** ADR-0209 lists structured-output
validation as an implemented P0 responsibility; `json_object` would demote that
to a hope, and the Pydantic re-validation would then be the only real check.

This is **stronger** than what the Anthropic adapter had, not weaker — see
Consequences.

### The constraints strict mode imposes

Strict mode requires that every property is listed in `required` and that every
object sets `additionalProperties: false`. Pydantic's `model_json_schema()`
satisfies neither by default: optional fields are omitted from `required`, and
`additionalProperties` is simply absent.

The adapter therefore **post-processes the caller's schema** before sending it
(`_strictify`), walking every object node to add `additionalProperties: false`
and promote all properties to `required`. This is a transformation of the
*wire* schema only; validation on the way back still uses the caller's original
Pydantic model, so an optional field remains optional to the caller — the model
is merely required to emit the key (as `null`) rather than omit it.

### Model support is narrow, and it constrains the default

`strict: true` is supported on **`openai/gpt-oss-120b`** and
**`openai/gpt-oss-20b`** only. The default model is therefore
**`openai/gpt-oss-120b`** (`AI_MODEL`), the more capable of the two.

**Consequence worth stating:** on this provider, model choice and
structured-output strength are coupled. Pointing `AI_MODEL` at, say,
`llama-3.3-70b-versatile` silently drops constrained decoding and leaves
Pydantic re-validation as the only guarantee. The adapter logs a warning when
configured with a model outside the strict-capable set rather than failing,
because a non-strict model is a degraded-but-working configuration, not an
invalid one.

## Decision 2 — Token classes: three, not four, and one is a *subset*

This is the finding that actually affects correctness.

| `TokenUsage` field | Groq source | Notes |
|---|---|---|
| `input_tokens` | `prompt_tokens − cached_tokens` | **normalised — see below** |
| `output_tokens` | `completion_tokens` | |
| `cache_read_input_tokens` | `prompt_tokens_details.cached_tokens` (0 when absent) | |
| `cache_creation_input_tokens` | **always 0** | Groq has no cache-write concept or charge |

### `cached_tokens` is a subset of `prompt_tokens`

Groq's documentation is explicit that `cached_tokens` counts tokens *within*
`prompt_tokens`, and that cached tokens receive a 50% discount. Anthropic's
`cache_read_input_tokens` is the opposite: a **separate** count, disjoint from
`input_tokens`.

`estimate_cost` sums the four classes independently, which is correct only if
they are disjoint. Mapping `input_tokens = prompt_tokens` directly would bill
every cached token **twice** — once at full rate inside `prompt_tokens` and
again at the cache rate.

**Decision: the adapter normalises to disjoint classes** by subtracting:
`input_tokens = prompt_tokens − cached_tokens`. `TokenUsage` keeps one meaning
across every provider — "counts that may be summed at their own rates" — and
each adapter is responsible for expressing its vendor's representation in those
terms. `total_tokens` still reconciles to Groq's own total:
`(prompt − cached) + completion + cached + 0 = prompt + completion`.

`estimate_cost` and the `model_runs` schema are therefore **unchanged**. No
migration is required, and `model_runs.input_token_count` continues to mean
"tokens billed at the full input rate" on both providers.

### No schema change; the cache columns stay NOT NULL

The patch brief asked whether the cache columns must become nullable. **They
must not, and nothing changes.** They are already `NOT NULL DEFAULT 0` from
migration `0005`, and 0 is the honest value for a provider with no cache-write
concept — writing NULL would say "unknown" when the answer is "none". Migration
`0006` remains the head; no `0007` is introduced by this patch.

### `reasoning_tokens` is deliberately not priced — open item

`completion_tokens_details.reasoning_tokens` exists on the gpt-oss models.
Groq's reasoning and pricing documentation **does not state** whether it is a
subset of `completion_tokens` or an additional count, and I did not find an
authoritative answer.

The adapter therefore treats `completion_tokens` as the authoritative output
count and does not add `reasoning_tokens` to it. Under the standard
OpenAI-compatible convention (subset) this is exactly right; if Groq instead
counted it separately, `estimated_cost` would *understate* output cost on
reasoning-heavy calls. It is recorded nowhere else because `model_runs` has no
column for it and inventing one to hold an unpriced, ambiguous number would add
a schema change for no decision.

**Open item:** reconcile `estimated_cost` against a real Groq invoice before
Phase 6 evaluation work depends on cost roll-ups.

## Decision 3 — Retry and exception mapping

**`max_retries=0` on the client.** Groq's SDK defaults to 2. The reasoning is
unchanged from the Anthropic adapter and from ADR-0203: with both loops active,
one logical call makes up to `attempts × SDK-retries` requests and
`model_runs.attempts` under-reports by the SDK's factor. The gateway owns
retries so the audit column stays true.

| Groq exception | HTTP | Mapped to | Retried |
|---|---|---|---|
| `APITimeoutError` | — | `GatewayTimeoutError` | **yes** |
| `RateLimitError` | 429 | `RetryableProviderError` | **yes** |
| `InternalServerError` / `APIStatusError` ≥ 500 | 500/502/503 | `RetryableProviderError` | **yes** |
| `APIStatusError` 408 / 409 | 408/409 | `RetryableProviderError` | **yes** |
| `APIConnectionError` | — | `RetryableProviderError` | **yes** |
| `BadRequestError` | 400 | `ProviderError` | no |
| `UnprocessableEntityError` | 422 | `ProviderError` | no |
| `AuthenticationError` / `PermissionDeniedError` | 401/403 | `ProviderError` | no |
| Schema violation after parse | — | `ProviderResponseInvalidError` | no |
| `finish_reason == "length"` | — | `ProviderResponseInvalidError` | no |

Retryability remains expressed as an **exception type**, not a status-code check
inside the retry loop, exactly as ADR-0209 established.

`finish_reason == "length"` is called out because it is a structured-output
failure mode with no Anthropic analogue in the old adapter: a truncated response
yields syntactically incomplete JSON. Treating it as a schema violation (rather
than letting `json.loads` fail with a confusing message) makes the cause legible
in `model_runs.error_code`.

### Groq has no refusal — name it plainly

**Groq exposes no refusal signal.** Verified structurally: `finish_reason` has no
`"refusal"` literal and `ChatCompletionMessage` has no `refusal` field. The
error documentation lists no content-moderation-specific status or error type;
the nearest is a generic 422 ("semantic errors or model hallucinations"), which
is not a refusal.

**Decision: `GroqProvider` never raises `ProviderRefusalError`.** A content-policy
rejection, if one occurs, arrives as a non-retryable 4xx and is recorded as
`FAILED` / `PROVIDER_ERROR` — that is Groq's equivalent, and it is what the
re-gate exercises.

Guessing at an undocumented error string to synthesise a `REFUSED` status would
put a fabricated distinction into the audit record. `ModelRunStatus.REFUSED`
stays in the vocabulary — the column, the enum, and `MockProvider` all keep it,
so N10 can still exercise the path and a future provider that *does* signal
refusals needs no schema change — but on Groq it is unreachable, and
`model_runs` will simply never show it.

## Decision 4 — Pricing table

Source: <https://groq.com/pricing>, retrieved 2026-07-31. Per **million** tokens,
USD.

| Model | Input | Cached input | Output | Cache write |
|---|---|---|---|---|
| `openai/gpt-oss-120b` *(default)* | $0.15 | $0.075 | $0.60 | $0 |
| `openai/gpt-oss-20b` | $0.075 | $0.0375 | $0.30 | $0 |
| `moonshotai/kimi-k2-instruct-0905` | $1.00 | $0.50 | $3.00 | $0 |
| `llama-3.3-70b-versatile` | $0.59 | $0.59 † | $0.79 | $0 |
| `llama-3.1-8b-instant` | $0.05 | $0.05 † | $0.08 | $0 |
| `qwen/qwen3.6-27b` | $0.60 | $0.60 † | $3.00 | $0 |

† No cached-input price is published for these models. The table assumes **no
discount** (cache rate = input rate) rather than inferring the 50% that the
gpt-oss models get. An assumed discount would understate cost; assuming none can
only overstate it, and overstating is the safe direction for a budget ceiling
(`max_generation_cost_usd`, ADR-0208).

Cache-write is $0 across the board: Groq states prompt caching is provided at no
additional cost.

An unpriced model still raises `UnknownModelError` rather than recording `0.00`
(ADR-0209 unchanged) — a silent zero is indistinguishable from a free call.

## Consequences

- **Provider-neutrality held.** Swapping vendors changed no interface, no
  contract, no table, and no migration. The §18 ABCs, `StructuredGenerationRequest`
  / `Response`, `TokenUsage`, the recorder, and every ADR-0209 boundary are
  untouched.
- **Structured output is now genuinely enforced.** Constrained decoding is a
  stronger guarantee than the previous adapter's post-hoc validation — but it is
  **conditional on the model**, which is new coupling that N5+ must respect.
- **`ModelRunStatus.REFUSED` is unreachable in production** until a provider that
  signals refusals is added. Analysis over `model_runs` must not read its absence
  as "no refusals ever happened".
- **Cost accuracy depends on one unverified assumption** — that
  `reasoning_tokens ⊆ completion_tokens`. Flagged above as an open item.
- The adapter now **transforms the caller's JSON schema** on the way out. A
  schema Pydantic accepts may be rejected by strict mode (notably `$ref`/`$defs`
  from nested models, which are not exercised yet); N5 will be the first caller
  with a non-trivial schema and should validate this early.
