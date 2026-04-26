# Phase 1 Data Model — T03 Next.js Skeleton

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-26

T03 introduces no persistent data (no tables, no client-side stores, no localStorage writes). The "entities" below are the in-process objects and committed artefacts the reviewer and every later frontend task must be able to point at. Each row maps an entity to the file that realises it in the PR and to the validation rule(s) that protect its contract.

---

## Entities

### 1. `RootLayout` — the chrome-bearing Next.js root layout

| Field             | Value                                                                                                                                                         |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition        | The default-export React Server Component that wraps every later route in the App Router. Composed of `<html>`, `<body>`, and a `<Shell>` that surrounds `{children}`. |
| File              | `app/frontend/src/app/layout.tsx`                                                                                                                              |
| Children slots    | One — `{children}` rendered inside `<Shell>`'s content slot.                                                                                                   |
| Boot preconditions | None — no `cookies()`, no `headers()`, no async data. Static rendering only at T03.                                                                            |
| Lifecycle         | Created at server-render time on every request; client-side it is hydrated once and persists across client-side navigations between sub-routes (the chrome does not re-mount). |
| Validation        | `pnpm dev` serves the chrome on `/` (FR-001, FR-002, SC-001). The smoke test renders this layout via the App Router test pattern and asserts the chrome elements are in the DOM (FR-011). |
| Stability         | The layout's role as "chrome host" is **frozen**: any later screen task adds its own `app/<route>/page.tsx` and inherits the chrome. Re-locating the chrome out of `app/layout.tsx` requires a new spec + ADR. |

### 2. `Shell` (composed of `TopBar` + `Sidebar` + content slot)

| Field          | Value                                                                                                                                                          |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition     | A presentation React component that arranges the `<TopBar />`, the `<Sidebar />`, and a content slot (rendered as `{children}`) into the Chat-iX visual baseline (white canvas, surface.raised sidebar, 1-px subtle dividers). |
| File           | `app/frontend/src/components/shell/shell.tsx` (composition root). `top-bar.tsx` and `sidebar.tsx` live alongside.                                              |
| Sub-components | `<TopBar />` — top bar with the N-iX wordmark in brand orange (the only orange slot exercised at T03). `<Sidebar />` — left nav stub items, focusable list (the keyboard-tab target for FR-011(c)). |
| Validation     | Smoke test asserts: (a) wordmark text present; (b) sidebar nav items present; (c) `userEvent.tab()` cycles focus through the sidebar items and the focus ring renders (FR-011, FR-012). |
| Stability      | Component file paths are **stable** (`@/components/shell/{shell,top-bar,sidebar}`). Sub-components added later (user menu, nav-item icons, breadcrumbs) extend the shell via composition; the existing files are not renamed. |

### 3. `DesignTokenExport` (`tokens.ts`) — typed token object

| Field            | Value                                                                                                                                                       |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition       | The TypeScript module that exports the design token tree as an `as const` object literal. Consumed by `tailwind.config.ts` (via `theme.extend`) and indirectly by `globals.css` (the same generator emits the CSS-vars block from the same source). |
| File             | `app/frontend/src/design/tokens.ts` — **GENERATED, do not hand-edit**.                                                                                       |
| Producer         | `app/frontend/scripts/generate-tokens.ts` (run via `pnpm tokens:generate`).                                                                                  |
| Source of truth  | `docs/design/tokens/*.md` (markdown role tables; canonical per FR-006).                                                                                      |
| Schema           | Nested object with the same dot-paths as the markdown role names — `colors.brand.primary`, `colors.surface.base`, `space.4`, `radius.md`, `typography.body`, `motion.fast`, etc. |
| Validation       | Token-drift Jest test asserts byte-equality between the on-disk file and the in-memory regenerated bytes (FR-006, SC-003). The pre-commit `tokens-drift` hook does the same.                                            |
| Stability        | The role names are **stable** (they ARE the contract). Adding a new role to a markdown table is additive — additive changes propagate by re-running the generator. Removing a role is a breaking change requiring a new spec.                                                                |

### 4. `CSSCustomPropertiesBlock` — the generated section of `globals.css`

| Field             | Value                                                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Definition        | The marker-bracketed block inside `app/frontend/src/app/globals.css` that defines `--surface-base`, `--brand-primary`, `--ring`, etc. as CSS custom properties on `:root`.       |
| File              | `app/frontend/src/app/globals.css` — the **section between `/* TOKENS:START — generated, do not edit */` and `/* TOKENS:END */`** is generated; everything else is hand-edited. |
| Producer          | Same generator as the typed export (`generate-tokens.ts`).                                                                                                                     |
| Format            | Colours: space-separated HSL triplets (`--brand-primary: 14 81% 57%;`) so shadcn primitives can compose `hsl(var(--brand-primary) / <alpha-value>)`.                              |
| Validation        | Same drift-detection mechanism as `tokens.ts` — the test loads the file, finds the markers, and compares the bracketed region against in-memory regenerated bytes.              |
| Stability         | The marker syntax (`/* TOKENS:START */` / `/* TOKENS:END */`) is **frozen** — moving it would invalidate the drift check across every later PR.                                  |

### 5. `TokenGenerator` — the regen script

| Field          | Value                                                                                                                                                  |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Definition     | A TS-on-Node script that reads `docs/design/tokens/*.md`, parses the role tables, and writes both `tokens.ts` and the marker-bracketed block of `globals.css` deterministically. |
| File           | `app/frontend/scripts/generate-tokens.ts`.                                                                                                              |
| Invocations    | `pnpm tokens:generate` (writes); `pnpm tokens:check` (`--check` flag — exits 1 on drift, 0 otherwise, prints unified-diff head).                        |
| Determinism    | Same input markdown + same generator version → same output bytes, on any machine, on any day.                                                          |
| Side effects   | None besides the two file writes. No network. No git mutations. No `node_modules` modifications.                                                       |
| Validation     | The Jest test imports the generator and runs it against the on-disk markdown and the on-disk artefacts; the pre-commit hook calls it via `--check`.   |
| Stability      | The script's command-line surface (`pnpm tokens:generate`, `pnpm tokens:check`) is **frozen**. Internal parsing logic may evolve as long as the output bytes do not churn. |

### 6. `ShadcnPrimitiveInventory` — the vendored UI primitives

| Field                | Value                                                                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition           | A set of TSX files under `app/frontend/src/components/ui/`, one file per primitive, vendored from the shadcn CLI and committed to the repo.                       |
| Inventory at T03 close | `button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table` (nine primitives, matching the implementation-plan T03 description).   |
| Source               | `pnpm dlx shadcn@latest add <primitive>` invoked once per primitive against the committed `components.json`.                                                      |
| Token consumption    | Each primitive consumes design tokens **exclusively** through Tailwind utilities (e.g., `bg-primary`, `text-foreground`) and CSS custom properties (e.g., `border-input`) emitted by the generator. No raw hex inside a primitive. |
| Validation           | Visual-discipline pre-commit hook scans `components/ui/*.tsx` for raw hex (must be zero matches). The smoke test imports each primitive in a stub assertion to confirm zero compile errors (SC-009). |
| Stability            | Primitives are extension-only. Later tasks add primitives via the same CLI; the existing files are NOT hand-edited (re-running the CLI overwrites them, which is the correct behaviour). |

### 7. `ShellSmokeTest` — the FR-011 admin-shell test

| Field          | Value                                                                                                                                                                                                                       |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition     | A Jest + RTL test that mounts the admin-shell route through Next.js's real rendering pipeline and asserts (a) the wordmark is present, (b) sidebar nav items are present, (c) `userEvent.tab()` advances focus across the items and the focus ring renders. |
| File           | `app/frontend/src/__tests__/shell.test.tsx`.                                                                                                                                                                                  |
| Test runner    | `pnpm test` (Jest 29 + `next/jest` factory + JSDOM).                                                                                                                                                                          |
| Test isolation | Each `test()` mounts a fresh tree; no global state.                                                                                                                                                                            |
| Validation     | Removing any of the three assertions or any of the chrome elements they target MUST cause the test to fail (FR-011, SC-002).                                                                                                  |
| Stability      | The file path (`app/frontend/src/__tests__/shell.test.tsx`) is **stable** — reviewer sub-agents look for it by name. Adding more assertions to extend coverage is additive and welcome.                                       |

### 8. `TokenDriftTest` — the FR-006 byte-equality test

| Field          | Value                                                                                                                                                          |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition     | A Jest test that imports the token generator, runs it against the on-disk markdown, captures the output bytes in memory, reads the committed `tokens.ts` and `globals.css` bytes, and asserts byte equality. Emits a unified-diff head on failure. |
| File           | `app/frontend/src/__tests__/tokens.test.ts`.                                                                                                                    |
| Producer of the bytes under test | `generate-tokens.ts` (same as the `--check` CLI surface).                                                                                  |
| Validation     | Mirrors T02's `test_openapi_regeneration.py` pattern. Failure modes the test must surface: hand-editing `tokens.ts`; hand-editing the marker-bracketed region of `globals.css`; editing the markdown without re-running the generator. |
| Stability      | Test file path is **stable**.                                                                                                                                  |

### 9. `VisualDisciplineHook` — the pre-commit guardrail

| Field         | Value                                                                                                                                                                                                                              |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Definition    | A `local` pre-commit hook entry that runs `app/frontend/scripts/check-visual-discipline.sh`, which performs two ripgrep searches: (1) raw hex in any `app/frontend/src/**/*.{ts,tsx,js,jsx,css,scss}` file outside `tokens.ts` and the marker-bracketed region of `globals.css`; (2) any `dark:` Tailwind variant anywhere in `app/frontend/src/`. |
| Files         | `.pre-commit-config.yaml` (hook entry) and `app/frontend/scripts/check-visual-discipline.sh` (the runner).                                                                                                                          |
| Failure mode  | Exits 1 with a one-line summary plus the offending file:line for each violation.                                                                                                                                                    |
| Side effects  | None. Read-only — does not mutate any file.                                                                                                                                                                                          |
| Validation    | Manual: introduce `bg-[#ff0000]` in a stub file, run `pre-commit run visual-discipline --all-files`, observe failure; revert and re-run, observe pass. Same for `dark:bg-foo`.                                                       |
| Stability     | The pattern set is **extension-only**. Later tasks may tighten (add patterns) but not loosen.                                                                                                                                        |

---

## Relationships

```text
docs/design/tokens/*.md ──read-by──► generate-tokens.ts ──writes──► tokens.ts (typed export)
                                                       └─writes──► globals.css [TOKENS:START..TOKENS:END] (CSS vars)

tokens.ts ──imported-by──► tailwind.config.ts (theme.extend.{colors,fontSize,borderRadius,…} + spacing OVERRIDE)
globals.css ──read-by──► browser/runtime (CSS variables at :root)

components.json ──configures──► shadcn CLI ──vendors──► components/ui/*.tsx
components/ui/*.tsx ──consume tokens via──► Tailwind utilities + CSS variables (FR-005 channel a + b)

components/shell/{top-bar,sidebar,shell}.tsx ──compose into──► <Shell>
<Shell> ──used-by──► app/layout.tsx (root layout) ──wraps──► every page.tsx

app/layout.tsx ──exercised-by──► shell.test.tsx (smoke: render + keyboard tab)
generate-tokens.ts ──exercised-by──► tokens.test.ts (drift: regenerate → byte-compare)

.pre-commit-config.yaml hooks ──validate──► tokens-drift (calls tokens:check) + visual-discipline (ripgrep)

app/frontend/package.json ──consumed-by──► pnpm install in Dockerfile.frontend stages (deps → dev → build → runtime)
```

---

## Validation rules (collected)

All validation runs inside the Dockerfile.frontend `dev` stage (constitution §7; research §7).

1. `docker compose --profile web up -d frontend` reaches "ready on http://0.0.0.0:3000" within 10 s and `curl http://127.0.0.1:3000/` returns HTTP 200 with the chrome HTML (FR-001, FR-002, FR-003, SC-001).
2. `docker compose -f docker-compose.test.yml run --rm frontend pnpm test` exits 0 in under 60 s on a clean tree (FR-011, FR-006, SC-002).
3. `docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check` exits 0 in under 5 s on the committed tree; introducing a deliberate single-value drift in `docs/design/tokens/colors.md` causes it to exit 1 with a unified-diff head (FR-006, SC-003).
4. `pre-commit run visual-discipline --all-files` exits 0 on the committed tree; introducing a single raw hex in any `app/frontend/src/**/*.tsx` file outside `tokens.ts` causes it to exit 1 (FR-007, SC-004, SC-005). Same for any `dark:` Tailwind variant (SC-006).
5. `docker compose -f docker-compose.test.yml run --rm frontend sh -c 'pnpm exec eslint --max-warnings=0 . && tsc --noEmit'` exits 0 on every T03-introduced file (FR-014, SC-008).
6. `pre-commit run --all-files` exits 0 on host — pre-commit operates around `git commit`, not inside the container (FR-014).
7. No T03 file contains a secret value, a credential, or a real PII sample (FR-016; enforced by `gitleaks` + `detect-secrets`).
8. T03 introduces no real screen, no auth middleware, no generated OpenAPI client, no `dark:` styling, no motion library, no analytics (FR-013; reviewer diff check).
9. Visual inspection: brand orange (`#E8573C`) renders only in the wordmark and the focus ring of the admin shell when compared against `docs/design/references/hellow_page.png` (FR-008, SC-007).

No other data-model concerns — T03 has no persistence, no migrations, no LLM inputs/outputs, no rubric references, no client-side state. Those arrive in T05, T13+, T20+, and later.
