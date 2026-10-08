# AGENTS.md

Rules for agents working in `falcoria/`. The root `AGENTS.md` holds the rules shared with
`asm/`. Nested `AGENTS.md` files (one per workspace member) add area-specific rules — the
file nearest the edited file wins.

## Overview

**falcoria** is a network-scanning platform: a uv-workspace monorepo of a system-of-record
service (`scanledger`), an API server + Hatchet client (`tasker`), nmap job runners
(`worker`), and three shared library packages (`falcoria-contracts`, `falcoria-http`,
`falcoria-logging`).

## Principles

1. **Think before coding.** State assumptions. Surface confusion and trade-offs; don't hide them.
2. **Simplicity first.** Minimum code that solves the problem. Nothing speculative, no
   unrequested features or abstractions.
3. **Surgical changes.** Touch only what the request needs. Match existing style. Remove only
   code orphaned by your own change.
4. **Goal-driven.** Define a verifiable success criterion before starting; check it at the end.
5. **DRY.** No duplication across logic, config, types or tests — reuse the shared packages.
6. **Focused files.** Split a file past ~300 lines. Purposeful, general filenames.
7. **Be brief and exact.** Short answers, plain language, no filler. Ask when unclear.

## Hatchet

- **Docs are the source of truth.** Any Hatchet-specific question (SDK API, task options,
  retries, events, filters, limits) is answered from the docs at
  `https://docs.hatchet.run/llms.txt`. Never from memory.
- **If the docs are silent, unclear or contradict each other** on something that matters
  (cancellation, retries, run filtering, concurrency, durability), verify with a real run
  against the local Hatchet test engine (its `docker-compose.yml`) and record the finding.
- Record a significant Hatchet design choice as an ADR (`architecture-decision-records` skill).

## Commands

`uv` only — never bare `pip`.

| Task | Command |
|---|---|
| Sync the whole workspace | `uv sync` |
| Sync one member's deps | `uv sync --package falcoria-scanledger` |
| Add a runtime dep to a member | `uv add --package falcoria-scanledger <pkg>` |
| Add a workspace-wide dev tool | `uv add --group dev <pkg>` |
| Format | `uv run ruff format .` |
| Lint (autofix) | `uv run ruff check . --fix` |
| Type-check | `uv run pyright` |
| Test — all | `uv run pytest` |
| Test — fast (no Postgres/Hatchet) | `uv run pytest -m "not postgres and not hatchet"` |
| Test — one node | `uv run pytest apps/scanledger/tests/test_foo.py::test_bar` |

Run `uv` from the `falcoria/` directory — from inside a member directory `uv add` / `uv sync`
target that member, not the workspace.

## Project structure

```
packages/falcoria-contracts/   import falcoria_contracts     pydantic + stdlib only; pyright strict
packages/falcoria-http/        import falcoria_http          httpx-based retrying transport for service calls
packages/falcoria-logging/     import falcoria_logging       stdlib-only process-wide logging config
apps/scanledger/               import falcoria_scanledger    FastAPI + SQLModel + asyncpg + alembic
apps/tasker/                   import falcoria_tasker        API server + Hatchet client (one instance)
apps/worker/                   import falcoria_worker        nmap job runner (N instances)
```

- src-layout for every member: code lives in `<member>/src/<import_name>/`.
- Dist names are hyphenated, `falcoria-` prefixed (`falcoria-scanledger`); import names are
  underscored, `falcoria_` prefixed (`falcoria_scanledger`).
- Cross-member deps go through `[tool.uv.sources] <name> = { workspace = true }`.

## Code style

Ruff, the Ruff formatter and pyright own formatting, lint, import order and typing — config
is in the root `pyproject.toml`. **Do not restate their rules as prose.** What they cannot
enforce:

- Type hints on all public code; concrete types over `Any`; narrow in tests with
  `assert isinstance(...)`, not `# type: ignore`.
- All imports at file top — inline imports hide dependencies.
- Catch specific exceptions; no bare `except Exception` outside a top-level handler;
  `logger.exception()` inside an `except`; keep `try` blocks small.
- Text I/O always `encoding="utf-8"`.
- Logging: `falcoria_logging.configure_logging` once at process entry, never
  `logging.basicConfig()`. Loggers via `logging.getLogger(__name__)`.
- Don't silence a checker (`# noqa` / `# type: ignore` / `# pragma: no cover`) to get the
  gate green — fix the cause. A suppression is allowed only when genuinely unavoidable, and
  only with a specific rule code plus a one-line reason.
- Model transformations via `model_dump()` / `model_validate()` — don't hand-list fields.
  `TargetModel(**source.model_dump(), field=override)` is the base pattern (pydantic v2
  drops unknown keys, so `include=` is never needed and is banned — it re-introduces a
  hidden hardcode). `model_dump(exclude={"x"})` only when a name means different things in
  source and target; `model_dump(mode="json")` when enums must serialise to `str` for the
  DB layer. An explicit field is acceptable only when the names differ (`number` → `port`).

### Docstrings

Ruff `D` (google convention) enforces presence on the public surface (`D101/102/103`);
private names, `tests/` and `migrations/` are exempt. What the tool cannot check:

- **Summary:** one physical line (≤ ~80 chars), capitalised, ending with a period.
  Descriptive voice — "Returns …", "Reconciles …" — not "Return", not "This function …".
- **Sections** (`Args:` / `Returns:` / `Raises:` / `Yields:`) only when they add what the
  signature and type annotations do not already say. Under the google convention `Args:`
  is all-or-nothing per function — document every parameter or none.
- **Body paragraph** only for the non-obvious: side effects, commit / transaction
  behaviour, invariants, units, what `None` / an empty result means, a precondition on the
  inputs, and — for a pure function — the rule it implements and what it deliberately does
  *not* do.
- **Narration test:** delete any line that re-describes the code step by step; that is a
  `# why` comment's job, and only for the *why*.
- **Pydantic schemas:** one line on the class (what the payload is, where it is used);
  document fields with `Field(description=...)`, not an `Attributes:` block. A `Settings`
  class *may* use `Attributes:` — the env-var names have no other home.
- **FastAPI handlers:** the docstring is the OpenAPI description — keep it client-facing.
  The error contract goes in `responses=` / `status_code`, never a `Raises:` block. Do not
  also pass `description=` (it overrides the docstring).
- **Custom exception classes:** one line stating *when* it is raised.
- **Scanner-neutral:** prose in docstrings, comments and `Field(description=...)` says
  "the scan" / "the scanner reported", never "nmap" — other scanners (masscan, …) are
  planned. Field *names* may still mirror the scanner-flavoured contract (`servicefp`).
- **No cross-references:** never point a docstring at another doc or spec file
  ("see …", "per the … spec"). State the rule inline in a few words, or leave it out.
- **Never:** restate the name; repeat an annotated type; open with "This function …" /
  "A helper that …"; put change history, TODO or author tags in a docstring.

## Git workflow

- Branch before committing on `main`.
- Never rebase, squash, amend or force-push commits that are already pushed.
- Commit message: subject line only, imperative mood. No attribution trailers — never add
  `Co-Authored-By` or a session/assistant id.
- Never commit secrets, credentials, or real scan data (IPs, hostnames, emails). Redact
  them from logs and test fixtures.

## Boundaries

**✅ always**
- Run the verification block below before calling a task done.
- New behaviour ships with tests.
- `uv add`, never `pip`. `encoding="utf-8"` on file I/O.

**⚠️ ask first**
- Adding a dependency. A new `packages/*` member, or a change to which packages an
  `apps/*` member depends on.
- Changing a `falcoria-contracts` type — it is imported by every service, so a change here
  is a contract change.
- Adding, removing or renaming a Hatchet task or workflow — names are the contract between
  `tasker` and `worker`.
- A DB schema or Alembic migration change.
- Anything outward-facing: an API contract, a published event, a CLI flag.

**🚫 never**
- Commit secrets or real scan data.
- Suppress a checker without a specific code and a one-line reason (see Code style).
- Delete or weaken a failing test without explicit authorization.
- Hand-edit generated Alembic revisions under `**/migrations/versions/`.

## Verification

Run verbatim before a task is complete — all four must pass:

```
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

## Containers

`compose.yml` in this directory describes the falcoria services under the profile `falcoria`:
`scanledger-migrate` (one-off migrations), `scanledger`, `tasker`, `scanner`, `uploader`. The
Dockerfiles are in `apps/*/Dockerfile`; build from this directory.

- The file does not run alone. It refers to `postgres`, `hatchet-engine` and `hatchet-dashboard`
  from `deploy/compose.infra.yml`. Start it through
  `deploy/compose.test.yml --profile falcoria`; see `deploy/README.md`.
- A new app: add its Dockerfile, its service here with the profile `falcoria`, its entry in the
  filter and the matrix of `.github/workflows/falcoria-ci.yml` and `falcoria-publish.yml`.
  `docs/CONTAINERS.md` (repo root) has the steps.
- Ask first: renaming a service, changing a profile, or changing an environment variable that
  `deploy/.env.example` documents. Other services and the asm system read these names.

## Documentation

`docs/` is a generated navigation map for agents (and humans): one master index
(`docs/MAP.md`) plus focused files. It is produced by the `project-doc-map` skill, committed
at `.claude/skills/project-doc-map/`.

After changes that touch source code — not docs-only, not pure formatting — run
`/project-doc-map` before calling a task done. It updates only the affected files and never
writes outside `docs/`.

Architecture decisions go to `docs/adr/` via the `architecture-decision-records` skill.

## Tests

- `pytest`; plain `test_*` functions, no `Test*` classes; mirror the source tree under
  `<member>/tests/`. Import mode is `importlib` (set in `pyproject.toml`).
- Async tests use `anyio`: put `pytestmark = pytest.mark.anyio` at the top of the file; the
  `anyio_backend` fixture in the root `conftest.py` pins the backend to asyncio.

## Working convention

While `tasker` is being written, every non-test file goes one at a time:

**show the file's planned content → explain what it does and why → wait for an explicit
"yes" to that specific file → write it → next file.**

- Never describe more than one file in the same message.
- Approval must be unambiguous and about that specific file.
- Test files are exempt — write and update them without waiting for approval.
- Work outside `tasker` is exempt unless the user says otherwise.
