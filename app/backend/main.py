"""TechScreen backend composition root.

Exposes the module-level ``app`` object that ``uvicorn`` boots
(``uvicorn app.backend.main:app``). At T02 the only route is a liveness
``GET /health``; everything else (candidate, session, admin, Planner) is
added by later tasks on top of this skeleton.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Final, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.backend.logging import configure_logging

_SERVICE_NAME: Final[Literal["techscreen-backend"]] = "techscreen-backend"


def _project_version() -> str:
    try:
        return version("techscreen")
    except PackageNotFoundError:
        return "0.0.0"


class HealthResponse(BaseModel):
    """Response body for ``GET /health`` — stable across revisions."""

    status: Literal["ok"]
    service: Literal["techscreen-backend"]
    version: str


configure_logging()

app = FastAPI(title="TechScreen Backend", version=_project_version())


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe.

    Unauthenticated and dependency-free. Cloud Run readiness probes hit
    this endpoint anonymously; dependency-aware readiness belongs to a
    future ``/ready`` added by the first task that introduces a
    dependency (T04 Vertex, T05 Postgres).
    """
    return HealthResponse(
        status="ok",
        service=_SERVICE_NAME,
        version=_project_version(),
    )
