# Authentication & Authorization — Design Stub

> Status: **stub (Phase 0)**. This documents the intended design; enforcement is
> implemented in a later phase. Phase 0 ships only the `qe_auth` type stubs and
> the `roles` / `user_roles` tables.

## Model
- **Tenancy:** every principal belongs to exactly one `organisation`. All
  resources are scoped by `organisation_id`.
- **Identity:** `users` table; login is out of scope for Phase 0.
- **RBAC:** `roles` (`admin`, `maintainer`, `contributor`, `viewer`) joined to
  users via `user_roles`. `qe_auth.Role` mirrors the seeded role names.

## Request flow (target)
1. Client sends `Authorization: Bearer <token>`.
2. `qe_auth.verify_token` resolves the token to a `Principal`
   (`user_id`, `organisation_id`, `roles`). *(TODO(phase-1): implement.)*
3. A FastAPI dependency injects the `Principal`; route guards assert required
   roles and raise `UnauthorizedError` / `ForbiddenError` (standard envelope).
4. `bind_log_context(user_id=..., project_id=...)` so every log line is
   attributable.

## Token strategy (target)
- Short-lived signed JWTs for API calls; opaque session tokens for the web app.
- Secrets/keys come from the environment (`qe_common.config.Settings`); nothing
  committed. `qe_security.redact` masks tokens in logs.

## Not in Phase 0
- Token issuance/verification, session storage, OAuth/GitHub App login,
  per-route enforcement, rate limiting. All marked `TODO(phase-1)` / `phase-6`.
