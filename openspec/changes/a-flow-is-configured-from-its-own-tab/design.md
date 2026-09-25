# Design — a flow is configured from its own tab

**Round 1, 2026-09-25.** Decisions made with the operator in an interactive explore are marked
**(operator)**; the rest are this round's and are open to R2/R3.

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

`JobUpdate` gains `agent: Optional[str]`, checked by `_check_agent_exists` (`jobs.py:181-236`;
unknown and archived names refused 400), as agent-loops "A job SHALL name an agent that exists"
already requires for an update.

**On a loop, an agent edit is staged, not applied at once.** `job.agent` is read outside the firing
itself: by the busy guard (`_loop_flow_busy_refusal`, `scheduler.py:355+`, called at `:3077`), by
the held-queue coalescing (`InboundQueueEntry.agent == job.agent`, `:1050-1072`), and as the flow's
default agent in `decide_firing` (`:3267`). Changing it while a firing runs would make the busy
guard ask about an agent that is not the one running, and a Run press could start a second firing
beside the first. agent-loops "An edit to a loop takes effect at its next firing and never during
one" already says this for purpose and stop, and the agent joins them:

- New nullable column `loops.pending_agent` (migration; `recreate="never"`, add-column only).
- `_stage_pending_loop_edit` applies it to `job.agent` with the other pending fields, and
  `loop_edit_applied` carries it.
- `loop_edit_staged`'s `changes` and `LoopSummary.pending_edit` include `agent`.

**On a plain job (no loop), an agent edit applies at once and clears `last_session_id`.** A
resume-mode job would otherwise resume the old agent's session as the new agent
(`scheduler.py:3056`), which the product refuses elsewhere (`:3689`).

**What the edit does not move** (stated in the panel's help text and in the spec):

- Tasks already assigned keep their assignee (agent-loops: staffing "never takes work away").
- Input already queued for the old agent stays with it.
- The flow's checkpoint lineage is keyed by the loop (`Checkpoint.loop_id`), so it survives.
- **`control="creator"` follows the new agent.** The creator *is* `job.agent` (`api/v1/tasks.py:611,
  678-704`); there is no separate column. Adding one to preserve the original creator is not this
  change. The panel says so when control is `creator`.

### D3 — A loop's listing entry carries its document and its agent

`LoopSummary` gains `spec_document_id` (`jobs.py` `_batch_loop_summaries`, `:293-300, 472`). The
document page finds its flow by filtering the loops it already fetches with `useLoops()`: the
unarchived loop whose `spec_document_id` equals the document's id. No new route and no document
field. (`LoopSummary.agent` already exists; the tab starts showing it.)

### D4 — The document page links to its flow, or offers to start one

In `SpecPhaseBar.tsx`, for a **change-spec document at `approved`**:

- **A flow exists** → a **Flow: <label>** control that opens the loop's tab. The spec page and the
  conversation view are different panes; how the phase bar opens `loop:<id>` (the same route
  `LoopsIndexTab` uses via `ConversationView.tsx:360-373`) is task 3.1's first step, and the task
  must follow whatever navigation already exists rather than adding a second one.
- **No unarchived flow** → **Start a flow…**, which opens `StartFlowDialog`.

Not on `exploring`/`proposed` (no tasks yet, and change 2 creates the flow at approval), not on
capability documents, not on `archived`.

### D5 — `StartFlowDialog` is a new component, not `JobForm`

`JobForm` sends `work_needs_evidence` whenever its loop section is open (`JobForm.tsx:281-362`),
which a flow refuses (the MCP `create_flow` refusal), and it is being reworked by
`a-dialog-takes-the-keyboard-when-it-opens`. A flow needs five things, so it gets its own dialog:

| Field | Default |
|---|---|
| Name | the document's title |
| Default agent | required select of **open** agents (`useAgents()`), no preselection when there is more than one |
| Message | `Work the next task of "<title>".` |
| Stop | **when the queue empties** (checked); optional stop-at time |
| Cadence | `*/5 * * * *`, the `create_flow` default, with previews |

It posts `POST /jobs` with `spec_document_id` and one stop condition, so it always opts in to a
loop. It never sends `work_needs_evidence`. The TS `JobCreate` gains `spec_document_id`. The first
firing is on the next cron tick (the route registers a `CronTrigger` and runs nothing at once);
the dialog says so. A 409 claim conflict shows the route's own sentence. If `useDialogFocus` has
landed, the dialog uses it; if not, the dialog-focus change adds it to its list.

### D6 — Hooks and freshness

- `api/loops.ts` gains `useUpdateLoopSettings(jobId)` → `PATCH /jobs/{jobId}`, invalidating **both**
  `['project', pid, 'loops']` and `['project', pid, 'jobs']`. This is the same reason B10 gave its
  loop hooks: `useUpdateJob` invalidates only jobs, so the tab would go stale.
- `useSSE.ts`: `job_updated` also invalidates the loop keys, so a second window sees the edit.
- TS `JobUpdate.agent` stops being drift: it is now accepted.

## Risks and order

- **After B10** (`a-loop-is-stopped-archived-and-delegated-from-its-own-tab`): same tab, same hooks
  file, same route. B10 moves `loop_edit_staged` inside the transaction; this change adds a field
  to that event and must build on B10's version. B10's rule that a `stop_reason` on an ended loop
  refuses the whole PATCH does not reach this panel, which never sends `stop_reason`.
- **Before change 2** (`a-document-says-how-it-will-be-built-and-approval-starts-it`), which reuses
  D3's lookup and D4's link.
- `a-loop-that-is-gone-lets-go-of-its-document` (B11) makes `POST /jobs` refuse a document without a
  loop opt-in (F157). The dialog always opts in, so it is unaffected in either order.
- **Skew on `:8000`:** the bundle reaches the live app on the next reload. Before `:8000` restarts, an
  agent edit answers 422 and changes nothing, `LoopSummary` has no `spec_document_id` (so the phase
  bar shows **Start a flow…** even for a document with a flow, and the POST answers 409 with the
  claim sentence), and the other fields work. Tell the operator before the bundle commit.
