"""TechScreen backend composition root.

Exposes the module-level ``app`` object that ``uvicorn`` boots
(``uvicorn app.backend.main:app``). The FastAPI ``lifespan`` handler runs
the production-mode startup guards (Settings) and, when a database is
configured, brings up the :class:`FeatureFlagService` (§9 dark-launch
substrate, T05a).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.backend.logging import configure_logging
from app.backend.services.feature_flags import FeatureFlagService, set_service
from app.backend.settings import Settings

_SERVICE_NAME: Final[Literal["techscreen-backend"]] = "techscreen-backend"
_FEATURE_FLAGS_YAML: Final[Path] = (
    Path(__file__).resolve().parents[2] / "configs" / "feature-flags.yaml"
)


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


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup + shutdown.

    Validates env (Settings) on every boot; if a ``DATABASE_URL`` is
    configured, also loads ``configs/feature-flags.yaml``, validates it
    against the committed JSON Schema, and starts the LISTEN/NOTIFY
    listener that keeps the in-process cache fresh (T05a — FR-003/SC-003).
    """
    settings = Settings()
    settings.assert_safe_for_environment()

    flag_service: FeatureFlagService | None = None
    if settings.database_url:
        flag_service = FeatureFlagService.from_yaml(
            _FEATURE_FLAGS_YAML,
            settings.database_url,
        )
        await flag_service.start()
        set_service(flag_service)
    try:
        yield
    finally:
        if flag_service is not None:
            await flag_service.stop()
            set_service(None)


app = FastAPI(title="TechScreen Backend", version=_project_version(), lifespan=lifespan)


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
