# Navigation

Entrypoints (`main.py` factories, route handlers, the two worker commands) are listed in [ARCHITECTURE.md](ARCHITECTURE.md). This file indexes the symbols a task lands on after the entrypoint.

## Symbol index

### Shared contracts (`packages/falcoria-contracts/src/falcoria_contracts`)

- `scan_names.py#scan_run_metadata` — builds the three metadata keys attached to every run (`project`, `project_scan`, `ip`); tasker filters on them, so open it before touching run queries.
- `scan_names.py#SCAN_WORKFLOW_NAME`, `SCAN_MAX_AGE`, `WORKER_ROLE_LABEL`, `ROLE_SCANNER`, `ROLE_UPLOADER` — the names and limits tasker and worker both depend on.
- `scan_io.py#ScanTask` — the run input: IP, hostnames, scan options, timeout, mode, project and scan ids.
- `scan_options.py#OpenPortsOpts`, `ServiceOpts` — option models validated by tasker and turned into nmap arguments by worker.
- `enums.py#ImportMode` — `insert`, `replace`, `update`, `append`.

### tasker (`apps/tasker/src/falcoria_tasker`)

- `scans/service.py#_prepare_targets` — classify, resolve and dedup the requested hosts.
- `scans/service.py#_dedupe_insert_mode` — INSERT-mode skip of IPs scanledger knows or Hatchet is already running.
- `scans/service.py#_build_tasks` — one `ScanTask` per (IP, port shard); open it to change what a run carries.
- `scans/service.py#_scan_state` — maps run-status counts to `running`, `cancelled`, `failed`, `completed`.
- `scans/targets.py#partition_targets`, `is_public_ip`, `expand_cidr` — pure target rules; private ranges are dropped here.
- `scans/resolve.py#resolve_targets` — DNS resolution with retries.
- `scans/sharding.py#shard_ports` — balanced port splitting.
- `scans/schemas.py#RunScanRequest`, `_validate_host` — request shape and the accepted host formats (IPv4, IPv4 CIDR no larger than /16, FQDN).
- `hatchet/runs.py#start_scan_tasks`, `count_by_status`, `running_targets`, `cancel_scan`, `cancel_project`, `cancel_ips` — every Hatchet run operation.
- `hatchet/workers.py#active_scanners` — active workers carrying the `role=scanner` label.
- `scanledger.py#ScanledgerClient` — access check, IP search, hostname merge calls.
- `security.py#require_project_access`, `require_token` — bearer check delegated to scanledger, cached per token hash and project.

### worker (`apps/worker/src/falcoria_worker`)

- `workflow.py#build_workflow` — declares tasks `scan` and `upload`, their retries, timeouts and label routing.
- `scan.py#scan_ip`, `upload_report`, `ScanReport` — bodies of the two tasks.
- `nmap/args.py#build_open_ports_args`, `build_service_args` — option models to nmap argument strings.
- `nmap/scanner.py#run_nmap_scan` — open-ports pass, optional service pass, merge.
- `nmap/xml.py#parse_open_ports`, `enrich_xml` — pure XML helpers.
- `nmap/executor.py#AsyncCommandExecutor` — subprocess run; SIGTERM then SIGKILL on timeout or cancel.
- `main.py#_run`, `worker_name` — worker registration, labels and naming.

### scanledger (`apps/scanledger/src/falcoria_scanledger`)

- `ips/service.py#apply_import` — the import transaction: lock rows, dedup, apply mode, write history and events.
- `ips/modes.py#apply_mode`, `_POLICIES` — per-mode matrix of what a report may add, refresh or close.
- `ips/reconcile.py#diff_ports`, `refresh_port`, `close_stale_port` — port comparison primitives.
- `ips/nmap.py#parse_report`, `export_report` — nmap XML in and out.
- `ips/search.py#build_search_conditions` — compiles the search filter to SQL.
- `events/service.py#write_events`, `read_events` — outbox write and the cursor-based read.
- `events/build.py#build_event` — builds one `IPChangedEvent` from a change set.
- `auth/service.py#ensure_primary_users` — seeds `admin`, `tasker`, `worker`, `asm` from settings at startup.
- `auth/tokens.py#hash_token`, `generate_token` — token primitives, no I/O.
- `projects/dependencies.py#validate_project_access` — membership gate used by every project-scoped router.
- `database.py#get_session` — request-scoped unit of work: commit on success, rollback on error.

## Task routing

| To do this | Start at | Then check |
|---|---|---|
| Add or change an nmap option | `falcoria_contracts/scan_options.py` | `worker/nmap/args.py`, `tasker/scans/schemas.py`, tests in `packages/falcoria-contracts/tests` and `apps/worker/tests` |
| Accept a new kind of target | `tasker/scans/schemas.py#_validate_host` | `scans/targets.py`, `scans/resolve.py`, `apps/tasker/tests/scans` |
| Change what an import mode does | `scanledger/ips/modes.py#_POLICIES` | `ips/reconcile.py`, `events/build.py`, `apps/scanledger/tests/ips/test_modes.py` |
| Add a scanledger endpoint | new router in its package, mounted in `main.py#create_app` with its prefix and dependencies | schemas, service, `constants.py#Tag`, tests |
| Change the database schema | the package's `models.py` | a new Alembic revision under `apps/scanledger/migrations/versions`, `apps/scanledger/tests/conftest.py` imports (it builds the schema with `create_all`) |
| Add, rename or reroute a workflow task | `worker/workflow.py#build_workflow` | `worker/constants.py`, `falcoria_contracts/scan_names.py`, `tasker/hatchet/runs.py` filters |
| Change progress or cancel behavior | `tasker/hatchet/runs.py` | `scans/service.py#_scan_state`, `apps/tasker/tests/hatchet` |
| Change the event payload | `scanledger/events/schemas.py` | `events/build.py`, `events/service.py`, every event consumer outside this repository |
| Change authentication | `scanledger/auth/` | `tasker/security.py` (delegates the check), seeded accounts in `main.py#lifespan` |
| Debug a scan that stays queued | `GET /api/workers`, `tasker/hatchet/workers.py#active_scanners` | worker labels in `worker/main.py#_run`, `schedule_timeout` in `workflow.py` |
| Debug a failed upload | `worker/scanledger.py` | `ips/router.py` (400 parse error, 413 size limit via `max_report_bytes`), task retries in `workflow.py` |
| Add a test | the app's `tests/` mirror of the source tree | `conftest.py` files, [TESTING.md](TESTING.md) |

## Change impact

- **`falcoria_contracts`** is imported by all three apps. A changed field in `ScanTask`, an option model or a name constant needs matching edits in tasker and worker, and in-flight Hatchet runs keep the old input shape.
- **`worker/workflow.py`** defines names that tasker queries by (`SCAN_WORKFLOW_NAME`, step names in `constants.py`). Renaming a task or a label breaks routing and run listings without a type error.
- **`scanledger/ips/service.py`** and **`events/`** are coupled: events are written in the import transaction, and the feed's visibility rule depends on it (see [INVARIANTS.md](INVARIANTS.md)).
- **`scanledger/database.py`** sets the idle-in-transaction timeout for the whole service.
- **Settings classes** (`config.py` in each app) read environment variables with the prefixes listed in [INTEGRATIONS.md](INTEGRATIONS.md); a new required field breaks startup and the test environment in the root `conftest.py`.
