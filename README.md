# falcoria-hatchet

Network-scanning platform on a self-hosted [Hatchet](https://hatchet.run) engine. One
repository, two independent systems.

| Directory | System | What it does |
|---|---|---|
| `falcoria/` | falcoria | Scans networks with nmap, stores open ports in `scanledger`, publishes an event feed of changes. |
| `asm/` | asm-core | Reads that feed; probes new HTTP ports with httpx and scans them with nuclei; stores findings. |

Each system is its own `uv` workspace with its own lockfile, database, Docker images and CI.
Run `uv` from inside `falcoria/` or `asm/`:

```sh
cd falcoria && uv sync && uv run pytest -m "not postgres and not hatchet"
cd asm      && uv sync && uv run pytest -m "not postgres and not hatchet"
```

See `AGENTS.md` for the rules shared by both systems, then `falcoria/AGENTS.md` or
`asm/AGENTS.md`. Deployment files (`deploy/`) are not written yet.
