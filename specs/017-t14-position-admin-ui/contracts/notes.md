# Contract: Position Template admin UI (T14)

T14 **authors no contract** — it consumes the committed backend contract.

- **Source of truth**: `app/backend/openapi.yaml` (paths `/position-templates`,
  `/position-templates/{template_id}`, `/rubric/active`; components
  `PositionTemplateCreate/Read/Update`, `CompetencySelection`, `RubricSnapshot`
  and its nested `Snapshot*`).
- **Generated artefact**: `app/frontend/src/api/schema.d.ts`, produced by
  `openapi-typescript` from `openapi.yaml` (committed; regenerate via
  `pnpm gen:api` whenever `openapi.yaml` changes). The UI's types come from here.
- **JSON-schema contracts** (already committed, T12/T15): `docs/contracts/position-template.schema.json`, `docs/contracts/rubric-snapshot.schema.json`.

If `openapi.yaml` and `schema.d.ts` drift, regenerate; CI builds against the
committed lockfile + committed types (no network).
