import logging
from collections.abc import Mapping
from typing import Final

from asm_contracts.nuclei import NucleiFinding, NucleiTarget
from asm_contracts.nuclei_task import NucleiScanResult, NucleiScanStatus, NucleiScanTask
from asm_execution.command import CommandExecutionError, CommandRunner, CommandTimeoutError
from asm_nuclei_worker.scan import scan_batch

logger = logging.getLogger(__name__)

NUCLEI_MAX_ATTEMPTS: Final = 2


async def run_batch[K](
    runner: CommandRunner, nuclei_path: str, tasks: Mapping[K, NucleiScanTask]
) -> dict[K, NucleiScanResult]:
    """Scans one batch and answers every member: its findings, or the error text.

    All members share one group (same params and timeout), so the first one speaks for the batch.
    Never raises: any failure becomes an ERROR answer for every member.
    """
    first = next(iter(tasks.values()))
    targets = [task.target for task in tasks.values()]
    try:
        findings = await _scan_with_retry(runner, nuclei_path, targets, first)
    except Exception as exc:  # top-level handler: a raise would fail every member without an answer
        logger.exception("nuclei batch of %d targets failed", len(targets))
        error = str(exc) or type(exc).__name__
        return {
            key: NucleiScanResult(target=task.target, status=NucleiScanStatus.ERROR, error=error)
            for key, task in tasks.items()
        }
    return {
        key: NucleiScanResult(
            target=task.target,
            status=NucleiScanStatus.SUCCESS,
            findings=[finding for finding in findings if finding.target == task.target],
        )
        for key, task in tasks.items()
    }


async def _scan_with_retry(
    runner: CommandRunner, nuclei_path: str, targets: list[NucleiTarget], first: NucleiScanTask
) -> list[NucleiFinding]:
    """Runs nuclei, retrying once on a failed run; a timeout is never retried."""
    for attempt in range(1, NUCLEI_MAX_ATTEMPTS + 1):
        try:
            return await scan_batch(runner, nuclei_path, targets, first.params, first.timeout)
        except CommandTimeoutError:
            raise
        except CommandExecutionError:
            if attempt == NUCLEI_MAX_ATTEMPTS:
                raise
            logger.warning("nuclei run failed (attempt %d), retrying", attempt)
    raise AssertionError("unreachable")
