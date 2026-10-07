# Documentation map

Generated against commit `6a6dc4c77b079a75ef6da5096930d97fe223de52` on branch `packaging`. The working tree also holds uncommitted additions made after that commit: `apps/tasker/Dockerfile`, `apps/worker/Dockerfile`, `.github/workflows/ci.yml` and `.github/workflows/docker-publish.yml`.

Falcoria is a uv workspace monorepo: three apps (`scanledger`, `tasker`, `worker`) and three shared packages. The stack is read from the root `pyproject.toml` and each member's `pyproject.toml`; no separate stack file exists.

| File | Holds | Open it when |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | What the three processes own, the entrypoint table, runtime flows for starting a scan, one run, status and cancel, and the event feed. | You need to know which process does what, or trace a request. |
| [STRUCTURE.md](STRUCTURE.md) | Root tree, directory purposes, a small tree per app. | You need to know what lives where. |
| [NAVIGATION.md](NAVIGATION.md) | Symbol index past the entrypoints, task routing, change-impact notes. | You know the task and need the file to open first. |
| [INVARIANTS.md](INVARIANTS.md) | Hatchet name contracts, scanner limits, event outbox and import-lock rules. | You change run queries, the workflow, the import path or the feed. |
| [INTEGRATIONS.md](INTEGRATIONS.md) | Hatchet, Postgres, scanledger API, nmap, DNS, settings prefixes. | You configure a deployment or debug an outage. |
| [TESTING.md](TESTING.md) | Test selections, markers, the Postgres test database, environment defaults. | A test needs a database or a new settings field breaks collection. |
| [adr/0001-hatchet-run-model.md](adr/0001-hatchet-run-model.md) | The recorded decision on the Hatchet run model (existing file, not generated). | You question why there is no parent task or why roles are labels. |

Skipped on purpose: `STACK.md` (single language, versions visible in `pyproject.toml`), `GLOSSARY.md` (little jargon beyond Hatchet's `slot`, `label`, `run`, defined where used), `diagrams/` (the one fan-out, a bulk start of runs, reads as the linear flow in ARCHITECTURE.md). Extended per-package trees: written in STRUCTURE.md, because the three apps have independent dependency sets.

## Verification

Commands from `AGENTS.md`:

```
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest -m "not postgres and not hatchet"
```

The last command needs no database. For the full suite and for invariant-specific checks see [TESTING.md](TESTING.md) and [INVARIANTS.md](INVARIANTS.md).

Open items: [TODO] `.env.prod.example` points at `./scripts/generate-env.sh`, which is not in the repository. [ASK USER] how scan servers reach the Hatchet engine in production is not recorded in the repository.
