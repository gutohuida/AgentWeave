# Design

## Context

`ask_user` is the operator-in-the-loop path and it works: the question is structured, the answer
reaches the agent, and the turn resumes. What does not work is what the *task* says while that is
happening, and what it says afterwards when nobody answered.

Two findings, one mechanism. F14 is the wait being invisible; F60 is the wait ending in silence.
The operator decided on 2026-08-30 to fix both in one change, because F60's half has nowhere to
live until F14's half puts the task in `blocked`.

## D1 — The park happens in the questions route, not in the tool

`ask_user` runs in `hub/hub/mcp_server.py`, which may import only stdlib and fastmcp and reaches the
Hub over HTTP. Everything about the park — the transition machine, the actor, the reason text, the
event — lives in the Hub. So the park is Hub-side, in the agent-facing question routes
(`hub/hub/api/v1/agent_actions.py`: `ask_operator_question` and `ask_operator_question_batch`),
using the `AgentActor` those routes already resolve.

Not in `ask_question_for_actor`: that helper is shared with the **operator-facing** `POST
/questions`, which has no run and no binding, and a park there would be a park with no asker.

Not in the operator-facing route at all. A question the operator writes is not an agent waiting.

## D2 — `block_task_for_question` is reused unchanged, not reimplemented

The function already does exactly the right thing and already has the two branches a batch needs:

* the map permits `blocked` → transition, write `blocked_reason`, record `blocked_task_id`;
* the map does not (the task is `under_review`, `pending`, or already `blocked`) → record
  `blocked_task_id` if already blocked, and otherwise leave everything alone.

That second branch is what satisfies `run-task-binding:663` for the second and later questions of a
batch, and it is why a batch parks once and records four times without a line of new logic.

It keeps `origin=ORIGIN_RUNTIME` and `run_actor(run.id, run.agent)`. `run_advanced_its_task` counts
only `origin=ACTOR`, so parking a task does not make the run look like it moved its own work.

`_announce_block` moves from `run_divergence.py` to `run_task_binding.py` beside the function it
belongs to, because it now has two callers. It stays `info`, not `warn`, for the reason its own
docstring gives: this is the mechanism working.

## D3 — The deadline is supplied by the tool, and the Hub stores it

`QUESTION_ANSWER_TIMEOUT` is resolved in `mcp_server.py` from `AW_QUESTION_TIMEOUT` with a default
of 240. The Hub sets that env var from `Agent.question_timeout_seconds`
(`agent_trigger.py:973-974`) **only when it is not null**, so the Hub does not know the effective
value and cannot compute the deadline. Restating the 240 default Hub-side would create a second
source of truth for a number that is already awkwardly split.

So the ask carries `wait_seconds`, and `Question` grows `wait_expires_at`. This is a durable record
of how long the operator actually had, which is what makes half (b)'s statement honest rather than
merely accusatory.

`wait_seconds` is optional. `blocking=False` sends none and gets none; an older tool sending none
gets a null deadline, and a null deadline refuses every expiry report — the safe direction.

## D4 — The end of the wait is a report, not a lever

`POST /questions/wait-ended` on the agent-facing router, taking the batch's question ids. It is not
an `@mcp.tool()`, so it is not in the agent's capability surface and no model can be prompted into
calling it; `ask_user` calls it directly over the same authenticated channel it already uses.

It refuses, per question:

* a question whose `created_by_run_id` is not the calling run — you may only report your own wait;
* a question with no `wait_expires_at`, or whose `wait_expires_at` has not passed — the report must
  describe a fact, not create one;
* a question already answered or declined — nothing expired.

Everything surviving those gets `wait_ended_at` set. Then, once, the task is released if it is
`blocked`.

**Why a report and not a Hub-side sweep.** A sweep would need a timer, would fire whether or not the
agent was still there, and would release a task on a clock while the tool was still waiting because
its own deadline had not passed. The tool knows the moment it stops waiting; that is the fact worth
recording.

**Why the endpoint is not dangerous.** The worst a hypothetical forged call can do is release a
block early and mark the question as proceeded-without-an-answer — which is a *truthful and
unflattering* record, not a way to look clean. There is no version of this call that hides
something.

## D5 — Resuming a wait is not gated

`apply_transition` runs the dependency gate on every `-> in_progress` edge, `blocked -> in_progress`
included. Today `release_block_for_question` swallows the refusal, so an answer can fail to release
a task whose prerequisite regressed while it waited, silently. The window is short and nobody has
hit it.

Half (a) makes the window the whole wait. Half (b) makes the release the thing that lets the agent
finish: refused, the agent's `update_task(completed)` comes back `409` from `blocked`, for a task it
has genuinely completed, with no action available to it.

So the gate skips the `blocked -> in_progress` edge, **derived from the task's status inside the
transition service** rather than from a flag the caller passes. A flag would be one more thing a
caller can forget and one more thing a caller can abuse; the status at the transition already
carries the whole fact. The justification is the gate's own: it asks whether work may **start**, and
`blocked` is reachable only from `in_progress`, so this work started.

All three releases — answer, decline, expiry — get it that way, which is right: the reasoning does
not distinguish them, and leaving two of them gated would be an inconsistency nobody could explain
later.

This does not weaken `task-dependencies`: the gate still guards every edge that *begins* work.

## D6 — An expired wait is not an open one

`unanswered_blocking_question` is the shared predicate for "this run is waiting on a person". It
selects `blocking AND NOT answered AND NOT declined`. A question whose wait ended still satisfies
that, which would make a timed-out run park its task at the run boundary and suppress a divergence
that is real — the agent proceeded, then dropped the work, and the record would say it was waiting.

So the predicate gains `wait_ended_at IS NULL`, and both readers inherit it:
`evaluate_run_end`'s park, and `tasks.py`'s `_attach_awaiting_answer`.

## D7 — The mark is derived, and permanent

Durable: `Question.wait_ended_at`. Derived: a task-response field stating that this work proceeded
without the operator's answer, computed from a question with `blocked_task_id == task.id` and
`wait_ended_at IS NOT NULL`.

Derived rather than stored, matching `awaiting_answer_reason`, `has_open_divergence` and
`dependency_state` — the question row is the record, and a copy on the task is a second thing that
can disagree with it.

**Permanent rather than clearable.** The condition is `wait_ended_at IS NOT NULL` alone: not
"and still unanswered". F60 measured the operator answering the question five minutes after the run
ended, choosing the option the agent did *not* ship. If the answer cleared the mark, the record of
the unilateral call would disappear at the exact moment it became most misleading — the question
would read answered, the task would read clean, and the code would carry a decision neither of them
names.

A **declined** question is not marked. The tool returns early on a decline rather than waiting out
the deadline, so `wait_ended_at` is never set, and that is right: a decline is a decision the
operator made and handed back, not silence.

## D8 — Text

`reason_from_question` produces "Waiting on your answer: …" and is shared by the park and the
derived wait so two surfaces cannot spell the same wait differently. Half (b) gets a sibling in the
same module producing "Proceeded without your answer: …", trimmed by the same limit, for the same
reason.

## D9 — `awaiting_answer_reason` stays

Its stated rationale stops being true and its comment must be corrected, but the field still earns
its place twice:

* a run bound to a task that **cannot** park — `under_review`, `pending`, `assigned` — still waits,
  and only this reports it;
* a batch where one question is answered releases the task while the run waits for the rest (see the
  proposal); only this reports the remaining wait.

## Alternatives rejected

**Add `blocked -> completed`.** Cheapest by far, and it is the one thing
`task-lifecycle-governance:413` explicitly forbids, in a sentence written to prevent exactly F60's
record. Adding the edge would make the machine able to state, in history, that a task was completed
while waiting on a person who never answered.

**Leave the lifecycle alone and render `awaiting_answer_reason` more prominently.** Recorded as
rejected in F14: smaller, touches no transitions — and F60 measured the run-end fallback failing in
precisely the case that matters, so a more prominent secondary field still leaves a timed-out
question ending as a clean completed task.

**A Hub-side expiry sweep.** See D4.

**Release on answer only when the run is no longer waiting on anything else.** Contradicts the
shipped `run-task-binding:684`, which was written to fix the opposite defect. Not re-decided here.

## An adjacent defect, observed and not fixed

`scheduler._pending_loop_request` (`hub/hub/scheduler.py:376-382`) selects the loop's outstanding
question with `Question.answered == False` and **no `declined` exclusion** — so a question the
operator explicitly closed is still reported as what the loop is waiting on. Every other reader of
this predicate excludes `declined`, for the reason `2026-08-11-declining-a-question` D3 gives.

Out of scope: it is about a loop's stop reason, not about a task's status, and folding it in would
put an unrelated fix inside a change whose reproduction cannot cover it. Recorded here so it is not
lost.
