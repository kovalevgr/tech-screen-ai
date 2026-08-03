"""Deterministic interview orchestrator (T20, constitution §2 / ADR-005).

The package is split into a **functional core** and the models the
imperative shell (T22/T23) needs to drive it — see
``docs/contracts/state-machine.md`` (v1.1), which is normative for every
phase, edge, policy and threshold implemented here:

- :mod:`app.backend.orchestrator.state_machine` — the pure core.
  ``transition(state, event, config) -> TransitionResult`` performs no I/O,
  reads no clock, draws no randomness; every timestamp arrives ON an event.
- :mod:`app.backend.orchestrator.plan` — ``PlanSnapshot``, the plan-shape
  input contract (contract §7) the Planner (T24/T25) must satisfy.
- :mod:`app.backend.orchestrator.config` — the frozen, load-time-validated
  loader for ``configs/orchestrator.yaml`` (contract §8, constitution §16).
- :mod:`app.backend.orchestrator.persistence` — the only module here that
  touches the database: encode/decode plus load/save of
  ``interview_session.session_state`` (contract §9).

Deliberately no re-exports: importers name the module they depend on, so
the "pure core" boundary stays visible in every import line (a
``from app.backend.orchestrator.persistence import ...`` inside the core
would be obvious at review).
"""
