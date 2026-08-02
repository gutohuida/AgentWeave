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
5. **No backend change is expected.** If a task appears to need one, stop and reconcile with
   `design.md` before writing it — the premise of this change is that the server already does its
   part.

## 1. Navigation and shell

- [ ] 1.1 Write the navigation test spec: project entry with separately activatable name and
      expander, agent activation opening a conversation directly, overview roster activation, one
      header only, and back-to-project in a single action.
- [ ] 1.2 Build the rail data adapter returning a collection of projects, populated with the one
      authenticated project, and render the project-and-agents tree from it.
- [ ] 1.3 Apply each agent's identity colour beside its name in the rail, always alongside the name
      in text, matching the colour used in the timeline.
- [ ] 1.4 Add the agent-scoped conversation destination to the app's view model and render the
      conversation full-height with exactly one header.
- [ ] 1.5 Make the project overview's agent roster open a conversation directly, and add the
      back-to-project control to the conversation header.
- [ ] 1.6 Remove the Agents master-detail page with its filter tabs and grid view, and remove the
      Messages navigation destination. Leave both APIs, all records, and their tests untouched.
- [ ] 1.7 Verify the navigation, tree, back-to-project, destination-removal, and project-collection
      scenarios.
- [ ] 1.8 **`/handoff`**

## 2. Talking to a running agent

*The sharpest defect, and the reason this change is first. The backend already returns
`status: "queued"` with a `queue_entry_id` and broadcasts `queue_entry_queued`; only the interface
refuses.*

- [ ] 2.1 Write the queue-during-run test spec: composer enabled while running, submission calls the
      trigger endpoint, a queued outcome renders an undelivered timeline entry without a refresh, a
      second submission queues in order behind the first, and a failed submission restores the typed
      text.
- [ ] 2.2 Remove the running state from the composer's disabled condition, leaving only an in-flight
      submission able to disable submission.
- [ ] 2.3 Implement the submission algorithm from `design.md`: never branch on running state, render
      queued input from the server's recorded entry rather than synthesizing one locally, and restore
      the operator's text on failure.
- [ ] 2.4 Verify the running-composer scenarios.
- [ ] 2.5 **`/handoff`**

## 3. Composer

- [ ] 3.1 Write the composer test spec: resting and maximum heights, growth then scroll, per-agent
      draft retention across navigation and reload, clearing on successful submission, and graceful
      degradation when storage is unavailable.
- [ ] 3.2 Extract the composer into its own component with bounded autosizing — at least 3 rows at
      rest, at least 12 before scrolling.
- [ ] 3.3 Implement the per-agent draft store from `design.md`, degrading to no-persistence when
      storage is unavailable.
- [ ] 3.4 Write the control-placement test spec: the resting control set idle and running, absence of
      the removed controls, full keyboard operation of the overflow menu including focus return on
      dismissal, and unavailable actions shown disabled with a reason.
- [ ] 3.5 Build the composer control row and the keyboard-operable overflow menu with the fixed
      ordering and disabled-with-reason behaviour from `design.md`.
- [ ] 3.6 Move session selection into the overflow menu and keep the continuity state visible as
      text, preserving the new-session binding and the handoff state machine unchanged.
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
