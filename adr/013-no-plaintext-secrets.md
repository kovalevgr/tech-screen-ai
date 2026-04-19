# ADR-013: No plaintext secrets — Secret Manager + WIF

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen handles:

- Vertex AI credentials (access to an expensive LLM API).
- Database passwords (access to all candidate PII).
- OAuth client secrets (access to internal user accounts).
- Session signing keys (ability to forge session tokens).
- Email provider API keys (ability to impersonate the product to candidates).

A leak of any of these is at minimum an embarrassment, at worst a GDPR incident. The cheapest way to prevent leaks is to ensure secrets never live where they could be leaked.

## Decision

### Storage

- **Production:** Google Secret Manager. Each secret is a named entry with versioning. Cloud Run services receive secrets at runtime via `--set-secrets=NAME=secret-id:latest`.
- **Local dev:** `.env` files, excluded from git via `.gitignore`. `.env.example` contains the list of required keys with empty or placeholder values.
- **Configs-as-code:** non-secret configs live in `configs/*.yaml` (ADR-021).

### Authentication (secrets' replacement for CI)

- **GitHub Actions → GCP:** Workload Identity Federation (OIDC). No JSON service-account keys are created for any service account.
- **Local developer → GCP:** `gcloud auth application-default login` using the engineer's own Google Workspace account.

### Enforcement

- `pre-commit` hook runs `gitleaks` and `detect-secrets`.
- CI blocks any PR containing a string matching the secrets regex allow-list.
- `gcloud iam service-accounts keys create` is project-policy-forbidden at the org level (requested from N-iX platform team as part of onboarding).
- Log formatters strip known secret-shaped fields (`password`, `api_key`, `token`, `secret`, `bearer`).

## Consequences

**Positive.**

- Zero long-lived credentials anywhere that can be committed, leaked, or improperly rotated.
- WIF provides short-lived, per-run, auditable tokens for CI.
- Alignment with constitution §5 and §6 (these ADRs ratify those principles).

**Negative.**

- WIF setup is non-obvious and requires a first-time bootstrap script (`infra/bootstrap.sh`).
- Local developers need gcloud set up; curl-style scripts that hard-code a key will not work.

**Mitigation.**

- `infra/bootstrap.sh` is documented and idempotent.
- Onboarding doc explains gcloud setup in < 5 steps.
