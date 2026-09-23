## 0. Rounds and decision

- [ ] 0.1 R2: independent re-derivation of the six hold sites (`turn_scheduler.py:378-392`, `api/v1/inbound_queue.py:120-145`, `api/v1/jobs.py:1340-1357`, `scheduler.py:280-296,1005-1030,1128-1200`); note `jobs.py:1354` is also edited by `pressing-run-names-the-reason-that-held` — coordinate, `provider_allowance.py:140-215`, `agent_lifecycle.py`, `stop_agent_run`. Check design D2's claim that nothing else reads `provider_hold` (`grep -rn provider_hold hub/hub`)
- [ ] 0.2 R3: second independent re-derivation; `openspec validate an-agent-can-be-paused-and-keeps-its-input --strict` passes
- [ ] 0.3 The operator answers F15 (queue-and-keep / refuse / no pause); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — new file `hub/tests/test_an_agent_can_be_paused.py`

- [ ] 1.1 Pause an idle agent (with `bind_runner`, spawn stubbed as `_no_spawn` does), then `POST /agent/trigger` it: 200 `queued`, `waiting_reason` contains `is paused`; no `Run` row. FAILS today (404 on the pause route)
- [ ] 1.2 Peer message to a paused agent (`POST /agent-actions/messages` with a run credential): accepted; the entry stays `queued` with `delivery_attempts == 0` after three `schedule_agent` passes. FAILS today
- [ ] 1.3 Operator message to a paused agent: also waits (no probe). FAILS today
- [ ] 1.4 Resume: entries delivered in `sequence` order (assert on the real order the queue returns). FAILS today
- [ ] 1.5 `pause` with `stop_running: true` on an agent with a live run (seeded `Run` + a patched PTY stop, as `test_agent_trigger.py`'s stop tests do): `paused_at` set before the stop is called (assert via a stop stub that reads the row), and no new run starts when the stopped run's end schedules the queue. FAILS today
- [ ] 1.6 A flow with two agents, one paused: `_agents_that_are_free` omits it; the flow fires to the other. FAILS today
- [ ] 1.7 A loop whose agent is paused: pressing Run answers 409 with `is paused`; no entry queued. FAILS today
- [ ] 1.8 `GET /queue/{agent}/status` names the pause. FAILS today
- [ ] 1.9 Agent-plane credential calling `/agents/{name}/pause`: refused (not in the allowlist). Control once the route exists
- [ ] 1.10 `resume` with `schedule_agent` patched to raise: 200, `paused_at` cleared. FAILS today

## 2. The fix

- [ ] 2.1 `Agent.paused_at` + migration (nullable UTC datetime; head bumps)
- [ ] 2.2 `agent_hold` (design D2) and its two kinds; sentences for each
- [ ] 2.3 Point the six sites at `agent_hold`; `agents_held` includes paused agents; `operator_would_probe` applies only to the provider kind
- [ ] 2.4 `pause` / `resume` routes (design D3); `paused_at` on `AgentSummary`
- [ ] 2.5 UI: Pause/Resume beside Stop (`AgentOutputPanel.tsx:~827` is where Stop is issued), "Paused" on the roster row; vitest for both; `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Verify

- [ ] 3.1 Group 1 passes; full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Drive F15's scenario on a trial Hub with two Haiku agents: `critic` messages `builder` while `builder` runs; pause+stop `builder`; confirm no new `builder` run for two minutes; resume; confirm the queued message is delivered. Record run ids
- [ ] 3.3 Sync the delta and archive
