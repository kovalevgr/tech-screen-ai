# 12 — Recruiter Plan Review

Review and approve the pre-interview plan before the candidate joins.

**Route:** `/sessions/[id]/plan`.
**Audience:** recruiter.
**Language:** Ukrainian labels, English technical terms.

---

## Purpose

The Pre-Interview Planner produces a plan (Variant C, hybrid) tying competencies to seed questions and depth-probe branches. The recruiter reviews, tweaks, and approves before the candidate link goes out.

---

## States

### Draft (freshly generated)

- Summary header: candidate, position, competencies covered, estimated length.
- Plan body: tree view of competencies → seed questions → depth-probe branches.
- Actions: "Затвердити", "Згенерувати заново", "Редагувати вручну".

### Approved

- Plan is frozen (`interview_plan` becomes `rubric_snapshot`-backed).
- Read-only; badge "Затверджено" visible.
- Action "Надіслати запрошення кандидату" becomes primary.

### Regenerating

- Loading state on the plan body; header and actions unchanged.

---

## Layout

Two-column on lg+:

- Left (2/3): plan tree. Expandable competency cards. Each competency shows coverage goal, seed questions, and any depth-probe branches.
- Right (1/3): summary rail — session metadata, candidate info, action buttons pinned to top-right.

On md and below: single-column, actions move to a sticky bottom bar.

---

## Interactions

- **Manual edit** opens an inline editor per seed question (text + level hint).
- **Regenerate** re-runs the Planner; the user is prompted to confirm because it discards manual edits.
- **Approve** freezes the plan and transitions the session to `SCHEDULED`.
- **Cancel session** available in a less-prominent menu.

---

## Accessibility

- Plan tree uses a `treeview` role; nodes are keyboard-navigable with arrow keys.
- Destructive confirmations use `ConfirmDialog` with an explicit confirmation checkbox for "Regenerate".

---

## Components used

- `Card`, `Button`, `Dialog`, `ConfirmDialog`
- Custom: plan tree (a specialised instance of the `RubricTree` variant, not yet extracted)
- `LevelChip`, `Badge`
