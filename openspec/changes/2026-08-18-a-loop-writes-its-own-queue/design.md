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

---

# Addendum — decisions taken with the operator after this design was written

Decisions D1–D9 above were authored at 12:32–12:38 on 2026-08-18. The operator continued the design
conversation afterwards and settled five further things, two of which **generalise** decisions above
rather than contradicting them. Recorded here rather than edited into place, so the sequence stays
legible: an earlier decision that was later widened is more useful than one silently rewritten.

## D10. Control is an explicit per-loop setting, and it generalises D7

**Creator and controller are two subjects, not one.** The creator is the agent whose run created the
loop. The **controller** decides whether the queue may be extended, defaults to the **operator**, and
may be delegated to the creator agent and taken back — after creation. The operator:

> "The operator will never create loops by himself. He will do it with an agent. So we have two
> subjects there. The one who created and the one who controls it… any new task or decision should
> reach the operator via the agent he used and only the operator can decide on it. But the operator
> can leave the control to the agent that can decide for himself."

**How this relates to D7.** D7 decided the boundary for a *self-created* loop is its first fire,
after which the creator needs operator approval. That conclusion survives — but as a *consequence*
of the default rather than as a special case: control defaults to the operator for every loop, so a
self-created loop's post-definition additions need the operator because nothing was delegated. D7's
distinction between "creator is executor" and "creator is distinct" is replaced by a single question:
**who holds control.** Delegating control to a creator agent is what makes D7's unconditional-creator
path available, and it is now an explicit act rather than an inference from role identity.

The field follows `Agent.default_permission_mode` (`models.py:196`) exactly: nullable, where **NULL
means the current default rather than a stored copy of it** — *"a row storing today's default would
keep saying it after the default moved."* It is the same operator-in-the-loop posture the composer's
Permissions pill already sets, pointed at queue extension instead of tool calls.

*Rejected: a boolean `autonomous`.* It cannot later name a third controller — a reviewing agent, say
— without a migration and a vocabulary change.

*Rejected: keeping D7's role-identity inference as the only rule.* It cannot express the operator's
actual requirement, which is that an agent creates the loop while the operator keeps the decision.

## D11. A loop is editable, and an edit lands on a firing boundary

Control is handed over after creation, the operator adds tasks, and a loop's definition changes over
its life. The constraint: *"we need enforcements not to break the loop. If I'm editing a loop it only
goes after no run is active."*

**Decided: an edit is always accepted and applied at the next firing.** The firing in flight keeps
the definition it was briefed with. Pending edits are visibly distinct from applied ones.

*Rejected: refusing an edit while a run is active.* The literal reading, and the simplest — but a
long firing locks the operator out of their own loop, and the refusal is racy against a firing that
starts a moment later.

*Rejected: applying immediately.* A firing briefed at start mostly would not observe it, but "mostly"
is load-bearing: a firing that re-reads its queue mid-turn would see a world it was never briefed on.

The cost is a requirement, not polish: **a staged edit with no visible sign of it is worse than a
refused edit.**

## D12. A late task is refused with its reason and offered to a successor

D6 terminates a loop whose queue empties even with a request outstanding. That leaves a closing
window: the queue empties, the loop stops, and a task added a moment later arrives at a stopped loop.

**Decided: refuse it, state when and why the loop stopped, and offer it as the initial work of a new
loop.** Termination stays final — consistent with the operator's *"the architect can create another
one"* — without discarding work already written.

*Rejected: reviving a loop stopped for an empty queue.* A stopped thing becoming live again is a
transition that is hard to render honestly and harder to reason about in history.

*Rejected: discarding the task with a plain error.* It throws away something the operator wrote at
the moment they were trying to help.

*Rejected: suspending termination while an edit is open.* Closes the race, and reintroduces the third
state D6 exists to avoid.

## D13. A per-loop history, and a firing that can say it is running

Two facts the decisions above need, which the database cannot currently state.

**`EventLog` is not a per-loop history.** It exists (`models.py:907`) and `persist_event` already
writes loop events such as `loop_stopped`, but it is indexed by **project and agent, not by loop** —
retrieving one loop's history would mean filtering unindexed JSON. `Loop.updated_by_run_id` records
only the most recent writer, which is provenance, not history. D10's control changes and D11's edits
both need to be answerable per loop.

**`JobRun.status` is `"fired"` or `"failed"`** (`models.py:1178-1180`) — there is no value for a
firing *in progress*, so a running firing is indistinguishable from a finished one. D11's rule needs
this fact, and so does the loop panel's "is an agent working right now"
(`2026-08-18-one-shell-three-panels`). It should be **one helper both callers use**, not two joins.

*Rejected: deriving "is a firing running" by joining `JobRun.conversation_id` to
`Run.status == "running"` and leaving the column alone.* The join is correct and should exist — but
leaving `JobRun.status` unable to state its own value keeps a lie in the table and obliges every
future reader to know to join.

## D14. `Task.loop_id` is immutable after creation

Reassigning a task between loops would make a loop's queue history unable to answer what work it was
ever given — and `stop_when_queue_empties` is derived from exactly that history
(`scheduler.py:98-101` counts every task that ever named the loop, precisely so a terminal task still
counts). Enforce at the service layer, not with a database constraint: SQLite cannot drop one later,
the same undroppable-column reasoning `many-named-loops` D2 already established.

## D15. What D8 does not cover: name reuse

D8 decided to accept the existing trust boundary rather than add a foreign key, on the grounds that
an archived or renamed creator produces a **starved queue** — visible, and eventually ended by D6 —
rather than a silent security hole. That reasoning holds for archive and rename.

It does not cover **name reuse.** Identity here is a *name*, not a row: archive agent `arch`, create
a new agent also called `arch`, and the new one satisfies every creator check the old one did,
inheriting control over every loop the old one created. Attribution is genuinely verified at creation
(`jobs.py:31-33`) but only **once**; afterwards only the string survives.

Not resolved here, and deliberately not silently widened into D8's conclusion. It is a real
consequence of making a name load-bearing for permissions, and it should be closed before control
delegation (D10) is relied on for anything the operator would not do by hand. Note it is not a live
vulnerability: the Hub is local and single-operator, and the API key is the real boundary.

---

# Addendum 2 — decisions taken with the operator on the side panel, 2026-08-18 afternoon

D1–D9 were authored by unattended firings at 12:32–12:38. D10–D15 were added after an operator
conversation that afternoon. **D16–D21 below come from a third conversation**, recorded in
`openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md`, which was nominally about the
side panel and turned out to settle four things about loops themselves. Appended rather than edited
in, for the same reason the first addendum was: the order decisions were taken in stays legible.

Two of these (D16, D17) close a hole **this change already argues against without noticing** — see
D16's opening.

## D16. Nothing is deletable. A loop, and a plain job, are archivable instead

**D14 already states this change's principle**, in the course of forbidding `Task.loop_id`
reassignment: *"Reassigning a task between loops would make a loop's queue history unable to answer
what work it was ever given."* D14 protects a task's attribution to a loop and never notices that the
loop row itself can be destroyed outright:

- `Loop.job_id` is `ForeignKey("ai_jobs.id", ondelete="CASCADE")` (`models.py:1208-1210`).
- `DELETE /api/v1/jobs/{job_id}` exists (`jobs.py:482`).
- `delete_job` is agent-callable (`mcp_server.py:533`).

One call, available to an agent, cascades away a loop's purpose, stop reason, stopped-at and every
`JobRun` it ever had. D14 bolts the window; the door stands open.

The operator, stating it as philosophy rather than as a bug report: *"Loops should never be deleted.
We need the information is tracking. Don't forget about the philosophy. Governance and traceability.
We shouldn't lose information."*

**Decided: nothing is deletable — a loop or a plain job.** Both archive. `Loop` and `AIJob` each gain
a nullable `archived_at`; the delete route and its MCP tool become archive (D18).

Specs already settled this exact question and are the model copied here: `ARCHIVED = "archived"`,
*"There is no transition out of `archived`"*, *"only the operator can archive a document"*
(`spec_lifecycle.py:31, 49, 241`).

**Rejected: keep delete for a plain job with no loop, archive only loops.** Considered because a bare
cron job accumulates with no governance value, and because it is the smaller change. Rejected by the
operator directly — *"The job with no loop is not deletable. It's archivable"* — and it has an
independent defect: `delete_job`'s success would then depend on a property its signature does not
expose, so an agent cannot know before calling whether the call is legal. A uniform rule is
checkable; a conditional one is a trap.

## D17. Complete and archived are different axes, and `complete` is a value, not a sentence

The operator: *"The loop can be marked as complete. The archivability is just to clean the UI."*

```
   LIFECYCLE — what happened                 VISIBILITY — housekeeping
   running ──┬──▶ complete  (queue drained)  ──▶  archived
             └──▶ stopped   (stop_at, operator,   operator only, hides
                             queue exhausted)     from default lists,
                                                  destroys nothing
```

**`complete` becomes a real state value on `Loop`.** Today `stop_reason` is `Text, nullable`
(`models.py:1226`) and `scheduler.py:102` writes the English string `"loop queue is empty"`. A
governance surface that wants to show or filter *"4 complete · 1 stopped early · 2 running"* cannot
string-match prose. `stop_reason` is kept beside the value as the human explanation — the value says
what class of ending it was, the prose says why.

**A loop that is running SHALL NOT be archivable.** Archiving one would hide unattended work that is
still firing, which is the exact governance failure loops exist to make impossible. This also
*replaces* a clumsier rule considered earlier in the session — "archiving must force
`enabled = False`" — because requiring stopped-or-complete first makes it unnecessary: `enabled` is
already false by then. Note `AIJob.enabled` is the **only** gate on firing (`scheduler.py:153, 227,
275`), so an archive path that skipped this would leave an archived loop firing invisibly.

**Rejected: derive "complete" by string-matching `stop_reason == "loop queue is empty"`.** It works
today and breaks the first time anyone rewords the message, which is a thing prose invites and a
value forbids.

**Rejected: one lifecycle with `archived` as its terminal state.** This is what the session assumed
before the operator corrected it. It conflates "this loop finished its work" with "I am tidying my
list," and it makes archiving destructive of meaning — an archived loop would no longer be able to
say whether it *succeeded*.

## D18. `delete_job` becomes `archive_job`, and always asks

With D16, the agent-callable `delete_job` has no valid target left. The operator: *"Agent can archive
only with the explicit direction from the user. So the mcp endpoint becomes archive."*

**The existing gate does not supply "explicit direction."** `_require_agent_job_allowance`
(`jobs.py:21-40`) checks `project.allow_agent_jobs` — a standing, project-level boolean. Once the
operator enables it, an agent may mutate recurring work unattended indefinitely. The route's own error
text treats them as alternatives: *"requires operator approval **or** an enabled allowance."*

**Decided: `archive_job` SHALL always produce an operator approval decision, independent of the run's
permission posture.** The standing allowance grants the capability; the approval supplies the
direction. This makes `archive_job` the first MCP tool with an always-confirm rule — recorded as a
deliberate precedent rather than inherited from `create_job`'s gate by copy-paste.

**Archiving a loop remains operator-only** and is not reachable by an agent at all, mirroring
`spec_lifecycle.py:241`. `archive_job`'s agent path therefore only ever targets a job with no loop.

**Rejected: gate `archive_job` on the standing allowance alone, like every other job tool.** It is the
consistent choice and it is not what was asked for: under an `auto` posture an agent would archive
without asking, which is the opposite of "only with the explicit direction from the user."

*Open, and deliberately not decided here:* whether an agent should be able to archive a bare job **at
all**, even with a card. D18 settles that the path always asks; it does not settle that the path
should exist.

## D19. The live-ness helper is D13's, and the panel change's own version is withdrawn

`2026-08-18-one-shell-three-panels` D6, written by a different firing about twenty minutes after D13,
decided on *"a new, job-scoped live-ness lookup... keyed by the loop's `AIJob.id` via its most recent
`JobRun.conversation_id`"* — **precisely the shape D13 rejected by name**: *"Rejected: deriving 'is a
firing running' by joining `JobRun.conversation_id` to `Run.status == "running"` and leaving the
column alone... it keeps a lie in the table and obliges every future reader to know to join."*

**Decided: D13 stands unchanged and the panel change's D6 is withdrawn.** This change owns the data
layer; a `JobRun.status` that cannot state its own value is a defect regardless of who reads it. D13's
own words already anticipated both callers: *"It should be one helper both callers use, not two
joins."* The loop tab is now specced in this change (D20) and is one of those two callers.

## D20. The loop surface is project-wide, and lives in this change

The panel change specced a loop tab showing *"the loop bound to the conversation's job."* **No such
binding exists.** `Conversation` (`models.py:369-405`) has no `job_id`; the only link is
`JobRun.conversation_id` (`models.py:1194`), and `scheduler.py:337-343` creates a **fresh
conversation per firing** whenever `session_mode` is `"new"` — which D4 guarantees is always, for a
loop, since `resume` is refused outright.

So a conversation-scoped loop view is empty in every conversation the operator actually sits in, and
duplicated across every firing conversation they do not.

**Decided: a project-wide loops index, plus a drill-down per loop**, and it is specced here rather
than in the panel change, because everything it displays is this change's data — the queue, the
claimed item, the briefing chain, D6's telemetry, D13's history and live-ness, D17's complete state.
The panel change owns the container it renders in; this change owns the tenant.

This supersedes this change's own D9 bullet — *"The side panel's loop view... `2026-08-18-the-side-
panel-family` is where that surface is specced"* — and the Non-Goal "Not building the side panel."
Both are edited in `proposal.md` rather than left to contradict this addendum.

**A gap it exposes:** `LoopSummary` (`schemas/jobs.py:70-81`) carries no name — the Jobs page labels a
loop with its *job's* name (`JobCard.tsx:197`). A picker needs a label, so `LoopSummary` gains one.

**Rejected: spec the loops index in the panel change with the rest of the panels.** It would put the
requirements for this change's data in a change that cannot test them — the panel change has no loop
to render.

## D21. `_batch_loop_summaries` cannot see a claimed task, and the fix belongs here

`_batch_loop_summaries`'s `current_task` candidates query (`jobs.py:122-124`) filters
`Task.status.in_(("in_progress", "blocked", "pending"))`. **`"assigned"` is absent**, while
`checkpoints.py`'s `_LIVE_TASK_STATUSES` (`:43-49`) and `task_transitions.py`'s `ENTRY_STATUSES`
(`:94`) both already treat it as live.

**D3 is what produces that status** — a firing claims its queue item by setting it. So the moment this
change ships, a freshly claimed task vanishes from `current_task` on the Jobs page's existing
`LoopBlock` *and* on D20's loops index, until something else moves it along.

**Decided: add `"assigned"` to the `IN` clause, in this change.** The panel change claimed this fix on
the grounds that it was the first surface to make the gap visible; that reasoning is now moot, and a
fix belongs beside its cause. One clause.

*Still open, carried from the panel change's D6 and not resolved here:* whether
`run_task_binding.py:250-254`'s automatic entry-status transition applies to a loop firing's binding
path, which would make `"assigned"` momentary rather than persistent. The fix lands either way — a
query that cannot represent a reachable status is wrong independent of how long that status lasts.
