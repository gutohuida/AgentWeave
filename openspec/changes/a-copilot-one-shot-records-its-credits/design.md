# Design — a Copilot one-shot records its credits

Re-verified at `957fc84` (2026-10-03, R1), `9d1f617` (R2), `3233108` (R3) and `0b784b1` (the Opus review). Labels follow the archived
`a-copilot-run-shows-its-credits`: **MEASURED** is read from the capture or the code today, and
**UNVERIFIED** has not been observed.

## The evidence

**The capture** (`hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`, slice 2's task 1.2,
2026-09-29). It is a real `copilot -p "Reply with the word ok" --output-format json` on the Free
plan's Auto model (`mai-code-1.1-flash`). It has 15 lines, in this order (MEASURED):
`session.info`, `session.auto_mode_resolved`, `session.mcp_servers_loaded`, `session.tools_updated`,
`user.message`, `assistant.turn_start`, `model.call_start`, `assistant.message_start`,
`assistant.message_delta`, `model.call_finished`, `assistant.message`, `assistant.turn_end`,
**`session.usage_checkpoint`**, `assistant.idle`, `result`.

- `session.usage_checkpoint.data` = `{"totalNanoAiu": 32840000, "totalPremiumRequests": 1,
  "modelCacheState": [], "promptCacheBreakState": [...]}`.
- `result` = `{"sessionId": "48580219-…", "exitCode": 0, "usage": {"premiumRequests": 1,
  "totalApiDurationMs": 1023, "sessionDurationMs": 2729, "codeChanges": {...}}}`. It has no `data`.
- There is **no** `assistant.usage`, **no** `session.shutdown` and **no usage token count**
  (no input/output/total on any line's `data` or `usage`). The stream does carry ephemeral events
  (`"ephemeral": true` on `session.info`, the message delta and others), so the absence is not an
  ephemeral filter hiding them.
- *(R2 correction.)* The checkpoint's `data.promptCacheBreakState[0].models["mai-code-1.1-flash"]`
  is a prompt-cache diagnostic. It carries `prompt_tokens: 1612`, `tool_tokens: 0`,
  `frontier_tokens: 0`, `cache_read: 0`, `cache_write: 0`, and 18 `system_segments`, each with
  its own `tokens`. R1's "no token count on any line" missed these (`grep -o '"tokens"'` counts 18
  in line 13). There is still no output or completion count anywhere, so no total can be formed.
  D3 says why none of it is read.

**The parser today** (`runner_adapters/copilot.py:96-130`). It reads `assistant.message.content` and
`session.error`, and returns `WorkerUsage()` on all three exits (failure, no answer, answer).

**The writer today** (`worker.py:265-311`). `_record` already writes
`ai_nano_aiu=result.usage.ai_nano_aiu` and `premium_requests=result.usage.premium_requests`.
`test_a_workers_copilot_credits_reach_its_invocation_row` (`hub/tests/test_worker.py:574`) proves
that a parser which fills them reaches the row. It does so with a monkeypatched parser.

**The run ledger's rule** (`copilot_usage.py:181-185`, `:54-60`). On `session.usage_checkpoint` it
replaces its checkpoint with `_nonneg_number(data["totalNanoAiu"])` and
`_nonneg_number(data["totalPremiumRequests"])`. A bool, a non-number or a negative value becomes
None. The last checkpoint wins.

## D1 — read the last `session.usage_checkpoint`

`parse_copilot_envelope` keeps the most recent checkpoint's two figures. When the loop ends,
`ai_nano_aiu = int(nano)` if the figure is known, and `premium_requests = float(premium)` if that
one is known. Each field is independent: a checkpoint with a good `totalNanoAiu` and a negative
`totalPremiumRequests` records the credits and leaves the premium requests unknown.

**Why the last one, and why it is the whole charge.** The checkpoint is session-cumulative (the
archived D2's premise, which the run ledger is built on). A one-shot is a fresh session:
`copilot_one_shot_command` builds `copilot -p <prompt> <COPILOT_ONE_SHOT_FLAGS> [--no-custom-instructions] [--model m]`,
and none of those flags resumes anything. So the session's final cumulative total is the process's
total. More than one checkpoint in a single one-shot (a retry, an automatic compaction) is
UNVERIFIED. If it happens, the last checkpoint is still the cumulative total, and taking it is
correct. Summing the checkpoints would double-count.

**A later checkpoint without a figure.** If a later checkpoint carries `totalNanoAiu` that is
unusable (missing, bool, negative), the field becomes unknown, exactly as the run ledger does: the
ledger replaces its whole `_Checkpoint` on each event. The two readers agree, by construction (D2).

## D2 — one helper, two callers

`copilot_usage.py` gains a public, stdlib-only function:

```python
def checkpoint_totals(data: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    """(totalNanoAiu, totalPremiumRequests) of one `session.usage_checkpoint`, each through
    `_nonneg_number`, then refused (None) unless `value <= 2**53 - 1` (the review's plausibility
    ceiling, one constant for both figures). The comparison is the whole check: it is False
    for NaN and both infinities, and it never raises."""
```

*(Opus review.)* The ceiling was R3's `2**63 - 1` for `totalNanoAiu` and `sys.float_info.max`
for `totalPremiumRequests`, the largest each column can store. That is not enough, as the next
paragraphs explain. The comparison argument below is R3's, and it holds unchanged for the new
constant.

**One comparison, not `math.isfinite` (R3).** R2 specified `_nonneg_number`, then
`math.isfinite`, then the bound. That helper raises. `json.loads` reads an integer literal of up
to 4300 digits as a Python `int` (longer ones raise `ValueError`, which the parser's existing
`except ValueError` skips). An `int` of more than 308 digits passes `_nonneg_number`, and then
`math.isfinite(10**400)` raises `OverflowError: int too large to convert to float`, and so does
`float(10**400)` (MEASURED under `py -3.11`). So `"totalPremiumRequests": 1000…0` (400 digits)
would escape R2's helper. The same literal as `totalNanoAiu` would escape too, if `isfinite` ran
before the bound. Python compares an `int` with a `float` exactly, without converting either,
so `value <= ceiling` cannot raise. It is False for `nan`, `inf` and `10**400` alike, and True
for `2**63 - 1` and `1e308` (MEASURED). That one comparison per figure replaces both of R2's
checks. Once it has passed, `int(nano)` and `float(premium)` cannot raise either.

**The 64-bit bound (R2; re-measured R3).** Both stores of this figure are `BigInteger`:
`worker_invocations.ai_nano_aiu` (`hub/hub/db/models.py:1922`) and `turn_usage.session_nano_aiu_total`
(`:1300`). Python's `sqlite3` raises `OverflowError: Python int too large to convert to SQLite
INTEGER` for `2**63` (MEASURED under `py -3.11`; `2**63 - 1` inserts). On the worker path that
raise lands in `_record`'s catch-all, so `run_worker` still returns. But the invocation row,
which holds the outcome, the error and every other figure, is lost, and `invocation_id` is
`None`. That breaks `run_worker`'s own promise that *"every exit records an invocation"*. *(R3.)*
The same raise reaches the Hub's real stack unchanged: an `insert` of `2**63` into a
`BigInteger` column through `create_async_engine("sqlite+aiosqlite://")` raises the builtin
`OverflowError`, not a SQLAlchemy `DBAPIError` (MEASURED), so no `except DBAPIError` anywhere
would catch it. On PostgreSQL `bigint` has the same range. That is UNVERIFIED here: no
PostgreSQL driver is a Hub dependency (`hub/pyproject.toml` lists `aiosqlite` only), and
`engine.py` passes `DATABASE_URL` straight through. So the ceiling is right for every database
the Hub can reach today, and not wrong for the one it might. A
malformed credit figure must cost only itself, so the helper refuses it, exactly as it refuses a
negative one. The comparison is exact (`9.223372036854776e18 <= 2**63 - 1` is `False` in Python),
so no float rounding lets one through.

**A row's ceiling is not its sum's (Opus review, re-measured).** A row that holds `2**63 - 1`
can be stored, but it cannot be summed. `_aggregate_columns` runs `func.sum(TurnUsage.ai_nano_aiu)`
(`usage_accounting.py:304`), and SQLite's integer `sum()` raises `OperationalError: integer
overflow` once the total passes `2**63 - 1`. The review measured that through aiosqlite. This
round measured it again with plain `sqlite3`: rows of `2**63 - 1` and `1` raise. `accounting_snapshot`
and `conversation_usage` have no handler, and `PATCH budget` calls `accounting_snapshot`. With
R3's ceiling, then, one near-ceiling run checkpoint would turn today's single failed finalisation
into a 500 on that project's accounting routes, lasting until the row is removed. The sibling
change will sum `worker_invocations.ai_nano_aiu` the same way. So the ceiling is a plausibility
bound, `2**53 - 1`, for both figures:

- It is about 9.0 million AI credits in one session. The capture's call cost 0.033 credits.
- It is the largest integer that a float and a JavaScript number hold exactly. That matters,
  because `recent_turns` sends the raw figure to the UI.
- It takes 1025 rows at the ceiling to overflow a sum: 1024 sum to `9223372036854774784`, and
  1025 raise (MEASURED this round). That is the accepted residual. It needs a thousand malformed
  checkpoints in one project, and at the capture's cost a thousand real ones add up to about 33
  credits.
- `totalPremiumRequests` takes the same constant. A `Float` sum does not raise (the review
  measured SQLite 3.45.1 returning NULL), so the reason there is simpler: no plausible premium
  count is near `2**53`, and one constant is one rule.

Python compares `2**53` and `float(2**53)` with `2**53 - 1` exactly, so both are refused
(MEASURED). The run side's per-call `copilotUsage.totalNanoAiu` sum still goes unbounded into
`turn_usage.ai_nano_aiu`. That is out of scope, as R3 left it (see "What each route returns").

`CopilotUsageLedger.observe_event` builds its `_Checkpoint` from it, and `parse_copilot_envelope`
calls it. The adapter imports `copilot_usage` at module level. That stays clear of `hub.db` and
`hub.api` (MEASURED: importing `hub.runner_adapters.copilot` and `hub.copilot_usage` in a fresh
`py -3.11` process loads neither), and `test_runner_adapters_imports.py` pins it.

**Considered and rejected: run the whole `CopilotUsageLedger` over the one-shot stream.** It would
share more code, but `finish()` reports `ai_nano_aiu` as the per-call **sum** (its provisional
figure) and leaves the checkpoint to `settle_copilot_credits`, which needs the database. A one-shot
has no per-call events (MEASURED), so the ledger's `ai_nano_aiu` would be None and the parser would
have to read `session_nano_aiu_total` instead. That is the checkpoint figure reached the long way
round, plus token-summing code that has nothing to sum. The helper shares exactly the part that is
the same: how a checkpoint's numbers are read.

## D3 — `result.usage.premiumRequests` is not read

The operator chose the checkpoint, "the same figure the ledger trusts for agent runs". A second
source for one field brings a disagreement rule that nothing has ever measured. The run path does not
read the ACP prompt result's premium requests either. In the capture the two agree (1 and 1). A
stream with a `result` and no checkpoint is UNVERIFIED and leaves both fields NULL, which
under-reports and never misreports, the property the decision row named as the safe floor.

**The cache diagnostic's `prompt_tokens` is not read either (R2).** It is the only token-shaped
figure in the stream, and three reasons keep it out. It is input-only. It is nested in a
diagnostic structure (`promptCacheBreakState`) that nothing in the Hub reads, and the run ledger
does not read it for runs either. And filling `input_tokens` while `output_tokens` and
`total_tokens` stay NULL would put a partial figure into a row that `worker-spend-counts-against-the-budget`
will sum into a budget, under-counting while looking measured. *(R3, re-derived from the
sibling's own text; citation corrected by the Opus review.)* R3 cited the sibling's
`design.md:39-43`, but that is migration `0106`'s one-time backfill, and it covers only
`cli='claude'` and `cli='codex'`. The rule that would apply to a new Copilot row is the sibling's
forward rule (its D1, `design.md:26`). That rule forms the total with
`runner_parsing._accounting_from_dimensions(raw_usage, source="worker", …)`, and the review
measured `_accounting_from_dimensions({'input_tokens': 1612}, source='worker')` → `(1612, None,
1612)`. So an `input_tokens`-only Copilot row would be counted as a measured total of exactly the
prompt, not left unknown. The refusal is what
keeps the sibling's own "unknown, never zero" rule true for Copilot. The decision row asked for
credits. Whether worker token accounting for Copilot should use it is that sibling's question. It
is noted in D5.

## D4 — which exits keep the credits

| Stream | Today | After |
|---|---|---|
| answer, checkpoint | answer, empty usage | answer, credits |
| `session.error`, checkpoint | error, empty usage | error, **credits** |
| no assistant message, checkpoint | error, empty usage | error, **credits** |
| no checkpoint | empty usage | empty usage (unchanged) |
| process exited non-zero | stdout not parsed (`worker.py:432-438`) | **unchanged** |
| timed out, or failed to spawn | no stdout captured (`worker.py:249`, `:251`) | **unchanged** |

*(Opus review.)* The spec delta's requirement now names only a call *"whose process exited
successfully"*. As R3 left it, it covered any call whose output carried a checkpoint, and a
non-zero exit's stdout can carry one. That would have required what this section deliberately
leaves out. A scenario now says that a non-zero, timed-out or unspawned call records both
figures as unknown.

The parser computes the usage once and returns it on every exit. `_interpret` already passes
`usage` into the `unparseable` result when there is an envelope error, so the row receives it with
no change to `worker.py`.

**Non-zero exit is left alone, deliberately.** `_interpret` skips parsing for every CLI on a non-zero
exit. Whether `copilot -p` exits non-zero after a charged call, for example on a `session.error`
late in the turn, is UNVERIFIED: no failing one-shot has been captured. Parsing stdout on a non-zero
exit for Copilot alone would be a new behaviour, built on no evidence, in a path every runner shares.
If a future capture shows a charged non-zero exit, that is its own finding.

## D5 — who reads it (what the route returns)

The rule *"also ask what each route returns"* gives an uncomfortable answer here: **no route
returns these figures.** `GET /accounting` aggregates `turn_usage` only (`usage_accounting.py:304-305`,
`_aggregate_columns`). The only `WorkerInvocation` readers are `api/v1/checkpoints.py:107` and
`:208`, and both read `.error`. After this change, a Copilot checkpoint's credits are in the
database and on no screen.

That is still what the decision asked for. The row is the durable record, and leaving it NULL loses
the figure for good: nothing can recover a past one-shot's charge. The display belongs to
`worker-spend-counts-against-the-budget`. The archived change's D12 says *"whichever lands second
adds `ai_nano_aiu` / `premium_requests` sums to each `workers` line"*, and its task 6.4 recorded
on 2026-10-02 that *"that change owns them now"*. **R1 found that change's `tasks.md`, `design.md`
and spec delta never mention credits** (`grep -i "credit\|nano\|copilot"` over the directory finds
nothing). The obligation was written only into the archived change. See Open question 1.

The same sibling also states (in the archived design's composition note) that *"a Copilot one-shot's
`total_tokens` comes from slice 2's envelope parser through its normaliser"*. The capture has no
usage token counts, so that `total_tokens` will be NULL for every Copilot worker call (MEASURED
against the capture, not against a live call). The only token-shaped figure is the cache
diagnostic's input-only `prompt_tokens` (see the evidence and D3). This change cannot fix that. It
is recorded for the sibling's own next round, along with the question of whether that diagnostic
is worth reading.

## D6 — BYOK

A one-shot on a provider (BYOK) runner goes through `copilot_one_shot_env`'s
`copilot_provider_env`. Whether Copilot emits a `session.usage_checkpoint` under BYOK, and with
what `totalNanoAiu`, is UNVERIFIED: task 7.6 of `a-copilot-agent-uses-hooks-and-its-own-agents` is
the operator's, and not driven. Whatever the stream says is recorded. A `0` is recorded as `0`,
which is the provider's own report, and the run path records the same. Nothing here converts or
infers.

## What each route returns when what it calls raises

- `parse_copilot_envelope` already skips any line that is not JSON or not an object. A
  `session.usage_checkpoint` whose `data` is not an object reaches the helper as `{}` (the loop's
  existing `data` guard) and yields `(None, None)`. The helper raises on nothing: `_nonneg_number`
  only does type checks and a comparison, and D2's ceiling is one more comparison. *(R3: R2's
  `math.isfinite` step did raise, on an integer literal of more than 308 digits. See D2.)*
- `int()`/`float()` run only on values `_nonneg_number` has accepted (finite or not). **Non-finite
  values are the case:** `json.loads` accepts `Infinity`, `NaN`, and an overflowing literal such
  as `1e400` (read as `inf`) (MEASURED under `py -3.11`). `_nonneg_number` returns both `inf` and
  `nan`, since `nan < 0` is `False`. Then `int(inf)` raises `OverflowError` and `int(nan)` raises
  `ValueError`. *(R2: R1 named only `inf`.)* The run ledger has the same exposure
  for a checkpoint (`copilot_usage.py:348`), but there it is inside `finish()`'s catch-all, so a run
  survives it. The worker's path has no catch-all around the parser: `_interpret` →
  `parse_envelope` raising would escape `run_worker`, whose contract is "never raises". **D2's
  helper therefore rejects non-finite values**, by its ceiling comparison (R3; R2 used
  `math.isfinite`). *(R3, read from the code, not driven.)* Here is what the callers would then
  return. `POST /conversations/{conversation_id}/checkpoint` (`checkpoints.py:134`) awaits
  `generate_checkpoint` → `run_worker` with no handler of its own. Its `finally` releases the
  claim, and the request ends in FastAPI's 500. No checkpoint and no invocation row are written,
  and `run_worker` skips `worker_dir_context.cleanup()`, so the temporary directory is left behind.
  The context-pressure trigger (`checkpoint_trigger.py:341`) and the handover
  (`checkpoint_handover.py:263`) call `generate_checkpoint` the same way. The titler is the third
  caller of the parser, and it is safe: `maybe_generate_title`'s catch-all
  (`conversation_titles.py:325`) logs and drops the title. For the ledger's checkpoint this
  is strictly narrower than today: an infinite checkpoint now gives unknown session totals, instead
  of the catch-all dropping the whole sample (tokens, allowance and all). The ledger's per-call
  `copilotUsage.totalNanoAiu` still goes through the bare `_nonneg_number`, and is still caught by
  `finish()`. That is out of scope here. Test 6 pins the checkpoint case.
- `run_worker` → `_record`: unchanged. A recording failure is already logged and swallowed. That
  swallow is what made R2 add the 64-bit bound (D2): a figure that converts cleanly but cannot be
  inserted would not raise out of `run_worker`, but it would silently cost the operator the whole
  audit row. *(R3: R2 understated the run side.)* Today the run side is worse off.
  `finish()` → `settle_copilot_credits` → `stored_total = checkpoint_total` →
  `record_turn_usage`'s `flush()` (`hub/hub/api/v1/agent_trigger.py:3985`) runs inside the RPC executor's
  finalising session. That session already set `run.status = final_status` (`:3954`) and has
  not yet committed (`:4018`). The `OverflowError` therefore rolls back the whole finalisation
  and reaches the executor's catch-all (`:4093`), and `_record_run_failure_tail` relabels the
  still-`running` row `failed` (read from the code, not driven). A Copilot turn that completed
  would be recorded as failed because of one telemetry figure. `settle_copilot_credits`'s own
  catch-all cannot help, because the raise comes after it, at the flush. The settled
  `ai_nano_aiu` (`diff <= checkpoint_total`) is bounded once the checkpoint is. The shared
  helper closes all of this for the checkpoint figure. The per-call
  `copilotUsage.totalNanoAiu` sum stays out of scope, as above.

## Tests that can fail

1. **The capture's credits.** `parse_copilot_envelope(oneshot_ok.jsonl)` → `ai_nano_aiu ==
   32_840_000`, `premium_requests == 1.0`, answer `"ok"`. It fails today (both None). It replaces
   `test_the_captured_copilot_one_shot_has_no_session_shutdown`, whose name and docstring record
   the old condition. The `session.shutdown`-absent assertion stays as a line in the new test, so
   the reason the figure comes from the checkpoint stays pinned.
2. **Through `run_worker` to the row, unpatched parser.** `_patch_spawn` returns the capture with
   the answer line's `content` replaced by a valid output-model JSON body (`Answer`: `objective`,
   `state`, `confidence`), and `_run(cli="copilot", model="auto")`. *(R2.)* It needs the
   `copilot_exe` fixture, because `copilot_one_shot_command` resolves the platform executable
   before `_patch_spawn`'s `resolve_executable` stub is reached. It also needs `Path.home`
   monkeypatched to `tmp_path`, as `test_the_copilot_spawn_gets_the_worker_home_and_no_token` does,
   or `ensure_copilot_worker_home` writes under the real home. The `worker_invocations` row reads
   `outcome == "ok"` and `(32_840_000, 1.0)`. It fails today. This is the evidence
   that `test_a_workers_copilot_credits_reach_its_invocation_row` is not (that one patches the
   parser).
3. **Last checkpoint wins.** Two checkpoint lines, `(10, 1)` then `(25, 2)`, give `(25, 2.0)`, not
   `(35, 3)` and not `(10, 1)`. The ordering is the capture's (checkpoint after `assistant.message`),
   and the test fails if the parser takes the first checkpoint instead. *(Opus review.)* A second
   case pins D1's "a later checkpoint without a figure": `(10, 1)` then `(-1, 2)` give
   `(None, 2.0)`. Without it, an implementation that kept the last *good* value per field would
   pass every test.
4. **Credits on error exits.** The capture with its `assistant.message` replaced by a
   `session.error` line gives an error and `(32_840_000, 1.0)`. The capture with the
   `assistant.message` removed gives "no assistant message" and the same credits. Both fail today.
5. **A bad figure is unknown, field by field.** `totalNanoAiu: -1` with `totalPremiumRequests: 1`
   gives `(None, 1.0)`. `true` gives None. A string gives None. It fails today: today's parser
   returns empty usage, so the valid `1.0` is missing too (`(None, None)`, measured by the Opus
   review; R1-R3 called it a guard that passes today).
6. **Non-finite, and too large to store.** `totalNanoAiu: Infinity` gives None, and so do `NaN` and
   `1e400` (*R2*). `totalPremiumRequests: NaN` gives None. *(R3.)* So does a 400-digit integer
   literal, in either field: `"totalPremiumRequests": 1` followed by 400 zeros, with a valid
   `totalNanoAiu`, gives `(32_840_000, None)`. The same literal as `totalNanoAiu` gives
   `(None, 1.0)`. This fails with `OverflowError` if the helper calls `math.isfinite` or `float`
   before its ceiling. `parse_copilot_envelope` does not raise. *(Opus review.)* This fails
   today, because today's parser returns no figure at all, so the valid one is missing. R3 said
   it passed today. It also fails (with `OverflowError` or `ValueError`) if the ceiling
   comparison is removed. Also, for the ledger,
   one `assistant.usage` call with tokens, then
   `observe_event("session.usage_checkpoint", {"totalNanoAiu": inf, "totalPremiumRequests": 1})`,
   then `finish()`, gives `session_nano_aiu_total is None`, `session_premium_requests_total == 1`,
   and the call's tokens. This fails today: the catch-all's sample carries no tokens. *(R3.)*
   The same with `totalNanoAiu: 2**63` gives `session_nano_aiu_total is None`. It fails today:
   the ledger keeps `9223372036854775808`, as the Opus review measured (R3 said it passed). It
   is also the guard on the bound for the run side, whose unguarded failure is the relabel
   described in "What each route returns".
   *(R2; ceiling moved by the Opus review.)* The ceiling gets these cases.
   `checkpoint_totals({"totalNanoAiu": 2**53, "totalPremiumRequests": 1})` gives `(None, 1)`,
   `2**53 - 1` is kept, and `float(2**53)` is refused. Then through `run_worker` (test 2's setup,
   with the checkpoint's `totalNanoAiu` edited to `2**63`), exactly one `worker_invocations` row
   is written, with `ai_nano_aiu is None`, `premium_requests == 1.0` and `outcome == "ok"`. It
   fails today: the parser reads no checkpoint, so `premium_requests` is NULL. (R2 and R3 said it
   passed.) It also fails if 2.2 lands without 2.1's bound, because the row is lost to the measured
   `OverflowError` and the test finds zero rows.
7. **The run ledger is unchanged otherwise.** The existing `copilot_usage` tests pass untouched.
   This is the control: D2 moved the rule and did not change it.
8. **The import restriction.** `test_runner_adapters_imports.py` passes with the module-level
   import.

`test_the_captured_copilot_envelope_yields_its_answer`'s `usage.input_tokens is None, "usage and
credits are slice 4's"` keeps its assertion. It is still true, since there are no usage tokens and
D3 does not read the cache diagnostic. Its message becomes *"the one-shot stream reports no usage
tokens (design D3)"*.

## Open questions

1. **Who adds the credit sums to the `workers` lines?** The archived change assigned them to
   `worker-spend-counts-against-the-budget`, but nothing in that change's own files says so.
   Options: (a) add a task, a test and a delta line to that change in its next round (it is still
   unapproved: its `0.3`, the operator's D7 answer, is open). (b) Put the sums in this change, ahead
   of the `workers` lines existing, which is impossible because there is no line to sum into. (c)
   Do nothing and let it be rediscovered. Option (b) is listed for completeness: it is not
   really available. **Recommendation: (a), as a real task, a test and a spec-delta line in
   that change's next round.** A round-log note is not enough *(Opus review)*: a note is not a
   task, and that gap is exactly how F486 arose. This change does not carry it, because a
   change must never be carried in two places. The sibling's task should also carry D2's
   sum-overflow hazard, since it will `sum()` `worker_invocations.ai_nano_aiu`. What the
   operator decides is only whether the sibling's next round gains that task. Their D7 answer
   does not affect it, because every D7 branch keeps the `workers` lines (the sibling's
   `design.md:5-6`). Recorded as finding **F486**.
2. **Should a later capture be taken under BYOK and on a paid plan?** Both would turn D6's and
   D1's UNVERIFIED items into measurements. Neither blocks this change, since the parser records
   what the stream says. This is the operator's call because it spends credits (the Free plan's
   call budget, or the operator's own key).

## Round log

- **R1, 2026-10-03 night (iter 21).** Explored `runner_adapters/copilot.py`, `copilot_usage.py`,
  `worker.py` (`_record`, `run_worker`, `_interpret`), `conversation_titles.py`, `usage_accounting.py`,
  `api/v1/checkpoints.py`, migration `0117`, the archived change's D5/D12/tasks 5.4 and 6.4, the
  current `usage-accounting` spec, `worker-spend-counts-against-the-budget`, and the capture line by
  line. Found three things the decision row did not say. (1) The capture has no token counts at
  all, so credits are a Copilot worker call's only spend figure. (2) No route reads the columns, and
  the sibling change that is meant to never mentions credits (F486). (3) `int(inf)` would make
  `run_worker` raise, so the shared helper must refuse non-finite values.
- **R2, 2026-10-03 night (iter 22).** Re-derived from the code at `9d1f617`, not from R1's lists.
  Parsed the capture line by line with `json.loads` (15 lines, the order and the `data` keys as
  R1 said; `result` has no `data`). Grepped `hub/hub` for `parse_copilot_envelope`,
  `parse_envelope`, `parse_one_shot`, `.ai_nano_aiu`, `.premium_requests` and `WorkerInvocation`.
  The parser's callers are `worker.parse_envelope` (via `CopilotAdapter.parse_one_shot`) and the
  titler (`conversation_titles.py:290`, usage discarded). The only `WorkerInvocation` readers are
  `checkpoints.py:107`/`:208`, both `.error`. `run_worker`'s callers are `checkpoint_generation.py:556`
  (`kind="checkpoint"`) and `:644` (`"checkpoint_probe"`), matching drive 3.1. Nothing in `src/`
  reads the columns. `COPILOT_ONE_SHOT_FLAGS` plus the optional `--no-custom-instructions` and
  `--model` contain no resume flag. `_interpret` carries `usage` on the envelope-error, no-JSON,
  schema-invalid and ok exits, and drops it only for `spawn.outcome != "ok"` (where
  `_run_worker_process` does keep `stdout`, but `_interpret` never reads it), so D4's table holds.
  `copilot_usage` imports only `runner_events`/`runner_parsing`/`model_catalog`/`workspace_writes`
  (MEASURED in a fresh process), so D2's import claim holds. The sibling directory still has no
  `credit|nano|copilot` (F486 holds). **Changed:** (1) the "no token count on any line" claim was
  wrong. The checkpoint nests a prompt-cache diagnostic with `prompt_tokens: 1612` and 18
  per-segment `tokens`. The evidence, the proposal, D3 (why it is not read) and D5 (the sibling's
  question) are corrected, and test 1.4's message is restated. (2) `NaN` and `1e400` join `inf` as
  non-finite (`int(nan)` raises `ValueError`). (3) A new **64-bit bound**: a finite `totalNanoAiu
  >= 2**63` passes R1's helper, and inserting it raises `OverflowError` (MEASURED), which
  `_record` swallows by dropping the whole invocation row. The helper now refuses it (D2), the
  spec delta says so, and test 6 pins it at the row. (4) Test 2 now names the `copilot_exe`
  fixture and the `Path.home` patch that it cannot run without. Nothing else changed: D1, D3's
  premium-request rule, D4, D5's read-side finding, and D6 re-derived the same.
- **R3, 2026-10-03 night (iter 23).** Re-derived at `3233108`, aimed at R2's own additions
  first. Measured that `json.loads` turns a long integer literal into an `int` (up to 4300 digits;
  longer raises `ValueError`, which the parser already skips), and that `math.isfinite(10**400)`
  and `float(10**400)` raise `OverflowError`. Measured that `value <= 2**63 - 1` and
  `value <= sys.float_info.max` never raise and are False for `nan`, `inf` and `10**400`.
  Measured `2**63` through `create_async_engine("sqlite+aiosqlite://")` into a `BigInteger`:
  the builtin `OverflowError`, not a `DBAPIError`. Read `settle_copilot_credits`,
  `record_turn_usage`, the RPC executor's finalising session (`hub/hub/api/v1/agent_trigger.py:3951-4018`) and its
  catch-all (`:4093`), the checkpoint route and the two other `generate_checkpoint` callers, the
  titler's catch-all, `engine.py` and `hub/pyproject.toml`'s drivers, and
  `worker-spend-counts-against-the-budget`'s backfill rule. **Changed:** (1) **R2's helper
  raised.** Its `math.isfinite` step raises on an integer literal of more than 308 digits, in
  either field, so a checkpoint of `"totalPremiumRequests": 1` followed by 400 zeros would escape
  `run_worker`. D2 now specifies one ceiling comparison per figure instead
  (`<= 2**63 - 1`, `<= sys.float_info.max`). That comparison also covers non-finite values. The
  proposal, the spec delta ("a figure too large", both figures now), task 2.1 and test 6 follow.
  (2) **R2 understated the run side.** A `>= 2**63` checkpoint does not just fail one column's
  flush. It rolls back the RPC executor's whole finalisation, and the catch-all relabels a
  completed run `failed` (read from the code, not driven). Test 6 gains a run-side guard. (3)
  "What each route returns" now names the answer: the operator's checkpoint `POST` would end in
  a 500 with no invocation row and a leaked temporary directory. The titler is safe behind its
  catch-all. **Re-derived the same:** the bound belongs in the shared helper, because both
  `BigInteger` stores take the checkpoint figure and the run side's settled `ai_nano_aiu` is
  `<= checkpoint_total`. PostgreSQL's `bigint` has the same range, UNVERIFIED because no
  PostgreSQL driver is a Hub dependency. D3's refusal of `prompt_tokens` holds, and it is now
  sharper: the sibling's `COALESCE` rule would count an input-only row as a measured total. D1,
  D4, D5 and D6 are unchanged.
- **Adversarial Opus review, 2026-10-03 night (iter 24).** An Opus subagent re-derived the change
  at `0b784b1` and measured under `py -3.11`. It found **seven problems**, all applied. (1) **The
  ceiling was a row's, not its sum's.** `func.sum` over `turn_usage.ai_nano_aiu` raises
  `integer overflow` once one near-`2**63 - 1` row meets any other, and the accounting routes
  have no handler. So R3's bound would have turned a failed finalisation into a lasting 500
  (this round re-measured it with plain `sqlite3`). D2's ceiling is now `2**53 - 1` for both
  figures, and the residual is 1025 rows at the ceiling (MEASURED). (2) **Five "passes today"
  labels were wrong.** Tests 5 and 6 (the 400-digit case, the ledger's `2**63`, and the bound's
  row) all fail today, because today's parser returns empty usage and the ledger keeps `2**63`.
  The labels in design and in tasks 1.1/1.3 are corrected. (3) **The spec delta required what D4
  leaves out.** It covered any call whose output carried a checkpoint, including a non-zero
  exit. It is now scoped to a process that exited successfully, with a scenario for non-zero,
  timeout and spawn failure, and the timeout row is added to D4's table. (4) **The run side
  changed with no spec delta.** The delta now MODIFIES the run requirement (non-numeric, boolean,
  non-finite or above `2**53 - 1` is ignored, and does not fail the run or lose its tokens), with
  a scenario. (5) **No test pinned D1's later-unusable-checkpoint rule.** Test 3 gains `(10, 1)`
  then `(-1, 2)` → `(None, 2.0)`, and the delta gains a scenario. (6) **D3 cited the wrong rule.**
  `design.md:39-43` is migration `0106`'s claude/codex backfill. The forward rule is the sibling's
  D1, via `_accounting_from_dimensions` (`{'input_tokens': 1612}` → `(1612, None, 1612)`). The
  conclusion holds. (7) **File references** corrected: `checkpoints.py:107`/`:208`,
  `hub/hub/db/models.py`, `hub/hub/api/v1/agent_trigger.py`. Open question 1's recommendation is
  now a real task, a test and a delta line in the sibling, with the sum-overflow hazard, not a
  round-log note. **Survived:** the comparison never raises for any `json.loads` value (all types,
  4300-digit ints, `-0.0`). `Float` stores up to the float maximum. R3's relabel-to-failed trace
  holds line by line, and nothing guards it today. D1, D4 and the import claim hold. `--strict`
  passed. The review is kept at `spec-queue/tracks/reviews/copilot-oneshot-credits-2026-10-03.md`.
