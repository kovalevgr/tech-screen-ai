---
description: "Task list for T03 — Next.js Skeleton"
---

# Tasks: Next.js Skeleton (T03)

**Input**: Design documents from [`specs/006-t03-nextjs-skeleton/`](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/frontend-contract.md](./contracts/frontend-contract.md), [quickstart.md](./quickstart.md)

**Tests**: Generated. The spec's acceptance criteria pin two committed tests — the admin-shell smoke (FR-011, exercising US1 + US4) and the design-token drift check (FR-006, exercising US2 + constitution §14 / §16). Tests are part of the T03 acceptance gate, not an optional TDD overlay.

**Agent ownership**: All tasks are owned by `agent: frontend-engineer` with `parallel: false` at the sub-agent level, per [docs/engineering/implementation-plan.md](../../docs/engineering/implementation-plan.md) T03. The `[P]` marker inside this file means "different files, no intra-phase dependency" — the orchestrator may open these files in any order within a phase, not that they go to different sub-agents. Sub-agent fan-out (to T13, T20, T21, T22, …) starts **after** T03 lands.

**Organization**: Tasks are grouped by user story. The spec assigns US1, US2, US3 all to **co-equal P1** and US4 to P2. The implementation order is Setup → Foundational → **US2** (tokens) → **US3** (primitives + visual discipline) → **US1** (admin shell) → **US4** (smoke test) → Polish. This is reverse-priority for the three P1 stories because US1's shell consumes tokens (US2 artefacts) and the Button primitive (US3 artefacts), so US2 and US3 must land first. Each story remains independently testable per its `Independent Test` clause in [spec.md](./spec.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can edit/create in any order inside the same phase (different files, no in-phase dependency).
- **[Story]**: `US1`, `US2`, `US3`, `US4`. Setup, Foundational, and Polish tasks carry no story label.
- Paths are **relative to the repo root**.

## Path Conventions

- Runtime code: `app/frontend/src/**/*.{ts,tsx,css}`.
- Tests: `app/frontend/src/__tests__/*.{ts,tsx}`.
- Generator and helper scripts: `app/frontend/scripts/*.{ts,sh}`.
- Frontend config: `app/frontend/{package.json,tsconfig.json,next.config.ts,next-env.d.ts,tailwind.config.ts,postcss.config.mjs,jest.config.ts,jest.setup.ts,eslint.config.mjs,components.json}`.
- Repo-root infra: `Dockerfile.frontend`, `docker-compose.yml`, `docker-compose.test.yml`, `.pre-commit-config.yaml`, `README.md`.
- No files outside these locations are touched (FR-013 scope fence).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the workspace is ready to receive T03 changes. No source files created yet.

- [X] T001 Verify the working tree is clean and the feature directory is correctly registered: run `git status --short` (expect clean), `cat .specify/feature.json` (expect `"feature_directory": "specs/006-t03-nextjs-skeleton"`), and confirm `app/frontend/package.json` and `app/frontend/tsconfig.json` from T01 are present unmodified. If any check fails, stop and investigate before continuing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land the dependency updates, the toolchain configs (Tailwind, PostCSS, Jest, ESLint), the Next.js scaffolding stubs, the i18n placeholder convention, and the empty token-export module so US2 has a target to populate. Every later phase imports or runs against these. No real shell, no real tokens, no shadcn primitives yet.

**⚠️ CRITICAL**: Phases 3–6 cannot begin until this phase is complete — every later task assumes `next`, `tailwindcss`, `jest`, `tsx`, and the import alias `@/*` resolve.

- [X] T002 Edit `app/frontend/package.json`: under `dependencies` add `"next": ">=15.0,<16"`, `"react": "^18.3.0"`, `"react-dom": "^18.3.0"`, `"tailwindcss": ">=3.4,<4"`, `"postcss": "^8.4"`, `"autoprefixer": "^10.4"`, `"lucide-react": "^0.460"`, `"class-variance-authority": "^0.7"`, `"clsx": "^2.1"`, `"tailwind-merge": "^2.5"`. Under `devDependencies` add (keeping every existing T01 entry intact) `"eslint-config-next": ">=15.0,<16"`, `"jest": "^29.7"`, `"jest-environment-jsdom": "^29.7"`, `"@testing-library/react": "^16.0"`, `"@testing-library/user-event": "^14.5"`, `"@testing-library/jest-dom": "^6.6"`, `"@types/jest": "^29.5"`, `"@types/react": "^18.3"`, `"@types/react-dom": "^18.3"`, `"tsx": "^4.19"`. Replace `scripts` with: `"dev": "next dev --port 3000"`, `"build": "next build"`, `"start": "next start --port 3000"`, `"lint": "eslint . --max-warnings=0 --no-error-on-unmatched-pattern && tsc --noEmit"`, `"format": "prettier --write ."`, `"test": "jest"`, `"tokens:generate": "tsx scripts/generate-tokens.ts"`, `"tokens:check": "tsx scripts/generate-tokens.ts --check"`, `"lint:visual-discipline": "bash scripts/check-visual-discipline.sh"`. Reference: [research.md](./research.md) §1, §2, §6.
- [X] T003 Regenerate the frontend lockfile by running `pnpm --dir app/frontend install` from the repo root (after T002). Commit the updated `app/frontend/pnpm-lock.yaml` exactly as produced — `Dockerfile.frontend` `pnpm install --frozen-lockfile` consumes it. No manual edits.
- [X] T004 [P] Edit `app/frontend/tsconfig.json`: add `"baseUrl": "."` and `"paths": {"@/*": ["./src/*"]}` to `compilerOptions`; add `"next-env.d.ts"` to `include` (alongside the existing `**/*.ts`, `**/*.tsx`); add `".next"` to `exclude` (already present). Keep every other compilerOption byte-identical. Reference: [research.md](./research.md) §1.
- [X] T005 [P] Create `app/frontend/next-env.d.ts` with the standard Next.js content (`/// <reference types="next" />` and `/// <reference types="next/image-types/global" />` plus the auto-managed comment). This file is committed; Next.js maintains it on `pnpm dev` runs.
- [X] T006 [P] Create `app/frontend/next.config.ts` with a minimal config: `import type { NextConfig } from "next"; const nextConfig: NextConfig = { reactStrictMode: true, experimental: { typedRoutes: true } }; export default nextConfig;`. No custom webpack, no rewrites, no headers — those arrive with the first task that needs them. Reference: [research.md](./research.md) §1.
- [X] T007 [P] Create `app/frontend/postcss.config.mjs` with `export default { plugins: { tailwindcss: {}, autoprefixer: {} } };`.
- [X] T008 [P] Create `app/frontend/tailwind.config.ts`: import `tokens` from `./src/design/tokens`; export a `Config` with (a) `content: ["./src/**/*.{ts,tsx}"]`; (b) `theme.spacing` set to a complete OVERRIDE object derived from `tokens.space` (per `docs/design/tokens/spacing.md` Export note — no `extend`); (c) `theme.extend.colors`, `theme.extend.fontSize`, `theme.extend.fontFamily`, `theme.extend.borderRadius`, `theme.extend.transitionDuration` all reading from the corresponding `tokens.*` branches; (d) `darkMode: "class"` — and the line MUST carry an inline comment in the committed file: `// intentionally no-op at MVP: visual-discipline pre-commit blocks "dark:" variants (FR-010); future dark mode is a deliberate project (design principle §6), not a flag.` This comment is the contract — the value `"class"` would otherwise look like opt-in dark-mode preparation, contradicting the spec assumption "A future dark mode is a deliberate project, not a flag" (`spec.md` Assumptions). (e) empty `plugins: []`. Reference: [research.md](./research.md) §2; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 2; spec Assumptions "Stack" + design principle §6.
- [X] T009 [P] Create `app/frontend/src/design/tokens.ts` as a placeholder: `// AUTO-GENERATED by app/frontend/scripts/generate-tokens.ts — do not edit by hand.\nexport const tokens = { colors: {}, space: { 0: "0px" }, fontSize: {}, fontFamily: {}, borderRadius: {}, transitionDuration: {} } as const;\nexport type Tokens = typeof tokens;`. The placeholder lets `tailwind.config.ts` import resolve and `tsc --noEmit` pass in Foundational; US2 (T015) replaces the body with the generator's real output. Reference: [data-model.md](./data-model.md) entity 3.
- [X] T010 [P] Create `app/frontend/src/lib/cn.ts`: `import { clsx, type ClassValue } from "clsx"; import { twMerge } from "tailwind-merge"; export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)); }`. Standard shadcn helper; later primitives (US3) and shell components (US1) import from `@/lib/cn`. Reference: [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3.
- [X] T011 [P] Create `app/frontend/src/app/globals.css`: at the top three Tailwind directives (`@tailwind base; @tailwind components; @tailwind utilities;`); then the empty marker block exactly `/* TOKENS:START — generated by scripts/generate-tokens.ts, do not edit */\n:root {\n}\n/* TOKENS:END */` — US2 (T015) populates the variables between the markers. Reference: [data-model.md](./data-model.md) entity 4; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 2 channel B.
- [X] T012 Create `app/frontend/src/app/layout.tsx` as a minimal placeholder: `import "@/app/globals.css"; export const metadata = { title: "TechScreen" }; export default function RootLayout({ children }: { children: React.ReactNode }) { return (<html lang="uk"><body className="bg-surface-base text-content-primary antialiased">{children}</body></html>); }`. The real `<Shell>{children}</Shell>` wrapping is added by US1 (T024). Depends on T011 logically (imports `globals.css`). Reference: [data-model.md](./data-model.md) entity 1.
- [X] T013 [P] Create `app/frontend/src/app/page.tsx`: `export default function Home() { return (<main className="p-6"><p className="text-content-secondary">TechScreen — admin shell stub.</p></main>); }`. This is the route content the chrome will surround in US1; it stays as a stub at T03 close.
- [X] T014 [P] Create `app/frontend/eslint.config.mjs` (flat config): import `next/core-web-vitals` and the existing T01 base; export an array combining the two; disable rules irrelevant to App Router (e.g., the no-html-link-for-pages rule for the App Router is already off in `next/core-web-vitals`). Keep `--max-warnings=0` policy from T01. Reference: [research.md](./research.md) §1.
- [X] T015 [P] Create `app/frontend/jest.config.ts` using the `next/jest` factory: `import nextJest from "next/jest"; const createJestConfig = nextJest({ dir: "./" }); export default createJestConfig({ setupFilesAfterEach: ["./jest.setup.ts"], testEnvironment: "jsdom", testMatch: ["<rootDir>/src/__tests__/**/*.{test,spec}.{ts,tsx}"], moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" } });`. Reference: [research.md](./research.md) §6.
- [X] T016 [P] Create `app/frontend/jest.setup.ts`: `import "@testing-library/jest-dom";`. The single import wires the custom RTL matchers (`toBeInTheDocument`, `toHaveFocus`, etc.) the smoke test relies on.
- [X] T017 [P] Create the i18n placeholder triple under `app/frontend/src/messages/`: (a) `uk.json` containing exactly `{ "wordmark.alt": "N-iX TechScreen" }`; (b) `en.json` containing exactly `{ "wordmark.alt": "N-iX TechScreen" }`; (c) `README.md` explaining: "T03 marker only — no i18n runtime is wired. The first task that ships real Ukrainian copy (T20 candidate session) picks the runtime mechanism (`next-intl`, `react-intl`, or built-in Next i18n) and may freely reshape this directory or move the JSON files." None of these are imported at T03 close. Reference: [research.md](./research.md) §8; spec Q4 clarification.
- [X] T018 [P] Delete `app/frontend/tooling.d.ts`. The file's purpose ("placeholder marker until real .ts/.tsx exist") is now obsolete because T005, T009, T010, etc. ship real TS sources. Reference: [plan.md](./plan.md) "Source Code" tree.

**Checkpoint**: `pnpm --dir app/frontend install` succeeds; `pnpm --dir app/frontend lint` exits 0 (with the placeholder tokens.ts and the placeholder layout); `pnpm --dir app/frontend dev` boots Next.js on port 3000 and `curl http://127.0.0.1:3000/` returns HTTP 200 (page shows "TechScreen — admin shell stub." plus the default Tailwind reset). The structural rails are in place; story phases now fill them.

---

## Phase 3: User Story 2 — Design tokens are the single source of truth (Priority: P1) 🎯 MVP slice 1 of 4

**Goal**: `app/frontend/src/design/tokens.ts` and the marker-bracketed region of `app/frontend/src/app/globals.css` are produced deterministically from `docs/design/tokens/*.md` by a committed generator. Drift between any of the three artefacts fails a Jest test and a pre-commit hook before merge.

**Independent Test**: From the branch with Phase 2 complete, run `docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check` (or, until the Docker setup lands in Polish, `pnpm --dir app/frontend tokens:check`); expect exit 0 with no diff. Run `pnpm --dir app/frontend test -- --testPathPattern tokens.test.ts`; expect green in < 5 s. Mutate one row in `docs/design/tokens/colors.md`, re-run the check, expect exit 1 with a unified-diff head identifying the role; revert. Acceptance Scenarios 1–3 in [spec.md](./spec.md) US2.

### Implementation for User Story 2

- [X] T019 [US2] Create `app/frontend/scripts/generate-tokens.ts`: a TS-on-Node script (run via `tsx`) that (a) walks `docs/design/tokens/*.md`, parses each role table by reading rows of the shape `| token-path | value | … |` (skip header and separator rows), and produces a normalised `{ [path]: value }` map; (b) builds an `as const`-typed nested object literal grouping by the dotted path's first segment (`colors`, `space`, `fontSize`, `fontFamily`, `borderRadius`, `transitionDuration`) and writes it to `app/frontend/src/design/tokens.ts` with the auto-generated header comment; (c) builds the CSS-vars block under `:root` with **two layers** in the order specified by [research.md](./research.md) §4 + [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 2 channel B: **first** the semantic-role layer (each markdown role → `--<role-with-hyphens>: <value>;`, colours converted to space-separated HSL triplets via a small inline `hexToHsl` helper), **then** a `/* shadcn aliases */` sub-comment, **then** the shadcn-alias layer (every row from research §4 "Role-to-shadcn alias mapping" → `--<shadcn-name>: var(--<our-role>);`); writes the assembled block between `/* TOKENS:START — generated by scripts/generate-tokens.ts, do not edit */` and `/* TOKENS:END */` markers in `app/frontend/src/app/globals.css`; everything outside the markers is preserved byte-for-byte. The role-to-alias mapping is **embedded in the script as a typed const** (single source-of-truth in the script body, mirroring the table in research §4) so that adding a new mapping is one localised edit. (d) supports a `--check` CLI flag that runs the same logic in memory and exits 1 with a unified-diff head (first ~40 lines via `node:diff` or a small `diffLines` helper) if either output file would change. Determinism: same input → same output bytes on any machine. Reference: [research.md](./research.md) §4 + the role-to-shadcn alias mapping table; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 2 channel B; [data-model.md](./data-model.md) entity 5.
- [X] T020 [US2] Run `pnpm --dir app/frontend tokens:generate` (after T019). The command writes the populated `app/frontend/src/design/tokens.ts` (replacing the Foundational placeholder body) and populates the marker region of `app/frontend/src/app/globals.css` with **both** the semantic-role layer and the shadcn-alias layer (the latter as `var(...)` pointers). Commit both files exactly as produced. Confirm idempotency by running the command twice and `git diff --stat` showing zero changes the second time. Spot-check the `globals.css` output: every shadcn alias from the research §4 table appears as a `--<shadcn-name>: var(--<our-role>);` line under the `/* shadcn aliases */` sub-comment; at minimum `--background`, `--foreground`, `--primary`, `--ring` MUST be present (without these, US3's shadcn primitives would not resolve their referenced vars at runtime). Reference: [data-model.md](./data-model.md) entities 3 and 4; [research.md](./research.md) §4 mapping table.
- [X] T021 [US2] Create `app/frontend/src/__tests__/tokens.test.ts`: a Jest test `tokens artefacts match the generator output` that imports the generator module's pure functions (e.g., `buildTokensTs()` and `buildCssBlock()`), reads the on-disk `tokens.ts` and the marker-bracketed region of `globals.css`, and asserts byte-equality against the regenerated outputs. On failure, the assertion message includes the first ~40 lines of `unified diff`. The file MUST start with the per-file Jest annotation `/** @jest-environment node */` so this drift test runs in the lightweight `node` environment (file-I/O only, zero DOM access) — overriding the project-wide `jsdom` default set in `jest.config.ts` (T015). Saves jsdom startup cost (~150 ms) on every test run; matters at the Phase-7 `pnpm test` SC-002 budget. Mirrors T02's `test_openapi_regeneration.py` pattern. Reference: [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 4; [data-model.md](./data-model.md) entity 8; [research.md](./research.md) §6.
- [X] T022 [US2] Edit `.pre-commit-config.yaml`: add a new `local` repo block with a hook `id: tokens-drift`, `name: "tokens drift (frontend)"`, `language: system`, `pass_filenames: false`, `files: ^(docs/design/tokens/.*\\.md|app/frontend/src/design/tokens\\.ts|app/frontend/src/app/globals\\.css|app/frontend/scripts/generate-tokens\\.ts)$`, `entry: bash -c 'cd app/frontend && pnpm tokens:check'`. Place it alongside the existing `eslint` local hook to keep all frontend hooks in one section. Reference: [research.md](./research.md) §5; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 4.
- [X] T023 [US2] Validate US2 acceptance: run `pnpm --dir app/frontend test -- --testPathPattern tokens.test.ts` (expect green). Run `pnpm --dir app/frontend tokens:check` (expect exit 0). Deliberately mutate `#E8573C` → `#FF0000` in `docs/design/tokens/colors.md`, re-run `pnpm tokens:check` (expect exit 1 with diff head identifying `colors.brand.primary`); `git checkout -- docs/design/tokens/colors.md` to revert. Run `pre-commit run tokens-drift --all-files` (expect green). Record the wall-clock time of `pnpm tokens:check` for SC-003 verification (must be < 5 s).

**Checkpoint**: tokens.ts and globals.css are populated; the drift Jest test is green; the `tokens-drift` pre-commit hook is wired; T03 design-system source-of-truth is enforceable. US3 can now begin (it adds primitives that consume these tokens via Tailwind utilities and CSS variables).

---

## Phase 4: User Story 3 — Visual discipline is enforceable, not aspirational (Priority: P1) 🎯 MVP slice 2 of 4

**Goal**: The shadcn primitive inventory (nine primitives) is committed under `app/frontend/src/components/ui/`, importable via `@/components/ui/*`, and styled exclusively through token-backed Tailwind utilities and CSS variables. A pre-commit hook flags raw hex outside the token files and any `dark:` Tailwind variant anywhere in the frontend tree.

**Independent Test**: Inspect `app/frontend/src/components/ui/` — nine TSX primitive files present. Run `bash app/frontend/scripts/check-visual-discipline.sh` (expect exit 0). Inject `bg-[#ff0000]` into a stub file under `app/frontend/src/`, re-run, expect exit 1 with file:line; revert. Same for `dark:bg-foo`. Acceptance Scenarios 1–4 in [spec.md](./spec.md) US3.

### Implementation for User Story 3

- [X] T024 [US3] Create `app/frontend/components.json` exactly: `{"$schema":"https://ui.shadcn.com/schema.json","style":"new-york","rsc":true,"tsx":true,"tailwind":{"config":"tailwind.config.ts","css":"src/app/globals.css","baseColor":"neutral","cssVariables":true},"aliases":{"components":"@/components","ui":"@/components/ui","utils":"@/lib/cn","lib":"@/lib"},"iconLibrary":"lucide"}`. Commit. The shadcn CLI in T025 reads this file. Reference: [research.md](./research.md) §3; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3.
- [X] T025 [US3] Install the nine shadcn primitives following the **Post-install procedure** in [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3 verbatim. Concretely: (1) snapshot `globals.css` to `/tmp/globals.css.before-shadcn`; (2) confirm T020 has already run (the alias layer must be present in `globals.css` before shadcn can resolve its expected vars — without it primitives render as transparent / unstyled); (3) from the repo root run `pnpm dlx shadcn@latest add button card input label dialog dropdown-menu tooltip popover table` (one invocation, all nine primitives, reads `components.json`); (4) `diff /tmp/globals.css.before-shadcn app/frontend/src/app/globals.css` — expected empty diff (CLI does not rewrite once `cssVariables: true` is set and aliases already exist); if the CLI did rewrite, revert from the snapshot and stop. The CLI writes `app/frontend/src/components/ui/{button,card,input,label,dialog,dropdown-menu,tooltip,popover,table}.tsx`. Inspect each file: every Tailwind utility / CSS-var reference must resolve through the alias layer (`bg-primary`, `text-foreground`, `ring-ring`, etc.); zero raw hex. If any primitive contains a raw hex value, report and stop. Commit all nine files. Reference: [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3 "Post-install procedure" steps 1–4 + 7.
- [X] T025a [US3] Verify alias coverage (Post-install procedure step 5 from [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3): run `for v in $(grep -oE 'var\(--[a-z-]+\)' app/frontend/src/components/ui/*.tsx | grep -oE '\-\-[a-z-]+' | sort -u); do grep -q "$v" app/frontend/src/app/globals.css || echo "MISSING: $v"; done` from the repo root. Expected: zero `MISSING:` lines. If any variable is missing, the shadcn template references a CSS var our generator has not aliased yet — extend the role-to-shadcn mapping in [research.md](./research.md) §4 with a new row, extend the corresponding markdown role in `docs/design/tokens/colors.md` if needed, re-run `pnpm tokens:generate`, re-run this verification. Loop until zero misses. Then run `pnpm --dir app/frontend dev` (or `pnpm build` headless), open `http://127.0.0.1:3000/`, and visually confirm Button (the only primitive consumed at T03 by `sidebar.tsx`) renders with the expected brand-orange primary fill on hover/focus — confirming the alias layer wires correctly end-to-end. Reference: [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 3 "Post-install procedure" steps 5–6.
- [X] T026 [P] [US3] Create `app/frontend/scripts/check-visual-discipline.sh` (bash, executable `chmod +x`): two ripgrep searches over `app/frontend/src/`. (a) Raw hex: `rg -n -t ts -t tsx -t js -t jsx -t css -t scss -e '#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b' app/frontend/src/ -g '!**/design/tokens.ts' -g '!**/app/globals.css'` — non-zero exit (in the script) on any match, with a one-line summary `visual-discipline: raw hex outside the token file` plus the file:line list, then `exit 1`. (b) `dark:` variant: `rg -n -t ts -t tsx -t js -t jsx -t css -t scss -e '\bdark:[a-z]' app/frontend/src/` — same treatment. Both clean → script `exit 0` with no output. Reference: [research.md](./research.md) §6; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 5.
- [X] T027 [US3] Edit `.pre-commit-config.yaml`: add a `local` hook `id: visual-discipline`, `name: "visual discipline (frontend)"`, `language: system`, `pass_filenames: false`, `files: ^app/frontend/src/.*\\.(ts|tsx|js|jsx|css|scss)$`, `entry: bash app/frontend/scripts/check-visual-discipline.sh`. Place alongside the `tokens-drift` and `eslint` local hooks.
- [X] T028 [US3] Validate US3 acceptance: (a) primitives importable — write a one-line stub in `app/frontend/src/__tests__/.scratch.tsx` that imports each of the nine primitives and renders one of them, run `pnpm --dir app/frontend lint` (expect exit 0, zero compile errors — SC-009), then `rm app/frontend/src/__tests__/.scratch.tsx`. (b) Visual-discipline raw-hex case: write `export const oops = "#ff0000";` to `app/frontend/src/oops.ts`, run `pre-commit run visual-discipline --all-files` (expect exit 1 with file:line), `rm app/frontend/src/oops.ts`. (c) Visual-discipline dark: case: write `export const oops = "dark:bg-red-500";` to `app/frontend/src/oops.ts`, re-run (expect exit 1), `rm app/frontend/src/oops.ts`. (d) Run `bash app/frontend/scripts/check-visual-discipline.sh` (expect exit 0 in < 5 s — SC-004). Reference: [quickstart.md](./quickstart.md) Steps 6 + 7.

**Checkpoint**: nine shadcn primitives committed; visual-discipline guardrail wired and exercised; FR-007 + FR-008 enforceable on every later frontend PR. US1 can now compose the shell using the Button primitive.

---

## Phase 5: User Story 1 — The frontend application boots and renders the admin shell (Priority: P1) 🎯 MVP slice 3 of 4

**Goal**: Browsing `/` shows the admin shell — N-iX wordmark in brand orange in the top bar, `surface.raised` left sidebar with focusable nav stub items, content slot consistent with the Chat-iX reference. The chrome lives in the root layout `app/layout.tsx` so every later route inherits it.

**Independent Test**: From the branch with Phases 2–4 complete, run `pnpm --dir app/frontend dev`, open `http://127.0.0.1:3000/`, confirm the wordmark, sidebar items, and content slot render and match `docs/design/references/hellow_page.png` visually. Acceptance Scenarios 1–3 in [spec.md](./spec.md) US1.

### Implementation for User Story 1

- [X] T029 [P] [US1] Create `app/frontend/src/components/shell/top-bar.tsx`: a stateless server component rendering a `<header>` with `surface.base` background, 1-px `border.subtle` bottom divider, height ~64 px (`h-16`), horizontal padding `space.6` (`px-6`); inside, the N-iX wordmark on the left as `<span className="font-semibold text-brand-primary">N-iX TechScreen</span>` (the `bg-brand-primary` token role IS brand orange — the only orange slot exercised at T03 alongside the focus ring). Right side empty for T03 (user menu / search slots arrive with later tasks). Reference: [data-model.md](./data-model.md) entity 2; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 1.
- [X] T030 [P] [US1] Create `app/frontend/src/components/shell/sidebar.tsx`: a stateless server component rendering an `<aside>` with `surface.raised` background, 1-px `border.subtle` right divider, width ~240 px (`w-60`), padding `p-4`; inside, a `<nav>` with `<ul>` and three placeholder `<li>` items each rendered through `<Button variant="ghost" className="w-full justify-start">…</Button>` (imports from `@/components/ui/button`). Stub labels: "Dashboard", "Sessions", "Settings". Each Button is keyboard-focusable by default (Button primitive); the focus ring uses `--ring` which maps to brand orange (the second orange slot exercised at T03). Reference: [data-model.md](./data-model.md) entity 2; FR-009 + FR-012.
- [X] T031 [US1] Create `app/frontend/src/components/shell/shell.tsx`: `import { TopBar } from "./top-bar"; import { Sidebar } from "./sidebar"; export function Shell({ children }: { children: React.ReactNode }) { return (<div className="min-h-screen flex flex-col bg-surface-base text-content-primary"><TopBar /><div className="flex flex-1 min-h-0"><Sidebar /><main className="flex-1 min-w-0">{children}</main></div></div>); }`. Composes top-bar + sidebar + content slot per the Chat-iX baseline. Depends on T029 and T030. Reference: [data-model.md](./data-model.md) entity 2.
- [X] T032 [US1] Edit `app/frontend/src/app/layout.tsx`: replace the placeholder `<body>{children}</body>` from Foundational T012 with `<body className="bg-surface-base text-content-primary antialiased"><Shell>{children}</Shell></body>` (import `Shell` from `@/components/shell/shell`). The chrome is now inherited by every later route. Reference: spec Q1 clarification; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 1.
- [X] T033 [US1] Validate US1 acceptance: `pnpm --dir app/frontend dev` (expect "ready on http://localhost:3000" within 10 s — Acceptance Scenario 1, SC-001). In a browser, open `http://127.0.0.1:3000/`: (a) wordmark "N-iX TechScreen" rendered in brand orange in the top bar; (b) sidebar with three nav stub items, focus ring visible on Tab; (c) content slot shows "TechScreen — admin shell stub." (Acceptance Scenarios 2–3, FR-002, FR-009). Compare against `docs/design/references/hellow_page.png`: brand orange visible only on the wordmark and the focus ring (FR-008, SC-007). Stop the dev server.

**Checkpoint**: chrome is live. Every later screen task can now write only its `app/<route>/page.tsx` and inherit the shell automatically.

---

## Phase 6: User Story 4 — A frontend test suite and a smoke test convention (Priority: P2)

**Goal**: A committed admin-shell smoke test mounts the root layout through Next.js's real rendering pipeline and asserts (a) the wordmark renders, (b) the sidebar nav items render, (c) keyboard tab navigation moves focus across the items and the focus ring is rendered. The test runs as part of `pnpm test`.

**Independent Test**: Run `pnpm --dir app/frontend test -- --testPathPattern shell.test.tsx`; expect green in < 5 s; the test exercises FR-011(a)/(b)/(c). Acceptance Scenarios 1–2 in [spec.md](./spec.md) US4.

### Implementation for User Story 4

- [X] T034 [US4] Create `app/frontend/src/__tests__/shell.test.tsx`: an RTL test that imports `Shell` from `@/components/shell/shell` and renders it through `@testing-library/react`'s `render(<Shell><p>content</p></Shell>)`. Per FR-011 (and the spec Clarifications "What counts as the application's real rendering pipeline" Q&A), `<Shell>` IS the chrome layer — `app/layout.tsx` is a one-line `<body><Shell>{children}</Shell></body>` wrapper around it — so mounting `<Shell>` exercises the full chrome composition (`<TopBar>` + `<Sidebar>` + 3× shadcn `<Button>`) through the Next.js compiler (via `next/jest`) and JSDOM. Three assertions: (1) `screen.getByText(/N-iX TechScreen/i)` is in the document (FR-011a); (2) `screen.getAllByRole("button", { name: /Dashboard|Sessions|Settings/i })` returns at least three elements (FR-011b); (3) using `userEvent.tab()` repeatedly, focus advances through the sidebar buttons in order, and the active element receives `:focus-visible` (`expect(document.activeElement).toBe(...)` for each, plus a `expect(document.activeElement).toHaveStyle({ outline: ... })` or equivalent class-based check confirming the focus ring renders — FR-011c). Reference: spec FR-011 + Clarifications Q on rendering pipeline; [contracts/frontend-contract.md](./contracts/frontend-contract.md) Surface 4 chrome smoke + [data-model.md](./data-model.md) entity 7.
- [X] T035 [US4] Validate US4 acceptance: run `pnpm --dir app/frontend test` (expect both `tokens.test.ts` from US2 and `shell.test.tsx` from US4 collected, both green, total wall-clock < 60 s — SC-002). Deliberately remove the wordmark `<span>` from `top-bar.tsx`, re-run, confirm `shell.test.tsx` fails with a `getByText` "not found" error; revert.

**Checkpoint**: All four user stories functional. `pnpm test` reports two committed tests, both green. The frontend test convention (location, fixture-free RTL pattern) is established for every later screen task to copy.

---

## Phase 7: Polish & Docker parity (post-implementation)

**Purpose**: Close the §7 Docker-parity gap that Phases 1–6 left open by quietly using a host-side `pnpm` path. Mirrors T02's Phase 8 pattern: implementation done first, Docker canonicalisation second. Also ships the README dev-loop subsection, deletes the i18n READme typo if any, and runs the final guardrail sweep + diff audit.

**Why post-implementation rather than reordered into Phase 1**: T03 acceptance criteria from `implementation-plan.md` are tool-agnostic (`pnpm dev serves /`, `Jest configured; one smoke test green`, `tokens.ts round-trips`). Phases 1–6 satisfy those criteria via the fastest available path (host `pnpm`). Phase 7 retrofits the canonical Docker workflow without altering source code or tests committed by earlier phases.

- [X] T036 [P] Create `Dockerfile.frontend` at the repo root with the multi-stage shape from [research.md](./research.md) §7: `FROM node:20-bookworm-slim AS base` (corepack pnpm@9.12.0); `FROM base AS deps` (`COPY package.json pnpm-lock.yaml ./` + `pnpm install --frozen-lockfile`); `FROM deps AS dev` (`COPY app/frontend/ ./`, `EXPOSE 3000`, `CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]`); `FROM deps AS build` (`pnpm build`); `FROM node:20-bookworm-slim AS runtime` (corepack pnpm@9.12.0; copy `.next`, `public`, `node_modules`, `package.json` from build; `CMD ["pnpm", "start"]`). Note: the `COPY package.json pnpm-lock.yaml ./` step in `deps` uses paths relative to the build context — use `app/frontend/package.json` and `app/frontend/pnpm-lock.yaml` from the repo-root context. Also extends root `.dockerignore` (added `.github/` and `specs/` — the file existed from a prior chunk; T036 brings it in line with the T036 caveat list so both Dockerfile and Dockerfile.frontend benefit from a shared exclude list).
- [X] T037 Edit `docker-compose.yml`: change the `frontend` service `build.target` from `build` to `dev` (the T02-stub value pointed at an intermediate stage); change `build.dockerfile` to `Dockerfile.frontend` (already correct); relax `depends_on.backend` from a bare `- backend` to `backend: { condition: service_started, required: false }` so the frontend boots without the backend per FR-003. Keep every other key (env vars, ports, volumes, command) byte-identical.
- [X] T038 [P] Edit `docker-compose.test.yml`: add a `frontend` service block targeting `dev`, that runs `pnpm test` non-interactively when invoked via `docker compose -f docker-compose.test.yml run --rm frontend pnpm test` (and the same for `pnpm tokens:check` and `pnpm lint`). Mirror the existing `backend` block's profile + volume conventions. The compose file already has the runner pattern from T02 — extend it.
- [X] T039 [P] Edit `README.md`: add a "Frontend dev loop (Docker-first)" subsection alongside the existing "Backend dev loop (Docker-first)" section (added by T02). Three commands, each in a code-fenced block: **"Run the frontend"** (`docker compose --profile web up -d frontend && open http://127.0.0.1:3000`); **"Run the frontend tests"** (`docker compose -f docker-compose.test.yml run --rm frontend pnpm test`); **"Regenerate design tokens"** (`docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:generate` plus a note about `pnpm tokens:check` and the `tokens-drift` pre-commit hook). Add a callout that native `pnpm --dir app/frontend …` is intentionally undocumented as the canonical path — Docker is canonical (constitution §7).
- [X] T040 Run [quickstart.md](./quickstart.md) Steps 2–8 end-to-end as the reviewer would (Docker build, dev loop, in-container tests, drift check, visual-discipline check, in-container lint+tsc, host pre-commit). Any step that fails is a merge-blocker. Record the Step 2 build wall-clock time and the Step 4 test wall-clock time for SC-001 / SC-002 verification in the PR description.
- [X] T041 [P] Run the T01 + T02 + T03 guardrail contract: `pre-commit run --all-files` AND `docker compose -f docker-compose.test.yml run --rm frontend pnpm run lint` AND `docker compose -f docker-compose.test.yml run --rm frontend pnpm test`. All three MUST exit 0 on the post-T03 tree (FR-014, SC-008). If anything fails idempotency on second run (e.g., a generator producing different bytes), report and fix before proceeding. (Note: the lint command is `pnpm run lint` rather than `sh -c 'pnpm exec eslint . && tsc --noEmit'` — the chained form fails because `tsc` is not on PATH in the second `sh -c` segment; `pnpm run lint` invokes the same chain via the package.json script with `node_modules/.bin` on PATH for both binaries. Quickstart Step 7 was updated to match.)
- [X] T042 Run the T03 diff audit: `git diff --stat origin/main..HEAD` and confirm the changed file set matches the [quickstart.md](./quickstart.md) Step 9 "Diff-walk the PR" table. Any file outside that list (particularly: any auth code; any candidate-facing screen under `app/<route>/`; any generated OpenAPI client; any `dark:` styling; any motion library import; any analytics, telemetry, or third-party script; any `Dockerfile`/`docker-compose*.yml` change beyond the two flagged in T037–T038) is a FR-013 scope-fence violation and a merge-blocker. Document any intentional exception in the PR description. (Two intentional additions to the expected surface: (1) `.gitignore` adds `*.tsbuildinfo` so the TypeScript incremental cache is no longer tracked — it was accidentally staged in a prior chunk; (2) `.specify/feature.json` flips from `005-t02-fastapi-skeleton` to `006-t03-nextjs-skeleton`, expected for a Spec Kit feature switch.)

**Checkpoint**: §7 parity is no longer aspirational — every documented frontend command executes inside the canonical container; the `dev` Dockerfile.frontend stage and updated compose files are committed; the README and every spec doc agree on the Docker-only contract; the diff audit confirms FR-013 scope-fence is intact. T03 is ready for `reviewer` sub-agent handoff and then merge.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup** (T001): no dependencies.
- **Phase 2 Foundational** (T002–T018): depends on Setup. T002 blocks T003; T003 blocks T004–T018. T012 depends on T011 (imports `globals.css`) but is also `[P]` in the sense of "different files, no in-phase blocker that fails compile". T004–T018 can be opened in any order relative to each other once T003 lands.
- **Phase 3 US2** (T019–T023): depends on Foundational (needs `tokens.ts` placeholder + `globals.css` markers + Jest config + the package's `tokens:generate` script). T020 depends on T019; T021 depends on T019 (imports the generator's pure functions); T022 depends on T019 (the hook calls `pnpm tokens:check`); T023 depends on T020+T021+T022.
- **Phase 4 US3** (T024–T028): depends on Foundational (needs `tailwind.config.ts` + `globals.css` + `lib/cn.ts`) and on US2 (the shadcn primitives reference the CSS-vars **alias layer** emitted by US2's generator — `--background`, `--foreground`, `--primary`, `--ring`, etc. only exist after T020 produces both the semantic-role and the shadcn-alias layers per [research.md](./research.md) §4). T025 depends on T024 (CLI reads `components.json`) and on T020 (alias layer must be present before install); T025a depends on T025 (verifies alias coverage of installed primitives); T026, T027 are **independent** of T025/T025a and can run before primitives land — they will simply scan the smaller tree; for sequence reasons inside one PR they are listed after T025a; T028 depends on T025+T025a+T026+T027.
- **Phase 5 US1** (T029–T033): depends on Foundational + US2 + US3. T029, T030 are `[P]` — different files. T031 depends on T029+T030 (imports both). T032 depends on T031 (imports `Shell`). T033 depends on T032.
- **Phase 6 US4** (T034–T035): depends on Foundational (Jest config) + US1 (mounts `<Shell>`). T035 depends on T034.
- **Phase 7 Polish** (T036–T042): depends on every prior phase. T036, T038, T039, T041 are `[P]`. T037 depends on T036 (target name `dev` must exist). T040 depends on T036+T037+T038. T042 is the final gate.

### User-story dependencies

- **US2** (tokens) is functionally the design-system source-of-truth. No dependency on US1, US3, US4.
- **US3** (primitives + visual discipline) depends on US2's generator output for CSS-variable names that the primitives reference (`--primary`, `--ring`, etc.). No dependency on US1 or US4.
- **US1** (admin shell) depends on US2 (token-backed Tailwind utilities like `bg-surface-base`) and US3 (the Button primitive used inside `sidebar.tsx`). No dependency on US4.
- **US4** (smoke test) depends on US1 (the test mounts `<Shell>`). No dependency on US2 or US3.

The implementation order is therefore reverse-priority for the three P1 stories: US2 → US3 → US1 → US4. Each story's **acceptance** remains independently testable per its `Independent Test` clause; the dependencies are implementation-level.

### Within each phase

- `[P]`-marked tasks inside a phase may be opened in any order.
- Non-`[P]` tasks inside a phase are strictly sequential.

### Parallel opportunities within this task set

- **Phase 2 Foundational**: T004, T005, T006, T007, T008, T009, T010, T011, T013, T014, T015, T016, T017, T018 are all `[P]` once T003 lands (different files; no in-phase compile-breaking dependency). T012 logically follows T011 but is small enough to coexist.
- **Phase 3 US2**: T021 (`tokens.test.ts`) and T022 (pre-commit hook entry) are independent of each other once T019 lands; both depend on T020's regenerated artefacts.
- **Phase 4 US3**: T026 (visual-discipline script) is independent of T025 (shadcn install) and could be opened in parallel; we list it after for narrative coherence.
- **Phase 5 US1**: T029 and T030 are `[P]` — `top-bar.tsx` and `sidebar.tsx` are independent files.
- **Phase 7 Polish**: T036, T038, T039 are `[P]` — different files; T041 is `[P]` (read-only validations); T037 depends on T036; T040, T042 are sequential.

**Constitution §18 reminder**: the `parallel: true` annotation in the implementation plan for T03 refers to T03 running concurrently with **other tasks** (T02 backend skeleton, T04 Vertex wrapper, T06 Cloud Run after T01 lands), not to sub-agent fan-out **inside** T03. Every task below is executed by one `frontend-engineer` agent sequentially.

---

## Parallel Example: Phase 2 Foundational

Once T003 (`pnpm install`) completes, the remaining Foundational files are independent and can be opened in any order:

```bash
# Open any order — none depends on the others (T012 logically follows T011 but the file write is independent).
Task: "T004 — edit app/frontend/tsconfig.json (paths alias, includes)"
Task: "T005 — create app/frontend/next-env.d.ts (Next.js standard)"
Task: "T006 — create app/frontend/next.config.ts (minimal)"
Task: "T007 — create app/frontend/postcss.config.mjs"
Task: "T008 — create app/frontend/tailwind.config.ts (theme.extend + spacing OVERRIDE)"
Task: "T009 — create app/frontend/src/design/tokens.ts (placeholder body)"
Task: "T010 — create app/frontend/src/lib/cn.ts (clsx+tailwind-merge)"
Task: "T011 — create app/frontend/src/app/globals.css (Tailwind directives + empty TOKENS markers)"
Task: "T012 — create app/frontend/src/app/layout.tsx (placeholder, no Shell yet)"
Task: "T013 — create app/frontend/src/app/page.tsx (stub content)"
Task: "T014 — create app/frontend/eslint.config.mjs (extends next/core-web-vitals)"
Task: "T015 — create app/frontend/jest.config.ts (next/jest factory)"
Task: "T016 — create app/frontend/jest.setup.ts (jest-dom import)"
Task: "T017 — create app/frontend/src/messages/{uk,en}.json + README.md"
Task: "T018 — delete app/frontend/tooling.d.ts"

# Phase 3 (T019) can start only after Foundational completes.
```

---

## Implementation Strategy

### Single-PR MVP (all four stories)

T03 is a single-PR task per the implementation plan. It does not ship incrementally — the acceptance clause requires `pnpm dev serves admin shell + Jest+RTL configured + one smoke test green + tokens.ts round-trips + visual-discipline hooks pass` as one set. Recommended order:

1. Complete Phase 1 Setup (T001).
2. Complete Phase 2 Foundational (T002–T018).
3. Complete Phase 3 US2 (T019–T023) — generator + tokens.ts + globals.css + drift detection.
4. Complete Phase 4 US3 (T024–T025a + T026–T028) — primitives + visual-discipline guardrail.
5. Complete Phase 5 US1 (T029–T033) — admin shell wired into root layout.
6. Complete Phase 6 US4 (T034–T035) — admin-shell smoke test.
7. Complete Phase 7 Polish (T036–T042) — Docker parity + README + validation + diff audit.

Each story is still independently testable per its `Independent Test` in [spec.md](./spec.md) — a reviewer can run a single story's test in isolation (`pnpm test -- --testPathPattern tokens.test.ts` for US2; `pnpm test -- --testPathPattern shell.test.tsx` for US1+US4) and get a clean pass/fail.

### Rollback posture

Every task in this list is a pure file edit, a deterministic re-runnable command (`pnpm install`, `pnpm tokens:generate`, `pnpm dlx shadcn@latest add …`), or a validation step. Reverting T03 is a single `git revert` of the T03 commit(s) — no data migration, no Cloud Run state change (the T06 Cloud Run frontend service does not exist yet), no Vertex state change (§19 rollback as first-class).

### Handoff to `reviewer`

When Phase 7 is green, hand off to the `reviewer` sub-agent with: (a) [quickstart.md](./quickstart.md) as the validation script, (b) the Phase 7 T042 diff audit as the scope-fence check, (c) the T03 acceptance clause in `implementation-plan.md` as the external acceptance reference. No additional context needed.

---

## Notes

- Every `[P]` task in this file edits a different file; no task requires a sub-agent other than `frontend-engineer`.
- File paths are relative to the repo root.
- Verify `quickstart.md` runs green before handing off for review.
- Commit cadence: one commit per phase is the default; larger PRs can be squashed at merge time. We commit manually (see [CLAUDE.md](../../CLAUDE.md) — `auto_commit: false`).
- Any task whose acceptance fails in a way not covered by the spec: surface the ambiguity to the user before working around it; do not silently broaden T03's scope (FR-013).
