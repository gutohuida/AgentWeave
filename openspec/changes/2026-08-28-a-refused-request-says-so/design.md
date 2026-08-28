# Design — A refused request says so

## D1. The edit is at the route, not in `turn_scheduler`

F108's own text proposes "making `turn_scheduler` propagate non-transient refusals". It already
does. `ScheduleResult.terminal_failure` has existed since F56 and is set from the error's own
classification at `turn_scheduler.py:229`; `scheduler.py:2446` and `:2585` both read it and mark the
job run `failed`. The operator's HTTP route is the only caller that ignores it.

Recording this because the finding is right and its mechanism is wrong, and following the mechanism
would have produced a change that edits a working component and leaves the broken one alone. Same
shape as F107, whose finding proposed carrying `params` onto `tool_input` when the code already did
and the data was elsewhere.

## D2. Presence of a refusal object, not reinterpretation of `terminal_failure`

The naive route-side test — `if scheduled.terminal_failure: raise` — is wrong, because
`terminal_failure` **defaults to `True`** (`turn_scheduler.py:33`) and five early returns take the
default without meaning it: `"queue is empty"`, `"hop budget exhausted"`, `"queued entry has no
conversation"`, `"conversation is unavailable"`, `"token budget exhausted"`.

`"queue is empty"` is the one that would ship a defect. The route commits its entry at `:1260` and
calls `schedule_agent` at `:1273`; `redrain_queued_agents` runs at the end of every turn, so a
re-drain in that window delivers the entry and the scheduler then truthfully reports an empty queue.
A route gating on `terminal_failure` would answer *failed* to a request that worked.

So `ScheduleResult` gains an optional `refusal` field, populated **only** in the
`except TriggerAgentError` branch and **only** when the error is non-transient. Its presence is the
classification. The five early returns cannot set it, so the defaulted-`True` trap cannot fire —
by construction rather than by a list of exclusions that the next early return would have to be
added to.

`terminal_failure` is left exactly as it is. Rewriting the defaults would change what
`scheduler.py`'s two flow consumers do, and this change has driven none of that.

## D3. A refusal is attributed to entries, and the route refuses only for its own

`schedule_agent` picks the conversation of the **oldest eligible entry across the agent's whole
queue**. The route's own comment at `:1276` says so, and the success path already handles the
mismatch — when the scheduler started a run for a different conversation, the route does not return
that run, it says *"an older conversation's queued input is being delivered first"*.

The refusal path never got the same treatment, so today a refusal raised while building a turn for
**another** conversation is reported to this caller as its own `waiting_reason`. That is a second
defect, unfiled, found by this exploration.

The refusal object therefore carries the ids of the entries it applies to — `selected`, which the
refusal branch already iterates at `turn_scheduler.py:151` to stamp `entry.waiting_reason`. The
route refuses only when its own entry id is among them. One field answers both F108 and the
mis-attribution, because they are the same question asked twice: *is this refusal about my input?*

## D4. The status code comes from the error, not from the route

`TriggerAgentError` already carries the status the condition deserves — 403 for the author-as-own
-reviewer case, 409 for a task in the wrong state, 501 for an unimplemented runner. The refusal
object carries it out unchanged. The route inventing a single code would flatten distinctions the
Hub has already made correctly, and would diverge from what F76's pre-queue guards return for the
same conditions.

## D5. The entry does not stay in the queue after the operator has been told

`transient=False` means the scheduler has classified the refusal as one that cannot clear on its
own. Retrying it is pointless by construction — F108's own observation, that the request "retries
until the abandonment counter gives up", is the waste being removed.

Once this request answers with an error, its entry is withdrawn with a reason naming the refusal, so
the synchronous answer and the queue agree. Without this the operator gets an error *and* the entry
works behind their back, and a `queue_entry_abandoned` event arrives minutes later for a request
that already reported failure.

Scoped to the entry this request created, and only on the path that returns the error. The general
question — whether a non-transient refusal should consume all three attempts for *any* caller —
belongs to the flow path too, which this change has not driven. Filed, not smuggled in.

`schedule_agent` has already incremented `delivery_attempts` and may itself have withdrawn the entry
at the limit, so this step is idempotent: it must tolerate an entry already `withdrawn`.

## D6. A foreign refusal stops being reported as this request's reason

When a refusal exists but names other entries, the route reports that this input is queued behind
another conversation's, mirroring the success path's existing treatment. It does not repeat the
foreign detail, which describes a conversation the caller did not ask about and cannot act on.

## D7. The operator must not end up worse informed, so the UI is in scope

Two of the three UI call sites discard the server's message on a non-2xx:
`AgentOutputPanel.tsx:672` throws `Trigger failed with status <n>`; `NewConversationSurface.tsx:108`
sets `Could not start the conversation`. `api/tasks.ts` is already fine — `fetchWithAuth` throws
`ApiError(status, text)`, which preserves the detail.

Shipping the server change alone would trade a *misleading but informative* message for an
*accurate but useless* one. The operator today at least reads why the turn did not start. Both
sites render the server's sentence.

## D8. What this change must not disturb

- **The flow path.** `scheduler.py:2446` and `:2585` keep reading `terminal_failure` unchanged.
- **F76's three route guards** at `:1214`. They run *before* the entry is queued (`:1257`), so they
  refuse with no queue residue at all — strictly better than propagating after the fact. They stay
  authoritative; this change is the backstop for conditions that cannot be hoisted ahead of the
  queue write.
- **`transient` classification.** Read, never redefined.

## D9. Blast radius on the suite

`waiting_reason` appears 35 times across 13 hub test files. The conditions F108 names each have a
test that asserts today's `200` — `test_archived_send_refusal.py`,
`test_a_decided_task_takes_no_new_work.py`, `test_project_workspace_unavailable.py` among them.
Those assertions change deliberately, and **R2 must enumerate them before implementation** rather
than discovering them as failures: a test that flips from `200` to `409` without anyone deciding it
should is how a behaviour change hides inside a green suite.

## Filed, not fixed here

1. **`terminal_failure`'s defaults are dishonest.** Five early returns claim `True` without meaning
   it, and `scheduler.py`'s two consumers gate on it — so a job run may be being marked `failed`
   today because a re-drain won a race against `"queue is empty"`. Candidate defect, own change.
2. **A non-transient refusal consumes three delivery attempts on every path.** D5 fixes it only for
   the entry whose request is answering with an error.
