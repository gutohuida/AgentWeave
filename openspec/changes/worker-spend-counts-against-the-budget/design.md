# Design — worker spend counts against the budget

**Built on the recommended answer to D7 (first question): worker spend joins the total as its own
lines, counts against the budget, and autonomous worker calls pause at exhaustion.** If the operator
answers *"its own line, but not against the budget"*, drop D3 and the budget half of D2, and keep
D1, D4 and the `workers` lines: the titler's row and the visible total are not a decision (F240:
*"the titler must write an invocation row like every other worker, or its cost is
unrecoverable"*). If they answer *"counts, but is never refused"*, drop D3 only.

## The options for D7 (worker spend), with evidence

| Option | What it releases | What it breaks or costs |
|---|---|---|
| **A. Outside everything (today)** | Nothing | Money leaves, unseen, in the state the operator set specifically to stop it (F240, driven) |
| **B. Shown as its own line, not budgeted** | Visibility | The budget still does not bound spend. An operator who sets a budget to cap spending keeps spending at exhaustion, which is F240's defect |
| **C. Counted and gated like turns (recommended)** | One meaning for "budget": every model call the Hub makes for a project, autonomous ones paused at exhaustion, operator ones always available. That is the rule `usage-accounting` already states for turns | A migration. An automatic checkpoint at exhaustion is not taken; the operator is told one is due (D3a, and the proposal's table) |
| **D. Counted, never refused** | Totals are honest | Same defect as B at exhaustion |

C is the only option where *"Autonomous turns are paused; operator messages can still run"*
(`BudgetExhaustionNotice.tsx:12`) is true of everything the Hub spends.

## D1 — one normalised total per worker call

`WorkerUsage` gains `total_tokens`. `parse_claude_envelope` (`worker.py:231-262`) and
`parse_codex_envelope` (`:264-312`) build it with
`runner_parsing._accounting_from_dimensions(raw_usage, source="worker", cache_is_separate_input=<True for Claude, False for Codex>)`,
the same call and flag the turn path uses: Claude at `runner_parsing.py:334-340`, Codex exec at
`:578-583`. **Why this matters:** F240 counted the probe as `in=10 out=215`. A Claude worker's
`input_tokens` excludes cache (`worker.py:232-236`, *"it read 2 input tokens against 47091 cache
reads"*), so a sum of `input + output` would under-count a worker by roughly 100× against how a turn
is counted.

`WorkerInvocation.total_tokens` (nullable Integer) is written by `record_invocation` (today's
`_record`, made public for D4).

**Migration `0106`** (per `.claude/rules/db-migrations.md`):
1. Guard on the table existing (as `0033` and `0034` do).
2. `batch_alter_table`: add `total_tokens`, and recreate `ck_worker_invocations_outcome` with
   `budget_exhausted` added to `WORKER_OUTCOMES` (`db/models.py:1846-1855`).
3. Backfill: for `cli='claude'`,
   `COALESCE(input,0)+COALESCE(cache_read,0)+COALESCE(cache_write,0)+COALESCE(output,0)`; for
   `cli='codex'`, `COALESCE(input,0)+COALESCE(output,0)`. In both cases only where `input_tokens`
   or `output_tokens` is not null. Otherwise leave it null (unknown, never zero).
4. Bump `HEAD_REVISION` (`hub/tests/test_migrations.py:40`) and `test_project_persistence.py:227`.

## D2 — one `used_tokens`

`usage_accounting.used_tokens(db, project_id) -> Optional[int]` is the measured `TurnUsage.total_tokens`
sum plus the `WorkerInvocation.total_tokens` sum, or None when both are None. Its readers:

| Reader | Today | After |
|---|---|---|
| `project_budget_state` (`usage_accounting.py:207-219`) | turn sum | `used_tokens` |
| `accounting_snapshot` → `budget` (`:184`) | `project_summary["total_tokens"]` | `used_tokens` |
| `PATCH /accounting/budget` response (`api/v1/accounting.py:79`) | `snapshot["project"]["total_tokens"]` | same field, which now includes workers |

`accounting_snapshot` gains `workers: [{kind, input_tokens, output_tokens, total_tokens,
measured_calls, unmeasured_calls, api_equivalent_usd_micros}]`, grouped by `kind` and ordered by
`kind`. A *measured call* has `total_tokens` not null. An *unmeasured call* spawned
(`outcome IN ('ok','nonzero_exit','timeout','unparseable','schema_invalid')`) but reported no usage.
Calls that never spawned (`unsupported_cli`, `unknown_model`, `spawn_failed`, `budget_exhausted`)
are neither. They cost nothing and are not counted. `project.total_tokens`, `input_tokens`,
`output_tokens` and `api_equivalent_usd_micros` include the worker sums. `project.measured_turns`
and `unavailable_turns` stay turn counts. If `an-estimate-that-misses-turns-says-so` has shipped,
each worker line also carries `unpriced_calls`, and the display counts them next to its turns.

**The headline caption.** `AccountingPanel.tsx:76-78` renders `project.total_tokens` over
*"N measured · M usage unavailable"*. Once the total includes workers, that caption reads as if N
turns made the whole total. It becomes *"N measured turns · K worker calls · M usage
unavailable"*, K being the sum of the worker lines' `measured_calls`. `project` keeps including
workers (R1's choice stands): the headline must equal `budget.used_tokens`, or the Budgets section
would show a spend the headline does not.

**Not changed:** `conversation_usage` (`GET /accounting/conversations/{id}`). A worker invocation
carries a `conversation_id`, but that rollup is *"this conversation's turns"*, and nothing in the
spec asks it to carry out-of-band calls. Recorded as a follow-up question, not built.

## D3 — the gate

`run_worker(..., initiator: Literal["operator", "autonomous"])`. It is **keyword-only with no
default**, so that no caller inherits a choice it did not make. Before the CLI and model checks:

```python
if initiator == "autonomous":
    try:
        async with async_session_factory() as db:
            exhausted = (await project_budget_state(db, project_id))["exhausted"]
    except Exception as exc:          # never raises (run_worker's contract)
        result = WorkerResult("spawn_failed", error=f"could not read the project's budget: {exc}")
    else:
        if exhausted:
            result = WorkerResult("budget_exhausted",
                error="the project's token budget is exhausted; autonomous spending is paused")
```

**It fails closed.** A budget that cannot be read does not authorise autonomous spend. F240 is about
exactly that spend, and the operator path is never gated, so control is kept.

`generate_checkpoint` derives `initiator = "operator" if trigger == "operator" else "autonomous"`
and passes it to `run_worker` and to `probe_checkpoint` (new parameter). The three triggers are
`operator`, `context_pressure` and `task_completion` (grep `trigger=` in `hub/hub`).

## D3a — the automatic triggers check first (R2)

R1 let an exhausted autonomous checkpoint fall through to `generate_checkpoint`, producing an
`unwritten` checkpoint. R2 found that this strands work, from the code:

- `generate_checkpoint` anchors on `latest_checkpoint` (`checkpoints.py:95-108`), which orders by
  `sequence` and **does not filter by status**. `_transcript_since` bounds the next transcript at
  `anchor.created_at` (`checkpoint_generation.py:181-197`) and the prompt carries `anchor.body`,
  which is `None` for an unwritten one. So the first written checkpoint after the budget is raised
  would cover only the turns since the last *gated* one, with no predecessor body: every span a
  gated checkpoint "covered" drops out of the chain.
- Under `automatic`, every operator turn at exhaustion is a new run, so `_nothing_new_since_last_checkpoint`
  (`checkpoint_trigger.py:111-136`) is false each time. One unwritten checkpoint, and one
  `checkpoint_ready` broadcast, per operator turn.
- On a handover, `consume_note` runs whatever the outcome (`checkpoint_handover.py:273`,
  `checkpoint_generation.py:600-603`), so the author's notes for its reviewer would be consumed
  into a checkpoint with no body. The loop's next firing briefs from `latest_checkpoint_for_loop`,
  which is that empty checkpoint.

So both triggers read `project_budget_state` **before** `generate_checkpoint`:

| Trigger | Where | At exhaustion (or an unreadable budget, fail-closed) |
|---|---|---|
| `checkpoint_trigger.consider` | **both** places that test `not policy.automatic` (R3): the dismissed/final backstop at `:192` and the warn path at `:263`. Each becomes `not policy.automatic or await budget_blocked()`, a small memoised helper that reads `project_budget_state` at most once per reading and only when `policy.automatic` (so an `offered` conversation, and every automatic reading that returns before `:192`'s test or below threshold, pays no read) | the automatic policy behaves as `offered` for that reading: the warn-don't-spend path (`checkpoint_warning = "due"`, one `checkpoint_due` broadcast, idempotent on `"due"`, return `None`), **and** the dismissed/final backstop (a dismissal is honoured; the final warning still fires near the window). No record, no anchor moves. The operator's *Checkpoint* button runs as `operator` |
| `checkpoint_handover.consider_handover` | after `resolve_policy(...).enabled` (`:244-246`), before `_resolve_runner` | `_declined(run_id, "the project's token budget is exhausted")`, return `None`. The note is not consumed |

**Why both `:192` and `:263` (R3).** R2 changed only `:263`. Under `automatic`, `:192`'s branch is
skipped, so with only `:263` changed: (a) a *Dismiss* at exhaustion is undone at the next reading,
because `dismissed != "due"` re-sets `due` and broadcasts again, contradicting the banner's promise
that dismissal is final (`AgentOutputPanel.tsx:641-647`, which renders the same banner whatever the
policy); and (b) the final-warning backstop (`needs_final_warning`, `FINAL_WARNING_PERCENT`) never
fires, so an exhausted automatic conversation can run into the CLI's own compaction with only a
*due* banner, which is the loss the backstop exists to announce. Treating the reading as `offered`
at both tests gives the operator exactly the manual-mode experience, which is what the proposal
promises. Once the budget is raised, the next reading is automatic again and generates and cuts
over as today, whatever the warning says.

**What the handover's pending note does and does not reach (R3).** Declining keeps the note
unconsumed, which is strictly better than R1's design: an `unwritten` checkpoint in the completing
run's conversation would have been found by `checkpoint_by_task_author` (`checkpoints.py:475-520`)
and briefed to the reviewer as the author's account, with no body. But the note does **not** reach
this task's reviewer either. That reviewer's firing is autonomous, so it waits for the budget; when
it runs, `_briefing_checkpoint` (`scheduler.py:2485-2505`) finds no author checkpoint and falls back
to `latest_checkpoint_for_loop`. The note waits for the same author's next handover, where
`_authors_pending_note` returns only the author's **newest** pending note in the loop: if the author
wrote a newer one, this one is not carried; if not, it is carried into a checkpoint recorded against
the later task. That is the same fate as a handover declined today for any other reason (no
checkpoint runner, `:249-255`), so it is not new here, and re-running declined handovers when the
budget is raised is a separate feature. Recorded as a candidate finding in B7's R3 section.

**Interaction with B8.** `a-checkpoint-is-handed-over-once-and-says-where-it-went` (design D6)
adds a decline to `consider` right after the lifecycle check (`:187-190`), for a conversation
already handed over. It runs before both tests above, so a handed-over conversation never reads the
budget. The two edits are in the same function and compatible in either order.

`run_worker`'s gate (D3) stays, as a backstop for the titler and for the race in which a turn
crosses the budget between the trigger's read and the spawn. In that race the result is an
unwritten checkpoint, which is today's behaviour for any worker failure; it is rare, and the
anchoring hazard it shares with every other unwritten checkpoint is recorded as a candidate
finding in B7's R2 section, not fixed here.

## D4 — the titler

`build_title_command` (`conversation_titles.py:61-84`) keeps `--tools ""`, the project directory,
and `--sandbox read-only` (F195), and adds `--output-format json` for Claude and `--json` for Codex.
`generate_conversation_title`:
1. Resolves the runner as today, then checks the budget as D3 does (always `autonomous`). At
   exhaustion or on a failed read it records the outcome and returns None, with no spawn.
2. Spawns as today, then `worker.parse_envelope(cli, stdout)` gives `(answer_text, usage, error)`.
   The title is `title_from_output(answer_text)`.
3. Calls `worker.record_invocation(kind="conversation_title",
   prompt_version=TITLE_PROMPT_VERSION, runner_id=runner.id, cli, model, conversation_id, result)`
   on every exit after the runner is resolved. `_run_titler`'s `""`-on-failure contract becomes a
   small result carrying the outcome (`spawn_failed`, `nonzero_exit` or `timeout`) so the row can
   say which. `TITLE_PROMPT_VERSION` is a new constant in `conversation_titles.py`
   (`"conversation-title/1"`): none exists today, and `worker_invocations.prompt_version` is
   NOT NULL (`db/models.py`).

**Adjacent, not changed here (R2).** `generate_conversation_title` has no "already generated"
guard: it re-runs after every completed turn (`agent_trigger.py:2630`, `:3219`) on the same
excerpt (the first message and first reply, `_excerpt`), so it pays for the same title each turn.
Once this change records it, that repetition becomes visible as one `conversation_title` row per
turn. Recorded as a candidate finding in B7's R2 section.

**Why not route the titler through `run_worker`.** `run_worker` builds its own command without
`--tools ""` (`worker.py:122-146`) and validates the answer against a Pydantic schema. Routing the
titler through it would either drop F195's protection or change the worker command for
checkpoints too. The accounting is what F240 asks for, and it is shared. The command is not.

## What each route returns when what it calls raises

- `GET /accounting`: one more aggregate query, on a table that has existed since migration `0042`.
  If the table is missing, the route 500s, which is the same as today for `turn_usage`. The
  migration chain guarantees both.
- `PATCH /accounting/budget`: unchanged shape. `schedule_agent` re-runs for queued agents as today.
- `POST /conversations/{id}/checkpoints` (operator): never gated. `run_worker` never raises, so the
  route still answers with a checkpoint (`ready` or `unwritten`).
- The automatic triggers (`checkpoint_trigger.consider_from_reading`, `checkpoint_handover`) are
  fire-and-forget. At exhaustion they now return `None` before generating (D3a); their budget read
  raising is caught and treated as exhausted, so neither raises. Only the backstop race yields a
  `budget_exhausted` worker result, and that produces an `unwritten` checkpoint, never an exception.
- `GET /queue` status (`inbound_queue.py:142`): the reason is still `token budget exhausted`,
  derived from the same `project_budget_state`, which now includes workers.

## Tests that can fail

New file `hub/tests/test_worker_spend_counts_against_the_budget.py` unless stated.

1. `parse_claude_envelope` with `input 2, cache_read 47091, cache_write 100, output 497` gives
   `total_tokens == 47690`. **Fails today** (no field). Fails if cache is dropped from the sum.
2. `parse_codex_envelope` with `input 1000, cached_input 800, output 50` gives `1050`, not `1850`.
   Fails if Codex cache is added again.
3. One `TurnUsage` of 1000 and one checkpoint `WorkerInvocation` of 500 give `GET /accounting`
   `project.total_tokens == 1500`, `budget.used_tokens == 1500`, and
   `workers == [{"kind": "checkpoint", "total_tokens": 500, …}]`. **Fails today** (1000, no
   `workers`).
4. Worker lines are ordered by `kind`. Seed `conversation_title` before `checkpoint`, and the route
   returns `checkpoint` first. The test asserts by position, so reversing the order fails it.
5. `token_budget = 1200` with the rows in test 3: an autonomous queue entry stays queued with
   `waiting_reason == "token budget exhausted"` (reuse `test_accounting_budget.py`'s helpers).
   **Fails today** (1000 < 1200, so it starts).
6. `run_worker(initiator="autonomous")` on an exhausted project: outcome `budget_exhausted`, one
   row recorded, and `_run_worker_process` is patched to raise if called. **Fails today.**
7. `run_worker(initiator="operator")` on the same project spawns (patched to return a Claude
   envelope), gives `ok`, and its row counts in test 3's total.
8. With `project_budget_state` patched to raise, the autonomous call gives `spawn_failed` naming the
   budget, does not spawn, and does not raise.
9. `generate_checkpoint` with each of the three triggers: a patched `run_worker` records `initiator`
   as `operator`, `autonomous`, `autonomous`. The probe gets the same value. (Extends the
   `watchful_run_worker` pattern at `test_checkpoint_generation.py:659`.)
10. An automatic `context_pressure` reading at exhaustion creates **no checkpoint** (the count of
    `checkpoints` rows is unchanged), sets `checkpoint_warning == "due"`, broadcasts one
    `checkpoint_due`, does no cutover, and never calls `run_worker` (patched to raise). A second
    reading after another turn broadcasts nothing new. In `hub/tests/test_checkpoint_cutover.py`,
    beside the automatic cutover tests. **Fails today** (a checkpoint is generated). It also fails
    under R1's design, which made an `unwritten` one.
10b. A flow handover at exhaustion creates no checkpoint and leaves the author's `CheckpointNote`
    with `consumed_by_checkpoint_id IS NULL`. Raising the budget and running the next handover
    consumes that same note. **Fails today** (generated and consumed).
10c. With `project_budget_state` patched to raise, both triggers behave as at exhaustion
    (fail-closed) and neither raises.
10d. (R3) Automatic policy, budget exhausted, `checkpoint_warning == "dismissed"`: a reading above
    the threshold but below `FINAL_WARNING_PERCENT` leaves the warning `dismissed` and broadcasts
    nothing; a reading at `FINAL_WARNING_PERCENT` sets `"final"` and broadcasts one `checkpoint_due`
    with `final: true`. **Fails under R2's D3a** (which re-set `"due"` and never reached the final
    warning). A control: under `offered` with no budget, the same readings give the same results
    today.
10e. (R3) Automatic policy, **no** budget set, a reading below threshold: `project_budget_state`
    is patched to raise and the reading still declines normally (the helper did not read). Pins the
    lazy read.
11. Titler (`hub/tests/test_conversation_titles.py`, extend): with `_run_titler` patched to return a
    Claude JSON envelope, one `conversation_title` row with `total_tokens`, and the title set.
    **Fails today** (no row). At exhaustion: no spawn, title unchanged, row `budget_exhausted`.
12. `build_title_command` still contains `["--tools", ""]` for Claude and `--sandbox read-only` for
    Codex, and now the JSON flag. This guards F195 through the rewrite.
13. `hub/tests/test_migrations.py`: `0106` on a database holding a legacy Claude row and a legacy
    Codex row backfills 47690-style and 1050-style totals, leaves a usage-less row null, and admits
    a `budget_exhausted` insert. A second test covers the guard when `worker_invocations` does not
    exist. Bump the head assertions.
14. `PATCH /accounting/budget` answers `used_tokens` equal to what `GET /accounting` reports right
    after it.
15. UI (`hub/ui/src/__tests__/accountingPresentation.test.tsx` or the panel test): with `workers`
    served in `kind` order, the Budgets section renders one line per kind after the agent chips.

## Round log

- R1 (2026-09-24): written.
- R2 (2026-09-24): added D3a (the automatic triggers check the budget first and create nothing;
  R1's `unwritten`-at-exhaustion would have become the next checkpoint's anchor and consumed a
  handover's notes). Tests 10/10b/10c rewritten. `TITLE_PROMPT_VERSION` is new. The headline
  caption names worker calls. Re-measured `:8000` `mode=ro`: 32 `ok` Claude rows, all
  LoopEngine, backfill total **962,599** (320 in + 564,480 cache-read + 330,296 cache-write +
  67,503 out), `$1.168`; 0 of 3 projects have a budget; head is `0105`. LoopEngine runs
  `conversation_title_mode = generate`, so its titler spend exists and is **not** backfillable (no
  row was ever written). Only spenders outside a turn: `run_worker` (checkpoint, probe) and
  `_run_titler`.
- R3 (2026-09-24): D3a now changes **both** `not policy.automatic` tests in `consider` (`:192` and
  `:263`), with a lazy memoised budget read; with only `:263`, a dismissal at exhaustion was undone
  at the next reading and the final-warning backstop never fired. Tests 10d/10e added; one spec
  scenario added. The handover's claim *"the next handover carries it"* corrected: the note does not
  reach this task's reviewer (`_briefing_checkpoint` falls back), and only the author's newest note
  is ever carried; same as any declined handover today. Confirmed no other consumer: the three
  `generate_checkpoint` callers are the route and the two triggers; `consume_note` is called only
  from `generate_checkpoint:603` and `consider_handover:275`. Re-measured `:8000` `mode=ro`: head
  `0105`, 32 rows (16 checkpoint 490,179 + 16 probe 472,420 = **962,599**, `$1.168`), 0 of 3
  projects budgeted.
