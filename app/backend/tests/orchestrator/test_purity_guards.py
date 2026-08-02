"""Static purity guards for the orchestrator core (spec FR-032-10).

Constitution §2 / ADR-005 and contract §1 are claims about what the code
CANNOT do. Behavioural tests can only sample; these guards parse the module
and prove the absence of whole categories:

- no clock reads (``datetime.now`` / ``date.today`` / ``time.time`` …) — every
  timestamp arrives on an event;
- no randomness (``random``, ``secrets``, ``uuid4``) — ids are ``uuid5`` over
  a structural counter (§6.9);
- no I/O, no database, no LLM client anywhere in the core;
- **no branching on candidate free text** — the core never even reads
  ``CandidateTurnReceived.text``, and never branches on an ``utterance``;
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
    tree = _parse(module)
    random_calls = [
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id in {"uuid4", "uuid1", "random"}
    ]

    assert random_calls == [], f"{module.name} uses non-deterministic ids: {random_calls}"


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


def test_the_core_never_branches_on_an_utterance() -> None:
    """The utterance is passed through to the shell, never inspected."""
    tree = _parse(_CORE)
    offenders: list[str] = []
    for node in ast.walk(tree):
        condition: ast.expr | None = None
        if isinstance(node, ast.If | ast.While | ast.IfExp):
            condition = node.test
        elif isinstance(node, ast.Compare):
            condition = node
        if condition is None:
            continue
        for inner in ast.walk(condition):
            if isinstance(inner, ast.Attribute) and inner.attr in {"utterance", "rationale_en"}:
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
