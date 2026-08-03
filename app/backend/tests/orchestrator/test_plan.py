"""``PlanSnapshot`` — the contract §7 input shape the Planner (T24/T25) must meet.

The machine validates shape, not referential integrity against the session's
``rubric_snapshot`` (spec Clarification 7 — that cross-check is T22's).
"""

from __future__ import annotations

from typing import Any

import pytest

from app.backend.orchestrator.plan import PlanInvalid, PlanSnapshot, plan_payload

from ._builders import NODE_A, NODE_B, competency, make_plan


def test_a_contract_shaped_plan_validates() -> None:
    plan = PlanSnapshot.validate_plan(make_plan())

    assert plan.plan_version == 1
    assert [entry.node_id for entry in plan.competencies] == [NODE_A, NODE_B]
    assert plan.competencies[0].target_level == 3
    assert plan.qa_minutes == 5
    assert plan.session_max_minutes == 60


def test_probe_branches_may_be_empty() -> None:
    plan = PlanSnapshot.validate_plan(make_plan(competencies=[competency(NODE_A, probes=())]))

    assert plan.competencies[0].probe_branches_uk == ()
    assert plan.competencies[0].probe_branch(0) is None


def test_extra_planner_keys_are_tolerated() -> None:
    """Forward compatibility: a richer Planner payload must not break a session."""
    payload = make_plan()
    payload["rationale_en"] = "future planner field"

    plan = PlanSnapshot.validate_plan(payload)

    assert plan.plan_version == 1


def test_seed_and_competency_lookups_are_bounded() -> None:
    plan = PlanSnapshot.validate_plan(make_plan())

    assert plan.competency(0) is not None
    assert plan.competency(2) is None
    assert plan.competency(-1) is None
    assert plan.competencies[0].seed_question(0) == "seed-1"
    assert plan.competencies[0].seed_question(1) is None


def test_a_plan_round_trips_through_its_payload() -> None:
    plan = PlanSnapshot.validate_plan(make_plan())

    assert PlanSnapshot.validate_plan(plan_payload(plan)) == plan


@pytest.mark.parametrize(
    ("description", "payload"),
    [
        ("not an object", ["competencies"]),
        ("no competencies", make_plan(competencies=[])),
        (
            "target level 0 is an outcome, never a target",
            make_plan(competencies=[competency(NODE_A, target_level=0)]),
        ),
        (
            "target level above the 0-5 scale",
            make_plan(competencies=[competency(NODE_A, target_level=6)]),
        ),
        ("no seed questions", make_plan(competencies=[competency(NODE_A, seeds=())])),
        ("empty node id", make_plan(competencies=[competency("")])),
        ("zero-minute competency", make_plan(competencies=[competency(NODE_A, minutes=0)])),
        ("zero-minute session", make_plan(session_max_minutes=0)),
        ("negative qa budget", make_plan(qa_minutes=-1)),
    ],
)
def test_a_malformed_plan_raises_plan_invalid(description: str, payload: Any) -> None:
    with pytest.raises(PlanInvalid):
        PlanSnapshot.validate_plan(payload)
