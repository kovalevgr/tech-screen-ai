# ADR-024: Identity Platform for internal SSO; role claims from configs-as-code

- **Status:** Accepted
- **Date:** 2026-07-05
- **Amends:** [ADR-016](./016-auth-split-sso-magic-link.md) (internal-user path only; the candidate magic-link path is unchanged)

## Context

ADR-016 split auth into two paths and, for internal users, chose bare Google Workspace OAuth with roles in a `user_role` DB table — explicitly *not* Identity Platform ("No Identity Platform bill") and *not* Workspace groups at MVP. The implementation plan's T07 (same authorship window) says the opposite: "Identity Platform with Google provider constrained to `n-ix.com`. Custom claim `role ∈ {admin, recruiter, reviewer}` injected by a Cloud Function trigger; membership driven by Workspace groups." The two documents were never reconciled — the same pattern ADR-023 resolved for topology.

T07 forced the choice. Two sub-decisions were open: the SSO substrate (bare OAuth vs Identity Platform) and the role source (DB table vs Workspace groups vs committed config).

## Decision

**Internal staff sign in through Identity Platform (GCIP) with the Google provider; the `role` custom claim is minted at sign-in by a blocking function that reads `configs/auth-roles.yaml` — the §16 configs-as-code source of truth.**

- **Substrate**: GCIP issues RS256 ID tokens the backend verifies **offline** against Google's published `securetoken` certs (`docs/contracts/id-token-claims.json` is the claim contract). No hand-rolled OAuth code flow, no server-side session store; the internal-user "session" is the bearer ID token (≤ 1 h), refreshed by the client SDK. The signed-cookie plan from ADR-016 is dropped for internal users at MVP (the `SESSION_COOKIE_SECRET` shell stays reserved).
- **Domain gate**: the blocking function (`infra/functions/auth_claims/`, Python `firebase-functions`) rejects sign-ins whose verified email is not `@n-ix.com`, and injects `hd` + `role` claims for admitted accounts (GCIP does not propagate Google's `hd` claim itself). The provider config carries no domain restriction — none exists as an API surface; enforcement is function + backend middleware, fail-closed.
- **Role source**: `configs/auth-roles.yaml` (email → role) in Git. A role change is a PR + function redeploy, effective at the person's next sign-in. Not the `user_role` table (role would be outside the token, forcing a DB read per request and a second source of truth); not Workspace groups (Directory API + domain-wide delegation is heavy machinery for ≤ ~10 staff — ADR-016's own "not via Workspace groups at MVP" stands).
- **Dark launch**: the backend seam is the `AUTH_MODE` env var (default `disabled` — the pre-T07 401-everywhere posture), deliberately *not* a `feature_flag` row: auth posture must not depend on database availability, and must not be flippable by the flag-sync CI identity or emergency flag SQL (see `specs/021-t07-identity-sso/research.md` R6).

## Alternatives considered

- **Bare Workspace OAuth per ADR-016** — rejected: more hand-written security-critical code (code flow, CSRF, session store) and no stable token contract for the frontend; T07's acceptance criteria name Identity Platform.
- **Workspace Groups API with domain-wide delegation** — rejected at MVP; **this is the documented upgrade path**: swap the blocking function's mapping lookup for a Directory `members` check. The token contract and backend do not change, so the upgrade is contained in the function.
- **Persistent custom claims via an Admin-SDK operator CLI** (no deployed function) — rejected: claims go stale on the user record (revocation is a second manual act), there is no sign-in-time domain gate, and the CLI would wield Admin SDK credentials. The blocking function re-derives claims at every sign-in and fails closed.
- **Terraform-managed Google provider (`defaultSupportedIdpConfig`)** — rejected: it requires `client_id`/`client_secret` literals that land plaintext-recoverable in Terraform state (the exact reason specs/018 R6 kept DB passwords out of state; constitution §5). Console enablement auto-provisions the OAuth client so no secret ever exists in Git, state, or a shell.

## Consequences

**Positive.**

- Managed token issuance/refresh/signing; the backend's auth path is offline verification with zero per-request network and zero DB dependency.
- Roles are Git-auditable (§16) and carried in the token — `require_roles` needs no lookup.
- ADR-016's "no Identity Platform bill" survives in practice: the free tier (50k MAU) exceeds staff headcount by three orders of magnitude.

**Negative.**

- **One identity plane for two environments**: GCIP config is project-global, so dev and prod (ADR-023, single project) share the user pool, provider, blocking function, and role mapping. Accepted: staff are the same humans in both envs; per-env *enforcement* is each service's `AUTH_MODE`. Revisit with GCIP tenants only if a genuinely separate audience appears.
- **No token revocation at MVP**: removing a role takes effect at the next sign-in (tokens live ≤ 1 h). Acceptable for an internal tool; revisit before any external exposure.
- **Role changes need a function redeploy** (the mapping is vendored into the function). Cheap at MVP cadence; the Groups-API upgrade removes it.
- One more deployed artifact (the blocking function) whose availability gates sign-in — failure mode is fail-closed (sign-in errors), never silent admission.

## Measurements

| Item | ADR-016 plan | This ADR |
| --- | --- | --- |
| Auth substrate (internal) | hand-rolled Workspace OAuth + cookie | Identity Platform bearer ID tokens |
| Role source | `user_role` DB table | `configs/auth-roles.yaml` (§16) |
| Role in token | no (DB read per request) | yes (`role` claim) |
| Workspace groups | not at MVP | not at MVP (upgrade path) |
| GCIP cost | "no bill" (unused) | $0 (free tier at MVP volume) |
| Candidate magic links | unchanged | unchanged |
