# Quickstart — T07 operator runbook + acceptance sweep

Audience: the operator (Ihor) taking the merged T07 artifacts live, and the reviewer verifying the branch without cloud access. Every command runs from the repo root on the operator's machine (gcloud authenticated as `ikovalov@n-ix.com`, ADC pre-flight per `cloud-setup.md` § Operator pre-flight).

> ⚠️ **Nothing in this runbook was executed during T07 implementation** — the task authored + validated only (same honesty boundary as specs/018). Apply **only from this branch's checkout** (shared GCS state — `cloud-setup.md` § How to apply a change).

> 💰 **Cost-idle note**: the Cloud SQL instances may be stopped. Steps 1–8 need no database. Step 9's role-gated smoke needs the dev DB (flag row) — start `techscreen-pg-dev` first, stop it after.

## 1. Workspace prerequisite + OAuth consent screen (console, one-time)

1. Verify project `tech-screen-493720` belongs to the N-iX Google Workspace organisation (Cloud Console → IAM & Admin → Settings → Organization). The **Internal** consent type below requires it.
2. Console → **APIs & Services → OAuth consent screen**: User type **Internal**, app name `TechScreen`, support + developer contact = `ikovalov@n-ix.com`. No scopes beyond the defaults (`email`, `profile`, `openid`). Save.

*(No Terraform surface exists for the general consent screen — research R3.)*

## 2. First Terraform apply — APIs, Identity Platform config, function SA

```bash
export GOOGLE_BILLING_PROJECT=tech-screen-493720 USER_PROJECT_OVERRIDE=true
terraform -chdir=infra/terraform plan    # paste summary into the PR
terraform -chdir=infra/terraform apply
```

Expected new resources: 3 API services (`identitytoolkit`, `cloudfunctions`, `cloudbuild`), `google_identity_platform_config` (no blocking triggers yet — the URI tfvars are empty), `techscreen-auth-claims@` SA + logWriter binding.

**Known fallback**: if the config create fails with an "Identity Platform not enabled" style error, enable it once via Console → **Identity Platform → Enable** (Marketplace page), then re-run `apply` — the resource adopts. (Provider ≥ 4.49 normally initializes it directly — research R3.)

## 3. Enable the Google provider (console — deliberately not Terraform)

Console → **Identity Platform → Providers → Add a provider → Google** → Enable.

> **Amended 2026-07-06 (live finding):** the console does NOT auto-provision the OAuth client — it requires a **Web client ID + secret**. Create them first under **APIs & Services → Credentials → OAuth client ID** (Web application; JS origins = both frontend run.app URLs + http://localhost:3000; redirect URI = `https://tech-screen-493720.firebaseapp.com/__/auth/handler`; consent screen Internal must exist), then paste both into the provider form. The secret lives only in Google's console/GCIP config — never in Git or Terraform state (that §5 property survives; R3's "no pasting" claim was wrong).

While here: **Settings → Authorized domains** should already show `localhost` + both frontend `run.app` hosts (Terraform-managed — do not hand-edit).

## 4. Deploy the auth-claims blocking function (gen2, per event type)

```bash
cp configs/auth-roles.yaml infra/functions/auth_claims/auth-roles.yaml   # vendored copy (gitignored)

for fn in before-created:before_created before-signed-in:before_signed_in; do
  name="techscreen-auth-claims-${fn%%:*}"; entry="${fn##*:}"
  gcloud functions deploy "$name" \
    --gen2 --region=europe-west1 --runtime=python312 \
    --source=infra/functions/auth_claims --entry-point="$entry" \
    --trigger-http --allow-unauthenticated \
    --service-account="techscreen-auth-claims@tech-screen-493720.iam.gserviceaccount.com" \
    --max-instances=3 --memory=256Mi
done
gcloud functions describe techscreen-auth-claims-before-created  --gen2 --region=europe-west1 --format='value(serviceConfig.uri)'
gcloud functions describe techscreen-auth-claims-before-signed-in --gen2 --region=europe-west1 --format='value(serviceConfig.uri)'
```

Notes: `--allow-unauthenticated` is correct — Identity Platform calls the endpoint with a **GCIP-signed JWT payload** which the `firebase-functions` SDK verifies; unauthenticated garbage is rejected in-handler (research R7). `firebase deploy --only functions` is the equivalent alternative if a `firebase.json` is ever added.

## 5. Register the blocking triggers (second apply)

1. Paste the two URIs from step 4 into `infra/terraform/terraform.tfvars` (`auth_before_create_uri`, `auth_before_sign_in_uri`) — non-secret `run.app` URLs, committed in a follow-up PR.
2. `terraform -chdir=infra/terraform apply` — the `blocking_functions` block lands. From this apply on, **all** sign-ins (both envs — shared plane, R8) pass through the domain gate.

## 6. Sign-in smoke — mint a real token (dev rehearsal)

The frontend sign-in UI is a later task; smoke with a throwaway local page (Firebase JS SDK, web API key from Console → Identity Platform → Application setup details — the API key is a non-secret identifier):

```html
<script type="module">
  import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-app.js";
  import { getAuth, GoogleAuthProvider, signInWithPopup } from "https://www.gstatic.com/firebasejs/10.12.0/firebase-auth.js";
  const app = initializeApp({ apiKey: "<web-api-key>", authDomain: "tech-screen-493720.firebaseapp.com" });
  signInWithPopup(getAuth(app), new GoogleAuthProvider())
    .then(async (r) => console.log(await r.user.getIdToken()));
</script>
```

Serve from `http://localhost` (authorized domain), sign in with an `@n-ix.com` account, copy the printed token. **Expected**: sign-in with a personal `@gmail.com` account **fails** (blocking function) → SC-006. Decode the staff token payload (`jwt.io` or `python -c ...`) → `role` matches `configs/auth-roles.yaml`, `hd == n-ix.com` → SC-005 first half.

## 7. Flip dev

```bash
gcloud run services update techscreen-backend-dev --region=europe-west1 \
  --update-env-vars=AUTH_MODE=identity_platform,GCP_PROJECT=tech-screen-493720,AUTH_ALLOWED_DOMAIN=n-ix.com
```

## 8. API smoke against dev (no DB needed)

```bash
URL=$(gcloud run services describe techscreen-backend-dev --region=europe-west1 --format='value(status.url)')
curl -s -o /dev/null -w '%{http_code}\n' "$URL/position-templates"                       # expect 404 (flag off — checked before auth)
curl -s -o /dev/null -w '%{http_code}\n' "$URL/health"                                    # expect 200 (unauthenticated liveness)
```

## 9. Role-gated smoke (needs dev DB awake + flag row on)

1. Start `techscreen-pg-dev`; flip `position_template_crud_enabled` in the dev DB (see `docs/engineering/feature-flags.md` § Emergency disable, inverted).
2. Matrix (record in the PR):

| Request | Expected |
| --- | --- |
| `curl "$URL/position-templates"` (no token) | **401**, `WWW-Authenticate: Bearer` |
| `curl -H "Authorization: Bearer garbage"` | **401** |
| valid token, email **not** in `configs/auth-roles.yaml` | **403**, body names `configs/auth-roles.yaml` |
| valid `recruiter`/`admin` token | **200** |
| valid `reviewer` token | **403** (role gate — seam unchanged) |

3. Flip the flag row back off; stop `techscreen-pg-dev`.

## 10. Flip prod (after the dev rehearsal)

Same `gcloud run services update` against `techscreen-backend` (no `-dev`). Dev is **not** a release gate (§8) — this is a rehearsal, and the prod flip is its own deliberate act. Rollback at any point: `--update-env-vars=AUTH_MODE=disabled` (returns to the pre-T07 401-dark posture in one revision, no code change).

## 11. Acceptance sweep summary

| # | Check | Where | Pass condition |
| --- | --- | --- | --- |
| SC-001 | suite green, verifier tests present | CI / branch | `uv run pytest` all green |
| SC-002 | dark by default | CI / branch | no auth env ⇒ authenticated endpoints 401; `/health` 200 |
| SC-003 | openapi regen | CI / branch | `python -m app.backend.generate_openapi --check` clean; bearer scheme present |
| SC-004 | HCL + hooks | branch | `terraform validate` + `pre-commit run` green; zero credential-shaped strings |
| SC-005 | live role claim + curl matrix | steps 6–9 | token `role` matches YAML; 200/401/403 matrix as tabled |
| SC-006 | non-domain blocked | step 6 | `@gmail.com` sign-in fails at the blocking function |
| SC-007 | single role source | branch | `git grep` shows no role mechanism besides `configs/auth-roles.yaml` |

## 12. Reviewer walkthrough (no cloud access needed)

1. `docs/contracts/id-token-claims.json` committed **before** implementation commits (git log order — §14).
2. `pre-commit run --all-files` green (gitleaks, terraform_validate, feature-flag hook untouched).
3. `identity.tf`: no `google_identity_platform_default_supported_idp_config`, no client-secret-shaped variables (§5, research R3); triggers gated on tfvars.
4. `deps.py` diff: `Principal`/`require_roles` call surface unchanged; 401/403 mapping per data-model.md.
5. Verifier tests: three role fixtures + tampered/expired/wrong-domain/wrong-aud/wrong-iss/unverified/unknown-key/missing-role; **no committed PEM/key material** anywhere in the diff.
6. ADR-024 content vs research R1/R2/R8; ADR-016 amendment appended (not edited in place); README index row.
