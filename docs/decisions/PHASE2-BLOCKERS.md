# Phase 2 — Blockers and corrections

Findings that survive the node that produced them. Each entry states what was
claimed, what is actually true, and what was done about it.

Opened at **N5-VALIDATE**, the independent verification pass over N5
(commit `0bdc4f4`). Every entry below was re-derived from source — statement
logs, `psql`, `pytest --collect-only`, and `git show` — not from the N5
scorecard's own narration.

---

## C-1 — "11/11 probes" and a ten-row table were two different denominators

**Claimed:** the N5 scorecard headline read "11/11 direct probes" above a table
with **ten** rows.

**Actually true:** both numbers are right and they count different things.

- **10** = the gate items in the N5 brief (its numbered list 1–10).
- **11** = individual `check()` assertions in the probe script, verified by
  counting call sites in the source: lines 74, 96, 103, 108, 135, 140, 145, 195,
  200, 244, 249.

The eleven probes are: `2.` ten decomposition keys · `2b.` request COMPLETED with
summary · `3.` one `model_runs` row per call · `3b.` `pytest_codegen` distinct
from `code_generation` · `3c.` registry-issued `prompt_version_id` · `7.`
27-column schema · `7b.` no unexplained NULLs · `8.` one loop across four calls ·
`8b.` one loop construction · `10.` four known drift items · `10b.` no Phase 2
drift.

**Correction:** the two counts are not interchangeable and must not be presented
against one another. Gate items: **10/10**. Probes: **11/11**. Neither number was
wrong; the presentation implied a single denominator and invited exactly the
challenge it received.

---

## C-2 — The gate evidence is not reproducible from the repository

**Found:** the probe script that produced the 11 probe results lives only in a
session scratchpad. `git ls-files` returns nothing for it; it is untracked.

**Why it matters:** the N5 gate's sharpest evidence — loop-identity
instrumentation, the drift probe, the direct NULL audit — cannot be re-run by
anyone else, and cannot be re-run by us after the scratchpad is cleared. A gate
whose evidence evaporates is a claim, not a gate.

**Status: open, assigned to N8.** The probes belong in `tests/` as marked
integration tests, or in `scripts/` as a committed gate runner. They were not
moved in this pass because doing so silently would change what N5 shipped after
it was reviewed. N8 owns the test-suite node and should absorb them.

---

## C-3 — ADR-0206 specifies three test tiers; only one exists

**Found by `pytest --collect-only -q`:** 293 tests collect as **207 unit + 86
integration**, and nothing else.

```
tests/contract     : 0 test files
tests/end_to_end   : 0 test files
tests/evaluation   : 0 test files
tests/performance  : 0 test files
```

`-m evaluation` collects **zero** tests, despite the marker now being registered.

**Why it matters:** ADR-0206 defines tier 2 (a contract test that the live
provider's structured output still validates against the pinned schema) and
tier 3 (the tolerance-based evaluation suite). Neither exists. The contract tier
is the one that would catch a provider or model change breaking the integration —
precisely the risk ADR-0210's vendor swap introduced. Its absence is not visible
in a green run, because there is nothing to fail.

**Status: open, assigned to N8.** ADR-0206 is not yet satisfied, and N5's green
suite should not be read as evidence that it is.

---

## C-4 — "Mid-pipeline failure" had two shapes and only one was covered

**Claimed:** N5's rollback evidence covered mid-pipeline failure.

**Actually true:** it covered failure *during* a provider call and failure
*after* every call. It did not cover failure *between* stages — the shape where a
stage raises on its own inputs before reaching the provider.

The distinction changes the expected row count, which is why it matters:

| Failure shape | `model_runs` rows | Reason |
|---|---|---|
| Provider errors during stage 3 | **3** | ADR-0209 requires a row for the failed call |
| Stage 3 raises before calling | **2** | there is no third call to record |
| Failure after all four calls | **4** | every call completed |

Anyone asserting "N rows survive a mid-pipeline failure" without naming the shape
will write a test that is wrong two-thirds of the time.

**Fixed in this pass.** Added
`test_a_failure_between_stages_leaves_exactly_the_completed_calls`, asserting via
direct query. Verified independently through `psql`:

```
         operation         |  status   | prompt_version_id | attempts
---------------------------+-----------+-------------------+----------
 requirement_decomposition | SUCCEEDED | decompose-v1      |        1
 test_plan                 | SUCCEEDED | testplan-v1       |        1
(2 rows)

 generated_test_cases_rows : 0
 status | error_reason
 FAILED | RuntimeError: test_generation stage aborted before any provider call
```

`provider.call_count == 2` confirms the third stage never reached the provider.

---

## C-5 — `updated_at` cannot evidence a lifecycle walk

**Found during the N5 gate.** `prompt_versions.updated_at > created_at` reads
**false** for every seeded row, even though each walked five transitions.

**Cause:** Postgres `now()` is transaction-start time, and seeding runs in one
transaction, so `created_at` and `updated_at` are identical no matter how many
`UPDATE`s occurred in between.

**Why it matters:** a future reviewer may reach for `updated_at` to prove a
version was promoted rather than inserted straight to `ACTIVE`. It cannot carry
that. The evidence that does is server-side statement logging — `4` INSERTs, none
carrying `ACTIVE`, and `20` UPDATEs whose target statuses are each of
`OFFLINE_EVALUATION`, `REVIEW`, `STAGING`, `LIMITED_RELEASE`, `ACTIVE` exactly
four times.

**Status: recorded, no code change.** The behaviour is correct; the inference
from it would not be.

---

## C-6 — No content was lost to the garbled scorecard prose

**Reported:** the N5 scorecard appeared to contain corrupted fragments
(`TEST_GENEumn`, `...produces no negativeat`).

**Verified:** those strings appear in **no** tracked or working file
(`grep -rn` across the repo, excluding `.git`/`.venv`/`node_modules`, returns
nothing). Whatever produced them was a rendering or transport artifact, not a
write.

More importantly, the reasoning behind hazard #6 does not depend on that prose
surviving. It is recorded in three independent committed places:

1. `packages/test_generation/qe_test_generation/persistence.py:116-123` — the
   comment and the `unmet` computation feeding `summary.unmet_requested_kinds`.
2. `packages/test_generation/qe_test_generation/config.py:55-66` —
   `requested_kinds`, the mapping that makes the gap computable at all.
3. `docs/decisions/ADR-0208-test-generator-config.md:93-100` — the governing
   rule: "Reporting the gap is honest; fabricating a negative case to satisfy a
   flag is not."

**Status: no action.** The chat artifact was not load-bearing.

---

## Verification run — N5-VALIDATE

Environment: disposable `pgvector/pgvector:pg16` + `redis:7-alpine`, migrations
`0001`→`0006` on a virgin database, prompts seeded via `qe prompts seed`.

| Tool | Result |
|---|---|
| `ruff check .` | `All checks passed!` (exit 0) |
| `ruff format --check .` | `98 files already formatted` (exit 0) |
| `mypy --strict packages/{test_generation,ai_gateway,prompt_registry}` | `no issues found in 18 source files` (exit 0) |
| `pytest -q` ×3 | `294 passed` / `294 passed` / `294 passed` (exit 0 each) |
| `pytest -q -rsxX` | zero skips, zero xfails; no skip markers exist in `tests/` |

294 = 293 at commit `0bdc4f4` plus C-4's new fixture. The count is genuine: every
collected test executes, none are skipped.

---

# N6 — API

Opened at N6 (ADR-0212 `9534f20`, routes `9cdc1f1`, tests `5fa63d7`).

## C-7 — `user_roles` has no `project_id`, so "project scope" is organisation scope

**Found while writing ADR-0212's RBAC section.** §15.1 L1270 specifies
`user_roles` with `user_id`, `role_id`, **and `project_id`**. The shipped table
has only the first two, and `Principal` carries no project set.

**Consequence:** the N6 brief asks for create/approve "within their project scope
only". That is not implementable in this phase. What N6 enforces instead is
tenant isolation (every query filtered by `organisation_id`, cross-tenant rows
404 rather than 403) plus project existence and ownership. **Within one
organisation, any role holding `TEST_GENERATION_CREATE` may create a request
against any project in that organisation.**

**Status: open, pre-existing Phase 1 gap.** Closing it needs a migration adding
`user_roles.project_id` and a `Principal` that carries project scope. Recorded so
nobody reads the RBAC tests as proving a per-project guarantee they do not test.

## C-8 — `jobs` has no idempotency key

§14 L1218 lists "Idempotency key" among the fields every job carries. The `jobs`
table has none, and **no idempotency mechanism existed anywhere in the codebase**
before N6.

Migration `0007` adds one to `test_generation_requests`, which is the unit a
client actually retries — a replayed POST returns the original request instead of
billing a second four-call generation. `jobs` is deliberately left alone: an
unused column would imply a guarantee nothing enforces.

**Status: open for `jobs`, closed for test-generation requests.**

## C-9 — `_preflight` ran outside the failure handler, stranding failed requests

**Found by the D5 test, and a real product defect.**
`run_generation` called `_preflight` *before* its `try`, so any failure there —
an unseeded registry, a drifted template, a refused config — failed the **job**
while the **request row stayed at `QUEUED` forever**. A client polling that
request would wait indefinitely on work that had definitively failed, and no
`error_code` was ever written for D5 to surface.

Compounding it, the job state machine has **no `QUEUED → FAILED` edge**, so even
moving the call inside the `try` was not enough: `_mark_failed` would have raised
`JobInvalidStateError` inside its own handler and recorded nothing.

**Fixed.** Pre-flight now runs inside the `try`, and the `RUNNING` claim is
committed *first*, before anything fallible, so `RUNNING → FAILED` is available
to the failure handler.

## C-10 — A global row-count assertion is an order-dependent assertion

The first D2 test asserted `SELECT count(*) FROM model_runs == 0` — table-wide.
It passed only while the table happened to be empty, and began failing the moment
the gate-evidence runs put rows in it. Nothing about the code changed.

**Fixed** by scoping every count to the fixture's organisation. Verified by
running the full suite three times **against the polluted database**, rather than
by re-cleaning it — a re-clean would have hidden the defect rather than proved
the fix.

Recorded because the pattern generalises: in a suite whose isolation comes from a
per-test tenant, any assertion not filtered by `organisation_id` is a function of
what ran before it.

---

## N6 task-gate table

| # | Gate | Expected | Result |
|---|---|---|---|
| 1 | ADR before code | ADR-0212 committed with all six decisions before any route file | **PASS** — `9534f20`, six decisions with rationale; first route file written after |
| 2 | Seven §16.3 routes | exactly L1623-1631, no more | **PASS** — 7/7 registered, verified by enumerating `app.routes` |
| 3 | D1 dispatch ordering | request + job in one transaction, committed before dispatch | **PASS** — `psql`: request and job share `created_at` to the microsecond (Postgres `now()` is transaction-start time, so identical stamps *are* the same-transaction proof); first `model_runs` row 84 ms later; `ordering_holds=true` |
| 4 | D2 boundary validation | 422, zero rows anywhere | **PASS** — `TEST_CONFIG_UNSUPPORTED`, requests/jobs/model_runs `1/1/4 → 1/1/4` unchanged |
| 5 | D3 regenerate scope | codegen only, original `request_id`, other cases untouched | **PASS** — exactly one further `model_runs` row, `operation=pytest_codegen`, original `request_id`, regeneration `job_id`, sibling case untouched |
| 6 | D4 prompt-version map | four-entry map, singular column not exposed | **PASS** — all four entries; `prompt_version` absent from every response |
| 7 | D5 drift error code | distinct, non-retryable code reaches the client | **PASS** — `error_code=PROMPT_TEMPLATE_DRIFT`, distinct from `PROVIDER_*` and `INTERNAL_ERROR` |
| 8 | D6 unmet kinds | reported field, never an error | **PASS** — `COMPLETED` with `unmet_requested_kinds=[boundary, security]`, `case_count=2`, nothing synthesised |
| 9 | RBAC | a real 403 per denied role/route | **PASS** — 5/5 pasted with envelopes; positive half asserted for 3 author roles; matrix pinned |
| 10 | Audit hook | actor, before/after, on approve/reject/regenerate | **PASS** — `human_status {before: PENDING_REVIEW, after: APPROVED}`, `actor_user_id` recorded |
| 11 | Idempotency (§26.8) | replay returns the original, bills nothing further | **PASS** — 202 then 200, same `id` and `job_id`, one row |
| 12 | Full lifecycle | 202 → real worker → COMPLETED, populated summary | **PASS** — `QUEUED → WAITING_FOR_PROVIDER → COMPLETED`, 0.15 s wall clock (§30 L2378 target <90 s), 2 cases, 4 `model_runs`, 4 prompt versions |
| 13 | Tooling | ruff, ruff format, mypy --strict, pytest ×3 | **PASS** — exit 0 / 102 files formatted / 54 files clean / `320 passed` ×3 |

**Measured numbers:** POST→COMPLETED wall clock **0.15 s** on `MockProvider`
(the §30 L2378 <90 s target governs the real provider; N10 measures that).
Request+job commit to first metering row: **84 ms**. Suite: **320 tests**, 0
skipped, 0 xfailed.
