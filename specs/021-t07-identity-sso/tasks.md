# Tasks: Identity Platform SSO + role claims (T07)

**Input**: Design documents from `specs/021-t07-identity-sso/`
**Prerequisites**: plan.md, spec.md (4 user stories), research.md (R1–R9), data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: verifier + seam + settings + blocking-function-logic unit tests ship with the code (FR-008); everything cloud-side is operator-executed (quickstart) — encoded as unchecked Phase 6 tasks, mirroring the specs/018 honesty pattern. Checked boxes attest to what shipped on this branch; Phase 6 stays open until the operator sweep.

**Organization**: sequential, one PR (constitution §18; §14 contract ordering enforced by phase/commit order). Story labels: US1 = staff calls API, US2 = rejects, US3 = dark-launch seam, US4 = configs-as-code roles.

## Phase 1: Spec + contract (agent: infra-engineer — §14 gate for everything below)

- [X] T001 Commit the Spec Kit artifacts (`specs/021-t07-identity-sso/` — spec, plan, research, data-model, contract pointer, quickstart, checklist, this file)
- [X] T002 [US1][US2] Commit `docs/contracts/id-token-claims.json` — JSON Schema (draft 2020-12, house style of `feature-flag.schema.json`) for the verified claims per data-model.md, **in its own commit before any implementation** (FR-001, Appendix A)

## Phase 2: Governance (FR-010)

- [X] T003 Write `adr/024-identity-platform-internal-sso.md` — context (ADR-016 ↔ implementation-plan conflict, research R1), decision (GCIP + Google provider; role claims from `configs/auth-roles.yaml` via blocking function; bearer tokens replace the planned signed-cookie internal session at MVP), alternatives (bare Workspace OAuth, Workspace Groups API + delegation, Admin-SDK persistent claims), consequences (shared identity plane dev+prod per R8; free tier; revocation = next sign-in; upgrade path to Groups API)
- [X] T004 Append the dated amendment note to `adr/016-auth-split-sso-magic-link.md` (in-place edits forbidden — amendment at the bottom) and update `adr/README.md`: 016 status → "Amended by 024", new 024 index row

## Phase 3: Infra — HCL + blocking function + role mapping (agent: infra-engineer)

- [X] T005 [US4] Create `configs/auth-roles.yaml` (§16 source of truth: `domain: n-ix.com`, `roles:` email→role map seeded with the operator) and gitignore the vendored function copy
- [X] T006 [US2][US4] Create `infra/functions/auth_claims/` — `roles.py` (pure: `load_mapping` with strict structural validation, `decide` per the data-model decision table), `main.py` (`firebase-functions` `identity_fn` wiring: block on non-domain/unverified, `custom_claims` at beforeUserCreated, `session_claims` at beforeUserSignedIn), `requirements.txt` (function-only deps)
- [X] T007 [US4] Add `infra/functions/auth_claims/tests/test_roles.py` (decision table + mapping validation + **the committed `configs/auth-roles.yaml` validates**) and extend pyproject `testpaths` so the repo suite runs it
- [X] T008 [US1][US2] Create `infra/terraform/identity.tf` per data-model.md (3 APIs, `google_identity_platform_config` with authorized domains from module outputs + tfvars-gated blocking triggers + `forward_inbound_credentials` off, `techscreen-auth-claims@` SA + logWriter) and add the two URI variables to `variables.tf` + documented empty placeholders in `terraform.tfvars`; `terraform fmt` + `validate` green

## Phase 4: Backend — verifier + seam (agent: backend-engineer)

- [X] T009 [US1][US2] Create `app/backend/services/auth.py` — `IdTokenVerifier` (google-auth RS256 decode against `securetoken` certs; TTL cache + unknown-`kid` refresh; `iss`/`aud`/`exp`/`iat`/`email_verified`/`hd`/email-suffix checks; `TokenVerificationError` / `MissingRoleClaimError` / `VerifiedIdentity`; module verifier registry `set_verifier`/`get_verifier`); declare `google-auth` in pyproject (already transitive — research R5)
- [X] T010 [US1][US2][US3] Rewire `app/backend/api/deps.py:get_current_user` — `HTTPBearer(auto_error=False)` sub-dependency (OpenAPI scheme), verifier-registry lookup (`None` → 401 dark posture), 401/403 mapping per data-model.md, `request.state.user = {sub, email, role}`, `Principal` gains optional `sub`/`email`; **`require_roles` + `Principal` call surface unchanged**
- [X] T011 [US3] Extend `app/backend/settings.py` (`auth_mode`, `gcp_project`, `auth_allowed_domain` + boot guard) and `app/backend/main.py` lifespan (install/uninstall verifier); add `AUTH_MODE`/`AUTH_ALLOWED_DOMAIN` to `.env.example` (ADR-022 non-secret defaults)
- [X] T012 [US1][US2][US3] Tests: `tests/services/test_auth.py` (three role fixtures; tampered/expired/wrong-domain/wrong-aud/wrong-iss/unverified/unknown-key/missing-role/`candidate`-role; certs refresh-on-rotation; registry round-trip — locally-minted RSA tokens, zero network, zero committed keys), `tests/api/test_auth.py` (HTTP-level 401/403/200 matrix through a probe app + real-app disabled-mode 401 + `request.state.user` + openapi scheme assertion), `test_settings.py` boot-guard cases
- [X] T013 Regenerate `app/backend/openapi.yaml` (`python -m app.backend.generate_openapi`) — bearer scheme lands; drift check green

## Phase 5: Docs + pre-merge verification

- [X] T014 Update `docs/engineering/cloud-setup.md` (resource inventory: Identity Platform + auth-claims function; IAM: humans sign-in path + `techscreen-auth-claims@` SA; document-versioning bump) and add the Appendix-C-compliant correcting note to `docs/engineering/implementation-plan.md` T07 (Workspace groups → configs-as-code per ADR-024/R2; env-seam note)
- [X] T015 Run `uv run pytest`, `uv run mypy app/backend`, `pre-commit run --files <changed>`, `terraform -chdir=infra/terraform validate`; fix fallout; confirm zero credential-shaped strings in the diff

## Phase 6: Operator execution + acceptance (live GCP — quickstart §§ 1–11; NOT executed on this branch)

- [ ] T016 [US1] Quickstart 1–2: consent screen; first apply (APIs, GCIP config, SA) — record SC-004 plan summary in the PR
- [ ] T017 [US1] Quickstart 3: enable the Google provider (console, auto client)
- [ ] T018 [US4] Quickstart 4–5: deploy both function endpoints; paste URIs into tfvars; second apply registers triggers
- [ ] T019 [US1][US2] Quickstart 6: token mint smoke — staff token carries `role` + `hd` (SC-005a); `@gmail.com` sign-in blocked (SC-006)
- [ ] T020 [US1][US2][US3] Quickstart 7–9: flip dev; curl matrix 200/401/403 (SC-005b) — needs dev DB awake + flag row on, then reverted
- [ ] T021 [US3] Quickstart 10: flip prod after the dev rehearsal; record rollback command in the PR

## Dependencies

```text
Phase 1 (T001–T002) → Phase 2 (T003–T004) → Phase 3 (T005–T008) → Phase 4 (T009–T013) → Phase 5 (T014–T015) → Phase 6 (T016 → … → T021)
```

Strictly sequential. T002 (contract) MUST precede T009–T013 in commit history (§14) — reviewer checks git log order.

## Implementation strategy

- MVP increment = Phases 1–5: mergeable, fully dark, suite green — nothing observable changes until an operator flips an env var.
- Phase 6 is deliberately post-merge: the blocking-trigger registration (T018) affects **all** sign-ins project-wide (shared plane, R8), so it happens only after the function is proven deployed; `AUTH_MODE=disabled` remains the sub-minute rollback at every step (§19).
