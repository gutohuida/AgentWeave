# A refused request says so

## Why

`POST /agent/trigger` answers `200 {"success": true, "status": "queued"}` to a request that can
never succeed. The refusal's own sentence is delivered — correct, complete, and in a field named
`waiting_reason`, under a flag saying the opposite:

```
POST /agent/trigger {"agent": "builder", "review_task_id": "task-c351c35eb718"}
  -> 200 {"success": true, "status": "queued",
          "waiting_reason": "Cannot move task ... to 'under_review': it is still assigned to
                             'builder', the agent recorded as completing it, ..."}
```

This is finding **F108**, filed 2026-08-28 by the live drive of F76's own fix, and closed there for
exactly one route condition — a review dispatch, by asking F76's three questions before anything is
queued. It is open as a class: an archived agent, a task that does not exist, an unimplemented
runner, and a `work_dir` the project does not contain all still answer the same way. Two queue
entries were left stranded in `aw-e2e1` by the drive that found it, which is the only reason it was
visible at all.

### The finding's proposed mechanism is wrong

F108's own text says the class fix is "making `turn_scheduler` propagate non-transient refusals".
`turn_scheduler` already does. `ScheduleResult` has carried `terminal_failure` since F56, the
refusal branch sets it from the error's own `transient` classification
(`turn_scheduler.py:229`), and **both** flow consumers already act on it — `scheduler.py:2446` and
`:2585` mark the job run `failed` and record the reason.

The operator's HTTP route is the only caller that throws the classification away. `agent_trigger.py`
reads `scheduled.waiting_reason` at `:1286` and never reads `scheduled.terminal_failure` at all.
So this is an **asymmetry between the flow path and the operator path**, not a missing capability,
and the edit belongs at the route.

This matters beyond bookkeeping: written as the finding proposes, the change would have gone
looking for a mechanism that is already there, and the natural next step — "make the route return
an error when `terminal_failure` is set" — is wrong twice over, as the next section shows.

### Why the obvious fix is a defect

`scheduled.terminal_failure` is **not** a usable proxy for "this request permanently failed", for
two independent reasons. Either one alone would make the naive fix worse than the bug.

**1. The flag defaults to `True` on outcomes that are not failures.**
`ScheduleResult.terminal_failure` defaults to `True` (`turn_scheduler.py:33`), and five early
returns take the default without meaning it:

| Return | `terminal_failure` | What it actually means |
|---|---|---|
| `"queue is empty"` | `True` | A concurrent re-drain already took this entry. **The request succeeded.** |
| `"hop budget exhausted"` | `True` | Depth limit on *some* entry in the queue |
| `"queued entry has no conversation"` | `True` | A defect state in another entry |
| `"conversation is unavailable"` | `True` | Closed/foreign conversation — possibly not this one |
| `"token budget exhausted"` | `True` | Budget resets; autonomous-initiated turns only |

`"queue is empty"` is the sharpest: the route commits its entry at `:1260` and calls
`schedule_agent` at `:1273`. Any re-drain in that window — and `redrain_queued_agents` runs at the
end of every turn — delivers the entry first, and the scheduler then truthfully reports an empty
queue. A route that errors on `terminal_failure` would return a failure for a request that worked.

**2. The scheduler is frequently not talking about this request at all.**
`schedule_agent` picks the conversation of the **oldest eligible entry across the agent's whole
queue**, which the route's own comment at `:1276` already says is "not necessarily the conversation
this request just appended to". The route handles that mismatch on the success path — it rewrites
`waiting_reason` to *"an older conversation's queued input is being delivered first"* rather than
returning another conversation's run.

It does **not** handle it on the refusal path. Today, when the scheduler refuses a turn it was
building for a *different* conversation, this request reports that other conversation's refusal as
its own `waiting_reason`. That is a second defect, unfiled, discovered by this exploration, and it
is in scope here because the fix for F108 has to answer the same question to be correct at all:
*is this refusal about my entry?*

### The operator must not end up worse informed

Three UI call sites reach this route, and two of them discard the server's message today:

| Call site | On a non-2xx |
|---|---|
| `AgentOutputPanel.tsx:672` | `throw new Error("Trigger failed with status " + status)` — **detail lost** |
| `NewConversationSurface.tsx:108` | `setError('Could not start the conversation')` — **detail lost** |
| `api/tasks.ts:365` (`postJson`) | `fetchWithAuth` throws `ApiError(status, text)` — detail preserved |

So changing the status code without changing the first two would trade a *misleading but
informative* message for an *accurate but useless* one. The operator currently at least reads why
the turn did not start. That must not regress, and it is why the UI work is part of this change
rather than a follow-up.

## What changes

1. `ScheduleResult` gains what the route needs to attribute a refusal: the ids of the entries the
   refusal applies to, and the refused status code. Both already exist inside `schedule_agent` —
   `selected` and `TriggerAgentError.status_code` — and are discarded on the way out.
2. `POST /agent/trigger` refuses with the error's own status and sentence **only** when the
   scheduler's refusal is terminal *and* names this request's own entry. Every other outcome keeps
   today's `200 … "queued"`.
3. The refused entry does not stay in the queue re-attempting work the operator has already been
   told failed.
4. A refusal that belongs to another conversation stops being reported as this request's
   `waiting_reason` — it gets the same treatment the success path's mismatch already gets.
5. The two UI call sites that discard the server's message render it instead.

## What does not change

- **The flow path.** `scheduler.py`'s two consumers of `terminal_failure` are correct and untouched.
- **`turn_scheduler`'s classification.** `transient` vs terminal is already right; this change reads
  it, it does not redefine it.
- **F76's three route guards.** They run *before* the entry is queued (`:1214` against `:1257`), so
  they refuse with no queue residue at all — a strictly better shape than propagating a refusal
  after the fact. They stay, and this change is the backstop for every condition that cannot be
  hoisted that way.
- **The five non-`TriggerAgentError` early returns.** They keep answering `200 … "queued"`; making
  their `terminal_failure` default honest is a separate question, recorded below.

## Open questions for review rounds

- **R2/R3 must check:** whether `"queue is empty"` and the other four defaulted-`True` returns
  should have `terminal_failure=False` set explicitly. The flow consumers at `scheduler.py:2446`
  and `:2585` gate on that same flag, so a job run may be being marked `failed` today because a
  re-drain won a race. That is a *third* candidate defect, out of scope here, and it must be filed
  rather than fixed in passing.
- Whether withdrawing the refused entry (item 3) is right, or whether it should be left for
  `DELIVERY_ATTEMPT_LIMIT` to abandon with its existing bookkeeping and its
  `queue_entry_abandoned` event.
