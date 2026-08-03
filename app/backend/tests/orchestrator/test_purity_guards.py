"""Static purity guards for the orchestrator core (spec FR-032-10).

Constitution §2 / ADR-005 and contract §1 are claims about what the code
CANNOT do. Behavioural tests can only sample; these guards parse the module
and prove the absence of whole categories:

- no clock reads (``datetime.now`` / ``date.today`` / ``time.time`` …) — every
  timestamp arrives on an event;
- no randomness (``random``, ``secrets``, ``uuid4``) in either bare-name or
  attribute form — ids are ``uuid5`` over a structural counter (§6.9);
- no ``import uuid``: the core takes ``from uuid import UUID, uuid5``, so
  ``uuid.uuid4`` is not one attribute access away from any line;
- no I/O, no database, no LLM client anywhere in the core;
- **no branching on candidate free text or generated prose** — the core never
  even reads ``CandidateTurnReceived.text``, and no ``if`` / ``while`` /
  ``match`` subject touches an ``utterance``, ``rationale_en``,
  ``description_en`` or ``manual_review_reason_en``;
- no ``.should_*``-style LLM-output flow control.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_CORE_DIR: Path = Path(__file__).resolve().parents[3] / "backend" / "orchestrator"
_CORE: Path = _CORE_DIR / "state_machine.py"
_PURE_MODULES: tuple[Path, ...] = (_CORE, _CORE_DIR / "plan.py")

_CLOCK_ATTRS: frozenset[str] = frozenset({"now", "utcnow", "today", "fromtimestamp"})
_CLOCK_OWNERS: frozenset[str] = frozenset({"datetime", "date", "time"})
_BANNED_IMPORTS: frozenset[str] = frozenset(
    {
        "random",
        "secrets",
        "time",
        "os",
        "asyncio",
        "yaml",
        "sqlalchemy",
        "httpx",
        "requests",
        "app.backend.db",
        "app.backend.llm",
        "app.backend.settings",
    }
)
_BANNED_MODULE_IMPORTS: frozenset[str] = frozenset({"uuid"})
"""Modules the core may import SYMBOLS from but never as a module.

``from uuid import UUID, uuid5`` is the sanctioned form. ``import uuid`` would
put ``uuid.uuid4()`` one attribute access away from every line and defeat a
name-based scan, so the module form is banned outright (§6.9)."""

_RANDOM_CALLABLES: frozenset[str] = frozenset(
    {"uuid4", "uuid1", "uuid3", "getrandbits", "token_hex", "token_bytes", "token_urlsafe"}
)
"""Non-deterministic callables, banned as bare names AND as attributes."""

_RANDOM_OWNERS: frozenset[str] = frozenset({"random", "secrets"})
"""Modules whose every member is non-deterministic — any attribute is a hit."""

_PROSE_ATTRS: frozenset[str] = frozenset(
    {"utterance", "rationale_en", "description_en", "manual_review_reason_en"}
)
"""Free-text fields on agent outputs. Passing them through is fine; deciding
anything on them would be LLM-driven flow control (constitution §2)."""


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


@pytest.mark.parametrize("module", _PURE_MODULES, ids=lambda path: path.name)
def test_the_core_never_reads_a_clock(module: Path) -> None:
    offenders = [
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(_parse(module))
        if isinstance(node, ast.Attribute)
        and node.attr in _CLOCK_ATTRS
        and isinstance(node.value, ast.Name)
        and node.value.id in _CLOCK_OWNERS
    ]

    assert offenders == [], f"{module.name} reads a clock: {offenders}"


@pytest.mark.parametrize("module", _PURE_MODULES, ids=lambda path: path.name)
def test_the_core_never_draws_randomness(module: Path) -> None:
    """Bare names AND attribute form — ``uuid.uuid4()`` must not slip past."""
    offenders: list[str] = []
    for node in ast.walk(_parse(module)):
        if isinstance(node, ast.Name) and node.id in _RANDOM_CALLABLES | _RANDOM_OWNERS:
            offenders.append(node.id)
        elif isinstance(node, ast.Attribute):
            owner_is_random = isinstance(node.value, ast.Name) and node.value.id in _RANDOM_OWNERS
            if node.attr in _RANDOM_CALLABLES or owner_is_random:
                offenders.append(ast.unparse(node))

    assert offenders == [], f"{module.name} uses non-deterministic ids: {offenders}"


@pytest.mark.parametrize("module", _PURE_MODULES, ids=lambda path: path.name)
def test_the_core_imports_uuid_symbols_never_the_module(module: Path) -> None:
    """``import uuid`` would put ``uuid.uuid4`` one attribute access away."""
    offenders = [
        alias.name
        for node in ast.walk(_parse(module))
        if isinstance(node, ast.Import)
        for alias in node.names
        if any(
            alias.name == banned or alias.name.startswith(f"{banned}.")
            for banned in _BANNED_MODULE_IMPORTS
        )
    ]

    assert offenders == [], (
        f"{module.name} imports a module it may only take symbols from: {offenders}"
    )


@pytest.mark.parametrize("module", _PURE_MODULES, ids=lambda path: path.name)
def test_the_core_imports_nothing_that_performs_io(module: Path) -> None:
    offenders = [
        name
        for name in _imported_modules(_parse(module))
        if any(name == banned or name.startswith(f"{banned}.") for banned in _BANNED_IMPORTS)
    ]

    assert offenders == [], f"{module.name} imports an I/O-capable module: {offenders}"


def test_the_core_never_reads_candidate_text() -> None:
    """Constitution §2: no control flow may depend on candidate free text."""
    offenders = [
        ast.unparse(node)
        for node in ast.walk(_parse(_CORE))
        if isinstance(node, ast.Attribute) and node.attr == "text"
    ]

    assert offenders == [], f"the core reads candidate text: {offenders}"


def test_the_core_never_branches_on_generated_prose() -> None:
    """Prose is passed through to the shell, never inspected.

    Covers every construct that can steer control flow on a value: ``if`` /
    ``while`` / conditional expressions, bare comparisons, and ``match`` —
    both the subject and each case's guard.
    """
    offenders: list[str] = []
    for node in ast.walk(_parse(_CORE)):
        conditions: list[ast.expr] = []
        if isinstance(node, ast.If | ast.While | ast.IfExp):
            conditions = [node.test]
        elif isinstance(node, ast.Compare):
            conditions = [node]
        elif isinstance(node, ast.Match):
            conditions = [node.subject]
        elif isinstance(node, ast.match_case) and node.guard is not None:
            conditions = [node.guard]
        for condition in conditions:
            for inner in ast.walk(condition):
                if isinstance(inner, ast.Attribute) and inner.attr in _PROSE_ATTRS:
                    offenders.append(ast.unparse(node))

    assert offenders == [], f"the core branches on generated prose: {offenders}"


def test_the_core_has_no_should_style_llm_flow_control() -> None:
    """No ``.should_advance`` / ``should_probe`` field may drive routing."""
    offenders = [
        node.attr
        for node in ast.walk(_parse(_CORE))
        if isinstance(node, ast.Attribute) and node.attr.startswith("should_")
    ]

    assert offenders == [], f"the core consults a `.should_*` field: {offenders}"


def test_the_core_defines_no_async_entry_points() -> None:
    """A pure core has nothing to await: async here would mean hidden I/O."""
    offenders = [
        node.name for node in ast.walk(_parse(_CORE)) if isinstance(node, ast.AsyncFunctionDef)
    ]

    assert offenders == [], f"the core defines async functions: {offenders}"


def test_no_provider_sdk_appears_anywhere_in_the_orchestrator() -> None:
    """Belt and braces alongside ``scripts/check-no-provider-sdk-imports.sh``."""
    forbidden = ("vertexai", "google.genai", "google.cloud.aiplatform", "anthropic", "openai")
    offenders = [
        f"{path.name}:{name}"
        for path in sorted(_CORE_DIR.glob("*.py"))
        for name in _imported_modules(_parse(path))
        if any(name == sdk or name.startswith(f"{sdk}.") for sdk in forbidden)
    ]

    assert offenders == [], f"provider SDK imported in the orchestrator: {offenders}"
