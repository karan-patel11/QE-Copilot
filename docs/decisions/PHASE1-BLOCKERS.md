# Phase 1 — Blockers

**None.** Every COMPLETION-GATE criterion was verified live in this environment.

## Phase 0's BLOCKER-1 is closed

`docs/decisions/PHASE0-BLOCKERS.md` recorded that Docker Hub blob downloads were
refused (HTTP 403 from the signed CloudFront blob host), so `docker compose up`
could not be exercised and Postgres/Redis were run natively instead.

That restriction does not apply in this environment: all images pull, and the
full stack was built and run for Phase 1.

```
$ docker compose ps -a --format '{{.Service}}\t{{.Status}}'
api        Up 41 seconds (healthy)
migrate    Exited (0) 41 seconds ago
minio      Up 10 hours (healthy)
postgres   Up 10 hours (healthy)
redis      Up 10 hours (healthy)
scheduler  Up 43 seconds (healthy)
web        Up 35 seconds (healthy)
worker     Up 41 seconds (healthy)
```

`migrate` is a one-shot service: `Exited (0)` is its success state, and the API
and worker start only after it completes successfully
(`depends_on: condition: service_completed_successfully`).

## Issues hit during the build, and their root-cause fixes

None were left masked; each was fixed at the cause rather than worked around.

1. **`MissingGreenlet` when serialising an updated row.** `updated_at` is
   computed by the database (`onupdate=now()`), so after an UPDATE the attribute
   is expired and reading it triggers lazy IO from a context that cannot await.
   Fixed by `commit_and_refresh()`, which performs that IO explicitly — not by
   dropping the column from the response model.

2. **Deleting a project with repositories returned 409.** The ORM relationship
   was loading children and trying to NULL their `NOT NULL` foreign key, fighting
   the database's `ON DELETE CASCADE`. Fixed with
   `cascade="all, delete", passive_deletes=True` on the relationships — not by
   catching the IntegrityError.

3. **Jobs stayed `QUEUED` during the T5 test run.** A stale Compose worker
   container was consuming from the same Redis queue and rejecting the message
   (`KeyError: 'qe_worker.run_job'`). Root cause was a stale image, fixed by
   rebuilding; the test was not weakened. The same class of failure appeared once
   more as `Can't locate revision identified by '0003_jobs'` when only some
   services were rebuilt — `docker compose build` (all services) is required
   after a migration is added, since `migrate` is its own image.

4. **`example.test` / `.local` addresses rejected with 422.** `email-validator`
   refuses special-use TLDs. Fixed by using `example.com` in fixtures and as the
   dev administrator default — the validation is correct and was left in place.

5. **A Playwright assertion matched Next.js's route announcer**, which carries
   `role="alert"`. Fixed by giving the app's own loading/error/empty components
   explicit test ids rather than loosening the assertion.
