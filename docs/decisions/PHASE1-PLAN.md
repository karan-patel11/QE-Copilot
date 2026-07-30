# Phase 1 — Core Platform Plan

Builds on the verified Phase 0 foundation (repo skeleton, FastAPI/worker/scheduler
shells, Next.js shell, Compose stack, baseline migration `0001_baseline`,
tooling + CI). Phase 0 artefacts are treated as stable and are not re-scaffolded.

## In scope
Authentication; users/roles/RBAC; organisations + projects with tenant isolation;
repositories; a real persisted job framework (API → Redis → worker → DB state
transitions → polling); audit logging; a live System Health API + page; and the
frontend shell wired to those APIs behind an auth gate.

## Out of scope (still `# TODO(phase-N):` stubs)
AI/LLM calls, RAG/knowledge base, test generation, CI ingestion, defect triage.

## Task order (dependency-driven)
- **T1** Auth — dev-mode identity provider + JWT bearer verification, `Principal`
  dependency, protected-route guard, roles seeded by migration `0002`. DEPS: none
- **T2** Users & RBAC — users/roles/user_roles CRUD, permission matrix enforced at
  route *and* service level. DEPS: T1
- **T3** Organisations & Projects — CRUD + organisation-scoped tenant isolation.
  DEPS: T2
- **T4** Repositories — CRUD tied to projects, FK + tenancy enforced. DEPS: T3
- **T5** Job framework — `jobs` table (migration `0003`), create API, Celery/Redis
  dispatch, worker-side persisted state transitions, polling endpoint. DEPS: T3
- **T6** Audit logging — `audit_logs` table (migration `0004`), audit service wired
  into every mutating action from T2–T5, read API. DEPS: T2–T5
- **T7** System Health — live API (uptime, DB/Redis latency, queue depth, worker
  and scheduler liveness, job counts) + frontend page. DEPS: T5
- **T8** Frontend integration — login flow, auth gate, Overview + System Health +
  Administration wired to real APIs with loading/empty/error states, Playwright
  covering login → Overview → System Health. DEPS: T1–T7

## Architecture Decision Records (one-liners)

- **ADR-0101 — Identity provider:** Phase 1 ships the *documented dev-mode identity
  provider* option. `POST /api/v1/auth/dev/login` mints a platform JWT for an email
  and is mounted only when `AUTH_DEV_MODE=true`; `Settings` refuses to start in
  `production` with dev mode on or the signing key left at its placeholder. The
  token *verifier* is provider-agnostic, so an external OIDC issuer plugs in later
  without touching route guards.
- **ADR-0102 — Token format:** short-lived HS256 JWTs (`iss`/`aud`/`sub`/`exp`/
  `iat`/`jti` + `org` and `roles` claims), signed with `AUTH_SECRET_KEY` from the
  environment. `pyjwt` is the only new runtime dependency. No refresh tokens or
  server-side sessions in Phase 1 (`TODO(phase-6)`).
- **ADR-0103 — Dev-mode auto-provisioning:** first dev login creates the user in the
  `default` organisation with the `engineer` role; the address in
  `AUTH_DEV_ADMIN_EMAIL` is provisioned as `administrator`. Existing users keep the
  roles recorded in the database. Dev mode never mutates roles after creation.
- **ADR-0104 — Role vocabulary:** the five design roles — `engineer`,
  `quality_engineer`, `qe_lead`, `platform_engineer`, `administrator` — replace the
  Phase 0 placeholder names (`admin`/`maintainer`/`contributor`/`viewer`), which
  were never seeded. Migration `0002` seeds them.
- **ADR-0105 — Permission model:** roles are mapped to a `Permission` enum by a
  single static matrix in `qe_auth`. Route guards depend on permissions, never on
  role names, so the matrix is the one place authorisation changes.
- **ADR-0106 — Tenant isolation:** every principal belongs to exactly one
  organisation and every query is filtered by `organisation_id` (as stated in
  `docs/security/AUTH-DESIGN.md`). Cross-tenant reads return **404**, not 403, so
  the API never confirms that another tenant's resource exists. Per-project
  membership (a `project_members` table) is *not* part of the design's table list
  and is deferred rather than invented.
- **ADR-0111 — Organisation lifecycle:** the organisation *is* the tenant
  boundary, so it cannot be created or destroyed from inside a tenant-scoped
  request — the creating principal would have no way to reach the new tenant, and
  deleting your own tenant deletes your own account. The API therefore exposes
  read + rename of the caller's own organisation; provisioning and removal are
  operator actions in the CLI (`qe org create|list|delete`), which connects with
  database credentials rather than as a principal.
- **ADR-0112 — Slug immutability:** `organisations.slug` and `projects.slug` are
  identifiers, not display names. Create derives a slug from the name when one is
  not supplied; update changes `name`/`description` only, so URLs and external
  references stay stable.
- **ADR-0107 — Job dispatch:** the API persists a job row, transitions it to
  `QUEUED`, then dispatches `qe_worker.run_job(job_id)` over the existing Celery/
  Redis broker. The worker owns every subsequent transition and writes each one to
  the database, so polling reads the authoritative state. Transitions are validated
  against `qe_common.jobs.ALLOWED_TRANSITIONS` in both processes.
- **ADR-0108 — Audit logging:** an explicit `record_audit()` call in each mutating
  service function (rather than implicit middleware), so the actor, entity id, and
  before/after payload are captured accurately and the write shares the caller's
  transaction — an audited action and its audit row commit atomically.
- **ADR-0109 — Health of runtime components:** worker liveness comes from the
  Celery control plane (`inspect ping`) and scheduler liveness from a Redis
  heartbeat key written by a beat task. The API does **not** mount the Docker
  socket to shell out to `docker ps` — that would grant the API container root-
  equivalent host access for strictly less information than the control plane
  already provides.
- **ADR-0110 — Frontend session storage:** the JWT is held in `localStorage` and
  attached by the typed API client; a client-side `AuthGate` redirects
  unauthenticated users to `/login`. Cookie-based sessions with CSRF protection are
  deferred to the phase that adds server-side sessions (`TODO(phase-6)`).

## Verification strategy
Unlike Phase 0, Docker Hub pulls succeed in this environment: the full Compose
stack (postgres/redis/minio/api/worker/scheduler/web) is up and healthy, so every
gate — migrations, readiness, worker round-trip, end-to-end flow — is verified
against live services rather than native substitutes.
