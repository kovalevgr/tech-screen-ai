"""T23 — end-to-end scripted mock session (the Tier-3 gate).

An 8-candidate-turn interview driven through the REAL stack — dev-session
shell → state machine → agent wrappers → ``call_model`` → mock backend →
durable trace sink — with the transition sequence pinned as a fixture table.

The script is designed around the §6.1 assessment lag (``proceed_planned``):
the move answering candidate turn N is decided from coverage as of turn N-1,
because the Assessor never blocks the dialogue. The pinned table below is
therefore not just "what happened once" — every row was cross-checked against
the state-machine contract §5/§10 during authoring (spec 035, main loop).

Paths covered that the 033 happy-path does not: multi-seed iteration
(ANSWERED → seed 2), competency advance (ANSWERED → next competency),
level-0 short-circuit → NONE on the last competency, and late assessment
acceptance after the phase moved on (§6.8).

Acceptance (implementation plan T23): stable green — CI runs it on every
push; 5 consecutive local runs verified at authoring time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.orchestrator.config import load_orchestrator_config
from app.backend.services.dev_session import (
    DevSessionService,
    ImmediateTaskScheduler,
)
from app.backend.settings import Settings
from app.backend.tests.conftest import purge_session

pytestmark = pytest.mark.anyio

_FIXTURES: Path = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"

_T23_SESSION_ID = uuid.UUID("23232323-2323-5323-8323-232323232323")
"""Fixed: the Assessor echoes session/turn ids, so its prompt SHAs — and the
mock fixtures — depend on it. Turn ids are uuid5-derived, hence stable too."""

PLAN: dict[str, object] = {
    "plan_version": 1,
    "competencies": [
        {
            "node_id": "py.async",
            "label_uk": "Асинхронний Python",
            "target_level": 3,
            "minutes": 12,
            "seed_questions_uk": [
                "Що таке подієвий цикл asyncio і як він виконує корутини?",
                "Як обмежити час виконання корутини?",
            ],
            "probe_branches_uk": [
                "Що станеться з CPU-важкою задачею всередині циклу?",
                "Коли ви обрали б потоки замість asyncio?",
            ],
        },
        {
            "node_id": "db.transactions",
            "label_uk": "Транзакції в PostgreSQL",
            "target_level": 3,
            "minutes": 10,
            "seed_questions_uk": ["Що гарантує рівень ізоляції REPEATABLE READ?"],
            "probe_branches_uk": [
                "Наведіть приклад аномалії, яку REPEATABLE READ не виключає.",
                "Що таке фантомне читання?",
            ],
        },
    ],
    "qa_minutes": 0,
    "session_max_minutes": 60,
}

TURNS: tuple[str, ...] = (
    # 1 → INTRO consumed; first seed issued.
    "Так, усе зрозуміло — починаймо.",
    # 2 → weak answer to C1 seed 1 (assessed level 2 / 0.50).
    "Це механізм, який якось керує асинхронними задачами, точніше не поясню.",
    # 3 → strong probe answer (level 3 / 0.90).
    "CPU-важка задача заблокує цикл — він кооперативний, інші корутини не "
    "отримають контроль. Такі задачі виносять у ProcessPoolExecutor через "
    "run_in_executor.",
    # 4 → strong second-probe answer (level 3 / 0.85).
    "Через asyncio.wait_for: вона обгортає корутину і скасовує її після дедлайну з TimeoutError.",
    # 5 → strong answer to C1 seed 2 (level 3 / 0.90).
    "Ще є asyncio.timeout як контекстний менеджер, а в TaskGroup дедлайни "
    "зручно комбінувати зі скасуванням.",
    # 6 → confused answer to C2 seed (level 2 / 0.45).
    "Здається, це щось про те, щоб дані не губились під час запису... точно не скажу.",
    # 7 → substantive failure (level 0 / 0.80 — evidence-backed None).
    "Не знаю. Чув назву, але не розумію, що таке рівні ізоляції взагалі.",
    # 8 → substantive failure again (level 0 / 0.85) → NONE short-circuit.
    "На жаль, теж не знаю — з транзакціями майже не працював, приклад навести не можу.",
    # 9 → QA sign-off: with qa_minutes=0 the budget is already reached, so this
    # turn fires edge 16 (QA → CLOSE, scripted closing, no LLM call).
    "У мене немає запитань, дякую.",
)

# The transition fixture table (T23 acceptance): the exact ordered sequence of
# LLM calls the session must produce — (agent, issued_move). Assessor rows
# carry the move of the transition that scheduled them; their own content is
# scoring, not routing. Derived from contract §5/§10 with the §6.1 lag:
#   reply(N) is decided from coverage(N-1).
EXPECTED_CALLS: tuple[tuple[str, str | None], ...] = (
    ("interviewer", "ask_seed"),  # t1: INTRO → TECH, C1 seed 1
    ("interviewer", "depth_probe"),  # t2: C1 empty coverage → proceed_planned
    ("assessor", None),  # scores t2
    ("interviewer", "depth_probe"),  # t3: sees (2,.50) → CLARIFY, probe 2
    ("assessor", None),  # scores t3
    ("interviewer", "acknowledge_and_transition"),  # t4: sees (3,.90) → seed 2
    ("assessor", None),  # scores t4
    ("interviewer", "acknowledge_and_transition"),  # t5: still ANSWERED → C2
    ("assessor", None),  # scores t5
    ("interviewer", "depth_probe"),  # t6: C2 empty → proceed_planned
    ("assessor", None),  # scores t6
    ("interviewer", "depth_probe"),  # t7: sees (2,.45) → CLARIFY, probe 2
    ("assessor", None),  # scores t7
    ("interviewer", "acknowledge_and_transition"),  # t8: sees level 0 → NONE →
    ("assessor", None),  # QA transition; scores t8 (§6.8)
)


@dataclass
class _Harness:
    service: DevSessionService
    scheduler: ImmediateTaskScheduler
    engine: AsyncEngine

    async def turn(self, text_value: str) -> object:
        result = await self.service.post_turn(_T23_SESSION_ID, text_value)
        await self.scheduler.drain()
        return result


@pytest.fixture
async def t23(db_engine: AsyncEngine, clean_sessions: None) -> _Harness:
    await purge_session(db_engine, _T23_SESSION_ID)
    scheduler = ImmediateTaskScheduler()
    service = DevSessionService(
        engine=db_engine,
        settings=Settings(
            llm_backend="mock",
            app_env="test",
            llm_budget_per_session_usd=Decimal("5.00"),
            llm_fixtures_dir=_FIXTURES,
        ),
        config=load_orchestrator_config(),
        scheduler=scheduler,
    )
    return _Harness(service=service, scheduler=scheduler, engine=db_engine)


async def test_the_scripted_eight_turn_session_matches_the_fixture_table(
    t23: _Harness,
) -> None:
    view = await t23.service.create_session(PLAN, session_id=_T23_SESSION_ID)
    await t23.scheduler.drain()
    assert view.phase == "INTRO"

    for candidate_text in TURNS:
        assert view.phase not in ("COMPLETED", "ABORTED"), (
            f"session ended early at {view.phase!r} before turn {candidate_text[:30]!r}"
        )
        view = (await t23.turn(candidate_text)).session  # type: ignore[attr-defined]

    # --- terminal shape -----------------------------------------------------
    assert view.phase == "COMPLETED"
    assert view.abort_reason is None
    assert view.awaiting is None
    assert view.flagged_for_review is False

    # --- the pinned transition table (T23 acceptance) -----------------------
    traces = await t23.service.list_traces(_T23_SESSION_ID)
    calls = [
        (row.agent, row.transition["issued_move"])
        for row in traces.traces
        if row.transition is not None
    ]
    assert calls == list(EXPECTED_CALLS)

    # --- every turn is a complete, attributable audit artifact --------------
    assert all(row.outcome == "ok" for row in traces.traces)
    assert all(row.turn_id is not None for row in traces.traces)
    assert all(row.system_prompt and row.user_payload for row in traces.traces)
    assert all(row.response_text and row.parsed is not None for row in traces.traces)
    interviewer_rows = [r for r in traces.traces if r.agent == "interviewer"]
    assessor_rows = [r for r in traces.traces if r.agent == "assessor"]
    assert len(interviewer_rows) == 8  # one per candidate turn
    assert len(assessor_rows) == 7  # every TECH turn scored, intro not
    assert {r.prompt_version for r in assessor_rows} == {"v0003"}

    # --- coverage tells the designed story ----------------------------------
    coverage = view.coverage
    assert coverage["py.async"]["best_level"] == 3  # ANSWERED at target
    assert coverage["db.transactions"]["best_level"] == 2  # tried, weak
    assert coverage["db.transactions"]["latest_level"] == 0  # evidence-backed None
    assert coverage["db.transactions"]["gap_not_assessable"] is False

    # --- cost: single source of truth ---------------------------------------
    expected_cost = sum((Decimal(r.cost_usd) for r in traces.traces), Decimal("0"))
    assert Decimal(view.cost_usd_total) == expected_cost > 0

    # --- transcript bookends are the repo scripts, not LLM output -----------
    roles = [entry.role for entry in view.transcript]
    assert roles[0] == "system" and roles[-1] == "system"
    assert [e.text for e in view.transcript if e.role == "candidate"] == list(TURNS)


async def test_the_session_is_deterministic_across_reruns(t23: _Harness) -> None:
    """Two consecutive full runs produce identical call tables and costs —
    the property that makes the 5/5 CI stability acceptance credible."""

    async def run_once() -> tuple[list[tuple[str, str]], str]:
        await purge_session(t23.engine, _T23_SESSION_ID)
        view = await t23.service.create_session(PLAN, session_id=_T23_SESSION_ID)
        await t23.scheduler.drain()
        for candidate_text in TURNS:
            view = (await t23.turn(candidate_text)).session  # type: ignore[attr-defined]
        traces = await t23.service.list_traces(_T23_SESSION_ID)
        calls = [
            (r.agent, r.transition["issued_move"])
            for r in traces.traces
            if r.transition is not None
        ]
        return calls, view.cost_usd_total

    first = await run_once()
    second = await run_once()
    assert first == second
