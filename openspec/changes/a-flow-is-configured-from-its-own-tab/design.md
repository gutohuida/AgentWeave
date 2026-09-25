# Design — a flow is configured from its own tab

**Round 1, 2026-09-25.** Decisions made with the operator in an interactive explore are marked
**(operator)**; the rest are this round's and are open to R2/R3.

## Round 3, 2026-09-25

Re-derived against HEAD `3f15bae`, from the code rather than from Round 2's notes. **Changed:**

1. **The shared "firing active" helper must live in `scheduler.py`, not `jobs.py`.** `api/v1/jobs.py`
   imports `scheduler` at module level (`jobs.py:19`). `_do_fire_job` importing a helper back from
   `api.v1.jobs` would be a cycle. The query leaves `_batch_loop_summaries` (`jobs.py:454-465`)
   for `scheduler._jobs_with_active_firing(session, job_ids) -> set[str]`, and both call it (D2a,
   task 2.3a).
2. **A staged agent change could resume the old agent's provider session.** `_do_fire_job` looks
   up the resumed conversation for `job.agent` at `:3056-3064`, before the loop is loaded, and both
   D2a's early application and the late one at `:3179` come after it. A loop in resume mode would
   then hand A's session and thread to B. D4 of `many-named-loops` stops a loop being *set* to
   resume, but only when `session_mode` is in the same PATCH (`jobs.py:1083-1092`). A resume-mode
   plain job opted into a loop by a later `{"purpose": ...}` keeps `resume`. D2 now says a firing
   that applies an agent change drops what it looked up for the old agent. The ADDED requirement
   is widened from "a plain job" to any job, and test 1.2a is added.
3. **The Spec-destination link would land on the document, not the loop.** On mount,
   `ConversationView`'s destination-to-store effect (`ConversationView.tsx:220-233`) calls
   `openTab(specTabId(...))` for the attached document. That makes the document tab active, so
   `openTab(loop)` followed by a navigation *with* the document leaves the loop tab behind it.
   D4 now navigates with `document: null`. The shell is open because `openTab` set `isOpen`, and
   the loop tab is the active one. Back returns to the Spec page and its document.
4. **The `except` path of `_do_fire_job` is now handled here rather than filed.** Round 2 left
   this as a residual, but D2a makes it this change's problem. That path commits whatever the
   session holds (`scheduler.py:3549-3571`). D2a applies the edit earlier, so a firing that raises
   anywhere after that point commits an applied edit and emits no `loop_edit_applied`. The same
   block also reads `acting_agent`, which is first bound at `:3254`. An exception between the
   `JobRun`'s creation (`:3095`) and `:3254` (the skip check, `_loop_stop_reason`) therefore
   raises `UnboundLocalError` out of the handler. On a Run press, `run_job`'s own `except`
   (`jobs.py:1532-1537`) then commits through `_record_job_run_failure`, taking the half-updated
   run and the applied edit with it. Task 2.3a binds `acting_agent` and `pending_edit_payload`
   before the first statement that can raise, and emits `loop_edit_applied` after the handler's
   commit. Test 1.3c covers it. The fix is three lines in a block this change already rewrites.
5. **`loop_edit_applied` now changes a job column**, so `useSSE` also invalidates the jobs keys on
   it (D6). Today it invalidates only loops (`useSSE.ts:543-556`), so `useJob` and the jobs list
   would keep naming A after B is in force.
6. **An `agent` in the same PATCH that opts a job into being a loop.** The loop is looked up
   *before* the loop-fields branch creates one. A loop created by this call has no firing to
   protect, so it takes the agent at once, as it does its other fields (`jobs.py:1029-1035`). One
   PATCH makes one `loop_edit_staged`, whose `changes` carry every staged field.
7. **Test 1.4's claimed mutation could not fail.** `update_job` commits once (`:1145`), and
   `get_session` commits nothing on a raise (`db/engine.py:166-169`). A check placed after the name
   is set, but before the commit, therefore leaves the name unchanged too. The named mutation is
   now "check after the commit".
8. **The requirement says what "next firing" means under D2a.** An edit applied at a firing that
   is then refused as busy, or skipped, was already the behaviour for the stall and in-flight
   paths (`:3295`, `:3329`, `:3339`). Adding the busy refusal needed a sentence in the MODIFIED
   requirement, so it no longer reads as though a briefing must follow.
9. **Migration number.** Many open changes add migrations, so this change takes the next free
   revision at build time: `0108` if it builds first, with `down_revision` set to the head at
   build time. D5's default name is the document title truncated to `JobCreate.name`'s 256.
10. Test 1.3a names its setup: an open, unassigned task and a future `stop_at`. Without them the
    documentless loop's firing stops or proceeds empty, and "queued for B" is not what gets tested.

**Checked and held:** the agent plane's `PATCH /agent-actions/jobs/{job_id}` passes `actor.agent`/
`actor.run_id` as `agent_identity`/`run_identity` (`agent_actions.py:857-871`). The operator
route needs an operator credential (`auth.py:134-159`), so "headers present" means an agent's run.
`_require_agent_job_allowance` is `update_job`'s first statement and refuses incomplete or stale
attribution itself. The 403 for `agent` therefore sits after it, and before the first mutation at
`:1010`. The busy guard, the skip check, the late staging at `:3179`, every `loop_edit_applied`
emit site, and the fact that the busy path records no `JobRun` all hold. `run_job` re-asks
`_loop_flow_busy_refusal` with the same in-memory `job` (`jobs.py:1473`), so after an early
application its 409 names B, which is what 1.3b expects. The only `loop_edit_*` consumer is
`useSSE`. `_batch_loop_summaries`' firing-active join (`JobRun` `in_progress` joined to a
`running` `Run` on the same conversation) also covers a flow's extra selections, each of which has
its own `JobRun` and conversation. `openTab` sets `isOpen` (`panelTabsStore.ts:326-348`).
`SpecPhaseBar` reads `kind`/`phase`/`id` from `useSpecDocuments`. `loopTabId`, `agentDestination`
and the `onOpenTasks` threading are where Round 2 said. Both MODIFIED blocks carry the complete
current text of `openspec/specs/agent-loops/spec.md`, line for line, and no other open change
modifies either requirement. Every requirement's first line has SHALL. `0080` is the right model,
and `HEAD_REVISION` (`test_migrations.py:40`) and `test_project_persistence.py:227` are the two
head assertions.

**Residual, recorded rather than closed:** "a firing is active" is `JobRun in_progress` with a
`running` `Run`. Between a firing's commit at `:3479` and `schedule_agent` creating its `Run`,
several awaits can interleave with a concurrent tick or Run press. That press sees no active firing,
applies B, and can start B's firing beside A's on a documentless loop. Today the same window
yields a duplicate briefing for A, because the guard also reads only `running` `Run`s. Counting an
`in_progress` `JobRun` with no `Run` yet as active would close it, but would also count A's held,
queued firing, and that brings back the defect D2a fixes. File it as a finding if it is ever seen.

## Round 2, 2026-09-25

Re-derived against HEAD `1cddc75`. **Changed:**

1. **D2's staging argument was half right, and the fix as written could not fire in the case that
   most needs it.** `_stage_pending_loop_edit` runs at `scheduler.py:3179`, *after* the busy guard
   (`:3077`) and `_job_agent_skip_reason` (`:3110`), and both ask about the live `job.agent`. The
   guard's "busy" includes a provider **hold** (`_loop_agent_busy_reason`, `scheduler.py:255-291`).
   So on a documentless loop, or on a flow whose queue is empty or has no other free agent, a switch
   away from a held agent never gets applied. The next firing is refused before it reaches
   `:3179`, and that repeats every tick until A's reset. A spent allowance is the likeliest reason
   to switch agents. Added **D2a**: the staged edit is also applied *before* the guard when no
   firing of this job is active. Also corrected the hazard itself. A Run press beside a running
   firing is a hazard only where the guard serialises, i.e. a documentless loop, or a flow with
   nobody else free or nothing queued. For a flow with a free agent, D12 already lets a firing run
   beside the job agent's. Spec scenario, task 1.3 and the test guide are now scoped that way.
2. **An agent edit on a loop never reaches the staging code as R1 wrote it.** `update_job` loads
   the loop only when `loop_fields_supplied` (`jobs.py:989-1000`), and `agent` must not join that
   set: it would opt a plain job into being a loop. D2 now says the loop is looked up for `agent`
   on its own. It also says the agent check runs before any mutation.
3. **A staged agent and a revert.** If the panel diffed against the live values, a revert back to A
   would send nothing, and B would still be applied. D1 now diffs against what the form opened
   with, which is the staged value where one exists. A revert then stages A, which applies as a
   no-op, the same way a reverted purpose already works.
4. **`agent` becomes writable by agents.** `JobUpdate` is also the body of the agent-plane
   `PATCH /agent-actions/jobs/{job_id}` (`agent_actions.py:857-871`, gated only by `allow_agent_jobs`). A run
   could re-point any loop at itself, and under `control="creator"` it would take over who may add
   to the queue (`tasks.py:676-704`). D2 now refuses `agent` from an agent caller (403). **Needs
   the operator's confirmation.**
5. **D4 / task 3.1 answered.** The navigation already exists: `usePanelTabsStore.openTab(projectId,
   loopTabId(id))`, called from outside `ConversationView` by `ConversationRow.tsx:290` and
   `LoopFiringGroup.tsx:94`. But `SpecPhaseBar` has two hosts. One is the conversation view's panel
   (`ConversationView.tsx:384`), where the tab appears at once. The other is the Spec destination
   (`SpecPage`, `App.tsx:428-446`), where no panel shell is mounted, so `openTab` alone changes
   nothing on screen. D4 now threads an `onOpenLoop` prop the way `onOpenTasks` is threaded.
6. **Freshness after starting a flow.** `job_created` invalidates only `jobs` (`useSSE.ts:521-536`),
   and `useCreateJob` does the same (`jobs.ts:198-205`). After **Start a flow…**, the phase bar would
   keep offering Start a flow until something else refetched loops, and a second press answers 409.
   D6 now has the create invalidate loops, and `job_created`/`job_updated`/`job_deleted` invalidate
   loop keys.
7. **D5: `useDialogFocus` already exists** (`hub/ui/src/hooks/useDialogFocus.ts`). What the
   dialog-focus change adds is moving focus and the `data-dialog-initial-focus` mark. The route
   does not refuse `work_needs_evidence` beside a document. Only the MCP `create_flow` does,
   client-side (`mcp_server.py:836-844`). So the dialog must not send it, and must itself refuse to
   submit with no stop condition, as `create_flow` does (`:821`).
8. **The Settings panel needs the job.** `LoopDetail` carries `label`, `agent` and `job_id`, but not
   `message` or `cron`. D1 now reads `useJob(loop.job_id)`. `job_updated` already invalidates that
   key.
9. **Migration corrected.** The head is `0107`, so this is `0108`. `recreate="never"` is not this
   repo's idiom for an add. `0080_loop_pending_edit.py` is the model: a guarded plain
   `op.add_column`, `String(64)` like `AIJob.agent`, and bump `HEAD_REVISION`
   (`test_migrations.py:40`) and `test_project_persistence.py:227`
   (`.claude/rules/db-migrations.md`). `_stage_pending_loop_edit(loop)` has one caller (`:3179`) and
   needs the job, so its signature becomes `(loop, job)`.
10. **Collisions R1 missed.** B5's `a-document-moves-forward-only-through-its-checks` and
    `a-documents-rigor-history-and-retired-requirements-are-on-screen` also edit `SpecPhaseBar.tsx`
    and `specPhaseBar.test.tsx`, in different regions. B10's task 2.5 adds hooks to the
    `@/api/loops` mocks in `loopTab.test.tsx` and `loopPendingEdit.test.tsx`, and this change must
    add its own to the same factories. Change 2 renders **Start a flow…** in a second place
    (`SpecApprovalReport`), so the lookup is now one hook (`useDocumentFlow`) and the dialog is
    host-agnostic.

**Checked and held:** every R1 citation for `update_job` (`:906-1171`), the table of fields, the
422 for `agent`, `_check_agent_exists` (`:181-236`, and it passes silently when the project has no
roster yet), `useUpdateJob` having no caller, `LoopTab` not rendering `agent`, the creator being
`job.agent` (`tasks.py:611`, `:678-704`), the plain-job resume hazard (`scheduler.py:3056`), and
`LoopSummary` lacking `spec_document_id`. `GET /loops` excludes archived loops by default and
orders by `Loop.created_at` ascending (`loops.py:112-133`). The partial unique index `ux_loops_spec_document_live` on
`loops.spec_document_id WHERE archived_at IS NULL` (`models.py:1570-1575`, F53) means at most one listed
loop can match a document, so the lookup does not depend on order. The F190 fixture rule is met by
using the route's order and shape, and task 3.5 says so. The B10 and B11 order claims hold. B10
moves `loop_edit_staged` into the transaction but leaves `job_updated`'s handler alone. B11 makes a
document without an opt-in a 400 (its D4), and the dialog always opts in. Both MODIFIED
requirements carry the full current text. Residual, not fixed here: the `except` path of
`_do_fire_job` (`scheduler.py:3549-3572`) commits an edit already applied in memory without
emitting `loop_edit_applied`. That is true today for purpose and stop, and the agent inherits it.

## Context

A flow is one `AIJob` row and one `Loop` row, with `Loop.spec_document_id` set (agent-flows "A flow
is a loop that declares a specification document"; design D1 of that change: "a configuration, not
a record"). Everything below edits those two rows through routes that already exist, apart from one
new field (`agent`) and one new column (`loops.pending_agent`).

What `PATCH /jobs/{job_id}` does today (`hub/hub/api/v1/jobs.py:906-1171`):

| Field | On a loop | Where |
|---|---|---|
| `name`, `message`, `cron`, `session_mode`, `enabled` | applied immediately (cron re-registered) | `:1098-1141` |
| `purpose`, `stop_at`, `stop_when_queue_empties` | **staged** in `Loop.pending_*`, event `loop_edit_staged`, applied by `scheduler._stage_pending_loop_edit` at the next firing | `:1036-1059`, `scheduler.py:2348-2419` |
| `spec_document_id` | claimed and adopted at once | `:1017-1027` |
| `stop_reason` | ends the loop | `:1068-1076` |
| `agent` | **not accepted (422, `extra="forbid"`)** | `schemas/jobs.py:56-72`, `schemas/common.py:21-32` |

## Decisions

### D1 — The panel lives on the loop's own tab (operator: panel first)

`LoopTab.tsx` gains a **Settings** section above the pending-edit panel. At rest it states the
settings in force, including the **default agent**, which the tab does not show today. **Edit**
turns them into inputs, and **Save** sends only the fields that changed.

- **Where the values come from (R2).** `LoopDetail` has `label`, `agent`, `purpose`, the stop fields
  and `job_id`, but no `message` or `cron`. The tab also reads `useJob(loop.job_id)`
  (`api/jobs.ts:170-177`), which `job_updated` already invalidates (`useSSE.ts:522-530`).
- **What "changed" means (R2).** Each input opens on the value that will govern the **next** firing:
  the staged value from `pending_edit` where there is one, and otherwise the live value. A field is
  sent when it differs from what it opened on. If the operator staged B and then puts A back, the
  panel sends `agent: "A"`, which stages A as a no-op. A diff against the live values would send
  nothing, and B would still be applied.
- The agent select lists `useAgents()` (open agents), and keeps the current value as an option even
  when that agent is not in the list, so an archived agent's loop still renders its settings.

- **Editable:** name, default agent, message, cadence (cron, with the `lib/cron` previews and the
  ambiguity check `JobForm` already uses), purpose, and stop condition (stop at a time, and/or when
  the queue empties).
- **Shown, not editable:** the declared document (a flow's identity; rebinding a flow to another
  document is a new flow, not a setting) and `work_needs_evidence` (declared at creation, agent-loops
  "A loop declares at creation whether its work needs evidence").
- The panel never sends `stop_reason`. Stopping is B10's Stop action.
- An ended or archived loop shows Settings read-only. Editing a loop that will not fire again would
  stage an edit nothing ever applies.

Staged fields come back as `pending_edit` and appear in the existing "In force now / From the next
firing" panel, so the panel needs no second rendering of what is pending. Name, message and cron
apply at once, and the Settings section reflects them on save.

### D2 — The default agent is editable, and on a loop it is staged

`JobUpdate` gains `agent: Optional[str]` (`max_length=64`, as `AIJob.agent`), checked by
`_check_agent_exists` (`jobs.py:181-236`; unknown and archived names refused 400), as agent-loops
"A job SHALL name an agent that exists" already requires for an update. The check passes silently
when the project has no roster yet (its own docstring), so the refusal tests seed a roster.

**Where it sits in `update_job` (R2).** The check runs at the top, beside the `work_needs_evidence`
refusal (`:979`), before anything is mutated, so a 400 leaves nothing half-applied.

`agent` does **not** join `loop_fields_supplied` (`:989-995`). That set opts a plain job into being
a loop (`:1000-1016`), and an agent is not a loop field. The loop is looked up on its own when
`body.agent` is given (`_job_loop`, `:1360`), **before** the loop-fields branch can create one (R3).
A loop that already existed stages the edit. Without one, including a loop this same PATCH opts
into existence, the agent is applied at once, as that new loop's other fields are
(`:1029-1035`). One PATCH makes at most one `loop_edit_staged`, and its `changes` carry every
field staged, `agent` included.

**Operator-only (R2; needs the operator's confirmation).** `JobUpdate` is also the body of the
agent-plane `PATCH /agent-actions/jobs/{job_id}` (`agent_actions.py:857-871`), gated only by
`allow_agent_jobs` (`jobs.py:31-53`). Accepting `agent` there would let a run re-point any loop at
itself. Under `control="creator"` that run then decides what enters the queue
(`tasks.py:676-704`). `update_job` refuses `agent` with 403 when `agent_identity` or `run_identity`
is present: *"only the operator can change which agent a job names"*. No MCP tool sends it
(`toggle_job` sends only `enabled`, `mcp_server.py:926`).

**On a loop, an agent edit is staged, not applied at once.** The hazard is narrower than R1 stated.
The busy guard (`_loop_flow_busy_refusal`, `scheduler.py:355-399`, at `:3077`) asks about
`job.agent`. For a loop that declares no document, and for a flow with nothing queued or nobody
else free, that guard is what keeps the loop to one turn at a time. Changing `job.agent` to B while
A's firing runs would make it ask about B, and a Run press or a tick would start B's firing beside
A's. For a flow with a free agent and open work, the guard already lets a firing proceed beside the
job agent's turn (flow design D12), so staging protects nothing there that is not already allowed.
The agent is staged anyway, because agent-loops "An edit to a loop takes effect at its next firing
and never during one" states one rule for a loop's definition, and the agent joins purpose and stop:

- New nullable column `loops.pending_agent` (migration `0108`, D7).
- `_stage_pending_loop_edit(loop, job)` applies it to `job.agent` with the other pending fields, and
  `loop_edit_applied` carries `{"agent": {"from", "to"}}`. `_stage_pending_loop_edit` has one caller
  (`:3179`); the signature change adds the job.
- **A firing that applies an agent change resumes nothing of the old agent's (R3).** `_do_fire_job`
  looks up the resumed conversation for `job.agent` at `:3056-3064`, before either application
  point. When the applied payload carries `agent`, `_stage_pending_loop_edit` sets
  `job.last_session_id = None`, and `_do_fire_job` drops the `conversation` and
  `resume_session_id` it looked up for A. On the late path it also clears `run.session_id`,
  because the `JobRun` was built with A's session at `:3102`. A loop is meant never to resume (D4
  of `many-named-loops`), but `jobs.py:1083-1092` checks that only when `session_mode` is in the
  same PATCH. So a resume-mode plain job later opted into a loop keeps `resume`, and this is
  reachable.
- `loop_edit_staged`'s `changes`, `_pending_loop_edit` (`jobs.py:528-545`) and so
  `LoopSummary.pending_edit` include `agent`. The TS `LoopPendingEdit` (`jobs.ts:29-35`) gains
  `agent?`, and `LoopTab`'s `stagedFields` gains a "Default agent" row.
- `pending_edit_at` stays the sentinel. Its comment and `0080`'s docstring say "one of the three
  pending fields", which becomes four.

**On a plain job (no loop), an agent edit applies at once and clears `last_session_id`,** when the
name actually changes. A resume-mode job would otherwise hand the old agent's provider session to
the new agent (`scheduler.py:3056-3064`), which the product refuses where a flow's selection
diverges from its job's agent (`_fire_additional_selection`'s docstring, `:3686-3690`). No scheduler
re-registration is needed, because a firing reads the job back by id (`_fire_job_by_id`, `:2994-2999`).

**What the edit does not move** (stated in the panel's help text and in the spec):

- Tasks already assigned keep their assignee (agent-loops: staffing "never takes work away").
- Input already queued for the old agent stays with it.
- The flow's checkpoint lineage is keyed by the loop (`Checkpoint.loop_id`), so it survives.
- **`control="creator"` follows the new agent.** The creator *is* `job.agent` (`api/v1/tasks.py:611,
  678-704`); there is no separate column. Adding one to preserve the original creator is not this
  change. The panel says so when control is `creator`.

### D2a — A staged edit is also applied before the busy guard, when no firing of the job is active (R2)

**The defect in R1's version.** In `_do_fire_job` the order is: the busy guard asks about
`job.agent` (`:3077`), then `_job_agent_skip_reason` asks about it (`:3110`), and only then
`_stage_pending_loop_edit` runs (`:3179`). The guard's "busy" includes a provider **hold**
(`_loop_agent_busy_reason`, `:255-291`). Take a documentless loop, or a flow whose queue is empty
or has nobody else free, whose agent A has spent its allowance. The operator switches it to B. Every
tick is refused at `:3077` because A is held, so `:3179` is never reached and B is never applied
until A's reset. A self-registered poll agent is skipped at `:3110` the same way, forever. The
switch the operator makes *because* A cannot work is the one that cannot take effect.

**The rule.** At the top of the `if loop is not None:` block (`:3070`), before the guard: if
`loop.pending_edit_at` is set **and no firing of this job is active**, call
`_stage_pending_loop_edit(loop, job)` there. The guard, the skip check and `decide_firing` then all
ask about the agent that will run. "A firing is active" is `_batch_loop_summaries`' existing
`firing_active` fact: a `JobRun` in `in_progress` whose conversation has a `Run` in `running`
(`jobs.py:454-466`, read at `:487`). That query moves into one helper that both call, so the panel's "Running now"
and this gate cannot disagree. The helper lives in `scheduler.py` (`_jobs_with_active_firing(session,
job_ids) -> set[str]`), because `api/v1/jobs.py` imports `scheduler` at module level (`:19`) and the
reverse import would be a cycle (R3). While a firing is active the edit is left for `:3179`, exactly as
today. For a documentless loop that means the guard still asks about A, A is running, and the
firing is refused, which is the protection D2 exists for.

- `pending_edit_payload` is bound before the guard. `:3179` becomes
  `pending_edit_payload = pending_edit_payload or _stage_pending_loop_edit(loop, job)`. The two
  early returns that follow an early application also emit `loop_edit_applied` after their commit:
  the busy refusal (commit at `:3089`) and the skip (commit at `:3114`). Every later return already does.
- **The `except` path (R3).** `pending_edit_payload = None` and `acting_agent = job.agent` are
  bound before the first statement in the `try` that can raise. Today `acting_agent` is first bound
  at `:3254`, and the handler reads it (`:3563`, `:3568`), so an exception between `:3095` and
  `:3254` raises `UnboundLocalError` out of the handler. After its commit, the handler emits
  `loop_edit_applied` when a payload was made, so the applied edit it commits is recorded. When no
  `JobRun` exists yet, the handler commits nothing, the session rolls back, and the edit stays
  staged. That is consistent as it stands.
- This moves purpose and stop too, not only the agent. That is deliberate. Applying them at a tick
  where no firing of the loop is running is still "between firings". Splitting the agent from the
  others would need a second sentinel and two `loop_edit_applied` events for one edit.
- **What it leaves:** a firing queued for A but not yet running (A held with an entry already
  queued) is not "active", so B is applied and may fire while A's queued briefing waits. That is
  "input already queued for the old agent stays with it" (D2), and the task A claimed stays A's.

### D3 — A loop's listing entry carries its document and its agent

`LoopSummary` gains `spec_document_id` (`jobs.py` `_batch_loop_summaries`, `:273-489`; the model
at `schemas/jobs.py:99-190`). It goes on the summary, so `LoopDetail` inherits it
(`loops.py:86-87`, `**summary.model_dump()`). `LoopSummary.agent` already exists
(`schemas/jobs.py:111`). The tab starts showing it.

**One lookup, used twice (R2).** `api/loops.ts` gains `useDocumentFlow(documentId)`, which reads
`useLoops()` (default `include_archived=false`) and returns the loop whose `spec_document_id` equals
the id, or `undefined`. `SpecPhaseBar` uses it here. Change 2's `SpecApprovalReport` uses it too.

- **Archived loops.** `GET /loops` excludes them by default (`loops.py:125-126`), so "no unarchived
  flow" is the empty result. A test fixture that puts an archived loop in the default listing has
  a shape the route never returns (F190). Test the archived case at the route (1.7). In vitest it
  is an empty list.
- **Order.** The route orders by `Loop.created_at` ascending (`loops.py:127`). The partial unique
  index `ux_loops_spec_document_live` (`models.py:1570-1575`) allows at most one unarchived loop per
  document, so the lookup does not depend on order. The fixture still lists loops oldest first, as
  the route does, with a documentless loop ahead of the flow.
- **An ended, unarchived flow still counts.** `_check_spec_document_conflict` (`jobs.py:143-178`)
  treats it as the holder. So the bar shows **Flow: <label>** for it, not Start a flow, and its tab
  offers B10's Archive. Only after archiving does Start a flow appear.

### D4 — The document page links to its flow, or offers to start one

In `SpecPhaseBar.tsx`, for a **`change-spec` document at `approved`**:

- **A flow exists** → a **Flow: <label>** control that opens the loop's tab.
- **No unarchived flow** → **Start a flow…**, which opens `StartFlowDialog`.

Not on `exploring`/`proposed` (no tasks yet, and change 2 creates the flow at approval), not on
other kinds (a capability document is only ever `current`, `spec_lifecycle.py:198-205`; baselines,
maps and roadmaps are not decomposed into flows), not on `archived`.

**How the tab opens (R2; task 3.1 answered).** No second navigation is needed. The existing one is
the panel-tab store: `usePanelTabsStore.getState().openTab(projectId, loopTabId(loop.id))`
(`store/panelTabsStore.ts:62-64`, `:326-348`, which also sets `isOpen`). `ConversationRow.tsx:290`
and `LoopFiringGroup.tsx:94` already call it from outside `ConversationView`. `SpecPhaseBar` has
**two hosts**, though (`SpecDocumentPanel.tsx:235`):

| Host | Panel shell mounted? | What the link does |
|---|---|---|
| Conversation view's panel, a `spec:` tab (`ConversationView.tsx:384`) | yes | `openTab`; the loop tab appears beside the document |
| Spec destination (`SpecPage`, `App.tsx:428-446`) | no | `openTab`, then `navigateTo(agentDestination(projectId, loop.agent, null, null))` (`lib/navigation.ts:152`), so the panel is mounted with the loop tab open **and active**. **No document is passed (R3).** `ConversationView`'s destination-to-store effect (`:220-233`) opens the attached document's tab on mount, and that tab would then be the active one, in front of the loop. Back returns to the Spec page and its document |

So `SpecPhaseBar` takes an `onOpenLoop?: (loop: LoopSummary) => void`. `SpecDocumentPanel` threads it
the way it already threads `onOpenTasks` (`SpecDocumentPanel.tsx:42`, `:66`, `:240`). Each host
passes its row of the table. `SpecPage` gains the same prop, and `App.tsx` supplies it. With no
`onOpenLoop`, or a loop whose `agent` is `''` on the Spec destination, the label is shown as text
rather than as a link that does nothing.

### D5 — `StartFlowDialog` is a new component, not `JobForm`

`JobForm` sends `work_needs_evidence` whenever its loop section is open (`JobForm.tsx:98-108`).
The route accepts that beside a document (`jobs.py:622-633` refuses it only without an opt-in). Only
the MCP `create_flow` refuses it, client-side (`mcp_server.py:836-844`), because a flow's work is
always evidence-governed. `JobForm` is also being reworked by `a-dialog-takes-the-keyboard-when-it-opens`.
A flow needs five things, so it gets its own dialog. It takes `document: {id, title}` and an
`onClose`, and no host props, so change 2's report can open the same dialog:

| Field | Default |
|---|---|
| Name | the document's title, truncated to `JobCreate.name`'s 256 characters |
| Default agent | required select of **open** agents (`useAgents()`), no preselection when there is more than one |
| Message | `Work the next task of "<title>".` |
| Stop | **when the queue empties** (checked); optional stop-at time. At least one is required, and the dialog refuses to submit without one, as `create_flow` does (`mcp_server.py:821-827`) |
| Cadence | `*/5 * * * *`, the `create_flow` default (`:767`), with `lib/cron`'s previews and `cronDayAmbiguity` |

It posts `POST /jobs` with `spec_document_id` and at least one stop condition, so it always opts in
to a loop (`_loop_opts_in`, `jobs.py:106-108`). It sends `purpose: ""` as `create_flow` does. It
never sends `work_needs_evidence` or `session_mode: "resume"`. The TS `JobCreate` gains
`spec_document_id`. The first firing is on the next cron tick (the route hands the job to the
scheduler, `:804`, and runs nothing at once); the dialog says so. A 409 claim conflict shows the
route's own sentence (`jobs.py:173-177`; it names the holding loop by id). The dialog uses
`useDialogFocus` (`hooks/useDialogFocus.ts`, present today) with `data-dialog-initial-focus` on
the agent select. That mark is inert until the dialog-focus change lands, and that change's ADDED
requirement then covers this dialog too.

### D6 — Hooks and freshness

- `api/loops.ts` gains `useUpdateLoopSettings(jobId)` → `PATCH /jobs/{jobId}`, invalidating **both**
  `['project', pid, 'loops']` and `['project', pid, 'jobs']` **on settle**, the same shape as B10's
  three loop hooks. `useUpdateJob` invalidates only jobs (`jobs.ts:207-215`), so the tab would go
  stale.
- **`useCreateFlow()`** (R2) in `api/loops.ts` → `POST /jobs`, invalidating loops and jobs on
  settle. `useCreateJob` invalidates only jobs (`jobs.ts:198-205`). Without this the phase bar would
  keep offering Start a flow after one was made, and a second press answers 409.
- `useSSE.ts` (`:521-536`): `job_created`, `job_updated` and `job_deleted` also invalidate
  `['project', pid, 'loops']`, as `job_fired` already does. A second window then sees an edit or a
  new flow. `useSSE`'s loop-event branch (`:544-556`) already covers `loop_edit_staged` and
  `loop_edit_applied` for the loop keys. **`loop_edit_applied` also invalidates
  `['project', pid, 'jobs']` (R3)**, since applying a staged agent now writes `job.agent`. The
  prefix covers `useJob`'s `['project', pid, 'jobs', id]`. A busy-refused or skipped tick
  broadcasts no `job_fired`, so nothing else would refresh them.
- TS `JobUpdate.agent` stops being drift: it is now accepted.

### D7 — Migration `0108` (R2)

The next free revision at build time. It is `0108` if this change lands first; several open changes
add migrations, so `down_revision` is whatever the head is then (R3).
`0108_loop_pending_agent.py`, following `0080_loop_pending_edit.py`: a guard for a missing `loops`
table and for the column already existing, then `op.add_column("loops", sa.Column("pending_agent",
sa.String(64), nullable=True))`. Downgrade drops it the same way `0080` does. Bump
`HEAD_REVISION` in `hub/tests/test_migrations.py:40` and the assertion at
`hub/tests/test_project_persistence.py:227` (`.claude/rules/db-migrations.md` step 3). Nullable,
additive, no backfill. On `:8000`'s next restart it adds an empty column.

## Risks and order

- **After B10** (`a-loop-is-stopped-archived-and-delegated-from-its-own-tab`): same tab, same hooks
  file, same route. B10 moves `loop_edit_staged` inside the transaction (`commit=False`, B10 task
  2.1). This change adds a key to that event and builds on B10's version. B10's rule that a
  `stop_reason` on an ended loop refuses the whole PATCH does not reach this panel, which never
  sends `stop_reason`. B10's task 2.5 adds its hooks to the `@/api/loops` mock factories in
  `loopTab.test.tsx` and `loopPendingEdit.test.tsx`. This change adds `useUpdateLoopSettings`
  there, and mocks `@/api/jobs` (`useJob`) and `@/api/agents`, or `LoopTab` calls `undefined`.
- **`SpecPhaseBar.tsx` is edited by two other open changes** (R2):
  `a-document-moves-forward-only-through-its-checks` (B5, Approve's `onError`) and
  `a-documents-rigor-history-and-retired-requirements-are-on-screen` (the rigor history toggle). The
  regions differ, so whichever lands later rebases. All three add to `specPhaseBar.test.tsx`'s mocks,
  and this one adds `@/api/loops` there.
- **Before change 2** (`a-document-says-how-it-will-be-built-and-approval-starts-it`), which reuses
  `useDocumentFlow`, `StartFlowDialog` and D4's link.
- `a-loop-that-is-gone-lets-go-of-its-document` (B11) makes `POST /jobs` refuse a document without a
  loop opt-in (F157). The dialog always opts in, so it is unaffected in either order. Until B11
  lands, a flow started on a document whose previous flow was **archived** does not adopt that
  flow's unfinished tasks (`_adopt_document_tasks` takes only `loop_id IS NULL`, `jobs.py:239-270`),
  so its queue may start short. The dialog does not claim otherwise.
- **Skew on `:8000`:** the bundle reaches the live app on the next reload. Before `:8000` restarts, an
  agent edit answers 422 and changes nothing, `LoopSummary` has no `spec_document_id` (so the phase
  bar shows **Start a flow…** even for a document with a flow, and the POST answers 409 with the
  claim sentence), and the other fields work. The restart then runs migration `0108` on their data.
  Tell the operator before the bundle commit.
- **`_do_fire_job`'s `except` path** (`scheduler.py:3549-3572`) is fixed here after all (R3, D2a).
  R2 had it as a residual.
- **Residual, not fixed:** the firing-active window between a firing's commit and its `Run`
  starting (Round 3, "Residual").
