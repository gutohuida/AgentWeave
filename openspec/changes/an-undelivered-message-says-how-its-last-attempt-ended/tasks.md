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
- [ ] 0.3 The operator records D11/F291 and D11/F273 in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (Hub) New `hub/tests/test_an_undelivered_message_says_why.py`: seed an operator entry
      `withdrawn` with `abandoned_reason` and `delivered_in_run_id=R`, and `Run` R `failed` with
      `error="%1 is not a valid Win32 application."`. `GET` the conversation's chat route: `runs[R].error`
      equals that string. Record that it FAILS today (no `error` key)
- [ ] 1.2 (Hub) The same for the recent-chat route and for `GET /agents/{name}/timeline` with a
      `run_failed` event naming R. Record that both FAIL today
- [ ] 1.3 (Hub) A completed run's facts carry `error: null`. Control-ish: FAILS today only on the key's
      absence; assert the key is present and null
- [ ] 1.4 (Hub) An over-long `Run.error` (2,000 characters) is served fitted, and the route answers 200.
      Record that it FAILS today (no key)
- [ ] 1.5 (UI) `hub/ui/src/__tests__/agentTimeline.test.tsx`: a chat response **in the route's real
      order** — a delivered turn at t0 (run A, completed), the abandoned operator entry at t1 with
      `run_id: 'R'`, a delivered turn at t2 (run B, completed) — with `runs = {A, B, R: failed, error}`.
      The error text renders inside the abandoned message's block and in neither turn, and in DOM
      order A's text precedes the *Last attempt* line, which precedes B's text. Reversing the
      fixture's order (t2, t1, t0) must fail that order assertion, since `groupIntoTurns` preserves
      arrival order (F190 rule). Record that the forward case FAILS today (no error text anywhere)
- [ ] 1.6 (UI) An abandoned entry with `run_id: null` (the scheduler's give-up) renders the reason and
      no *Last attempt* line. Control, PASSES today
- [ ] 1.6b (UI) An abandoned entry whose run is `interrupted` renders exactly *Last attempt was
      interrupted*, and no text naming a Hub restart (design D2, operator review 2026-09-24). Record
      that it FAILS today (no line)
- [ ] 1.7 (UI) `hub/ui/src/__tests__/agentChat.test.tsx`: `eventTargetsAgent('queue_entry_abandoned',
      { agent: 'a' }, 'a')` is true. Record that it FAILS today
- [ ] 1.8 (Hub, F273 pin) Patch `record_agent_output` so the status-line write raises
      `OperationalError("database is locked")` on every attempt, for one run that completes
      (`test_a_turn_says_how_it_ended.py` has the fake-runner staging). The run reads `completed` with
      its exit code; a warning names the run; the chat response's `runs[run].status == 'completed'` and
      `exit_code` is set. Control, PASSES today and must keep passing. Add the same with a non-lock
      error: the run is still `completed`, not relabelled; an error log names the run

## 2. The fix

- [ ] 2.1 `hub/hub/schemas/agents.py`: `RunFacts.error` and its bound (design D1)
- [ ] 2.2 `hub/hub/api/v1/agent_chat.py:341`, `hub/hub/api/v1/agents.py:894`: fill it, fitted
- [ ] 2.3 `hub/ui/src/api/agents.ts`: `AgentRunFacts.error`; `hub/ui/src/api/agentChat.ts`:
      `queue_entry_abandoned` in `QUEUE_EVENT_TYPES`, and its comment; rewrite the comment above
      `RUN_TERMINAL_EVENT_TYPES` (`:311-315`) so it no longer says `run_interrupted` can never reach a
      live client (design D3; only the startup broadcast is unseen)
- [ ] 2.4 `hub/ui/src/components/agents/AgentTimeline.tsx`: the abandoned branch passes
      `runs[entry.run_id]`; `MessageEntry` renders design D2's line
- [ ] 2.5 `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.6 Run group 1; full `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm test -- --run`,
      counts inline
- [ ] 2.7 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui &&
      npm run lint`, clean

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`), reproduce F291's fixture (an agent whose pinned CLI
      is a text file, as F291's *Driven 2026-09-09* section does, through `POST /session/sync`). Send a
      message with the conversation open, touch nothing, and record what the served bundle shows after
      the third failure: the *not delivered* block with the Hub's reason and *Last attempt failed:
      %1 is not a valid Win32 application.*, live, without a reload
