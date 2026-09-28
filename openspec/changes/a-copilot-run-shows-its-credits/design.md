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
- `observe_prompt_error(data)` (R3): the `data` of a JSON-RPC error answering `session/prompt`. It
  is read only for D8's structured quota fields;
- `finish(*, session_was_new) -> AccountingSample`: called once, on every return path of `run_turn`
  that produced a session, and passed to `cb.on_accounting`. `session_was_new` is True when
  `run_turn` called `session/new`, including slice 2's `-32002` fallback (its D7). The transport
  knows which call it made. The executor does not.

`finish` has no database, so it returns final **tokens** and **provisional credits**: the last
checkpoint's session totals, the per-call nano-AIU sum, `session_was_new`, and the allowance reading
(D7, D8), possibly without `resetsAt`. The executor settles the credits at run end, in the
finalising session and before `record_turn_usage`, with
`usage_accounting.settle_copilot_credits(db, sample, *, project_id, agent, session_id)` (D4, D8).
It acts on any sample whose `credit_session_new` is not None, and only the ledger sets it. So the
generic RPC executor needs no runner literal. **(R3 correction.)** R2's text keyed the settle on "a
sample that carries a session credit total". The runs that most need settling carry none: the
per-call fallback (D4), whose stored total the settle writes, and a quota refusal on the run's first
call (D8), whose `resetsAt` the settle fills from the prior reading. Keyed on a checkpoint total,
neither branch could fire, while every test seeded with a checkpoint passed. `finish` sets
`credit_session_new` on every sample it returns, checkpoint or not.

A run where `run_turn` raised records no sample, which gives an `unavailable` row, as today: the
executor's pre-spawn `except` records `sample=None` whatever `on_accounting` delivered
(`agent_trigger.py:3256-3263`). Its spend stays in the session's checkpoint, so the next run's
difference (D4) carries it. So `run_turn` must not raise once the ledger has recognised a quota
refusal (D8).

`AccountingSample.merged` carries all five new fields, `credit_session_new` included (R3: R2 listed
only the four persisted ones). Under slice 1's contract (its D3, *run_turn's accounting contract*)
the ledger's sample is the only `on_accounting` call a Copilot run makes. But a merge that dropped
the flag would silently turn the settle into a no-op if anything else ever called it.

**Raw-event subscription is slice 2's list.** Slice 2's design subscribes `session.error` but not
`assistant.usage`, `session.usage_checkpoint` or `session.compaction_complete`. It names the list
`copilot_acp.COPILOT_RAW_EVENTS` and sends it de-duplicated in first-seen order (its D10). Task 4.1
appends all three. Slice 5 subscribes `session.compaction_complete` for its own trigger, and the
de-duplication makes that harmless.

**Why not slice 2's `on_raw_event` (R3).** Slice 2's R2 offers the executor an `on_raw_event(type,
data)` callback and two `TurnOutcome` fields, `prompt_usage` and `session_was_new`, *"so slice 4
extends the executor instead of re-opening the transport"* (its D10). This change does not use
them. To consume them, the generic `_execute_rpc_run` would have to build a Copilot ledger, which is
a runner branch or a new adapter member. Slice 1's D3 rules out both: *"A transport whose usage must
be summed or differenced keeps its own per-run ledger inside `run_turn` and calls `on_accounting`
once."* The ledger reads the same armed dispatch that feeds slice 2's mapper, inside `run_turn`.
See *Required of slices 1 and 2*.

## D3 — Tokens: per-call sum, cross-checked by the differenced prompt result

- **Per-call:** sum `inputTokens`, `outputTokens`, `cacheReadTokens`, `cacheWriteTokens`,
  `reasoningTokens` over this run's `assistant.usage` events, each counted once (dedup by
  `providerCallId` when present, else by `apiCallId`: the same call can reach the Hub only once in
  practice, but the dedup makes a replayed notification harmless). `total = input + output`.
  `input` already includes cache (D3 table), so it is normalised with
  `cache_is_separate_input=False`, the flag Codex uses (`runner_parsing.py:72-126`). Reasoning is not
  added.
- **Key names (review 2026-09-28, finding 7).** The shared normaliser `_accounting_from_dimensions`
  (`runner_parsing.py:83-95`) knows none of Copilot's cache spellings: per call Copilot sends
  `cacheReadTokens`/`cacheWriteTokens`, and the prompt result `cachedReadTokens`/`cachedWriteTokens`
  and `thoughtTokens`. So the ledger maps both to the normaliser's own names before calling it:
  `inputTokens → input_tokens`, `outputTokens → output_tokens`, `cacheReadTokens` and
  `cachedReadTokens → cache_read_tokens`, `cacheWriteTokens` and `cachedWriteTokens →
  cache_write_tokens`, `reasoningTokens` and `thoughtTokens → reasoning_tokens`, `totalTokens →
  total_tokens`. The shared key lists are not widened, so no other runner's parsing changes. Totals
  never depended on this (cache is not added again), but without the mapping the breakdown came out
  None whenever the prompt result won; test 1.3 asserts `cache_read_tokens == 21888` on that path.
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
  (unknown). The recorded totals are those of the source with the larger `total_tokens`, and a tie
  goes to `copilot_calls` (R3: R2 named no tie rule, and acp4 **is** a tie). Its name goes in
  `AccountingSample.source` (`copilot_calls` or `copilot_prompt_result`). A disagreement of more
  than 1% is logged at warning level with both figures, because it is evidence about which lower
  bound is short. Neither is added to the other.
- **The acp4 numbers, recomputed in R3** (log lines 19, 33, 46 for the calls, 52 the checkpoint, 54
  the result; R2's 18/32/45/51/53 are one line early). Input 10988 + 11028 + 11092 = 33108, output
  21 + 38 + 5 = 64, cache read 0 + 10880 + 11008 = 21888, total 33172. The result reads 33108 / 64 /
  33172 / 21888, a tie, so `source == "copilot_calls"`. With call 2 dropped (task 1.3), the calls
  give 22080 + 26 = 22106, and the result's 33172 wins with a 33.4% disagreement logged.
  `copilotUsage.tokenDetails` reproduces each call's nano-AIU exactly: 10988 × 20000 + 21 × 120000 =
  222280000, 148 × 20000 + 10880 × 2000 + 38 × 120000 = 29280000, and 84 × 20000 + 11008 × 2000 +
  5 × 120000 = 24296000. The three sum to 275856000, the checkpoint's total, which displays as `0.28
  AI credits`.
- **Model:** the model with the largest per-call total (as `_claude_model_accounting` does,
  `runner_parsing.py:128-162`). With no per-call events, the model is unknown (`None`).
- **No telemetry at all** (no events, no result usage): `total_tokens` stays None, so
  `record_turn_usage` writes `unavailable` (`usage_accounting.py:36-42`), as for any runner.

## D4 — Credits and premium requests: the session checkpoint, differenced across runs

The credit ledger that survives resume is `session.usage_checkpoint` (session-cumulative). Per run:

- `session_total` = the **last** checkpoint this run received (later replaces earlier). The ledger
  (D2) supplies it.
- `per_call` = the sum of this run's `copilotUsage.totalNanoAiu` (plus compaction's, deduped as in
  D3). It is None when no call reported one.
- `baseline` = 0 if the session was created in this run (`session_was_new`, from the transport,
  D2). Otherwise the `session_nano_aiu_total` / `session_premium_requests_total` of the **last
  written** earlier `turn_usage` row for the same project, agent and provider session that has a
  non-null `session_nano_aiu_total`: `ORDER BY turn_usage.rowid DESC`, as `_approval_outcome` orders
  `spec_document_events` (`api/v1/spec.py:262-281`, `literal_column("….rowid")`).
  **(Review 2026-09-28, finding 3.)** R1–R3 ordered by `observed_at, id`. `observed_at` is wall-clock
  time at flush (`db/models.py:1280`, `_now`), and `id` is a random `short_id`, so a clock that steps
  backwards between two runs of one session makes an older row the "newest". Recomputed (`py -3.11`,
  a scratch simulation of this rule): four runs spending 275856000, 124144000, 100000000 and 50000000,
  with the clock stepped back before run 3, charge run 4 150000000 against the older run 2 total, 650000000
  in all against a real 550000000. Ordered by rowid, the same runs charge exactly 550000000. `turn_usage`
  has a `String` primary key, so it is a rowid table, and a new rowid is always above every existing one
  (SQLite takes max + 1 without `AUTOINCREMENT`). A session's runs are serial, and each run's row is
  written in its finalising commit before the next run of that session can settle, so insertion order
  is run order. A table rebuild (`batch_alter_table` recreate) copies rows with `INSERT … SELECT` in
  rowid order; this change's own migration only adds nullable columns, so SQLite adds them in place.
  The same wall-clock `observed_at` also ties on this machine (15.625 ms resolution, the `spec.py`
  comment), which `id` could not break deterministically either. `MAX(session_nano_aiu_total)` is not
  a fix: after a `/clear` reset it double-charges once the new counter passes the old maximum.
  `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)` reads it by joining
  `turn_usage.run_id` to `runs.id` on `Run.session_id == session_id`. `Run.session_id` is set at
  creation from the resume id (`api/v1/agent_trigger.py:1309`) and rebound by `_bind_session_id`
  (`:3102-3125`). The current run's own row is not written yet, so it is never its own baseline.
  Rows written by crash reconciliation or by the executor's pre-spawn `except` carry no total, so
  they are skipped.
- **Credits are the larger of two lower bounds (R3), as tokens are in D3.** Let `diff =
  session_total - baseline`, defined only when both are known.
  - `diff` defined and `diff >= (per_call or 0)`: `ai_nano_aiu = diff`, and `premium_requests =`
    the premium total minus its baseline when both are known and the result is not negative, else
    None.
  - Otherwise: `ai_nano_aiu = per_call` (None when there is none), and `premium_requests = None`.
    That covers no checkpoint, no baseline, a negative `diff`, and a `diff` smaller than the run's
    own calls.
  - The run stores `session_total` (and its premium total) whenever it saw a checkpoint, whichever
    figure it was charged. Premium requests have no per-call equivalent (`cost` is a multiplier, and
    acp4 charged one premium request for three calls).
- **Why the larger, and not R2's "difference first, per-call only as a fallback".** Take any
  difference that is smaller than the run's own calls: the counter can only have been reset. Its
  causes are `/clear` or `/new` (`help limits`: *"/clear and /new reset used AI credits"*), or a
  checkpoint that restarts per process after `session/load`. The second is the INFERRED row of the
  table, measured only by task 7.3. Under R2's rule a restarted counter gave garbage. `A` ends at
  275856000. A loaded run `B` that really spent 300000000 checkpoints 300000000 in its own process
  and was charged 24144000. One that spent 124144000 was charged nothing (a negative difference gave
  None). Under the larger-of rule both are charged their own calls, 300000000 and 124144000. When
  the counter does continue (the schema's *"for reconstructing aggregate accounting on resume"*),
  `diff >= per_call` always holds (proof below), so the rule is exactly R2's. Under either answer
  to 7.3 the rule never charges twice and never charges a negative amount.
- **But it is not right under both answers, and 7.3 still gates D4 (review 2026-09-28, finding 4;
  R3 had said it no longer did).** Under restart-per-process semantics, a loaded run's checkpoint
  `K'` is that run's whole spend, and the baseline `S` is a figure from another process. When a call
  event is lost, `diff = K' − S` can still be at least the per-call sum `P`, and the run is charged
  `diff`, short by up to `S`. Recomputed: `S` = 100000000, real spend `K'` = 250000000, one call
  event dropped so `P` = 140000000; `diff` = 150000000 ≥ `P`, so D4 charges 150000000 against a truth
  of 250000000. Its premium count, `K'_prem − S_prem`, is meaningless there (0 in this example).
  With no lost event `P = K'` > `diff`, and the per-call branch charges the truth, so the defect
  needs a dropped event (appendix A §A allows it: at most 256 raw events in flight). The spend is
  lost, never doubled. **So:** if 7.3 observes restart semantics, D4 is revised before archive: a
  run on a loaded session charges `max(K', P)` and takes premium requests from `K'_prem` alone, with
  no baseline; tests 1.8(a) and (e) and the credits paragraph of the `usage-accounting` delta are
  rewritten to match, and 1.8(d) becomes the ordinary case. If 7.3 observes a continuing counter, D4
  stands as written. Either way 7.3's figures go in the round log.
- **Never twice, never negative (R3 proof, continuing counter).** Invariant: after each run the
  stored total `S` is at most the real counter `K`, and every credit charged so far is at most `S`
  (equal when no call event was lost). A run with a checkpoint is charged `max(K' − S, P)`, where
  `P <= K' − K <= K' − S`, so the charge is `K' − S` and it stores `K'`: the running charge equals
  `K'`. A run without one is charged `P` and stores `S + P <= K'`. Neither step charges past the
  counter, and every charge is at least 0.
- **A fallback run stores the total it reached (R2, kept).** When a run is charged `per_call` with no
  checkpoint and a known baseline (0 for a new session, or a stored total), it stores
  `session_nano_aiu_total = baseline + per_call` and `session_premium_requests_total = None`. Without
  this, the next run's difference against the older baseline would charge the same credits again.
  The next run's premium requests then come out None, because their baseline is unknown, rather
  than doubled. With no known baseline, or no `per_call`, it stores nothing.

A run that recorded nothing leaves its spend in the next run's difference. That covers a crash, a
Hub restart mid-run, and a `run_turn` that raised. The total stays right, and the attribution moves
one run later. That is accepted and stated, not hidden. Spend that never reached the durable
checkpoint (a process killed before its turn-end checkpoint) is not charged at all. It is lost, and
never counted twice.

`settle_copilot_credits` never raises. A failed baseline read is "no baseline". Any other exception
is logged, and the sample is returned with the ledger's provisional per-call credits (D11).

**Negative figures (review 2026-09-28, finding 12).** The ledger ignores a `totalNanoAiu` or
`totalPremiumRequests` that is negative, non-numeric or a bool, on a call, a compaction or a
checkpoint, exactly as `_token_int` ignores a bad token count. Test 1.8(g) includes one negative
per-call value. With every input non-negative, D4's rule yields no negative charge (a negative
`diff` takes the per-call branch). D5 adds no CHECK constraint for the new columns: that would need
a table rebuild of `turn_usage`, which this change avoids, so non-negativity is the code's guarantee,
not the database's.

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
and **only when non-null**, so a Claude-only or Codex-only project's **screens** look exactly as
they do today.

**Its API responses do not stay byte-identical, and this change says so (review 2026-09-28, Q-b and
finding 9).** A project with no Copilot row gains, with every new key appended after the existing
ones so that key order is otherwise unchanged:

- `ai_nano_aiu: null` and `premium_requests: null` in `project`, in every `agents[]` entry, in
  `GET /accounting/conversations/{id}`, and in every `recent_turns[]` row;
- `runner` inside a `preferred_display` of kind `allowance` (`"claude"` for a Claude reading). This
  is the common case: 345 of the 348 Claude rows on `:8000` carry a reading (review, `mode=ro`);
- `checkpoint_compaction_percent: 95` on every agent bound to a Claude or Codex runner in
  `GET /agents` (null only for an agent with no bound runner, D10);
- `threshold_source` on every `checkpoint_due` broadcast (D10).

`budget` and the `api_equivalent` display are unchanged, and so is `PATCH /accounting/budget`'s
response. Exact-equality assertions that move, found by grep over `hub/tests`: in
`hub/tests/test_accounting_api.py`, `:89` (`data["project"] ==`), `:98` (`data["agents"] ==`),
`:136` (`preferred_display ==` for an allowance, which gains `runner`) and `:368` (the conversation
`response.json() ==`). Task 6.1 **extends** these four with the new keys, never loosens them to
subset checks; that extension is the byte-identity test. Not moving: `:120` and `:308` (`budget`),
`:167` and `:217` (`api_equivalent`). No test asserts a whole `GET /agents` item or a whole
`checkpoint_due` payload (grep; `test_checkpoint_cutover.py:820` reads only `final`).

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
  the refused call was the run's first, from the **project's** newest earlier Copilot reading whose
  `resetsAt` is still ahead. The ledger cannot read that (no database, D2), so it emits the rejected
  reading without `resetsAt`, and `settle_copilot_credits` fills it in at run end from the last
  written (`rowid`, as D4) `turn_usage` row for the project, **any agent**, with `runner ==
  "copilot"`, a dict allowance and a numeric `resetsAt` ahead of now. The dict test is done in
  Python, as `_is_informative` does (`provider_allowance.py:108-119`). With neither, the reading is
  `rejected` with no `resetsAt`: shown as *allowance exhausted*, and not a hold (the existing rule,
  `provider_allowance.py:68-75`, unchanged). Such a reading is still informative, so it ends any
  earlier hold.
  - **Why the project, not the agent (review 2026-09-28, finding 1(b)).** Once a plan is spent, the
    refusal lands on a run's first call, which has no `assistant.usage` and so no snapshot. Keyed on
    the agent, a newly bound Copilot agent, one whose last reading is from last month, or one on a
    plan with no `resetDate` never finds a reset, so its refusal is counted like F355. The Copilot
    quota is per GitHub account, so another agent's reading states the same reset. The hold itself
    stays keyed on the refused agent's name (`provider_allowance.py:122-143`): only the date is
    borrowed. If two Copilot runners of one project ever sign in to different accounts, a borrowed
    date may be the other account's; individual plans all reset at 00:00 UTC on the 1st
    (DOCUMENTED), so the error is bounded by the Business/Enterprise case (Q4). Test 1.9 adds agent
    `b` refused on its first call with agent `a`'s reading ahead: held until `a`'s reset.
  - **Only `resetsAt`, and only when refused (review 2026-09-28, finding 2).** `quota_reading
    (snapshots, *, refused, prior_reading)` consults `prior_reading` only when `refused` is True, and
    copies from it **only `resetsAt`**. `status` is `rejected` because this run was refused, and
    `quota`/`remainingPercentage` come from this run's snapshot or are absent. A run that was not
    refused and saw no qualifying snapshot writes **no** reading (D7), whatever the prior reading
    says. Otherwise an ordinary failure (say a `rate_limit` on the first call) after a month-long
    hold would re-emit the earlier `rejected` reading and renew the hold on a non-quota error. The
    settle likewise fills `resetsAt` only into a reading that is already `rejected`. Test 1.9 pins
    both.
  - **When nothing holds, the input is counted (review 2026-09-28, finding 1(a)).** With no known
    reset, `allowance_refusal` returns None (it needs a numeric `resetsAt`), so `_execute_run`'s
    branch (`agent_trigger.py:2681-2689`), which task 5.3 copies, sets no refusal, and
    `return_run_entries(db, run_id)` counts the attempt. At `RESUME_RETRY_LIMIT = 2`
    (`inbound_queue.py:286`) the conversation's provider session is cleared, which discards the
    Copilot context; at `DELIVERY_ATTEMPT_LIMIT = 3` (`:294`) the input is given up. That is the
    stated consequence of "no reset known", and the `agent-conversation-workspace` delta now says so
    instead of claiming an uncounted return "in every case". Widening the lookup to the project makes
    it rare.
  - **A reset the server applies late (review 2026-09-28, finding 13).** A refusal just after
    `resetDate` (for example on the first call at 00:00:30 on the 1st, before Copilot's server has
    reset) finds only a past `resetsAt`, which is not filled. The reading is `rejected` without
    `resetsAt`: no hold, and the input is counted as above. (The review said a 60 s floor hold
    starts. That happens only when the reading carries a past `resetsAt`, which here it does not:
    only a refusal on a later call of a run whose own earlier snapshot named the past date gets the
    `HOLD_FLOOR` hold, `provider_allowance.py:100`, and it is still counted, because `resets_at >
    run.ended_at` fails.) This is Claude's existing behaviour for a past reset; no change.
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
- **A refused turn must not raise either (R3 correction).** D8 counts the quota fields on a
  `session/prompt` JSON-RPC error's `data`. As slice 2 designs its client, that error is raised:
  `ACPProcess.request` raises `CopilotACPError(code=…)` for any error response, and `CopilotACPError`
  subclasses `AppServerError` (its D12). A raise lands in the executor's pre-spawn `except`
  (`agent_trigger.py:3244`), which records `sample=None` and calls `return_run_entries(db, run_id)`
  with no refusal (`:3256-3266`). No reading is recorded, nothing holds, and the input is counted,
  so that clause could never fire. The same happens if the process exits after a quota
  `session.error` but before the prompt returns. So once the prompt has been written, `run_turn`
  handles any exception from the prompt's wait in one step. It passes the error's `data` to
  `observe_prompt_error`, when there is one. If the ledger has then recognised the refusal, it calls
  `cb.on_accounting(ledger.finish(…))` and **returns** the failed outcome instead of raising. Any
  other error after the prompt is written also ends in slice 2's returned `failed` outcome, with no
  refusal recorded: that is slice 2's contract since its D12 R3 (contract reconciliation, 2026-09-28; R3 here said it was re-raised). A stop still wins: an
  `interrupted` outcome stays `stopped` and keeps its input. This needs `CopilotACPError` to carry
  the error's `data` as well as its `code` (*Required of slices 1 and 2*).
- **The first real refusal is captured verbatim.** Until one is observed, the Copilot executor logs
  every `session.error` payload at warning level, and task 8.2 asks the operator to paste the first
  quota one into FINDINGS. That is how D8's recognition is confirmed or corrected.

**Is a month-long hold wanted?** On an individual plan a refusal holds the queue until the 1st of
next month, 00:00 UTC. The operator's probe-once rule (`operator_would_probe`,
`provider_allowance.py:192-201`) still lets their own message through. The operator can end the
hold sooner by buying credits and messaging the agent, or by rebinding the agent **and then
messaging it**. Rebinding alone writes no `turn_usage` row, so the hold, keyed on the agent's name
(`provider_allowance.py:122-143`), stays, and loops and jobs stay blocked (`scheduler.py:1182`,
`:1740`); only operator input served by the new runner ends it, as the main spec already says
(`agent-conversation-workspace/spec.md:2489-2492`; review 2026-09-28, finding 8). This matches the
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
  to the C=95 values, for any other reader. The two new fields default to those C=95 values
  (`final_warning_percent = FINAL_WARNING_PERCENT`, `compaction_percent = 95`), after
  `threshold_source`, because `hub/tests/test_checkpoint_policy.py:184` and `:214` construct
  `CheckpointPolicy(...)` directly with the six existing fields.
- **A configured threshold past the final-warning point is lowered to it.**
  - In percent mode, when the value is above `final_warning_percent`, it becomes `final_warning_percent`,
    and `threshold_source` becomes `"runner_ceiling"`. **For Claude this also lowers a configured
    93–99% to 92%.** `threshold_error` accepts up to 99 (`checkpoint_policy.py:125-129`). R1 stated
    only the token-mode change, and this is a second Claude behaviour change (Q7). **R3 measured
    its reach:** a `mode=ro` read of the operator's `:8000` database and of the trial database found
    no project and no agent with a configured threshold (every `checkpoint_threshold_mode` is NULL).
    All seven projects use the built-in 80/70/92, so none of the three Claude bands changes anything
    configured on this machine today. It can change a PyPI user's configuration, so Q7 is an
    operator question (review 2026-09-28), and the lowering is stated in the agent's and the
    project's checkpoint settings (*Where the lowering is stated*, below).
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
  - **Token-mode notes (R3, added).** R2 put the ceiling into the threshold half of
    `should_request_notes`, which stops the notes requests. It left the notes half alone, so they
    never start. Example: a project token threshold of 150000 with notes at 140000, and a Copilot
    agent whose window is 128000 (acp4's `maxPromptTokens`). The checkpoint now fires at 77%, about
    98600 tokens, but 140000 is never reached, so no notes are ever asked for and the checkpoint is
    generated from none. So, in token mode and only when a notes value is set, the notes half also
    counts as reached at `percent >= final_warning_percent − 10`. That is the percent-mode result
    for a notes value past the ceiling (the lowered threshold minus 10): 67 for Copilot and 82 for
    Claude. It is one line in `should_request_notes`, and like the threshold ceiling it needs a
    reading that carries `percent`. No notes value, no notes, as today.
  - **A threshold at the ceiling leaves no room for a dismissal.** With the threshold equal to the
    final warning, a conversation dismissed at the ceiling gets its final warning on the next
    reading. That is what a configured 92% does for Claude today, and it is the design's intent:
    past the final-warning point a dismissal is not respected.
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
- **Where the lowering is stated (review 2026-09-28, finding 5).** R1–R3's requirement said *"stated
  wherever the threshold is reported"*, and D10 built only the Copilot line above. Claude's own
  lowering (a configured 93–99% becoming 92) travelled only on the `checkpoint_due` payload, which no
  UI reads, and `ProjectSettingsPanel` showed a project threshold of 80 with nothing saying it is 77
  for the project's Copilot agents. Now, with the requirement narrowed to the two settings surfaces:
  - **Agent settings.** The line also appears whenever the agent's effective threshold is below its
    configured one, for **any** runner: its own override, else the project's threshold, in percent
    mode and above `checkpoint_compaction_percent − 3`. For Claude: *"This agent's threshold of 96%
    is lowered to 92%: Claude compacts at about 95% of its window."* A token threshold cannot be
    compared with a percent in the UI, so for one the line reads *"This agent's checkpoint fires at
    <N> tokens or at <C − 3>% of its window, whichever comes first"*, shown whenever the token-mode
    ceiling applies to the runner (every runner under Q7's current answer). The comparison is one
    helper, `runnerCeilingNote(compactionPercent, mode, value)`, beside
    `describeThreshold` (`components/environment/describeThreshold.ts`), used by both surfaces.
    `AgentSettingsControls` already has the agent's override; the project threshold comes from
    `useProjectSettings`.
  - **Project settings.** `ProjectSettingsPanel.tsx` (the checkpoint threshold row, `:237-259`) reads
    the project's agents (`useAgents`, `api/agents.ts:180`) and, when the project's percent threshold
    is above any bound agent's `checkpoint_compaction_percent − 3`, shows one line per compaction
    point: *"Lowered to 77% for agents on a runner that compacts at about 80% (cop)."*
  - A Claude or Codex project with no configured threshold shows neither line (80 < 92), so its
    screens stay identical. Test 1.18 covers the Claude 96 → 92 line, the Copilot line, the project
    panel line, and the no-line default.
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
  **Review 2026-09-28, finding 10, answered and not applied to the string.** The label's *"no
  reported cost"* is imprecise for a Copilot turn, which did report a cost, in credits. Rewording it
  to *"no reported API-equivalent cost"* would change a string every Claude and Codex project shows
  today (pinned at `accountingPresentation.test.tsx:132`, `:261`) to fix a case that is reachable only
  when a Copilot project's newest 50 rows carry no allowance reading (a plan with no qualifying
  snapshot, Q4, or BYOK, Q11). It is left to test-guide Human-only item 2, which now names it. The
  `usage-accounting` ADDED requirement now says explicitly that credits are the provider's report of
  consumption, not a monetary figure, and so outside *"Allowance and currency presentation cannot
  imply billing"*, although 1 credit = $0.01 (DOCUMENTED).
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

## Required of slices 1 and 2 (R3, the cross-slice contract)

Slice 1 (`each-runner-cli-is-one-adapter`) is the authority on adapter and transport member names,
and slice 2 (`a-copilot-agent-runs-over-acp`) on what the ACP client and executor provide. This
change uses their names, as their designs stood on 2026-09-28, still unbuilt. Each item below is
**needed**, **already provided**, **owned here**, or **not needed**.

**Slice 1**

1. *Already provided.* `RpcTransport.run_turn(req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome`,
   with the accounting contract *"keeps its own per-run ledger inside `run_turn` and calls
   `on_accounting` once"* (its D3). The executor's `_on_accounting` merges with
   `AccountingSample.merged` (Codex today: `agent_trigger.py:3173-3177`).
2. *Already provided.* `spend_from` and `quota_hold_from` are struck from its D16 table as superseded
   by this change's ledger. Nothing further is needed (R2's gap G1 is closed).
3. *Owned here.* `RunnerAdapter.compaction_percent: ClassVar[Optional[int]]`. Slice 1 keeps it
   deferred to this slice (its D16 row, R2), so task 3.1 adds it **unconditionally**, with Claude 95,
   Codex 95 and Copilot 80, and extends slice 1's conformance test (its task 1.5) to require it on
   every `ADAPTERS` entry.
4. *Owned here.* The run-end refusal branch in `_execute_rpc_run`. Slice 1 states it does not add it
   (its D16 row). This is task 5.3. Also task 5.1: `settle_copilot_credits` before `record_turn_usage`
   in the finalising session, and `runner=adapter.name`.
5. *Needed.* `_execute_rpc_run` keeps the pre-spawn `except` tuple `(FileNotFoundError,
   AppServerError, asyncio.TimeoutError, OSError)` and its `sample=None` recording (its D15). D2 and
   D8 rely on a raise recording nothing, which is today's behaviour.

**Slice 2**

6. *Needed, and provided by its D10.* `copilot_acp.COPILOT_RAW_EVENTS` is extendable and is sent
   de-duplicated. Task 4.1 appends `assistant.usage`, `session.usage_checkpoint` and
   `session.compaction_complete`.
7. *Needed.* Inside `copilot_acp.run_turn`, one armed dispatch point for raw events: the one that
   feeds the mapper after the `session/prompt` request is written (its D7 arming). Task 4.4 calls
   `ledger.observe_event(type, data)` there, and `ledger.observe_prompt_result(result.get("usage"))`
   where the prompt result is read.
8. *Needed, and provided by its D7.* `run_turn` knows whether it called `session/new`, including
   the `-32002` fallback, and passes it to `ledger.finish(session_was_new=…)`.
9. *Needed, and provided by its D12 (R3).* `CopilotACPError` carries the JSON-RPC error's `data`
   (as `.data`) beside `.code`, so that D8 can read the structured quota fields of a `session/prompt`
   error. (contract reconciliation, 2026-09-28: R3 here said slice 2 names only `code`; slice 2's R3 added `.data`.)
10. *Owned here.* Slice 2 says `on_accounting` is *"never called"* and records `sample=None` (its
    D11, D18). Task 4.4 replaces that: one `cb.on_accounting(ledger.finish(…))` on every return path
    once a session exists. So is the D8 rule that a recognised quota refusal returns
    `TurnOutcome(status="failed")` whatever the stop reason. (contract reconciliation, 2026-09-28: slice 2's D12 R3 now returns a
    `failed` outcome, instead of raising, for **every** failure after the prompt is written, and fails
    the turn on an armed `session.error` whatever the stop reason (its D10). So "instead of raising"
    is slice 2's general rule, and this change adds only its ledger, `observe_prompt_error` and the
    recognised-refusal hold on top.)
11. *Not needed.* The `on_raw_event` callback and the `TurnOutcome.prompt_usage` /
    `TurnOutcome.session_was_new` fields slice 2's R2 added for this slice (its D10, D18). Using them
    would put a Copilot ledger in the generic executor (D2). Slice 2's R3 dropped all three, and
    slice 1 does not add `on_raw_event` (contract reconciliation, 2026-09-28).
12. *Needed, and provided by its task 1.2.* The captured `-p --output-format json` stream that
    `parse_copilot_envelope` is tested against. Task 5.4 reads `session.shutdown` from it only if the
    capture contains it. The parser keeps returning `WorkerUsage()` until then, as slice 2 says.

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
- **R3 (2026-09-28).** Task 0.2: a second re-derivation of D3, D4 and D10 (and of R2's D8
  correction), from the code at master `fc33ff9` and the acp4 transcript. R2's entry was read only
  after the derivation, to compare against it. Slices 1–3 are still unbuilt, so every "(rebase at
  IMPL: …)" mark stays; each was re-checked against the sibling designs as they stood that day.
  - **Read (code):** `usage_accounting.py` (whole, 224 lines, with `unpriced_turns`);
    `runner_events.py:225-318`; `checkpoint_policy.py` (whole); `checkpoint_trigger.py:1-60`,
    `:100-320`; `provider_allowance.py:40-210`; `api/v1/agent_trigger.py:1305-1314`,
    `:2640-2760`, `:3095-3130`, `:3225-3380`; `runner_parsing.py` (the function map);
    `db/models.py` (`observed_at` defaults, `Agent.runner_id`); `api/v1/agents.py:400-412`,
    `:544-552`; the `resolve_policy`/constant callers (grep); the UI's readers of `threshold_value`
    (grep: none reads the `checkpoint_due` payload's value). **Designs:** slice 1 `design.md` D3
    (`:125-176`) and D16 (`:420-435`); slice 2 `design.md` D3, D7 (`:400-425`), D10 (`:660-712`),
    D11, D12 (`:720-742`), D17-D18 (`:940-1000`), its route table and cross-slice notes. **Data:**
    `mode=ro` reads of `~/.agentweave/hub/data/agentweave.db` (`:8000`) and the trial database for
    configured checkpoint thresholds and runner CLIs.
  - **Computed (acp4, log lines 19/33/46 calls, 52 checkpoint, 54 result):** tokens 33108 / 64 /
    21888 / 33172 both ways (a tie). nano-AIU per call from `tokenDetails` × `costPerBatch/batchSize`:
    222280000, 29280000 and 24296000, which sum to 275856000 = the checkpoint = `0.28 AI credits`.
    Calls 1 + 3 alone give 22106 tokens, 33.4% short of the result. Newest `chat` snapshot 96.5,
    reset 2026-10-01T00:00Z = 1790812800. D10: C=95 gives 80/70/92, C=80 gives 65/55/77, and the
    notes ceiling (final − 10) is 82/67. Task 1.13's readings: 66 ≥ 65 is due for `cop`; 66 is
    below both 70 and 80 for `cla`; a dismissed 78 ≥ 77 gets the final warning.
  - **Attack sequences on D4, under a checkpoint that continues after a load (K = the real
    counter):**
    - S1: new A (checkpoint 275856000/1), then loaded B (checkpoint 400000000/2, calls
      124144000). A is charged 275856000/1.0 and B 124144000/1.0. The charges sum to 400000000,
      equal to K. Correct under R2 and R3.
    - S2: new A is stopped with no checkpoint (calls 275856000), then B as in S1. A is charged
      275856000 and stores 275856000/None, and B is charged 124144000 with premium None. The
      credits are exact. One premium request is unattributed, and none is doubled.
    - S3, a Hub restart mid-run: A as in S1. B is reconciled with no totals, and its spend reached
      the checkpoint. C is loaded with checkpoint 450000000/3 and calls 124144000. C is charged
      174144000/2.0, so B's spend moves to C and is counted once. If B died before its turn-end
      checkpoint, its spend is never counted, and still never twice.
    - S4: B's `run_turn` raises after the prompt, so the pre-spawn `except` records `sample=None`.
      Same outcome as S3.
    - S5: B fails without a quota refusal, returns a failed outcome with its checkpoint, and is
      charged normally. Its requeued input's run uses B's total as its baseline, with no double
      count.
    - S6: the `-32002` fallback gives `session_was_new=True` and baseline 0, correct whatever the
      old id's rows say.
    - The invariant proof is in D4.
  - **Attack sequences on D4, under a checkpoint that restarts per process (the INFERRED row):**
    - S7: A = 275856000. Loaded B really spends 124144000, so its checkpoint reads 124144000. Under
      R2 the difference is negative, so B is charged **None** and 124144000 is lost. Under R3 B is
      charged 124144000.
    - S8: loaded B really spends 300000000. Under R2 B is charged **24144000**, 275856000 too little.
      Under R3 it is charged 300000000.
    - In S7 and S8 R2 was never negative and never double, but wrong, and 7.3 was its only guard.
    - S9: `/clear` resets the counter mid-session. It behaves like S7.
  - **Attack sequences on D2/D8:**
    - S10: a quota refusal on the run's first call. There is no checkpoint and no call, so the sample
      carries no session total. Under R2's D2 text the settle skipped it, so its `resetsAt` was
      never filled from the prior reading: no hold ever, while 1.9's seeded test (checkpoint
      present) passed. Fixed by keying the settle on `credit_session_new`.
    - S11: a quota refusal arriving as a `session/prompt` JSON-RPC error. Slice 2 raises
      `CopilotACPError`, and the pre-spawn `except` records `sample=None` and counts the input.
      D8's clause could never fire. Fixed in `run_turn` (D8, task 4.4, test 1.15(a)).
    - S12: a quota `session.error`, then the process exits. The same path as S11, with the same fix.
  - **Agreed with R2, re-derived independently:**
    - D3's lower-bound argument. Both figures are this run's, and the larger is the better bound.
      Only the tie rule was missing.
    - The ceiling cannot live in `crosses`: it takes no policy and serves the notes point too
      (`checkpoint_policy.py:156-172`, `:209-219`).
    - The percent clamp lowers a Claude 93–99 to 92.
    - The fallback-store correction to D4.
    - The requirement that a refused turn end `failed` (`agent_trigger.py:2684-2689`, `:2719-2723`).
    - The baseline join on `Run.session_id`, rebound by `_bind_session_id` (`:3102-3125`).
  - **Disagreed with R2, and changed:**
    1. D4: "difference first; a negative difference is None" becomes the larger of the difference
       and the per-call sum, with premium requests only from the difference. The rule is now correct
       whichever way 7.3 answers, and 7.3 no longer gates D4. Tests 1.8(a)–(f) are rewritten with
       fixtures chosen so that either single-source rule fails.
    2. D2 and tasks 4.3/5.1: the settle is keyed on `credit_session_new`, not on a session total
       (S10). `merged` carries the flag.
    3. D8: the JSON-RPC-error route (S11, S12). `observe_prompt_error` is added. Slice 2's
       `CopilotACPError` must carry `.data`.
    4. D10: the token-mode notes point gets the `final − 10` ceiling. R2 stopped notes at the
       ceiling but never started them.
    5. D3: the tie goes to `copilot_calls`, and test 1.1 asserts it.
    6. References: the acp4 line numbers are 19/33/46/52/54, not R2's 18/32/45/51/53. `Run(…,
       session_id=…)` is at `agent_trigger.py:1309`, not `:1310`.
    7. Spec deltas: `usage-accounting`'s MODIFIED text still said the prompt result is "used only
       as the difference from the previous prompt result in that process", with a scenario charging
       a *second run* in the same process. That contradicts D3 since R2 (one process per turn; test
       1.4 keeps the later result). It is rewritten, and the credits rule and its scenarios now
       state the larger-of rule. `agent-conversation-workspace` covers the error-response refusal,
       and `conversation-checkpoint` the token notes point.
  - **Contract resolutions** (the new *Required of slices 1 and 2* section):
    - G1 is closed: slice 1 struck `spend_from`/`quota_hold_from`.
    - G2 is closed: slice 1's D3 now states the transport-ledger accounting contract.
    - G3 is answered: `COPILOT_RAW_EVENTS` is named and de-duplicated, and task 4.1 appends three.
    - G4 and G6 are owned here (task 4.4).
    - G5 is unchanged.
    - New: slice 2's `on_raw_event` and `TurnOutcome.prompt_usage`/`session_was_new` are not
      needed, and using them would put a runner branch in the generic executor. `CopilotACPError.data`
      is needed.
    - `compaction_percent` stays this change's (task 3.1), as slice 1's D16 row now says.
  - **Open questions:**
    - Q7 is answered on evidence: no configured threshold exists on either database, and the
      uniform rule is kept.
    - Q9 is carried to the operator: it is a product choice, reachable only with Codex and Copilot
      in one project.
    - Q10 is carried and narrowed to tokens, because credits no longer depend on it.
  - **Route-raises, re-asked:**
    - Only S11 was a route whose raise silently cancelled a promised behaviour. It is fixed.
    - `settle_copilot_credits` and `finish` never raise (D11).
    - `consider` resolving the runner adds one `db.get`, and `consider_from_reading` already
      swallows.

- **Contract reconciliation, 2026-09-28** (a textual pass over the five slices' contract sections after their
  concurrent R2/R3 rounds; not a design round; no code read). Changed here:
  - *Required of slices 1 and 2* item 9: `CopilotACPError.data` is provided by slice 2's D12 R3.
  - Items 10 and 11: slice 2 now returns `failed` for every failure after the prompt; `on_raw_event`,
    `prompt_usage` and `session_was_new` are dropped.
  - D8 and tasks 1.15(a), 4.4: an unrecognised post-prompt error ends in slice 2's returned `failed` outcome
    (no refusal), not a re-raise; the `rate_limit` case asserts a returned outcome with no hold.
  - Q11: slice 5's BYOK-credits request (its 4.3) carried as an open question.

- **Review fixes, 2026-09-28** (task 0.3: Opus adversarial review
  `spec-queue/tracks/reviews/ghcp-s4-2026-09-28.md`, APPROVE WITH FIXES, against master `450de52`).
  Each should-fix was re-verified before it was applied.
  - **1 (should-fix), applied: (a) and (b).** Re-read `agent_trigger.py:2667-2743`,
    `provider_allowance.py:60-80` and `inbound_queue.py:286`, `:294`: with no `resetsAt` no refusal
    is set and the input is counted, the session cleared at attempt 2 and the input abandoned at 3.
    The `agent-conversation-workspace` delta no longer says "in every case"; the uncounted return is
    conditional on a hold, and the counted consequence is stated, with a scenario. D8's prior-reading
    lookup is widened to the project's newest Copilot reading with a reset ahead (the quota is per
    account); a scenario and a 1.9 case (agent `b` held on agent `a`'s reset) are added.
  - **2 (should-fix), applied.** D8 now says `prior_reading` is consulted only when `refused`, and
    only for `resetsAt`; a non-refused run with no snapshot writes no reading. Two 1.9 cases and a
    spec scenario ("an earlier refusal is not renewed by an unrelated failure") are added.
  - **3 (should-fix), applied with the monotonic order.** Recomputed with a `py -3.11` scratch
    simulation of D4's rule: `observed_at` order charges 650000000 against a real 550000000; `rowid`
    order charges 550000000. D4's baseline is now `ORDER BY turn_usage.rowid DESC` (precedent:
    `api/v1/spec.py:262-281`), the spec states "written last, not latest clock", and test 1.8(h) seeds
    a stepped-back clock. Not the review's option (b) (assume a monotone clock), which leaves the
    defect; not its option (a) (a chain column), which a rowid order makes unnecessary.
  - **4 (should-fix), applied.** Recomputed: 150000000 charged against a real 250000000 under restart
    semantics with one lost call event. D4 now says the rule never double-charges or goes negative
    under either answer, but is right under only the continuing one; 7.3 gates D4 again, with the
    revision stated (`max(K', P)`, premium from `K'`). Task 7.3 and test-guide item 5 corrected.
  - **5 (should-fix), applied (the review's options (a) and (b) both).** The requirement names the
    two settings surfaces instead of "wherever the threshold is reported", and states Claude's
    93–99 → 92. The agent line appears whenever the effective threshold is below the configured one,
    for any runner; `ProjectSettingsPanel` gains a line when any agent's runner lowers the project
    threshold. Test 1.18 extended. Because it changes PyPI users' configured behaviour, Q7 is
    re-opened as an operator question with three answers.
  - **Q-b (byte identity), applied.** D6 now lists every key a Claude/Codex project's API responses
    gain and the four exact-dict asserts that move (`test_accounting_api.py:89`, `:98`, `:136`,
    `:368`); the `usage-accounting` delta separates screens (unchanged) from responses (gain empty
    fields); test-guide item 3 lists all of them; task 6.1 names the four asserts.
  - **6 (note), applied.** The denominator risk is in Q7.
  - **7 (note), applied.** D3 names the Copilot keys and maps them to the normaliser's names in the
    ledger (`runner_parsing.py:83-95` re-read: no match today); test 1.3 asserts `cache_read_tokens`
    on the prompt-result path.
  - **8 (note), applied.** D8 and Q6 say "rebind and then message"; the delta says rebinding alone
    does not end a hold.
  - **9 (note), applied.** See Q-b; task 6.1.
  - **10 (note), answered, string not changed.** Rewording the label would change every Claude/Codex
    screen that shows it (two pinned UI tests) for a rarely reachable Copilot case; D12 and
    Human-only item 2 name it, and the ADDED requirement says credits are not a monetary figure.
  - **11 (note), applied.** Test 1.10 asserts `project_budget_state(...)["exhausted"] is False` at
    `token_budget = 1801`; a spec scenario covers the scheduling gate.
  - **12 (note), applied.** The ledger ignores negative credit figures; D5's lack of a CHECK is
    stated; test 1.8(g).
  - **13 (note), answered, with one disagreement.** Stated under D8. The review said a 60 s floor
    hold starts; for a first-call refusal the reading has no `resetsAt`, so `hold_for_reading`
    returns None and nothing holds. The floor applies only when the run's own earlier snapshot named
    the past date.
  - **Also found while applying:** `CheckpointPolicy(...)` is constructed directly at
    `test_checkpoint_policy.py:184`, `:214`, so D10's new fields get C=95 defaults.
    `provider_allowance._newest_informative` (the existing Claude hold) also orders by
    `observed_at` and has the same clock hazard; out of scope here, passed on to be filed as a finding.

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
  holding? D1–D6 do not answer this. For the answer (review 2026-09-28, finding 8): rebinding the
  agent to another runner does **not** end the hold by itself; the operator must rebind and then
  message the agent, and until then its loops and jobs stay blocked too.
- **Q7.** D10's ceiling changes Claude's behaviour in two bands. First, token thresholds that fall
  between 92% and 100% of a known window. Second (found in R2), configured **percent** thresholds of
  93–99, which are lowered to 92. Keep it uniform (R1's choice: a threshold above 92 leaves at most
  3 points before Claude compacts, and one above 95 can never fire in time), or restrict the ceiling
  to runners whose compaction point is below 95? **R3: answered on evidence, with the uniform rule
  kept.** R3 added a third band: token-mode notes values past 82% of a known window (D10). No project
  or agent on `:8000` or on the trial Hub configures a threshold (D10, `mode=ro` read, 2026-09-28), so
  none of the three bands changes anything configured today. For a Claude threshold above 95 the
  uniform rule is the only one that fires before the loss. Restricting it would keep an
  unreachable threshold unreachable for Claude alone. The operator can still overrule this at the
  0.3 review or in APPROVALS. If they do, the change is one condition,
  `compaction_percent < 95`, in front of the three ceilings.
  **Review 2026-09-28 (findings 5, 6): re-opened as an operator question.** The evidence covers this
  machine only. For a PyPI user it lowers a configured Claude percent threshold of 93–99 (and a notes
  value of 92 or more, which becomes 82), fires a token threshold set above 92% of the window at 92%
  (in `automatic` mode that **bills a checkpoint generation** earlier than configured), and asks for
  token-mode notes from 82%. Those are behaviour changes for existing users, so the operator decides.
  A further risk for the token band: token mode exists for windows the Hub cannot trust
  (`checkpoint_policy.py:8-11`, `:163-168`), and the token ceiling trusts the reading's `percent`. If
  that denominator is wrong, say a catalog limit of 200k on a 1M session, a token threshold of 600k is
  overridden at 184k. Three answers: (a) uniform, as designed (the default until answered); (b) the
  percent ceiling for every runner, the token ceilings only for runners that compact below 95, which
  removes the denominator risk for Claude and keeps Copilot's fix; (c) all three ceilings only below
  95. Each is one condition. The lowering is stated on screen under any answer (D10, finding 5).
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
  operator. **R3: carried to the operator, with a reason.** It is a choice about what the Budgets
  headline is for, not a fact the code can settle. Both answers are consistent with `usage-accounting`,
  and the smaller one is not wrong, only lossy. It is reachable only in a project that runs both
  Codex and Copilot, and Codex is undrivable on this machine since 2026-08-29. So it can wait for
  the 0.3 review without blocking IMPL. The per-runner display would be additive (a list beside
  `preferred_display`), so choosing it later rewrites no data.
- **Q10 (R2).** After a process restart and `session/load`, does the first **model** prompt's
  `usage` start from zero? D3's "larger wins" is sound only if it does. R1's evidence is a `/usage`
  slash prompt after load that returned no `usage`, while in the original process slash prompts
  returned the cumulative totals. That is strong evidence, but not a model call. Task 7.3 records the
  prompt result and the per-call sum of the resumed turn. If the result includes the earlier turn,
  D3 must make the per-call sum authoritative on a loaded session. **R3: carried, and narrowed to
  tokens.** Credits no longer depend on it: D4's larger-of rule is correct whether the session
  checkpoint continues after a load or restarts. Tokens still do, because no stored token baseline
  exists to difference against. R3 found no way to tell "the result includes history" from "call
  events were dropped" inside `finish`, where there is no database. The evidence stays as R2 stated
  it: after a load, the slash prompt that had returned the cumulative totals in the original process
  returned no `usage` at all. That points to a per-process counter that starts empty. Task 7.3
  remains the gate for D3.
- **Q11 (contract reconciliation, 2026-09-28, carried from slice 5's *Required of slices 1–4* 4.3).** Under BYOK a Copilot
  run's credits are probably 0 and the provider bills tokens (slice 5's open question 6). This design
  does not mention BYOK, so a BYOK run would show 0 credits as if the turn were free. Not a member or
  field of the contract, so not settled here: decide at the 0.3 review whether a provider runner
  (`runners.provider_config` set) shows credits at all.
