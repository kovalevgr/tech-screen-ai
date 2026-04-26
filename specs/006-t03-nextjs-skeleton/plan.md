# Implementation Plan: Next.js Skeleton (T03)

**Branch**: `006-t03-nextjs-skeleton` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/006-t03-nextjs-skeleton/spec.md`

## Summary

T03 is the first frontend-code PR on top of the T01 monorepo baseline. It lands six things, nothing more:

1. A runnable Next.js (App Router) application under `app/frontend/` that starts without any secret, backend, or external dependency. The chrome (top bar with the N-iX wordmark, left nav stub, content slot) lives in the **root layout** `app/frontend/src/app/layout.tsx` so every later route inherits it automatically.
2. A committed shadcn/ui primitive inventory at `app/frontend/src/components/ui/` covering the nine primitives the implementation plan calls out (`button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table`) plus `components.json` so future tasks add primitives via the same `pnpm dlx shadcn@latest add …` path.
3. A typed design-token export at `app/frontend/src/design/tokens.ts` and a CSS-custom-properties block emitted into `app/frontend/src/app/globals.css`. Both are produced by a committed generator that reads `docs/design/tokens/*.md` (the canonical source) so contributors edit markdown only — never the generated artefacts.
4. Two design-system guardrails: (a) a token-drift check (a Jest test that runs the generator in memory and asserts byte-equality with the committed artefacts, mirroring T02's OpenAPI regen-and-diff pattern), and (b) a visual-discipline check (a pre-commit hook + CI step that fails on raw `#hex` outside `tokens.ts`/`globals.css` and on any `dark:` Tailwind variant anywhere in the frontend tree).
5. A minimal frontend test suite at `app/frontend/src/__tests__/` with the admin-shell smoke (FR-011) — render assertion + `userEvent.tab()` keyboard focusability — and the token-drift test from §4. Jest is wired via the `next/jest` factory so it shares the Next.js compiler with the app.
6. The Docker-compose `frontend` service flipped from its T02-stub `target: build` to a working `target: dev`, plus a new `Dockerfile.frontend` multi-stage image (`base/deps/dev/build/runtime`) that satisfies constitution §7 Docker parity.

No real screens, no auth, no generated OpenAPI client, no `dark:` variants, no motion library, no analytics, no telemetry. The candidate-facing screens (Tier 4: T20+), recruiter screens (Tiers 2/4/5/6), and OpenAPI client (Tier 2: T13) all build on this skeleton; T03 is deliberately narrow so its diff is reviewable in one sitting.

## Technical Context

**Language/Version**: TypeScript 5.5+ (already in `app/frontend/package.json` from T01) targeting Node 20.x (already in `engines`). React 18.3.x. No host Python required for T03 (the design-token generator is TS-on-Node, run via `tsx`).

**Primary Dependencies** (added to `app/frontend/package.json`'s `dependencies`):

- `next` ≥ 15.0, < 16 — App Router, with the `next/jest` factory, the file-based router, and built-in OpenTelemetry hook (the latter not used at T03 but available for T07).
- `react` 18.3.x and `react-dom` 18.3.x — Next 15 supports both 18 and 19; we pin 18 for shadcn-CLI default-template parity at MVP.
- `tailwindcss` ≥ 3.4, < 4 — classic JS config (`tailwind.config.ts` with `theme.extend`), per the spec's CSS-vars-plus-utility-classes assumption. Tailwind 4 is a deliberately deferred decision (it's a CSS-first config rewrite that would invalidate the shadcn primitive templates).
- `@radix-ui/react-*` — pulled in transitively by the shadcn primitives the CLI installs (`@radix-ui/react-dialog`, `@radix-ui/react-dropdown-menu`, `@radix-ui/react-tooltip`, `@radix-ui/react-popover`, `@radix-ui/react-label`, `@radix-ui/react-slot`).
- `class-variance-authority` and `clsx` and `tailwind-merge` — shadcn's standard CVA-plus-`cn()` helper stack.
- `lucide-react` — icon library named in `docs/design/principles.md` §"the stack". Not heavily used at T03 (the wordmark is text); ships now to lock the choice.

**Dev dependencies** (added to `app/frontend/package.json`'s `devDependencies`):

- `eslint-config-next` matching the `next` major — extends the existing T01 eslint stack with React Hooks + Next.js rules.
- `@tailwindcss/postcss` (or the legacy `postcss` + `autoprefixer` combo) — Tailwind's PostCSS plugin pipeline.
- `jest` ≥ 29.7, < 30 — test runner. `jest-environment-jsdom` ≥ 29.7 — DOM environment.
- `@testing-library/react` ≥ 16, `@testing-library/user-event` ≥ 14, `@testing-library/jest-dom` ≥ 6.6 — RTL stack the smoke test imports.
- `@types/jest`, `@types/react`, `@types/react-dom` — type declarations.
- `tsx` ≥ 4.19 — runs the design-token generator (`scripts/generate-tokens.ts`) without a separate compile step.

**shadcn primitives** are installed via the `shadcn` CLI (`pnpm dlx shadcn@latest add <primitive>`) and **committed to `app/frontend/src/components/ui/`**. The CLI itself is not a `devDependency` — invoking it transiently is enough.

**Storage**: N/A — T03 has no persistence. No `localStorage`/`sessionStorage` writes either.

**Testing**: Jest (configured via `next/jest`) + RTL + `@testing-library/user-event` + `@testing-library/jest-dom`. Tests live under `app/frontend/src/__tests__/` (a flat folder, mirroring T02's `app/backend/tests/` pattern). Two committed tests at T03 close: `shell.test.tsx` (admin-shell render + keyboard tab) and `tokens.test.ts` (design-token drift check). **Test invocation is Docker-only** (constitution §7): `docker compose -f docker-compose.test.yml run --rm frontend pnpm test`; the host-side `pnpm --dir app/frontend test` path stays available but the canonical README command is the Docker one.

**Target Platform**: Browser (modern Chromium / Firefox / Safari evergreens) for the rendered admin shell. Server-side rendering happens inside the Next.js Node 20 runtime; T03 uses **only** static rendering (no `cookies()`, no `headers()` access at the layout level — the shell is a static React tree). Dev container is `node:20-bookworm-slim`. Production target stage is shipped in `Dockerfile.frontend` but its Cloud Run wiring is T06's job.

**Project Type**: Monorepo web — frontend slice only in this PR. Backend (T02) is already committed; T03 does not consume any of T02's runtime endpoints (the OpenAPI client generator is deferred).

**Performance Goals**:

- `pnpm dev` first contentful paint of `/` on developer machine localhost: under 2 s warm cache, under 5 s cold (informational floor; not a Spec SC).
- `docker compose -f docker-compose.test.yml run --rm frontend pnpm test` wall time < 60 s on a clean tree (SC-002), excluding image build (build is cached after the first run).
- `docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check` wall time < 5 s (SC-003).
- Visual-discipline check (`pnpm lint:visual-discipline`) wall time < 5 s on the post-T03 tree (SC-004).

**Constraints**:

- **§14 Contract-first** — design-system contract artefacts (`tokens.ts`, `components.json`, the primitive inventory, the visual-discipline rule) committed in this PR unblock every later screen task in Tiers 2, 4, 5, 6, 7. T03's contract IS this skeleton.
- **§7 Docker parity** — frontend runs the **same image shape** in dev (`docker compose --profile web up frontend`) and in CI (`docker compose -f docker-compose.test.yml run --rm frontend …`). Production deploys the `runtime` target via T06 Cloud Run.
- **No secret at boot** (FR-003) — zero `process.env[...]` required-key reads in the T03 boot path. Build-time `NEXT_PUBLIC_API_BASE_URL` may exist in compose args but the app must not crash if it is unset.
- **No raw hex outside `tokens.ts`/`globals.css`** (FR-007) — visual-discipline guardrail enforces.
- **No `dark:` Tailwind variants** (FR-010) — visual-discipline guardrail enforces.
- **Tailwind spacing scale is OVERRIDDEN, not extended** — `docs/design/tokens/spacing.md` Export note: "Default Tailwind spacing scale is overridden to match this table exactly (no stray `w-7`)." T03's `tailwind.config.ts` therefore sets `theme.spacing = {…}` (full replacement) rather than `theme.extend.spacing`, for the spacing axis only.
- **Token markdown is canonical** — the generator writes `tokens.ts` and the CSS-vars block; contributors edit markdown only. The drift test fails on any hand-edit of the generated artefacts.
- **Pre-commit guardrails from T01** — `gitleaks`, `detect-secrets`, `forbid-env-values`, eslint, ruff, etc. all pass on every T03-introduced file. T03 only **adds** two new hooks (the visual-discipline grep and the token-drift Jest reference); never weakens the existing ones.

**Scale/Scope**: Single PR, ~30–35 new files (≈ 600 LOC source + ≈ 80 LOC tests + 9 vendored shadcn primitives + the generated `tokens.ts` and `globals.css`). One committer (`agent: frontend-engineer`). No sub-agent fan-out from inside T03 — the fan-out T03 enables happens afterwards on T13+ (Tier 2 Position Template UI), T20+ (candidate session), T21+ (recruiter session review), T22+ (corrections / audit), and so on.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

T03 is a thin frontend skeleton with carefully limited scope. Every invariant below is either satisfied by design or not yet in scope (no LLM, no DB, no auth, no candidate-facing screen at T03).

| §   | Principle                                | Applies to T03?                                                                                                                                                                                       | Status |
| --- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first      | Indirectly — accessible chrome (FR-012) and Ukrainian-ready typography (long-string accommodation, principle §1) are candidate-trust invariants, even though no candidate copy ships at T03.         | Pass   |
| 2   | Deterministic orchestration              | No backend logic, no LLM, no orchestrator code. The shell is pure React markup.                                                                                                                       | N/A    |
| 3   | Append-only audit trail                  | No tables.                                                                                                                                                                                            | N/A    |
| 4   | Immutable rubric snapshots               | No rubric code.                                                                                                                                                                                       | N/A    |
| 5   | No plaintext secrets                     | Yes — zero secrets, zero `.env` values added, `gitleaks` + `detect-secrets` pass on every new file. FR-003 forbids boot-time secret loading; FR-016 reiterates.                                       | Pass   |
| 6   | Workload Identity Federation only        | No SA keys touched.                                                                                                                                                                                   | N/A    |
| 7   | Docker parity dev → CI → prod            | Yes — `Dockerfile.frontend` ships `dev/build/runtime` stages (research §7); `docker-compose.yml` flips the `frontend` service to `target: dev`; `docker-compose.test.yml` runs the same image in CI.  | Pass   |
| 8   | Production-only topology                 | No deploy in T03.                                                                                                                                                                                     | N/A    |
| 9   | Dark launch by default                   | No user-visible behaviour shipped. The admin shell is operational chrome (no candidate exposure); FR-013 forbids any feature ship.                                                                    | N/A    |
| 10  | Migration approval                       | No migrations.                                                                                                                                                                                        | N/A    |
| 11  | Hybrid language                          | Indirect — the shell typography accommodates Ukrainian copy lengths (§1); `messages/uk.json` + `messages/en.json` placeholders mark the i18n location for the first task that ships real Ukrainian copy. | Pass   |
| 12  | LLM cost and latency caps                | No LLM call.                                                                                                                                                                                          | N/A    |
| 13  | Calibration never blocks merge           | No calibration work.                                                                                                                                                                                  | N/A    |
| 14  | Contract-first for parallel work         | Yes — this is the **frontend** counterpart to T02's backend-contract-first work. The committed token export, primitive inventory, layout-as-shell convention, and design-system guardrails ARE the contract every later screen task fans out against. FR-005 + FR-006 + FR-007 + `contracts/frontend-contract.md`. | Pass   |
| 15  | PII containment                          | Indirect — no PII handled. FR-013 explicitly forbids candidate screens; no log writes touch candidate data because no candidate data exists yet.                                                       | Pass   |
| 16  | Configs as code                          | Yes — design tokens in markdown (canonical) → generated TS/CSS via committed script; shadcn primitives committed; primitive inventory documented in `docs/design/components/README.md`.               | Pass   |
| 17  | Specifications precede implementation    | Yes — `/speckit-specify` produced `spec.md` and a `/speckit-clarify` session resolved 5 high-impact ambiguities before this plan.                                                                    | Pass   |
| 18  | Multi-agent orchestration is explicit    | Yes — plan declares `agent: frontend-engineer`, `parallel: false` for T03 itself (single-committer PR enabling downstream parallel fan-out across all later screen tasks).                              | Pass   |
| 19  | Rollback is a first-class operation      | Indirect — T03 introduces no production state, so `git revert` is sufficient; later deploys depending on T03 still get Cloud Run traffic-shift rollback.                                              | Pass   |
| 20  | Floor, not ceiling                       | Pass.                                                                                                                                                                                                 | Pass   |

**Gate result**: PASS. No violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-t03-nextjs-skeleton/
├── spec.md                          # Feature spec (written in /speckit-specify, clarified in /speckit-clarify)
├── plan.md                          # This file
├── research.md                      # Phase 0 — design-altitude decisions
├── data-model.md                    # Phase 1 — "data" entities (mostly non-persistent at T03)
├── contracts/
│   └── frontend-contract.md         # Phase 1 — design-system contract (tokens, primitives, guardrails, layout convention)
├── quickstart.md                    # Phase 1 — reviewer-facing validation walkthrough
├── checklists/
│   └── requirements.md              # From /speckit-specify (passed)
└── tasks.md                         # Created by /speckit-tasks (NOT this command)
```

### Source Code (repository root, after T03 merges)

Every bold/`NEW`/`EDITED` entry is touched by T03. Pre-existing files (from T01/T02) are untouched unless explicitly marked.

```text
.
├── app/
│   └── frontend/
│       ├── package.json                          # EDITED — add next/react/react-dom/tailwindcss/lucide-react/cva/clsx/tailwind-merge
│       │                                         #          and devDeps (eslint-config-next, jest, jest-environment-jsdom, RTL, user-event,
│       │                                         #          jest-dom, @types/jest, @types/react, @types/react-dom, tsx, postcss, autoprefixer);
│       │                                         #          add scripts: dev, build, start, test, tokens:generate, tokens:check, lint:visual-discipline
│       ├── pnpm-lock.yaml                        # EDITED — regenerated by `pnpm install` after the manifest edit
│       ├── tsconfig.json                         # EDITED — add `paths: {"@/*": ["./src/*"]}`, add `next-env.d.ts` to include
│       ├── tooling.d.ts                          # DELETED — its sole purpose ("placeholder until real .ts/.tsx exist") is now obsolete
│       ├── next.config.ts                        # NEW — Next.js config; mostly empty, sets `experimental.typedRoutes` (optional) and `output: undefined`
│       ├── next-env.d.ts                         # NEW — auto-managed by Next; committed so the type check passes on a clean tree
│       ├── tailwind.config.ts                    # NEW — reads `tokens.ts` via `theme.extend.colors|fontSize|borderRadius` and OVERRIDES `theme.spacing` (per spacing.md export note)
│       ├── postcss.config.mjs                    # NEW — tailwindcss + autoprefixer
│       ├── jest.config.ts                        # NEW — wraps `next/jest` factory; `testEnvironment: "jsdom"`, `setupFilesAfterEach: ["./jest.setup.ts"]`
│       ├── jest.setup.ts                         # NEW — `import "@testing-library/jest-dom"`
│       ├── components.json                       # NEW — shadcn config (style: new-york, cssVariables: true, baseColor: neutral, aliases: @/components/ui, @/lib/cn)
│       ├── eslint.config.mjs                     # NEW — flat config extending `next/core-web-vitals`; replaces T01's "no config" default
│       ├── scripts/
│       │   └── generate-tokens.ts                # NEW — reads docs/design/tokens/*.md → writes tokens.ts + the marker-bracketed CSS-vars block in globals.css
│       └── src/
│           ├── app/
│           │   ├── layout.tsx                    # NEW — root layout: <html><body>{shell with content slot {children}}</body></html>
│           │   ├── page.tsx                      # NEW — root content stub (renders an empty-state placeholder inside the shell's content slot)
│           │   └── globals.css                   # NEW — Tailwind directives + the GENERATED CSS-vars block (between `/* TOKENS:START */` and `/* TOKENS:END */`)
│           ├── components/
│           │   ├── ui/                           # NEW — committed shadcn primitives (vendored, edited only via `pnpm dlx shadcn@latest add`)
│           │   │   ├── button.tsx                # NEW — shadcn install
│           │   │   ├── card.tsx                  # NEW — shadcn install
│           │   │   ├── input.tsx                 # NEW — shadcn install
│           │   │   ├── label.tsx                 # NEW — shadcn install
│           │   │   ├── dialog.tsx                # NEW — shadcn install
│           │   │   ├── dropdown-menu.tsx         # NEW — shadcn install
│           │   │   ├── tooltip.tsx               # NEW — shadcn install
│           │   │   ├── popover.tsx               # NEW — shadcn install
│           │   │   └── table.tsx                 # NEW — shadcn install
│           │   └── shell/
│           │       ├── top-bar.tsx               # NEW — top bar with N-iX wordmark (the only brand-orange slot exercised at T03)
│           │       ├── sidebar.tsx               # NEW — left nav stub items (focusable list — keyboard-tab target for FR-011(c))
│           │       └── shell.tsx                 # NEW — composes <TopBar />, <Sidebar />, content slot {children}; consumed by app/layout.tsx
│           ├── design/
│           │   └── tokens.ts                     # NEW — GENERATED from docs/design/tokens/*.md by scripts/generate-tokens.ts
│           ├── lib/
│           │   └── cn.ts                         # NEW — `clsx` + `tailwind-merge` helper, the standard shadcn pattern
│           ├── messages/
│           │   ├── README.md                     # NEW — explains: T03 marker only, no i18n runtime; first task with real copy picks the library
│           │   ├── uk.json                       # NEW — placeholder dict, one demo key
│           │   └── en.json                       # NEW — placeholder dict, one demo key
│           └── __tests__/
│               ├── shell.test.tsx                # NEW — FR-011 admin-shell smoke (render + keyboard tab + focus ring)
│               └── tokens.test.ts                # NEW — FR-006 token-drift Jest test (mirrors T02's OpenAPI regen-and-diff pattern)
├── Dockerfile.frontend                           # NEW — multi-stage: base → deps → dev (default for compose) → build → runtime (T06 prep)
├── docker-compose.yml                            # EDITED — `frontend` service: `target: dev` (was `build`); `depends_on.backend` relaxed to `required: false`
├── docker-compose.test.yml                       # EDITED — adds a `frontend` service block targeting `dev`, runs `pnpm test` & `pnpm tokens:check` non-interactively
├── .pre-commit-config.yaml                       # EDITED — adds two LOCAL hooks: `visual-discipline` (raw hex / dark: regex grep) and `tokens-drift` (runs the generator with `--check`)
├── README.md                                     # EDITED — "Frontend dev loop (Docker-first)" subsection alongside the existing backend section
└── (every other path untouched)
```

**Structure Decision**: Frontend slice only, contained entirely under `app/frontend/`. The module layout intentionally mirrors what every later screen task will reuse: `components/ui/` for shadcn primitives (vendored, never forked), `components/<feature>/` for custom components (`shell/` is the first such feature, established as the convention), `app/<route>/` for Next.js routes (only the root at T03), `design/` for token artefacts, `lib/` for cross-cutting helpers, `messages/` for i18n placeholders. **Tests live alongside the code under `app/frontend/src/__tests__/`** mirroring T02's `app/backend/tests/` convention so reviewer sub-agents find both languages by the same pattern. No premature abstraction: no `services/` folder, no `hooks/` folder, no Redux/Zustand store, no React Query provider — every one of those arrives with the first task that needs it.

**Single committer**: `agent: frontend-engineer`, `parallel: false` for T03 itself. T03 enables downstream `parallel: true` fan-out on every later screen task because the design-system contract (token export, primitive inventory, layout convention, guardrails) is what those tasks depend on.

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                            | Agent               | Parallel? | Depends on                              | Contract reference                                                              |
| ----------------------------------------------------- | ------------------- | --------- | --------------------------------------- | ------------------------------------------------------------------------------- |
| Next.js scaffolding + root layout/page + globals.css  | `frontend-engineer` | false     | T01                                     | n/a (in-PR; chrome contract codified in `frontend-contract.md` Surface 1)       |
| Tailwind + PostCSS wiring                             | `frontend-engineer` | false     | Next.js scaffolding                     | `frontend-contract.md` Surface 2 (token roles)                                  |
| Token generator + tokens.ts + globals.css TOKENS block | `frontend-engineer` | false     | Tailwind wiring                         | `frontend-contract.md` Surface 2 (token export shape)                            |
| shadcn CLI init + 9 primitives committed              | `frontend-engineer` | false     | Tailwind + tokens.ts                    | `frontend-contract.md` Surface 3 (primitive inventory)                          |
| Shell components (top-bar, sidebar, shell composer)   | `frontend-engineer` | false     | shadcn primitives                       | `frontend-contract.md` Surface 1 (chrome shape)                                 |
| Jest + RTL config + admin-shell smoke + token-drift   | `frontend-engineer` | false     | Shell components + token generator      | `frontend-contract.md` Surface 4 (drift detection)                              |
| Visual-discipline pre-commit hook + CI step           | `frontend-engineer` | false     | Tailwind + tokens.ts (so it has scope)  | `frontend-contract.md` Surface 5 (visual discipline)                            |
| Dockerfile.frontend + compose edits                   | `frontend-engineer` | false     | All source files                        | n/a (in-PR; documented in research §7)                                          |
| README "Frontend dev loop (Docker-first)" section     | `frontend-engineer` | false     | All source files                        | T01 + T02's existing README structure                                           |

Every T03 slice is sequential inside a single PR; no sub-agent fan-out. `/speckit-tasks` will break these further but the parallelism boundary is "T03 as a whole → afterwards, downstream screen tasks", not "inside T03".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md).

The spec has zero `[NEEDS CLARIFICATION]` markers and the five clarifying questions from `/speckit-clarify` are already resolved in the Clarifications section. A handful of implementation-detail decisions still sit below spec altitude and above `/speckit-tasks` altitude — Phase 0 resolves them with rationale rooted in an existing repo artefact so the reviewer can verify without external searches.

1. **Next.js + React versions**, including the Next 15 / React 18-vs-19 choice and the implications for shadcn template parity.
2. **Tailwind 3 vs Tailwind 4**, and how `theme.extend` plus the spacing OVERRIDE land in a Tailwind 3 config.
3. **shadcn CLI configuration** — `style`, `baseColor`, `cssVariables`, alias map, and the consequences for the shadcn templates we will commit.
4. **Token generator design** — markdown parser choice, output format (TS object literal vs JSON-then-TS-import), CSS-vars channel format (HSL triplet vs RGB-comma), and idempotency contract.
5. **Token-drift detection surface** — Jest test vs pre-commit hook vs both, and how this mirrors T02's pytest pattern.
6. **Visual-discipline check mechanism** — custom ESLint rule vs ripgrep-backed pre-commit hook vs both, with concrete patterns and exclusion semantics.
7. **Dockerfile.frontend stages** — dev-target choice, build-target inclusion of `pnpm build`, runtime target shape (Next.js standalone vs default), and how `docker-compose.yml`'s existing T02-stub block converts.
8. **i18n placeholder layout** — exact directory location, JSON shape (`{ "wordmark.alt": "N-iX TechScreen" }`), README content, and how the first task that picks an i18n runtime can relocate the directory without violating T03.

All eight decisions are resolved in `research.md` with a decision, a rationale, and rejected alternatives.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T03 has no persistent data. The "entities" enumerated there are the in-process objects and committed artefacts a reviewer should be able to point at — `RootLayout`, `Shell` (composed of `TopBar` + `Sidebar`), `DesignTokenExport`, `CSSCustomPropertiesBlock`, `TokenGenerator`, `TokenDriftTest`, `ShellSmokeTest`, `VisualDisciplineHook` — each with its validation rules and lifecycle. No persistence row schemas; no migrations; no client-side state stores.

### Contracts

See [contracts/frontend-contract.md](./contracts/frontend-contract.md). A single consolidated document covers the five surfaces T03 commits to:

1. **Layout/chrome contract** — where the chrome lives (root `app/layout.tsx`), the slots a later route can rely on (top bar, sidebar, content slot), and the convention "every new route writes a `page.tsx` only".
2. **Design-token export contract** — TS export shape, role names, the CSS-custom-properties block format, and the canonical generation command.
3. **shadcn primitive inventory contract** — which primitives are vendored, which import alias they live behind, and the shadcn-CLI install-extension procedure for later tasks.
4. **Drift-detection contract** — the Jest test path, the `--check` flag on the generator, what failure looks like for the reviewer.
5. **Visual-discipline contract** — what patterns the regex hook flags, what is excluded, what error output the reviewer sees.

Like T02, the runtime artefacts (`tokens.ts`, `globals.css`, `components/ui/*.tsx`, `components.json`) are NOT duplicated under `specs/006-t03-nextjs-skeleton/contracts/` — that would create two sources of truth that the drift-check could not reconcile. The contract document references the runtime paths.

### Quickstart

See [quickstart.md](./quickstart.md) — a reviewer-facing walkthrough that validates the T03 PR end-to-end in under 5 minutes. Mirrors SC-010 ("a reviewer can validate using only the commands documented in FR-001, FR-006, FR-007, FR-011, FR-015 — without reading the implementation diff").

### Agent context update

`CLAUDE.md` does not carry `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->` markers (verified via `grep` — zero matches, same as T02). T00 deliberately stripped them, and the existing "How work happens here (Spec Kit)" section in CLAUDE.md already points sub-agents at the Spec Kit flow. T03 does not re-introduce the auto-generated block. **No CLAUDE.md edit in this step.**

### Re-evaluate Constitution Check (post-design)

Nothing in Phase 0/1 changes the gate result. The commitments made in Phase 0 (Tailwind 3 with `theme.extend`, ripgrep-based visual-discipline hook, Jest-based token-drift test, multi-stage `Dockerfile.frontend`, file-only i18n marker) are fully consistent with §7, §14, §15, §16, §17, §18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations. This table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
