"""Idempotent registration of the source-resident templates (ADR-0211 Decision 3).

Nothing else puts rows in ``prompt_versions``, so on a virgin database the first
``get_active()`` of a generation run would raise. This module is what makes a
fresh environment usable — and it is deliberately an *operator action*
(``qe prompts seed``) rather than a migration or a startup hook:

- a migration calling the service layer is pinned to today's
  ``transition_status()`` signature forever, and only ever runs once, so a
  template added later would never be seeded;
- a startup hook makes every process boot write to the database, couples
  readiness to seeding, and races when several workers start at once.

**Seeding walks the full §19 lifecycle.** Every version reaches ``ACTIVE`` through
five ``transition_status()`` calls, never a direct write. The ordering guarantee
in ADR-0209 Decision 3 lives in that function; a bootstrap path that bypassed it
would make the guarantee false for precisely the rows every generation depends on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_common.prompts import PromptStatus
from qe_database.models import PromptVersion
from qe_observability import get_logger
from qe_prompt_registry.service import create_version, transition_status
from qe_prompt_registry.templates import SOURCE_TEMPLATES, SourceTemplate

logger = get_logger(__name__)

#: The five forward transitions from ``DRAFT`` to ``ACTIVE``, in §19 order.
#: ``DRAFT`` is where ``create_version()`` lands, so it is not repeated here.
PATH_TO_ACTIVE: tuple[PromptStatus, ...] = (
    PromptStatus.OFFLINE_EVALUATION,
    PromptStatus.REVIEW,
    PromptStatus.STAGING,
    PromptStatus.LIMITED_RELEASE,
    PromptStatus.ACTIVE,
)


@dataclass(frozen=True, slots=True)
class SeedOutcome:
    """What seeding did to one template."""

    version: str
    #: ``created`` | ``advanced`` | ``already_active`` | ``deprecated_skipped``
    action: str
    transitions: int
    final_status: PromptStatus

    @property
    def as_dict(self) -> dict[str, str | int]:
        return {
            "version": self.version,
            "action": self.action,
            "transitions": self.transitions,
            "final_status": self.final_status.value,
        }


def seed_template(
    session: Session,
    template: SourceTemplate,
    *,
    created_by: uuid.UUID | None = None,
) -> SeedOutcome:
    """Bring one template to ``ACTIVE``, from wherever it currently is.

    Idempotent by construction: re-running against an already-active version is a
    no-op, and a version stranded part-way through the lifecycle is carried the
    rest of the way rather than duplicated.

    A ``DEPRECATED`` version is left alone. It is terminal and ADR-0209 keeps no
    backward edge — the response to needing it again is a new version, not a
    resurrection that would erase the record of its retirement.
    """
    existing = session.scalar(
        select(PromptVersion).where(PromptVersion.version == template.version)
    )

    if existing is None:
        row = create_version(session, template=template, created_by=created_by)
        action = "created"
    else:
        row = existing
        action = "advanced"

    status = PromptStatus(row.status)
    if status is PromptStatus.DEPRECATED:
        logger.warning(
            "prompt version is deprecated; leaving it alone",
            extra={"event_type": "prompt.seed_skipped", "prompt_version": row.version},
        )
        return SeedOutcome(row.version, "deprecated_skipped", 0, status)

    if status is PromptStatus.ACTIVE:
        return SeedOutcome(
            row.version, "already_active" if action == "advanced" else action, 0, status
        )

    # Walk only the remaining steps, so a half-seeded row converges rather than
    # failing on a transition it has already made.
    remaining = PATH_TO_ACTIVE[PATH_TO_ACTIVE.index(_next_status(status)) :]
    for target in remaining:
        row = transition_status(session, row.id, target)

    logger.info(
        "prompt version seeded to ACTIVE",
        extra={
            "event_type": "prompt.seeded",
            "prompt_version": row.version,
            "transitions": len(remaining),
        },
    )
    return SeedOutcome(row.version, action, len(remaining), PromptStatus(row.status))


def _next_status(current: PromptStatus) -> PromptStatus:
    """The one legal successor of ``current`` on the path to ``ACTIVE``."""
    if current is PromptStatus.DRAFT:
        return PATH_TO_ACTIVE[0]
    return PATH_TO_ACTIVE[PATH_TO_ACTIVE.index(current) + 1]


def seed_all(
    session: Session,
    *,
    created_by: uuid.UUID | None = None,
) -> list[SeedOutcome]:
    """Seed every source-resident template, oldest version string first.

    Does not commit — the caller owns the transaction boundary (§37 L2743), so a
    partial seed rolls back as a unit rather than leaving some prompts active and
    others stranded mid-lifecycle.
    """
    return [
        seed_template(session, SOURCE_TEMPLATES[version], created_by=created_by)
        for version in sorted(SOURCE_TEMPLATES)
    ]


__all__ = ["PATH_TO_ACTIVE", "SeedOutcome", "seed_all", "seed_template"]
