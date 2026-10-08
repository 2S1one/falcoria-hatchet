# syntax=docker/dockerfile:1
# Build from the asm/ directory: docker build -f apps/asm-core/Dockerfile .
# One image, three entry points; pick one with the container command:
#   python -m asm_core.main                                   Hatchet worker: chain and findings storage (default)
#   uvicorn asm_core.app:fastapi_app --host 0.0.0.0 --port 8000   REST API
#   python -m asm_core.bridge_main                            scanledger event poller
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Third-party deps first, cached separately from app source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-workspace --no-dev --package asm-core

# Now the workspace source, and the real (non-editable) install.
COPY packages/ packages/
COPY apps/asm-core/ apps/asm-core/
RUN uv sync --frozen --no-dev --no-editable --package asm-core


FROM python:3.12-slim AS runtime

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# Needs HATCHET_CLIENT_TOKEN and ASM_CORE_DB_*; the bridge also needs SCANLEDGER_API_URL and SCANLEDGER_ASM_TOKEN.
CMD ["python", "-m", "asm_core.main"]
