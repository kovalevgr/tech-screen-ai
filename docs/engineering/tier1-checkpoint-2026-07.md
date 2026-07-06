# Tier-1 checkpoint (T11) — 2026-07-06

Gate record for `docs/engineering/implementation-plan.md` § T11. Executed live by the operator (Ihor) + orchestrator on 2026-07-06; sign-off = merging this PR (acceptance: "Ihor signs off with LGTM on the checkpoint PR").

## Checklist vs the T11 acceptance

| # | T11 item | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Local `docker compose up` → backend health 200 → admin shell 200 | ✅ **smoke PASSED** | `scripts/smoke-docker-stack.sh`: backend OK (attempt 2), frontend OK (attempt 2). One local-only pre-step: the `frontend-node-modules` named volume predated T14's dependency additions and had to be reset via the documented `docker compose down -v` path (docker.md § reset). CI runs volume-less and was green throughout. |
| 2 | Deploy to `dev` Cloud Run via `/deploy` | ✅ | Live pipeline runs: backend [28817604920](https://github.com/kovalevgr/tech-screen-ai/actions/runs/28817604920) + [28818039420](https://github.com/kovalevgr/tech-screen-ai/actions/runs/28818039420), promote-100 [28818210096](https://github.com/kovalevgr/tech-screen-ai/actions/runs/28818210096); frontend rehearsal incl. `/rollback` in 19 s (record on [PR #20](https://github.com/kovalevgr/tech-screen-ai/pull/20)). |
| 3 | Deployed backend health | ✅ | `https://techscreen-backend-dev-…/health` → `{"status":"ok","service":"techscreen-backend","version":"0.0.0"}`; frontend URL → 200. |
| 4 | §3 append-only trigger fires on a direct SQL attempt | ✅ | As `techscreen_app` on the dev instance: `UPDATE turn_trace …` → `permission denied for table turn_trace`; 6 `_no_mutation` triggers present (both instances verified 2026-07-03, dev re-verified today). |
| 5 | §9 seed flag `is_enabled=false` via the service | ✅ | `feature_flag` rows on dev: `example_demonstration=false`, `position_template_crud_enabled=false` — **and** the running service enforces it: `GET /position-templates` → 404 (flag-gated surface hidden), proving the DB→service path end-to-end. |
| 6 | `/debug/*` routes absent from `openapi.yaml` | ✅ | `grep -c '/debug' app/backend/openapi.yaml` → 0 (the temp endpoints were never introduced — see deviation D1). |

## Declared deviations (owner adjudicates by merging)

- **D1 — `/debug/vertex-ping` was never built; Vertex-from-deployed-backend not exercised.** The plan predates two later decisions: dev deliberately runs `LLM_BACKEND=mock` (zero Vertex spend — D12/PR #26), and the wrapper's Vertex path was proven from GCP in T01a's live smoke (SA impersonation, `europe-west1`, latency recorded in `vertex-quota.md`); the deployed backend SA holds `roles/aiplatform.user` (both envs). The first deployed-backend→Vertex call therefore lands with the Tier-3 agent tasks (T17+) on a `vertex`-configured service, where it is load-bearing rather than throwaway ceremony. Accepted risk: an IAM/egress surprise unique to the Cloud Run runtime would surface at Tier 3 first.
- **D2 — Tier-1 leftovers tracked elsewhere, not blockers**: prod instance sleeps in cost-idle (wake-day checklist in `cloud-setup.md` § Cost-idle: wake + grants + `wire_runtime=true` + sync-matrix re-enable + `DATABASE_URL` DSN→connector form); T07 browser token smoke (real `@n-ix.com` sign-in) pending the frontend sign-in task or the quickstart §6 snippet; billing SC-007 glance due ~2026-07-07.

## Beyond the letter of T11 (already live, part of this gate's confidence)

- Full release loop rehearsed on dev: `/deploy` (0 % + `candidate` tag smoke) → `/promote 10/100` → `/rollback` (19 s).
- Identity Platform auth **live on dev**: JWT verifier answers 401 to missing/garbage tokens; blocking functions gate every sign-in (fail-closed) with roles from `configs/auth-roles.yaml`.
- Configs-as-code fully live on dev: flags upsert + first rubric seed via `sync-configs.yml` (both jobs green post-merge).
- `terraform plan` clean at checkpoint time (65+ resources under management, one state).

**Tier 1 is closed by merging this PR.** Next: Tier 3 — core agents + state machine (T17 prompt artifacts already exist; T18/T19/T20 are the first product-code tasks).
