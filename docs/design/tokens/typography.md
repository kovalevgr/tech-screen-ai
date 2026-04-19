# Typography

Fonts, scale, weights, and how text behaves under Ukrainian copy (which runs 30–40 % longer than English).

---

## Font stack

- **Primary (all UI):** `Inter`, loaded via `next/font/google` with Latin + Cyrillic subsets.
- **Monospace (code, ids, hashes):** `JetBrains Mono`, Latin + Cyrillic.

Rationale: both fonts have full Ukrainian Cyrillic coverage, excellent hinting at small sizes, and a sibling mono that shares metrics. Inter is the default shadcn/ui recommendation; we stay on the well-trodden path.

Fallback stack:

```
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
font-family: 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, monospace;
```

---

## Scale

| Token             | Size  | Line height | Use                                                                                                                                                                   |
| ----------------- | ----- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `text.display`    | 32 px | 40 px       | Dashboard headline, session title, empty-state hero (the "IT is AI" treatment in `docs/design/references/hellow_page.png`, rendered in `brand.primary` + `font.bold`) |
| `text.headline`   | 24 px | 32 px       | Section headers                                                                                                                                                       |
| `text.title`      | 20 px | 28 px       | Card titles, panel headers                                                                                                                                            |
| `text.subtitle`   | 18 px | 26 px       | Sub-section labels, prominent list titles                                                                                                                             |
| `text.body`       | 16 px | 24 px       | Primary reading size, candidate-facing                                                                                                                                |
| `text.body-dense` | 14 px | 20 px       | Recruiter tables, dense panels                                                                                                                                        |
| `text.caption`    | 13 px | 18 px       | Metadata, timestamps, secondary labels                                                                                                                                |
| `text.small`      | 12 px | 16 px       | Chips, badges, tiny meta                                                                                                                                              |

Candidate screens use `text.body` as the minimum. Recruiter screens may use `text.body-dense`. Never below `text.caption` in body copy.

---

## Weights

| Token           | Value | Use                          |
| --------------- | ----- | ---------------------------- |
| `font.regular`  | 400   | Body                         |
| `font.medium`   | 500   | Labels, emphasis within body |
| `font.semibold` | 600   | Titles, CTAs                 |
| `font.bold`     | 700   | Rare — display only          |

Italic is reserved for Ukrainian quotations and citations. We do not italicise for emphasis; use weight instead.

---

## Line height rules

Line heights above are minimums for Ukrainian copy. Ukrainian has descenders (`р`, `щ`, `у`) that crowd tight leading. Never drop below the values in the table, even for visual compactness.

---

## Letter spacing

Default: `0` (Inter ships generous default tracking).

Exceptions:

- All-caps labels — section kickers and table column headers (`USER`, `DEPARTMENT`, `CONVERSATIONS`, etc., as in `docs/design/references/admin_page.png`): `+0.04em` tracking, `text.small` (12 px), `font.medium` weight, `content.muted` colour.
- Numeric displays (large cost or time digits): `-0.01em`.

All-caps is **for labels only** — kickers, column headers, chip text. Never for body copy or sentences. Ukrainian all-caps in running text is unusual and reads as shouting.

---

## Candidate-facing typography

- `text.body` minimum.
- Line length: 56–72 characters. Enforce via `max-w-prose` or an explicit `max-w-[64ch]` on the paragraph container.
- No all-caps.
- Paragraph spacing: `spacing.4` (16 px) between paragraphs.
- Questions from the interviewer render in `font.medium` to distinguish from candidate replies without colour.

---

## Recruiter-facing typography

- Dense tables use `text.body-dense` (14 px).
- Chip text uses `text.small` (12 px), always bold-weight `font.medium` for legibility.
- Turn bubble body: `text.body` (16 px) even on recruiter view — we are reading candidate answers, not summarising them.

---

## Monospace usage

- IDs (`session_id`, `turn_id`, commit SHAs).
- Code snippets in answer replay.
- Cost and latency values in dashboards (tabular-numeral alignment).

Never use mono for Ukrainian body copy.

---

## Tabular numerals

Enable `font-feature-settings: "tnum"` wherever numbers align vertically (dashboards, cost columns). Tailwind class `tabular-nums`.

---

## Truncation

- Prefer wrapping over truncation for primary copy.
- Truncation (`text-ellipsis`) is acceptable on single-line meta in table cells; the full value must appear on hover / focus (via `title` or a shadcn tooltip).
- Never truncate the candidate's name in the header. Wrap or go to two lines.

---

## Export

- `app/frontend/src/design/tokens.ts` exports `typography` object.
- Tailwind theme maps: `text-display`, `text-headline`, `text-title`, `text-subtitle`, `text-body`, `text-body-dense`, `text-caption`, `text-small`.
- Font weights: Tailwind's `font-normal` / `font-medium` / `font-semibold` / `font-bold` map to our tokens.

## Document versioning

- v1.1 — 2026-04-19. Aligned with Chat-iX reference. Clarified that all-caps is for labels (kickers, column headers) — not banned outright. Noted the empty-state hero treatment (brand-orange display) as in `hellow_page.png`.
- v1.0 — 2026-04-18. Initial scale.
