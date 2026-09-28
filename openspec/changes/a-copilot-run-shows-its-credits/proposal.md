# Proposal — a Copilot run shows its credits

**Depends on:** the `RunnerAdapter` of `each-runner-cli-is-one-adapter` (slice 1): `get_adapter`,
`parse_one_shot`, and the generic RPC executor `_execute_rpc_run`. This change **adds** the adapter
member **`compaction_percent`**, which slice 1 reserves for this slice without defining it (its D16;
design D9 here). The per-event `spend_from`/`quota_hold_from` that slice 1 also reserves are
replaced by a per-run ledger (design D2). It also depends on `a-copilot-agent-runs-over-acp` (slice
2): `copilot_acp.run_turn`, which owns the ledger, its raw-event subscription constant, its Copilot
one-shot envelope parser and its migration widening `ck_runners_cli`. It lands after the 2026-09-27
night queue (DECISIONS `ghcp-d5-order`) and after slices 2 and 3. At R2 (2026-09-28) slices 1–3 were
designs, not code, and 5 of the night's 28 changes had landed (design, round log).

R1, 2026-09-27. Slice 4 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. It
carries out decision **`ghcp-d3-credits`**: *tokens stay the accounting unit; AI credits (`nanoAiu`)
and premium requests are recorded and shown beside them, and do not drive the budget.*

## Why

A Copilot run on slices 1–3 alone would be accounted wrongly in three ways, and its conversations
would lose their context without the Hub acting first.

1. **Its tokens would be double counted or lost.** Copilot reports usage twice. Each model call
   emits a raw `assistant.usage` event. The ACP `session/prompt` result carries a `usage` that is
   **cumulative for the session in that process**, not for the prompt (appendix A §A, VERIFIED-LOCAL).
   The accumulator the Hub uses today, `AccountingSample.merged`, overlays the newest non-null field
   (`hub/hub/runner_events.py:302-318`). Fed per-call events, it keeps only the last call. Fed the
   prompt result of a second prompt in one process, it charges this turn with the first prompt's
   tokens too.
2. **Its spend would be invisible.** Copilot bills in AI credits, not dollars. Nothing in
   `turn_usage` can hold a credit (`hub/hub/db/models.py:1258-1298`). The only money column,
   `api_equivalent_usd_micros`, means "API-equivalent estimate", and
   `usage-accounting` forbids inventing money (*"MUST NOT invent a monetary figure"*).
3. **A spent Copilot allowance would hammer the queue.** Only the Claude parser produces an
   allowance reading (`hub/hub/runner_parsing.py:364-369`). `allowance_refusal` needs
   `status == "rejected"` and a numeric `resetsAt` (`hub/hub/provider_allowance.py:60-80`). A Copilot
   quota refusal would be counted like any failure and retried into the same exhausted plan, which
   is F355's defect for a new runner.
4. **Copilot compacts before the Hub checkpoints.** Copilot auto-compacts at about **80%** of the
   window and blocks at about 95% (docs `context-management`, DOCUMENTED). The Hub's built-in
   threshold is **80%** and its final warning **92%**, both chosen against Claude's ~95%
   (`hub/hub/checkpoint_policy.py:24-38`). On a Copilot agent the checkpoint and the compaction
   race at the same reading, and the final warning can never fire before the loss it announces.

## What R1 measured today that shapes the design

- **The per-call events sum exactly to Copilot's own totals** (acp4 transcript, VERIFIED-LOCAL). Three
  `assistant.usage` events: input 10988 + 11028 + 11092 = **33108**, output 21 + 38 + 5 = **64**,
  cache read 0 + 10880 + 11008 = **21888**. The prompt result read `inputTokens 33108, outputTokens
  64, totalTokens 33172, cachedReadTokens 21888`. Input **includes** cache reads (call 2: 148 fresh +
  10880 cached = 11028).
- **Each call carries its own credit cost.** `assistant.usage.copilotUsage.totalNanoAiu` was
  222 280 000 + 29 280 000 + 24 296 000 = **275 856 000**, equal to `session.usage_checkpoint.totalNanoAiu`.
- **Each call carries the plan's quota.** `assistant.usage.quotaSnapshots.chat` read
  `entitlementRequests 200, usedRequests 7, remainingPercentage 96.6 (96.5 on the later two calls), resetDate "2026-10-01T00:00:00Z"`.
- **A quota refusal has a structured shape.** The 1.0.88 package's own event schema
  (`schemas/session-events.schema.json`, VERIFIED by reading the shipped file; never observed live)
  gives `session.error` an `errorType` (`"quota"`, `"rate_limit"`, …) and an `errorCode` (`"quota_exceeded"`,
  `"session_quota_exceeded"`, `"billing_not_configured"` for quota).
- **The ACP cumulative counter does not survive a process restart.** R1 restarted `copilot.exe`,
  `session/load`ed the acp4 session, and sent `/usage` (no model call). The prompt result carried
  **no `usage` at all**, while `/usage` in the original process had returned the cumulative totals
  (VERIFIED-LOCAL). The session's *credit* ledger does persist: the schema calls
  `session.usage_checkpoint` *"durable session usage checkpoint for reconstructing aggregate
  accounting on resume"*.

## What changes

- **One ledger per Copilot run** (`hub/hub/copilot_usage.py`, new) turns the raw events and the
  prompt result into the one `AccountingSample` the run records. Tokens are summed from
  `assistant.usage`, including subagent calls, once each. The prompt result is cumulative per process,
  and slice 2 runs one process per turn, so it is the run's own figure. It is the cross-check, and the
  larger of the two lower bounds wins (design D3). Nothing is added twice.
- **Credits and premium requests are recorded per run.** Four nullable columns on `turn_usage`:
  this run's `ai_nano_aiu` and `premium_requests`, and the session totals the run ended at, which are
  the next run's baseline. A run's credits are the larger of its session-total difference and its
  own per-call credit sum, so a counter that restarts or resets never under- or double-charges
  (design D4, D5). Two on `worker_invocations` for Copilot one-shot calls.
  One migration.
- **They are shown, never budgeted, never converted to money** (D3 of the operator; design D6). The
  Budgets section, the Overview, a conversation's header and each turn's "Worked for" line show
  *AI credits* beside tokens. `budget.used_tokens` stays tokens only. `api_equivalent_usd_micros`
  stays NULL for a Copilot turn.
- **A Copilot quota refusal holds the queue like Claude's.** Recognised only from the structured
  `session.error` `errorType: "quota"` with `errorCode: "quota_exceeded"`, never from message text.
  The reset instant comes from the newest `quotaSnapshots` reading (`resetDate`). The ledger writes
  the same allowance reading shape the hold already reads, so `provider_allowance.py` is unchanged.
  A refused turn ends `failed` whatever Copilot's stop reason. When the prompt is answered by an
  error response, which slice 2's client would raise, it returns instead. Either way its input goes
  back to the queue uncounted, and the RPC executor gains the refusal branch that only the stream executor has today
  (design D7, D8).
- **Checkpoint thresholds follow the runner's compaction point.** The adapter declares
  `compaction_percent` (Claude 95, Codex 95, Copilot 80). The built-in threshold, notes point and
  final warning are derived from it: Claude keeps 80/70/92 exactly; Copilot gets 65/55/77. A
  configured threshold past the runner's final-warning point is lowered to it, and the policy says
  so (design D9, D10).

## Out of scope

- Copilot's `session.compaction_*` events **as a checkpoint trigger**, and Copilot errors as stream
  diagnostics: slice 5 (`a-copilot-agent-uses-hooks-and-its-own-agents`, group A). This change only
  accounts the compaction's own model call (design D3) and moves the threshold so the Hub normally
  acts first.
- The context meter from `usage_update`: slice 2.
- Converting credits to dollars, a credit budget, or a price table: excluded by D3 and by
  `usage-accounting`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- **usage-accounting**: MODIFIED *"Supported runner telemetry normalizes to one accounting shape"*
  (Copilot's per-call and cumulative telemetry). ADDED *"A Copilot turn's AI credits and premium
  requests are recorded and shown, and are not budgeted"*.
- **agent-conversation-workspace**: ADDED *"A Copilot turn refused for its plan quota is a refusal
  of its allowance"*.
- **conversation-checkpoint**: ADDED *"The threshold, the notes point and the final warning are
  placed before the runner's own compaction"*.

## Impact

- New `hub/hub/copilot_usage.py`. Edits to `runner_events.py` (`AccountingSample` gains four
  persisted fields and `credit_session_new`), `usage_accounting.py` (`copilot_session_baseline`,
  `settle_copilot_credits`, the aggregates), `worker.py` (`WorkerUsage` and the invocation write),
  `checkpoint_policy.py`, `checkpoint_trigger.py`, `db/models.py`, `api/v1/agents.py` (the agent
  summary's compaction point), slice 1's `_execute_rpc_run` (settle, and the refusal branch it lacks),
  slice 2's `copilot_acp.run_turn` (the ledger, three more subscribed events, a quota refusal ends
  `failed`) and one-shot envelope parser, and slice 1's adapters (`compaction_percent`).
- **Migration** (next free number in build order): four columns on `turn_usage`, two on
  `worker_invocations`, no backfill, no table rebuild. It reaches the operator's `:8000` on their next
  restart. It adds nullable columns only, so their data is unchanged.
- **UI**: `api/accounting.ts`, `accountingDisplay.ts`, `AccountingPanel.tsx`,
  `OverviewBudgetSummary.tsx`, `AgentOutputPanel.tsx`, `agentTimelineModel.ts`, `AgentTimeline.tsx`,
  `AgentSettingsControls.tsx`. The bundle is refreshed and committed with the source
  (`.claude/rules/hub-ui.md`); it reaches `:8000` on the operator's next reload.
- **Composes with open changes** (design D12): `an-estimate-that-misses-turns-says-so` (tonight)
  counts a Copilot turn among its unpriced turns, which is correct, and edits the same two functions;
  `worker-spend-counts-against-the-budget` (REVISING) counts Copilot worker tokens and gains the
  credit sums if it lands first.
