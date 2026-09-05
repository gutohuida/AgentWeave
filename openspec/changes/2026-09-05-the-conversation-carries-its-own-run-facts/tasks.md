## 0. Observe it before building — a gate, not a preamble

F274 was measured on 2026-09-03 and **did not reproduce** on the 2026-09-05 drive at nine runs
across six conversations, because those runs were short and the cap is on events rather than turns.
So the first thing to establish is that the defect is still live on this checkout, at a volume you
choose deliberately. **If phase 0 has not been recorded, do phase 0 and stop.**

- [ ] 0.1 Trial Hub on **8011** — never `proj-5e960453` or `proj-18e5d4e0`, never port 8000 — from
      `hub/` with uvicorn from source, against a fresh fixture project. Every real agent turn binds
      `claude-haiku-4-5`. Confirm no `.py` under `hub/hub` or `src` is newer than the process start.
- [ ] 0.2 **The headline, cross-conversation.** In conversation A, run a turn and stop it; confirm
      `GET /agents/{a}/timeline` has its run in `runs` and the served bundle shows the terminal
      label and the "Worked for Ns" line. Then drive turns in **other** conversations on the same
      agent until `len(timeline.events) == 50` and A's run id is no longer a key in `runs`. Reload
      A in the browser and record: turn boundaries, terminal-label occurrences, stat lines.
      **Count events, not turns** — a short turn contributes fewer events, which is why the
      2026-09-05 drive missed this.
- [ ] 0.3 **The headline, single-conversation.** Same agent, one conversation, enough turns that the
      chat response names more distinct runs than the timeline's fifty events do. Record
      `distinct run ids in chat` vs `len(runs)` vs `terminal labels on screen`. This is the half
      that proves no widening of the event window fixes it.
- [ ] 0.4 **The live half (D4).** With conversation A open in the browser, restart the Hub so
      `reconcile_interrupted_runs` writes `interrupted` for A's running run. Record how long the
      turn stays unlabelled with nobody touching the page, and confirm it labels itself on reload.
      That measurement is what the new invalidation has to change.
- [ ] 0.5 Record run ids, conversation ids, event counts and timestamps in
      `scripts/drive/FINDINGS.md` under F274.

## 1. The chat responses carry their own run facts

- [ ] 1.1 `ChatHistoryResponse` (`hub/hub/api/v1/agent_chat.py:173`) gains
      `runs: Dict[str, RunFacts] = Field(default_factory=dict)`, importing `RunFacts` from
      `hub.schemas.agents` rather than declaring a second shape (design D7).
- [ ] 1.2 One helper in `agent_chat.py` — `_run_facts_for(session, project_id, entries)` — that
      collects `entry.run_id` over the entries handed to it, returns `{}` on an empty set, and
      otherwise runs `select(Run).where(Run.project_id == project_id, Run.id.in_(run_ids))` with no
      `ORDER BY` and no `LIMIT`. Carry the `project_id` predicate and the comment saying it is
      enforcement rather than inference (design D2).
- [ ] 1.3 `get_chat_history` (`:567`) calls it on the **final** `entries` list — after the sort and
      after `_queued_entries_for` extends it (`:633-635`) — and returns the map.
- [ ] 1.4 `get_recent_chat` (`:646`) calls it on **its** final list — after `entries[-limit:]`
      (`:697`) and after `_queued_entries_for` — so the map matches what that response returns and
      not what it read (design D3).
- [ ] 1.5 The status rename is the boundary's, once: `RunFacts` is constructed exactly as
      `agents.py:830-841` does, `running` spelled `started`, `outside_workspace_writes` passed
      through with no default. If both routes now build `RunFacts` the same way, factor the
      construction rather than copying it — one boundary rename, one place.

## 2. The client reads the facts from the response that carries the turns

- [ ] 2.1 `hub/ui/src/api/agentChat.ts`: `ChatHistoryResponse` gains
      `runs: Record<string, AgentRunFacts>`, importing `AgentRunFacts` from `./agents`.
- [ ] 2.2 `AgentOutputPanel.tsx:333`: `runFacts` comes from `chat.data?.runs ?? {}` and no longer
      from `timeline?.runs`. Check whether `useAgentTimeline` is still called in this component for
      anything else — as of this proposal it is not (`:332-333` is its only use) — and remove the
      call if it has become dead. **Do not remove the timeline route's map** (design D5).
- [ ] 2.3 `AgentTimeline.tsx`'s `runs` prop comment currently reads *"straight from the timeline
      route"*. Rewrite it to name the chat response and to say why: the map must be keyed to the
      same query as `entries`, and the timeline route's map is scoped to a different window. Keep
      the existing "a caller with nothing to say must say `{}`" rule.

## 3. The invalidation moves with the map

- [ ] 3.1 `agentChat.ts`: `eventTargetsAgent` (`:284`) also returns true for `run_completed`,
      `run_failed`, `run_stopped` and `run_interrupted` when `data.agent` matches — deliberately
      **not** `run_started` (design D4). Comment the divergence from `eventBelongsToTimeline` at the
      site, including the `interrupted`-writes-no-output-row reason.
- [ ] 3.2 Confirm the four events actually carry `agent` in their SSE payload before relying on it —
      `eventBelongsToTimeline` reads `d.agent === name` for exactly these, so this is a check that
      the existing reader is right, not an assumption inherited from it.
- [ ] 3.3 Both hooks share `eventTargetsAgent`, so 3.1 covers the recent view too. Verify that is
      still true rather than assuming it.

## 4. Tests — each one mutation-checked

Every test below must be shown to fail against the unfixed code. A test that passes both ways is
not evidence, and this repository's dominant failure mode is exactly that.

- [ ] 4.1 `hub/tests/` — a conversation's chat response carries facts for every run its entries
      name. Mutation: return `{}` and watch it fail.
- [ ] 4.2 The one that would have caught F274: build an agent with **one** conversation holding a
      finished run, then enough events on **other** conversations to exceed any fixed window, and
      assert the first conversation's response still carries that run. Assert on the chat response
      alone — a test that also reads the timeline route will pass for the wrong reason.
- [ ] 4.3 Single-conversation volume: more distinct runs in one conversation than a fifty-event
      window can name, every one present in the map.
- [ ] 4.4 The recent-chat route carries facts for the runs **it** returns, taken after its `limit`
      truncation — construct a case where a pre-truncation entry names a run the post-truncation
      entries do not, and assert that run is absent. This is what pins "after, not before".
- [ ] 4.5 An entry naming a run with no row leaves the key absent rather than raising.
- [ ] 4.6 `hub/tests/test_bola.py` — both chat routes' `runs` maps cannot carry another project's
      run. Mutation: drop the `project_id` predicate.
- [ ] 4.7 `hub/ui/src/__tests__/` — the panel passes the **chat** response's `runs` to
      `AgentTimeline`. Mutation: wire it back to the timeline query and watch it fail. This is D5's
      guard and the reason the two maps may coexist.
- [ ] 4.8 `hub/ui/src/__tests__/` — `eventTargetsAgent` returns true for the four terminal run
      events and false for `run_started`. Mutation both directions.

## 5. Gates

- [ ] 5.1 `pytest hub/tests/ -v` and `pytest tests/ -v`, under `py -3.11`, never bare `python`.
- [ ] 5.2 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`, `mypy src/`.
- [ ] 5.3 `cd hub/ui && npm run lint && npm test`.
- [ ] 5.4 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py`. Commit
      `hub/ui/src` and `hub/hub/static/ui` together so `/health` does not report `ui_stale`.

## 6. Drive it — the same measurements as phase 0, inverted

A passing suite is not proof of behaviour, and phase 0 exists to make this comparison possible.

- [ ] 6.1 Re-run 0.2 exactly: the evicting turns in other conversations, then reload conversation A.
      Terminal label and "Worked for Ns" both present. Record the numbers beside phase 0's.
- [ ] 6.2 Re-run 0.3 exactly: single conversation, every turn on screen labelled.
- [ ] 6.3 Re-run 0.4 exactly: with the conversation open, restart the Hub and record how long the
      interrupted turn takes to label itself **without** a reload. Phase 0's answer was "never".
- [ ] 6.4 The recent view — no conversation selected — labels its turns too. That branch of the
      ternary is untested by 6.1-6.3.
- [ ] 6.5 Measure the added query's cost on a conversation large enough to matter: response time for
      `GET /agent/{a}/chat/{cid}` before and after, on the same fixture. Record it rather than
      asserting it is negligible (design, Risks).
- [ ] 6.6 Teardown: no job left enabled, fixture project named in the write-up so the review page
      can cite it.

## 7. Close the ledger

- [ ] 7.1 Set F274's `**Status:**` line in `scripts/drive/FINDINGS.md` to `fixed <sha>` and add the
      phase-6 numbers under it.
- [ ] 7.2 Correct the ledger's severity-A summary lines (`FINDINGS.md:96-112`), which name F274 as
      open.
- [ ] 7.3 `openspec-sync-specs`, then `openspec-archive-change`. The MODIFIED requirement replaces
      the text at `openspec/specs/agent-stream-events/spec.md:299` in full, including the corrected
      cross-reference.
