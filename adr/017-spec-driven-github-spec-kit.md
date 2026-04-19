# ADR-017: Spec-driven development via GitHub Spec Kit

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen involves significant AI-assisted implementation (Claude Code + Claude Agent SDK). Without a disciplined spec-first workflow, AI assistance produces fast-but-wrong code that costs more to revert than to write by hand.

We evaluated:

1. **Informal** — write English descriptions in PRs, let the AI generate code.
2. **Custom in-house** — design our own spec templates and workflow.
3. **GitHub Spec Kit** — a published toolkit (`/specify`, `/plan`, `/tasks`, `/implement` commands and `.specify/memory/` conventions) designed exactly for this.

Informal produces chaos. Custom in-house means maintaining a framework that is not our product. Spec Kit gives us a community-vetted workflow with published slash commands and conventions, while remaining thin enough that we can modify it.

## Decision

TechScreen uses **GitHub Spec Kit** as its spec-driven development workflow.

- Feature work progresses through `/specify` → `/plan` → `/tasks` → `/implement` in Claude Code.
- Project invariants live in `.specify/memory/constitution.md` (this repo's is ratified as of this ADR).
- Each spec lives under `.specify/specs/<slug>/` with its own `spec.md`, `plan.md`, `tasks.md`.
- Per-feature design references (screens, tokens) must be linked from `plan.md` (see `docs/design/README.md`).
- Trivial changes (typo fixes, dependency bumps, formatting) may skip Spec Kit entirely.

## Consequences

**Positive.**

- A community-maintained workflow, not a bespoke one to maintain.
- Clear artefacts to review at each stage — spec reviewers are not forced to read code to find the intent.
- Good fit for multi-agent (ADR-014): `plan.md` is where agent assignments and parallel groupings live.

**Negative.**

- Adds ceremony for small features. Mitigated by the "trivial changes can skip" carve-out.
- Our team must learn the Spec Kit conventions — short learning curve but non-zero.

**Mitigation.**

- `CLAUDE.md` documents the workflow in ~20 lines.
- Templates for `spec.md`, `plan.md`, `tasks.md` are committed under `.specify/templates/` and the `/specify` command uses them automatically.
