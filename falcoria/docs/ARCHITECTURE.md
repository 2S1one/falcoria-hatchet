# Architecture

Falcoria scans hosts with nmap and stores what it finds. Three processes do the work, and a self-hosted Hatchet engine sits between them as the task queue.

- **scanledger** (`apps/scanledger`) is the system of record. It owns projects, users, IPs, open ports, hostnames, the port-change history and the event outbox. It accepts nmap XML, merges it into stored state under one of four import modes, and serves an event feed.
- **tasker** (`apps/tasker`) is a stateless REST API. It validates a scan request, resolves and deduplicates targets, and starts one Hatchet run per (IP, port shard). It also reports scan progress and cancels runs. It holds no scan data; run state lives in Hatchet.
- **worker** (`apps/worker`) is one package with two Hatchet worker entry points. The scanner runs nmap, one scan at a time per process. The uploader sends the finished XML report to scanledger.

Data ownership: scanledger owns all scan results. Hatchet owns run state and carries the scan report from the `scan` task to the `upload` task as task output. Scan identity (project, scan id, IP) lives in run metadata, built by `falcoria_contracts.scan_names.scan_run_metadata`.

## Entrypoints

| Process | Command | What it serves |
|---|---|---|
| scanledger API | `uvicorn falcoria_scanledger.main:app` | REST under `/api` (`/admin`, `/projects`, `/projects/{id}/ips`, `/history`, `/events`) and `GET /health`. The schema comes from Alembic: run `alembic upgrade head` first; the app never issues DDL. |
| scanledger CLI | `python -m falcoria_scanledger.port_prevalence.sync` | Loads the port frequency table from the vendored `nmap-services` file into `port_prevalence`. |
| tasker API | `uvicorn falcoria_tasker.main:app` | `/api/projects/{project_id}/scans` (start, list, status, cancel), `/api/workers`, `GET /health`. |
| scanner | `falcoria-scanner` (`falcoria_worker.main:scanner`) | Hatchet worker, `slots=1`, label `role=scanner`, named `<hostname>_<external ip>`. |
| uploader | `falcoria-uploader` (`falcoria_worker.main:uploader`) | Hatchet worker, `slots=10`, label `role=uploader`. |

Both APIs are built by a `create_app()` factory in `main.py`. In `main.py`, scanledger's `lifespan` seeds the service accounts through `auth.service.ensure_primary_users`, and tasker's `lifespan` calls `connect_hatchet()` and `init_dns_resolver()`.

## Runtime flows

### Start a scan (HTTP path)

```
POST /api/projects/{project_id}/scans
  -> security.require_project_access -> ScanledgerClient.check_access   (cached 45 s)
  -> scans.router.run_scan -> scans.service.run_scan
       -> _prepare_targets
            -> targets.partition_targets   (public IPs only, CIDR expansion, dedup)
            -> resolve.resolve_targets     (DNS, bounded by dns_resolve_semaphore_limit)
       -> [mode == INSERT only]
            -> _dedupe_insert_mode         (scanledger.search_ips + runs.active_runs)
            -> _merge_known_hostnames      (new hostnames of skipped, known IPs -> scanledger)
       -> _build_tasks                     (one ScanTask per IP and port shard, shuffled)
       -> runs.start_scan_tasks            (one bulk Hatchet call, run metadata attached)
  <- RunScanResponse(scan_id, summary, not_scanned)
```

`scan_id` is `None` when every target was skipped. `shard_ports` splits the port list; the shard count is forced to 1 in INSERT mode (`_shard_count`).

### One run (worker path)

```
Hatchet queue
  -> scan task    (worker label role=scanner, retries=1)
       -> scan.scan_ip
            -> nmap.args.build_open_ports_args / build_service_args
            -> nmap.scanner.run_nmap_scan
                 -> _run_nmap_pass            (nmap ... -oX <tmp file>)
                 -> [service pass, only when service_opts is set and ports are open]
                 -> xml.enrich_xml            (merge passes, attach hostnames)
       <- ScanReport(xml)                     (task output, stored by Hatchet)
  -> upload task  (worker label role=uploader, retries=3, parents=[scan])
       -> scan.upload_report -> ScanledgerClient.upload_report
            -> POST /api/projects/{id}/ips/import
                 -> ips.router.import_scan -> ips.service.import_scan -> apply_import
                      -> _load (SELECT ... FOR UPDATE) -> dedup_batch -> modes.apply_mode
                      -> _create / _update, _write_history
                      -> events.service.write_events   (outbox rows, same transaction)
                      <- commit by database.get_session
```

The workflow is declared once in `falcoria_worker.workflow.build_workflow`; both worker entry points register it, and the `role` label decides which process runs which task.

### Status and cancel

`GET .../scans/{scan_id}` calls `runs.count_by_status` (one list request per status, workflow-level rows, filtered on the `project_scan` metadata key) and `runs.running_targets` (task-level `RUNNING` rows per active scanner worker). State is `running` if anything is queued or running, else `cancelled`, `failed` or `completed`. Cancel is one bulk cancel by metadata filter over `QUEUED` and `RUNNING` runs.

### Event feed (consumer path)

```
GET /api/projects/{project_id}/events?after=<txid>.<id>&limit=N
  -> events.router.read_events -> events.service.read_events
       rows after the cursor, ordered by (txid, id), only rows whose transaction has finished
  <- EventPage(items, next_cursor)
```

Delivery is at least once. A consumer stores `next_cursor` after processing a page and deduplicates on `event_id`.

## Notes on intent versus code

- `docs/adr/0001-hatchet-run-model.md` records why there is no parent task and why the workflow has two tasks routed by worker label.
- `.env.prod.example` mentions `./scripts/generate-env.sh`; no `scripts/` directory exists in the repository. [TODO] port or remove the reference.
- Dockerfiles and CI workflows are on branch `packaging`, not on `main`.
