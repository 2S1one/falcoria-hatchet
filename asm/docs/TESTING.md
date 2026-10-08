# Testing

Run from `asm/`. Config is in `pyproject.toml`: `testpaths = ["packages", "apps"]`, import mode `importlib`, strict markers.

| Command | Covers |
|---|---|
| `uv run pytest -m "not postgres and not hatchet"` | Everything that needs no database and no engine (88 tests at the time of writing). |
| `uv run pytest -m postgres` | Tests marked `postgres` (12 at the time of writing). Needs `ASM_CORE_DB_*` in the environment. |

Markers: `postgres` and `hatchet`. No test is marked `hatchet`; the marker is declared for tests against a real engine.

## Database tests

The `session` fixture in `apps/asm-core/tests/conftest.py`:
- skips the test when `ASM_CORE_DB_HOST` is unset;
- overrides `ASM_CORE_DB_NAME` with `asm_core_test`, clears the cached settings, engine and session factory, creates the tables, then `TRUNCATE`s the four tables listed in `_TABLES`;
- needs the database `asm_core_test` to exist and its role to connect. The fixture does not create it; `deploy/postgres-init/01-create-databases.sh` does on a fresh compose stack.

A new table must be added to `_TABLES`, or its rows survive between tests.

## Hatchet token

`asm_core.tasks` builds a `Hatchet()` client when imported, and the SDK parses the token then. `conftest.py` sets a structurally valid placeholder JWT and `HATCHET_CLIENT_TLS_STRATEGY=none` with `os.environ.setdefault`, so a real token in the environment wins. No test contacts an engine.

## Fixtures and helpers

- `apps/httpx-worker/tests/servers.py` starts real local TCP and TLS servers for the probe tests. A TCP-connect timeout cannot be reproduced locally; `test_errors.py` covers that classification with a synthetic exception.
- `apps/httpx-worker/tests/conftest.py#tls_cert` generates a one-day self-signed certificate with the `openssl` command; the tests need `openssl` on the PATH.
- `pythonpath = ["apps/httpx-worker/tests"]` makes `servers.py` importable by name.
- Launch endpoints are tested with a replaced starter: `get_nuclei_starter` and `get_httpx_starter` are FastAPI dependencies.
