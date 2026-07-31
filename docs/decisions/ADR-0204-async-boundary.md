# ADR-0204 — Sync/async boundary: generation is a worker job, never a blocking endpoint

**Status:** Accepted (Phase 2, N1) — **verified against `docs/architecture/design-spec.md` (N0.5)**

## Sources

| Claim | Spec |
|---|---|
| Test generation is an asynchronous request | §13.2 L1152–1154 |
| API returns a job id; worker claims and processes | §13.2 L1161–1179 |
| Job states | §14 L1187–1197 |
| Test-generation job completed within 90 seconds | §30 L2378 |
| Endpoint paths | §16.3 L1623–1631 |

§13.2 L1161–1179 specifies the exact flow this ADR adopts:
`Client → API validates request → Database job created → Queue message published
→ API returns job ID → Worker claims job → Worker processes job → Worker stores
result → Frontend receives status update`.

## Context

Phase 1 built a persisted job framework: the API writes a `jobs` row, moves it
`PENDING → QUEUED`, dispatches over Celery/Redis, and the worker owns every
transition afterwards, writing each to the same row (ADR-0107). Clients poll
`GET /api/v1/jobs/{id}`.

Test generation is the first genuinely slow operation in the platform. A single
generation involves multiple provider calls, each of which can take tens of
seconds on `claude-opus-5` at useful effort levels — and the SDK's own guidance
is to stream anything long-running rather than hold a request open.

A synchronous `POST /test-generation` that blocked until completion would:

- hold an HTTP connection and a worker thread for the full duration;
- put a p99 measured in **minutes** on an endpoint targeted at **<90s**, and
  breach it under any provider slowdown;
- fail the whole request on a transient provider error, with no retry and no
  record of what was attempted;
- lose all work on client disconnect;
- be untestable against the timeout/outage failure modes N10 requires.

## Decision

**Generation is an asynchronous worker job. There is no blocking generation
endpoint.**

- `POST /api/v1/test-generation/requests` **validates input, persists a
  `test_generation_requests` row, creates a Phase 1 job, and returns `202
  Accepted`** with the request record and its `job_id`. It performs no provider
  call.
- The worker claims the job (`QUEUED → RUNNING`, `SELECT … FOR UPDATE`, idempotent
  on redelivery) and runs the pipeline: decompose → generate → validate → persist
  cases → terminal state.
- The client polls `GET /api/v1/test-generation/requests/{request_id}` (or the
  generic `GET /api/v1/jobs/{job_id}`) until `status` is terminal. Both read the
  authoritative database row, not broker state.
- **Endpoint paths are taken from §16.3 L1623–1631**, under the `/api/v1` prefix
  Phase 0 established. An earlier revision of this ADR used
  `POST /api/v1/test-generation` and `GET /api/v1/test-generation/{id}`, which
  did not match the spec; corrected. The full set:

  ```http
  POST /api/v1/test-generation/requests
  GET  /api/v1/test-generation/requests/{request_id}
  GET  /api/v1/test-generation/requests/{request_id}/tests
  POST /api/v1/generated-tests/{test_id}/approve
  POST /api/v1/generated-tests/{test_id}/reject
  POST /api/v1/generated-tests/{test_id}/regenerate
  POST /api/v1/generated-tests/{test_id}/validate
  ```
- **One state machine.** `test_generation_requests.status` mirrors
  `qe_common.jobs.JobState` and every transition is validated by the existing
  `assert_transition`. Phase 2 introduces no second lifecycle vocabulary.
- **Review actions stay synchronous.** Approve, reject, and validate are fast
  database operations and return `200` directly. Only *regenerate* creates a new
  job, because only regenerate calls the provider. *(Inference: §16.3 lists all
  four as `POST` endpoints but does not state which are synchronous. §13.2 L1152
  makes "Test generation" asynchronous, which covers regenerate; the other three
  touch no provider, so §13.1 synchronous handling applies.)*

### Where the <90s target is measured

The target applies to **job wall-clock** — `queued_at` to `finished_at` on the
job row — not to the `POST`, which returns in milliseconds. N10 measures that
interval on a representative input and reports the observed number.

## Consequences

- The API's latency profile is decoupled from provider latency.
- A provider outage fails a job cleanly with a recorded error code, leaving a
  `FAILED` row and a `model_runs` entry — it does not fail an HTTP request with
  nothing written down.
- Retry, idempotent redelivery, and per-attempt accounting come from Phase 1's
  job framework for free rather than being re-invented.
- Clients must poll. That is the same contract they already have for every other
  job, so it adds no new client concept.
