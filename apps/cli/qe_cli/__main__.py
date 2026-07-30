"""QE Copilot CLI entry point.

Phase 0 provides a minimal ``qe`` command exposing environment and version
introspection. Feature subcommands (generate, triage, ingest) arrive in later
phases.
"""

from __future__ import annotations

import argparse
import json

from qe_common.config import get_settings


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qe", description="QE Copilot CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("info", help="Print service/environment info as JSON")
    # TODO(phase-4): `qe generate`  TODO(phase-5): `qe triage`
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "info":
        return _cmd_info()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
