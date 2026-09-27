# Design — a Copilot run shows its credits

Decision **`ghcp-d3-credits`** (binding): tokens stay the accounting unit. AI credits and premium
requests are recorded and shown as information. They never drive the budget.

## What is known about Copilot, and how

Tags follow appendix A. **VERIFIED-LOCAL** = observed on this machine. **VERIFIED-SCHEMA** = read in
the shipped 1.0.88 package's `schemas/session-events.schema.json` or `app.js`, but never exercised.
**DOCUMENTED** = docs.github.com or `copilot help`. **INFERRED** = reasoned, not observed.

| Fact | Tag | Evidence |
|---|---|---|
| `assistant.usage` is emitted once per model call, with `model, inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, reasoningTokens, cost, isAuto, initiator` | VERIFIED-LOCAL | acp4 transcript, three events |
| `inputTokens` includes cache reads; `totalTokens = inputTokens + outputTokens` | VERIFIED-LOCAL | acp4 call 2: `copilotUsage.tokenDetails` input 148 + cache_read 10880 = `inputTokens` 11028; prompt result 33108 + 64 = 33172 |
| The per-call token sum equals the ACP prompt result of the first prompt in a process | VERIFIED-LOCAL | acp4: 33108 / 64 / 21888 both ways |
| `reasoningTokens` is a subset of output (*"Number of output tokens used for reasoning"*) | VERIFIED-SCHEMA | `AssistantUsageData.reasoningTokens` |
| `assistant.usage.copilotUsage.totalNanoAiu` is the call's credit cost | VERIFIED-LOCAL | acp4: 222 280 000 + 29 280 000 + 24 296 000 = 275 856 000 = the checkpoint's total |
| `assistant.usage.quotaSnapshots.<id>` carries `entitlementRequests, usedRequests, remainingPercentage, usageAllowedWithExhaustedQuota, overageAllowedWithExhaustedQuota, resetDate` | VERIFIED-LOCAL | acp4, key `chat` on the Free plan, `resetDate "2026-10-01T00:00:00Z"` |
| `assistant.usage` includes subagent calls (`parentToolCallId`, `initiator: "sub-agent"`) | VERIFIED-SCHEMA + DOCUMENTED | schema; SDK doc *"emitted once for every model API call in a turn (including calls made by sub-agents)"*. No subagent ran in acp4 |
| `assistant.usage` is ephemeral: not replayed on resume | DOCUMENTED | SDK `usage-and-billing` |
| The ACP prompt result's `usage` is cumulative for the session **within the process** | VERIFIED-LOCAL | acp4: two later slash prompts returned the same totals; after a restart and `session/load`, `/usage` returned **no `usage` field** (R1 probe, 2026-09-27) |
| `session.usage_checkpoint {totalNanoAiu, totalPremiumRequests}` is session-cumulative and survives resume | VERIFIED-LOCAL (emitted at turn end) + VERIFIED-SCHEMA (*"Durable session usage checkpoint for reconstructing aggregate accounting on resume"*) | acp4; R1 probe: `/usage` after load read "Requests: 1" from the restored session. Whether the **next** checkpoint after a load continues the total is INFERRED; task 7.3 measures it |
| `session.error {errorType, errorCode, message, statusCode, remediation}`; quota codes `quota_exceeded`, `session_quota_exceeded`, `billing_not_configured`; rate-limit codes `user_weekly_rate_limited`, `user_global_rate_limited`, `rate_limited`, … | VERIFIED-SCHEMA | `ErrorData`; never observed |
| `session.error` also reaches the ACP text stream as an `Error: <message>` chunk | VERIFIED-SCHEMA (`app.js` maps `session.error` → `agent_message_chunk "Error: …"`) | code read |
| Individual plans' allowance resets at 00:00:00 UTC on the 1st of each month; Business/Enterprise ask an administrator for more budget | DOCUMENTED | docs `billing` |
| `session.compaction_complete.compactionTokensUsed {inputTokens, outputTokens, cacheReadTokens, copilotUsage.totalNanoAiu}` and `requestId` | VERIFIED-SCHEMA | `CompactionCompleteData`. Whether the compaction call also emits an `assistant.usage` is **unknown**; task 7.4 measures it |
| Auto-compaction at ~80% of the window, a pause at ~95% | DOCUMENTED | docs `context-management` |
| 1 AI credit = $0.01 | DOCUMENTED | docs `billing` |
| AI credits = `nanoAiu / 1e9` | DOCUMENTED as a convention only | SDK doc: *"The examples divide by 1e9 as a convenience, following the SI nano prefix; confirm this matches current billing"*. acp4's `costPerBatch` gives mai-code-1.1-flash 20 AIU per million input tokens, i.e. $0.20/M at 1 AIU = 1 credit, which is plausible (INFERRED) |
| What a real plan-quota refusal looks like on the wire | **UNKNOWN** | Not observable on Free without ~190 prompts. Design D8 is conservative because of it |

## D1 — Tokens stay the unit; credits are information (the operator's D3)

`TurnUsage.total_tokens` for a Copilot turn is computed like every other runner's and counts
toward `token_budget`, `project_budget_state` and every aggregate exactly as today. Credits and
premium requests go to their own columns and are **never** summed into tokens, never compared with
`token_budget`, and never converted into `api_equivalent_usd_micros`. Converting would put a real
billing figure into a column the spec labels *API-equivalent estimate*, and *"MUST NOT invent a
monetary figure"* forbids the reverse direction too.

## D2 — One ledger per run, not per-line samples

`AccountingSample.merged` overlays newer non-null fields (`runner_events.py:302-318`). That is right
for Claude's final result and Codex's `last` usage, and wrong for Copilot's two streams, which have
to be summed (per call) or differenced (cumulative). So Copilot does not feed per-event samples into
the executor's `accounting_sample` merge (`agent_trigger.py:2554-2558`, `:3173-3177` for the Codex
executor slice 2 models itself on).

`hub/hub/copilot_usage.py` holds a `CopilotUsageLedger`, created once per run by the Copilot
adapter's **`usage_from`** member. Slice 1 defines `usage_from`; its contract must admit a stateful
per-run accumulator (open question Q1). The executor feeds it:

- `observe_event(type, data)`: every raw `github.com/copilot/sessionEvent` of the types
  `assistant.usage`, `session.usage_checkpoint`, `session.compaction_complete`, `session.error`;
- `observe_prompt_result(usage)`: the `usage` of this run's `session/prompt` result, if any;
- `finish(*, session_was_new, baseline) -> AccountingSample`: once, at run end, before
  `record_turn_usage`.

**Raw-event subscription is slice 2's.** This change requires that slice 2's `initialize` list
includes `assistant.usage`, `session.usage_checkpoint`, `session.compaction_complete` and
`session.error` (task 4.1 checks it and adds any missing).

## D3 — Tokens: per-call sum, cross-checked by the differenced prompt result

- **Per-call:** sum `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`,
  `reasoningTokens` over this run's `assistant.usage` events, each counted once (dedup by
  `providerCallId` when present, else by `apiCallId`: the same call can reach the Hub only once in
  practice, but the dedup makes a replayed notification harmless). `total = input + output`.
  `input` already includes cache (D3 table), so it is normalised with
  `cache_is_separate_input=False`, the flag Codex uses (`runner_parsing.py:72-126`). Reasoning is not
  added.
- **Compaction's own call:** a successful `session.compaction_complete` adds
  `compactionTokensUsed` **unless** an `assistant.usage` of this run has `providerCallId ==
  compaction.requestId` (both are the `x-github-request-id`). That dedup is what makes the unknown in
  the table harmless either way.
- **Cumulative:** the prompt result's `usage` minus the previous prompt result **in the same
  process for the same session**. The baseline is zero when the session was created or loaded in
  this process (VERIFIED: no `usage` after load). If slice 2 runs one process per run, the
  difference is the result itself.
- **Which wins.** Each is a lower bound: the per-call sum can lose events (at most 256 raw events in
  flight, excess dropped, appendix A §A), and the cumulative may or may not include subagent calls
  (unknown). The recorded totals are those of the source with the larger `total_tokens`. Its name
  goes in `AccountingSample.source` (`copilot_calls` or `copilot_prompt_result`). A disagreement
  of more than 1% is logged at warning level with both figures, because it is evidence about which
  lower bound is short. Neither is added to the other.
- **Model:** the model with the largest per-call total (as `_claude_model_accounting` does,
  `runner_parsing.py:128-162`). With no per-call events, the model is unknown (`None`).
- **No telemetry at all** (no events, no result usage): `total_tokens` stays None, so
  `record_turn_usage` writes `unavailable` (`usage_accounting.py:36-42`), as for any runner.

## D4 — Credits and premium requests: the session checkpoint, differenced across runs

The credit ledger that survives resume is `session.usage_checkpoint` (session-cumulative). Per run:

- `session_total` = the **last** checkpoint this run received (later replaces earlier).
- `baseline` = 0 if the session was created in this run (`session/new`). Otherwise the
  `session_nano_aiu_total` / `session_premium_requests_total` of the newest earlier `turn_usage` row
  for the same project, agent and provider session (`Run.session_id`) that has one.
  `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)` reads it.
- `ai_nano_aiu = session_total - baseline`, and likewise for premium requests.
- **No checkpoint this run** (for example a run that failed on its first call): fall back to the
  per-call sum of `copilotUsage.totalNanoAiu` (plus compaction's, deduped as in D3). Premium
  requests have no per-call equivalent (`cost` is a multiplier, and acp4 charged one premium request
  for three calls), so they stay None.
- **No baseline for a loaded session** (its earlier runs predate this change, or their rows were
  lost): fall back to the per-call sum for credits. Store the checkpoint as the new baseline anyway.
- **A negative difference** (the session's counter was reset, e.g. `/clear`; `help limits` says
  *"/clear and /new reset used AI credits"*): credits None for this run. The stored checkpoint
  becomes the new baseline. A reset is never reported as negative spend.
- The run always stores the checkpoint it ended at, when it saw one, so the next run can difference.

A run that crashed without recording leaves its spend in the next run's difference. The total stays
right; the attribution moves one run later. That is accepted and stated, not hidden.

## D5 — Schema

Migration (number: the next free one when it is built, after tonight's queue from `0111` and after
slice 2's migration). Per `.claude/rules/db-migrations.md`: guard each table's existence (as `0033`
and `0034` do), use `batch_alter_table`, bump `HEAD_REVISION` in `hub/tests/test_migrations.py:40`
and the head assertion in `hub/tests/test_project_persistence.py`.

| Table | Column | Type | Meaning |
|---|---|---|---|
| `turn_usage` | `ai_nano_aiu` | BigInteger, nullable | This run's credit cost in nano-AIU |
| `turn_usage` | `premium_requests` | Float, nullable | This run's premium requests (fractional: 0.33 was observed) |
| `turn_usage` | `session_nano_aiu_total` | BigInteger, nullable | The session checkpoint this run ended at |
| `turn_usage` | `session_premium_requests_total` | Float, nullable | Same, premium requests |
| `worker_invocations` | `ai_nano_aiu` | BigInteger, nullable | A Copilot one-shot call's credit cost |
| `worker_invocations` | `premium_requests` | Float, nullable | Same, premium requests |

- **Raw nano-AIU, never credits or dollars, is stored.** It is the exact integer Copilot reports.
  The conversion to credits is a display concern with one constant (D6), so a correction to it
  rewrites no data.
- No backfill: no existing row is a Copilot run. NULL means "not reported", not zero.
- `ck_turn_usage_availability` (`db/models.py:1284-1290`) constrains only token columns, so an
  `unavailable` row may still carry credits. That is intended: a run whose token telemetry was lost
  but whose checkpoint arrived still cost what it cost.
- Why columns and not a JSON blob: the aggregates must `SUM` them, and the code base avoids
  JSON-function SQL (`provider_allowance.py:116-118`: *"`json_type` is SQLite's alone"*).
- `isAuto` and the per-call multiplier are not stored. The runner's configured model already says
  whether it is Auto, the resolved model is `TurnUsage.model`, and the multiplier's effect is in the
  premium-request count.

`AccountingSample` gains the four `turn_usage` fields (all Optional, default None), and `merged`
carries them like the others. `record_turn_usage` writes them whether or not the sample is measured.
The one-shot envelope parser that slice 2 adds for `copilot -p --output-format json` fills
`WorkerUsage` / the invocation's two columns from the stream's `session.shutdown {totalNanoAiu,
totalPremiumRequests}` (a one-shot is a fresh session, so its totals are its own). Whether that
stream also carries `assistant.usage` is unknown (it is ephemeral); `session.shutdown` is in the
VERIFIED `events.jsonl` type list (appendix A §F).

## D6 — Where credits are shown

Credits appear wherever tokens already appear for a turn, a conversation, an agent or the project,
and **only when non-null**, so a Claude-only or Codex-only project looks exactly as it does today.

| Surface | Today | After |
|---|---|---|
| Budgets headline caption (`AccountingPanel.tsx:77-79`) | `N measured · M usage unavailable` | a second line `X.XX AI credits · P premium requests (Copilot) — not counted against the budget` |
| Budgets per-agent chips (`AccountingPanel.tsx:90-99`) | `agent: N tokens` | `agent: N tokens · X.XX AI credits` |
| Overview budget summary (`OverviewBudgetSummary.tsx:34-43`) | tokens | one `AI credits` row |
| Conversation header (`AgentOutputPanel.tsx:1113-1122`) | `N tokens` | `N tokens · X.XX AI credits` |
| Each turn's "Worked for" line (`AgentTimeline.tsx:449-477`, from `tokensByRunId`, `agentTimelineModel.ts:124-131`) | `N tokens` | `N tokens · X.XX AI credits`. `tokensByRunId` becomes `usageByRunId` returning `{tokens, nanoAiu}` |

- One formatter, `formatAiCredits(nano)` in `components/accounting/accountingDisplay.ts`, with the
  single constant `NANO_AIU_PER_AI_CREDIT = 1_000_000_000`. Its comment cites the SDK doc's caveat.
  Two decimals, `<0.01` below that, never a currency sign.
- The API: each summary (`project`, each `agents` entry, `GET /accounting/conversations/{id}`) gains
  `ai_nano_aiu: int | null` and `premium_requests: float | null` (SQL `SUM`, which is NULL when no row
  has a value: exactly the "not reported" we want). Each `recent_turns` row gains the two per-run
  fields. `budget` is unchanged and still tokens only.
- **`preferred_display` of kind `allowance` gains `runner`** (the reading row's `TurnUsage.runner`),
  and the label names the provider when it is not Claude: `Copilot monthly allowance available ·
  96% left · resets Oct 1`. Copilot writes an allowance reading on every run (D7), so without the
  name a mixed project's headline would switch between providers with no way to tell which one it
  describes. The existing Claude label is byte-identical (a test pins it).

## D7 — The allowance reading a Copilot run writes

Every Copilot run that saw a `quotaSnapshots` map writes one reading into `TurnUsage.allowance`, in
the shape `provider_allowance.allowance_refusal` already reads:

```json
{"status": "allowed" | "rejected", "resetsAt": <epoch seconds from resetDate>,
 "rateLimitType": "monthly", "quota": "<snapshot id>", "remainingPercentage": <float>,
 "provider": "copilot"}
```

- **Which snapshot.** Among the newest `quotaSnapshots` of the run: exclude `completions` (code
  completions are not billed in credits, docs `billing`), exclude `isUnlimitedEntitlement: true`, and
  exclude `entitlementRequests <= 0`. That leaves `chat` on this Free account. `premium_interactions`
  has entitlement 0 here. Of what remains, the lowest `remainingPercentage` is the reading. Which key
  a paid or Business plan draws on is INFERRED; the work-PC probe settles it (open question Q4). A
  run with no qualifying snapshot writes no reading.
- **`resetsAt`** is `resetDate` parsed as UTC. With no `resetDate` there is no `resetsAt`, and
  (by the existing rule, `provider_allowance.py:68-70`) no hold.
- **`rateLimitType: "monthly"`** because individual plans reset monthly (DOCUMENTED). The existing
  `hold_sentence` then reads *"its monthly usage limit is spent until …"*. `allowancePeriod`
  (`accountingDisplay.ts:4-8`) gains `monthly → Monthly`.
- **`status`** is `rejected` only under D8. Otherwise `allowed`.

An `allowed` reading is informative (`provider_allowance._is_informative`), so it ends a hold, as
the served turn it describes should.

## D8 — Recognising a quota refusal: structured fields only

A Copilot run's reading is `rejected` when, and only when, the run received a `session.error` with
`errorType == "quota"` and `errorCode == "quota_exceeded"`. The same fields on a `session/prompt`
JSON-RPC error's `data` count too (INFERRED that they may arrive there; nothing is matched in
`message`).

- **Not message text.** No quota-exhaustion message has been observed, and R1 found no
  client-side exhaustion string in `app.js` (searched: `quota`, `exceed`, `exhaust`, `allowance`,
  `402`, `rate_limited`). Matching guessed prose would be inventing a fact. This is the same rule
  `allowance_refusal` states for Claude (*"Not the harness's prose"*).
- **`session_quota_exceeded`** is a session cap (`--max-ai-credits`, which the Hub does not set).
  **`billing_not_configured`** needs the operator and has no reset. **`rate_limit`** codes carry no
  reset instant in the schema. None of these holds. Each is still recorded: the run fails as
  today, slice 5 renders the error, and the reading stays `allowed` or absent.
- **The reset** comes from D7's snapshot, taken from the newest `quotaSnapshots` of this run, or, when
  the refused call was the run's first, from the agent's newest earlier Copilot reading whose
  `resetsAt` is still ahead. With neither, the reading is `rejected` with no `resetsAt`: shown as
  *allowance exhausted*, and not a hold (the existing rule, unchanged).
- **The run end.** Slice 2's ACP executor must apply the refusal branch `_execute_run` applies today
  (`agent_trigger.py:2679-2745`: `hold_for_reading`, `allowance_refusal`, `return_run_entries(...,
  refusal=)`, `arm_allowance_wake`, the `queue_agent_held` event). The Codex executor never needed it
  (`agent_trigger.py:3340-3370` records usage and nothing else). If slice 1 unified the run end,
  nothing is to be added. If not, task 5.3 adds it to the Copilot executor. Re-verify in R2.
- **The first real refusal is captured verbatim.** Until one is observed, the Copilot executor logs
  every `session.error` payload at warning level, and task 8.2 asks the operator to paste the first
  quota one into FINDINGS. That is how D8's recognition is confirmed or corrected.

**Is a month-long hold wanted?** On an individual plan a refusal holds the queue until the 1st of
next month, 00:00 UTC. The operator's probe-once rule (`operator_would_probe`,
`provider_allowance.py:192-201`) still lets their own message through. The operator can end the
hold sooner by buying credits and messaging the agent, or by rebinding the agent. This matches the
Claude weekly hold. It is flagged as an operator decision (Q6) because a month is long.

## D9 — The runner's compaction point is an adapter member

`RunnerAdapter.compaction_percent: Optional[int]`, the percentage of the context window at which the
CLI compacts by itself:

| Runner | Value | Source |
|---|---|---|
| Claude | 95 | `checkpoint_policy.py:24` comment, the value today's numbers were chosen against |
| Codex | 95 | Unknown for Codex (INFERRED: it has its own auto-compaction limit). 95 keeps today's behaviour exactly; Codex is undrivable (2026-08-29) |
| Copilot | 80 | DOCUMENTED, `context-management` |

Slice 1 defines the member for Claude and Codex, because `checkpoint_policy` reads it for every
runner (slice 1's rule D16 adds a member in the slice that first *reads* it; here Claude code reads
it). If slice 1's R2 does not add it, task 3.1 adds it with these values. Either way the contract is
this table.

## D10 — Thresholds derived from the compaction point

From `C = compaction_percent` (95 when the agent has no runner or the runner is unknown):

| Quantity | Formula | Claude (C=95) | Copilot (C=80) |
|---|---|---|---|
| Built-in threshold | C − 15 | **80** (today's) | 65 |
| Built-in notes point | threshold − 10 | **70** (today's) | 55 |
| Final warning | C − 3 | **92** (today's) | 77 |

The formulas are fixed so that Claude's three numbers are byte-identical, and a test pins them.

- `resolve_policy(agent, project, *, compaction_percent=None)` returns a `CheckpointPolicy` with two
  new fields: `final_warning_percent` and `compaction_percent`. `needs_final_warning` reads
  `policy.final_warning_percent` instead of the module constant (`checkpoint_policy.py:222-237`).
  `FINAL_WARNING_PERCENT`, `DEFAULT_THRESHOLD_VALUE` and `DEFAULT_NOTES_VALUE` stay exported, equal
  to the C=95 values, for any other reader.
- **A configured threshold past the final-warning point is lowered to it.**
  - In percent mode, when the value is above `final_warning_percent`, it becomes `final_warning_percent`,
    and `threshold_source` becomes `"runner_ceiling"`.
  - In token mode the window is not known to the policy, so the ceiling is applied in `crosses`: a
    token threshold also counts as crossed when the reading's percent is at or above
    `final_warning_percent`. For Claude that fires a token threshold set above 92% of a known window
    at 92%. Today such a threshold is reached only after Claude has compacted at 95%, so it can
    never fire in time. That is the same defect this change fixes for Copilot. It is a behaviour
    change for Claude token-mode thresholds only in that band, stated here and pinned by a test
    (open question Q7).
  - A notes value that is not below the lowered threshold is lowered to `threshold − 10`, or it
    would be silently ignored (`should_request_notes`, `:205-208`).
  - Configuration is **accepted, not refused**. The project's threshold is shared by agents on
    different runners, so refusing 80% because one agent is on Copilot would refuse a threshold that
    is right for the others. The lowering is per agent, at evaluation time, and is said on screen.
- **Callers:**
  - `checkpoint_trigger.consider` (`:168-182`) resolves the agent's runner
    (`Agent.runner_id` → `Runner.cli` → adapter) and passes its `compaction_percent`. Its decline
    message (`:214-219`) names `policy.final_warning_percent`.
  - `checkpoint_handover.py:244` and `api/v1/jobs.py:536` read only `.enabled`, and are unchanged.
- **Surfaces.** The `checkpoint_due` broadcast already carries `threshold_mode` and
  `threshold_value` (`checkpoint_trigger.py:223-232`, `:298-307`). It now sends the effective value and
  gains `threshold_source`. `AgentSummary` gains `checkpoint_compaction_percent` (the bound runner's
  `compaction_percent`, null when there is none). `AgentSettingsControls.tsx` (`:315-391`) shows one line
  under the threshold for an agent whose runner compacts below 95: *"Copilot compacts at about 80% of
  its window. This agent's checkpoint fires by 77% at the latest."*
- **Compaction events.** Copilot's `session.compaction_*` as a checkpoint *trigger* is slice 5's
  (group A, `consider_from_compaction`). This change places the threshold before the compaction, so
  that trigger is the backstop and not the usual path.

## D11 — What each route returns when what it calls raises

- `GET /accounting`, `GET /accounting/conversations/{id}`: two more `SUM` columns in queries they
  already run. `accounting_snapshot` raising `ValueError` stays unreachable behind `get_project`
  (as `an-estimate-that-misses-turns-says-so` also notes). A missing column (migration not run) is a
  500, the same as for any column today.
- `PATCH /accounting/budget`: unchanged; it reads `total_tokens` only.
- **The run end.** `CopilotUsageLedger.finish` must never raise into the executor. Malformed
  telemetry degrades to an unavailable outcome (the existing requirement). `finish` catches its own
  errors and returns a sample with no tokens and no credits, logged. `copilot_session_baseline`
  runs in the finalising session. If it raises, the executor's existing failure tail applies. So it
  is wrapped: a failed baseline read yields "no baseline" (D4's fallback), never a failed run.
- `checkpoint_trigger.consider_from_reading` is fire-and-forget and already swallows exceptions
  (`:386-399`). The runner lookup adds one `db.get(Runner, …)`. A missing runner row yields C=95.
- `GET /agents` (the summary): one more field computed from a runner row it already loads for
  `runner_options`. Re-verify in R2 that it does load it. If it does not, the value is null, never an
  error.

## D12 — How this composes with the open changes

- **`an-estimate-that-misses-turns-says-so`** (APPROVED, tonight's ORDER). It adds `unpriced_turns`
  to `_aggregate_columns` and `_summary_from_row` (`usage_accounting.py:61-96`). This change adds
  `ai_nano_aiu` and `premium_requests` to the same two functions. They are independent columns, so
  whichever builds second rebases. A Copilot turn has `api_equivalent_usd_micros IS NULL`, so it
  **is** counted among the unpriced turns, and the label reads *"excludes N turns with no reported
  cost"*. That is true: the turn reported no API-equivalent USD figure. Its credits are shown on the
  line below, so the operator sees where that spend went. That change's text is not edited.
- **`worker-spend-counts-against-the-budget`** (REVISING). It adds `worker_invocations.total_tokens`,
  rebuilds the outcome CHECK (its migration), sums worker tokens into `used_tokens`, and adds
  `workers` lines. Composition:
  - Its migration and this one both `batch_alter_table` `worker_invocations`, on different columns,
    and compose in either order.
  - A Copilot one-shot's `total_tokens` comes from slice 2's envelope parser through its normaliser
    with `cache_is_separate_input=False` (Copilot's input includes cache, D3).
  - **Whichever lands second** adds `ai_nano_aiu` / `premium_requests` sums to each `workers` line
    (task 6.4 is conditional on it). This is the pattern that change's review used for `unpriced_calls`.
  - Its D3a edits `checkpoint_trigger.consider` at the two `not policy.automatic` tests. This change
    edits `resolve_policy`'s call and the final-warning comparison in the same function. They are
    compatible in either order. Its review asks for an *effective* policy at exhaustion; the
    `final_warning_percent` field added here is part of whatever effective policy it builds.
- **`a-checkpoint-is-handed-over-once-and-says-where-it-went`** is archived (2026-09-25). Its
  handed-over decline in `consider` (`checkpoint_trigger.py:235-252`) is already in the code this
  change edits.
- **Slice 5** reads the same `session.error` events for stream diagnostics and says *"Recording one
  does not move any quota hold: holds are slice 4's"*. The two consumers are independent.

## Tests that can fail (summary; tasks.md group 1 is the list)

Pure-ledger tests use event sequences in the order Copilot emitted them in acp4 (`usage_update`,
`assistant.usage` ×3, `hook` events, `session.usage_checkpoint`, then the prompt result). Where
order matters (two checkpoints: the later wins), the test asserts the later one, so reversing the
order fails it. API tests assert by position in the order the route returns (`agents` by name,
`recent_turns` by `observed_at` descending).

## Round log

- **R1 (2026-09-27).** Read: the exploration and appendices A, B, C; DECISIONS `ghcp-d1`..`d6`; the
  brief; `usage_accounting.py`, `provider_allowance.py`, `context_readings.py`,
  `checkpoint_policy.py`, `checkpoint_trigger.py`, `runner_events.py`, `runner_parsing.py` (`:30-165`,
  `:300-372`, `:660-707`), `codex_appserver.py:340-390`, `agent_trigger.py` (`:2640-2745`,
  `:3040-3370`), `api/v1/accounting.py`, `api/v1/agents.py:596-620,2370-2440`, `db/models.py`
  (`Agent`, `Runner`, `Run`, `TurnUsage`, `WorkerInvocation`); UI `api/accounting.ts`,
  `accountingDisplay.ts`, `AccountingPanel.tsx`, `AgentOutputPanel.tsx:1105-1125`,
  `agentTimelineModel.ts:110-131`, `AgentTimeline.tsx`; specs `usage-accounting`,
  `agent-context-usage`, `conversation-checkpoint` (`:298-466`), `agent-conversation-workspace`
  (`:2472-2578`); the open changes `an-estimate-that-misses-turns-says-so` and
  `worker-spend-counts-against-the-budget` (and its APPROVALS row); slice 1's and slice 5's proposals
  as far as written; `.claude/rules/db-migrations.md`, `hub-ui.md`. Measured: the acp4 transcript's
  per-call sums against the prompt result and the checkpoint, and its `quotaSnapshots`; the 1.0.88
  `session-events.schema.json` definitions `AssistantUsageData`, `UsageCheckpointData`, `ErrorData`,
  `CompactionCompleteData`, `CompactionStartData`; a restart + `session/load` + `/usage` probe with no
  model call (the cumulative prompt usage is absent after a load); `copilot-user-cache.json` (read
  only, not used by the design, see Q4); docs `billing`, `usage-and-billing`, `context-management`,
  `help billing`, `help limits`.

## Open questions for R2/R3

- **Q1 (slice 1).** Does slice 1's `usage_from` contract admit a stateful per-run ledger created by
  the adapter (D2)? If it defines `usage_from` as a pure per-line function, the Copilot adapter needs a
  separate `new_usage_ledger()` member. Reconcile with slice 1's design D3 and D16.
- **Q2 (slice 2).** Does slice 2 run one `copilot.exe` per run or reuse a process across runs? D3's
  cumulative baseline depends on it, and the ledger takes the previous in-process result as an
  argument either way. Also: does slice 2 know, at run end, whether it called `session/new` or
  `session/load` (D4 needs `session_was_new`)?
- **Q3.** Does the ACP prompt-result `usage` include subagent calls? And does a compaction's call
  also emit an `assistant.usage`? D3's rules are right either way (max of lower bounds; dedup by
  request id). The drive measures both (tasks 7.4, 7.5).
- **Q4.** Which `quotaSnapshots` key does a paid or Business plan draw on? D7 picks the lowest
  remaining among billable, limited snapshots. A work-PC probe (human-only) confirms it. R1 read
  `%LOCALAPPDATA%\copilot\copilot-user-cache.json`. It holds the same snapshots plus
  `quota_reset_date_utc`, but it is an undocumented *"disposable cache"*, so the design does not use
  it.
- **Q5.** Is `nanoAiu / 1e9` exactly one AI credit? DOCUMENTED only as the SDK's convention with a
  caveat. The Hub stores raw nano-AIU, so only the one display constant would change.
- **Q6 (operator).** A Copilot quota refusal on an individual plan holds the agent's queue until the
  1st of next month (D8). Is a month-long hold wanted, or should a Copilot refusal be shown without
  holding? D1–D6 do not answer this.
- **Q7.** D10's token-mode ceiling changes Claude's behaviour for token thresholds set between 92%
  and 100% of a known window. Keep it uniform (R1's choice: that band can never fire before Claude
  compacts), or restrict the ceiling to runners whose compaction point is below 95?
- **Q8.** `hub/ui/src/components/context/contextPresentation.ts:7` colours the meter amber at a fixed
  70%. For Copilot (final warning 77) that is still before the final warning. Confirm no other UI
  literal assumes 80/92.
- **Q9.** `accounting_snapshot`'s `preferred_display` picks the newest allowance of any runner. D6
  adds the runner name. Is a per-runner display (one line per provider) the better fix? R1 kept the
  smaller one.
