# Batch timing with one slot per worker

How `nuclei-scan` (a Hatchet batch task) is timed when a worker runs one batch at a time
(`slots=1`), and what that means for the design. Measured on 2026-10-06 against a local engine
v0.107.2 with the Python SDK 1.41.1 and, for one check, the Go SDK 0.107.2. Throw-away tasks with
instant or sleeping handlers stood in for nuclei; no real nuclei run is behind these numbers.

## Design

- One nuclei process at a time per worker: it is tuned for full speed and uses the machine's whole
  network bandwidth. Hence `slots=1` on the nuclei worker.
- A batch is cut at 25 tasks of one group or when the group's interval (30 s, placeholder) runs
  out. A group is one `batch_key`: project, scan, scan params, timeout.

## How the engine times a group

The engine keeps one timer per group. Findings, each measured:

1. **Full batches run back to back.** 260 tasks of one group, 5 s per batch: ten batches of 25 started
   0.1 to 0.3 s after the previous one ended. The interval does not delay a full batch.
2. **The timer restarts after every flush.** The leftover 10 tasks of that run started at 82.3 s;
   the last full batch had started at 52.3 s, and 52.3 + 30 = 82.3. A leftover waits one interval
   counted from the group's previous flush.
3. **A busy slot costs one more interval.** When a group's timer runs out and the slot is taken, the
   batch is not started and the timer restarts. Example: a full batch of group F ran 3.6 to 43.6 s
   (40 s scan); 10 tasks of group R, sent at 1 s, hit their timer at about 34 s with the slot busy,
   and started at 63.8 s. The worker sat idle for 20 s. The idle time is at most one interval.
4. **Several groups due at the same moment share one slot one at a time.** Three groups, one task
   every 3 s, 10 s interval, instant handler, `slots=1`: groups A and C flushed about every 10 s, group
   B first flushed at 95.5 s with 10 tasks. The Go SDK showed the same shape (B flushed at 13.2 s and
   93.7 s), so the behaviour is the engine's, not the Python SDK's. With `slots=2` every group flushed
   every ~10 s.

## Why (engine source, tag v0.107.2, commit e53ce04)

`pkg/scheduling/v1/batch_scheduler.go`:

- 411-417: a group flushes when its deadline has passed.
- 400-409: a group holding a full batch flushes without waiting for the deadline.
- 639-641: every flush attempt resets the group's deadline to now + interval.
- 887-895, 897-899: if no slot is assigned, the group goes back to the buffer and its deadline is reset.
- 383: groups are visited in Go map order, which is not fixed.

## Decision

- Keep `slots=1`. The one-process-at-a-time rule is the requirement; a full-batch stream is not
  slowed by the timer (finding 1).
- The idle time of a leftover batch is bounded by `batch_max_interval` (findings 2 and 3). The
  interval is a placeholder and is chosen from measurements of real nuclei runs (start-up cost against
  batch size), not from these tests.
- No code change follows from this. Worker code does not depend on the timing; it only receives
  the batch.

## Not measured

- Real nuclei runs, and thousands of groups at once.
- Why group B lost the slot about nine times in a row in finding 4: with a random visiting order that
  is unlikely, and the cause is unknown.
- The claim that a full batch retries every scheduler tick while the slot is busy is read from the
  source; the 260-task run shows the result (no gaps) but not the retry itself.
