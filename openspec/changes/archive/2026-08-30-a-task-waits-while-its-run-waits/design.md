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

## D3 — The deadline is the Hub's own, and the ask carries nothing

**Round 3 overturned this decision.** Rounds 1 and 2 had the ask carry `wait_seconds` and the Hub
store it as `wait_expires_at`, on the stated ground that "the Hub does not know the effective value
and cannot compute the deadline". That ground is false, and the design it justified put the guard's
threshold in the hands of the party the guard exists to check.

**The Hub resolves the effective timeout itself, at spawn, today.** `agent_trigger.py:955` builds
the child environment from the Hub's own `os.environ` (or `resolve_agent_env`'s merge of it with the
agent's `env_vars`), then `:973-974` overwrite `AW_QUESTION_TIMEOUT` from
`Agent.question_timeout_seconds` when that column is set. `mcp_server.py:834` reads exactly that
variable through `_configured_wait`, falling back to 240 and to 240 again for anything unparseable
or outside `[10, 600]`. Every input to that resolution is Hub-side: a column the Hub owns, an
environment the Hub built, and a default and range the Hub can restate. So the deadline is
computable at ask time and does not have to be told to anybody.

Restating the default and the range is not a new source of truth — it is the pattern this codebase
already uses at this exact boundary. `mcp_server.py:801-802` restates `MIN_WAITING_SECONDS` and
`MAX_WAITING_SECONDS` under a comment that ends *"A test asserts the two agree"*, precisely because
the module may import only stdlib and fastmcp. One more restated constant with one more agreeing
test is the established cost of that import rule, and it is smaller than the cost of the
alternative.

**Why the alternative was not merely more expensive but wrong.** `wait_seconds` would arrive on the
*agent-facing* ask schema, over the run's own credential — the same channel, the same trust domain
and the same caller as the expiry report. A run that wanted to park and instantly unpark would send
`wait_seconds` at its floor and report immediately; the refusal would compare the report against a
number the reporting party chose. The proposal's crux says the refusal "is what keeps this a report
of a fact rather than a lever", and `task-lifecycle-governance:445` is the requirement it is
keeping. A threshold supplied by the guarded party keeps neither.

So: no `wait_seconds` on any schema, no change to `mcp_server.py`'s ask, and `wait_expires_at`
computed Hub-side while serving the ask, from `Agent.question_timeout_seconds` where set and from
the Hub's own resolution of `AW_QUESTION_TIMEOUT` and its 240 default otherwise.

**It stays a stored column rather than a derivation at report time**, and the reason is not
convenience. The wait belongs to the moment it started: `Agent.question_timeout_seconds` is
operator-editable (`agents.py:1533`'s `WAITING_SETTING_FIELDS`) and can change while the run waits,
and a deadline recomputed afterwards from the current setting would describe a wait that never
happened. Storing it also gives half (b)'s statement the honest number — how long the operator
actually had — without a second derivation. This is the one place in this change where D2's
prefer-derived default is deliberately not taken, and this paragraph is the argument for it.

**The two clocks still cannot cross, and the margin only grew** (round 2 established the ordering;
round 3 re-derived it under Hub-side computation). The Hub stamps `wait_expires_at = now + timeout`
while serving the ask, *before* it commits and responds; the tool computes `deadline =
time.monotonic() + QUESTION_ANSWER_TIMEOUT` at `mcp_server.py:354`, **after** that request returns,
and its poll loop sleeps `QUESTION_POLL_SECONDS` before its first check. So the tool's real expiry
is later than the Hub's recorded one by at least a round trip plus one poll interval. The refusal
can reject a forged early report and can never reject a genuine one. Note that no cross-process
clock comparison is involved at all now: the Hub compares its own `now` against its own stamp.

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

**Why a report and not a Hub-side sweep *alone*.** A sweep by itself would need a timer, would fire
whether or not the agent was still there, and would release a task on a clock while the tool was
still waiting because its own deadline had not passed. The tool knows the moment it stops waiting;
that is the fact worth recording, and it is the primary signal.

**But the report cannot be the only signal, and round 3 found that rounds 1 and 2 had merged two
different cases into one to conclude otherwise.** The proposal's "if the report never arrives"
paragraph, and the ADDED requirement's "Where no such report arrives", both name two causes — the
tool died, the run was killed — and conclude *"nobody proceeded, so nothing has changed"*. There is
a third: **the report was sent and did not land.** Task 5.5 requires exactly that failure to be
swallowed, and it is right to require it — the tool must still hand the agent its answers. In that
case the agent *did* proceed, and the two cases are opposite in every consequence:

| The report | Did the agent proceed? | The task afterwards |
|---|---|---|
| was never sent (process died, run killed) | no | `blocked`, correctly — nobody is working it |
| was sent and failed (Hub 500, connection blip) | **yes** | `blocked`, **wrongly** — its agent is working it and cannot record the result |

The second is not "today's behaviour". Today the task was never parked, so the agent completes it.
After this change the agent's `update_task(completed)` is refused from `blocked`, which is the exact
stranding D5 ungates the resume edge to prevent, arriving through a different door.

So the shipped analogue is followed rather than half-followed. `expire_permission_request`
(`agent_actions.py:765`) is the same fact reported by the same kind of tool over the same channel,
and its docstring states the design in one line: *"The run reports and the run's end sweeps (design
D1), so arriving second is the normal case, not an error."* This change takes both halves.
`evaluate_run_end` already loads the run's outstanding blocking question; where that question's
`wait_expires_at` has passed and it is neither answered nor declined, the wait has demonstrably
ended and the run-end path records `wait_ended_at` and releases, idempotently, exactly as the report
would have. The sweep never fires early, because it only ever runs at a boundary already past the
deadline it checks.

**Why the endpoint is not dangerous.** The worst a hypothetical forged call can do is release a
block early and mark the question as proceeded-without-an-answer — which is a *truthful and
unflattering* record, not a way to look clean. There is no version of this call that hides
something. This is an argument about the *endpoint*, and round 3 wants it read narrowly: it does
**not** extend to the ordinary task route, which offers a way to leave the waiting status that hides
everything. See D10.

## D10 — Leaving the waiting status by assertion is already possible, and this change makes it the obvious move

`task-lifecycle-governance:445` forbids both directions: *"A task SHALL NOT enter **or leave** the
waiting status because an agent asserted that it should."* The code enforces one. `tasks.py:1157`
refuses a non-operator setting `status: blocked`, with a docstring giving the reason, and
`mcp_server.py`'s `TaskStatus` literal withholds `blocked` from the tool surface as a second layer.
**Nothing guards the way out.** `TRANSITIONS["blocked"]["in_progress"]` is `_BOTH`, the PATCH route
applies no equivalent check, and `in_progress` is in `TaskStatus` and named in `update_task`'s
docstring as an ordinary option.

Today that is a latent breach with almost no pressure behind it: a task only reaches `blocked` when
its run has ended, so the agent that could assert its way out is no longer running. **Ask-time
parking removes exactly that protection.** The sequence is short, and an agent following its charter
will find it:

1. the agent asks four blocking questions; its task parks; it waits 240s;
2. `ask_user` returns *"Continue as best you can and say plainly which decisions you made without an
   answer"* — the tool's own instruction to proceed;
3. the agent does the work and calls `update_task(task_id, "completed")`;
4. `blocked -> completed` does not exist, so it gets a 409;
5. the remedy visible in its own tool surface is `update_task(task_id, "in_progress")`, which
   succeeds.

The task then completes with `wait_ended_at` never set and no proceeded-without-an-answer statement
on it. **That is F60 reproduced through the door this change opens**, and it makes the whole of half
(b) — the refused endpoint, the recorded deadline, the permanent mark — bypassable by a call the
agent is already told it may make. Group 7's ungating removes the last incidental obstacle, since
the dependency gate was the only thing that ever refused this edge.

So the guard is mirrored, in the same place and for the same reason as the one on the way in: the
PATCH route refuses a **non-operator** moving a task out of `blocked`, with a message naming what
actually releases it. Nothing legitimate is refused, because no legitimate agent-asserted release
exists — the three real releases are the operator's answer and decline (both `operator()`
attributed, `run_task_binding.py:687`) and the expiry release (run-attributed but `origin=runtime`,
reached from the endpoint above, and passing `_guard_run_holds_the_task`'s `run.task_id == task.id`
branch). The route is the right place because that is where the entering guard lives and why: *"The
map permits the edge to a run because the runtime takes it on the run's behalf; this is what stops
the agent asking for it directly."* The exit needs the identical sentence.

This is stated as part of this change rather than filed separately because half (b)'s ADDED
requirement is unenforceable without it, and because this change is what turns a latent breach into
a reachable one.

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

So the predicate gains `wait_ended_at IS NULL`, and both its readers inherit it:
`evaluate_run_end`'s park, and `tasks.py`'s `_attach_awaiting_answer`.

**Round 3: that predicate has two readers, but the *concept* has four, and two of the other two are
governed by shipped requirements in other capabilities.** `wait_ended_at` introduces a state that
did not exist — a question that is unanswered, undeclined, and nobody is waiting on — and every
surface deriving "somebody is waiting" from `answered = False` now describes it wrongly. Rounds 1
and 2 fixed the two queries this change happens to touch and did not ask what else asks the same
question:

| Surface | Query | After an expiry it says | Governed by |
|---|---|---|---|
| the run-end park | `run_task_binding.py:598` | — fixed by 6.1 | `run-task-binding:594` |
| the task board | `tasks.py:369` | — fixed by 6.2 | this change |
| **conversation navigation** | `conversations.py:424` — `answered.is_(False)` alone | the conversation is **waiting on the operator**, outranking `running`, for the rest of the run | `agent-conversation-workspace`, *A conversation's attention state is visible in navigation* |
| **a loop's open-question count** | `jobs.py:385` — `answered AND declined` | the loop still has an open question | `agent-loops`, *A loop surfaces its current state…* |
| a checkpoint's `open_questions` | `checkpoints.py:293` — `answered` alone | the successor is told the question is open | `conversation-checkpoint` |

The navigation one is the sharpest, because the shipped requirement states its own reason and that
reason expires with the wait: *"The waiting state MUST be distinguishable from the running state,
**because a waiting run consumes its configured timeout while the operator is unaware of it**."*
Once the timeout has been consumed and the run has gone back to work, the conversation reads
"waiting on the operator" — and `conversation_attention`'s docstring says waiting deliberately
outranks running — about a run that is running and waiting for nothing. That is F14's own defect,
inverted, on the conversation rail.

`conversation_attention` also contains its own answer. Its two arms are not symmetric: the
permission arm selects `PermissionRequest.status == "pending"`, which already excludes `expired`,
because permission expiry has been a modelled state since `expire_permission_request` shipped. The
question arm has had no expired state to exclude. This change gives it one, and the arms should
match.

**What each surface does about it is not one answer**, and this change decides them separately:

* **navigation** — excluded. The requirement's own rationale is the consumed timeout, and it is
  spent. A `task-lifecycle-governance` scenario is not the right home for a conversation-rail rule,
  so this carries a small `agent-conversation-workspace` delta saying an ended wait is not an
  attention state.
* **the loop's open-question count** — excluded, for the same reason and with an `agent-loops`
  delta. A count the operator reads as "these still need me" must not include waits nobody is in.
* **the checkpoint** — **kept, and marked.** A successor agent must know the question was asked and
  never answered; dropping it would lose the most useful thing on that list. But it must not be
  called merely open, so the entry carries that its wait ended. This is also what keeps the
  proposal's reason for leaving `LIVE_STATUSES` alone honest — see D11.

The adjacent defect below (`_pending_loop_request` never excluding `declined`) is a fifth reader of
the same family and stays out of scope; it is about a stop reason, not about who is waiting.

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

**Round 3 widened the derivation's first half.** Keying on `blocked_task_id` alone makes the mark
reachable only for a task that actually parked, and `block_task_for_question` records
`blocked_task_id` **only** where the task was `in_progress` (it transitioned) or already `blocked`
(`run_task_binding.py:625-628`, the finding round 2 corrected task 2.8 for). A run bound to a task
in `under_review` asks, waits out the full deadline, decides for itself and carries on — and the
task carries nothing, because it was never parkable. That is F60's own shape with a different
starting status, and the ADDED requirement is written more broadly than the derivation would
deliver: *"Where a task's wait for an operator's answer ended without one"*, not "where a task was
parked".

So the derivation takes the same two-arm shape `_attach_awaiting_answer` already uses
(`tasks.py:371-374`): a question with `wait_ended_at IS NOT NULL` and either `blocked_task_id ==
task.id` **or** asked by a run bound to that task. The second arm drops `_attach_awaiting_answer`'s
`Run.status == "running"` condition, deliberately — that condition is there because a live wait
needs a live run, and this mark is permanent and looks backwards.

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

## D11 — Who is on a blocked task, while a run is on it

Round 3's addition to the proposal's blocked-while-running table, and the one row it did not have.
The table checked the divergence boundary, binding, claim, the loop board, `_free_agents`, the
scheduler's gate bypass, `dependency_state` and `LIVE_STATUSES`. It did not check
**`task_attribution`**, which is the module whose entire job is answering who is on a task — and
which is governed by a shipped requirement with a scenario keyed on `blocked` by name.

`agent-loops`, *An agent attributed to a task SHALL be attributed in a stated capacity*, says two
things that today can never collide:

* *"Whether an agent is mid-turn on a task is answered by the runs the system started"*, and
  `CAPACITY_WORKING`'s own comment is "Something is running against this task right now";
* scenario *A task waiting on a person* — **WHEN** the task is blocked and the name is its own
  assignee **THEN** the surface SHALL present the name as assigned rather than as working. And
  `CAPACITY_ASSIGNED`'s comment: *"Nobody is being selected and nothing is running; this is the
  `blocked` case."*

Ask-time parking makes them collide for the length of every wait, and the code resolves the
collision by accident rather than by decision. `attribute` (`task_attribution.py:176-188`) consults
`live.task_ids` **only inside the `unstaffable` branch**; a `blocked` task is not claimable, so a
firing never records it as unstaffable, and `jobs.py:352` passes empty staffing for the non-flow
path besides. The fall-through therefore reaches `CAPACITY_ASSIGNED` without ever asking the runs —
so for the whole 240s the board states, of an agent that is mid-turn on that exact task, that it is
merely assigned to it. That is the same class of false statement as F14 itself: the board describing
something other than what is happening.

**Decision: `working` wins, and the requirement's scenario is narrowed to say so.** The requirement
names the source that answers each capacity, and for mid-turn it names the runs. A run is running
and it is bound to this task; that is the whole test. `assigned` keeps meaning what its own comment
says — nothing is running — which is still the case the scenario was written for, a task left
`blocked` after its run ended. The wait itself does not need the capacity column to carry it: the
status is `blocked` and `blocked_reason` says what for, and `TaskCard` already renders both.

Mechanically this means `attribute` asks `live.task_ids` before falling through to `assigned`, not
only inside the unstaffable branch. That is a narrower change than it sounds and it does not
re-merge the collections the requirement insists stay separate: `live.task_ids` is the runs table,
`staffing` is the firing, and each still answers only its own question.

**The roster's "active task" is the same decision and gets the same answer, differently.**
`agents._ACTIVE_TASK_STATUSES` derives from `LIVE_STATUSES`, which deliberately excludes `blocked`
— *"a task waiting on a person is not work anyone is presently doing"*. Rounds 1 and 2 left that
alone on the ground that the band classification is a decided answer, and round 3 agrees, but the
proposal's reason for leaving it was that the checkpoint case is covered by `open_questions` — and
D6 has just found that `open_questions` will itself misdescribe an expired wait. The two are now
linked: `LIVE_STATUSES` stays untouched **because** the checkpoint's question list is corrected to
carry the ended wait, not merely because it exists. If that correction is dropped, this row has to
be reopened.

The distinction that makes both answers consistent is worth stating once, since it is what two
surfaces disagreed about: `LIVE_STATUSES` asks *is anyone accountable for this work*, and during a
wait nobody is, which is why `blocked` is out of it. `task_attribution` asks *who is on this task,
and in what relation*, and during a wait an agent's process is suspended inside a tool call bound to
it, which is a relation. Different questions, different sources, and the requirement's own rule —
"no source SHALL be asked a question it does not answer" — is what keeps them from being folded
together.

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

## What round 3 overturned

Round 3 re-derived the proposal against the code again, independently. It attacked round 2's own
biggest lesson — that `--strict` does not compare capabilities, so the question is what *else* in
the corpus this change contradicts without editing — and asked the standing questions: what does a
route return when the thing it calls raises, which two cases have been merged, which scenario can no
surface reach.

| Rounds 1–2 said | Round 3 found |
|---|---|
| The ask carries `wait_seconds` because "the Hub does not know the effective value and cannot compute the deadline" (D3) | **False, and the design it justified is unsound.** The Hub owns every input: `Agent.question_timeout_seconds`, the environment it builds at `agent_trigger.py:955`, and `_configured_wait`'s 240 default and `[10, 600]` range — which `mcp_server.py:801` already shows is the restate-with-an-agreeing-test boundary. Worse, `wait_seconds` would arrive over the run's own credential, so the refusal that "keeps this a report of a fact rather than a lever" would compare the report against a number the reporting party chose. D3 rewritten: Hub-derived, no schema field, no `mcp_server` change |
| "If the report never arrives … nobody proceeded … the failure mode of a missed report is the old behaviour" | **Two different cases merged.** *Never sent* (process died, run killed) and *sent and failed* are opposite: task 5.5 requires the second to be swallowed, so the agent proceeds and the task is left `blocked` with its own agent unable to record the work — which is not the old behaviour, and is the stranding D5 exists to prevent. The shipped analogue in the same router already solves this with two signals: `expire_permission_request` — *"The run reports and the run's end sweeps."* A run-end sweep added (D4, group 5a) |
| The whole of half (b) is protected because the report is refusable and not in the tool surface | **Bypassable in one advertised tool call.** `task-lifecycle-governance:445` forbids leaving the waiting status by assertion as well as entering it; only entering is enforced (`tasks.py:1157`). `blocked -> in_progress` is `_BOTH`, unguarded at the route, and `in_progress` is in `mcp_server`'s `TaskStatus`. The agent that waits out its deadline, is refused `blocked -> completed`, and moves itself to `in_progress` reproduces F60 with no mark. Latent today because `blocked` implies no running run; ask-time parking removes exactly that. New D10, new group 2b |
| "Every reader of task status was checked" (the blocked-while-running table) | **`task_attribution` was not**, and it is the one with a shipped scenario keyed on `blocked` by name. `attribute` consults the runs only inside its `unstaffable` branch, so for the whole wait the board calls an agent that is mid-turn on the task merely `assigned`. New D11, new group 3a |
| "Both readers of that predicate must exclude a question whose wait has ended" (D6) | **The predicate has two readers; the concept has five.** `conversations.py:424` (navigation's waiting state, whose shipped rationale is the consumed timeout), `jobs.py:385` (a loop's open-question count) and `checkpoints.py:293` (`open_questions`) all derive "somebody is waiting" from `answered = False`. Two carry requirements in other capabilities. D6 rewritten with a decision per surface and two new deltas |
| The mark is derived from `blocked_task_id` and `wait_ended_at` (D7) | **Narrower than its own requirement.** `blocked_task_id` is recorded only where the task parked, so a run whose task was `under_review` waits out the full deadline, decides for itself, and the task carries nothing. Derivation widened to `_attach_awaiting_answer`'s two-arm shape |
| The run-end park still covers "a question asked in an earlier turn" | **That case is excluded by design.** `unanswered_blocking_question` selects `created_by_run_id == run.id`, and its own docstring says why: *"A question another run left unanswered is not evidence that this run stopped for it."* An earlier turn is an earlier run. The other stated case — a task not `in_progress` at ask time — is near-unreachable, since binding drives a task to `in_progress` and the statuses that refuse the park have no path back without the operator. The fallback's real remaining job is the one nobody listed: a park that raised and was swallowed (task 2.2) |

Round 3 re-derived and **confirmed**, against the code rather than against round 2's prose: the
batch releasing on the first answer is genuinely covered by `awaiting_answer_reason`, because
`block_task_for_question`'s already-blocked branch records `blocked_task_id` on every later question
of the batch and `_attach_awaiting_answer`'s first arm (`tasks.py:372`) matches on exactly that, with
`setdefault` over `ORDER BY created_at, batch_index` naming the earliest still-unanswered one; and
`_guard_run_holds_the_task` takes its `run.task_id == task.id` no-op branch on the expiry release,
so a run-attributed `blocked -> in_progress` is not refused there.

Re-derived by round 2 and **confirmed**, so a later round can spend its budget elsewhere: the transition map
needs no edit and `blocked -> completed` stays absent (`task_transitions.py:113-133`);
`_guard_run_holds_the_task` does not fire on `-> blocked` and takes its no-op branch on the expiry
release, because the run is already bound; the batch parks once and records the rest through the
already-blocked branch; `release_reason` is reached on both existing exits (`tasks.py:1183`, shared
by the operator and agent PATCH routes, and `run_task_binding.py:687`); `expired` rather than
`unanswered` is the right list at `mcp_server.py:411`, and a decline leaves the wait early and is
never marked; and all seven "safe" rows of the proposal's blocked-while-running table hold, with the
UI needing no behavioural change because `TaskCard` already coalesces the two reasons.
