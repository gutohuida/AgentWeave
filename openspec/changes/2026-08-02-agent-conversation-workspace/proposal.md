## Why

The `2026-07-30-hub-native-experience` change has completed phases 1–8 and become an umbrella: 69
unchecked items spanning eight phases and at least five unrelated outcomes. That is more than one
review can honestly cover, and it postpones the surface the operator touches on every interaction.
This change extracts the conversation work into a slice that can be approved, implemented, and
verified on its own. `design.md` records how the remaining phases are re-cut; this proposal covers
only the conversation.

Three findings from a read of the ten delta specs against the shipped code drive it:

1. **The interface contradicts two approved delta specs.** `agent-inbound-queue` requires entries
   arriving during a running turn to be queued and delivered at the start of the next turn.
   `agent-conversation-timeline` requires operator input submitted while an agent is running to
   appear immediately in an undelivered state, and states the operator "may continue submitting
   further input." The backend honours both: `POST /api/v1/agent/trigger` returns
   `status: "queued"` with a `queue_entry_id`, persists a `queue_entry_queued` event, broadcasts it
   over SSE, and `agent_chat.py` appends still-queued entries to the timeline as undelivered.

   The UI throws it away. `AgentOutputPanel.tsx` defines
   `interactionLocked = isRunning || isSending || handoffState === 'preparing' || isBindingNewSession`
   and uses it to disable both the textarea and the send button. During precisely the window the
   durable queue exists to serve, the operator is locked out. A queue whose only human producer
   cannot reach it is dead weight. `agent-composer` likewise requires a draft to survive
   navigation; the composer holds its value in component state, so navigating away discards it.
   No test asserts either behaviour, which is how both survived phases 6–8.

2. **The conversation is buried.** Reaching it costs four steps: open *Agents*, pick a filter tab,
   select an agent from a 240 px master list, then find the Output tab inside the detail panel. It
   renders two agent headers — one from the page, one from the panel — and the timeline gets
   whatever vertical space is left. Meanwhile *Messages* is a separate top-level destination even
   though peer traffic in both directions is already merged into the conversation timeline, so the
   operator is offered two places to read the same records.

3. **The composer is a single-row input surrounded by controls that do not earn their place.** It
   is `rows={1}` with a 96 px ceiling — roughly four lines — beside a raw session `<select>` listing
   truncated UUIDs, a handoff button, and a "Pause scroll" toggle that duplicates what the scroll
   position already says.

All three are client-side. This change requires no new endpoint, no schema change, and no new
dependency.

## What Changes

**Navigation**

- Navigation SHALL list the current project and its agents as a tree, replacing the flat
  eleven-entry page list. Activating the project name navigates to its overview; activating its
  expander toggles the agent list without navigating.
- Selecting an agent — from the rail or from the project overview's roster — SHALL open that
  agent's conversation as the whole content area, with no intermediate list, filter tab bar, or
  detail-panel selection step.
- The containing project SHALL be reachable from a conversation in one action.
- *Agents* and *Messages* SHALL be removed as navigation destinations. Their records, APIs, and
  storage are untouched — they remain source data for routing, attribution, and history.
- Navigation SHALL read from an adapter shaped as a collection of projects, populated with exactly
  the one authenticated project. No control may imply a second project is reachable.

**Talking to a running agent**

- The composer SHALL accept and submit input while the agent is running; the submitted input
  appears in the timeline in the undelivered state without a manual refresh.
- The composer's input and submit control MUST NOT be disabled on account of the agent's running
  state. They may be disabled only while a submission of their own is in flight.

**Composer**

- The composer SHALL present at least 3 rows at rest, grow to at least 12, then scroll.
- Unsent text SHALL be retained per agent conversation across navigation and reload, cleared on
  successful submission, and never visible in another agent's conversation.
- Only submit, stop (while running), the active-agent indicator, and context usage remain visible.
  New conversation, session selection, handoff, fold-all, and agent details move into one
  keyboard-operable overflow menu.
- The session `<select>` leaves the resting surface; continuity remains visible as text.
- The manual pause/resume-scroll control is removed; autoscroll follows the operator's scroll
  position.
- A banner stack above the composer carries run failure, stream loss, and blocked-queue conditions.
- The existing context-usage indicator is placed in the composer, rendering nothing rather than a
  zero when no usage event has been received.

**Preserved**

- Session continuity, durable handoff, stop, withdraw, and deliver-now behave exactly as they do
  today. Queue semantics — hop budget, per-turn cap, delivery ordering — are unchanged.

## Non-Goals

- **Real multi-project switching or project creation.** `_project_from_api_key` resolves one bearer
  key to one `project_id` and the SSE ticket is signed `{project_id}:{expires}`, so a switcher is
  not a frontend task. See `design.md` § open research.
- **Composer trigger menus** for `@path`, `/command`, `$skill`. Their workspace-path result source
  needs a path-listing endpoint that does not exist; including them would turn a client-side change
  into a client-and-server one.
- **Changing which agent handles a conversation from inside the composer.** The composer shows
  which agent is active; it does not offer an in-place switcher. Once every agent is one click away
  in the rail, a switcher's remaining value is reassigning an in-flight conversation, which is a
  change to turn routing rather than to layout.
- **Changing what a turn receives.** No queue semantics change.
- **Runner records, model reassignment, charters, or templates.**
- **Specification traceability, authoring, and approval gates.**
- **Token accounting and budgets.**
- **Deleting message storage, the messages API, or the agents API.** Only the destinations go.
- **A permission-mode control.** No permission behaviour exists to control yet.
- **A project-level agent directory.** Once agents are reachable from the rail and the overview
  roster, a bulk list has no remaining job. It may return if a real bulk-management workflow
  appears.

## Impact

- Affected specs: `agent-conversation-workspace` (new). Brings the interface into conformance with
  the existing `agent-inbound-queue`, `agent-conversation-timeline`, and `agent-composer` deltas
  without restating or amending them.
- Affected code: `hub/ui/src/App.tsx`, `hub/ui/src/components/layout/Sidebar.tsx`,
  `hub/ui/src/components/agents/AgentOutputPanel.tsx`,
  `hub/ui/src/components/agents/AgentsPage.tsx`,
  `hub/ui/src/components/agents/AgentDetailPanel.tsx`,
  `hub/ui/src/components/overview/OverviewPage.tsx`.
- Removed from the interface: the Agents master-detail page with its filter tabs and grid view, the
  Messages navigation destination, the session `<select>`, and the pause-scroll toggle.
- No backend change. No new endpoint, permission, schema, or runtime dependency.
- Supersedes umbrella phases 11 and 12 in full and 10.3–10.7 in part; see `design.md`.
