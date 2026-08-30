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

**The two clocks cannot cross, and the ordering is why** (established round 2, because D4's refusal
depends on it and nothing said so). The Hub stamps `wait_expires_at = now + wait_seconds` while
serving the ask; the tool computes `deadline = time.monotonic() + QUESTION_ANSWER_TIMEOUT`
*after* that request returns (`hub/hub/mcp_server.py:354`), and its poll loop sleeps
`QUESTION_POLL_SECONDS` before its first check. So the tool's real expiry is always **later** than
the deadline the Hub recorded, by at least a round trip. The refusal in D4 can therefore reject a
forged early report but can never reject a genuine one — which is what makes "refuse a report that
arrives before the deadline" safe rather than a race.

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

## D5 — Resuming a wait is not gated, and that reverses a shipped requirement

`apply_transition` runs the dependency gate on every `-> in_progress` edge, `blocked -> in_progress`
included — deliberately, and the code says so: `task_transition_service.py:370-378` names "the
`blocked -> in_progress` resume edge" and cites `task-dependencies` design D1, whose diagram spells
it out. Today `release_block_for_question` swallows the refusal, so an answer can fail to release a
task whose prerequisite regressed while it waited, silently. The window is short and nobody has hit
it.

Half (a) makes the window the whole wait. Half (b) makes the release the thing that lets the agent
finish: refused, the agent's `update_task(completed)` comes back `409` from `blocked`, for a task it
has genuinely completed, with no action available to it.

**So the gate skips this edge — and because that is a shipped rule, this change carries deltas for
both places it is written.** `task-dependencies`' requirement *An unmet dependency prevents starting
and nothing else* carries the scenario *Resuming is gated the same way as starting*
(`openspec/specs/task-dependencies/spec.md:76`); `task-lifecycle-governance`'s *Starting work is
gated on its prerequisites* (`:1193`) states the placement half. Round 1 modified only the second and
left the first standing, which would have archived a corpus stating both rules at once —
`openspec validate --strict` does not compare capabilities and passed either way. Round 2 added the
`task-dependencies` delta.

Three facts carry the reversal, and only the first was in round 1's argument.

1. **The gate asks whether work may start, and `blocked` is reachable only from `in_progress`**, so
   this work started.
2. **Every refusal at this edge is a change that happened after the task started.** The way *into*
   `in_progress` is the gated edge, so a waiting task cleared the gate on the way in. A prerequisite
   can therefore only be unmet on the way out because it left `approved` during the wait, or was
   declared during the wait. The first case is governed by the shipped requirement *A dependency that
   regresses after a dependent has started does not halt it* (`task-dependencies:105`) — "the
   dependent SHALL continue, and the situation SHALL be surfaced". The current gate stops it. So the
   ungating **restores** that requirement at this edge; it does not trade it away.
3. **The scheduler already made this decision, the opposite way from the transition service.**
   `candidate_is_startable` (`hub/hub/scheduler.py:619-625`) exempts `blocked` from the same
   `dependency_gate.evaluate` call with this argument in these words: *"nothing is about to
   transition it either — it is waiting on a person. Gating it would be asking whether work that is
   not about to start is allowed to start."* The board and the gate contradict each other today at
   exactly one edge, and `task-dependencies` human check 13.1 is that the firing and the board never
   disagree about a queue item. This is the change that makes them agree.

**The consequence, stated rather than left to be found.** A dependency *declared* while a task waits
(`task-dependencies:262` — "the existing gate SHALL apply to B unchanged") will no longer stop that
task resuming. That is the honest cost, and it is small: the work is already under way, so the gate
could not have prevented it, only the record of it. It surfaces as `running_on_regressed` on the
task once the release lands, which is where a dependency problem on started work already belongs.

**Mechanism.** Derived from the task's status inside the transition service — `from_status` is
already captured at the top of `apply_transition` — rather than from a flag the caller passes. A flag
would be one more thing a caller can forget and one more thing a caller can abuse; the status at the
transition already carries the whole fact, and it is sufficient precisely because the rule is
unconditional. All three releases — answer, decline, expiry — get it that way, which is right: the
reasoning does not distinguish them, and leaving two of them gated would be an inconsistency nobody
could explain later.

**Coupled to the `dependency_state` fix (proposal, task 3.5), in both directions.** Teaching the
board to read a waiting task as `running_on_regressed` — "flagged, not stopped" — while the gate can
still stop it permanently would make the board state something false. Ungating without the board fix
leaves a resumable task rendered as `gated`. Neither half is shippable alone.

**A shipped test asserts the old rule** and the implementation must overturn it, not work around it:
`hub/tests/test_dependency_gate.py:185` `test_the_blocked_resume_edge_is_gated_the_same_way`, plus
that module's own docstring and the section comment at `:155`. Its sibling
`test_the_blocked_resume_edge_succeeds_once_the_prerequisite_is_approved` stays true and stays.

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

## What round 2 overturned

Round 2 re-derived the proposal against the code rather than re-reading round 1. Recorded here
because the next round should attack these conclusions, not rebuild them.

| Round 1 said | Round 2 found |
|---|---|
| Ungating `blocked -> in_progress` needs a `task-lifecycle-governance` delta | It needs **two**. `task-dependencies` states the same rule and carries the scenario *Resuming is gated the same way as starting* (`:76`). Round 1 modified the duplicate and left the original, and `--strict` passed because it does not compare capabilities. Delta added; D5 rewritten |
| The ungating is justified by "the gate asks whether work may start" | True but the weakest of the three available arguments. Round 2 added: every refusal at this edge is necessarily a *post-start* change, so the shipped *A dependency that regresses … does not halt it* already governs it and the current code **breaches** it; and `scheduler.candidate_is_startable` already exempts `blocked` in the same words, so board and gate disagree today |
| (unstated) | A dependency **declared** during a wait will no longer stop the resume (`task-dependencies:262`). Stated as the honest cost, with a test (7.6) |
| Task 3.5 (`dependency_state`) is an independent fix | Coupled to group 7 in both directions. Either alone makes the board state something false |
| Task 2.8: an `under_review` task's question "still records `blocked_task_id`" | **Wrong about the code.** `block_task_for_question` records it only when the task is already `blocked` (`run_task_binding.py:625-628`) — and that is correct, since `run-task-binding:663` is scoped to a task *already waiting*. Assertion inverted; D2's "reused unchanged" survives |
| Two comments state the retired fact | **Four**: the two backend ones plus `hub/ui/src/api/tasks.ts` and `TaskCard.tsx` |
| (unstated) | The park needs its own **commit**, because `ask_question_for_actor` already committed; and the ask must survive a park that raises |
| (unstated) | `hub/tests/test_dependency_gate.py:185` asserts the old rule and must be overturned by name (7.5), along with two gate docstrings |

Re-derived and **confirmed**, so a later round can spend its budget elsewhere: the transition map
needs no edit and `blocked -> completed` stays absent (`task_transitions.py:113-133`);
`_guard_run_holds_the_task` does not fire on `-> blocked` and takes its no-op branch on the expiry
release, because the run is already bound; the batch parks once and records the rest through the
already-blocked branch; `release_reason` is reached on both existing exits (`tasks.py:1183`, shared
by the operator and agent PATCH routes, and `run_task_binding.py:687`); `expired` rather than
`unanswered` is the right list at `mcp_server.py:411`, and a decline leaves the wait early and is
never marked; and all seven "safe" rows of the proposal's blocked-while-running table hold, with the
UI needing no behavioural change because `TaskCard` already coalesces the two reasons.
