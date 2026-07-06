# Contract pointer — T07

Per the implementation plan (Appendix A), T07's `contract:` is **`docs/contracts/id-token-claims.json`** — the JSON Schema for the verified ID-token claims the backend consumes. It is committed **in its own commit, before any implementation** (§14), and blocks Tier-1 parallel work per the Appendix A rule.

Committed artefacts downstream tasks bind to:

1. **`docs/contracts/id-token-claims.json`** — claim names, types, and the staff-role enum. Consumers: the frontend sign-in task (sends the token this schema describes), T21 (`turn_trace`/audit actor identity from `request.state.user`), any future endpoint using `require_roles`.
2. **`app/backend/api/deps.py` seam** — `Principal{user_id, role, sub, email}` + `require_roles(*roles)` + `get_current_user`; unchanged call surface from T13, now backed by real verification. Consumers: every authenticated router; tests override `get_current_user` exactly as before.
3. **`configs/auth-roles.yaml`** — the §16 role-membership contract (validated by `infra/functions/auth_claims/roles.py` + repo unit test). Consumer: the auth-claims blocking function (vendored copy at deploy).
4. **`infra/terraform/identity.tf` variables** (`auth_before_create_uri`, `auth_before_sign_in_uri`) — the handoff point between the operator's function deploy and Terraform's trigger registration.

OpenAPI surface change: `app/backend/openapi.yaml` regenerated — bearer security scheme (`IdentityPlatformBearer`) appears on role-gated operations; regen-diff check stays green.
