# Design — a loop writes its own queue

Every decision below either restates something the operator settled in the design conversation
recorded at `openspec/explorations/2026-08-18-loops-as-an-agent-tool.md` (cited, not re-derived) or
resolves something that exploration left open (§8), argued fresh with a rejected alternative
recorded so it does not resurface.

## D1. Two queue-write paths, each naming its actor

**Decided by the operator:** *"Loops can have their own tasks. A spec is one source."* The
exploration measured the write gap; it did not say how the spec source attributes tasks to a loop,
because document approval (`spec.py:1113`, `approve_document`/`_operator()`) is an operator-only
route with no loop in its request. Two ways to close that gap:

| | Loop declares its source document | Approval call threads a `loop_id` |
|---|---|---|
| Where the binding lives | `Loop.spec_document_id`, set once at loop creation | Passed on each `POST /spec/.../transition` call |
| Who can mis-attribute | Nobody after creation — the binding is fixed | Whoever calls approve, for any document, to any loop |
| Auditable | Yes — one row, one binding, queryable | No — a transient request parameter, gone once handled |
| Needs the approve route to know about loops | No | Yes — couples an operator-phase route to loop internals |

**Decided: the loop declares its source.** `Loop.spec_document_id` (nullable, `unique=True` — one
loop per document, matching `Loop.job_id`'s own uniqueness reasoning so two loops cannot silently
race to claim the same decomposition), not a ForeignKey, for the identical SQLite-irreversibility
reason `Task.spec_document_id`/`loop_id` already state (`models.py:636-647`). `spec_tasks.materialise()`
gains one query at its top: look up `Loop` where `spec_document_id == document.id`; if found, every
`Task` it constructs in this call gets `loop_id=loop.id`. The actor is `materialise()` itself —
it already runs with the document and project in scope, needs no new parameter, and cannot be
called with a loop it was not told about at loop-creation time.

**Creator-authored tasks:** `create_task` (MCP `mcp_server.py:212`, REST `POST /tasks`) gains
`loop_id: Optional[str]`. The Hub resolves the calling identity from the run credential
(`agent_auth.AgentActor.agent`, never from a request body — matching the standing rule "identity is
never accepted from a request body or header") and compares it by string equality to the target
loop's `AIJob.agent`. Equal, or the caller is the operator (`_operator()` actor, which every
operator-only route in this codebase already exempts from agent-scoped checks) → accepted.
Otherwise → `403`, with a message naming `send_message` as the alternative, so a rejected agent is
told what to do rather than left to guess.

**Rejected: a single `spec_document_id` on `Task` implies membership, no `Loop.spec_document_id`
needed.** Considered — since `Task.spec_document_id` and `Task.loop_id` already coexist on the same
row, could a loop's queue just mean "every task this loop's own job created via `create_task`, plus
every task whose `spec_document_id` names a document this job also happens to reference"? Rejected:
there is no existing link from a job to a document at all, so this would require inventing one
anyway, and it makes "which loop does this document feed" an inference from task rows rather than a
stated fact — the exact passive-voice failure mode this whole change exists to remove.

## D2. `create_loop` as a separate MCP + REST-backed tool, not a widened `create_job`

Argued per `DEC-create-loop-tool-shape`'s pre-authorisation. `create_job` today (`mcp_server.py:503`)
exposes `name`, `agent`, `message`, `cron`, `session_mode` — none of the three loop fields
`many-named-loops` already added to the REST `JobCreate` schema (`purpose`, `stop_at`,
`stop_when_queue_empties`). Two ways to let an agent create a loop:

- **Widen `create_job`** with the same three optional fields the REST schema has, plus this change's
  new ones (`spec_document_id`, initial tasks). Cheapest — no new tool, no new gate to register.
- **A separate `create_loop` tool.** Costs one more tool in the surface and one more line in
  `test_mcp_tool_schemas.py`.

**Decided: separate `create_loop`.** The argument does not come out even — it favours a separate
tool outright, for a reason sharper than the pre-authorisation's default ("if it comes out even"):
a widened `create_job` would let an agent create what is *actually* a loop (by supplying `purpose`)
while never learning it has a stop condition, because nothing in the tool's shape says so — the same
"three optional fields nobody reads" trap the REST API already has for a human filling in a form,
now for a model that cannot see a collapsed UI section either. `create_loop` states its own
contract: it refuses creation (`400`) unless at least one of `stop_at`/`stop_when_queue_empties` is
supplied — a loop that cannot stop is refused outright, which a widened `create_job` cannot express
without becoming a different, and worse, kind of validation (mode-dependent required fields on a
single endpoint). `create_job` keeps behaving exactly as it does today, unmodified.

**Rejected: `create_job` with mode-dependent required fields.** i.e., `create_job(..., loop=True)`
makes `stop_at`/`stop_when_queue_empties` conditionally required. Rejected: FastMCP's generated
schema (the thing an agent actually reads before calling) cannot express "these fields become
required when this other one is true" — every field would still show as independently optional,
reproducing exactly the discoverability failure a second tool avoids.

**Where the "no stop condition" refusal is enforced.** `create_loop` is an MCP-only addition —
`mcp_server.py` gains the tool function, but it calls the same `POST /jobs` route `create_job`
already calls, now widened with `spec_document_id` and `initial_tasks` (D1, D2). The refusal lives
in the `create_loop` tool function itself, checked before the HTTP call is made, **not** in `POST
/jobs`'s own schema or route validation. `POST /jobs` keeps accepting a job with `purpose` set and
no stop condition exactly as it does today — that path is how a human operator uses the existing
UI form (`JobForm.tsx`'s "Make this a loop" section, `many-named-loops` task 5), and this change
does not require the operator's own workflow to gain a restriction nothing asked for. Only the
agent-facing `create_loop` tool states the stricter contract.

## D3. A firing claims the queue's current item — deterministically

`2026-08-18-loops-as-an-agent-tool.md` §8 item 2 left open whether a firing *claims* the next task
or is *briefed with the whole queue and chooses*. Both are defensible on their own; the choice
follows directly from the checkpoint module's own stated principle
(`checkpoints.py:1-11`): *"What the Hub can check, it must not delegate."* Selecting "the next task"
from a `status`/`created_at`-ordered queue is exactly the kind of thing the Hub can check — there is
one right answer given the data — so delegating it to a model's judgement each firing would be
asking for something the Hub can already compute, the identical failure `checkpoints.py` names for
timestamps and pending-work counts.

**Decided: claim.** Before composing the briefing, the firing selects the queue's own
`in_progress`/`blocked` task if one exists (a prior firing that did not finish, or a task an operator
parked mid-way), else the oldest `pending` one by `created_at` — the same derivation
`_batch_loop_summaries` (`jobs.py:98`, design D7 of `many-named-loops`) already computes for the UI's
"current item," now made load-bearing: the scheduler sets that task's `status="assigned"` (or leaves
`in_progress` if resuming one) and `assignee=job.agent` before the entry is queued, so "what is this
firing working on" is answered by the task board itself, not by parsing a transcript.

**Rejected: brief with the whole open queue, let the agent choose.** Rejected on three grounds,
recorded so the choice does not need re-litigating: (a) it duplicates a decision the Hub can already
make deterministically once ordering is fixed, for no benefit — the queue has no priority field this
change adds (Non-Goals); (b) "which task is this firing about" becomes unanswerable until the
firing's own output is read and interpreted, which is strictly weaker traceability than
`many-named-loops` already built `JobRun.conversation_id` to provide; (c) an agent could reorder the
queue for reasons never recorded anywhere, which is the same complaint that Non-Goal's own reasoning
raises about a queue-ordering field, in reverse — an *implicit*, per-firing reordering is worse than
an *absent* explicit one.

## D4. Continuity: loop-scoped checkpoint chaining, `resume` refused for a loop

`2026-08-18-loops-as-an-agent-tool.md` §6 already settled *that* continuity is checkpoints, not
`session_mode="resume"`, and why (the operator's context-management purpose; checkpoints survive
compaction and restart; a resumed conversation does not). What it left as "the gap is small and
specific" (§6, end) is the mechanism:

1. **`Checkpoint.loop_id`** (nullable, indexed, no FK — same reasoning as every other loop-adjacent
   column in this codebase), stamped by `create_checkpoint` when the checkpoint's conversation
   belongs to a job that has a `Loop`. Considered joining through `Conversation` →
   `JobRun.conversation_id` → `AIJob` → `Loop` at read time instead of storing a column: rejected,
   because every firing creates a *new* conversation (`origin="job"`, `scheduler.py:338`), so "the
   latest checkpoint for this loop" is a query across every conversation the loop has ever fired
   into — a four-table join run on every firing, versus one indexed column. The same trade
   `JobRun.conversation_id` itself already made over "derive it from timestamps."
2. **`latest_checkpoint_for_loop(db, loop_id)`**, mirroring `latest_checkpoint(db, conversation_id)`
   (`checkpoints.py:65`) exactly except for the `WHERE` clause — ordered by `created_at DESC, id DESC`
   the same way, so the anchor-selection tie-break behaviour used elsewhere is not reinvented.
3. **`compute_envelope`'s `tasks` field becomes the loop's queue** (`Task.loop_id == loop.id`, every
   status — mirroring the "explicit scope hides nothing" rule `TASK_SCOPE_NOTE` already documents for
   the agent-wide case) when `conversation.origin == "job"` and its job has a loop. The existing
   agent-wide `_tasks_for` behaviour is unchanged for every conversation that is not a loop firing.
4. **`session_mode="resume"` is refused (400) at `PATCH`/`POST /jobs` when the job carries a `Loop`
   row.** Not merely unused — actively rejected, so a caller who sets it gets an error naming why
   ("this job is a loop; continuity is by checkpoint, not by resumed session") instead of the
   current silent no-op. This is the one piece of `2026-08-18-loops-as-an-agent-tool.md` §2b's
   finding this change resolves; the rest (a *plain* job's `resume` being equally broken) is
   deliberately untouched — see Non-Goals.

**Rejected: fix `AIJob.last_session_id` and let a loop opt into `resume` if it wants to.** This is
the alternative `2026-08-18-loops-as-an-agent-tool.md` §6 already rejected on the operator's own
purpose statement, carried here rather than re-argued: fixing `resume` would rebuild "a single
unstopped session with more and more polluted context," which is the specific thing loops exist to
avoid. Restated as a decision here because D4 is the design that has to act on it, not just record
it.

## D5. The briefing — content and cap

`_do_fire_job` (`scheduler.py:296`) passes `content=job.message` to `new_entry` verbatim today
(`scheduler.py:431-440`). For a loop firing, this becomes a composed prefix, then `job.message`
unchanged, so the operator's own message template still reads exactly as authored — the briefing
adds context, it does not replace intent.

**Content, in order:**

1. The loop's `purpose` (may be empty — `Loop.purpose` defaults to `""`, `models.py:1216`).
2. The claimed task (D3) — title, description, acceptance criteria — so the firing knows *which*
   queue item it is working, not just that a queue exists.
3. The prior firing's checkpoint body, if `latest_checkpoint_for_loop` returns one, rendered the same
   way `render_checkpoint` already renders a checkpoint for a human reader — reusing the render
   function rather than inventing a second serialisation for the same data.
4. A one-line queue summary (open/done counts), reusing the same aggregation
   `_batch_loop_summaries` already computes.

**The cap.** Checkpoint generation already has a precedent for a named, reasoned character budget:
`_TRANSCRIPT_CHAR_LIMIT = 60_000` (`checkpoint_generation.py:53`) bounds what a *generator* reads
before writing a checkpoint. The briefing is the opposite direction — a *consumer* reading a
checkpoint that was itself already produced as a bounded summary — so the budget is far smaller:
`_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`. Reasoning for the number, not just its existence: a
checkpoint body is a handful of short fields (`objective`, `state`, bulleted `decisions`/
`dead_ends`/`next_actions`/`risks`, `checkpoint_generation.py:72-94`) that a probe-graded generation
pass already keeps terse; 4,000 characters comfortably fits one well-formed checkpoint rendered in
full, with room for the queue summary and claimed-task text around it, and only ever truncates the
pathological case (a checkpoint that failed to stay terse) rather than the common one. Truncation
drops from the end of the rendered body (oldest sections first would require re-ordering
`render_checkpoint`'s own section order for a rare case; simplest to cut is the correct default here
because if 4,000 characters is ever routinely insufficient, that is itself a signal the checkpoint
generation prompt needs revisiting, not that the briefing needs a cleverer truncation).

**Rejected: summarise the checkpoint again for the briefing, rather than truncate.** A second Worker
call per firing, purely to shorten text the first Worker call already shortened once, costs a model
call on every single firing for marginal gain over a hard truncation — and reintroduces exactly the
"asked a model for something the Hub could compute" pattern D3 already rejected for queue selection.

## D6. Empty queue with an unanswered request — terminate, and record telemetry

Already decided by the operator (exploration §5, quoted in full there): terminate rather than add a
third "paused" state; the request becomes something to learn from, not something to wait on.
**What this design adds is the mechanism**, since the exploration recorded the decision, not the
event shape:

- New persisted+broadcast event `loop_queue_exhausted`, alongside the existing `loop_stopped`
  (`scheduler.py:415-423`) — not folded into it, because "the queue is empty" and "was a request in
  flight when it emptied" are two independently useful facts a reader should not have to parse out of
  one payload. Payload: `{job_id, loop_id, pending_request: {kind: "message"|"question", to, reason,
  created_at} | null}`. `pending_request` is populated by checking, at the moment `_loop_stop_reason`
  reports the queue empty, whether the loop's executor has an unread `Message` addressed to the
  creator or an unanswered `Question` in the firing's conversation — both already queryable
  (`Message.read`, `Question.answered`) with no new storage.
- This event is what the side-panel's loop telemetry (`2026-08-18-the-side-panel-family`, not this
  change) will read to answer "how often did a loop discover work late, and how much" — the exact
  question the operator asked for.

## D7. Extending after the first fire — operator approval only when creator is executor

The exploration recorded the operator's rule for the general case (creator ≠ executor: only the
creator adds tasks, always) and the self-created case (*"Agent can create loops for themselves but
once the loop is defined only with user approval then can add more tasks"*) as two halves of the
same quote. This design has to say precisely when "once the loop is defined" ends, since the
operator's sentence names the rule, not the boundary.

**Decided: the boundary is the loop's first fire.** Before the first fire, the creator (who is also
the executor, in the self-created case) is still authoring the loop — adding tasks during this
window is indistinguishable from the initial queue `create_loop` itself accepts (D1/D2), so gating it
would only make the same action illegal depending on which call it arrived in. After the first fire,
the loop is running, and D1's creator-privilege check for `create_task(loop_id=...)` requires an
answered `ask_user` in the same run rather than accepting the call outright, when (and only when) the
calling agent equals the loop's own `AIJob.agent` (i.e., creator and executor are the same agent for
this loop). A loop with a distinct creator keeps D1's unconditional creator-privilege rule — the
operator already gates that loop's *existence* through `_require_agent_job_allowance`, and a second
approval on top of every task addition would make the creator/executor split more expensive to use
than a plain job, defeating its own purpose.

**Rejected: gate every `create_task(loop_id=...)` call behind `ask_user`, self-created or not.**
Simpler to state, but it taxes the common case (an architect's loop, executed by a developer) to
guard against the rare one (an agent's own self-created loop), and the operator's quote specifically
carves out the self-created case as the one needing the extra step — treating them identically
contradicts the quote it is meant to implement.

## D8. Creator-identity enforcement without a foreign key

`2026-08-18-loops-as-an-agent-tool.md` §8 item 4 names this the sharpest open question:
"creator identity is now load-bearing for permissions, but `AIJob.agent` is a bare `String(64)` with
no foreign key, and `scheduler.py:51-56` returns `None` (proceed) when no agent row matches." This
change makes the gap costlier — D1's `create_task(loop_id=...)` check and D7's `ask_user` gate both
now depend on that same string comparison staying meaningful.

**Decided: accept the existing trust boundary, do not add a foreign key.** `_job_agent_skip_reason`
already looks up `Agent` by `(project_id, name)` and treats "no row found" as "proceed" — this
change's checks (D1, D7) use the identical shape: compare the run-credential-derived
`AgentActor.agent` string to `AIJob.agent`. An archived or renamed creator agent means no run can
ever again present that identity, so the creator-privilege path in D1 becomes permanently
unreachable for that loop — the loop does not misbehave, it just becomes unable to accept new tasks
from a creator who no longer exists, which is a starved queue (visible, and D6's `stop_when_queue_
empties` eventually ends it) rather than a silent security hole.

**Rejected: add a ForeignKey from `AIJob.agent` to `Agent.name`, or a new `AIJob.creator_agent_id`.**
Rejected for this change specifically because it is materially larger than everything else here — a
migration touching a column three other write paths already read
(`scheduler.py:328,368`, `jobs.py:69,342`, `mcp_server.py`), decided without the operator having
asked for it, and orthogonal to "a loop writes its own queue." Recorded as still open, not resolved,
so it is not silently dropped — see D9.

## D9. What this leaves for a future change, named rather than assumed away

Mirroring `many-named-loops` D8's own practice of naming rather than hiding what a change does not
reach:

- **`AIJob.agent` has no foreign key** (D8). This change depends on the string staying meaningful and
  does not fix it.
- **Overlapping firings are still undefined.** A firing that outlives its cron interval before
  claiming or completing its item — two firings could both observe the same task as the queue's
  "current item" and race to claim it. `Task.status` transitions are not currently guarded by an
  optimistic lock; `run_task_binding.py`'s existing transition machinery may already provide one, but
  this change did not verify it. Named in `2026-08-18-loops-as-an-agent-tool.md` §8 item 6, still
  unverified.
- **Spend bounds for unattended work, and whether a loop's executor may create loops of its own** —
  raised by the exploration (§8 item 7), not settled by the operator, not addressed here.
- **A plain (non-loop) job's `session_mode="resume"` stays broken** (D4) — this change only refuses
  it for a loop; fixing `AIJob.last_session_id`'s write path for an ordinary job is separable work.
- **The side panel's loop view** is where an operator actually sees any of this — the queue, the
  claimed item, the briefing history, D6's telemetry. This change produces the data; it produces no
  UI. `2026-08-18-the-side-panel-family` is where that surface is specced.
