# Implementation Plan: Configs-as-Code sync — rubric job (T16)

**Branch**: `022-t16-rubric-sync` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/022-t16-rubric-sync/spec.md`

## Summary

T16 completes the §16 delivery pipe: the T05a/T06 flag-sync workflow gains a `sync-rubric` job and becomes the single owner of every configs-as-code surface. `agent: infra-engineer` for the workflow/grants/docs, `agent: backend-engineer` for the Python gate + tests; **sequential** (`parallel: false`) — one branch, tightly coupled artefacts. Deliverables:

1. **`.github/workflows/sync-configs.yml`** — renamed from `sync-feature-flags.yml` (research R1); triggers extended (`configs/rubric/**`, `docs/contracts/rubric.schema.json`); new independent `sync-rubric` job matrixed dev+prod, same WIF SA + sha256-pinned proxy; gate steps (schema validation → baseline extraction → ADR-context collection → destructive gate) run **before** any cloud step.
2. **`scripts/sync_rubric_to_db.py`** — `check` (pure destructive-change classifier + ADR-citation gate; data-model.md taxonomy) and `sync` (thin wrapper over `RubricImporter.seed` with a 20 s cost-idle pre-flight and wake hint). No importer logic duplicated (research R2).
3. **`scripts/cloud-db-grants.sql`** — rubric-surface grants for the CI identity, per-statement justification, zero UPDATE/DELETE on rubric tables, INSERT-only on `audit_log`, nothing on the other five §3 tables (research R6).
4. **Tests** — `app/backend/tests/contracts/test_rubric_sync_check.py`, subprocess pattern, 9 cases, no DB/git/network.
5. **Docs** — cloud-setup.md § Configs-as-code sync (+ wake-first rule, v2.1 bump), feature-flags.md pointer, implementation-plan.md T05a/T16 notes, Terraform comment/description updates, flag-script docstring.
6. **Operator execution** (quickstart.md) — grants apply ×2, live gate/seed verification: the only part that cannot be exercised from CI.

**Honest scope boundary**: everything DB/cloud-side (grants, WIF, proxy, seed, sleeping-instance behaviour) can only be *exercised* live by the operator; branch-local validation = pytest subset + pre-commit (actionlint, shellcheck, gitleaks, rubric-schema, ruff) — same honesty pattern as T06.

## Technical Context

**Language/Version**: GitHub Actions YAML; Python 3.12 (stdlib + pyyaml for the gate; asyncpg + the T08 importer for sync); SQL (grants). No HCL resources added — only comments and one SA `description` string.

**Primary Dependencies**: `RubricImporter` (T08 — idempotent seed, §4 immutability, FR-009 rename rejection, FR-010 audit receipt); `scripts/check-rubric-schema.py` (T08 hook); T06 workflow contract (WIF provider/SA, instance names, IAM DB user, pinned proxy); branch `019-cloud-sql-idle` for `scripts/cloud-sql-power.sh` (research R8 — merge-order note).

**Storage**: existing tables only — `rubric_tree_version`, `stack`, `competency_block`, `competency`, `topic`, `level`, `audit_log` (INSERT-only). Zero migrations.

**Testing**: `uv run pytest app/backend/tests/contracts/test_rubric_sync_check.py` (9 tests, DB-free); `pre-commit run --files <changed>`; live acceptance = quickstart.md numbered sweep.

**Target Platform**: GitHub-hosted runners → Cloud SQL PG17 ×2 via Auth Proxy (project `tech-screen-493720`, `europe-west1`).

**Project Type**: CI workflow + operational scripts + docs. No application slice, no frontend, no migration.

**Performance Goals**: policy failures cost zero GCP calls; sleeping-instance failure surfaces < 60 s; benign no-op seed < 1 min per leg.

**Constraints**: §3 (INSERT-only on audit_log; five other tables untouched), §4/ADR-018 (importer semantics unchanged), §5/§6 (no secrets, WIF-only, pinned binary), §10 (no DDL at all), §16 (this task IS the enforcement), §17 (this spec flow), untrusted-input hygiene (no `github.event.*` text in `run:` blocks — env/file indirection only).

**Scale/Scope**: 1 workflow (renamed + ~140 new lines), 1 new script (~330 lines), 1 SQL extension, 1 test module, 5 doc touch-ups, 8 spec artefacts. Zero cloud mutations from this branch.

## Constitution Check

| §   | Principle                           | Applies to T16?                                                                                                                               | Status |
| --- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first | Indirect — the ADR gate preserves the "why did the rubric change" audit trail reviewers rely on.                                                | Pass   |
| 2   | Deterministic orchestration         | N/A — no LLM anywhere in this pipe.                                                                                                             | N/A    |
| 3   | Append-only audit trail             | **Core.** audit_log grant is INSERT-only (the §3-permitted verb, FR-010 receipt); trigger + REVOKEs untouched; other five tables get no grant.  | Pass   |
| 4   | Immutable rubric snapshots          | **Core.** All writes go through the T08 importer: new version per change, prior rows never touched; no UPDATE/DELETE grant exists to violate it. | Pass   |
| 5   | No plaintext secrets                | Yes — no new secret, IAM DB auth (no password in the DSN), gitleaks in pre-commit.                                                              | Pass   |
| 6   | WIF only                            | Yes — same `techscreen-flag-sync@` WIF identity; no JSON keys.                                                                                  | Pass   |
| 7   | Docker parity                       | N/A — CI-only job; the gate's pytest runs in the standard test env.                                                                             | N/A    |
| 8   | Two envs, no staging gate           | Yes — matrix dev+prod (ADR-023); neither env gates the other (fail-fast: false, independent legs).                                              | Pass   |
| 9   | Dark launch by default              | N/A — no candidate-facing feature; the sync applies config, it doesn't enable behaviour (flags stay the §9 mechanism).                          | N/A    |
| 10  | Migration approval                  | Yes — zero DDL; grants are DCL applied by the operator runbook, additive and re-runnable.                                                       | Pass   |
| 11  | Hybrid language                     | Yes — all artefacts English; Ukrainian appears only inside test fixture labels, as the schema requires.                                         | Pass   |
| 12  | LLM cost caps                       | N/A.                                                                                                                                            | N/A    |
| 13  | Calibration never blocks merge      | N/A — the ADR gate blocks *sync*, not merge, and is a governance check, not calibration.                                                        | N/A    |
| 14  | Contract-first for parallel work    | N/A — sequential; the plan `contract:` field is "none (internal job)" per the implementation plan.                                              | N/A    |
| 15  | PII containment                     | Yes — rubric YAML and audit receipts carry no candidate PII.                                                                                    | Pass   |
| 16  | Configs as code                     | **This task.** After T16 the workflow owns all §16 surfaces; drift stays impossible for flags and rubric alike.                                 | Pass   |
| 17  | Specs precede implementation        | Yes — this flow.                                                                                                                                | Pass   |
| 18  | Multi-agent explicit                | Yes — agents labelled per task, `parallel: false` throughout.                                                                                   | Pass   |
| 19  | Rollback first-class                | Yes — a bad rubric version is superseded by merging a fix (new version); nothing is destroyed, no deploy involved.                              | Pass   |
| 20  | Floor, not ceiling                  | Pass.                                                                                                                                           | Pass   |

**Gate result**: PASS. One deliberate posture change surfaced (not a violation): the first-ever grant on a §3 table — INSERT-only on `audit_log` — argued in research R6 and spec Clarifications. Post-design re-check: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/022-t16-rubric-sync/
├── spec.md
├── plan.md                  # This file
├── research.md              # R1..R9
├── data-model.md            # taxonomy, grants matrix, CLI/exit-code contract, workflow contract
├── quickstart.md            # operator runbook — live acceptance sweep
├── contracts/
│   └── plan-contract.md     # pointer: the artefacts downstream tasks bind to
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source (repository)

```text
.github/workflows/sync-configs.yml        # renamed + extended (infra-engineer)
scripts/sync_rubric_to_db.py              # new (backend-engineer)
scripts/cloud-db-grants.sql               # extended (infra-engineer)
scripts/sync_feature_flags_to_db.py       # docstring pointer only
app/backend/tests/contracts/test_rubric_sync_check.py   # new (backend-engineer)
infra/terraform/{iam,outputs}.tf          # comments + SA description
docs/engineering/{cloud-setup,feature-flags,implementation-plan}.md
```

## Phases

- **Phase 0 (research.md)**: rename impact, importer reuse, taxonomy, baseline + ADR-source mechanics, grants derivation, cost-idle failure mode — complete.
- **Phase 1 (design)**: data-model.md + contracts pointer + quickstart — complete.
- **Phase 2 (tasks.md)**: ordered tasks; branch-local ones executed in this PR, operator tasks left unchecked for the live sweep.
