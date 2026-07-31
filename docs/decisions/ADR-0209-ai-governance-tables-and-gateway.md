# ADR-0209 — AI governance tables, prompt lifecycle, and gateway boundaries

**Status:** Accepted (Phase 2, N3+N4)
**Extends:** ADR-0201 (gateway), ADR-0203 (schema)
**Supersedes in part:** ADR-0202 — see "Relationship to ADR-0202" below

## Sources

| Claim | Spec |
|---|---|
| `prompt_versions` columns | §15.8 L1542–1551 |
| `model_runs` columns | §15.8 L1527–1540 |
| `model_runs.prompt_version_id` references `prompt_versions` | §15.8 L1533 |
| Gateway interface signatures | §18 L1732–1748 |
| Thirteen gateway responsibilities | §18 L1750–1764 |
| Domain modules call the gateway, not a provider SDK | §18 L1766 |
| Seven-stage prompt lifecycle | §19 L1791–1807 |
| Twelve per-version fields | §19 L1774–1787 |
| No production deploy without evaluation | §19 L1789 |
| Backend module list (AI Provider Gateway, Prompt Management are separate) | §12.2 L1090–1091 |
| No provider calls directly from controllers | §37 L2745 |
| Prompt versioning is P1; model fallback is P1 | §39 L2905, L2907 |

## Context

Three prior decisions constrain this one, and one of them has to give.

**ADR-0203 already created `model_runs`** in migration `0005` (committed `38101e0`,
N2 gate PASS). Its §15.8 column coverage was verified 12/12. `0006` therefore
**does not create `model_runs`** — doing so would raise `DuplicateTable` and the
migration would never apply. `0006` adds the one thing `0005` is missing: an
index on `prompt_version_id`.

**ADR-0202 deferred `prompt_versions` and the seven-stage lifecycle** to the P1
prompt-versioning work (§39 L2907), and committed to prompts being
"source-resident, git-versioned" with "no runtime mutation of prompt text".
Phase 2 now builds the table and the lifecycle. That is a deliberate scope
change, recorded below rather than left as a silent contradiction.

**PHASE2-PLAN.md separates N3 (`qe_ai_gateway`) from N4 (`qe_prompt_registry`).**
This ADR covers both, because the prompt registry is the only thing that can
legitimately produce a `prompt_version_id`, and shipping the gateway without it
would leave that column to be filled by whatever the caller invents — exactly
the hazard ADR-0203 flagged.

## Relationship to ADR-0202

ADR-0202 stands except for three bullets, superseded here:

| ADR-0202 said | Now |
|---|---|
| `prompt_versions` table deferred to P1 | **Built in Phase 2** (this ADR) |
| Seven-stage lifecycle deferred to P1 | **Built in Phase 2** (this ADR) |
| `model_runs.prompt_version_id` as an FK deferred to P1 | **Still deferred** — unchanged, and reinforced below |

**ADR-0202's source-of-truth commitment is preserved, not superseded.** Prompt
template text remains source-resident and git-versioned. `prompt_versions` is a
**registry mirror**: it records which source-resident templates exist, what
lifecycle stage each has reached, and who moved it there. `create_version()`
registers a template that already exists in source; it never invents prompt text.

This matters because §19 L1772 calls prompts "version-controlled application
assets", and a prompt body that lives only in a database row is not
version-controlled — it does not appear in a diff, a review, or a revert. The
lifecycle state, by contrast, is genuinely runtime state and belongs in a table.
Splitting on that line keeps both properties.

The mirror is verified, not assumed: `template_checksum` holds the SHA-256 of
the source template, and a mismatch between row and source is an error at
startup rather than a silent divergence.

## Decision 1 — `prompt_versions` (§15.8 L1542–1551)

Spec columns, kept verbatim: `id`, `prompt_name`, `version`, `template`,
`schema_version`, `status`, `created_by`, `created_at`.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `Uuid` PK, `gen_random_uuid()` | no | |
| `prompt_name` | `String(64)` | no | e.g. `testgen` |
| `version` | `String(64)` | no | e.g. `testgen-v3` — the exact string `model_runs.prompt_version_id` holds |
| `template` | `Text` | no | mirror of the source-resident template |
| `schema_version` | `String(32)` | no | version of the output contract, e.g. `1` |
| `status` | `String(32)`, default `DRAFT` | no | CHECK-constrained, see Decision 3 |
| `created_by` | `Uuid` FK → `users.id` `ON DELETE SET NULL` | yes | null for system-seeded versions |
| `created_at` | `DateTime(tz)`, `now()` | no | |

Additions (derived, not in §15.8):

| Column | Why |
|---|---|
| `updated_at` | status transitions mutate the row; every other mutable table carries it |
| `template_checksum` | `String(64)` — SHA-256 of the source template; makes the git-mirror claim checkable rather than asserted |

**No `organisation_id`.** This is the only Phase 2 table without one, and the
omission is deliberate: prompts are platform assets, not tenant data. ADR-0202
deferred per-organisation prompt overrides, and §19 is silent on prompt
multi-tenancy. Adding a tenant column now would imply an isolation guarantee
Phase 2 does not implement. When per-tenant prompts arrive, they arrive as a
migration and an explicit decision, not as a column that was quietly always there.

### Version string format

```
{prompt_name}-v{n}        n a positive integer, no leading zero
^[a-z][a-z0-9_]*-v[1-9][0-9]*$
```

Validated in the service layer on `create_version()`, and the `prompt_name`
embedded in `version` must equal the `prompt_name` column — a row claiming
`prompt_name="testgen"` with `version="codegen-v1"` is rejected.

### Constraints

| Constraint | Shape | Why |
|---|---|---|
| `uq_prompt_versions_name_version` | `UNIQUE (prompt_name, version)` | a version identifier is unique within its prompt — the identity `model_runs` points at |
| `uq_prompt_versions_one_active` | `UNIQUE (prompt_name) WHERE status = 'ACTIVE'` | **at most one active version per prompt**, enforced by the database |
| `ck_prompt_versions_status` | `CHECK (status IN (...seven states...))` | see Decision 3 |

The composite unique is partially redundant given the format rule (a valid
`version` already embeds its `prompt_name`), but it is what §15.8's shape implies
and it holds even if the format rule is ever relaxed. Recorded as intentional
redundancy rather than left to look like an oversight.

The **partial unique index is the load-bearing one**. `get_active(prompt_name)`
must return exactly one row; without it, two concurrent activations could both
commit and every later generation would silently pick one at random.

### Indexes

| Index | Columns |
|---|---|
| `ix_prompt_versions_name_status` | `(prompt_name, status)` — the `get_active` and `list_versions` access path |
| `uq_prompt_versions_name_version` | unique, above |
| `uq_prompt_versions_one_active` | partial unique, above |

## Decision 2 — `model_runs`: `prompt_version_id` stays a string

**Hard constraint, inherited from ADR-0203 and reaffirmed:
`model_runs.prompt_version_id` is `String(64)` holding
`prompt_versions.version` (e.g. `"testgen-v3"`). It is NOT a foreign key to
`prompt_versions.id`, and `0006` must not add one.**

The table already exists from `0005` with all twelve §15.8 columns. `0006`
changes exactly one thing:

```
CREATE INDEX ix_model_runs_prompt_version_id ON model_runs (prompt_version_id);
```

`0005` indexes `organisation_id+created_at`, `job_id`, and `request_id`, but not
`prompt_version_id` — and "which runs used prompt version X" is the query that
justifies the column existing at all (§19 L1789 evaluation, cost attribution per
version).

### Why not an FK now

Adding one would mean either retyping the column to `Uuid` (breaking the ADR-0203
seam and every row `0005` can already accept) or an FK to a non-unique target.
Neither is a Phase 2 problem worth creating. The string is forward-compatible;
a UUID written today would not be.

### What the future FK migration will need

Recorded now, because the backfill is the hard part and it is cheapest to
constrain the data while it is still small:

1. **Precondition** — `prompt_versions.version` must be globally unique, not just
   unique per `prompt_name`. The format rule already guarantees this; the
   migration must *verify* it (`SELECT version, count(*) ... HAVING count(*) > 1`)
   rather than assume it.
2. **Add** `prompt_version_uuid Uuid NULL` alongside the existing column.
3. **Backfill** — `UPDATE model_runs m SET prompt_version_uuid = p.id FROM
   prompt_versions p WHERE p.version = m.prompt_version_id`.
4. **Verify, and do not proceed silently** — count rows where
   `prompt_version_id IS NOT NULL AND prompt_version_uuid IS NULL`. These are
   strings that were never registry identifiers. The migration must **report
   the count and fail** rather than NULL them out; a run whose prompt provenance
   cannot be resolved is exactly the record governance exists to keep.
5. **Swap** — drop `prompt_version_id`, rename `prompt_version_uuid` to
   `prompt_version_id`, add the FK with `ON DELETE RESTRICT` (a prompt version
   with runs attributed to it must not be deletable).

Step 4 is why Decision 5 forbids the gateway from constructing this value.

## Decision 3 — Lifecycle: DB enforces the vocabulary, the service enforces the order

§19 L1791–1807 specifies seven stages:

```
DRAFT → OFFLINE_EVALUATION → REVIEW → STAGING → LIMITED_RELEASE → ACTIVE → DEPRECATED
```

### The decision

**Both layers, at different levels — and the split is forced, not stylistic.**

| Layer | Enforces | Mechanism |
|---|---|---|
| Database | the *set* of legal values | `CHECK (status IN (...))` |
| Service | the *ordering* between values | `transition_status()` |

**A CHECK constraint structurally cannot enforce the ordering.** It sees only the
row being written, never the row being replaced, so it cannot express
"`DRAFT` → `ACTIVE` is illegal" — that requires the previous value. Only a
trigger could, and a trigger puts business rules in a place no reader of
`qe_prompt_registry` will look, that unit tests cannot exercise without a
database, and that a future migration can silently drop.

So the DB catches what it can catch cheaply and completely — a typo, a rogue
script, a future module writing `"active"` instead of `"ACTIVE"` — and the
service owns the rule that needs history.

### The tradeoff, stated plainly

Ordering is enforced only for writers that go through `qe_prompt_registry`.
A direct `UPDATE prompt_versions SET status='ACTIVE'` against the database
bypasses it. This is accepted because the alternative — a trigger — trades a
visible, testable Python state machine for an invisible one, and because the
partial unique index still holds the invariant that actually matters at
generation time (at most one `ACTIVE` per prompt) no matter who writes the row.

### `String` + CHECK, not a native PG enum

Adding a state to a native enum is `ALTER TYPE ... ADD VALUE`, which has
transaction restrictions and no clean removal; adding one to a CHECK is an
ordinary `DROP CONSTRAINT` / `ADD CONSTRAINT` in a normal migration. Every other
status column in this codebase (`jobs.state`, `generated_test_cases.human_status`)
is already `String` + a `qe_common` `StrEnum`, and a second pattern for the same
job is not worth the inconsistency.

### Legal transitions

Forward, one step at a time:

| From | To |
|---|---|
| `DRAFT` | `OFFLINE_EVALUATION` |
| `OFFLINE_EVALUATION` | `REVIEW` |
| `REVIEW` | `STAGING` |
| `STAGING` | `LIMITED_RELEASE` |
| `LIMITED_RELEASE` | `ACTIVE` |
| `ACTIVE` | `DEPRECATED` |
| `DEPRECATED` | — terminal |

Everything else raises. `DRAFT → ACTIVE` is rejected; so is `ACTIVE → STAGING`,
`DEPRECATED → ACTIVE`, and any self-transition.

**No backward edges.** §19 draws a linear pipeline with none, and a rejected
prompt does not need one: ADR-0202 makes versions **immutable**, so the response
to "review rejected this" is to register a new version, not to reopen the old
one. That keeps the audit trail — `testgen-v3` stayed in `REVIEW` forever and
`testgen-v4` shipped — which a rollback edge would erase.

**Activation is atomic.** Promoting a version to `ACTIVE` demotes the current
`ACTIVE` version of the same `prompt_name` to `DEPRECATED` in the same
transaction. Without that, the partial unique index would reject the promotion
and the caller would have to run a two-step dance that can fail halfway.

### What is not enforced

§19 L1789 — "prompt changes must not be deployed to production without
evaluation" — is **not enforced in Phase 2**. `OFFLINE_EVALUATION → REVIEW`
records that the stage was passed; nothing verifies an evaluation actually ran,
because the §33 evaluation framework is Phase 6 (ADR-0202). The lifecycle makes
the gate *representable* now and *enforceable* later. Recorded as a known
shortfall against §19 L1789, not as compliance with it.

## Decision 4 — Gateway: what N3 implements now

Interfaces are taken from §18 L1732–1748 verbatim, as ADR-0201 already locked:

```python
class LanguageModelProvider(ABC):
    async def generate_structured(
        self, request: StructuredGenerationRequest
    ) -> StructuredGenerationResponse: ...

class EmbeddingProvider(ABC):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

All thirteen §18 L1750–1764 responsibilities, matching ADR-0201's table:

| Responsibility | Phase 2 |
|---|---|
| Authentication | implemented — key from `Settings`, never logged |
| Request formatting | implemented |
| Timeout handling | implemented — explicit per-call timeout |
| Retry handling | implemented — bounded, exponential backoff, non-retryable 4xx never retried |
| Structured-output validation | implemented — response validated against the caller's Pydantic model |
| Token counting | implemented — from the provider's `usage`, persisted to `model_runs` |
| Cost estimation | implemented — per-model rate table → `model_runs.estimated_cost` |
| Logging | implemented — structured, plus a `model_runs` row per call |
| Metrics | implemented **as structured log fields** — see below |
| Model fallback | **deferred — P1 (§39 L2905)**; provider is injected, the chain is not built |
| Provider-health checks | **deferred — `TODO(phase-7)`** |
| Circuit breaking | **deferred — `TODO(phase-7)`** |
| Rate limiting | **deferred — `TODO(phase-7)`**; the SDK's own 429 backoff covers Phase 2 |

Deferred items get an interface shape and a named TODO, not a silent omission.

### Correction to ADR-0201: there is no metrics package

ADR-0201 records Metrics as "implemented — counters/latency via the Phase 0
observability package". **`qe_observability` exports logging only** —
`get_logger`, `bind_log_context`, `configure_logging`, `JsonLogFormatter`. There
are no counters and no latency histograms, and OpenTelemetry is P1 (§39 L2908).

Phase 2 therefore emits latency, token counts, and cost as **structured fields on
the per-call log record**, which the Phase 0 JSON formatter already carries. That
is a real, queryable signal; it is not a metrics backend, and this ADR does not
claim it is one. Building a counter API for one caller would be inventing
infrastructure ahead of a P1 decision.

### `model_runs` is written on every call — success, failure, and refusal

The row is the audit record, so the failure paths are the ones that matter:

| Outcome | `status` | `error_code` | Row written |
|---|---|---|---|
| Success | `SUCCEEDED` | null | yes |
| Provider 4xx/5xx after retries | `FAILED` | provider error type | yes |
| Timeout | `FAILED` | `timeout` | yes |
| Schema validation failed | `FAILED` | `schema_validation_failed` | yes |
| `stop_reason == "refusal"` | `REFUSED` | refusal category | yes |

`attempts` records the retry count. A raised exception never replaces the row —
the row is written first, then the typed error propagates with context. **No
`except: pass`**: every catch either re-raises with context or writes an
`error_code`, per ADR-0201 and the N3 brief.

`stop_reason` is checked **before** reading content (a refusal arrives as HTTP
200 with empty or partial content), and its value lands in `model_runs.stop_reason`
— the derived column ADR-0203 added for exactly this.

### Cost estimation

A per-model rate table in configuration, not a hardcoded constant, because rates
change without code changing. For `claude-opus-5`: **$5.00 / MTok input,
$25.00 / MTok output**. Cached input is billed differently — reads at roughly
0.1× the input rate, 5-minute-TTL writes at 1.25× — which is precisely why
ADR-0203 added `cache_read_input_tokens` and `cache_creation_input_tokens` as
derived columns. `estimated_cost` sums all four token classes at their own rates;
computing it from `input_token_count` and `output_token_count` alone would be
wrong on any cached call.

The name is honest: it is an *estimate* from a local rate table, not a billing
figure from the provider.

### Provider parameters

`temperature`, `top_p`, `top_k` and `thinking.budget_tokens` are **not sent** —
all four are rejected with a 400 on `claude-opus-5`. Thinking is on by default on
this model. This is the independent reason ADR-0206's deterministic suite runs on
`MockProvider`: output variance cannot be reduced by request parameters.

### MockProvider is in scope

The N3 brief omits it; ADR-0201 specifies it and `PHASE2-PLAN.md:43` lists it
under N3. It stays in scope, because ADR-0206's deterministic tier — the default
CI job — has nothing to run against without it. Implements both protocols, no
network, validates its canned payload against the caller's schema, and can be
programmed to time out, return malformed JSON, or exhaust retries.

## Decision 5 — Package boundaries

Two packages, matching §12.2's separate "AI Provider Gateway" and
"Prompt Management" modules:

```
packages/ai_gateway/qe_ai_gateway/       interfaces, AnthropicProvider, MockProvider
packages/prompt_registry/qe_prompt_registry/   CRUD + lifecycle for prompt_versions
```

`packages/ai_gateway/qe_ai_gateway/__init__.py` currently holds the Phase 0 stub
(`AIGateway`, `CompletionRequest`, `complete()`, sync `embed(text)`), which does
not match §18. ADR-0201 supersedes it; N3 replaces it.

### What each depends on

| Package | Exposes to these two |
|---|---|
| `qe_database` | `Base`, `ModelRun`, `PromptVersion`, `get_session` / `get_async_session` |
| `qe_observability` | `get_logger`, `bind_log_context`, `LogContext` |
| `qe_common` | `get_settings` / `Settings`, the shared `StrEnum` vocabularies |

### Table ownership — no cross-module DB queries (§12.2)

| Table | Owner | Everyone else |
|---|---|---|
| `prompt_versions` | `qe_prompt_registry` | via its service functions |
| `model_runs` | `qe_ai_gateway` | via its recorder |

**`qe_ai_gateway` never queries `prompt_versions`.** It receives
`prompt_version_id` as a parameter from its caller and writes it through
unmodified. This is the boundary that makes ADR-0203's hazard survivable: the
gateway *cannot* invent a version string, because it has no access to the table
that would let it guess at one, and no reason to construct one.

The resolution path is therefore:

```
N5 pipeline
  → qe_prompt_registry.get_active("testgen")  → PromptVersion.version
  → qe_ai_gateway.generate_structured(..., prompt_version_id=<that string>)
  → model_runs row
```

Neither package imports the other, in either direction — no cycle, and the
dependency that would create one (gateway → registry) is the one forbidden above.

Per §37 L2745 and §18 L1766, **only `qe_ai_gateway` imports the `anthropic` SDK.**
Mechanically checkable, and checked in N3's tests.

### Session handling

The gateway does not own transaction boundaries. It writes `model_runs` through
an injected recorder; the default implementation uses `qe_database`, and tests
use an in-memory one. The gateway is `async` per §18 while the Phase 1 worker is
sync Celery (ADR-0204) — that sync/async bridge happens once at the N5 pipeline
entry point, not per provider call.

## Migration plan — `0006_ai_governance`

`down_revision = "0005_testgen"`.

### Table order

One new table. `prompt_versions` before the `model_runs` index — no dependency
between them, but the new table is the substantive change and reads first.

1. `CREATE TABLE prompt_versions` (with the `CHECK` on `status` inline)
2. `uq_prompt_versions_name_version` — `UNIQUE (prompt_name, version)`
3. `uq_prompt_versions_one_active` — `UNIQUE (prompt_name) WHERE status='ACTIVE'`
4. `ix_prompt_versions_name_status` — `(prompt_name, status)`
5. `ix_model_runs_prompt_version_id` on the **existing** `model_runs` table

### Index list

| Index | Table | Kind |
|---|---|---|
| `uq_prompt_versions_name_version` | `prompt_versions` | unique |
| `uq_prompt_versions_one_active` | `prompt_versions` | partial unique (`WHERE status='ACTIVE'`) |
| `ix_prompt_versions_name_status` | `prompt_versions` | btree |
| `ix_model_runs_prompt_version_id` | `model_runs` | btree |

### Downgrade

Exact reverse: drop `ix_model_runs_prompt_version_id`, then the three
`prompt_versions` indexes/constraints, then `DROP TABLE prompt_versions`.
`model_runs` must survive the downgrade — it belongs to `0005`.

### What `--autogenerate` is expected to produce

**Empty for the two Phase 2 governance tables.** Specifically:

- Nothing for `prompt_versions` — the ORM model matches the migration
  column-for-column, including the CHECK and both unique constraints.
- Nothing for `model_runs` — the ORM model is unchanged from `0005` except for
  the new `Index` entry in `__table_args__`, which `0006` creates.
- **Nothing that adds a ForeignKeyConstraint on `model_runs.prompt_version_id`.**
  If autogenerate ever proposes one, the ORM model has drifted and the fix is the
  model, not the migration.
- The four **pre-existing Phase 0/1 drift items** ADR-0203 logged as backlog —
  `ix_projects_organisation_id`, `ix_repositories_project_id`,
  `ix_users_organisation_id`, `uq_user_roles` — will still appear. They are out
  of scope, reported not fixed, and their continued presence (exactly four, no
  more) is itself a gate check.

Alembic does not autogenerate partial indexes reliably; the N3 gate verifies
`uq_prompt_versions_one_active` by querying `pg_indexes` for its definition
rather than trusting an empty diff alone.

## Consequences

- Every `model_runs` row traces to an exact, immutable prompt version; every
  prompt version traces to a git-versioned source template via `template_checksum`.
- At most one `ACTIVE` version per prompt is a **database** guarantee, so
  `get_active()` cannot silently pick between two.
- Lifecycle *ordering* is guaranteed only for writers using
  `qe_prompt_registry` — stated in Decision 3, not papered over.
- §19 L1789's evaluation gate is representable but not enforced until Phase 6.
- `prompt_version_id` remains a string. The hazard is unchanged, the boundary in
  Decision 5 is what contains it, and the backfill this defers is specified
  above rather than left to be rediscovered.
