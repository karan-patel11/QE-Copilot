# ADR-0203 — Schema: test_generation_requests, generated_test_cases, model_runs

**Status:** Accepted (Phase 2, N1) — corrected against
`docs/architecture/design-spec.md`, **migration `0005` amended in place and the
N2 round-trip gate re-run and passing**

## Sources

| Claim | Spec |
|---|---|
| `test_generation_requests` columns | §15.6 L1459–1469 |
| `generated_test_cases` columns | §15.6 L1471–1489 |
| `model_runs` columns | §15.8 L1527–1540 |
| `audit_logs` columns (Phase 1) | §15.8 L1575–1585 |
| Fields the Test Generator page must display | §11.5 L869–885 |
| Job states / job fields | §14 L1187–1212 |

## Corrections applied in this pass

**1. The §15.8 "contradiction" is retracted — confirmed against the source.**
§15.8 "AI Governance Tables" (L1525) contains `model_runs` (L1527) *and*
`audit_logs` (L1575) as separate tables under one subsection. Both Phase 1 and
Phase 2 briefs cited §15.8 correctly. The earlier claim that the section number
was unreliable was wrong and is withdrawn.

**2. Column names and shape corrected to §15.6 / §15.8.** The first revision
renamed and collapsed spec columns. Most seriously, it replaced
`objective / preconditions / test_data / steps / expected_result / tags` with a
single free-text `description` — but §11.5 L873–885 requires the Test Generator
page to display each of those fields individually, so the collapse would have
broken N7. Corrected below.

## Decision

Three tables. **Spec column names are authoritative**; every addition is listed
separately with its justification, so spec-sourced and derived columns are never
confused.

### `test_generation_requests` (§15.6 L1459–1469)

Spec columns, kept verbatim: `id`, `project_id`, `user_id`, `source_type`,
`source_reference`, `framework`, `configuration`, `status`, `created_at`.

Additions (derived, not in §15.6):

| Column | Why |
|---|---|
| `organisation_id` | tenant boundary — §26.2 authorisation and ADR-0106; every Phase 0/1 table carries it |
| `updated_at` | Phase 0/1 convention (`TimestampMixin`) |
| `job_id` | §13.2 makes the request job-backed; this is the link the poller follows |
| `repository_id` | §11.5 L853 lists "Repository context" as an input source |
| `title` | human label for the request list; §11.5 shows requests before their tests |
| `prompt_version` | provenance (ADR-0202) |
| `error`, `summary` | failure reason and per-request counts for polling |

`status` uses the §14 L1187–1197 job states, which `qe_common.jobs.JobState`
already implements exactly — one vocabulary, not two.

### `generated_test_cases` (§15.6 L1471–1489)

Spec columns, kept verbatim: `id`, `request_id`, `title`, `objective`,
`preconditions`, `test_data`, `steps`, `expected_result`, `priority`, `tags`,
`generated_code`, `schema_valid`, `syntax_valid`, `duplicate_score`,
`execution_status`, `human_status`, `created_at`.

Notes on shape:

- `steps` and `tags` are JSONB arrays; `test_data` is JSONB. `objective`,
  `preconditions` and `expected_result` are text.
- `schema_valid` and `syntax_valid` are **separate booleans** as specified — not
  collapsed into one status field.
- `execution_status` **exists and stays NULL in Phase 2**. The column is
  specified (§15.6 L1487) and displayed (§11.5 L885); the sandbox that would
  populate it is P1 (ADR-0205). A null column is the honest representation of
  "not executed", and it means the P1 sandbox needs no migration.
- `human_status` is the review state, defaulting to a pending value. **Nothing
  auto-approves** — §8.2 human-in-the-loop, §11.5 L890 explicit approve action.

Additions (derived): `organisation_id` (tenancy, denormalised to avoid a join),
`updated_at`, `framework`, `ordinal` (stable display order), `validation_errors`
(JSONB — carries *why* a check failed, which the booleans cannot),
`duplicate_of` (the counterpart the `duplicate_score` refers to), `is_edited`,
`reviewed_by`, `reviewed_at` (§11.5 L889–891 edit/approve/reject need an actor),
and `test_type` — §11.5 L857–867 lets the requester ask for a mix of positive,
negative, boundary, security and accessibility cases, and without a per-case
type there is no way to show that the mix was honoured. (This column was in
migration `0005` from the start but was missing from this list; recorded now so
the "every addition is justified" rule actually holds.)

`schema_valid` and `syntax_valid` default to **false**, not true. The
pre-amendment `validation_status` defaulted to `PASSED`, so a row written before
validation ran would read as valid — fail-open. Defaulting to false makes an
unvalidated case indistinguishable from a failed one, which is the safe reading.

`validation_status` survives as a **derived property** on the ORM model, not a
column: §11.5 L883 displays one "Validation status", but §15.6 makes the two
booleans the source of truth, and a stored third field could disagree with them.

### `model_runs` (§15.8 L1527–1540)

Spec columns, kept verbatim: `id`, `provider`, `model`, `operation`,
`prompt_version_id`, `input_token_count`, `output_token_count`, `latency_ms`,
`estimated_cost`, `status`, `error_code`, `created_at`.

- `prompt_version_id` is listed by §15.8 L1533 as a bare column name: **the spec
  states no type and no foreign key for it.** `String(64)` holding the version
  identifier is therefore a choice filling a gap the spec leaves open — not a
  divergence from a stated spec position, and not a shortfall to be made good
  later. (The `prompt_versions` table itself is §15.8 L1542; ADR-0202 deferred it
  to P1, and ADR-0209 subsequently built it in Phase 2.) What the choice does
  create is an operational hazard, and that hazard is real:

  > **Hazard for N3/N4.** The column is named `_id` but holds a `String(64)`,
  > not a UUID. Anything writing it must write the prompt *version identifier*
  > from the registry (ADR-0202), e.g. `"testgen-v3"` — never a row id, and
  > never a free-form label. When `prompt_versions` lands, the migration that
  > converts this to a real FK has to map those strings to rows; strings that
  > were never registry identifiers will not map. N3 and N4 must therefore take
  > this value straight from the prompt registry rather than constructing it.
- Immutable: written once, no `updated_at` — matching `audit_logs`.
- **No prompt or response text is stored.** §15.8 lists none — that part is
  sourced. Keeping it that way also keeps requirement text out of a second table,
  which is *an inference from §26.5's intent rather than a rule it states*:
  §26.5 specifies detection and redaction of secrets and PII and says nothing
  about duplicating data across tables. The smaller redaction surface is our
  reasoning.

Additions (derived): `organisation_id`, `project_id`, `job_id`, `request_id`
(attribution and cost roll-up), `cache_read_input_tokens` /
`cache_creation_input_tokens` (the provider bills these separately, so
`estimated_cost` is wrong without them), `stop_reason` (needed to record refusals
per ADR-0201), `attempts` (retries visible rather than collapsed).

### Tenancy

All three tables are rooted at `organisations` via `ON DELETE CASCADE`,
inheriting the Phase 1 isolation model and the 404-not-403 cross-tenant rule.

## Resolved: migration `0005` amended in place, N2 re-gated

Migration `0005` (commit `8768a34`) was written against the pre-correction
column set and has now been **amended in place** — it has only ever existed on
this branch and has no external consumers, so a stacked corrective `0006` would
have added a rename-churn artifact to the permanent history for no benefit. The
ORM models in `qe_database.models` were amended in the same pass; a migration
that no model can address would have passed a DDL gate and still been unusable.

Deltas applied:

- `requirement_text` → `source_reference`; `config` → `configuration`;
  `requested_by` → `user_id`
- add `objective`, `preconditions`, `test_data`, `steps`, `expected_result`,
  `tags`; drop `description`
- `code` → `generated_code`; `status` → `human_status`
- `validation_status` → separate `schema_valid` / `syntax_valid` booleans
- add `execution_status` (nullable)
- `purpose` → `operation`; `prompt_version` → `prompt_version_id`;
  `input_tokens` / `output_tokens` → `input_token_count` / `output_token_count`;
  `cost_usd` → `estimated_cost`

### N2 re-gate evidence

Re-run against a disposable `pgvector/pgvector:pg16` container — the image
`docker-compose.yml` declares — from a virgin database:

| Check | Result |
|---|---|
| `upgrade head` (pass 1), 0001→0005 | applied, head `0005_testgen` |
| Phase 2 tables created | 3/3 |
| `downgrade 0004_audit` | applied, head `0004_audit` |
| Phase 2 tables / indexes remaining | 0 / 0 |
| Phase 0/1 tables intact after downgrade | 8/8 |
| `upgrade head` (pass 2) | applied, head `0005_testgen` |
| Pass 1 vs pass 2 schema (columns, types, nullability, defaults, indexes, FKs) | identical across 93 lines |
| `--autogenerate` drift, Phase 2 tables | empty |
| §15.6 / §15.8 spec column coverage | 9/9, 17/17, 12/12 |
| ORM insert/select round-trip through all three tables | passes |

Two gate-design notes, since the gate is the thing that has to be trustworthy:

- The first run reported "IDENTICAL" while comparing two **empty** captures
  (migration `0001` had failed on a missing `vector` extension). An equality
  check that passes on no data is not a gate; it now fails explicitly on an
  empty capture.
- The autogenerate probe is scoped to the three Phase 2 tables. It reports
  Phase 0/1 drift but does not fail on it — see the backlog flag below.

## Backlog flag (not actioned in Phase 2)

The drift probe surfaces four pre-existing Phase 0/1 mismatches between
`qe_database.models` and the migrated schema:

- index `ix_projects_organisation_id` — in the DB, absent from the model
- index `ix_repositories_project_id` — in the DB, absent from the model
- index `ix_users_organisation_id` — in the DB, absent from the model
- unique constraint `uq_user_roles` — in the model, absent from the DB

These were confirmed pre-existing by running the same probe against the
pre-amendment tree: the identical four appear. They are **out of scope for
Phase 2** and no code was changed for them. Recorded here so a future phase
picks them up deliberately, alongside the `audit_logs` drift noted earlier.

## Consequences

- The schema matches the fields §11.5 requires, so N7 can be built from it.
- Spec-sourced and derived columns are separated, so a future reader can tell
  which is which without re-reading the spec.
- N2's artifact is corrected, re-gated, and consistent with the ORM: N3–N5 can
  be built against it.
- `prompt_version_id` as a `String(64)` is **not** a divergence from the spec —
  §15.8 L1533 states no type and no FK, so there is no spec position to diverge
  from. The operational hazard is unchanged and stands: only registry-sourced
  version strings resolve, and a free-form label written here could not be mapped
  by a future foreign-key backfill. It is flagged where the code that writes it
  will be read, and ADR-0209 Decision 5 is the boundary that contains it.
