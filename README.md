# QE Copilot

AI-Powered Test Generation and Defect Triage Platform.

This repository is at **Phase 1 (Core Platform)**, built on the Phase 0
foundation. It ships a working core: authentication and RBAC, organisations,
projects and repositories with tenant isolation, a persisted job framework
(API → Redis → worker → database → polling), audit logging, a live System
Health API and page, and an auth-gated frontend. Feature work (AI/LLM calls,
RAG, test generation, defect triage, GitHub ingestion) is stubbed with
`# TODO(phase-N):` markers and lands in later phases.

## Architecture

```
apps/
  api/        FastAPI service  (qe_api)     — /healthz, /readyz, /api/v1
  worker/     Celery worker    (qe_worker)  — runs persisted jobs (Redis broker)
  scheduler/  Celery beat      (qe_scheduler) — heartbeat tick
  cli/        CLI              (qe_cli)     — `qe info`, `qe org`
  web/        Next.js + TS frontend (auth-gated)
packages/
  common/         qe_common        — errors, Settings, job/audit/health vocabulary
  observability/  qe_observability — JSON structured logging
  database/       qe_database      — SQLAlchemy models + sessions
  auth/           qe_auth          — tokens, Principal, role -> permission matrix
  ai_gateway/     qe_ai_gateway    — provider interface (phase 2)
  security/       qe_security      — redaction helpers
migrations/    Alembic (organisations, users, roles, user_roles, projects,
               repositories, jobs, audit_logs + pgvector extension)
infrastructure/docker/  Dockerfiles for the Python services and the web app
docs/          architecture, api, security, operations, decisions (ADRs)
```

Apps and packages share one code path via prefixed, importable package names
(`qe_*`) — see `docs/decisions/PHASE0-PLAN.md` (ADR-0001). The worker and API
import the **same** domain packages; there is no duplicated logic.

### API surface (v1)

| Route | Purpose |
| ----- | ------- |
| `POST /api/v1/auth/dev/login` | Dev-mode sign-in; returns an access token (mounted only when `AUTH_DEV_MODE=true`) |
| `GET /api/v1/auth/me` | The caller's identity, roles, and effective permissions |
| `GET/POST/PATCH/DELETE /api/v1/users`, `PUT /api/v1/users/{id}/roles` | User and role management |
| `GET /api/v1/roles` | Assignable roles |
| `GET/PATCH /api/v1/organisations` | The caller's own organisation |
| `GET/POST/PATCH/DELETE /api/v1/projects` | Projects |
| `GET/POST /api/v1/projects/{id}/repositories`, `GET/PATCH/DELETE /api/v1/repositories/{id}` | Repositories |
| `POST /api/v1/jobs` (202), `GET /api/v1/jobs/{id}` | Create a job, then poll its status |
| `GET /api/v1/audit-logs` | The audit trail |
| `GET /api/v1/system-health` | Live status of API, DB, Redis, queue, workers, scheduler |

Every `/api/v1` route except `/ping` requires `Authorization: Bearer <token>`
and is scoped to the caller's organisation. See
[`docs/security/AUTH-DESIGN.md`](docs/security/AUTH-DESIGN.md) for the full
role-to-permission matrix.

## Prerequisites

- Python 3.11+
- Node.js 22+
- Docker + Docker Compose (for the full stack)
- `make`

## Quick start (Docker Compose)

```bash
cp .env.example .env          # adjust if needed; never commit .env
make up                       # docker compose up -d (waits for healthchecks)
curl localhost:8000/healthz   # {"status":"ok"}
curl localhost:8000/readyz    # {"status":"ready", ...} once deps are healthy
open http://localhost:3000    # frontend — sign in with any email address
make down                     # docker compose down -v
```

Signing in as `AUTH_DEV_ADMIN_EMAIL` (default `admin@example.com`) provisions an
administrator; any other address is provisioned as an engineer. To provision a
separate tenant, use the CLI — organisations cannot be created from inside a
tenant-scoped request (ADR-0111):

```bash
qe org create "Acme QA" --admin-email lead@acme.example
qe org list
```

Compose applies database migrations automatically via a one-shot `migrate`
service before the API and worker start.

## Local development (without Docker)

```bash
make install                  # create .venv, install Python (editable) + web deps
# Point Settings at your local Postgres/Redis via env or .env, then:
make migrate                  # alembic upgrade head
make check                    # ruff (format+lint) + mypy + pytest + eslint + tsc
```

Run the services individually:

```bash
uvicorn qe_api.main:app --reload                                   # API
celery -A qe_worker.celery_app:celery_app worker --loglevel=INFO   # worker
celery -A qe_scheduler.beat:celery_app beat --loglevel=INFO        # scheduler
npm --prefix apps/web run dev                                      # frontend
```

## Make targets

| Target             | Description                                             |
| ------------------ | ------------------------------------------------------- |
| `make install`     | Create venv, install Python (editable) + web deps       |
| `make check`       | Full gate: ruff format+lint, mypy, pytest, eslint, tsc  |
| `make test`        | All pytest tests (unit + integration)                   |
| `make test-unit`   | Unit tests only (`-m "not integration"`)                |
| `make test-integration` | Integration tests (need live Postgres + Redis)     |
| `make lint` / `make typecheck` / `make fmt` | Individual Python gates        |
| `make web-build` / `make web-lint` / `make web-typecheck` | Frontend gates    |
| `make web-e2e`     | Playwright end-to-end suite (needs the API running)      |
| `make up` / `make down` | Start / tear down the Docker Compose stack         |
| `make migrate` / `make downgrade` | Alembic upgrade head / downgrade one       |

## Quality & CI

`make check` mirrors the GitHub Actions workflow in `.github/workflows/ci.yml`,
which runs on every push/PR:

- **backend** — ruff format + lint, mypy (strict), Alembic upgrade/downgrade
  round-trip, and unit + integration tests against Postgres (pgvector) and Redis
  service containers.
- **frontend** — eslint, `tsc --noEmit`, `next build`, and the Playwright
  end-to-end suite against a real API, Postgres, and Redis (the flow signs in
  and reads live System Health, so it cannot run against a mock).
- **secret-scan** — gitleaks.

## Configuration

All configuration comes from environment variables (see `.env.example` for the
full list). No secrets are committed. Settings are typed in
`qe_common.config.Settings`.

## Documentation

- `docs/decisions/PHASE0-PLAN.md` — Phase 0 plan and ADRs (0001-0012).
- `docs/decisions/PHASE1-PLAN.md` — Phase 1 plan and ADRs (0101-0112).
- `docs/decisions/PHASE0-BLOCKERS.md` / `PHASE1-BLOCKERS.md` — environmental
  blockers, if any.
- `docs/security/AUTH-DESIGN.md` — authentication, tenancy, and the
  role-to-permission matrix.

## License

MIT — see [LICENSE](LICENSE).
