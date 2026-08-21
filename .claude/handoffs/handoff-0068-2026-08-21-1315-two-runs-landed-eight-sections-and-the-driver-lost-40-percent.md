# Handoff: two autonomous runs landed eight sections, and the driver lost 40% of the second one

**Date:** 2026-08-21T13:15:00+01:00 · **Branch:** `autonomous/2026-08-20-open-specs` · **HEAD:** `c77d0a6`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0067-2026-08-20-2300-the-corpus-is-tracked-and-the-marker-pointed-nowhere.md`
**Status:** chunk complete. Working tree clean. **43 commits ahead of `master`; 2 unpushed** (`470d0cc`, `c77d0a6`).

## Goal

Implement the openspec changes that were proposed-but-unbuilt, across two unattended runs, on a
branch the operator can read and throw away. The *why*: handoff 0067 ended with four changes at 0
tasks done and 234 tasks between them. The operator went to bed with *"There is a lot specs opens
for development. Work on them in any order you see fit."*

The deeper why, which should govern the next session's judgment: **this repository is dogfooding its
own product.** Friction the spec flow causes is a finding, not an obstacle — and this session
produced more findings about the *autonomous harness* than about the product.

## Current state

### What was built — eight sections across three changes

| Change | Start | Now | What remains |
|---|---|---|---|
| `agent-created-documents` | 0/35 | **27/35** | 6 human-only (6.1–6.6) + 2 explained-but-unticked (5.3 mypy baseline, 5.5 implicit assertion) |
| `corpus-aware-documents` | 0/55 | **45/55** | 7 human-only (8.1–8.7) + content work (6.6, 6.7) + lint note (7.3) |
| `task-dependencies` | 0/80 | **49/83** | §8 board (13), §10 agent checks (9), §11 human-only (8), §12 test guide (1), plus new 1.6–1.8 |
| `loop-notices-and-reacts` | 0/64 | **0/44** | untouched, and **deliberately narrowed** — see below |

Three changes remain `✓ Complete` and unarchived: `document-adoption`, `writable-spec-index`,
`operator-authored-documents`. **The operator was asked directly and chose "Not yet."**

### `task-dependencies` is coherent and safe to merge as far as it goes

Sections 1–7 and 9 have landed. **Section 9 mattering more than section 8 is the one judgment call
worth understanding:** §9's own title is *"without this the change deadlocks every loop."* Once §5
shipped the gate, a loop could claim a task whose prerequisites were unmet and then stall on a
transition the gate refuses. **That window was open for roughly three hours and is now closed.** §8
(the board, 13 tasks, touches `hub/ui/src` and needs a UI bundle rebuild) was skipped on purpose to
get there.

Net effect today: dependencies are declared, stored, materialised into edges, **enforced**, readable
via `GET /tasks/board` and `GET /tasks/boards` — and **not yet visible in the board UI.**

### The corpus is arranged

`spec/index.json` holds **41 documents, 40 carrying a `parent`** (the one null is the home,
correctly). The `parent` field had been validated, preserved across rebuilds, and had **never had a
producer** since the day it was built. Six area documents now exist under `spec/areas/`. Verified by
reading `index.json` directly, not from the run's claims.

### Two operator decisions landed after run 2 closed, from a concurrent session

- **`470d0cc`** added tasks **1.6–1.8** to `task-dependencies` — a task may name *the kind of
  reviewer it needs*, deliberately not an agent identity, because *"the file is the portable truth,
  the database is machine-local state"*. Total went 80 → 83.
- **`c77d0a6`** **narrowed `loop-notices-and-reacts` from 64 to 44 tasks**, deleting groups 3, 6, 7,
  8 and the whole `loop-review-handoff` capability as superseded by the flow explorations. It was at
  0/64, so nothing was lost — but **anyone picking it up from an older description would build the
  thing that was decided against.**

## Files touched

`git status --short` is **empty** and `git diff --stat HEAD` is **empty** — everything is committed.

**Mine this session (interactive), in order:**

- `hub/tests/test_project_delete_api.py` — added `task_dependencies` and `task_dependency_references`
  to `PROJECT_SCOPED_TABLE_NAMES`, their model imports, and fixture rows (a dependency needs two
  tasks to be an edge, so the prerequisite is its own row). **Finished.** Commit `0177df1`.
- `hub/tests/test_spec_render.py` — recaptured `_BASELINE_DIGEST` to
  `d2b5513d641e10d8005b2793a628034e2b9d4c3c4a05bb63509ab2f868b8b9c7` and extended its comment with
  the rule for distinguishing a recapture from a regression. **Finished.** Commit `0177df1`.
- `hub/hub/spec_service.py` — `rename_document` now refuses on `first_approved_at is not None`
  rather than `phase == APPROVED`. **Written by a firing, verified and landed by me.** Commit `1db9781`.
- `hub/tests/test_spec_rename.py` — two new tests for the archive and reopen holes. Commit `1db9781`.
- `hub/hub/api/v1/tasks.py`, `hub/hub/schemas/tasks.py`, `hub/tests/test_task_dependency_reads.py` —
  section 7. **Written by a firing, verified and landed by me.** Commit `2e06d87`.
- `hub/hub/scheduler.py`, `hub/hub/api/v1/jobs.py`, `hub/tests/test_loop_claim_dependency_gate.py` —
  section 9. **Written by a firing, verified and landed by me.** Commit `1f7697c`.
- `openspec/changes/task-dependencies/tasks.md` — ticked §6, §7, §9 with landing notes.
- `.claude/autonomous/STATE.json` and `.claude/autonomous/2026-08-20-open-specs-log.md` — the run's
  position and narrative, rewritten many times. **Finished.**
- `.claude/autonomous/scratch/render_dump.py` — **gitignored**, kept deliberately. Renders the exact
  document the digest test renders, so a future digest recapture can be diffed rather than reasoned
  about.

**Not mine — a concurrent session committed 5 times into this branch while I worked:**
`f1951cf`, `f152fd1`, `c823551`, `470d0cc`, `c77d0a6`, plus `eff4039`. They touch
`openspec/explorations/`, `openspec/changes/loop-notices-and-reacts/`,
`hub/tests/test_agent_message_routing.py`, and `task-dependencies`' design/tasks. **No file overlap
with mine.** Staging explicit paths is the only reason that stayed true.

## Key decisions

1. **Drove the run with a Windows Scheduled Task, not `ScheduleWakeup`/`CronCreate`.** *Rejected:*
   the session-bound drivers, because the 2026-08-15 run asked for nine hours and got forty minutes
   when the session went away. This was correct — run 1 survived the interactive session ending.
2. **Ordered the queue so `loop-notices-and-reacts` came after `task-dependencies`**, because its
   proposal reasons about the world `task-dependencies` creates. Vindicated in an unexpected way:
   it has since been narrowed by 20 tasks precisely because that world changed.
3. **Skipped §8 (the board) to reach §9.** *Rejected:* doing sections in order, which would have
   left the deadlock window open past the deadline for a UI feature.
4. **Committed three sections (6, 7, 9) that headless firings wrote but failed to land**, after
   verifying each myself. *Rejected:* leaving them for the next iteration — three consecutive
   iterations had already failed to land work, and the tree had been dirty across four boundaries.
5. **Mutation-checked rather than trusting a green suite.** For §6, reverting the check to
   `phase == APPROVED` makes exactly its two new tests fail. For the delete fix, excluding
   `task_dependencies` from the sweep makes the orphan test fail. Both files restored byte-identical
   afterwards and confirmed with `git status`.
6. **Recaptured the render digest rather than "fixing" the renderer**, after diffing the rendered
   HTML across the regression boundary and confirming the delta was exactly `"depends_on": []` and
   `"from": null`. The test's own comment prescribes recapture for a deliberate payload change.
7. **Told the loop to expect the concurrent session rather than stand down** — the operator chose
   this explicitly. The 11:37 firing had ended its turn writing *"no commits, no pushes, and no
   `STATE.json` edits, to avoid adding a third writer"*, which was reasonable and wrong.
8. **Read "13h" as 13:00 today, not 13 hours.** Stated the assumption to the operator; the shorter
   reading is the recoverable one.

## Constraints and user directives (verbatim)

From this session:

- *"I'm going to sleep. There is a lot specs opens for development. Work on them in any order you
  see fit. I won't respond to anything anymore. Most things are specced out. Prepare a autonomous
  run until 8AM. Good night"*
- *"Ahhh so there still work to be done. Okay. Schedule a new autonomous run for 13h and continue
  the work on this branch"*
- **Archiving:** chose **"Not yet"** when offered all three complete changes. Do not raise again
  unprompted.
- **Regenerating `spec/` from code and openspec:** raised, then **dropped** in favour of finishing
  the implementation. **Do not run a bulk reindex** — `corpus-aware-documents` 8.4 wants the
  operator to read the *first* reindex diff themselves.
- **Two writers on one branch:** chose *"Keep both, tell the loop not to stand down."*

Standing, carried forward and **still in force**:

- *"8010 is a test environment. 8000 is real usage."*
- *"Any test that you can do with playwright do it. Just leave the tests that I need to do and guide
  me with what I need to test"*
- Never `git add -A`; stage paths explicitly. **Load-bearing all session** — six foreign commits.
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp. `approve_tool_call` has **no return
  annotation**. Keep the two `spec_manifest.py` twins in sync by hand.
- `hub/hub/static/ui` is a committed build artefact — after `cd hub/ui && npm run build`, run
  `py -3.11 scripts/refresh_ui_bundle.py` (`make` is not on PATH in Git Bash here).
- From memory: commit each completed checkpoint without asking first; specs must carry test guides
  split into agent-verifiable and human-only.

## Dead ends

**Three driver defects, which are the real story of this session.** They cost roughly **80 of run
2's 210 minutes**:

1. **Background-and-wait.** Each firing is a fresh `claude -p`; a command it backgrounds **dies when
   the process exits**. Three consecutive iterations (10:36, 10:52, 11:06) started the ~15-minute
   test suite in the background, ended the turn to "wait" for it, and killed it. No notification was
   ever coming. **Mitigated** by `NEVER_BACKGROUND_AND_WAIT` in `STATE.json`; **not fixed** in
   `run-iteration.ps1`, which still says only *"Verify it: run the tests."*
2. **Wrapper processes outliving their child.** PID 20280 started 11:37, its `claude` exited 11:45,
   the PowerShell wrapper never terminated. `MultipleInstances=IgnoreNew` then treats the task as
   running and **silently skips later firings with no log line at all** — the log simply goes quiet.
   Killed by hand. **Not fixed.**
3. **A dead iteration's fresh heartbeat.** An iteration around 12:04 refreshed `last_heartbeat` to
   "now" and then died without committing or backdating it. The 25-minute grace then correctly
   blocked the 12:07 and 12:22 firings, costing 30 minutes. The interlock **cannot tell "working"
   from "dead"**. **Not fixed.**

**Other traps hit this session:**

- **The Bash tool's cwd persists between calls.** `cd hub/ui` in one call silently broke
  `openspec validate` and a `wc -l` two calls later, which reported "No items found to validate" and
  a missing file. Use absolute paths in anything that matters.
- **`pytest <nonexistent_file.py>` runs nothing and reports `5 warnings in 0.00s`** — which reads
  almost exactly like a pass. Cost two wasted verification attempts (`test_tasks_api.py` and
  `test_loops.py` do not exist; the real names are `test_tasks.py`, `test_task_transitions_api.py`,
  `test_scheduler.py`). **Always check the test count is non-zero.**
- **`cp` after `cd hub &&` resolved relative to `hub/`**, so a mutation-check restore silently failed
  and left a source file mutated. Caught by re-grepping the file. Restore with absolute paths.
- **Reasoning about which commits touched a file is not bisecting.** The render regression was
  attributed to `c2492c7` because only it and one other touched `spec_render.py`. Bisecting all
  eleven commits named `758db52`, which touches `spec_payload.py` instead. Targeted selection follows
  the file you edited, not the files that depend on it.
- **`pytest hub/tests/` does not accept `--timeout`** (no `pytest-timeout` plugin); it fails the
  whole run with "unrecognized arguments".

Carried forward from 0067, not re-encountered but still true: PowerShell here-strings (`@'...'@`)
mangle a commit message in the **Bash** tool; `py -3.11` cannot open a Git Bash `/tmp/...` path;
always pass an absolute sqlite path; credentials live in `operator_credentials`, not `api_keys`;
`py -3.11 -m openspec` fails, use the console script.

## Verification

**Ran, and passed:**

- **Full Hub suite, four times**, tracking the run: `2582` (pre-run baseline) → **`4 failed, 2665
  passed`** (run 1's real end state) → `2669 passed, 0 failed` (after my repair) → `2699 passed, 0
  failed` (after §6). Iteration 17 independently ran it after §9: **`2718 passed, 12 skipped, 1
  xpassed, 0 failed` in 925s** — note it used `--ignore=tests/browser`, so its *skip* count differs
  from my full-path runs (84).
- `pytest tests/ -q` (CLI) → **404 passed, 3 skipped**, unchanged all session.
- `npx vitest run` → **1172 passed / 118 files**. `npx tsc --noEmit` → clean.
- `openspec validate --all --strict` → **40 passed, 0 failed**, checked at both ends of the session.
- Targeted: §6 `test_spec_rename.py` 22 passed; §7 104 passed across six files; §9 130 passed / 3
  skipped across seven files.
- **Two mutation checks**, both confirming the tests have teeth, both restored byte-identical.
- The corpus arrangement read directly out of `spec/index.json`: 41 documents, 40 with a `parent`.
- `create_spec_document` is **served** — it appeared in this session's own MCP tool list, which is
  live evidence rather than a claim about `agent-created-documents`.

**NOT run — do not claim otherwise:**

- **`ruff` / `black` / `mypy` were never run repo-wide**, only on touched files. `mypy` is known
  *not* clean: ~296 pre-existing errors across 40 files, confirmed identical before the change by
  `git stash`. `agent-created-documents` 5.3 is unticked for exactly this reason.
- **Task 7.3's "must not N+1" property was never measured.** No query-counting test exists. The
  task is ticked with that caveat stated inline in `tasks.md`. **This is the weakest tick on the
  branch.**
- **No browser/Playwright test was run this session**, and the Spec tab was never opened. Every one
  of the 21 human-only tasks is untouched.
- **CI has not been checked** for any of the 43 commits.
- **The UI bundle was not rebuilt.** `ui_stale: true` on both 8010 and 8000, stamped
  2026-08-20T14:14:54Z. **Inherited, not caused here** — no `hub/ui/src` change was made.
- **The concurrent session's six commits are unverified by me.** I read their messages, not their
  diffs.

## Git state

- **Branch:** `autonomous/2026-08-20-open-specs`. **HEAD:** `c77d0a6`. **Working tree clean.**
- **43 commits ahead of `master`.** `master` itself is unchanged and still 16 commits ahead of
  `origin/master`, unpushed — the operator declined that push two sessions ago.
- **2 commits unpushed:** `470d0cc`, `c77d0a6` (both the concurrent session's).
- The Scheduled Task **self-unregistered past 13:00** as designed.

## Next steps

1. **Push the two stragglers:** `git push` on this branch to carry `470d0cc` and `c77d0a6` to
   `origin/autonomous/2026-08-20-open-specs`. Nothing else is needed to make the branch durable.
2. **Fix `run-iteration.ps1` before arming any run 3.** Two concrete changes:
   (a) make the wrapper exit when its `claude` child exits, so `IgnoreNew` stops silently skipping
   firings — and add a log line when a firing *is* skipped, since today the log just goes quiet;
   (b) make an iteration backdate `last_heartbeat` on **any** exit path, not only the happy one.
   Without these a third run loses the same ~40%.
3. **Add the missing query-counting test for task 7.3** in `hub/tests/test_task_dependency_reads.py`
   — assert `GET /tasks/board` issues a bounded number of queries regardless of card count. It is
   the one ticked box on this branch whose property was never measured.
4. **Then continue `task-dependencies`:** §10 (agent-verifiable checks, 9 tasks) is the cheapest
   next unit; §8 (the board, 13 tasks) needs `hub/ui/src` plus a bundle rebuild.

## Open questions for the user

- **Merge, and how?** 43 commits, of which ~9 carry real work. A cherry-pick of the `Land ...`
  commits plus `0177df1` is the shape; the rest is bookkeeping and the concurrent session's
  explorations.
- **Is `task-dependencies` merge-ready without §8?** Enforced and readable, not visible on a board.
- **The three taste judgements** in `document-adoption` §8, open since handoff 0067.
- **Should adoption have a UI?** curl is still the only operator path.
- **Should CLAUDE.md's trial-Hub table be corrected?** It still misstates both the database and the
  registration — offered twice, never selected.
- **Should 8010 stay on beta**, or return to `<repo>/hub/data/agentweave.db`?
- **Push `master`'s 16 commits?** **Retire `openspec/specs/`?** **Delete `proj-adf8a200`?** All open
  since handoffs 0062–0063.
- **Archiving** — answered "Not yet" today; re-raise only when the operator does.

## Read on resume

- `.claude/autonomous/2026-08-20-open-specs-log.md` — 1242 lines, newest at the bottom. The
  narrative of both runs including every driver failure as it happened. **The single best source.**
- `.claude/autonomous/STATE.json` — `run2_outcome`, `NEVER_BACKGROUND_AND_WAIT` and
  `CONCURRENT_SESSION_IS_EXPECTED` are the three keys worth reading before arming anything.
- `openspec/changes/task-dependencies/tasks.md` — §7.3's caveat and §9's landing notes; §10–§12 are
  what remains.
- `openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md` — the operator settled job/loop/flow
  as three configurations of one row, and `create_flow` as a third tool. **Unread by me**, and it is
  why `loop-notices-and-reacts` shrank.
- `openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md` — the other half of that
  reasoning. Also unread by me.
- `.claude/skills/autonomous-session/scripts/run-iteration.ps1` — where next-step 2's two fixes go.
