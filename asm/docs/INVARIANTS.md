# Invariants

Basic lint, type and test commands are in `MAP.md`. Paths start with the package name (`asm_core/`, `asm_nuclei_worker/`, `asm_httpx_worker/`, `asm_contracts/`) and are under that package's `src/` directory. Paths without a package name are under `asm_core/`.

- **The nuclei batch never raises.** `batch.py#run_batch` turns any exception into an `ERROR` answer for every member. A raise would fail the whole batch without an answer per target. Lives in `asm_nuclei_worker/batch.py`.
- **A nuclei timeout is not retried.** `_scan_with_retry` retries only `CommandExecutionError`, once. Retrying a timeout would double the wall-clock limit. Lives in `asm_nuclei_worker/batch.py`.
- **`persist-nuclei-findings` stores nothing on an `ERROR` result.** Old findings stay. Storing an empty list would delete findings that were never rechecked. Lives in `asm_core/tasks.py`.
- **A finding is deleted only when the scan filter matches.** `reconcile_target_findings` deletes a stored finding that a scan did not report only if that scan's filter fields (`templates`, `tags`, `severity`, `exclude_severity`, `protocol_types`) equal the filter that last confirmed the row. A narrower scan would otherwise delete findings it never looked for. Lives in `persistence/nuclei.py`.
- **Storing is idempotent.** Both persistence functions upsert on a unique key (`NULLS NOT DISTINCT` on the nullable columns). That is what allows `persist-nuclei-findings` to retry twice and the bridge to replay a feed page. Lives in `persistence/` and `db/models.py`.
- **The dedup row is inserted before the launch and committed after it.** A failed launch rolls the row back, so the next poll retries the target. A failed commit after a successful launch can start the same target twice. Lives in `scanledger_bridge/adapter.py#handle_event`.
- **The feed cursor is saved after a whole page.** A crash in the middle of a page replays the page; the dedup table absorbs the replay. Lives in `scanledger_bridge/poller.py`.
- **Events with `scan_id` null are skipped.** A null `scan_id` marks a manual upload to scanledger, which does not trigger scans. Lives in `adapter.py#handle_event`.
- **`batch_key` must match the batch group key.** The nuclei worker declares `NUCLEI_BATCH_GROUP_KEY = "input.batch_key"`; the comment in `constants.py` says the engine reads that field from every call's input. What happens when the field is renamed without changing the constant is not tested [TODO]. Lives in `asm_nuclei_worker/constants.py` and `asm_contracts/nuclei_task.py`.
- **The nuclei worker has one slot.** One nuclei process uses the machine's network bandwidth. Raising `WORKER_SLOTS` changes the timing described in `docs/hatchet-batch-timing.md`. Lives in `asm_nuclei_worker/main.py`.
- **httpx connects to the given IP.** The probe ignores DNS for `hostname` and uses it only as Host header and TLS name. Certificates are not verified. Lives in `asm_httpx_worker/transport.py`.
- **A nuclei finding maps back to a target by its input line.** A finding whose `url` or `host:port` matches no target line is logged and dropped. Lives in `asm_nuclei_worker/scan.py`.
- **OAST callbacks are off by default.** `no_interactsh=True` passes `-ni`. Setting it false sends callbacks to a public interactsh server. Lives in `asm_contracts/nuclei.py#NucleiScanParams`.
- **`Hatchet()` runs at import.** `asm_core/tasks.py`, `asm_nuclei_worker/tasks.py` and `asm_httpx_worker/tasks.py` build the client when imported, so importing them needs `HATCHET_CLIENT_TOKEN` in the form of a JWT. `apps/asm-core/tests/conftest.py` sets a placeholder.
- **The schema is created, never migrated.** `create_db_and_tables` runs on every start of the worker, the API and the bridge. No change to an existing column reaches an existing database.

Verification beyond `MAP.md`:

```
uv run pytest -m postgres      # dedup, upsert and reconciliation against a real database
```
