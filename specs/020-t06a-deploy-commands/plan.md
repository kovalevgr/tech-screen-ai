# Implementation Plan: Deploy commands — `/deploy` + `/promote` + `/rollback` (T06a)

**Branch**: `020-t06a-deploy-commands` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/020-t06a-deploy-commands/spec.md`

## Summary

T06a gives the project its release verbs. One PR, `agent: infra-engineer`, sequential (`parallel: false`). Deliverables:

1. **`.github/workflows/deploy.yml`** — `workflow_dispatch(env, service, git_ref)`; gate job (prod-ancestry check, §10 migration-label gate against the deployed-image SHA with `origin/main~1` fallback, Cloud SQL asleep guard) → per-service matrix job (buildx `runtime` target linux/amd64 → push `<sha>-<env>` to Artifact Registry → `gcloud run deploy --no-traffic` with unique revision suffix → move `candidate` tag → 60 s HTTP smoke on the tag URL → job summary either way).
2. **`.github/workflows/promote.yml`** — `workflow_dispatch(env, service, percent 10|50|100)`; pins the latest **ready** revision by name at the requested percent (never floating `LATEST` — research D8); before/after split in the summary.
3. **`.github/workflows/rollback.yml`** — `workflow_dispatch(env, service, revision?)`; auto-detects the previous serving revision (or takes the override), one `update-traffic` call, wall-clock measured and reported; preempts in-flight deploys via the shared `cloud-run-<env>` concurrency group.
4. **`infra/terraform/iam.tf` extension (author-only, operator applies)** — `techscreen-deployer@` SA, repository-pinned WIF binding (flag-sync house pattern), `roles/run.developer` (project), `roles/artifactregistry.writer` (repo-level), `roles/cloudsql.viewer` (project, guard reads), `roles/iam.serviceAccountUser` **SA-level on the four runtime SAs only** (research D4 role table).
5. **`scripts/cloud-sql-power.sh`** — operator cost-idle helper (`wake|sleep|status` × env) that the guard's error message references; the repo previously had no committed tooling for the live stopped-by-default practice (research D10).
6. **`docs/engineering/deploy-playbook.md` v2.0** — descriptive → implemented: exact workflow invocations, wake-the-DB rule, migration-gate mechanics, honest not-yet-implemented list (deploys table, ChatOps, drain check, revision cleanup).

**Honest scope boundary**: everything cloud-side can only be *exercised* live (deploy runs, traffic shifts, timing, IAM apply) — and this authoring session performs **zero cloud mutations and zero pushes**. Validation here = `pre-commit` (actionlint, shellcheck, gitleaks, terraform_validate) + design-time reasoning; the operator acceptance sweep in [quickstart.md](./quickstart.md) carries SC-002…SC-008. Additionally, the first *backend* deploy is expected to fail at readiness until the env-wiring follow-up lands (research D12) — the workflows are correct; the template is incomplete, and that gap is documented rather than papered over.

## Technical Context

**Language/Version**: GitHub Actions YAML (actionlint-clean); Bash (shellcheck-clean) inside `run:` blocks and `scripts/cloud-sql-power.sh`; Terraform HCL (1.5.2 local, `hashicorp/google ~> 6.0`). No application code.

**Primary Dependencies**: T06 live infrastructure (4 Cloud Run v2 services on placeholder images with `ignore_changes` on image, Artifact Registry `techscreen`, WIF pool `github-actions`/provider `github` pinned to `kovalevgr/tech-screen-ai`, per-env runtime SAs); T10's `migration-approved` label mechanic + `ci.yml` SQL render; Dockerfile/`Dockerfile.frontend` `runtime` targets (backend uvicorn :8000; frontend `pnpm start` honouring `PORT`, build-time `NEXT_PUBLIC_*` args); `google-github-actions/auth@v2` + `setup-gcloud@v2`; `docker/build-push-action@v6`.

**Storage**: none new. Artifact Registry gains sha-env image tags; Cloud Run gains revisions; no DB objects.

**Testing**: `pre-commit run --files <changed>` (actionlint, shellcheck, gitleaks, terraform_validate, forbid-env-values); `terraform -chdir=infra/terraform validate`; operator acceptance sweep SC-002…SC-008 (live dispatches on `dev`, timing, IAM policy diff) recorded in quickstart.md — same honesty pattern as specs/018's "cloud-side only exercisable live" boundary.

**Target Platform**: GCP project `tech-screen-493720`, region `europe-west1`, services `techscreen-backend(-dev)`/`techscreen-frontend(-dev)`, instances `techscreen-pg(-dev)` (stopped by default — cost-idle), GitHub Actions runners (`ubuntu-latest`, WIF only).

**Project Type**: infrastructure/CI (workflows + IAM HCL + operator script + playbook). No application slice.

**Performance Goals**: rollback `update-traffic` ≤ 60 s measured, workflow end-to-end ≤ 2 min (T06a acceptance), §19 ceiling 5 min; smoke budget ≤ 60 s; deploy end-to-end dominated by the Docker build (minutes, uncached).

**Constraints**: §5/§6 — WIF only, no JSON keys, no GitHub secrets, no credential-shaped strings; §10 — label gate enforced, migrations never applied by CI (research D2); §17/§18 — this spec flow, single infra-engineer; §19 — rollback semantics above; T06 contract — `/deploy` changes only the image (+ computed `ports`) on the Terraform-owned template; no untrusted `${{ }}` in `run:` blocks.

**Scale/Scope**: 3 new workflows (~450 lines YAML), 1 new script (~60 lines bash), ~55 lines HCL in `iam.tf`, 1 playbook rewrite, 8 spec-kit docs. Zero app-code lines.

## Constitution Check

*GATE: evaluated against constitution v1.1.*

| §   | Principle                           | Applies to T06a?                                                                                                                                                     | Status |
| --- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first | Indirect — 0 %-revisions + fast rollback are what keep bad deploys away from live candidate sessions.                                                                   | Pass   |
| 2   | Deterministic orchestration         | N/A — no LLM anywhere in the deploy path.                                                                                                                               | N/A    |
| 3   | Append-only audit trail             | Indirect — no DB writes from these workflows at all; the deployer identity cannot connect to Cloud SQL (viewer only, research D4).                                       | Pass   |
| 4   | Immutable rubric snapshots          | N/A.                                                                                                                                                                    | N/A    |
| 5   | No plaintext secrets                | **Core.** Zero new secrets: WIF auth, `github.token` for label reads, no GitHub repo secrets, no credential-shaped strings; gitleaks + forbid-env-values run on the diff. | Pass   |
| 6   | WIF only                            | **Core.** `techscreen-deployer@` authenticates via the existing OIDC pool; SA-level `serviceAccountUser` keeps it off the owner-role terraform SA; no keys anywhere.     | Pass   |
| 7   | Docker parity                       | Yes — the deployed image **is** the committed `runtime` target (same Dockerfiles as dev/CI); no deploy-time image mutation.                                              | Pass   |
| 8   | Two envs, no staging gate           | Yes — both envs are dispatch targets; dev is rehearsal (any ref), prod requires main ancestry but **never** requires "passed dev" (release path stays ADR-012's).        | Pass   |
| 9   | Dark launch by default              | Yes at the release layer — every deploy starts dark (0 % traffic) by construction; feature-level flags unaffected.                                                       | Pass   |
| 10  | Migration approval                  | **Core.** Label gate enforced at deploy time against the deployed baseline; CI never applies DDL (operator-run, research D2).                                            | Pass   |
| 11  | Hybrid language                     | Yes — all artefacts English; no candidate-facing text.                                                                                                                  | Pass   |
| 12  | LLM cost caps                       | N/A — no LLM calls; infra cost unchanged (revisions/tags are ~free; cost-idle tooling *reduces* spend).                                                                  | N/A    |
| 13  | Calibration never blocks merge      | N/A.                                                                                                                                                                    | N/A    |
| 14  | Contract-first for parallel work    | N/A — single agent, sequential; the workflow input contract is documented in data-model.md for T11.                                                                     | N/A    |
| 15  | PII containment                     | Yes — workflows log revision names/URLs/SHAs only; no candidate data exists in the deploy path.                                                                          | Pass   |
| 16  | Configs as code                     | Yes — workflows, IAM, and the power script are Git-owned; no console-side configuration introduced.                                                                     | Pass   |
| 17  | Specs precede implementation        | Yes — this flow.                                                                                                                                                        | Pass   |
| 18  | Multi-agent explicit                | Yes — `agent: infra-engineer`, `parallel: false` throughout.                                                                                                            | Pass   |
| 19  | Rollback first-class                | **Core.** This task is §19's implementation: one-call pinned-revision rollback, measured, preempting, documented.                                                        | Pass   |
| 20  | Floor, not ceiling                  | Pass.                                                                                                                                                                   | Pass   |

**Gate result**: PASS, no starred rows. Post-design re-check: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/020-t06a-deploy-commands/
├── spec.md
├── plan.md                  # This file
├── research.md              # D1..D12 (incl. the two mandated questions: IAM roles, migrations-in-CI)
├── data-model.md            # Workflow contracts, identity/role matrix, traffic state machine, gate tables
├── contracts/
│   └── plan-contract.md     # Pointer: the three workflow files + deployer IAM are the contract
├── quickstart.md            # Operator runbook: apply IAM, dev rehearsal, timing, acceptance sweep
├── checklists/requirements.md
└── tasks.md
```

### Source / config (repository root, after T06a merges)

```text
.
├── .github/workflows/
│   ├── deploy.yml                       # NEW — /deploy (gate + build + 0%-revision + smoke + summary)
│   ├── promote.yml                      # NEW — /promote 10|50|100 (pinned-revision shift)
│   └── rollback.yml                     # NEW — /rollback (previous-revision shift, timed, preempting)
├── infra/terraform/
│   └── iam.tf                           # EDIT — techscreen-deployer@ SA + WIF + 5 least-privilege bindings
├── scripts/
│   └── cloud-sql-power.sh               # NEW — operator wake|sleep|status helper (cost-idle mode)
└── docs/engineering/
    └── deploy-playbook.md               # REWRITE sections → v2.0 (implemented reality + not-yet list)
```

**Structure Decision**: gate/deploy split inside `deploy.yml` (one gate, per-service matrix fan-out with `fail-fast: false`); promote/rollback stay single-job with the same inline service matrix. IAM lands at the Terraform root next to the flag-sync identity it mirrors — the environment module is deliberately untouched (research D12 keeps the template-wiring fix a separate reviewed change).

## Complexity Tracking

No constitution violations to justify. Two deliberate deviations from older documents, both argued in research.md and declared in spec.md Assumptions: the migration gate ships in this PR instead of a post-T10 follow-up (T10 already merged — D7), and results land in job summaries instead of PR comments (workflow_dispatch has no PR context — D5). ADR-012's "implemented via a Claude Code skill" sentence is superseded by the workflow mechanism (release philosophy unchanged — D1); no ADR edit needed since ADR-012's *decision* (traffic splitting) is exactly what ships.
