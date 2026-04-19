# ADR-001: Stack — Python FastAPI + Next.js + PostgreSQL

- **Status:** Accepted
- **Date:** 2026-04-18
- **Amended:** 2026-04-19 — PostgreSQL 15 → PostgreSQL 17 (see Amendment below).

## Context

TechScreen needs a stack that (a) has first-class support in the team's existing skill set, (b) integrates cleanly with Google Vertex AI, (c) supports both synchronous request/response (assessments, admin views) and streaming (live interview turns), and (d) is cheap to host on Cloud Run for an internal MVP.

N-iX engineering standards already include Python and TypeScript toolchains. Introducing a third runtime (Go, Rust, Java) would slow onboarding and complicate CI.

## Decision

- **Backend:** Python 3.12 with **FastAPI**, SQLAlchemy 2.x (async), Alembic for migrations, Pydantic v2 for I/O validation.
- **Frontend:** **Next.js 14+** (App Router) with TypeScript, shadcn/ui on top of Radix, Tailwind CSS, lucide-react for icons.
- **Database:** **PostgreSQL 17** with the `pgvector` extension (see ADR-007).

Both services run as independent Cloud Run services behind the same domain.

## Consequences

**Positive.**

- Python dominates the ML/LLM tooling ecosystem (Vertex SDK, token counters, eval harnesses).
- FastAPI's type-driven routing + Pydantic gives us free OpenAPI schemas — essential for contract-first multi-agent work (constitution §14).
- Next.js App Router maps cleanly to our screen set and gives us server components for auth-gated routes with minimal client JS.
- Both runtimes have mature Cloud Run images and short cold starts.

**Negative.**

- Two runtimes to manage, two CI lanes, two Docker images.
- FastAPI streaming support is workable but less mature than Node's; if we hit limits, we revisit.

**Mitigation.**

- A single `docker-compose.yml` orchestrates both runtimes locally; a shared `.env` avoids config drift.
- OpenAPI schema is committed to the repo and regenerated in CI — type-safe clients on both sides.

## Amendment — 2026-04-19: PostgreSQL 15 → 17

**Context.** ADR-001 was accepted 2026-04-18. No production code, migrations, or Cloud SQL instance existed yet when this amendment was drafted — cost of changing the pinned version is near zero (a line in `docker-compose.yml`, the Terraform `database_version`, and this note).

**Decision change.** PostgreSQL 15 → **PostgreSQL 17** for dev, CI, and Cloud SQL prod.

**Why.**

- **EOL runway.** PG15 community support ends 2027-11-11 (~18 months from today); PG17 ends 2029-11-09 (~42 months). Constitution §3 makes audit tables append-only, so they grow monotonically — pushing the first unavoidable major-version upgrade as far out as possible is a direct operational win.
- **pgvector parity.** pgvector (including HNSW indexes, the upgrade path ADR-007 calls out) supports PG15, 16, and 17 identically for our workload.
- **Cloud SQL parity.** PG17 is GA on Cloud SQL in `europe-west1` with the `pgvector` extension flag available (verify at provisioning time in T01a). PG16 is the acceptable fallback if PG17 provisioning blocks for any reason.
- **PG16/17 bonuses relevant to us.** `pg_stat_io` (PG16) for Cloud Run observability; improved vacuum and better SLRU handling (PG17) for append-only audit tables.
- **Greenfield cost of doing it now vs later.** Zero today; non-trivial maintenance window on a live MVP with active interview sessions later.

**Consequences of the amendment.** `docker-compose.yml` pins `pgvector/pgvector:pg17`. Terraform sets `database_version = "POSTGRES_17"` when T01a (infra bootstrap) lands. ADR-007 amended in parallel to match. No other ADR depends on the version string.
