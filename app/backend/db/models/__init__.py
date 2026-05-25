"""ORM models for the T05 schema.

Importing this package registers every table on ``Base.metadata`` (the
side-effect ``alembic/env.py`` relies on for ``target_metadata``). Modules are
grouped by domain: ``rubric`` (read-only tree), ``identity`` (staff users),
``interview`` (session placeholders), and ``audit`` (the six §3 append-only
tables).
"""

from __future__ import annotations

from app.backend.db.models.audit import (
    Assessment,
    AssessmentCorrection,
    AuditLog,
    SessionDecision,
    TurnAnnotation,
    TurnTrace,
)
from app.backend.db.models.identity import User
from app.backend.db.models.interview import (
    InterviewPlan,
    InterviewSession,
    PositionTemplate,
)
from app.backend.db.models.rubric import (
    Competency,
    CompetencyBlock,
    Level,
    RubricTreeVersion,
    Stack,
    Topic,
)

__all__ = [
    # rubric tree
    "RubricTreeVersion",
    "Stack",
    "CompetencyBlock",
    "Competency",
    "Topic",
    "Level",
    # identity
    "User",
    # session placeholders
    "PositionTemplate",
    "InterviewSession",
    "InterviewPlan",
    # append-only audit set
    "TurnTrace",
    "Assessment",
    "AssessmentCorrection",
    "TurnAnnotation",
    "AuditLog",
    "SessionDecision",
]
