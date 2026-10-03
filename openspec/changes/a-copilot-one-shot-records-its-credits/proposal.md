# Proposal — a Copilot one-shot records its credits

Decision: **`copilot-oneshot-credits`** (`spec-queue/DECISIONS.md`, DECIDED 2026-10-02, operator,
as recommended): *"Yes: read the one-shot's `session.usage_checkpoint`. A follow-up change, not
this one."* R1, 2026-10-03 night window (the operator's stated exception to "no proposals"),
re-verified against the code at `957fc84`.

## Why

`a-copilot-run-shows-its-credits` (archived 2026-10-02) gave `worker_invocations` two nullable
credit columns, `ai_nano_aiu` and `premium_requests` (migration `0117`), and taught `run_worker` to
write them from `WorkerUsage` (`worker.py:299-300`). Its task 5.4 was to fill them from a
`session.shutdown` event **if** the captured `copilot -p --output-format json` stream had one. It
does not (`hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl`), so the task left
`parse_copilot_envelope` unchanged. Every exit of that parser still returns an empty `WorkerUsage()`
(`runner_adapters/copilot.py:126-130`). Both columns are therefore NULL for every Copilot worker
call, on every Hub.

The same capture does carry the figure. Its `session.usage_checkpoint` line reads
`{"totalNanoAiu": 32840000, "totalPremiumRequests": 1, ...}`, and the closing `result` line has
`usage.premiumRequests: 1`. A one-shot is one `copilot -p` process, and `COPILOT_ONE_SHOT_FLAGS`
names no `--resume`, so it opens one fresh session. That makes the session's cumulative checkpoint
the call's whole charge. It is the same event, with the same two keys, that `CopilotUsageLedger`
already trusts for a Copilot run (`copilot_usage.py:181-185`, the archived change's D4).

For a Copilot one-shot, credits are the only spend figure the stream reports as usage. The capture
has **no `assistant.usage` line and no usage token count**: the `result` line's `usage` holds only
`premiumRequests`, durations and `codeChanges`. (The checkpoint's `promptCacheBreakState` does
nest a prompt-cache diagnostic with `prompt_tokens: 1612` and per-segment system-prompt sizes, but
it has no output count, so no token total can be formed from it. See design D3.) So without this
change a Copilot checkpoint, probe or title costs the operator credits that the Hub never records
at all.

## What changes

- **The one-shot parser reads the checkpoint.** `parse_copilot_envelope` keeps the **last**
  `session.usage_checkpoint` it sees, because the figure is cumulative. `totalNanoAiu` goes into
  `WorkerUsage.ai_nano_aiu` and `totalPremiumRequests` into `WorkerUsage.premium_requests`. Each
  value is accepted by the rule the run ledger already applies: a bool, a non-number or a negative
  value is ignored, and that field stays unknown. Two cases are added to that rule. A non-finite
  value (`Infinity`, `NaN`) is ignored, because converting it would raise. A credit figure too
  large for the 64-bit column is also ignored, because inserting it would lose the whole
  invocation row (design D2).
- **One rule, two readers.** The checkpoint-reading rule moves into one public helper in
  `copilot_usage.py`. `CopilotUsageLedger.observe_event` and `parse_copilot_envelope` both call it,
  so a Copilot schema change is fixed in one place. Importing it does not reach `hub.db`, which the
  adapter package requires (slice 1 D1).
- **Credits survive a failed answer.** A stream that ends in `session.error`, or that carries no
  assistant message, still returns the checkpoint's credits alongside its error. `_interpret`
  already keeps usage on an envelope error (`worker.py:440-450`): *"a worker that burned tokens
  producing prose still cost money."*
- **No other source is read.** `result.usage.premiumRequests` is not a fallback (design D3). No
  token columns are filled. The stream reports no usage tokens, and the cache diagnostic's
  `prompt_tokens` is not read (D3).

## What does not change

- **The read side.** No API returns `worker_invocations.ai_nano_aiu` today. Its only readers are
  the checkpoint routes, and they read `error` (`api/v1/checkpoints.py:106`, `:207`). The archived
  change's D12 and task 6.4 assigned the `workers`-line credit sums to
  `worker-spend-counts-against-the-budget`, the second of the two changes to land. That change's
  `tasks.md` does not yet carry them (design D5, Open question 1). Until it does, this change's
  figures can be seen only by reading the table.
- **The titler.** `conversation_titles.py:290` already calls `parse_copilot_envelope` and discards
  the usage it returns. It writes no `worker_invocations` row for any CLI, which is
  `worker-spend-counts-against-the-budget`'s D4. Once that change routes the titler's row through
  this parser, the titler's Copilot credits arrive with no further work here.
- **A one-shot that exits non-zero.** `_interpret` returns before it parses stdout
  (`worker.py:432-438`), for every CLI. That is unchanged (design D4).
- **The budget.** Credits are not tokens and count toward nothing, as the `usage-accounting`
  requirement for Copilot runs already says.
- **No migration, no UI, no Hub-restart hazard** beyond the ordinary one: the change is a parser
  edit inside an already-shipped column write.

## Impact

- `hub/hub/copilot_usage.py`: a public `checkpoint_totals(data)`. `observe_event` calls it, so a
  Copilot run's checkpoint gains the same two refusals (non-finite, and too large to store).
- `hub/hub/runner_adapters/copilot.py`: `parse_copilot_envelope` reads the last checkpoint and
  returns it on every exit, and its docstring stops saying "usage stays empty".
- `hub/tests/test_worker.py`: `test_the_captured_copilot_one_shot_has_no_session_shutdown` is
  inverted, and `test_the_captured_copilot_envelope_yields_its_answer`'s "slice 4's" assertion is
  restated. New tests are run against the real capture and through `run_worker` to the row.
- `openspec/specs/usage-accounting/spec.md`: one ADDED requirement.
- Reaches `:8000` on its next restart: the operator's Copilot worker calls start recording credits.
  This writes to no existing row.
