# scripts/drive — driving the product as an operator

These are the scenarios from the 2026-08-23 stress test, kept so every fix that came out of it can
be re-verified against a running Hub rather than only against a unit test. They talk to the Hub
exactly the way an operator does: REST only, no row inserts, no test doubles.

## Why these exist

Twenty findings came out of driving AgentWeave end to end. Most of them are invisible to the unit
suites because they live *between* two features — the hop budget between the queue and the
scheduler, the reviewer's blindness between worktree isolation and the evidence chain. Rebuilding
the situation that exposes one of those is the expensive part; the assertion is cheap. So the
situations are kept.

## Running them

```bash
# The trial Hub only. Port 8000 is real operator usage — never point these at it.
export AW_HUB=http://127.0.0.1:8010
export AW_KEY=$(curl -s $AW_HUB/api/v1/setup/token | python -c "import sys,json;print(json.load(sys.stdin)['api_key'])")
export AW_PROJECT=proj-...        # a project registered against the trial Hub

python scripts/drive/t_loop.py 24     # watch a loop claim, work, drain and stop
python scripts/drive/t_hop.py 30      # watch hop depths propagate under a low budget
```

`aw.py` is the whole client: `api(method, path, body)` returns `(status, parsed)` and never raises,
so a scenario can assert on a refusal as easily as on a success.

## The fixture these were written against

`ledger` — a small double-entry library at `C:\Users\huida\Documents\aw-stress`, its own git
repository, with three deliberately seeded defects that the test suite does not cover. It is the
subject rather than the point: real work with real stakes is what exercises the parts of AgentWeave
that decide whether work is *good*, which a make-work fixture never reaches.

By the end of the drive it carried an approved specification, four materialised tasks with a real
dependency graph, accepted evidence, and a merge into `master` produced by approving a task. That
accumulated state is the expensive part to recreate — prefer re-using the project over rebuilding
it.

## Reading order for the findings

- `FINDINGS.md` — the twenty findings, each with the request and the row or log that proves it,
  plus what worked and held under pressure.
- `SURVEY.md` — the codebase map and the twelve code-read suspicions the drive was designed to
  confirm or kill. Nine survived, three did not.
- `TESTPLAN.md` — the scenarios and the rules the drive was run under.

## One trap, learned the hard way

Run the Hub suite with **`py -3.11 -m pytest hub/tests/ -q`**. Bare `python` resolves to a venv that
*has* pytest — so it runs and looks legitimate — but produces three false failures in
`test_pty_runner.py` on a completely green tree. Measured 2026-08-23: bare `python` gave
3 failed / 2755 passed; `py -3.11` gave 2758 passed / 84 skipped.

## The 2026-08-29 fixture — rows 12 and 16

`drive-wt-0829` at `C:\Users\huida\Documents\drive-wt-0829`, registered as `proj-dc4d43543bea` on the
**8011** Hub (`sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0829/aw0829.db`), not on 8010.
A four-line `calc.py` in its own git repo, three agents (`alpha`, `beta`, `gamma`) all on
`claude-haiku-4-5-20251001`, and an approved change document (`spec/changes/olive-chimera/spec.html`,
`spdoc-ee4305b82730`) whose two tasks materialised into a flow's queue.

It is deliberately trivial subject matter, unlike `ledger`, because rows 12 and 16 are about *the
machinery around the work* — parallel checkouts, conflict detection, reviewer resolution — and a
one-line function is enough to make two branches diverge on the same line.

Harnesses:

- `t_row16_worktrees.py` — two agents, two tasks, one file; then `/worktrees` and
  `/worktrees/conflicts`.
- `t_row12_flows.py` — document → approve → flow → fire → parallel turns → review dispatch, and
  archives the job in a `finally`. **Do not pipe its output through `head`**: SIGPIPE kills it before
  the `finally` runs and leaves the job enabled.
- `t_row17_integration.py` — approving a completed task, and what the integration gate says.

The flow's job is archived. Nothing in this project is left enabled.

## Row 19's crash half — four harnesses that kill the Hub, in the same fixture

Added 2026-08-29, all against `drive-wt-0829` on 8011. Each one triggers a real turn, kills the
Hub with `Stop-Process -Force` (so `lifespan`'s `terminate_all_active_runs()` never runs — a crash,
not a bounce), restarts it from `hub/` on the same database, and reads what the operator sees.

- `t_row19_crash.py` — the plain case: is the spawned CLI orphaned, is the run reconciled, is the
  agent wedged, does the operator's message come back.
- `t_row19_crash_card.py` — a crash with a **permission card** on screen.
- `t_row19_crash_question.py` — a crash with **`ask_user`** blocking.
- `t_row19_crash_task.py` — **three** crashes on one task-bound run, which is the only way to reach
  `reconcile_interrupted_runs`' `if run.task_id and not returned_entry_ids` branch.

They restart the Hub themselves, so running one leaves a Hub up on 8011 serving whatever code was
on disk when it fired. Two things they cost time to learn: the `Run` row's pid is `claude.exe`
itself and it dies with its Hub, and an interrupted run's `ended_at` is the **restart** time, so
run durations read from the database are inflated by the outage.

## Row 11's second half — a loop's ending, in the same fixture

Added 2026-08-29, against `drive-wt-0829` on 8011. Row 11's first half (a loop firing at all) was
driven in earlier sweeps; the ending never was.

- `t_row11_loop.py` — the **queue-drained** ending. Creates a loop with two `initial_tasks` and
  `stop_when_queue_empties`, fires it once by hand and lets the cron take the rest, watches it
  stall on completed-but-unapproved work, approves both as the operator, and reads the four facts
  `loop_ending.end_loop` promises. Then the three ways an operator might restart it. ~9 minutes,
  two real Haiku turns. **19/21** — the two failures are one mis-specified assertion, kept
  deliberately; see F121's strengthening in `FINDINGS.md`.
- `t_row11_loop_quiet.py` — the **stop-time** ending, and the only check that distinguishes "the
  four facts were written" from "the loop actually stopped": 160 seconds of wall clock, three cron
  ticks, asserting `run_count` does not move. Costs no agent turn at all — the stop condition is
  checked before the spawn. ~4 minutes. **11/12**, and the failure found F125.

Both archive their loop and disable their job in a `finally`. **Do not pipe either through `head`**:
SIGPIPE kills the process before the `finally` runs and leaves a job enabled.

Two things they cost time to learn. A loop's queue drains at `approved`/`rejected`, not at
`completed` — `TERMINAL_FOR_BINDING` is those two — so a loop only ends once somebody reviews its
work, and until then it stalls with a reason rather than stopping. And approving a loop's task
merges nothing, ever, for the structural reason in F124.

## The 2026-09-02 fixture — D-1, the model catalog

`drive-0902-d1` at `C:\Users\huida\Documents\drive-0902-d1` — a one-file git repo, deliberately
trivial, because nothing in this harness needs an agent to do work. The **project** is created and
deleted by the harness on every run, so only the directory persists; keep it, or
`t_d1_catalog_is_the_only_door.py` cannot open a project at all.

- `t_d1_catalog_is_the_only_door.py` — the day window's independent re-drive of
  `runner-model-is-chosen-from-the-catalog`, against the **served bundle** on `:8011` (no Vite dev
  server). It derives what to assert from `openspec/specs/runner-registry/spec.md` and from
  `GET /model-catalog`, never from the component's source, which is the point of it existing beside
  `t_n3_*` and `t_n4_*` rather than replacing them: those two were written by the change's own
  author in the same sitting as the code.

  **33 passed / 3 failed**, and the three reds are the findings, not breakage — F267 (the Codex
  catalog declares two models the CLI's own `models_cache.json` no longer lists, one of them the
  declared default) and F268 (the runner-binding select renders `name (cli)`, so two runners
  differing only by model are one string). Expect it to stay red until those are fixed.

  Costs no tokens: it triggers no agent turn, and the one `POST /agent/trigger` it makes carries a
  deliberately invalid model override that `validate_overrides` refuses before anything spawns.

## The 2026-09-03 fixture — D-1, `a-turn-says-how-it-ended` in a real browser

`drive-0903-d1` at `C:\Users\huida\Documents\drive-0903-d1`, registered as `proj-f0b9dc9732d3` on
the **8011** Hub (`sqlite+aiosqlite:///C:/Users/huida/AppData/Local/Temp/aw0903d1/aw0903d1.db`).
Built by `setup_aturn_p6.py`, which the night window wrote for phase 6 and this window reused
unchanged.

The point of this set is that phases 6 and 7 both evaluated `aturn_model.py`, a Python
transcription of the built component. **These drive the served bundle in Chromium**, which is how
F274 was found: the transcription and the component agree, and the screen still loses the outcome.

- `d1_aturn_runs.py stop|fail|clean|show` — makes the runs an operator would make and prints the
  conversation and run ids. One real Haiku turn on the `stop` leg; the `fail` leg costs nothing.
- `d1_aturn_browser.py <agent> [expected-label]` — opens the agent in the served bundle, counts
  `data-turn-boundary` elements against terminal-label occurrences and `turn-worked-for` stat lines.
- `d1_aturn_window.py <agent> <n>` — pushes an agent past the timeline route's fifty-event cap and
  reports how many turns on screen have no run in the map. Costs nothing on the bad-flag agent.
- `d1_aturn_conv_browser.py <agent> <needle>` — clicks the sidebar's `Switch to recent conversations`
  rail and opens a *named* older conversation, which is the only way to see F274 from the operator's
  seat.

Two things they cost time to learn. `page.goto(..., wait_until="networkidle")` **never returns** —
the dashboard holds an SSE connection open, so use `domcontentloaded`. And the sidebar's agent tree
does not list conversations; the rail toggle at `aria-label="Switch to recent conversations"` does.

`p6driver0903d1` is left bound to the bad-flag runner, which is where F274's reproduction ends.
Rebind it to `haiku-0903d1` before reusing the fixture for anything that needs a real turn. No job
or loop was ever created in this project.
