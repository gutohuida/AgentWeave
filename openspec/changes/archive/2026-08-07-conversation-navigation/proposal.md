# Conversations as a navigable level, with durable identity

## Why

A conversation is the unit of work in AgentWeave, and it is the one object with no place in the
shell. Today every conversation an agent owns is crammed into a single overflow menu
(`hub/ui/src/components/agents/ConversationControls.tsx:109-183`) alongside "New conversation",
"Handoff" and "Agent details" — so durable agent settings sit at the bottom of a conversation
switcher, behind sixteen entries labelled `conv-a3f81b2c…`, because a conversation has no name to
show (`ConversationControls.tsx:153` renders `conversation.id.slice(0, 20)`).

Two consequences follow, and the second is the expensive one:

1. **Nothing is findable.** The operator's words: *"kind of confusing and hard to find. Also those 3
   buttons showing all the conversations is not good."* There is no way to scan what is in flight,
   no way to name a thread, and no way to remove one — `Conversation.lifecycle` accepts `archived`
   and is checked by `ck_conversations_lifecycle`, but no code path in the Hub ever writes it.

2. **The operator-in-the-loop work is invisible until you go looking.** `Question`,
   `PermissionRequest` and `UnaskedQuestion` all block a run pending an answer, and none of them
   are visible anywhere except inside the conversation that raised them. With three agents working,
   a run that stopped to ask something is discovered by clicking through agents one at a time —
   while `Agent.question_timeout_seconds` counts down. Putting conversations in the navigation is
   what makes that state surfaceable at all.

This is the "ease of use is a review criterion" test from
`openspec/explorations/2026-08-02-product-direction.md`: the shell currently adds a barrier between
the operator and the work.

## What Changes

**Navigation**

- The rail gains a third level: project → agent → conversation. Agents expand to list their
  conversations, newest first, capped with an explicit expander for the remainder.
- A view toggle switches the rail between the **agent tree** (default) and a **recency list** of
  conversations across all agents of the project, ordered by last activity, each carrying its
  agent's identity colour as a persistent 2px leading edge.
- Each conversation row shows an attention state — running, awaiting the operator, or idle — so a
  blocked run is visible without opening it. **This requires `conversation_id` on `Question`,
  `PermissionRequest` and `UnaskedQuestion`**, which today reach a conversation only by joining
  through `Run`.
- Selecting a conversation is the rail's job. `AgentOutputPanel`'s internal
  `selectedConversationId` and its auto-select-first effect (`AgentOutputPanel.tsx:145`) lift into
  the destination, which already carries `conversationId` (`hub/ui/src/lib/navigation.ts:30, 83`).

**Conversation identity**

- `Conversation` gains `title` and `origin`. `origin` is one of `operator`, `peer`, `handoff`,
  `spec`, `job` — recorded at creation so a thread started by a peer agent
  (`hub/hub/api/v1/messages.py:93`) is distinguishable from one the operator started, and so a
  spec-spawned thread has somewhere to say so when that capability lands.
- Titles are set from the first message, truncated at a word boundary. A **project-level setting**
  opts into model-generated titles instead, using the project's existing `claude`/`codex` runners —
  no new provider registry, no new credential surface. The titling run is a one-shot throwaway
  spawn bound to no conversation (`Run.conversation_id` is already nullable), so it never consumes
  the agent's own context window and never appears in a timeline.
- Conversations can be renamed by the operator. An operator-set title is never overwritten by a
  generated one.

**Lifecycle**

- Conversations can be **archived** and **unarchived**, writing the `lifecycle` value the schema
  has always accepted. Archived conversations are hidden from the tree behind a per-agent
  "Show archived (N)" affordance.
- Archiving is **refused**, with a stated reason, while the conversation has a live run or
  undelivered `InboundQueueEntry` rows. Refusal rather than a silent stop: killing a run from a
  context menu is not recoverable, and an undelivered entry bound to an archived conversation would
  be stranded — `latest_open_conversation` would return nothing and the next peer message would
  open a fresh thread, orphaning the first.
- An agent that sends a message to an archived conversation receives a **failure that tells it what
  to do**: start a new conversation, with the original content restated so nothing is lost.

**Controls**

- Every row-level action lives behind a **hover `⋯` menu**, on both agent and conversation rows —
  discoverable, keyboard-reachable, and the same menu for both pointer and keyboard.
  Conversation: rename, archive. Agent: new conversation, agent settings, show archived.
- **Handoff moves to the conversation header**, beside "Fold all turns", as a persistent labelled
  control. It is not a row action and not behind a menu: it is easy to forget it exists, and a
  menu makes that worse.
- With conversations, settings and handoff all rehoused, the conversation-actions overflow menu is
  **removed entirely**.
- `AgentsPage` and `AgentDetailPanel` are **deleted**. Nothing imports them outside their own files
  and tests; the tree and the `⋯` menus are now the routed surface for everything they offered.

**Not changing**

- The composer, the timeline, autoscroll, runtime overrides, and the queue delivery contract.
- Provider session identity stays out of navigation, per the existing requirement.

## Capabilities

### New Capabilities

- `conversation-lifecycle`: the durable record behind a conversation — its title, its origin, how
  it is named, renamed, archived and unarchived, and what an agent is told when it addresses an
  archived one. Distinct from the workspace capability, which governs the surfaces that render it.

### Modified Capabilities

- `agent-conversation-workspace`: navigation becomes three levels rather than two; conversation
  selection moves from the overflow menu to the rail; the recency view and per-conversation
  attention state are added; the overflow menu is removed and its contents rehoused.
- `agent-capability-plane`: `send_message` gains a stated failure for an archived recipient
  conversation, carrying the recovery instruction and the original content.

## Impact

**Database** — `conversations.title`, `conversations.origin`; `conversation_id` on `questions`,
`permission_requests`, `unasked_questions`. Migrations `0035`–`0037`, each guarding for a missing
table the way `0033`/`0034` do. Head assertions in `hub/tests/test_migrations.py` and
`hub/tests/test_project_persistence.py` move.

**Backend** — `hub/hub/conversations.py` (creation takes `origin`, gains title helpers and the
archive guard), `hub/hub/api/v1/agent_chat.py` (PATCH title, POST archive/unarchive, archived
listing), `hub/hub/api/v1/messages.py` (archived-recipient refusal),
`hub/hub/api/v1/agents.py` (roster carries per-conversation attention), `hub/hub/api/v1/questions.py`,
`permissions.py`, `unasked_questions.py` (record `conversation_id`), a new titling module, and
`hub/hub/api/v1/projects.py` for the naming setting.

**Frontend** — `hub/ui/src/components/layout/Sidebar.tsx` (the tree gains a level and a view
toggle), `hub/ui/src/lib/navigation.ts`, `hub/ui/src/api/agentChat.ts`,
`hub/ui/src/components/agents/AgentOutputPanel.tsx` (selection lifts out; header gains Handoff),
`ConversationControls.tsx` (overflow menu removed), new row-menu and recency-list components.
Deleted: `AgentsPage.tsx`, `AgentDetailPanel.tsx`.

**Dependencies** — none. The `⋯` menu reuses `@radix-ui/react-dropdown-menu`, already present.

**Follows this change** — the handoff rework
(`openspec/changes/2026-08-07-conversation-handoff-rework/`) consumes `archive`, `origin` and
`title`, and is explicitly gated on its own exploration first.
