# Containers: Dockerfiles and Compose files

How the images are built and how Compose starts them. Written for someone who has not used Docker
before. Commands and the stack layout are in `deploy/README.md`.

## Dockerfile: one image

An image is a program packed with everything it needs. A Dockerfile is the recipe. The scanledger
Dockerfile (`falcoria/apps/scanledger/Dockerfile`) has two stages:

```text
builder   start from python:3.12-slim, install uv, install the dependencies and the scanledger code into .venv
runtime   start from a clean python:3.12-slim, copy only the finished .venv, add a user, run uvicorn
```

The tools used to build stay in the first stage, so the final image is smaller.

Two details worth knowing:

- **Dependency layer.** `pyproject.toml` and `uv.lock` are copied and the third-party libraries are
  installed before the source code is copied. While only code changes, Docker reuses the cached
  libraries layer and a rebuild takes seconds.
- **No root.** The process runs as `appuser` (uid 1000).

The start command (`CMD`) runs `uvicorn`. The migration files are in the image, but they are not run
at start. Applying them is its own step: the `scanledger-migrate` service in `falcoria/compose.yml`.

**Build context.** Paths in a Dockerfile (`COPY packages/`, `COPY apps/scanledger/`) are relative to the
system directory, `falcoria/` or `asm/`. Build from there:
`cd falcoria && docker build -f apps/scanledger/Dockerfile .`

How the other images differ:

| Image | Difference |
|---|---|
| `falcoria/apps/worker` | Installs nmap and grants it raw-socket capabilities. Needs `cap_add: [NET_RAW, NET_ADMIN]` at run time and `NMAP_PRIVILEGED=1` (nmap decides about raw sockets by user id, not by file capability). One image, two commands: `falcoria-scanner` and `falcoria-uploader`. |
| `asm/apps/nuclei-worker` | First stage downloads a pinned nuclei release, checks its SHA-256, and downloads a pinned template archive. Versions are `ARG` lines at the top of the file. amd64 only. |
| `asm/apps/asm-core` | One image, three commands: the worker (default `CMD`), the API (`uvicorn`) and the bridge (`python -m asm_core.bridge_main`). Compose overrides `command` for the last two. |
| `tasker`, `httpx-worker` | Same pattern as scanledger. |

## Compose file: which containers run together

A Compose file lists services. One service is one container, started from an image. Two services from
`falcoria/compose.yml`:

```yaml
scanledger-migrate:             # one-off job: apply migrations, then exit
  image: falcoria-scanledger:dev
  build: { context: ., dockerfile: apps/scanledger/Dockerfile }
  command: ["alembic", "-c", "apps/scanledger/alembic.ini", "upgrade", "head"]
  depends_on: { postgres: { condition: service_healthy } }

scanledger:
  image: falcoria-scanledger:dev
  environment: { SCANLEDGER_DB_HOST: postgres, ... }        # settings are passed as variables
  depends_on: { scanledger-migrate: { condition: service_completed_successfully } }
  ports: ["8101:8000"]          # container port 8000 is reachable on the host as 8101
```

The start order is: database healthy, then migrations finished, then the service.

Elements used in these files:

| Element | Meaning |
|---|---|
| `${NAME:-value}` | Take `NAME` from `deploy/.env`; use `value` when it is missing. The stack starts without any setup, and real values replace the defaults. |
| `profiles: [falcoria]` | The service starts only when its profile is selected (`--profile falcoria`). Services without a profile (the infrastructure) always start. |
| `include` | `deploy/compose.test.yml` pulls in `compose.infra.yml` and the two system files. Relative paths in an included file are resolved from that file's own directory, so `context: .` in `asm/compose.yml` means `asm/`. |
| `&name`, `*name`, `<<:` | YAML anchors: a block such as the database settings is written once and reused by several services. |
| `healthcheck` | A command that tells Compose whether the service is ready (`pg_isready` for the databases). `depends_on: service_healthy` needs it. |
| `restart: on-failure` | Restart the container if the process dies. Applications that start before the Hatchet engine accepts connections recover this way. |
| `volumes` | Persistent storage. The databases live in named volumes, so data survives re-creating a container. `down -v` deletes the volumes and with them all data. |
| `cap_add` | Extra Linux capabilities for one container; the nmap scanner uses it. |

## Rules that save time

- **Names inside, ports outside.** Containers reach each other by service name: `postgres`,
  `hatchet-engine`, `scanledger`. From the host, use the published ports (`localhost:8101`).
  Inside a container, `localhost` is the container itself.
- **`.env` location.** Compose reads `.env` from the directory of the main Compose file
  (`deploy/`), not from where the command is run.
- **System files do not run alone.** `falcoria/compose.yml` and `asm/compose.yml` refer to
  `postgres` and `hatchet-engine` from `deploy/compose.infra.yml`. Run a system through
  `deploy/compose.test.yml` with its profile. Each service is described once; this is the cost.
- **Images are built locally in the test stack.** `build:` builds from source and tags the image
  `...:dev`. `deploy/compose.prod.yml` pulls tagged images from GHCR instead and removes `build:`.
- **Profiles say where a service runs.** `main` is the control host, `remote` the scanner machines
  (`scanner`, `httpx-worker`, `nuclei-worker`). `falcoria` and `asm` select a whole system.

## Adding a service

1. Add its Dockerfile under `apps/<name>/` of the system.
2. Add the service to the system's `compose.yml` with the system's profile, `build.context: .`, and
   the environment it needs.
3. Add a `depends_on` entry for what it needs at start (database, engine, another service).
4. Add the image to the system's CI filter and publish matrix
   (`.github/workflows/<system>-ci.yml`, `<system>-publish.yml`).
