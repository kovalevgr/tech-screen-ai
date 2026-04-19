# Colors

Semantic colour roles first. Raw palette is the implementation detail.

All interactive states meet WCAG 2.2 AA contrast (4.5 : 1 for body, 3 : 1 for large text and UI controls). Contrast is checked in CI via `axe-core`.

The palette is calibrated against `docs/design/references/hellow_page.png` and `docs/design/references/admin_page.png` — the N-iX Chat-iX reference screens. When a token disagrees with the references, the token is wrong.

TechScreen ships light-theme only at MVP (principle §6). This file documents light values only. A future dark-mode addition is a deliberate project with its own token table — do not silently add `dark:` variants.

---

## Semantic roles

Components use Tailwind classes that map to these roles (`bg-surface-base`, `text-content-muted`, etc.), never raw hex.

| Role | Value | Used for |
| --- | --- | --- |
| `surface.base` | `#FFFFFF` | Main page canvas; candidate session background |
| `surface.raised` | `#FAFAFA` | Sidebar, side panels, footer ribbon |
| `surface.muted` | `#F4F4F5` | Subtle containers, table zebra, empty-state backdrop |
| `surface.sunken` | `#EEEEF0` | Code blocks, inline mono backdrops |
| `surface.inverted` | `#1A1A1A` | Tooltips, inverted badges — rare |
| `border.subtle` | `#ECECEE` | Row separators inside tables, sidebar-to-canvas divider |
| `border.default` | `#E3E3E6` | Card borders, input borders at rest |
| `border.strong` | `#CFCFD3` | Input borders on hover, focus-adjacent emphasis |
| `content.primary` | `#111111` | Body text, strong headings |
| `content.secondary` | `#4B4B52` | Supporting text, table cell body |
| `content.muted` | `#8A8A93` | Captions, metadata, "N users" annotations |
| `content.subtle` | `#B4B4BB` | Placeholder text, disabled text |
| `content.inverted` | `#FFFFFF` | Text on filled brand buttons |
| `brand.primary` | `#E8573C` | Primary CTA fill, wordmark, filled checkbox |
| `brand.primary-hover` | `#D04A30` | Primary CTA hover |
| `brand.primary-active` | `#B53D25` | Primary CTA pressed |
| `brand.primary-subtle` | `#FDECE6` | Soft brand surface (hover row, selected row tint) |
| `brand.link` | `#E8573C` | Text links, back-to links ("Back to Chat") |
| `brand.link-hover` | `#C94026` | Text link hover |
| `status.info` | `#2B6FB4` | Informational chips — used sparingly, not the primary voice |
| `status.info-subtle` | `#EAF2FB` | Info chip background |
| `status.success` | `#1E8554` | Completed, passed, saved |
| `status.success-subtle` | `#E6F4EC` | Success chip background |
| `status.warning` | `#9A6B00` | Paused, warning-only calibration, needs review |
| `status.warning-subtle` | `#FBF1DC` | Warning chip background |
| `status.danger` | `#B42318` | Errors, destructive confirmations, halted sessions |
| `status.danger-subtle` | `#FBEAE8` | Danger chip background |
| `status.neutral` | `#6C6C75` | Inactive / scheduled / tertiary state |
| `status.neutral-subtle` | `#F0F0F2` | Neutral chip background |
| `focus.ring` | `#E8573C` | Keyboard focus ring (2-px outline, 2-px offset) |
| `overlay.scrim` | `rgba(17, 17, 17, 0.45)` | Modal scrims (rare — candidate session avoids modals, §2) |

---

## Level palette

Assessment levels (1 – 4) have a fixed colour mapping. These live on the recruiter side only; candidates never see them. They are a *status* scale, not a *brand* scale — do not use brand orange here.

| Level | Name | Fill | Subtle background | Notes |
| --- | --- | --- | --- | --- |
| 1 | Entry | `#6C6C75` | `#F0F0F2` | Neutral, never alarming |
| 2 | Specialist | `#2B6FB4` | `#EAF2FB` | Info-blue |
| 3 | Confident | `#1E8554` | `#E6F4EC` | Success-green |
| 4 | Expert | `#9A6B00` | `#FBF1DC` | Warm amber |

Levels are always labelled textually in addition to the colour. Colour alone is never the signal (accessibility).

---

## Red flags palette

Red flags are orthogonal to levels and use the danger role, with an amber fallback for softer categories.

| Flag | Fill | Subtle background |
| --- | --- | --- |
| `FACTUALLY_WRONG` | `#B42318` | `#FBEAE8` |
| `CONTRADICTION` | `#B42318` | `#FBEAE8` |
| `FABRICATED_TECHNOLOGY` | `#B42318` | `#FBEAE8` |
| `LIKELY_CHEATING` | `#B42318` | `#FBEAE8` |
| `RED_FLAG_OTHER` | `#9A6B00` | `#FBF1DC` |

---

## Session state chip mapping

Every session badge uses exactly one semantic role. No per-state hex.

| State | Role |
| --- | --- |
| `SCHEDULED` | `status.neutral` |
| `IN_PROGRESS` | `status.info` |
| `COMPLETED`, `ASSESSED` | `status.success` |
| `PAUSED`, `HALTED_UPSTREAM` | `status.warning` |
| `HALTED_COST_CEILING`, `CANCELLED` | `status.danger` |
| `NEEDS_MANUAL_REVIEW` | `status.warning` with dotted 1-px border |

---

## Where the brand appears

Keep this list short. If a screen wants to add a new brand-orange element, it goes on this list first.

- The N-iX wordmark in the top bar.
- The primary CTA per screen (one per screen max — usually `+ New …` or the primary form submit).
- The "Back to …" link-style navigation, with a leading arrow.
- The filled state of checkboxes (`admin_page.png`).
- A single optional emphasis word or glyph in the empty-state display ("IT is AI" treatment). One per page.
- The focus ring.
- Error / alert iconography does *not* use brand orange — it uses `status.danger`. Orange is *not* a warning colour here.

---

## What we explicitly do not use

- Pure black (`#000`). It reads as ink-on-paper but clashes with the warm-neutral surface scale. Use `content.primary = #111111`.
- Pure white text on light — only on the brand orange fill.
- Gradients in UI chrome. Gradients only in marketing materials (out of scope for this repo).
- Colour alone to convey state. Always paired with icon or text.
- Blue as a primary brand. Blue appears only as `status.info` and is used sparingly. The product voice is orange-on-white, not blue-on-white.

---

## Export

`app/frontend/src/design/tokens.ts` exports these values as a typed object. Tailwind theme extension reads them in `tailwind.config.ts`. Source of truth is this file; the TS file is kept in sync manually (a one-file lint rule diffs the two and fails CI on drift).

## Document versioning

- v1.1 — 2026-04-19. Repalette after adopting the Chat-iX reference screens: brand moved from `#2E5BFF` blue to `#E8573C` N-iX orange; dark-mode column dropped (light-first, principle §6); level palette reshuffled to status-scale (neutral → info → success → amber) to stop competing with brand; added `brand.primary-subtle`, `surface.sunken`, `content.subtle`, and per-status subtle backgrounds; "Where the brand appears" section added to keep orange disciplined.
- v1.0 — 2026-04-18. Initial token table with dual light/dark columns and blue brand.
