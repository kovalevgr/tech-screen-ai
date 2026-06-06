"""DB integration tests for the T05 baseline schema.

Every test in this package depends on a reachable, migrated database. The
session-scoped ``db_available`` / ``migrated_schema`` fixtures in the top-level
``conftest.py`` skip the whole package when no database is configured, so the
no-DB unit run stays green (research §9).
"""
