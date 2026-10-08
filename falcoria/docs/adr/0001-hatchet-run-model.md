# 0001. Hatchet run model for scans

Status: accepted (2026-10-05)

## Context

The Temporal version ran one parent workflow per batch of scan tasks. The parent held a sliding
window, counted progress (answered by a query), set search attributes, and cancelled children.
A scan machine runs exactly one nmap at a time (one process uses all the network bandwidth), so
parallelism equals the number of scan workers.

Evidence: `refactor/hatchet-experiments/README.md` (E1–E13) and the Hatchet docs (Runs client,
Cancellation, Additional Metadata, Timeouts, Durable Tasks, Priority, Workers, Worker Affinity).

## Decision

1. **No parent task.** `tasker` starts one workflow run per (IP, port-shard) in one bulk call.
   Hatchet's queue holds the backlog.
2. **One workflow `scan-target`, two regular tasks:** `scan` (nmap) then `upload` (report to
   scanledger). Neither is a durable task: nmap is a long local process that must occupy the
   worker, and durable tasks must not call external APIs directly. The report passes from `scan`
   to `upload` as the task output through Hatchet (default message limit 4 MiB), so it is visible
   in Hatchet.
3. **Two worker pools, routed by the worker label `role`:** `scanner` (`slots=1`, scan servers)
   and `uploader` (`slots=10`, control plane next to `tasker`). Priority cannot replace this: it
   is set per run, not per task, and only orders runs of one workflow. Both processes use one
   package and image, started by `falcoria-scanner` / `falcoria-uploader`.
4. **Retries are Hatchet's:** `scan` `retries=1`, `upload` `retries=3` with `backoff_factor=2.0`,
   `backoff_max_seconds=10`. No retry loop in application code.
5. **Timeouts:** `execution_timeout` is fixed when a task is declared (it cannot be set per run),
   so the request's per-IP timeout is enforced by the executor and Hatchet's value is an outer
   bound. `schedule_timeout` is `SCAN_MAX_AGE` (7 days) on both tasks: the default 5 minutes
   fails queued tasks (verified).
6. **Scan identity lives in `additional_metadata`.** Keys: `project_scan`
   (`"<project_id>:<scan_id>"`), `project`, `ip`. A run filter with several keys matches ANY of
   them, so every filter uses exactly one key.
7. **Progress and scan state** are computed by `tasker` from workflow-level run statuses
   (`only_tasks=False`; two tasks per IP would double the counts otherwise) of the runs matching
   `project_scan`. The status response carries `queued`, `running`, `completed`, `failed`,
   `cancelled` and `total`. State: running if anything is queued or running, else cancelled, else
   failed, else completed.
8. **Cancel** is one bulk cancel by `project_scan` for QUEUED and RUNNING runs; a running scan
   task receives `asyncio.CancelledError` and the executor terminates nmap. No graceful period or
   forced terminate step.
9. **Run listings always pass `since`** (`SCAN_MAX_AGE` back): Hatchet defaults to the last 24 h.
10. **Worker fleet view** comes from `workers.aio_list()`, filtered to active workers with the
    `scanner` role. The worker name is `hostname_external_ip` (Hatchet rejects `:` in names). The IP
    a worker is scanning comes from `runs.aio_list(worker_id=..., statuses=[RUNNING])` and the
    run's metadata.
11. **Scan options are parsed on the worker.** The task carries the raw options; building the
    scanner arguments moved from `tasker` to `worker`. The option models live in
    `falcoria-contracts`. The scanner needs no access to scanledger.
12. **A failed bulk start is not rolled back:** the error reaches the client as a 500 and the scan
    can be cancelled with the normal cancel request.

## Alternatives considered

- Parent durable task with window and counters (Temporal-style): cancelling the parent does not
  cancel its children, so a separate bulk cancel is needed anyway; more code, more state.
- One task doing nmap and upload: a retry after an upload failure would rerun nmap; the report
  would not be visible in Hatchet.
- Hatchet `concurrency` limit instead of `slots=1`: not needed, slots already give one nmap per
  worker.

## Consequences

- Cancelling a scan, listing running scans and progress all depend on run filters and the
  metadata keys above; changing a key name is a contract change between `tasker` and `worker`.
- The scan report goes scanner → Hatchet → uploader, and is limited by the message size limit.
- Two processes per deployment (scanner on scan servers, uploader on the control plane).
- `schedule_timeout` was tested only up to 1 hour.
- Not exercised: upload retries when scanledger fails, two scanner workers at once.
