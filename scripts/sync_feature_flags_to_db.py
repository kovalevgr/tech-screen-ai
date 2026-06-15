#!/usr/bin/env python3
"""Sync ``configs/feature-flags.yaml`` into the ``feature_flag`` DB table (T05a).

Invoked by ``.github/workflows/sync-feature-flags.yml`` after WIF auth +
Cloud SQL Auth Proxy are up. Reads ``DATABASE_URL`` from the environment.

For every YAML entry: ``INSERT ... ON CONFLICT DO UPDATE`` — on first sync
the row gets ``enabled=<yaml.default>``; subsequent syncs leave ``enabled``
alone (operators may have flipped it via direct SQL or a later PR).

For every DB row with no YAML counterpart: emit a GitHub Actions
``::warning::`` annotation. **Never deletes** (FR-009): an orphan row may be
intentional (e.g. emergency disable preceding a YAML follow-up); a human
decides whether to reconcile.

Exit codes:
- ``0`` — upsert + orphan check completed; non-fatal warnings may have been
  emitted.
- ``1`` — DB unreachable, auth failed, or upsert raised.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
import yaml

_REPO_ROOT: Path = Path(__file__).resolve().parents[1]
_YAML_PATH: Path = _REPO_ROOT / "configs" / "feature-flags.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


async def _upsert_all(conn: asyncpg.Connection, flags: list[dict[str, Any]]) -> int:
    upserted = 0
    for entry in flags:
        await conn.execute(
            """
            INSERT INTO feature_flag (name, owner, default_value, enabled, updated_by)
            VALUES ($1, $2, $3::jsonb, $4, 'configs-as-code')
            ON CONFLICT (name) DO UPDATE SET
              owner = EXCLUDED.owner,
              default_value = EXCLUDED.default_value,
              updated_by = 'configs-as-code'
            """,
            entry["name"],
            entry["owner"],
            json.dumps(entry["default_value"]) if entry.get("default_value") is not None else None,
            bool(entry["default"]),
        )
        upserted += 1
    return upserted


async def _warn_on_orphans(conn: asyncpg.Connection, yaml_names: set[str]) -> int:
    rows = await conn.fetch("SELECT name FROM feature_flag")
    orphans = [r["name"] for r in rows if r["name"] not in yaml_names]
    for name in sorted(orphans):
        # GitHub Actions warning annotation — surfaces in the run UI.
        print(
            f"::warning::feature_flag row '{name}' exists in DB but has no YAML "
            "entry (orphan). Not auto-deleted (FR-009)."
        )
    return len(orphans)


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: DATABASE_URL is required", file=sys.stderr)
        return 1
    yaml_doc = _load_yaml(_YAML_PATH)
    flags: list[dict[str, Any]] = list(yaml_doc.get("flags") or [])
    yaml_names = {f["name"] for f in flags}

    try:
        conn = await asyncpg.connect(dsn)
    except Exception as exc:  # noqa: BLE001 — workflow logs the cause
        print(f"error: cannot connect to {dsn!r}: {exc}", file=sys.stderr)
        return 1
    try:
        upserted = await _upsert_all(conn, flags)
        orphans = await _warn_on_orphans(conn, yaml_names)
    finally:
        await conn.close()
    print(f"upserted {upserted} flag(s); {orphans} orphan row(s) flagged as warnings")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
