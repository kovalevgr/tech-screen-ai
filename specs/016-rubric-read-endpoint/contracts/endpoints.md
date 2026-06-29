# Contract: Rubric read endpoint

Design reference. The **committed** contract is the regenerated
`app/backend/openapi.yaml` (path + the `RubricSnapshot` components) plus the
existing `docs/contracts/rubric-snapshot.schema.json`. T14 generates its client
from `openapi.yaml`.

| Method | Path | Body | Success | Errors |
| --- | --- | --- | --- | --- |
| GET | `/rubric/active` | — | `200` `RubricSnapshot` (active version's full tree) | `404` (no active version), `401` (unauthenticated), `403` (wrong role) |

Notes:
- recruiter/admin only (reuses the T13 auth seam).
- Read-only; the rubric is never edited via the API (edits are Git/YAML + PR).
- The response shape is exactly `RubricSnapshot` (T15): `rubric_tree_version_id`,
  `label`, `stacks[] → competency_blocks[] → competencies[] → {topics[], levels[]}`,
  ids carried as plain values.
- Leaves room for a future `GET /rubric/{version_id}` (Rubric Browser, screen 15).
