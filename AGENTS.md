# AGENTS.md

Rules shared by every system in this repo. `CLAUDE.md` imports this file. Each system has its
own `AGENTS.md` with area rules; the file nearest the edited file wins.

## Overview

A network-scanning platform on one self-hosted Hatchet engine, made of two systems:

| Directory | System | Role |
|---|---|---|
| `falcoria/` | falcoria | Port scanning with nmap. `scanledger` stores results and serves an event feed; `tasker` starts and tracks scans; `worker` runs nmap and uploads reports. |
| `asm/` | asm-core | Reads the scanledger event feed, probes new HTTP ports with httpx, scans them with nuclei, stores findings in its own database. |
| `deploy/` | deployment | Compose files and environment templates for both systems; see `deploy/README.md`. Test stack only so far. |
| `docs/` | shared docs | Documentation that covers both systems. Per-system docs live in `falcoria/docs/` and `asm/docs/`. |

## Isolation between systems

- Each system is its own `uv` workspace with its own `pyproject.toml` and `uv.lock`. Run `uv`
  from inside `falcoria/` or `asm/`, never from the repo root.
- No system imports code from the other. `asm` talks to falcoria only through the scanledger
  HTTP event feed. `asm` keeps its own copy of the event-feed models on purpose.
- Each system has its own database, database role, Docker images, CI workflow and
  environment-variable prefix (`SCANLEDGER_*`, `TASKER_*`, `WORKER_*` for falcoria; `ASM_CORE_*`
  for asm). Only the Hatchet engine is shared.
- CI runs per system by path: a change in `falcoria/**` does not run `asm` jobs, and the
  reverse. A change under `.github/workflows/` runs its own system's jobs only.
- Releases are per system. A tag `falcoria-vX.Y.Z` publishes the falcoria images, a tag
  `asm-vX.Y.Z` publishes the asm images. Each system has its own version numbers.
- Moving code into a shared top-level package needs an explicit decision. Ask first.

## Git workflow

- Branch before committing on `main`.
- Never rebase, squash, amend or force-push commits that are already pushed.
- Commit message: subject line only, imperative mood. No attribution trailers.
- Never commit secrets, credentials, or real scan data (IPs, hostnames, emails, machine
  paths). Use the documentation IP ranges `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`
  and `example.com` names in fixtures.
- Before the first push of a new directory, search it for public IPv4 addresses, `/home/`
  paths, personal names and email addresses, and token-like strings.

## Hatchet

- The Hatchet docs (`https://docs.hatchet.run/llms.txt`) are the source of truth. If they are
  silent or contradict each other on something that matters, verify with a real run against
  the local test engine and record the finding.
- Hatchet task and workflow names are the contract between a system's services. Adding,
  removing or renaming one needs explicit approval.

## Where to look

- Falcoria: `falcoria/AGENTS.md`, `falcoria/docs/MAP.md`.
- asm: `asm/AGENTS.md`, `asm/docs/`.
