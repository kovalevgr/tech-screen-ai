# Spacing

4-px base scale. Every spacing value in the product comes from this table. Components reference tokens via Tailwind utilities (`p-4`, `gap-6`), never arbitrary pixel values.

Calibrated against `docs/design/references/` — the Chat-iX references use the same 4/8/16/24 rhythm. Reference observations:

- Sidebar width ~240 px. Sidebar item row: `space.3` X / `space.2` Y. List-to-item gap: `space.1`.
- Top bar height ~64 px, vertical centring via auto-margin, horizontal padding `space.6`.
- Table column header row: `space.3` Y. Table body cell row: `space.4` Y. Generous — rows are easy to scan.
- The empty-state hero ("IT is AI") has ~`space.16` of breathing room above and below.

---

## Scale

| Token      | Value | Tailwind | Typical use                    |
| ---------- | ----- | -------- | ------------------------------ |
| `space.0`  | 0 px  | `p-0`    | Reset                          |
| `space.1`  | 4 px  | `p-1`    | Inline icon-to-text gap        |
| `space.2`  | 8 px  | `p-2`    | Chip padding, tight stack      |
| `space.3`  | 12 px | `p-3`    | Compact buttons, dense rows    |
| `space.4`  | 16 px | `p-4`    | Default padding, paragraph gap |
| `space.5`  | 20 px | `p-5`    | Form field spacing             |
| `space.6`  | 24 px | `p-6`    | Card padding, section gap      |
| `space.8`  | 32 px | `p-8`    | Panel padding                  |
| `space.10` | 40 px | `p-10`   | Large section gap              |
| `space.12` | 48 px | `p-12`   | Hero / empty state padding     |
| `space.16` | 64 px | `p-16`   | Page-level vertical rhythm     |

No half-steps, no `space.7`, no `space.11`. If something "almost fits" at 28 px, it fits at 24 or 32.

---

## Layout grid

- **Max content width:** 1280 px (`max-w-screen-xl`). Larger displays gain side padding, not content.
- **Gutter (between columns):** `space.6` (24 px).
- **Column count:** 12 on ≥ lg (1024 px), 8 on md (768 px), 4 on sm (< 768 px).
- **Page side padding:** `space.6` on md+, `space.4` on sm.

The recruiter dashboard uses the 12-col grid. Candidate screens are a single column with `max-w-[64ch]` on paragraphs; the grid is mostly decorative for them.

---

## Component-level rules

### Buttons

- Padding X: `space.4` (16 px). Padding Y: `space.2` (8 px).
- Small variant: X `space.3`, Y `space.1`.
- Icon-only: `p-2`, square aspect.
- Gap between button icon and label: `space.2`.

### Cards

- Padding: `space.6` (24 px).
- Between card sections (header / body / footer): `space.4`.
- Between sibling cards in a stack: `space.4`.

### Forms

- Gap between label and input: `space.1` (4 px).
- Gap between field groups: `space.5` (20 px).
- Gap between sections in a long form: `space.8` (32 px).

### Tables

- Cell padding X: `space.4`. Cell padding Y: `space.3`.
- Header cell padding Y: `space.2` (tighter than body cells).
- Row divider: 1 px `border.subtle`.

### Turn bubbles (candidate dialogue)

- Bubble padding: `space.4` (16 px).
- Gap between sibling bubbles: `space.3` (12 px).
- Gap between sender name and bubble: `space.1`.

### Chips / badges

- Padding X: `space.2` (8 px). Padding Y: `space.1` (4 px).
- Gap between chip icon and text: `space.1`.

---

## Vertical rhythm

- Between paragraphs: `space.4` (16 px).
- Between heading and following paragraph: `space.3` (12 px).
- Between a section heading and a form below: `space.5` (20 px).

---

## Touch targets

Minimum 40 × 40 px for any interactive element on the candidate side (sessions may be on laptops but we do not want to be the reason someone misses a click). Recruiter UI may use 32 × 32 px for secondary actions.

---

## Export

Tokens exported in `tokens.ts`, referenced by Tailwind config. Default Tailwind spacing scale is overridden to match this table exactly (no stray `w-7`).

## Document versioning

- v1.1 — 2026-04-19. Annotated with observed measurements from the Chat-iX reference screens. Scale unchanged.
- v1.0 — 2026-04-18. Initial 4-px scale.
