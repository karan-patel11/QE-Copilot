# Phase 0 — Foundation Plan

Scope confirmed: **Phase 0 (Foundation) only**. This plan is derived from the QE
Copilot design (table names, error format, nav items, job-state machine, and the
stack: FastAPI + Celery + Next.js/TS + Postgres/pgvector + Redis + MinIO).

## In scope
Monorepo skeleton; FastAPI API + async Celery worker + Celery-beat scheduler
shells; Next.js/TypeScript frontend shell; Postgres+pgvector, Redis, MinIO via
Docker Compose; baseline Alembic migration; coding-standard tooling
(Ruff, MyPy strict, Pytest, ESLint, tsc); CI.

## Out of scope (interface stubs only, marked `# TODO(phase-N):`)
Real AI/LLM calls, RAG, test generation, defect triage, GitHub webhook ingestion.

## Task order (dependency-driven)
- **T0** Repo skeleton — DEPS: none
- **T1** Python tooling (pyproject, Ruff, MyPy strict, Pytest, importable packages) — DEPS: T0
- **T2** Common/config/observability (error types, error-code enum, JSON logging, Settings) — DEPS: T1
- **T3** Database + baseline migration (engine/session, Alembic, 6 baseline tables + vector ext) — DEPS: T2
- **T4** API shell (`/api/v1`, `/healthz`, `/readyz`, correlation-id, error handler, OpenAPI) — DEPS: T3
- **T5** Worker + scheduler shells (Celery no-op task, beat tick, Job model + state enum) — DEPS: T3
- **T6** Frontend shell (Next.js, 10 nav routes, typed API client, ESLint, Playwright smoke) — DEPS: T0 (parallel to T1–T5)
- **T7** Docker Compose (postgres/redis/minio/api/worker/scheduler/web, healthchecks) — DEPS: T3–T6
- **T8** Makefile + CI (`make check`, workflow mirroring it) — DEPS: T1–T7

## Architecture Decision Records (one-liners)

- **ADR-0001 — Package layout:** Prefixed importable names (`qe_common`,
  `qe_database`, `qe_api`, …) discovered via a single editable install with
  setuptools multi-root `find.where`, so apps and packages share one code path
  with no duplication and no top-level name collisions.
- **ADR-0002 — Package/dependency manager:** A single root `pyproject.toml`
  (setuptools backend) installed editable; all runtime + dev deps pinned to exact
  versions for reproducibility.
- **ADR-0003 — Async worker:** Celery on Redis (broker + result backend); Redis
  is already required as the app cache, avoiding a second broker dependency.
- **ADR-0004 — Scheduler:** Celery beat in a dedicated process (`apps/scheduler`),
  sharing task definitions with the worker so there is one source of truth.
- **ADR-0005 — Config:** `pydantic-settings` `BaseSettings` loaded from env /
  `.env`; no secrets committed; `.env.example` documents every variable.
- **ADR-0006 — Error format:** A single `ErrorResponse` envelope
  (`{"error": {"code", "message", "request_id", "details"}}`) with a structured
  `ErrorCode` enum, emitted by a global exception handler.
- **ADR-0007 — Structured logging:** JSON logs with the mandated fields
  (timestamp, service, environment, severity, message, request_id, trace_id,
  user_id, project_id, job_id, event_type, error_code); no free-form prints.
- **ADR-0008 — DB driver:** `psycopg` v3 (binary) with SQLAlchemy 2.0; async
  engine for the API readiness probe, sync engine for Alembic migrations.
- **ADR-0009 — pgvector:** Enabled via `CREATE EXTENSION IF NOT EXISTS vector`
  in the baseline migration; the `pgvector/pgvector` image ships the extension.
- **ADR-0010 — Frontend:** Next.js App Router + TypeScript strict + Tailwind;
  a shared typed fetch client is the only backend boundary; Playwright for the
  smoke test.
- **ADR-0011 — IDs:** UUID primary keys (`gen_random_uuid()` via pgcrypto) for
  all baseline tables, so IDs are non-guessable and mergeable across services.
- **ADR-0012 — Spelling:** `organisations` table name kept per the design doc
  (British spelling) even though code identifiers use US spelling elsewhere.

## Verification strategy in this environment
Docker Hub blob downloads are blocked by egress policy (see PHASE0-BLOCKERS.md),
so Compose cannot be brought up here. Postgres 16 + pgvector and Redis are run
natively instead to validate migrations, readiness probes, and the worker
integration test. The Compose file is authored to spec and is the deployment
path where image pulls are permitted.
