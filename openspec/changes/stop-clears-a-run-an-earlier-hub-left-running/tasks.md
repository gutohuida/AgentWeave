## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`; the UI's Stop does settle on
      `run_interrupted`: `useSSE.ts:474-487` invalidates the agents query for it, and
      `AgentOutputPanel.tsx:315` clears the stopping state once the agent no longer reads `running`): an independent re-derivation against `hub/hub/api/v1/agent_trigger.py` (`stop_agent_run`,
      `trigger_agent_directly`'s running guard, every writer of `Run` rows), `hub/hub/run_reconciliation.py`,
      `hub/hub/run_liveness.py`, `hub/hub/turn_scheduler.py` (`_attempt_turn`) and `hub/hub/pty_runner.py`
      (`pid_alive`, `terminate_process_tree`). Check in particular: is `trigger_agent_directly` really
      the only creator of `Run` rows (grep `Run(`)? Does the UI's Stop (`AgentOutputPanel.tsx:822-840`)
      settle on `run_interrupted` as it does on `run_stopped`? Record in `spec-queue/tracks/B2.md`
- [ ] 0.2 R3: a second independent re-derivation, not starting from R2's notes. `openspec validate
      stop-clears-a-run-an-earlier-hub-left-running --strict` passes
- [ ] 0.3 The operator records D11/F168 in `spec-queue/DECISIONS.md` and answers design Open
      Question 1

## 1. Tests first — each must fail on today's code unless marked as a control

New file `hub/tests/test_stop_clears_a_run_an_earlier_hub_left.py`. Seed `Run` rows directly, as
`test_run_reconciliation.py` does. Monkeypatch `run_liveness.PROCESS_STARTED_AT` to a fixed instant
and seed `started_at` either side of it.

- [ ] 1.1 A `running` run, `started_at` before boot, `pid=None`, a job or operator entry `delivered`
      in it. `POST /agent/{agent}/stop` answers **200** `status: "interrupted"`; the run is
      `interrupted` with `ended_at`; the entry is `queued`; a `run_interrupted` event is persisted.
      Record that it FAILS today (409)
- [ ] 1.2 Before Stop, with 1.1's seed and a runner bound, `POST /agent/trigger` answers 200
      `queued` (it does today: R2). After Stop, the queued input is delivered: a new `Run` starts on
      the agent, with no Hub restart. Record that the second half FAILS today (the input waits
      behind the stale row)
- [ ] 1.3 The surviving process: spawn a real sleeper (`subprocess.Popen([sys.executable, "-c",
      "import time; time.sleep(60)"])`), seed its pid. Stop answers 200, and the sleeper has exited
      (`poll()` is not `None` within a few seconds). Record that it FAILS today (409, sleeper alive).
      Always kill the sleeper in a `finally`
- [ ] 1.4 Terminate raises: patch `terminate_process_tree` to raise and `pid_alive` to answer True.
      Stop answers **409** naming the pid; the run is still `running`. Record that it FAILS today
      (409 but the old sentence; assert on the new sentence)
- [ ] 1.5 Reconciliation raises: patch `reconcile_run` to raise. Stop answers **500** naming the run;
      the run is still `running`. Record that it FAILS today (the function does not exist)
- [ ] 1.6 Control, PASSES today and must keep passing: a `running` run with `started_at` **after**
      boot and no registry handle answers 409 *"not in a stoppable state right now"*
- [ ] 1.7 Control, PASSES today and must keep passing: every test in `test_run_reconciliation.py`,
      including `:132` (`test_run_with_live_pid_is_left_running`), which pins the startup skip this
      change deliberately does not touch
- [ ] 1.8 The busy reasons: with 1.1's seed, `POST /agent/trigger` answers 200 `queued` whose
      `waiting_reason` contains `earlier Hub` and `Stop`; `schedule_agent` returns the same
      `waiting_reason` with `terminal_failure=False`; `GET /queue/{agent}/status` states it too.
      Record that all three FAIL today (`agent is already running`)
- [ ] 1.9 Stop's commit raises after `reconcile_run` staged its event: no `run_interrupted` frame is
      broadcast (capture `sse_manager.broadcast`), and the run reads `running`. Record that it FAILS
      today (the function does not exist; the startup loop broadcasts before its commit)

## 2. The fix

- [ ] 2.1 `hub/hub/run_liveness.py`: `PROCESS_STARTED_AT`, and `started_by_an_earlier_process(run)`
- [ ] 2.2 `hub/hub/run_reconciliation.py`: extract `reconcile_run` (design D1); `reconcile_interrupted_runs`
      calls it with no change in effect (1.7 is the check)
- [ ] 2.3 `hub/hub/api/v1/agent_trigger.py` `stop_agent_run`: design D2 and D4
- [ ] 2.4 Design D3's sentence, from one helper, at `turn_scheduler.py:325-331`,
      `api/v1/inbound_queue.py:128-129` and `agent_trigger.py:747-754`
- [ ] 2.5 Run group 1; full `py -3.11 -m pytest hub/tests/ -q`, count inline; any moved assertion is
      named and explained
- [ ] 2.6 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, clean

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (fresh port and profile; never `:8000`): start a long Haiku turn,
      kill the Hub's own process only (not the tree: on Windows `taskkill /PID <hub> /F` without
      `/T`), confirm the agent's process survives, start the Hub again. Confirm the roster shows the
      agent busy and a new message waits with the new reason. Press Stop in the conversation header:
      the agent's process ends, the run reads *Turn interrupted*, and the waiting message is delivered.
      Record each step's answer verbatim
