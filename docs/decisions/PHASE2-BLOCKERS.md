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
