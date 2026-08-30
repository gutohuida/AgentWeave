# Autonomous run log — 2026-08-30, decided work and drive

**Brief:** `.claude/autonomous/STATE.json` · **Branch:** `autonomous/2026-08-30-decided-work-and-drive`
**Cut from:** `master` at `7224d42` · **Stop at:** 2026-08-30T12:00+01:00
**Runner:** `claude` (Opus 5), posture `unattended-full-access`

Newest entry at the **bottom**.

---

## Iteration 0 — prepared 2026-08-30 ~02:00, by the interactive session

Not a work iteration. What was removed from the run's path before it started.

### What the operator decided while awake

Four decisions were taken in the session that prepared this run, and all four are written into
`scripts/drive/FINDINGS.md` so the loop implements rather than re-litigates:

1. **F14 + F60** — park the task at ask time **and** flag the timeout outcome, in one change.
   F60's parked half stops being parked and ships with F14.
2. **F115 part (2)** — detect at the tool-event parse point, and name the recorded fact for exactly
   what it catches: *a file tool wrote outside the workspace*, never "escapes".
3. **The drive is guaranteed.** The operator extended the stop from 10:00 to 12:00 specifically to
   make room for it, so it is time-boxed by the 08:00 rule rather than conditional on the queue
   emptying.
4. **Delete the merged branches.** Done — `autonomous/2026-08-29-decided-fixes-and-drive` and
   `f131-continue-starts-what-it-names` are gone from local and origin.

### What was created so the loop would not have to

- **The F131 spec loop, all three rounds, merged to master** (`7224d42`). F131-IMPL is the first
  queue item and its proposal, design, spec delta and `tasks.md` are already on the branch it will
  cut from. Without this the run would have had to re-do a loop that was already finished on a
  branch it would never have seen.
- **F115's decision, the field research, and a variant the operator raised** — appended to F115:
  that "a worktree is not a sandbox" is the explicit industry consensus, that containment is
  buyable (`@anthropic-ai/sandbox-runtime`) rather than buildable, and that an agent writing into
  *another agent's* worktree is worse than writing into the operator's, because
  `snapshot_worktree` auto-commits it onto the wrong agent's branch under that agent's name.
- **F66 closed.** Its status line claimed it was waiting on an operator decision. It was not — the
  question was answered in code four days earlier by `2026-08-27-every-run-knows-its-task`. Left
  as-is it would have cost this run an iteration.

### Environment, measured rather than assumed

| Check | Result |
|---|---|
| CI on `894d5b2` | **all nine jobs green** (run 33271924205), verified job-by-job |
| Code changed since that commit | **none** — `git diff --name-only 894d5b2..7224d42 -- hub/hub hub/tests src tests` is empty, so CI still describes this tree |
| Hub suite | 3555 passed / 84 skipped / 1 xpassed / **0 failed**, 13:38. The F109 flake did **not** fire |
| CLI suite | 440 passed / 3 skipped |
| Gates | `ruff` clean · `black` 520 files unchanged · `mypy` clean |
| Hubs responding | 8010 (operator's trial) and 8011 both `{"status":"ok"}` at 01:56 |
| `openspec validate --strict` | `continue-starts-what-it-names` valid |
| Drive harnesses | 39 under `scripts/drive/` |

One thing that was **red and is now fixed**, worth carrying: CI failed on the first merge tonight,
in `test_request_strictness.py`, with *"found no request body models at all"*. Not a product
regression — the probe walked `app.routes` directly, which finds nothing on the Starlette CI
resolves (1.6.0 nests routes under `_IncludedRouter`) while the dev machine's 0.52.1 flattens them.
`hub/tests/_routing.py` already existed for exactly that split. **If a route-table walk ever returns
zero, suspect the Starlette version before suspecting the code.**

### Five pre-authorised decisions

`decisions_for_user` D1–D5 cover: a task `blocked` while its run is `running`; whether new state is
a column or derived; where a detected outside-workspace write is recorded; that F129+F132 gets
**round 1 only** and is not to be built unattended; and which drive findings to fix versus file.
Each carries the cost if the default is wrong.

### Queue

27 items. F131-IMPL, then four-item spec loops for F14+F60, F115, F130, F127, F111+F3 and F113,
then F129+F132 **round 1 only**, then the drive. Ordered so stopping anywhere leaves complete
changes rather than half-written proposals.

**Ready.** Nothing is waiting on the operator.
