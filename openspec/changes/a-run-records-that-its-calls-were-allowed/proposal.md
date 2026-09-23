# Proposal — a run records that its calls were allowed

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F389 (C)**. Re-verified
on `ce086b6`. **Nothing here is implemented yet.** This is the lowest-priority change in B11: nothing
is broken today, and it exists so the next F52 can be answered from a record.

## Why

`record_permission_decision` (`hub/hub/api/v1/agent_actions.py:969-1010`) persists an event only when
a call was refused (`:991-1009`) and returns `{"recorded": false}` for an allowed one. Codex's
runtime reports refusals only (`codex_appserver.py:1083-1100`, `agent_trigger.py:2979-3014`). So
*"this run asked, and every call was allowed"* and *"this run never asked"* leave byte-identical
state. F52 claimed every git commit was silently refused under the `workspace` posture, and
disproving it took two commits and a live turn (`0cda570`, `57eb92b`) because no stored record could
answer the question directly. F52 is retired; the gap that let it stand for three weeks is not.

The refusal rule is right, and `agent-run-sandboxing` states it: *"Only refusals SHALL be recorded
**as refusals** … This constrains what the refusal record may contain; it is not a rule about every
durable event the system keeps."* An event per allowed call would bury the refusals (the operator's
question to D13 was *"event per allow?"*; the answer is no). A count per run does not.

## What Changes

- **Each run carries a count of the decisions it received** (design D1): a nullable JSON column
  `Run.permission_decisions`, `{"allowed": n, "refused": m}`. `NULL` means no decision reached the
  Hub for this run (it had no approver, or it predates this), `{"allowed": 0, "refused": 0}` never
  occurs, and any count means the approver was asked.
- **Written on first sight, made exact at the end** (design D2), the pattern
  `outside_write_record.py` already uses: the first decision of each kind in a run writes the row
  once; later ones are counted in memory; the run's end flushes the exact counts. A Hub that dies
  mid-run keeps "at least one allowed" and "at least one refused".
- **Both runtimes feed it**: the Claude route above for every decision it reports, and Codex's
  approval loop through a new `on_decision` alongside its `on_refusal`.
- **Nothing is shown in the UI yet.** The run detail API returns the field; a surface can come later.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing`: a new requirement, *A run records how many of its calls were allowed and
  refused*.

## Impact

- `hub/hub/db/models.py` (`Run`), a new migration (the next free revision at IMPL time),
  `hub/hub/api/v1/agent_actions.py`, `hub/hub/codex_appserver.py`, `hub/hub/api/v1/agent_trigger.py`
  (both runs' `finally` flush, beside `outside_writes.flush()` at `:2714` and `:3254`), a new
  `hub/hub/permission_tally.py`, and the run response schema.
- **A migration**: runs on `:8000` at its next restart; adds one nullable column.
- **Write load**: at most two row writes per run from the route (first allowed, first refused) plus
  one at the end, not one per call. That matters because `database is locked` is a live concern
  (F349, F292).
