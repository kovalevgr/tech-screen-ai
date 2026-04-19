---
name: rubric-yaml
description: Validate, diff, and snapshot the rubric tree. Rubric content lives in configs/rubric/*.yaml and is the source of truth; a new rubric_tree_version is created on every content change — existing nodes are never edited in place. Use whenever anything under configs/rubric/** changes.
---

# rubric-yaml

You are changing rubric content. The rubric tree is immutable in the most-important sense: once a session has started, its `rubric_snapshot` must remain interpretable years from now. That means node ids are stable, level descriptors are concrete, and edits produce a new `rubric_tree_version` — they do not rewrite the old one.

## When to use this skill

- Adding a new competency (e.g., `python.async`, `system-design.observability`).
- Revising level descriptors based on reviewer calibration feedback.
- Retiring a competency (mark retired; never delete the node row).
- Fixing a level descriptor that reads ambiguously.
- Splitting a node into two (one of the least-clean operations; requires an ADR).

## When NOT to use

- Editing the Assessor prompt — that is `agent-prompt-edit`.
- Editing the rubric-rendering UI — that is frontend work; the UI is read-only for rubric content.
- Changing the correctness variant (A vs B). That is ADR-020 territory; start with an ADR amendment.

## Source of truth

`configs/rubric/` holds one YAML per top-level area:

```
configs/rubric/
├── python.yaml
├── system-design.yaml
├── databases.yaml
├── distributed-systems.yaml
├── ...
```

The Admin UI is **read-only** for rubric content (constitution §16, ADR-021). Promote any UI-originated suggestion through a PR to these files.

## Rubric shape

```yaml
# configs/rubric/python.yaml
version: 7                         # bumped whenever this file changes
retired: false                     # retire whole areas by flipping this
nodes:
  - id: python.concurrency         # STABLE identifier; never rename, never reuse after retire
    label_uk: "Конкурентність у Python"
    label_en: "Python concurrency"
    retired: false
    parent: null                   # top-level node in this area
    levels:
      - level: 1
        label_uk: "Початковий"
        descriptor_en: >
          Knows threads and processes exist; can describe the GIL in one sentence.
          Cannot reliably choose between threading, multiprocessing, and asyncio.
        evidence_examples_en:
          - "Mentions 'threading' without describing when it helps."
          - "Unable to state what the GIL protects."
      - level: 2
        label_uk: "Практичний"
        descriptor_en: >
          Picks asyncio for I/O-bound work and multiprocessing for CPU-bound work.
          Can explain why the GIL matters for CPU-bound threads.
        evidence_examples_en:
          - "Correctly picks asyncio for a web-scraper task."
          - "Names GIL as the reason threads don't help CPU-bound workloads."
      - level: 3
        label_uk: "Впевнений"
        descriptor_en: >
          ...
      - level: 4
        label_uk: "Експертний"
        descriptor_en: >
          ...
```

Rules the validator enforces:

- `id` is snake/dot case, unique across all YAMLs, and **never reused after retirement**.
- Four levels required (1–4). Exactly four.
- `descriptor_en` is 1–3 concrete sentences. No vague "junior / senior / expert" labels.
- `evidence_examples_en` has at least one item per level. Concrete. Speech-act or observable behaviour.
- `label_uk` required; `descriptor_uk` optional (Assessor reads English).
- `parent` is `null` for top-level or a valid `id` of a sibling in the same file.
- No circular references.

## The flow

### 1. Read the active version

```bash
# What version is active?
cat configs/models.yaml | grep rubric_tree_version
# e.g., rubric_tree_version: 7
```

Every area YAML has its own `version` field. The composite `rubric_tree_version` is bumped when any area file changes.

### 2. Decide the change shape

- **Add a node.** Append to `nodes:`. Set `retired: false`. Give it a fresh, stable `id`. Write all four levels.
- **Revise a descriptor.** Edit the `descriptor_en` / `evidence_examples_en` in place. The `id` stays. A new tree version is still produced because content changed.
- **Retire a node.** Set `retired: true`. Leave everything else. The node stays in the file forever — it is referenced by old session snapshots.
- **Split a node.** Retire the old node (`retired: true`), add two new nodes with new ids. Document the split in `notes.md` at the commit. Requires an ADR if the split changes the rubric philosophy.
- **Never rename an id.** A rename silently breaks every session that references the old id by `rubric_node_id` in `assessment` rows.

### 3. Validate

Run the validator (implemented under `scripts/rubric_validate.py`, invoked by the skill):

```bash
uv run python -m scripts.rubric_validate configs/rubric/
```

The validator checks:

- Schema shape (required keys, types, enums).
- Id uniqueness across all area files.
- No renamed ids between the working tree and the last tagged rubric snapshot.
- No deleted nodes (retirement only).
- All four levels present per node.
- Descriptors non-empty and below 600 characters.
- No placeholder text like `"TODO"`, `"FIXME"`, `"..."`.
- Languages: `label_uk` is Ukrainian (no русизми — checked against the shared anchor list), `descriptor_en` is English.

Non-zero exit = stop. Fix the findings before proceeding.

### 4. Diff vs active

```bash
uv run python -m scripts.rubric_diff --from v7 --to working
```

Output is a human-readable change list:

```
+ added node: python.async (levels: 4)
~ revised descriptor: system-design.consistency L3
  was: "Understands eventual consistency trade-offs..."
  now: "Picks eventual vs strong consistency per workload and explains the SLO impact..."
- retired node: python.generators-and-iterators
```

Paste this into the PR body.

### 5. Generate the new snapshot

The snapshot is the frozen form that sessions reference. The `rubric-yaml` skill produces it:

```bash
uv run python -m scripts.rubric_snapshot --bump
```

This:

- Bumps `rubric_tree_version` in `configs/models.yaml` to `N+1`.
- Writes `configs/rubric/snapshots/v<N+1>.json` — flat, fully-resolved, deterministic ordering, stable sort keys.
- The snapshot is what services read at session creation time; `interview_session.rubric_snapshot` is populated from this file, not from the YAML.

Commit the snapshot in the same PR as the YAML change. The reviewer blocks a YAML change without a matching snapshot bump.

### 6. Notes

Write `configs/rubric/notes/<new-version>.md`:

```markdown
# rubric v<N+1> — notes

## Change list
- added python.async (4 levels).
- revised system-design.consistency L3 descriptor.
- retired python.generators-and-iterators (subsumed into python.async).

## Why
- Calibration showed L3 descriptor was ambiguous — reviewers disagreed on 40 % of L3 calls.
- python.async request came from the senior-role interviewer template.

## Impact on in-flight sessions
- None. Existing sessions keep `rubric_snapshot: v<N>`.
- New sessions created after this merge use v<N+1>.
```

### 7. Commit

- Branch: `feat/rubric-<slug>`.
- Subject: `bump rubric to v<N+1>: <slug>` — imperative, lowercase.
- Body: the change list from the diff step, the "Impact on in-flight sessions" line, and any calibration-related motivation.

## Invariants the reviewer checks

- No id renamed between the old snapshot and the new one (hard block).
- No node row deleted — only `retired: true` (hard block).
- Every YAML change is accompanied by a snapshot bump (hard block).
- `rubric_tree_version` in `configs/models.yaml` matches the latest `snapshots/v<N>.json` filename.
- No placeholder strings in descriptors.

Constitution §4 (rubric edits never touch existing sessions), §16 (configs as code). ADR-018 (rubric snapshots), ADR-021 (configs as code).

## Tests

- `scripts/rubric_validate.py` is covered by unit tests in `scripts/tests/test_rubric_validate.py`.
- The validator runs in CI on every PR that touches `configs/rubric/**`.
- Integration test in `app/backend/tests/integration/test_rubric_snapshot.py` asserts that reading a v7 snapshot on a restored test DB yields the same tree shape the session originally saw.

## Common mistakes the reviewer will block

- Renaming `python.concurrency` to `python.concurrency-and-async` to be "more descriptive". Retire and add; do not rename.
- Deleting the `python.generators` block "because we retired it". Retire it; keep the block forever.
- Bumping YAML but forgetting to regenerate the snapshot. CI catches it via the matching-version check.
- Editing a level descriptor directly on `main` without a PR "because it's just a wording fix". Still a PR; still a tree-version bump. Session integrity depends on this.
- Adding a 5th level. The rubric is 4 levels by design; a 5-level rubric is a constitution change.

## References

- Constitution §4, §16.
- ADR-018 (rubric snapshots), ADR-021 (configs as code).
- `docs/data-model.docx` — rubric tables.
- `docs/prompt-engineering-playbook.md` — rubric + assessor interplay.
