"""Worker entry points: the scanner (nmap) and the uploader (reports to scanledger)."""

import asyncio
import logging
import re
import socket

import httpx
from falcoria_logging import configure_logging

from falcoria_contracts.scan_names import (
    ROLE_SCANNER,
    ROLE_UPLOADER,
    WORKER_ROLE_LABEL,
)
from falcoria_worker.config import Env, get_app_settings
from falcoria_worker.hatchet_client import build_hatchet
from falcoria_worker.workflow import build_workflow, close_scanledger

logger = logging.getLogger(__name__)

_EXTERNAL_IP_URL = "https://api.ipify.org"
_EXTERNAL_IP_TIMEOUT_SECONDS = 5.0
_SCANNER_SLOTS = 1  # one scan at a time: it uses the host's whole network bandwidth
_UPLOADER_SLOTS = 10


def worker_name(suffix: str) -> str:
    """Builds a Hatchet-valid worker name: hostname_suffix, other characters replaced by '-'."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", f"{socket.gethostname()}_{suffix}")


def _resolve_external_ip() -> str:
    """Fetches this host's external IP; falls back to "unknown" on any failure."""
    try:
        response = httpx.get(_EXTERNAL_IP_URL, timeout=_EXTERNAL_IP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not resolve external IP; using 'unknown'.")
        return "unknown"
    return response.text.strip()


def _run(role: str, name: str, slots: int) -> None:
    settings = get_app_settings()
    configure_logging(level=settings.log_level, json_output=settings.env is not Env.LOCAL)
    hatchet = build_hatchet()
    worker = hatchet.worker(
        name,
        slots=slots,
        labels={WORKER_ROLE_LABEL: role},
        workflows=[build_workflow(hatchet)],
    )
    try:
        worker.start()
    finally:
        asyncio.run(close_scanledger())


def scanner() -> None:
    """Runs the scanner worker, named hostname_external_ip, until stopped."""
    _run(ROLE_SCANNER, worker_name(_resolve_external_ip()), _SCANNER_SLOTS)


def uploader() -> None:
    """Runs the uploader worker until stopped."""
    _run(ROLE_UPLOADER, worker_name("uploader"), _UPLOADER_SLOTS)
