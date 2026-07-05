# Data model — T06a deploy commands

CI/infra feature: the "entities" are workflow contracts, cloud identities, image tags, and traffic states. No database objects change.

## Workflow input contracts

| Workflow | Input | Type | Values / default | Notes |
| --- | --- | --- | --- | --- |
| `deploy.yml` | `env` | choice | `dev` \| `prod` | picks name suffix (`-dev` / empty) + SQL instance |
| | `service` | choice | `backend` \| `frontend` \| `both` (default `both`) | fans out the matrix |
| | `git_ref` | string | default `main` | free text → env-mapped only (FR-013); prod requires main ancestry |
| `promote.yml` | `env`, `service` | choice | as above | |
| | `percent` | choice | `10` \| `50` \| `100` | pinned to `status.latestReadyRevisionName` |
| `rollback.yml` | `env`, `service` | choice | as above | |
| | `revision` | string | optional, empty = auto-detect | free text → env-mapped only |

All three: `permissions: id-token: write, contents: read` (deploy adds `pull-requests: read` for the label gate); concurrency group `cloud-run-<env>` (rollback alone sets `cancel-in-progress: true`).

## Derived values (computed in the workflows, never hardcoded per-env twice)

| Value | dev | prod |
| --- | --- | --- |
| name suffix | `-dev` | `` (empty) |
| backend service | `techscreen-backend-dev` | `techscreen-backend` |
| frontend service | `techscreen-frontend-dev` | `techscreen-frontend` |
| Cloud SQL instance | `techscreen-pg-dev` | `techscreen-pg` |
| image tag suffix | `-dev` | `-prod` |

Constants: project `tech-screen-493720`, region `europe-west1`, registry `europe-west1-docker.pkg.dev/tech-screen-493720/techscreen`, WIF provider `projects/463244185014/locations/global/workloadIdentityPools/github-actions/providers/github`, deployer SA `techscreen-deployer@tech-screen-493720.iam.gserviceaccount.com`.

## Image tag scheme (research D3)

```
europe-west1-docker.pkg.dev/tech-screen-493720/techscreen/backend:<full-40-hex-sha>-<env>
europe-west1-docker.pkg.dev/tech-screen-493720/techscreen/frontend:<full-40-hex-sha>-<env>
```

- Immutable by convention (sha-unique); `provenance: false` → one manifest per tag.
- The migration gate parses `<sha>` back out of the deployed backend image — the tag is the deploy-provenance link.
- Frontend bytes differ per env (`NEXT_PUBLIC_API_BASE_URL` inlined at build; fetched live from the env's backend service URL). Backend bytes are env-agnostic; the tag still carries env for symmetric audit.
- Container ports at deploy: backend `8000` (uvicorn, Dockerfile CMD), frontend `3000` (Cloud Run sets `PORT`=containerPort; `next start` honours it).

## Deployer identity → access matrix (research D4)

| Grant | Scope | Resource(s) | Deny-by-omission consequence |
| --- | --- | --- | --- |
| `roles/run.developer` | project | 4 Cloud Run services + revisions | no `setIamPolicy` → cannot widen public access |
| `roles/iam.serviceAccountUser` | **SA-level ×4** | `techscreen-backend@`, `techscreen-backend-dev@`, `techscreen-frontend@`, `techscreen-frontend-dev@` | cannot actAs `terraform@` (owner) or `techscreen-flag-sync@` |
| `roles/artifactregistry.writer` | repository | AR repo `techscreen` | no project-wide registry write |
| `roles/cloudsql.viewer` | project | instance metadata (guard reads) | no `instances.connect`, no `instances.update` → cannot touch data, cannot wake/sleep instances |
| `roles/iam.workloadIdentityUser` | SA-level | deployer SA itself, for `principalSet://…/attribute.repository/kovalevgr/tech-screen-ai` | only this repo's Actions runs can impersonate |

What the deployer explicitly **cannot** do: read any secret, connect to any database, modify IAM, apply Terraform, create keys, wake instances.

## Traffic state machine (per service; research D8/D9)

```
                     ┌────────────────────────────────────────────┐
                     ▼                                            │
  [R_old 100%] ──deploy──▶ [R_old 100%, R_new 0% +candidate]      │
                     │                                            │
                promote 10 ──▶ [R_old 90%, R_new 10%]             │
                promote 50 ──▶ [R_old 50%, R_new 50%]        rollback (≤60s)
                promote 100 ─▶ [R_new 100%] ──── deploy … ────────┘
```

- Every assignment is a **pinned revision name**; no floating `LATEST` allocation ever remains after the first deploy (`--no-traffic` converts it).
- `candidate` tag: moved to each new revision via `update-traffic --update-tags` — exactly one candidate per service at any time; its URL (`https://candidate---<service>-<hash>.run.app`) is the smoke surface.
- Rollback target = newest **ready** revision older than the current primary (max-percent holder), unless overridden.

## Migration-gate decision table (research D7)

| Deployed backend image | Baseline | `alembic/versions/**` changed in `baseline..target`? | Associated PR labelled `migration-approved`? | Gate |
| --- | --- | --- | --- | --- |
| `…/techscreen/backend:<sha>-<env>`, sha in history | `<sha>` | no | — | pass |
| same | `<sha>` | yes | yes (≥1 PR per commit) | pass |
| same | `<sha>` | yes | no / commit has no PR | **fail** (files+commits+PRs named) |
| placeholder / unparseable tag | `origin/main~1` | (same rows as above) | (same) | same, plus `::notice` about the fallback |

Gate runs for every deploy (any `service` value): a frontend-only deploy of a migration-carrying, unapproved ref is still §10 friction by design.

## DB-asleep guard decision table (research D11)

| Instance state | Deploying backend? | Backend template wires `DATABASE_URL`? | Outcome |
| --- | --- | --- | --- |
| `RUNNABLE` + `ALWAYS` | — | — | pass silently |
| asleep | yes | yes | **fail**: "instance is asleep — run `scripts/cloud-sql-power.sh wake <env>`" |
| asleep | yes | no *(today)* | notice + continue |
| asleep | no (frontend only) | — | notice + continue |

Steps that need the DB: backend revision startup **iff** `DATABASE_URL` is wired (flag-service connects in lifespan); `alembic upgrade head` (operator-run, outside these workflows). Build/push/traffic/frontend-smoke never touch it.

## Job summary contract (all three workflows)

| Field | deploy | promote | rollback |
| --- | --- | --- | --- |
| env / service | ✓ | ✓ | ✓ |
| git SHA + image tag | ✓ | — | — |
| revision name (new/target) | ✓ | ✓ | ✓ (from → to) |
| candidate tag URL | ✓ | — | — |
| smoke verdict | ✓ | — | — |
| traffic split before/after | — | ✓ | ✓ |
| measured shift duration | — | — | ✓ (vs ≤60 s target, §19 5-min ceiling) |
| gate results (ancestry / migration / DB) | ✓ (gate job) | — | — |
