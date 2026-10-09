# Ansible deployment

Deploys the production stack: one control host (Hatchet engine, databases, falcoria and asm
services) and any number of remote worker machines. Run everything from this directory. The full
runbook, with decisions, checks and failure messages, is `../../docs/DEPLOYMENT.md`.

## Layout

| Path | Holds |
|---|---|
| `inventory/hosts.example.ini` | Groups `control_plane`, `nmap_workers`, `nuclei_workers`. Copy to `hosts.ini` (ignored by git). |
| `inventory/group_vars/all.yml` | Image owner and versions, engine port and name, shared paths. |
| `inventory/group_vars/vault.example.yml` | Names of the secrets. Copy to `vault.yml` and encrypt (ignored by git). |
| `playbooks/` | `site.yml` (everything), `control_plane.yml`, `workers.yml`. |
| `roles/` | `common`, `docker`, `pki`, `control_plane`, `worker`. |
| `.pki/` | Worker certificates fetched from the control host (ignored by git). |

## Run

```sh
ansible-galaxy collection install -r requirements.yml
cp inventory/hosts.example.ini inventory/hosts.ini                      # then edit
cp inventory/group_vars/vault.example.yml inventory/group_vars/vault.yml  # then edit, then:
ansible-vault encrypt inventory/group_vars/vault.yml
ansible-playbook playbooks/site.yml --ask-vault-pass
```

Each role has a tag of its name, for example `--tags pki,control_plane`. Run `ansible-lint playbooks roles`
and `ansible-playbook --syntax-check playbooks/site.yml` before a deploy.

Images are pulled from `ghcr.io/<ghcr_owner>/<image>:<version>`. To use images loaded by hand with
`docker load`, add `-e control_plane_pull=missing -e worker_pull=missing` so Compose does not
pull them.

## Network and ports

- Only SSH and the engine gRPC port (`hatchet_grpc_port`, 8443) face the internet. The port is
  published on 0.0.0.0 and protected by mutual TLS plus the engine token.
- Docker publishes container ports in a way that bypasses ufw. Open the gRPC port in the provider's
  firewall, and keep the other published ports on 127.0.0.1 (they are; reach them through an SSH tunnel).
- The control host's API, dashboard and database ports listen on 127.0.0.1 only.

## Mutual TLS

The `pki` role creates a CA, the engine certificate (name `hatchet-engine`, usages server and client),
one client certificate for the services on the control host, and one per worker host in the inventory.
Certificates are valid for ten years and are not rotated.

A remote worker needs both `HATCHET_CLIENT_HOST_PORT=<server address>:<port>` and
`HATCHET_CLIENT_TLS_SERVER_NAME=hatchet-engine`: the certificate carries the name, not the address.
To add a worker, add it to the inventory and run `--tags pki,worker`.

## Known behavior

- A second run reports `changed` for the Compose steps: `docker compose up` starts the one-shot
  containers (migrations, `hatchet-setup`) again. They are idempotent.
- The `docker` role is skipped on a machine that already has Docker CE installed.
