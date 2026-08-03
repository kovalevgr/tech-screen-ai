"""interview_session.session_state (orchestrator working state, T20)

Revision ID: 0006_add_session_state_column
Revises: 0005_rubric_snapshot
Create Date: 2026-08-03

Adds the ``session_state`` JSONB column to ``interview_session``
(``docs/contracts/state-machine.md`` §9). The ``upgrade()`` is **additive** and
zero-downtime: a single nullable ``ADD COLUMN`` with no default and no
rewrite — every existing row keeps ``NULL``, which the orchestrator reads as
"this session has not started". No destructive *upgrade* DDL → no ADR.

``interview_session`` is deliberately NOT one of the six append-only audit
tables (constitution §3): this column is mutable working state, rewritten in
place after every transition. The audit trail lives in ``turn_trace`` and the
T21 transition records, never here.

``downgrade()`` is dev/test-only (production is forward-only, §10/§19). T10's
destructive-DDL detector greps the whole migration file, so the ``DROP COLUMN``
below will set ``needs_adr=true`` on the PR even though the *upgrade* is purely
additive — the reviewer confirms the upgrade SQL when applying
``migration-approved`` (same as ``0004`` / ``0005``).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_add_session_state_column"
down_revision: str | None = "0005_rubric_snapshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE interview_session ADD COLUMN session_state JSONB")


def downgrade() -> None:
    # Dev/test only — production is forward-only (§10).
    op.execute("ALTER TABLE interview_session DROP COLUMN IF EXISTS session_state")
