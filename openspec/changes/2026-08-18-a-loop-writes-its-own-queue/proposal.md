# A loop writes its own queue

## Why

**`2026-08-16-many-named-loops` gave a loop a queue and a memory, and wired neither.**
`openspec/explorations/2026-08-18-loops-as-an-agent-tool.md`, written this session in an
interactive design conversation with the operator, measured it directly: `Task.loop_id` is read in
five places (`tasks.py:427`, `scheduler.py:86,99,417`, `schemas/jobs.py:71`) and written in zero —
not the REST `TaskCreate` schema, not MCP `create_task`, not the update path. Every test exercising
it fabricates the row directly in the ORM. `AIJob.last_session_id` is the same shape a second time:
read in four places (`scheduler.py:328`, `jobs.py:69,342`, `JobCard.tsx:323`), written in none, zero
test references anywhere. **`stop_when_queue_empties` is dead in production** because it guards on
`ever_count`, which can never become non-zero, and `session_mode="resume"` silently behaves
identically to `"new"` every single firing.

`many-named-loops/design.md` D8 named this outcome and deferred it on purpose: *"Composing
`Loop`/`Task.loop_id`/`JobRun.conversation_id` into something that actually drives itself... is
explicitly future work; this change gives that future work a data model and a visibility surface to
build on, and stops there."* This change is that future work.

**Why the passive voice is the root cause, not a style note.** The shipped requirement reads *"A
task MAY be linked to a loop"* — permissive mood, no actor, both its scenarios are read scenarios.
That sentence is the entire specification of queue population, and it cannot be checked for
completeness because there is no subject whose behaviour a scenario could describe. Every
requirement below that touches state names who writes it.

**The design is the operator's, recorded in the exploration and carried here verbatim where it
settles something:**

> "Loops can have their own tasks. A spec is one source. Loops can be attributed to other agents. If
> a loop is created by the architect and attributed to the developer only the creator can create new
> tasks. So either the agent will have to send a message to the architect agent with an explanation
> on why it needs another task or the user will have to talk with the architect to add another task.
> Agent can create loops for themselves but once the loop is defined only with user approval then can
> add more tasks."

> "The loop should be a way to execute something in a period of time were the user can be doing
> another thing... the loop helps with **context management** since it's not a single unstopped
> session with more and more polluted context and helps with **governance and visibility** since we
> need checkpoints and stages between tasks and executions."

The second quote is why continuity is built on checkpoints rather than on fixing `resume` — see
design D4.

## What Changes

- **Two queue-write paths, each naming its actor.** `Loop` gains an optional `spec_document_id`
  (nullable, no FK — same reasoning as `Task.spec_document_id`/`loop_id` themselves): a loop MAY
  declare, at creation, that its queue is one specification document's decomposition. When
  `spec_tasks.materialise()` creates the tasks that document declares (on operator approval,
  `spec.py:1113`), it now stamps `loop_id` on each for the loop that declared it, if any — the
  materialise call itself is the actor, which is why this works even though document approval is an
  operator-only route with no loop in its request body. Separately, `create_task` (MCP and REST)
  gains an optional `loop_id`; the Hub accepts it only from the loop's own creator (the run's
  server-derived agent identity matches the loop's job's `agent`) or from the operator, and rejects
  it otherwise with a message pointing the caller at `send_message`.
- **A new `create_loop` MCP tool, not a widened `create_job`.** Distinct from `create_job` the way
  `create_task` is distinct from `send_message` — a separate name teaches an agent the concept
  exists (a loop ends; a job does not) rather than hiding it behind three optional arguments nobody
  reads. Takes everything `create_job` does, plus `purpose`, an initial task list or a source spec
  document, and a stop condition — a loop with neither `stop_at` nor `stop_when_queue_empties` is
  refused, because a "loop" that cannot stop is just `create_job` under a different name.
- **A firing claims its queue's current item — deterministically, never by model judgement.** Before
  composing what an agent sees, a loop firing selects the queue's existing `in_progress`/`blocked`
  task if one exists, else its oldest `pending` one (the same derivation `_batch_loop_summaries`
  already computes for the UI's "current item," now load-bearing rather than cosmetic), and marks it
  `in_progress`/assigned to the firing's agent before the turn starts.
- **Continuity is loop-scoped checkpoints, not `session_mode="resume"`.** `Checkpoint` gains a
  nullable `loop_id`, stamped when its conversation's job has a loop. A new
  `latest_checkpoint_for_loop()` finds the most recent checkpoint across every conversation the loop
  has ever fired into — the join `many-named-loops` D8 left unbuilt. `compute_envelope`'s `tasks`
  field becomes the loop's queue, not the executing agent's whole task list, when the conversation
  belongs to a loop. **`session_mode="resume"` is refused outright for a job that has a loop** — it
  is the polluted-context failure mode the operator named loops as the fix for, so a loop cannot
  opt back into it. Whether to fix or remove `resume` for a *plain* (non-loop) job is unchanged by
  this proposal and stays open — see Non-Goals.
- **Every firing is briefed, and the briefing is capped.** `_do_fire_job` composes a bounded prefix
  ahead of `job.message` — the loop's purpose, the claimed task, and the prior firing's checkpoint
  body (if any) truncated to a fixed character budget — before calling `new_entry`. A firing that
  has never been briefed before (a loop's first) gets purpose and claimed task only; there is nothing
  to chain yet.
- **An empty queue with an unanswered request still terminates**, and the request becomes telemetry.
  No new "paused" state — the operator's own reasoning: *"We can track this kind of information and
  improve the loops... how many tasks were added from the initial process."* A new
  `loop_queue_exhausted` event records whether a `send_message`/`ask_user` was in flight when the
  queue emptied.
- **An agent-created loop needs operator approval to extend after it first fires.** When a loop's
  creator and executor are the same agent (it made the loop for itself), the creator/executor
  privilege above collapses — a self-authoring loop could otherwise always add one more task and
  never terminate, defeating the entire reason creator and executor are separated. For this case
  only, `loop_id` on `create_task` is accepted from the creator up to the loop's first fire, and
  requires an answered `ask_user` afterward — there is no second agent to `send_message`.

## Capabilities

### Modified Capabilities

- `agent-loops`: names the actor for every write this capability's own requirements previously left
  passive (`many-named-loops`'s "A task MAY be linked to a loop"), adds the two queue-write paths, the
  claim-on-fire rule, loop-scoped checkpoint continuity in place of `resume`, the capped briefing, the
  empty-queue-terminates-with-telemetry rule, and the extend-after-first-fire approval gate for a
  self-created loop.

## Impact

**Behaviour** — a loop created before this change (queue always empty, because nothing could write
`loop_id`) starts accumulating tasks the moment either write path is used; nothing about a plain,
non-loop job changes. A loop's firing now carries a briefing where before it carried `job.message`
verbatim; the message itself is unchanged and still appears, appended after the briefing.

**API** — `POST /tasks` and MCP `create_task` gain optional `loop_id`, rejected (403, naming the
reason) for a caller who is neither the loop's creator nor the operator. `POST /jobs` gains
`spec_document_id` and an initial-tasks payload alongside the three fields `many-named-loops`
already added; this route's own validation is otherwise unchanged, so a human operator's existing
"Make this a loop" form still creates a loop with no stop condition if that is what they submit.
`PATCH /jobs/{id}` refuses (400) `session_mode="resume"` for a job carrying a `Loop` row. New MCP
tool `create_loop`, gated by the existing `_require_agent_job_allowance` (`jobs.py:21`) `create_job`
already uses — no new allowance concept — which calls the same `POST /jobs` route but refuses
(before ever making the call) to create a loop with no stop condition. That stricter contract is
`create_loop`'s own, not a change to what `POST /jobs` accepts from anyone else.

**Migration** — one additive nullable column each on `loops` (`spec_document_id`, no FK, unique) and
`checkpoints` (`loop_id`, no FK, indexed). No existing column, index, or constraint changes.

**UI** — none in this change. The side-panel loop view (governance and visibility for exactly this
mechanism) is `2026-08-18-the-side-panel-family`'s loop panel, explored and specced separately per
the operator's own sequencing (`STATE.json` Q7/Q8).

## Non-Goals

- **Not fixing or removing `session_mode="resume"` for a plain (non-loop) job.** Refused outright
  for a job that *is* a loop (see above); an ordinary job's own broken `resume` is `2026-08-18-loops-
  as-an-agent-tool.md` §2b's second finding and stays exactly as broken as it is today. Fixing it is
  separable work this change does not need and the operator has not asked for.
- **Not a queue-ordering field.** The claimed item is still derived from `status`/`created_at`
  exactly as `_batch_loop_summaries` already derives "current item" for the UI — no new position
  column, and this change does not let a creator reorder the queue, only add to it.
- **Not solving overlapping firings.** `2026-08-18-loops-as-an-agent-tool.md` §8 item 6 names this
  open; a firing that outlives its cron interval before claiming or completing its item is out of
  scope here and stays a known gap, recorded in design D9.
- **Not adding a foreign key from `AIJob.agent` to `Agent`.** The creator-identity enforcement this
  change depends on (D8) is built on the run-credential identity the Hub already trusts
  (`agent_auth.AgentActor.agent`) compared by string equality against `AIJob.agent` — the same
  no-FK trust boundary `_job_agent_skip_reason` already uses. Archiving or renaming a loop's creator
  agent still silently strands the loop's permission model, exactly as `2026-08-18-loops-as-an-agent-
  tool.md` §8 item 4 describes; this change does not close that gap, only avoids making it worse.
- **Not spend bounds on unattended work, and not deciding whether a loop's executor may create loops
  of its own.** Both raised by the exploration (§8 item 7) and left to the operator; this change adds
  no enforcement either way.
- **Not building the side panel.** Visibility for everything this change adds — a loop's queue,
  claimed item, briefing history, telemetry — is `2026-08-18-the-side-panel-family`'s loop panel.
  This change's own surface is API and MCP only.
