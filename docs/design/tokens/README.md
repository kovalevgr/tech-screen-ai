# Design Tokens

Source-of-truth design values that propagate to Tailwind theme and component code. Components never reference raw hex / px values — only tokens. A one-off deviation is a token bug; fix the token.

Tokens come from the N-iX brand references in `../references/` (`hellow_page.png`, `admin_page.png` — the Chat-iX screens we treat as the visual baseline, see principle §9). Where the references are silent, values are chosen for legibility, accessibility, and density goals in `../principles.md`.

The product is light-theme only at MVP. These token files describe light values. A dark-mode addition is a future deliberate project — do not silently add `dark:` variants.

## Files

- [`colors.md`](./colors.md) — light palette, semantic roles, brand-orange usage rules, level / red-flag / status chip mappings.
- [`typography.md`](./typography.md) — font stack, scale, line-heights, weights.
- [`spacing.md`](./spacing.md) — 4-px base scale, component-level rules, layout grid.
- [`radii.md`](./radii.md) — border radii scale.
- [`motion.md`](./motion.md) — durations, easings, reduced-motion rules.

## How tokens reach the code

1. Token tables in these `.md` files are the source of truth.
2. `app/frontend/src/design/tokens.ts` exports the same values as TypeScript constants.
3. `tailwind.config.ts` extends the theme from `tokens.ts`.
4. Components use Tailwind classes (`bg-surface-muted`, `text-body`, `p-4`) or the TS constants (rarely — only where Tailwind cannot reach, e.g., inline SVG fills).

A token change flow:

- Edit the relevant `.md` file here.
- Update `tokens.ts` to match.
- Screenshot-diff runs in CI (Playwright visual regression) to catch accidental visual drift.

## Document versioning

- v1.1 — 2026-04-19. Pointed at the Chat-iX reference screens; noted light-theme-only MVP and banned silent `dark:` variants.
- v1.0 — 2026-04-18. Initial token index.
