# Implementation plan

## Working protocol — read before starting any phase

1. **Re-read the spec before beginning a phase.** Read `proposal.md`, `design.md`, and
   `specs/agent-conversation-workspace/spec.md`. The reasoning behind each decision lives in
   `design.md` and is deliberately not repeated in the task lines below.
2. **Tests first within each phase.** Every phase opens with the test task for the behaviour it
   adds. Two of the defects this change fixes survived phases 6–8 of the umbrella precisely because
   no test asserted them.
3. **Verify against scenarios, not intent.** Each phase ends with a verification task naming the
   requirement whose scenarios must pass.
4. **Run `/handoff` at every threshold** — after each numbered phase, and after any substantial chunk
   within a long one. A phase is not done until its handoff is written.
5. **Phase 0 is the implementation gate for every UI phase.** The approved stable-conversation
   contract MUST be green before the running-state lock or provider-session picker is removed.

## 0. Stable conversation identity

- [ ] 0.1 Write backend contract and migration tests for `Conversation(id, project_id, agent,
      provider_session_id, lifecycle, created_at, updated_at, archived_at)`; deterministic legacy
      backfill; synchronous allocation; immutable scope; idempotent provider binding; binding
      conflict; retry/stop retention; and reset-only deletion.
- [x] 0.2 Add the `conversations` migration and `conversation_id` associations on `Run`,
      `InboundQueueEntry`, `AgentOutput`, and `Message`, retaining legacy `session_id` only as a
      provider-continuation snapshot during migration.
- [x] 0.3 Replace the operator trigger contract with optional `conversation_id`; return
      `conversation_id` and `queue_entry_id` for both `running` and `queued`; create a new
      conversation plus its first entry atomically when the field is omitted.
- [x] 0.4 Bind the first provider session ID transactionally without changing `conversation_id`;
      reject conflicting binding; stamp every output with `run_id` and `conversation_id`.
- [x] 0.5 Make scheduling choose the oldest eligible entry's conversation and drain only that
      conversation up to the existing cap; derive provider new/resume from
      `Conversation.provider_session_id`; preserve hop-budget, withdraw, deliver-now, stop, and
      return-on-failure behavior.
- [x] 0.6 Add `GET /agent/{agent}/conversations` and route
      `GET /agent/{agent}/chat/{conversation_id}` entirely by recorded conversation association.
      Keep the unscoped recent-history route only as a migration overview.
- [x] 0.7 Update peer-message, agent-request, scheduled-job, output, SSE, and diagnostics producers
      so every new run/queue/output row receives a conversation association and normal UI payloads
      do not treat provider session IDs as conversation identity.
- [x] 0.8 Write frontend API/state tests proving a returned `conversation_id` is retained before
      output, immediate follow-up uses it, conversation selection/history never uses provider IDs,
      and a new handoff successor binds from the trigger response.
- [x] 0.9 Verify every stable-conversation and modified handoff scenario before beginning phase 1.
- [x] 0.10 **`/handoff`**

## 1. Navigation and shell

- [x] 1.1 Write the navigation test spec: project entry with separately activatable name and
      expander, agent activation opening a conversation directly, overview roster activation, one
      header only, and back-to-project in a single action.
- [x] 1.2 Build the rail data adapter returning a collection of projects, populated with the one
      authenticated project, and render the project-and-agents tree from it.
- [x] 1.3 Apply each agent's identity colour beside its name in the rail, always alongside the name
      in text, matching the colour used in the timeline.
- [x] 1.4 Add the agent-scoped conversation destination to the app's view model and render the
      selected `conversation_id` full-height with exactly one header; a not-yet-created state is
      keyed by project and agent, never by a provider session.
- [x] 1.5 Make the project overview's agent roster open a conversation directly, and add the
      back-to-project control to the conversation header.
- [x] 1.6 Remove the Agents master-detail page with its filter tabs and grid view, and remove the
      Messages navigation destination. Leave both APIs, all records, and their tests untouched.
- [x] 1.7 Verify the navigation, tree, back-to-project, destination-removal, and project-collection
      scenarios.
- [x] 1.8 **`/handoff`**

## 2. Talking to a running agent

*The sharpest defect, and the reason this change is first. The backend already returns
`status: "queued"` with a `queue_entry_id` and broadcasts `queue_entry_queued`; only the interface
refuses.*

- [x] 2.1 Write the queue-during-run test spec: composer enabled while running, submission calls the
      trigger endpoint, a queued outcome renders an undelivered timeline entry without a refresh, a
      second submission queues in order behind the first, and a failed submission restores the typed
      text.
- [x] 2.2 Remove the running state from the composer's disabled condition, leaving only an in-flight
      submission able to disable submission.
- [x] 2.3 Implement the submission algorithm from `design.md`: never branch on running state, render
      queued input from the server's recorded entry rather than synthesizing one locally, and restore
      the operator's text on failure.
- [x] 2.4 Verify the running-composer scenarios.
- [x] 2.5 **`/handoff`**

## 3. Composer

- [x] 3.1 Write the composer test spec: resting and maximum heights, growth then scroll,
      project-and-conversation-scoped draft retention across navigation and reload, isolation
      between two conversations of one agent, clearing without a delayed-write race, and graceful
      degradation when storage is unavailable.
- [x] 3.2 Extract the composer into its own component with bounded autosizing — at least 3 rows at
      rest, at least 12 before scrolling.
- [x] 3.3 Implement the project-and-conversation draft store from `design.md`, degrading to no-persistence when
      storage is unavailable.
- [ ] 3.4 Write the control-placement test spec: the resting control set idle and running, absence of
      the removed controls, full keyboard operation of the overflow menu including focus return on
      dismissal, and unavailable actions shown disabled with a reason.
- [ ] 3.5 Build the composer control row and the keyboard-operable overflow menu with the fixed
      ordering and disabled-with-reason behaviour from `design.md`; agent details opens without
      navigating away or unmounting the conversation.
- [ ] 3.6 Replace provider-session selection with AgentWeave conversation selection in the overflow
      menu; keep continuity visible as human-readable text and provider IDs confined to details or
      diagnostics; preserve the successor-conversation handoff state machine.
- [ ] 3.7 Remove the pause/resume-scroll control and drive autoscroll from scroll position.
- [ ] 3.8 Place the existing `ContextUsageIndicator` in the composer control row, rendering nothing
      when no usage event has been received. *The indicator, its compact variant, and
      `record_context_usage` already exist — umbrella tasks 11.6–11.7 were built but never checked
      off. Only placement remains.*
- [ ] 3.9 Build the banner stack above the composer for run failure, stream loss, and blocked-queue
      conditions, with stable ordering across simultaneous conditions.
- [ ] 3.10 Verify the composer, draft, control-placement, session-identity, autoscroll, banner, and
      context-usage scenarios.
- [ ] 3.11 **`/handoff`**

## 4. Regression and closeout

- [ ] 4.1 Re-point the existing `agentChat`, `agentTimeline`, `agentTimelineEvents`, `agentHandoff`,
      `agentStatus`, and `App-mount` suites at the new surface, changing only how it is mounted and
      queried.
- [ ] 4.2 Confirm every continuity, handoff, stop, withdraw, and deliver-now assertion still passes,
      and that queue semantics are untouched.
- [ ] 4.3 Annotate the superseded phases of `openspec/changes/2026-07-30-hub-native-experience/`
      naming this change, per the reconciliation rule in `design.md`. Do not mark any umbrella task
      complete — only real implementation closes a task, and it closes it here.
- [ ] 4.4 Sync `specs/agent-conversation-workspace/` into `openspec/specs/` and archive this change.
- [ ] 4.5 **`/handoff`**
