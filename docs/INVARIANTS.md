# Invariants

Rules that break at runtime without breaking a type check or a lint. The basic verification commands are in [MAP.md](MAP.md); commands specific to one rule are listed with it.

## Hatchet contract between tasker and worker

- **Names are a contract.** The workflow name `scan-target`, the step names `scan` and `upload`, the label key `role` with values `scanner` and `uploader`, and the metadata keys `project`, `project_scan` and `ip` are read by both tasker and worker. Renaming one in only one app breaks run listings, status counts and routing, and no test fails at compile time. Lives in `falcoria_contracts/scan_names.py` and `falcoria_worker/constants.py`. Changing a name needs agreement first (see `AGENTS.md`).
- **A run filter uses exactly one metadata key.** A Hatchet filter with several keys matches any of them, so project-wide and scan-wide queries each filter on a single key (`project`, or the composite `project_scan`). Lives in `tasker/hatchet/runs.py`.
- **Counts use workflow-level rows.** `count_by_status` and `_list_runs` pass `only_tasks=False`; with task-level rows each IP counts twice (two tasks per run). `running_targets` is the exception: it reads task-level `RUNNING` rows to learn which worker holds which IP.
- **Listings pass `since`.** Hatchet defaults to the last 24 hours; every list call in `tasker/hatchet/runs.py` passes `since=SCAN_MAX_AGE` (7 days). A scan older than the window disappears from status and cancel.
- **`schedule_timeout` equals `SCAN_MAX_AGE`.** Both tasks in `worker/workflow.py` use it. The Hatchet default of 5 minutes cancels runs that wait in the queue behind running scans.
- **`execution_timeout` is fixed at declaration.** The per-IP timeout from the request is enforced by `AsyncCommandExecutor`; the Hatchet value (`_SCAN_EXECUTION_TIMEOUT`, 2 days 1 hour) is an outer bound.

## Scanner process

- **One scan at a time per scanner process.** `falcoria_worker.main._SCANNER_SLOTS` is 1 because nmap uses the host's whole network bandwidth. Two scanner processes on one host run two nmap processes and share the worker name `<hostname>_<external ip>`.
- **nmap is stopped only by the executor's own paths.** `AsyncCommandExecutor` sends SIGTERM and then SIGKILL on timeout or cancellation. The subprocess is not started in its own process group, so a hard kill of the worker process (SIGKILL, out-of-memory kill) does not stop the nmap child by this code.
- **The container needs capabilities and an environment variable.** `apps/worker/Dockerfile` sets `cap_net_raw,cap_net_admin` on nmap and `NMAP_PRIVILEGED=1`. Without the variable, `nmap -sS` as a non-root user stops with "requires root privileges" even with the capabilities granted. Run with `--cap-add=NET_RAW --cap-add=NET_ADMIN`.
- **The report travels through Hatchet.** `ScanReport.xml` is the `scan` task output and the `upload` task reads it with `ctx.task_output`. Hatchet's default message limit (4 MiB) caps the report size. [TODO] untested with large reports.
- **The uploader builds its scanledger client lazily.** `workflow._get_scanledger` creates it on first use; Hatchet's worker `lifespan` hook is experimental.

## scanledger

- **Events commit with the change they describe.** `events.service.write_events` only stages outbox rows; `database.get_session` commits them with the IP changes. Do not commit inside a service before the events are staged.
- **The import's first statement is the row lock.** `ips.service._load` selects the affected IPs `FOR UPDATE`. A transaction waiting on those locks has no transaction id yet, which the feed's visibility rule depends on (comment in `_load`). Keep it first.
- **The feed hides unfinished transactions.** `events.service._finished` keeps rows with `txid < pg_snapshot_xmin(pg_current_snapshot())`, and the cursor is `<txid>.<id>`. A slow import delays its events and never skips them. Consumers deduplicate on `event_id` because delivery is at least once.
- **Idle transactions are killed after 60 seconds.** `database.get_engine` sets `idle_in_transaction_session_timeout=60000`, because one open transaction holds back the feed for every project.
- **Seed tokens must all differ.** `auth.service.ensure_primary_users` raises `ValueError` if any two of the `admin`, `tasker`, `worker` and optional `asm` tokens are equal, and it overwrites each stored token hash on every startup. Unsetting the `asm` token later does not remove an already-seeded account.
- **INSERT mode adds no ports and no metadata to an existing IP.** In `ips/modes.py` its policy has every flag off; only new hostnames still merge (all modes merge them). Tasker also skips IPs scanledger knows or Hatchet is running, and ignores sharding in this mode (`scans/service._shard_count`). `append`, `update` and `replace` merge progressively more (see `_POLICIES`).
- **The schema belongs to Alembic.** The app never issues DDL (`main.lifespan` docstring). The test suite builds its schema with `SQLModel.metadata.create_all`, so a new models module must also be imported in `apps/scanledger/tests/conftest.py`.

Verify the database-dependent rules with `uv run pytest -m "postgres and not hatchet"` (needs the Postgres described in [TESTING.md](TESTING.md)).
