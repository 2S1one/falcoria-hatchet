# Overview

What the platform does, who does what, and where the data lives. For file-level navigation use
`falcoria/docs/MAP.md` and `asm/docs/MAP.md`; for containers see `CONTAINERS.md`.

## One run, start to finish

A scan request for `scanme.nmap.org`, ports 22, 80 and 443. Times are approximate, read from
15-second status polls of a real run.

```text
t = 0 s      The request reaches tasker. Tasker resolves the name to an IP, skips private
             addresses, and starts a Hatchet run for the IP.
t = 10 s     The scanner (nmap) takes the run and probes the three ports.
t = 25 s     Ports 22 and 80 are open. The uploader sends the nmap report to scanledger,
             which stores the ports and appends an event "this IP got ports 22 and 80".
t = 30 s     The asm bridge polls scanledger every 5 s, reads the event, and starts one
             httpx-then-nuclei run for each new port.
t = 35 s     httpx probes both ports. Port 80 answers HTTP 200; port 22 does not speak HTTP.
             Both outcomes are stored in the asm database.
t = 40 s     Port 80 goes on to nuclei. Port 22 stops here.
t = 2 min    nuclei runs the targets collected in its batch (up to 25 targets or 30 s) in one
             process. Two findings, apache-detect and waf-detect, are stored.
```

When a second scan arrives while the scanner is busy, it waits in the queue: one scanner process
runs one nmap scan at a time.

## The two systems

**falcoria** answers "what is open in the network".

| Service | Role |
|---|---|
| `tasker` | Accepts scan requests, resolves and filters targets, starts Hatchet runs (one per IP and port shard), reports progress and cancels runs. Holds no scan data. |
| `scanner` | Runs nmap. One scan at a time per process. |
| `uploader` | Sends the finished nmap report to scanledger. |
| `scanledger` | System of record: projects, IPs, open ports, hostnames, the history of port changes. Serves an event feed of changes. |

**asm** answers "what is running there, and is something wrong".

| Service | Role |
|---|---|
| `asm-bridge` | Polls scanledger's event feed. Turns each new TCP port into one `httpx-then-nuclei` run and remembers which targets it already launched. |
| `httpx-worker` | Tries https, then http only after a TLS failure, and reports what happened. |
| `nuclei-worker` | Runs nuclei over a batch of targets in one process. |
| `asm-worker` | Runs the chain `httpx-then-nuclei` and the tasks that store results. |
| `asm-api` | Starts scans by hand (httpx, nuclei) and reads the results. |

**Hatchet** hands work between services: it keeps the queue, gives tasks to workers, retries failed
ones, and shows statuses in the dashboard. Data does not travel through it. Scan data goes to
scanledger over HTTP: tasker calls its API, the uploader posts reports to it, and the asm bridge
reads its event feed.

## Where data lives

| Data | Place | Owner |
|---|---|---|
| nmap results, port history, events | database `scanledger` | falcoria |
| httpx probes, nuclei findings | database `asm_core` (current state, no history) | asm |
| runs, queue, worker registry | Hatchet's own database and RabbitMQ | Hatchet |

In the test stack both application databases are in one PostgreSQL instance as separate databases
with separate roles. asm never reads scanledger's database; it only calls its HTTP API.

## Decisions that shape the behavior

1. **The chain does not wait for nuclei.** `httpx-then-nuclei` waits for httpx (seconds), starts
   the nuclei run, and finishes. Thousands of targets do not hold slots for long scans.
2. **nuclei runs in batches.** One process for up to 25 targets or 30 seconds, so the start-up and
   template-loading cost is paid once per batch. Both numbers are placeholders until measured on
   real runs.
3. **A nuclei error is an answer, not a crash.** Every target in a batch gets a result: findings or
   an error text. After an error, stored findings stay.
4. **Results are the current state.** A repeat scan updates rows; a finding that a scan with the
   same filters no longer reports is removed. There is no history in asm.
5. **Events can repeat, launches should not.** The bridge saves its position in the feed after each
   page and records every launched target, so a replayed page does not launch it twice. A crash at
   the wrong moment can still launch one target twice.

## Limits worth knowing

- Checked on a small run (two targets, three ports). Behavior with hundreds of events per second is
  not measured.
- The asm API checks the caller's token against project membership in scanledger. It has no scan
  status and no cancel, by decision for the MVP.
- asm creates its tables on start and has no migrations; a changed column does not reach an
  existing database.
- nuclei is limited to light templates and 20 requests per second in the test stack. Keep that for
  hosts you do not own.
- The production deployment (`deploy/compose.prod.yml`, `deploy/ansible/`) ran once on three
  machines with one small scan. Images were loaded by hand: publishing to GHCR was never run, so
  the image tag format is unverified. Certificates are not rotated, and databases are not backed up.

## Read next

- `CONTAINERS.md` and `../deploy/README.md`: how to run it.
- `../falcoria/docs/MAP.md`, `../asm/docs/MAP.md`: where things are in the code.
- `../asm/docs/hatchet-batch-timing.md`: measured timing of nuclei batches.
