# ADR-0203 — Schema: test_generation_requests, generated_test_cases, model_runs

**Status:** Accepted (Phase 2, N1) — **corrected against `docs/architecture/design-spec.md` (N0.5)**

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
`reviewed_by`, `reviewed_at` (§11.5 L889–891 edit/approve/reject need an actor).

### `model_runs` (§15.8 L1527–1540)

Spec columns, kept verbatim: `id`, `provider`, `model`, `operation`,
`prompt_version_id`, `input_token_count`, `output_token_count`, `latency_ms`,
`estimated_cost`, `status`, `error_code`, `created_at`.

- `prompt_version_id` is specified as a reference to `prompt_versions`
  (§15.8 L1542). That table is deferred to the P1 prompt-versioning work
  (ADR-0202), so in Phase 2 the column holds the version **string** and is not
  yet a foreign key. Recorded as a known, forward-compatible shortfall.
- Immutable: written once, no `updated_at` — matching `audit_logs`.
- **No prompt or response text is stored.** §15.8 lists none, and §26.5
  sensitive-data redaction argues against duplicating requirement text into a
  second table.

Additions (derived): `organisation_id`, `project_id`, `job_id`, `request_id`
(attribution and cost roll-up), `cache_read_input_tokens` /
`cache_creation_input_tokens` (the provider bills these separately, so
`estimated_cost` is wrong without them), `stop_reason` (needed to record refusals
per ADR-0201), `attempts` (retries visible rather than collapsed).

### Tenancy

All three tables are rooted at `organisations` via `ON DELETE CASCADE`,
inheriting the Phase 1 isolation model and the 404-not-403 cross-tenant rule.

## Outstanding: migration `0005` does not yet match this ADR

Migration `0005` (commit `8768a34`) was written against the pre-correction
column set. It must be amended before N5 builds on it. Known deltas:

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

`0005` has only ever existed on this branch, so it is amended in place rather
than corrected by a stacked `0006`. **The N2 round-trip gate must be re-run
after the amendment.**

## Consequences

- The schema matches the fields §11.5 requires, so N7 can be built from it.
- Spec-sourced and derived columns are separated, so a future reader can tell
  which is which without re-reading the spec.
- N2's artifact is now known-stale and is tracked, not silently wrong.
