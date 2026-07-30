# QE Copilot

AI-Powered Test Generation and Defect Triage Platform.

This repository is the **Phase 0 (Foundation)** scaffold: a runnable monorepo
skeleton with a FastAPI API, a Celery worker and scheduler, a Next.js frontend,
Postgres + pgvector, Redis, and MinIO — wired together with migrations, quality
tooling, and CI. Feature work (AI/LLM calls, RAG, test generation, defect
triage, GitHub ingestion) is stubbed with `# TODO(phase-N):` markers and lands
in later phases.

## Architecture

```
apps/
  api/        FastAPI service  (qe_api)     — /healthz, /readyz, /api/v1
  worker/     Celery worker    (qe_worker)  — async jobs (Redis broker)
  scheduler/  Celery beat      (qe_scheduler)
  cli/        CLI              (qe_cli)     — `qe info`
  web/        Next.js + TS frontend shell
packages/
  common/         qe_common        — errors, error codes, Settings, Job model
  observability/  qe_observability — JSON structured logging
  database/       qe_database      — SQLAlchemy models + sessions
  auth/           qe_auth          — RBAC stubs (phase 1)
  ai_gateway/     qe_ai_gateway    — provider interface (phase 2)
  security/       qe_security      — redaction helpers
migrations/    Alembic (baseline: organisations, users, roles, user_roles,
               projects, repositories + pgvector extension)
infrastructure/docker/  Dockerfiles for the Python services and the web app
docs/          architecture, api, security, operations, decisions (ADRs)
```

Apps and packages share one code path via prefixed, importable package names
(`qe_*`) — see `docs/decisions/PHASE0-PLAN.md` (ADR-0001). The worker and API
import the **same** domain packages; there is no duplicated logic.

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
open http://localhost:3000     # frontend shell
make down                     # docker compose down -v
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
| `make web-e2e`     | Playwright smoke test                                    |
| `make up` / `make down` | Start / tear down the Docker Compose stack         |
| `make migrate` / `make downgrade` | Alembic upgrade head / downgrade one       |

## Quality & CI

`make check` mirrors the GitHub Actions workflow in `.github/workflows/ci.yml`,
which runs on every push/PR:

- **backend** — ruff format + lint, mypy (strict), Alembic upgrade/downgrade
  round-trip, and unit + integration tests against Postgres (pgvector) and Redis
  service containers.
- **frontend** — eslint, `tsc --noEmit`, `next build`, Playwright smoke test.
- **secret-scan** — gitleaks.

## Configuration

All configuration comes from environment variables (see `.env.example` for the
full list). No secrets are committed. Settings are typed in
`qe_common.config.Settings`.

## Documentation

- `docs/decisions/PHASE0-PLAN.md` — Phase 0 plan and ADRs.
- `docs/decisions/PHASE0-BLOCKERS.md` — environmental blockers, if any.
- `docs/security/AUTH-DESIGN.md` — auth/RBAC design stub.

## License

MIT — see [LICENSE](LICENSE).
