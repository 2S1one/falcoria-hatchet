#!/bin/sh
# Prints a new Hatchet API token for the `default` tenant. Run after the infrastructure is up:
#   deploy/scripts/create-hatchet-token.sh
# Put the printed value into deploy/.env as HATCHET_TOKEN. Do not paste it into chat or commits.
#
# The engine also holds a service tenant named `internal`. A token for it is accepted, but
# runs sent with it stay QUEUED forever, so the tenant is picked by its slug, never by position.
set -eu

cd "$(dirname "$0")/.."
compose="docker compose -f compose.test.yml"

tenant_id=$($compose exec -T hatchet-postgres \
  psql -U hatchet -d hatchet -tA -c "SELECT id FROM \"Tenant\" WHERE slug = 'default'")
if [ -z "$tenant_id" ]; then
  echo "No default tenant found: has hatchet-setup finished? Check '$compose ps -a'." >&2
  exit 1
fi

$compose run --rm --no-deps hatchet-setup \
  /hatchet/hatchet-admin token create --config /hatchet/config --tenant-id "$tenant_id" | tail -1
