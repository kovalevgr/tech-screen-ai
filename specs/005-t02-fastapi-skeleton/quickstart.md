# Quickstart — Validating the T02 PR

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contract**: [contracts/backend-contract.md](./contracts/backend-contract.md)
**Audience**: Human reviewer or `reviewer` sub-agent validating the T02 PR before merge.
**Target time**: under 5 minutes end-to-end (after the first image build, which takes ~60 s).

Constitution §7 says dev = CI = prod containers; **this walkthrough exercises the canonical Docker loop only.** No native `uv run` step appears. If a step fails because Docker is not running, treat that as a hard precondition error rather than a T02 acceptance failure.

---

## Prerequisites (one-time per machine)

- **Docker Engine 24.x or Docker Desktop** running locally. `docker --version` and `docker compose version` both succeed.
- **`pre-commit` ≥ 3.7.0** installed on the host (T01 baseline) — the only host tool the canonical loop still needs, and only because pre-commit hooks fire from `git commit`.
- `git` and `curl` (for the `/health` smoke).

No GCP credentials, no Vertex access, no Postgres needed for T02 — backend boots without external dependencies (FR-003) and profiles gate everything else.

---

## Step 1 — Check out the PR branch

```bash
git fetch origin
git switch 005-t02-fastapi-skeleton
git status --short            # expect: clean tree
```

## Step 2 — Build the dev image

```bash
docker compose build backend
```

**Expected**: image `techscreen-dev-backend` builds successfully. First run is ~60 s (downloads Python base image + uv binary + deps); subsequent runs hit the layer cache and finish in <5 s. The image targets the `dev` stage of the multi-stage Dockerfile — pytest, ruff, mypy, httpx, types-PyYAML are all bundled.

## Step 3 — Start the backend and hit `/health`

```bash
docker compose up -d backend                           # detached so we can curl from the same shell
curl -sS http://127.0.0.1:8000/health | python -m json.tool
docker compose down                                    # stop + clean up
```

**Expected** (`status`, `service`, `version` keys — exact `version` value depends on `pyproject.toml`):

```json
{
    "status": "ok",
    "service": "techscreen-backend",
    "version": "0.0.0"
}
```

The container hot-reloads on source changes thanks to the `app/backend/` bind-mount in `docker-compose.yml`, so a follow-up `curl` after editing `main.py` shows the new behaviour without a rebuild.

## Step 4 — Run the backend test suite in container

```bash
docker compose -f docker-compose.test.yml run --rm --build backend \
    pytest app/backend/tests/ -v
```

**Expected**: 6 tests collected and all pass in well under 30 s after the build cache warms (SC-002):

- `test_health.py::test_health_returns_200_with_expected_shape`
- `test_logging_pii.py::test_candidate_email_redacted_in_field_and_freetext`
- `test_logging_pii.py::test_cyrillic_idn_email_redacted_in_freetext`
- `test_logging_pii.py::test_pii_redactor_does_not_mutate_input`
- `test_logging_pii.py::test_every_pii_field_in_allow_list_is_redacted[candidate_email]`
- `test_openapi_regeneration.py::test_committed_openapi_matches_regenerated_bytes`

If any test fails, the PR is not ready to merge — annotate the failure in the review.

## Step 5 — Verify the OpenAPI contract is committed and has no drift

```bash
# (a) File exists and is non-empty.
test -s app/backend/openapi.yaml && echo "openapi.yaml: present, $(wc -l < app/backend/openapi.yaml) lines"

# (b) Regeneration is idempotent on a clean tree (canonical command).
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi --check

# (c) Optional — regenerate and verify `git diff` is empty.
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi
git diff --stat app/backend/openapi.yaml     # expect: empty output
```

**Expected**: (a) prints a line count > 0; (b) exits 0 silently; (c) prints no diff (SC-003, SC-005).

## Step 6 — Run lint + type-check in container

```bash
docker compose -f docker-compose.test.yml run --rm backend \
    sh -c "ruff check app/backend && mypy app/backend"
```

**Expected**: both checks exit 0 inside the container (FR-012, SC-006). The dev image bundles ruff and mypy with the exact versions from `pyproject.toml` — host parity issues cannot regress this step.

Pre-commit still runs on the host (it operates around `git commit`, not inside the container):

```bash
pre-commit run --all-files
```

**Expected**: all 21 hooks exit 0 (FR-014).

## Step 7 — Diff audit: T02 PR scope

```bash
git diff --stat origin/main..HEAD
```

**Expected files changed** (± a few bytes):

```text
pyproject.toml                                       (deps added)
uv.lock                                              (regenerated)
README.md                                            ("Backend dev loop (Docker-first)")
Dockerfile                                           (`dev` stage + two pre-existing-bug fixes)
docker-compose.yml                                   (target: dev, profiles, env_file removed)
docker-compose.test.yml                              (target: dev, alembic gated on T05)
app/backend/main.py                                  (NEW)
app/backend/logging.py                               (NEW)
app/backend/generate_openapi.py                      (NEW)
app/backend/openapi.yaml                             (NEW)
app/backend/tests/__init__.py                        (NEW, empty)
app/backend/tests/conftest.py                        (NEW)
app/backend/tests/test_health.py                     (NEW)
app/backend/tests/test_logging_pii.py                (NEW)
app/backend/tests/test_openapi_regeneration.py      (NEW)
specs/005-t02-fastapi-skeleton/**                    (spec-kit artefacts)
```

**Not expected** (FR-011 scope fence): any Alembic migration, any `app/backend/llm/**`, any `app/backend/db/**`, any auth/CORS middleware, any new route besides `/health`, any change to `.pre-commit-config.yaml`, any change to `CLAUDE.md`, any change to `adr/`.

> Note: `Dockerfile`, `docker-compose.yml`, `docker-compose.test.yml` *are* edited by T02 — the FR-011 fence was originally written assuming Docker stacks were untouched until T09. Research §8 records the scope expansion: the §7 invariant could not be implemented today without a `dev` stage and matching compose tweaks, so the change ships in this PR with T09's full Docker-stack work still pending.

---

## Acceptance summary

| Check                                            | Tied to                        | Passes when                                                                  |
| ------------------------------------------------ | ------------------------------ | ---------------------------------------------------------------------------- |
| Step 2 — `docker compose build backend`          | SC-001                         | Dev image builds; first run < ~90 s, cached < 10 s.                          |
| Step 3 — backend `up` + `curl /health`           | SC-001, FR-001, FR-002, FR-003 | `/health` returns 200 with the expected JSON; backend boots without `.env`. |
| Step 4 — `pytest` in container                   | SC-002, FR-008–FR-010          | 6 tests pass in < 30 s.                                                      |
| Step 5 — OpenAPI committed + no drift            | SC-003, SC-005, FR-004, FR-005 | File present, `--check` exits 0, `git diff` empty after regen.               |
| Step 6 — ruff + mypy in container, pre-commit on host | SC-006, FR-012, FR-014    | Both container checks exit 0; pre-commit's 21 hooks exit 0 on host.          |
| Step 7 — diff audit                              | FR-011 (with §8 scope note)    | Only the expected file set is modified.                                      |

If every row is ✅, the PR satisfies T02 acceptance and can be approved.
