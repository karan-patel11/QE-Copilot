# ADR-0211 — N5 test-generation pipeline: bridge, metering, seeding, vocabulary, §22 step ownership

**Status:** Accepted (Phase 2, N5 Phase 1) — written against
`docs/architecture/design-spec.md`, which is present and readable (see
PHASE2-PLAN.md's design-authority note)
**Amends:** ADR-0209 (session handling, for the metering path only)
**Depends on:** ADR-0203 (schema), ADR-0204 (async boundary), ADR-0205
(validation scope), ADR-0207 (decomposition), ADR-0208 (config), ADR-0209
(gateway/registry boundaries), ADR-0210 (Groq)

## Sources

| Claim | Spec |
|---|---|
| Test-generation pipeline, thirteen stages | §22 L1931–1955 |
| The ten decomposition outputs | §22.1 L1962–1971 |
| Seven validation levels | §22.2 L1977–1983 |
| Test-generation job completed within 90 seconds | §30 L2378 |
| Test generation is asynchronous; worker claims and processes | §13.2 L1152–1179 |
| Eleven Test Generator configuration options | §11.5 L857–867 |
| Boundary cases and edge cases are distinct kinds | §7.1 L214–215 |
| Initially supported frameworks | §7.1 L229–234 |
| Phase 2 delivers Pytest code generation and static validation | §38 L2801–2802 |
| Explicit transaction boundaries; no silent exception handling | §37 L2743, L2746 |
| Modules must not modify another module's records via uncontrolled queries | §12.2 L1110 |
| Prompt lifecycle, seven stages | §19 L1791–1807 |
| No production deploy without evaluation | §19 L1789 |

---

## Decision 1 — The sync/async bridge is exactly one call, at the Celery task boundary

§18 makes the gateway `async`; ADR-0204 makes generation a sync Celery job. The
conversion happens **once**, and this ADR fixes where.

```
qe_worker.tasks.generate_tests            (sync Celery task)
  └── qe_test_generation.run_generation()  (sync facade — THE bridge)
        └── asyncio.run(_run_generation(...))   ← the only asyncio.run in N5
              ├── await decompose(...)          → gateway call 1
              ├── await plan(...)               → gateway call 2
              ├── await generate_cases(...)     → gateway call 3
              └── await generate_code(...)      → gateway call 4
```

### The rule, stated so it can be enforced

**Below `run_generation`, no code may call `asyncio.run()`,
`loop.run_until_complete()`, `asyncio.new_event_loop()`, or
`asyncio.set_event_loop()`.** Every stage is `async def` and awaits the gateway
directly.

This is not style. A per-call `asyncio.run()` would:

- create and tear down an event loop per provider call, discarding whatever
  connection state the provider's async client holds across calls;
- serialise every call by construction, removing the possibility of overlap the
  pipeline could otherwise exploit against the §30 L2378 <90 s target;
- make the four calls four unrelated async contexts, so no cancellation,
  timeout, or backpressure policy could ever span them.

**Enforced mechanically**, in the manner of `tests/unit/test_module_boundaries.py`:
a unit test walks the AST of `packages/test_generation/` and asserts that
`asyncio.run` appears exactly once, in the designated bridge module. A rule that
only lives in an ADR decays; this one fails a test.

### Concurrency: available, deliberately unused in Phase 2

Keeping one loop alive across all four calls makes `asyncio.gather` *possible*.
Phase 2 does not use it, for a reason worth recording rather than discovering:
the pipeline stages are genuinely sequential (each consumes the previous stage's
output), and the one natural fan-out point — per-case code generation — would
have concurrent tasks writing `model_runs` through a **SQLAlchemy `Session`,
which is not safe for concurrent use**. Phase 2 therefore issues **one code
generation call covering all cases**, which is also fewer billed calls and less
latency. Per-case regeneration (§16.3's `POST /generated-tests/{id}/regenerate`)
re-enters the same stage with a single-case input; it is N6's concern.

### Known tradeoff: blocking DB I/O inside the loop

The `model_runs` recorder is synchronous (`session.add` + commit), and it is
called from inside `async` code. That is blocking I/O on the event loop. It is
accepted: the worker runs one generation at a time, a local `INSERT` is
sub-millisecond against multi-second provider calls, and the alternative —
an async recorder — would fork the gateway's persistence path that N3/N4 already
shipped and tested. Recorded as a tradeoff, not overlooked.

---

## Decision 2 — Metering commits independently of the pipeline transaction

### The problem

`DatabaseModelRunRecorder.record()` calls `session.flush()`, not `commit()`, so
the row joins the caller's transaction (ADR-0209, deliberately). If N5 wrapped a
generation in one transaction and a late stage failed, the rollback would erase
`model_runs` rows for provider calls that **actually happened and actually cost
money**. The audit record of a billed call would be destroyed by the failure of
an unrelated downstream step.

### The decision

**`model_runs` rows are written in their own transaction, committed immediately,
and survive any rollback of the pipeline transaction.**

Mechanism: a new `CommittingModelRunRecorder` in
`packages/ai_gateway/qe_ai_gateway/recorder.py` — **in the gateway, because
`qe_ai_gateway` owns `model_runs`** (ADR-0209 table ownership). It takes a
session *factory* rather than a session, and per row opens a short-lived session
on its own pooled connection, inserts, commits, and closes:

```python
class CommittingModelRunRecorder:
    def __init__(self, session_factory: Callable[[], Session]) -> None: ...

    def record(self, run: ModelRunRecord) -> uuid.UUID | None:
        with self._session_factory() as session:
            row = _to_model_run(run)      # shared with DatabaseModelRunRecorder
            session.add(row)
            session.commit()
            return row.id
```

`DatabaseModelRunRecorder` stays exactly as it is. Both exist because they answer
different questions: join-the-caller's-transaction is right when the caller *is*
the audit boundary; commit-independently is right when the caller may roll back
work that the provider already billed for. N5 injects the committing one.

**This amends ADR-0209's "the gateway does not own transaction boundaries."** For
the metering path it now does, deliberately, and the amendment is recorded here
rather than left as a contradiction between two ADRs.

### Why a separate connection is required, and not a SAVEPOINT

A `SAVEPOINT` (SQLAlchemy's nested transaction) rolls back with its parent — it
would provide exactly none of the durability wanted here. Only a genuinely
separate transaction, on a separate connection, survives the outer rollback.

### The precondition that makes this safe

`model_runs.request_id` is an FK to `test_generation_requests.id` and `job_id` an
FK to `jobs.id`. An independently-committed row referencing an *uncommitted*
request row would fail the foreign key. It does not, because of ADR-0204's flow:
**the API commits the `test_generation_requests` and `jobs` rows before
dispatching the job**, so both FK targets are already visible on every connection
by the time the worker's first provider call happens. N5 never creates the
request row it meters against.

Stated as a precondition because it is one: anything that invokes this pipeline
against an uncommitted request row will get a foreign-key error, and the fix is
to commit the fixture, not to weaken the metering.

### Failure of the metering write must not mask the provider error

The `ModelRunRecorder` protocol says `record()` "must not raise for an ordinary
failed call". If the independent commit itself fails, `CommittingModelRunRecorder`
**logs at ERROR with every field of the record in the log payload, and returns
`None`** — it does not raise. Raising would replace a real provider exception,
mid-propagation, with a persistence exception, and the operator would lose the
actual failure.

This is **not** silent exception handling (§37 L2746): the metering data survives
in the structured log stream even when the row does not, and the failure is
logged at ERROR rather than swallowed. The honest description is "the row can be
lost only if the database rejects it, and when that happens the data is still in
the logs and the loss is loud".

---

## Decision 3 — Seeding is an idempotent CLI command that walks the full lifecycle

Nothing currently seeds `prompt_versions`, so on a virgin database N5's first
`get_active()` raises `PromptVersionNotFoundError`.

### The hard constraint

**Seeding goes through `transition_status()` and walks all five forward
transitions.** No raw `INSERT ... status='ACTIVE'`, and no direct `UPDATE`, even
for bootstrap data:

```
DRAFT → OFFLINE_EVALUATION → REVIEW → STAGING → LIMITED_RELEASE → ACTIVE
```

The order-enforcement in `transition_status()` is the only thing guaranteeing
nothing reaches `ACTIVE` without passing through the review states (ADR-0209
Decision 3 — the DB CHECK cannot see the previous value, so ordering is the
service's job). Seed data that bypassed it would make the guarantee false for
exactly the rows every generation depends on, and would leave the seeded rows
indistinguishable from ones written by a rogue script.

### The mechanism: idempotent CLI command

**`qe prompts seed`**, in the existing Phase 0 CLI (`apps/cli`, the `qe` entry
point already registered in `pyproject.toml`), backed by
`qe_prompt_registry.seed` — in the registry package, because it owns the table.
A `make seed` target mirrors `make migrate`.

Rejected alternatives, with reasons:

| Option | Rejected because |
|---|---|
| **Alembic data migration** | A migration that calls the service layer is pinned to today's `transition_status()` signature forever; when the service changes, an old migration breaks or silently diverges. Migrations also run once, so a template added later would never be seeded. |
| **Startup bootstrap** (API/worker boot) | Makes every process start perform DB writes, couples readiness to seeding, and races when several workers boot at once. The unique indexes make the race *safe*, but one process still crashes on `IntegrityError` at boot. |

An explicit command is also the honest representation of what seeding *is*: an
operational action someone takes, auditable, re-runnable, and absent from the hot
path.

### Idempotency rules

Per source template, keyed on the version string:

| Existing row | Action |
|---|---|
| none | `create_version()` (lands in `DRAFT`), then walk to `ACTIVE` |
| mid-lifecycle (`DRAFT`…`LIMITED_RELEASE`) | continue walking forward to `ACTIVE` |
| `ACTIVE` | no-op |
| `DEPRECATED` | leave alone and report — terminal, and ADR-0209 has no backward edge |

Re-running is therefore always safe and always converges on "one ACTIVE version
per prompt". Promotion to `ACTIVE` atomically deprecates the outgoing active
version, which `transition_status()` already handles.

### The prompts seeded

Four, one per pipeline stage. `decompose-v1` and `testgen-v1` exist in
`templates.py`; `testplan-v1` and `pytest_codegen-v1` are added by N5, as
source-resident templates (ADR-0202's git-versioned source of truth — the
registry mirrors them, it never invents prompt text).

| Prompt name | Version | Stage |
|---|---|---|
| `decompose` | `decompose-v1` | §22 requirement decomposition (+ steps 4–5, Decision 7) |
| `testplan` | `testplan-v1` | §22 test-plan generation |
| `testgen` | `testgen-v1` | §22 detailed test generation |
| `pytest_codegen` | `pytest_codegen-v1` | §22 code generation |

All four satisfy ADR-0209's `^[a-z][a-z0-9_]*-v[1-9][0-9]*$` format rule.

### `get_active()` takes a **prompt name**, not a version string

Recorded because the N5 brief writes it the other way round: the signature is
`get_active(session, prompt_name)`, so the calls are `get_active(session,
"decompose")`, not `get_active(session, "decompose-v1")`. The returned row's
`.version` is what goes to `model_runs.prompt_version_id`.

### The two derived `prompt_versions` columns — checked, not assumed

ADR-0209 added `updated_at` and `template_checksum` beyond §15.8. Their relevance
to N5, having actually looked:

- **`template_checksum` is load-bearing for N5.** `get_active()` calls
  `_assert_matches_source()`, which raises `PromptTemplateDriftError` (HTTP 500)
  when a registered row's checksum no longer matches its source template. N5
  therefore has a failure mode on *every* stage that is neither a provider error
  nor a validation error, and it must surface as a clean job failure rather than
  an unhandled exception. Editing a template in place without registering a new
  version triggers it — which is the intended behaviour, not a bug to work around.
- **`updated_at` is not relevant to N5.** It records lifecycle mutations; nothing
  in the pipeline reads it.

---

## Decision 4 — `ModelOperation` gains `PYTEST_CODEGEN` (and `TEST_PLAN`)

`pytest_codegen` is added as **its own value**, not defaulted onto
`CODE_GENERATION`:

```python
REQUIREMENT_DECOMPOSITION = "requirement_decomposition"   # stage 1
TEST_PLAN = "test_plan"                                   # stage 2  (new)
TEST_GENERATION = "test_generation"                       # stage 3
PYTEST_CODEGEN = "pytest_codegen"                         # stage 4  (new)
CODE_GENERATION = "code_generation"                       # reserved, never written in Phase 2
EMBEDDING = "embedding"
```

### Confirmation that this does not blur cost roll-ups

`model_runs.operation` is the column cost and evaluation are grouped by. The four
Phase 2 values are disjoint and each maps to exactly one pipeline stage and one
prompt, so a roll-up by `operation` answers "what did decomposition cost versus
code generation" without any inference.

Defaulting codegen to `CODE_GENERATION` would have been the blurring move, and
specifically an *irreversible* one: §7.1 L229–234 names Playwright and REST-API
Python alongside Pytest as initially-supported frameworks, so a future
`playwright_codegen` would land in the same bucket as Phase 2's pytest rows, and
**no backfill could separate them** — the rows carry no framework column.
Framework-specific operation values keep per-framework cost separable from the
first row written.

`CODE_GENERATION` is retained but **never written in Phase 2**; it is reserved
for framework-agnostic code generation. A roll-up that sees `code_generation`
rows therefore knows they did not come from this phase.

`TEST_PLAN` is an addition beyond the N5 brief's four decisions, on the same
reasoning: test-plan generation is a separate billed provider call with its own
prompt, and folding it into `TEST_GENERATION` would make two distinct calls
indistinguishable in exactly the column that exists to distinguish them.

No migration: `model_runs.operation` is `String(64)` with no CHECK constraint.

---

## Decision 5 — `ValidationCheck` corrected to §22.2

`qe_common.test_generation.ValidationCheck` shipped with an invented
`DISCOVERABILITY` member and **no safety-scanning member**, implementing the
first revision of ADR-0205 — a revision ADR-0205 itself retracted, in `efd65cc`,
three hours after the enum was committed. `grep -ic discoverab` over the whole of
`design-spec.md` returns **0**; `Safety scanning` is real, at §22.2 L1982.

Corrected: `DISCOVERABILITY` removed, `SAFETY` added, members ordered as §22.2
levels 1–6, with level 7 remaining a `TODO`.

**Zero blast radius, verified before removal.** `ValidationCheck` had no
consumers anywhere in `packages/`, `apps/`, `tests/`, or `migrations/` — N5 is
its first consumer, which is why this had to be fixed before N5 rather than
after. Nothing persisted depended on it: `validation_errors` is free-form JSONB
and no rows exist. No migration.

Had discoverability shipped into `validation_errors` rows first, the fix would
have required a data migration to rewrite persisted check names — the reason the
timing matters.

A pytest-collectability check, if ever wanted, belongs inside the `SYNTAX`
stage's error payload rather than as a peer level, because the enum's members are
§22.2's levels and a seventh peer that is not one of them would make that untrue.

---

## Decision 6 — `TestType` widened to express the requested mix

`TestType` was `{UNIT, INTEGRATION, EDGE_CASE, NEGATIVE}`. ADR-0203 justifies the
`test_type` column as the way to show "a mix of positive, negative, boundary,
security and accessibility cases … was honoured" — but of those five the enum
could express **one**. ADR-0208's commitment that an unmet `include_*` flag is
"reported in the request `summary`" was therefore unimplementable: nothing could
be labelled positive, boundary, or security.

Added `POSITIVE`, `BOUNDARY`, `SECURITY`. `EDGE_CASE` is untouched and stays
**distinct from** `BOUNDARY`, because §7.1 L214–215 lists "Boundary cases" and
"Edge cases" as separate items. Existing member values are unchanged; only the
grouping order changed.

### Accessibility deliberately has no `TestType` value

ADR-0208 rejects `include_accessibility_cases` with a **422 at the request
boundary** — the request never becomes a job, so no case of that kind can ever
reach `generated_test_cases`. Adding an `ACCESSIBILITY` member would create a
value that is unreachable by construction and would invite a future writer to
produce exactly the mislabelled output ADR-0208 refuses: tests presented as
covering accessibility that do not. The absence is the enforcement.

No migration: `test_type` is `String(32)` with no CHECK constraint in `0005`.

---

## Decision 7 — §22 steps 4 and 5 fold into decomposition, with a named mapping

§22's pipeline lists thirteen stages. Two of them —

```
4. Entity and constraint extraction
5. Risk identification
```

— appear **nowhere** in ADR-0201 through ADR-0210 except as passing prose in
ADR-0207 describing where decomposition sits. They had no owner, no deferral, and
no stated mapping. This decision gives them one.

**Both fold into requirement decomposition's existing ten-field output
(§22.1 L1962–1971). Neither gets its own gateway call. Neither is deferred.**

### The mapping, named rather than assumed

| §22 stage | ADR-0207 decomposition fields that carry it |
|---|---|
| **4. Entity and constraint extraction** | `actors` (the entities), `data_constraints` (`{field, constraint}`), `business_rules` (behavioural constraints), `integration_dependencies` (external entities the requirement depends on) |
| **5. Risk identification** | **`security_constraints` and `failure_conditions`, jointly** — what can go wrong, and what must not be allowed to |

The risk mapping is the one that would otherwise have been assumed, so it is
stated flatly: **`security_constraints` + `failure_conditions` together are the
risk-identification output of this pipeline.** There is no third field, no
separate risk score, and no risk artifact persisted anywhere.

### Why fold rather than split

- Each extra stage is another provider round-trip and another billed call against
  the §30 L2378 <90 s target, to re-derive from the same requirement text.
- §22.1's ten outputs already name exactly the material both stages would
  produce. Two more calls would create a **second, independently-generated copy**
  of entities and risks that can disagree with the first — and nothing downstream
  would know which to believe.
- ADR-0207 already closed the decomposition field list for Phase 2 ("no
  additions, no renames, no silent omissions"). Folding respects that; adding
  stages producing new fields would reopen it.

### Why not defer

§22 places both inside the test-generation pipeline and §38 L2795–2802 puts that
pipeline in Phase 2. Skipping a numbered spec stage in silence is precisely the
failure the N5 reconciliation existed to catch.

### Consequences, stated

- **No separate `model_runs` row for steps 4–5.** Their cost sits inside the
  decomposition row. A cost roll-up cannot price entity extraction separately,
  and that is a consequence of folding, not an oversight.
- **No `entity_extraction` or `risk_identification` `ModelOperation` values**,
  deliberately — there is no call to attribute to them.
- If a later phase needs entities or risks as first-class artifacts (a risk score
  driving prioritisation, say), that is a new decision with new fields, taken
  then, on top of a decomposition contract that already carries the raw material.

---

## Scope confirmations

**Sandbox execution (§22.2 level 7, §23) is out of scope for N5** — unchanged
from ADR-0205, which defers it on the spec's own terms (§22.2 L1983 calls it
"Optional", §39 L2910 makes the generated-code sandbox P1, and §38 L2802 scopes
Phase 2 to "Static validation"). `execution_status` stays NULL. Nothing in N5
executes generated code anywhere.

**No new migration.** N5 adds no columns to any table. Confirmed against the
shipped schema:

| Table | Spec columns (§15.6) | Physical columns (`0005`) | N5 changes |
|---|---|---|---|
| `test_generation_requests` | 9/9 present | 17 (8 derived, all justified in ADR-0203) | writes `status`, `prompt_version`, `error`, `summary`; adds nothing |
| `generated_test_cases` | 17/17 present | 27 (10 derived, all justified in ADR-0203) | writes all case fields; adds nothing |
| `model_runs` | 12/12 present | 20 (8 derived) | one row per gateway call; adds nothing |

The three enum widenings in Decisions 4, 5 and 6 all target `String` columns with
no CHECK constraint, which is why none of them needs DDL.

**Decomposition output is not persisted** — ADR-0207's accepted tradeoff, not
reopened. Traceability is preserved through `model_runs` instead: every stage's
row carries `request_id`, `job_id`, `operation`, and `prompt_version_id`, so a
reviewer can trace which run produced which `generated_test_cases` rows even
though the decomposition itself is not queryable. N5 additionally logs the
decomposition's ten key names and their cardinalities (**not their contents** —
the requirement text is untrusted and potentially sensitive, §26.5) at INFO with
the `model_run_id` bound, so the shape of what was extracted is recoverable from
logs without duplicating requirement text into a second store.

**`include_accessibility_cases: true` is rejected with 422 before any provider
call**, per ADR-0208. The check lives in a service-level function in
`qe_test_generation` so it is enforceable by direct call, not only through the
API route — matching §26.2's "checked at both API-route level and
service/business-logic level" and making the N5 gate's direct-call assertion
meaningful.

## Consequences

- One event loop per generation, enforced by a test rather than by convention.
- A billed provider call is recorded even when the generation that made it fails
  and rolls back — the audit trail's integrity no longer depends on the pipeline
  succeeding.
- Every `ACTIVE` prompt version in every environment has walked the full §19
  lifecycle, including seeded ones, so "nothing reaches ACTIVE without passing
  review states" is true of the whole table rather than of hand-written rows only.
- Cost roll-ups by `operation` distinguish all four pipeline stages, and stay
  able to distinguish future frameworks' code generation from this phase's.
- The validation vocabulary is §22.2's, and the case-type vocabulary can express
  what §11.5 lets a requester ask for.
- Two spec pipeline stages that had no owner now have one, with a written mapping
  instead of an assumption.
