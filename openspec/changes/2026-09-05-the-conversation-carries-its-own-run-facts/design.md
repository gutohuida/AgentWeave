## Context

`a-turn-says-how-it-ended` (archived 2026-09-03) gave the timeline response a `runs` map so a turn
could state its outcome from the run row rather than from event names. It succeeded at what it
argued about: the map is exact for the events the response returns, by primary-key lookup, and its
round 3 correctly rejected the ranked-and-capped query rounds 1 and 2 had specified.

F274 is the residue. The component that consumes the map does not render the response the map came
from. Turns are chat entries; the map is keyed to timeline events. The change's three rounds argued
about the run query and never asked what the client was rendering **outside** the event window.

This change moves one map. Everything below is about making that move exactly right, because the
same defect has now been shipped twice by an argument that was right about the wrong window.

## Goals / Non-Goals

**Goals**

- A turn on screen presents its outcome for as long as its entries are on screen, whatever the agent
  did elsewhere.
- Coverage by construction, not by a bound that could be chosen too small.
- The outcome arrives live when a run ends, including when the run ends at Hub restart.

**Non-Goals**

- Changing what a run's facts *are*, or where they are recorded. `RunFacts` is reused verbatim.
- Removing the timeline route's map (D5).
- Bounding the conversation-scoped chat route. It is unbounded today and this change does not make
  that better or worse (D6).

## Decisions

### D1 - The facts travel with the turns, not with the events

**Chosen:** both chat-history responses carry `runs: Dict[str, RunFacts]`, and `AgentTimeline` reads
its `runs` prop from the chat response.

The invariant the client needs is *every run a rendered turn names has facts*. A turn names a run
because a chat entry does. So the only response that can satisfy the invariant by construction is
the one that returns those entries. Any other arrangement makes coverage a claim about two windows
agreeing, which is what F274 is.

*Rejected: widening or re-scoping the timeline's event window.* It does not fix the single
conversation case - twelve turns, ten labelled, no second conversation involved - because the chat
route has no bound at all, and no event window has to be as large as an unbounded query's result.
Choosing a larger cap is the same mistake at a larger number, and design D7 of the prior change
already rejected size as a route to coverage.

*Rejected: a second round trip -- `GET /projects/{p}/runs?ids=...` called by the client with the ids
it just rendered.* Three costs and no benefit: a client-assembled query string that grows with the
conversation and can exceed a URL length limit; a second cache entry that can disagree with the
first, so a turn can render before its facts arrive and flicker from silent to stopped; and a new
public route whose only caller is this one.

*Rejected: leaving the map where it is and having the client merge two maps.* Both are still bounded
by the same fifty events. It changes nothing.

### D2 - Lookup by id off the returned entries, not by conversation

**Chosen:** collect `entry.run_id` over the entries the route is about to return, then
`select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))`. No `ORDER BY`, no `LIMIT`.
The id set is the bound, exactly as `agents.py:818-841` does it.

*Rejected: `select(Run).where(Run.conversation_id == conversation_id)`.* `Run` does carry
`conversation_id` and is indexed on it (`models.py:1180`, `ix_runs_conversation_started`), so this
is available and would be one fewer parameter to bind. It is refused on two grounds. It relies on
`Run.conversation_id` and `AgentOutput.conversation_id` agreeing - a denormalization holding, rather
than the ids the response is literally returning - and the recent-chat route
(`agent_chat.py:646`) is cross-conversation, so it would need the id-set form anyway. One
construction for both routes, and it is the one that cannot disagree with the payload.

The `project_id` predicate is carried across for the same reason `agents.py`'s comment gives: the
ids come from rows already filtered, so it is enforcement rather than inference, and this is a new
cross-project leak surface that `test_bola.py` should cover.

### D3 - Both chat routes, because the panel switches between them

`AgentOutputPanel.tsx:352` reads `chat = currentConversationId ? conversationChat : recentChat`.
Giving only the conversation route a map would leave the recent view - the one shown before a
conversation is chosen - reading `{}` and silently presenting every turn as outcomeless, which is
the defect this change removes, reintroduced on the other branch of one ternary.

`get_recent_chat` already truncates to `limit` before returning (`agent_chat.py:697`), so its id set
is taken **after** that truncation, from the entries it returns. Ordering matters: the map is built
from the final `entries` list, after `entries = entries[-limit:]` and after `_queued_entries_for`
extends it, so that a still-queued or abandoned entry naming a delivered run is covered too.

### D4 - The invalidation moves with the map

`useAgentChatHistory` and `useAgentRecentChat` invalidate on `message_created`, `agent_output` and
the queue lifecycle events (`agentChat.ts:284-291`). `useAgentTimeline` invalidates on those plus
`run_started`, `run_completed`, `run_failed`, `run_stopped`, `run_interrupted`, `log_event`,
`agent_heartbeat` (`agents.ts:389-407`).

Move the map without moving the invalidation and the terminal label becomes a thing that arrives
when something *else* happens. Mostly it would look fine: `record_agent_output` persists a terminal
status line on both spawn paths' finalize blocks, and that broadcasts `agent_output`. The case that
never arrives is the one the corpus already carves out at `:393-400` - a run reconciled
`interrupted` at Hub restart writes **no** terminal status line, because there was no Hub process to
write one. An operator with the conversation open watches that turn stay silent indefinitely.

So the chat hooks' SSE predicate gains the four run-terminal event types. Not `run_started`: nothing
in a chat response changes when a run begins that an `agent_output` event will not already carry,
and an extra refetch of an unbounded response is a real cost. This is a deliberate divergence from
`eventBelongsToTimeline` rather than reuse of it, and the reason belongs in a comment at the call
site.

### D5 - `AgentTimeline.runs` stays

After this change nothing in the UI reads it: `AgentActivityTab` unwraps `events` only and says so
in its own comment (`AgentActivityTab.tsx:24-26`).

Kept anyway. Removing it deletes two requirements that shipped two days ago
(`agent-stream-events:334` and `:368`) and their tests, removes a field from a public response, and
buys no behaviour - the map is correct for what it describes. The Activity tab showing outcomes is a
plausible next consumer, and the requirements are worth keeping regardless as the statement of how
such a map is built.

The risk of keeping it is that a future author re-wires the panel back to it. The mitigation is the
prop documentation on `AgentTimeline` - which today reads *"straight from the timeline route"* and
must be corrected as part of this change, not left saying the opposite of the new rule - plus a
regression test that fails when the panel's `runs` come from the timeline query.

### D6 - The unbounded id set is not chunked, and that is measured

`get_chat_history` applies no limit, so the id set is bounded only by the distinct runs in one
conversation. SQLite's bound-parameter ceiling is `SQLITE_MAX_VARIABLE_NUMBER`, 32766 since 3.32;
this machine's Python 3.11 links **3.45.1** (measured, `py -3.11 -c "import sqlite3; print(...)"`).
A conversation would need 32,766 distinct runs to reach it, at which point the unbounded entry list
is the operator's problem long before the parameter count is.

No chunking, then, and no limit added here. Bounding the conversation route is a real question with
its own consequences (pagination, "load older", scroll restoration) and does not belong to a change
about run facts.

### D7 - `RunFacts` is reused, not re-declared

`hub/hub/schemas/agents.py:136` already carries the four fields plus `outside_workspace_writes`, and
the client's `AgentRunFacts` (`hub/ui/src/api/agents.ts:134`) mirrors it. `agent_chat.py` imports the
schema rather than defining a parallel one; the TypeScript `ChatHistoryResponse` reuses
`AgentRunFacts` by import from `./agents`. Two shapes for one concept is how a boundary rename gets
applied to one of them.

## Risks / Trade-offs

- **One extra query per chat fetch, on the hottest read path in the product.** A primary-key `IN`
  lookup over a set the route already holds; the alternative is the defect. Worth measuring in the
  drive rather than asserting.
- **Two maps built the same way from different windows.** Accepted under D5, with the prop comment
  and a test as the guard.
- **The recent-chat route's map is agent-wide by nature.** That is correct there - that view is
  agent-wide - but it means the same component receives a conversation-scoped map in one branch and
  an agent-scoped one in the other. Both satisfy the invariant, because both are keyed to their own
  entries.

## Migration Plan

None. Two responses gain an additive field; older clients ignore it. The UI change and the API
change ship together, and the timeline route is untouched, so a UI bundle from before this change
continues to work against a Hub after it.

## Open Questions

- Should `AgentActivityTab` gain outcome rendering, making D5's "plausible next consumer" real?
  Out of scope here; worth a finding if the operator wants it.
