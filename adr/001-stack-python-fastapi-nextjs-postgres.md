# ADR-001: Stack — Python FastAPI + Next.js + PostgreSQL

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen needs a stack that (a) has first-class support in the team's existing skill set, (b) integrates cleanly with Google Vertex AI, (c) supports both synchronous request/response (assessments, admin views) and streaming (live interview turns), and (d) is cheap to host on Cloud Run for an internal MVP.

N-iX engineering standards already include Python and TypeScript toolchains. Introducing a third runtime (Go, Rust, Java) would slow onboarding and complicate CI.

## Decision

- **Backend:** Python 3.12 with **FastAPI**, SQLAlchemy 2.x (async), Alembic for migrations, Pydantic v2 for I/O validation.
- **Frontend:** **Next.js 14+** (App Router) with TypeScript, shadcn/ui on top of Radix, Tailwind CSS, lucide-react for icons.
- **Database:** **PostgreSQL 15** with the `pgvector` extension (see ADR-007).

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
