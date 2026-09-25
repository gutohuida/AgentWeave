# Proposal — a flow is configured from its own tab

**Round 1, 2026-09-25**, from an interactive explore with the operator on request **R1** (F377).
**Round 2, same day**: re-derived against the code. See design.md "Round 2" for what changed.
First of two changes; the second is `a-document-says-how-it-will-be-built-and-approval-starts-it`,
which builds on this one. **Nothing here is implemented yet.**

## Why

Once a flow exists, nothing about it can be changed from the app, and one thing about it cannot be
changed at all:

- `PATCH /jobs/{job_id}` (`hub/hub/api/v1/jobs.py:906`) accepts name, message, cron, purpose and the
  stop condition, but its only UI hook, `useUpdateJob` (`hub/ui/src/api/jobs.ts:207`), has **no
  component caller**. `LoopTab.tsx` only displays a loop, and it does not even show the loop's agent.
- `JobUpdate` (`hub/hub/schemas/jobs.py:56-72`) has **no `agent` field** and forbids extras, so a
  flow's default agent is fixed at creation: `{"agent": "dev2"}` answers 422. The TypeScript
  `JobUpdate` still declares `agent?` (`jobs.ts:146-160`), which is drift.
- Nothing creates a flow from the app either. `JobForm.tsx` has no document field, and the TS
  `JobCreate` has no `spec_document_id`. The operator's only route is to ask an agent to call
  `create_flow`, which is how F376 lost a night.
- A document cannot find its own flow: `SpecDocumentRecord` carries no loop, and `LoopSummary` does
  not carry the document it declares.

The operator's direction (explore, 2026-09-25): build the edit panel **first**. Change 2 then makes
approval create the flow, and this panel is where anything about it is corrected afterwards.

## What Changes

- **A Settings section on the loop's own tab.** It shows and edits name, default agent, message,
  cadence (cron), purpose and stop condition, through `PATCH /jobs/{job_id}`. The document a flow
  declares and `work_needs_evidence` are shown but not editable: the first is the flow's identity,
  and the second is declared at creation (`agent-loops` "A loop declares at creation whether its
  work needs evidence").
- **The default agent becomes editable, by the operator only.** `JobUpdate` gains `agent`, checked
  by the existing `_check_agent_exists` before anything is mutated. An agent's run is refused
  (403), because `JobUpdate` is also the agent-plane body and a run could otherwise re-point a loop
  at itself (design D2). On a loop the change is **staged** like purpose and stop condition (new
  `Loop.pending_agent`, migration `0108`) and applied at the next firing. On a plain job it applies
  at once and clears `last_session_id`, since the resumed session belonged to the old agent.
- **A staged edit is applied before the busy guard when no firing of the loop is running** (design
  D2a, R2). Today staging runs after the guard, which asks about the old agent. A switch away from
  an agent whose allowance is spent would therefore wait for that agent's reset.
- **A loop's listing entry names the document it declares.** `LoopSummary` gains
  `spec_document_id`. One hook, `useDocumentFlow`, finds a document's flow for this change and
  change 2.
- **The document page links to its flow, or offers to start one.** On an approved change document,
  the phase bar shows **Flow: <label>** (opens the loop tab) when an unarchived loop declares it.
  Otherwise it shows **Start a flow…**, a small dialog (name, default agent, message, stop condition,
  cadence) that posts a flow through `POST /jobs`. This is R1's original button, kept as the fallback
  for documents change 2 does not cover.
- The link opens the loop's tab through the panel-tab store the sidebar already uses. On the Spec
  destination, where no panel is mounted, it also opens the loop agent's view (design D4).
- Starting a flow, and `job_created`/`job_updated`/`job_deleted`, refresh the loop caches, so the
  document names its new flow at once and another open window sees an edit.

## Capabilities

### Modified Capabilities

- `agent-loops`: "An edit to a loop takes effect at its next firing and never during one" names the
  default agent among the staged fields. "A project's loops are listable and individually
  inspectable" has each entry carry its declared document and its agent. ADDS "The operator edits
  a loop's settings from the loop's own view", "A plain job's change of agent does not resume the
  old agent's session" and "Only the operator changes which agent a job names".
- `agent-flows`: ADDS "An approved document offers the operator its flow, or a way to start one".

## Impact

- **Backend:** `schemas/jobs.py` (`JobUpdate.agent`), `api/v1/jobs.py` (PATCH agent handling,
  `LoopSummary.spec_document_id`, `_pending_loop_edit`, a shared "firing active" helper),
  `schemas/jobs.py` (`LoopSummary.spec_document_id`), `scheduler.py` (`_stage_pending_loop_edit(loop,
  job)` applies `pending_agent`; D2a's early application), `db/models.py` plus migration `0108`
  (`loops.pending_agent`, nullable), and the head assertions in `test_migrations.py` and
  `test_project_persistence.py`.
- **UI:** `api/jobs.ts`, `api/loops.ts`, `LoopTab.tsx`, a new `StartFlowDialog.tsx`,
  `SpecPhaseBar.tsx`, `SpecDocumentPanel.tsx`, `SpecPage.tsx`, `ConversationView.tsx` and `App.tsx`
  (the `onOpenLoop` prop), `useSSE.ts`, the mocks in `loopTab.test.tsx`, `loopPendingEdit.test.tsx`
  and `specPhaseBar.test.tsx`, and a bundle refresh.
- **Order:** after B10's `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` (same tab, same
  hooks file, same PATCH route). Before change 2. `SpecPhaseBar.tsx` is also edited by
  `a-document-moves-forward-only-through-its-checks` and
  `a-documents-rigor-history-and-retired-requirements-are-on-screen`, in other regions.
- **`:8000`:** the bundle reaches the operator's live app on their next reload. Until `:8000`
  restarts, an agent edit from that page answers 422 and changes nothing (the old route), a
  document with a flow still offers **Start a flow…** (which then answers 409), and every other field
  works. The restart runs migration `0108` on their data.
