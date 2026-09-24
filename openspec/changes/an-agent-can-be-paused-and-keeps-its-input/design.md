# Design — an agent can be paused, and keeps its input

**Built on the recommended answer to D10/F15**: *build a pause; input that arrives while paused is
queued and kept, uncounted, and delivered on resume.* **If the operator answers otherwise** — "no
pause, stop and archive are the levers" — this change is withdrawn and F15 closes as decided; the
documented remedy then is *stop, withdraw each queued entry (`DELETE /queue/entries/{id}`), archive*,
which still loses the race against a peer that messages between the steps.

## Context — re-verified on HEAD `404c7d5`

- No pause exists: `grep -rn "paused" hub/hub/db/models.py` finds only job/loop pause; `Agent` has
  `lifecycle` (`open`/`archived`, `agent_lifecycle.py:22`) and nothing else.
- `stop_agent_run` (`agent_trigger.py:1681-1700`) terminates the one running run; it does not touch
  the queue, and the run's end schedules the next turn.
- `archivable` (`agent_lifecycle.py:25-60`) refuses while a run is live **or** any entry is queued.
- The provider hold, which this design reuses, is read at six sites (`grep -rn provider_hold hub/hub`):
  `turn_scheduler.py:388` (start nothing, `terminal_failure=False`), `api/v1/inbound_queue.py:135`
  (status sentence), `scheduler.py:292` (a loop's busy guard), `scheduler.py:1018` (a plain job's
  coalesce), `api/v1/jobs.py:1354` (the Run button's in-flight answer, `_held_in_flight_reasons`), and
  `provider_allowance.agents_held` → `scheduler._roster_availability` `:1148` (the free pool and the
  reviewer ladder).
- **R2: seven, not six.** `agents_held` has a second caller, `scheduler.py:1705`, in the loop's candidate
  walk (it keeps a loop from briefing a held agent's assigned task again). And `agents_held` only
  enumerates agents that have a `TurnUsage` row (`provider_allowance.py:171-189`), so *"`agents_held`
  includes paused agents"* needs a second query — `Agent.paused_at IS NOT NULL` for the project — unioned
  in; an agent paused before its first turn has no usage row and would otherwise be missed at both
  callers. `trigger_agent_directly`'s only caller is `turn_scheduler._attempt_turn` (`:408`), so the
  `:388` read does gate every spawn.

## D1 — What a paused agent does with input (the F15 question)

| Option | Effect | Verdict |
|---|---|---|
| **Queue and keep** | entries wait uncounted; resume delivers in order | **recommended** — the product's standing promise is that input the Hub accepted is kept until a repair delivers it (F96, F114's `agent_wide` reasoning at `turn_scheduler.py:~545-560`); a pause is the operator's own "repair pending" |
| Refuse | senders get 409; peers must retry later | loses a peer's message the peer has already moved past; contradicts `agent-capability-plane`'s archived-agent rule, which refuses only because *nothing will ever run* the agent |
| Drop | withdraw on arrival | destroys input silently; rejected |

## D2 — A pause is a hold, read where the hold is read

Rather than add a sixth kind of refusal, a pause is expressed as the hold the Hub already has:

```python
async def agent_hold(db, project_id, agent) -> Optional[Hold]:
    """Why this agent's queue is held: the operator's pause if set, else the provider's."""
```

returning a small union (`PauseHold(since)` | `ProviderHold`). Each of the seven sites calls it and
branches on the kind only for its sentence. Two deliberate differences from a provider hold:

1. **Operator input does not probe a pause.** `operator_would_probe` exists because only the operator
   can change a provider allowance and the hold cannot see that they did. A pause is the operator's
   own setting; their new message waits with the rest. (An operator who wants it delivered resumes.)
2. **No wake is scheduled.** A pause has no end time; `resume` calls `schedule_agent` once.

Why not a `TriggerAgentError(agent_wide=True)` at `trigger_agent_directly` instead: the provider
hold is checked in `_attempt_turn` **before** the trigger (`turn_scheduler.py:388`), and every other
consumer (busy guard, coalesce, free pool) reads the hold, not the trigger's refusal. Putting the
pause at the trigger would leave the flow staffing a paused agent and the loop firing briefings into
its queue every tick — the F368 shape.

## D3 — Routes

- `POST /projects/{p}/agents/{name}/pause`, body `{"stop_running": false}` (optional). Sets
  `paused_at` and commits **first**, **while holding the scheduler's per-agent lock**
  (`turn_scheduler._lock_for(project_id, agent)`, R3); then, if asked and a run is live, calls the same stop path as
  `stop_agent_run`. Answers `200 {agent, paused_at, stopped_run_id}`. Pausing an archived agent: 409
  (archive already stops everything). Pausing a paused agent: 200, unchanged (idempotent).
- `POST /projects/{p}/agents/{name}/resume`: clears `paused_at`, commits, calls `schedule_agent`;
  answers `200 {agent, status}` with the scheduler's result. If `schedule_agent` raises after the
  commit, the route still answers 200 with `status: "resumed"` and a `waiting_reason` saying delivery
  did not start, and logs. (R2: this is a new pattern — no other `api/v1` caller of `schedule_agent`
  catches — and nothing sweeps a queue later; the input waits until the agent is next scheduled by new
  input, the Run button or a Hub start. The answer must say so rather than imply delivery.)
- Both operator-only (`get_project`); neither is added to the agent plane.
- If the stop in `pause` raises, the pause stands (it was committed first) and the route answers 500
  naming the stop failure; the operator's next step — pressing Stop — is the existing route.

**R3 — why the pause takes the scheduler's lock.** `schedule_agent` reads the hold inside
`_lock_for(project_id, agent)` (`turn_scheduler.py:283`, hold at `:388`) and then triggers, which
commits the `Run` before it returns (`agent_trigger.py:1314`). A pause committed without the lock can
land between a pass's hold check and its `Run` commit: that pass starts a turn after the pause, and
with `stop_running` the stop's run lookup (`agent_trigger.py:1689-1695`) can still find no running
run, so it answers "nothing to stop" while a turn starts. Taking the same in-process lock for the
write means any pass in flight has either committed its `Run` (which the stop then finds) or not yet
read the hold (which then sees the pause). The lock is released before the stop is signalled; the
stopped run's end schedules the agent later and waits on the lock normally.

**R3 — the loop's resume arm, and S1.** A held assignee with nothing queued for its task is briefed
once, and one with its briefing queued is recorded in flight (`scheduler.py:1848-1856`). A paused
assignee gets the same: at most one briefing waits in its queue per task; no firing adds another.
B1's `a-task-is-attended-only-by-a-turn-that-will-reach-it` removes the `agent in held_agents and`
qualifier from that arm in favour of *"a queued turn attends the task"*, which keeps exactly this
behaviour, and keeps `held_agents` in the default-agent branch (`:1869-1870`) and the free list
(`:1148`) — the two places a pause must also be read. Tasks 1.6a/1.6b are phrased to hold before and
after S1.

## D4 — What each surface says

| Surface | Sentence |
|---|---|
| trigger / send while paused | `status: "queued"`, `waiting_reason`: *"<agent> is paused. Resume it to deliver queued input."* |
| `GET /queue/{agent}/status` | the same sentence |
| loop firing whose agent is paused | busy guard: *"<agent> is paused"* (same slot as `hold_busy_reason`) |
| flow staffing | the agent is not in the free pool, so the ladder's own "no agent free" reasons apply |
| roster (`AgentSummary`) | a new `paused_at` field; the UI shows "Paused" |

## Interaction

- **`pressing-run-names-the-reason-that-held` (R3, correcting R2's "also edited").** It does not edit
  `_held_in_flight_reasons`' body (`jobs.py:1339-1357`); it reshapes `run_job`'s in-flight answer
  around it (the newest `skipped` row's reason first, F373) and splits `_loop_flow_busy_reason` into
  `_loop_flow_busy_refusal`, which still calls `_agent_busy_reason` (`scheduler.py:292`, where the
  pause is read). Textual adjacency in `run_job` and a sentence shape, not a semantic conflict: a
  paused agent's refused firing records a `skipped` row whose reason names the pause, which is what
  that change then answers. Task 1.7 asserts only `409` and `is paused`, not the sentence around it.
- **`why-queued-input-waits-is-told-truthfully` (B1)** adds a live checkout-holder check to
  `GET /queue/{agent}/status` *after* the provider-hold check (`inbound_queue.py:135-139`); this change
  replaces that hold check with `agent_hold`. Whichever lands second keeps the order: pause/hold first.
- **`request-agent-models-the-new-agent-on-one-the-operator-made`**: whichever lands second refuses a
  paused agent as a template (that change's design D5).
- **B1/S1** rewrites *what counts as attending a task* and the free-pool helpers
  (`_agents_that_are_free`, `on_it`). This change only adds paused agents to the `held` set those
  helpers already exclude; if S1 lands first, re-point task 2.3 at S1's single helper.
- `agents-no-longer-register-themselves` deletes `_job_agent_skip_reason`; this change does not use
  it (a paused job agent is handled by the busy guard and the coalesce, like a provider hold).

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): hold sites re-derived by `grep`: seven, including `scheduler.py:1705`; `agents_held` needs paused agents added by a separate query. The resume route's raise path reworded (no precedent, no sweep). Remaining claims (`stop_agent_run` touches only the run; `archivable` refuses on live run or queued input; operator input probes only a provider hold, `provider_allowance.py:192-202`) hold. `jobs.py:1354` is also edited by `pressing-run-names-the-reason-that-held`, whose text does not mention this change.
- R3 (2026-09-24): hold sites re-counted (seven; no reader outside `provider_allowance`'s importers). Found the pause/scheduler race (pause now written under `_lock_for`); corrected task 1.6a, which asserted against today's resume arm (a held assignee with nothing queued *is* briefed once), and the spec's "no further briefings" to "no second briefing"; corrected the `pressing-run` collision to adjacency; added the queue-status ordering with B1's `why-queued-input-waits-is-told-truthfully` and the paused-template refusal. The resume raise path is confirmed: a raise out of `schedule_agent` means no run started (`agent_trigger.py:1314-1365`, `turn_scheduler.py:692`).
