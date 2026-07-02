-- T06 — in-database grants for CI identities (per environment).
--
-- Run once per Cloud SQL instance AFTER `alembic upgrade head`, as
-- techscreen_migrator (or postgres), via the Auth Proxy:
--
--   psql 'postgresql://techscreen_migrator:<pw>@127.0.0.1:5432/techscreen' \
--     -f scripts/cloud-db-grants.sql
--
-- Scope: the flag-sync IAM user gets exactly what the upsert in
-- scripts/sync_feature_flags_to_db.py needs on feature_flag — a table that
-- is deliberately mutable (T05a). The six §3 append-only tables are NOT
-- touched by this script; their protection comes from migration 0001's
-- triggers + REVOKEs and applies to every role.
--
-- T16 extends this file if the rubric-sync job needs additional tables.

GRANT SELECT, INSERT, UPDATE ON TABLE feature_flag
  TO "techscreen-flag-sync@tech-screen-493720.iam";
