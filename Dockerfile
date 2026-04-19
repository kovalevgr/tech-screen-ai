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
        curl \
        libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# Install uv (pinned).
RUN curl -LsSf https://astral.sh/uv/0.4.25/install.sh | sh \
 && mv /root/.local/bin/uv /usr/local/bin/uv

WORKDIR /app

# Copy only manifests first for better layer cache.
COPY pyproject.toml uv.lock ./

# Install deps into /app/.venv. No dev deps for runtime image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy the app and install the project itself.
COPY app/backend ./app/backend
COPY alembic ./alembic
COPY alembic.ini ./
COPY configs ./configs
COPY prompts ./prompts

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
# Stage 2 — runtime: minimal image with only runtime deps + the virtualenv.
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
