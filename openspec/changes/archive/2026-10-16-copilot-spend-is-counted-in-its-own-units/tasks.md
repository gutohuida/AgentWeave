## 0. Rounds and decision

- [x] 0.1 R2: an independent re-derivation of WPC-6. Do not re-read R1 first. (Done 2026-10-12 on
      the work PC; see design.md's Round log.)
      - Trace from the database outwards: `worker_invocations` (`db/models.py`, `WorkerInvocation`)
        → `hub/hub/worker.py` (`run_worker`, `record_invocation`) →
        `hub/hub/runner_adapters/copilot.py` (`parse_copilot_envelope`) →
        `hub/hub/usage_accounting.py` (`accounting_snapshot`, `_aggregate_columns`,
        `_summary_from_row`, `project_budget_state`) → `hub/hub/api/v1/accounting.py` →
        `hub/ui/src/components/accounting/*` and `components/overview/OverviewBudgetSummary.tsx`.
      - Read `openspec/changes/worker-spend-counts-against-the-budget/` in full, and check whether
        this change's D1 really extends its D2 without re-modifying any of its requirement blocks.
      - Try to break three claims:
        - Can a Copilot one-shot call ever carry tokens? Check every Copilot CLI fixture under
          `hub/tests/fixtures/copilot_acp/`.
        - Is `'null'` truly unread by SQL? Grep `allowance` across `hub/hub/`, including raw `text(`
          queries.
        - Does any consumer of `preferred_display` switch on `kind` exhaustively, so that a new kind
          would break it? Check `AccountingPanel.tsx` and `OverviewBudgetSummary.tsx`, and grep the
          rest of `hub/ui/src`.
      - Re-query the trial DB read-only (`mode=ro`) and confirm the R1 figures.
      - Record the round in design.md's Round log.
- [x] 0.2 R3: a second independent re-derivation, traced from the dashboard inwards, starting at the
      Budgets panel's credits line and the Overview's "Allowance" row. (Done 2026-10-12 on the work
      PC; see design.md's Round log.)
      - Ask what `GET /accounting` and `PATCH /accounting/budget` **return** when the new worker
        credit sum raises. Read `api/v1/accounting.py` from the commit at :62 onwards, including
        the `schedule_agent` loop that R2 found an overflow skips (design D2).
      - Ask whether worker-spend's D4 titler path records a Copilot title's credits. Its
        `record_invocation(result)` must carry the `envelope_usage` that `parse_copilot_envelope`
        already returns in `conversation_titles.py`. If it does not, add a task here (2.7).
      - Run `npx openspec validate copilot-spend-is-counted-in-its-own-units --strict`.
      - Record the round in design.md's Round log.
- [ ] 0.3 The operator answers design Open Questions wpc6-a through wpc6-d, wpc6-e only if
      worker-spend's D7 is A or B, and wpc6-f whenever worker credits reach the project totals
      (D7 C or D, or `wpc6-e` = yes). The answers go in `spec-queue/DECISIONS.md`, together with one
      line re-pointing `copilot-oneshot-credits-oq1` (`DECISIONS.md:321-351`) to this change.
      Implementation waits for worker-spend's D7 **and** for worker-spend to land, because D1 edits
      the query that change creates.

## 1. Tests first — each must fail on today's code unless marked as a control

New file `hub/tests/test_copilot_spend_in_its_own_units.py`.

- Seed `TurnUsage` and `WorkerInvocation` rows directly into `proj-test`, as
  `hub/tests/test_accounting_api.py::_seed_usage` does.
- Use the drive's real figures: turns totalling 154 000 145 000 nano-AIU and 19.0 premium requests
  (any split of rows that sums exactly will do, with one row of 0.0 premium requests as on the
  drive). Add `checkpoint` 1 102 140 000 / 1.0 and `checkpoint_probe`
  822 390 000 / 1.0, with `cli="copilot"`, `outcome="ok"`, and every token and cost column NULL.
- Seed the turns in the shape the ACP path writes (`record_turn_usage` after
  `settle_copilot_credits`), which is what the drive's 20 rows hold (R3, re-queried `mode=ro`):
  `runner="copilot"`, `status="measured"`, `total_tokens` set (the drive's sum is 2 516 676),
  `api_equivalent_usd_micros` NULL, and `allowance` None. A turn seeded without tokens makes
  today's `preferred_display` `unavailable`, not `tokens`, and 1.7's "FAILS today" claim would
  then name the wrong kind.
- "Fails today" means fails on worker-spend's landed code. Before that change lands, the `workers`
  key does not exist, and the tests fail on that instead.

- [ ] 1.1 The project's totals include the workers. `GET /projects/proj-test/accounting` returns
      `project.ai_nano_aiu == 155_924_675_000` and `project.premium_requests == 21.0`. Record that it
      FAILS today (154 000 145 000 and 19.0).
- [ ] 1.2 The worker lines carry credits. The `checkpoint` line has `ai_nano_aiu == 1_102_140_000`,
      `premium_requests == 1.0`, `credited_calls == 1`, `unmeasured_calls == 0`,
      `measured_calls == 0`. The `checkpoint_probe` line is the same, with 822 390 000. Record that
      it FAILS (worker-spend counts each call as unmeasured and has no credit keys).
- [ ] 1.3 A call that reported nothing stays unmeasured. Add a Copilot `checkpoint` row with
      `outcome="timeout"` and every usage column NULL. The line's `unmeasured_calls == 1` and
      `credited_calls == 1`, and its credit sums are unchanged. Also add a `spawn_failed` row; it is
      counted in neither. FAILS (no `credited_calls`).
- [ ] 1.4 Control: the agents stay turns-only. The `cop-1` agent's figures are 154 000 145 000 and
      19.0. PASSES today and must keep passing.
- [ ] 1.5 Control: the budget is unchanged. Set `token_budget`. `budget.used_tokens` and
      `project.total_tokens` equal the turn token sum, and `PATCH /accounting/budget` returns the
      same `used_tokens`. PASSES today and must keep passing.
- [ ] 1.6 Control: `GET /accounting/conversations/{id}` for the conversation the workers name
      returns turn-only credits. PASSES today and must keep passing.
- [ ] 1.7 The preferred display names credits. For 1.1's seed (no allowance, no cost):
      `preferred_display == {"kind": "credits", "label": "AI credits", "runner": "copilot",
      "ai_nano_aiu": 155_924_675_000, "premium_requests": 21.0}`. A second case has turn credits only
      and no workers, and still gives `credits`. Record that it FAILS today (`kind: "tokens"`).
      Two further cases (R3), each a headline move that D3 now names:
      - Worker credits alone: one Codex turn (`runner="codex"`, tokens, no cost, no allowance) and
        one Copilot `checkpoint` row with credits — a Codex project whose `checkpoint_runner_id`
        is a Copilot runner (`checkpoint_trigger.py:155-157`). Gives `credits` with the worker's
        figures (assumes `wpc6-f` = yes). FAILS today (`kind: "tokens"`).
      - A quota-refused Copilot turn: `status="unavailable"`, no tokens, `ai_nano_aiu` set (the
        case `record_turn_usage`'s own comment names, `usage_accounting.py:65-67`). Gives
        `credits`. FAILS today (`kind: "unavailable"`).
- [ ] 1.8 Precedence controls, which PASS today and must keep passing:
      - add one Claude turn with `api_equivalent_usd_micros=10_000`; the result is `api_equivalent`
      - add instead a Copilot turn with `allowance={"remainingPercentage": 40, ...}`; the result is
        `allowance` with `runner: "copilot"`
      - a project with no credits gives `tokens`
- [ ] 1.9 Control, the `'null'` allowance:
      - Record a turn through `record_turn_usage(..., runner="copilot",
        sample=AccountingSample(source="copilot_calls", total_tokens=..., ai_nano_aiu=...))`, whose
        `allowance` defaults to None. `record_turn_usage` takes a `sample`, not an `allowance=`
        keyword (`usage_accounting.py:25-36`; `AccountingSample` is `runner_events.py:384`).
      - Assert, with raw SQL, that `typeof(allowance) = 'text'` and the value is `'null'`. This pins
        today's storage.
      - Assert that `preferred_display` is not `allowance`, and that the turn's `recent_turns` entry
        has `allowance` None.
      - PASSES today and must keep passing.
- [ ] 1.10 Re-run `hub/tests/test_accounting_api.py` unchanged and confirm that no existing
      assertion breaks. R1 found that no test pins `kind: "tokens"`. The seeds with Copilot credits
      (`test_copilot_credits_aggregate_alongside_claude_tokens`, `:291`, and
      `test_conversation_accounting_sums_a_conversations_copilot_credits`, `:445`) either have a cost,
      an allowance, or no display assertion. If one breaks, the expectation changes only where D3
      says it should, and the reason is recorded here. R2 found that `:291` seeds Copilot credits
      with no cost and no allowance, so its `preferred_display` moves from `tokens` to `credits`. It
      asserts no kind today. Add that assertion there, since this is the case D3 says moves.
      R3: the tests that pin today's ranking, all in `hub/tests/test_accounting_api.py`, and none
      moves under D3 because each has an allowance or a cost:
      - `test_allowance_precedes_api_equivalent_and_unavailable_is_not_zero` (`:137`, asserts
        `:143`): allowance over a Claude cost.
      - `test_api_equivalent_label_is_explicit_when_no_allowance` (`:154`, `:173`): Claude cost.
      - `test_unpriced_turns_counts_every_turn_with_no_reported_cost` (`:184`, `:225`): a Claude
        cost over Codex tokens, the mixed case.
      - `test_claude_only_project_has_null_credits_everywhere` (`:367`, `:386`): allowance, credits
        null.
      - `test_newer_copilot_allowance_displaces_claude_with_its_own_runner_name` (`:395`, `:436`):
        an allowance beats Copilot credits.
      Nothing pins `tokens` or `unavailable` today; 1.8's third bullet becomes the `tokens` pin.
- [ ] 1.11 End to end through the real parser:
      - Run `ONESHOT_FIXTURE` (`hub/tests/test_worker.py:468`) through `run_worker` with a copilot
        runner, the same way `test_a_copilot_one_shots_credits_reach_its_invocation_row_unpatched`
        (`:687`) does: the `copilot_exe` fixture, `Path.home` patched to `tmp_path`, the fixture's
        `assistant.message` replaced by a schema-valid answer (its own content is `"ok"`), the
        spawn patched with `_patch_spawn`, `_run(cli="copilot", model="auto")` (kind
        `checkpoint`, project `proj-test`), and the `initiator` that worker-spend makes
        keyword-only.
      - Then `GET /accounting`. The project shows `ai_nano_aiu == 32_840_000` and
        `premium_requests == 1.0`, and the `checkpoint` line has `credited_calls == 1`.
      - FAILS today.
- [ ] 1.12 UI (vitest) in `hub/ui/src/__tests__/accountingPresentation.test.tsx`:
      - `accountingDisplayLabel({kind:'credits', ...})` returns
        `'Copilot AI credits · no allowance reported'`, and the panel renders that text. FAILS
        (today it falls through to `label`).
      - A `workers` line with credits and no tokens renders `1.10 AI credits · 1 premium request`,
        and does not render "usage unavailable". FAILS. The singular is new formatting: the
        existing `creditsLine` (`AccountingPanel.tsx:16-23`) always says "premium requests", so
        the worker line needs its own pluralisation rather than a reuse of `creditsLine` (R3).
      - A control: the existing credits-line tests (`:284-350`) pass unchanged.
- [ ] 1.13 UI in `hub/ui/src/__tests__/overviewBudgetSummary.test.tsx`:
      - Make the mocked `preferred_display` mutable, as `project` already is.
      - With `kind: 'credits'`, the summary reads "Copilot AI credits" and not "Tokens". FAILS.
- [ ] 1.14 Every worker kind is counted, not only checkpoints (R2):
      - Seed a Copilot `WorkerInvocation` with `kind="vault-distillation"` (`manager.DISTILLATION`),
        `outcome="ok"`, 50 000 000 nano-AIU and 1.0 premium request, and NULL tokens.
      - Its line has `credited_calls == 1` and those credits.
      - The project totals include them.
      - FAILS today.
- [ ] 1.15 A Copilot conversation title records its credits (R3, the titler finding):
      - Set up as worker-spend's titler tests do (its tasks 1.4, tests 11 and 12): the titles job
        enabled with a copilot runner, a resolvable workspace, and the `copilot_exe` fixture.
        Patch `_run_titler` to return `hub/tests/fixtures/copilot_acp/oneshot_ok.jsonl` verbatim.
      - Expect one `WorkerInvocation` with `kind="conversation_title"`, `ai_nano_aiu ==
        32_840_000`, `premium_requests == 1.0` and NULL tokens, and a `conversation_title` line
        with `credited_calls == 1`.
      - FAILS on today's HEAD (no row: `conversation_titles.py:304-329` puts the parsed usage only
        in the `manager_job_fired` payload). On worker-spend's landed code it fails unless its D4
        `record_invocation` carries the parsed usage; if it passes there, record that it is a guard.
- [ ] 1.16 The project's credits reconcile with the breakdown the dashboard shows (R3):
      - On 1.1's seed plus 1.14's row, assert `project.ai_nano_aiu == Σ agents[].ai_nano_aiu +
        Σ workers[].ai_nano_aiu`, and the same for `premium_requests` with `pytest.approx` (the
        float sums are computed in different orders).
      - FAILS today (no `workers` key, or no line credits on worker-spend's code).
- [ ] 1.17 A credited call need not be `ok` (R3):
      - Run `ONESHOT_FIXTURE` **unmodified** through `run_worker` as 1.11 does. Its answer is the
        prose `"ok"`, so the outcome is `unparseable`, and `_interpret` (`worker.py:428`) keeps the
        usage on that outcome and on `schema_invalid`.
      - Its `checkpoint` line has `credited_calls == 1`, `unmeasured_calls == 0`, and
        32 840 000 / 1.0.
      - FAILS today (worker-spend counts it unmeasured).

## 2. Implementation

- [ ] 2.1 Worker-spend's worker-line query (in `accounting_snapshot`, whatever its line numbers are
      once it lands):
      - add `func.sum(WorkerInvocation.ai_nano_aiu)` and `func.sum(WorkerInvocation.premium_requests)`
      - add a `credited_calls` count: spawned, `total_tokens IS NULL`, and either credit column NOT
        NULL
      - narrow `unmeasured_calls` to exclude those calls
- [ ] 2.2 Project credit totals: add the worker sums to the turn sums from `_aggregate_columns`, with
      None handling (design D2). Take the worker sums **from the lines 2.1 builds**, summed in
      Python, not from a separate query, so the total cannot disagree with the lines (task 1.16).
      Leave the agent and `conversation_usage` paths alone.
- [ ] 2.3 `preferred_display`: insert the `credits` branch after `api_equivalent` and before
      `tokens` (design D3).
- [ ] 2.4 `hub/ui/src/api/accounting.ts`:
      - the `credits` member of `AccountingDisplay`
      - credit fields and `credited_calls` on worker-spend's worker-line type
- [ ] 2.5 `accountingDisplay.ts`:
      - add the `credits` branch to `accountingDisplayLabel`
      - correct the comment at `:56`
      - in `AccountingPanel.tsx`'s worker lines (worker-spend task 2.6), show credits through
        `formatAiCredits`
- [ ] 2.6 Rebuild the bundle (`make ui` or `scripts/refresh_ui_bundle.py`). Confirm
      `diff -rq hub/ui/dist hub/hub/static/ui`. Commit `hub/ui/src` and `hub/hub/static/ui`
      together.
- [ ] 2.7 The titler's row carries the parsed credits (R3). Worker-spend's D4 has
      `generate_conversation_title` call `worker.parse_envelope(cli, stdout)` and then
      `record_invocation(kind="conversation_title", ..., result)`, but never says that
      `result.usage` is the parsed usage, and its titler test is Claude-only. Today's code parses a
      Copilot envelope (`conversation_titles.py:304-311`) and sends the usage only to
      `manager.usage_record`.
      - In `hub/hub/conversation_titles.py`, once worker-spend's titler has landed, make sure the
        `WorkerUsage` returned by the parse, for every CLI and Copilot included, is the `usage` of
        the result handed to `record_invocation`, on every exit that parsed output, including a
        parse error (credits survive `unparseable`, as in `_interpret`).
      - Leave the `manager_job_fired` payload as it is.
      - A non-zero exit still records no credits: `_run_titler` returns None on a non-zero
        return code (`conversation_titles.py:135-137`) and discards stdout. That is the same
        residual as `_interpret`'s (design Risks), and is not changed here.
      - Task 1.15 is the test.
- [ ] 2.8 Sync the two ADDED requirements into `openspec/specs/usage-accounting/spec.md` at archive
      time, after worker-spend's delta has been synced.
- [ ] 2.9 Run the verification suite:
      - `py -3.11 -m pytest hub/tests/ -q`
      - `cd hub/ui; npx vitest run; npx tsc --noEmit; npm run lint`
      - `ruff check hub/`
      - `black --check hub/hub/ hub/tests/ --target-version py311`
      - `npx openspec validate --specs --strict`

## 3. Live drive

- [ ] 3.1 On a trial Hub run from source, never `:8000`:
      - Use a project with one Copilot agent, run three turns, and force a checkpoint and its probe.
      - Compare `GET /projects/{pid}/accounting` against read-only sums of `turn_usage` and
        `worker_invocations` for that project. `project.ai_nano_aiu` and `premium_requests` must
        equal turns plus workers. `total_tokens` and `budget.used_tokens` must equal turns plus any
        Claude or Codex worker tokens only.
      - The Budgets panel's worker lines must show credits.
      - The Overview must show "Copilot AI credits · no allowance reported", unless the licence
        reports a qualifying quota.
      - Record the figures in design.md's Round log.
