# Proposal — a task is attended only by a turn that will reach it

**Round 1, 2026-09-24** (bundle B1, spec track S1). Findings: **F370 (B)**, **F371 (C)**, **F368 (B)**.
All three re-measured on HEAD `404c7d5` with a throwaway test through the real firing
(`JobScheduler._fire_job_internal` / `decide_firing`), copied under `hub/tests/`, run and deleted.
**Nothing here is implemented yet.**

This is the first of the bundle's changes. `a-flow-stages-its-review-in-the-dispatch` (S13) is built
on the helper this change introduces and must be ordered after it.

## Why

A flow asks one question in three places — *is somebody on this task?* — and answers it from
`run_task_binding.tasks_with_a_turn_pending_or_running` (`hub/hub/run_task_binding.py:268-310`),
read once into `on_it` (`hub/hub/scheduler.py:1699`). That helper answers `task_id -> one agent`,
keeps whichever queued row comes back first (`pending.setdefault(candidate, agent)` over a select
with no `ORDER BY`, `:303-306`), counts input for **any** agent, and counts input at **any** hop
depth. Each reader is wrong in its own way.

**F370 — a held assignee is re-briefed every firing** (measured). The held-resume arm asks
`on_it.get(task.id) == agent` (`scheduler.py:1848`). Staged: flow job agent `held-dev`, held by a
provider refusal; task `assigned` to it; a `job` entry naming the task for `held-dev`; a peer entry
naming it for `aaa-peer`. The helper answered `{'task-width-f370': 'aaa-peer'}`, and three firings
queued three more briefings for `held-dev` (four `job` entries in all). That is the pile-up
`a-spent-allowance-holds-the-queue` D6 was built to stop, returning through the map.

**F371 — a review nobody is doing reads as attended** (measured, two legs). The F154 surfacing asks
`task.id not in on_it` (`scheduler.py:1796`). A task `under_review` with `beta` named and no turn:
with a peer message naming the task queued for `gamma`, `decide_firing` answered `in_flight`,
`stall_reason None`, `unstaffed ()`. With `beta`'s only entry at hop 99 (past the budget), the same.
F361 measured suspended entries still queued 2–13 hours later on `:8000`, so this never decays.

**F368 — an idle assignee whose queued turn cannot start is re-briefed every firing** (measured).
The ordinary resume arm treats an assigned task as in flight only when `agent in running`, or when
the agent is **held** and `on_it` names it (`scheduler.py:1848`). An assignee that is not held and
not running, with its briefing queued but not started (token budget exhausted, conversation
unavailable, a refused delivery awaiting retry), is briefed again. Staged with `schedule_agent`
answering `token budget exhausted`: three firings left four queued `job` entries for one task.

`agent-loops` *A task reported as in flight is one an agent is actually working* (`:1356-1358`)
already says the in-flight condition is "input naming that task is queued for delivery". The code
reads "for delivery" as "for anybody, ever". `agent-flows` *A flow treats an agent whose queue is
held…* already says input for a different agent "does not count" (`:862-863`); F370 is that sentence
failing.

## What Changes

- **One helper answers "who is on this task", by pair** (design D1). `task_attendance` replaces both
  `tasks_with_a_turn_pending_or_running` and `task_agent_pairs_with_a_turn_queued`. It returns
  `(task, agent)` pairs, each with how it is attended: a running turn bound to the task, input
  queued within the hop budget, or input queued within the budget behind that agent's refused head
  (refusal is read at the entry the agent's next turn would start with; design D1, R3).
  Suspended input (past the budget) is not a pair at all. `tasks_held_by_a_running_turn` stays: the
  trigger's *may this turn start* question is a different one (its own docstring, `:363-371`).
- **The three `decide_firing` readers ask the pair question** (design D2):
  - the F154 surfacing asks whether **the named agent** attends the task (F371);
  - the held-resume arm, and now every resume arm, asks whether **the assignee** attends it (F370,
    F368) — the `agent in held_agents and` qualifier goes, because the question was never about
    the hold;
  - the F70 recovery guard keeps asking whether **anyone** attends the task, now without suspended
    or refused input.
- **Refused input is not attendance** (design D3). A turn whose last delivery was refused is not
  being taken. For a review, the surfaced sentence carries the refusal's own words. For ordinary
  work, the firing briefs the assignee as it does today, which is what retries a refused head today
  (there is no tick: `turn_scheduler.py:665`, `agent_trigger.py:2643`); removing that would strand it.
  An F70/F167 author wedge whose recovery waits for another agent's turn is not surfaced as a
  review the author is not doing (design D2, `wedge_deferred`, R3).
- **The F154 sentence stops claiming "none is queued"** (design D4). Input the flow does not count
  may be queued.
- **Availability is unchanged** (design D5). `_roster_availability` reads the same pairs through the
  new helper with the same meaning it has today (any input queued within the budget, refused or
  not).

Scheduler and binding module only: no migration, no route shape, no UI, no `mcp_server.py`.

## Capabilities

### Modified Capabilities

- `agent-loops` — *A task reported as in flight is one an agent is actually working*: the in-flight
  condition is keyed to the agent whose name is on the task, excludes input past the hop budget and
  input whose last delivery was refused, and an in-flight assigned task is not briefed again whatever
  holds its turn.
- `agent-flows` — *A review nobody is doing is named, whatever its history*: defined by that
  condition; a third agent's input does not hide it; a refused delivery is named. *A flow treats an
  agent whose queue is held as unable to take a turn*: its "does not count" list is aligned.

## Impact

- `hub/hub/run_task_binding.py`: new `task_attendance` / `TaskAttendance`; the two helpers above
  removed.
- `hub/hub/scheduler.py`: `_roster_availability` (`:1162`, `:1179`), `decide_firing` (`:1699`,
  `:1792`, `:1796`, `:1811`, `:1848`), `_wedged_review_reason` (`:2195-2225`), one new sentence
  function for a refused review.
- `hub/tests/`: a new test file; the predicate tests in `test_a_review_nobody_is_doing.py:448-501`
  and one premise assertion in `test_a_task_nothing_will_move_holds_nobody.py:318-322` are rewritten
  against the new helper (design D6).
- **Collisions checked.** Round 5's F167 edit (`6117d15`) is `scheduler.py:1777-1785` (the
  `wedged_review` author test); this change edits the lines after it and leaves those alone.
  `pressing-run-names-the-reason-that-held` edits `_loop_flow_busy_reason` (`:312-350`) and
  `run_job`, not `decide_firing`; its busy guard reads availability, which D5 leaves unchanged.
