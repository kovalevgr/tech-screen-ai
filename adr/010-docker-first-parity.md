# ADR-010: Docker-first dev / CI / prod parity

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

With no staging environment (ADR-009), our main pre-production defence is **parity between what a developer runs locally and what runs in production**. Any drift between the two produces bugs that appear only under load or under specific prod config and are painful to reproduce.

## Decision

Every service runs in Docker. The dev environment is `docker-compose.yml`. The CI environment is `docker-compose.test.yml`. The production image is the `prod` target of the same multi-stage Dockerfile used for dev.

- Multi-stage Dockerfiles for backend and frontend: `base` → `dev` (with hot-reload tooling) → `test` (dev + test tooling) → `prod` (slim, no dev tooling).
- `docker-compose.yml` mounts source as volumes for hot reload in the `dev` target.
- `docker-compose.test.yml` runs the `test` target and exits when all tests finish.
- GitHub Actions reuses the same compose files via `docker compose -f docker-compose.test.yml up --abort-on-container-exit`.
- Cloud Run deploys the `prod` target image from Artifact Registry.

## Consequences

**Positive.**
- A passing local test that fails in CI is a bug, not an environment issue — the pipelines are byte-identical.
- New engineers have a one-command onboarding: `docker compose up`.
- No "works on my machine" class of incidents.
- Makes ADR-009 (no staging) tolerable.

**Negative.**
- Slower iteration on platforms with poor Docker performance (notoriously macOS on Apple Silicon with old Docker Desktop).
- Multi-stage builds require more Dockerfile discipline than quick hacks allow.

**Mitigation.**
- Documented recommendations in `docs/dev-environment.md` for macOS users (VirtioFS, cache volumes, etc.).
- The `dev` Dockerfile target is tuned for fast rebuilds (BuildKit cache mounts, layered dependency install).
