# Documentation map

Generated against commit `623c31a1bf98731dc1e5e880839393f8d5ed5272` on branch `monorepo`.

asm-core is a uv workspace of three apps (`asm-core`, `httpx-worker`, `nuclei-worker`) and three shared packages (`asm-contracts`, `asm-execution`, `asm-logging`). It turns new open ports from falcoria's scanledger into httpx probes and nuclei scans on Hatchet, and stores the current result of each in its own Postgres database. Stack and dependency versions: `pyproject.toml` (workspace) and each member's `pyproject.toml`; the nuclei release and template versions: `apps/nuclei-worker/Dockerfile`.

| File | Holds | Open it when |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Entrypoints, REST routes, Hatchet tasks, runtime flows. | You need to know which process runs what, or trace one target end to end. |
| [STRUCTURE.md](STRUCTURE.md) | Directory ownership and a two-level tree. | You need to know what lives where. |
| [NAVIGATION.md](NAVIGATION.md) | Symbol index, task routing, change impact. | You know the task and need the file or function to start from. |
| [INVARIANTS.md](INVARIANTS.md) | Rules that break at runtime without failing lint or types. | Before changing batching, persistence, the bridge or the contracts. |
| [INTEGRATIONS.md](INTEGRATIONS.md) | Hatchet, Postgres, scanledger, nuclei, scan targets. | You configure or debug a connection. |
| [TESTING.md](TESTING.md) | Markers, database fixture, placeholder Hatchet token, local servers. | A test fails to start or you add a database test. |
| [hatchet-batch-timing.md](hatchet-batch-timing.md) | Measured timing of Hatchet batch tasks with one slot. | You change `NUCLEI_BATCH_SIZE`, `NUCLEI_BATCH_INTERVAL` or the worker's slots. |

Not written: `STACK.md` (versions are readable from the manifests and the Dockerfile), `GLOSSARY.md` (no heavy jargon), `diagrams/` (the flows in `ARCHITECTURE.md` stay linear). Extended per-package trees skipped: six workspace members, no deep nesting.

## Verification

Run from `asm/`; the same commands run in `.github/workflows/asm-ci.yml`:

```
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest -m "not postgres and not hatchet"
```

Database tests: `uv run pytest -m postgres`, see [TESTING.md](TESTING.md).
