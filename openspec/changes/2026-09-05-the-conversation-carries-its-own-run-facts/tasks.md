## 0. Observe it before building — a gate, not a preamble

F274 was measured on 2026-09-03 and **did not reproduce** on the 2026-09-05 drive at nine runs
across six conversations, because those runs were short and the cap is on events rather than turns.
So the first thing to establish is that the defect is still live on this checkout, at a volume you
choose deliberately. **If phase 0 has not been recorded, do phase 0 and stop.**

- [x] 0.1 A Hub on **a spare port** — never port 8000, and leave `:8010` alone — from `hub/` with
      uvicorn from source, against a fresh fixture project deleted afterwards. Every real agent turn
      binds `claude-haiku-4-5`. Confirm no `.py` under `hub/hub` or `src` is newer than the process
      start.

      *Reworded by the second review, 2026-09-08.* This task said "trial Hub on 8011, never
      `proj-5e960453` or `proj-18e5d4e0`", written 2026-09-05 and overtaken by the 2026-09-07 clean
      slate: `proj-5e960453` and the `drive8011` profile were deleted, and the trial Hub is now
      `:8010` serving `~/.agentweave/hub/profiles/trial/agentweave.db` with this repo registered as
      `proj-d85a82bf4216`. Naming a spare port and a throwaway project survives the next profile
      churn; naming a specific one did not survive two days.
- [x] 0.2 **The headline, cross-conversation.** In conversation A, run a turn and stop it; confirm
      `GET /agents/{a}/timeline` has its run in `runs` and the served bundle shows the terminal
      label and the "Worked for Ns" line. Then drive turns in **other** conversations on the same
      agent until `len(timeline.events) == 50` and A's run id is no longer a key in `runs`. Reload
      A in the browser and record: turn boundaries, terminal-label occurrences, stat lines.
      **Count events, not turns** — a short turn contributes fewer events, which is why the
      2026-09-05 drive missed this.
- [x] 0.3 **The headline, single-conversation.** Same agent, one conversation, enough turns that the
      chat response names more distinct runs than the timeline's fifty events do. Record
      `distinct run ids in chat` vs `len(runs)` vs `terminal labels on screen`. This is the half
      that proves no widening of the event window fixes it.
- [x] 0.4 **The live half (D8), and it is expected to already work.** With conversation A open in
      the browser, restart the Hub so `reconcile_interrupted_runs` writes `interrupted` for A's
      running run. Record how long the turn stays unlabelled with nobody touching the page.
      **Expect seconds, not "never"** — `useSSE`'s reconnect handler invalidates every query
      (`useSSE.ts:404-412`), so this is a baseline the change must not regress, not a defect to fix.
      If it *does* read "never", D8 is wrong and this whole change needs another round before
      phase 1.
- [x] 0.5 **The live half that is a defect (D4, F291).** Make a run fail before it spawns — bind the
      agent to a runner whose binary does not exist — with the conversation open, and with its
      delivered entry already at `DELIVERY_ATTEMPT_LIMIT` so nothing is requeued. Record whether the
      turn ever presents `failed` without a reload, a reconnect, or unrelated traffic. This is the
      case task 3.1 exists for.
- [x] 0.6 Record run ids, conversation ids, event counts and timestamps in
      `scripts/drive/FINDINGS.md` under F274, and 0.5's result under F291.

**Phase 0 recorded 2026-09-09 (night window, iteration 14). The gate is passed and the defect is
live**, in both shapes: eight ordinary turns in *other* conversations take a stopped turn's label
and its "Worked for 8s" off the screen, and ten turns in *one* conversation leave the two oldest
with no duration. Numbers, run ids and screenshots are in `scripts/drive/FINDINGS.md` under F274.
Hub `127.0.0.1:8012`, own profile database, project `proj-9042770d2ae3`, agent `scribe050237`;
scripts uncommitted in `testbed/scratch/f274p0/`. **0.1's "deleted afterwards" was not
done, deliberately:** phase 6 re-runs 0.2 and 0.3 *exactly*, and a before/after is worth more
on the same rows than on new ones. The Hub process was stopped; the profile database, the
project and the fixture directory are kept, and `testbed/scratch/f274p0/start_hub.sh` brings
the instance back.

**0.4 read seconds, not "never"** — 8.6 s from the row being written to the label appearing, with
no reload — so D8 stands and phase 1 may proceed. One confound is recorded with it: the interrupted
run's entry was re-delivered 2 s earlier, so queue traffic was in the same window and this does not
by itself show that the *reconnect* invalidation is what refreshed the page. Task 3.5 still has to
ask its own question.

**0.5 changed two things and phase 3 must not be written until they are read.**

1. Its own recipe does not work. *"A runner whose binary does not exist"* is refused by
   `probe_agent` at `agent_trigger.py:665` before a `Run` row exists, so nothing fails and there is
   nothing to watch. The pre-spawn `except` block is reached by pinning a CLI at a file that exists
   and is not an executable — and pinning a CLI has no operator-facing route at all.
2. **F291's predicted symptom is falsified.** The failing run's entry is *abandoned*, an abandoned
   entry lands in `groupIntoTurns`'s `pending`, and so **there is no turn**: 0 turn boundaries for
   the whole watch, and the operator is told live by a NOT DELIVERED block instead. `run_failed`
   has nothing to label on this path.

   Task 3.1 is probably still right — after this change the map rides on the chat response and
   something has to refresh it — but **the reason written into 3.1's text is false as stated**, and
   3.1 says in as many words to comment that reason at the site. Re-derive it against the code
   before writing it; do not transcribe the sentence about F291 into a source comment.

## 1. The chat responses carry their own run facts

- [x] 1.1 `ChatHistoryResponse` (`hub/hub/api/v1/agent_chat.py:173`) gains
      `runs: Dict[str, RunFacts] = Field(default_factory=dict)`, importing `RunFacts` from
      `hub.schemas.agents` rather than declaring a second shape (design D7).
- [x] 1.2 One helper in `agent_chat.py` — `_run_facts_for(session, project_id, entries)` — that
      collects `entry.run_id` over the entries handed to it, returns `{}` on an empty set, and
      otherwise runs `select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))` with no
      `ORDER BY` and no `LIMIT`. Carry the `project_id` predicate and the comment saying it is
      enforcement rather than inference (design D2). **`Run` is not imported in `agent_chat.py`** —
      its `from ...db.models import (...)` block at `:36-47` does not name it, so add it there.
      (Noted by the third review; every other symbol this change touches was already named.)
- [x] 1.3 `get_chat_history` (`:567`) calls it on the **final** `entries` list — after the sort and
      after `_queued_entries_for` extends it (`:633-635`) — and returns the map.
- [x] 1.4 `get_recent_chat` (`:646`) calls it on **its** final list — after `entries[-limit:]`
      (`:697`) and after `_queued_entries_for` — so the map matches what that response returns and
      not what it read (design D3).
- [x] 1.5 The status rename is the boundary's, once: `RunFacts` is constructed exactly as
      `agents.py:830-841` does, `running` spelled `started`, `outside_workspace_writes` passed
      through with no default. Both chat routes go through 1.2's single helper, so there is one
      construction in `agent_chat.py` and nothing to factor — **do not** factor it together with
      `agents.py:830-841`, which would contradict this proposal's Impact line (*"No server code
      outside `agent_chat.py`"*). The duplication across the two modules is accepted deliberately;
      task 4.6's BOLA test is what keeps the `project_id` half honest. (Clarified by the third
      review, which read the original clause both ways and found one of them vacuous and the other
      contradicting the proposal.)

## 2. The client reads the facts from the response that carries the turns

- [x] 2.1 `hub/ui/src/api/agentChat.ts`: `ChatHistoryResponse` gains
      `runs: Record<string, AgentRunFacts>`, importing `AgentRunFacts` from `./agents`.
- [x] 2.2 `AgentOutputPanel.tsx:333`: `runFacts` comes from `chat.data?.runs ?? {}` and no longer
      from `timeline?.runs`. Check whether `useAgentTimeline` is still called in this component for
      anything else — as of this proposal it is not (`:332-333` is its only use) — and remove the
      call if it has become dead. **Do not remove the timeline route's map** (design D5). The
      two-line comment directly above it (`:330-331`, *"This panel reads neither half; it is the
      only thing that can carry them"*) explains why the hook lives here and must go with the hook
      rather than be left describing something that is no longer there.
- [x] 2.3 `AgentTimeline.tsx`'s `runs` prop comment currently reads *"straight from the timeline
      route"*. Rewrite it to name the chat response and to say why: the map must be keyed to the
      same query as `entries`, and the timeline route's map is scoped to a different window. Keep
      the existing "a caller with nothing to say must say `{}`" rule.
- [x] 2.4 **The working indicator reads this prop too, in two more places** (design D9), and neither
      is about a turn's terminal label: `lastRunSettled` (`AgentTimeline.tsx:148-150`) and
      `anotherRunIsUnderway` (`:166-172`), whose own comment says it depends on the map holding a
      run *before that run's first entry has been grouped into a turn* — which the new map cannot do
      by construction. Do not change the logic; R2 measured that it survives and R3 re-derived the
      chain link by link (`inbound_queue.py:152-160` stamps `delivered_in_run_id` in the same
      commit that adds the `Run`; `_queue_entry_to_timeline` gives a delivered entry
      `timestamp=entry.delivered_at`; both routes sort ascending, so that entry is last and
      `groupIntoTurns` — which preserves array order and does not sort — makes its run the newest
      turn). Do correct the three comments that name the timeline route as that prop's source
      (`:133-135`, `:143-145`, `:152-155`) and state the chain instead: a delivered `InboundQueueEntry` names the new run from the instant the run is
      committed, so the new run *is* the newest turn rather than an entry-less key. Task 6.7
      measures it live rather than trusting this paragraph.

## 3. The invalidation moves with the map

- [x] 3.1 `agentChat.ts`: `eventTargetsAgent` (`:284`) also returns true for `run_completed`,
      `run_failed`, `run_stopped` and `run_interrupted` when `data.agent` matches — deliberately
      **not** `run_started` (design D4). Comment the divergence from `eventBelongsToTimeline` at the
      site, and give the reason that is actually load-bearing: a run that fails **before its process
      spawns** writes no output row at all (`agent_trigger.py:1960-2010`), so on that path
      `run_failed` is the only event a chat hook can hear (F291). Do **not** write the
      Hub-restart reason there — that case is served by `useSSE`'s reconnect invalidation and this
      predicate has nothing to do with it (design D8).
- [x] 3.2 Confirm the four events actually carry `agent` in their SSE payload before relying on it —
      `eventBelongsToTimeline` reads `d.agent === name` for exactly these, so this is a check that
      the existing reader is right, not an assumption inherited from it.
- [x] 3.3 Both hooks share `eventTargetsAgent`, so 3.1 covers the recent view too. Verify that is
      still true rather than assuming it.
- [x] 3.4 **Add no reconnect subscription** (design D8). R2's version of this task told you to give
      both chat hooks their own `onSseReconnect` handler; R3 measured that `useSSE` already has one
      that invalidates *every* query (`useSSE.ts:404-412`), from a hook mounted app-wide at
      `App.tsx:216`. Confirm both facts on the checkout before relying on them — read the two lines,
      do not take them from here — and then write nothing. If either has changed, stop: the second
      ADDED requirement's reconnect half has lost its mechanism and needs a decision, not a patch.
- [x] 3.5 Confirm the ordering claim on the checkout rather than inheriting it from this document:
      with a browser attached, restart the Hub and check whether any `run_interrupted` frame arrives
      on the reconnected stream. Expect none. If one does arrive, D8's premise is wrong — say so
      rather than deleting the comment, because 0.4's measurement would then have a second
      explanation.

**Sections 2 and 3 built 2026-09-09 (night window, iteration 16), client only.** What was
written, and what was confirmed and then deliberately not written:

- **2.2's removal was justified before it was made.** `useAgentTimeline` was called once in
  `AgentOutputPanel` (`:332`) and `timeline` read once (`:333`); both are gone, the import with
  them, and the two-line comment moved WITH the value to its new site beside `chat.data?.entries`.
  It says what the pairing is for rather than only that the panel does not read it.
- **3.1's comment does not carry F291's sentence, and the reason it carries instead is measured
  off the code.** The load-bearing case is an operator **stop**: `stop_agent_run`
  (`agent_trigger.py:1571-1627`) force-terminates the process and writes no `AgentOutput` row, so
  no event this predicate already matched fires and `run_stopped` is the only thing a chat
  listener hears about that run ending. The secondary reason is an ordering one: on the paths that
  do persist a terminal status line, the `agent_output` broadcast and the run row's commit are
  separate, so a refetch triggered by the output alone can read the row while it still says
  `started`.
- **3.2 confirmed rather than inherited.** All four events carry `agent`:
  `_broadcast_run_lifecycle` builds `payload = {"agent": agent, "run_id": run_id, **fields}`
  (`agent_trigger.py:1785`) for `run_completed`/`run_failed`/`run_stopped`, and
  `run_reconciliation.py:102-117` does the same for `run_interrupted`, which is broadcast from a
  different module and so had to be checked separately.
- **3.3 confirmed:** `useAgentChatHistory` and `useAgentRecentChat` both call `eventTargetsAgent`
  in their `useSSE` callbacks, so 3.1 covers the recent view with no second edit.
- **3.4 confirmed, and nothing written.** `useSSE.ts:404-412` still invalidates every query on
  reconnect, and `App.tsx:216` still mounts `useSSE()` app-wide. Both read on this checkout.
- **3.5 answered from the code, and the live half is 6.3's.** No `run_interrupted` frame can reach
  a reconnecting client: `reconcile_interrupted_runs()` is awaited at `main.py:402`, six lines
  before the lifespan's `yield`, so it broadcasts into `_subscribers` before uvicorn serves
  anything. D8's premise holds. This is an ordering argument, not a browser measurement — 6.3 has
  the browser attached and re-runs 0.4, and that is where the frame count gets watched.

## 4. Tests — each one mutation-checked

Every test below must be shown to fail against the unfixed code. A test that passes both ways is
not evidence, and this repository's dominant failure mode is exactly that.

- [x] 4.1 `hub/tests/` — a conversation's chat response carries facts for every run its entries
      name. Mutation: return `{}` and watch it fail.
- [x] 4.2 The one that would have caught F274: build an agent with **one** conversation holding a
      finished run, then enough events on **other** conversations to exceed any fixed window, and
      assert the first conversation's response still carries that run. Assert on the chat response
      alone — a test that also reads the timeline route will pass for the wrong reason.
- [x] 4.3 Single-conversation volume: more distinct runs in one conversation than a fifty-event
      window can name, every one present in the map.
- [x] 4.4 The recent-chat route carries facts for the runs **it** returns, taken after its `limit`
      truncation — construct a case where a pre-truncation entry names a run the post-truncation
      entries do not, and assert that run is absent. This is what pins "after, not before".
- [x] 4.5 An entry naming a run with no row leaves the key absent rather than raising.
- [x] 4.6 `hub/tests/test_bola.py` — both chat routes' `runs` maps cannot carry another project's
      run. Mutation: drop the `project_id` predicate.

**4.1-4.6 built and mutation-checked 2026-09-09 (night window, iteration 15).** Ten tests in
`hub/tests/test_chat_run_facts.py` plus one in `hub/tests/test_bola.py`; 29 passed with
`test_agent_chat.py`. **Seven mutations run**, `agent_chat.py` md5-verified back to
`4cf271e0f368f1f5cb03c0eb6d6d524a` after each, and **every one of the eleven tests is named by at
least one of them**:

| Mutation | Kills |
|---|---|
| M1 `_run_facts_for` returns `{}` | 8 of the 10 in the new file |
| M2 recent-chat map built **before** `entries[-limit:]` | `..._map_is_taken_after_the_limit_truncation` |
| M3 `Run.project_id == project_id` dropped | the BOLA test, and only it |
| M4 boundary rename dropped (`running` served raw) | `..._renamed_started_at_the_boundary` |
| M5 `outside_workspace_writes or []` | `..._never_none_becomes_empty_list` |
| M6 `.limit(50)` on the run lookup | `..._more_runs_than_a_window_holds` |
| M7 map bounded by the project rather than by the entries | 3, including the empty-map test |

Two things the tally makes visible and no test yet covers. **1.3's "after `_queued_entries_for`"
is not observable**: a queued entry's `run_id` is `delivered_in_run_id`, which is `NULL` until it
is delivered, so moving that call has no effect on the map today. The ordering is kept because it
stops being free the moment an abandoned entry keeps its delivered run — but it rests on reading
the code, not on a red test, and a future change to `_queue_entry_to_timeline` would not be
caught. **M7 was what forced the empty-map test to be worth writing**: as first drafted it asserted
`runs == {}` for a conversation with no runs at all, which no mutation of this code can falsify.
It now gives the agent a run in a *different* conversation, and M7 kills it.
- [x] 4.7 `hub/ui/src/__tests__/` — the panel passes the **chat** response's `runs` to
      `AgentTimeline`. Mutation: wire it back to the timeline query and watch it fail. This is D5's
      guard and the reason the two maps may coexist.
- [x] 4.8 `hub/ui/src/__tests__/` — `eventTargetsAgent` returns true for the four terminal run
      events and false for `run_started`. Mutation both directions.
- [x] 4.9 `hub/ui/src/__tests__/` — an SSE **reconnect** refetches a chat query (design D8). This
      pins existing behaviour rather than new code, and it is the requirement's only guard: nothing
      else fails if `useSSE.ts:404-412` is narrowed from `invalidateQueries()` to a filtered call.
      Drive it through `useSSE`'s own reconnect path rather than through a per-hook mock —
      `useSSE-lifecycle.test.tsx:229` is the shape, `agentOutput-polling.test.tsx:22` is the wrong
      one here because it mocks the very layer under test. Mutation: narrow the global invalidation
      to any single key and watch this fail.
- [x] 4.10 `hub/ui/src/__tests__/` — the working indicator still shows for a just-started run whose
      only entry is its delivered operator input, with the previous turn settled (design D9). This
      is the 2026-08-20 stop-then-send behaviour, and it is the one thing the map move could take
      away silently. Mutation: drop the delivered entry from the fixture and watch it fail.

**4.7-4.10 built and mutation-checked 2026-09-09 (night window, iteration 16).** Four tests
across three files plus one new file, run inside the whole UI suite: **146 files, 1512 tests,
all passing**, `npm run lint` clean. Every source file was md5-verified back to its baseline after
each mutation.

| Mutation | Kills |
|---|---|
| M-A `runFacts` wired back to `useAgentTimeline(agent.name).data?.runs` | 4.7 (`timelineEnvelopeUnwrap`) |
| M-B1 `RUN_TERMINAL_EVENT_TYPES` dropped from the predicate | 4.8's positive case |
| M-B2 `run_started` added to that set | 4.8's `does NOT match run_started` |
| M-B3 predicate ignores which agent (`return true`) | 4.8's different-agent case, and 2 older ones |
| M-C reconnect invalidation narrowed to `{queryKey: ['agents']}` | 4.9 — **and nothing else** |
| M-D `runVisiblyActive` drops the `!lastRunSettled` half | 4.10's positive case, and 6 older ones |
| M-E `runVisiblyActive` drops both gates | 4.10's negative case, and 7 older ones |

Three things the pass established that the tasks only asserted:

1. **4.9's premise is correct, measured.** Under M-C the existing
   `useSSE-lifecycle.test.tsx` reconnect test **still passes** — it spies `invalidateQueries` and
   a filtered call is still a call. 4.9 counts real refetches of a real chat query instead, and it
   is the only test in the suite that fails when that invalidation is narrowed.
2. **4.7 needed a decoy, not a fixture.** The existing assertion (`runs` equals the timeline
   envelope's map) had to change direction anyway; asserting equality against the chat map alone
   would pass under M-A whenever the two fixtures agreed. The timeline mock now serves a
   `run-timeline-only` row that must never reach the screen, and M-A fails on both halves.
3. **4.10's fixture derives `runs` from its entries**, the way the response does. Hand-building
   the two independently would let it assert a state the response cannot produce — a key for a run
   no entry names — which is precisely what stopped being true when the map moved.

## 5. Gates

- [ ] 5.1 `pytest hub/tests/ -v` and `pytest tests/ -v`, under `py -3.11`, never bare `python`.
- [ ] 5.2 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`, `mypy src/`.
- [x] 5.3 `cd hub/ui && npm run lint && npm test`.
- [x] 5.4 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py`. Commit
      `hub/ui/src` and `hub/hub/static/ui` together so `/health` does not report `ui_stale`.

## 6. Drive it — the same measurements as phase 0, inverted

A passing suite is not proof of behaviour, and phase 0 exists to make this comparison possible.

- [ ] 6.1 Re-run 0.2 exactly: the evicting turns in other conversations, then reload conversation A.
      Terminal label and "Worked for Ns" both present. Record the numbers beside phase 0's.
- [ ] 6.2 Re-run 0.3 exactly: single conversation, every turn on screen labelled.
- [ ] 6.3 Re-run 0.4 exactly: with the conversation open, restart the Hub and record how long the
      interrupted turn takes to label itself **without** a reload. This is a **no-regression check,
      not a fix** — 0.4 should already have measured seconds, and the map move must not turn that
      into "never" by moving the facts onto a query the reconnect no longer refreshes. Record both
      numbers side by side. Then re-run 0.5, the pre-spawn failure: that one *is* a before/after,
      and 3.1 is what changes it.
- [ ] 6.4 The recent view — no conversation selected — labels its turns too. That branch of the
      ternary is untested by 6.1-6.3.
- [ ] 6.5 Measure the added query's cost on a conversation large enough to matter: response time for
      `GET /agent/{a}/chat/{cid}` before and after, on the same fixture. Record it rather than
      asserting it is negligible (design, Risks).
- [ ] 6.6 Teardown: no job left enabled, fixture project named in the write-up so the review page
      can cite it.
- [ ] 6.7 **The working indicator, live** (design D9). Stop a turn, then immediately send another
      message, and watch the indicator across the window between the run being committed and its
      first output row arriving. Today the timeline map covers that window; after this change a
      delivered queue entry is what covers it. Record what the operator sees, not what the fixture
      returns. Then do the negative half: with conversation A on screen, start a run in conversation
      B on the same agent and confirm A's indicator stays quiet — that is the narrowing D9 chose.

## 7. Close the ledger

- [ ] 7.1 Set F274's and F291's `**Status:**` lines in `scripts/drive/FINDINGS.md` to
      `fixed <sha>` and add the phase-6 numbers under each. F290 is already retracted and needs
      nothing.
- [ ] 7.2 Correct the ledger's severity-A summary lines (`FINDINGS.md:96-112`), which name F274 as
      open.
- [ ] 7.3 `openspec-sync-specs`, then `openspec-archive-change`. The MODIFIED requirement replaces
      the text at `openspec/specs/agent-stream-events/spec.md:299` in full, including the corrected
      cross-reference.
