# Design

## Re-cutting the remaining umbrella

The `2026-07-30-hub-native-experience` change carries 69 unchecked items across phases 9–16. They
are not one capability. This section records how they are re-cut into independently approvable
changes, so that no two ledgers are live at once and so that this change's boundary is explicit.

| Slice | Intent | Deferred out of it | Depends on | State |
|---|---|---|---|---|
| **Agent conversation workspace** (this change) | Make the conversation the primary surface and let the operator talk to a running agent | Trigger menus, project switching, charters, spec authoring, approvals | Phases 1–8 | approved identity; ready to apply phase 0 |
| **Composer intelligence** | `@path` / `/command` / `$skill` triggers, keyboard menu, in-place agent selector | Anything changing what a turn receives | this change | ready to propose |
| **Local multi-project workspace** | One local operator opens several directory-backed projects | Multi-user accounts, roles, sharing | this change, single runtime | ready for technical exploration; **RQ-1 resolved** |
| **Accounting and budgets** | Per-turn token usage, aggregation, project budget pausing autonomous turns | Billing, invoicing | — (independent) | ready to propose |
| **Runner / agent / charter separation** | Reusable execution capability vs. addressable identity vs. behaviour | Charter authoring UI | — (independent) | ready to propose |
| **Specification program** | Requirement identity, traceability, evidence, drift, rigor, authoring | remote reconciliation and multi-user editing | narrowed **RQ-2** | ready for technical exploration |
| **Approval gates** | Pending task-lifecycle and spec-gate decisions inline in the conversation | New approval semantics | this change, spec program | blocked |
| **Agent capability plane** | One least-privilege read/write application API for agents, available through direct HTTP and a thin MCP adapter with equal capability and run-bound attribution | Public remote API, federation, user accounts | — (independent) | needs its own proposal |
| **Single runtime** | Make the locally-installed app the only way to run AgentWeave: delete the watchdog, local/git transports, and the CLI-only collaboration modes | The rename below | agent capability plane for replacement of the CLI fallback | needs its own proposal |
| **Retire the "Hub" name** | It is just AgentWeave | — | single runtime | deferred until the architecture settles |

Accounting and runner/charter separation carry no dependency on this change and may be proposed in
parallel. This change is placed first because it is the surface the operator touches on every
interaction, and because continuing to build against the interaction model it removes would waste
that work.

**Direction decided 2026-08-02:** AgentWeave becomes a locally-installed app that is the *only* way
to use it. There is no no-Hub product. This **reverses** the `2026-07-30-hub-native-experience`
proposal's non-goal "Not changing the CLI's local/git transports" — those transports, the watchdog,
and the Zero-relay MCP and manual-relay modes are all to be removed rather than preserved.

**Access-path correction decided 2026-08-02:** MCP is an optional adapter, not the agent API.
Company policy may prohibit MCP servers, so every supported agent capability — including selected
reads — must also be available through direct HTTP. The current MCP implementation already calls
`/api/v1` endpoints, but the non-MCP contract is still expressed as CLI-command parity and agent
identity is not uniformly bound at the REST boundary. The agent capability-plane slice replaces
that fallback and is a prerequisite to deleting its CLI commands. See
`openspec/explorations/2026-08-02-product-direction.md` for the evidence and security boundary.

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

The local-only direction resolves the first question's multi-tenant premise and narrows the second.
The specification question still needs a decision before its implementation proposal.

### RQ-1 — Operator identity versus project-scoped authentication (resolved)

Authentication binds one bearer API key to exactly one project. `_project_from_api_key` in
`hub/hub/auth.py` resolves a key row to a single `project_id`, and the SSE ticket is signed as
`{project_id}:{expires}`. Every request and every event stream is scoped to one project for the
lifetime of the credential, and the local setup endpoint returns the first non-revoked project key.

A project switcher is therefore not a sidebar feature. It requires deciding what an operator *is*
when they are not a project, how a session selects a project, whether one credential may span
projects or the client holds several, and how the SSE stream is torn down and re-established on a
switch without dropping events.

**Resolved by product direction on 2026-08-02:** AgentWeave is local-only, with one operator and
directory-backed projects. No multi-tenant operator identity is required. The future local
multi-project exploration still needs to define project discovery, lifecycle, and SSE switching,
but it must not invent accounts or cross-project bearer credentials. This change still ships a rail
adapter shaped for many projects but populated with one, and forbids a switcher before that local
project lifecycle exists.

### RQ-2 — Specification file authority

The specification program introduces stable requirement identifiers, evidence records, proposals,
and live verification state, all of which need one unambiguous home. AgentWeave ships two
specification systems as product features: this repository's own workflow under `openspec/`, and the
`aw-spec-workflow` capability (`openspec/specs/aw-spec-workflow/spec.md`) that generates portable
HTML for *user* projects and indexes it in a manifest.

The local-only direction removes cross-machine and multi-user reconciliation from the question.
What remains is deciding which portable file format is authoritative for a user's project, how the
database indexes rather than competes with it, and how identifiers, evidence, and links survive an
edit made in the user's own editor. That decision must precede building the authoring surface.
Implementing in-position accept/reject/discuss before settling it would force a second migration
once identifiers need to outlive a rewrite.

## Approach for this change

### Stable conversation identity — approved 2026-08-02

A provider session ID is not known when a new run is accepted. `POST /api/v1/agent/trigger`
currently returns `status: "running"`, a `run_id`, and `session_id: null`; the session ID is learned
later from runner output. `AgentOutputPanel` therefore keeps `isBindingNewSession` true and locks
interaction until output reveals the ID. Removing that lock alone is incorrect: a rapid follow-up
still carries `session_mode: "new"` and can start a second provider session.

The approved correction follows T3 Code's thread/turn/provider-session separation. AgentWeave owns
a durable `Conversation`; a `Run` is one execution attempt within it; provider continuation state
is a nullable binding beneath it. The application identity exists before any provider process and
never changes when that binding arrives.

#### Persistence contract

`Conversation` has these canonical fields:

| Field | Contract |
|---|---|
| `id` | `conv-{short_id()}` primary key, allocated by the server |
| `project_id` | Required project foreign key and authorization boundary |
| `agent` | Required immutable target agent; validated with the existing agent-name rule |
| `provider_session_id` | Nullable opaque provider continuation ID; not an operator-facing identity |
| `lifecycle` | `open` or `archived`; execution state is derived from runs and queue entries |
| `created_at` / `updated_at` | Server timestamps; `updated_at` advances on recorded conversation activity |
| `archived_at` | Nullable; set exactly when lifecycle becomes `archived` |

`(project_id, agent, provider_session_id)` is unique whenever `provider_session_id` is non-null, so
one provider conversation cannot silently back two AgentWeave conversations. Agent ownership is
immutable. A handoff creates a successor conversation rather than changing the agent or rebinding
the original conversation to a different provider session.

The following records gain `conversation_id`:

- `Run`: required for every newly created run and authoritative for execution attribution.
- `InboundQueueEntry`: required for every new entry; a run may drain entries from exactly one
  conversation.
- `AgentOutput`: recorded directly from the run's conversation so history needs no provider-ID or
  timestamp inference.
- `Message`: the sender conversation for outbound timeline placement; its recipient queue entry has
  the independently resolved recipient conversation.

Existing `session_id` fields remain temporarily as provider-continuation snapshots for runner
compatibility and diagnostics. They are not accepted as the canonical UI route or draft key.

#### HTTP contract

`POST /api/v1/agent/trigger` accepts:

```json
{
  "agent": "claude",
  "message": "Continue the work",
  "conversation_id": "conv-...",
  "work_dir": null
}
```

Omitting `conversation_id` means "create a new conversation." The server creates the conversation
and initial queue entry in one transaction before scheduling. Supplying it means "append to this
conversation"; the server requires the same project and agent and rejects archived, missing, or
mismatched conversations. The normal API no longer asks the client to choose `session_mode` or
send a provider `session_id`; the scheduler derives new versus resume from the conversation's
nullable provider binding.

Every successful response contains `conversation_id`, including queued outcomes:

```json
{
  "success": true,
  "agent": "claude",
  "status": "running",
  "conversation_id": "conv-...",
  "run_id": "run-...",
  "queue_entry_id": "entry-...",
  "provider_session_id": null
}
```

`status` remains `running | queued`; `run_id` is present only when this request caused a run to
start; `queue_entry_id` is always present for accepted operator input; and
`provider_session_id` is nullable diagnostic data. Legacy request fields may be decoded during the
migration only to resolve or create a conversation, but new clients and all response routing use
`conversation_id`.

History and selection use these routes:

- `GET /api/v1/agent/{agent}/conversations` lists AgentWeave conversations, newest activity first.
- `GET /api/v1/agent/{agent}/chat/{conversation_id}` returns only that conversation's recorded
  entries and its still-queued entries.
- `GET /api/v1/agent/{agent}/chat` remains the recent cross-conversation overview during migration,
  but is not the source for a selected conversation.

Normal UI copy and URLs use "conversation." Provider session IDs may appear only in agent details
or diagnostics.

#### Binding algorithm

1. Create the conversation and its first queue entry atomically, then return its ID regardless of
   whether scheduling starts immediately.
2. A run copies `conversation_id` and derives its provider resume argument from
   `Conversation.provider_session_id`: null starts a provider session; non-null resumes it.
3. When runner output first reports a provider session ID, update the run snapshot and bind the
   conversation in the same transaction before recording that output.
4. If the conversation binding is null, set it. If it already equals the reported value, do
   nothing. If it differs, fail the run and record a binding-conflict event; never overwrite it.
5. Record every output with both `run_id` and `conversation_id`. History never reconstructs
   identity from timestamps or provider IDs.

#### Queue scheduling algorithm

1. Every new queue entry already targets one conversation.
2. When an agent becomes idle, choose the conversation belonging to the oldest eligible queued
   entry. Preserve the global rule that older eligible work is chosen first.
3. Drain only entries for that conversation, in their arrival order, up to the existing per-turn
   cap. Never combine entries from different conversations in one provider turn.
4. Derive new/resume solely from that conversation's provider binding. An unbound conversation with
   a currently running run remains queued; it does not start another provider session.
5. Hop-budget blocking, withdraw, deliver-now, return-on-failure, and subsequent scheduling retain
   their existing semantics within the selected conversation.

#### Lifecycle, retry, stop, and handoff

- A conversation remains `open` across run completion, failure, interruption, stop, and retry.
- Stop targets the active run, not the conversation; queued entries remain attached to it.
- Retry creates a new run under the same conversation. It resumes the bound provider session when
  available; an unbound failed first attempt starts a fresh provider attempt without changing the
  AgentWeave conversation ID.
- Archive rejects new input but preserves history. Unarchive restores input eligibility.
- Handoff first checkpoints the source conversation, then creates a new successor conversation for
  the next message. The successor is unbound and receives the handoff-resume prompt exactly once;
  neither conversation changes identity.

#### Legacy and reset policy

The migration is deterministic and preserves records:

1. For each distinct non-null `(project_id, agent, session_id)` represented by an existing run,
   create one open conversation and attach matching runs, outputs, delivered queue entries, and
   outbound messages.
2. For an existing run with null `session_id`, create one conversation for that run and attach its
   recorded outputs and delivered entries.
3. Each still-queued operator entry gets the conversation resolved from its requested legacy
   session; a legacy `new` entry gets its own unbound conversation.
4. Still-queued peer entries resolve to the recipient's newest open conversation, or create one
   unbound conversation if none exists.
5. Ambiguous orphan rows remain queryable through the recent overview and are reported by migration
   diagnostics; the migration never guesses from timestamp proximity and never deletes them.

`agentweave reset` may delete conversation/runtime data only under its existing explicit reset
confirmation. Ordinary startup, migration, stop, archive, and project reopen never clear it.

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
                                          └── overflow ▸ new · conversations · handoff
                                                          · fold all · details

POST /api/v1/agent/trigger ──► { status: "running" | "queued",
                                conversation_id, queue_entry_id, run_id? }
SSE  queue_entry_queued / queue_entry_delivered / agent_output   (all existing)
```

## Algorithms

### Submitting composer input

This replaces a path whose first step is effectively "if the agent is running, do nothing."

1. If the composer text is empty or whitespace only, stop.
2. If a submission for this conversation is already in flight, stop.
3. Mark a submission in flight and clear the composer text optimistically.
4. Call the trigger endpoint with the agent, the text, and the current `conversation_id`; omit the
   ID only for the explicit new-conversation state. Do not branch on the agent's running state — the
   endpoint decides.
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

1. Drafts are keyed by project and AgentWeave conversation identity under one namespaced storage
   key. A not-yet-created conversation uses a distinct project-and-agent new-conversation key.
2. On mounting a conversation, read that conversation's draft and seed the composer; an absent
   draft seeds an empty composer.
3. On every change to the composer text, write that agent's draft, debounced.
4. Before deleting a successfully submitted draft, cancel any pending debounced write so stale text
   cannot be written back after deletion.
5. On successful submission, delete that conversation's draft.
6. If storage is unavailable the composer still functions; only persistence is lost. This mirrors
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
   conversation, conversation selection, handoff, fold all, agent details.
4. If an action is unavailable — handoff on a manual runner, for example — present it disabled with
   its reason rather than omitting it, so the menu's contents do not shift between agents.
5. Activating agent details opens a non-navigating details panel for the current agent and leaves
   the conversation mounted; closing it returns focus to the invoking menu item.

## Key decisions

- **The composer never inspects `isRunning` to decide whether to accept input.** The endpoint
  already reports which of the two outcomes occurred, and the queue is durable. Any client-side
  prediction of agent state is a second source of truth that can only be wrong.
- **Queued input is rendered from server records, not optimistically.**
  `agent-conversation-timeline` requires entries to be placed by recorded association. A locally
  synthesized entry would violate that and would double-render when the real record arrives.
- **Provider sessions are diagnostic bindings, not UI identity.** Normal navigation, selection,
  history, drafts, and URLs use `conversation_id`. Exposing provider IDs as the picker would merely
  recreate the coupling this migration removes.
- **Drafts live in browser storage keyed by project and conversation, not on the server.** A draft is unsent operator
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

- Conversation endpoints add no new principal type. They consume the same project-scoped operator
  credential and signed SSE ticket as today, and every conversation lookup verifies both project
  and agent scope before returning or mutating data.
- A caller cannot choose `provider_session_id`, reassign a conversation to another agent, or use a
  conversation from another project. Provider binding is written only by the run-output path.
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
| `hub/hub/api/v1/agent_trigger.py` | The backend returns `running | queued`, but new runs expose no durable identity before the provider session arrives |
| `hub/hub/turn_scheduler.py` | A second legacy `new` entry can start another provider session; queue draining currently has no conversation boundary |
| `hub/hub/api/v1/agent_chat.py` | History is routed by provider session and the recent route appends agent-wide queued entries |
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
- Phase 0 changes backend persistence and routing and therefore requires contract, migration, and
  concurrency tests before the frontend running-composer lock is removed.
- Accessibility beyond keyboard operability of the overflow menu is not specified here and is not
  claimed.
