# Frontend Contract — T03 Next.js Skeleton

**Feature**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md)
**Stable from**: T03 merge onwards.
**Consumers**: every later frontend task (Tier 2: T13 Position Template UI; Tier 4: T20 candidate session; Tier 5: T21 recruiter session monitor; Tier 6: T22+ recruiter session review and corrections; Tier 7: admin screens), `infra-engineer` (T06 Cloud Run frontend service; T09 Docker `web` profile), `reviewer` sub-agent (validates the visual-discipline + token-drift guardrails on every later frontend PR), human Tier-1 sign-off (T11 — admin shell visible in browser).

This is a single consolidated contract covering the five surfaces T03 commits to: the layout/chrome convention, the design-token export, the shadcn primitive inventory, the drift-detection mechanism, and the visual-discipline mechanism. A later task may **extend** any of them additively; breaking changes (rename, remove, narrow exit semantics, weaken a guardrail) require an ADR and a plan update referencing this file.

---

## Surface 1 — Layout / chrome contract

### Where the chrome lives

`app/frontend/src/app/layout.tsx` — the root Next.js App Router layout. It wraps every later route automatically.

### Shape

```tsx
// app/frontend/src/app/layout.tsx (T03 close)
import "@/app/globals.css";
import { Shell } from "@/components/shell/shell";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="uk">
      <body className="bg-surface-base text-content-primary antialiased">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
```

### Slots a later task can rely on

- **Top bar** — fixed top region, includes the N-iX wordmark on the left. A later task can extend with right-aligned slots (user menu, search) by editing `top-bar.tsx`.
- **Sidebar** — left region, holds the nav stub at T03. A later task replaces the stub items with real routes; the structural slot is permanent.
- **Content slot (`{children}`)** — the main region where every later route's `page.tsx` renders.

### Convention for downstream tasks

> Every later route lives at `app/frontend/src/app/<route>/page.tsx` and inherits the chrome via the root layout. Routes do NOT re-import `<Shell>`. A route that needs a different chrome wraps its own `app/<route>/layout.tsx` underneath the root one (Next.js layouts compose).

### Stability

- The root layout's role as "chrome host" is **frozen**. Moving the chrome out of `app/layout.tsx` breaks every downstream task.
- The `<html lang="uk">` attribute is **stable** (the product's primary candidate locale). A later task that ships English copy adjusts via the i18n runtime it picks (Q4 clarification — this is T20's call), not by mutating this attribute hard.
- `globals.css` import path is **frozen**: `@/app/globals.css`.

---

## Surface 2 — Design-token export contract

### Source of truth

`docs/design/tokens/*.md` — colours, spacing, typography, radii, motion. Markdown role tables. **Edit markdown only**; never edit the generated artefacts directly.

### Generated artefacts

- `app/frontend/src/design/tokens.ts` — typed `as const` object literal exporting the token tree.
- `app/frontend/src/app/globals.css` — the marker-bracketed block under `:root` (between `/* TOKENS:START — generated, do not edit */` and `/* TOKENS:END */`) declaring CSS custom properties keyed by role name.

### Producer

```bash
# Writes both artefacts
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:generate

# Dry-run; exits 1 with unified-diff head on drift
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
```

The script lives at `app/frontend/scripts/generate-tokens.ts` and runs via `tsx`. A future task substituting a different runner keeps the same `pnpm` script names.

### Channel A — Tailwind utility classes

`app/frontend/tailwind.config.ts` reads `tokens.ts` and feeds Tailwind's theme:

- `theme.extend.colors`, `theme.extend.fontSize`, `theme.extend.borderRadius`, `theme.extend.transitionDuration` — keep Tailwind defaults available, add our role-named classes (`bg-surface-base`, `text-content-primary`, `border-border-subtle`, `rounded-md`, `duration-fast`, …).
- `theme.spacing` — **OVERRIDDEN entirely** with the scale from `docs/design/tokens/spacing.md` (no `extend`). Per the spacing.md Export note, Tailwind's defaults must NOT leak through (no stray `w-7`).

### Channel B — CSS custom properties

The generated block in `globals.css` declares **two layers** under `:root`:

```css
:root {
  /* Semantic-role layer — keyed by our markdown role names */
  --surface-base: 0 0% 100%;
  --surface-raised: 0 0% 98%;
  --surface-muted: 240 5% 96%;
  --content-primary: 0 0% 7%;
  --content-muted: 240 5% 56%;
  --content-inverted: 0 0% 100%;
  --border-default: 240 4% 89%;
  --brand-primary: 14 81% 57%;
  --brand-primary-subtle: 14 87% 95%;
  --status-danger: 0 79% 40%;
  --focus-ring: 14 81% 57%;
  /* …every role from docs/design/tokens/*.md… */

  /* shadcn aliases — `var(...)` pointers to the semantic layer above */
  --background: var(--surface-base);
  --foreground: var(--content-primary);
  --card: var(--surface-base);
  --card-foreground: var(--content-primary);
  --popover: var(--surface-base);
  --popover-foreground: var(--content-primary);
  --primary: var(--brand-primary);
  --primary-foreground: var(--content-inverted);
  --secondary: var(--surface-muted);
  --secondary-foreground: var(--content-primary);
  --muted: var(--surface-muted);
  --muted-foreground: var(--content-muted);
  --accent: var(--brand-primary-subtle);
  --accent-foreground: var(--content-primary);
  --destructive: var(--status-danger);
  --destructive-foreground: var(--content-inverted);
  --border: var(--border-default);
  --input: var(--border-default);
  --ring: var(--focus-ring);
  --radius: 0.5rem; /* from docs/design/tokens/radii.md role `radius.md`; direct length, not HSL */
}
```

- **Semantic-role layer** — colours are space-separated HSL triplets so the alias layer can use `hsl(var(--primary) / <alpha-value>)`.
- **shadcn-alias layer** — `var(...)` pointers (not duplicated triplets) so the value is single-source. The mapping (which semantic role each alias points at) is the canonical role-to-shadcn alias mapping in [research.md](../research.md) §4 "Role-to-shadcn alias mapping".
- Non-colour tokens (spacing, type, radii, motion) are emitted in their canonical CSS unit (`px`, `rem`, `ms`).
- **Single-source guarantee**: editing the semantic layer (`--brand-primary: 14 60% 40%;`) propagates to every alias automatically (`--primary` resolves through `var(--brand-primary)`). The drift test (Surface 4) catches any hand-edit attempting to break the alias indirection.

### Stability

- Role names are **frozen** (they ARE the contract). Adding a role is additive (extends the markdown table; regen propagates). Removing a role is a breaking change requiring a new spec.
- The `as const` export shape is **stable**.
- The `TOKENS:START` / `TOKENS:END` markers are **frozen** — the drift check depends on them.
- HSL triplet format for colours is **frozen** — switching to RGB or hex breaks every shadcn template that consumes the variables.

---

## Surface 3 — shadcn primitive inventory contract

### Inventory at T03 close

| Primitive       | File                                                        | Used by (T03)   |
| --------------- | ----------------------------------------------------------- | --------------- |
| `button`        | `app/frontend/src/components/ui/button.tsx`                 | Sidebar nav stub items (renders nav items as buttons for a focusable role) |
| `card`          | `app/frontend/src/components/ui/card.tsx`                   | (vendored only — no consumer at T03; ready for T13+)                       |
| `input`         | `app/frontend/src/components/ui/input.tsx`                  | (vendored only — ready for T13+)                                           |
| `label`         | `app/frontend/src/components/ui/label.tsx`                  | (vendored only — ready for T13+)                                           |
| `dialog`        | `app/frontend/src/components/ui/dialog.tsx`                 | (vendored only — ready for T13+)                                           |
| `dropdown-menu` | `app/frontend/src/components/ui/dropdown-menu.tsx`          | (vendored only — ready for T13+)                                           |
| `tooltip`       | `app/frontend/src/components/ui/tooltip.tsx`                | (vendored only — ready for T13+)                                           |
| `popover`       | `app/frontend/src/components/ui/popover.tsx`                | (vendored only — ready for T13+)                                           |
| `table`         | `app/frontend/src/components/ui/table.tsx`                  | (vendored only — ready for T13+)                                           |

### Import alias

`@/components/ui/*` — codified in `app/frontend/components.json` and `tsconfig.json`. Stable; documented in `docs/design/components/README.md`.

### Token consumption inside primitives

Every committed primitive consumes design tokens through Tailwind utilities (`bg-primary`, `text-foreground`, `ring-ring`) which Tailwind resolves to `hsl(var(--primary) / <alpha-value>)` etc. via the **shadcn-alias layer** of channel-B CSS variables. The alias layer in turn dereferences to our **semantic-role layer** (`--primary` → `var(--brand-primary)` → `14 81% 57%`). **No primitive contains a raw hex.** The visual-discipline hook (Surface 5) enforces this at commit time. The dual-layer indirection is documented in [Surface 2](#surface-2--design-token-export-contract) and the canonical mapping table lives in [research.md](../research.md) §4.

### Post-install procedure (run during T025; mandatory)

shadcn primitives are committed verbatim as the CLI emits them — they reference standard shadcn CSS-var names (`--primary`, `--background`, `--ring`, …). Those names exist **only because** the token generator (Surface 2 channel B) emits them as the alias layer. Therefore the procedure to install any primitive (the nine at T03 close, or any later addition) MUST follow this order:

1. **Snapshot `globals.css`**: `cp app/frontend/src/app/globals.css /tmp/globals.css.before-shadcn` (so any CLI overwrite of the file outside the `TOKENS:START`/`TOKENS:END` markers can be detected and reverted).
2. **Run `pnpm tokens:generate` first** so the alias layer is populated. Without this, the shadcn primitives will reference variables that do not exist and will render as transparent / unstyled. (Already done at T020 — but re-confirm before T025.)
3. **Install primitives**: `pnpm dlx shadcn@2 add <primitive> [<primitive> ...]`. The CLI reads `components.json`. **Pin the major version explicitly** (`@2`, not `@latest`) so future shadcn 3.x template-breaking changes do not silently land in a maintenance install. When a future task needs to bump the major, that bump is its own ADR-discussed change touching `components.json` + every primitive it would now re-install.
4. **Diff `globals.css` against the snapshot**: `diff /tmp/globals.css.before-shadcn app/frontend/src/app/globals.css`. Expected diff = empty (CLI does not touch it once `cssVariables: true` is set and `:root { --primary: ...; }` blocks already exist). If the CLI **did** rewrite `globals.css`, the rewrite is wrong (it would have used hard-coded shadcn defaults instead of our aliases) — revert via `cp /tmp/globals.css.before-shadcn app/frontend/src/app/globals.css` and report the deviation; do not commit until it is understood.
5. **Verify every CSS variable the new primitive references exists in `globals.css`**: `for var in $(grep -oE 'var\(--[a-z-]+\)' app/frontend/src/components/ui/*.tsx | grep -oE '\-\-[a-z-]+' | sort -u); do grep -q "$var" app/frontend/src/app/globals.css || echo "MISSING: $var"; done`. Expected: zero `MISSING:` lines. If any variable is missing, extend the canonical mapping table in [research.md](../research.md) §4 with a new row, extend the corresponding markdown role in `docs/design/tokens/colors.md`, re-run `pnpm tokens:generate`, and re-verify.
6. **Run `pre-commit run --all-files`**. The `tokens-drift` hook re-asserts the generator-vs-committed equality; the `visual-discipline` hook scans the new primitive(s) for raw hex (zero matches required).
7. Commit the primitive(s) in the same PR as the install.

This procedure is replayed by every later task that adds a primitive (T13 PositionTemplate UI may add `select`, `form`, `checkbox`; T20 may add `textarea`, `toast`; etc.) — the mapping table in research §4 grows additively.

### Stability

- The CLI invocation (`pnpm dlx shadcn@2 add`, with the major version explicitly pinned) and the alias (`@/components/ui/*`) are **frozen**.
- The `components.json` settings (`style: new-york`, `baseColor: neutral`, `cssVariables: true`) are **frozen**. Changing any of them invalidates every committed primitive.
- The committed primitive list is **extension-only**. Removing a primitive requires confirming no consumer exists.

---

## Surface 4 — Drift-detection contract

### Where drift is caught

Two surfaces, both backed by the same generator:

1. **Jest test** — `app/frontend/src/__tests__/tokens.test.ts`:
   - Imports `generate-tokens.ts` (the producer module).
   - Runs the generator against the on-disk `docs/design/tokens/*.md` and captures the output bytes in memory.
   - Reads the committed `app/frontend/src/design/tokens.ts` and the marker-bracketed region of `app/frontend/src/app/globals.css` from disk.
   - Asserts byte-equality between (in-memory) and (on-disk).
   - Emits the first ~40 lines of `diff` output on failure.
2. **Pre-commit hook** — `.pre-commit-config.yaml` adds a `local` hook `tokens-drift` whose `entry` is `bash -c 'cd app/frontend && pnpm tokens:check'`. Same exit semantics as the Jest test.

### Why both surfaces

The Jest test gives CI coverage for free once T10 wires `pnpm test` into the workflow. The pre-commit hook gives the developer immediate feedback at `git commit` time — without the contributor having to remember to run the test suite. T02 used pytest only because its drift was OpenAPI-shaped and tied to FastAPI's request lifecycle. T03's drift is purely byte-shaped and worth catching pre-commit too.

### Manual check

```bash
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
```

Exits 1 with a unified-diff head if drift exists, 0 otherwise. Useful in a tight edit loop.

### Stability

- The Jest test path (`app/frontend/src/__tests__/tokens.test.ts`) is **stable** — reviewer sub-agents look for it by name.
- The `pnpm tokens:generate` and `pnpm tokens:check` script names are **frozen**.

---

## Surface 5 — Visual-discipline contract

### Patterns the hook flags

1. **Raw hex outside the canonical token files**. Pattern: `#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b` (3, 4, 6, or 8 hex digits with a word boundary). Searched in `app/frontend/src/**/*.{ts,tsx,js,jsx,css,scss}`. Excluded paths: `app/frontend/src/design/tokens.ts` (the generated typed export) and `app/frontend/src/app/globals.css` (the generated CSS-vars block).
2. **`dark:` Tailwind variants anywhere**. Pattern: `\bdark:[a-z]` (word boundary, then `dark:`, then a Tailwind class). Searched in `app/frontend/src/**/*.{ts,tsx,js,jsx,css,scss}`. No exclusions.

### Where the hook lives

- Hook entry: `.pre-commit-config.yaml` adds a `local` hook `visual-discipline` (alongside the existing `eslint` local hook).
- Runner: `app/frontend/scripts/check-visual-discipline.sh` — a small bash script that runs both ripgrep searches and exits 1 with a one-line summary on first violation.

### Failure output (illustrative)

```text
visual-discipline: raw hex outside the token file
  app/frontend/src/components/shell/top-bar.tsx:14:  return <h1 style={{color: "#E8573C"}}>...
visual-discipline: 1 violation(s); see above. Use a token role instead.
```

### What this catches

- Raw hex in component code (`bg-[#ff0000]`, inline `style={{color: "#xxxxxx"}}`, CSS-in-JS literals).
- `dark:bg-foo`, `dark:text-bar` — anywhere in the frontend source tree.

### What this does NOT catch (deferred)

- Hex values computed at runtime (e.g., concatenated string literals). Rare; a code-smell on its own.
- Off-token Tailwind utilities like `bg-blue-500` (using a Tailwind default instead of a role). Caught by reviewer eyeball at T03; a stricter ESLint rule may land in T10.
- Off-allowlist brand-orange usage (e.g., orange used as a background colour somewhere). Caught by reviewer eyeball + visual comparison against `docs/design/references/`.

### Stability

- The hook id `visual-discipline` is **stable** (reviewer sub-agents may refer to it by id).
- The two patterns are **extension-only** — later tasks may tighten (add patterns) but not loosen.
- Excluded paths (`tokens.ts`, `globals.css` marker region) are **stable** unless the token-generation strategy itself changes.

---

## Invocation preconditions (all five surfaces)

1. Docker Engine 24.x or Docker Desktop installed and running.
2. `docker compose build frontend` has run at least once (subsequent runs reuse cached layers; first build downloads Node base + installs deps).
3. `pre-commit ≥ 3.7.0` installed on the host (T01 baseline) — required for the visual-discipline and tokens-drift hooks to fire on `git commit`.
4. Current working directory is the repo root so the bind-mount in `docker-compose.yml` resolves to actual source.

Steps 1–4 are documented in the README "Frontend dev loop (Docker-first)" subsection added by T03. Native `pnpm --dir app/frontend …` is available but not the canonical path.

---

## Summary of frozen surfaces

| Surface                                            | Frozen symbol / path                                                                                      |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Root layout file                                   | `app/frontend/src/app/layout.tsx` (chrome host)                                                            |
| Shell composition root                             | `app/frontend/src/components/shell/shell.tsx`                                                              |
| Design-token markdown source                       | `docs/design/tokens/*.md`                                                                                  |
| Design-token TS export                             | `app/frontend/src/design/tokens.ts` (generated)                                                            |
| CSS custom properties block                        | `app/frontend/src/app/globals.css` between `/* TOKENS:START */` and `/* TOKENS:END */` (generated)         |
| Token generator entrypoint                         | `app/frontend/scripts/generate-tokens.ts` (TS-on-Node, run via `tsx`)                                       |
| Token generator commands                           | `pnpm tokens:generate` (writes), `pnpm tokens:check` (dry-run + drift exit)                                 |
| Colour CSS-var format                              | space-separated HSL triplets — `--brand-primary: 14 81% 57%;`                                              |
| Tailwind config path                               | `app/frontend/tailwind.config.ts`                                                                          |
| Tailwind spacing axis                              | `theme.spacing` (full OVERRIDE) per `docs/design/tokens/spacing.md`                                        |
| shadcn config                                      | `app/frontend/components.json` (`style: new-york`, `baseColor: neutral`, `cssVariables: true`, `iconLibrary: lucide`) |
| shadcn primitive alias                             | `@/components/ui/*`                                                                                         |
| shadcn primitive inventory at T03 close            | button, card, input, label, dialog, dropdown-menu, tooltip, popover, table                                  |
| Drift-detection Jest test                          | `app/frontend/src/__tests__/tokens.test.ts`                                                                 |
| Drift-detection pre-commit hook id                 | `tokens-drift`                                                                                              |
| Visual-discipline pre-commit hook id               | `visual-discipline`                                                                                         |
| Visual-discipline runner                           | `app/frontend/scripts/check-visual-discipline.sh`                                                           |
| Admin-shell smoke test                             | `app/frontend/src/__tests__/shell.test.tsx`                                                                 |
| Frontend test command                              | `pnpm test` (Jest + RTL via `next/jest`)                                                                    |
| Frontend dev command                               | `pnpm dev` (Next.js dev server on port 3000)                                                                |
| Docker dev image stage                             | `dev` target in `Dockerfile.frontend`                                                                       |
| Docker production image stage                      | `runtime` target in `Dockerfile.frontend` (T06 wires Cloud Run on top)                                      |
