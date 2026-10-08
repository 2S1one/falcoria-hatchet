# deploy

Docker Compose files that run falcoria and asm together. Only the test stack exists so far:
a full stack on one machine, images built from source.

| File | Holds |
|---|---|
| `compose.infra.yml` | Hatchet engine, dashboard (REST API), its PostgreSQL and RabbitMQ; one PostgreSQL for the application databases (`scanledger`, `asm_core`, `asm_core_test`). |
| `compose.test.yml` | The stack: includes the infrastructure and the service files of both systems. |
| `../falcoria/compose.yml` | falcoria services (profile `falcoria`). |
| `../asm/compose.yml` | asm services (profile `asm`). |
| `postgres-init/` | Creates the roles and databases on the first start of an empty volume. |
| `scripts/create-hatchet-token.sh` | Prints a Hatchet API token. |
| `.env.example` | Every variable with its development default. Copy to `.env` (ignored by git). |

The service files of the systems cannot run alone: they refer to services of `compose.infra.yml`.
Run one system with its profile.

## Start

```sh
cd deploy
cp .env.example .env
docker compose -f compose.test.yml up -d                  # infrastructure only
./scripts/create-hatchet-token.sh                         # put the output into .env as HATCHET_TOKEN
docker compose -f compose.test.yml --profile falcoria --profile asm up -d --build
```

Use `--profile asm` or `--profile falcoria` alone to run one system. asm's bridge needs falcoria's
`scanledger`, so `asm` without `falcoria` leaves the bridge failing and retrying until scanledger
is reachable.

Host ports (changeable in `.env`): dashboard 8088, scanledger 8101, tasker 8102, asm API 8103,
Hatchet gRPC 7070, application PostgreSQL 5436.

Stop and delete the data: `docker compose -f compose.test.yml --profile falcoria --profile asm down -v`.

## Things that cost time

- **Use the `default` tenant.** The engine also has a service tenant named `internal`. A token for
  it is accepted, but runs stay `QUEUED` forever. The token script picks the tenant by slug.
- **A new token is needed after `down -v`.** The tenant is created again with new data.
- **The engine is quiet.** It logs warnings only. Set `HATCHET_LOG_LEVEL=debug` in `.env` and
  recreate `hatchet-engine` to see the scheduler.
- The stack runs real tools. nuclei in `asm-worker` is limited to light templates and 20 requests
  per second (`ASM_CORE_CHAIN_NUCLEI_PARAMS` in `asm/compose.yml`); keep it that way for hosts you
  do not own.

## Not written yet

- A production stack (images from GHCR by tag, TLS or mutual TLS to the engine, no published
  database ports).
- Worker files for separate scanner machines.
- Secrets handling beyond `.env`.
