## Context

Conversations are already durable, first-class records. `Conversation`
(`hub/hub/db/models.py:224`) owns identity independent of the provider session, `Run`,
`AgentOutput`, `Message` and `InboundQueueEntry` all carry `conversation_id`, and the destination
model already serialises a conversation into the URL (`hub/ui/src/lib/navigation.ts:30, 83`).

What is missing is everything an operator needs to *treat* them as objects: a name, a way to find
them, a way to remove them, and a way to see which one needs attention. The rail stops at agents
(`Sidebar.tsx:194-209`), and the conversation list lives in a dropdown that also holds "New
conversation", "Handoff" and "Agent details" (`ConversationControls.tsx:134-180`).

Two prior decisions shape this work and are not reopened here:

- **Colour is information, not decoration.** From handoff-0013: *"I don't want it to be colorful…
  it should be like the chat box but maybe a little lighter."* Agent colour appears where it
  identifies something, at rest, never as a hover tint.
- **The tree is three levels because agents are real.** T3's sidebar is two levels because a thread
  picks its own model. AgentWeave's agents are durable identities with a charter, a runner, an
  inbox and a context budget, so they are a level. The recency view exists to recover the flat
  scan that the extra level costs.

## Goals / Non-Goals

**Goals:**

- Make every conversation findable, nameable, and removable from the rail.
- Make a run that is waiting on the operator visible without opening it.
- Empty the conversation-actions overflow menu and delete it.
- Give durable handoff a fixed, visible home.
- Record enough about a conversation's provenance that the specification program has somewhere to
  attach when it lands, without building any of it now.

**Non-Goals:**

- The handoff rework itself. Only its *placement* moves here; its mechanism is
  `2026-08-07-conversation-handoff-rework`, which is gated on exploration.
- Search over conversations. A named, capped tree makes it valuable; it is not this slice.
- Cross-project navigation. The recency view is scoped to one project.
- Any spec-spawned conversation behaviour. `origin` accepts `spec` so the value exists; nothing
  produces it yet.
- Hard deletion of a conversation.

## Decisions

### A conversation is created by its first message, not by the "new" action

`new_conversation()` (`hub/hub/conversations.py:15`) is called server-side from the trigger path;
there is no `POST /conversations`. The UI carries a `__new__` sentinel until the send returns a real
id (`lib/constants.ts:7`).

**Keep this.** "New conversation" navigates to a composer-primary surface; the record appears when
the first message is sent. The alternative — materialising a row on click — buys pre-configuration
(pick a model before speaking) at the cost of abandoned empty rows in a tree whose whole purpose is
scanning. Rejected. It also means the tree never contains an untitled row, which is what lets the
title requirement be unconditional.

### Attention state is denormalised onto the three blocking tables

`Question` is keyed by `from_agent`, `PermissionRequest` by `agent`; neither carries
`conversation_id`. Both reach a conversation only through `Run` (`Question.created_by_run_id`,
`PermissionRequest.run_id` → `Run.conversation_id`).

Navigation reads this state continuously, for every conversation of every agent. A two-hop join per
row on a surface that re-renders on every SSE event is the wrong shape. **Add `conversation_id` to
`questions`, `permission_requests` and `unasked_questions`**, populated at creation from the run
that opened them.

This mirrors the `batch_size` decision in `2026-08-07-batched-operator-questions`: denormalise the
field the display needs so the display costs one query. Alternative considered — a computed
attention field on the agent roster response, joining server-side. Rejected: it moves the cost
rather than removing it, and it leaves the conversation↔question link underivable for anything else
that wants it later.

### Selection lifts out of `AgentOutputPanel` into the destination

Today the panel owns `selectedConversationId`, seeds it from `initialConversationId`, auto-selects
`conversations[0]` when it loads (`AgentOutputPanel.tsx:145`), and reports changes upward through
`onConversationChange`. Two sources of truth kept in sync by effects.

The destination already carries `conversationId`. **Make it the only source.** The panel receives a
conversation and renders it.

The auto-select-first effect must move up with it, not be deleted: it is what makes "click an agent"
open something. Moved to destination resolution, where it can also be made to not fire when the
destination is deliberately the new-conversation surface — which is the bug that would otherwise
appear the moment the conversations list resolves and clobbers the operator's intent.

### Archiving refuses rather than resolves

Two obstructions, one rule.

A live run: refusing costs the operator a click; stopping the run for them destroys work with no
undo, from a row menu, in a local app with no trash.

An undelivered `InboundQueueEntry`: this one is not a preference. `latest_open_conversation`
(`conversations.py:41`) filters on `lifecycle == 'open'`, so archiving a conversation with queued
entries strands them — the next peer message finds no open conversation, creates a fresh one
(`messages.py:93-99`), and the queued entry sits in the archived thread with nothing that will ever
deliver it. Refusal is the only option that does not require inventing a re-homing rule.

Alternative considered: re-home undelivered entries to a new conversation on archive. Rejected as
scope — it invents delivery semantics to serve a housekeeping action.

### Titling is a throwaway spawn, never the agent's own session

Every model call in the Hub is a runner spawn (`hub/hub/runner_commands.py`); the handoff feature
works by sending a canned prompt as a full trigger run *inside* the conversation
(`AgentOutputPanel.tsx:334`). There is no lightweight side channel.

Titling through the agent's live session would spend the agent's own context window on titles — in
a product that tracks `context_usage` and warns on it — and would put the exchange in the timeline
unless suppressed.

**Spawn a one-shot run bound to no conversation.** `Run.conversation_id` is nullable, so a
conversation-less run is a shape the schema already permits. Fresh process, no session resume, no
timeline, no context cost. It runs after the first response has landed, so it never delays the
operator, and its failure is a no-op because the truncated title is already in place.

Alternatives considered: a direct provider API call (needs a credential surface the product does not
have, and contradicts "no new registry"); titling inside the agent's session (context cost, timeline
pollution).

### Truncation is the default and the floor

The generated title is an *upgrade*, never the only source. The conversation is titled by truncation
the moment the first message lands, so:

- a title is never absent, so the tree never shows an identifier;
- generation failing, timing out, or being disabled changes nothing structural;
- the setting is a genuine opt-in to spending tokens, which is the operator's stated intent.

### `origin` is recorded now, consumed later

One column, five values, immutable. The cost is a migration; the cost of *not* doing it is that
every conversation predating the decision is `unknown` forever.

It is already load-bearing at merge time: peer-created conversations are real rows today
(`messages.py:93-99`) and will appear in the tree indistinguishable from operator-started ones
unless something records the difference. `handoff` and `spec` are accepted values with no producer
yet — that is the point.

### `AgentsPage` and `AgentDetailPanel` are deleted, not routed

Nothing imports `AgentsPage` outside its own file and tests; it has been maintained and tested while
unreachable, and a "Settings" tab rename made in `2026-08-07-per-agent-waiting-settings` lives there
inert. With the tree owning agent navigation and the row menu owning agent settings, no future route
exists for either. Deleting them is the honest outcome; leaving them is how the question gets asked
a fourth time.

## Risks / Trade-offs

**Three migrations touching hot tables (`questions`, `permission_requests`, `unasked_questions`)**
→ Each guards for a missing table with `inspector.get_table_names()` and returns early, as `0033`
and `0034` do — an upgrade starting from an early revision reaches them with only that revision's
tables. Head assertions move in both `test_migrations.py` and `test_project_persistence.py`.

**Lifting selection out of `AgentOutputPanel` touches the most effect-dense component in the UI**
→ The panel's effects around `selectedConversationId` are already documented as fragile: one
comments that depending on the conversations array itself "re-fires the effect on every such change
and loops forever" (`AgentOutputPanel.tsx:104-115`). Removing a source of truth reduces that
surface, but the change must be made with the existing tests green at each step, not in one sweep.

**Attention state is only as fresh as the events that drive it** → It is derived from rows whose
creation already broadcasts over SSE (`question_created`, permission events, `question_not_asked`).
No new event type; if an existing broadcast is missing, the state is stale and the operator is back
to not noticing — so each of the three sources needs an explicit test that navigation updates.

**A titling spawn is a process the operator did not ask for** → It is off by default, runs after the
response, is bound to no conversation, and its failure is silent by design. Its one real risk is
process accumulation if many conversations start at once; the titling path must be serialised or
bounded, and that bound is a task, not an assumption.

**The tree can still get long** → Three agents × capped-at-N conversations plus the expander. The
cap plus archiving is the answer for now; search is the answer when it is not, and is deliberately
out of scope.

**`origin` values with no producer** (`handoff`, `spec`) → They will look like dead enum members to
a future reader. The spec states they are accepted and unproduced, and the handoff change consumes
`handoff` immediately after this one.

## Migration Plan

1. Migrations `0035` (`conversations.title`, `conversations.origin`), `0036`
   (`conversation_id` on the three blocking tables), `0037` (project title-generation setting).
   Existing rows: `title` null, backfilled lazily on first read from the conversation's first
   message; `origin` defaults to `operator` for existing rows, which is true for every conversation
   an operator has actually used and unknowable for the rest.
2. Backend first, with the UI unchanged and passing — the new fields are additive and every existing
   endpoint keeps its shape.
3. Rail gains conversations behind the existing tree, still reading the old selection path.
4. Selection lifts; the overflow menu's conversation entries are removed in the same step, so there
   is never a state with two conversation switchers disagreeing.
5. Handoff moves to the header; the overflow menu is deleted; `AgentsPage`/`AgentDetailPanel` are
   deleted.

Rollback is per-step: every step before 4 leaves a working shell with the old menu intact.

## Open Questions

- **The conversation cap.** Stated as a fixed number with an expander; the number itself is a
  judgement to make against a real project rather than in advance.
- **Whether the recency view should show archived conversations at all.** Currently no. If the
  operator archives aggressively, a recency view that hides them may feel like data loss.
- **Whether `origin: peer` should be visually distinct in the tree, or only in the conversation
  header.** The spec requires it be distinguishable; it does not say where.
