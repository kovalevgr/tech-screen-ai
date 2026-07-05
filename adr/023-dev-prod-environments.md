# ADR-023: Dev and prod environments in a single project

- **Status:** Accepted
- **Date:** 2026-07-02
- **Supersedes:** [ADR-009](./009-prod-only-topology.md)

## Context

ADR-009 declared production the only long-lived environment, with Docker parity (ADR-010) and 0%-traffic Cloud Run revisions (ADR-012) as the compensating pre-prod controls. Constitution §8 encoded the same rule.

Two forces pushed against it as T06 (cloud runtime provisioning) started:

1. The implementation plan (`docs/engineering/implementation-plan.md`, v1.0, same authorship window as ADR-009) consistently assumes a `dev` cloud environment: T01a smokes Vertex "from `dev` Cloud Run", T06 says "Two workspaces: `dev`, `prod`", T06a measures `/rollback` "on `dev`", T11 deploys "to `dev` Cloud Run via `/deploy`". The two documents were never reconciled.
2. Deploy tooling (T06a) and SSO (T07) need somewhere to be exercised that is not the production users' environment — 0%-traffic revisions cover *application* releases well, but infrastructure-level work (traffic-shift commands themselves, IAM changes, proxy wiring) has no safe rehearsal space in a strictly prod-only world.

The conflict was surfaced to the owner on 2026-07-02 (spec `specs/018-t06-cloud-runtime/`, Clarifications session) with the cost/drift trade-offs stated. The owner chose dev + prod.

## Decision

**Two long-lived environments — `dev` and `prod` — live in the single GCP project `tech-screen-493720`, single region `europe-west1`.**

- One Terraform codebase: a reusable `infra/terraform/modules/environment/` module instantiated twice from the root configuration, in one state. Environments cannot drift structurally — they are the same HCL with different names.
- Naming: prod keeps the canonical resource names (`techscreen-backend`, `techscreen-pg`, secret names as in `.env.example`); dev appends `-dev` (resources) / `_DEV` (secrets).
- **The release path is unchanged from ADR-012**: prod deploys still go out as Cloud Run revisions at 0% traffic, smoke-tested, then ramped. `dev` is a development/integration environment — it is *not* a staging gate, no release is required to "pass dev" before prod.
- There is still no staging, QA, or UAT environment, and still no second GCP project.

## Alternatives considered

- **Keep prod-only (ADR-009 status quo)** — cheapest (~$11–12/mo infra) and doc-consistent; rejected by the owner: no rehearsal space for deploy/IAM/infra work, and the implementation plan's task acceptance criteria (T06a, T11) reference `dev` explicitly.
- **Second GCP project for dev** — stronger isolation; rejected: doubles bootstrap/WIF/billing surface, contradicts the single-project simplicity the MVP relies on, and §8's "no second GCP project" enforcement clause survives this ADR.
- **Ephemeral dev (spin up / tear down per need)** — Terraform makes it possible; rejected for MVP: Cloud SQL PITR + secret fills make teardown/rebuild operationally expensive; revisit if cost pressure appears.

## Consequences

**Positive.**

- Deploy tooling, SSO wiring, and migrations get a real rehearsal environment identical in shape to prod.
- Module-twice instantiation gives structural anti-drift guarantees ADR-009 worried about with staging.
- The implementation plan's `dev`-referencing acceptance criteria become executable as written.

**Negative.**

- Infra baseline roughly doubles: ~$11–12 → **~$22–25/mo** (2 × Cloud SQL `db-f1-micro` + PITR dominates). Still under the PLN 200 (~$50) project budget; §12 interpretation unchanged.
- Two databases to migrate and two secret sets to fill — operator runbooks (quickstart in `specs/018-t06-cloud-runtime/`) cover both.
- "It worked in dev" false confidence is a real risk ADR-009 named. Mitigation: dev is explicitly *not* a release gate; prod verification remains 0%-traffic revision smoke (ADR-012) + dark launches (§9).

## Measurements

| Item | prod-only (rejected) | dev + prod (chosen) |
| --- | --- | --- |
| Cloud SQL instances | 1 | 2 |
| Cloud Run services | 2 | 4 |
| Secret shells | 5 | 10 |
| Est. infra cost /mo | ~$11–12 | ~$22–25 |
| Staging gate in release path | none | none (unchanged) |

Constitution §8 is amended in the same PR (v1.1) per the constitution's own change procedure.
