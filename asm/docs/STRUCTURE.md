# Structure

| Path | Purpose |
|---|---|
| `apps/asm-core/src/asm_core` | Owns the asm-core worker, the scanledger bridge, the REST API, the database and the storage of results. |
| `apps/httpx-worker/src/asm_httpx_worker` | Owns the httpx probe: pinned-IP HTTP client, error classification, the `httpx-scan` task. |
| `apps/nuclei-worker/src/asm_nuclei_worker` | Owns nuclei command building, batch execution, output parsing and the `nuclei-scan` workflow. |
| `packages/asm-contracts/src/asm_contracts` | Owns the pydantic models and Hatchet task names shared by all apps. |
| `packages/asm-execution/src/asm_execution` | Owns `OsCommandRunner`: subprocess start, timeout, process-group kill. |
| `packages/asm-logging/src/asm_logging` | Owns `configure_logging`. |
| `docs/` | Owns this map and `hatchet-batch-timing.md`, the measurements behind the nuclei batch settings. |

```
asm/
├── apps/
│   ├── asm-core/        src/asm_core, tests, Dockerfile
│   ├── httpx-worker/    src/asm_httpx_worker, tests, Dockerfile
│   └── nuclei-worker/   src/asm_nuclei_worker, tests, Dockerfile
├── packages/
│   ├── asm-contracts/   src/asm_contracts, tests
│   ├── asm-execution/   src/asm_execution, tests
│   └── asm-logging/     src/asm_logging
├── docs/
├── pyproject.toml       workspace root, Ruff, pyright, pytest settings
└── uv.lock
```

Inside `asm_core`:

| Path | Purpose |
|---|---|
| `main.py`, `bridge_main.py`, `app.py` | The three process entrypoints. |
| `tasks.py`, `chain.py` | Hatchet task definitions and the chain logic they call. |
| `config.py`, `constants.py` | Environment settings and fixed timeouts, slots and intervals. |
| `scanledger_bridge/` | Event-feed models, event-to-target rules, polling loop, dedup and cursor tables. |
| `persistence/` | Upserts and reconciliation of httpx and nuclei results. |
| `db/` | Engine, session factory, table creation, result tables. |
| `api/httpx/`, `api/nuclei/` | Router, schemas and read service per scanner. |

Skipped: per-package trees. Six workspace members, no deep nesting.
