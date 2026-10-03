# Design — a Copilot one-shot records its credits

Re-verified at `957fc84` (2026-10-03, R1). Labels follow the archived
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
- There is **no** `assistant.usage`, **no** `session.shutdown` and **no** token count on any line.
  The stream does carry ephemeral events (`"ephemeral": true` on `session.info`, the message
  delta and others), so the absence is not an ephemeral filter hiding them.

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
    `_nonneg_number`."""
```

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

## D4 — which exits keep the credits

| Stream | Today | After |
|---|---|---|
| answer, checkpoint | answer, empty usage | answer, credits |
| `session.error`, checkpoint | error, empty usage | error, **credits** |
| no assistant message, checkpoint | error, empty usage | error, **credits** |
| no checkpoint | empty usage | empty usage (unchanged) |
| process exited non-zero | stdout not parsed (`worker.py:432-438`) | **unchanged** |

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
`_aggregate_columns`). The only `WorkerInvocation` readers are `api/v1/checkpoints.py:106` and
`:207`, and both read `.error`. After this change, a Copilot checkpoint's credits are in the
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
token counts, so that `total_tokens` will be NULL for every Copilot worker call (MEASURED against
the capture, not against a live call). This change cannot fix that. It is recorded for the
sibling's own next round.

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
  only does type checks and a comparison.
- `int()`/`float()` run only on values `_nonneg_number` has accepted (finite or not). **`inf` is
  the one case:** `json.loads` accepts `Infinity`, `_nonneg_number(inf)` returns `inf`, and
  `int(inf)` raises `OverflowError` (MEASURED under `py -3.11`). The run ledger has the same exposure
  for a checkpoint (`copilot_usage.py:348`), but there it is inside `finish()`'s catch-all, so a run
  survives it. The worker's path has no catch-all around the parser: `_interpret` →
  `parse_envelope` raising would escape `run_worker`, whose contract is "never raises". **D2's
  helper therefore rejects non-finite values** (`math.isfinite`). For the ledger's checkpoint this
  is strictly narrower than today: an infinite checkpoint now gives unknown session totals, instead
  of the catch-all dropping the whole sample (tokens, allowance and all). The ledger's per-call
  `copilotUsage.totalNanoAiu` still goes through the bare `_nonneg_number`, and is still caught by
  `finish()`. That is out of scope here. Test 6 pins the checkpoint case.
- `run_worker` → `_record`: unchanged. A recording failure is already logged and swallowed.

## Tests that can fail

1. **The capture's credits.** `parse_copilot_envelope(oneshot_ok.jsonl)` → `ai_nano_aiu ==
   32_840_000`, `premium_requests == 1.0`, answer `"ok"`. It fails today (both None). It replaces
   `test_the_captured_copilot_one_shot_has_no_session_shutdown`, whose name and docstring record
   the old condition. The `session.shutdown`-absent assertion stays as a line in the new test, so
   the reason the figure comes from the checkpoint stays pinned.
2. **Through `run_worker` to the row, unpatched parser.** `_patch_spawn` returns the capture with
   the answer line's `content` replaced by a valid output-model JSON body, and `cli="copilot"`.
   The `worker_invocations` row reads `(32_840_000, 1.0)`. It fails today. This is the evidence
   that `test_a_workers_copilot_credits_reach_its_invocation_row` is not (that one patches the
   parser).
3. **Last checkpoint wins.** Two checkpoint lines, `(10, 1)` then `(25, 2)`, give `(25, 2.0)`, not
   `(35, 3)` and not `(10, 1)`. The ordering is the capture's (checkpoint after `assistant.message`),
   and the test fails if the parser takes the first checkpoint instead.
4. **Credits on error exits.** The capture with its `assistant.message` replaced by a
   `session.error` line gives an error and `(32_840_000, 1.0)`. The capture with the
   `assistant.message` removed gives "no assistant message" and the same credits. Both fail today.
5. **A bad figure is unknown, field by field.** `totalNanoAiu: -1` with `totalPremiumRequests: 1`
   gives `(None, 1.0)`. `true` gives None. A string gives None.
6. **Non-finite.** `totalNanoAiu: Infinity` gives None, and `parse_copilot_envelope` does not
   raise. Today's parser ignores the checkpoint, so this test passes today. It is a guard on the
   new conversion, and it fails (with `OverflowError`) if the `isfinite` check is removed. Also, for the ledger,
   one `assistant.usage` call with tokens, then
   `observe_event("session.usage_checkpoint", {"totalNanoAiu": inf, "totalPremiumRequests": 1})`,
   then `finish()`, gives `session_nano_aiu_total is None`, `session_premium_requests_total == 1`,
   and the call's tokens. This fails today: the catch-all's sample carries no tokens.
7. **The run ledger is unchanged otherwise.** The existing `copilot_usage` tests pass untouched.
   This is the control: D2 moved the rule and did not change it.
8. **The import restriction.** `test_runner_adapters_imports.py` passes with the module-level
   import.

`test_the_captured_copilot_envelope_yields_its_answer`'s `usage.input_tokens is None, "usage and
credits are slice 4's"` keeps its assertion. It is still true, since there are no tokens to read. Its
message becomes *"the one-shot stream reports no tokens (design D5)"*.

## Open questions

1. **Who adds the credit sums to the `workers` lines?** The archived change assigned them to
   `worker-spend-counts-against-the-budget`, but nothing in that change's own files says so.
   Options: (a) add a task, a test and a delta line to that change in its next round (it is still
   unapproved: its `0.3`, the operator's D7 answer, is open). (b) Put the sums in this change, ahead
   of the `workers` lines existing, which is impossible because there is no line to sum into. (c)
   Do nothing and let it be rediscovered. **Recommendation: (a)**, done as a note in that change's
   round log, not by this change carrying it. A change must never be carried in two places.
   Recorded as finding **F486**.
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
