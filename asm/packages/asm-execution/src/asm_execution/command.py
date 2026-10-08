"""OS command execution: spawn, timeout, and SIGTERM→SIGKILL of the process group."""

import asyncio
import contextlib
import os
import signal
from typing import Protocol


class CommandExecutionError(Exception):
    """Raised when a command exits with a non-zero status."""


class CommandTimeoutError(Exception):
    """Raised when a command exceeds its timeout, even after SIGKILL escalation."""


class CommandRunner(Protocol):
    """Runs one command to completion; the interface scanners depend on."""

    async def run(self, command: list[str], *, timeout: float | None = None) -> bytes:
        """Runs `command` to completion and returns its stdout."""
        ...


class OsCommandRunner:
    """Runs one subprocess to completion, stopping its process group on timeout or cancellation."""

    def __init__(self, grace_period_seconds: float = 5.0) -> None:
        self._grace_period_seconds = grace_period_seconds

    async def run(self, command: list[str], *, timeout: float | None = None) -> bytes:
        """Runs `command` to completion and returns its stdout.

        stdin is /dev/null, so a command that reads stdin when it's a pipe (nuclei does) can't hang
        on the worker's own stdin.

        The process runs in its own session, so its children (e.g. headless Chrome) share its
        process group. On timeout or cancellation the group is sent SIGTERM, then SIGKILL after
        `grace_period_seconds`.

        Raises:
            CommandTimeoutError: `timeout` elapsed before the process exited.
            CommandExecutionError: the process exited with a non-zero status.
        """
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            await self._stop(process)
            raise CommandTimeoutError(f"Command timed out after {timeout}s: {command}") from None
        except asyncio.CancelledError:
            await self._stop(process)
            raise

        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise CommandExecutionError(
                f"Command exited with code {process.returncode}: {command}"
                + (f"\n{detail}" if detail else "")
            )
        return stdout

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        """SIGTERM the process group, then SIGKILL whatever is left after the grace period.

        SIGKILL runs in `finally`, so a cancellation during the grace period can't skip it, and it
        goes to the group even if the leader already exited, since children may outlive it.
        """
        _signal_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=self._grace_period_seconds)
        except TimeoutError:
            pass
        finally:
            _signal_group(process, signal.SIGKILL)
            await process.wait()


def _signal_group(process: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    """Signals the process's group; a group that no longer exists is not an error."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, sig)
