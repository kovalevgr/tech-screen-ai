"""CLI entrypoint for the rubric matrix importer (T08).

Subcommands:

- ``convert <xlsx> --out <dir>`` — read a workbook, validate, write canonical
  YAMLs to ``<dir>``.
- ``seed [--dry-run]`` — read ``configs/rubric/*.yaml`` and reconcile the
  database. New ``rubric_tree_version`` per content change; identical payload
  hash → no-op. Audit row per new version (FR-010).

Exit codes:
- ``0`` — success / no-op.
- ``1`` — validation failure (xlsx structure, YAML schema, rename rejection).
- ``2`` — configuration error (DSN missing, IO error).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.backend.services.rubric_importer import (
    RubricImporter,
    RubricImporterError,
    SeedResult,
)
from app.backend.settings import Settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.backend.cli.import_matrix",
        description="Convert a rubric matrix workbook into YAML and/or seed the database.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    convert = sub.add_parser("convert", help="xlsx → YAML (no DB access).")
    convert.add_argument("xlsx", type=Path, help="Path to the .xlsx workbook.")
    convert.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for the canonical YAML files.",
    )

    seed = sub.add_parser("seed", help="YAML → DB (idempotent; advisory-locked).")
    seed.add_argument(
        "--yaml-dir",
        type=Path,
        default=Path("configs/rubric"),
        help="Directory containing the source-of-truth YAMLs (default: configs/rubric).",
    )
    seed.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and compute the diff; do NOT write to the DB.",
    )
    return parser


def _print_seed_result(result: SeedResult) -> None:
    if result.noop:
        print(f"no-op: payload hash {result.new_payload_hash[:12]} matches latest version")
    elif result.new_version_id is None:
        print(f"dry-run: would create new version (hash {result.new_payload_hash[:12]})")
    else:
        print(
            f"created rubric_tree_version {result.new_version_id} "
            f"(hash {result.new_payload_hash[:12]}, "
            f"{result.rows_inserted} rows inserted)"
        )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    importer = RubricImporter()
    try:
        if args.cmd == "convert":
            written = importer.convert(args.xlsx, args.out)
            for path in written:
                print(path)
            return 0
        if args.cmd == "seed":
            settings = Settings()
            if not settings.database_url:
                print("error: DATABASE_URL is required for seed", file=sys.stderr)
                return 2
            result = asyncio.run(
                importer.seed(args.yaml_dir, dsn=settings.database_url, dry_run=args.dry_run)
            )
            _print_seed_result(result)
            return 0
    except RubricImporterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
