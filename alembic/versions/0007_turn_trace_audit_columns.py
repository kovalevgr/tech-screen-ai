"""turn_trace audit columns, session_decision reason, dev transcript, T21 flags

Revision ID: 0007_turn_trace_audit_columns
Revises: 0006_add_session_state_column
Create Date: 2026-08-03

T21 — the migration ``alembic/versions/0001_baseline.py`` and
``app/backend/db/models/audit.py`` both anchor ("the rich columns … land in
T21 via a forward-only migration"). Four additive groups, no rewrite of any
existing row:

1. ``turn_trace`` gains every column named by the committed row contract
   ``docs/contracts/turn-trace.schema.json``: T04's ``TraceRecord`` fields, the
   full payload columns, and the orchestrator context (``turn_id``,
   ``transition``, ``wrapper_outcome``). All non-nullable additions carry a
   transitional server default so the pre-T21 placeholder rows (and the
   ``tests/db/_seed.py`` chain) stay valid — the T12/T15/T20 precedent.
2. ``session_decision`` gains ``reason`` and drops ``NOT NULL`` on
   ``decided_by``: the machine's ``RecordDecision`` commands (plan_invalid,
   agent_failure, timeout, completed) and T21's ``cost_ceiling`` breach are
   SYSTEM decisions with no human actor. Dropping a ``NOT NULL`` is a widening
   change — no data is lost and no existing row becomes invalid (§10).
3. ``interview_session`` gains ``dev_transcript`` — the shell-side chat log the
   dev-session API renders. Like ``session_state`` (0006) this is mutable
   working state on a table deliberately OUTSIDE the six §3 append-only tables;
   the audit trail lives in ``turn_trace``.
4. The two T21/T22 feature flags are seeded ``enabled = false`` (§9 dark
   launch), matching ``configs/feature-flags.yaml``.

**§3 is untouched.** No trigger is dropped or recreated, no grant changes:
``turn_trace_no_mutation`` and the ``REVOKE UPDATE, DELETE`` from
``techscreen_app`` keep applying to the widened table exactly as before
(``app/backend/tests/db/test_turn_trace_columns.py`` proves it on the new
columns).

``downgrade()`` is dev/test-only — production is forward-only (§10/§19). T10's
destructive-DDL detector greps the whole file, so the ``DROP COLUMN`` calls
below set ``needs_adr=true`` on the PR even though the *upgrade* is purely
additive; the reviewer confirms the upgrade SQL when applying
``migration-approved`` (same as 0004 / 0005 / 0006).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_turn_trace_audit_columns"
down_revision: str | None = "0006_add_session_state_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Columns added to ``turn_trace``, in contract order. Kept as a table so the
#: upgrade and the downgrade cannot drift apart.
_TURN_TRACE_COLUMNS: tuple[tuple[str, str], ...] = (
    # --- orchestrator context (contract: "Null for non-session calls") ---
    ("turn_id", "UUID"),
    ("transition", "JSONB"),
    # --- T04 TraceRecord mirror --------------------------------------------
    ("agent", "TEXT NOT NULL DEFAULT ''"),
    ("prompt_version", "TEXT NOT NULL DEFAULT ''"),
    ("model", "TEXT NOT NULL DEFAULT ''"),
    ("model_version", "TEXT"),
    ("outcome", "TEXT NOT NULL DEFAULT ''"),
    ("wrapper_outcome", "TEXT"),
    ("attempts", "SMALLINT NOT NULL DEFAULT 1"),
    ("latency_ms", "INTEGER NOT NULL DEFAULT 0"),
    ("input_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("output_tokens", "INTEGER NOT NULL DEFAULT 0"),
    ("cost_usd", "NUMERIC(12, 6) NOT NULL DEFAULT 0"),
    ("prompt_sha", "TEXT NOT NULL DEFAULT ''"),
    ("error_message", "TEXT"),
    # --- full payloads (the reason this table exists, constitution §1) -----
    ("system_prompt", "TEXT NOT NULL DEFAULT ''"),
    ("user_payload", "TEXT NOT NULL DEFAULT ''"),
    ("response_text", "TEXT NOT NULL DEFAULT ''"),
    ("parsed", "JSONB"),
)

#: ``turn_trace`` value constraints. ``agent`` deliberately has NO enum check:
#: T04's FR-008 requires a trace for an *unknown* agent name too (the
#: ``config_error`` outcome), so the column records what was requested rather
#: than what is valid. ``''`` is admitted on ``outcome`` for the pre-T21 rows
#: that carry the transitional default.
_TURN_TRACE_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    (
        "ck_turn_trace_outcome",
        "outcome IN ('', 'ok', 'schema_error', 'timeout', 'upstream_unavailable', "
        "'budget_exceeded', 'config_error', 'trace_write_error')",
    ),
    (
        "ck_turn_trace_wrapper_outcome",
        "wrapper_outcome IS NULL OR wrapper_outcome IN "
        "('accepted', 'contract_miss_retried', 'rejected')",
    ),
    ("ck_turn_trace_attempts", "attempts BETWEEN 1 AND 3"),
    (
        "ck_turn_trace_counters_non_negative",
        "latency_ms >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0",
    ),
)

#: T21 / T22 dark-launch flags (§9). Mirrors ``configs/feature-flags.yaml``.
_SEEDED_FLAGS: tuple[str, ...] = (
    "enforce_session_cost_ceiling",
    "enable_live_orchestrator",
)


def upgrade() -> None:
    # --- 1. turn_trace: the contract row shape ------------------------------
    for name, definition in _TURN_TRACE_COLUMNS:
        op.execute(f"ALTER TABLE turn_trace ADD COLUMN {name} {definition}")
    for name, expression in _TURN_TRACE_CONSTRAINTS:
        op.execute(f"ALTER TABLE turn_trace ADD CONSTRAINT {name} CHECK ({expression})")
    # The reviewer panel reads one session's traces oldest-first (T22/T34).
    op.execute(
        "CREATE INDEX ix_turn_trace_session_created "
        "ON turn_trace (interview_session_id, created_at)"
    )

    # --- 2. session_decision: system decisions have no human actor ----------
    op.execute("ALTER TABLE session_decision ADD COLUMN reason TEXT")
    op.execute("ALTER TABLE session_decision ALTER COLUMN decided_by DROP NOT NULL")

    # --- 3. interview_session: shell-side dev transcript (mutable) ----------
    op.execute("ALTER TABLE interview_session ADD COLUMN dev_transcript JSONB")

    # --- 4. Dark-launch flag rows (§9) --------------------------------------
    for flag in _SEEDED_FLAGS:
        op.execute(
            "INSERT INTO feature_flag (name, enabled, owner, updated_by) "
            f"VALUES ('{flag}', false, '@andrii', '{revision}') "
            "ON CONFLICT (name) DO NOTHING"
        )


def downgrade() -> None:
    """Dev/test only — production is forward-only (§10).

    ``session_decision.decided_by`` is deliberately LEFT nullable. Restoring
    ``NOT NULL`` would require deleting every system-authored decision the
    pre-0007 schema cannot represent, and deleting rows from an append-only
    audit table is exactly what §3 forbids — even on a local reset. A widened
    column is harmless (0007's upgrade re-applies ``DROP NOT NULL`` as a
    no-op), a silently truncated audit trail is not.
    """
    for flag in _SEEDED_FLAGS:
        op.execute(f"DELETE FROM feature_flag WHERE name = '{flag}'")

    op.execute("ALTER TABLE interview_session DROP COLUMN IF EXISTS dev_transcript")

    op.execute("ALTER TABLE session_decision DROP COLUMN IF EXISTS reason")

    op.execute("DROP INDEX IF EXISTS ix_turn_trace_session_created")
    for name, _expression in _TURN_TRACE_CONSTRAINTS:
        op.execute(f"ALTER TABLE turn_trace DROP CONSTRAINT IF EXISTS {name}")
    for name, _definition in _TURN_TRACE_COLUMNS:
        op.execute(f"ALTER TABLE turn_trace DROP COLUMN IF EXISTS {name}")
