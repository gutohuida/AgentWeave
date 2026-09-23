# Proposal — an agent can be paused, and keeps its input

**Round 1, 2026-09-24** (bundle B3, decision D10, first item). Finding **F15 (C)**, re-verified on
HEAD `404c7d5`. **Nothing here is implemented yet.**

## Why

*"Stopping an agent does not stop the work."* `POST /agent/{agent}/stop`
(`hub/hub/api/v1/agent_trigger.py:1681`) interrupts one run correctly, and the queue starts the next
one moments later if a peer has messaged the agent meanwhile (F15's measurement: `critic` → `builder`
started `run-448817a1` right after the stop). The only other lever, archiving, is refused while a run
is live or any input is queued (`hub/hub/agent_lifecycle.py:25-60`), so an operator racing a chatty
peer cannot win: stop → the queue starts another turn → archive is refused again.

F15 was never decided. Commit `a2424d9` (2026-08-24) records it as *"a missing capability needing a
decision about what a paused agent does with input that arrives while it is paused (queue it, refuse
it, or drop it)"*.

The Hub already has exactly that behaviour for another cause. The **provider hold**
(`a-spent-allowance-holds-the-queue`, `hub/hub/provider_allowance.py:160-215`) makes
`schedule_agent` start nothing for an agent while its input waits **uncounted and not failed**
(`turn_scheduler.py:378-392`), names the hold on the queue status (`api/v1/inbound_queue.py:131-139`),
counts the agent as busy for its loops (`scheduler.py:292-294`), coalesces a plain job's repeat
firings (`scheduler.py:1008-1030`), and keeps it out of a flow's free pool (`scheduler.py:1148`,
`_agents_that_are_free`). A pause is that hold, set by the operator, with no end time.

## What Changes

- **`POST /projects/{p}/agents/{name}/pause` and `/resume`** (operator only; the agent plane gains
  nothing — `agent-capability-plane`'s allowlist). Pause optionally stops the live run in the same
  call (`{"stop_running": true}`), in the order *pause, then stop*, so the queue cannot start a turn
  in between.
- **`Agent.paused_at`** (nullable timestamp; one migration). Separate from `lifecycle`: a paused
  agent stays on the roster and in its conversations; archiving is a different act.
- **One hold read.** A new `agent_hold(db, project_id, agent)` returns the pause if set, else the
  provider hold; the six sites that read `provider_hold` read it instead, and
  `agents_held` includes paused agents. Unlike the provider hold, **operator input does not probe a
  pause** — the operator said stop; their own new message waits with the rest.
- **What input does while paused: it is queued and kept** (the decision F15 asked for). A trigger or
  a peer message answers `queued` with the waiting reason *"<agent> is paused. Resume it to deliver
  queued input."* Nothing is counted against any entry, nothing is withdrawn, and resuming delivers
  in queue order.
- **UI:** a Pause / Resume control beside Stop in the agent header, and "Paused" on the roster row.
  One bundle refresh.

## Capabilities

### Modified Capabilities

- `agent-configuration` — adds the pause requirement.

## Impact

- Migration (next free number), backend in `agents.py`, `provider_allowance.py` (or a new
  `agent_hold.py`), `turn_scheduler.py`, `scheduler.py`, `api/v1/inbound_queue.py`; UI in the agent
  header and roster.
- Interacts with bundle B1/S1 (the attending/free-pool helpers) — see design.
