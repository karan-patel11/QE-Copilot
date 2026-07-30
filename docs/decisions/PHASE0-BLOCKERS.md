# Phase 0 — Blockers

Tracks COMPLETION-GATE criteria that could not be verified live in this build
environment, with evidence and attempts. Root causes are environmental (egress
policy), not defects in the scaffold.

---

## BLOCKER-1 — Docker Hub image blobs are not fetchable (egress policy)

**Affects gate 1:** `docker compose up -d` → every service healthy.

**Command**
```
docker pull pgvector/pgvector:pg16
docker pull redis:7-alpine
docker pull minio/minio:latest
docker pull python:3.11-slim
docker pull node:22-slim
```

**Error (identical for every image — manifest resolves, blob download denied)**
```
unknown: failed to copy: httpReadSeeker: failed open: unexpected status from
GET request to https://production.cloudfront.docker.com/registry-v2/docker/
registry/v2/blobs/sha256/.../data?...: 403 Forbidden
```

**Attempts**
1. Direct `docker pull` — 403 on the blob host (`production.cloudfront.docker.com`).
2. Retried each image 3× with exponential backoff (2s/4s/8s) — same 403.
3. Checked the agent proxy: `curl "$HTTPS_PROXY/__agentproxy/status"` shows
   `recentRelayFailures: []`, i.e. the 403 originates at Docker Hub's signed
   CloudFront blob URL, which does not survive the re-terminating egress proxy.
   Docker Hub hosts are not in the proxy `noProxy` allowlist (unlike pypi/npm).

**Impact & mitigation**
- The Compose file and all Dockerfiles are authored to spec and pass
  `docker compose config` (syntax + interpolation validated; all 8 services
  parse). They are the deployment path wherever Docker Hub pulls are permitted.
- To keep the *substance* of the blocked gates verified, the equivalent
  dependencies were run **natively** in this environment and every dependent
  gate was exercised against them:
  - **PostgreSQL 16 + pgvector** (apt: `postgresql-16`, `postgresql-16-pgvector`)
    → gate 2 (migrations up/downgrade round-trip) and gate 3 (`/readyz` 200).
  - **Redis** (apt: `redis-server`) → gate 3 (`/readyz` 200) and gate 4
    (worker task via Redis, scheduler tick).
- Therefore only the literal `docker compose up` invocation is BLOCKED; the
  behaviours it would prove are independently verified. Re-run
  `docker compose up -d` in an environment with Docker Hub access to close it.

**Status:** BLOCKED (environmental). No code change would resolve it here.
