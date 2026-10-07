# Testing

pytest with `--import-mode=importlib` (set in the root `pyproject.toml`); plain `test_*` functions; async tests use `anyio` with `pytestmark = pytest.mark.anyio` and the `asyncio` backend pinned by the `anyio_backend` fixture in the root `conftest.py`. Tests mirror the source tree under each member's `tests/` directory.

| Selection | Command | Count (at the stamped commit) | Needs |
|---|---|---|---|
| No database, no engine | `uv run pytest -m "not postgres and not hatchet"` | 263 | nothing |
| Database tests | `uv run pytest -m "postgres and not hatchet"` | 159 | Postgres, see below |
| Engine tests | `uv run pytest -m hatchet` | 0 collected | a real Hatchet engine; no test carries this marker yet |

## Environment defaults

The root `conftest.py` sets dummy values with `os.environ.setdefault` for the required settings of all three apps (`SCANLEDGER_*` tokens, `TASKER_SCANLEDGER_*`, `WORKER_SCANLEDGER_*`). A real variable in the environment wins. A new required settings field needs a default there, or test collection fails.

## Postgres

`apps/scanledger/tests/conftest.py` builds the schema once per session: it connects to the maintenance database `scanledger`, drops and recreates `scanledger_test`, and runs `SQLModel.metadata.create_all`. Each test then runs in a transaction that is rolled back at the end. The connecting role must be allowed to create databases.

Connection variables (defaults in parentheses): `SCANLEDGER_DB_USER` (`scanledger`), `SCANLEDGER_DB_PASSWORD` (`scanledger`), `SCANLEDGER_DB_HOST` (`localhost`), `SCANLEDGER_DB_PORT` (`5433`).

- The conftest marks every test that uses the `session` fixture (directly or through `client`) as `postgres` automatically.
- `apps/scanledger/tests/test_database.py` builds the app's own engine from `get_db_settings`, so it also needs `SCANLEDGER_DB_HOST`, `SCANLEDGER_DB_USER`, `SCANLEDGER_DB_PASSWORD` and `SCANLEDGER_DB_NAME` set; without them it fails with a settings validation error.
- A new models module must be imported in the conftest, or `create_all` skips its tables.

A throw-away database for a local run:

```
docker run -d --name falcoria-test-pg -e POSTGRES_USER=scanledger -e POSTGRES_PASSWORD=scanledger \
  -e POSTGRES_DB=scanledger -p 5433:5432 postgres:16
```
