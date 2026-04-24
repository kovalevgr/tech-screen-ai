# Quickstart — Validating the T02 PR

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contract**: [contracts/backend-contract.md](./contracts/backend-contract.md)
**Audience**: Human reviewer or `reviewer` sub-agent validating the T02 PR before merge.
**Target time**: under 5 minutes end-to-end.

---

## Prerequisites (one-time per machine — same as T01)

- Python 3.12 on `PATH`.
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`).
- `pre-commit` ≥ 3.7.0 installed (T01 already required this).

No GCP credentials, no Vertex access, no Postgres, no Docker required for T02 — the skeleton must boot without any of them (FR-003).

---

## Step 1 — Check out the PR branch and sync deps

```bash
git fetch origin
git switch 003-t02-fastapi-skeleton
git status --short            # expect: clean tree

uv sync --dev                 # installs fastapi/uvicorn/structlog/pyyaml + pytest/httpx
```

**Expected**: `uv sync` completes, produces/updates `.venv/`. `git status --short` prints nothing (the lockfile change is already committed on this branch).

## Step 2 — Start the backend and hit `/health`

In one shell:

```bash
uv run uvicorn app.backend.main:app --reload
```

**Expected**: uvicorn prints `Application startup complete.` within ~5 s (SC-001). No traceback, no missing-env-var error.

In another shell:

```bash
curl -sS http://127.0.0.1:8000/health | python -m json.tool
```

**Expected** (`status`, `service`, `version` keys — exact `version` value depends on `pyproject.toml`):

```json
{
    "status": "ok",
    "service": "techscreen-backend",
    "version": "0.0.0"
}
```

Stop the dev server (`Ctrl-C`) before Step 3 — the test client constructs its own in-process app and does not need the external server.

## Step 3 — Run the backend test suite

```bash
uv run pytest app/backend/tests/ -v
```

**Expected**: three tests collected and all pass in well under 30 s (SC-002):

- `test_health.py::test_health_returns_200_with_expected_shape`
- `test_logging_pii.py::test_candidate_email_redacted_in_field_and_freetext`
- `test_openapi_regeneration.py::test_committed_openapi_matches_regenerated_bytes`

If any test fails, the PR is not ready to merge — annotate the failure in the review.

## Step 4 — Verify the OpenAPI contract is committed and has no drift

```bash
# (a) File exists and is non-empty.
test -s app/backend/openapi.yaml && echo "openapi.yaml: present, $(wc -l < app/backend/openapi.yaml) lines"

# (b) Regeneration is idempotent on a clean tree (equivalent to the test in Step 3,
#     but invokes the module directly — useful as a reviewer sanity check).
uv run python -m app.backend.generate_openapi --check

# (c) Optional — regenerate and verify `git diff` is empty.
uv run python -m app.backend.generate_openapi
git diff --stat app/backend/openapi.yaml     # expect: empty output
```

**Expected**: (a) prints a line count > 0; (b) exits 0 silently (or prints "no drift"); (c) prints no diff (SC-003, SC-005).

## Step 5 — Verify PII redaction directly (quick sanity, orthogonal to Step 3)

```bash
uv run python - <<'PY'
from app.backend.logging import configure_logging
import structlog, json, io, sys

# Capture structlog output to a string buffer for inspection.
buf = io.StringIO()
configure_logging(stream=buf)
log = structlog.get_logger("quickstart")
log.info("candidate hit from foo bar x@y.com", candidate_email="x@y.com")

out = buf.getvalue()
assert "x@y.com" not in out, f"RAW EMAIL LEAKED: {out!r}"
assert "<REDACTED>" in out or "<REDACTED_EMAIL>" in out, f"no redaction marker: {out!r}"
print("PII redaction OK. Sample output:")
print(out.strip())
PY
```

**Expected**: prints `PII redaction OK.` followed by a JSON log line containing `<REDACTED>` in the `candidate_email` field and `<REDACTED_EMAIL>` in place of the free-text email. Zero occurrence of `x@y.com` anywhere (SC-004).

> If `configure_logging` doesn't accept a `stream=` kwarg in the final implementation, swap for whatever the final signature is and record the deviation in the review. The spec locks the contract (§3 of `backend-contract.md`), not the test-harness ergonomics.

## Step 6 — Run guardrails + lint + type-check (inherits T01 contract)

```bash
pre-commit run --all-files                              # T01 Command 3
uv run ruff check app/backend                           # T01 Command 1 (lint half)
uv run mypy app/backend                                 # T01 Command 1 (type-check half)
```

**Expected**: all exit 0 (FR-012, SC-006). The T01 baseline forbids regressions — any new pre-commit finding or ruff/mypy error is a blocker.

## Step 7 — Diff audit: T02 PR scope

```bash
git diff --stat origin/main..HEAD
```

**Expected files changed** (± a few bytes):

```text
pyproject.toml                                  (deps added)
uv.lock                                         (regenerated)
README.md                                       (Developer setup: backend subsections)
app/backend/main.py                             (NEW)
app/backend/logging.py                          (NEW)
app/backend/generate_openapi.py                 (NEW)
app/backend/openapi.yaml                        (NEW)
app/backend/tests/__init__.py                   (NEW, empty)
app/backend/tests/conftest.py                   (NEW)
app/backend/tests/test_health.py                (NEW)
app/backend/tests/test_logging_pii.py           (NEW)
app/backend/tests/test_openapi_regeneration.py  (NEW)
specs/003-t02-fastapi-skeleton/**               (spec-kit artefacts)
```

**Not expected** (FR-011 scope fence): any Alembic migration, any `app/backend/llm/**`, any `app/backend/db/**`, any auth/CORS middleware, any new route besides `/health`, any change to `.pre-commit-config.yaml`, any change to `Dockerfile*`, any change to `docker-compose*.yml`, any change to `CLAUDE.md`, any change to `adr/`.

---

## Acceptance summary

| Check                                 | Tied to                   | Passes when                                                             |
| ------------------------------------- | ------------------------- | ----------------------------------------------------------------------- |
| Step 2 — uvicorn starts + `/health`   | SC-001, FR-001, FR-002    | `uvicorn` boots in < 5 s; `/health` returns 200 with the expected JSON. |
| Step 3 — `pytest` all pass            | SC-002, FR-008, FR-009, FR-010 | Three tests pass in < 30 s.                                         |
| Step 4 — OpenAPI committed + no drift | SC-003, SC-005, FR-004, FR-005 | File present, `--check` exits 0, `git diff` empty after regen.      |
| Step 5 — PII redaction sanity         | SC-004, FR-006, FR-007    | Raw email absent from serialised output; redaction literals present.    |
| Step 6 — T01 guardrails still green   | SC-006, FR-012, FR-014    | pre-commit, ruff, mypy all exit 0.                                      |
| Step 7 — diff audit                   | FR-011                    | Only the expected file set is modified; no out-of-scope files touched.  |

If every row is ✅, the PR satisfies T02 acceptance and can be approved.
