"""rubric_tree_version.payload_hash + UNIQUE constraint

Revision ID: 0003_rubric_payload_hash
Revises: 0002_feature_flags
Create Date: 2026-04-28

Adds the ``payload_hash`` column to ``rubric_tree_version`` — the SHA-256 of
the canonical YAML payload that materialised the version (T08 research §3).
The UNIQUE constraint protects FR-007 (one row per distinct payload), and
combined with the seed-path advisory lock (``pg_advisory_xact_lock(987654321)``,
research §6) makes concurrent seed runs serialise without UNIQUE-violation
errors.

Transitional safety (research §10): the column is added with
``NOT NULL DEFAULT ''``, so any pre-existing rows (none in prod at T08 time,
but defensive in dev) get the empty string. The UNIQUE constraint allows at
most one row with ``''``, which is acceptable for the migration's transitional
moment — the first real seed run inserts a fresh row with a real 64-char hex
hash that cannot collide with the empty string.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_rubric_payload_hash"
down_revision: str | None = "0002_feature_flags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNIQUE_NAME: str = "uq_rubric_tree_version_payload_hash"


def upgrade() -> None:
    op.execute("ALTER TABLE rubric_tree_version ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''")
    op.execute(
        f"ALTER TABLE rubric_tree_version ADD CONSTRAINT {_UNIQUE_NAME} UNIQUE (payload_hash)"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE rubric_tree_version DROP CONSTRAINT IF EXISTS {_UNIQUE_NAME}")
    op.execute("ALTER TABLE rubric_tree_version DROP COLUMN IF EXISTS payload_hash")
