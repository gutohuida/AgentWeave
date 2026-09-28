**Depends on:** `each-runner-cli-is-one-adapter` (slice 1: `RunnerAdapter`, `get_adapter`, the
RPC executor `_execute_rpc_run`; it does **not** define `compaction_percent`, which task 3.1 adds),
`a-copilot-agent-runs-over-acp` (slice 2: `copilot_acp.run_turn`, its raw-event subscription
constant, `parse_copilot_envelope`, the `copilot` literal and migration) and
`a-run-reaches-the-hub-without-mcp` (slice 3). Build after all three are archived and after the
2026-09-27 night queue. Test commands use `py -3.11`, never bare `python`. Run pytest from the repo
root.

## 0. Rounds

- [x] 0.1 R2: re-derive the design independently against the code **as it stands after slices 1–3
  and tonight's queue**. In particular: (a) slice 1's `usage_from` contract and whether it defines
  `compaction_percent` (Q1, D9); (b) slice 2's executor, whether it runs one process per run, whether
  it knows `session/new` vs `session/load`, whether its `initialize` subscribes to the four event
  types, and whether its run end applies the refusal branch of `_execute_run` (Q2, D8); (c) every
  file:line in design.md, especially `usage_accounting.py:61-96` after
  `an-estimate-that-misses-turns-says-so` lands, and `checkpoint_trigger.py:168-310`; (d) what
  `GET /agents` loads per agent (D11). Also: what does each route return when the function it calls
  raises? Record the result in design.md's round log
  - **Done 2026-09-28** against master `ef55e6f`. Slices 1–3 are unbuilt and 5 of the 28 night changes
    have landed, so (a) and (b) were answered from those slices' designs. 12 corrections, among them
    a credit double count (D4), a refused turn whose input would not have been returned (D8), the
    ledger's home (D2), where the token ceiling goes (D10), and a drive step that could not raise its
    banner (7.6). Q1, Q2 and Q8 are answered, and gaps G1–G6 are in the round log
- [x] 0.2 R3: a second, fresh re-derivation of D3 (the lower-bound argument), D4 (the baseline
  lookup) and D10 (the formulas and the token-mode ceiling), from the code and the acp4 numbers, not
  from R2's notes. `openspec validate a-copilot-run-shows-its-credits --strict` passes
  - **Done 2026-09-28** against master `fc33ff9`. The acp4 sums were recomputed and hold (33108 / 64 /
    21888 / 33172, and 275856000 nano-AIU from each call's `tokenDetails`). The corrections: D4 is
    now the larger of two lower bounds, correct whether the checkpoint continues after a load or not.
    D2's settle was keyed on a checkpoint total, which starved the fallback and the D8 reset fill. The
    D8 JSON-RPC-error route could not fire, because slice 2 raises. The token-mode notes point was
    missing. Plus a "Required of slices 1 and 2" section; details in the round log
- [ ] 0.3 Opus adversarial review of the change and its decisions (the operator's standing step
  before an APPROVED row). It re-derives in particular: whether any path adds a Copilot credit to a
  token total or to the budget; whether a Claude or Codex project's API responses and screens are
  byte-identical when no Copilot row exists; whether D8 can hold a queue on anything but the
  structured quota code

## 1. Tests first — each fails on today's code

- [ ] 1.1 New `hub/tests/test_copilot_usage.py`, fixture `acp4_events()` built from the acp4
  transcript in the order Copilot emitted it (three `assistant.usage`, then `session.usage_checkpoint`,
  then the prompt result `{inputTokens 33108, outputTokens 64, totalTokens 33172, thoughtTokens 0,
  cachedReadTokens 21888, cachedWriteTokens 0}`). With `session_was_new=True`, `finish()` gives input
  33108, output 64, total 33172, cache_read 21888, reasoning 0, model `mai-code-1.1-flash`,
  `ai_nano_aiu` 275856000, `premium_requests` 1.0, both session totals equal to those, and
  `source == "copilot_calls"` (the calls and the result tie at 33172; a tie goes to the calls, D3).
  Fails today
  (no module). `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`
- [ ] 1.2 Same file: the sum is not doubled. Total is 33172, not 66344, whichever of the calls or
  the prompt result the ledger saw first
- [ ] 1.3 Same file: dropped events (`session_was_new=True`). Only calls 1 and 3 observed (their sum
  is 22080 + 26 = 22106), plus the full prompt result, gives total 33172 and
  `source == "copilot_prompt_result"`, and logs one warning naming both figures. All three calls and
  no prompt result gives 33172 and `source == "copilot_calls"`
- [ ] 1.4 Same file: one ledger (one process) that observes two prompt results, 33172 and then a
  cumulative 40000, uses 40000, not their sum 73172 (design D3: the process-cumulative figure is the
  run's). Assert with the results in the order they were emitted, so a ledger that kept the earlier
  one fails
- [ ] 1.5 Same file: a subagent call (`parentToolCallId` set, `initiator: "sub-agent"`) is counted
  once; a repeated notification with the same `providerCallId` is counted once
- [ ] 1.6 Same file: a `session.compaction_complete` with `compactionTokensUsed` adds its tokens and
  nano-AIU when no call has `providerCallId == requestId`, and adds nothing when one does
- [ ] 1.7 Same file: two `session.usage_checkpoint` events (first 100000000/0, later 275856000/1) in
  emitted order: the later wins. Reversing their order fails this test
- [ ] 1.8 Same file, credits (D4, R3's larger-of rule). Each case runs through
  `settle_copilot_credits` with a seeded `turn_usage`/`runs` baseline. "One call of N" means one
  `assistant.usage` whose `copilotUsage.totalNanoAiu` is N. Each case's per-call sum is chosen so that
  a rule taking only the difference, or only the calls, fails it:
  - (a) loaded, baseline 275856000/1, checkpoint 400000000/2, one call of 124144000 gives 124144000
    and premium 1.0, and stores 400000000/2;
  - (b) loaded with no baseline, the acp4 calls (275856000), checkpoint 400000000/2 gives 275856000
    and `premium_requests is None`, and stores 400000000/2;
  - (c) counter reset: baseline 275856000/1, checkpoint 124144000/1, one call of 124144000 gives
    124144000 (not None, R2's rule), `premium_requests is None`, and stores 124144000/1;
  - (d) counter restarted per process: baseline 100000000/1, checkpoint 124144000/1, one call of
    124144000 gives 124144000, not the difference 24144000, and `premium_requests is None`;
  - (e) the fallback stores what it charged: a new-session run with the acp4 calls and no
    checkpoint records 275856000 and `session_nano_aiu_total == 275856000`,
    `session_premium_requests_total is None`. The following loaded run, checkpoint 400000000/2 and
    one call of 124144000, is charged 124144000 with `premium_requests is None`. This fails if the
    fallback stores nothing;
  - (f) a run whose sample has `credit_session_new` set but no checkpoint and no calls is settled
    (a no-op on credits) rather than skipped. A sample without `credit_session_new` is returned
    unchanged. No events at all gives `total_tokens is None`
- [ ] 1.9 Same file, quota (D7, D8): acp4's snapshots give reading `{"status": "allowed", "quota":
  "chat", "rateLimitType": "monthly", "resetsAt": 1790812800, "remainingPercentage": 96.5,
  "provider": "copilot"}`. (1790812800 is 2026-10-01T00:00:00Z; assert it with
  `datetime(2026,10,1,tzinfo=timezone.utc).timestamp()`.) Adding `session.error {errorType: "quota",
  errorCode: "quota_exceeded"}` gives `status "rejected"`, and `provider_allowance.allowance_refusal`
  of it is not None. `errorType "rate_limit"`, `errorCode "session_quota_exceeded"`,
  `"billing_not_configured"`, and `errorType "query"` with message `"quota exceeded"` each leave
  `status "allowed"`. A refused run with no snapshot and a `prior_reading` whose `resetsAt` is ahead
  uses it (`settle_copilot_credits` supplies it from a seeded `turn_usage` row, design D8). With one
  whose reset is past, `resetsAt` is absent. A replayed `session.usage_checkpoint` observed before
  the ledger is armed is ignored
- [ ] 1.10 Extend `hub/tests/test_accounting_api.py`: seed a Claude turn (1000 tokens, no credits)
  for agent `a-claude` and two Copilot turns (500 and 300 tokens; 200000000 and 75856000 nano-AIU;
  premium 1.0 and 0.5) for agent `b-copilot`. `GET /accounting` gives `project.total_tokens == 1800`,
  `project.ai_nano_aiu == 275856000`, `project.premium_requests == 1.5`, `budget.used_tokens == 1800`.
  `agents[0]` is `a-claude` with `ai_nano_aiu is None`, `agents[1]` is `b-copilot` with 275856000 (by
  position, in the route's name order). `recent_turns` in `observed_at` descending order carry their
  own `ai_nano_aiu`, asserted by position. Fails today
- [ ] 1.11 Same file: a project with only Claude rows returns `ai_nano_aiu: null` and
  `premium_requests: null` everywhere. `preferred_display` for a Claude allowance row is unchanged
  except for the new `runner: "claude"` key. For a newer Copilot allowance row it carries
  `runner: "copilot"`. `GET /accounting/conversations/{id}` sums a conversation's credits
- [ ] 1.12 Extend `hub/tests/test_checkpoint_policy.py`: `resolve_policy(None, None)` and
  `compaction_percent=95` give threshold 80, notes 70, final 92 (pins Claude). `compaction_percent=80`
  gives 65 / 55 / 77. A project percent threshold 80 with `compaction_percent=80` gives 77 and
  `threshold_source == "runner_ceiling"`, and a notes value of 78 becomes 67. A Claude percent
  threshold 95 with `compaction_percent=95` gives 92 (`runner_ceiling`; Q7). Token mode:
  `should_checkpoint` with tokens below the threshold is True at percent 92 under C=95 and False at
  percent 91. `crosses` itself is unchanged, since its signature has no policy.
  `needs_final_warning` at 77 is True under C=80 and False under C=95. Token-mode notes (R3): with
  C=80, a token threshold of 150000 and notes 140000, `should_request_notes` at 30000 tokens is False
  at percent 66 and True at percent 67, and False at percent 77 (the threshold ceiling). With no
  notes value it is False at 67. Fails today
- [ ] 1.13 Extend `hub/tests/test_checkpoint_cutover.py` (beside the offered-mode tests): an `offered`
  project, a `copilot` runner bound to agent `cop` and a `claude` runner bound to agent `cla`, both
  with no threshold of their own. A reading of 66% for `cop`'s conversation sets
  `checkpoint_warning == "due"` and broadcasts one `checkpoint_due` with `threshold_value == 65`. The
  same reading for `cla` changes nothing. Then a dismissed `cop` conversation at 78% gets
  `"final"`. Fails today
- [ ] 1.14 Extend `hub/tests/test_migrations.py`: upgrade to head adds the four `turn_usage` and two
  `worker_invocations` columns, nullable; downgrade removes them; a pre-existing `turn_usage` row
  survives with NULLs. Fails today
- [ ] 1.15 The run end, in two files.
  - (a) `hub/tests/test_copilot_acp_run_turn.py` (slice 2's scripted fake session): a session whose raw
    events include the quota refusal and whose `session/prompt` returns `stopReason: "end_turn"` yields
    `TurnOutcome.status == "failed"` and one `on_accounting` call carrying the rejected reading. This
    is design D8's case. A fixture that ends `failed` by construction could not catch it. R3 adds
    two more. First, a session whose `session/prompt` answers with a JSON-RPC error whose `data`
    carries `errorType "quota"` and `errorCode "quota_exceeded"`. Second, one whose process exits
    after the quota `session.error` and before the prompt returns. In both, `run_turn` **returns**
    the failed outcome and calls `on_accounting` once, where slice 2's client would raise. The same
    JSON-RPC error with `errorType "rate_limit"` still raises `CopilotACPError`.
  - (b) `hub/tests/test_a_refused_turn_holds_the_queue.py` gains an RPC case. It patches the Copilot
    transport's module-level `run_turn` (slice 1 D9's seam) to deliver that sample and a failed
    outcome. The run persists one `queue_agent_held` event. Its entries are returned, and the refusal
    is not counted as a delivery attempt. The job run is not finalised, and `provider_hold` names the
    reset. A run with `errorType "rate_limit"` persists no `queue_agent_held`, and a Codex RPC run's
    end is unchanged.

  Both fail today. (Rebase at IMPL: slices 1 and 2 unbuilt at R2)
- [ ] 1.16 UI, extend `hub/ui/src/__tests__/accountingPresentation.test.tsx`: `formatAiCredits(275856000)`
  is `0.28 AI credits`, `formatAiCredits(4000000)` is `<0.01 AI credits`, and `formatAiCredits(null)` is
  `null`. `accountingDisplayLabel` with a Copilot allowance `{status: 'allowed', rateLimitType:
  'monthly', resetsAt, remainingPercentage: 96.5}` and `runner: 'copilot'` starts `Copilot monthly
  allowance available`. The existing Claude label strings are unchanged
- [ ] 1.17 UI, extend `agentTimelineModel.test.ts`: `usageByRunId` returns `{tokens, nanoAiu}` per run
  and omits unavailable turns as `tokensByRunId` did. Extend `agentTimeline.test.tsx`: a turn with
  credits reads `… tokens · 0.28 AI credits`, and a turn without them reads exactly as today
- [ ] 1.18 UI: an `AccountingPanel` test renders the credits line only when `project.ai_nano_aiu` is
  not null. Extend `overviewBudgetSummary.test.tsx` to match. Extend `agentCheckpointSettings.test.tsx`:
  an agent with `checkpoint_compaction_percent: 80` shows the "compacts at about 80%" line, and one
  with 95 or null does not

## 2. Schema and sample

- [ ] 2.1 `db/models.py`: add the four `TurnUsage` columns and two `WorkerInvocation` columns (design
  D5). Leave `ck_turn_usage_availability` unchanged
- [ ] 2.2 The migration (next free number at build time): table guards as `0033`/`0034`,
  `batch_alter_table`, no backfill. Bump `HEAD_REVISION` (`hub/tests/test_migrations.py`) and the head
  assertion in `hub/tests/test_project_persistence.py`. `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`
- [ ] 2.3 `runner_events.AccountingSample`: add `ai_nano_aiu`, `premium_requests`,
  `session_nano_aiu_total`, `session_premium_requests_total` (Optional, default None) and the
  unpersisted `credit_session_new: Optional[bool]`, and carry all five in `merged` (R3: a merge that
  dropped the flag would turn the settle into a no-op). `usage_accounting.record_turn_usage` writes them whether or not the sample is measured

## 3. The compaction point and the thresholds

- [ ] 3.1 `RunnerAdapter.compaction_percent` (`ClassVar[Optional[int]]`, no base default) with
  Claude 95 and Codex 95, and 80 on slice 2's `CopilotAdapter` (design D9). Slice 1 reserves the
  member for this slice (its D16). Extend slice 1's conformance test so every `ADAPTERS` entry
  declares it. `grep -rn "compaction_percent" hub/hub/runner_adapters` shows all three. (Rebase at
  IMPL: `each-runner-cli-is-one-adapter` unbuilt at R2)
- [ ] 3.2 `checkpoint_policy.py`: D10's formulas, the two new `CheckpointPolicy` fields, the percent
  clamp, the notes clamp, the token-mode ceiling in `should_checkpoint` and in the threshold half of
  `should_request_notes` (not in `crosses`), and `needs_final_warning` reading the
  policy. Keep the three module constants at their C=95 values. Task 1.12 passes
- [ ] 3.3 `checkpoint_trigger.consider`: resolve the agent's runner (`Agent.runner_id` → `Runner` →
  adapter) and pass `compaction_percent`; the decline message names `policy.final_warning_percent`;
  both `checkpoint_due` payloads carry `threshold_source`. Task 1.13 passes.
  `py -3.11 -m pytest hub/tests/test_checkpoint_policy.py hub/tests/test_checkpoint_cutover.py -q`
- [ ] 3.4 `AgentSummary.checkpoint_compaction_percent` in `schemas/agents.py`, filled in
  `list_agents`'s `AgentSummary(...)` (`api/v1/agents.py:581-630`) from `bound_runner` (`:548`, taken
  from `runners_by_id`, `:405-407`) through `get_adapter`, null when there is none, with no new
  query

## 4. The ledger

- [ ] 4.1 Add `assistant.usage`, `session.usage_checkpoint` and `session.compaction_complete` to
  slice 2's subscription constant. Its design already lists `session.error`, leaves the first two to
  this slice, and includes none of the three. A test asserts that the `initialize` request carries all
  four. (Rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2)
- [ ] 4.2 `hub/hub/copilot_usage.py`: `CopilotUsageLedger` (`observe_event`, `observe_prompt_result`,
  `observe_prompt_error`, `finish`) per design D2–D4, and `quota_reading(snapshots, *, refused, prior_reading)` per D7–D8.
  `finish(*, session_was_new)` is pure and never raises (D11). Tasks 1.1–1.7 and the ledger half of
  1.9 pass. `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`
- [ ] 4.3 `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)`: the newest
  `turn_usage` row joined to `runs` on `Run.session_id == session_id`, for that project and agent, with
  `session_nano_aiu_total` not null. It returns None on any exception, logged. Also
  `usage_accounting.settle_copilot_credits(db, sample, *, project_id, agent, session_id)` (design D2,
  D4, D8): the larger of the baseline difference and the per-call sum, premium requests only when the
  difference was used, the fallback's stored total, and the prior reading's `resetsAt`. It acts on
  every sample whose `credit_session_new` is not None, checkpoint or not, returns any other sample
  unchanged, and never raises.
  Tasks 1.8 and the settle half of 1.9 pass
- [ ] 4.4 `copilot_acp.run_turn` (design D2; R2's answer to Q1 is that there is no adapter
  `usage_from`):
  - one ledger per call, armed when the `session/prompt` request is written;
  - every subscribed raw event and the prompt result go to the ledger;
  - `cb.on_accounting(ledger.finish(session_was_new=…))` is called exactly once on every return path
    after a session exists;
  - it returns `TurnOutcome(status="failed", …)` when the ledger recorded the quota refusal (D8);
  - once the prompt is written, an exception while waiting for it (a JSON-RPC error, whose `data`
    goes to `observe_prompt_error`, or the process ending) is turned into that failed outcome when
    the ledger has recognised the refusal, and is re-raised unchanged otherwise. This needs slice 2's
    `CopilotACPError` to carry `.data` (design, *Required of slices 1 and 2*, item 9).

  Task 1.15(a) passes. (Rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2)

## 5. The run end

- [ ] 5.1 `_execute_rpc_run` (slice 1's generic RPC executor): at run end, in the finalising session
  and before `record_turn_usage`, pass the merged sample through `settle_copilot_credits`, which acts
  on any sample whose `credit_session_new` is set (R3: not only one with a session credit total). Then record it with `runner=adapter.name`. The
  executor has no `"copilot"` literal. (Rebase at IMPL: slice 1 unbuilt at R2)
- [ ] 5.2 Log every `session.error` payload at warning level with its `errorType`, `errorCode` and
  `statusCode` (design D8, capture)
- [ ] 5.3 Apply `_execute_run`'s refusal branch (`api/v1/agent_trigger.py:2667-2743`) to
  `_execute_rpc_run`. Its Codex ancestor has none of it (`:3345-3362`), and slice 1's design does not
  unify the run end (R2). The branch is:
  - `hold_for_reading`, and `allowance_refusal` gated on `final_status == "failed"`, no binding
    conflict and a reset still ahead;
  - `finalize_job_run_for_conversation` skipped under a refusal;
  - `return_run_entries(..., refusal=)`;
  - after the commit, `arm_allowance_wake` and the `queue_agent_held` event.

  Task 1.15(b) passes. (Rebase at IMPL: slice 1 unbuilt at R2)
- [ ] 5.4 `WorkerUsage` gains `ai_nano_aiu` and `premium_requests`, and `run_worker` writes them into
  `WorkerInvocation(...)` (`worker.py:393-412`). Slice 2's `parse_copilot_envelope` reads
  `session.shutdown {totalNanoAiu, totalPremiumRequests}` into them **if** slice 2's task 1.2 capture
  of the `-p --output-format json` stream contains that event. The parser test uses that capture, not
  a hand-written line. If the capture has no `session.shutdown`, record that here and leave the
  columns NULL. (Rebase at IMPL: slices 1 and 2 unbuilt at R2)

## 6. API and UI

- [ ] 6.1 `usage_accounting`: `ai_nano_aiu` and `premium_requests` in `_aggregate_columns`,
  `_summary_from_row`, `recent_turns` and `conversation_usage`; `runner` on the allowance display.
  Tasks 1.10–1.11 pass. `py -3.11 -m pytest hub/tests/test_accounting_api.py hub/tests/test_accounting_budget.py hub/tests/test_provider_allowance.py -q`
- [ ] 6.2 `api/accounting.ts` types; `accountingDisplay.ts`: `NANO_AIU_PER_AI_CREDIT`,
  `formatAiCredits`, `monthly` period, provider name in the allowance label
- [ ] 6.3 `AccountingPanel.tsx`, `OverviewBudgetSummary.tsx`, `AgentOutputPanel.tsx` (conversation
  header), `agentTimelineModel.ts` (`usageByRunId`), `AgentTimeline.tsx`, `AgentSettingsControls.tsx`
  per design D6 and D10. Tasks 1.16–1.18 pass. `cd hub/ui && npm run lint && npx vitest run`
- [ ] 6.4 Only if `worker-spend-counts-against-the-budget` has already landed: each `workers` line
  gains `ai_nano_aiu` and `premium_requests` sums, with a test in its test file. Otherwise record here
  that it has not landed, so that change adds them when it lands (design D12)
- [ ] 6.5 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit
  `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 6.6 The CI set: `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`,
  `mypy src/`, `py -3.11 -m pytest hub/tests/ -q`, `py -3.11 -m pytest tests/ -q`

## 7. Drive

On the trial Hub `:8010`, started from `hub/` per `CLAUDE.md`:
`cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`.
Read its startup line to confirm the database. **Never touch `:8000`.** The account is **Copilot
Free**: Auto model only, a small monthly allowance. Keep prompts to one short sentence and the whole
drive to at most **four** model-calling turns. Record each figure verbatim in design.md's round log.

- [ ] 7.1 Bind a Copilot agent (slice 2's runner, model Auto) in the trial project. Send "Reply with
  the word OK." Read its `turn_usage` row (`mode=ro` SQLite read of the trial database). `total_tokens`
  equals the sum of the run's `assistant.usage` events in the run's log, and `ai_nano_aiu` and
  `session_nano_aiu_total` are set. `GET /accounting`: `budget.used_tokens` rose by exactly the
  tokens, and `project.ai_nano_aiu` equals the row's
- [ ] 7.2 In the app: the Budgets section shows the credits line and the agent chip, the Overview
  shows credits, the conversation header shows `… tokens · X AI credits`, and the turn's "Worked for"
  line shows the credits. A Claude agent's turn in the same project shows no credits
- [ ] 7.3 A second turn in the **same conversation** (a resumed session): its `ai_nano_aiu` equals its
  `session_nano_aiu_total` minus 7.1's. That answers whether the checkpoint total continues across
  `session/load` (design table, INFERRED until now). If it restarted from zero instead, D4's
  larger-of rule charges the per-call sum (R3). Record which it was and check that `ai_nano_aiu`
  equals the run's per-call sum. D4 needs no revision either way. Also record this resumed
  turn's prompt-result `usage` beside its per-call sum (Q10). If the result includes 7.1's tokens,
  stop and make the per-call sum authoritative on a loaded session (design D3)
- [ ] 7.4 Record the run's `quotaSnapshots` keys and which one's `usedRequests` rose. Record whether
  the ACP prompt result and the per-call sum agreed (the ledger's warning log line, if any)
- [ ] 7.5 Optional, only if 7.1–7.3 used little allowance: `/compact` in the same conversation (one
  compaction model call). Record whether an `assistant.usage` accompanied `session.compaction_complete`
  (same `providerCallId` as its `requestId`) and that the run's credits were counted once
- [ ] 7.6 Thresholds with no model call: with the project's checkpoint mode `offered`, post a synthetic
  66% reading for the Copilot agent's conversation through `POST /agents/{name}/context-usage`
  (`api/v1/agents.py:2980`), carrying that conversation's provider `session_id`, `status: "measured"`,
  `source`, `observed_at`, `context_tokens`, `limit_tokens` **and `percent: 66`**. The route does not
  derive `percent` when `limit_tokens` is present (`output_recording.py:139-140`), and without it no
  banner can appear (the route resolves the conversation from the session,
  `output_recording.py:173-189`, and hands the reading to `consider_from_reading`, `:233-238`). The conversation shows the checkpoint-due banner. The same
  reading for the Claude agent shows nothing. The Copilot agent's settings show the "compacts at
  about 80%" line
- [ ] 7.7 The hold, by fixture: quota exhaustion cannot be reached on Free. Replay 1.15's event
  sequence through the executor on `:8010` if slice 2 offers a replay seam, and read `GET /queue`
  status: it names the hold and the reset. If there is no seam, record that the hold is verified by
  task 1.15 only, and leave test-guide Human-only item 3 open

## 8. Archive

- [ ] 8.1 Sync the three delta specs into `openspec/specs/` (`openspec-sync-specs`), archive the
  change, and record slice 4 as done in the exploration's slice list
- [ ] 8.2 File a finding (or append to an open one) asking for the first real Copilot quota refusal's
  `session.error` payload, captured by task 5.2's log, so that D8's recognition is confirmed or
  corrected. Copy any answer to Q6 (month-long hold) into DECISIONS
