# Deployment runbook

How to deploy the production stack from nothing, and why it is built this way. Written so that an
agent can follow it without prior context. Commands run from `deploy/ansible/` unless stated.
The test stack on one machine is described in `deploy/README.md`; the container background is in
`docs/CONTAINERS.md`.

Status: deployed from scratch and checked on DigitalOcean machines (a control host and two workers),
with images pulled from GHCR and one small scan run through the remote workers. See "Not verified"
for what that did not cover.

## 1. What gets deployed

| Machine | Ansible group | Runs | Compose file |
|---|---|---|---|
| Control host (1) | `control_plane` | Hatchet engine, dashboard, its PostgreSQL and RabbitMQ; application PostgreSQL; scanledger, tasker, uploader; asm-worker, asm-api, asm-bridge | `deploy/compose.prod.yml`, profile `main` |
| nmap machines (N) | `nmap_workers` | `scanner` (nmap), host network, raw-socket capabilities | `worker` role template `compose.nmap.yml.j2` |
| nuclei machines (N) | `nuclei_workers` | `httpx-worker` and `nuclei-worker` of asm | `worker` role template `compose.nuclei.yml.j2` |

Images (`ghcr.io/<ghcr_owner>/<name>:<version>`): `falcoria-scanledger`, `falcoria-tasker`,
`falcoria-worker` (used by uploader and scanner), `asm-core` (worker, API and bridge),
`asm-httpx-worker`, `asm-nuclei-worker`. falcoria images use `falcoria_version`, asm images use
`asm_version`. All images are amd64 only (the nuclei image downloads an amd64 binary).

Remote workers need exactly one connection: outbound gRPC to the engine, with mutual TLS. They
have no scanledger or database settings. Reports and results are stored by services on the control
host.

### Ports

| Port | Where | Exposure |
|---|---|---|
| 22 | all machines | internet |
| `hatchet_grpc_port` (8443) -> container 7070 | control host | internet, protected by mutual TLS and the engine token |
| 8088 dashboard, 8101 scanledger, 8102 tasker, 8103 asm-api, 5436 PostgreSQL | control host | `127.0.0.1` only; use an SSH tunnel |

8443 is used because it is usually already open and leaves 443 free for a future HTTPS front. There
is no reverse proxy: nothing but SSH and the gRPC port faces the internet.

## 2. Prerequisites

- **Machines:** Ubuntu 24.04 x86_64, root SSH with a key. Used sizes: control host 4 vCPU / 8 GB,
  workers 1 vCPU / 2 GB. A provider image with Docker CE already installed is fine; the `docker`
  role skips such machines.
- **Provider firewall:** allow inbound TCP 22 and `hatchet_grpc_port` from anywhere. Ansible does not
  manage a firewall. Docker publishes container ports in a way that bypasses ufw, so only the
  provider's firewall (or `DOCKER-USER` rules) restricts them. On DigitalOcean check with
  `doctl compute firewall get <id> -o json`; a closed port shows as a TCP timeout and the iptables
  counters on the host stay at zero.
- **Local tools:** `ssh`, `docker` (to build and move images), `uv`. Ansible is run through `uvx`:
  `uvx --from ansible-core ansible-playbook ...`, `uvx ansible-lint ...`. A normal `ansible-core`
  install works the same.
- **Collections** (pinned in `requirements.yml`; versions are at least two weeks old):
  `ansible-galaxy collection install -r requirements.yml`. If you use a custom
  `ANSIBLE_COLLECTIONS_PATH`, include every directory that holds them, or tasks fail with
  "couldn't resolve module/action".

## 3. Configure

1. **Inventory:** `cp inventory/hosts.example.ini inventory/hosts.ini` and put real addresses in. The
   groups are `control_plane`, `nmap_workers`, `nuclei_workers`. The inventory host name of a worker
   becomes the name of its certificate (`<name>.crt`). `hosts.ini` is ignored by git.
2. **Shared variables:** edit `inventory/group_vars/all.yml`: `ghcr_owner`, `falcoria_version`,
   `asm_version`. Nothing else there normally changes.
3. **Secrets:** `cp inventory/group_vars/vault.example.yml inventory/group_vars/vault.yml`, fill in
   with random values, encrypt. Use letters and digits only: the values end up in a Compose `.env`
   file where `$` and quotes have meaning. The four `vault_scanledger_*_token` values must differ.
   ```sh
   python3 -c 'import secrets,string;print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))'
   # create the vault password file once (any random string), then encrypt:
   python3 -c 'import secrets,string;print("".join(secrets.choice(string.ascii_letters+string.digits) for _ in range(40)))' > .vault-pass && chmod 600 .vault-pass
   ansible-vault encrypt --vault-password-file .vault-pass inventory/group_vars/vault.yml
   ```
   `vault.yml` and `.vault-pass` are ignored by git. Supply the password with `--ask-vault-pass`, or
   `ANSIBLE_VAULT_PASSWORD_FILE=$PWD/.vault-pass` (`ansible-lint` also needs it, because it
   syntax-checks the playbooks).
4. **Images:** either publish them (see "Publishing the images" below), or move locally built ones:
   ```sh
   # from the repo root: build with the test stack, then retag and copy
   docker compose -f deploy/compose.test.yml --profile falcoria --profile asm build
   O=<ghcr_owner>; F=<falcoria_version>; A=<asm_version>
   for i in falcoria-scanledger falcoria-tasker falcoria-worker; do docker tag $i:dev ghcr.io/$O/$i:$F; done
   for i in asm-core asm-httpx-worker asm-nuclei-worker; do docker tag $i:dev ghcr.io/$O/$i:$A; done
   docker save ghcr.io/$O/falcoria-scanledger:$F ghcr.io/$O/falcoria-tasker:$F ghcr.io/$O/falcoria-worker:$F ghcr.io/$O/asm-core:$A \
     | gzip -1 | ssh root@<control-host> 'gunzip | docker load'
   docker save ghcr.io/$O/falcoria-worker:$F | gzip -1 | ssh root@<nmap-host> 'gunzip | docker load'
   docker save ghcr.io/$O/asm-httpx-worker:$A ghcr.io/$O/asm-nuclei-worker:$A | gzip -1 | ssh root@<nuclei-host> 'gunzip | docker load'
   ```
   Then run Ansible with `-e control_plane_pull=missing -e worker_pull=missing` so Compose does not
   try to pull them.

## 4. Deploy

```sh
uvx ansible-lint playbooks roles
uvx --from ansible-core ansible-playbook --syntax-check playbooks/site.yml
uvx --from ansible-core ansible-playbook playbooks/site.yml --ask-vault-pass      # add the -e pull flags if images were loaded by hand
```

`site.yml` runs `control_plane.yml` and then `workers.yml`. The order matters: workers copy
certificates that the `pki` role on the control host created and fetched to `.pki/`. Each role has a
tag of its name (`--tags common|docker|pki|control_plane|worker`).

What the roles do:

| Role | Effect |
|---|---|
| `common` | base packages, timezone `Etc/UTC` |
| `docker` | on a machine without Docker CE: removes unofficial packages, adds Docker's apt repository, installs Engine and Compose plugin. Skipped when `docker-ce` is installed. |
| `pki` | control host only. Creates a CA (`certs/ca`), the engine certificate (`certs/engine`, name `hatchet-engine`, usages server and client), one client certificate shared by the control host services (`certs/client`, key owned by uid 1000), and one certificate per worker host (`certs/workers`). Fetches `ca.crt` and the worker pairs to `.pki/` (mode 0700, ignored by git). |
| `control_plane` | copies the Compose files into `/opt/falcoria/{deploy,falcoria,asm}` (the layout the `include` paths need), writes `deploy/.env` (mode 0600) from the vault, starts the infrastructure, creates the Hatchet token once and stores it in `deploy/.hatchet-token` (0600), rewrites `.env` with it, starts profile `main`. |
| `worker` | copies the CA and this host's certificate pair to `/opt/falcoria/worker/certs`, reads the token from the control host, writes `.env` and `compose.yml`, starts the containers. |

## 5. Verify

On the control host (`cd /opt/falcoria/deploy`):

```sh
docker compose -f compose.prod.yml --profile main ps          # 11 services up, none restarting
ss -ltnH | awk '{print $4}'                                    # only :22 and :8443 on 0.0.0.0
```

From outside: `bash -c 'echo > /dev/tcp/<control-host>/<grpc-port>'` must succeed. On each worker:
`docker compose -f /opt/falcoria/worker/compose.yml ps` and `docker compose logs` must show
"started, waiting for tasks".

End-to-end check (use only a host you may scan, such as `scanme.nmap.org`). On the control host,
tokens are in `deploy/.env`; the APIs are on `127.0.0.1`:

1. `POST /api/projects` on scanledger (8101, `/api` prefix) with the admin token, then add the
   `tasker`, `worker` and `asm` users as members (`GET /api/admin/users` gives their ids;
   `POST /api/projects/{id}/members` with `{"user_id": ...}`).
2. `POST /api/projects/{id}/scans` on tasker (8102) with the tasker token and a body like
   `{"hosts":["scanme.nmap.org"],"open_ports_opts":{"ports":["22","80"]},"service_opts":{},"timeout":600,"include_services":true,"mode":"replace"}`.
3. Poll `GET /api/projects/{id}/scans/{scan_id}` until `completed`.
4. `GET /api/projects/{id}/ips` on scanledger shows the ports; after about a minute
   `GET /projects/{id}/results/httpx` and `/results/nuclei` on asm-api (8103, no `/api` prefix, same
   Bearer token) fill in. With light templates expect `info` findings only.

Mutual TLS from outside (client environment `HATCHET_CLIENT_*`): a worker certificate with
`HATCHET_CLIENT_TLS_SERVER_NAME=hatchet-engine` connects. These must fail: no client certificate,
a certificate from another CA, no TLS, and a valid certificate with a wrong token.

## 6. Operate

- **Upgrade:** change `falcoria_version` / `asm_version`, load or publish the images, rerun the
  playbook. The Hatchet engine version is `HATCHET_VERSION` (default in `deploy/compose.infra.yml`).
- **Add a worker:** add it to the inventory, run `--tags pki,worker`. The new host's certificate is
  issued on the control host and fetched first.
- **Reach the APIs and dashboard:** `ssh -L 8102:127.0.0.1:8102 root@<control-host>`, same for 8088,
  8101, 8103.
- **Reset the engine:** `docker compose down -v` deletes the volumes. The Hatchet tenant is created
  again with new data, so the old token is useless: delete `deploy/.hatchet-token`, rerun the
  `control_plane` role (it creates a new token), then rerun the `worker` role.
- **Secrets:** never print `.env`, the token or `vault.yml`. The roles use `no_log` for them.

## 7. Decisions and facts that explain the setup

- **Mutual TLS, port facing the internet.** Workers may live in any region or cloud, so the gRPC
  port is public and protected by a client certificate (CA ours) plus the engine token. Both are
  checked independently. Engine settings: `SERVER_TLS_STRATEGY=mtls`, `SERVER_GRPC_INSECURE=false`,
  `SERVER_TLS_{CERT,KEY,ROOT_CA}_FILE`, `SERVER_INTERNAL_CLIENT_TLS_SERVER_NAME=hatchet-engine`.
- **Certificates are issued for the name `hatchet-engine`, not an address.** Clients must set
  `HATCHET_CLIENT_TLS_SERVER_NAME=hatchet-engine`; without it the connection fails. This keeps the
  certificates valid if the server address changes.
- **The engine's own client reuses the engine certificate**, so that certificate needs both the
  server and the client usage. The internal services (tasker, uploader, asm) use a separate client
  certificate; they run as uid 1000, the engine as root, which is why each has its own directory
  and key owner. The CA key is never mounted into a container.
- **`HATCHET_CLIENT_HOST_PORT` overrides the address inside the token** (checked by a run; the
  documentation only says the default is inherited from the token). Remote workers therefore need no
  token with a public address, and `SERVER_GRPC_BROADCAST_ADDRESS` stays internal.
- **The engine token must be for the `default` tenant.** The engine also has a service tenant
  `internal`; a token for it is accepted but runs stay `QUEUED`. `create-hatchet-token.sh` selects
  the tenant by slug, and takes the compose file from `COMPOSE_FILE`.
- **Compose layout.** `compose.prod.yml` includes the test-stack service files and overrides what
  differs: `image` from GHCR, `build: !reset null`, `ports: !override` with `127.0.0.1`, restart
  policy, log rotation, mutual TLS. `ports` lists are merged, not replaced, without `!override`: a
  plain override would publish the port twice, once on all interfaces. Profile `main` is the
  control host, `remote` the scanner machines. Image tags and versions are required variables
  (`${VAR:?}`), so a development image cannot reach production.
- **No rotation or revocation.** Certificates last ten years (decision). There is no revocation
  list: deleting a worker's files does not invalidate its certificate, and revocation was not
  tested. After a leak, the sound approach is a new CA and new certificates for every client
  (delete `certs/ca` on the control host and rerun `pki`, `control_plane` and `worker`; this path
  has not been run).
- **Idempotence.** A second run reports `changed` for the two Compose steps because `up` starts the
  one-shot containers (migrations, `hatchet-setup`) again; they are safe to repeat.
- **Failure messages.** `Client CA is required for mTLS` on the engine means the CA path or its
  permissions are wrong (the message does not say which). `TLS handshake error ... first record does
  not look like a TLS handshake` in the engine log is a client still using plain gRPC.

## 8. Publishing the images

Pushing a git tag `falcoria-vX.Y.Z` or `asm-vX.Y.Z` on the commit to release starts
`falcoria-publish.yml` or `asm-publish.yml`. Each builds its images and pushes them to
`ghcr.io/<owner>/<image>` (owner in lower case) with the tags `X.Y.Z`, `X.Y`, `latest` and
`sha-<commit>`; the version has no `falcoria-v` / `asm-v` prefix, and `X.Y.Z` is what
`falcoria_version` / `asm_version` must hold. Run it from the commit that is already on `main`.

- **Name clash.** The workflow authenticates with the repository's `GITHUB_TOKEN`. If a package with
  the same name already exists in the account and was created by another repository, the push fails
  with `permission_denied: write_package`. Either delete the old package or give this repository
  write access to it (package settings, "Manage Actions access"). The three `falcoria-*` names had
  been used by an earlier project and had to be deleted.
- **Visibility.** The packages created by these workflows could be pulled without logging in. If a
  deployment has to log in to pull, check the package visibility first.
- **Check the result** without credentials: request an anonymous registry token for
  `repository:<owner>/<image>:pull` from `https://ghcr.io/token` and list
  `https://ghcr.io/v2/<owner>/<image>/tags/list`. A missing package returns no token.
- Re-run a failed publish with `gh run rerun <run-id> --failed`.

## 9. Not verified

- The `docker` role on a machine without Docker: every machine used so far came with Docker
  installed, so the role only skipped its install block there.
- The whole stack under load; database backups; monitoring; certificate rotation and revocation;
  the production stack on more than one worker per group.
- A deployment where the control host was restarted or its volumes were removed (see "Operate" for
  the intended steps).
