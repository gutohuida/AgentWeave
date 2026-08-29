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
