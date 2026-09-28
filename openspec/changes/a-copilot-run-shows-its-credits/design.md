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
to be summed (per call) or taken as a process-cumulative figure. So Copilot does not feed per-event
samples into the executor's `accounting_sample` merge (`api/v1/agent_trigger.py:2555-2558` for the
stream executor; `:3174-3177`, `_on_accounting`, for the Codex RPC executor that slice 2 reuses).

**Where the ledger lives (R2, re-derived against slices 1 and 2 as designed, not built).**
Slice 1's design defines no adapter-level `usage_from`. `usage_from` is a `StreamTransport` member,
`(*, session_id, env, model) -> Optional[AccountingSample]`, read once after the process exits (its
D3). For an `RpcTransport` the name only labels the notification-to-`cb.on_accounting` mapping
inside `run_turn`. Slice 1's D16 reserves `spend_from(event)` and `quota_hold_from(event)` for this
slice as **per-event** functions. A per-event function cannot sum with dedup, cannot take a
process-cumulative figure, and cannot let the later checkpoint win. So this change does not add
them: the ledger below replaces both (cross-slice gap G1). Slice 2 runs **one `copilot.exe` per
turn** and one `run_turn` call per run (its D3, D18), so a per-call object is a per-run object.

`hub/hub/copilot_usage.py` holds a `CopilotUsageLedger`. It is stdlib-only and imports nothing that
reaches the database, as slice 1's D1 requires of adapter code. `copilot_acp.run_turn` (slice 2)
creates one per call and feeds it:

- `observe_event(type, data)`: every raw `github.com/copilot/sessionEvent` of the types
  `assistant.usage`, `session.usage_checkpoint`, `session.compaction_complete`, `session.error`,
  **only once the `session/prompt` request has been written**. That is the same arming slice 2's
  mapper uses (its D7), so nothing `session/load` replays can reach the ledger. Whether a load
  replays a durable `session.usage_checkpoint` is unknown. Unarmed, a replayed one would become the
  "last" checkpoint of a run that failed before its own.
- `observe_prompt_result(usage)`: the `usage` of the `session/prompt` result, if any;
- `finish(*, session_was_new) -> AccountingSample`: called once, on every return path of `run_turn`
  that produced a session, and passed to `cb.on_accounting`. `session_was_new` is True when
  `run_turn` called `session/new`, including slice 2's `-32002` fallback (its D7). The transport
  knows which call it made. The executor does not.

`finish` has no database, so it returns final **tokens** and **provisional credits**: the last
checkpoint's session totals, the per-call nano-AIU sum, `session_was_new`, and the allowance reading
(D7, D8), possibly without `resetsAt`. The executor settles the credits at run end, in the
finalising session and before `record_turn_usage`, with
`usage_accounting.settle_copilot_credits(db, sample, *, project_id, agent, session_id)` (D4, D8).
It acts on any sample that carries a session credit total, and only Copilot's do. So the generic RPC
executor needs no runner literal. A run where `run_turn` raised before `finish` records no sample,
which gives an `unavailable` row, as today.

**Raw-event subscription is slice 2's list.** Slice 2's design subscribes `session.error` but not
`assistant.usage`, `session.usage_checkpoint` or `session.compaction_complete`. It says *"Slice 4
adds its own (`assistant.usage`, `session.usage_checkpoint`)"* and keeps the list as a module
constant. Task 4.1 adds all three. Slice 5 subscribes `session.compaction_complete` for its own
trigger, and a set union makes that harmless.

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
  compaction.requestId` (both are the `x-github-request-id`, schema descriptions re-read in R2), or
  failing that the same `serviceRequestId` (both schemas carry one). That dedup is what makes the
  unknown in the table harmless either way. `compactionTokensUsed.copilotUsage` is marked
  `"visibility": "internal"` in the schema, so it may be absent on the wire. The compaction's credits
  are then only in the checkpoint, which is where D4 reads them first anyway.
- **Cumulative:** the **last** prompt result's `usage` in the process. Slice 2 runs one process per
  turn (its D3), and the counter is per process (VERIFIED: no `usage` after a restart and load). So
  the process-cumulative figure *is* this run's figure, and no cross-run difference exists to take.
  If a run ever sent two prompts, the later cumulative result would already include the earlier one.
  So the ledger keeps the later result and never adds the two together. That the counter starts at
  zero after a load **for a model prompt** is still INFERRED: R1's post-load probe was `/usage`,
  which makes no model call. Task 7.3 measures it (Q10). If it is false, the rule below would record
  the whole session's history as this run's cost.
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

- `session_total` = the **last** checkpoint this run received (later replaces earlier). The ledger
  (D2) supplies it.
- `baseline` = 0 if the session was created in this run (`session_was_new`, from the transport,
  D2). Otherwise the `session_nano_aiu_total` / `session_premium_requests_total` of the newest earlier
  `turn_usage` row for the same project, agent and provider session that has one.
  `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)` reads it by joining
  `turn_usage.run_id` to `runs.id` on `Run.session_id == session_id`. `Run.session_id` is set at
  creation from the resume id (`api/v1/agent_trigger.py:1310`) and rebound by `_bind_session_id`
  (`:3102-3125`). The current run's own row is not written yet, so it is never its own baseline.
- `ai_nano_aiu = session_total - baseline`, and likewise for premium requests.
- **No checkpoint this run** (for example a run that failed on its first call, or was stopped):
  fall back to the per-call sum of `copilotUsage.totalNanoAiu` (plus compaction's, deduped as in D3).
  Premium requests have no per-call equivalent (`cost` is a multiplier, and acp4 charged one premium
  request for three calls), so they stay None.
- **No baseline for a loaded session** (its earlier runs predate this change, or their rows were
  lost): fall back to the per-call sum for credits. Store the checkpoint as the new baseline anyway.
- **A negative difference** (the session's counter was reset, e.g. `/clear`; `help limits` says
  *"/clear and /new reset used AI credits"*): credits None for this run. The stored checkpoint
  becomes the new baseline. A reset is never reported as negative spend.
- The run always stores the checkpoint it ended at, when it saw one, so the next run can difference.
- **A fallback run stores the total it reached (R2 correction).** Without this, a run with no
  checkpoint was charged its per-call sum, and the next run's difference against the older baseline
  charged the same credits again. R1's text said the spend "moves one run later". That holds only for
  a run that recorded nothing, not for one that recorded the fallback. So when a run takes the
  per-call fallback **and** its baseline is known (0 for a new session, or a stored total), it stores
  `session_nano_aiu_total = baseline + per_call_sum` and `session_premium_requests_total = None`. The
  next run then differences against what was already charged. Its premium requests come out None,
  because their baseline is unknown, rather than doubled. With no known baseline it stores nothing.
  acp4 showed the per-call sum equal to the checkpoint exactly, so the synthetic total is the real
  one whenever no call event was dropped.

A run that crashed without recording anything leaves its spend in the next run's difference. The
total stays right, and the attribution moves one run later. That is accepted and stated, not hidden.

`settle_copilot_credits` never raises. A failed baseline read is "no baseline". Any other exception
is logged, and the sample is returned with the ledger's provisional per-call credits (D11).

## D5 — Schema

Migration (number: the next free one when it is built, after slice 2's migration; head is `0110` at
R2, and none of the five night changes that landed added one). Per `.claude/rules/db-migrations.md`:
guard each table's existence (as `0033` and `0034` do, e.g. `0033_add_question_batches.py:32-35`),
use `batch_alter_table`, bump `HEAD_REVISION` in `hub/tests/test_migrations.py:40` and the head
assertion in `hub/tests/test_project_persistence.py:227`.

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

`AccountingSample` (`runner_events.py:287-318`) gains the four `turn_usage` fields (all Optional,
default None), and `merged` carries them like the others. It also gains one field that is not
persisted, `credit_session_new: Optional[bool]`, which `settle_copilot_credits` reads (D2).
`record_turn_usage` (`usage_accounting.py:15-58`) writes the four whether or not the sample is
measured. `WorkerUsage` (`worker.py:89-102` today; slice 1 moves it to
`runner_adapters/one_shot.py`) gains `ai_nano_aiu` and `premium_requests`, and `run_worker` writes
them into the `WorkerInvocation(...)` it builds (`worker.py:393-412`). The one-shot envelope parser
that slice 2 adds (`parse_copilot_envelope`, the Copilot adapter's `parse_one_shot`) fills them from
the stream's `session.shutdown {totalNanoAiu, totalPremiumRequests}`. A one-shot is a fresh
session, so its totals are its own. `session.shutdown` is in the VERIFIED `events.jsonl` type list
(appendix A §F), but that it appears in the **`-p --output-format json`** stream is not verified.
Slice 2's task 1.2 capture fixes the stream's event names, and task 5.4 here reads them from that
capture. If the capture has no `session.shutdown`, the two columns stay NULL and task 5.4 says so.

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
- **`preferred_display` of kind `allowance` gains `runner`** (the reading row's `TurnUsage.runner`;
  today `latest_allowance` keeps only `row.allowance`, `usage_accounting.py:163-165`, so the row
  itself must be kept). The label names the provider when it is not Claude: `Copilot monthly
  allowance available · 96% left · <resetLabel>`. `<resetLabel>` is today's `resetLabel`
  (`accountingDisplay.ts:10-20`), which prints month, day and time in the viewer's zone. R1's
  "resets Oct 1" was not what that function prints. Copilot writes an allowance reading on every run
  (D7), so without the name a mixed project's headline would switch between providers with no way to
  tell which one it describes. The existing Claude label is byte-identical (a test pins it).
- **What the Copilot reading displaces (R2).** `preferred_display` has one kind. `allowance` wins
  whenever any of the newest 50 rows carries a reading (`usage_accounting.py:163-184`). In a
  Codex + Copilot project, where Codex writes no reading, one Copilot run replaces the
  `api_equivalent` headline (the Codex dollar estimate and its "excludes N turns" note) with
  Copilot's allowance. A Claude-only, Codex-only or Claude + Copilot project's headline is unaffected
  in kind. This is Q9, sharpened. R2 leaves the decision open.
- **Credits on an unavailable turn.** The aggregate `SUM(ai_nano_aiu)` is not filtered by `status`,
  so the project, agent and conversation totals include the credits of a turn whose token
  telemetry was lost (D5). `usageByRunId` omits unavailable turns as `tokensByRunId` does
  (`agentTimelineModel.ts:124-131`), so such a turn's own line shows nothing. The totals are right.
  The per-turn line is silent rather than showing "0 tokens".

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
  `resetsAt` is still ahead. The ledger cannot read that (no database, D2), so it emits the rejected
  reading without `resetsAt`, and `settle_copilot_credits` fills it in at run end from the newest
  `turn_usage` row for the project and agent with `runner == "copilot"` and a dict allowance. The
  dict test is done in Python, as `_is_informative` does (`provider_allowance.py:108-119`). With
  neither, the reading is `rejected` with no `resetsAt`: shown as *allowance exhausted*, and not a
  hold (the existing rule, `provider_allowance.py:68-75`, unchanged). Such a reading is still
  informative, so it ends any earlier hold.
- **The run end (re-verified in R2).** `_execute_run` applies the refusal branch today
  (`api/v1/agent_trigger.py:2667-2743`): `record_turn_usage` returns the row, then `hold_for_reading`
  and `allowance_refusal` read `usage.allowance`, `refusal` is set only for `final_status ==
  "failed"` with no binding conflict and a reset ahead of `run.ended_at`,
  `finalize_job_run_for_conversation` is skipped under a refusal, `return_run_entries(...,
  refusal=)` runs, and after the commit come `arm_allowance_wake` and the `queue_agent_held` event.
  The Codex RPC executor has none of it (`:3345-3362` records usage, finalises the job run and
  returns entries uncounted). Slice 1's D9 turns that executor into `_execute_rpc_run` by
  parameterisation only, and slice 2's D18 passes the Copilot adapter to it unchanged. **Neither
  unifies the run end.** So task 5.3 adds the branch to `_execute_rpc_run` itself, not to a
  Copilot-only copy. For Codex the branch is inert, because no Codex sample carries an allowance.
- **A refused turn must end `failed` (R2 correction).** The branch above requeues the input
  uncounted only when `final_status == "failed"`. Otherwise `held` is still armed (a hold is derived
  from the reading, whatever the status), but `return_run_entries` is not called. The refused
  message is then treated as delivered and never retried: the queue waits a month for nothing. Which
  `stopReason` Copilot returns after a quota `session.error` is **unknown**: the schema maps the error
  into an `Error: …` text chunk, and the prompt may still end `end_turn`. So `copilot_acp.run_turn`
  returns `TurnOutcome(status="failed", error=<the session.error message>)` whenever its ledger
  recorded the D8 refusal, whatever the stop reason. Task 1.15 covers it with a scripted session whose
  prompt returns `end_turn`. A fixture that ends `failed` by construction could not fail on this.
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

**Slice 1 does not define it (R2).** Its D16 lists `compaction_percent` under *"reserved for later
slices (contract only, not added here)"*, slice 4, and its rule is that the slice that first
*reads* a member adds it. This slice is that reader. Slice 2's cross-slice note says *"whichever
change lands first adds the member"*. So task 3.1 adds it unconditionally: a `ClassVar[Optional[int]]`
on `RunnerAdapter`, with Claude 95 and Codex 95. It also sets Copilot's 80 on slice 2's
`CopilotAdapter`, which exists by then. It has no base-class default, so an adapter that omits it
fails slice 1's conformance test that `ADAPTERS` instantiates and declares every member (task 3.1
extends that test). The contract is this table. (Rebase at IMPL: `each-runner-cli-is-one-adapter`
unbuilt at R2.)

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
    and `threshold_source` becomes `"runner_ceiling"`. **For Claude this also lowers a configured
    93–99% to 92%.** `threshold_error` accepts up to 99 (`checkpoint_policy.py:125-129`). R1 stated
    only the token-mode change, and this is a second Claude behaviour change (Q7).
  - In token mode the window is not known to the policy, so the ceiling is applied to the reading's
    percent. **Not in `crosses`** (R2 correction): `crosses(mode, value, *, context_tokens, percent)`
    (`:156-172`) takes no policy and is also used for the notes point. The ceiling goes in
    `should_checkpoint` (`:175-192`) and in the threshold half of `should_request_notes`
    (`:214-219`, so that notes stop being asked once the ceiling is reached). In both, a token
    threshold counts as crossed when `crosses(...)` is True **or** `percent >= final_warning_percent`.
    For Claude that fires a token threshold set above 92% of a known window at 92%. Today such a
    threshold is reached only after Claude has compacted at 95%, so it can never fire in time. That
    is the same defect this change fixes for Copilot. It is a behaviour change for Claude token-mode
    thresholds only in that band, stated here and pinned by a test (open question Q7).
  - A notes value that is not below the lowered threshold is lowered to `threshold − 10`, or it
    would be silently ignored (`should_request_notes`, `:205-208`).
  - Configuration is **accepted, not refused**. The project's threshold is shared by agents on
    different runners, so refusing 80% because one agent is on Copilot would refuse a threshold that
    is right for the others. The lowering is per agent, at evaluation time, and is said on screen.
- **Callers:**
  - `checkpoint_trigger.consider` (`:168-182`) resolves the agent's runner
    (`Agent.runner_id` → `db.get(Runner, …)` → `get_adapter(runner.cli)`) and passes its
    `compaction_percent`. No agent row, no `runner_id`, a missing runner row or no adapter gives C=95.
    `checkpoint_trigger` importing `runner_adapters` adds no cycle, because slice 1's D1 lets
    `runner_adapters` import nothing that reaches the database. Its decline message (`:214-219`)
    names `policy.final_warning_percent` instead of the imported `FINAL_WARNING_PERCENT` (`:26`).
  - `checkpoint_handover.py:244` and `api/v1/jobs.py:536` read only `.enabled`, and are unchanged.
    Those are the only other `resolve_policy` callers (grep, R2).
- **Surfaces.** The `checkpoint_due` broadcast already carries `threshold_mode` and
  `threshold_value` (`checkpoint_trigger.py:222-232`, `:298-307`). It now sends the effective value and
  gains `threshold_source`. `AgentSummary` gains `checkpoint_compaction_percent` (the bound runner's
  `compaction_percent`, null when there is none; D11 says where `GET /agents` reads it).
  `CheckpointOverrideSetting` in `AgentSettingsControls.tsx` (`:333-406`) shows one line under the
  threshold for an agent whose runner compacts below 95: *"Copilot compacts at about 80% of its
  window. This agent's checkpoint fires by 77% at the latest."*
- **Where the percent comes from.** A live Copilot reading derives `percent` in
  `ContextUsageSample.__post_init__` (`runner_events.py:260-268`) from slice 2's `usage_update
  {used, size}`. D10 assumes Copilot's "about 80%" is a fraction of that same `size` (INFERRED). The
  HTTP route `POST /agents/{name}/context-usage` does **not** derive it: `resolve_usage_limit`
  returns a payload that already carries `limit_tokens` unchanged, percent-less
  (`output_recording.py:139-140`). So a synthetic reading must carry `percent` itself (task 7.6).
- **Compaction events.** Copilot's `session.compaction_*` as a checkpoint *trigger* is slice 5's
  (group A, `consider_from_compaction`). This change places the threshold before the compaction, so
  that trigger is the backstop and not the usual path.

## D11 — What each route returns when what it calls raises

- `GET /accounting`, `GET /accounting/conversations/{id}` (`api/v1/accounting.py:25-46`): two more
  `SUM` columns in queries they already run. `accounting_snapshot` raises `ValueError` only for a
  missing project (`usage_accounting.py:117-119`), and that stays unreachable, because `get_project`
  has already answered 404 (`auth.py:158`, `:181`), as the landed `an-estimate-that-misses-turns-says-so`
  also notes. The conversation route 404s an unknown or foreign conversation before
  `conversation_usage` runs (`accounting.py:43-45`). A missing column (migration not run) is a 500,
  the same as for any column today.
- `PATCH /accounting/budget`: its response reads `total_tokens` only. But it calls
  `accounting_snapshot(…, recent_limit=0)` (`accounting.py:66`) **after** committing the budget, so the
  new `SUM` columns do run there. If they raise (no migration), the budget is saved and the route
  answers 500, which is today's behaviour for any aggregate column.
- **The run end.** `CopilotUsageLedger.finish` must never raise into `run_turn`. Malformed telemetry
  degrades to an unavailable outcome (the existing requirement). `finish` catches its own errors and
  returns a sample with no tokens and no credits, logged. `settle_copilot_credits` runs in the
  finalising session, inside the `async with` whose exceptions the executor's failure tail would
  take. So it catches everything: a failed baseline or prior-reading read yields D4's "no baseline"
  and D8's "no prior reading", never a failed run.
- `checkpoint_trigger.consider_from_reading` is fire-and-forget and already swallows exceptions
  (`:387-399`). The runner lookup adds one `db.get(Runner, …)`. A missing runner row yields C=95.
- `GET /agents` (the summary) — **(d) re-verified in R2:** `list_agents` loads every runner of the
  project once into `runners_by_id` (`api/v1/agents.py:405-407`) and reads the bound one per agent
  (`:548`, `bound_runner`). R1 said the row came from `runner_options`. It does not:
  `runner_options` is session metadata (`:596`). `checkpoint_compaction_percent` is then
  `get_adapter(bound_runner.cli).compaction_percent` when there is a bound runner and an adapter,
  else null, set in the `AgentSummary(...)` built at `:581-630`. It adds no query and cannot raise.
  The route returns `[]` before this point when the project has no session metadata (`:409-410`).

## D12 — How this composes with the open changes

- **`an-estimate-that-misses-turns-says-so`** (**landed**, archived 2026-09-28). `unpriced_turns` is
  now in `_summary_from_row` (`usage_accounting.py:61-84`, `:80`) and `_aggregate_columns`
  (`:87-100`, `:97-99`), and in the `api_equivalent` display (`:174-180`). This change adds
  `ai_nano_aiu` and `premium_requests` beside it in the same two functions, which is additive. A
  Copilot turn has `api_equivalent_usd_micros IS NULL`, so it **is** counted among the unpriced
  turns. That is true: the turn reported no API-equivalent USD figure. The *"excludes N turns with
  no reported cost"* label (`accountingDisplay.ts:44-47`) shows only when the headline is
  `api_equivalent`, and a Copilot reading usually makes it `allowance` (D6, Q9). So in practice the
  unpriced count reaches the operator only through the API. That change's text is not edited.
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
- **R2 (2026-09-28).** An independent re-derivation from the code at master `ef55e6f`.
  - **Drift, stated explicitly.** Task 0.1 asked for the code "after slices 1–3 and tonight's queue".
    Only 5 of the 2026-09-27 night ORDER's 28 changes are on master: `a-runner-choice-names-its-model`,
    `an-estimate-that-misses-turns-says-so`, `a-model-alias-is-a-model-choice`,
    `the-codex-models-offered-are-the-ones-its-cli-lists` and
    `a-firing-is-counted-once-however-many-agents-it-starts`. Slices 1–3 are **unbuilt**, and each has
    its own R2 running concurrently. So every statement below about slices 1 and 2 is about their
    `design.md` as written on 2026-09-28, **not about code**. Each dependency on them is marked
    *(rebase at IMPL: <change> unbuilt at R2)*. Migration head is still `0110`.
    `worker-spend-counts-against-the-budget` has not landed.
  - **Read (code):** `usage_accounting.py` (whole, 224 lines, after `unpriced_turns` landed);
    `api/v1/accounting.py` (whole); `provider_allowance.py` (whole); `checkpoint_policy.py` (whole);
    `checkpoint_trigger.py:1-410`; `runner_events.py:230-318`; `runner_parsing.py:28-165`,
    `:340-372`; `api/v1/agent_trigger.py:2640-2760`, `:3099-3180`, `:3320-3380`, and the grep of every
    `record_turn_usage`/refusal-branch site; `codex_appserver.py:887-917` (`TurnOutcome`);
    `db/models.py:1128-1150` (`Run`), `:1258-1298` (`TurnUsage`), `:1889-1935` (`WorkerInvocation`);
    `worker.py:89-102`, `:393-412`; `api/v1/agents.py:277-300`, `:400-440`, `:548`, `:560-640`,
    `:2980-2996`; `output_recording.py:125-189`, `:225-239`; `schemas/agents.py:190-240`;
    `hub/tests/test_migrations.py:40`, `test_project_persistence.py:227`,
    `test_checkpoint_policy.py:249-269`. UI: `AccountingPanel.tsx:60-110`,
    `accountingDisplay.ts:1-51`, `OverviewBudgetSummary.tsx:30-45`,
    `AgentOutputPanel.tsx:1108-1124`, `agentTimelineModel.ts:118-133`, `AgentTimeline.tsx` (the
    `tokenCount` sites), `AgentSettingsControls.tsx:310-415`, and a grep for 80/92/95 literals.
  - **Read (designs, not code):** slice 1 `design.md` (whole: D1, D3, D9, D15, D16); slice 2
    `design.md` `:15-40`, `:125-160`, `:295-350`, `:485-560`, `:590-630`, `:695-790`, `:870-883`, and
    its `tasks.md` test-file names; slice 3 and slice 5 designs (greps for slice-4 touchpoints);
    the archived `an-estimate-that-misses-turns-says-so/design.md:36-45`; DECISIONS `ghcp-d3`..`d6`.
  - **Re-measured:** the 1.0.88 `session-events.schema.json` (`CompactionCompleteData`,
    `UsageCheckpointData`, `ErrorData`, `AssistantUsageData` properties and descriptions); the acp4
    transcript (`a-copilot-agent-runs-over-acp/evidence/acp4-turn-mcp-shell-1.0.88.log`). The event
    order is three `assistant.usage` (lines 18, 32, 45), then `session.usage_checkpoint` (51), then
    the prompt results (53+, `end_turn`). The per-call nano-AIU are 222280000 + 29280000 + 24296000.
    `quotaSnapshots` are `chat` 200 / 96.6→96.5, `completions` 2000 / 100 and `premium_interactions`
    0 / 0. The newest `chat` reading is 96.5, as test 1.9 says. The proposal's 96.6 is call 1's.
  - **Wrong, and changed:**
    1. D2 put the ledger behind an adapter `usage_from`. Slice 1 defines no such member (Q1).
       The ledger now lives in `copilot_acp.run_turn`, is armed with the mapper, emits one sample
       through `cb.on_accounting`, and is settled by a new `settle_copilot_credits` at run end.
    2. D3 differenced the prompt result against a previous in-process result. With one process per
       turn (slice 2 D3) there is none, so the figure is the last result in the process (Q2). The
       post-load zero is still INFERRED (Q10).
    3. D4 **double-counted credits**: a run with no checkpoint was charged its per-call sum, and the
       next run's difference against the older baseline charged the same credits again. A fallback
       run now stores `baseline + per_call_sum` as its session total (test 1.8).
    4. D8 did not require a refused Copilot turn to end `failed`. With an `end_turn` stop reason
       (unknown for a quota error), `_execute_run`'s logic would arm the hold but never return the
       refused input (`agent_trigger.py:2684-2689`, `:2719-2723`). `run_turn` now fails the turn.
       R1's "if slice 1 unified the run end" is answered: it does not (slice 1 D9, slice 2 D18). So
       task 5.3 adds the branch to `_execute_rpc_run`.
    5. D9 assumed slice 1 defines `compaction_percent`. Its D16 reserves it for this slice, so task
       3.1 is unconditional.
    6. D10 put the token-mode ceiling in `crosses`, which takes no policy. It now goes in
       `should_checkpoint` and `should_request_notes` (test 1.12 rewritten). D10 also missed that the
       percent clamp lowers a Claude 93–99% threshold to 92 (Q7).
    7. D11(d): `GET /agents` reads the runner row from `runners_by_id` (`:405-407`, `:548`), not
       from `runner_options`.
    8. Task 7.6 would have raised no banner: `POST /agents/{name}/context-usage` does not derive
       `percent` when `limit_tokens` is given (`output_recording.py:139-140`). The task now posts
       `percent`. The route is at `:2980`, not `:2976`.
    9. D5 did not add `ai_nano_aiu`/`premium_requests` to `WorkerUsage` or the
       `WorkerInvocation(...)` write (`worker.py:393-412`). It also called `session.shutdown` in the
       `-p` JSON stream verified, when only the `events.jsonl` list is verified.
    10. Line references re-derived: `usage_accounting.py:61-96` → `:61-84` + `:87-100`; the refusal
        branch `:2679-2745` → `:2667-2743`; the Codex run end `:3340-3370` → `:3345-3362`;
        `AgentSettingsControls.tsx:315-391` → `:333-406`; the `checkpoint_due` payloads
        `:223-232` → `:222-232`; D6's reset label, which is not "resets Oct 1".
    11. D6/D12: a Copilot allowance reading displaces the `api_equivalent` headline in a Codex +
        Copilot project (Q9 sharpened), so the "excludes N turns" label rarely shows beside credits.
    12. Spec deltas: `agent-conversation-workspace` now says a refused turn ends failed and its input
        is returned uncounted. `usage-accounting` says a fallback run records the total it reached.
  - **Verified as R1 stated:** `runner_events.py:302-318`; `usage_accounting.py:36-42`;
    `provider_allowance.py:60-80`, `:68-70`, `:116-118`, `:192-201`; `db/models.py:1258-1298`,
    `:1284-1290`; `runner_parsing.py:72-126`, `:128-162`, `:364-369`; `checkpoint_policy.py:24`,
    `:205-208`, `:222-237`; `checkpoint_trigger.py:168-182`, `:214-219`, `:235-252`, `:298-307`,
    `:386-399`; `checkpoint_handover.py:244`; `api/v1/jobs.py:536`; `output_recording.py:173-189`,
    `:233-238`; `AccountingPanel.tsx:77-79`, `:90-99`; `OverviewBudgetSummary.tsx:34-43`;
    `AgentOutputPanel.tsx:1113-1122`; `AgentTimeline.tsx:449-477`; `agentTimelineModel.ts:124-131`;
    `accountingDisplay.ts:4-8`. Every schema fact tagged VERIFIED-SCHEMA was re-read. The
    `providerCallId`/`requestId` match holds, and `serviceRequestId` is on both.
  - **Route-raises (D11):** accounting routes 404 before the aggregate can raise. `PATCH /budget`
    commits and then aggregates, so a missing column gives saved-then-500, as today. `GET /agents`
    cannot raise on the new field. The run end cannot fail on the ledger or the settle, and
    `consider_from_reading` swallows.
  - **Answers:** Q1 and Q2 answered (above, from designs). Q8 answered. D8's run end: not unified
    by slice 1, so task 5.3 applies. D9: this change adds the member. D11(d): answered from code.
  - **Cross-slice gaps** (for the slice R2s and the orchestrator; not edited here):
    G1, slice 1 D16 still reserves `spend_from`/`quota_hold_from`, which this change supersedes.
    G2, slice 1's `RpcTransport.run_turn` contract should let a transport call `cb.on_accounting`
    once with a whole-turn sample, and slice 2's D18 says `on_accounting` is "never called".
    G3, slice 2's subscription list lacks `assistant.usage`, `session.usage_checkpoint` and
    `session.compaction_complete` (task 4.1 adds them).
    G4, slice 2's `TurnOutcome` mapping has no rule for a `session.error` that ends `end_turn`, and
    this change needs one for quota.
    G5, slice 2's `parse_copilot_envelope` leaves `WorkerUsage()` empty and fixes event names by
    capture (task 5.4 reads that capture).
    G6, slice 2 D11 records `sample=None`, which this change replaces.
  - **Rebase at IMPL:** tasks 3.1, 4.1, 4.4, 5.1, 5.3, 5.4 and 1.15 name slice 1 and slice 2
    members that exist only in their designs.

## Open questions for R2/R3

- **Q1 (slice 1). Answered in R2, from slice 1's design (unbuilt).** No. `usage_from` is a
  `StreamTransport` post-exit reader, not an adapter factory. The reserved slice-4 members
  `spend_from` and `quota_hold_from` are per-event. D2 now puts the ledger inside
  `copilot_acp.run_turn`, which emits one sample through `cb.on_accounting`, and declares the two
  reserved members superseded (G1). No new adapter member is needed.
- **Q2 (slice 2). Answered in R2, from slice 2's design (unbuilt).** One process per turn (its D3),
  so no cross-run cumulative difference exists (D3). `run_turn` decides `session/new` vs
  `session/load` from `Conversation.provider_session_id`, with the `-32002` fallback to new (its D7).
  The transport, not the executor, knows `session_was_new`, and it passes it to `finish`.
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
- **Q7.** D10's ceiling changes Claude's behaviour in two bands. First, token thresholds that fall
  between 92% and 100% of a known window. Second (found in R2), configured **percent** thresholds of
  93–99, which are lowered to 92. Keep it uniform (R1's choice: a threshold above 92 leaves at most
  3 points before Claude compacts, and one above 95 can never fire in time), or restrict the ceiling
  to runners whose compaction point is below 95?
- **Q8. Answered in R2.** No UI literal assumes 80/92/95. A grep of `components/checkpoints`,
  `AgentSettingsControls.tsx`, `BannerStack.tsx`, `ProjectSettingsPanel.tsx` and
  `components/context` found none. Only `CONTEXT_WARNING_PERCENT = 70`
  (`contextPresentation.ts:7`) exists, which is below Copilot's 77. The Python pin
  `DEFAULT_THRESHOLD_VALUE < FINAL_WARNING_PERCENT < 95` (`hub/tests/test_checkpoint_policy.py:249`)
  still holds, because the constants keep their C=95 values.
- **Q9.** `accounting_snapshot`'s `preferred_display` picks the newest allowance of any runner. D6
  adds the runner name. R2 found the sharper consequence: in a Codex + Copilot project the Copilot
  reading replaces the Codex API-equivalent headline outright (D6). Is a per-runner display (one line
  per provider) the better fix? R1 kept the smaller one, and R2 leaves the decision to R3 or the
  operator.
- **Q10 (R2).** After a process restart and `session/load`, does the first **model** prompt's
  `usage` start from zero? D3's "larger wins" is sound only if it does. R1's evidence is a `/usage`
  slash prompt after load that returned no `usage`, while in the original process slash prompts
  returned the cumulative totals. That is strong evidence, but not a model call. Task 7.3 records the
  prompt result and the per-call sum of the resumed turn. If the result includes the earlier turn,
  D3 must make the per-call sum authoritative on a loaded session.
