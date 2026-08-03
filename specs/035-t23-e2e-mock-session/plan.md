# Plan — T23 e2e mock session

**Branch** `035-t23-e2e-mock-session` · **Spec** [spec.md](./spec.md)

- **agent:** none — main orchestrator (implementation plan: `agent: orchestrator`; policy rev. 2)
- **parallel:** false (Tier-3 gate)
- **depends_on:** [T18, T19, T20, T21] (all merged)
- **contract:** none (consumes existing contracts; pins behavior, adds none)

## Phases

1. Script + expected-table design against state-machine contract §5/§10 with the §6.1 lag (main loop, inline).
2. Test module + deterministic session/turn ids.
3. Mechanical fixture recording loop (generator over `_unrecorded/` envelopes).
4. 5× stability + full gates both DB modes.

## Gate plan

pytest both modes, ruff ×2, mypy --strict, sdk-import guard; throwaway Postgres for DB mode (container removed after).
