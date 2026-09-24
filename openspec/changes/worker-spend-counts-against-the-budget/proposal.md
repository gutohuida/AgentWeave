# Proposal — worker spend counts against the budget

Finding: **F240 (B)**, which also carries the question F92 left for the operator. Bundle B7 (models
and budget), R1, 2026-09-24. Built on the recommended answer to **D7's first question** (*"Does the
budget cover worker spend (checkpoint, probe, titler)?"*): **yes. Worker tokens join the project
total as their own lines, count against `token_budget`, and an autonomous worker call is refused
at exhaustion while an operator-requested one still runs**, which is the rule the budget already
applies to turns.

## Why

Re-verified against the code today (HEAD `404c7d5`). Every clause of F240 still holds:

- **The budget reads turns only.** `project_budget_state` sums `TurnUsage.total_tokens`
  (`hub/hub/usage_accounting.py:207-219`), and so does `accounting_snapshot`
  (`:110-129`). `worker_invocations` is joined to no aggregate. Grep finds its only readers are
  the checkpoint routes (`api/v1/checkpoints.py:106`, `:207`).
- **No worker consults the budget.** `project_budget_state` has two callers, both about agent turns:
  `turn_scheduler.py:393` and `api/v1/inbound_queue.py:142`. `run_worker` (`worker.py:414-486`)
  checks the CLI and the model, then spawns.
- **Workers spend autonomously.** `generate_checkpoint` has three triggers: `operator` (the button,
  `api/v1/checkpoints.py:176-183`), `context_pressure` (`checkpoint_trigger.py:302`, automatic
  mode), and `task_completion` (`checkpoint_handover.py:262-265`, every flow handover that has
  notes). Each runs a checkpoint and then a probe (`checkpoint_generation.py:606-615`).
- **The titler records nothing.** `conversation_titles.py` spawns plain-text `claude -p` or
  `codex exec` (`:61-84`), reads stdout (`:101-121`), and writes no `worker_invocations` row and no
  `turn_usage` row. Its cost is unrecoverable. It runs after every completed turn when
  `conversation_title_mode == "generate"` (`api/v1/agent_trigger.py:2630`, `:3219`).

F240 drove it: `token_budget` set below usage, `exhausted: true`, *"Autonomous turns are paused"*
on screen. A checkpoint and its probe then spent `$0.042` that reached no total and no budget.

**Scale on the operator's real Hub** (read `mode=ro`, 2026-09-24): 32 worker invocations, all
Claude, on LoopEngine. That is 320 input, 67,503 output, 564,480 cache-read and 330,296 cache-write
tokens, and `$1.17` of reported cost, against 348 turns and `$418` of turn cost. **No project there
has a `token_budget` set**, so counting worker spend, including the backfill below, pauses nothing
on `:8000`.

## What changes

- **One normalised total per worker call.** A `total_tokens` column on `worker_invocations`
  (migration `0106`), computed by the same normaliser the turn path uses
  (`runner_parsing._accounting_from_dimensions`). For Claude, cache reads and writes count as
  input, as they do for a Claude turn (`runner_parsing.py:334-340`). For Codex, cached input is
  already inside `input_tokens`. Existing rows are backfilled by the same rule.
- **Worker tokens count.** `used_tokens` = measured turn tokens + worker tokens, computed once and
  read by `project_budget_state`, `accounting_snapshot` and `PATCH /accounting/budget`. The
  accounting API gains `workers`: one line per worker kind (`checkpoint`, `checkpoint_probe`,
  `conversation_title`), beside `agents`. `project` totals include them.
- **An automatic checkpoint at exhaustion is not taken, and the operator is told one is due.**
  (R2.) Both automatic triggers read the budget *before* `generate_checkpoint`. At exhaustion,
  `checkpoint_trigger.consider` takes its existing manual-mode branch (sets
  `checkpoint_warning = "due"`, broadcasts `checkpoint_due`, spends nothing, creates no record), and
  `checkpoint_handover.consider_handover` declines and **leaves the author's note pending**. Neither
  creates a checkpoint. An `unwritten` checkpoint made here would become the next checkpoint's
  anchor (`checkpoints.latest_checkpoint` orders by `sequence` with no status filter), so every
  later checkpoint would begin after it, with no anchor body: the span it covered would drop out of
  the checkpoint chain for good, and a handover's consumed notes would be gone with it.
- **Every worker call is also gated at the spawn, as a backstop.** `run_worker` takes a required
  `initiator` (`"operator"` or `"autonomous"`). An autonomous call on an exhausted budget does not
  spawn. It is recorded with a new outcome, `budget_exhausted`, as every non-spawning exit already
  is (*"Every exit records an invocation, including the ones that never spawn"*,
  `worker.py:430-432`). A checkpoint's initiator is `operator` only for the `operator` trigger, and
  its probe inherits it. The backstop matters for the titler (which has no trigger-level check to
  lean on) and for the race where a turn crosses the budget between a trigger's read and the spawn.
- **The titler is accounted like every other worker.** It keeps its own command (tools off,
  project directory: F195) but runs it in JSON mode, reads usage with the worker's envelope parser,
  writes a `conversation_title` invocation, and is always `autonomous`. At exhaustion it does not
  spawn, and the truncated title stays, which is already its floor (`conversation_titles.py:1-5`).

## What an exhausted budget does to each worker

| Trigger | At exhaustion, after this change |
|---|---|
| Operator presses *Checkpoint* | Runs, and is counted (operator control is retained, as for turns) |
| `context_pressure`, automatic | No checkpoint and no model call. For that reading the policy behaves as `offered` (R3: at both of `consider`'s `not policy.automatic` tests, `checkpoint_trigger.py:192` and `:263`): `checkpoint_warning = "due"` and `checkpoint_due` are sent, a dismissal is honoured, and the final warning still fires near the window. The operator can press *Checkpoint*, which runs. No cutover happens until the budget is raised |
| `task_completion` (flow handover) | No checkpoint and no model call. The handover declines and the author's note stays unconsumed. It does not reach this task's reviewer (whose briefing falls back to the loop's latest checkpoint, as for any declined handover today); design D3a states where it can go later |
| Probe | Runs only when its checkpoint is `ready`; an exhausted autonomous trigger never makes one |
| Titler | No spawn; the truncated title stays |

## Capabilities

- **usage-accounting**: MODIFIED *"Usage aggregates by agent and project"* and *"A project token
  budget pauses autonomy but not the operator"*. ADDED *"Every model call the Hub makes for a
  project is recorded"*.

## Impact

- Migration `0106`: add a column, backfill it, and rebuild the outcome CHECK to admit
  `budget_exhausted`. It reaches the operator's `:8000` on their next restart. Per the measurement
  above, it changes their totals by about 962k tokens and pauses nothing.
- `hub/hub/worker.py`, `checkpoint_generation.py`, `conversation_titles.py`, `usage_accounting.py`,
  `api/v1/accounting.py`, `db/models.py`.
- The UI shows worker lines in the Budgets section (`AccountingPanel.tsx:88-101`), so the bundle
  is refreshed.
- `checkpoint_trigger.py` and `checkpoint_handover.py` gain one budget read each, before `generate_checkpoint`.
- Every `run_worker` caller must pass `initiator`. That is two call sites
  (`checkpoint_generation.py:552`, `:641`) and the test helper at `hub/tests/test_worker.py:267`.
