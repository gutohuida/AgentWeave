## Why

A turn's terminal label and its "Worked for Ns" line are read out of one map, and that map is
built from a different query, with a different scope and a different bound, than the turns it is
asked to label. So an operator loses a turn's outcome by doing work somewhere else.

`AgentTimeline` reads both halves from `runs`: `runs[turn.runId]?.status`
(`hub/ui/src/components/agents/AgentTimeline.tsx:237`) and `runDurationSeconds(runs[turn.runId])`
(`:280`). `turn.runId` is `entry.run_id` off a chat entry — `groupIntoTurns` sets it and nothing
else does (`hub/ui/src/lib/agentTimelineModel.ts:57`). The entries come from the chat history:
`useAgentChatHistory(agent.name, currentConversationId)` for a named conversation, the
cross-conversation recent chat otherwise (`AgentOutputPanel.tsx:350-352`).

The map does not. `runFacts = timeline?.runs ?? {}` (`AgentOutputPanel.tsx:333`), from
`GET /projects/{p}/agents/{a}/timeline`, which merges three **agent-scoped** row sets, sorts them
newest-first and truncates to fifty (`hub/hub/api/v1/agents.py:802-803`) before looking up the runs
those surviving fifty name (`:818-841`).

The two are therefore bounded by unrelated things:

| | turns rendered | runs labelled |
|---|---|---|
| source | `GET /agent/{a}/chat/{conversation_id}` | `GET /agents/{a}/timeline` |
| scope | one conversation | every conversation the agent has |
| bound | **none** — `get_chat_history` applies no limit (`agent_chat.py:567-642`) | 50 merged events |

Every turn outside that fifty-event window renders with no terminal label and no duration — which
is exactly a turn that ended with nothing to say. Measured twice on 2026-09-03 (F274,
`scripts/drive/FINDINGS.md`):

- one conversation's stopped turn read `Worked for 6s` / `Turn stopped`, then four ordinary turns
  **in four other conversations** evicted its run from the map and the same conversation reloaded
  with `{'Turn failed': 0, 'Turn stopped': 0, 'Turn interrupted': 0}` and zero stat lines;
- and without any second conversation at all: twelve turns on screen, ten in the map, the two
  oldest presenting as silent.

The eviction is driven by **event count**, not by turn count or by outcome — four filler turns
reach the cap. The 2026-09-05 drive did not reproduce it at nine runs across six conversations
precisely because those runs were short; volume, not time, is the variable.

## The requirement position, re-derived

**The timeline route is not in breach of its own two requirements, and the conversation is in
breach of a third.** This is a correction to F274's own framing, which says no requirement covers
the case.

- *The timeline carries each run's own facts* (`openspec/specs/agent-stream-events/spec.md:334`)
  ends with *"WHEN the agent has runs whose events fall entirely outside the returned event window
  THEN the map contains no entries for them"* (`:363-366`). The route does that, deliberately.
- *The run facts cover every run the events name* (`:368`) is satisfied: every run the fifty
  events name is present, by primary-key lookup.
- *A run's terminal outcome is visible* (`:299`) says **the conversation** SHALL show, for every
  run that ended, how it ended, and shall show it again after a reload. It then says: *"A run whose
  row genuinely cannot be found is the only case that may present no outcome."* F274's runs have
  rows. **That requirement is breached.**

Its next sentence points the reader at the wrong sibling: *"That is distinct from a run whose row
exists but was omitted from the response, which is a defect and is forbidden by* The run facts cover
every run the events name*."* That sibling is quantified over *the runs the events name* — it cannot
forbid omitting a run **no returned event names**, which is the whole of F274. So the corpus already
forbids the behaviour and simultaneously mis-states which rule forbids it, and the mis-statement is
why three rounds could read `:299` and still ship this: the cross-reference sends you to a
requirement the route satisfies.

## What changes

The map travels with the turns. Both chat-history responses gain a `runs` map, built from the run
ids **their own returned entries** name, looked up by primary key — the same
coverage-by-construction the timeline route already uses (`a-turn-says-how-it-ended` design D7), now
applied to the query whose result the client actually renders. `AgentTimeline` takes its `runs`
prop from the chat response.

Coverage then holds by construction and cannot be broken by volume anywhere else: the ids come from
the entries, the entries are what is drawn, and there is no window either side to fall out of.

One live-update consequence comes with it, and it is not cosmetic. `useAgentChatHistory` invalidates
on `message_created`, `agent_output` and the queue events (`agentChat.ts:284-291`) — **not** on the
run lifecycle events, which is what `useAgentTimeline` invalidates on (`agents.ts:389-407`). Moving
the facts without moving the invalidation would make a terminal label wait for unrelated traffic. A
run reconciled `interrupted` at Hub restart is the case that never arrives: the corpus states at
`:393-400` that such a run writes no terminal status line, so there is no `agent_output` event to
piggyback on.

**And the run lifecycle events do not fix that case either**, which is R2's finding:
`reconcile_interrupted_runs()` is awaited in the lifespan (`main.py:350`), before uvicorn serves
anything, so the `run_interrupted` it broadcasts reaches an empty subscriber set and
`SSEManager.broadcast` has no replay. **But the case needs nothing built, which is R3's.** `useSSE`
already subscribes to `onSseReconnect` and calls `queryClient.invalidateQueries()` with no filter
(`useSSE.ts:404-412`) — every query, chat and timeline alike — from a hook mounted app-wide at
`App.tsx:216`, and a test already pins it (`useSSE-lifecycle.test.tsx:229`). A restart refreshes the
conversation today. So the restart case is not what the four terminal events are for, and F290,
filed off R2's reading, is retracted.

What the four events are for is the terminal run that reaches **no** chat-hook event at all: a run
that fails before its process ever spawns writes no output row (`agent_trigger.py:1960-2010` calls
`record_agent_output` nowhere), and if every entry it was carrying has exhausted
`DELIVERY_ATTEMPT_LIMIT` its only broadcasts are `run_failed` and `queue_entry_abandoned`, neither of
which the chat hooks listen to. That is F291, filed by this round, and `run_failed` in
`eventTargetsAgent` closes it (design D4, D8).

## What does not change

- `GET /agents/{a}/timeline` keeps its `runs` map and both its requirements. It is a correct
  envelope for the events it returns; the defect is not that this map is wrong but that the wrong
  map was consulted. Its consumer is the Activity tab (`AgentActivityTab.tsx:24-26`).
- No migration, no new table, no new column. Two response bodies gain one additive field.
- The client-side reduction over lifecycle events that `a-turn-says-how-it-ended` deleted stays
  deleted. This change moves where the facts are read from, not who computes them.

## Impact

- Affected specs: `agent-stream-events` — two requirements added, one modified.
- Affected code: `hub/hub/api/v1/agent_chat.py` (both chat routes, `ChatHistoryResponse`),
  `hub/ui/src/api/agentChat.ts` (the response type, both hooks' SSE predicates, and both hooks'
  reconnect subscription), `hub/ui/src/components/agents/AgentOutputPanel.tsx:330-333` and `:1036`,
  `hub/ui/src/components/agents/AgentTimeline.tsx`'s `runs` prop documentation and the two working
  indicator comments that name the timeline route as that prop's source (`:133-135`, `:143-145`,
  `:152-155`).
- No server code outside `agent_chat.py`. `main.py`'s startup ordering, `run_reconciliation.py`'s
  broadcast and `useSSE`'s app-wide reconnect invalidation are read by this change's argument
  (design D8) and changed by none of them.
- Retires F274 (A) and F291 (C). Retracts F290 (B) as not a defect. Does not touch F275, F288 or
  F289.
