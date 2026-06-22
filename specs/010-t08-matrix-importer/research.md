# Phase 0 Research: T08 — Matrix importer

Ten implementation-altitude decisions. Each is grounded in a constitution clause, an existing repo artefact, or a load-bearing Python/Postgres behaviour.

---

## §1 — xlsx parser library

**Decision**: `openpyxl >= 3.1, < 4`.

**Rationale**:
- Pure-Python, no native compilation, no system libs needed in the Docker image (so the `dev` stage doesn't grow). Verified by reading openpyxl's wheel metadata.
- Read-only is its strongest use case; we don't need cell formatting / charts / styles for the rubric matrix.
- Tiny dep tree (just `et-xmlfile`).
- Active maintenance; supports `.xlsx` (Office Open XML) which is the only format we accept.
- Programmatic workbook construction (used in fixture tests, research §9) is well-documented.

**Alternatives considered**:
- `pandas` — would also work but pulls in `numpy` (~30 MB), much heavier than we need for a read-only "iterate cells" use case. Rejected on weight.
- `xlrd` — legacy library; current versions dropped `.xlsx` support and only handle `.xls`. Rejected as the wrong format.
- `pyexcel` — wrapper around several backends; adds indirection for no gain. Rejected.

---

## §2 — Canonical YAML output

**Decision**: Use `yaml.safe_dump` with the kwargs that guarantee byte-identical reruns:
```python
yaml.safe_dump(
    payload,
    sort_keys=True,
    default_flow_style=False,
    allow_unicode=True,
    indent=2,
    width=120,
    line_break="\n",
)
```
Plus explicit pre-sort of the `nodes` list by `id`, and of each node's `levels` list by `level` integer (since `sort_keys=True` does not reorder list contents).

**Rationale**:
- `sort_keys=True` makes dict ordering deterministic.
- `default_flow_style=False` ensures block-style output (one item per line for readability + diff stability).
- `allow_unicode=True` writes UTF-8 directly instead of `\xNN` escapes (Ukrainian labels stay readable).
- `indent=2` and explicit `width=120` prevent line-wrap drift across PyYAML versions.
- Explicit `line_break="\n"` rules out CRLF / mixed line endings on Windows-edited workbooks.
- Manual list sorting on `nodes`/`levels` is necessary because YAML lists carry order; we choose a deterministic order (by `id` then by `level`) and document it as part of the canonical format contract.

**Alternatives considered**:
- `ruamel.yaml` — preserves comments + round-trip fidelity. Rejected: we control both the producer (convert) and the consumer (seed), no need to preserve user comments.
- Custom YAML emitter — overkill; PyYAML's safe_dump with the above kwargs already gives byte-identical output.

---

## §3 — Payload hash algorithm

**Decision**: SHA-256 of the concatenated canonical YAML bytes of every `configs/rubric/*.yaml` file, joined by a `0x00` byte separator and sorted by filename. Recorded as a 64-char hex string in `rubric_tree_version.payload_hash`.

**Rationale**:
- Filename-sorted concatenation gives a deterministic input across machines + OSes.
- `0x00` separator (a byte that cannot appear in UTF-8 text) makes the joined input unambiguous; no risk of an end-of-file `\n` collapsing into the next file's start.
- SHA-256 is cryptographically irrelevant here but is the standard "deterministic identifier" hash; one entry in the standard library, no extra dep.
- The recorded hex string is compact (64 chars), readable in `psql`, and indexable in Postgres (used by the UNIQUE constraint).
- Documented in `docs/contracts/matrix-format.md` so any future loader (T16 workflow, calibration tooling) can reproduce the hash deterministically.

**Alternatives considered**:
- Hash each YAML file independently and store a list — more complex bookkeeping; rejected.
- MD5 / xxhash — speed-irrelevant here (the hash is computed once per seed run). Rejected.
- Hash the parsed dict structure — relies on Python's serialisation which can vary by version. The on-disk canonical bytes are the contract; hash that. Rejected as fragile.

---

## §4 — `rubric_tree_version.payload_hash` migration shape

**Decision**: One additive column added via `0003_rubric_payload_hash.py`:
```sql
ALTER TABLE rubric_tree_version
  ADD COLUMN payload_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE rubric_tree_version
  ADD CONSTRAINT uq_rubric_tree_version_payload_hash UNIQUE (payload_hash);
```
The `DEFAULT ''` covers any legacy rows; at T08 time the table is empty in prod (T05 just landed schema, no rubric seeded yet), but the migration must still be safe. The empty string is unique (only one row can ever hold it), which is acceptable for the historical edge case where no real seed ever ran.

**Rationale**:
- Single additive column + UNIQUE constraint = minimal forward-only change (§10).
- `NOT NULL DEFAULT ''` keeps the migration valid even if rows existed; the importer's first real seed creates a fresh row with a real hash.
- UNIQUE protects FR-007 — two YAML payloads with the same hash cannot produce two distinct versions; the importer's check-then-insert path is therefore racing-resistant when paired with the advisory lock (research §6).
- Reversible `downgrade()`: drop UNIQUE constraint → drop column.

**Alternatives considered**:
- Encode the hash in `label` and parse it out at read time — fragile; semantic overload. Rejected.
- Separate `rubric_tree_payload` table 1:1 with `rubric_tree_version` — overkill for a single column. Rejected.
- BYTEA hash column — saves 32 bytes per row vs 64-char hex, but loses `psql` readability. Rejected: storage is irrelevant at this scale.

---

## §5 — Rename detection

**Decision**: Post-state check. After the seed has parsed the new YAML payload:
1. Build `new_active = { node.id for node in new_payload if not node.retired }`.
2. Load the previous `rubric_tree_version`'s active node ids (or every active id across all prior versions; configurable but default is the most-recent version's active set).
3. `disappeared = prior_active - new_active - new_retired`.
4. If `disappeared` is non-empty, fail with: `Stable id(s) {disappeared} disappeared from the new payload without being retired. Renames are forbidden — retire the old id (set retired: true) and introduce the new id as a separate node in a separate PR.`

**Rationale**:
- Detects the most common foot-gun: a maintainer changing `python.concurrency` to `python.threading` thinking they're "fixing the name".
- The check needs no diff history — it's a pure post-state comparison between the prior version's active set and the new payload's active+retired sets.
- "Most-recent version's active set" is the practical baseline; cross-version (every-version-ever-active) is stricter but redundant in the common case (a retired node stays retired). Use most-recent.
- The error message explicitly tells the maintainer the policy: retire old, introduce new (FR-009 / SC-005).

**Alternatives considered**:
- Levenshtein distance between disappeared/new ids — fuzzy, would produce false positives ("python.concurrency" vs "python.context_managers" are not a rename). Rejected.
- Diff git history — adds Git dependency to the seed path. Rejected (the post-state check is enough).

---

## §6 — Advisory lock for the seed path

**Decision**: `pg_advisory_xact_lock(987654321)` (a hard-coded `int8` constant) taken at the start of the seed transaction. The lock is automatically released on COMMIT or ROLLBACK.

**Rationale**:
- Postgres advisory locks are transactional, lightweight, and don't contend with table locks.
- A fixed constant means every seed run anywhere targets the same lock; concurrent seeds serialise without coordination.
- `987654321` is a deterministic, memorable constant; not derived from `hashtext('rubric.seed')` because that's tied to Postgres's hashing implementation (acceptable but less explicit). Document the constant in code.
- The lock is held for the entire seed transaction; the migration on `rubric_tree_version` (write-light, ~hundreds of rows max) doesn't block anything else for meaningful time.

**Alternatives considered**:
- Table-level `LOCK rubric_tree_version IN EXCLUSIVE MODE` — would block readers unnecessarily. Rejected.
- No lock, rely on UNIQUE constraint — two concurrent runs would each fail on UNIQUE violation; we'd get a confusing error. The advisory lock yields a cleaner "second run is a no-op" path. Rejected.
- Application-level mutex — doesn't cross processes. Rejected.

---

## §7 — Single source-of-truth canonical emitter

**Decision**: Both `convert` and `seed` import the same `_emit_canonical_yaml(payload: RubricArea) -> str` helper from `rubric_importer.py`. The helper is the only place that calls `yaml.safe_dump` with the canonical kwargs (research §2). The same `_compute_payload_hash(yaml_dir: Path) -> str` is shared.

**Rationale**:
- A duplicated emitter would let the two paths drift; a YAML produced by `convert` could fail to round-trip through `seed` because of subtle key-order differences. Single source of truth eliminates this whole class of bug at the design level.
- Same applies to the hash: convert never computes a hash (it just writes files), but the schema-validating helpers + canonical bytes are shared, so the contract holds.

**Alternatives considered**:
- Separate emitters with a contract test asserting equivalence — fragile (the test might miss edge cases). Rejected.

---

## §8 — Workbook quirks

**Decision**:
- **Merged cells**: any merged cell spanning a key column (`block`, `competency_id`, `topic`, `level`) is rejected with a clear error naming the cell range. Maintainers must "fill down" the merged values before saving.
- **Unicode normalisation**: every string cell is normalised to NFC (`unicodedata.normalize("NFC", s)`) before further processing. Avoids the "looks identical but byte-different" duplicate-id false positive.
- **Semicolon-separated `evidence_examples`**: split on `;`, trim each item, drop empty items. Semicolon was chosen because Excel autocompletes commas inside cells and we want a delimiter that survives Excel's autocomplete.
- **HTML entities**: passed through verbatim. The matrix-format contract says cells are plain text; if a maintainer types `&amp;` we treat it as the literal 5 characters. Documented.
- **Empty cells**: trailing empty cells in a row are tolerated; a row with empty `competency_id` is silently skipped (treated as a "section break" in the spreadsheet). A row with empty `level` is rejected (a level is required).

**Rationale**:
- These cover the realistic patterns we'll see in maintainer-edited Excel files. Each rule is documented in `docs/contracts/matrix-format.md` so a maintainer can produce a conforming workbook from the contract alone.

**Alternatives considered**:
- Accept merged cells and "fill down" automatically — surprising behaviour; rejected. Better to fail fast and force the maintainer to clean the workbook.
- Accept commas instead of semicolons — collides with English prose in `evidence_examples_en`. Rejected.

---

## §9 — Fixture workbook generation

**Decision**: Tests build the xlsx fixture **programmatically with `openpyxl.Workbook()` in `tmp_path`** during setup. No binary `.xlsx` is committed to the repo.

**Rationale**:
- Keeps the PR diff text-only and reviewable.
- Avoids the "what's actually in this binary blob" problem — the fixture is exactly what the test code says it is.
- Exercises the real xlsx codepath (real openpyxl read, real cell access) rather than a mock.
- The same helper that constructs the "happy path" workbook also constructs the deliberately-broken variants (duplicate id, merged cell across key column, etc.) for negative tests.

**Alternatives considered**:
- Commit a binary fixture — opaque in code review, easy to misedit. Rejected.
- Use a CSV instead of xlsx for tests — would not exercise the openpyxl codepath. Rejected.

---

## §10 — Prod-DB backward-compat for `payload_hash`

**Decision**: The 0003 migration adds `payload_hash TEXT NOT NULL DEFAULT ''`. At T08 time, `rubric_tree_version` is empty in prod (T05 just landed schema; no rubric seeded yet), so the DEFAULT covers a hypothetical edge case rather than a real one. The migration is still defensive — if any legacy rows existed, they'd get `payload_hash=''`, and a follow-up UPDATE could backfill the actual hash before the UNIQUE constraint became enforceable (currently the UNIQUE allows one row with `''`, which is acceptable for the migration's transitional moment).

**Rationale**:
- A migration that assumes "the table is empty" is brittle; even if true today, it could trip a local dev who's been experimenting.
- The DEFAULT + UNIQUE combination is safe: at most one legacy row can hold `''`, the importer's first real seed inserts a new row with a real 64-char hex hash that cannot collide with `''`.
- Documented in the migration docstring so a future contributor reading downgrade/upgrade understands the transitional pattern.

**Alternatives considered**:
- Migrate without DEFAULT and assert the table is empty — fragile in dev. Rejected.
- Skip the UNIQUE constraint — relies on the advisory lock alone for the race-free path. Rejected: UNIQUE is the structural anchor for the idempotency check (research §3) and protects future programmatic callers (T16) that might not bother taking the lock.

---

## Summary of resolved decisions

| # | Decision |
| - | -------- |
| 1 | `openpyxl >= 3.1` for xlsx (lean, pure-Python, read-only well-supported). |
| 2 | `yaml.safe_dump(sort_keys=True, default_flow_style=False, allow_unicode=True, indent=2, width=120, line_break="\n")` + explicit list pre-sorts. |
| 3 | SHA-256 over filename-sorted canonical YAML bytes joined by `0x00`; stored as 64-char hex. |
| 4 | Additive `payload_hash TEXT NOT NULL DEFAULT ''` + UNIQUE constraint in migration `0003`. |
| 5 | Post-state rename detection — any active id present in prior version but absent (and not retired) in new → reject. |
| 6 | `pg_advisory_xact_lock(987654321)` at the start of the seed transaction. |
| 7 | Single shared `_emit_canonical_yaml(...)` + `_compute_payload_hash(...)` between convert and seed. |
| 8 | Merged-cells-across-key-cols rejected; NFC normalisation; `;`-separated evidence; HTML entities passthrough; empty rows tolerated; empty `level` rejected. |
| 9 | Fixtures generated programmatically with `openpyxl.Workbook()` in `tmp_path`; never committed. |
| 10 | DEFAULT `''` + UNIQUE on `payload_hash` keeps migration safe across all transitional states. |
