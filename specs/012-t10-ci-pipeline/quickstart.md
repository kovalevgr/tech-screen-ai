# Quickstart: Validate the T10 CI-pipeline PR

Reviewer-facing walkthrough. The local part validates in under 10 minutes; the GitHub-only part is a one-time manual checklist the operator runs once branch protection is configured. Run from the repo root.

## Part A — Local validation (no GitHub needed)

### 1. The workflow is syntactically valid (SC-009)

```bash
docker run --rm -v "$PWD/.github/workflows":/wf rhysd/actionlint:latest -color /wf/ci.yml; echo "EXIT=$?"
# EXPECT: EXIT=0
```

### 2. The bash helpers pass shellcheck (research §10)

```bash
docker run --rm -v "$PWD":/src -w /src koalaman/shellcheck:stable \
  scripts/ci-render-migration-sql.sh scripts/ci-detect-destructive-ddl.sh \
  scripts/ci-reviewer.sh scripts/smoke-docker-stack.sh; echo "EXIT=$?"
# EXPECT: EXIT=0
```

### 3. The migration-SQL renderer produces DDL (SC-002 proxy)

```bash
docker compose -f docker-compose.test.yml --profile db up -d postgres
bash scripts/ci-render-migration-sql.sh | head -40
# EXPECT: the rendered CREATE TABLE / CREATE EXTENSION / ALTER ... SQL for the baseline + 0002 + 0003 migrations.
```

### 4. The destructive-DDL detector flags / passes correctly (SC-005 proxy)

```bash
# Negative fixture: a migration with only ADD COLUMN → needs_adr=false
printf 'op.execute("ALTER TABLE x ADD COLUMN y TEXT")\n' > /tmp/add.py
bash scripts/ci-detect-destructive-ddl.sh /tmp/add.py; echo "needs_adr from output file/var"

# Positive fixture: a migration with DROP COLUMN → needs_adr=true
printf 'op.execute("ALTER TABLE x DROP COLUMN y")\n' > /tmp/drop.py
bash scripts/ci-detect-destructive-ddl.sh /tmp/drop.py
# EXPECT: the script reports DROP COLUMN found and sets needs_adr=true.
```

### 5. The reviewer placeholder is honest

```bash
bash scripts/ci-reviewer.sh; echo "EXIT=$?"
# EXPECT: prints "Reviewer agent invocation DEFERRED — see docs/engineering/ci.md §Reviewer agent"; EXIT=0
```

### 6. The 138-test regression baseline still passes (SC-007)

```bash
docker compose -f docker-compose.test.yml --profile db run --rm backend \
  sh -c "alembic upgrade head && pytest app/backend/tests -q --no-header"
# EXPECT: 138 passed (or higher if newer tests landed).
```

### 7. The pre-commit chain is clean (SC-006 / SC-008)

```bash
pre-commit run --all-files
# EXPECT: every hook passes (including the new shellcheck hook); exit 0.
```

### 8. The docs answer the four contributor questions (SC-006)

Open `docs/engineering/ci.md` and confirm you can answer, from the doc alone:
1. Which checks block merge? *(§1 + §2 — backend / frontend / smoke / lint.)*
2. How do I fix a failing migration-SQL-render job? *(§6 troubleshooting.)*
3. What do `migration-approved` and `needs-adr` mean? *(§3 + §4.)*
4. Why is the reviewer-agent step a placeholder, and where is the real integration tracked? *(§5.)*

## Part B — GitHub-only validation (operator, one-time, after branch protection)

> These behaviours can only be exercised on GitHub. Run them once after configuring branch protection per `docs/engineering/ci.md` §2.

### 9. A trivial PR goes green (SC-001)

Open a one-line README-typo PR. Confirm the four required jobs (`backend`, `frontend`, `smoke`, `lint`) run and pass within ~5 minutes on warm cache; the `migration-sql-render` job is skipped; the merge button turns green.

### 10. A migration PR surfaces its SQL (SC-002 / SC-003)

Open a fixture PR adding a no-op additive migration under `alembic/versions/`. Confirm:
- the `migration-sql-render` job runs;
- a PR comment appears with the rendered SQL inside a collapsed `<details>` block within 90 seconds;
- a force-push updates the same comment (no duplicate).

### 11. A destructive migration is auto-labelled (SC-005)

Open a fixture PR whose migration contains `DROP COLUMN`. Confirm the `needs-adr` label appears on the PR within 60 seconds and the reviewer/human blocks merge until an ADR is linked.

### 12. An invariant break is blocked (SC-004)

Open a fixture PR that adds a `print()` in `app/backend/`. Confirm the `lint` job fails and the merge button stays red.

## Success-criteria checklist

- [ ] SC-001 — trivial PR < 5 min warm cache (Part B §9)
- [ ] SC-002 — migration SQL comment < 90 s (Part B §10; local render in A §3)
- [ ] SC-003 — comment updated in place, no duplicates (Part B §10)
- [ ] SC-004 — invariant break blocks merge (Part B §12; local lint in A §7)
- [ ] SC-005 — DROP COLUMN auto-labelled needs-adr (Part B §11; local detector in A §4)
- [ ] SC-006 — docs answer the 4 questions (A §8)
- [ ] SC-007 — 138 tests green (A §6)
- [ ] SC-008 — no new secrets (A §7 gitleaks/detect-secrets)
- [ ] SC-009 — actionlint clean (A §1)
- [ ] SC-010 — branch protection requires the 4 checks (operator config, documented A §8 / ci.md §2)
