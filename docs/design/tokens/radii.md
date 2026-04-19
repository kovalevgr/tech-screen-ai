# Radii

Border-radius scale. Consistent radii give the product one voice across panels, buttons, inputs, and chips.

The scale is calibrated against the Chat-iX reference (`docs/design/references/`) — buttons and inputs are gently rounded (6 px), chips and checkboxes more tightly (4 px), cards and modals slightly larger (10 px). Nothing is sharply pill-shaped except true pills (status chips, avatars).

---

## Scale

| Token         | Value   | Tailwind        | Use                                                |
| ------------- | ------- | --------------- | -------------------------------------------------- |
| `radius.none` | 0 px    | `rounded-none`  | Full-bleed dividers, table rows, never interactive |
| `radius.xs`   | 2 px    | `rounded-[2px]` | Inline tags, key-cap shapes                        |
| `radius.sm`   | 4 px    | `rounded-sm`    | Checkboxes, small chips, inline code               |
| `radius.md`   | 6 px    | `rounded-md`    | Buttons, inputs, dropdowns, small cards (default)  |
| `radius.lg`   | 10 px   | `rounded-lg`    | Cards, panels, popovers                            |
| `radius.xl`   | 14 px   | `rounded-xl`    | Modal dialogs only                                 |
| `radius.pill` | 9999 px | `rounded-full`  | Status pills, avatars, primary CTA when icon-only  |

No `rounded-2xl`. No custom `rounded-[14px]` outside this table — `radius.xl` is exactly 14 px. If a spec calls for something between, pick the nearest token.

---

## Rules

- **Buttons and inputs share the same radius** (`radius.md = 6 px`). They visually align when side-by-side. Matches the input + send icon row at the bottom of `hellow_page.png`.
- **Primary CTA** uses `radius.md` even when prominent (the orange `+ New chat` button in the reference is gently rounded, not pill).
- **Outline / secondary actions** ("All", "Clear" in `admin_page.png`) also `radius.md`.
- **Checkboxes** are `radius.sm = 4 px`.
- **Cards and panels** are `radius.lg = 10 px`. The whole table chrome in `admin_page.png` is one `radius.lg` panel with `border.default`.
- **Modal dialogs** are `radius.xl = 14 px`. They are the only place `xl` is allowed.
- **Status pills are always `radius.pill`.** Never a soft rounded rectangle — the pill shape is the signal.
- **Avatars are `radius.pill`.** No square avatars.
- **Turn bubbles** use `radius.lg` on all four corners. We do not use asymmetric "chat tail" shapes — they add visual noise with no signal.

---

## Combining with borders

Most rounded shapes pair with `border.default` (1 px). Cards: 1 px `border.default` + `radius.lg`. Inputs: 1 px `border.default` + `radius.md`, switching to `border.strong` on hover and to `focus.ring` (2-px outline + 2-px offset) on focus.

We do not stack shadows on rounded surfaces in the main interface. The reference deliberately uses borders, not shadows, to define surface edges. The only allowed shadow is on popovers and dropdowns: `0 8px 24px rgba(17, 17, 17, 0.08)`.

---

## Export

Tokens exported in `tokens.ts`. Tailwind theme overrides the default `borderRadius` scale with this table.

## Document versioning

- v1.1 — 2026-04-19. Tightened to match Chat-iX reference: introduced `radius.xs` (2 px), shrunk `md` from 8 → 6 px, shrunk `lg` from 12 → 10 px, shrunk `xl` from 16 → 14 px. Added explicit border-vs-shadow rule (borders define edges, shadows reserved for popovers).
- v1.0 — 2026-04-18. Initial scale.
