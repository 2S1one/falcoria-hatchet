# Integrations

| Dependency | Used by | How | Configured in | If unavailable |
|---|---|---|---|---|
| Hatchet engine (self-hosted) | tasker, scanner, uploader | gRPC for workers and bulk run start; REST for run and worker listings (`hatchet_sdk` client) | `TASKER_HATCHET_*`, `WORKER_HATCHET_*` (`token`, `host_port`, `tls_strategy`) via `hatchet/client.py` and `hatchet_client.py#build_hatchet` | tasker cannot start scans or report status; workers stop receiving tasks. A broken REST proxy returns 502 to tasker's run listings while gRPC still works. |
| PostgreSQL | scanledger only | asyncpg through SQLModel; one database | `SCANLEDGER_DB_*` (`host`, `port`, `user`, `password`, `name`) read by `config.get_db_settings`; engine in `database.py` | scanledger returns errors; tasker's access check fails closed with 503 (`ServiceUnavailable`). |
| scanledger HTTP API | tasker, uploader | tasker: access check, IP search, hostname merge. Uploader: report import | `TASKER_SCANLEDGER_BASE_URL`, `TASKER_SCANLEDGER_TOKEN`; `WORKER_SCANLEDGER_BASE_URL`, `WORKER_SCANLEDGER_TOKEN`, `WORKER_SCANLEDGER_TLS_VERIFY` | tasker rejects requests (access check) and cannot dedup in INSERT mode; the `upload` task retries 3 times with backoff, then the run fails and the report stays only as `scan` task output in Hatchet. |
| nmap binary | scanner | subprocess, two passes, XML output | `WORKER_NMAP_PATH`, `WORKER_COMMAND_GRACE_PERIOD_SECONDS` | the `scan` task fails and retries once. |
| DNS | tasker | `aiodns` resolver created in the lifespan | `TASKER_DNS_RESOLVE_SEMAPHORE_LIMIT` | hostnames land in `not_scanned.unresolvable_hosts`. |
| `api.ipify.org` | scanner at startup | one HTTP GET to name the worker `<hostname>_<external ip>` | `main._EXTERNAL_IP_URL` | the worker name uses `unknown`. |
| Event consumers (outside this repository) | scanledger feed | `GET /api/projects/{id}/events`, bearer token of a seeded account | `SCANLEDGER_ASM_TOKEN` seeds the `asm` account | the feed keeps accumulating; consumers resume from their cursor. |

Other settings prefixes: `SCANLEDGER_` (`ADMIN_TOKEN`, `TASKER_TOKEN`, `WORKER_TOKEN`, `ASM_TOKEN`, `MAX_REPORT_BYTES`, `LOG_LEVEL`, `ENV`, `DEBUG`, `API_PREFIX`), `TASKER_` (`ENV`, `DEBUG`, `API_PREFIX`, `LOG_LEVEL`) and `WORKER_` (`ENV`, `DEBUG`, `LOG_LEVEL`). In `prod` environment the docs endpoints of both APIs are hidden (`Env.PROD`).

`.env.prod.example` lists the production variable names with placeholder values.
