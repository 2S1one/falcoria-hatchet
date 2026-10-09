# Navigation

Entrypoints are in `ARCHITECTURE.md`. A path that starts with a package name (`asm_core/`, `asm_nuclei_worker/`, `asm_httpx_worker/`, `asm_contracts/`, `asm_execution/`) is under that package's `src/` directory in its app or package folder. A path in a section headed by one of those names is relative to that package.

## Symbol index

asm_core:
- `chain.py#run_chain` — httpx, store, then start nuclei if `is_http`. Takes the four steps as callables, so tests run it without Hatchet.
- `chain.py#run_httpx_store` — the same without the nuclei leg; used by the API's httpx launch.
- `tasks.py#_save_httpx` — opens a session, calls `save_httpx_result`, commits.
- `tasks.py#start_chain`, `start_nuclei_scans`, `start_httpx_scans` — launch runs without waiting; the last two send chunks of `BULK_START_SIZE` (250).
- `scanledger_bridge/adapter.py#_derive_targets` — rules A, B, C: event to (hostname, port) pairs.
- `scanledger_bridge/adapter.py#_mark_seen` — dedup insert; True only for a new (project, scan, target, port, protocol).
- `scanledger_bridge/adapter.py#handle_event` — one event to launches; launch runs before the dedup row commits.
- `scanledger_bridge/poller.py#_drain_project` — pages through one project's feed and saves the cursor after each page.
- `scanledger_bridge/events.py` — local copy of the scanledger event-feed models; open it when the feed changes.
- `persistence/nuclei.py#reconcile_target_findings` — upsert reported findings, delete resolved ones.
- `persistence/httpx.py#save_httpx_result` — upsert one probe, keep `first_seen_*`.
- `db/database.py#create_db_and_tables` — lists the tables it creates; a new table model must be added here.
- `config.py#get_chain_settings` — nuclei params for the chain, from `ASM_CORE_CHAIN_NUCLEI_PARAMS`.

asm_nuclei_worker:
- `batch.py#run_batch` — one answer per member; never raises.
- `batch.py#_scan_with_retry` — second attempt on `CommandExecutionError`, none on `CommandTimeoutError`.
- `scan.py#scan_batch` — writes the target list file, runs nuclei, parses JSONL.
- `scan.py#nuclei_input` and `_input_line` — the `host:port[/path]` line a target becomes and the line a finding maps back from.
- `args.py#build_command` — `NucleiScanParams` to nuclei argv.

asm_httpx_worker:
- `probe.py#probe` — https first; http only after `TLS_REJECTED` or `TLS_HANDSHAKE_FAILED`.
- `transport.py#pinned_client` — client that connects to the given IP and does not verify certificates.
- `errors.py#classify_exception` — exception to `ScanStatus`; re-raises an exception type it does not know.

asm_contracts and asm_execution:
- `nuclei_task.py#NucleiScanTask.batch_key` — group key: project, scan, hash of params and timeout.
- `nuclei.py#NucleiScanParams` — nuclei flags with defaults and bounds.
- `httpx.py#HttpxScanResult.is_http` — true when any attempt succeeded.
- `asm_execution/command.py#OsCommandRunner.run` — subprocess with timeout; SIGTERM then SIGKILL to the process group.

## Task routing

| To do | Start at | Then check |
|---|---|---|
| Change which targets an event produces | `scanledger_bridge/adapter.py#_derive_targets` | `tests/test_scanledger_adapter.py`; `events.py` if the feed fields change |
| Change the nuclei params the chain uses | `config.py` (`ChainSettings`) | `NucleiScanParams` bounds in `asm_contracts/nuclei.py`; `batch_key` changes with params |
| Add a nuclei flag | `asm_contracts/nuclei.py#NucleiScanParams` | `args.py#build_command`, `tests/test_nuclei_args.py`; the field also splits batches |
| Change batch size or interval | `asm_nuclei_worker/constants.py` | `docs/hatchet-batch-timing.md` first; the values are placeholders |
| Change how findings are stored or retired | `persistence/nuclei.py` | `db/models.py`, `tests/test_persistence.py` |
| Add a column or table | `db/models.py` | `db/database.py#create_db_and_tables`, `_TABLES` in `apps/asm-core/tests/conftest.py`; existing tables are not altered |
| Add an API endpoint | `api/<scanner>/router.py` | `app.py#create_app`, `api/<scanner>/schemas.py` |
| Change who may call the API | `api/security.py#require_project_access` | `api/scanledger_access.py`, `api/errors.py`, router `dependencies=` in `api/<scanner>/router.py`, `tests/test_api_security.py` |
| Change httpx probe behavior | `probe.py`, `errors.py` | `ScanStatus` in `asm_contracts/httpx.py`, `tests/test_probe.py`, `tests/test_errors.py` |
| Change a timeout, slot count or retry | `asm_core/constants.py`, `asm_nuclei_worker/constants.py`, `asm_httpx_worker/tasks.py` | Hatchet limits in `ARCHITECTURE.md` task table |
| Rename a Hatchet task | `asm_contracts/task_names.py` | needs approval; every stub and worker registration |
| Update nuclei or its templates | `apps/nuclei-worker/Dockerfile` (`NUCLEI_VERSION`, `NUCLEI_SHA256`, `TEMPLATES_VERSION`) | `.github/workflows/asm-ci.yml` docker build check |
| A target never launches | `adapter.py#handle_event` | event `scan_id` null (skipped); row in `scanledger_bridge_seen_targets`; cursor in `scanledger_bridge_cursor` |
| Add a scanner | a new task and result in `asm_contracts`, a worker app, a stub in `asm_core/tasks.py` | table in `db/`, router in `api/`, Dockerfile, `asm-ci.yml` filter, `asm-publish.yml` matrix |

## Change impact

- `asm_contracts`: imported by all three apps. A changed field breaks runs already queued in Hatchet that carry the old shape.
- `task_names.py`: the names are registered on workers and called through stubs; one side renamed alone means calls wait for a worker that does not exist.
- `batch_key` and `NucleiScanParams`: a change to either changes which targets share a nuclei process.
- `db/models.py`: `create_all` adds missing tables only. A changed column needs a manual change to a running database.
- `scanledger_bridge/events.py`: a copy of scanledger's feed models. A field renamed in `falcoria/apps/scanledger` is not noticed by asm CI.
