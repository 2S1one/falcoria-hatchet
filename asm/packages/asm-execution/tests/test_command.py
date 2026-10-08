"""Tests for asm_execution.command — real subprocess lifecycle, not mocked.

Uses trivial shell commands — OsCommandRunner is scanner-neutral and its subprocess/signal-handling
behavior is best verified against real processes rather than a mocked event loop.
"""

import asyncio
import os
from pathlib import Path

import pytest

from asm_execution.command import CommandExecutionError, CommandTimeoutError, OsCommandRunner

pytestmark = pytest.mark.anyio


async def test_run_succeeds_on_zero_exit() -> None:
    await OsCommandRunner().run(["true"])


async def test_run_returns_stdout() -> None:
    assert await OsCommandRunner().run(["echo", "hi"]) == b"hi\n"


async def test_run_gives_the_command_an_empty_stdin() -> None:
    assert await OsCommandRunner().run(["cat"], timeout=5) == b""


async def test_run_raises_on_nonzero_exit() -> None:
    with pytest.raises(CommandExecutionError):
        await OsCommandRunner().run(["false"])


async def test_run_includes_stderr_in_the_error() -> None:
    with pytest.raises(CommandExecutionError, match="boom"):
        await OsCommandRunner().run(["sh", "-c", "echo boom >&2; exit 1"])


async def test_run_raises_command_timeout_error_on_timeout() -> None:
    runner = OsCommandRunner(grace_period_seconds=0.2)
    with pytest.raises(CommandTimeoutError):
        await runner.run(["sleep", "5"], timeout=0.1)


async def test_run_kills_process_that_ignores_sigterm() -> None:
    runner = OsCommandRunner(grace_period_seconds=0.2)
    with pytest.raises(CommandTimeoutError):
        await runner.run(["sh", "-c", "trap '' TERM; sleep 5"], timeout=0.1)


async def test_run_propagates_cancellation() -> None:
    task = asyncio.ensure_future(OsCommandRunner().run(["sleep", "5"]))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def _assert_process_gone(pid: int) -> None:
    """Poll until `pid` no longer exists; an orphan is briefly a zombie until init reaps it."""
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        await asyncio.sleep(0.05)
    pytest.fail(f"Child process {pid} survived")


def _spawn_child_command(pid_file: Path) -> list[str]:
    return ["sh", "-c", f"sleep 60 & echo $! > {pid_file}; wait"]


async def test_run_kills_child_processes_on_timeout(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    runner = OsCommandRunner(grace_period_seconds=0.2)
    with pytest.raises(CommandTimeoutError):
        await runner.run(_spawn_child_command(pid_file), timeout=0.3)
    await _assert_process_gone(int(pid_file.read_text(encoding="utf-8")))


async def test_run_kills_child_processes_on_cancellation(tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    task = asyncio.ensure_future(
        OsCommandRunner(grace_period_seconds=0.2).run(_spawn_child_command(pid_file))
    )
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _assert_process_gone(int(pid_file.read_text(encoding="utf-8")))
