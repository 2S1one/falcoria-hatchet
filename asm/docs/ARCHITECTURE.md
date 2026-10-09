# Architecture

asm-core reads falcoria's scanledger event feed, probes each new TCP port with httpx, and scans ports that answer HTTP with nuclei. It accepts scanledger events (polled over HTTP) and manual launch requests (REST). It produces two tables in its own Postgres database: `httpx_results_current` and `nuclei_findings_current`, both current state without history. Hatchet runs every step. asm-core owns its database; scanledger owns the scan data it reads from.

## Entrypoints

| Entrypoint | Invoked as | Role |
|---|---|---|
| `asm_core.main:main` | `python -m asm_core.main` | Hatchet worker `asm-core-worker`, 500 slots. Registers `httpx-then-nuclei`, `httpx-scan-and-store`, `persist-nuclei-findings`. Creates the tables on start. |
| `asm_core.bridge_main:main` | `python -m asm_core.bridge_main` | Polls scanledger and starts `httpx-then-nuclei` runs. Not a Hatchet worker. |
| `asm_core.app:fastapi_app` | `uvicorn asm_core.app:fastapi_app` | REST API: launch scans, read results. |
| `asm_httpx_worker.main:main` | `python -m asm_httpx_worker.main` | Hatchet worker `httpx-worker`. Registers `httpx-scan`. |
| `asm_nuclei_worker.main:main` | `python -m asm_nuclei_worker.main` | Hatchet worker `nuclei-worker`, 1 slot. Registers the `nuclei-scan` workflow. |

REST routes (prefix `/projects/{project_id}`; every route needs the Bearer token of a user who is a member of that project in scanledger):

| Route | Handler | Effect |
|---|---|---|
| `POST /scans/nuclei` | `api/nuclei/router.py#launch_nuclei` | Returns 202 and a new `scan_id`; starts one `nuclei-scan` run per target. |
| `GET /results/nuclei` | `api/nuclei/router.py#read_nuclei_results` | Lists the project's rows of `nuclei_findings_current`. |
| `POST /scans/httpx` | `api/httpx/router.py#launch_httpx` | Returns 202 and a new `scan_id`; starts one `httpx-scan-and-store` run per target. |
| `GET /results/httpx` | `api/httpx/router.py#read_httpx_results` | Lists the project's rows of `httpx_results_current`. |

Access check: `api/security.py#require_project_access` is a router-level dependency. It relays the caller's token to scanledger's `GET /projects/{id}` (`api/scanledger_access.py`) and maps 401, 403 and 404 through unchanged. Results are cached for 45 seconds per token and project. If scanledger does not answer, the request fails with 503.

## Hatchet tasks

Names live in `packages/asm-contracts/src/asm_contracts/task_names.py`. They are the contract between workers.

| Name | Defined in | Runs on | Options |
|---|---|---|---|
| `httpx-then-nuclei` | `asm_core/tasks.py#httpx_then_nuclei` | asm-core worker | execution timeout 10 min, schedule timeout 1 day |
| `httpx-scan-and-store` | `asm_core/tasks.py#httpx_scan_and_store` | asm-core worker | same timeouts |
| `persist-nuclei-findings` | `asm_core/tasks.py#persist_nuclei_findings` | asm-core worker | 2 retries, execution timeout 2 min |
| `httpx-scan` | `asm_httpx_worker/tasks.py#httpx_scan` | httpx worker | 1 retry, execution timeout 120 s |
| `nuclei-scan` (workflow) | `asm_nuclei_worker/tasks.py#nuclei_scan` | nuclei worker | steps `scan` (batch task) and `persist` |

asm-core and the nuclei worker call tasks of other workers through `hatchet.stubs.task` and `hatchet.stubs.workflow`, which carry only the name and the pydantic models.

## Flow: scanledger event to stored result

```
bridge_main._run
 -> poller.run_poller(start_chain)               every 5 s
      -> _list_project_ids                       GET /projects
      -> _drain_project                          GET /projects/{id}/events?after=<cursor>
           -> adapter.handle_event               skipped when event.scan_id is None
                -> _derive_targets               rules A, B, C
                -> _mark_seen                    insert ... on conflict do nothing
                     new row -> tasks.start_chain -> httpx-then-nuclei (not awaited)
           -> _save_cursor                       after each page

httpx-then-nuclei (asm-core worker)
 -> chain.run_chain
      -> httpx-scan (httpx worker)               probe.probe: https first, http only after a TLS failure
      -> _save_httpx                             persistence/httpx.py#save_httpx_result, every target
      -> not is_http: ChainOutcome NOT_HTTP, stop
      -> _start_nuclei                           nuclei-scan.aio_run(wait_for_result=False)
                                                 host = hostname, else ip; same port

nuclei-scan (nuclei worker)
 -> scan (batch_task)                            group key input.batch_key, 25 targets or 30 s
      -> batch.run_batch -> scan.scan_batch      one nuclei process per batch, via OsCommandRunner
 -> persist                                      calls persist-nuclei-findings (asm-core worker)
      -> persistence/nuclei.py#reconcile_target_findings
```

Branch points:
- The three rules in `_derive_targets`: A, an added TCP port on every current hostname (or the bare IP); B, an added hostname on every current TCP port; C, a service change on a TCP port, on every current hostname.
- `persist_nuclei_findings` stores nothing when the nuclei result has status `ERROR`.

## Flow: manual launch through the API

```
POST /projects/{id}/scans/nuclei
 -> launch_nuclei            one scan_id for all targets
      -> tasks.start_nuclei_scans   nuclei-scan.aio_run_many, chunks of 250, not awaited
         -> same nuclei-scan flow as above

POST /projects/{id}/scans/httpx
 -> launch_httpx
      -> tasks.start_httpx_scans    httpx-scan-and-store.aio_run_many, chunks of 250
         -> chain.run_httpx_store -> httpx-scan -> save_httpx_result
```
