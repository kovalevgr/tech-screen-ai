# Data model — T07 Identity Platform SSO + role claims

Auth feature: the "entities" are token claims, decision outcomes, runtime config, and cloud resources. Application tables are untouched (no migrations; `Principal.user_id` stays `None` until the user-aggregate task).

## Verified ID-token claims (`docs/contracts/id-token-claims.json`)

The subset of GCIP ID-token claims the backend consumes **after** signature verification. `additionalProperties: true` — GCIP adds `auth_time`, `firebase`, `user_id` etc.; the backend ignores them.

| Claim | Type | Producer | Backend enforcement (`IdTokenVerifier`) |
| --- | --- | --- | --- |
| `iss` | string | GCIP | `== https://securetoken.google.com/<GCP_PROJECT>` |
| `aud` | string | GCIP | `== <GCP_PROJECT>` (checked by `google.auth.jwt.decode`) |
| `sub` | string | GCIP (stable uid) | non-empty; becomes `request.state.user["sub"]` |
| `email` | string (email) | Google IdP → GCIP | present **and** ends with `@<AUTH_ALLOWED_DOMAIN>` (defense in depth vs `hd`) |
| `email_verified` | boolean | Google IdP → GCIP | `is True` — anything else rejects |
| `hd` | string (hostname) | **auth-claims blocking function** (GCIP does not copy Google's `hd` — research R4) | `== AUTH_ALLOWED_DOMAIN` (`n-ix.com` at MVP) |
| `role` | `"admin" \| "recruiter" \| "reviewer"` | **auth-claims blocking function** from `configs/auth-roles.yaml` | membership in the staff enum; **absent/unknown → 403**, not 401 |
| `iat` | integer (unix s) | GCIP | not in the future (checked by `google.auth.jwt.decode`) |
| `exp` | integer (unix s) | GCIP (≤ 1 h) | not in the past (checked by `google.auth.jwt.decode`) |
| *(signature)* | RS256, `kid` header | GCIP signing keys | verified against `securetoken@system.gserviceaccount.com` X.509 certs; TTL-cached, refreshed once on unknown `kid` |

## Exception → HTTP mapping (`app/backend/api/deps.py`)

| Condition | Raised by | HTTP | Body / headers |
| --- | --- | --- | --- |
| `AUTH_MODE=disabled` (no verifier installed) | `get_current_user` | 401 | pre-T07 dark posture; detail names the seam |
| No / non-Bearer `Authorization` header | `get_current_user` | 401 | `WWW-Authenticate: Bearer` |
| Signature / `iss` / `aud` / `exp` / `iat` / domain / `email_verified` failure | `TokenVerificationError` | 401 | generic detail (no claim echo — §15), `WWW-Authenticate: Bearer` |
| Valid identity, `role` claim absent or not a staff role | `MissingRoleClaimError` | 403 | actionable body naming `configs/auth-roles.yaml` |
| Valid staff token, role not in the endpoint's allow-list | existing `require_roles` | 403 | unchanged (seam untouched) |

## Runtime settings (`app/backend/settings.py`, env-loaded — ADR-022 non-secret)

| Field | Env var | Default | Notes |
| --- | --- | --- | --- |
| `auth_mode` | `AUTH_MODE` | `"disabled"` | `"disabled" \| "identity_platform"` — the §9 seam (research R6) |
| `gcp_project` | `GCP_PROJECT` | `""` | ID-token audience + issuer suffix; **required when enabled** (boot guard) |
| `auth_allowed_domain` | `AUTH_ALLOWED_DOMAIN` | `"n-ix.com"` | hosted-domain + email-suffix enforcement |

Boot guard: `assert_safe_for_environment` raises `RuntimeError` on `identity_platform` + empty `gcp_project` (any env — fail fast in Cloud Run logs).

Lifespan wiring (`main.py`): `auth_mode == "identity_platform"` → construct `IdTokenVerifier(project_id, allowed_domain)` and `set_verifier(...)`; teardown resets to `None`. Tests install stub verifiers via the same registry (mirrors the `feature_flags.set_service` pattern).

## Role mapping (`configs/auth-roles.yaml` — §16 source of truth)

```yaml
domain: n-ix.com          # verified-email domain admitted at sign-in
roles:                    # lower-cased email → staff role
  ikovalov@n-ix.com: admin
```

Validation lives in `infra/functions/auth_claims/roles.py` (`load_mapping`): mapping shape, non-empty domain, email keys contain `@`, role values ∈ {admin, recruiter, reviewer}. A repo unit test loads the **committed** file, so an invalid mapping cannot merge. The function reads a **vendored copy** (`infra/functions/auth_claims/auth-roles.yaml`, gitignored) placed by the deploy runbook step.

## Blocking-function decision table (`roles.decide`)

| Input | Outcome |
| --- | --- |
| Email missing / not verified | **block** (`beforeUserCreated` + `beforeUserSignedIn` raise permission-denied) |
| Email domain ≠ `domain` | **block** |
| Domain email, present in `roles` | allow; claims `{hd: <domain>, role: <mapped>}` |
| Domain email, absent from `roles` | allow; claims `{hd: <domain>}` — backend answers 403 until mapped |

Claims are injected as `custom_claims` at `beforeUserCreated` and re-derived as `session_claims` at every `beforeUserSignedIn` — role edits take effect at next sign-in, no persistent stale claims (research R2).

## Cloud resources (`infra/terraform/identity.tf` — authored, operator-applied)

| Resource | Name / value | Key attributes |
| --- | --- | --- |
| `google_project_service` × 3 | `identitytoolkit`, `cloudfunctions`, `cloudbuild` | `disable_on_destroy = false` |
| `google_identity_platform_config` | project singleton (**shared dev+prod** — R8) | email/phone/anonymous off; `allow_duplicate_emails = false`; `authorized_domains` = localhost + both frontend run.app hosts (module outputs); `blocking_functions` triggers only when tfvars URIs non-empty; `forward_inbound_credentials` all false |
| `google_service_account` | `techscreen-auth-claims@` | function runtime identity |
| `google_project_iam_member` | `roles/logging.logWriter` on the SA | least privilege — the function needs nothing else |
| Root variables | `auth_before_create_uri`, `auth_before_sign_in_uri` (default `""`) | filled in `terraform.tfvars` after the operator deploys the function; second apply registers the triggers |

**Console-managed (not resources — research R3)**: OAuth consent screen (brand), Google provider enablement (auto-provisioned OAuth client; secret never in Git/state), the function deploy itself.

## State transitions (operator, quickstart.md)

1. **Merge**: everything dark; suite green; no cloud changes.
2. **Apply 1**: APIs + GCIP config (no triggers) + SA exist.
3. **Console**: consent screen + Google provider on.
4. **Deploy**: two function endpoints live; URIs → tfvars.
5. **Apply 2**: blocking triggers registered — domain gate + claims active at sign-in.
6. **Flip dev**: `AUTH_MODE=identity_platform` on `techscreen-backend-dev` → acceptance sweep.
7. **Flip prod**: same, after the dev rehearsal.
