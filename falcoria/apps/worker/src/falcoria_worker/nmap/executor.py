"""Impure async subprocess execution: lifecycle and signal escalation."""

import asyncio

from falcoria_worker.exceptions import CommandExecutionError, CommandTimeoutError


class AsyncCommandExecutor:
    """Runs one subprocess to completion, escalating signals on timeout or cancellation."""

    def __init__(self, grace_period_seconds: float = 5.0) -> None:
        self._grace_period_seconds = grace_period_seconds

    async def run(self, command: list[str], *, timeout: float | None = None) -> None:
        """Runs `command` to completion.

        On timeout or cancellation the process is sent SIGTERM, then SIGKILL after
        `grace_period_seconds` if it is still alive.

        Raises:
            CommandTimeoutError: `timeout` elapsed before the process exited.
            CommandExecutionError: the process exited with a non-zero status.
        """
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            await self._terminate(process)
            raise CommandTimeoutError(f"Command timed out after {timeout}s: {command}") from None
        except asyncio.CancelledError:
            await self._terminate(process)
            raise

        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise CommandExecutionError(
                f"Command exited with code {process.returncode}: {command}"
                + (f"\n{detail}" if detail else "")
            )

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self._grace_period_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()
