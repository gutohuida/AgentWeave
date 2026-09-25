# Proposal — pressing Run names the reason that held

**Round 1, 2026-09-23** (day window, D-2b, spec loop B). Findings: **F400 (B)** and **F373 (B)**,
taken together because both are false sentences in one branch of one route (`run_job`'s
`if not success:` block, `hub/hub/api/v1/jobs.py:1428-1497` at `8bc926f`) and both are governed by one
requirement. Two proposals editing those lines would collide (the F300/F312 rule). Both were
**re-measured on HEAD `dcdf723`** through the real route
(`scripts/drive/d2b_0923_run_answer_probe.py`). Round 1 also filed **F411**: the app's Run button
never displays this answer at all. F411 stays out of scope (design Open Question 1).
**Round 2, 2026-09-23** (D-3b) re-derived the decline paths from the code, measured two more false
answers from the same branch (a firing that fails, before or after writing its row), widened D3 to
cover them, and filed **F412** (Open Question 3). **Round 3** (D-4b) re-derived them again. It found
that a crash leaving no row cannot be told from a decline that left none, filed **F413** (Open
Question 4), replaced D3's `else → 500` with named statuses, and made the precedence a total order.
**Nothing here is implemented yet.**

## Why

When a firing declines without doing anything, `POST /jobs/{id}/run` answers 409 with a sentence
saying why. `agent-loops`' *"Pressing Run on a loop that declines names why it declined"* requires
that sentence to be the real reason. Two of its answers are not.

**F400: a documentless loop is told nobody else is free.** Since `a-loop-staffs-the-agent-it-names`
(archived 2026-09-22), a loop that declares no specification document gives its work only to the
agent its job names. `_agents_a_loop_may_staff` returns `[]` for it (`scheduler.py:1263-1284`). So the
busy guard refuses it whenever that agent is busy, **whoever else is free**. `run_job` still picks its
second clause as if the roster were the reason. Measured, with a sibling agent free:

> `probe-owner is already running a turn, and no other agent is free to take this loop's work. Nothing was started.`

That is false. The code's own comment (`jobs.py:1443-1445`) names what this does: it *"would send
them to free an agent, which changes nothing"*. The empty-queue clause has the same flaw, milder:
*"this loop's queue holds no open task for another agent to take"*. A documentless loop never gives
work to another agent. The current requirement says the documentless open-task sentence is *"not yet
decided"* (`agent-loops/spec.md:1515-1518`). This change decides it.

**F373: an in-flight decline is answered with an earlier firing's stall.** After the busy-guard
re-ask, the route answers from `latest_run` whenever its status is `skipped`
(`jobs.py:1455-1459`). That branch is not gated on whether this press wrote or counted that row. An
in-flight decline writes nothing (F23), so the newest row is some earlier firing's. Measured: a flow
whose only task is `in_progress` under its busy agent, with another agent free (so the guard
passes), and an hour-old skipped row. The route answered 409:

> `loop queue is stalled: 1 still awaiting a prerequisite's approval`

The queue's only task was being worked. The requirement already forbids this (*"SHALL answer from a
firing record only when the manual firing wrote that record"*, `:1520`); the code does not meet it.

## What Changes

- **The busy guard reports which half refused** (design D1). `_loop_flow_busy_reason`'s logic
  moves into one function that returns the busy reason and which of three conditions held: the
  queue is empty, the loop names one agent, or no other agent is free. The route reads that instead
  of re-deriving it with a second `_loop_has_open_task` query. The firing and the board keep their
  string-only reader, unchanged.
- **Three clauses, one per condition** (design D2). A documentless loop with open work is told its
  work goes only to the agent its job names. A documentless loop's empty queue drops *"for another
  agent to take"*. A flow keeps both of today's sentences word for word.
- **The route answers from a record only where this press wrote it or counted into it** (design D3).
  `run_job` copies the newest row's `tick_count` to a plain `int` before firing. Measured:
  `_fire_job_internal` gets the route's session, and a continuing stall increments the same object
  the route read (`same_object=True`, 1→2 in place). So comparing the object with itself after the
  firing would always read "unchanged". A counted stall still answers from its row; an in-flight
  decline now falls through to the in-flight answer.
  **R2 widened this:** the row the press wrote is its answer whatever its status. A `failed` row is
  answered as a 500 with its reason; today the route re-decides the loop first, and measured, it
  answered *"already being worked … nothing is wrong"* over a firing that crashed after its turn
  started. A firing that crashed before writing anything is answered *"Failed to fire job"*; today it
  gets an earlier firing's stall, as a 409. **R3 narrowed that claim.** This holds only where the
  guard does not refuse and the work is not in flight. Otherwise a crash that left no row looks
  exactly like a decline that left none. It is answered as that decline, which on an in-flight flow
  is *"nothing is wrong"*. The repair belongs in the firing (F413, design Open Question 4). R3 also
  made the row's statuses explicit, so a concurrent tick's `in_progress` row is no longer read as a
  failure. Today that row answers 500, measured.
- **The requirement is decided** (spec delta). The *"not yet decided"* paragraph becomes a SHALL.
  The answer names the condition that held and none that did not. *"Wrote that record"* becomes
  *"wrote or counted into"*, which says what a continuing stall already does.

Route and scheduler only: no migration, no API shape, no UI, no bundle. Two existing assertions move
on purpose (`test_board_agent_role.py:385` and `:420`). Both stage a documentless loop, and both
pin *"no other agent is free"*. After this change they read the scope clause (design D2, task 1.6).

## Capabilities

### Modified Capabilities

- `agent-loops` — *Pressing Run on a loop that declines names why it declined*: the documentless
  open-task answer is decided, the three-way condition is named and exclusive, and *"wrote"* covers
  a counted stall.

## Impact

- `hub/hub/scheduler.py`: the new structured guard answer (`_loop_flow_busy_refusal`), with
  `_loop_flow_busy_reason` reduced to a wrapper over it. Its other two callers (the firing, in `_do_fire_job`, `scheduler.py:3045`, and the board's re-ask, `jobs.py:389`) are unchanged.
- `hub/hub/api/v1/jobs.py`: `run_job`'s `not success` branch only.
- `hub/tests/`: new tests, and two named assertions moved in `test_board_agent_role.py`.
- **Not touched**: `hub/ui/`, `hub/hub/static/ui/`, `mcp_server.py`, models or migrations. Nothing
  here shares a file with `an-at-mention-an-agent-wrote-reads-no-file`: that change cites
  `jobs.py:560-570` in its design but edits no line of it.
