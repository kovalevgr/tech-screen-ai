"""interview_session.rubric_snapshot (immutable rubric snapshot, §4)

Revision ID: 0005_rubric_snapshot
Revises: 0004_position_template
Create Date: 2026-06-24

Adds the ``rubric_snapshot`` JSONB column to ``interview_session`` (constitution
§4). The ``upgrade()`` is **additive**: a single ``ADD COLUMN`` with a
transitional ``NOT NULL DEFAULT '{}'::jsonb`` so the existing placeholder/seed
inserts (which predate real session creation, T28) keep working with zero
downtime — the T12 ``0004`` precedent. Real sessions overwrite the default with
a real snapshot at capture time. No destructive *upgrade* DDL → no ADR.

``downgrade()`` is dev/test-only (production is forward-only, §10/§19). Note:
T10's destructive-DDL detector greps the whole migration file, so the
``DROP COLUMN`` in ``downgrade()`` will set ``needs_adr=true`` on the PR even
though the *upgrade* is purely additive — the reviewer confirms the upgrade SQL
when applying ``migration-approved`` (same as ``0004``).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_rubric_snapshot"
down_revision: str | None = "0004_position_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE interview_session "
        "ADD COLUMN rubric_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    # Dev/test only — production is forward-only (§10).
    op.execute("ALTER TABLE interview_session DROP COLUMN IF EXISTS rubric_snapshot")
