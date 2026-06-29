# Data Model: Position Template admin UI (T14)

No database. The "model" here is (a) the API types consumed from the generated
client and (b) the UI's form/view state. No new persisted entity.

## API types (generated — `src/api/schema.d.ts` from `openapi.yaml`)

- **PositionTemplateRead** — `id, title, level, jd_text, archived_at, created_at, created_by, stack_ids[], competencies[{competency_id, must_have}]`.
- **PositionTemplateCreate** — `title, level, jd_text?, stack_ids[], competency_ids[], must_have_competency_ids[]`.
- **PositionTemplateUpdate** — all optional (partial), selection sets replace wholesale.
- **RubricSnapshot** (from `/rubric/active`) — `rubric_tree_version_id, label, stacks[{id, name, competency_blocks[{id, name, position, competencies[{id, name, topics[], levels[]}]}]}]`.

These types are imported, never re-declared.

## React Query hooks (`src/api/`)

| Hook | Endpoint | Notes |
| --- | --- | --- |
| `usePositionTemplates(includeArchived)` | GET `/position-templates?include_archived=` | list query |
| `usePositionTemplate(id)` | GET `/position-templates/{id}` | edit prefill |
| `useCreatePositionTemplate()` | POST `/position-templates` | invalidates list |
| `useUpdatePositionTemplate(id)` | PATCH `/position-templates/{id}` | invalidates list + item |
| `useArchivePositionTemplate(id)` | DELETE `/position-templates/{id}` | invalidates list |
| `useActiveRubric()` | GET `/rubric/active` | form options |

## Form state (`PositionForm`)

```
title: string                       // required, 1..200
level: "Junior"|"Middle"|"Senior"|"Tech Leader"
jdText: string | ""                 // optional
selectedStackIds: Set<uuid>         // checkbox group from active rubric
selectedCompetencyIds: Set<uuid>    // checkbox group scoped to selected stacks
mustHaveCompetencyIds: Set<uuid>    // ⊆ selectedCompetencyIds
```

Derived: the competency options = competencies whose block's stack is in
`selectedStackIds`. Deselecting a stack prunes its competencies (and their
must-have flags) from the selections.

## Client-side validation (mirrors the contract; server is source of truth)

- `title` non-empty; `level` chosen.
- `selectedCompetencyIds` ≥ 1.
- `mustHaveCompetencyIds ⊆ selectedCompetencyIds`.
- every selected competency belongs to a selected stack.
- On submit, a server `422` is surfaced inline at the offending field; the form keeps the user's input.

## Component tree

```
/positions (page)        → PositionTable(usePositionTemplates) + include-archived toggle + "+ Нова позиція"
                           → archive confirm Dialog (useArchivePositionTemplate)
/positions/new (page)    → PositionForm(mode=create, useActiveRubric, useCreatePositionTemplate)
/positions/[id] (page)   → PositionForm(mode=edit, usePositionTemplate(id), useActiveRubric, useUpdatePositionTemplate)
```

## States (per design §10)

Loaded / loading (skeleton) / empty (prose + CTA) / error (incl. 404 feature-off,
401 sign-in, 403 forbidden, rubric-unreadable → submit disabled). Detailed in the
screen spec `docs/design/screens/16-recruiter-positions/spec.md`.
