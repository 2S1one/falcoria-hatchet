# syntax=docker/dockerfile:1
# Build from the repository root: docker build -f apps/worker/Dockerfile .
# One image, two roles; pick one with the container command:
#   falcoria-scanner    nmap runner, one scan at a time (default; needs the capabilities below)
#   falcoria-uploader   uploads scan reports to scanledger (control plane; does not use nmap)
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Third-party deps first, cached separately from app source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-workspace --no-dev --package falcoria-worker

# Now the workspace source, and the real (non-editable) install.
COPY packages/ packages/
COPY apps/worker/ apps/worker/
RUN uv sync --frozen --no-dev --no-editable --package falcoria-worker


FROM python:3.12-slim AS runtime

# libcap2-bin provides setcap, used once below then removed: the resulting
# file capability on the nmap binary is what matters at runtime, not the tool.
RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        libcap2-bin \
    && setcap cap_net_raw,cap_net_admin+eip /usr/bin/nmap \
    && apt-get purge -y --auto-remove libcap2-bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 appuser

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

# nmap's default TCP scan and its UDP scan (-sU) need CAP_NET_RAW / CAP_NET_ADMIN,
# granted to the nmap binary above via setcap rather than running this container as
# root. Run the scanner with `--cap-add=NET_RAW --cap-add=NET_ADMIN` or scans fail
# with a permissions error. The uploader needs neither.
# nmap decides it may use raw sockets from its effective uid, not from the file capability,
# so a non-root user needs NMAP_PRIVILEGED (verified: without it, `nmap -sS` as appuser
# stops with "requires root privileges" even with the capabilities granted).
ENV NMAP_PRIVILEGED=1

# Needs WORKER_HATCHET_*; the uploader also needs WORKER_SCANLEDGER_*.
CMD ["falcoria-scanner"]
