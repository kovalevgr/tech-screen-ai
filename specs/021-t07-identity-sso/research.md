# Research — T07 Identity Platform SSO + role claims

**Date**: 2026-07-05 · **Feature**: [spec.md](./spec.md) · All spec plan-phase research items resolved below. **No live GCP calls were made** — items are resolved from provider documentation, the repo's own dependency closure (verified locally), and prior-task precedent; anything that can only be proven against the live project is an operator runbook step (quickstart.md) with the expected outcome stated.

## R1. ADR-016 conflict → Identity Platform (ADR-024)

- **Decision**: T07 builds **Identity Platform (GCIP)** with the Google provider, per the implementation plan's own T07 title/description. ADR-016's internal-user path (bare Workspace OAuth + `user_role` DB table + "No Identity Platform bill") is amended by **ADR-024**; the candidate magic-link half of ADR-016 is untouched.
- **Rationale**: the two documents were written in the same authorship window and never reconciled (same pattern ADR-023 resolved for topology). GCIP wins on engineering grounds: managed token issuance/refresh, a stable offline-verifiable JWT surface (`securetoken.google.com` certs), first-class custom claims (the mechanism T07's role requirement names), and a blocking-function hook for domain gating — versus hand-rolling an OAuth code flow, session store, and CSRF surface in the backend. The "no bill" consequence survives in practice: GCIP's free tier covers ~tens of staff MAU.
- **Alternatives considered**: bare Workspace OAuth per ADR-016 (rejected — more hand-written security-critical code, no token contract for the SPA-era frontend, contradicts the plan's T07 acceptance); keeping both docs unreconciled (rejected — §-level doc honesty, ADR-023 precedent).

## R2. Role-claims mechanism: blocking function + configs-as-code

- **Decision**: **(a) GCIP blocking function** (`beforeUserCreated` + `beforeUserSignedIn`) that reads a **vendored copy of `configs/auth-roles.yaml`** (§16 source of truth, `email → role` map + `domain`) and injects `role` + `hd` claims; unmapped domain users sign in role-less and the backend answers 403 with an actionable body.
- **Rationale**: of the two options the implementation plan implies — (a) function + committed mapping vs **(b) Workspace Groups API with domain-wide delegation** — (a) is materially simpler and §16-native: (b) needs a Workspace super-admin to grant domain-wide delegation to a service account, broad `admin.directory.group.readonly` scopes, Directory API quota/error handling inside the sign-in path, and group-name↔role convention management — heavy machinery for three roles and ≤ ~10 staff at MVP. ADR-016 itself said "not via Workspace groups at MVP". Git gives the audit trail §16 wants; a role change is a reviewable PR.
- **Also considered — (c) persistent custom claims via Admin SDK** (operator CLI sets claims, no deployed function): fewer moving parts but rejected: claims persist stale on the user record (revoking a role requires another out-of-band operator act, easy to forget), there is no sign-in-time domain gate (non-N-iX accounts would accumulate in the user pool), and it adds an operator tool with elevated Admin SDK credentials — the blocking function re-derives claims at **every** sign-in from the deployed mapping and fails closed.
- **Upgrade path (documented in ADR-024)**: swap `roles.load_mapping()` for a Directory API `members.hasMember` lookup when Workspace group management becomes real; the claim surface (`role` in the ID token, backend contract `docs/contracts/id-token-claims.json`) does not change, so the backend is untouched by the upgrade.

## R3. What Terraform can honestly manage vs console/manual

- **Terraform-managed** (`infra/terraform/identity.tf`):
  - `google_project_service` for `identitytoolkit.googleapis.com` + the function build path (`cloudfunctions`, `cloudbuild`; `run`/`artifactregistry` already enabled by T06).
  - `google_identity_platform_config` — on providers ≥ 4.49 creating this resource calls `initializeAuth`, i.e. it can *activate* Identity Platform on the project. Caveat recorded honestly: if the live API still demands the one-time Marketplace/console enablement, the apply fails with a clear error and quickstart step 2 names the console fallback; the resource then adopts on re-apply.
  - Authorized domains (`localhost` + both frontend `*.run.app` hosts from the T06 module outputs), provider posture (email/phone/anonymous **off**, duplicate emails off), and the blocking-function triggers — the latter behind two root variables (`auth_before_create_uri`, `auth_before_sign_in_uri`, default `""`) so the config applies cleanly *before* the function exists and registers the triggers on a second apply once the operator pastes the deployed URIs into `terraform.tfvars`.
  - A least-privilege runtime SA for the function (`techscreen-auth-claims@`, `roles/logging.logWriter` only).
- **Console/manual (operator runbook, quickstart.md)**:
  - **OAuth consent screen (brand)** — no honest Terraform surface: `google_iap_brand` only creates *internal-type* IAP brands and cannot manage the general consent screen; runbook step.
  - **Google provider enablement** — deliberately **not** `google_identity_platform_default_supported_idp_config`: that resource requires `client_id`/`client_secret` literals which land plaintext-recoverable in the GCS state object — rejected for exactly the reason specs/018 R6 rejected `google_sql_user.password` (constitution §5: the cheapest prevention is absence). Enabling the provider in the console instead **auto-provisions the OAuth client** inside Google's infrastructure, so no secret ever exists in Git, state, or the operator's shell. Note: the Terraform resource has **no hosted-domain restriction field anyway** — `hd`-gating never was a provider-config capability; it lives in the blocking function + backend check (R4).
  - **Workspace prerequisite** — the consent screen's **Internal** user type requires the project to belong to the N-iX Workspace organisation; verified by the operator in step 1.
  - **Function deployment** — `gcloud functions deploy` (gen2) from `infra/functions/auth_claims/` with the vendored mapping copy; Terraform never deploys code (same image-ownership philosophy as T06's `ignore_changes` handoff to `/deploy`).

## R4. `hd` claim honesty

- **Finding**: GCIP mints its **own** ID token and does *not* copy Google's `hd` claim from the upstream IdP token. A backend `hd == n-ix.com` check against a raw GCIP token would therefore always fail.
- **Decision**: the blocking function **injects** `hd` (alongside `role`) for accounts it admits, deriving the domain from the verified email; `forward_inbound_credentials` stays fully off (no upstream tokens flow to our function — §5-friendly). The backend enforces `hd == AUTH_ALLOWED_DOMAIN` **and** independently checks the email suffix, so domain enforcement holds even if a claim-injection regression ships.

## R5. JWT verification library: `google-auth`

- **Decision**: **`google-auth`** (`google.auth.jwt.decode` + the published `securetoken@system.gserviceaccount.com` X.509 certs). Declared explicitly in `pyproject.toml` (`google-auth>=2.45,<3`) — it is *already in the runtime closure* as a base dependency of `google-genai`/`google-api-core` (2.49.2 installed), ships `py.typed` (mypy --strict clean, no override needed), and its RS256 backend is `cryptography` (a base dependency of google-auth ≥ 2.42, present at 47.0.0). Zero genuinely new packages.
- **Certs transport**: fetched with stdlib `urllib` wrapped in `asyncio.to_thread` (conventions: sync work off the event loop) — avoids promoting `requests`/`httpx` to declared runtime deps for one rare fetch. In-process TTL cache (1 h) + one forced refresh when a token presents an unknown `kid` (Google key rotation).
- **Alternatives considered**: `PyJWT[crypto]` + `PyJWKClient` (fine library, but a genuinely new dependency and the `securetoken` endpoint publishes X.509 PEMs, not JWKS — extra conversion); `python-jose` (maintenance state disqualifies it for an auth path); `firebase-admin` (heavyweight SDK whose `verify_id_token` wants Admin credentials for revocation checks we don't do at MVP).
- **Test strategy**: tokens minted locally with a throwaway 2048-bit RSA key (`cryptography` keygen, `google.auth.crypt.RSASigner`), certs injected via the verifier's `certs_fetcher` seam — **no network, no committed key material** (a committed test PEM would trip `detect-private-key`/gitleaks by design).

## R6. Dark-launch seam: env var, not a feature flag

- **Decision**: `AUTH_MODE` env var on `Settings` (`disabled` | `identity_platform`, default `disabled`), mirroring the `LLM_BACKEND` precedent. `disabled` keeps the exact pre-T07 posture: no verifier installed, every authenticated endpoint 401, tests override `get_current_user` as before.
- **Why not a `feature_flag` row (§9's default mechanism)**: (1) **bootstrap** — the flag service exists only when `DATABASE_URL` is configured and the DB is reachable; auth posture must be decidable without a database (and the cloud instances sit stopped in cost-idle). (2) **trust boundary** — the flag table is writable by the flag-sync CI identity and by emergency operator SQL; letting a DB write flip authentication on/off would hand auth-posture control to identities that must not hold it. (3) **coupled config** — enabling auth requires `GCP_PROJECT` (audience) at boot anyway, so the enable act is inherently an env/deploy-level change; a flag would add a second switch that can contradict the first. §9's *intent* (risky feature ships off-by-default, flip is deliberate and reversible per environment) is fully met; the justification lives here per FR-007, and no registry entry is added (the bidirectional hook stays untouched).
- **Boot guard**: `Settings.assert_safe_for_environment` refuses `AUTH_MODE=identity_platform` with an empty `GCP_PROJECT` — fail-fast in Cloud Run logs, same pattern as FR-007/T04.

## R7. Blocking-function runtime: Python `firebase-functions` SDK

- **Decision**: Python 3.12 Cloud Function (gen2) using the **`firebase-functions`** SDK (`identity_fn.before_user_created` / `before_user_signed_in`) under `infra/functions/auth_claims/`, with the decision logic isolated in a pure module (`roles.py`) that the repo's pytest suite tests directly (no SDK import needed at test time; the SDK is a function-only dependency in its `requirements.txt`).
- **Rationale**: keeps the repo single-language (coding-conventions: Python 3.12 backend); the SDK implements the blocking-function wire protocol (the request is itself a GCIP-signed JWT that must be verified — hand-rolling that in `functions-framework` would be new security-critical code, the exact thing to avoid in an auth path). Node's `firebase-functions` is the more-travelled path but buys nothing here worth a second toolchain.
- **Failure semantics**: if the function is unreachable or errors, Identity Platform **fails the sign-in** — fail-closed. A cold-start mapping-load failure (missing vendored YAML) raises at import, which surfaces as failed sign-ins + function error logs, not as silent allow.

## R8. Single identity plane across dev and prod

- **Finding**: `google_identity_platform_config` is a **project-global singleton** — with ADR-023's both-envs-in-one-project topology, dev and prod share one user pool, one provider config, one blocking function, one role mapping. (GCIP multi-tenancy could split them, but per-tenant providers/functions roughly double the operator surface for zero MVP benefit — staff identities are *supposed* to be the same people in both environments.)
- **Decision**: accept the shared plane at MVP; per-environment *enforcement* is each Cloud Run service's `AUTH_MODE`/`GCP_PROJECT` env vars (dev flips first, prod after the rehearsal — ADR-023's stated purpose for dev). Recorded in ADR-024 consequences; revisit with tenants if candidate-facing auth ever moves onto GCIP (it should not — ADR-016 magic links).

## R9. What T07 explicitly does not decide

- Frontend sign-in UI + client-side session handling — later frontend task (quickstart carries a smoke-only token snippet).
- Staff `user` table and `Principal.user_id` population — the task that owns the user aggregate; `user_id` stays `None`.
- Candidate magic-link path (ADR-016), `SESSION_COOKIE_SECRET` consumption, token revocation, Workspace-groups automation (R2 upgrade path).
- `/deploy` growing env-var management — operator uses `gcloud run services update` until T06a tooling extends.
