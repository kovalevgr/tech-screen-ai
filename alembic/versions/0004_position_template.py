"""position_template domain columns + stack/competency selection tables

Revision ID: 0004_position_template
Revises: 0003_rubric_payload_hash
Create Date: 2026-06-24

Finalises the T05 ``position_template`` placeholder for T12. Everything in
``upgrade()`` is **additive** (constitution §10): ``ADD COLUMN`` (with
transitional defaults so the change is zero-downtime on any pre-existing dev
rows — same pattern as ``0003``), ``ADD CONSTRAINT``, and two new ``CREATE
TABLE`` selection tables. No destructive *upgrade* DDL → no ADR is required.

``downgrade()`` is symmetric (house convention — the T05 baseline migration test
exercises ``downgrade base`` → ``upgrade head``). Production is forward-only and
never downgrades (§10/§19); the downgrade exists for dev/test round-trips only.

Note: T10's destructive-DDL detector greps the whole migration file, so the
``DROP`` statements in ``downgrade()`` will set ``needs_adr=true`` on the PR even
though the *upgrade* is purely additive. The reviewer confirms the upgrade SQL is
additive when applying ``migration-approved``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_position_template"
down_revision: str | None = "0003_rubric_payload_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- position_template: domain columns (additive, with transitional defaults)
    op.execute("ALTER TABLE position_template ADD COLUMN title TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE position_template ADD COLUMN jd_text TEXT")
    op.execute("ALTER TABLE position_template ADD COLUMN level TEXT NOT NULL DEFAULT 'Middle'")
    op.execute("ALTER TABLE position_template ADD COLUMN archived_at TIMESTAMPTZ")
    op.execute("ALTER TABLE position_template ADD COLUMN created_by UUID")
    op.execute(
        "ALTER TABLE position_template ADD CONSTRAINT ck_position_template_level "
        "CHECK (level IN ('Junior', 'Middle', 'Senior', 'Tech Leader'))"
    )
    op.execute(
        "ALTER TABLE position_template ADD CONSTRAINT fk_position_template_created_by_user "
        'FOREIGN KEY (created_by) REFERENCES "user" (id)'
    )

    # --- position_template_stack: which rubric stacks a template covers
    op.execute(
        "CREATE TABLE position_template_stack ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "position_template_id UUID NOT NULL REFERENCES position_template (id), "
        "stack_id UUID NOT NULL REFERENCES stack (id), "
        "CONSTRAINT uq_position_template_stack UNIQUE (position_template_id, stack_id)"
        ")"
    )

    # --- position_template_competency: selected competencies + must-have flag
    op.execute(
        "CREATE TABLE position_template_competency ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "position_template_id UUID NOT NULL REFERENCES position_template (id), "
        "competency_id UUID NOT NULL REFERENCES competency (id), "
        "must_have BOOLEAN NOT NULL DEFAULT false, "
        "CONSTRAINT uq_position_template_competency UNIQUE (position_template_id, competency_id)"
        ")"
    )


def downgrade() -> None:
    # Dev/test only — production is forward-only (§10). Reverse order of upgrade.
    op.execute("DROP TABLE IF EXISTS position_template_competency")
    op.execute("DROP TABLE IF EXISTS position_template_stack")
    op.execute(
        "ALTER TABLE position_template "
        "DROP CONSTRAINT IF EXISTS fk_position_template_created_by_user"
    )
    op.execute("ALTER TABLE position_template DROP CONSTRAINT IF EXISTS ck_position_template_level")
    op.execute("ALTER TABLE position_template DROP COLUMN IF EXISTS created_by")
    op.execute("ALTER TABLE position_template DROP COLUMN IF EXISTS archived_at")
    op.execute("ALTER TABLE position_template DROP COLUMN IF EXISTS level")
    op.execute("ALTER TABLE position_template DROP COLUMN IF EXISTS jd_text")
    op.execute("ALTER TABLE position_template DROP COLUMN IF EXISTS title")
