# AGENTS.md

Rules for agents working in `asm/`. The root `AGENTS.md` holds the rules shared with
`falcoria/` (isolation, git, secrets, Hatchet). Code style, docstring and test conventions
follow `falcoria/AGENTS.md` (sections "Code style", "Docstrings", "Tests"); Ruff and pyright
config in `asm/pyproject.toml` enforce most of it.

## Overview

**asm-core** reacts to new open ports in falcoria's scanledger. For each new HTTP port it runs
a Hatchet chain: an httpx probe, then a nuclei scan. It stores the current state of each
result in its own Postgres database. It has no history tables.

Flow:

```
scanledger event feed -> bridge (poller, cursor and "seen" table in the asm database)
  -> httpx-then-nuclei (plain task, waits only for httpx)
       httpx-scan -> save httpx result (every target, HTTP or not)
       if HTTP: start nuclei-scan without waiting
  -> nuclei-scan workflow: scan (batch task) -> persist -> persist-nuclei-findings
```

## Project structure

```
packages/asm-contracts/    import asm_contracts     pydantic models and Hatchet task names
packages/asm-execution/    import asm_execution     OsCommandRunner: subprocess, timeout, process-group kill
packages/asm-logging/      import asm_logging       configure_logging
apps/httpx-worker/         import asm_httpx_worker  task httpx-scan
apps/nuclei-worker/        import asm_nuclei_worker workflow nuclei-scan (batch scan step + persist step)
apps/asm-core/             import asm_core          worker, bridge, FastAPI API, database
```

- src-layout for every member: code lives in `<member>/src/<import_name>/`.
- Dist names are hyphenated, `asm-` prefixed; import names are underscored, `asm_` prefixed.
- Cross-member deps go through `[tool.uv.sources] <name> = { workspace = true }`.
- The scanledger event-feed models in `asm-core` are a copy. Do not import `falcoria_*`.

## Commands

`uv` only — never bare `pip`. Run from the `asm/` directory.

| Task | Command |
|---|---|
| Sync the workspace | `uv sync` |
| Format | `uv run ruff format .` |
| Lint (autofix) | `uv run ruff check . --fix` |
| Type-check | `uv run pyright` |
| Test — no database or Hatchet | `uv run pytest -m "not postgres and not hatchet"` |
| Test — Postgres | `uv run pytest -m postgres` (needs `ASM_CORE_DB_*`; the suite recreates `asm_core_test`) |

## Configuration

Environment variables: `HATCHET_CLIENT_TOKEN`, `HATCHET_CLIENT_TLS_STRATEGY`,
`ASM_CORE_DB_{HOST,PORT,USER,PASSWORD,NAME}`, `SCANLEDGER_API_URL`, `SCANLEDGER_ASM_TOKEN`,
`ASM_CORE_CHAIN_NUCLEI_PARAMS` (JSON `NucleiScanParams`; default is all templates at 150
requests per second), `NUCLEI_PATH`.

Tests set a placeholder Hatchet JWT in `apps/asm-core/tests/conftest.py`, because the SDK
parses the token when `Hatchet()` is created at import.

## Boundaries

**✅ always**
- Run the verification block below before calling a task done.
- New behaviour ships with tests.
- A nuclei batch never raises: every target gets a `NucleiScanResult` with status `success`
  or `error`.

**⚠️ ask first**
- Adding a dependency, a new `packages/*` member, or changing which packages an app uses.
- Changing an `asm-contracts` type: every app imports it.
- Adding, removing or renaming a Hatchet task or workflow (`httpx-scan`,
  `httpx-scan-and-store`, `nuclei-scan`, `httpx-then-nuclei`, `persist-nuclei-findings`).
- A database schema change. The schema is created by `create_all` at startup for now.
- Changing the HTTP API (`/projects/{id}/scans/...`, `/projects/{id}/results/...`).
  It has no authentication, status or cancel by decision; do not add them unasked.
- Changing the nuclei batch size or interval. The current values are placeholders.

**🚫 never**
- Run nuclei with the default full template set against hosts you do not own. Use light
  templates and a low rate limit, for example
  `{"templates":["/opt/nuclei-templates/http/technologies"],"protocol_types":["http"],"rate_limit":20}`.
- Commit secrets or real scan data.
- Suppress a checker without a specific rule code and a one-line reason.
- Delete or weaken a failing test without explicit authorization.

## Verification

Run before a task is complete — all four must pass:

```
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest -m "not postgres and not hatchet"
```

Run `uv run pytest -m postgres` too when a change touches `db/` or `persistence/`.

## Documentation

`docs/hatchet-batch-timing.md` records measured behaviour of Hatchet batch tasks that
shaped the nuclei worker (group timers, slot behaviour). It was measured on engine 0.107.2
and partly re-checked on 0.110.5. Recheck before relying on it for a new engine version.
