# Authentication & Authorization

> Status: **implemented (Phase 1)**. Phase 0 shipped type stubs and the
> `roles`/`user_roles` tables; Phase 1 implements issuance, verification, and
> per-route enforcement.

## Model
- **Tenancy:** every principal belongs to exactly one `organisation`. All
  resources are scoped by `organisation_id`; cross-tenant reads return **404**
  so the API never confirms another tenant's resource exists (ADR-0106).
- **Identity:** the `users` table. Sign-in goes through an identity provider —
  Phase 1 ships the dev-mode provider (below).
- **RBAC:** `roles` (`engineer`, `quality_engineer`, `qe_lead`,
  `platform_engineer`, `administrator`) joined to users via `user_roles` and
  seeded by migration `0002_roles`. `qe_auth.Role` mirrors those names.

## Request flow
1. Client sends `Authorization: Bearer <token>`.
2. `qe_auth.decode_token` verifies signature, issuer, audience, and expiry, and
   returns `TokenClaims`. Any failure raises `UnauthorizedError` → 401.
3. `qe_api.dependencies.get_principal` loads the user, rejects an unknown or
   deactivated account, and **re-reads roles from `user_roles`** — the token
   authenticates, the database authorises, so revoking a role takes effect
   immediately instead of when the token expires.
4. Route guards (`require(Permission.…)`) and service functions
   (`principal.require(…)`) assert permissions and raise `ForbiddenError` → 403.
5. `bind_log_context(user_id=…)` makes every subsequent log line attributable.

## Roles → permissions
Policy lives in exactly one place, `qe_auth.roles.ROLE_PERMISSIONS`; guards name
permissions, never roles (ADR-0105).

| Permission | engineer | quality_engineer | qe_lead | platform_engineer | administrator |
|---|:--:|:--:|:--:|:--:|:--:|
| `organisation:read`  | ✓ | ✓ | ✓ | ✓ | ✓ |
| `organisation:write` |   |   |   |   | ✓ |
| `user:read`          |   |   | ✓ |   | ✓ |
| `user:write`         |   |   |   |   | ✓ |
| `role:assign`        |   |   |   |   | ✓ |
| `project:read`       | ✓ | ✓ | ✓ | ✓ | ✓ |
| `project:write`      |   |   | ✓ | ✓ | ✓ |
| `repository:read`    | ✓ | ✓ | ✓ | ✓ | ✓ |
| `repository:write`   |   | ✓ | ✓ | ✓ | ✓ |
| `job:read`           | ✓ | ✓ | ✓ | ✓ | ✓ |
| `job:create`         | ✓ | ✓ | ✓ | ✓ | ✓ |
| `audit:read`         |   |   | ✓ | ✓ | ✓ |
| `system:read`        | ✓ | ✓ | ✓ | ✓ | ✓ |

## Token strategy
Short-lived HS256 JWTs (`iss`, `aud`, `sub`, `org`, `email`, `roles`, `iat`,
`exp`, `jti`) signed with `AUTH_SECRET_KEY`, TTL `AUTH_TOKEN_TTL_SECONDS`
(default 1h). The `roles` claim is advisory only — see step 3 above. Keys come
from the environment (`qe_common.config.Settings`); nothing is committed, and
`qe_security.redact` masks tokens in logs.

## Dev-mode identity provider
`POST /api/v1/auth/dev/login {"email": …}` returns an access token. It is
mounted **only** when `AUTH_DEV_MODE=true`, and `Settings` refuses to construct
at all when `ENVIRONMENT=production` with dev mode on or the placeholder signing
key still in place. First sign-in provisions the user in the organisation named
by `AUTH_DEV_ORGANISATION_SLUG` with the `engineer` role;
`AUTH_DEV_ADMIN_EMAIL` is provisioned as `administrator`. Roles are assigned at
creation only, so the provider can never escalate an existing account.

Swapping in a real OIDC issuer means replacing `qe_auth.tokens.decode_token`
with a JWKS-backed verifier: `Principal` resolution, guards, and every route
stay unchanged.

## Not yet implemented
- Refresh tokens, server-side session storage, and cookie/CSRF handling —
  `TODO(phase-6)`.
- OAuth/GitHub App login and per-route rate limiting — `TODO(phase-6)`.
