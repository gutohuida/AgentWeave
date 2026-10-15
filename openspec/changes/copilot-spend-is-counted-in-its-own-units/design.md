# Design — Copilot spend is counted in its own units

## Context

AgentWeave measures spend in three units, and none of them converts into another:

- **Tokens.** These are the budget's unit (`token_budget`). The operator decided this
  (`ghcp-d3-credits`).
- **API-equivalent dollars.** Only Claude reports them.
- **Copilot credits.** A Copilot call reports two figures:
  - `ai_nano_aiu`: AI credits × 10⁹, an integer.
  - `premium_requests`: a float.

A Copilot *turn* reports both tokens and credits. Its tokens count against the budget, and its
credits are summed and shown beside them, "not counted against the budget"
(`AccountingPanel.tsx:14-23`).

A Copilot *one-shot* call is any `run_worker` call on a `copilot` runner, plus a conversation title
once worker-spend's D4 records one. It reports **only** credits (proposal, "Where the spend goes
missing"). Its `WorkerInvocation` row has `ai_nano_aiu` and `premium_requests`, and NULL in every
token and cost column.

`worker-spend-counts-against-the-budget` (the dependency) is past R3 and waits on its D7. It adds
three things:

- `WorkerUsage.total_tokens`, set for Claude and Codex only (its D1);
- a `workers` list on `GET /projects/{pid}/accounting`, one line per kind (its D2);
- project token totals that include those lines (its D2).

Its D2 line carries `kind`, `input_tokens`, `output_tokens`, `total_tokens`, `measured_calls`,
`unmeasured_calls` and `api_equivalent_usd_micros`. A *measured* call has `total_tokens` not null.
An *unmeasured* call spawned (outcome `ok`, `nonzero_exit`, `timeout`, `unparseable` or
`schema_invalid`) and reported no usage. Credits are never mentioned, so a Copilot call lands in
`unmeasured_calls`.

This change is written **on top of** that one. Every reference below to "the worker-line query",
"the `workers` lines" or "measured/unmeasured" means worker-spend's design D2 as it stands at
`3cfe0f00`.

Today, every `run_worker` call writes a `worker_invocations` row, because `run_worker` always ends in
`_record` (`worker.py:265`, `:311`). There are six call sites, in five kinds:

- `checkpoint`, at `checkpoint_generation.py:564`
- `checkpoint_probe`, at `checkpoint_generation.py:652`
- `vault-distillation`, at `distillation.py:304` and `:384`
- `vault-reports`, at `vault_reports.py:231`
- `spec-vault-check`, at `vault_spec_check.py:312`

The last three are manager jobs, and each can run on a Copilot runner. The drive happened to fire
only a checkpoint and its probe. D1 is written per kind, so it covers every kind on the same terms.

The conversation titler already parses a Copilot envelope (`conversation_titles.py:304-311`). It
keeps the usage only in the `manager_job_fired` event payload (`manager.usage_record`, `:309`), and
writes no row. Worker-spend's D4 adds that row, but never says the row's usage is the parsed usage,
and its only titler test is Claude's (R3). Task 2.7 makes it carry the parsed credits, and task 1.15
tests it.

## Decisions

### D1 — Each `workers` line carries its kind's credits, and a credited call is not "unmeasured"

Each `workers` line gains three fields:

- `ai_nano_aiu`: the sum over the kind's calls, or `null` when no call reported credits.
- `premium_requests`: the same rule.
- `credited_calls`: the count of spawned calls with `total_tokens` NULL and at least one credit
  figure not NULL.

`unmeasured_calls` narrows to spawned calls that reported **neither** tokens nor credits.
`measured_calls` keeps worker-spend's meaning: the call's tokens are known.

On the drive, the result is these two lines:

- `checkpoint`: measured 0, credited 1, unmeasured 0, 1 102 140 000, 1.0
- `checkpoint_probe`: measured 0, credited 1, unmeasured 0, 822 390 000, 1.0

The three counts partition the spawned calls, so the caption keeps worker-spend's form. The worker
call count it prints is `measured + credited + unmeasured`.

**Alternatives.**
- *Count a credited call as measured.* This was rejected. A "measured" call is one whose tokens
  entered the token total, and a credited call's did not. The budget arithmetic would no longer
  reconcile with the count.
- *Keep "unmeasured" and add the credit sums only.* This was rejected. The scenario "a call that
  started but reported no usage SHALL be counted as such" would be false of a call that reported
  1.10 credits.

### D2 — The project's credit totals include worker credits; agents and conversations stay turns-only

`accounting_snapshot`'s `project.ai_nano_aiu` and `project.premium_requests` become two sums added
together in Python: the turn sum and the worker sum. `None` plus a number is the number, and
`None + None` is `None`. On the drive, the totals become 155 924 675 000 and 21.0.

**The worker sum is the sum of the `workers` lines (R3).** It is added up in Python from the lines
D1 builds, not read by a separate query. The Budgets panel shows the project credits line beside the
per-agent chips (`AccountingPanel.tsx:93-113`) and, after worker-spend task 2.6, the worker lines;
the operator can add them up. Computing the worker part from the lines makes
`project = Σ agents + Σ workers` hold by construction rather than by two queries agreeing (task
1.16). Under D7-A no worker lines exist, so a `wpc6-e` = yes would put credits in the total that no
line on the panel explains (see `wpc6-e`). The Overview lists only agents' tokens (`:48-53`), so its
"AI credits" row exceeding the agents shown there contradicts no figure it prints.

- **Agents** stay turns-only, because a worker call belongs to no agent. Worker-spend makes the same
  choice for tokens.
- **`conversation_usage`** (`usage_accounting.py:406-421`) stays turns-only too. Worker-spend leaves
  it untouched. Adding credits there without tokens would make a conversation's figures disagree
  with each other about what they include.
  - The alternative, adding both, belongs in a change that adds both together.
  - A worker row does carry `conversation_id`, so the data exists if that change is ever made.

**The worker sum uses `func.sum`, matching the turn path.** It therefore carries the residual that
the turn path accepted (F486):
- Each figure is capped at 2**53−1.
- SQLite's integer `sum()` raises after roughly 1 025 rows at the cap.
- The result would be a lasting 500 on `GET /accounting`.

One consequence is recorded neither by F486 nor by worker-spend. `PATCH /accounting/budget`
(`api/v1/accounting.py:49-80`) **commits the budget at :62**, persists and broadcasts
`accounting_budget_updated` at :64-65, and only then calls `accounting_snapshot` at :66. The route
has no `try`, and no exception handler in `main.py` catches it. An overflow there therefore has
three effects:

- It returns 500 for a budget that has already been saved and announced.
- It skips the `schedule_agent` loop at :67-79. An operator who raised the budget to release paused
  queues finds them still queued until something else schedules those agents.
- PATCH reads only `snapshot["project"]["total_tokens"]` (:80), so the credit sums are raise surface
  on a route that does not use them.

The turn sums already expose PATCH this way. Worker-spend's worker token sum (its tasks 2.5) adds
another source, and this change's two worker credit sums add two more.

The alternative is SQLite `total()`, which returns a float and never raises. It would lose exact
integers above 2**53. It is recorded and not chosen. Either path needs worker-spend's line-cap
argument, and a fix belongs to F486, not here.

### D3 — `preferred_display` gains a `credits` kind, ranked before `tokens`

The new order:

1. allowance (newest reading)
2. `api_equivalent` (any reported cost)
3. **`credits`**
4. `tokens`
5. `unavailable`

`credits` is used when the project's credit totals from D2 have either figure not null. Its shape:

```json
{"kind": "credits", "label": "AI credits", "runner": "copilot",
 "ai_nano_aiu": 155924675000, "premium_requests": 21.0}
```

`accountingDisplayLabel` renders it as **"Copilot AI credits · no allowance reported"**: a unit and
a reason, not a number. The figure is already printed by the Overview "AI credits" row
(`OverviewBudgetSummary.tsx:38-43`) and by the Budgets credits line. Printing it a third time would
risk the three disagreeing.

The rule follows **which data exists, not which runner is dominant** (question `wpc6-c`). A mixed
project that has a Claude cost still shows `api_equivalent`, as it does today. The headline moves
only when the newest 50 turns carry no allowance reading, no turn reported a cost, and credits
exist. R3 found that this covers more than the one case R1 named:

- **An all-Copilot project with no reading** (the drive): `tokens` → `credits`. This is the change's
  purpose.
- **A mixed project with no cost** and Copilot credits: `tokens` → `credits`.
- **A project with no Copilot turns whose Copilot spend is all worker calls**: for example a Codex
  project whose `checkpoint_runner_id` is a Copilot runner (the checkpoint runner is the project's,
  not the agents', `checkpoint_trigger.py:155-157`), or a manager job on a Copilot runner. Its
  credits come from D2's worker sum, so it moves `tokens` → `credits` under D7 C or D. Question
  `wpc6-f` asks whether worker credits alone should do this; the design assumes yes.
- **A project whose only Copilot turns were refused**, `status="unavailable"` with no tokens but a
  settled charge (`usage_accounting.py:65-67`): `unavailable` → `credits`.

A pure Claude or Codex project, with no Copilot runner anywhere, has null credits and does not move.
The tests that pin today's ranking are named in task 1.10; each carries an allowance or a cost, so
none moves.

**Alternatives.**
- *Rank `credits` before `api_equivalent`.* This was rejected. It would demote a dollar figure the
  operator already reads, on every mixed project, for the sake of a unit the dashboard already
  prints beside it.
- *Use `credits` only when every turn is Copilot.* This was rejected. A single Claude turn with no
  cost would flip the headline back to "Tokens", which is the "dominant runner" flapping in another
  form.
- *Fix it in the UI only, by printing credits when the kind is `tokens` and credits exist.* This was
  rejected. `preferred_display` is the API's statement of the headline unit, so it should say so
  itself.

### D4 — The token budget is unchanged, and a Copilot one-shot call has no tokens to count

There is no change to `budget_state`, `project_budget_state`, or `token_budget`.

- The credits stay information (`ghcp-d3-credits`).
- A Copilot worker's `total_tokens` stays NULL. It is **never estimated**. Nothing is converted from
  credits, and the nested `prompt_tokens` diagnostic is not read.

So under worker-spend's D7-C, a project whose only worker runner is Copilot has checkpoints that
never move the budget. The new spec requirement says this outright, so that a reader does not
mistake it for a bug.

Question `wpc6-a` asks whether this is acceptable.

### D5 — The `'null'` allowance text stays, guarded by a control test

`turn_usage.allowance` holds the JSON text `null` when no reading exists. This is SQLAlchemy `JSON`
with `none_as_null=False`, and it is documented at `provider_allowance.py:123-126`.

- Every reader tests `isinstance(..., dict)`.
- No query filters `allowance IS NOT NULL`.

Changing the writer would need `none_as_null=True` plus a data migration of every existing row, all
for a value nothing misreads. A control test pins the behaviour that matters: a turn without a
reading never becomes the allowance `preferred_display`, and never appears as an allowance in
`recent_turns`.

### D6 — Dashboard

- **The `AccountingDisplay` union** (`hub/ui/src/api/accounting.ts:29-44`) gains
  `{kind:'credits'; label; runner; ai_nano_aiu: number|null; premium_requests: number|null}`.
- **`accountingDisplayLabel`** gains the `credits` branch from D3. The stale comment at
  `accountingDisplay.ts:56` ("Copilot writes one on every run") is corrected to say Copilot writes a
  reading only when it reports a qualifying quota.
- **The worker lines** that worker-spend task 2.6 renders in `AccountingPanel.tsx` gain credits,
  formatted by `formatAiCredits`.
  - A credited line reads, for example, `checkpoint · 1.10 AI credits · 1 premium request`.
  - It never reads "usage unavailable".
- **The credits line** (`creditsLine`, `AccountingPanel.tsx:14-23`) and the Overview "AI credits"
  row need no new code. They read `project.ai_nano_aiu` and `premium_requests`, which now include
  the workers.
- **The Overview row titled "Allowance"** (`OverviewBudgetSummary.tsx:44-47`) keeps its title. It
  already mislabels the `api_equivalent` and `tokens` kinds, and renaming it is a separate concern.
- **The bundle** is rebuilt and copied to `hub/hub/static/ui` (`.claude/rules/hub-ui.md`).

### D7 — What happens if the operator's D7 for worker-spend differs

| Worker-spend D7 | `workers` lines | This change |
|---|---|---|
| **C** counted and gated (recommended there) | yes, in totals and the budget | D1–D6 whole. Worker credits join the project credit totals, and the budget still counts only tokens. |
| **D** counted, never refused | yes, in totals | The same as C. The budget gate does not matter to credits. |
| **B** its own line, not budgeted | yes, but **not** in the token total | D1 whole. D2 is `wpc6-e`. The recommended answer is to follow B, so worker credits stay **out** of the project credit totals and appear only on their lines. `preferred_display` (D3) uses the totals, so a Copilot project with no turn credits would still read "Tokens". |
| **A** outside everything | none | D1 has nothing to extend, and `copilot-oneshot-credits-oq1` falls. D3, D5 and the label half of D6 still apply, using turn credits only. Whether worker credits should still reach the project totals becomes `wpc6-e`. |

Under every option, **the token budget is untouched by this change**.

## Risks / Trade-offs

- **Overflow residual (F486), now with more summed sources.** It is accepted on the same terms as the
  turn path. Worker credits pass the same per-figure ceiling (`parse_copilot_envelope` calls
  `checkpoint_totals`, `runner_adapters/copilot.py:136`; `_CHECKPOINT_CEILING`,
  `copilot_usage.py:68`). PATCH-after-commit is the sharper symptom: a saved budget, a 500, and
  queued agents left unscheduled (D2).
- **A charged Copilot call that exits non-zero records no credits.** `_interpret` (`worker.py:428`)
  returns before parsing stdout on any outcome but `ok`, so a `nonzero_exit` or `timeout` row has
  NULL credits even if the CLI charged. That row lands in `unmeasured_calls`, which under-reports
  rather than misreports. It keeps the usage on `unparseable` and `schema_invalid`, which follow a
  clean exit, so a credited call can carry either outcome (task 1.17). The archived 10-06 change (design D4) deliberately left this alone: it is
  unverified whether `copilot -p` exits non-zero after charging, and a capture showing it would be a
  new finding. This change does not alter it.
- **The headline moves for every project with credits and no reading or cost** (D3 lists the four
  cases). "Tokens" or "Usage unavailable" becomes "Copilot AI credits". This is visible and
  intended, and the token figure is still the headline number above it
  (`AccountingPanel.tsx:88-90`). The least obvious case is a Codex project whose checkpoints run
  on Copilot (`wpc6-f`).
- **A Copilot title's credits depend on worker-spend's D4 being implemented to carry them** (R3).
  Its text does not require it, and its own titler test seeds a Claude envelope only. Task 2.7
  closes it from this side. A title whose CLI exits non-zero records no credits either, because
  `_run_titler` returns None and drops stdout (`conversation_titles.py:135-137`), the same residual
  as `_interpret`'s above.
- **Rebase risk.** Worker-spend's own cites are stale against `6208e9a5`:
  - its "migration 0106"; the head is now `0125`
  - `usage_accounting.py:207-219` and `:184`; `accounting_snapshot` now runs `:319-403`
  - `api/v1/accounting.py:79`; the PATCH return is now `:66-80`

  This change's tasks name functions, not line numbers, for anything worker-spend will move.
- **A Copilot one-shot's tokens are permanently unknown.** If a later Copilot CLI emits
  `assistant.usage` in one-shot mode, the parser should read it, and this change's `credited_calls`
  would then become `measured_calls` on its own. Nothing here prevents that.

## Migration Plan

There is no schema change. The worker credit columns exist (`0117`). The order of work:

1. Worker-spend lands, with its own migration renumbered after `0125`.
2. This change lands.

Rollback is a code revert. No data is rewritten.

## Round log

- **R1 (2026-10-12).** Re-derived WPC-6 from the trial DB and the code at `6208e9a5`.
  - Corrected the handoff's counts: 20 turns, a checkpoint plus a probe, and the mixed bases.
  - Found the following:
    - oq1 is unfulfilled.
    - Worker-spend's "unmeasured" class would swallow Copilot calls.
    - Turn credits are already aggregated.
    - The `'null'` allowance is harmless.
    - This licence produces no allowance reading.
    - PATCH /budget commits before it snapshots.
- **R2 (2026-10-12, work PC).** An independent re-derivation from the code at `6208e9a5` and the
  trial DB (`mode=ro`).
  - **Figures confirmed.** `turn_usage` has 20 rows, giving 19.0 and 154 000 145 000. `runs` and
    `inbound_queue_entries` each have 20, so "21 turns" is wrong. The 2 rows missing from
    `GET /accounting` are `wrk-fe6df82345e4` and `wrk-52953be92501`, because `accounting_snapshot`
    reads only `TurnUsage`. Adding them gives 155 924 675 000 and 21.0. The titler spent nothing
    (`conversation_title_mode='truncate'`).
  - **The one-shot fixture carries no token figure.** `oneshot_ok.jsonl` has 15 event types; tokens
    appear only in the nested `prompt_tokens` diagnostic, and `result.usage` has `premiumRequests`
    only.
  - **`'null'` is harmless at every reader.** SQLAlchemy JSON reads it back as `None`. Every DB
    reader tests `isinstance(..., dict)`: `usage_accounting.py:153, 234, 364, 372` and
    `provider_allowance.py:126`. `hold_for_reading` passes `None` on to `allowance_refusal`.
    `agent_trigger.py:3134` and `:4160` read the in-memory value. No raw `text(` query and no
    `IS NOT NULL` filter touches `allowance`.
  - **No exhaustive switch on the display kinds.** `accountingDisplayLabel` (`:40-77`) is an if-chain
    ending in `return display.label`. Its two callers are `AccountingPanel.tsx:29` and
    `OverviewBudgetSummary.tsx:46`. The only Python consumer is the route itself. No MCP or CLI reader
    exists. No test asserts `kind: "tokens"`. A `credits` kind already renders its `label` before
    the UI change. The existing test `test_copilot_credits_aggregate_alongside_claude_tokens`
    (`test_accounting_api.py:291`) has credits and no cost, so its unasserted kind moves to
    `credits` (task 1.10).
  - **Fixed, medium: the scope was too narrow.** The design said only checkpoint and probe calls write
    rows, and the spec defined a one-shot call as a checkpoint, a probe, or a title. All six
    `run_worker` call sites write rows, including three manager-job kinds (Context). Both texts are
    now generalised to every kind.
  - **Fixed, medium: the spec contradicted task 1.3.** The scenario "A call that reported nothing is
    still unmeasured" said the line's credit figures are null. That is false when the line also has a
    credited call, which is exactly 1.3's seed. It now says the call adds nothing to those figures.
  - **Fixed, low to medium: PATCH.** The commit is at :62, not :60. An overflow also skips the
    `schedule_agent` loop (:67-79) (D2, Risks). As with F486, no overflow test is added.
  - **Added, low: the non-zero-exit residual** (Risks).
  - **Fixed, low: cites.** `checkpoint_generation.py:566` and `:654` are the `kind=` lines; the calls
    are at `:564` and `:652`. `conversation_titles.py:304-308` becomes `:304-310`.
  - **Added: task 1.14,** a control for a manager-job kind.
  - **Checked: D7 coherence holds for A–D.** Under B the lines exist and carry credits whatever
    `wpc6-e` says. Under A, D3 reads turn credits only, which already exist. The spec delta states
    the C/D behaviour, and D7's table covers A and B through `wpc6-e`.
  - **Noted, not changed:** the allowance is chosen only from the newest 50 turns (`recent_limit`,
    `usage_accounting.py:320`). This is existing behaviour that `credits` inherits.
  - Open questions: none added, none changed.
- **R3 (2026-10-12, work PC).** Traced from the dashboard inwards at `6208e9a5`, the trial DB
  re-queried `mode=ro`.
  - **Confirmed.** All six `run_worker` call sites pass `kind=` and end in `_record`
    (`worker.py:388` → `:265`), which writes both credit columns (`:299-300`); the non-spawn
    outcomes carry an empty `WorkerUsage`. GET has no `try` (`api/v1/accounting.py:25-31`), and
    `main.py`'s two handlers (`:548`, `:560`) catch neither accounting error, so an overflow is a
    500; PATCH commits at `:62`, broadcasts at `:63-65`, snapshots at `:66`, schedules at `:67-79`,
    and reads only `total_tokens` at `:80`. The drive: 20 `copilot`/`measured` turns, tokens set,
    cost NULL, allowance the text `null`; two worker rows; no `manager_jobs` rows, so the titler
    never ran.
  - **Fixed, medium: the titler's credits were not guaranteed.** Worker-spend's D4 parses the
    envelope and records a row but never ties the row's usage to the parse; its test 11 is
    Claude-only. Task 2.7 filled, test 1.15 added, Risks updated. Noted, not changed: D4 is stale
    on flags (Copilot's title command already has `--output-format json`; Claude's has none).
  - **Fixed, low to medium: D3 understated who moves.** Four cases, not one (D3): including a Codex
    project with a Copilot checkpoint runner, and a project whose Copilot turns were all refused
    (`unavailable` → `credits`). New question `wpc6-f`; task 1.7 gains both cases. The ranking
    pins are named in task 1.10; none moves. No test pinned `tokens` or `unavailable`.
  - **Fixed, low to medium: no reconciliation invariant.** The project's credits could have
    disagreed with the chips plus worker lines the Budgets panel shows if the worker part came from
    its own query. D2 now derives it from the lines; task 1.16 pins `project = Σ agents + Σ
    workers`.
  - **Fixed, low: seed shapes.** The §1 preamble now states the ACP turn shape; without tokens,
    1.7's "FAILS today" would name `unavailable`. Task 1.9's `record_turn_usage(allowance=None)`
    does not exist as a call; it takes a `sample`. Task 1.11 lacked the `copilot_exe` fixture and
    the answer substitution its model test uses.
  - **Added, low: a credited call that is not `ok`** (task 1.17, the unmodified fixture gives
    `unparseable` with credits). **Noted, low:** task 1.12's "1 premium request" is new
    pluralisation; `creditsLine` always prints the plural.
  - **Fixed, cite:** the Overview "AI credits" row is `:38-43`, not `:36-41`.
  - Open questions: `wpc6-f` added; `wpc6-e` sharpened (under D7-A its "yes" leaves an
    unexplained gap on the panel).

## Open Questions

Each needs the operator's decision. The design assumes the recommended answer.

- **wpc6-a — Should a Copilot budget be expressible in premium requests or AI credits?**
  - The options:
    - (1) Keep tokens only.
    - (2) Add an optional second limit in premium requests.
    - (3) Let the budget's unit follow the runner.
  - **Recommend (1).** `ghcp-d3-credits` already decided it. A second limit would need its own pause
    and resume semantics, its own refusal path in `inbound_queue.py:211` and `turn_scheduler.py:364`,
    and a premium-request figure for every Claude turn, which has none.
  - Picking (2) makes it a new change with new spec text under "A project token budget pauses
    autonomy but not the operator", not a delta here.
- **wpc6-b — Should project accounting show mixed units side by side?**
  - The options:
    - (1) Yes: each in its own unit, never converted.
    - (2) Convert to one estimate.
    - (3) Show only the preferred unit.
  - **Recommend (1).** It is the existing pattern (the token headline, the credits line, the
    dollars), and the two currencies have no honest exchange rate.
  - Picking (2) needs a priced rate table that nobody maintains today.
- **wpc6-c — Should `preferred_display` follow the dominant runner?**
  - The options:
    - (1) Follow which data exists (D3).
    - (2) Follow the runner with the most turns or calls.
    - (3) Return one display per runner (archived 10-02 Q9).
  - **Recommend (1).** It is stable: a headline never flips because the turn mix shifted by one run.
  - (3) stays an additive option for later.
  - Picking (2) replaces D3's ranking with a count, and the "only Copilot credits" scenario becomes
    "dominant runner".
- **wpc6-d — Who carries the worker-line credit sums that `copilot-oneshot-credits-oq1` assigned to
  worker-spend's next round?**
  - **Recommend this change.** Worker-spend's R2 and R3 are closed, and re-opening it for this would
    re-run both rounds. Record oq1 as re-pointed here in `spec-queue/DECISIONS.md`.
  - If the operator prefers worker-spend, fold D1 into it and drop D1 from here.
- **wpc6-e — Under worker-spend D7-A or D7-B, should worker credits still reach the project credit
  totals?**
  - **Recommend no.** Follow D7 for both units, so that tokens and credits never disagree about what
    "the project's total" includes.
  - Under D7-A there are no worker lines, so "yes" would also put credits in the project total that
    nothing on the Budgets panel accounts for (D2, R3).
  - Asked only if D7 is A or B.
- **wpc6-f — Should worker credits alone move the headline to `credits`? (new, R3)**
  - The case: a project with no allowance reading, no cost and no Copilot turns, whose only Copilot
    spend is worker calls, for example a Codex project with a Copilot checkpoint runner.
  - The options:
    - (1) Yes: D3 reads the project credit totals, which include workers (D2).
    - (2) No: D3 ranks on turn credits only, and the headline stays "Tokens".
  - **Recommend (1).** It is one notion of the project's credits, and it follows `wpc6-c`'s rule
    that the data which exists picks the headline. (2) would make the headline and the "AI credits"
    row beside it disagree about whether credits exist.
  - Asked only when worker credits reach the totals (D7 C or D, or `wpc6-e` = yes).
