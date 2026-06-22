"""Seed path: YAML → DB (T08 / US2, US4).

Live-DB e2e on the migrated test database. Asserts:
- First seed inserts one rubric_tree_version + the full tree + one audit row.
- Repeat seed on unchanged YAML is a no-op (SC-003).
- Content change → new rubric_tree_version row + fresh tree; prior-version
  rows are byte-identical pre/post (SC-004 — §4 immutability).
- Each new version writes exactly one audit_log row (SC-008).
- Rename of a stable id is rejected with no writes (SC-005 — US4).

All tests skip cleanly when no DATABASE_URL is reachable (existing T05 pattern).
"""

from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.services.rubric_importer import (
    RenameForbiddenError,
    RubricImporter,
    _compute_payload_hash,
)

pytestmark = pytest.mark.asyncio


def _bare_dsn(sqlalchemy_dsn: str) -> str:
    return sqlalchemy_dsn.replace("+asyncpg", "")


def _write_minimal_yaml(yaml_dir: Path, descriptor: str = "default descriptor") -> Path:
    yaml_dir.mkdir(parents=True, exist_ok=True)
    body = textwrap.dedent(
        f"""\
        version: 1
        retired: false
        nodes:
          - id: block.core
            label_en: Core
            label_uk: Ядро
            parent: null
            retired: false
          - id: python.concurrency
            label_en: Concurrency
            label_uk: Конкурентність
            parent: block.core
            retired: false
            levels:
              - level: 1
                label_uk: Початковий
                descriptor_en: {descriptor}
        """
    )
    path = yaml_dir / "python.yaml"
    path.write_text(body, encoding="utf-8")
    return path


async def _row_count(db_conn: AsyncConnection, table: str, **where: str) -> int:
    if where:
        clause = " AND ".join(f"{k} = :{k}" for k in where)
        result = await db_conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {clause}"), where)
    else:
        result = await db_conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
    return int(result.scalar_one())


async def _truncate_rubric(db_conn: AsyncConnection) -> None:
    """Cleanup: drop every rubric row + the rubric audit rows. FK-safe order.

    audit_log normally REVOKEs DELETE from techscreen_app, but the superuser
    connection used by the test fixture bypasses grants (and the trigger
    exempts only the migrator role); the importer never uses this DELETE path
    — it's strictly test cleanup. Wrapping the whole thing in SET ROLE
    techscreen_migrator makes the trigger's exemption fire and keeps the §3
    invariant honest (the app role still can't DELETE; tests cheat via
    migrator, which is allowed by FR-006).
    """
    await db_conn.execute(text('SET ROLE "techscreen_migrator"'))
    try:
        for table in (
            "level",
            "topic",
            "competency",
            "competency_block",
            "stack",
            "rubric_tree_version",
        ):
            await db_conn.execute(text(f"DELETE FROM {table}"))
        await db_conn.execute(text("DELETE FROM audit_log WHERE action = 'rubric.versioned'"))
    finally:
        await db_conn.execute(text("RESET ROLE"))
    await db_conn.commit()


async def test_first_seed_creates_full_tree(
    db_conn: AsyncConnection, migrated_schema: str, tmp_path: Path
) -> None:
    """First seed inserts version + stack + block + competency + level + audit."""
    await _truncate_rubric(db_conn)
    yaml_dir = tmp_path / "rubric"
    _write_minimal_yaml(yaml_dir)
    importer = RubricImporter()
    result = await importer.seed(yaml_dir, dsn=migrated_schema)

    assert result.noop is False
    assert result.new_version_id is not None

    assert await _row_count(db_conn, "rubric_tree_version") == 1
    assert await _row_count(db_conn, "stack") == 1
    assert await _row_count(db_conn, "competency_block") == 1
    assert await _row_count(db_conn, "competency") == 1
    assert await _row_count(db_conn, "level") == 1
    assert await _row_count(db_conn, "audit_log", action="rubric.versioned") == 1


async def test_repeat_seed_is_no_op(
    db_conn: AsyncConnection, migrated_schema: str, tmp_path: Path
) -> None:
    """SC-003: a second seed on unchanged YAML produces zero new rows."""
    await _truncate_rubric(db_conn)
    yaml_dir = tmp_path / "rubric"
    _write_minimal_yaml(yaml_dir)
    importer = RubricImporter()
    await importer.seed(yaml_dir, dsn=migrated_schema)

    pre = {
        t: await _row_count(db_conn, t)
        for t in ("rubric_tree_version", "stack", "competency_block", "competency", "level")
    }
    audit_pre = await _row_count(db_conn, "audit_log", action="rubric.versioned")

    result = await importer.seed(yaml_dir, dsn=migrated_schema)
    assert result.noop is True
    assert result.rows_inserted == 0

    for t, count in pre.items():
        assert await _row_count(db_conn, t) == count, t
    assert await _row_count(db_conn, "audit_log", action="rubric.versioned") == audit_pre


async def test_content_change_creates_new_version_leaving_prior_untouched(
    db_conn: AsyncConnection, migrated_schema: str, tmp_path: Path
) -> None:
    """SC-004: edit descriptor → new version + fresh tree; prior rows byte-identical."""
    await _truncate_rubric(db_conn)
    yaml_dir = tmp_path / "rubric"
    _write_minimal_yaml(yaml_dir, descriptor="initial descriptor")
    importer = RubricImporter()
    first = await importer.seed(yaml_dir, dsn=migrated_schema)

    # Capture every prior-version row as a SHA-256 fingerprint of its full content.
    async def fingerprint(table: str, version_id: UUID | None) -> set[str]:
        rows = (
            await db_conn.execute(
                text(
                    f"SELECT row_to_json({table}.*)::text AS j FROM {table} "
                    "WHERE rubric_tree_version_id = :v"
                ),
                {"v": str(version_id)},
            )
        ).fetchall()
        return {hashlib.sha256(r[0].encode("utf-8")).hexdigest() for r in rows}

    pre_fingerprints: dict[str, set[str]] = {}
    for table in ("stack", "competency_block", "competency", "level"):
        pre_fingerprints[table] = await fingerprint(table, first.new_version_id)

    # Mutate the YAML (and bump version, though hash is what matters).
    _write_minimal_yaml(yaml_dir, descriptor="EDITED descriptor")
    second = await importer.seed(yaml_dir, dsn=migrated_schema)
    assert second.noop is False
    assert second.new_version_id is not None
    assert second.new_version_id != first.new_version_id

    # Prior-version rows must be byte-identical.
    for table in ("stack", "competency_block", "competency", "level"):
        post = await fingerprint(table, first.new_version_id)
        assert post == pre_fingerprints[table], f"{table}: prior-version rows were mutated"

    # New version produced one new audit row (SC-008).
    assert await _row_count(db_conn, "audit_log", action="rubric.versioned") == 2
    # Two rubric_tree_version rows total now.
    assert await _row_count(db_conn, "rubric_tree_version") == 2


async def test_rename_attempt_rejected(
    db_conn: AsyncConnection, migrated_schema: str, tmp_path: Path
) -> None:
    """SC-005 / FR-009 — a stable id rename is rejected; no rows written."""
    await _truncate_rubric(db_conn)
    yaml_dir = tmp_path / "rubric"
    _write_minimal_yaml(yaml_dir)
    importer = RubricImporter()
    await importer.seed(yaml_dir, dsn=migrated_schema)

    # Rewrite the YAML with the competency id renamed (no retire of the old id).
    renamed = textwrap.dedent(
        """\
        version: 2
        retired: false
        nodes:
          - id: block.core
            label_en: Core
            label_uk: Ядро
            parent: null
            retired: false
          - id: python.threading
            label_en: Threading
            label_uk: Потоки
            parent: block.core
            retired: false
            levels:
              - level: 1
                label_uk: Початковий
                descriptor_en: renamed
        """
    )
    (yaml_dir / "python.yaml").write_text(renamed, encoding="utf-8")

    versions_before = await _row_count(db_conn, "rubric_tree_version")
    with pytest.raises(RenameForbiddenError, match="python.concurrency"):
        await importer.seed(yaml_dir, dsn=migrated_schema)

    # No version row added.
    assert await _row_count(db_conn, "rubric_tree_version") == versions_before


async def test_payload_hash_recorded_on_version(
    db_conn: AsyncConnection, migrated_schema: str, tmp_path: Path
) -> None:
    """The new rubric_tree_version row carries the SHA-256 hex of the canonical bytes."""
    await _truncate_rubric(db_conn)
    yaml_dir = tmp_path / "rubric"
    _write_minimal_yaml(yaml_dir)
    importer = RubricImporter()
    result = await importer.seed(yaml_dir, dsn=migrated_schema)
    expected = _compute_payload_hash(yaml_dir)
    assert result.new_payload_hash == expected
    row = await db_conn.execute(
        text("SELECT payload_hash FROM rubric_tree_version WHERE id = :v"),
        {"v": str(result.new_version_id)},
    )
    assert row.scalar_one() == expected
    # 64-char hex.
    assert len(expected) == 64
