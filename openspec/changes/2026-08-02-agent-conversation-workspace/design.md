# Design

## Re-cutting the remaining umbrella

The `2026-07-30-hub-native-experience` change carries 69 unchecked items across phases 9–16. They
are not one capability. This section records how they are re-cut into independently approvable
changes, so that no two ledgers are live at once and so that this change's boundary is explicit.

| Slice | Intent | Deferred out of it | Depends on | State |
|---|---|---|---|---|
| **Agent conversation workspace** (this change) | Make the conversation the primary surface and let the operator talk to a running agent | Trigger menus, project switching, charters, spec authoring, approvals | Phases 1–8 | proposed |
| **Composer intelligence** | `@path` / `/command` / `$skill` triggers, keyboard menu, in-place agent selector | Anything changing what a turn receives | this change | ready to propose |
| **Multi-project operator access** | One operator, several projects | Multi-user accounts, roles, sharing | this change, **RQ-1** | blocked on research |
| **Accounting and budgets** | Per-turn token usage, aggregation, project budget pausing autonomous turns | Billing, invoicing | — (independent) | ready to propose |
| **Runner / agent / charter separation** | Reusable execution capability vs. addressable identity vs. behaviour | Charter authoring UI | — (independent) | ready to propose |
| **Specification program** | Requirement identity, traceability, evidence, drift, rigor, authoring | everything, until **RQ-2** is answered | **RQ-2** | blocked on research |
| **Approval gates** | Pending task-lifecycle and spec-gate decisions inline in the conversation | New approval semantics | this change, spec program | blocked |
| **Single runtime** | Make the locally-installed app the only way to run AgentWeave: delete the watchdog, local/git transports, and the CLI-only collaboration modes | The rename below | — (independent) | needs its own proposal |
| **Retire the "Hub" name** | It is just AgentWeave | — | single runtime | deferred until the architecture settles |

Accounting and runner/charter separation carry no dependency on this change and may be proposed in
parallel. This change is placed first because it is the surface the operator touches on every
interaction, and because continuing to build against the interaction model it removes would waste
that work.

**Direction decided 2026-08-02:** AgentWeave becomes a locally-installed app that is the *only* way
to use it. There is no no-Hub product. This **reverses** the `2026-07-30-hub-native-experience`
proposal's non-goal "Not changing the CLI's local/git transports" — those transports, the watchdog,
and the Zero-relay MCP and manual-relay modes are all to be removed rather than preserved.

One consequence for triage: in HTTP mode the CLI watchdog still spawns an agent on peer-message
arrival (`_make_ping_callback`) while `hub/hub/api/v1/messages.py` independently calls
`schedule_agent()` — two execution paths for one message. That defect is real but is **not worth a
targeted fix**, because it disappears with the watchdog. This change is unaffected either way: its
surface is Hub-only already, and the decision makes it more central rather than less.

**Reconciliation rule.** Umbrella phases superseded by a slice are annotated in the umbrella's
`tasks.md` naming the successor change. A superseded task is never marked complete on the strength
of a successor existing — only real implementation closes a task, and it closes it in the successor.
The ten delta specs under the umbrella's `specs/` remain authoritative for behaviour implemented in
phases 1–8; a successor references them rather than restating them. The umbrella is archived when
every slice is done.

## Open research questions

Two slices cannot be specified from existing material. Each needs a decision, not an implementation.

### RQ-1 — Operator identity versus project-scoped authentication

Authentication binds one bearer API key to exactly one project. `_project_from_api_key` in
`hub/hub/auth.py` resolves a key row to a single `project_id`, and the SSE ticket is signed as
`{project_id}:{expires}`. Every request and every event stream is scoped to one project for the
lifetime of the credential, and the local setup endpoint returns the first non-revoked project key.

A project switcher is therefore not a sidebar feature. It requires deciding what an operator *is*
when they are not a project, how a session selects a project, whether one credential may span
projects or the client holds several, and how the SSE stream is torn down and re-established on a
switch without dropping events. Until that is decided, any multi-project affordance would be a claim
the backend cannot honour — which is why this change ships a rail adapter shaped for many projects
but populated with one, and forbids any control implying otherwise.

### RQ-2 — Specification file authority

The specification program introduces stable requirement identifiers, evidence records, proposals,
and live verification state, all of which need one unambiguous home. AgentWeave ships two
specification systems as product features: this repository's own workflow under `openspec/`, and the
`aw-spec-workflow` capability (`openspec/specs/aw-spec-workflow/spec.md`) that generates portable
HTML for *user* projects and indexes it in a manifest.

Deciding which is authoritative for AgentWeave's own requirement identity — and how identifiers,
evidence, and links survive an external edit — must precede building the authoring surface.
Implementing in-position accept/reject/discuss before settling it would force a second migration
once identifiers need to outlive a rewrite.

## Approach for this change

The conversation stops being a tab inside `AgentsPage → AgentDetailPanel` and becomes a destination.
`App.tsx`'s flat `Page` union gains an agent-scoped destination, so the active view is either a
project-level view or one agent's conversation. `AgentOutputPanel` is split: the timeline host stays,
and the composer becomes its own component owning drafts, controls, and the banner stack.

```
Rail (adapter: Project[] — one entry today)
  └─ Project ▾ ──────────────► ProjectOverview
       ├─ agent A ───────────► AgentConversation(agent)
       ├─ agent B                   │
       └─ agent C                   ├── one header ── back-to-project
                                    ├── AgentTimeline  (unchanged)
                                    ├── BannerStack    (new)
                                    └── Composer       (new)
                                          ├── textarea + draft store
                                          ├── submit / stop
                                          ├── active agent · context usage
                                          └── overflow ▸ new · session · handoff
                                                          · fold all · details

POST /api/v1/agent/trigger ──► { status: "started" | "queued", queue_entry_id? }
SSE  queue_entry_queued / queue_entry_delivered / agent_output   (all existing)
```

## Algorithms

### Submitting composer input

This replaces a path whose first step is effectively "if the agent is running, do nothing."

1. If the composer text is empty or whitespace only, stop.
2. If a submission for this conversation is already in flight, stop.
3. Mark a submission in flight and clear the composer text optimistically.
4. Call the trigger endpoint with the agent, the text, and the current session selection. Do not
   branch on the agent's running state — the endpoint decides.
5. If the endpoint reports the turn started, clear the stored draft and let the existing output
   stream render the turn.
6. If the endpoint reports the input was queued, clear the stored draft and rely on the
   `queue_entry_queued` event and the chat endpoint's undelivered entries to render it. Do **not**
   synthesize a local entry: the timeline is built from stored records, and must not gain an entry
   the server did not record.
7. If the call fails, restore the text into the composer, restore the stored draft, and raise a
   run-failure banner.
8. Clear the in-flight mark.

### Draft persistence

1. Drafts are keyed by agent name under one namespaced storage key.
2. On mounting a conversation, read that agent's draft and seed the composer; an absent draft seeds
   an empty composer.
3. On every change to the composer text, write that agent's draft, debounced.
4. On successful submission, delete that agent's draft.
5. If storage is unavailable the composer still functions; only persistence is lost. This mirrors
   how the rail width is persisted and must never break the surface.

### Autoscroll

1. Maintain one derived flag: the operator is at the bottom if the scroll position is within a small
   threshold of the maximum.
2. When new content arrives and the flag is set, scroll to the newest entry.
3. When new content arrives and the flag is clear, do not move the viewport.
4. Recompute the flag on every scroll event. No manual override exists, because the scroll position
   already expresses the intent the removed control duplicated.

### Control placement

1. Render submit, the active-agent indicator, and context usage in the composer control row.
2. If the agent is running, additionally render stop.
3. Render every remaining conversation action inside the overflow menu in a fixed order: new
   conversation, session selection, handoff, fold all, agent details.
4. If an action is unavailable — handoff on a manual runner, for example — present it disabled with
   its reason rather than omitting it, so the menu's contents do not shift between agents.

## Key decisions

- **The composer never inspects `isRunning` to decide whether to accept input.** The endpoint
  already reports which of the two outcomes occurred, and the queue is durable. Any client-side
  prediction of agent state is a second source of truth that can only be wrong.
- **Queued input is rendered from server records, not optimistically.**
  `agent-conversation-timeline` requires entries to be placed by recorded association. A locally
  synthesized entry would violate that and would double-render when the real record arrives.
- **Drafts live in browser storage keyed by agent, not on the server.** A draft is unsent operator
  text with no coordination value; persisting it server-side would create a record other agents
  could observe. Storage failure degrades to no-persistence rather than breaking the composer.
- **The rail consumes a project collection from day one.** Shaping the adapter now costs nothing and
  means the multi-project slice changes what fills the collection rather than rewriting the rail.
  Shaping it as a single project would guarantee a rewrite.
- **Messages disappear as a destination, not as a model.** Peer traffic is already merged into the
  timeline, so the destination is redundant; the records remain source data for routing,
  attribution, and history.
- **Unavailable overflow actions are shown disabled with a reason.** A menu whose contents change
  between agents forces the operator to re-learn it each time.

## Security considerations

- No new endpoint, permission, or authentication change. The change consumes the same project-scoped
  bearer credential and the same signed SSE ticket as today.
- Drafts are unsent operator text in browser storage on the operator's own machine. They are not
  transmitted and not shared between agents. Draft keys are namespaced and keyed by agent name,
  already constrained by `^[a-zA-Z0-9_-]{1,32}$`, so a key cannot be forged into another namespace.
- Removing navigation destinations does not remove authorization checks; the underlying endpoints
  keep their existing dependencies.
- No new runtime dependency.

## Evidence and coverage limits

Inspected while writing this change:

| Source | What it establishes |
|---|---|
| `hub/ui/src/components/agents/AgentOutputPanel.tsx` | The running-turn lock, the single-row composer with a 96 px ceiling, in-component draft state, the session selector, the scroll toggle |
| `hub/ui/src/components/agents/AgentsPage.tsx`, `AgentDetailPanel.tsx` | The master-detail and tab structure being removed, and the duplicate header |
| `hub/ui/src/App.tsx`, `components/layout/Sidebar.tsx` | The flat eleven-entry page model being replaced |
| `hub/hub/api/v1/agent_trigger.py` | The backend already returns `status: "queued"` with a `queue_entry_id` and broadcasts `queue_entry_queued` |
| `hub/hub/api/v1/agent_chat.py` | Still-queued entries are appended to the timeline as undelivered |
| `hub/hub/auth.py` | One API key resolves to one `project_id`; the SSE ticket is signed per project |
| `hub/hub/output_recording.py`, `hub/ui/src/components/context/` | Context-usage capture and rendering already exist end to end |
| Delta specs `agent-inbound-queue`, `agent-conversation-timeline`, `agent-composer` | The approved requirements the interface must be brought back into line with |

Limits:

- **No test asserts that the composer accepts input while an agent is running.** That gap is why the
  contradiction survived phases 6–8. Task 2.1 closes it.
- **No test asserts draft persistence.** The `agent-composer` "draft survives navigation" scenario
  has never been exercised.
- Umbrella tasks 11.6–11.7 (the context meter) are **already implemented** and were never checked
  off: `record_context_usage`, `context_usage` on the agent summary, and `ContextUsageIndicator`
  with a compact variant, covered by `contextPresentation.test.tsx`. Only placement in the composer
  remains, which is task 3.8 here.
- The visual direction comes from `mock-full.html`, which is static. It proves layout at one viewport
  and nothing about live data, streaming, or state transitions.
- Backend behaviour is taken as given from reading the endpoints and their existing tests; this
  change adds no backend test because it adds no backend behaviour. If implementation reveals the
  trigger endpoint's queued path is untested, that test belongs to this change.
- Accessibility beyond keyboard operability of the overflow menu is not specified here and is not
  claimed.
