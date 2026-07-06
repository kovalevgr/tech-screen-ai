#!/usr/bin/env python3
"""Sync ``configs/rubric/*.yaml`` into the database via the T08 importer (T16).

Invoked by the ``sync-rubric`` job in ``.github/workflows/sync-configs.yml``.
Two subcommands, matching the job's two phases:

``check`` — pure policy gate. No database, no git, no network:
    Compares a baseline snapshot of the rubric YAMLs (extracted by the
    workflow from the push's ``before`` commit into ``--baseline-dir``)
    against ``--rubric-dir`` and classifies every difference:

    - **FORBIDDEN** — a stable id disappeared from the payload entirely.
      Refused outright, mirroring the importer's own rename/removal rejection
      (specs/010 FR-009): retire the id (``retired: true``); ids are never
      deleted and never reused. No ADR citation can authorise this.
    - **DESTRUCTIVE** — the change alters assessment semantics going forward:
      a node retired or un-retired, a level rank removed, or a level's
      ``descriptor_en`` retyped. Allowed only when ``--adr-context-file``
      (head commit message + associated PR bodies, collected by the workflow)
      matches the citation regex ``ADR-\\d{3}``.
    - **benign** — everything else (new nodes / levels / stacks, label and
      evidence edits, ``version`` integer bumps). Applies without ceremony.

    The gate is a *policy* layer over the git diff; the importer's DB-side
    rename check (RenameForbiddenError) remains the structural safety net.

``sync`` — wraps :meth:`app.backend.services.rubric_importer.RubricImporter.seed`:
    schema validation, payload-hash no-op, a NEW immutable
    ``rubric_tree_version`` per content change (§4 / ADR-018), one
    ``audit_log`` receipt row (INSERT only — the single verb §3 permits).
    Reads ``DATABASE_URL`` from the environment. A pre-flight connect with a
    short timeout fails fast with a wake hint when the Cloud SQL instance is
    stopped (cost-idle mode).

Exit codes:
- ``0`` — check passed (no destructive change, or destructive + ADR citation);
  sync completed (including the hash-match no-op).
- ``1`` — destructive change without an ADR citation; DB unreachable; importer
  validation/rename error.
- ``2`` — forbidden id removal (retire instead), or configuration error
  (missing directory / ``DATABASE_URL``).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# The citation regex from the T16 plan text ("requires the PR body to include
# an ADR-xxx citation"). Word-bounded so 'ADR-0245' or 'BADR-024' don't match.
_ADR_RE: re.Pattern[str] = re.compile(r"\bADR-\d{3}\b")

# Pre-flight connect budget. The Auth Proxy answers on 127.0.0.1 even when the
# backing instance sleeps, so the failure we are catching is the proxy-side
# "instance is not running" dial error — it surfaces well inside this window.
_CONNECT_TIMEOUT_S: float = 20.0

FORBIDDEN: str = "FORBIDDEN"
DESTRUCTIVE: str = "DESTRUCTIVE"


@dataclass(frozen=True)
class Finding:
    """One classified difference between the baseline and the current payload."""

    severity: str  # FORBIDDEN | DESTRUCTIVE
    kind: str  # NODE_REMOVED | NODE_RETIRED | NODE_UNRETIRED | LEVEL_REMOVED | LEVEL_RETYPED
    detail: str


@dataclass(frozen=True)
class _Node:
    """Destructiveness-relevant projection of one rubric node."""

    retired: bool
    levels: dict[int, str]  # rank -> descriptor_en


def _load_yaml_dir(path: Path) -> dict[str, dict[str, Any]]:
    """Return ``{filename: parsed-doc}`` for every ``*.yaml`` in ``path``."""
    docs: dict[str, dict[str, Any]] = {}
    for file in sorted(path.glob("*.yaml")):
        loaded = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{file}: expected a YAML mapping at top level")
        docs[file.name] = loaded
    return docs


def _index_nodes(docs: dict[str, dict[str, Any]]) -> dict[str, _Node]:
    """Flatten all docs into ``{stable-id: _Node}``.

    A file-level ``retired: true`` marks every node inside as retired (schema
    semantics). Id uniqueness across files is owned by the schema hook and the
    importer; on collision the last file (sorted order) wins here.
    """
    index: dict[str, _Node] = {}
    for doc in docs.values():
        stack_retired = bool(doc.get("retired", False))
        for node in doc.get("nodes") or []:
            levels = {
                int(lvl["level"]): str(lvl.get("descriptor_en", ""))
                for lvl in node.get("levels") or []
            }
            index[str(node["id"])] = _Node(
                retired=stack_retired or bool(node.get("retired", False)),
                levels=levels,
            )
    return index


def detect_destructive_changes(
    baseline_docs: dict[str, dict[str, Any]],
    current_docs: dict[str, dict[str, Any]],
) -> list[Finding]:
    """Classify baseline → current differences. Pure function; DB-free."""
    old = _index_nodes(baseline_docs)
    new = _index_nodes(current_docs)
    findings: list[Finding] = []
    for node_id in sorted(old):
        old_node = old[node_id]
        new_node = new.get(node_id)
        if new_node is None:
            findings.append(
                Finding(
                    FORBIDDEN,
                    "NODE_REMOVED",
                    f"stable id '{node_id}' disappeared from the payload — ids are never "
                    f"deleted or renamed; set 'retired: true' instead (specs/010 FR-009)",
                )
            )
            continue
        if not old_node.retired and new_node.retired:
            findings.append(
                Finding(DESTRUCTIVE, "NODE_RETIRED", f"'{node_id}' goes active -> retired")
            )
        elif old_node.retired and not new_node.retired:
            findings.append(
                Finding(
                    DESTRUCTIVE,
                    "NODE_UNRETIRED",
                    f"'{node_id}' goes retired -> active (ids are never reused after retire)",
                )
            )
        if old_node.retired or new_node.retired:
            # Level comparisons only make sense for nodes active on both
            # sides; retiring already reports the whole node.
            continue
        for rank in sorted(old_node.levels):
            old_desc = old_node.levels[rank]
            new_desc = new_node.levels.get(rank)
            if new_desc is None:
                findings.append(
                    Finding(DESTRUCTIVE, "LEVEL_REMOVED", f"'{node_id}' level {rank} removed")
                )
            elif new_desc != old_desc:
                findings.append(
                    Finding(
                        DESTRUCTIVE,
                        "LEVEL_RETYPED",
                        f"'{node_id}' level {rank} descriptor_en changed "
                        f"(assessment semantics shift going forward)",
                    )
                )
    return findings


def has_adr_citation(text: str) -> bool:
    return bool(_ADR_RE.search(text))


def _cited_adrs(text: str) -> list[str]:
    return sorted(set(_ADR_RE.findall(text)))


def _cmd_check(args: argparse.Namespace) -> int:
    baseline_dir: Path = args.baseline_dir
    rubric_dir: Path = args.rubric_dir
    if not baseline_dir.is_dir():
        print(f"error: baseline directory missing: {baseline_dir}", file=sys.stderr)
        return 2
    if not rubric_dir.is_dir():
        print(f"error: rubric directory missing: {rubric_dir}", file=sys.stderr)
        return 2

    findings = detect_destructive_changes(_load_yaml_dir(baseline_dir), _load_yaml_dir(rubric_dir))
    forbidden = [f for f in findings if f.severity == FORBIDDEN]
    destructive = [f for f in findings if f.severity == DESTRUCTIVE]

    for f in forbidden:
        print(f"::error::rubric-sync {f.kind}: {f.detail}")
    if forbidden:
        print(
            "error: forbidden change(s) — no ADR citation can authorise deleting a "
            "stable id. Retire the id and introduce replacements as new ids.",
            file=sys.stderr,
        )
        return 2

    if not destructive:
        print("rubric check: no destructive changes against the baseline")
        return 0

    adr_text = ""
    if args.adr_context_file is not None and args.adr_context_file.is_file():
        adr_text = args.adr_context_file.read_text(encoding="utf-8")
    if has_adr_citation(adr_text):
        cited = ", ".join(_cited_adrs(adr_text))
        for f in destructive:
            print(f"::notice::rubric-sync {f.kind}: {f.detail} — authorised by citation: {cited}")
        print(f"rubric check: {len(destructive)} destructive change(s) authorised by {cited}")
        return 0

    for f in destructive:
        print(f"::error::rubric-sync {f.kind}: {f.detail}")
    print(
        f"error: {len(destructive)} destructive change(s) but no ADR citation found. "
        "Destructive rubric edits (retired/un-retired node, removed level, retyped "
        "descriptor_en) require an 'ADR-xxx' reference in the merged PR body or the "
        "head commit message (T16 gate).",
        file=sys.stderr,
    )
    return 1


def _wake_hint() -> str:
    env_name = os.environ.get("SYNC_ENV", "<env>")
    return (
        "The Cloud SQL instance is likely STOPPED (cost-idle mode). Wake it with "
        f"'scripts/cloud-sql-power.sh wake {env_name}' (~60-90 s until RUNNABLE), "
        "then use 'Re-run failed jobs' on this workflow run."
    )


async def _run_sync(dsn: str, yaml_dir: Path, dry_run: bool) -> int:
    # Deferred imports: `check` must stay runnable with pyyaml alone, and the
    # importer lives inside the backend package (namespace import off repo root).
    sys.path.insert(0, str(_REPO_ROOT))
    import asyncpg

    from app.backend.services.rubric_importer import RubricImporter, RubricImporterError

    # Fail-fast pre-flight: the importer's own connect would eventually error
    # too, but this bounds the wait and owns the cost-idle message.
    try:
        conn = await asyncpg.connect(dsn, timeout=_CONNECT_TIMEOUT_S)
        await conn.close()
    except (TimeoutError, OSError, asyncpg.PostgresError) as exc:
        print(f"::error::rubric-sync: cannot reach the database: {exc}. {_wake_hint()}")
        return 1

    try:
        result = await RubricImporter().seed(yaml_dir, dsn=dsn, dry_run=dry_run)
    except RubricImporterError as exc:
        print(f"::error::rubric-sync: importer refused the payload: {exc}")
        return 1

    if result.noop:
        print(f"no-op: payload hash {result.new_payload_hash[:12]} matches the latest version")
    elif result.new_version_id is None:
        print(f"dry-run: would create a new version (hash {result.new_payload_hash[:12]})")
    else:
        print(
            f"created rubric_tree_version {result.new_version_id} "
            f"(hash {result.new_payload_hash[:12]}, {result.rows_inserted} rows inserted)"
        )
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("error: DATABASE_URL is required for sync", file=sys.stderr)
        return 2
    yaml_dir: Path = args.rubric_dir
    if not yaml_dir.is_dir():
        print(f"error: rubric directory missing: {yaml_dir}", file=sys.stderr)
        return 2
    return asyncio.run(_run_sync(dsn, yaml_dir, args.dry_run))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python scripts/sync_rubric_to_db.py",
        description=__doc__.splitlines()[0],
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    check = sub.add_parser("check", help="Destructive-change gate (no DB access).")
    check.add_argument(
        "--baseline-dir",
        type=Path,
        required=True,
        help="Directory of baseline rubric YAMLs (extracted from the pre-push commit).",
    )
    check.add_argument(
        "--rubric-dir",
        type=Path,
        default=Path("configs/rubric"),
        help="Directory of current rubric YAMLs (default: configs/rubric).",
    )
    check.add_argument(
        "--adr-context-file",
        type=Path,
        default=None,
        help="File holding the head commit message + PR bodies scanned for 'ADR-xxx'.",
    )

    sync = sub.add_parser("sync", help="Seed the DB via the T08 importer (DATABASE_URL).")
    sync.add_argument(
        "--rubric-dir",
        type=Path,
        default=Path("configs/rubric"),
        help="Directory of source-of-truth rubric YAMLs (default: configs/rubric).",
    )
    sync.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate + compute the diff; do NOT write to the DB.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args)
    return _cmd_sync(args)


if __name__ == "__main__":
    sys.exit(main())
