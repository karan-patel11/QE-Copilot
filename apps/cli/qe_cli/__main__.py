"""QE Copilot CLI entry point.

Besides environment introspection, the CLI owns the operations that cannot be
performed from inside a tenant-scoped API request (ADR-0111): provisioning and
removing organisations, and seeding a tenant's first administrator. It connects
with database credentials rather than as a principal, so it is an operator tool.
"""

from __future__ import annotations

import argparse
import json
import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from qe_auth import Role
from qe_common.config import get_settings
from qe_database.models import Organisation, User
from qe_database.models import Role as RoleRow
from qe_database.session import get_engine

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    return _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")[:255]


def _cmd_info() -> int:
    settings = get_settings()
    print(
        json.dumps(
            {
                "service": settings.service_name,
                "environment": settings.environment,
                "version": "0.0.0",
            }
        )
    )
    return 0


def _cmd_org_list() -> int:
    with Session(get_engine()) as session:
        rows = session.execute(select(Organisation).order_by(Organisation.slug)).scalars().all()
        print(json.dumps([{"id": str(o.id), "name": o.name, "slug": o.slug} for o in rows]))
    return 0


def _cmd_org_create(name: str, slug: str | None, admin_email: str | None) -> int:
    """Provision a tenant and, optionally, its first administrator."""
    resolved_slug = _slugify(slug or name)
    if not resolved_slug:
        print(json.dumps({"error": "a non-empty slug is required"}))
        return 2

    with Session(get_engine()) as session:
        existing = session.execute(
            select(Organisation).where(Organisation.slug == resolved_slug)
        ).scalar_one_or_none()
        if existing is not None:
            print(json.dumps({"error": f"organisation {resolved_slug!r} already exists"}))
            return 2

        org = Organisation(name=name, slug=resolved_slug)
        session.add(org)
        session.flush()

        payload: dict[str, str] = {"id": str(org.id), "name": org.name, "slug": org.slug}
        if admin_email:
            role = session.execute(
                select(RoleRow).where(RoleRow.name == Role.ADMINISTRATOR.value)
            ).scalar_one()
            user = User(organisation_id=org.id, email=admin_email.strip().lower(), is_active=True)
            user.roles.append(role)
            session.add(user)
            session.flush()
            payload["administrator_id"] = str(user.id)
            payload["administrator_email"] = user.email
        session.commit()
        print(json.dumps(payload))
    return 0


def _cmd_org_delete(slug: str) -> int:
    """Remove a tenant and, by cascade, every row inside it."""
    with Session(get_engine()) as session:
        org = session.execute(
            select(Organisation).where(Organisation.slug == slug)
        ).scalar_one_or_none()
        if org is None:
            print(json.dumps({"error": f"organisation {slug!r} not found"}))
            return 2
        session.execute(delete(Organisation).where(Organisation.id == org.id))
        session.commit()
        print(json.dumps({"deleted": slug}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qe", description="QE Copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="Print service/environment info as JSON")

    org = sub.add_parser("org", help="Manage organisations (tenants)")
    org_sub = org.add_subparsers(dest="org_command", required=True)
    org_sub.add_parser("list", help="List organisations")

    create = org_sub.add_parser("create", help="Provision an organisation")
    create.add_argument("name")
    create.add_argument("--slug", default=None, help="Defaults to a slug derived from name")
    create.add_argument("--admin-email", default=None, help="Seed a first administrator")

    remove = org_sub.add_parser("delete", help="Delete an organisation and all its data")
    remove.add_argument("slug")

    # TODO(phase-4): `qe generate`  TODO(phase-5): `qe triage`
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "info":
        return _cmd_info()
    if args.command == "org":
        if args.org_command == "list":
            return _cmd_org_list()
        if args.org_command == "create":
            return _cmd_org_create(args.name, args.slug, args.admin_email)
        if args.org_command == "delete":
            return _cmd_org_delete(args.slug)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
