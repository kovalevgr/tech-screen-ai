"""Agent wrappers — thin, typed adapters between the orchestrator and ``call_model``.

Import wrappers directly from their modules (e.g. ``from
app.backend.agents.interviewer import ...``); this package deliberately
re-exports nothing so parallel agent tasks (T18/T19) never touch the same line.
"""
