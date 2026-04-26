# Phase 0 Research — T03 Next.js Skeleton

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-26

This document resolves the design-altitude decisions that sit below the spec but above `/speckit-tasks`. Every decision is rooted in an existing repo artefact (`docs/design/principles.md`, `docs/design/tokens/*.md`, `app/frontend/package.json`, `docker-compose.yml`, `.pre-commit-config.yaml`, constitution, ADRs) so the reviewer can verify without external searches.

---

## 1. Next.js + React versions

**Decision**: `next` `>=15.0,<16` and `react`/`react-dom` pinned to `18.3.x`. Added to `app/frontend/package.json` `dependencies`. `engines.node` already pinned to `20.x` (T01).

**Rationale**:

- Next 15 is the stable App Router release line. It supports both React 18 and React 19; the shadcn CLI's default templates as of the T03 close target React 18, so pinning React 18 minimises the gap between the committed shadcn primitives and the upstream templates.
- Pinning the major (`<16`) prevents a silent jump that could break the shadcn template diff. Patch / minor upgrades remain free.
- Next 15 ships the `next/jest` factory we use in §6 below — no manual Babel-with-SWC juggling.

**Alternatives considered**:

- *React 19 + Next 15*: works, but the shadcn primitives' TS types and the few `@radix-ui/react-*` peer-dep declarations are still flagged "support coming soon" for some primitives at the install snapshot we will use. Rejected for now; revisitable when shadcn templates default to React 19.
- *Vite + React Router instead of Next.js*: rejected — `docs/design/principles.md` explicitly fixes the stack as Next.js. Switching would require an ADR.
- *Next 14*: superseded by Next 15; the latter's stable App Router behaviours and the `next/jest` factory are both useful at T03.

---

## 2. Tailwind major version + spacing OVERRIDE

**Decision**: `tailwindcss` `>=3.4,<4`. JS config (`tailwind.config.ts`). Colours, radii, typography, motion are wired via `theme.extend.*` so Tailwind's defaults remain available; **`theme.spacing` is OVERRIDDEN entirely** (no `extend`) per `docs/design/tokens/spacing.md`'s Export note ("Default Tailwind spacing scale is overridden to match this table exactly (no stray `w-7`)").

**Rationale**:

- The spec assumption explicitly describes `tailwind.config.ts` reading the typed token export via `theme.extend`. That syntax is Tailwind 3.
- `docs/design/tokens/spacing.md` is unambiguous: the spacing scale must NOT include stray utilities like `w-7`. The only way to enforce that in Tailwind 3 is to set `theme.spacing` to a complete object (overriding the default 0/0.5/1/1.5/…/96 scale). Other axes (colours, radii, typography) extend so the defaults remain.
- Tailwind 4 is a CSS-first config rewrite (`@theme {}` blocks, no `tailwind.config.ts`) that would invalidate the shadcn primitive templates we vendor. Adopting it would require migrating every committed primitive at the same time; that is its own ADR-worthy initiative, not a T03 sub-task.

**Alternatives considered**:

- *Tailwind 4*: rejected for now (CSS-first config + shadcn template gap).
- *`theme.extend.spacing`*: would let `w-7` through; violates `docs/design/tokens/spacing.md`. Rejected.
- *Authoring all spacing utilities manually (no Tailwind)*: rejected — `docs/design/principles.md` fixes Tailwind in the stack.

---

## 3. shadcn CLI configuration

**Decision**: `app/frontend/components.json` is committed with the following settings:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.ts",
    "css": "src/app/globals.css",
    "baseColor": "neutral",
    "cssVariables": true
  },
  "aliases": {
    "components": "@/components",
    "ui": "@/components/ui",
    "utils": "@/lib/cn",
    "lib": "@/lib"
  },
  "iconLibrary": "lucide"
}
```

The nine T03 primitives are installed via `pnpm dlx shadcn@latest add button card input label dialog dropdown-menu tooltip popover table` (run once, locally) and the resulting files are committed verbatim under `app/frontend/src/components/ui/`. **The committed primitives are immediately mutated by the post-install token-overlay step** so the CSS variable names they reference (`--primary`, `--background`, `--ring`, …) match the names emitted by the token generator (decision §4) — see the post-install procedure in `contracts/frontend-contract.md` Surface 3.

**Rationale**:

- `style: "new-york"` matches the more polished, condensed visual the Chat-iX reference screens (`docs/design/references/`) lean toward. The "default" style is more generic.
- `baseColor: "neutral"` is the closest shadcn neutral to our `surface.*`/`content.*` greys. `cssVariables: true` is the flag that makes shadcn emit `bg-primary` (utility) → `var(--primary)` (CSS var) under the hood; without it the primitives hard-code Tailwind utilities and the spec's "shadcn primitives work natively" outcome (Q2 clarification, FR-005) is impossible.
- `aliases.utils: "@/lib/cn"` matches our chosen helper name (`lib/cn.ts`); `aliases.ui: "@/components/ui"` matches the path documented in `docs/design/components/README.md`.
- `iconLibrary: "lucide"` aligns with `docs/design/principles.md` §"the stack is fixed".

**Alternatives considered**:

- *`baseColor: "slate"`*: pulls bluish greys; clashes with the warm-neutral surface scale described in `docs/design/tokens/colors.md`. Rejected.
- *`cssVariables: false`*: makes shadcn primitives compile to raw Tailwind colour utilities. We would then have to fork every primitive to swap in our token classes. Conflicts with FR-005 channel (b). Rejected.
- *Skipping `components.json` and using the shadcn CLI ad-hoc per primitive*: rejected — without the committed config, future tasks installing more primitives would re-prompt for style/baseColor/etc., risking drift.

---

## 4. Token generator design

**Decision**: `app/frontend/scripts/generate-tokens.ts` (TS-on-Node, run via `tsx`). Reads every markdown file in `docs/design/tokens/*.md`, parses the role tables (a small purpose-built parser; no `remark` dependency), and writes two artefacts deterministically:

1. `app/frontend/src/design/tokens.ts` — a TypeScript module exporting a typed object literal (`as const` so the Tailwind config gets literal-type inference). Roles preserve markdown-source order; key naming converts the dotted role notation (`brand.primary`) to the same dotted-key path inside the object literal (`brand: { primary: "#E8573C" }`).
2. The CSS-variables block inside `app/frontend/src/app/globals.css`, between two committed marker lines — `/* TOKENS:START — generated, do not edit */` and `/* TOKENS:END */`. The block contains **two layers** under `:root` (separated by a blank-line + `/* shadcn aliases */` sub-comment for diff readability): (a) **semantic-role layer** keyed by our markdown role names (`--brand-primary`, `--surface-base`, `--content-primary`, `--border-default`, `--focus-ring`, …); (b) **shadcn-alias layer** keyed by the standard names shadcn primitives expect (`--background`, `--foreground`, `--primary`, `--ring`, `--card`, `--popover`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`, plus their `*-foreground` pairs). The alias layer is **emitted as `var(...)` references** to the semantic layer (e.g., `--primary: var(--brand-primary);`) so the value is single-source — editing the semantic layer flows through the aliases without a second markdown change. **Colours in the semantic layer are emitted as space-separated HSL triplets** (`--brand-primary: 14 81% 57%;`) so shadcn's `hsl(var(--primary) / <alpha-value>)` pattern composes correctly through the alias.

The script is invoked via `pnpm tokens:generate` (writes) and `pnpm tokens:check` (`--check` flag — exits 1 with a unified-diff head if either output differs from the committed file).

### Role-to-shadcn alias mapping

This table is the canonical source for the alias layer the generator emits. Editing a row here without regenerating fails the drift check (FR-006). Every shadcn primitive shipped at T03 close (T025 inventory: `button`, `card`, `input`, `label`, `dialog`, `dropdown-menu`, `tooltip`, `popover`, `table`) consumes only the right-hand side names; no primitive references the left-hand side directly.

| Our semantic role            | shadcn alias              | Notes                                                                                |
| ---------------------------- | ------------------------- | ------------------------------------------------------------------------------------ |
| `surface.base`               | `--background`            | Page canvas — the default `bg-background` utility.                                   |
| `content.primary`            | `--foreground`            | Body text — the default `text-foreground` utility.                                   |
| `surface.base`               | `--card`                  | Cards sit on the canvas in the light theme.                                          |
| `content.primary`            | `--card-foreground`       | Same colour as body text.                                                            |
| `surface.base`               | `--popover`               | Popovers / dropdown menus on white.                                                  |
| `content.primary`            | `--popover-foreground`    |                                                                                       |
| `brand.primary`              | `--primary`               | Primary CTA fill — the only allowlisted brand-orange surface slot.                   |
| `content.inverted`           | `--primary-foreground`    | White-on-orange.                                                                     |
| `surface.muted`              | `--secondary`             | Secondary button background, subtle filled chips.                                    |
| `content.primary`            | `--secondary-foreground`  |                                                                                       |
| `surface.muted`              | `--muted`                 | Muted region background (table zebra, empty-state backdrop).                         |
| `content.muted`              | `--muted-foreground`      | Caption / metadata text.                                                             |
| `brand.primary-subtle`       | `--accent`                | Hover-row tint, selected-row tint — the only soft-orange slot.                       |
| `content.primary`            | `--accent-foreground`     |                                                                                       |
| `status.danger`              | `--destructive`           | Destructive confirmations.                                                           |
| `content.inverted`           | `--destructive-foreground`|                                                                                       |
| `border.default`             | `--border`                | Card / input borders at rest.                                                        |
| `border.default`             | `--input`                 | Input borders track the general border colour at MVP; can split later if needed.     |
| `focus.ring`                 | `--ring`                  | Keyboard focus ring (per `colors.md`, `focus.ring` IS `brand.primary`).              |

The `--radius` shadcn variable is a length, not HSL; it is emitted into the same alias layer as a direct value from `docs/design/tokens/radii.md` (the role `radius.md` → `--radius`).

If a future task introduces a primitive that references a CSS var not in this table (e.g., shadcn adds `--sidebar` or `--chart-1`), the procedure is: (1) extend `docs/design/tokens/colors.md` with the new role; (2) extend this table with the new alias mapping; (3) re-run `pnpm tokens:generate`. The drift test catches any step skipped.

**Rationale**:

- A purpose-built parser (≈ 60 LOC) for the well-structured markdown tables in `docs/design/tokens/*.md` avoids pulling `remark` + `unified` (≈ 200 KB of transitive deps) for one script.
- Emitting `as const` makes Tailwind's config strongly typed without an extra step; consumer code can `import type { Tokens } from "@/design/tokens"` for IntelliSense.
- HSL triplets (not `hsl(...)` calls) are the shadcn convention because they let alpha be parameterised at use-site (`hsl(var(--brand-primary) / 0.5)` for a 50%-opacity fill). Storing the triplet string as the variable value is what makes that work.
- Markers in `globals.css` allow contributors to hand-edit Tailwind directives, base styles, and global resets while keeping the generated block byte-isolated. The drift check only diffs the marker-bracketed region; everything outside is free territory.
- `tsx` (rather than `ts-node`) is faster and the modern community choice; it is also already a transitive dep of several Next.js plugins.

**Alternatives considered**:

- *Python generator under `app/backend/scripts/`*: would require contributors to flip languages mid-edit-loop. The frontend tooling is TS-native; a TS generator stays in-stream. Rejected.
- *Generate JSON + TS-import*: an extra indirection with no benefit — Tailwind's config and the CSS-vars emitter both want the data inline. Rejected.
- *Emitting RGB triplets instead of HSL*: rgb works for opacity-via-alpha too, but shadcn's templates default to HSL; sticking with HSL minimises template drift. Rejected as a switch.
- *Store the markers as separate files (`globals-base.css` + `globals-tokens.css`) imported into one `globals.css`*: more files, no real benefit — the marker approach is industry standard for "generated block inside a hand-edited file".

---

## 5. Token-drift detection surface

**Decision**: Drift is detected by **both** a Jest test (`app/frontend/src/__tests__/tokens.test.ts`) and a pre-commit hook (a `local` hook in `.pre-commit-config.yaml` that calls `pnpm tokens:check`). The Jest test runs the generator in memory and asserts byte-equality with the committed `tokens.ts` and the marker-bracketed region of `globals.css`. The pre-commit hook gives developers immediate feedback before `git commit` lands.

**Rationale**:

- Mirrors T02's pytest-based OpenAPI drift check (research §3 in T02) for direct symmetry, with one addition: a pre-commit hook on top — because the frontend already has a lot of files outside the test suite (vendored shadcn primitives, generated CSS) that benefit from a fast local check independent of `pnpm test` (which runs JSDOM and is heavier than necessary for a byte-diff).
- The Jest test gives CI coverage for free once T10 wires `pnpm test` into the workflow.
- The pre-commit hook costs ~1 s on a typical machine (`tsx` startup + small parse + diff). Adding it to `.pre-commit-config.yaml` does not violate the file's "no auto-formatters" header comment — the hook is read-only (`--check`), it never mutates.

**Alternatives considered**:

- *Pre-commit hook only*: imposes the "the contributor must have node_modules installed" gotcha at commit time. Rejected as the sole surface; kept as the second surface for fast feedback.
- *Jest test only*: leaves a feedback gap until the contributor runs the test suite. Rejected as the sole surface.
- *CI-only check*: too late — a contributor could push a drift-broken commit that wastes a CI cycle. Rejected.

---

## 6. Visual-discipline check mechanism

**Decision**: A `local` pre-commit hook in `.pre-commit-config.yaml` that runs **two ripgrep searches** over `app/frontend/src/`:

1. **Raw hex outside the token file** — `rg -n --type-add 'frontsrc:*.{ts,tsx,js,jsx,css,scss}' --type frontsrc -e '#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b' -g '!**/design/tokens.ts' -g '!**/app/globals.css'` — non-zero exit on any match.
2. **`dark:` Tailwind variant anywhere** — `rg -n -e '\bdark:[a-z]' app/frontend/src/` — non-zero exit on any match.

The hook's `entry` is a small shell script under `app/frontend/scripts/check-visual-discipline.sh` that runs both searches and exits 1 with a human-readable summary on first violation. CI inherits the same hook through `pre-commit run --all-files` (T10).

A second, complementary surface is added during T10: an ESLint rule wrapper around `no-restricted-syntax` for hex-literal AST patterns and `no-restricted-classes` for `dark:`. **This is not in T03's scope** — the regex hook is sufficient floor; the ESLint rule is a refinement.

**Rationale**:

- ripgrep is already in every contributor's machine (it ships with most modern dev environments) and is faster than authoring an ESLint plugin (≈ 5 ms per file vs ≈ 50 ms per file for ESLint AST parsing on a tree of this size).
- The two pattern searches are independent: a contributor introducing a raw hex sees the first error; a contributor introducing a `dark:` variant sees the second.
- Excluding `tokens.ts` and `globals.css` is necessary because both of those files literally contain the hex / HSL triplets the design system pivots on. Only those two paths are excluded; everything else (including `components/ui/*.tsx` shadcn primitives) must NOT contain raw hex.
- The hook is read-only; it does not violate the `.pre-commit-config.yaml` header comment about "no auto-formatters".

**Alternatives considered**:

- *Custom ESLint rule only*: significantly more code (a small plugin package, peer-dep on `eslint`, AST traversal). Slower per-file. Rejected as the sole surface for T03; revisitable in T10 if hex creeps in via patterns ripgrep can't catch (e.g., a hex value computed at runtime, which is a separate code-smell anyway).
- *grep instead of ripgrep*: works but `grep -E` syntax is uglier and slower. ripgrep is universally available on developer machines. Use ripgrep.
- *Tailwind plugin that throws on `dark:` variant compile*: would break Tailwind's compilation entirely. Rejected — too blunt.

---

## 7. Dockerfile.frontend stages

**Decision**: A new `Dockerfile.frontend` at the repo root, multi-stage:

```dockerfile
FROM node:20-bookworm-slim AS base
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate

FROM base AS deps
COPY app/frontend/package.json app/frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS dev
COPY app/frontend/ ./
EXPOSE 3000
CMD ["pnpm", "dev", "--hostname", "0.0.0.0", "--port", "3000"]

FROM deps AS build
COPY app/frontend/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN pnpm build

FROM node:20-bookworm-slim AS runtime
WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.12.0 --activate
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
ENV NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
EXPOSE 3000
CMD ["pnpm", "start"]
```

The existing `docker-compose.yml` `frontend` service is edited from `target: build` to `target: dev` (the previous value pointed at an intermediate stage; that was T02's stub-state). `depends_on.backend` is relaxed to `condition: service_started, required: false` so the frontend boots without the backend (FR-003).

**Rationale**:

- The `dev` stage is the canonical local + CI image: ships dev deps, runs `pnpm dev` with hot-reload, mounts the source directory via the existing compose volume binding.
- The `build` stage is intermediate; production `runtime` copies from it. Splitting `build` from `runtime` keeps the runtime image small (no source, no dev deps).
- Pinning `node:20-bookworm-slim` matches `engines.node = "20.x"` from `app/frontend/package.json`. The `slim` variant trims ~200 MB compared with the default tag.
- `corepack enable` lets us pin `pnpm@9.12.0` without committing a custom `package@…` script.
- `NEXT_TELEMETRY_DISABLED=1` is a Cloud-Run-friendly default that also avoids noisy first-build network calls in CI.
- `PORT` and `HOSTNAME` env vars in `runtime` keep the prod CMD identical regardless of what Cloud Run injects.

**Alternatives considered**:

- *Single-stage Dockerfile*: ships dev deps in production, larger image, longer cold-start. Rejected.
- *Standalone Next.js output mode*: smaller runtime image but breaks bind-mount-based dev hot-reload at the layout level. The `runtime` stage above can be migrated to standalone in T06 once the dev / runtime split is settled.
- *Distroless runtime base*: needs a custom CMD that calls `node` directly; loses `pnpm start` ergonomics. Rejected for T03; revisitable in T06 as a Cloud Run image-size tuning.

---

## 8. i18n placeholder layout

**Decision**: Three files under `app/frontend/src/messages/`:

- `README.md` — explains: T03 marker only, no i18n runtime; first task with real Ukrainian copy (T20 candidate session) picks the runtime mechanism (`next-intl`, `react-intl`, or built-in `next` i18n) and may freely reshape this directory.
- `uk.json` — `{ "wordmark.alt": "N-iX TechScreen" }` (one demo key; not actually consumed at T03).
- `en.json` — same shape, English value.

The shell components do **not** import these files at T03 — they are filesystem markers documenting the convention.

**Rationale**:

- Per the Q4 clarification, T03 leaves a marker, not a runtime. The convention is "JSON dict files under a `messages/` folder, one per locale".
- The marker README prevents future contributors from looking at empty JSON files and either deleting them ("looks like dead code") or accidentally locking us into a JSON shape that conflicts with whichever i18n library T20 picks.
- Locating the folder under `src/messages/` (not `src/locales/`, not `app/messages/`) matches the most common shadcn/Next.js community precedent and is also what `next-intl` defaults to. Both `react-intl` and the built-in Next i18n can also work with this path; if T20 picks a library that wants a different path, relocating two JSON files plus the README is trivial.

**Alternatives considered**:

- *Defer entirely (no files)*: the Q4 clarification explicitly chose Option C ("file-convention only"), not Option B ("defer entirely"). Rejected.
- *Set up `next-intl` now with empty dicts*: pre-commits us to a runtime library; spec assumption explicitly says "first task with real copy picks the library". Rejected.
- *Put the files under `app/frontend/messages/`* (outside `src/`): would require an extra path entry in `tsconfig.json` aliases for any task that does import them later. `src/messages/` keeps everything inside the standard `@/messages` alias space. Rejected.

---

## Summary

Eight decisions, all rooted in existing repo artefacts. None introduce a new external dependency we do not already need. None violate constitution invariants. All are reversible with bounded blast radius (the largest blast is "swap Tailwind 3 → 4" which is its own ADR).

The implementer (`agent: frontend-engineer`) has enough to start `/speckit-tasks` without further clarification.
