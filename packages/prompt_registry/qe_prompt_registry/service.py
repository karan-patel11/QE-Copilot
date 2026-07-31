"""Prompt-registry service layer (ADR-0209).

Owns the ``prompt_versions`` table. Nothing else queries it directly (§12.2); the
gateway in particular never reads it at all, which is what keeps the gateway
unable to invent a ``prompt_version_id`` (ADR-0209 Decision 5).

The database enforces the *set* of legal statuses via a CHECK constraint and the
one-active invariant via a partial unique index. This module enforces the
*ordering* between statuses, which a CHECK structurally cannot see.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from qe_common.errors import (
    PromptTemplateDriftError,
    PromptVersionNotFoundError,
)
from qe_common.prompts import (
    PromptStatus,
    assert_transition,
    assert_version_matches_name,
)
from qe_database.models import PromptVersion
from qe_observability import get_logger
from qe_prompt_registry.templates import SourceTemplate, get_source_template, sha256_of

logger = get_logger(__name__)


def create_version(
    session: Session,
    *,
    template: SourceTemplate,
    created_by: uuid.UUID | None = None,
) -> PromptVersion:
    """Register a source-resident template as a new ``DRAFT`` version.

    Takes a :class:`SourceTemplate` rather than raw text: the registry mirrors
    templates that already exist in source, and never invents prompt text
    (ADR-0202, preserved by ADR-0209). New versions always start at ``DRAFT`` —
    a caller cannot register something directly into ``ACTIVE``.
    """
    assert_version_matches_name(template.prompt_name, template.version)

    row = PromptVersion(
        prompt_name=template.prompt_name,
        version=template.version,
        template=template.template,
        schema_version=template.schema_version,
        status=PromptStatus.DRAFT.value,
        created_by=created_by,
        template_checksum=template.checksum(),
    )
    session.add(row)
    session.flush()
    logger.info(
        "prompt version registered",
        extra={"prompt_name": row.prompt_name, "prompt_version": row.version},
    )
    return row


def get_active(session: Session, prompt_name: str) -> PromptVersion:
    """Return the single ``ACTIVE`` version of ``prompt_name``.

    Exactly one row can be active per prompt — ``uq_prompt_versions_one_active``
    makes that a database guarantee, so this cannot silently pick between two.
    Raises :class:`PromptVersionNotFoundError` when nothing is active, because a
    generation attributed to no prompt version has no provenance.
    """
    row = session.scalar(
        select(PromptVersion).where(
            PromptVersion.prompt_name == prompt_name,
            PromptVersion.status == PromptStatus.ACTIVE.value,
        )
    )
    if row is None:
        raise PromptVersionNotFoundError(f"No active version for prompt {prompt_name!r}.")
    _assert_matches_source(row)
    return row


def get_version(session: Session, version: str) -> PromptVersion:
    """Return one version by its version string, whatever its status."""
    row = session.scalar(select(PromptVersion).where(PromptVersion.version == version))
    if row is None:
        raise PromptVersionNotFoundError(f"Unknown prompt version {version!r}.")
    return row


def list_versions(session: Session, prompt_name: str) -> list[PromptVersion]:
    """Every version of ``prompt_name``, oldest first."""
    return list(
        session.scalars(
            select(PromptVersion)
            .where(PromptVersion.prompt_name == prompt_name)
            .order_by(PromptVersion.created_at, PromptVersion.version)
        )
    )


def transition_status(
    session: Session,
    version_id: uuid.UUID,
    new_status: PromptStatus,
) -> PromptVersion:
    """Advance one version to ``new_status``, enforcing the §19 lifecycle order.

    Rejects any move the state machine does not permit — including ``DRAFT`` ->
    ``ACTIVE``, backward moves, and self-transitions — with
    :class:`PromptVersionInvalidStateError`.

    Promotion to ``ACTIVE`` **atomically deprecates** whichever version of the
    same prompt is currently active. Without that, the partial unique index
    would reject the promotion and callers would need a two-step dance that can
    fail halfway, leaving a prompt with no active version at all.
    """
    row = session.get(PromptVersion, version_id)
    if row is None:
        raise PromptVersionNotFoundError(f"Unknown prompt version id {version_id!s}.")

    current = PromptStatus(row.status)
    assert_transition(current, new_status)

    if new_status is PromptStatus.ACTIVE:
        _deprecate_current_active(session, row.prompt_name, exclude_id=row.id)

    row.status = new_status.value
    session.flush()
    logger.info(
        "prompt version transitioned",
        extra={
            "prompt_name": row.prompt_name,
            "prompt_version": row.version,
            "from_status": current.value,
            "to_status": new_status.value,
        },
    )
    return row


def _deprecate_current_active(session: Session, prompt_name: str, *, exclude_id: uuid.UUID) -> None:
    """Move the prompt's current ``ACTIVE`` version to ``DEPRECATED``, if any.

    ``ACTIVE -> DEPRECATED`` is itself a legal transition, so this does not
    bypass the state machine — it applies it to the outgoing version.
    """
    outgoing = session.scalar(
        select(PromptVersion).where(
            PromptVersion.prompt_name == prompt_name,
            PromptVersion.status == PromptStatus.ACTIVE.value,
            PromptVersion.id != exclude_id,
        )
    )
    if outgoing is None:
        return
    assert_transition(PromptStatus.ACTIVE, PromptStatus.DEPRECATED)
    outgoing.status = PromptStatus.DEPRECATED.value
    session.flush()
    logger.info(
        "prompt version deprecated by activation",
        extra={"prompt_name": prompt_name, "prompt_version": outgoing.version},
    )


def _assert_matches_source(row: PromptVersion) -> None:
    """Raise if a stored version has drifted from its source template.

    The row claims to mirror a git-versioned template; if the two disagree, the
    row no longer describes what would actually run, and every ``model_runs``
    entry citing it is misattributed. Failing loudly beats generating against a
    prompt nobody reviewed.
    """
    source = get_source_template(row.version)
    if source is None:
        raise PromptTemplateDriftError(
            f"Prompt version {row.version!r} is registered but has no source template. "
            "Source templates are the source of truth (ADR-0202)."
        )
    if sha256_of(source.template) != row.template_checksum:
        raise PromptTemplateDriftError(
            f"Prompt version {row.version!r} no longer matches its source template; "
            "versions are immutable, so register a new version instead of editing one."
        )


__all__ = [
    "create_version",
    "get_active",
    "get_version",
    "list_versions",
    "transition_status",
]
