-- T06/T16 — in-database grants for CI identities (per environment).
--
-- Run once per Cloud SQL instance AFTER `alembic upgrade head`, as
-- techscreen_migrator (or postgres), via the Auth Proxy:
--
--   psql 'postgresql://techscreen_migrator:<pw>@127.0.0.1:5432/techscreen' \
--     -f scripts/cloud-db-grants.sql
--
-- Instances sleep by default (cost-idle mode) — wake the target first:
--   scripts/cloud-sql-power.sh wake <env>
--
-- One CI identity, two configs-as-code surfaces
-- (.github/workflows/sync-configs.yml, renamed from sync-feature-flags.yml
-- in T16). GRANT is idempotent — re-running this file is safe.

-- ---------------------------------------------------------------------------
-- Surface 1 (T05a): feature flags. The upsert in
-- scripts/sync_feature_flags_to_db.py needs INSERT (new flags),
-- UPDATE (ON CONFLICT DO UPDATE of owner/default_value/updated_by), and
-- SELECT (orphan detection). feature_flag is deliberately mutable — the only
-- UPDATE grant in this file.
-- ---------------------------------------------------------------------------

GRANT SELECT, INSERT, UPDATE ON TABLE feature_flag
  TO "techscreen-flag-sync@tech-screen-493720.iam";

-- ---------------------------------------------------------------------------
-- Surface 2 (T16): rubric tree. The importer
-- (app/backend/services/rubric_importer.py `seed`) materialises a FRESH tree
-- under a NEW rubric_tree_version per content change and NEVER updates or
-- deletes prior rows (§4 / ADR-018) — so NO rubric table gets UPDATE or
-- DELETE. Per-table justification:
--
--   rubric_tree_version  SELECT + INSERT — SELECT for the latest-payload-hash
--                        no-op check and the INSERT .. RETURNING id;
--                        INSERT for the new version row.
--   stack                SELECT + INSERT — INSERT .. RETURNING id (RETURNING
--                        requires SELECT privilege on the read columns).
--   competency_block     SELECT + INSERT — same RETURNING-id shape.
--   competency           SELECT + INSERT — RETURNING id, plus the SELECT of
--                        the prior version's names for the FR-009 rename
--                        rejection.
--   topic                INSERT only — plain INSERT, no RETURNING, no reads.
--   level                INSERT only — plain INSERT, no RETURNING, no reads.
-- ---------------------------------------------------------------------------

GRANT SELECT, INSERT ON TABLE rubric_tree_version
  TO "techscreen-flag-sync@tech-screen-493720.iam";
GRANT SELECT, INSERT ON TABLE stack
  TO "techscreen-flag-sync@tech-screen-493720.iam";
GRANT SELECT, INSERT ON TABLE competency_block
  TO "techscreen-flag-sync@tech-screen-493720.iam";
GRANT SELECT, INSERT ON TABLE competency
  TO "techscreen-flag-sync@tech-screen-493720.iam";
GRANT INSERT ON TABLE topic
  TO "techscreen-flag-sync@tech-screen-493720.iam";
GRANT INSERT ON TABLE level
  TO "techscreen-flag-sync@tech-screen-493720.iam";

-- ---------------------------------------------------------------------------
-- audit_log — the ONE §3 append-only table this identity touches, INSERT
-- only. specs/010 FR-010 requires exactly one receipt row
-- (action='rubric.versioned') per new version; INSERT is the single verb §3
-- permits, and it is the only verb granted here (no SELECT — the importer
-- never reads audit_log, and the INSERT has no RETURNING clause). UPDATE and
-- DELETE stay impossible for every non-migrator role — including this one —
-- via migration 0001's reject_audit_mutation() trigger (techscreen_migrator is
-- exempt by design, for §10 human-approved migrations); this grant cannot
-- weaken §3.
-- The other five §3 tables (turn_trace, assessment, assessment_correction,
-- turn_annotation, session_decision) get NOTHING.
-- ---------------------------------------------------------------------------

GRANT INSERT ON TABLE audit_log
  TO "techscreen-flag-sync@tech-screen-493720.iam";
