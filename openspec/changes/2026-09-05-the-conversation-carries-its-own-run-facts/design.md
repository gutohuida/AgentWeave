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
- The outcome arrives live when a run ends, including when the run ends at Hub restart and
  when it ends before its process ever spawned (D4, F291).

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
`conversation_id` and is indexed on it (`models.py:1179`, `ix_runs_conversation_started`), so this
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

**And that is not sufficient for the case it was chosen for. R2 measured it.** The paragraph above
justified the four events by the Hub-restart case, and the four events cannot serve that case, for a
reason that is entirely in the ordering: `reconcile_interrupted_runs()` is awaited inside the
lifespan at `hub/hub/main.py:350`, so it runs **before uvicorn serves anything**. Its
`sse_manager.broadcast(run.project_id, "run_interrupted", payload)`
(`hub/hub/run_reconciliation.py:117`) therefore pushes into `self._subscribers` while that dict is
empty — the browser's stream died with the old process and has not reconnected yet — and
`SSEManager.broadcast` has no replay, no buffer and no last-event-id: an event with no subscriber is
simply gone (`hub/hub/sse.py:86-103`). Adding `run_interrupted` to `eventTargetsAgent` changes
nothing at all for a run interrupted at restart. Phase 6.3's answer would still have been *never*.

**R3: the restart case was never this decision's to justify, and the case that does justify it is a
different one.** R2 was right that the four events cannot reach a browser that was disconnected
while the Hub started, and right about every line it cited. What both rounds missed is that the
restart case is **already covered on this checkout**, by a mechanism that is not per-hook: `useSSE`
itself subscribes to `onSseReconnect` and calls `queryClient.invalidateQueries()` **with no filter**
(`hub/ui/src/hooks/useSSE.ts:404-412`), which invalidates every query in the cache — both chat
queries and the timeline query included. `useSSE()` is mounted app-wide at `App.tsx:216`, and the
behaviour is already pinned by a test (`useSSE-lifecycle.test.tsx:229`, *"invalidates all queries
once the stream actually reconnects (not on the initial connect)"*). D8 is therefore a statement
about existing behaviour rather than a new subscription, and F290 — filed off R2's reading — is
retracted.

So the four events need a justification of their own, and there is one, found by looking for a
terminal run that reaches no chat-hook event at all: **a run that fails before its process ever
spawns writes no output row.** The pre-spawn `except` block (`agent_trigger.py:1960-2010`) sets
`run.status = "failed"`, commits, and broadcasts `run_failed`; it calls `record_agent_output`
nowhere, and all four call sites in that file (`:2104`, `:2325`, `:2645`, `:2898`) are after the
spawn. Its only other broadcasts are `queue_entry_queued` for the entries `return_run_entries` hands
back and `queue_entry_abandoned` for the ones it gives up on — and when every entry has reached
`DELIVERY_ATTEMPT_LIMIT` the requeued set is empty (`inbound_queue.py:222-235`), so the only events
that fire are two the chat hooks do not listen to. That is **F291**, and `run_failed` in
`eventTargetsAgent` is what closes it.

Ordering was checked for the observed cases rather than assumed: the run row's terminal status is
committed at `agent_trigger.py:2265` — **before** `_broadcast_run_lifecycle` (`:2286`) and before
the terminal status row's `record_agent_output` (`:2325`) — so a refetch triggered by either event
reads a run that has already ended. The four events are a backstop for the cases the Hub observes
and the only signal for the pre-spawn one.

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

`hub/hub/schemas/agents.py:136` already carries the four fields plus `outside_workspace_writes`.
The client's `AgentRunFacts` (`hub/ui/src/api/agents.ts:134`) carries **four of the five** — it has
no `outside_workspace_writes` (R3, measured; R2's round said it mirrored the Python shape and it does
not). That asymmetry is deliberate and stays: the field has no UI consumer, TypeScript ignores extra
JSON keys, and the server passes it through with no default so `None` and `[]` stay distinct. Task
1.5's "passed through with no default" is a rule about the **server** construction only.
`agent_chat.py` imports the schema rather than defining a parallel one; the TypeScript
`ChatHistoryResponse` reuses `AgentRunFacts` by import from `./agents`. Two shapes for one concept is how a boundary rename gets
applied to one of them.

### D8 - The restart case is served by the stream reconnecting, and that already works

**Chosen:** nothing. The reconnect refresh this requirement is stated over **exists on this
checkout**, app-wide, and is already covered by a test. This change adds no subscription; it adds a
test that pins the existing behaviour at the chat query, because the requirement now depends on it.

R2 chose this decision believing the mechanism had to be built per hook — *"the mechanism is not new
here; only its second subscriber is"* — reasoning from `useAgentOutput`'s subscription
(`hub/ui/src/api/agents.ts:557`, "a one-shot reconciliation poll after the stream was down (M21)").
R3 measured the layer above it. **`useSSE` itself subscribes**:

```ts
// hub/ui/src/hooks/useSSE.ts:404-412
useEffect(() => {
  return onSseReconnect(() => {
    queryClient.invalidateQueries()
  })
}, [queryClient])
```

`invalidateQueries()` with no filter matches every query in the cache and, at React Query v5's
default `refetchType: 'active'`, refetches every mounted one — both chat queries and the timeline
query included. `useSSE()` is mounted unconditionally at `App.tsx:216`, and the reconnect fires only
after a `fetch` to `/api/v1/events` has succeeded (`useSSE.ts:315-317`), which cannot happen until
the new Hub process is serving — by which time `reconcile_interrupted_runs()` has already written
`interrupted`, since it is awaited before `yield` in the lifespan. So the outcome is refetched
within one reconnect cycle of the Hub coming back, with no reload.

The behaviour is already pinned: `useSSE-lifecycle.test.tsx:229`, *"invalidates all queries once the
stream actually reconnects (not on the initial connect)"*.

*Rejected: adding an `onSseReconnect` subscription to each chat hook (R2's D8).* It would invalidate
a key that a broader invalidation fired from the same callback list already covers — a second
refetch of the same response, or none, depending on ordering. Redundant code that reads as
load-bearing is worse than none, because the next reader repairs the wrong thing.

*Rejected: replaying missed events on reconnect (a server-side ring buffer plus `Last-Event-ID`).*
It is the general answer and a much larger change — every event type, every consumer, a retention
policy, and a new correctness question about duplicates — for a case that is already answered.

*Rejected: making `reconcile_interrupted_runs` broadcast later, after the server accepts
connections.* It would trade a deterministic miss for a race, and it would make a startup routine's
placement load-bearing for a UI refresh. The client knows when it reconnected; the server cannot
know when the client will.

**What this costs the change, stated plainly.** The requirement's reconnect half is satisfied before
a line is written, so phase 6.3 is no longer a before/after comparison — it is a confirmation that
the map move did not take away a refresh that already worked. Phase 0.4 will measure seconds, not
"never", and tasks 0.4 and 6.3 say so.

*Rejected: replaying missed events on reconnect (a server-side ring buffer plus `Last-Event-ID`).*
It is the general answer and a much larger change — every event type, every consumer, a retention
policy, and a new correctness question about duplicates — for a case that a single invalidation
answers exactly. Worth its own change if a second consumer ever needs it; not worth carrying inside
this one.

*Rejected: making `reconcile_interrupted_runs` broadcast later, after the server accepts
connections.* It would trade a deterministic miss for a race, and it would make a startup routine's
placement load-bearing for a UI refresh. The client knows when it reconnected; the server cannot
know when the client will.

Note what this means for the requirement: the rule is *an ended run's outcome reaches an open
conversation without new content arriving*, and the two mechanisms together are what satisfy it. A
test that only exercises the four events would pass while the case that motivated them still fails.

### D9 - The `runs` prop has two readers besides the terminal label, and both were checked

`AgentTimeline` reads `runs` in three places, not one. Beyond `runs[turn.runId]` at `:237`/`:280`,
the working indicator reads it twice: `lastRunSettled` (`AgentTimeline.tsx:150`) asks whether the
newest turn's run has a terminal status, and `anotherRunIsUnderway` (`:166-172`) scans the whole map
for a non-terminal run other than the newest turn's. The second one's own comment states the
property it depends on: *"A new run's row is in `runs` before that run's first entry has been
grouped into a turn"*. **The new map cannot have that property by construction** — its keys come
from the entries — so this had to be measured rather than assumed.

**It survives, and here is the chain that makes it survive.** `deliver_entries_with_run`
(`hub/hub/inbound_queue.py:125-162`, the stamp at `:155`) stamps `entry.delivered_in_run_id = run.id` in the same commit
that inserts the `Run`, so a delivered `InboundQueueEntry` names the new run from the instant the run
exists. Both chat routes return delivered entries (`agent_chat.py:597-606`, `:665-674`) and
`_queue_entry_to_timeline` carries `run_id=entry.delivered_in_run_id`, so the entry is in the
response and `groupIntoTurns` makes it the newest turn. `queue_entry_delivered` is already in
`QUEUE_EVENT_TYPES` (`agentChat.ts:272-278`), so the response is already refetched on delivery. The
new run is therefore `lastRunId` with a non-terminal status, `lastRunSettled` is false, and the
indicator shows — by a different route than today's, but it shows. Stop-then-send (operator,
2026-08-20) is not regressed.

**Two things follow that belong in the record rather than in a reader's head.**

`agent_trigger.py:1175-1185` has an `else: session.add(run)` branch that creates a run with **no**
delivery, and a run created there would be invisible to the new map until its first output row
lands. It is unreachable in production today: `turn_scheduler.py:322` is the only production caller
of `trigger_agent_directly` and it returns at `:304-305` when `selected` is empty, so
`queue_entry_ids` is never empty there. Every other caller is a test. The branch is not removed by
this change — it is out of scope — but the dependency is now written down, and the drive checks the
behaviour rather than the argument.

And there is a real narrowing. `anotherRunIsUnderway` scans an **agent-wide** map today, so a run
executing in a *different* conversation can light the indicator in the conversation on screen. The
conversation-scoped map cannot do that. This is an improvement — the indicator should describe the
conversation being looked at — but it is a behaviour change, not a no-op, and it is chosen here
rather than discovered later.

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
