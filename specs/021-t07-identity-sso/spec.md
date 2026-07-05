# Feature Specification: Identity Platform SSO + role claims (T07)

**Feature Branch**: `021-t07-identity-sso`
**Created**: 2026-07-05
**Status**: Draft
**Input**: User description: T07 — Identity Platform SSO + role claims per `docs/engineering/implementation-plan.md` Tier 1. Identity Platform with the Google provider constrained to `n-ix.com`; custom claim `role ∈ {admin, recruiter, reviewer}` in the ID token; backend middleware validates the JWT and populates `request.state.user`; contract `docs/contracts/id-token-claims.json` committed first (Appendix A). Terraform authored but never applied in this task; all live steps are operator runbook items.

## Clarifications

### Session 2026-07-05

- Q: ADR-016 says internal SSO is bare Workspace OAuth with a `user_role` DB table and "No Identity Platform bill", while `implementation-plan.md` T07 (same authorship window) says "Identity Platform with Google provider … custom claim `role` injected by a Cloud Function trigger". Which one does T07 build? → A: **Identity Platform** (the implementation-plan reading — T07's own title and acceptance name it; the free tier keeps the "no bill" consequence true at MVP volume). Consequence: T07 ships **ADR-024** amending ADR-016's internal-user path (the candidate magic-link half is untouched), same reconciliation pattern ADR-023 used for ADR-009.
- Q: "Membership driven by Workspace groups" (implementation-plan T07) — Groups API with domain-wide delegation at MVP? → A: **No.** Role membership is configs-as-code (`configs/auth-roles.yaml`, §16) read by the blocking function; the Workspace-groups automation is the documented upgrade path (ADR-024). ADR-016 already said "not via Workspace groups at MVP".

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are: **staff** (recruiters, reviewers, admins — N-iX Workspace accounts) who need to call authenticated API endpoints; the **operator** (Ihor) who enables SSO per environment and owns the role mapping; **every later task** that needs a real `request.state.user` (T14 admin UI wiring, T21 audit actor identity); and the **backend itself**, which finally replaces the T13-era 401 placeholder with real verification while staying byte-identical for local dev and tests.

### User Story 1 — Staff member calls the API as themselves (Priority: P1)

A recruiter signs in with their `@n-ix.com` Google account through Identity Platform and receives an ID token whose custom `role` claim matches the committed role mapping. API requests carrying that token as a bearer credential resolve to a `Principal{sub, email, role}`; recruiter/admin roles pass the existing `require_roles("recruiter", "admin")` gate on position-template endpoints, and `request.state.user` carries the identity for downstream audit use.

**Why this priority**: P1 — this is the task. Every authenticated endpoint from Tier 2 onward depends on this seam being real.

**Independent Test**: Unit: a locally-minted RS256 token with `role=recruiter` passes the verifier and produces the expected `Principal`. Live (operator): `curl -H "Authorization: Bearer $TOKEN"` against dev returns 200 on a role-gated endpooint once the flag row is on.

**Acceptance Scenarios**:

1. **Given** a validly signed token with `role=admin` (or `recruiter`, `reviewer`), **When** it is presented to the verifier, **Then** verification succeeds and yields `{sub, email, role}` matching the token claims (three role fixtures — constitution acceptance).
2. **Given** a valid recruiter token, **When** a position-template endpoint is called (flag on), **Then** the request is authorized by the untouched `require_roles` seam and `request.state.user` is populated.
3. **Given** a valid `reviewer` token, **When** a recruiter/admin-gated endpoint is called, **Then** the response is 403 from the existing role gate (seam behaviour unchanged).

---

### User Story 2 — Everyone else is rejected, with honest status codes (Priority: P1)

Sign-in with a non-`n-ix.com` account is blocked at the front door (blocking function). Defense in depth: even a token that somehow exists without the right hosted domain, with an unverified email, tampered signature, wrong audience/issuer, or expired lifetime is rejected by the backend with 401. A genuine `n-ix.com` identity that has no role in the mapping gets 403 with a body that says exactly what to do about it.

**Why this priority**: P1 — the failure mode of auth is a security incident; the reject paths are the feature.

**Independent Test**: Unit tests cover tampered / expired / wrong-domain / wrong-audience / wrong-issuer / unverified-email / unknown-key tokens (401 mapping) and the missing-role claim (403 mapping).

**Acceptance Scenarios**:

1. **Given** a token whose payload was modified after signing, **When** presented, **Then** verification fails and the API returns 401.
2. **Given** an expired token, **When** presented, **Then** 401.
3. **Given** a token with `hd` ≠ `n-ix.com` (or missing, or an email outside the domain), **When** presented, **Then** 401.
4. **Given** a valid `n-ix.com` token with no `role` claim, **When** presented, **Then** 403 with a body pointing at `configs/auth-roles.yaml`.
5. **Given** no `Authorization` header at all, **When** an authenticated endpoint is called, **Then** 401 with `WWW-Authenticate: Bearer`.

---

### User Story 3 — Operator enables SSO per environment; local dev never notices (Priority: P2)

The seam ships dark (§9): with `AUTH_MODE=disabled` (the default everywhere today) the backend behaves exactly as before T07 — every authenticated endpoint answers 401, tests override the dependency, no tokens or Google infrastructure are needed. The operator flips `AUTH_MODE=identity_platform` (plus `GCP_PROJECT`) on the dev Cloud Run service first, rehearses the runbook end-to-end, then flips prod.

**Why this priority**: P2 — dark-launch is what makes T07 mergeable before the console/runbook steps happen; the flip itself is an operator act, not code.

**Independent Test**: The full existing test suite passes with no auth environment configured; a settings unit test proves `AUTH_MODE=identity_platform` without `GCP_PROJECT` refuses to boot.

**Acceptance Scenarios**:

1. **Given** no auth configuration (CI, local dev), **When** the suite runs, **Then** all pre-T07 tests pass unchanged and authenticated endpoints return 401.
2. **Given** `AUTH_MODE=identity_platform` and no `GCP_PROJECT`, **When** the app boots, **Then** startup fails fast with a clear error.
3. **Given** the operator flips the env vars on one environment, **When** the other environment is inspected, **Then** it is unaffected (per-env Cloud Run env vars; single shared identity plane documented).

---

### User Story 4 — Role membership is configs-as-code (Priority: P2)

Who is an admin/recruiter/reviewer lives in `configs/auth-roles.yaml` in Git (§16). The blocking function reads a vendored copy of that file and injects the `role` (and `hd`) claims at sign-in. Changing a role is a PR + function redeploy; the change takes effect at the person's next sign-in. There is no second, hidden source of role truth.

**Why this priority**: P2 — this is the governance half; US1 works without it only in the sense that tokens could be hand-minted.

**Independent Test**: Unit tests on the mapping loader + decision logic, including a test that validates the committed `configs/auth-roles.yaml` itself.

**Acceptance Scenarios**:

1. **Given** an email present in the mapping, **When** the decision logic runs, **Then** the claims include that role and `hd`.
2. **Given** an `n-ix.com` email absent from the mapping, **When** the decision runs, **Then** sign-in is allowed but no `role` claim is injected (the backend answers 403 until the mapping is amended).
3. **Given** a non-`n-ix.com` or unverified email, **When** the decision runs, **Then** sign-in is blocked.

---

### Edge Cases

- **Single identity plane for two environments**: Identity Platform config is project-global — dev and prod share one GCIP user pool and one role mapping (consequence of ADR-023's single project). Accepted at MVP: per-environment *enforcement* is the per-service `AUTH_MODE` env var. Documented in ADR-024.
- **Google signing-key rotation**: the verifier caches the `securetoken` certs with a TTL and force-refreshes once when a token's `kid` is unknown; an unknown key after refresh is a 401, not a crash.
- **Blocking function unavailable**: Identity Platform fails sign-in when a registered blocking function is unreachable — fail-closed, no unauthorized tokens minted. (Operator runbook notes this as the observable symptom of a broken deploy.)
- **User signed in before their mapping row existed**: they hold a role-less token → 403 with an actionable body; next sign-in after the mapping lands picks up the claim.
- **`hd` claim honesty**: GCIP does not copy Google's `hd` claim into its own tokens; the blocking function injects it (and the backend additionally checks the email domain), so the middleware's `hd == n-ix.com` check is real, not aspirational.
- **Token revocation**: not implemented at MVP — tokens live ≤ 1 h; removing a role takes effect at next sign-in. Recorded in ADR-024 consequences.
- **No client secret anywhere in Git/state**: the Google provider's OAuth client is console-provisioned; Terraform deliberately does not manage `defaultSupportedIdpConfig` (its `client_secret` argument would be plaintext-recoverable in the GCS state object — same rejection as DB passwords in specs/018 R6).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The verified-claims contract `docs/contracts/id-token-claims.json` (JSON Schema for `iss`, `aud`, `sub`, `email`, `email_verified`, `hd`, `role`, `iat`, `exp`) MUST be committed in its own commit **before** any implementation (§14; implementation-plan Appendix A names this artifact).
- **FR-002**: Terraform (`infra/terraform/identity.tf`) MUST declare: the additionally required APIs (`identitytoolkit`, plus the Cloud Functions build path for the blocking function), the project-level `google_identity_platform_config` (email/phone/anonymous providers off, duplicate emails off, authorized domains = localhost + both frontend service URLs, blocking-function triggers registered only once the operator supplies the deployed URIs via tfvars), and a least-privilege runtime service account for the blocking function. **Authored only — never applied in this task.**
- **FR-003**: Every step Terraform cannot honestly manage MUST be a numbered operator runbook item in `quickstart.md`: OAuth consent screen (brand), enabling the Google provider in the console (auto-provisions the OAuth client — no secret ever enters Git/state), deploying the blocking function, pasting the trigger URIs into `terraform.tfvars`, flipping per-env Cloud Run env vars, and the live acceptance sweep.
- **FR-004**: The blocking function (`infra/functions/auth_claims/`) MUST gate sign-in on verified `@n-ix.com` emails and inject `role` (from `configs/auth-roles.yaml`) + `hd` claims; its decision logic MUST be pure and unit-tested in the repo suite; deployment is operator-run.
- **FR-005**: The backend MUST replace the T13 401 placeholder in `app/backend/api/deps.py` with real verification: RS256 signature against Google's published `securetoken` certs, `iss`/`aud`/`exp`/`iat` checks, `email_verified` + `hd`/email-domain enforcement, `request.state.user = {sub, email, role}`, and the **exact same** `Principal`/`require_roles` seam so position-template endpoints and their tests keep working.
- **FR-006**: Reject mapping MUST be: missing/invalid/expired/tampered/wrong-domain token → **401** (with `WWW-Authenticate: Bearer`); valid identity without a staff `role` claim → **403** with a body naming `configs/auth-roles.yaml`.
- **FR-007**: The feature MUST ship dark (§9) behind `AUTH_MODE` (env var, default `disabled` = pre-T07 posture); the mechanism choice (env var, not a DB feature flag) MUST be justified in research.md; no new feature-flag registry entry is created.
- **FR-008**: Unit tests MUST cover three role fixtures (admin/recruiter/reviewer) plus tampered, expired, wrong-domain, wrong-audience, wrong-issuer, unverified-email, unknown-key and missing-role tokens; the full backend suite and `pre-commit` MUST stay green.
- **FR-009**: `app/backend/openapi.yaml` MUST be regenerated (bearer security scheme appears) and the regen-drift check MUST pass; new non-secret env keys (`AUTH_MODE`, `AUTH_ALLOWED_DOMAIN`) MUST be added to `.env.example` per ADR-022. No new Secret Manager shells are needed (the backend verifies tokens offline; the OAuth client secret is Google-console-held).
- **FR-010**: Governance MUST ship in the same PR: `adr/024` (Identity Platform for internal SSO; role claims from configs-as-code) amending ADR-016's internal-user path, the `adr/README.md` index row, an Appendix-C-compliant correcting note on implementation-plan T07 ("Workspace groups" → configs-as-code with upgrade path), and the `docs/engineering/cloud-setup.md` inventory/IAM update.

### Key Entities

- **ID-token claims contract** (`docs/contracts/id-token-claims.json`): the JSON Schema for what the backend consumes after verification — the Appendix A artifact that unblocks Tier-1 parallel work.
- **Identity Platform config** (project-global): Google provider only, `n-ix.com` gated via blocking function; shared by both environments.
- **Auth-claims blocking function** (`infra/functions/auth_claims/`): domain gate + claim injection; reads the vendored role mapping at cold start.
- **Role mapping** (`configs/auth-roles.yaml`): §16 source of truth — `domain` + `email → role` map.
- **Verifier + seam** (`app/backend/services/auth.py`, `app/backend/api/deps.py`): `IdTokenVerifier` (offline JWT verification, certs cache) behind `get_current_user`; `AUTH_MODE` decides whether a verifier exists.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The backend test suite passes with **zero** changes to existing test expectations; the new verifier tests include the three role fixtures and all negative paths from FR-008.
- **SC-002**: With `AUTH_MODE` unset, observable API behaviour is identical to pre-T07: every authenticated endpoint answers 401; `/health` and rubric reads stay open.
- **SC-003**: `python -m app.backend.generate_openapi --check` reports no drift after regeneration, and the committed spec contains the bearer security scheme.
- **SC-004**: `terraform validate` and `pre-commit run` on all touched files pass; the diff contains **zero** credential-shaped strings (no OAuth client secret, no key material).
- **SC-005** *(operator, post-merge)*: Signing in with an `@n-ix.com` account on dev yields a token whose `role` claim matches `configs/auth-roles.yaml`; the curl matrix (valid role → 200 on a flag-enabled gated endpoint, no/bad token → 401, role-less token → 403) passes against dev.
- **SC-006** *(operator, post-merge)*: A non-`@n-ix.com` Google account cannot complete sign-in (blocked by the function).
- **SC-007**: `configs/auth-roles.yaml` is the only role source in the repo — `git grep` shows no other role assignment mechanism (no `user_role` table, no hardcoded emails in backend code).

## Assumptions

- **Identity Platform over bare Workspace OAuth** per the 2026-07-05 clarification; ADR-024 records it (FR-010). GCIP free tier (< 50 MAU) keeps ADR-016's "no bill" consequence true at MVP volume.
- The N-iX Google Workspace organisation exists and `n-ix.com` accounts can consent to an **Internal** OAuth app in project `tech-screen-493720`; the operator has console access.
- **No live GCP mutation happens in this task**: Cloud SQL instances may be stopped (cost-idle); Terraform is authored and validated only; all applies, deploys, console steps and smoke tests are operator runbook items (quickstart.md), same honesty boundary as specs/018.
- Both environments share the single project's Identity Platform (ADR-023); per-env enforcement is the `AUTH_MODE` env var on each Cloud Run service.
- Sequential execution, `infra-engineer` (contract, HCL, function, runbook) then `backend-engineer` (middleware, tests) — contract-first inside the task per §14; one PR.

## Out of scope

- Frontend sign-in UI (Firebase JS SDK wiring, session handling) — later task; the quickstart carries a minimal token-mint snippet for smoke only.
- Candidate magic-link auth (ADR-016's other half) — untouched, later task.
- Staff `user` table + `Principal.user_id` wiring — `user_id` stays `None` until the task that owns the user aggregate.
- Workspace Groups API automation (domain-wide delegation) — documented upgrade path in ADR-024, not built.
- Session cookies for internal users (`SESSION_COOKIE_SECRET` shell stays reserved), token revocation, refresh handling.
- `/deploy` env-var plumbing changes — the operator flips env vars with `gcloud run services update` until T06a's tooling grows config support.

## Plan-phase research items (handled in `research.md`)

- ADR-016 ↔ implementation-plan conflict reconciliation shape (R1).
- Role-claims mechanism: blocking function + configs vs Workspace Groups API vs Admin-SDK persistent claims (R2).
- Exactly which Identity Platform pieces Terraform can manage vs console/manual, incl. the client-secret-in-state problem (R3).
- `hd` claim propagation honesty (R4).
- JWT verification library already compatible with the repo's dependency closure (R5).
- Dark-launch seam mechanism: env var vs feature flag (R6).
- Blocking-function runtime and SDK (R7).
- Single-project identity plane consequences (R8).
