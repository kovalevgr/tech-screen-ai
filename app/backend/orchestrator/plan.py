"""Interview plan shape consumed by the orchestrator (contract §7).

This module is the **input contract** the Planner (T24/T25) must satisfy;
until it ships, the same shape is produced by fixtures (T23) and
hand-written dev plans. The orchestrator validates a raw plan payload once,
at session start (contract §10 edges 1/2): a payload that does not parse is
a *configuration* error (:class:`PlanInvalid`), not a candidate-facing
failure.

Pure: models plus one classmethod validator. No I/O, no clock, no
randomness — the state machine's purity guarantee extends here because the
core imports this module.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

NonEmptyStr = Annotated[str, Field(min_length=1)]


class PlanInvalid(Exception):
    """A raw plan payload does not satisfy the contract §7 shape.

    Raised only by :meth:`PlanSnapshot.validate_plan`. The state machine
    converts it into ``ABORTED(operator_abort)`` +
    ``RecordDecision(plan_invalid)`` (edge 2) — the session cannot start.
    The ``__cause__`` chain carries the underlying
    :class:`pydantic.ValidationError`.
    """


class PlannedCompetency(BaseModel):
    """One competency in the plan's ordered sequence (contract §7).

    ``target_level`` is 1..5: level 0 ("не володіє", assessor scale v0003) is
    an *outcome*, never a target.
    """

    model_config = ConfigDict(frozen=True)

    node_id: NonEmptyStr
    """Rubric node id; must exist in the session ``rubric_snapshot``. The
    referential cross-check belongs to the session-start service (T22) —
    the machine validates shape only (spec Clarification 7)."""

    label_uk: NonEmptyStr
    target_level: int = Field(ge=1, le=5)
    minutes: int = Field(ge=1)
    seed_questions_uk: tuple[NonEmptyStr, ...] = Field(min_length=1)
    probe_branches_uk: tuple[NonEmptyStr, ...] = ()
    """May be empty — probes then fall back to a generic ``depth_probe``
    context (contract §7)."""

    def seed_question(self, index: int) -> str | None:
        """Return seed question ``index``, or ``None`` when it does not exist.

        Args:
            index: Zero-based position in ``seed_questions_uk``.

        Returns:
            The seed question, or ``None`` past the end (negative indices
            are treated as absent — the machine never walks backwards).
        """
        if index < 0 or index >= len(self.seed_questions_uk):
            return None
        return self.seed_questions_uk[index]

    def probe_branch(self, index: int) -> str | None:
        """Return probe branch ``index``, or ``None`` for the generic fallback.

        Args:
            index: Zero-based position in ``probe_branches_uk``.

        Returns:
            The branch text, or ``None`` when the plan has no branch at that
            position (contract §7: probes then use a generic context).
        """
        if index < 0 or index >= len(self.probe_branches_uk):
            return None
        return self.probe_branches_uk[index]


class PlanSnapshot(BaseModel):
    """The frozen interview plan the machine routes over (contract §7).

    Extra keys are tolerated (pydantic's default ``ignore``) so a richer
    future Planner payload does not break a running orchestrator; every
    field the machine reads is required and bounded here.
    """

    model_config = ConfigDict(frozen=True)

    plan_version: int = Field(ge=1)
    competencies: tuple[PlannedCompetency, ...] = Field(min_length=1)
    """At least one competency — a plan with nothing to assess is a
    configuration error, not an interview (implementation note, spec
    Clarification 11)."""

    qa_minutes: int = Field(ge=0)
    session_max_minutes: int = Field(ge=1)

    @classmethod
    def validate_plan(cls, raw: object) -> PlanSnapshot:
        """Validate a raw plan payload into the typed snapshot.

        Args:
            raw: The plan as handed to the machine (normally the JSON object
                frozen onto the session at creation time).

        Returns:
            The validated :class:`PlanSnapshot`.

        Raises:
            PlanInvalid: The payload is not a mapping, or fails the §7 shape.
        """
        if not isinstance(raw, dict):
            raise PlanInvalid(f"plan must be a JSON object, got {type(raw).__name__}")
        try:
            return cls.model_validate(raw)
        except ValidationError as exc:
            raise PlanInvalid(f"plan does not satisfy contract §7: {exc}") from exc

    def competency(self, index: int) -> PlannedCompetency | None:
        """Return competency ``index``, or ``None`` when the sequence is done.

        Args:
            index: Zero-based position in ``competencies``.

        Returns:
            The competency, or ``None`` past the last one (the machine reads
            that as "no competencies remain" → QA).
        """
        if index < 0 or index >= len(self.competencies):
            return None
        return self.competencies[index]


def plan_payload(plan: PlanSnapshot) -> dict[str, Any]:
    """Serialise a plan back to its JSON-object form.

    Convenience for fixtures and the shell (T22/T23), which hold plans as
    JSON before the machine validates them.

    Args:
        plan: The validated plan.

    Returns:
        A JSON-mode dict equal to the payload ``validate_plan`` accepts.
    """
    return plan.model_dump(mode="json")
