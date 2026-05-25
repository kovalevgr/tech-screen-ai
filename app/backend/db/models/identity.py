"""Identity: the ``user`` staff-account table (data-model §Identity; §15).

Staff accounts only — recruiters, reviewers, admins — referenced by
``audit_log.actor_id``, ``assessment_correction.corrected_by``,
``turn_annotation.annotated_by``, and ``session_decision.decided_by``. This is
**not** candidate-PII storage: candidate identity lives in the Tier-5
``candidate`` table (§15), never here.

Minimal placeholder shape (research §10): ``subject`` (external SSO id) +
``role`` (free text now; the enum/CHECK is owned by T07). Display name, email
handling, and last-login are deferred to T07.
"""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class User(UUIDPk, TimestampCreated, Base):
    """A staff system account (recruiter / reviewer / admin)."""

    __tablename__ = "user"

    # External SSO subject id (Identity Platform, T07). Not candidate PII.
    subject: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # "recruiter" | "reviewer" | "admin" — free text at T05; enum/CHECK in T07.
    role: Mapped[str] = mapped_column(Text, nullable=False)
