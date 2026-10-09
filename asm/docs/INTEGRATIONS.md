# Integrations

| Dependency | How asm talks to it | Configured in | If unavailable |
|---|---|---|---|
| Hatchet engine | `hatchet-sdk` (gRPC). Each of `asm_core/tasks.py`, `asm_nuclei_worker/tasks.py`, `asm_httpx_worker/tasks.py` builds a `Hatchet()` client at import. | `HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_TLS_STRATEGY` | Workers cannot start; the bridge and API cannot start runs. Nothing queues on the asm side. |
| Postgres | SQLAlchemy async engine over asyncpg, built in `db/database.py`. Separate database from scanledger's. | `ASM_CORE_DB_{HOST,PORT,USER,PASSWORD,NAME}` | The worker, API and bridge fail at start (`create_db_and_tables`). While running, `persist-nuclei-findings` retries twice, API calls return errors, and a bridge poll fails and is retried after 5 s. |
| scanledger HTTP API | `httpx.AsyncClient` in `scanledger_bridge/poller.py`: `GET /projects` and `GET /projects/{id}/events?after=<cursor>`, Bearer token. | `SCANLEDGER_API_URL`, `SCANLEDGER_ASM_TOKEN` | No new launches. Events stay in scanledger's feed; the stored cursor resumes where it stopped. |
| scanledger access check | `httpx.AsyncClient` in `api/scanledger_access.py`: `GET /projects/{id}` with the caller's own Bearer token, called by `api/security.py` for every API request. | `SCANLEDGER_API_URL` | API requests fail with 503 (the check fails closed). The bridge and the workers are not affected. |
| nuclei binary and templates | `OsCommandRunner` starts the binary at `NUCLEI_PATH` (default `nuclei`). The nuclei worker image installs a pinned release and a pinned template archive (`apps/nuclei-worker/Dockerfile`, amd64 only). | `NUCLEI_PATH` | Every batch returns `ERROR` for all its targets. |
| Scan targets | The httpx worker and nuclei connect straight to the target IP or hostname from the worker's machine. | Worker placement | The target shows `UNREACHABLE`, `TIMEOUT` or a request failure in the httpx attempts. |

The Hatchet engine version is not set in this directory. `docs/hatchet-batch-timing.md` records the versions its measurements ran on.
