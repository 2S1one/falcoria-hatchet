#!/bin/sh
# Creates one role and one database per system on the first start of the application
# PostgreSQL instance. Passwords come from the container environment.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE scanledger LOGIN PASSWORD '${SCANLEDGER_DB_PASSWORD}';
CREATE DATABASE scanledger OWNER scanledger;

CREATE ROLE asm_core LOGIN PASSWORD '${ASM_CORE_DB_PASSWORD}';
CREATE DATABASE asm_core OWNER asm_core;
-- Database the asm-core Postgres tests truncate and refill; never holds real data.
CREATE DATABASE asm_core_test OWNER asm_core;
SQL
