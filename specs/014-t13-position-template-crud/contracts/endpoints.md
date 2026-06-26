# Contract: Position Template endpoints (T13)

Design reference. The **committed** contract is the regenerated
`app/backend/openapi.yaml` (paths + components, derived from the Pydantic models)
plus T12's `docs/contracts/position-template.schema.json` (shapes). T14 generates
its client from `openapi.yaml`.

Base path: `/position-templates`. All operations are gated by the §9 flag
`position_template_crud_enabled` (**404** when off) and then require role
`recruiter` or `admin` (401 if unauthenticated, 403 if wrong role).

| Method | Path | Request body | Query | Success | Errors |
| --- | --- | --- | --- | --- | --- |
| POST | `/position-templates` | `PositionTemplateCreate` | — | `201` `PositionTemplateRead` | `422` validation, `401`, `403` |
| GET | `/position-templates` | — | `include_archived: bool = false` | `200` `PositionTemplateRead[]` | `401`, `403` |
| GET | `/position-templates/{id}` | — | — | `200` `PositionTemplateRead` | `404`, `401`, `403` |
| PATCH | `/position-templates/{id}` | `PositionTemplateUpdate` | — | `200` `PositionTemplateRead` | `422`, `404`, `401`, `403` |
| DELETE | `/position-templates/{id}` | — | — | `200` `PositionTemplateRead` (archived) | `404`, `401`, `403` |

Notes:
- `DELETE` is a **soft archive**: it sets `archived_at` and returns the archived
  template; it never removes the row.
- `GET` list excludes archived templates unless `include_archived=true`.
- `422` bodies carry a field-identifying message for stateful failures
  (unknown stack / competency-not-in-selected-stack), per FR-003/FR-011.
- Shapes (`PositionTemplateCreate`/`Read`/`Update`, `CompetencySelection`) are
  defined in `app/backend/schemas/position_template.py` and reflected in
  `openapi.yaml` components after regeneration.
