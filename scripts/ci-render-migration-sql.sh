#!/usr/bin/env bash
# T10 — render the full Alembic migration DDL as SQL, for human review in a PR.
#
# Runs `alembic upgrade head --sql` in OFFLINE mode inside the test-stack
# backend container (T05 research §1: our async env.py renders every
# op.execute(...) raw SQL verbatim offline, with no live DB connection).
# Writes the rendered SQL to stdout; the CI migration-sql-render job captures
# it and posts it as a PR comment.
#
# Local usage (host): bash scripts/ci-render-migration-sql.sh
# CI usage: same — the runner has docker compose.
#
# Exit 0 on success; non-zero (with a stderr message) if the render fails.

set -euo pipefail

readonly COMPOSE_FILE="docker-compose.test.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "ci-render-migration-sql: docker not found on PATH" >&2
  exit 1
fi

# Offline render — no DB needed. The backend service's default command is
# overridden so we only run the alembic offline SQL render.
docker compose -f "${COMPOSE_FILE}" run --rm --no-deps backend \
  alembic upgrade head --sql
