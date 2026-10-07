# Structure

```
.
|- apps/
|   |- scanledger/   system of record, FastAPI + SQLModel + Alembic
|   |- tasker/       scan orchestration API, Hatchet client
|   `- worker/       Hatchet workers: scanner (nmap) and uploader
|- packages/
|   |- falcoria-contracts/   shared pydantic models, enums, Hatchet names
|   |- falcoria-http/        retrying httpx transport
|   `- falcoria-logging/     process-wide logging setup
|- docs/                     this documentation and ADRs
|- conftest.py               test environment defaults shared by all members
`- pyproject.toml            uv workspace root; ruff, pyright and pytest settings
```

Each member lives in `src/<import_name>/`. Distribution names are `falcoria-*`; import names are `falcoria_*`.

| Path | Purpose |
|---|---|
| `apps/scanledger/src/falcoria_scanledger` | Owns projects, identities, IP and port state, history, event outbox, port prevalence data. |
| `apps/scanledger/migrations` | Alembic revisions; one revision exists (`8011c58c0251_initial_schema`). |
| `apps/tasker/src/falcoria_tasker` | Owns request validation, target resolution, run start, status and cancel, worker fleet view. |
| `apps/worker/src/falcoria_worker` | Owns the scan workflow definition, nmap execution and the report upload client. |
| `packages/falcoria-contracts` | Owns types shared across process boundaries: scan task, scan options, import modes, workflow and metadata names. |
| `packages/falcoria-http` | Owns `RetryingTransport` for service-to-service httpx calls. |
| `packages/falcoria-logging` | Owns `configure_logging`. |

## scanledger

```
falcoria_scanledger/
|- main.py, config.py, database.py, constants.py, exceptions.py
|- auth/             tokens, identities, bearer-token dependencies, admin endpoints
|- projects/         projects, membership, project-access dependency
|- ips/              import pipeline, import modes, search, facets, nmap XML parsing
|- history/          append-only port-change log and its endpoints
|- events/           outbox table, event schema, feed endpoint
`- port_prevalence/  nmap-services parser and sync command, vendored data file
```

`ips/` owns the import transaction boundary; `events/` owns the outbox and the feed cursor.

## tasker

```
falcoria_tasker/
|- main.py, config.py, constants.py, exceptions.py, security.py
|- scanledger.py     HTTP client for scanledger (access check, IP search, hostname merge)
|- dns.py            shared resolver, created in the app lifespan
|- concurrency.py    bounded_gather
|- scans/            router, service pipeline, target classification, DNS resolution, sharding
|- hatchet/          client lifecycle, run operations, worker listing
`- workers/          fleet-visibility endpoint
```

## worker

```
falcoria_worker/
|- main.py           scanner() and uploader() entry points, worker naming
|- workflow.py       build_workflow: the scan-target workflow and its two tasks
|- scan.py           scan_ip and upload_report step bodies
|- scanledger.py     upload client
|- hatchet_client.py client built from settings
|- config.py, constants.py, exceptions.py
`- nmap/             argument building, subprocess executor, two-pass scan, XML merge
```
