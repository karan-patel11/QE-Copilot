"""Service layer: all business rules, tenancy filtering, and audit writes.

Routers stay thin — they parse input, call a service with the caller's
:class:`~qe_auth.principal.Principal`, and serialise the result. Services
re-assert permissions themselves so they are safe to call from a worker or a
script that has no HTTP layer above it.
"""
