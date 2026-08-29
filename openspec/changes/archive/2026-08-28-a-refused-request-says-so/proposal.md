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
queued. Two queue entries were left stranded in `aw-e2e1` by the drive that found it, which is the
only reason it was visible at all.

F108 says it stays open as a class, and names four examples: an archived agent, a task that does not
exist, an unimplemented runner, and a `work_dir` the project does not contain. **Round 2 checked
each against the route and none of the four survives** — three are already refused before the entry
is queued and the fourth cannot be reached through the API at all (see *Round 2* below). The class
is real, but it is not the one F108 described, and the two sections after that one say what it
actually is.

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
`ScheduleResult.terminal_failure` defaults to `True` (`turn_scheduler.py:33`), and six early-return
sites carrying these five reasons take the default without meaning it (`"hop budget exhausted"` is
returned from two places, `:73` and `:108`):

| Return | `terminal_failure` | What it actually means |
|---|---|---|
| `"queue is empty"` | `True` | A concurrent re-drain already took this entry. **The request succeeded.** |
| `"hop budget exhausted"` | `True` | Depth limit on *some* entry in the queue |
| `"queued entry has no conversation"` | `True` | A defect state in another entry |
| `"conversation is unavailable"` | `True` | Closed/foreign conversation — possibly not this one |
| `"token budget exhausted"` | `True` | Budget resets; autonomous-initiated turns only |

`"queue is empty"` is the sharpest: the route commits its entry at `:1260` and calls
`schedule_agent` at `:1273`, and `redrain_queued_agents` runs at the end of every turn, so a re-drain
in that window can deliver the entry and leave the scheduler truthfully reporting an empty queue. A
route that errors on `terminal_failure` would then return a failure for a request that worked.
**Round 2 measured how narrow that window is** — `schedule_agent` holds a per-agent lock, so the
re-drain's run must also have *finished* — and the design no longer rests on it: see D2.

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

### Round 2: three of F108's four examples are already refused, and the fourth is unreachable

Round 1 took F108's example list at face value. Round 2 read the route from its first line and
found that `POST /agent/trigger` **already hoists most of them ahead of the queue write**:

| F108's example | Where it actually lands today |
|---|---|
| an archived agent | **409 pre-queue**, `agent_trigger.py:1108-1115` — `test_trigger_refuses_an_archived_agent` asserts it |
| a task that does not exist | **409 pre-queue**, `:1173` `resolve_task_for_project`, and `:1199` for the review target |
| a `work_dir` the project does not contain | **400 pre-queue**, `:1134-1138` `Invalid work_dir:` |
| an unimplemented runner | **unreachable** — `Runner.cli` is schema-constrained to `claude`/`codex` since runner-agent-charter-separation, and `test_agent_trigger.py:2058` records the deletion of the test that used to reach the 501 |

Together with F76's three review guards at `:1214`, the route's pre-queue list also mirrors an
invalid agent name (`:1097`), an unavailable project workspace (`:1118`), a `work_dir` overriding
isolation for a writing agent (`:1125`), an unavailable conversation (`:1149`) and a decided task
(`:1191`).

**This is the same failure the round discipline exists to catch, one level up.** F108's *observation*
is correct and reproduced; its "open as a class" paragraph enumerated a class without checking
whether the route already answered it, and round 1 inherited the list without checking either. Left
alone, this change would have shipped a mechanism whose named cases could not fire — this
repository's dominant failure mode, arrived at from the specification end rather than the code end.

### What *is* still reachable, and it is a better reason than the one F108 gave

Two populations survive the pre-queue guards.

**1. Conditions with no pre-queue mirror at all.**

| Condition | Site | Why the route cannot see it at request time |
|---|---|---|
| the named agent is not in this project at all | `:452` | The route's archived check reads `Agent.lifecycle` and a missing agent simply yields `None`; nothing else asks whether the roster has the name. The raise site's own comment records this measured live: *"a job for a mistyped agent reported 'has no runner bound' every five minutes"* |
| `work_dir` combined with a review turn | `:591` | The route validates `work_dir` and validates the review target, never the combination |
| a turn batching two review targets, or mixing a review with work | `:337`, `:351` | Only exists once the *scheduler* batches this entry with others; no single request can be checked for it |

**2. Every hoisted guard is time-of-check/time-of-use.** The pre-queue guards run when the request
arrives; the entry is delivered when the agent is next idle, which the queue makes arbitrarily
later. A review dispatched against a task that was awaiting review at `:1214` meets `:643` at
dispatch when another reviewer took it in between — and the operator is told `200 … "queued"`.

That second population is the durable justification, and it is stronger than F108's: hoisting more
guards can never close it, because the gap is time, not coverage. It is also the reason the
pre-queue guards stay exactly as they are — they answer the common case with no queue residue at
all — and this change is the backstop behind them.

### Round 2: "non-transient" is the wrong gate

Round 1 proposed refusing whenever the scheduler's refusal is non-transient. Reading all 25
`TriggerAgentError` raise sites shows that population contains two different things, and refusing
the first would reverse decisions this product made deliberately and still tests:

- **no runner is bound** — `test_unbound_agent_accumulates_queue_with_visible_reason` states it as a
  decision in its own docstring: *"it queues with a stated reason rather than failing the request
  outright"*, and **F96** (`test_runner_binding_redrain.py`) exists so that binding the runner
  *delivers that very entry*. Refusing and withdrawing it deletes F96's fix.
- **the bound runner's CLI is not on PATH** — `test_runtime_diagnostics.py` asserts `200 … "not
  found in PATH"` for the same reason.

Those refusals are about the *environment*, and queuing is the product's answer to them. The
refusals F108 is about are about the *request*. Design D10 makes that the gate, asked directly on
`TriggerAgentError` the way `transient` already is, and defaulting to "not request-level" so that
no existing behaviour changes except where this change marks a site.

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

0. `TriggerAgentError` gains an explicit *request-level* classification, defaulting to `False`, and
   the raise sites that describe the request rather than the environment set it (D10). Nothing
   changes for an unmarked site.
1. `ScheduleResult` gains what the route needs to attribute a refusal: the ids of the entries the
   refusal applies to, and the refused status code. Both already exist inside `schedule_agent` —
   `selected` and `TriggerAgentError.status_code` — and are discarded on the way out.
2. `POST /agent/trigger` refuses with the error's own status and sentence **only** when the
   scheduler's refusal is request-level *and* names this request's own entry. Every other outcome
   keeps today's `200 … "queued"`.
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
- **Environment-level refusals.** No runner bound, a CLI missing from PATH, a worktree that could
  not be prepared: all keep today's `200 … "queued"` with the remedy stated, and their entries keep
  waiting to be delivered once the remedy is performed (F96). D10.
- **The route's pre-queue guards.** Nine of them, listed above. This change adds none and removes
  none; it is what answers the cases they structurally cannot see.

## Open questions for review rounds

- **R2/R3 must check:** whether `"queue is empty"` and the other four defaulted-`True` returns
  should have `terminal_failure=False` set explicitly. The flow consumers at `scheduler.py:2446`
  and `:2585` gate on that same flag, so a job run may be being marked `failed` today because a
  re-drain won a race. That is a *third* candidate defect, out of scope here, and it must be filed
  rather than fixed in passing.
- Whether withdrawing the refused entry (item 3) is right, or whether it should be left for
  `DELIVERY_ATTEMPT_LIMIT` to abandon with its existing bookkeeping and its
  `queue_entry_abandoned` event.
- **Answered in round 2, recorded here:** whether `"queue is empty"` is reachable after the route's
  own commit. It is, but only as a race — `schedule_agent` holds a per-agent lock, so a concurrent
  re-drain must finish first, and its run must *also* have ended before this call reads the queue.
  D2 no longer rests on it.
- **Raised by round 2, for round 3:** whether `:452` ("is not an agent in this project") is
  request-level or environment-level. Creating the agent would make the entry deliverable, which is
  the environment-level shape; but the operator named something that does not exist, which is the
  request-level shape. This change treats it as request-level, on the ground that the remedy is to
  correct the request, and the raise site's own wording leads with *"correct the name"*.
