# 11 — Recruiter Dashboard

Home screen for recruiters. Lists sessions with filters and quick actions.

**Route:** `/dashboard`.
**Audience:** recruiter.
**Language:** Ukrainian labels; English technical terms kept where idiomatic.

---

## Purpose

Give the recruiter a scannable overview of their sessions and a one-click path to the most common actions: review a completed session, check a live one, create a new one.

---

## States

### Populated

- Top bar: page title, candidate-search `Command`, new-session CTA.
- Filter bar: state multi-select, date range, owner (if more than one recruiter).
- Table of sessions.

### Empty (no sessions yet)

- `EmptyState` with a CTA "Створити першу сесію".

### Loading

- Skeleton rows (10 of them) while data fetches.

### Error

- Inline `Alert` "Не вдалося завантажити. Спробуйте оновити сторінку." No raw error.

---

## Layout

- **Header** (sticky): page title "Сесії", search, primary CTA "Нова сесія".
- **Filter bar**: state chips (toggle-on-click), date range picker, owner filter.
- **Table** columns:
  - Candidate name
  - Position / area
  - `SessionStateChip`
  - Scheduled / started at
  - Level summary (level chips for L1–L4 if session assessed; otherwise "—")
  - Red-flag badges (if any)
  - Actions (`dropdown-menu`: review, copy link, archive)

Rows are keyboard-navigable; `Enter` on a row opens the relevant next screen (`12` for `SCHEDULED`, `13` for `IN_PROGRESS`, `14` for `COMPLETED`).

---

## Interactions

- **Search** opens `Command` (Cmd+K) with live results across candidate name, email, session id.
- **Bulk actions** — not at MVP. Single-row actions only.
- **Pagination** — 25 rows per page. Cursor-based, not offset.

---

## Accessibility

- Table has a caption "Список сесій".
- Sortable columns announce sort state.
- Row-click is keyboard-equivalent to `Enter` on the row.

---

## Components used

- `Table` (shadcn)
- `Badge` via `SessionStateChip`, `LevelChip`, `RedFlagBadge`
- `Button`, `DropdownMenu`, `Command`, `Alert`, `Skeleton`, `EmptyState`
