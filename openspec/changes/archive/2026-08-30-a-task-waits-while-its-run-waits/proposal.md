## Why

A task parks on an unanswered question **only when the run that asked it ends**, and the whole
point of `ask_user` is the interval before that. `block_task_for_question` has exactly one caller,
`run_divergence.evaluate_run_end` (`hub/hub/run_divergence.py:718`), and `tasks.py:338` restates
the fact in its own comment:

> A task only reaches `blocked` when the asking run *ends* with the question still open —
> `block_task_for_question` is reached from `run_divergence.evaluate_run_end` and nowhere else.

So while an agent sits waiting for a person — minutes, up to `QUESTION_ANSWER_TIMEOUT`, 240s by
default (`hub/hub/mcp_server.py:834`) — its task reads `in_progress` with `blocked_reason: null`.
The board claims the work is progressing while nothing is happening and the answer is on the
operator's desk. That is **F14**, measured live on 2026-08-23 and again on 2026-08-26.

The second measurement is the one that decides the shape of the fix. **F60** polled the live
database every 10s for the full 290s a real Haiku turn ran on `proj-8605b92d0028`: `runs.status`
stayed `running` and `tasks.status`/`blocked_reason` stayed `in_progress`/`None` the entire time.
Then the timeout expired *inside the tool call*, the agent read the spec, made the call itself,
edited the code, ran the tests, and called `update_task(completed)` **in the same turn**. By the
time `evaluate_run_end` ran there was nothing left to park:

```
tasks.status = 'completed'   blocked_reason = None
questions.answered = 0       declined = 0       blocked_task_id = None
```

The board shows a clean completed task. Nothing on it records that a substantive judgment call was
made unilaterally because nobody answered in time. **The run-end fallback fails in exactly the case
that matters most**, which is why the second half ships with the first rather than after it: it has
nowhere to live until the task parks at ask time.

## What changes

Two halves, one change, per the operator's decision of 2026-08-30 recorded under F14 in
`scripts/drive/FINDINGS.md`.

**(a) The park moves to the moment the question blocks.** A blocking question asked by a run bound
to a task parks that task then, not at the run's end. The run-end park stays as the fallback it
already is — for a task that was not `in_progress` at ask time, and, more usefully, for an ask-time
park that failed and was swallowed so as not to cost the agent the question it just asked.

Rounds 1 and 2 also claimed the fallback covers "a question asked in an earlier turn". **It does
not, by design.** `unanswered_blocking_question` selects `created_by_run_id == run.id`, and its own
docstring gives the reason: *"A question another run left unanswered is not evidence that this run
stopped for it."* An earlier turn is an earlier run, so that question is excluded from this run's
boundary check and always was.

**(b) A wait that ends without an answer is recorded, and returns the task to its work.** When the
tool's wait expires and the agent proceeds anyway, the Hub is told, the task returns to
`in_progress`, and the question row keeps a durable mark that its wait ended unanswered. The task
then carries a derived statement — *this work proceeded without your answer* — that survives into
`completed` and `approved`.

## No new task status, and no new edge

`blocked` already exists and works. `src/agentweave/constants.py` declares it, `TRANSITIONS`
(`hub/hub/task_transitions.py:129-133`) gives it `in_progress` for both actor kinds and
`assigned`/`rejected` for the operator, `Question.blocked_task_id` records what to release,
`release_reason` is called on every exit, and `STATUS_BANDS` classifies it into
`BAND_AWAITING_PERSON` with five derived sets already reading that classification. The machinery is
right. **It fires at the wrong moment.**

In particular **`blocked -> completed` stays absent**, and this change is what makes it
load-bearing rather than decorative. `task-lifecycle-governance` already requires it
(`openspec/specs/task-lifecycle-governance/spec.md:413-415`):

> The status SHALL NOT have a direct edge to any status meaning the work is finished. Work that was
> waiting and is now done SHALL pass back through the in-progress status first, so that no recorded
> history states a task was completed while still waiting on a person who never answered.

F60 is that sentence's exact scenario, arriving from a direction the requirement did not anticipate:
the history did not *state* it, because the task never entered `blocked` at all. Half (a) puts the
task in `blocked`, and then half (b) is what the requirement forces — the wait must end
*explicitly*, through `in_progress`, before the work can be recorded as done.

## The crux: what ends a wait, and who says so

Four things end a wait. Three already have a path; the fourth is what (b) adds.

| The wait ends because | Today | After |
|---|---|---|
| the operator answers | `release_block_for_question` → `in_progress`, operator-attributed | unchanged |
| the operator declines | same function, same release | unchanged |
| the asking run ends | the task stays `blocked` — nobody is working on it | unchanged |
| **the tool's timeout expires and the agent proceeds** | nothing; the task was never parked | the task returns to `in_progress`, and the question records that its wait ended unanswered |

The fourth row is the only moment the Hub cannot observe for itself. The Hub knows the run is
running and the question is unanswered; it does not know whether the tool is still waiting. Only
`ask_user` knows, because the deadline is its own (`hub/hub/mcp_server.py:354`).

So **the tool reports the end of its wait**: when the deadline passes with the question unanswered,
it says so before returning to the agent.

**The deadline is the Hub's own, not the tool's report of it.** Rounds 1 and 2 had the ask carry a
`wait_seconds`; round 3 removed it, because the Hub already resolves that number itself — it writes
`AW_QUESTION_TIMEOUT` into the run's environment from `Agent.question_timeout_seconds`
(`agent_trigger.py:973-974`) and owns the 240 default and `[10, 600]` range the tool falls back to.
A deadline taken from the ask would have arrived over the run's own credential, so the refusal below
would have checked the report against a number the reporting party chose. It is computed Hub-side
while serving the ask and stored on the question. Design D3.

The Hub refuses a report that arrives before the deadline it recorded, which is what keeps this a
report of a fact rather than a lever. Nothing here is the *agent* asserting anything: `ask_user` is
the Hub's own code running in the agent's process, the report is not an MCP tool and so is not in
the agent's tool surface, and the endpoint acts only on questions the caller's own run asked. This
matters because `task-lifecycle-governance:445-447` forbids exactly the other thing —

> A task SHALL NOT enter or leave the waiting status because an agent asserted that it should.

— and that sentence needs more than this endpoint to be true. See the next section.

**If the report is never sent** — the tool process died, the run was killed — the task simply stays
`blocked` and the run ends. That is today's behaviour, and it is the correct one for that case:
nobody proceeded.

**If the report is sent and does not land**, that is a different case, and rounds 1 and 2 merged it
with the one above. Task 5.5 requires the tool to swallow a failed report so the agent still gets
its answers, which is right — but the agent then *proceeds* with its task left `blocked`, and its
`update_task(completed)` is refused from a status with no edge to a finished one. That is the exact
stranding the ungated resume exists to prevent, arriving through a different door, and it is not
"today's behaviour": today the task was never parked and the agent completed it.

So the report is not the only signal, following the shipped design for the identical problem one
router away. `expire_permission_request` says it in a line: *"The run reports and the run's end
sweeps, so arriving second is the normal case, not an error."* `evaluate_run_end` already loads the
run's outstanding blocking question; where that question's recorded deadline has passed and it is
neither answered nor declined, the wait has demonstrably ended, and the run-end path records that
and releases exactly as the report would have. It cannot fire early, because it only runs at a
boundary already past the deadline it checks.

## An agent can already leave the waiting status by asking, and this change makes that the obvious move

`task-lifecycle-governance:445` forbids both directions — *"enter **or leave**"* — and the code
enforces one. `tasks.py:1157` refuses a non-operator setting `status: blocked`, and
`mcp_server.py`'s `TaskStatus` literal withholds `blocked` from the tool surface as a second layer.
Nothing guards the way out: `TRANSITIONS["blocked"]["in_progress"]` is `_BOTH`, the PATCH route
applies no equivalent check, and `in_progress` is in `TaskStatus` and named in `update_task`'s
docstring as an ordinary option.

Today that breach is latent, because a task only reaches `blocked` once its run has ended — the
agent that could assert its way out is no longer running. **Ask-time parking removes precisely that
protection**, and puts an incentive behind it: the agent waits out 240s, is told by the tool to
"continue as best you can", does the work, is refused `blocked -> completed` with a 409, and finds
`update_task(task_id, "in_progress")` in its own tool surface. The task then completes with no
`wait_ended_at` and no statement that a decision was made without an answer — F60, reproduced
through the door this change opens, bypassing the refused endpoint, the recorded deadline and the
permanent mark alike.

So the guard is mirrored on the way out, in the same place and with the same sentence as the one on
the way in. Nothing legitimate is refused: the three real releases are the operator's answer and
decline, both operator-attributed, and the expiry release, which is run-attributed with
`origin=runtime`. Design D10.

## What a task `blocked` while its run is `running` breaks

This combination does not exist today, so every reader of task status was checked against it. Most
are already right, and the reasons are worth recording so a later round does not re-derive them:

| Site | Verdict |
|---|---|
| `evaluate_run_end` (`run_divergence.py:707-727`) | **safe.** The runtime park is `origin=runtime`, so `run_advanced_its_task` still answers False; `block_task_for_question` returns `None` on an already-blocked task and `if task.status == STATUS_BLOCKED: return None` catches it. No divergence, which is what `run-task-binding:594` requires |
| `bind_run_to_task` (`run_task_binding.py:430`) | **safe.** Returns early on `blocked`, which is `run-task-binding:618`, "Starting a run does not release a waiting task" |
| loop/flow claim — `CLAIMABLE_STATUSES` | **safe.** `blocked` is in `BAND_AWAITING_PERSON`, never claimable; and the task is held by a running turn besides (`tasks_held_by_a_running_turn`) |
| the loop board — `CURRENT_ITEM_STATUSES`, `jobs.py:354` | **safe, and better.** A blocked task is the loop's current item on purpose; the wait now shows there from the moment it starts |
| `_free_agents` (`scheduler.py:945`) | **safe.** The agent is excluded by the running-run query regardless of its task's status |
| `scheduler.py:642` dependency-gate bypass | **safe.** Already reads `("in_progress", "blocked")` together |
| `dependency_state` (`tasks.py:317`) | **wrong, and this change widens it.** `running_on_regressed` is derived from `response.status == "in_progress"`, so a parked task whose prerequisite regressed reads `gated` — "has not started" — about work that has started and is waiting. `blocked` is reachable only from `in_progress`, so it has always started |
| `LIVE_STATUSES` → `agents._ACTIVE_TASK_STATUSES`, `checkpoints._LIVE_TASK_STATUSES` | **unchanged in kind, widened in window.** `blocked` is deliberately outside `LIVE_STATUSES`, so a checkpoint taken during the wait omits the task. It already did once the run ended; the window is now the whole wait. Left alone — the band classification is a decided answer — but only because the checkpoint's own question list is corrected to say the wait ended (see below); that was the stated cover for this row and round 3 found it broken |
| `task_attribution.attribute` (`task_attribution.py:176-188`) | **wrong, and rounds 1–2 did not check it.** It consults `live.task_ids` only inside its `unstaffable` branch, and a `blocked` task is never unstaffable, so the fall-through reports `CAPACITY_ASSIGNED` — "nothing is running" — for the whole wait about an agent that is mid-turn on that exact task. `agent-loops` states both halves of the collision and this change decides it. Design D11 |
| the dependency gate on `blocked -> in_progress` (`task_transition_service.py:371-383`) | **newly load-bearing.** See below |
| leaving `blocked` through `PATCH /tasks/{id}` | **unguarded, and this change puts pressure on it.** See "An agent can already leave the waiting status by asking" above |

### The gate on the way out, and the shipped requirement that governs it

`blocked -> in_progress` shares its `to_status` with the claim edges, so `evaluate_dependencies`
runs on it. Today `release_block_for_question` catches `TransitionRefusedError` and returns `None`,
so a prerequisite that regressed while the task waited makes the answer silently fail to release it.
That is pre-existing and rare because the window is short. After (a) the window is the entire wait,
and after (b) the release is what lets the agent finish: a refused release means the agent's
`update_task(completed)` is answered `409` from `blocked` for a task it has actually completed — a
new failure with no remedy the agent can act on.

So **resuming a wait is not gated.** That is a change to a **shipped** requirement and this change
carries the delta for it. `task-dependencies` states the rule twice — as the requirement *An unmet
dependency prevents starting and nothing else* (`openspec/specs/task-dependencies/spec.md:42`), whose
scenario *Resuming is gated the same way as starting* (`:76`) says in as many words that the
resumption is refused, and as `task-lifecycle-governance`'s *Starting work is gated on its
prerequisites* (`:1193`), which is about placement. Both are modified here. Modifying only the
second, which is what this proposal did before round 2, would archive a corpus stating the opposite
rules in two capabilities; `openspec validate --strict` does not cross-check capabilities and passes
either way.

Three facts carry the reversal, and only the first was stated before round 2.

1. **The gate asks whether work may start, and this work started.** `blocked` is reachable only from
   `in_progress`.
2. **Every refusal at this edge is therefore a change that happened *after* the task started.** The
   edge into `in_progress` is itself gated, so a waiting task passed the gate on the way in. A
   prerequisite can only be unmet on the way out if it left `approved` while the task waited, or was
   declared against the task while it waited. The first is exactly the shipped requirement *A
   dependency that regresses after a dependent has started does not halt it*
   (`task-dependencies:105`) — "the dependent SHALL continue". **The current code breaches that
   requirement at this edge.** Ungating restores it rather than weakening anything.
3. **The scheduler already decided this, the other way from the transition service.**
   `candidate_is_startable` (`hub/hub/scheduler.py:619-625`) exempts `blocked` from the same
   dependency determination, in the same words: *"Gating it would be asking whether work that is not
   about to start is allowed to start."* So the board and the gate disagree today about one edge, and
   `task-dependencies` human check 13.1 requires the firing and the board never to disagree. This
   makes them agree.

One consequence follows and is stated rather than discovered later: a dependency **declared** while a
task is waiting (`task-dependencies:262`, "the existing gate SHALL apply to B unchanged") will no
longer stop that task resuming. It is reported against the task instead, which is all the gate could
usefully have done about work already under way.

The skip is derived from the task's status inside the transition service rather than passed by the
caller, so all three releases — answer, decline, expiry — get it. Status alone is sufficient because
the rule is unconditional: `from_status == 'blocked' and to_status == 'in_progress'`.

**This is coupled to the `dependency_state` fix below and must not ship without it, or without it
shipping too.** Fixing `dependency_state` so a waiting task reads `running_on_regressed` — "flagged,
not stopped" — while leaving the gate in place would make the board say a task is merely flagged
about work the gate can stop permanently.

## An expired wait is not an open one

`unanswered_blocking_question` selects on `answered=False AND declined=False`. A question whose wait
ended unanswered still matches. Without a third condition, a run that timed out, proceeded, and then
ended **without** moving its task would be parked as "waiting on a person" — recording a wait that
had already ended, and suppressing a divergence that is real. So both readers of that predicate —
the run-end park and `tasks.py`'s `_attach_awaiting_answer` — must exclude a question whose wait has
ended.

**That predicate has two readers; the idea behind it has five.** `wait_ended_at` creates a state
that did not exist — unanswered, undeclined, and nobody waiting — and every surface deriving
"somebody is waiting" from `answered = False` now describes it wrongly. Three more do:

* `conversations.py:424` — navigation's attention state, which marks the conversation **waiting on
  the operator** and, by its own docstring, lets that outrank `running`. The shipped requirement
  states its own reason and that reason expires with the wait: *"because a waiting run consumes its
  configured timeout while the operator is unaware of it."* Excluded, with an
  `agent-conversation-workspace` delta. Note the same function's permission arm already models this
  exactly right — `status == "pending"` excludes `expired` — and only the question arm lacked an
  expired state to exclude.
* `jobs.py:385` — a loop's open-question count, which the operator reads as "these still need me".
  Excluded, with an `agent-loops` delta.
* `checkpoints.py:293` — a checkpoint's `open_questions`, read by the *successor agent*. **Kept, and
  marked**: dropping it would lose the most useful thing on that list, but calling it merely open
  would tell the successor a decision is still pending when one was already taken without an answer.
  This is also what makes leaving `LIVE_STATUSES` alone honest, since `open_questions` is the stated
  cover for the task a checkpoint omits during the wait.

## A batch of questions parks once, and releases on the first answer

`ask_user` carries up to four questions sharing one deadline, created as separate rows sharing a
`batch_id`. The park is the existing two-branch shape of `block_task_for_question` applied to each
of them in turn: the first blocking question transitions the task, and every later one takes the
already-blocked branch that records `blocked_task_id` without transitioning. That is
`run-task-binding:663` — "Every question that parks a task SHALL record which task it parked" —
satisfied by the code that already implements it.

**The release rule is not touched.** `run-task-binding:684` requires that answering *any* recorded
question releases the task, and it was written to fix the defect where only the oldest one worked
and nothing said so. Under ask-time parking that means answering one of four returns the task to
`in_progress` while its run still waits for the other three. That is deliberate and not a
regression: the run really did get an answer, the status really is contestable, and the wait is
still reported — by `awaiting_answer_reason`, which covers exactly this shape, a running run bound
to a task it cannot park. It is the strongest argument for keeping that field rather than folding
it into the status.

Nothing re-parks. When the remaining questions' wait expires, the release is a no-op on a task
already `in_progress`, and half (b)'s mark applies to each expired question as normal.

## What (b) puts on the board

The statement is not scoped to tasks that parked. Keying it on `blocked_task_id` alone — which
rounds 1 and 2 did — would miss a run bound to a task in `under_review`, which waits out the full
deadline, decides for itself, and gets no mark, because `block_task_for_question` records
`blocked_task_id` only where the task transitioned or was already `blocked`. That is F60 with a
different starting status, and the requirement is written about a wait rather than about a park. So
the derivation takes the two-arm shape `_attach_awaiting_answer` already uses — the question named
the task, **or** the asking run was bound to it — without that function's `Run.status == "running"`
condition, which belongs to a live wait rather than to a permanent record.

The durable record is the question row, as it already is for every other fact in this area, and the
task-side statement is derived per request — the same choice `awaiting_answer_reason`,
`has_open_divergence` and `dependency_state` all make, and for the same reason: a second copy on the
task is one more thing that can disagree with it.

The derivation is deliberately **permanent**: a question whose wait ended unanswered marks its task
for good, even if the operator answers it afterwards. F60's compounding half is that a late answer
can be recorded against work that shipped on a different decision; clearing the mark on that answer
would erase the record of the unilateral call at the exact moment it becomes most misleading.

A **declined** question is not this. A decline is the operator saying "you decide", and the tool
returns early on it rather than expiring, so nothing is marked.

## Out of scope, deliberately

* **Answering a question whose run has ended.** Already handled: `run-task-binding:639` requires the
  answer to be queued as input, and `_asking_run_has_ended` implements it. F60 filed it as
  compounding; it is not this change.
* **`awaiting_answer_reason` is not removed.** It still reports a wait the status cannot show — a
  run bound to a task in `under_review`, where the park is legally impossible. Its comment
  (`hub/hub/schemas/tasks.py:317-322`) states a reason that stops being true and must be corrected.
* **Retiring the run-end park.** It stays, as the fallback for a question asked in an earlier turn.
