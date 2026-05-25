"""baseline schema v0 + append-only enforcement

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-28

The single baseline migration for TechScreen (T05). It creates, in one
forward-only step (constitution §10):

1. Extensions ``vector`` (pgvector, ADR-007) and ``pgcrypto`` (``gen_random_uuid``).
2. The rubric read-only tree, the ``user`` table, the three session
   placeholders, and the six §3 append-only tables.
3. The two cluster-global roles ``techscreen_app`` and ``techscreen_migrator``
   (NOLOGIN; T06 attaches LOGIN + a Secret-Manager password).
4. §3 append-only enforcement in TWO independent layers:
   - the shared ``reject_audit_mutation()`` trigger (migrator-exempt) on all
     six append-only tables, and
   - ``REVOKE UPDATE, DELETE`` from ``techscreen_app`` on those six tables
     (``GRANT INSERT, SELECT`` retained).

Every structural statement (extensions, roles, trigger, grants/revokes) is raw
``op.execute()`` SQL so the T10 offline ``alembic upgrade head --sql`` dry-run
renders it verbatim without a connection (research §1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The six append-only tables (§3 / ADR-019). Grouped here so the trigger
# wiring and the REVOKE block below are greppable in one place (SC-005).
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "turn_trace",
    "assessment",
    "assessment_correction",
    "turn_annotation",
    "audit_log",
    "session_decision",
)

# Tables in FK-safe drop order (children before parents) for downgrade().
_ALL_TABLES_DROP_ORDER: tuple[str, ...] = (
    # append-only set (leaf-most first)
    "assessment_correction",
    "turn_annotation",
    "session_decision",
    "assessment",
    "turn_trace",
    "audit_log",
    # session placeholders
    "interview_plan",
    "interview_session",
    "position_template",
    # identity
    "user",
    # rubric tree (leaves before roots)
    "level",
    "topic",
    "competency",
    "competency_block",
    "stack",
    "rubric_tree_version",
)

_UUID_PK = sa.text("gen_random_uuid()")


def _uuid_pk() -> sa.Column[sa.Uuid]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=_UUID_PK,
    )


def _created_at() -> sa.Column[sa.DateTime]:
    return sa.Column(
        "created_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    # --- 1. Extensions (idempotent) -------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # --- 2a. Rubric read-only tree (§4 / ADR-018) -----------------------
    op.create_table(
        "rubric_tree_version",
        _uuid_pk(),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _created_at(),
    )
    op.create_table(
        "stack",
        _uuid_pk(),
        sa.Column("rubric_tree_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["rubric_tree_version_id"], ["rubric_tree_version.id"]),
    )
    op.create_table(
        "competency_block",
        _uuid_pk(),
        sa.Column("rubric_tree_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stack_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _created_at(),
        sa.ForeignKeyConstraint(["rubric_tree_version_id"], ["rubric_tree_version.id"]),
        sa.ForeignKeyConstraint(["stack_id"], ["stack.id"]),
    )
    op.create_table(
        "competency",
        _uuid_pk(),
        sa.Column("rubric_tree_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_block_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["rubric_tree_version_id"], ["rubric_tree_version.id"]),
        sa.ForeignKeyConstraint(["competency_block_id"], ["competency_block.id"]),
    )
    op.create_table(
        "topic",
        _uuid_pk(),
        sa.Column("rubric_tree_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["rubric_tree_version_id"], ["rubric_tree_version.id"]),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"]),
    )
    op.create_table(
        "level",
        _uuid_pk(),
        sa.Column("rubric_tree_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("descriptor", sa.Text(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["rubric_tree_version_id"], ["rubric_tree_version.id"]),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"]),
    )

    # --- 2b. Identity (staff only; §15 — NO candidate PII) --------------
    op.create_table(
        "user",
        _uuid_pk(),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("subject"),
    )

    # --- 2c. Session placeholders (minimal; extended by later tiers) ----
    op.create_table(
        "position_template",
        _uuid_pk(),
        _created_at(),
    )
    op.create_table(
        "interview_session",
        _uuid_pk(),
        sa.Column("position_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["position_template_id"], ["position_template.id"]),
    )
    op.create_table(
        "interview_plan",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"]),
    )

    # --- 2d. Append-only audit set (§3 / ADR-019) -----------------------
    # turn_trace: T05 ships table + §3 guard only. The rich TraceRecord columns
    # (agent/model/outcome/latency_ms/cost_usd/prompt_sha) land in T21 via a
    # forward-only migration (mirrors db/models/audit.py:TurnTrace docstring).
    op.create_table(
        "turn_trace",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"]),
    )
    op.create_table(
        "assessment",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competency_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"]),
        sa.ForeignKeyConstraint(["competency_id"], ["competency.id"]),
    )
    op.create_table(
        "assessment_correction",
        _uuid_pk(),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corrected_score", sa.SmallInteger(), nullable=False),
        sa.Column("corrected_by", postgresql.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessment.id"]),
        sa.ForeignKeyConstraint(["corrected_by"], ["user.id"]),
    )
    op.create_table(
        "turn_annotation",
        _uuid_pk(),
        sa.Column("turn_trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("annotated_by", postgresql.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["turn_trace_id"], ["turn_trace.id"]),
        sa.ForeignKeyConstraint(["annotated_by"], ["user.id"]),
    )
    op.create_table(
        "audit_log",
        _uuid_pk(),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("subject_hash", sa.Text(), nullable=False),
        sa.Column(
            "ts",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"]),
    )
    op.create_table(
        "session_decision",
        _uuid_pk(),
        sa.Column("interview_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(["interview_session_id"], ["interview_session.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["user.id"]),
    )

    # --- 3. Roles (idempotent, NOLOGIN; T06 adds LOGIN + password) ------
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'techscreen_app') THEN
            CREATE ROLE techscreen_app NOLOGIN;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT FROM pg_roles WHERE rolname = 'techscreen_migrator'
          ) THEN
            CREATE ROLE techscreen_migrator NOLOGIN;
          END IF;
        END $$;
        """
    )

    # --- 4a. §3 trigger function (migrator-exempt) ----------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_audit_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF current_user = 'techscreen_migrator' THEN
            RETURN COALESCE(NEW, OLD);  -- allow human-approved migrations (§10)
          END IF;
          RAISE EXCEPTION 'append-only: % not allowed on %', TG_OP, TG_TABLE_NAME;
        END;
        $$;
        """
    )

    # --- 4b. Wire the trigger on every append-only table ----------------
    for table in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_no_mutation
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
            """
        )

    # --- 4c. Grants: app can append+read, NOT mutate, on the six tables --
    # techscreen_app gets baseline access to all tables so the runtime can
    # read the rubric tree and write sessions/plans; the six append-only
    # tables then have UPDATE/DELETE revoked (the hard privilege floor, §3).
    op.execute("GRANT USAGE ON SCHEMA public TO techscreen_app")
    op.execute("GRANT USAGE ON SCHEMA public TO techscreen_migrator")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO techscreen_app"
    )
    op.execute("GRANT ALL ON ALL TABLES IN SCHEMA public TO techscreen_migrator")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"GRANT INSERT, SELECT ON {table} TO techscreen_app")
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM techscreen_app")


def downgrade() -> None:
    """Return the database to empty — for LOCAL / CI reset only.

    Production is forward-only (constitution §10); ``downgrade`` is never run
    against prod. Drop order is dependency-safe: triggers → function → tables
    (children before parents) → roles → extensions. Dropping ``vector`` /
    ``pgcrypto`` is safe here because nothing else in this single-migration tree
    depends on them; a later migration that starts depending on an extension
    owns its own keep/drop decision.
    """
    # Triggers first, then the shared function.
    for table in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_mutation ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_audit_mutation()")

    # Tables, children before parents.
    for table in _ALL_TABLES_DROP_ORDER:
        op.drop_table(table)

    # Roles. The tables they held grants on are already gone, but the schema
    # USAGE grant still references each role, so `DROP OWNED BY` clears any
    # remaining privileges before `DROP ROLE` (guarded — the role may not
    # exist on a partially-applied DB).
    for role in ("techscreen_app", "techscreen_migrator"):
        op.execute(
            f"""
            DO $$ BEGIN
              IF EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'DROP OWNED BY {role}';
                EXECUTE 'DROP ROLE {role}';
              END IF;
            END $$;
            """
        )

    # Extensions last.
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
