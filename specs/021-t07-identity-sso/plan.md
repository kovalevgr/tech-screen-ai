# Implementation Plan: Identity Platform SSO + role claims (T07)

**Branch**: `021-t07-identity-sso` | **Date**: 2026-07-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/021-t07-identity-sso/spec.md` (clarified 2026-07-05: Identity Platform per implementation plan; configs-as-code role mapping)

## Summary

T07 replaces the T13-era 401 auth placeholder with real staff SSO, in one PR, **contract-first inside the task** (§14): the `IdTokenClaims` JSON Schema lands in its own commit before any implementation. Deliverables:

1. **`docs/contracts/id-token-claims.json`** — the Appendix A contract for the verified ID-token claims the backend consumes.
2. **`infra/terraform/identity.tf`** (+ two root variables) — API enablement, project-global Identity Platform config (authorized domains, providers off except Google-via-console, blocking triggers behind tfvars), blocking-function runtime SA. **Authored + validated only; never applied here.**
3. **`infra/functions/auth_claims/`** — Python blocking function (domain gate + `role`/`hd` claim injection) with pure, repo-tested decision logic; **`configs/auth-roles.yaml`** as the §16 role source.
4. **Backend** — `app/backend/services/auth.py` (`IdTokenVerifier`: offline RS256 verification via `google-auth` + Google `securetoken` certs, TTL cache, kid-rotation refresh) wired into `app/backend/api/deps.py:get_current_user` behind the **`AUTH_MODE` env seam** (default `disabled` = pre-T07 posture); `Principal`/`require_roles` seam unchanged; `request.state.user` populated.
5. **Tests** — verifier unit tests (three role fixtures + all reject paths, locally-minted RSA tokens, zero network), seam API tests, settings boot-guard tests, blocking-function logic tests; `openapi.yaml` regenerated (bearer scheme).
6. **Governance/docs** — ADR-024 (amends ADR-016 internal path), ADR index, implementation-plan T07 correcting note, cloud-setup.md inventory/IAM update, `.env.example` keys.
7. **Operator runbook** (quickstart.md) — consent screen, provider enablement, function deploy, tfvars URIs + second apply, per-env `AUTH_MODE` flip (dev first), live acceptance sweep. **Nothing live happens in this task** (Cloud SQL sits in cost-idle; no GCP mutation, no tokens minted against the real project).

**Honest scope boundary**: same as specs/018 — everything cloud-side is *authored and validated* here (`terraform validate`, pre-commit, unit tests) and *exercised* only by the operator sweep recorded in quickstart.md.

## Technical Context

**Language/Version**: Python 3.12 (backend + blocking function); Terraform HCL (`hashicorp/google` ~> 6.0, ≥ 4.49 needed for `google_identity_platform_config` initializeAuth — satisfied).

**Primary Dependencies**: `google-auth>=2.45,<3` (already transitive via `google-genai`; now declared — R5), `cryptography` (google-auth base dep; declared in dev group for test key generation), `firebase-functions` (function-only, in its `requirements.txt`, never in the backend closure). No new HTTP client: certs fetch is stdlib `urllib` in `asyncio.to_thread`.

**Storage**: none new. No DB reads/writes on the auth path (deliberate — R6); no new Secret Manager shells (no secret is ours to hold — R3).

**Testing**: `uv run pytest` (suite baseline 107 passed / 78 skipped stays green; DB suite keeps skipping without a database); `uv run mypy app/backend`; `pre-commit run --files <changed>`; `python -m app.backend.generate_openapi --check`; `terraform -chdir=infra/terraform validate`.

**Target Platform**: GCP project `tech-screen-493720`, `europe-west1`; Identity Platform is project-global (shared by dev + prod — R8); enforcement is per-env Cloud Run env vars.

**Project Type**: cross-layer (infra HCL + backend middleware) — **sequential**, contract committed before the backend work starts (§14); no parallel fan-out.

**Performance Goals**: token verification is offline (no per-request network); certs fetch amortised over a 1 h TTL cache.

**Constraints**: §5 (no client secret in Git/state — provider console-managed), §6 (no new keys/CI identities), §9 (dark by default via `AUTH_MODE=disabled`), §11 (all-English artifacts), §14 (contract first), §15 (staff email flows into `request.state.user` for audit use, never into logs — reject-path errors carry no PII), §17/§18 (this flow; agents labelled below).

**Scale/Scope**: ~1 new HCL file + 2 variables, 1 function package (2 modules + tests), 1 config YAML, 1 contract JSON, ~2 backend modules touched + 1 new, 3 test files, ADR + 4 doc edits. ~1200 lines net.

## Constitution Check

| §   | Principle                           | Applies to T07?                                                                                                                              | Status |
| --- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first | Yes — auditable actor identity (`request.state.user`) is what makes reviewer actions attributable later.                                       | Pass   |
| 2   | Deterministic orchestration         | N/A — no LLM.                                                                                                                                  | N/A    |
| 3   | Append-only audit trail             | N/A — no audit-table writes in this task.                                                                                                      | N/A    |
| 4   | Immutable rubric snapshots          | N/A.                                                                                                                                           | N/A    |
| 5   | No plaintext secrets                | **Core.** OAuth client secret never exists in Git/state (console-provisioned — R3); no test PEMs committed (R5); gitleaks/forbid-env-values green. | Pass   |
| 6   | WIF only                            | Yes — no new CI identity, no SA keys; the function runtime SA is key-less.                                                                     | Pass   |
| 7   | Docker parity                       | Yes — `AUTH_MODE=disabled` default means dev/CI/prod containers behave identically until an env flips it deliberately.                          | Pass   |
| 8   | Two envs, no staging gate           | Yes — dev is the rehearsal for the runbook flip (ADR-023's stated purpose); single shared identity plane documented (R8).                       | Pass   |
| 9   | Dark launch by default              | **Core.** Ships fully dark behind `AUTH_MODE=disabled`; env-var-not-flag justified in R6 per FR-007.                                            | Pass   |
| 10  | Migration approval                  | N/A — zero migrations.                                                                                                                         | N/A    |
| 11  | Hybrid language                     | Yes — all artifacts English; no candidate-facing output.                                                                                       | Pass   |
| 12  | LLM cost caps                       | N/A — no LLM calls; GCIP free tier noted in ADR-024.                                                                                           | N/A    |
| 13  | Calibration never blocks merge      | N/A.                                                                                                                                           | N/A    |
| 14  | Contract-first                      | **Core.** `docs/contracts/id-token-claims.json` in its own commit before implementation; Appendix A row satisfied.                              | Pass   |
| 15  | PII containment                     | Yes — staff email lives in `request.state.user` (request-scoped, for audit actors), never in log output or error bodies; no candidate PII.      | Pass   |
| 16  | Configs as code                     | Yes — `configs/auth-roles.yaml` is the sole role source; changes are PRs (US4).                                                                | Pass   |
| 17  | Specs precede implementation        | Yes — this flow.                                                                                                                               | Pass   |
| 18  | Multi-agent explicit                | Yes — `infra-engineer` then `backend-engineer`, `parallel: false` throughout (§14 ordering inside one PR).                                      | Pass   |
| 19  | Rollback first-class                | Yes — disabling is an env-var flip (no deploy) or config-only redeploy; Terraform resources revert by plan/apply.                              | Pass   |
| 20  | Floor, not ceiling                  | Pass.                                                                                                                                          | Pass   |

**Gate result**: PASS. Post-design re-check: unchanged.

## Project Structure

### Documentation (this feature)

```text
specs/021-t07-identity-sso/
├── spec.md
├── plan.md                  # This file
├── research.md              # R1..R9
├── data-model.md            # Claims model, exception→HTTP mapping, resources, settings
├── contracts/
│   └── plan-contract.md     # Pointer: docs/contracts/id-token-claims.json + module surfaces
├── quickstart.md            # Operator runbook (console steps, deploy, flip, acceptance sweep)
├── checklists/requirements.md
└── tasks.md
```

### Source / config (repository root, after T07 merges)

```text
.
├── docs/contracts/id-token-claims.json        # NEW — the §14 contract (own commit, first)
├── adr/
│   ├── 016-auth-split-sso-magic-link.md       # EDIT — amendment note (internal path → ADR-024)
│   ├── 024-identity-platform-internal-sso.md  # NEW
│   └── README.md                              # EDIT — index row + 016 status
├── configs/auth-roles.yaml                    # NEW — §16 role mapping (email → role)
├── infra/
│   ├── terraform/
│   │   ├── identity.tf                        # NEW — APIs, GCIP config, function SA
│   │   ├── variables.tf                       # EDIT — auth_before_create_uri / auth_before_sign_in_uri
│   │   └── terraform.tfvars                   # EDIT — documented empty placeholders for the URIs
│   └── functions/auth_claims/                 # NEW — blocking function package
│       ├── main.py                            # SDK wiring (firebase-functions identity_fn)
│       ├── roles.py                           # pure decision logic (repo-tested)
│       ├── requirements.txt                   # function-only deps
│       └── tests/test_roles.py                # runs in the repo suite (testpaths extended)
├── app/backend/
│   ├── services/auth.py                       # NEW — IdTokenVerifier + verifier registry
│   ├── api/deps.py                            # EDIT — real get_current_user; seam preserved
│   ├── settings.py                            # EDIT — auth_mode / gcp_project / auth_allowed_domain + guard
│   ├── main.py                                # EDIT — lifespan installs verifier when enabled
│   ├── openapi.yaml                           # REGEN — bearer security scheme
│   └── tests/
│       ├── services/test_auth.py              # NEW — verifier unit tests (3 roles + rejects)
│       ├── api/test_auth.py                   # NEW — seam/API mapping tests
│       └── test_settings.py                   # EDIT — boot-guard cases
├── pyproject.toml                             # EDIT — google-auth dep, cryptography (dev), testpaths
├── .env.example                               # EDIT — AUTH_MODE / AUTH_ALLOWED_DOMAIN (ADR-022)
├── .gitignore                                 # EDIT — vendored function copy of auth-roles.yaml
└── docs/engineering/
    ├── cloud-setup.md                         # EDIT — inventory + IAM + versioning
    └── implementation-plan.md                 # EDIT — T07 correcting note (Appendix C compliant)
```

**Structure Decision / task labelling (§18)**: sequential single PR. Contract + HCL + function + runbook are `agent: infra-engineer`; middleware + tests + regen are `agent: backend-engineer`; governance/docs ride with their phase. `parallel: false` throughout — the §14 contract ordering is enforced *inside* the task by commit order (tasks.md phases).

## Complexity Tracking

No constitution violations to justify. The one deliberate deviation from the implementation plan's T07 prose ("membership driven by Workspace groups") is a clarified scope decision recorded in spec Clarifications + ADR-024 with an upgrade path, and a correcting note lands on the plan per its own Appendix C.
