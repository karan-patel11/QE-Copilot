# ADR-0212 — Test-generation API: dispatch ordering, boundary validation, regenerate scope

**Status:** Accepted (Phase 2, N6) — written against `docs/architecture/design-spec.md`
**Depends on:** ADR-0204 (async boundary), ADR-0205, ADR-0208 (config), ADR-0209
(gateway/registry boundaries), ADR-0211 (N5 pipeline)
**Adds migration:** `0007_testgen_api`

## Sources

| Claim | Spec |
|---|---|
| The seven test-generation endpoints | §16.3 L1623–1631 |
| Async request flow: job created, job id returned, worker claims | §13.2 L1161–1179 |
| Permissions checked at API-route *and* service level | §26.2 L2100–2103 |
| Idempotency keys are an API security control | §26.8 L2190 |
| Jobs carry an idempotency key | §14 L1218 |
| `user_roles` carries `project_id` | §15.1 L1270 |
| Standard error envelope; errors expose no internals | §17 L1703–1722 |
| Eleven config options; accessibility refused | §11.5 L857–867, ADR-0208 |
| Regenerate one test / regenerate all tests | §11.5 L892–893 |
| Nothing auto-approves | §8.2 L439–447, §11.5 L890 |

---

## Decision 1 — One transaction for request + job, committed before dispatch

### The hazard

`CommittingModelRunRecorder` writes `model_runs` rows on **a separate connection**
(ADR-0211 Decision 2), carrying `request_id` and `job_id` foreign keys. If the
worker's first provider call happens before those rows are durable, every
metering write fails its foreign key. Nothing raises to the caller, no test goes
red — the audit rows are simply never written. This is the failure mode N5's
hazard list flagged against this node, and it is invisible by construction.

### The decision

**`test_generation_requests` and its `jobs` row are inserted in one transaction,
that transaction commits, and only then is the Celery message sent.**

The commit point is explicit and is the last statement of
`create_generation_request` before `_dispatch`:

```
BEGIN
  INSERT test_generation_requests  (flush → request.id)
  INSERT jobs  payload={"request_id": request.id}  (flush → job.id)
  UPDATE test_generation_requests SET job_id = job.id
  UPDATE jobs SET state='QUEUED', queued_at=now()
  INSERT audit_logs  (request created, job created)
COMMIT                         ← both rows durable here
                               ← nothing has been dispatched yet
send_task("qe_worker.run_job", [job.id])
```

The circular reference — the request needs `job_id`, the job's payload needs
`request_id` — is resolved by two flushes inside the one transaction rather than
by two transactions. A flush assigns the primary key without committing, so both
ids exist before either row is visible to anyone else.

### Why `create_job` is not reused verbatim

`qe_api.services.jobs.create_job` commits **three times** (after audit, after the
`QUEUED` transition, after recording the task id). Calling it with a
`test_generation_requests` row pending in the same session would commit that row
at an arbitrary point inside someone else's function, and any later failure would
leave a committed request with no job. N6 therefore has its own service function
with one commit, and `create_job` is left untouched for its Phase 1 callers.

That is a deliberate duplication of about fifteen lines, taken because the
alternative — making `create_job` transaction-boundary-agnostic — changes the
behaviour of every Phase 1 caller to serve one new one.

### Dispatch failure after commit

If `send_task` raises, the rows are already durable. Both are moved to `FAILED`
in a **follow-up transaction** with `error_code = SERVICE_UNAVAILABLE`, and the
route returns 503. A request that exists but was never queued is the honest
record; deleting it would erase the evidence that the attempt happened.

---

## Decision 2 — Configuration is validated in the route, before anything is written

### The hazard

Today `validate_configuration` runs in `_preflight`, **inside the worker**. So a
request with `include_accessibility_cases: true` — which ADR-0208 refuses — is
persisted, becomes a job, is dispatched, is claimed by a worker, and only then
fails. The API returned `202 Accepted` for a request the platform had already
decided it would not honour.

### The decision

**`validate_configuration` (which calls `assert_supported`) runs synchronously in
`POST /test-generation/requests`, before any row is created.** On failure the
route returns **422** with the standard envelope and writes nothing: no
`test_generation_requests` row, no `jobs` row, no `audit_logs` row, no
`model_runs` row.

The worker's `_preflight` check **stays**. It is not redundant: §26.2 L2100–2103
requires permission and validation checks at both the API-route level and the
service/business-logic level, and the pipeline is reachable from the CLI and from
tests without passing through a route. The route check makes the refusal cheap;
the service check makes it certain.

Named test: `test_d2_unsupported_config_rejected_before_job_creation` — asserts
422 and zero rows in `test_generation_requests`, `jobs`, and `model_runs`, by
direct query.

---

## Decision 3 — Regenerate re-runs code generation for one case, and nothing else

§16.3 L1629 gives a per-case endpoint (`POST /generated-tests/{test_id}/regenerate`)
while N5's code generation is one call covering every case in a request
(ADR-0211 Decision 1). Those two shapes have to be reconciled explicitly.

### The decision

**Regenerate re-runs the `pytest_codegen` stage for that single case. It does not
re-run decomposition, planning, or detailed generation, and it does not touch any
other case in the request.**

| | |
|---|---|
| Provider calls | exactly **1** (`pytest_codegen`) |
| Rows changed | one `generated_test_cases` row: `generated_code`, the two validity booleans, `validation_errors`, `is_edited` unchanged |
| Rows created | one `model_runs` row |
| Other cases | untouched, including their `human_status` |

### Why not re-run all four stages

The case body — title, objective, steps, expected result — is what a reviewer has
already read. Re-running detailed generation would silently replace it with
different content while the reviewer believed they were asking to fix the code.
Re-running the whole request would additionally discard the review state of every
*other* case, which §8.2 makes the human's to give and not ours to reset.

§11.5 L893 does list "Regenerate all tests" as a separate user action. §16.3
provides **no endpoint for it**, so it is **deferred with its absence named**
rather than smuggled into the per-case route.

### The limitation, stated

Regenerate cannot repair a defective *case* — only defective *code*. A case that
failed at §22.2 level 2 (required fields) will fail again, because the same case
body is sent. The remedy for a bad case is a new request. Recorded here so the
narrowness is a decision rather than a surprise.

### `model_runs` attribution

The new row carries **the original `request_id`**, taken from
`generated_test_cases.request_id` — not a new request, and never null. Cost and
evaluation therefore roll up to the request that owns the case, so a request's
total cost includes every regeneration performed against it. `job_id` is the new
regeneration job's id, so the two are distinguishable: same request, different
job.

Regeneration is asynchronous (ADR-0204: "only regenerate calls the provider"), so
it returns **202 + `job_id`** under a new `JobKind.TEST_CASE_REGENERATION`.

---

## Decision 4 — Responses surface the prompt-version **map**, never the singular column

`test_generation_requests.prompt_version` is one `String(64)`. Four prompts are
involved in every generation, and the singular column holds only `testgen-v1`
(ADR-0211). A response field called "the prompt version used" that returns it
would be **wrong about three stages out of four**.

### The decision

**The response schema exposes `prompt_versions: dict[str, str]`**, sourced from
`summary.prompt_versions`, keyed by `ModelOperation` value:

```json
"prompt_versions": {
  "requirement_decomposition": "decompose-v1",
  "test_plan":                 "testplan-v1",
  "test_generation":           "testgen-v1",
  "pytest_codegen":            "pytest_codegen-v1"
}
```

**The singular column is not exposed by any endpoint.** It remains an internal
convenience for indexing and for the future `prompt_versions` foreign-key
backfill (ADR-0209 Decision 2). It is empty until the pipeline reaches its
provider stages, so the response field is `{}` on a pending request — an empty map
being the honest "no stage has run yet", where a singular `null` would be
ambiguous between that and "not recorded".

---

## Decision 5 — Template drift gets its own error code, distinguishable from a retryable failure

`PromptTemplateDriftError` means a source template was edited without registering
a new version. **No retry can fix it and no operator action inside the running
application can clear it** — it needs a code change and a re-seed. Rendering it
as a generic failure would put a "Retry" button in front of a user for whom
retrying is guaranteed to fail.

### The decision

The code is **`PROMPT_TEMPLATE_DRIFT`**, which already exists in `ErrorCode`
(added in N3/N4) and is already carried by `PromptTemplateDriftError`. It is
distinct from `PROVIDER_ERROR` / `PROVIDER_TIMEOUT` (retryable, 502/504) and from
`INTERNAL_ERROR`.

**What N6 adds is the path by which it reaches a client.** Drift is raised inside
the worker, so it never becomes an HTTP status — it becomes a failed request row.
Today that row carries only a free-text `error` string, which a frontend would
have to pattern-match to branch on. So:

- migration `0007` adds **`test_generation_requests.error_code`** (`String(64)`, nullable);
- `_mark_failed` records `exc.code.value` when the exception is an `AppError`, and
  `INTERNAL_ERROR` otherwise;
- the response schema exposes `error_code` alongside `error`.

N7 branches on `error_code == "PROMPT_TEMPLATE_DRIFT"` to render "contact
engineering" instead of a retry affordance. The rule generalises: any code in the
`PROVIDER_*` family is retryable, `PROMPT_TEMPLATE_DRIFT` and
`TEST_CONFIG_UNSUPPORTED` are not.

---

## Decision 6 — Unmet requested kinds are a reported gap, never an error

ADR-0208 is explicit that the `include_*` flags are requests, not guarantees: a
requirement with no failure conditions legitimately produces no negative cases,
and "reporting the gap is honest; fabricating a negative case to satisfy a flag is
not."

### The decision

**`unmet_requested_kinds` is a first-class field on the request response, and an
empty kind bucket is never an error.** The response carries:

| Field | Meaning |
|---|---|
| `unmet_requested_kinds: list[str]` | requested kinds that no generated case carries |
| `coverage_notes: str` | the planner's own account of what it did not cover |
| `produced_by_type: dict[str, int]` | what actually came back, by kind |

A request whose every case is a positive case, with
`include_negative_cases: true`, still reaches `COMPLETED` and still returns 200.
No handler treats a missing kind as a failure, and nothing synthesises a case to
fill the bucket.

Named test: `test_d6_unmet_kinds_reported_not_errored`.

---

## RBAC (§26.2) — three new permissions, and one limitation stated plainly

### New permissions

| Permission | Routes |
|---|---|
| `TEST_GENERATION_READ` | the three `GET` routes |
| `TEST_GENERATION_CREATE` | `POST /test-generation/requests`, `POST …/regenerate` |
| `TEST_CASE_REVIEW` | `POST …/approve`, `POST …/reject`, `POST …/validate` |

Granted per the N6 brief — Engineer, Quality Engineer, and QE Lead may create and
approve; Administrator holds everything by construction. **Platform Engineer gets
`TEST_GENERATION_READ` only**: §6.4 makes it an operations role, and approving a
test is a quality judgement rather than an operational one.

This does not fit the existing inheritance chain
(`ENGINEER ⊂ QUALITY_ENGINEER ⊂ PLATFORM_ENGINEER`), because anything granted to
Engineer reaches Platform Engineer transitively. The two authoring permissions are
therefore composed onto the three roles explicitly rather than added to the
Engineer base set. Recorded because it is the one place the role matrix stops
being a pure chain, and a future reader will otherwise "tidy" it and silently
grant approval rights to Platform Engineer.

Guards name permissions, never roles (ADR-0105), and every route carries one —
§26.2 L2100–2103 requires the check at the route level, not only in the service.

### Limitation: "project scope" is organisation scope in Phase 2

The brief asks for create/approve "within their project scope only". **Per-project
role scoping does not exist in this codebase**: §15.1 L1270 specifies
`user_roles.project_id`, and the shipped `user_roles` table has only `user_id` and
`role_id`. A role is therefore held organisation-wide.

What N6 actually enforces:

1. **Tenant isolation** — every query filters on `principal.organisation_id`, and a
   row belonging to another organisation returns **404, not 403** (ADR-0106), so
   existence is not disclosed across tenants.
2. **Project existence and ownership** — `POST` resolves `project_id` through the
   existing project service, which 404s for another tenant's project.

Within one organisation, any role holding `TEST_GENERATION_CREATE` may create a
request against any project in that organisation. That is **weaker than the brief
asks for**, it is a pre-existing Phase 1 schema gap and not something N6 can close
without a migration to `user_roles` and a `Principal` that carries project scope,
and it is logged in `PHASE2-BLOCKERS.md` rather than papered over.

---

## Migration `0007_testgen_api`

Two columns on `test_generation_requests`, both named and justified per ADR-0203's
rule that every non-spec column is accounted for:

| Column | Type | Why |
|---|---|---|
| `idempotency_key` | `String(255)` NULL | §26.8 L2190. Without it a client retry creates a **second full generation** — four more billed provider calls for one logical request. No idempotency mechanism existed anywhere in the codebase before this. |
| `error_code` | `String(64)` NULL | Decision 5. A structured code the frontend can branch on, instead of pattern-matching a free-text message. |

Index:

| Index | Shape | Why |
|---|---|---|
| `uq_test_generation_requests_idempotency` | `UNIQUE (organisation_id, idempotency_key) WHERE idempotency_key IS NOT NULL` | Partial, so the many rows with no key do not collide. Scoped per organisation because a key is only unique to the client that issued it. |

### Idempotency semantics

A `POST` carrying `Idempotency-Key` that matches an existing row **in the same
organisation** returns **202 with that row and its existing `job_id`**, and
creates nothing. It does not compare request bodies: §26.8 asks for the key, and
"same key, different body" is a client defect that a 409 would report but not
prevent. Recorded as a deliberate narrowing.

`jobs` gets **no** idempotency column in this phase, though §14 L1218 specifies
one. The generation request is the idempotent unit a client actually retries, and
adding an unused column to a Phase 1 table would imply a guarantee nothing
enforces. Logged as a known gap.

## Consequences

- The metering foreign keys are satisfied by construction, not by timing luck.
- A refused configuration costs nothing: no rows, no job, no provider call.
- Regenerate is cheap and narrow, and its narrowness is documented where callers
  will read it.
- No endpoint can misreport which prompt produced a generation.
- The frontend can distinguish "retry might work" from "this needs an engineer".
- A gap in requested coverage is reported as data, which is what makes the report
  trustworthy.
- Two spec gaps inherited from Phase 1 — `user_roles.project_id` and the job
  idempotency key — are named rather than silently accepted.
