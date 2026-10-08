# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f apps/httpx-worker/Dockerfile .
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Third-party deps first, cached separately from app source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-workspace --no-dev --package asm-httpx-worker

# Now the workspace source, and the real (non-editable) install.
COPY packages/ packages/
COPY apps/httpx-worker/ apps/httpx-worker/
RUN uv sync --frozen --no-dev --no-editable --package asm-httpx-worker


FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# Needs HATCHET_CLIENT_TOKEN (and HATCHET_CLIENT_HOST_PORT / HATCHET_CLIENT_TLS_STRATEGY when not in the token).
CMD ["python", "-m", "asm_httpx_worker.main"]
