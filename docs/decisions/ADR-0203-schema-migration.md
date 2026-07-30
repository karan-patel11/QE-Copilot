# ADR-0203 — Schema: test_generation_requests, generated_test_cases, model_runs

**Status:** Accepted (Phase 2, N1)

> **Derivation note.** The spec cited as §15.6 (schema) and §15.8 (model runs) is
> not in this repository — `docs/architecture/` holds only `.gitkeep`. The column
> sets below are *derived* from what Phase 2's pipeline and API demonstrably
> need, under the Phase 0/1 conventions already in the codebase. They are a
> decision, not a transcription.
>
> **Retracted contradiction (corrected).** An earlier revision of this ADR
> claimed §15.8 was self-contradictory because Phase 1's brief cited it for
> `audit_logs` and Phase 2's cites it for `model_runs`. **That was wrong.** Both
> tables are specified as separate tables under the same subsection; there is no
> collision. The outcome is unchanged — `audit_logs` keeps its table from
> migration `0004`, `model_runs` is created here as its own — but it follows from
> the design, not from treating a section number as unreliable.
>
> Source of that correction: maintainer statement, **not** yet verified against
> `docs/architecture/design-spec.md`, which is still absent. Re-confirm during
> the source-verification pass.

## Context

Phase 1 established the conventions these tables must follow: UUID primary keys
via `gen_random_uuid()`, `created_at`/`updated_at` managed by the database,
`organisation_id` on every row as the tenant boundary (ADR-0106), `ON DELETE
CASCADE` to the tenant with `passive_deletes=True` on the ORM relationship, and
`ON DELETE SET NULL` for actor references so history outlives its actor.

## Decision

Three tables, added by **migration `0005`** on top of `0004_audit`.

### `test_generation_requests`

One row per generation request — the unit the API creates and the client polls.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `organisation_id` | UUID NOT NULL | FK `organisations` CASCADE — tenant boundary |
| `project_id` | UUID NOT NULL | FK `projects` CASCADE — generation is project-scoped |
| `repository_id` | UUID NULL | FK `repositories` SET NULL — optional source repo |
| `job_id` | UUID NULL | FK `jobs` SET NULL — the Phase 1 job executing this |
| `requested_by` | UUID NULL | FK `users` SET NULL — outlives the user |
| `title` | VARCHAR(255) NOT NULL | |
| `source_type` | VARCHAR(32) NOT NULL | which input source produced `requirement_text` |
| `requirement_text` | TEXT NOT NULL | **untrusted data** — see ADR-0205 / N9 |
| `framework` | VARCHAR(32) NOT NULL | `pytest` in Phase 2 |
| `status` | VARCHAR(32) NOT NULL | mirrors `JobState`; default `PENDING` |
| `config` | JSONB NOT NULL | generation options (`max_cases`, test types) |
| `prompt_version` | VARCHAR(64) NULL | the ADR-0202 version that produced the output |
| `error` | TEXT NULL | populated on failure |
| `summary` | JSONB NULL | per-request counts (generated / valid / duplicate) |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL | |

Indexes: `(organisation_id, created_at)`, `(project_id)`, `(job_id)`, `(status)`.

`status` mirrors `qe_common.jobs.JobState` rather than inventing a second
vocabulary — the request is executed *by* a job (ADR-0204), so one state machine
governs both and the request row stays self-describing for polling.

### `generated_test_cases`

One row per generated test case. This is the reviewable unit.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `request_id` | UUID NOT NULL | FK `test_generation_requests` CASCADE |
| `organisation_id` | UUID NOT NULL | FK `organisations` CASCADE — denormalised so tenant filtering needs no join |
| `ordinal` | INTEGER NOT NULL | stable display order within the request |
| `title` | VARCHAR(255) NOT NULL | |
| `description` | TEXT NULL | |
| `test_type` | VARCHAR(32) NOT NULL | `unit` / `integration` / `edge_case` / `negative` |
| `priority` | VARCHAR(16) NOT NULL | `P0`–`P3` |
| `framework` | VARCHAR(32) NOT NULL | `pytest` |
| `code` | TEXT NOT NULL | generated source — **never executed** (ADR-0205) |
| `status` | VARCHAR(32) NOT NULL | `PENDING_REVIEW` / `APPROVED` / `REJECTED`; default `PENDING_REVIEW` |
| `validation_status` | VARCHAR(32) NOT NULL | `PASSED` / `FAILED` |
| `validation_errors` | JSONB NOT NULL | `[{check, message}]`; empty list when clean |
| `duplicate_of` | UUID NULL | self-FK SET NULL — near-duplicate of another case |
| `duplicate_score` | DOUBLE PRECISION NULL | similarity that produced the link |
| `is_edited` | BOOLEAN NOT NULL | true once a human edits the code |
| `reviewed_by` | UUID NULL | FK `users` SET NULL |
| `reviewed_at` | TIMESTAMPTZ NULL | |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL | |

Indexes: `(request_id, ordinal)`, `(organisation_id, created_at)`, `(status)`.

**`status` defaults to `PENDING_REVIEW`, never `APPROVED`.** Nothing
auto-approves; approval is always an explicit, audited human action (N7).

### `model_runs`

One row per provider call — including failures and refusals.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `organisation_id` | UUID NOT NULL | FK `organisations` CASCADE |
| `project_id` | UUID NULL | FK `projects` CASCADE |
| `job_id` | UUID NULL | FK `jobs` SET NULL |
| `request_id` | UUID NULL | FK `test_generation_requests` CASCADE |
| `provider` | VARCHAR(32) NOT NULL | `anthropic` / `mock` |
| `model` | VARCHAR(128) NOT NULL | e.g. `claude-opus-5` |
| `purpose` | VARCHAR(64) NOT NULL | e.g. `test_generation.decompose` |
| `prompt_version` | VARCHAR(64) NULL | ADR-0202 version |
| `input_tokens`, `output_tokens` | INTEGER NOT NULL | default 0 |
| `cache_read_input_tokens`, `cache_creation_input_tokens` | INTEGER NOT NULL | default 0 |
| `cost_usd` | NUMERIC(12,6) NOT NULL | computed from a per-model rate table |
| `latency_ms` | INTEGER NULL | measured, not estimated |
| `status` | VARCHAR(32) NOT NULL | `SUCCEEDED` / `FAILED` / `REFUSED` |
| `stop_reason` | VARCHAR(32) NULL | provider stop reason, incl. `refusal` |
| `error_code` | VARCHAR(64) NULL | `qe_common.errors.ErrorCode` value |
| `attempts` | INTEGER NOT NULL | default 1 — retries are visible |
| `created_at` | TIMESTAMPTZ NOT NULL | immutable; **no `updated_at`** |

Indexes: `(organisation_id, created_at)`, `(job_id)`, `(request_id)`.

Like `audit_logs`, a `model_run` is an immutable record — written once, never
updated. **No prompt or response text is stored** (ADR-0205 / N9): the row
carries metering and provenance, not content, so a requirement containing
sensitive data is not duplicated into a second table.

### Tenancy

All three tables are rooted at `organisations` through `ON DELETE CASCADE`, so
they inherit the Phase 1 test-isolation strategy unchanged (delete the org, every
row beneath it goes) and the Phase 1 tenancy rule: cross-tenant reads return
**404**, never 403.

## Consequences

- Round-trip (`upgrade → downgrade → upgrade`) is verifiable on a scratch
  database exactly as in Phase 1 — that is N2's gate.
- Cost and latency are attributable per organisation, project, job, and purpose
  without a second system.
- Storing no prompt/response text keeps the sensitive-data surface to the one
  column that must hold it (`requirement_text`), rather than spreading it.
