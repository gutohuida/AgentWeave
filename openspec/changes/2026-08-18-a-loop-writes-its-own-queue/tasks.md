# Tasks — A loop writes its own queue

Nothing in this file has been started. Every box below is unchecked because this change is a spec
only — CLAUDE.md: "Never mark a task complete on the strength of a plan existing."

## 1. Migration

- [ ] 1.1 New migration, `down_revision` = the current head. Two additive, nullable, unindexed-except-
      as-noted columns, no existing constraint touched — same "no `batch_alter_table` recreate needed"
      shape as `0075`:
      (a) `ALTER TABLE loops ADD COLUMN spec_document_id VARCHAR(64)` nullable, no FK (design D1),
      plus a unique index (`uq_loops_spec_document_id`) so at most one loop can declare a given
      document.
      (b) `ALTER TABLE checkpoints ADD COLUMN loop_id VARCHAR(64)` nullable, no FK (design D4), plus
      `CREATE INDEX ix_checkpoints_loop_id`.
      Guard each step for a missing table, matching `0071`/`0073`/`0075`'s own precedent for an
      upgrade starting from an early revision.
- [ ] 1.2 `downgrade()`: drop `ix_checkpoints_loop_id` and `checkpoints.loop_id`, drop
      `uq_loops_spec_document_id` and `loops.spec_document_id` — same missing-table guard on each
      step.
- [ ] 1.3 Run `alembic upgrade head` then `alembic downgrade -1` then `alembic upgrade head` against a
      scratch SQLite file, confirming both directions actually execute — `0075`'s own precedent for
      catching a migration that parses but does not run.

## 2. Model (`hub/hub/db/models.py`)

- [ ] 2.1 `Loop.spec_document_id` (design D1): nullable, `String(64)`, no ForeignKey, `unique=True`,
      placed beside `job_id`, with the same "deliberately not a ForeignKey" comment reasoning `Task.
      spec_document_id`/`loop_id` already state, referenced rather than re-derived.
- [ ] 2.2 `Checkpoint.loop_id` (design D4): nullable, `String(64)`, no ForeignKey, indexed, placed
      beside `conversation_id`.

## 3. Queue-write path 1 — specification materialisation (`hub/hub/spec_tasks.py`)

- [ ] 3.1 `materialise()`: at the top, query `Loop` where `spec_document_id == document.id`. If found,
      every `Task` constructed in the function body gets `loop_id=loop.id` (design D1). No change to
      `materialise_quietly()`'s signature or error-swallowing behaviour.
- [ ] 3.2 Tests: a document with a declaring loop materialises tasks carrying that loop's id; a
      document with no declaring loop materialises tasks with `loop_id=None`, unchanged from today;
      re-approving a revised document (the existing idempotency path, `existing_keys`) still stamps
      `loop_id` on newly-created tasks only, matching the existing "only what's new" guarantee.

## 4. Queue-write path 1, creation side — declaring a source document (`hub/hub/api/v1/jobs.py`,
   `hub/hub/schemas/jobs.py`)

- [ ] 4.1 `JobCreate`/`JobUpdate` gain `spec_document_id: Optional[str]` (design D1). Creating or
      updating with a `spec_document_id` that another loop already holds SHALL 409, naming the
      conflicting loop (spec requirement "A document already claimed by one loop cannot be claimed by
      a second").
- [ ] 4.2 Tests: declaring a source document on loop creation; a second loop attempting the same
      document is refused with the first loop's id named in the error; a loop can be created with no
      source document, unchanged from `many-named-loops`.

## 5. Queue-write path 2 — creator authorship (`hub/hub/api/v1/tasks.py`, `hub/hub/mcp_server.py`,
   `hub/hub/schemas/tasks.py`)

- [ ] 5.1 `TaskCreate` schema and MCP `create_task` gain `loop_id: Optional[str]`.
- [ ] 5.2 `create_task` (both REST and the MCP tool, which calls the same REST route per the existing
      pattern): when `loop_id` is supplied, resolve the calling identity — `AgentActor.agent` for an
      agent-authenticated call, or the operator sentinel for an operator-authenticated one (design
      D1). Compare against the target loop's `AIJob.agent`. Equal, or operator → accept. Otherwise →
      403, message naming `send_message` to the creator (spec requirement "Only a loop's creator, or
      the operator, may add to its queue directly").
- [ ] 5.3 Apply design D7's extra gate on top of 5.2: when the calling agent equals both the target
      loop's creator *and* its `AIJob.agent` (self-created), and the loop has `run_count > 0` (has
      fired at least once), refuse the direct addition (403, naming that operator approval is
      required) regardless of 5.2's outcome. An operator-authenticated call is exempt from this gate,
      matching 5.2.
- [ ] 5.4 Tests: creator adds successfully (before and after first fire, for a loop with a distinct
      executor); operator adds successfully regardless of fire count; non-creator executor is
      refused, message names `send_message`; self-created loop accepts a creator addition before its
      first fire and refuses one after, message names operator approval.

## 6. Claiming the current item (`hub/hub/scheduler.py`)

- [ ] 6.1 New `_claim_loop_task(session, loop) -> Optional[Task]` (design D3): select the queue's
      existing active/non-terminal task if one exists, else the oldest entry-status task by
      `created_at`. Mirrors `_batch_loop_summaries`'s existing "current item" derivation
      (`jobs.py:98`) — read that function first rather than re-deriving the ordering independently,
      and factor the shared logic if it can be reused without changing `_batch_loop_summaries`'s own
      batch-query shape (design D7 of `many-named-loops`, which this task must not regress).
- [ ] 6.2 `_do_fire_job`: after `_loop_stop_reason` passes (fire proceeds), call `_claim_loop_task`
      when the job has a loop. If a task is returned and its status is an entry status, transition it
      to `assigned`/`in_progress` (whichever the existing task-transition machinery treats as the
      correct entry point — check `run_task_binding.py`'s declared transitions before picking one) and
      set `assignee=job.agent`. If it is already active, leave its status untouched.
- [ ] 6.3 Tests: a fire with only entry-status tasks claims the oldest; a fire with an existing
      active task resumes it rather than claiming another; a fire with an empty queue claims nothing
      and does not error (the stop-condition check already prevents this case when `stop_when_queue_
      empties` is set — assert the claim step itself is a no-op independent of that check, for a loop
      that has no `stop_when_queue_empties` and is allowed to fire on an empty queue).

## 7. Continuity — loop-scoped checkpoints (`hub/hub/checkpoints.py`, `hub/hub/checkpoint_generation.py`)

- [ ] 7.1 `create_checkpoint`: when the checkpoint's conversation's job has a `Loop` (join via
      `JobRun.conversation_id`, the same join `many-named-loops` D3 introduced), stamp
      `Checkpoint.loop_id` on the created row (design D4).
- [ ] 7.2 New `latest_checkpoint_for_loop(db, loop_id)` in `checkpoints.py`, mirroring
      `latest_checkpoint`'s shape and ordering (`created_at DESC, id DESC`) but filtered by
      `Checkpoint.loop_id` instead of `Checkpoint.conversation_id`.
- [ ] 7.3 `compute_envelope`: accept an optional `loop` parameter; when supplied, `tasks` is built
      from `Task.loop_id == loop.id` (every status, mirroring `TASK_SCOPE_NOTE`'s "explicit scope
      hides nothing" principle) instead of `_tasks_for(project_id, agent)`. Update the scope note text
      to say "loop" rather than "agent" for this case, matching the existing dishonesty-avoidance
      reasoning in `TASK_SCOPE_NOTE` itself.
- [ ] 7.4 Tests: a loop-scoped envelope's `tasks` matches the loop's queue regardless of status; a
      non-loop conversation's envelope is unchanged from today; `latest_checkpoint_for_loop` finds a
      checkpoint from a *different* conversation than the one it is called for, proving the
      cross-conversation join actually works (this is the one behaviour the whole task exists to add
      — a same-conversation-only test would not catch a regression to the old, narrower join).

## 8. Refusing resume for a loop's job (`hub/hub/api/v1/jobs.py`)

- [ ] 8.1 `create_job`/`update_job`: reject (400) a `session_mode="resume"` when the job has (or is
      being given, in the same request) a `Loop` row, naming checkpoint-based continuity as the
      reason (design D4, spec requirement "Setting resume mode on a loop's job is refused").
- [ ] 8.2 Tests: setting `resume` on a plain job still behaves exactly as before (unchanged, and
      still broken per `known_debts` — do not fix `AIJob.last_session_id`'s write path here, out of
      scope per Non-Goals); setting `resume` on a job that has, or is simultaneously given, loop
      fields is refused with the stated reason.

## 9. The briefing (`hub/hub/scheduler.py`)

- [ ] 9.1 New `_compose_loop_briefing(loop, claimed_task, prior_checkpoint) -> str` (design D5):
      purpose, claimed task (title/description/acceptance criteria), prior checkpoint content
      (rendered via the existing `render_checkpoint`-equivalent rendering, truncated to
      `_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`), and a one-line open/done queue summary reusing
      `_batch_loop_summaries`'s existing aggregation.
- [ ] 9.2 `_do_fire_job`: when the job has a loop, prepend the composed briefing to `job.message`
      before calling `new_entry` (design D5 — the operator's own message text is unchanged, the
      briefing is a prefix).
- [ ] 9.3 Tests: a first firing's briefing has no prior-checkpoint section; a later firing's briefing
      includes a prior checkpoint's content in full when under the cap; a prior checkpoint over the
      cap is truncated to exactly the cap, not omitted; a non-loop job's fired message is byte-
      identical to `job.message` (no briefing prepended) — this last one is the regression guard for
      every non-loop job in the suite.

## 10. Empty-queue telemetry (`hub/hub/scheduler.py`)

- [ ] 10.1 At the point `_loop_stop_reason` reports "loop queue is empty" (design D6), check for an
      unread `Message` from the executor addressed to the loop's creator, or an unanswered `Question`
      in the firing's conversation. Persist and broadcast a new `loop_queue_exhausted` event
      (`{job_id, loop_id, pending_request}`) alongside the existing `loop_stopped` event — a second
      event, not a folded field, per design D6's stated reasoning.
- [ ] 10.2 Tests: queue empties with no outstanding request → event's `pending_request` is null; queue
      empties with an unread message to the creator outstanding → event names it; queue empties with
      an unanswered question outstanding → event names it; the loop stops in every case (this
      requirement does not introduce a paused state — assert `job.enabled` is `False` and `Loop.
      stopped_at` is set exactly as `many-named-loops`'s existing stop path already does).

## 11. `create_loop` MCP tool (`hub/hub/mcp_server.py`)

- [ ] 11.1 New `@mcp.tool() create_loop(name, agent, message, cron, purpose="", stop_at=None,
      stop_when_queue_empties=False, spec_document_id=None, initial_tasks=None)` (design D2), gated
      by the same `_require_agent_job_allowance` `create_job` already uses. Refuses (400) creation
      when neither `stop_at` nor `stop_when_queue_empties` is supplied — a loop with no stop condition
      is refused outright, per design D2.
- [ ] 11.2 `initial_tasks`, if supplied, creates the named tasks with `loop_id` set to the new loop's
      id in the same call — the "definition window" design D7 treats as pre-first-fire authorship,
      not subject to D7's post-first-fire gate.
- [ ] 11.3 `test_mcp_tool_schemas.py`: assert `create_loop`'s generated schema agrees with the REST
      schema it calls, matching the existing pattern for every other MCP tool restated from the Hub's
      validators (CLAUDE.md's standing rule for `mcp_server.py`).
- [ ] 11.4 Tests: `create_loop` with no stop condition is refused; with a stop condition and no
      initial tasks, creates an empty-queue loop; with `initial_tasks`, creates a loop whose queue
      already holds them; with `spec_document_id`, creates a loop that later materialises tasks into
      its queue when that document is approved (integration test spanning 3.1 and 11.1).

## 12. Full-suite verification — agent-verifiable

- [ ] 12.1 `py -3.11 -m pytest hub/tests -q` — full suite green, including every new test above.
- [ ] 12.2 `py -3.11 -m mypy hub/hub/` (or the project's equivalent hub type-check command) clean.
- [ ] 12.3 `npx openspec validate --changes --strict` passes with this change included (already
      confirmed for the spec text itself; re-run after implementation in case a later edit to this
      file drifted from the delta).
- [ ] 12.4 Mutation-check design D3's claim logic: temporarily revert the deterministic-selection
      change to "always claim the newest task" and confirm the new test in 6.3 fails by name — the
      same mutation-testing discipline `Q2`'s merge-500 fix already applied this session.
- [ ] 12.5 Mutation-check design D8's identity check (5.2): temporarily remove the string-equality
      comparison (accept any caller) and confirm the new test in 5.4 (non-creator refusal) fails by
      name.

## 13. Human-only verification

- [ ] 13.1 **Does the claimed task actually match what the firing worked on?** Taste and correctness
      both — drive one real loop through two firings against a live agent (not a mock), read the
      second firing's transcript, and confirm the task it references is the one the board shows as
      claimed for that firing. This is the one place this change's whole premise (a firing knows its
      position) is either true or is not, and no unit test proves it end to end.
- [ ] 13.2 **Does the briefing read as useful context, or as noise the agent ignores?** Read a second
      firing's actual first turn. If the model's own opening response ignores the prior checkpoint's
      content entirely, the cap or the composition (design D5) may need revisiting — record what was
      observed rather than assuming the mechanism worked because it was present in the prompt.
- [ ] 13.3 **Does refusing a non-creator's task addition read as a helpful redirect, or a dead end?**
      Have an agent that is a loop's executor but not its creator attempt to add a task; read the
      403's message as the agent would receive it — does it plausibly lead the agent to actually send
      the message, or does it read like a bare permission error?
- [ ] 13.4 **The self-created-loop approval gate (D7) — does asking the operator actually work as a
      real interaction?** Drive an agent through creating a loop for itself, letting it fire once,
      then attempting an addition and going through the resulting `ask_user` flow for real. Confirm
      the operator sees a legible question, not a bare "may I add a task."

## 14. User test guide

**Setup.** A project with at least one registered agent and the operator's agent-job allowance
enabled (`_require_agent_job_allowance`, already required for any job-creating tool to work at all).
A short specification document with at least two declared tasks in its decomposition, not yet
approved.

1. **Create a loop bound to that document.** Use `create_loop` (or the equivalent job-creation UI
   once one exists) with `spec_document_id` set to the document's path and a `stop_when_queue_
   empties` stop condition. — *Expect:* the loop is created; its queue is empty (nothing approved
   yet).
2. **Approve the specification document.** — *Expect:* the loop's queue now holds the tasks the
   document declared — check via the task list scoped to the loop's id (`GET /tasks?loop_id=...`).
3. **Fire the loop once** (via its cron, or a manual trigger if one exists). — *Expect:* exactly one
   of the queue's tasks moves to an active status (claimed); the firing's message includes the
   loop's purpose and the claimed task's title and description, not just the job's own configured
   message.
4. **Let the claimed task reach a terminal status, then fire the loop again.** — *Expect:* the
   second firing claims a *different* task (the next oldest entry-status one); its briefing
   references what the first firing's checkpoint recorded — read the firing's transcript for
   language that plausibly reflects the first firing's outcome, not a generic restatement.
5. **Attempt to add a task to the loop as an agent that is not its creator.** — *Expect:* refused,
   with a message pointing at `send_message`.
6. **Drain the queue to empty and let the loop fire once more.** — *Expect:* the loop stops; check
   for a `loop_queue_exhausted` event (or its eventual UI surface) recording whether a request was
   outstanding when it stopped.

**Where it would go wrong:** if step 3's briefing is missing the claimed task's own text (only the
purpose and the operator's message appear), the composition in design D5/task 9.1 likely regressed.
If step 4's second firing shows no trace of the first firing's checkpoint, check
`latest_checkpoint_for_loop` is actually being called with the *loop's* id and not the new
conversation's id — the bug this whole change exists to prevent is exactly a checkpoint lookup that
silently falls back to "nothing found" because it is scoped to the wrong conversation.

---

# Addendum — tasks for the post-design decisions (D10–D15)

Added after the operator continued the design conversation. Sections A1–A5 are agent-verifiable;
A6 is human-only.

## A1. Control as a per-loop setting (design D10)

- [ ] A1.1 `loops.control` VARCHAR(32) nullable in the migration — **NULL means the current default**,
      never a stored copy of it, carrying `Agent.default_permission_mode`'s reasoning
      (`models.py:196`). Guard the migration step for a missing table.
- [ ] A1.2 Default the controller to the operator; delegation to the creator agent and back, after
      creation.
- [ ] A1.3 Route an extension request by controller: operator-controlled relays and changes nothing
      until the operator decides; delegated lets the creator decide.
- [ ] A1.4 **Reconcile with D7.** D7's first-fire boundary for self-created loops must now fall out
      of the default (control is the operator's, so nothing was delegated), not out of a separate
      role-identity check. Assert both routes reach the same outcome for a self-created loop, so the
      generalisation is proven rather than asserted.
- [ ] A1.5 Record each change of control against the loop with actor and time.

## A2. Editing, staged and visible (design D11)

- [ ] A2.1 Accept an edit at any time, including during a firing; store it as pending.
- [ ] A2.2 Apply pending edits at the next firing, before briefing.
- [ ] A2.3 Test that a firing in flight continues under the definition it was briefed with, with an
      edit landing mid-firing.
- [ ] A2.4 Report pending and in-force definitions **separately** — a requirement, not polish.
- [ ] A2.5 Record each edit against the loop with actor and time.

## A3. Late tasks (design D12)

- [ ] A3.1 Refuse a task added to a stopped loop, stating the stop reason and time. Refusal does not
      restart the loop.
- [ ] A3.2 Offer the refused task as the initial work of a new loop.

## A4. Per-loop history and a running firing (design D13)

- [ ] A4.1 A per-loop history home — `EventLog` is indexed by project and agent, not loop, so
      retrieving one loop's history must not mean scanning unindexed JSON.
- [ ] A4.2 Retrieve one loop's history; assert no event from another loop is returned.
- [ ] A4.3 `JobRun` records a firing as in progress while its run executes, distinct from completed
      and failed.
- [ ] A4.4 **One helper** answers "is a firing active for this loop", used by both the edit path and
      the loop panel in `2026-08-18-one-shell-three-panels`. Do not write it twice.
- [ ] A4.5 A crashed run must not leave a firing permanently in progress — reconcile on Hub restart
      as `Run.pid`/`last_heartbeat_at` already does.

## A5. Immutability and the identity gap (designs D14, D15)

- [ ] A5.1 `Task.loop_id` is write-once, enforced at the service layer, not by a DB constraint.
- [ ] A5.2 Test that reassigning a task between loops is refused and the task is unchanged.
- [ ] A5.3 **Record, do not fix, the name-reuse gap** (D15): a new agent taking an archived agent's
      name satisfies every creator check the original did. Add a test that *documents* the current
      behaviour so a future change closing it has something to flip, and reference D15 in its name.

## A6. Human-only — the operator's judgement

- [ ] A6.1 **Does "pending versus live" read clearly enough to trust?** Stage an edit during a firing.
      Not whether both are shown, but whether it is obvious which is in force right now.
- [ ] A6.2 **Is the refusal of a late task helpful or merely correct?** Does it read as the product
      helping, or as it saying no?
- [ ] A6.3 **Is delegating control discoverable without being easy to do by accident?**
- [ ] A6.4 **Does a loop's history read as a story or as a log?** It is the governance surface; if it
      cannot be skimmed it will not be read.

## A7. Additions to the user test guide

Run after the guide already in this file:

10. **Delegate control.** Delegate to the creator agent, then have the executor request work again.
    - *Expect:* the creator decides without involving you, and the change appears in the loop's
      history.
11. **Edit during a firing.** While a firing runs, change the loop's purpose.
    - *Expect:* accepted, marked pending, the running firing unaffected; live at the next firing.
12. **Add a task after it stops.**
    - *Expect:* refused, stating when and why it stopped, and offering the task to a new loop.

**Where it would go wrong.** If step 10 lets the creator decide *before* you delegated, A1.3 is not
reading the controller. If step 11's edit disturbs the running firing, A2.2 is applying immediately
rather than staging. If step 12 revives the loop, A3.1 is restarting it, which D12 rejected.

---

# Addendum 2 tasks — archival, ending state, and the loops surface (D16–D21)

Added after the operator conversation recorded in
`openspec/explorations/2026-08-18-the-side-panel-with-the-operator.md`. **B5 and B6 depend on
`2026-08-18-one-shell-three-panels` having landed its shell** — they are the shell's first non-spec
tenant. Everything in B1–B4 is independent of it and can land first.

## B1. Migration and model

- [ ] B1.1 Extend the migration from 1.1 (or add a follow-on, whichever is the current head at
      implementation time) with three more additive nullable columns, same missing-table guard as the
      rest: `loops.archived_at` (DateTime, timezone-aware), `ai_jobs.archived_at` (same), and the
      column recording **how a loop ended** as a value (D17) — a short string, nullable, NULL while
      running.
- [ ] B1.2 Leave `loops.job_id`'s `ondelete="CASCADE"` in place and add a comment saying why: no
      delete path survives D16, so it is unreachable, and dropping it on SQLite forces a table recreate
      for no behavioural change.
- [ ] B1.3 Bump the head assertions in **both** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py` (CLAUDE.md requires both).
- [ ] B1.4 Decide and document the permitted values for B1.1's ending column in `models.py`, in a
      comment next to it, the way `Loop.purpose` and `Loop.stop_reason` already carry their reasoning.
      At minimum: completed (queue drained) and stopped (everything else), with `stop_reason` still
      carrying the prose.

## B2. Archival replaces deletion

- [ ] B2.1 `DELETE /api/v1/jobs/{job_id}` refuses with a stated reason naming archiving as the
      alternative. Do not silently reinterpret a delete as an archive — a caller that asked to destroy
      data should be told it did not happen.
- [ ] B2.2 Archive route for a job, and for a loop. A loop's is **operator-only** — refuse any request
      carrying agent attribution, mirroring `spec_lifecycle.py:241`'s own rule for documents.
- [ ] B2.3 Refuse to archive a loop that is neither complete nor stopped (D17), stating that it must
      end first. Test that an enabled, firing loop cannot be archived.
- [ ] B2.4 Archived loops and jobs are excluded from default listings and included when explicitly
      asked for. Nothing is removed from the database.
- [ ] B2.5 Set the ending value from B1.1 where the loop actually ends: `scheduler.py`'s stop-condition
      path sets *completed* when the queue drained, *stopped* for `stop_at` and for an operator stop.
      `stop_reason`'s existing prose is unchanged and keeps its current wording.
- [ ] B2.6 Regression test: a loop archived after stopping still returns its purpose, queue history,
      firings, and stop reason. This is the D16 guarantee and the one most likely to rot.

## B3. `archive_job` on the MCP surface

- [ ] B3.1 Replace `delete_job` with `archive_job` in `hub/hub/mcp_server.py`. Remember the file is
      spawned standalone and may import only stdlib + fastmcp; anything it needs from the Hub is
      restated there, with the existing test asserting the two agree.
- [ ] B3.2 `archive_job` produces an operator approval decision on **every** call, independent of the
      run's permission posture (D18) — the standing `project.allow_agent_jobs` allowance grants the
      capability, not the direction. Test both postures.
- [ ] B3.3 `archive_job` refuses when the job has a loop, since a loop is operator-only (B2.2).
- [ ] B3.4 Update the tool-surface count and description in `CLAUDE.md` if the totals move, and update
      whatever test asserts the tool list matches the tools.

## B4. The loop summary tells the truth

- [ ] B4.1 Add `"assigned"` to `_batch_loop_summaries`'s `current_task` candidates query
      (`jobs.py:122-124`) — D21. One clause. Test with a task in `assigned` and nothing else.
- [ ] B4.2 `LoopSummary` gains the label the operator recognises a loop by (D20), sourced from the
      loop's job rather than requiring a second fetch, plus the ending value from B1.1 and whether it
      is archived.
- [ ] B4.3 Project-scoped list and detail endpoints for loops that require **no conversation id** —
      the reason D20 exists. Detail returns queue, current item, firing history (D13) and whether a
      firing is in progress (D13's helper, not a second join — D19).

## B5. The loops index tab

- [ ] B5.1 A `loops` index panel listing the project's loops: label, purpose, running/complete/stopped,
      queue counts, open questions. Registered in the shell as a singleton index tab.
- [ ] B5.2 Clicking a loop opens a `loop:<loop_id>` drill-down tab. The index **stays open** — unlike
      the files tree, which the shell's own design has a file replace (see the panel change). The
      distinction is deliberate: the index is a governance glance, not a launcher.
- [ ] B5.3 Counts by ending state (*"4 complete · 1 stopped early · 2 running"*) computed from B1.1's
      value, never by matching `stop_reason` text.
- [ ] B5.4 Archived loops are out of the index by default, reachable behind an explicit filter.

## B6. The loop drill-down tab

- [ ] B6.1 A `loop:<loop_id>` panel: purpose, stop condition, ending state and reason, queue counts by
      status, the claimed item, open questions, and the firing history.
- [ ] B6.2 The active-now indicator consumes **D13's helper** — the same one the loop's own machinery
      uses. Do not add a second join over `JobRun.conversation_id`/`Run.status` (D19).
- [ ] B6.3 Motion only on the active-now indicator; queue counts and ending state update without a
      transition. A CSS-driven animation inherits `index.css`'s existing blanket reduced-motion rule; a
      JS-driven one needs its own `matchMedia` check.
- [ ] B6.4 Live updates via `useSSE` plus React Query invalidation on the relevant events, including
      `loop_queue_exhausted` from D6 — this is that event's first consumer.
- [ ] B6.5 A loop that has ended still renders completely. The tab is the governance record; it is most
      valuable *after* the loop finished.
- [ ] B6.6 Audit the `Icon` map before assuming a loop/queue/claimed-item icon exists. `Icon` only —
      CLAUDE.md forbids a second icon system.

## B7. Human-only — the operator's judgement

- [ ] B7.1 **Does the loops index answer "what is running right now" at a glance**, without opening a
      drill-down? That is the whole reason it stays open when a drill-down is opened.
- [ ] B7.2 **Does a refused delete read as the product protecting history, or as it being obstinate?**
      B2.1's message is the entire experience of D16 for anyone who meets it.
- [ ] B7.3 **Is "complete" visibly different from "stopped early"** at a glance, or do they read as the
      same grey badge? If they read the same, B1.1's value bought nothing a sentence did not.
- [ ] B7.4 **Does `archive_job`'s always-ask feel like protection or like nagging** after the fifth
      time? D18 set a precedent; this is where it gets tested against real use.

## B8. Additions to the user test guide

Run after the guides already in this file:

13. **Try to delete a loop's job.** Use the UI, then the API directly.
    - *Expect:* refused both ways, naming archiving. The loop still exists with its full history.
14. **Archive a running loop.**
    - *Expect:* refused, stating it must stop or complete first.
15. **Let a loop drain its queue, then archive it.**
    - *Expect:* it records *completed* (not merely "stopped"), disappears from the default index, and
      is still fully readable when archived loops are shown.
16. **Ask an agent to archive a bare job**, with the allowance enabled and permissions on auto.
    - *Expect:* you are still asked to approve it. If it happens silently, B3.2 is reading the
      allowance as direction.
17. **Open the loops index, drill into a loop, then look at the index again.**
    - *Expect:* both tabs open; the index did not close when the drill-down opened.

**Where it would go wrong.** If step 13 succeeds anywhere, D16 is not enforced at the route and only
in the UI. If step 15 shows "stopped" rather than "completed", B2.5 is not setting the value at the
drain path. If step 16 archives silently, B3.2 fell back to `create_job`'s allowance-only gate.
