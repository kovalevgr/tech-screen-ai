"""feature-flag infrastructure (T05a)

Revision ID: 0002_feature_flags
Revises: 0001_baseline
Create Date: 2026-04-28

Creates the ``feature_flag`` table — the constitution-§9 dark-launch substrate.
The table is explicitly carved out of the §3 append-only set (FR-013):

- NO ``reject_audit_mutation()`` trigger on this table.
- NO ``REVOKE UPDATE, DELETE`` from ``techscreen_app``.
- Both roles retain full DML.

The carve-out is intentional and structural. ``feature_flag`` is mutable by
design (flags get flipped); audit history lives in ``configs/feature-flags.yaml``
git history, in ``docs/engineering/feature-flags.md``, and in the
``updated_at`` / ``updated_by`` columns. A future contributor must NOT extend
§3 protections to this table for "consistency" with the six audit tables —
that would defeat the emergency-disable path (SC-007) and break SC-009.

This migration ALSO creates two row-level triggers:

1. ``feature_flag_touch_updated_at`` (``BEFORE UPDATE``) — keeps the
   ``updated_at`` column in sync on every UPDATE.
2. ``feature_flag_notify_change`` (``AFTER INSERT OR UPDATE OR DELETE``) —
   fires ``pg_notify('feature_flag_changed', COALESCE(NEW.name, OLD.name))``.
   This is structural to FR-003 / SC-003 (the 1-second cache-invalidation
   SLO needs the database itself to wake long-lived listeners; the payload
   carries the single flag name so listeners evict one cache entry per
   NOTIFY rather than flushing the whole cache — research §2).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_feature_flags"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- 1. Table -----------------------------------------------------------
    op.create_table(
        "feature_flag",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("default_value", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("updated_by", sa.Text(), nullable=True),
    )

    # --- 2. §3 carve-out (FR-013): grants kept FULL for both roles ----------
    # NO reject_audit_mutation() trigger, NO REVOKE. This is the entire point
    # of the table — flags get flipped at runtime by the configs-as-code
    # workflow (techscreen_migrator) and on the emergency-disable path
    # (techscreen_app). SC-009 is the positive test locking this in.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flag TO techscreen_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flag TO techscreen_migrator")

    # --- 3. updated_at touch trigger ----------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION feature_flag_touch_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          NEW.updated_at := now();
          RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER feature_flag_touch_updated_at
        BEFORE UPDATE ON feature_flag
        FOR EACH ROW EXECUTE FUNCTION feature_flag_touch_updated_at();
        """
    )

    # --- 4. NOTIFY trigger (FR-003, SC-003; research §2) --------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION feature_flag_notify_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          PERFORM pg_notify(
            'feature_flag_changed',
            COALESCE(NEW.name, OLD.name)
          );
          RETURN COALESCE(NEW, OLD);
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER feature_flag_notify_change
        AFTER INSERT OR UPDATE OR DELETE ON feature_flag
        FOR EACH ROW EXECUTE FUNCTION feature_flag_notify_change();
        """
    )


def downgrade() -> None:
    """Drop the table, triggers, and helper functions (local/CI reset only).

    Production is forward-only (§10); ``downgrade`` is never run against prod.
    Drop order: triggers → functions → table.
    """
    op.execute("DROP TRIGGER IF EXISTS feature_flag_notify_change ON feature_flag")
    op.execute("DROP TRIGGER IF EXISTS feature_flag_touch_updated_at ON feature_flag")
    op.execute("DROP FUNCTION IF EXISTS feature_flag_notify_change()")
    op.execute("DROP FUNCTION IF EXISTS feature_flag_touch_updated_at()")
    op.drop_table("feature_flag")
