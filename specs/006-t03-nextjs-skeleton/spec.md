# Feature Specification: Next.js Skeleton (T03)

**Feature Branch**: `006-t03-nextjs-skeleton`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "T03 — Next.js skeleton" (from `docs/engineering/implementation-plan.md`, Tier 1 / W1–W2)

## Clarifications

### Session 2026-04-26

- Q: Admin shell — Next.js layout vs single page → A: Chrome lives in the root `app/layout.tsx` (every later route inherits top bar + sidebar automatically; route content lives in `page.tsx`).
- Q: Token export — how do Tailwind and shadcn consume it? → A: Both layers — the typed TS export feeds Tailwind's `theme.extend` (utility classes like `bg-surface-base`) **and** also emits CSS custom properties into `globals.css` so shadcn primitives work natively without per-primitive patching.
- Q: Token sync — validator-only or generator + validator? → A: Generator + validator. Markdown under `docs/design/tokens/*.md` remains the source of truth; a committed generator produces both the typed TS export and the CSS-custom-properties block from it; CI validates by running the generator on a clean tree and asserting zero diff against the committed artefacts.
- Q: i18n scaffolding — set up now or defer entirely? → A: File-convention only. T03 commits placeholder `messages/uk.json` and `messages/en.json` at the canonical frontend path (with at most one demo key) to establish the dict-file location for future tasks. T03 does NOT pick an i18n library, does NOT add a provider, does NOT introduce locale-segmented routes. The first task that ships real copy picks the runtime mechanism (e.g., `next-intl` vs `react-intl`) and may freely reshape the JSON.
- Q: Smoke-test scope — what does the T03 admin-shell test cover? → A: Render assertion + keyboard focusability. The committed smoke test mounts the admin-shell route through the application's real rendering pipeline, asserts the wordmark and the left-nav stub are in the DOM, and exercises `userEvent.tab()` across the nav stub items to assert focus moves through them and the focus ring is rendered (no extra dependencies beyond the Jest + RTL + `@testing-library/user-event` stack). `jest-axe` and full WCAG sweeps are deferred to later screen tasks (Playwright + axe-core).
- Q: What counts as "the application's real rendering pipeline" for the smoke test in FR-011, given that the App Router root layout (`app/layout.tsx`) returns `<html><body>...</body></html>` and is awkward to render under JSDOM? → A: The chrome layer — the layout-bearing component `<Shell>` exported from `@/components/shell/shell` — IS the renderable surface that exercises React's real reconciliation pipeline at T03. `RootLayout` is a thin one-liner that only ever wraps `<body className="..."><Shell>{children}</Shell></body>`; mounting `<Shell>` through `@testing-library/react`'s `render(...)` exercises the same component tree the browser sees inside the body. The smoke test is therefore NOT a "unit test against an isolated function" — it mounts the full chrome composition (`<Shell>` → `<TopBar>` + `<Sidebar>` → `<Button>` × 3 from shadcn primitives) through the Next.js compiler (via `next/jest`) and JSDOM. Direct `<RootLayout>` rendering is explicitly out of scope at T03 because it duplicates `<html>/<body>` inside JSDOM's existing document; full-page rendering arrives with Playwright in later screen tasks.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents that build every later frontend-touching feature: `frontend-engineer` (every recruiter and candidate screen from Tier 4 onwards), `infra-engineer` (T06 Cloud Run + T09 Docker stacks — the frontend container must boot and answer on a documented port for liveness probes and the Tier-1 smoke), the `reviewer` agent (validates the visual-discipline and token-drift guardrails on every later frontend PR), and the human operator running the Tier-1 sign-off (T11) who must open the admin shell in a browser and see the N-iX chrome before the gate passes. Until a bootable Next.js app with the admin-shell chrome, a working shadcn/ui primitive inventory, a token export wired into Tailwind, and the visual-discipline guardrails exists, every later frontend task is blocked or has to invent its own scaffolding.

### User Story 1 — The frontend application boots and renders the admin shell (Priority: P1)

Every downstream frontend task assumes a runnable Next.js application exists, with a chrome (top bar + left nav + content slot) ready to host real screens. Infra work (T06 Cloud Run, T09 Docker `web` profile) cannot wire liveness probes without a stable bootable process on a documented port. The Tier-1 gate (T11) requires a human to open the admin shell in a browser and see the N-iX chrome.

**Why this priority**: Without a bootable frontend and an admin shell skeleton, T06 cannot configure Cloud Run for the frontend service, T09 cannot bring up the `web` Compose profile alongside the backend, T11 cannot pass its smoke (admin shell + backend `/health`), and every later screen task (T13 Position Template UI, T20 candidate session, T21 recruiter session review) has to invent the chrome before doing real work. This is the single largest frontend unblocker in Tier 1.

**Independent Test**: A developer or sub-agent starts the frontend service locally with the documented command, opens the documented local URL in a browser, and sees the admin shell — N-iX wordmark in the top bar, a left nav stub, and a content slot — within seconds, without the backend running and without any database, secret, or cloud dependency configured.

**Acceptance Scenarios**:

1. **Given** a fresh clone with only the documented developer prerequisites installed, **When** a developer starts the frontend service locally, **Then** the process begins serving HTTP within 10 seconds and does not exit.
2. **Given** the frontend service is running, **When** any browser opens the root route, **Then** the response is an HTTP success and the rendered page contains the N-iX wordmark, a left nav stub, and a content slot consistent with the Chat-iX visual baseline.
3. **Given** the backend service is not running and no `.env` values for backend or LLM credentials are present, **When** the frontend is started, **Then** it still boots cleanly and the admin shell still renders — the skeleton does not require any backend or secret to run.

---

### User Story 2 — Design tokens are the single source of truth and drift is detected (Priority: P1)

Constitution-adjacent design principle §8 ("Tokens, never hex") and the explicit export note in `docs/design/tokens/colors.md` require that components reference token roles (`bg-surface-base`, `text-content-muted`, …), not raw hex. The markdown files under `docs/design/tokens/` are the source of truth; the TypeScript token object consumed by Tailwind must mirror them and any drift between the two must be caught before merge. Without this guardrail, every later screen has to re-litigate "is this hex correct" and the design system silently rots.

**Why this priority**: Co-equal P1 with User Story 1. The design system's enforceability hinges on this guardrail. Retrofitting it later means auditing every component already shipped — a far more expensive operation than installing the rule on day one. Token-drift is also the single most common silent regression on a multi-screen design system; we want it detected at the contract level, not at human-review time.

**Independent Test**: A reviewer opens the committed token export, confirms its values match the markdown source row-for-row, then deliberately mutates one row in either file and runs the documented drift-check command. The check fails and identifies the drifted row. Reverting the mutation makes the check pass again.

**Acceptance Scenarios**:

1. **Given** the T03 branch is checked out, **When** a reviewer opens the canonical token export file, **Then** every semantic role documented in `docs/design/tokens/*.md` is represented with the same value, with the markdown files cited as the source of truth.
2. **Given** the token files are in sync, **When** a developer changes a single value in either the markdown source or the token export, **Then** a documented drift-check command (locally or in CI) detects the mismatch and identifies the offending role(s) before merge.
3. **Given** the token export exists, **When** Tailwind builds the application, **Then** the same semantic roles are exposed as Tailwind utility classes (e.g., `bg-surface-base`, `text-content-primary`) that components can reference without writing raw hex.

---

### User Story 3 — Visual discipline is enforceable, not aspirational (Priority: P1)

Design principle §8 forbids raw hex anywhere outside the token export, and `docs/design/tokens/colors.md` constrains brand orange (`#E8573C`) to a short allowlist of slots (wordmark, primary CTA, focus ring, link, filled checkbox, single empty-state emphasis). Theme is light-only at MVP — `dark:` Tailwind variants are forbidden. These rules are silent regressions waiting to happen unless a guardrail catches them at PR time. T03 installs both the rules and a primitive inventory (shadcn/ui) that lets later screens compose without reaching for raw values.

**Why this priority**: Co-equal P1. The design system is only as strong as its weakest screen. Letting one screen sneak in a raw hex or a `dark:` class produces a precedent that future reviewers will struggle to reverse. The `reviewer` sub-agent (`.claude/agents/reviewer.md`) is the gate; T03 wires up what it inspects.

**Independent Test**: A reviewer adds a raw hex value to a component file, runs the documented visual-discipline command, and observes a failure that names the file and line. The same check fails when a `dark:` Tailwind variant is added in a non-`tokens.ts` file. Reverting the additions makes the check pass.

**Acceptance Scenarios**:

1. **Given** the T03 branch is checked out, **When** a reviewer looks at the `app/frontend/src/components/ui/*` folder, **Then** the documented shadcn primitives are installed, importable, and styled exclusively via Tailwind classes that resolve to token roles (no raw hex, no `dark:` variants).
2. **Given** the visual-discipline guardrail is wired up, **When** a developer commits a raw hex value (any `#RRGGBB` or `#RGB`) inside any frontend file other than the canonical token export, **Then** the guardrail fails at pre-commit or CI time and identifies the file and line.
3. **Given** the visual-discipline guardrail is wired up, **When** a developer commits a `dark:` Tailwind variant anywhere in the frontend tree, **Then** the guardrail fails (light-theme only at MVP, principle §6).
4. **Given** the admin shell renders, **When** a reviewer compares the chrome against `docs/design/references/hellow_page.png` and `docs/design/references/admin_page.png`, **Then** brand orange appears only in the documented allowlist slots exercised at T03 (the wordmark and the focus ring); everything else is neutral on white.

---

### User Story 4 — A frontend test suite and a smoke test convention are in place (Priority: P2)

Constitution §7 requires test coverage on new code, and the implementation plan calls for "Jest + React Testing Library configured; one smoke test green". The skeleton establishes the convention for where frontend tests live, how they are run, and what a "minimum viable test" looks like — so every later frontend task copies the pattern rather than invents it.

**Why this priority**: P2 because functional value is delivered by User Stories 1–3; this story is about ensuring the next frontend task has an obvious, already-exercised place to put its tests. Without it, every screen task reinvents test wiring.

**Independent Test**: A developer runs the documented frontend-test command on a clean tree and sees a green result. The smoke test that mounts the admin-shell route runs as part of that command. Adding a failing assertion to that test causes the command to fail.

**Acceptance Scenarios**:

1. **Given** a clean tree, **When** a developer runs the documented frontend-test command, **Then** at least the admin-shell smoke test executes and passes.
2. **Given** the test suite exists, **When** a reviewer looks at the canonical frontend-tests location, **Then** the tests are discoverable without reading CI configuration, and the location matches what any future frontend task would reuse.

---

### Edge Cases

- **Backend not running.** The frontend boots and renders the admin shell without the backend reachable. T03 does not generate or consume an OpenAPI client (deferred to the first task that needs an endpoint, per the implementation plan).
- **No secrets or environment.** No public-domain URL, no analytics key, no auth provider — none required for the skeleton. The admin shell renders against `localhost` only at this stage.
- **Long Ukrainian copy.** Even though no Ukrainian copy ships in the shell stub, the shell's chrome must accept 30–40% longer strings without truncation or layout collapse (principle §1). This is a forward-looking constraint validated visually rather than functionally at T03.
- **Reduced motion.** Components must respect `prefers-reduced-motion` (principle §11). Where a primitive ships with motion defaults, those defaults must remain disabled or trivial under reduced-motion.
- **Brand orange creeping outside the allowlist.** A future PR introducing brand orange in a non-allowlist slot must be detected by the visual-discipline guardrail and rejected.
- **`dark:` variants creeping in.** A future PR introducing `dark:` anywhere must be detected and rejected (principle §6: light-first, no silent dark mode).
- **Token markdown updated without TS update (or vice versa).** A drift in either direction must be detected before merge.
- **shadcn primitive update via CLI.** A reviewer running `pnpm dlx shadcn-ui@latest add <primitive>` later must produce the same chrome. If the CLI version drifts and re-installs a primitive with raw hex, the visual-discipline guardrail catches it.
- **Empty lint, type-check, and prettier targets.** T01's guardrails already exit zero on empty targets. After T03 they exit zero on the populated tree as well.
- **Worktree / monorepo path conventions.** The frontend lives under `app/frontend/`, established by T01. T03 does not move it.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain a runnable frontend web application under `app/frontend/`. A single documented command MUST start the development server locally and bind to a documented local port.
- **FR-002**: The frontend application MUST serve a root route (`/`) that renders the admin shell — at minimum: a top bar containing the N-iX wordmark; a left nav stub; a content slot. The route MUST be reachable without authentication and without the backend running. The chrome (top bar, sidebar, content slot wrapper) MUST be implemented as the root Next.js App Router layout (`app/layout.tsx`) so every later route inherits it automatically; `app/page.tsx` contributes the content area only, not the chrome.
- **FR-003**: The frontend application MUST boot successfully with no external dependencies configured — no backend URL, no LLM credentials, no Secret Manager binding, no analytics key. Boot-time failures that require any external dependency MUST NOT be introduced in T03.
- **FR-004**: The repository MUST install and commit the documented shadcn/ui primitive inventory (at minimum: `button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table`) under the canonical primitives folder, importable from a stable alias documented in the engineering reference.
- **FR-005**: The repository MUST commit a typed design-token export that encodes every semantic role documented in `docs/design/tokens/*.md` (colours, spacing, radii, typography, motion) using the same role names. The export MUST be consumed by **two** runtime channels: (a) Tailwind's `theme.extend` so application code can reference roles via utility classes (`bg-surface-base`, `text-content-primary`, …); and (b) CSS custom properties emitted into the global stylesheet (`--surface-base`, `--content-primary`, … — for colours in the form expected by shadcn/ui primitives so the installed primitives render correctly without per-primitive patching). Components MUST reference token roles through these channels, never via raw hex or arbitrary Tailwind values.
- **FR-006**: A committed generator script MUST treat `docs/design/tokens/*.md` as the canonical source of truth and emit both the typed TS export (FR-005a) and the CSS custom properties block (FR-005b) from it deterministically. A documented guardrail (pre-commit hook or CI check) MUST run the generator on a clean tree and fail before merge if the regenerated output differs in any byte from the committed artefacts. Running the check on an in-sync tree MUST exit zero; introducing a single divergent value in any of the three artefacts (markdown, TS, CSS) MUST cause the check to exit non-zero and identify the offending role(s).
- **FR-007**: A documented visual-discipline guardrail MUST detect raw hex usage (`#RRGGBB`, `#RGB`) outside the canonical token export file and fail before merge. The same guardrail MUST detect `dark:` Tailwind variants anywhere in the frontend tree and fail.
- **FR-008**: Brand orange (`#E8573C`) MUST appear in the rendered admin shell only in the slots documented under "Where the brand appears" in `docs/design/tokens/colors.md`. The slots exercised at T03 are the N-iX wordmark in the top bar and the keyboard focus ring; other allowlist slots (primary CTA per screen, filled checkbox, etc.) are exercised by later tasks. **Enforcement at T03 is two-layered**: (a) **mechanical** — the visual-discipline guardrail (FR-007) prevents raw hex outside the token files, ensuring brand orange always reaches a rendered element through a token role rather than ad-hoc; (b) **reviewer-validated** — slot-correctness (the allowlist itself: "orange ONLY on the wordmark, focus ring, primary CTA, filled checkbox, link, single empty-state emphasis") is reviewed at PR time via visual comparison against `docs/design/references/hellow_page.png` and `docs/design/references/admin_page.png`. Mechanical slot-correctness enforcement (e.g., a lint rule that flags `bg-brand-primary` outside an allowlisted file set) is **deferred** to a later task — at the design-system maturity of T03 the cost/benefit favours reviewer eyeball + the existing token-discipline floor.
- **FR-009**: The admin shell MUST follow the Chat-iX visual baseline documented in `docs/design/references/*.png`: white canvas, a `surface.raised` left sidebar, 1-px subtle dividers between regions, the N-iX wordmark in brand orange in the top bar, and otherwise neutral typography on white.
- **FR-010**: The frontend MUST be light-theme only. No `dark:` Tailwind variants and no theme toggle exist anywhere in the T03 deliverable.
- **FR-011**: The frontend test suite MUST live under `app/frontend/` (establishing the convention for every later frontend task). A single documented command MUST run the whole frontend test suite locally. At least one committed smoke test MUST mount the **chrome layer** — the layout-bearing component (`<Shell>`) that the root layout (`app/layout.tsx`) wraps around `{children}` — through React's real reconciliation pipeline (NOT a unit test against an isolated utility function), and assert: (a) the N-iX wordmark is in the DOM; (b) the left-nav stub items are in the DOM; (c) keyboard tab navigation moves focus across the nav stub items and the focus ring is rendered. The smoke test MUST run as part of the documented frontend-test command and MUST fail on any of (a)–(c) regressing. Direct rendering of `<RootLayout>` is out of scope at T03 (it duplicates `<html>/<body>` inside JSDOM's existing document); full-page rendering arrives with Playwright in later screen tasks.
- **FR-012**: Every interactive element in the admin shell MUST be reachable via keyboard (tab order); the focus ring MUST be visible (default shadcn focus ring acceptable). Icon-only controls MUST carry a programmatic label. These are minimum-viable accessibility floors per principle §5; full WCAG 2.2 AA verification (axe-core, full-page Playwright runs) is the responsibility of later screen tasks.
- **FR-013**: The T03 PR MUST NOT introduce: any authentication mechanism or session middleware; any candidate-facing screen (deferred to Tier 4); any recruiter screen with real data wiring (deferred to Tiers 2, 4, 5, 6); a generated OpenAPI client (deferred to the first task that needs an endpoint); real navigation routes beyond the chrome stub; any `dark:` styling; any motion beyond Tailwind defaults; any analytics, telemetry, or third-party script.
- **FR-014**: The T01 frontend lint, prettier, and type-check commands MUST continue to exit zero on the post-T03 tree. No T01 guardrails are relaxed, disabled, or worked around by T03.
- **FR-015**: The documented commands (`pnpm dev` or equivalent, the test command, the token-drift command, the visual-discipline command) and the canonical paths (admin-shell route, primitives folder, token export file, tests folder) MUST be discoverable from a single location in the repository (the developer-setup documentation or `docs/engineering/coding-conventions.md`), so downstream agents do not have to read CI workflows or source code to locate them.
- **FR-016**: Secrets, credentials, real candidate data, and PII samples MUST NOT be committed as part of the T03 PR. The T01 guardrail hooks (gitleaks, detect-secrets, forbid-env-values) MUST NOT be bypassed or weakened.

### Key Entities

- **Admin shell.** The frame chrome — top bar with N-iX wordmark, left nav stub, content slot — that hosts every recruiter screen post-T03. It is the structural contract every later recruiter screen extends, not a finished page.
- **shadcn primitive inventory.** The committed set of UI primitives under the canonical primitives folder, importable via a stable alias, styled exclusively via token-backed Tailwind classes. Later tasks add more primitives via the same install path.
- **Design-token export.** A typed module under `app/frontend/src/design/` that mirrors `docs/design/tokens/*.md` and is consumed by Tailwind's theme extension. The markdown files remain the source of truth; the typed export is the runtime artefact.
- **Token-drift guardrail.** A check that compares the markdown source against the typed export and fails when they diverge. It is the mechanism that keeps "tokens never hex" enforceable across the lifetime of the project.
- **Visual-discipline guardrail.** A check that flags raw hex values outside the token export and `dark:` Tailwind variants anywhere in the frontend tree.
- **Frontend smoke test.** A request-level test that mounts the admin-shell route through the application's real rendering pipeline and asserts the chrome renders. It establishes the pattern every later frontend task follows.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor, starting from a tree that already satisfies T01, can start the frontend and see the admin shell at the documented local URL within 2 minutes, following only the documented developer-setup instructions.
- **SC-002**: Running the full frontend test suite on the post-T03 clean tree completes in under 60 seconds and reports 100% pass, including the admin-shell smoke test.
- **SC-003**: Running the token-drift check on a clean tree completes in under 5 seconds and reports zero drift; introducing a deliberate single-value drift causes the check to fail and identify the role.
- **SC-004**: Running the visual-discipline check on a clean tree completes in under 5 seconds and reports zero violations; introducing a single raw hex anywhere outside the token export, or a single `dark:` variant anywhere, causes the check to fail and identify the file.
- **SC-005**: Zero raw hex values exist in any committed frontend file outside the canonical token export.
- **SC-006**: Zero `dark:` Tailwind variants exist anywhere in the committed frontend tree.
- **SC-007**: Brand orange (`#E8573C`) renders in the admin shell only in the wordmark and the focus ring; a reviewer can confirm by visual inspection against `docs/design/references/hellow_page.png`.
- **SC-008**: The frontend lint, prettier, and type-check commands from T01 exit zero on the post-T03 tree within the time budgets established for T01.
- **SC-009**: The committed shadcn primitive inventory (at minimum: `button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table`) is importable from the documented alias and resolves zero compile errors when referenced from a stub component.
- **SC-010**: A reviewer (human or sub-agent) can validate T03 acceptance using only the commands documented under FR-001, FR-006, FR-007, FR-011, and FR-015 — without reading the implementation diff.

## Assumptions

The implementation plan (`docs/engineering/implementation-plan.md`) and the design system docs (`docs/design/principles.md`, `docs/design/tokens/colors.md`, `docs/design/components/README.md`) already fix the technology choices below. Treating them as spec-level assumptions rather than functional requirements keeps the FRs outcome-focused while keeping the technical floor explicit for the implementing sub-agent.

- **Stack.** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui + lucide-react — fixed by `docs/design/principles.md` §"The stack is fixed". Versions follow the floors set by `app/frontend/package.json` from T01 (Node 20.x, pnpm 9.x).
- **Local dev command.** `pnpm dev` (or `pnpm --dir app/frontend dev` from the repo root) starts the development server on a documented local port; equivalent to the implementation-plan acceptance line "`pnpm dev` serves `/` with admin shell".
- **Test framework.** Jest + React Testing Library + `@testing-library/user-event`, per the implementation-plan acceptance line and the keyboard-focusability check now baked into FR-011(c). Playwright + axe-core full-page accessibility runs (and `jest-axe` snapshots) are deferred to later screen tasks; T03 only ships the unit-test wiring and one route-level smoke that covers render + keyboard tab navigation.
- **Primitives import alias.** `@/components/ui/*` for shadcn primitives; `@/design/tokens` for the typed token export — matching the convention already documented in `docs/design/components/README.md`.
- **Admin-shell route.** The chrome lives in the root layout `app/frontend/src/app/layout.tsx`; the content for the root path comes from `app/frontend/src/app/page.tsx` (a stub at T03). Sub-routes are not introduced at T03 — they will be added by later screen tasks and inherit the chrome automatically.
- **shadcn install path.** Primitives are installed via the shadcn CLI and committed to the repo; later tasks add primitives via the same path. We do not fork or vendor primitives elsewhere.
- **Tailwind theme extension.** `tailwind.config.ts` reads the typed token export via `theme.extend`, exposing semantic roles as utility classes. Raw colour values are not declared in the Tailwind config.
- **CSS custom properties.** The same typed token export is emitted into `app/frontend/src/app/globals.css` (or an equivalent global stylesheet imported from the root layout) as CSS custom properties keyed by role name (e.g., `--surface-base`, `--brand-primary`, with colours expressed in the channel format expected by shadcn primitives). The shadcn primitives installed at T03 read these variables natively. The CSS-vars emission is part of the same generation/validation step as the Tailwind theme to keep the two channels from drifting against the markdown source.
- **Token-drift check mechanism.** A committed generator script reads `docs/design/tokens/*.md` (the source of truth) and writes both the typed TS export and the CSS-custom-properties block deterministically. The drift check is "regenerate on a clean tree → assert zero byte diff against the committed artefacts" (mirrors the OpenAPI regen-and-diff pattern T02 established for the backend). The check runs locally (pre-commit) and in CI (lint job). The implementer chooses the scripting language for the generator (TS-on-Node or Python under `app/backend/scripts/` are both acceptable); the contract is "markdown changes propagate via the generator, never by hand-editing TS or CSS".
- **Visual-discipline check mechanism.** Either a custom ESLint rule, a regex-based pre-commit grep, or both — the contract is "raw hex outside the token file fails the check, and `dark:` anywhere fails the check". The implementer chooses the cheapest credible mechanism.
- **OpenAPI client generator.** Deferred to the first task that consumes a backend endpoint (Tier 2: T13 Position Template UI). T03 does not introduce a generator, a generated client, or any backend wiring.
- **Authentication / authorisation.** Deferred. The admin shell at T03 is an unauthenticated stub. Real auth lands with the first recruiter screen that requires it (Tier 6 onwards) or a dedicated auth task before that.
- **Internationalisation.** File-convention only at T03. The admin shell contains no candidate-facing copy and only minimal recruiter chrome (the N-iX wordmark in the top bar — brand asset, not localised). T03 commits placeholder `app/frontend/src/messages/uk.json` and `app/frontend/src/messages/en.json` (with at most one demo key) so the dict-file location is established for future tasks; no i18n library, provider, or locale routing is introduced. The first candidate-facing screen task (Tier 4: T20) picks the runtime i18n mechanism and may reshape the JSON freely. The exact path may be relocated by that task without violating T03 — the contract is "T03 leaves a marker, not a runtime".
- **Motion library.** Tailwind defaults only. No Framer Motion, no custom animation library at T03. `prefers-reduced-motion` is respected by virtue of using only opacity / minimal-translate transitions on shadcn primitives.
- **Existing T01 guardrails are inherited, not replaced.** ESLint, Prettier, TypeScript, and pre-commit hooks installed by T01 continue to run; T03 layers additional rules (visual discipline, token drift) on top.
- **No backend dependency.** Per the implementation plan, T03 depends on T01 only. T03 is parallelisable with T02 (FastAPI skeleton), so the admin shell must boot without the backend running.
