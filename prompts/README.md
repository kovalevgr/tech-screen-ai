# Prompts

All agent system prompts live here. Prompts are versioned per agent; a bad `v0003` is replaced by `v0004`, never edited in place (see [`docs/engineering/prompt-engineering-playbook.md`](../docs/engineering/prompt-engineering-playbook.md) and constitution §11).

---

## Layout

```
prompts/
├── interviewer/
│   ├── v0001/
│   │   ├── system.md         Main system prompt.
│   │   ├── level-guide.md    Per-level tone and depth.
│   │   └── notes.md          Author's notes: what changed, why, calibration delta.
│   └── active.txt            "v0001" — convenience pointer for tooling.
├── assessor/
│   ├── v0001/
│   │   ├── system.md
│   │   ├── level-guide.md
│   │   ├── schema.json       JSON schema of the agent's output.
│   │   └── notes.md
│   └── active.txt
├── planner/
│   ├── v0001/
│   │   ├── system.md
│   │   ├── schema.json
│   │   └── notes.md
│   └── active.txt
└── shared/
    ├── ukrainian-anchors.md  Register samples + dictionary + bad examples.
    ├── json-schemas/         Schemas used across agents (e.g., turn object).
    └── candidate-facing/     Fixed Ukrainian strings shown to the candidate.
        ├── opening.md
        ├── pause.md
        └── closing.md
```

## Active version per environment

`active.txt` is a convenience pointer for the `agent-prompt-edit` skill. The canonical active version at runtime is pinned in `configs/models.yaml`:

```yaml
dev:
  interviewer: v0001
  assessor: v0001
  planner: v0001
prod:
  interviewer: v0001
  assessor: v0001
  planner: v0001
```

Promoting a new prompt version = PR that bumps `configs/models.yaml`.

## Editing flow

Use the `agent-prompt-edit` skill. It:

1. Creates `prompts/<agent>/v<next>/` by copying the current active version.
2. Opens the new version for editing.
3. Prompts the author to fill `notes.md` (what changed, why, hypothesised effect).
4. Runs the `calibration-run` skill and attaches the delta to the PR.

See `docs/engineering/prompt-engineering-playbook.md` for the pre-merge checklist.
