# syntax=docker/dockerfile:1.7
# TechScreen backend image.
# Same image runs in dev, CI, and prod — behaviour is selected by env vars
# (LLM_BACKEND, APP_ENV). This is ADR-010 (Docker parity).

# ---------------------------------------------------------------------------
# Stage 1 — builder: install Python deps using uv, prepare a clean virtualenv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# System deps needed to build a few wheels (psycopg, cryptography).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install uv (pinned). Pulling the binary from the official astral image
# is faster, deterministic, and avoids the install-script's PATH quirks
# that broke earlier (`~/.cargo/bin` vs `~/.local/bin`).
COPY --from=ghcr.io/astral-sh/uv:0.4.25 /uv /usr/local/bin/uv

WORKDIR /app

# Copy only manifests first for better layer cache.
COPY pyproject.toml uv.lock ./

# Install deps into /app/.venv. No dev deps for runtime image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy the app and install the project itself.
COPY app/backend ./app/backend
COPY alembic ./alembic
# TODO(T05): re-introduce `COPY alembic.ini ./` once Alembic is wired.
# Today the file does not exist; copying a missing file fails the build.
COPY configs ./configs
COPY prompts ./prompts

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — dev: extends builder with dev deps (pytest, httpx, types-PyYAML).
# Used by docker-compose.yml (local dev with hot reload) and
# docker-compose.test.yml (pytest in container parity). NEVER deployed to
# Cloud Run — production always uses the `runtime` stage below
# (constitution §7).
# ---------------------------------------------------------------------------
FROM builder AS dev

ENV PATH="/app/.venv/bin:${PATH}" \
    APP_ENV=dev \
    LOG_FORMAT=json

# Add dev deps on top of the prod venv. Cached layer; only re-runs when
# `pyproject.toml` or `uv.lock` change.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

EXPOSE 8000

CMD ["uvicorn", "app.backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload"]

# ---------------------------------------------------------------------------
# Stage 3 — runtime: minimal image with only runtime deps + the virtualenv.
# This is what Cloud Run runs.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    APP_ENV=prod \
    LOG_FORMAT=json

# Runtime-only native libs.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libpq5 \
        tini \
        ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Non-root user. Cloud Run runs as root by default but we refuse to.
RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin techscreen

WORKDIR /app

# Copy the built virtualenv and source from the builder stage.
COPY --from=builder --chown=techscreen:techscreen /app /app

USER techscreen

EXPOSE 8000

# tini reaps zombies + forwards signals properly (Cloud Run cares).
ENTRYPOINT ["/usr/bin/tini", "--"]

# Uvicorn is fine at the scale we care about. Cloud Run gives one instance
# a single concurrent request ceiling; we configure that at deploy time.
CMD ["uvicorn", "app.backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
