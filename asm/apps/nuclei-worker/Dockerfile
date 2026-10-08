# syntax=docker/dockerfile:1
# Build from the asm/ directory: docker build -f apps/nuclei-worker/Dockerfile .
# linux/amd64 only: the nuclei release archive below is the amd64 build.
FROM python:3.12-slim AS nuclei

ARG NUCLEI_VERSION=3.11.1
ARG NUCLEI_SHA256=ea63d4ae232808cd7c6bc00d0142428e231fab59dae01042246097d195835ab6
ARG TEMPLATES_VERSION=10.4.9

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /fetch
RUN curl -fsSLO "https://github.com/projectdiscovery/nuclei/releases/download/v${NUCLEI_VERSION}/nuclei_${NUCLEI_VERSION}_linux_amd64.zip" \
    && echo "${NUCLEI_SHA256}  nuclei_${NUCLEI_VERSION}_linux_amd64.zip" | sha256sum -c - \
    && unzip -q "nuclei_${NUCLEI_VERSION}_linux_amd64.zip" nuclei \
    && curl -fsSL "https://github.com/projectdiscovery/nuclei-templates/archive/refs/tags/v${TEMPLATES_VERSION}.tar.gz" -o templates.tar.gz \
    && mkdir nuclei-templates \
    && tar -xzf templates.tar.gz -C nuclei-templates --strip-components=1


FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Third-party deps first, cached separately from app source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-workspace --no-dev --package asm-nuclei-worker

# Now the workspace source, and the real (non-editable) install.
COPY packages/ packages/
COPY apps/nuclei-worker/ apps/nuclei-worker/
RUN uv sync --frozen --no-dev --no-editable --package asm-nuclei-worker


FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=nuclei /fetch/nuclei /usr/local/bin/nuclei
COPY --from=nuclei --chown=appuser:appuser /fetch/nuclei-templates /home/appuser/nuclei-templates
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# Needs HATCHET_CLIENT_TOKEN. NUCLEI_PATH defaults to `nuclei`, which is on PATH.
CMD ["python", "-m", "asm_nuclei_worker.main"]
