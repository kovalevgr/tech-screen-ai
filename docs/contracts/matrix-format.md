# Matrix workbook format (T08, FR-003)

Reference for the `.xlsx` workbook the matrix importer (`python -m app.backend.cli.import_matrix`) consumes. A maintainer can produce a conforming workbook from this document alone, without reading code.

## File and sheet structure

- One Excel workbook (`.xlsx`) per delivery.
- **One sheet per stack.** The sheet name is the stable `stack-id` (snake_case + dots, e.g. `python`, `react`). The sheet name maps 1:1 to the file name of the YAML output (`configs/rubric/<stack-id>.yaml`).
- Sheets whose name starts with `_` (e.g. `_notes`) are ignored.

## Column convention

The first row of each sheet is the header. Columns (case-sensitive, order does not matter):

| Header | Required? | Type | Semantics |
| ------ | --------- | ---- | --------- |
| `block` | yes | text | The competency-block name (`competency_block.name` in the DB). |
| `competency_id` | yes | text | Stable id of the competency node. Snake_case + dots (regex `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$`). |
| `competency_label_uk` | yes | text | Candidate-facing UK label (`label_uk`). |
| `competency_label_en` | yes | text | Internal EN label (`label_en`). |
| `topic` | optional | text | Topic name (`topic.name`). Empty means "no topic on this row". |
| `level` | yes | integer 1..5 | Proficiency level. |
| `descriptor_en` | yes | text | Internal EN descriptor for this level. Required (§11). |
| `level_label_uk` | yes | text | UK label for this level (e.g. "Початковий" / "Просунутий"). |
| `evidence_examples` | optional | text | Semicolon-separated list (`;`) of EN evidence examples for this level. |
| `competency_retired` | optional | boolean (`true`/`false`/empty) | Mark a competency retired. Default `false`. |

## Row semantics

- One row contributes **one** `(competency, level)` tuple. The importer groups rows by `(block, competency_id)` and emits one YAML node per competency, with a `levels` array carrying the 1–5 entries.
- A competency with no rows at level N has no entry at level N in the output — but a competency must have at least one level row (typically 1..5).
- Empty cells in optional columns are tolerated.
- Empty cells in required columns trigger a precise error (the cell coordinate is named in stderr).

## Quirk rules (research §8)

- **Merged cells spanning a key column** (`block`, `competency_id`, `topic`, `level`) are rejected. Fill down before saving.
- **Unicode normalisation**: cell strings are NFC-normalised before processing. Avoids "byte-different but visually identical" duplicates.
- **Semicolon separator** for `evidence_examples`. Trailing semicolons are tolerated and produce no empty examples. Excel autocompletes commas inside cells; the semicolon survives that autocomplete.
- **HTML entities** (e.g. `&amp;`) are passed through verbatim. Cells are plain text; if you want an `&` write `&`, not `&amp;`.
- **Empty trailing rows** are tolerated (the importer stops at the first row whose required cells are all empty).
- **Sheet names** starting with `_` are ignored (e.g. `_changelog`, `_notes`).

## Output canonicalisation (research §2, §7)

The importer emits YAML with the following invariants (so re-running on unchanged input is byte-identical, SC-002):

- `sort_keys=True` (alphabetical key order within each mapping).
- `default_flow_style=False` (block style — one item per line).
- `allow_unicode=True` (UTF-8, no `\xNN` escapes).
- `indent=2`, `width=120`, explicit `line_break="\n"`.
- `nodes` array sorted by `id` ascending.
- Each node's `levels` array sorted by `level` ascending.

## Payload hash (research §3)

The seed path's idempotency check uses the **SHA-256** of the concatenation of the canonical UTF-8 bytes of every `configs/rubric/*.yaml` file, **sorted by filename**, separated by a single `0x00` byte. The 64-character hex string is stored in `rubric_tree_version.payload_hash` and is the only signal the importer uses to decide between no-op and new-version paths.

## Advisory lock (research §6)

The seed transaction takes `pg_advisory_xact_lock(987654321)` at the start; the lock is released automatically on COMMIT or ROLLBACK. Two concurrent seed runs therefore serialise without UNIQUE-constraint violations.

## Renames are forbidden (FR-009, SC-005)

If a stable `competency_id` value disappears from a YAML payload between versions WITHOUT being marked `retired: true` in the new payload, the importer rejects the seed with a precise error naming the disappeared id. Policy: **retire the old id (set `competency_retired: true` in the workbook), then introduce the new id as a separate row set in a follow-up edit**. Outright deletion is forbidden — old session snapshots rely on the id resolving in their frozen rubric tree (§4 / ADR-018).

## Example minimal workbook

A single sheet named `python` with three rows (one block, one competency, three levels):

| block | competency_id | competency_label_uk | competency_label_en | topic | level | descriptor_en | level_label_uk | evidence_examples |
| ----- | ------------- | ------------------- | ------------------- | ----- | ----- | ------------- | -------------- | ----------------- |
| Core | `python.concurrency` | Конкурентність | Concurrency | Threading | 1 | Knows threads exist; can describe the GIL in one sentence. | Початковий | Mentions threading without describing when it helps; cannot state what the GIL protects |
| Core | `python.concurrency` | Конкурентність | Concurrency | Asyncio | 3 | Confidently chooses between threading, multiprocessing, asyncio for typical IO/CPU cases. | Середній | Designs an async pipeline; reasons about back-pressure |
| Core | `python.concurrency` | Конкурентність | Concurrency | (empty) | 5 | Designs a custom scheduler / reasons about subtle interpreter behaviour. | Експерт | Diagnoses a deadlock from a thread-dump; understands GIL release patterns in C extensions |

After conversion: `configs/rubric/python.yaml` with one node `python.concurrency` and three levels (1, 3, 5).
