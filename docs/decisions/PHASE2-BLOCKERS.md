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

### As-built scope, stated without hedging

> **Project-level RBAC is NOT enforced. Any user with a qualifying role in the
> organisation can act on any project's test-generation requests and generated
> tests, regardless of project ownership, pending C-7
> (`user_roles.project_id`).**

**Owner: N9** (the security node). It is the node that reviews authorisation
boundaries, and closing this needs both a migration and a `Principal` change —
more than N7 (frontend) should carry.

### What the read routes actually require

Both `GET /test-generation/requests/{id}` and
`GET /test-generation/requests/{request_id}/tests` are guarded by
`Permission.TEST_GENERATION_READ` — a **role**, not merely authentication. All
five platform roles hold it, so in practice any role can read; an authenticated
user holding *no* role is refused with 403.

This was previously implicit in the dependency wiring and untested. Now covered
by `test_the_read_routes_require_a_role_not_merely_authentication` (roleless user
→ 403 on both routes) and `test_every_platform_role_can_read` (all five roles →
404 rather than 403, which is what proves the guard passed).

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

---

# N6-CLOSEOUT — pre-N7 verification

Opened at N6-CLOSEOUT, re-deriving N6's claims from source rather than from its
scorecard.

## C-11 — Idempotency dedupes the dispatch, not merely the row (verified, no bug)

**The question:** does migration `0007`'s key prevent a second *Celery dispatch*,
or only a second database row? Deduping the row while still dispatching would be
a **duplicate-billing bug** — the second job would run the whole four-call
pipeline against the same request.

**Verified with no worker consuming**, so the broker queue is directly
observable:

```
POST #1 → 202  id=7e588a4c…  job_id=c9bdacd1…
POST #2 → 200  id=7e588a4c…  job_id=c9bdacd1…     (same row, same job)

 request_rows | job_rows | model_run_rows
            1 |        1 |              0
celery broker queue depth: 1
```

**One broker message.** The early return happens before both the insert and the
dispatch, so neither occurs on the replay. **No duplicate-billing bug.**

The database invariant behind it, proven independently by two raw inserts:

```
INSERT 0 1
ERROR:  duplicate key value violates unique constraint
        "uq_test_generation_requests_idempotency"
DETAIL:  Key (organisation_id, idempotency_key)=(b6e44ce6…, RACEKEY) already exists.
```

…and the index is partial, so rows without a key do not collide with each other.

**Status: closed.** Covered permanently by
`test_idempotent_replay_enqueues_no_second_job`, which asserts on the `jobs`
table rather than on the response body.

## C-12 — The *concurrent* idempotency race is unproven

**Attempted and not completed.** The sequential replay above is proven. The
genuinely risky path in a read-then-write dedup is two POSTs racing the existence
check: both find nothing, both insert, and the unique index rejects one at
COMMIT.

An end-to-end probe firing four simultaneous POSTs through `TestClient` threads
**hung and was killed at ten minutes**. No backends were left waiting on locks
afterwards (`pg_stat_activity` reported `0 backends, 0 waiting on locks`), which
points at the test harness — `TestClient` runs its own event-loop portal per
thread over a shared async engine — rather than at a product deadlock. But that
is an inference, and it is not proof.

**What is established:** the partial unique index rejects the duplicate row
(shown above), and dispatch happens strictly *after* commit, so a racer that
loses the insert cannot reach `send_task`. That makes double-dispatch
structurally implausible.

**What is not established:** that a concurrent replay returns a sensible status
rather than a 500, and that the losing request is cleaned up rather than left
half-written.

**Status: open. Owner: N10** (reliability), which owns concurrency and failure
behaviour and will already be building load probes. It does **not** block N7:
the frontend issues one request per user action and has no concurrent-replay path.

## C-13 — A key replayed after a dispatch failure returns the failed request forever

Keying idempotency on the request row means the row *is* the record of the
attempt. If the first attempt's dispatch failed, that row exists in `FAILED`, and
a client retrying under the same key gets the failed row back — it can never
retry under that key.

This is a real limitation of the chosen design, not a defect in it: the
alternative (deleting the row so the key frees up) would erase the evidence that
the attempt happened, which ADR-0212 Decision 1 explicitly refuses for dispatch
failures.

**Status: open, documented. Owner: N7** — the frontend needs to surface "this
request failed; submit a new one" rather than offering a retry that will return
the same failed row. Pinned by
`test_a_replayed_key_after_dispatch_failure_returns_the_failed_request`.

## Correction to the N6 scorecard

The scorecard's prose showed **five** gate rows under "Gate evidence" while the
committed table has **thirteen**. The thirteen-row table in this document is the
authoritative one; the scorecard was summarising, and did not say so. Same class
of error as C-1 — a partial view presented without being labelled partial.

**D1–D6 mapping to gate rows and isolated tests**, verified from source:

| Decision | Gate row | Isolated named test(s) |
|---|---|---|
| D1 | 3 | `test_d1_request_and_job_are_committed_in_one_transaction_before_dispatch`, `test_d1_metering_foreign_keys_resolve_because_the_rows_were_durable_first` |
| D2 | 4 | `test_d2_unsupported_config_rejected_before_job_creation`, `test_d2_invalid_config_value_is_also_refused_at_the_boundary` |
| D3 | 5 | `test_d3_regenerate_reruns_codegen_only_and_attributes_to_the_original_request` |
| D4 | 6 | `test_d4_response_returns_the_four_entry_prompt_version_map`, `test_d4_prompt_versions_is_an_empty_map_before_any_stage_runs` |
| D5 | 7 | `test_d5_template_drift_surfaces_a_distinct_non_retryable_error_code` |
| D6 | 8 | `test_d6_unmet_kinds_reported_not_errored` |

All six have both a gate row and at least one isolated `test_dN_*` function. **D4
and D6 are not gaps** — each has a dedicated row and a dedicated test.

---

# N7-TOKENS — design system infrastructure

Opened at N7-TOKENS-CLOSEOUT, over commit `29b7fff`.

## C-14 — The three §9 enforcement guards are specified but unbuilt

`docs/design/design-tokens.md` §9 specifies three Playwright guards, and the
N7-DESIGN gate names them as the mechanism that keeps the lock honest:

| Guard | Asserts |
|---|---|
| (a) | every `[data-testid="highlight-mark"]` outside `/` has a `[data-testid="empty-state"]` ancestor |
| (b) | every `[data-variant="ai-action"]` carries a `data-ai-action` in the `AI_ACTIONS` allowlist |
| (c) | `/ci-failures` renders a table and zero `[data-variant="hero-card"]` |

**None of the three exists in `apps/web/e2e/`.** A one-off script asserted (b) by
hand during closeout — 2 dashed elements, both allowlisted, dashed count equal to
ai-action count — but that script was deleted after running and is not part of
the suite. Guards (a) and (c) have never run, and cannot until the Overview hero,
empty-state marks, and the CI Failures table exist.

Same failure mode as **C-2**: a check that only ever ran in a chat session is a
claim, not a guard.

**Status: open. Owner: N7 continuation.** They belong with the components they
police, not in a separate node — (a) and (c) are meaningless until those surfaces
are built, and building the surface without its guard is exactly how the
exclusion gets violated.

## C-15 — `StatCard` has not folded into `StatPanel`

design-tokens.md T5 specifies **one** reusable `<StatPanel>` — header row,
numeric readout, bar rows with right-aligned values, stat-tile mini-grid, tag
pills — shared by Failure Detail (§11.4), the confidence display (§25), and
Evaluations (§11.8), with the existing `components/StatCard.tsx` folding into its
tile grid.

`StatPanel` does not exist. `StatCard.tsx` is unchanged and still renders stock
`gray-*` classes (see C-16).

The risk is specific rather than cosmetic: T5 exists so the confidence bar-row —
the §25 pattern where the number must be visible beside the bar — is built once
and correctly. Three bespoke implementations is three chances to drop the number.

**Status: open. Owner: N7 continuation.**

## C-16 — The token set has no neutral ramp, so 94 stock-palette classes remain

design-tokens.md §8 requires components to read semantic tokens and never a stock
Tailwind palette class. Measured across `components/` and `app/` with all 22
numbered Tailwind families:

```
   87  gray
    7  red
   94  total
```

Two different problems inside that number:

- **87 `gray-*` are currently unavoidable.** The lock defines six *status*
  semantics plus `rule`, `pill`, `eyebrow` and `highlight` — and **no neutral
  ramp**. There is no token for body text, secondary text, or a default border,
  so every page legitimately falls back to `text-gray-600`, `border-gray-200`.
  This is a gap in the lock, not in the components.
- **7 `red-*` are genuine un-migrated violations** — `components/RequestState.tsx`
  lines 31 and 39 (`ErrorState`) and `app/login/page.tsx` line 60. All three
  predate the lock (untouched by `29b7fff`) and should read `status-failure`.

`components/StatusBadge.tsx` itself is clean: the corrected 22-family grep exits
1 with zero matches.

**Status: open. Owner: N7 continuation.** Adding the neutral ramp to
design-tokens.md must come first — migrating the 7 red classes is a five-minute
change, but migrating 87 gray ones before a token exists to migrate them *to*
would just relocate the problem.

## C-17 — Correction: the N7-TOKENS stock-colour grep checked 21 of 22 families

The N7-TOKENS report stated "grep for all 21 stock palette families returns
`matches: 0`". The count was accurate for the regex actually run, but the regex
**omitted `gray`** — Tailwind v3 ships 22 numbered families, and `gray` is the
single most-used one in this codebase (87 occurrences).

The scope was also narrower than a reader might infer: the palette grep ran
against `components/StatusBadge.tsx` only. The separate app-wide grep in that
report searched for **raw hex**, not palette classes, so nothing app-wide was
ever checked for stock colours until now.

**The StatusBadge conclusion survives** — re-run with all 22 families it still
exits 1 with zero matches. What did not survive is the impression that the
codebase as a whole had been checked.

Same class as **C-1** and **C-10**: a check that looked complete because its
output was `0`, when the zero came from a question narrower than the one being
answered.

**Status: corrected here. No code change.**

---

# N7-TOKENS-RAMP — closures

## C-14 — CLOSED (with one sub-assertion carried forward)

All three §9 guards are committed as `apps/web/e2e/design-lock.spec.ts` and run
via `npm run test:e2e:design`. Six tests, all passing in a fresh process:

```
Running 6 tests using 1 worker
  ✓ guard (a): highlight marks appear only on Overview or inside an empty state
  ✓ guard (a) is not vacuous: it rejects an injected mark on a functional route
  ✓ guard (b): every dashed pill is an allowlisted AI action
  ✓ guard (b) is not vacuous: it rejects a non-allowlisted label and a stray dashed element
  ✓ guard (c): no view uses the T6 hero-card treatment
  ✓ guard (c) is not vacuous: it rejects an injected hero card on CI Failures
  6 passed (10.4s)
```

**Each guard is written twice** — once against the real application, once against
an injected violation. That second half is the answer to the failure mode behind
C-2 and C-3: a guard that only ever runs where there is nothing to find passes
forever and proves nothing. Guards (a) and (c) currently find nothing real
(no highlight marks or hero cards exist yet), so without the injected half they
would be exactly that.

Guards (a) and (c) run against all ten authenticated routes with a real sign-in
against a live API. Guard (b) runs against `/dev/tokens`.

**Carried forward as design-tokens.md open item 4:** guard (c)'s positive half —
"`/ci-failures` renders a dense table" — cannot be asserted while that page is a
placeholder. The exclusion half (no hero-card treatment) is enforced now across
every route, and is the half that would catch a violation.

## C-15 — CLOSED

`components/StatPanel.tsx` implements the full T5 anatomy as one component:
header row, numeric readout, bar rows with right-aligned values, stat-tile grid,
tag-pill list. `components/StatCard.tsx` is **deleted**; Overview renders a
`StatPanel` with four tiles. Grep confirms `stat-tile` and `stat-bar` markup
exists in exactly one file, and the only surviving mention of `StatCard` anywhere
is the comment in `StatPanel.tsx` recording what folded in.

The bar row is why this was worth doing rather than three bespoke panels: §25
requires a confidence *score*, and `StatPanel` prints the number at the right
edge of every bar by construction, so no future page can render the bar and drop
the number.

All 8 pre-existing e2e tests still pass, so the Overview rewire is not a
regression.

## C-16 — CLOSED

The neutral ramp is added as design-tokens.md **T8**, with every ratio produced
by a script rather than estimated. Migration result:

```
$ grep -rnE '(bg|text|border|ring|from|to|via|divide|outline|decoration|accent|
   shadow|hover:bg|hover:text|focus:border|disabled:bg)-(slate|gray|zinc|neutral|
   stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|
   violet|purple|fuchsia|pink|rose)-[0-9]{2,3}' --include='*.tsx' components/ app/
EXIT CODE: 1   ← 1 means zero matches
```

94 stock-palette classes migrated (87 `gray` → neutral tokens, 7 `red` →
`status-failure`), plus 11 non-numbered `white`/`black` literals the family grep
could not see, which are now `surface` / `ink-inverse` / `surface-inverse` /
`ink` / `border-ink`.

### C-16a — an accessibility defect the ramp work exposed

The script rejected the obvious fifth text step. `neutral-400` (`#A1A1AA`) is
**2.56:1 on white** — below AA for text and below even the 3:1 non-text bar — yet
`text-gray-400` was carrying text in `Sidebar.tsx`. There is therefore **no
`ink-faint` token**, and that one usage moved up to `ink-subtle` (4.83:1).

A token that fails AA for text only invites text that cannot be read. Recorded
because the fix arrived as a side effect of tokenising, and would not have been
found by migrating the classes mechanically.
