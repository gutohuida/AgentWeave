## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation against `hub/hub/api/v1/agent_chat.py` (both chat routes'
      assembly order, `_queued_entries_for`, `_run_facts_for`), `hub/hub/api/v1/agents.py` (the
      timeline's run facts), `hub/hub/schemas/agents.py` (`RunFacts`), `hub/hub/api/v1/agent_trigger.py`
      (every write of `Run.error`; the status-line write and what happens when it raises),
      `hub/ui/src/lib/agentTimelineModel.ts`, `hub/ui/src/components/agents/AgentTimeline.tsx` and
      `hub/ui/src/api/agentChat.ts`. Check in particular that F273's premise is obsolete as design D4
      says: a run's facts carry `exit_code` from the row on both transports. Record in
      `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent re-derivation. `openspec validate
      an-undelivered-message-says-how-its-last-attempt-ended --strict` passes. `RunFacts`' two constructions, the unredacted `run_failed.error` (`agent_trigger.py:1837`) and `QUEUE_EVENT_TYPES` confirmed; no change
- [x] 0.3 The operator records D11/F291 and D11/F273 in `spec-queue/DECISIONS.md` — recorded
      2026-09-29 (night window iteration): both were already resolved by the operator's Opus
      adversarial review on 2026-09-24 (design.md's "Operator review" section, APPROVE WITH FIXES);
      this records that outcome rather than opening a new question.

## 1. Tests first — each must fail on today's code unless marked as a control

- [x] 1.1 (Hub) New `hub/tests/test_an_undelivered_message_says_why.py`: seed an operator entry
      `withdrawn` with `abandoned_reason` and `delivered_in_run_id=R`, and `Run` R `failed` with
      `error="%1 is not a valid Win32 application."`. `GET` the conversation's chat route: `runs[R].error`
      equals that string. Confirmed FAILS pre-2.1/2.2 (no `error` key); passes now
      (`test_the_chat_route_carries_the_last_attempts_error`)
- [x] 1.2 (Hub) The same for the recent-chat route and for `GET /agents/{name}/timeline` with a
      `run_failed` event naming R. Confirmed both FAILED pre-fix; both pass now
      (`test_the_recent_chat_route_carries_the_last_attempts_error`,
      `test_the_timeline_route_carries_the_last_attempts_error`)
- [x] 1.3 (Hub) A completed run's facts carry `error: null`. Asserts the key is present and null
      (`test_a_completed_runs_facts_carry_no_error`)
- [x] 1.4 (Hub) An over-long `Run.error` (2,000 characters) is served fitted, and the route answers 200
      (`test_an_over_long_error_is_served_fitted_not_a_500`)
- [x] 1.5 (UI) `hub/ui/src/__tests__/agentTimeline.test.tsx`: a chat response **in the route's real
      order** — a delivered turn at t0 (run A, completed), the abandoned operator entry at t1 with
      `run_id: 'R'`, a delivered turn at t2 (run B, completed) — with `runs = {A, B, R: failed, error}`.
      The error text renders inside the abandoned message's block and in neither turn, and in DOM
      order A's text precedes the *Last attempt* line, which precedes B's text
      (`says how the last attempt ended beneath an abandoned message...`). Reversing the fixture's
      order is its own test and fails the same ordering check
      (`reversing the fixture order breaks the DOM-order assertion (F190 rule)`)
- [x] 1.6 (UI) An abandoned entry with `run_id: null` (the scheduler's give-up) renders the reason and
      no *Last attempt* line. Control, still passes
      (`names no attempt on an abandoned entry with no run...`)
- [x] 1.6b (UI) An abandoned entry whose run is `interrupted` renders exactly *Last attempt was
      interrupted*, and no text naming a Hub restart (design D2, operator review 2026-09-24)
      (`says only that the last attempt was interrupted, naming no cause`)
- [x] 1.7 (UI) `hub/ui/src/__tests__/agentChat.test.tsx`: `eventTargetsAgent('queue_entry_abandoned',
      { agent: 'a' }, 'a')` is true (`matches queue_entry_abandoned, so a give-up without a run
      reaches an open conversation`)
- [x] 1.8 (Hub, F273 pin) Patch `record_agent_output` so the status-line write raises
      `OperationalError("database is locked")` on every attempt, for one run that completes
      (`test_a_turn_says_how_it_ended.py` has the fake-runner staging). The run reads `completed` with
      its exit code; a warning names the run; the chat response's `runs[run].status == 'completed'` and
      `exit_code` is set. Control, still passes
      (`test_a_status_line_that_cannot_be_written_leaves_a_lock_the_outcome_intact`). Added the same
      with a non-lock error: the run is still `completed`, not relabelled; an error log names the run
      (`test_a_status_line_write_that_raises_a_non_lock_error_also_leaves_the_outcome_intact`)

## 2. The fix

- [x] 2.1 `hub/hub/schemas/agents.py`: `RunFacts.error` and its bound (design D1) — `RUN_FACTS_ERROR_CHARS`
      and `fit_run_error`
- [x] 2.2 `hub/hub/api/v1/agent_chat.py:341`, `hub/hub/api/v1/agents.py:894`: fill it, fitted
- [x] 2.3 `hub/ui/src/api/agents.ts`: `AgentRunFacts.error`; `hub/ui/src/api/agentChat.ts`:
      `queue_entry_abandoned` in `QUEUE_EVENT_TYPES`, and its comment; rewrite the comment above
      `RUN_TERMINAL_EVENT_TYPES` (`:311-315`) so it no longer says `run_interrupted` can never reach a
      live client (design D3; only the startup broadcast is unseen)
- [x] 2.4 `hub/ui/src/components/agents/AgentTimeline.tsx`: the abandoned branch passes
      `runs[entry.run_id]`; `MessageEntry` renders design D2's line
- [x] 2.5 `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together
- [x] 2.6 Run group 1; full `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm test -- --run`,
      counts inline — see the night log for the exact numbers at this change's sha
- [x] 2.7 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui &&
      npm run lint`, clean

## 3. Drive it

- [x] 3.1 Driven 2026-09-29 (night window) on the trial Hub (`:8010`, from source, this checkout).
      Reproduced F291's fixture: agent `f291drive` roster-synced through `POST /session/sync` with
      `{"runner": "native", "cli": "C:\Users\huida\aw-f291drive\README.md"}`, a runner-agent-
      charter-separation-era addition over the 2026-09-09 recipe — since that change, triggering
      needs a bound `Runner` row too (`agent_trigger.py:729`, `runner_id is None` refuses
      unconditionally before the pinned-CLI probe is even consulted), so a `Runner{cli: "claude"}`
      was created and bound; the session-synced `cli` override survives that bind
      (`get_agent_config` only overwrites `runner`/`model` from the bound Runner, `launchability.py
      :521-525`). Sent a message with the conversation open in a real Chromium tab (Playwright,
      `scripts/drive/d0929_f291_last_attempt_error.py`) and touched nothing: three delivery
      attempts failed inside a second (WinError 193), the entry reached `abandoned`, and within 7s
      — no reload — the served bundle showed *NOT DELIVERED / delivery failed 3 times; the Hub
      stopped retrying* followed by *Last attempt failed: %1 is not a valid Win32 application.*
      Repeated for a second and third message in the same conversation; all three blocks carried
      the line. `GET .../agent/f291drive/chat` confirmed the server side: `runs[R].error` held the
      same string for both abandoned entries. Fixture agent, runner and a stray `README.md`
      removed afterward; the trial Hub's roster was restored to its prior state (see the night log
      for the `session/sync`-is-a-full-roster-replace mistake made and corrected during this
      drive) and the process stopped.
