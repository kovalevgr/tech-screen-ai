"""Feature-flag query surface (T05a, §9 dark-launch).

Public contract (consumed by every Tier-3+ risky feature):

    async def is_enabled(name: str, *, session_id: UUID | None = None) -> bool

Strict YAML-driven registry — a name not declared in
``configs/feature-flags.yaml`` raises :class:`UnknownFeatureFlag` (FR-004,
never silently false). Per-flag in-process cache with a 60-second TTL
backstop; a dedicated ``asyncpg`` LISTEN connection on the
``feature_flag_changed`` channel invalidates one cache entry per NOTIFY
(FR-003 / SC-003 — sub-second propagation across all instances without a
deploy). The listener reconnects with exponential backoff (1 s → 30 s cap)
on connection loss; while disconnected the cache silently degrades to the
TTL backstop (correctness preserved, freshness reduced).

The ``feature_flag`` table is **mutable by design** — see the explicit §3
carve-out documented in :mod:`app.backend.db.models.feature_flag` and in
``alembic/versions/0002_feature_flags.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import asyncpg
import yaml
from jsonschema import Draft202012Validator

_log = logging.getLogger(__name__)

# Repo-relative default paths. Tests inject their own paths via
# ``FeatureFlagService.from_yaml(path, dsn)``.
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
_DEFAULT_YAML_PATH: Path = _REPO_ROOT / "configs" / "feature-flags.yaml"
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "contracts" / "feature-flag.schema.json"

_CACHE_TTL_SECONDS: float = 60.0
_RECONNECT_BACKOFF_INITIAL_S: float = 1.0
_RECONNECT_BACKOFF_CAP_S: float = 30.0
_NOTIFY_CHANNEL: str = "feature_flag_changed"


class UnknownFeatureFlag(KeyError):
    """Raised when :func:`is_enabled` is called with a name not declared in YAML (FR-004)."""


@dataclass(frozen=True, slots=True)
class _FlagDecl:
    """One parsed entry from ``configs/feature-flags.yaml``."""

    name: str
    owner: str
    default: bool
    state: str  # "active" | "sunset"


# ---------------------------------------------------------------------------
# YAML + schema helpers
# ---------------------------------------------------------------------------


def _load_schema(schema_path: Path = _SCHEMA_PATH) -> dict[str, Any]:
    # json.loads is typed as Any; narrow explicitly for mypy --strict.
    return cast("dict[str, Any]", json.loads(schema_path.read_text(encoding="utf-8")))


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    # yaml.safe_load is typed as Any; narrow explicitly for mypy --strict.
    return cast("dict[str, Any]", loaded)


def _build_registry(yaml_doc: Mapping[str, Any]) -> dict[str, _FlagDecl]:
    flags = yaml_doc.get("flags") or []
    return {
        entry["name"]: _FlagDecl(
            name=entry["name"],
            owner=entry["owner"],
            default=bool(entry["default"]),
            state=entry["state"],
        )
        for entry in flags
    }


def _asyncpg_dsn(sqlalchemy_dsn: str) -> str:
    """Strip the SQLAlchemy ``+asyncpg`` tag from the DSN.

    ``asyncpg.connect()`` only accepts the bare ``postgresql://...`` shape.
    """
    return sqlalchemy_dsn.replace("+asyncpg", "")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FeatureFlagService:
    """In-process feature-flag query surface.

    Construct via :meth:`from_yaml` (load + validate the source-of-truth YAML)
    or directly with a pre-built registry (tests).
    """

    def __init__(self, registry: Mapping[str, _FlagDecl], dsn: str) -> None:
        self._registry: dict[str, _FlagDecl] = dict(registry)
        self._dsn: str = _asyncpg_dsn(dsn)
        self._cache: dict[str, tuple[bool, float]] = {}
        self._cache_lock: asyncio.Lock = asyncio.Lock()
        self._listen_conn: asyncpg.Connection | None = None
        self._listen_task: asyncio.Task[None] | None = None
        self._stopped: bool = False

    @classmethod
    def from_yaml(cls, yaml_path: Path, dsn: str) -> FeatureFlagService:
        """Validate ``yaml_path`` against the committed schema, then build the service.

        Schema-violation raises :class:`jsonschema.ValidationError` immediately;
        :func:`main` surfaces that as a startup error so a malformed
        source-of-truth never serves traffic (FR-005, FR-006).
        """
        yaml_doc = _load_yaml(yaml_path)
        schema = _load_schema()
        Draft202012Validator(schema).validate(yaml_doc)
        return cls(_build_registry(yaml_doc), dsn)

    # ---------- lifecycle ----------

    async def start(self) -> None:
        """Start the long-lived LISTEN task (idempotent)."""
        if self._listen_task is None or self._listen_task.done():
            self._stopped = False
            self._listen_task = asyncio.create_task(self._listen_forever())

    async def stop(self) -> None:
        """Cancel listener + close connection. Safe to call multiple times."""
        self._stopped = True
        task = self._listen_task
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._listen_task = None
        if self._listen_conn is not None and not self._listen_conn.is_closed():
            try:
                await self._listen_conn.close()
            except Exception:  # noqa: BLE001 — best-effort close
                pass
            self._listen_conn = None

    # ---------- query ----------

    async def is_enabled(self, name: str, *, session_id: UUID | None = None) -> bool:
        """Return the current ``enabled`` state for ``name`` (FR-002).

        Unknown ``name`` (not declared in YAML) raises :class:`UnknownFeatureFlag`
        — never silently false (FR-004). ``session_id`` is reserved for future
        per-session overrides and is currently ignored.
        """
        del session_id  # reserved for future per-session rollouts
        if name not in self._registry:
            raise UnknownFeatureFlag(name)
        now = time.monotonic()
        cached = self._cache.get(name)
        if cached is not None and cached[1] > now:
            return cached[0]
        value = await self._read_from_db(name)
        async with self._cache_lock:
            self._cache[name] = (value, now + _CACHE_TTL_SECONDS)
        return value

    # ---------- testing helpers ----------

    def _registry_view(self) -> Mapping[str, _FlagDecl]:
        """Read-only snapshot of the registry — used by tests + the hook script."""
        return dict(self._registry)

    # ---------- internals ----------

    async def _read_from_db(self, name: str) -> bool:
        """One-shot read of the current ``enabled`` value.

        Opens a fresh asyncpg connection per call; the cache hits make this
        rare. If the row does not exist yet (the sync workflow has not run
        since the YAML entry landed), fall back to the YAML ``default`` —
        which is ``false`` for any §9-conformant declaration.
        """
        conn = await asyncpg.connect(self._dsn)
        try:
            row = await conn.fetchrow(
                "SELECT enabled FROM feature_flag WHERE name = $1",
                name,
            )
        finally:
            await conn.close()
        if row is None:
            return self._registry[name].default
        return bool(row["enabled"])

    def _invalidate(self, name: str) -> None:
        """Drop one cache entry. Called from the asyncpg NOTIFY callback."""
        self._cache.pop(name, None)

    async def _listen_forever(self) -> None:
        """Long-lived listener with exponential-backoff reconnect (research §3)."""
        backoff = _RECONNECT_BACKOFF_INITIAL_S
        while not self._stopped:
            try:
                self._listen_conn = await asyncpg.connect(self._dsn)
                await self._listen_conn.add_listener(_NOTIFY_CHANNEL, self._on_notify)
                _log.info("feature_flag listener connected (channel=%s)", _NOTIFY_CHANNEL)
                backoff = _RECONNECT_BACKOFF_INITIAL_S  # reset on success
                # Sleep loop: wake periodically to react to stop() promptly.
                while not self._stopped and not self._listen_conn.is_closed():
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — log and back off
                _log.warning(
                    "feature_flag listener error: %s; reconnecting in %.1fs",
                    exc,
                    backoff,
                )
            finally:
                if self._listen_conn is not None and not self._listen_conn.is_closed():
                    try:
                        await self._listen_conn.close()
                    except Exception:  # noqa: BLE001 — best-effort close
                        pass
                self._listen_conn = None
            if self._stopped:
                return
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _RECONNECT_BACKOFF_CAP_S)

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """asyncpg NOTIFY callback — invalidate the matching cache entry."""
        del connection, pid, channel
        if payload:
            self._invalidate(payload)


# ---------------------------------------------------------------------------
# Module-level singleton + thin wrappers
# ---------------------------------------------------------------------------

_singleton: FeatureFlagService | None = None


def set_service(service: FeatureFlagService | None) -> None:
    """Install (or clear) the process-wide service. Called by main.py + tests."""
    global _singleton
    _singleton = service


def get_service() -> FeatureFlagService:
    """Return the installed service, or raise if main.py has not run startup."""
    if _singleton is None:
        raise RuntimeError(
            "FeatureFlagService is not initialised. Did FastAPI startup run? "
            "Tests must call set_service() with an injected instance."
        )
    return _singleton


async def is_enabled(name: str, *, session_id: UUID | None = None) -> bool:
    """Module-level convenience wrapper over the singleton (FR-002).

    Every consumer in Tier 3+ imports this name directly:
    ``from app.backend.services.feature_flags import is_enabled``.
    """
    return await get_service().is_enabled(name, session_id=session_id)
