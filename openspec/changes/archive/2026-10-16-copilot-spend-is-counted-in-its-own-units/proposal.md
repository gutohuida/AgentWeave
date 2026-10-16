> **Moved to the app 2026-10-16, archived.** Successor: `spec/changes/copilot-spend-is-counted-in-its-own-units/spec.json` (built f6701ef; folded into `usage-accounting`). D1-D3 and D6 were built as written on wpc6-a..c; wpc6-d and wpc6-f were taken as recommended and stay open; D5 is the control test. Not driven live: a Copilot worker call spends premium requests.

# Proposal — Copilot spend is counted in its own units

**Round 1, 2026-10-12** (finding **WPC-6 (low)**, from the work-PC Copilot drive, handoff
`.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`, and three accounting siblings).
Verified against HEAD `6208e9a5` and the drive's trial database (alembic head `0125`). **Depends on
`worker-spend-counts-against-the-budget`**, which is past R3, parked on the operator's D7 and not
implemented. **Nothing here is implemented yet.**

## Why

A Copilot checkpoint costs premium requests and AI credits, and the project's accounting does not
count them. It cannot be fixed the way `worker-spend-counts-against-the-budget` fixes the same gap
for Claude and Codex, because a Copilot one-shot call reports **no tokens at all**: its whole spend
is the credits.

### The drive's evidence (trial DB `profiles/workpc-drive/agentweave.db`, read-only)

Project `proj-d73f8848ee60`, `token_budget` NULL. `turn_usage` holds **20** rows, all agent `cop-1`,
runner `copilot`, status `measured` (19 `completed` runs and 1 `stopped`; the second agent, `cop-rev`,
never ran). Their sums: **19.0 premium requests** (run `run-57863f48fba0`, on the `gpt-5-mini`
override, charged 0.0), **154.000145 AI credits** (`ai_nano_aiu` 154 000 145 000), and 2 516 676
tokens. `api_equivalent_usd_micros` is NULL on every row.

`worker_invocations` holds two rows for conversation `conv-677f99c2b146`, cli `copilot`, runner
`runner-d4c6a928e95a`, model NULL, with every token and cost column NULL:

| id | kind | prompt_version | `ai_nano_aiu` | `premium_requests` |
|---|---|---|---|---|
| `wrk-fe6df82345e4` | `checkpoint` | `checkpoint/1` | 1 102 140 000 (1.10 credits) | 1.0 |
| `wrk-52953be92501` | `checkpoint_probe` | `checkpoint-probe/2` | 822 390 000 (0.82 credits) | 1.0 |

So the project spent **21 premium requests and 155.92 AI credits**, and `GET /accounting` reports
**19 and 154.00**.

**The handoff is wrong in three details.** It says "21 turns" (there were 20), "two checkpoint
worker calls" (a checkpoint and its probe), and "19 premium requests and about 156 AIU". Those two
figures are on different bases: 19 is turns-only and 156 includes the workers. On one basis the
figures are 19 and 154.00; on the other, 21 and 155.92.

### Where the spend goes missing

- **The parser can only yield credits.** `parse_copilot_envelope`
  (`hub/hub/runner_adapters/copilot.py:97`) fills `WorkerUsage` with `ai_nano_aiu` and
  `premium_requests` from the last `session.usage_checkpoint`, and nothing else. The captured
  envelope `hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl` (CLI 1.0.88) has no token count the
  parser reads. Its one token figure, a nested `prompt_tokens` diagnostic, is deliberately ignored
  because it is input-only (archived change `2026-10-06-a-copilot-one-shot-records-its-credits`,
  design D3). A Copilot worker row's tokens are therefore NULL by construction, not by accident.
- **No reader sums worker credits.** `accounting_snapshot` (`hub/hub/usage_accounting.py:319-403`)
  aggregates `TurnUsage` only, through `_aggregate_columns` (`:291-306`). That function already sums
  `ai_nano_aiu` and `premium_requests` for turns (`:304-305`). `WorkerInvocation.ai_nano_aiu` and
  `premium_requests` (`hub/hub/db/models.py:1977-1978`, migration `0117`) are written
  (`hub/hub/worker.py:299-300`) and read by nothing. The 10-06 change left it that way on purpose
  and handed the read to `worker-spend-counts-against-the-budget`.
- **The hand-off was decided and never carried out.** `spec-queue/DECISIONS.md:321-351`
  (`copilot-oneshot-credits-oq1`, decided 2026-10-04): worker-spend's next round would gain
  per-`workers`-line credit sums. Worker-spend's last commit is `3cfe0f00`. None of its files
  mentions credits, nano-AIU, Copilot or premium requests.
- **Worker-spend would count a Copilot call as unmeasured.** Its design D2 makes a *measured call*
  one with `total_tokens` not null, and an *unmeasured call* one that spawned and "reported no
  usage". A Copilot checkpoint that reported 1.10 credits would be counted in `unmeasured_calls`, and
  its credits would appear nowhere.
- **It is not only checkpoints (R2).** Every `run_worker` call writes a `worker_invocations` row,
  so a Copilot runner's distillation, reports and spec-vault-check calls are one-shot calls too. The
  drive happened to fire only a checkpoint and its probe. The fix is per kind (design Context).

### The siblings

- **(i) `preferred_display` reads "Tokens" for an all-Copilot project.** It is computed at
  `usage_accounting.py:371-395`, in the order allowance → `api_equivalent` → `tokens` →
  `unavailable`. There is no credits kind. A Copilot run writes an allowance reading only when a
  quota snapshot qualifies or the run was refused (`quota_reading`, `copilot_usage.py:144-181`;
  `_qualifying_snapshot`, `:106`). None of the drive's 20 rows has a reading, and none reported a
  cost, so the project falls through to `{"kind":"tokens"}`. The Overview's "Allowance" row then
  prints "Tokens" (`OverviewBudgetSummary.tsx:44-47`; `accountingDisplayLabel` falls through at
  `accountingDisplay.ts:76`). The comment at `accountingDisplay.ts:56` ("Copilot writes one on every
  run") is not true on this licence.
- **(ii) `turn_usage.allowance` is the text `'null'` on all 20 rows** (`typeof` = `text`, so
  `allowance IS NOT NULL` matches all 20). The writer is `record_turn_usage`
  (`usage_accounting.py:64`), writing into a SQLAlchemy `JSON` column (`models.py:1348`) that
  serialises Python `None` as JSON `null`. This is already known (`provider_allowance.py:123-126`).
  Every reader tests `isinstance(..., dict)` (`usage_accounting.py:153, 234, 364, 372`, and
  `provider_allowance.py`), and no reader filters on `IS NOT NULL`. **It is harmless today, and this
  change does not alter it.** It adds a control test, so that a reader written later cannot trip on
  it unnoticed.
- **(iii) A Copilot turn counts against `token_budget` by its tokens, and its credits never do.**
  This is on purpose. The spec scenario "Credits do not count against the budget"
  (`openspec/specs/usage-accounting/spec.md:171-265`) requires it, `project_budget_state`
  (`usage_accounting.py:424-435`) implements it, and the operator decided it (`ghcp-d3-credits`,
  `spec-queue/DECISIONS.md`: "tokens stay the accounting unit"). A Copilot turn's tokens are real.
  They come from ACP per-call usage through `_accounting_from_dimensions(source="copilot_calls")`
  (`copilot_usage.py:296-306`), or from the prompt result, whichever total is larger (`:330-341`).
  **This change keeps that rule.** It does state one consequence: a Copilot one-shot call has no
  tokens, so it can never count against a token budget (design D4).

## What Changes

- **Each `workers` line gains credit sums.** A `workers` line is the per-kind line that worker-spend
  adds to `GET /projects/{pid}/accounting`. Each line gains `ai_nano_aiu` and `premium_requests`
  (null when no call of that kind reported one) and `credited_calls`. A call that reported credits
  but no tokens is a *credited call*, not an *unmeasured* one.
- **The project's `ai_nano_aiu` and `premium_requests` include the worker calls.** On the drive
  they become 155 924 675 000 and 21.0. The agents' figures and the conversation rollup stay
  turns-only, just as worker-spend keeps their tokens turns-only.
- **`preferred_display` gains a kind, `credits`.** It applies when no allowance reading and no
  reported cost exist, and credits are known. It ranks before `tokens`, carries the credit figures,
  and has `runner: "copilot"`. R3: this moves the headline of every project in that state, not only
  a mixed one: an all-Copilot project, a mixed one with no cost, a Codex project whose checkpoint
  runner is Copilot (question `wpc6-f`), and a project whose only Copilot turns were refused
  (design D3). A pure Claude or Codex project does not move.
- **A Copilot conversation title records its credits (R3).** Worker-spend's D4 records the title
  call, but does not say its row carries the parsed usage. Task 2.7 makes it do so.
- **The project's credits reconcile with what the panel lists (R3).** The worker part is the sum of
  the `workers` lines, so the project's figures equal the agents' plus the workers'.
- **The token budget is unchanged.** Credits are still never budgeted, and a Copilot one-shot call
  still contributes no tokens. The spec now says the second fact explicitly.
- **The dashboard follows:**
  - The Budgets credits line and the Overview AI-credits row show the figures with worker calls
    included.
  - A Copilot worker line shows its credits rather than "usage unavailable".
  - `accountingDisplayLabel` names the `credits` kind.
  - The bundle is refreshed.
- **The `'null'` allowance is unchanged.** Only a control test is added.

## Capabilities

### Modified Capabilities

- `usage-accounting`: two ADDED requirements, "A Copilot one-shot call's credits count in the
  project's credit totals" and "When credits are the only spend a project reports, the preferred
  display names them".
  - They extend two worker-spend requirements: the ADDED "Every model call the Hub makes for a
    project is recorded", and the MODIFIED "Usage aggregates by agent and project" (its `workers`
    lines and its clause "a call that started but reported no usage").
  - They do not re-modify either block, so the two deltas cannot conflict.
  - Nothing here touches "A project token budget pauses autonomy but not the operator".
- `conversation-checkpoint`: **no delta.** Its scenario "Every invocation is accountable"
  (`openspec/specs/conversation-checkpoint/spec.md:61-64`) asks only that a call be recorded.
  Counting what the record costs belongs to `usage-accounting`.

## If the operator rejects or changes D7

D7 is worker-spend's first question: should worker spend join the totals and the budget?

- **C** (recommended there) or **D** (counted, never refused): the `workers` lines exist and their
  tokens join the totals, so this change applies whole. The budget is unaffected in every case,
  because credits are never budgeted.
- **B** (its own line, not budgeted): the `workers` lines exist, but their tokens stay out of the
  project total. D1 applies whole. D2 (worker credits in the project credit totals) becomes question
  `wpc6-e`. The recommended answer is to follow D7, which keeps worker credits on their lines only.
- **A** (outside everything): there are no `workers` lines, so design D1 has nothing to extend.
  `copilot-oneshot-credits-oq1`, which presupposed those lines, falls with it. D3 (the `credits`
  display kind), D5, and the display half of D6 still stand alone. D2 becomes question `wpc6-e`: an
  operator who keeps worker *tokens* out of the totals may still want worker *credits* in. The
  design explains what that costs.

## Impact

- `hub/hub/usage_accounting.py`:
  - credit columns on worker-spend's worker-line query
  - the addition to the project totals
  - the `credits` branch of `preferred_display`
- `hub/hub/conversation_titles.py`, only if worker-spend's D4 row does not already carry the
  title's parsed usage (task 2.7)
- The dashboard and its bundle:
  - `hub/ui/src/api/accounting.ts`
  - `hub/ui/src/components/accounting/accountingDisplay.ts` and `AccountingPanel.tsx`
  - `hub/ui/src/components/overview/OverviewBudgetSummary.tsx`
  - the committed bundle `hub/hub/static/ui`
- Tests:
  - a new `hub/tests/test_copilot_spend_in_its_own_units.py`
  - new cases in `hub/ui/src/__tests__/accountingPresentation.test.tsx` and
    `overviewBudgetSummary.test.tsx`
  - no existing assertion is reversed. No backend test pins `kind: "tokens"`, and the seeded
    projects in `hub/tests/test_accounting_api.py` that carry credits also carry an allowance or a
    cost, or assert nothing about the display (tasks §1.10 names the five that pin the ranking).
- **No migration.** The worker credit columns exist (`0117`), and worker-spend brings the one
  migration this change depends on (`total_tokens`).
- No MCP tool reads accounting: `accounting_snapshot`'s only callers are in
  `hub/hub/api/v1/accounting.py`. There is no CLI change.
