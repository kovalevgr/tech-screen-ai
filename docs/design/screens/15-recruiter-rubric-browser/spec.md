# 15 — Recruiter Rubric Browser

Read-only browser of rubric versions and snapshots.

**Route:** `/rubrics`.
**Audience:** recruiter (read), engineer (source of truth is the YAML in Git).
**Language:** Ukrainian labels, English technical.

---

## Purpose

Let recruiters inspect current and historical rubrics without exposing any editing affordance. Rubric edits happen through the `rubric-yaml` skill + PR flow, not in the UI (ADR-021).

---

## States

### List view (default)

- Table of `rubric_tree_version`s: version id, created by, created at, notes.
- "Current" pill on the active version.
- Each row clickable to open the detail view.

### Detail view

- `RubricTree` at the top (collapsed by default).
- Metadata panel: version, commit sha, who, when, linked ADR (if any).
- A list of sessions using this version (count; link to dashboard filtered by version).

### Empty

- Never happens at MVP (v1 is seeded at bootstrap). If it does, `EmptyState` with a pointer to the seeding docs.

---

## Layout

Simple single-column. `Table` on the list view; two-panel (tree + metadata) on detail.

---

## Interactions

- **No editing.** No "new version", no "edit". The page is a viewer.
- **Clicking a node** shows its full prose + level descriptors in a popover.

---

## Accessibility

- Tree uses `treeview` role; arrow-key navigation.
- Metadata table has explicit headers.

---

## Components used

- `Table`, `Card`, `Badge`, `Popover`
- `RubricTree` (read-only variant)
