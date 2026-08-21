# Handoff: driving the Hub found seven defects, and a change to hold them

**Date:** 2026-08-21T16:24:33+01:00 · **Branch:** `autonomous/2026-08-20-open-specs` · **HEAD:** `264a299`
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive)
**Previous handoff:** `.claude/handoffs/handoff-0069-2026-08-21-1405-the-loop-became-a-flow-and-three-loop-bugs-died.md`
**Status:** chunk complete. Everything of mine is committed and pushed. The working tree is dirty
with **run 3's** in-flight work, not mine — see Git state.

## Goal

Continue the dogfooding migration by using the product and fixing what using it reveals. This session
ran 14:13–16:24 **alongside run 3**, which was implementing `task-dependencies` section 8 on the same
branch throughout.

The *why* that governs judgement calls is unchanged from 0069: friction found while using AgentWeave
is a **deliverable**, not a distraction. This session is the strongest evidence yet for that — every
one of the seven defects below came from driving the Hub, and **none** would have been found by
reading code or running the suite.

## Current state

### Seven defects, all measured on the live trial Hub

Recorded in two explorations and now owned by a proposed change. Two are fixed.

| # | Defect | State |
|---|---|---|
| 1 | `blocked` was claimable, so a loop fired an agent per tick at work that could not move | **FIXED** `dc37b1a`, verified live |
| 2 | An unbound agent was reported as `Runner CLI '<its own name>' was not found in PATH` | **FIXED** `022cd36` |
| 3 | A firing that starts no agent leaves `JobRun` at `in_progress`, so the card reads "firing" indefinitely | proposed, group 2 |
| 4 | That card stays wrong until the Hub restarts | proposed, group 3 |
| 5 | Archiving a broken agent is refused *because* it is broken (undeliverable queue entries block it) | proposed, group 6 |
| 6 | A loop outlives its job's archival, then refuses archival as "still running" | proposed, group 5 |
| 7 | Every **refused** firing still creates a named, empty conversation | proposed, group 4 |

### `diagnose-and-clear-a-broken-loop` is proposed and validates

`openspec/changes/diagnose-and-clear-a-broken-loop/` — proposal, design (D1–D6), tasks (10 groups),
and four spec deltas. `openspec validate --all --strict` → **42 passed, 0 failed**.

The operator decided all three of its open questions this session (see Key decisions 5–7), and one
**dissolved rather than being answered** — the reaper needed no new trigger once group 2 stopped
producing stranded rows. Group 3 shrank from scheduler work to a derivation fix, and
`run_reconciliation.py` is now not modified at all.

### The driver was diagnosed and re-tuned

0068/0069 blamed "the wrapper exits early" for ~40% of run 2's firings being lost. **That was wrong.**
`MultipleInstances = IgnoreNew` means Windows *silently drops* a firing that lands mid-iteration —
no log line at all, which is why it read as an early exit. Overlap is therefore impossible, so the
interval never bounded iteration length; it only bounded idle time. **Lengthening it was backwards.**

Moved to **5 minutes** in place (the live task took it without disturbing the running iteration), and
the installer's doc comment, which taught the opposite, is corrected. Measured effect: iteration 2
began **29 seconds** after iteration 1 ended, against gaps of up to 20 minutes before.

### Two documentation claims were false and are corrected

- **CLAUDE.md named the wrong database.** 8010 serves `~/.agentweave/hub/profiles/beta/agentweave.db`,
  not `<repo>/hub/data/agentweave.db`. Proved by calling the API and watching which file's mtime
  moved. Fixed in `1e67980`; the doc's own "verify before trusting this, including this row"
  paragraph now records that it was wrong for a day.
- **`proj-5e960453` is empty** — no agents, tasks, loops or jobs. The live fixtures are in
  `proj-ff695d96` (`aw-loop10`). "Holds this repo's live trial fixtures" was also wrong.

### The board decision unblocked run 3 within one iteration

The operator decided section 8's concurrency display (Key decision 4). Run 3's next iteration
recorded *"section 8's hazard confirmed lifted"* and started building; by this handoff it has landed
8.1–8.9 and 8.12 across four iterations.

## Files touched

**All committed and pushed.** The four dirty files in `git status` are run 3's, not mine.

**Code and tests (mine)**

- `hub/hub/scheduler.py` — `blocked` removed from `CLAIMABLE_LOOP_TASK_STATUSES`; four docstrings
  corrected. **Finished.**
- `hub/tests/test_scheduler.py` — two new tests (a pure assertion and a behavioural reproduction),
  plus the derived-gap expectation widened to `{completed, under_review, blocked}`. **Finished.**
- `hub/hub/launchability.py` — `RUNNER_UNBOUND`, its `probe_agent` branch, and `get_agent_config`
  now merging the bound `Runner`. **Finished.**
- `hub/tests/test_launchability.py` — two new tests. **Finished.**
- `hub/hub/static/ui/ui-build-stamp.json` — re-recorded. **Finished.**

**Specs and explorations (mine)**

- `openspec/changes/diagnose-and-clear-a-broken-loop/` — **new**: proposal, design, tasks, and deltas
  for `loop-firing-accountability` (new), `agent-loops`, `agent-configuration`, `run-task-binding`.
- `openspec/changes/task-dependencies/design.md` — **new D12**, the board's concurrency display.
- `openspec/changes/task-dependencies/tasks.md` — 8.4 reworded; 8.14–8.16 added.
- `openspec/explorations/2026-08-21-what-a-flow-fires-into.md` — **new**, then twice corrected and
  twice extended with live measurements.
- `openspec/explorations/2026-08-21-which-band-blocked-belongs-to.md` — **new**, answers
  `loop-notices-and-reacts` task 3.4, extended with the live verification.
- `openspec/explorations/2026-08-21-reviewing-loop-becomes-a-flow.md` — **new**, the review.

**Config (mine)**

- `CLAUDE.md` — the trial-Hub database row and the `hub/data/` paragraph, both corrected.
- `.claude/skills/autonomous-session/scripts/install-driver.ps1` — `EveryMinutes` default 15 → 5, the
  doc comment reversed, and `IgnoreNew`'s silent-drop behaviour documented.
- `.claude/autonomous/STATE.json` — the territory claim (see Key decision 8).

## Key decisions

1. **`blocked` leaves the claimable band.** A task in `blocked` provably has an unanswered question,
   so no agent the loop can fire can advance it. *Rejected:* leaving it and fixing the briefing —
   which would tell the agent about a block it still cannot clear.
2. **`park_task_for_question`'s orphaned-release bug was deliberately NOT fixed.** Removing `blocked`
   from the claim closes the loop's route into it, and the remaining fix changes what a
   `Question`/`Task` binding means — an operator-in-the-loop semantic, not a scheduling one. It is
   group 7 of the new change.
3. **The driver interval goes to 5 minutes, not 30.** `IgnoreNew` makes overlap impossible, so a
   short interval only reduces idle time. *Rejected:* 0068's proposal to lengthen it.
4. **The dependency board shows concurrency per card, with a slow pulsing hue for liveness.**
   Operator: *"The card can show and we should use more of the UI... Take advantage of visual cues."*
   The cue carries a different fact from the badge — the badge says the task **is** `in_progress`,
   the pulse says a run is executing **now**, and `has_open_divergence` exists because those can
   disagree. *Rejected:* per-layer and a flow header.
5. **A firing whose turn never began records `failed`.** Already where these rows end up. The
   decisive argument against a new word: `JobCard.tsx:73` renders `error_summary` for
   `failed`/`skipped` only, so `not_started` without a UI branch would hide the reason the change
   exists to surface.
6. **The archive refusal carries a structured field the UI turns into a button.**
   `deleteQueueEntry` already exists in the UI. *Rejected:* prose naming the endpoint (tells a REST
   route to someone in a UI).
7. **The reaper gains no trigger; the derivation is fixed instead.** Group 2 removes the producer of
   stranded rows, so Hub-start already matches the only remaining failure mode.
8. **Concurrent work is coordinated by a claim in STATE.json, written between iterations.** Each
   iteration rewrites that file wholesale at its end, so a note added mid-iteration is clobbered
   before anyone reads it.

## Constraints and user directives (verbatim)

From this session:

- *"I want to let that other working and in this one explore more things that needs to be explored"*
- *"The card can show and we should use more of the UI. For example a green hue around the car
  pulsating slowly... Or something like that. Take advantage of visual cues."*
- *"You can restart the hub"*
- *"You can spend more turns to test"*
- Via AskUserQuestion: **"Shorten to 5 minutes"**, **"Rebuild UI, then drive 8010"**, **"I'll decide
  the display now"**, **"New openspec change, I keep executing"**, and all three of Key decisions
  5–7.

Standing, still in force:

- Stage paths explicitly; **never `git add -A`**. Never `git stash` on this branch.
- Never mark a task complete on the strength of a plan existing.
- `hub/hub/mcp_server.py` may import **only** stdlib + fastmcp. `approve_tool_call` has **no return
  annotation**.
- After `npm run build`, run `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and
  `hub/hub/static/ui` together.
- Keep the two `spec_manifest.py` twins in sync by hand.
- From STATE.json: **do not push `master`** (16 ahead of origin); do not archive any change; do not
  bulk-reindex `spec/`; **do not touch the Hub on port 8000** — that is real usage. 8010 is the test
  Hub and may be driven and restarted.
- From memory: commit each completed checkpoint without asking; specs carry test guides split into
  agent-verifiable and human-only.

## Dead ends

- **`GET /api/v1/projects/{id}/runs` DOES NOT EXIST.** It 404s, and a parser reading `.get('runs')`
  off the error body reports "0 runs". I made three confident "no agent spawned" claims on that
  basis. The conclusions survived only because I re-checked against the `runs` table directly. **Use
  SQLite read-only against the beta DB for run evidence**, or the project `/status` endpoint.
- **`/api/v1/projects/{id}/events` is the SSE stream, not an event log.** It hangs a plain `curl`.
- **`agents_active` in `/status` is `sorted(senders | assignees)`** — agents who have sent messages or
  hold task assignments. It does **not** mean "has a live run", and I briefly misread a disagreement
  with the stop endpoint as a bug.
- **A behavioural loop test that expects firings to be refused will HANG against code where they are
  not.** The mock supplies reads for one spawn; unfixed code spawned on all four firings, drained it,
  and the awaited background task never returned. ~3 s CPU over minutes. Write a pure-assertion test
  first for the measurement, keep the behavioural one for after the fix.
- **`JobCreate`'s queue-seed field is `initial_tasks`, not `tasks`** (`extra: "forbid"` rejects the
  latter).
- **A shell variable that silently ends up empty turns `PATCH .../tasks/$T` into a collection-route
  call**, which returns `Method Not Allowed` and looks like a wrong verb.
- **Do not trust `Get-Process` timing to attribute a spawned agent.** A `claude.exe` that appeared at
  the right moment was the autonomous driver's own iteration, not the probe.

## Verification

**Ran, and passed** (all `py -3.11`):

- Full Hub suite, twice: **2723 passed** / 84 skipped / 1 xpassed / 0 failed (after the `blocked`
  fix), then **2726 passed** / 84 skipped / 1 xpassed / 0 failed in 11m59s (after the launchability
  fix). *The tree moved between them — run 3 landed sections 10, 12 and part of 8 — so the +3 is not
  purely mine.*
- `tests/test_scheduler.py` → **31 passed** (was 28). `tests/test_launchability.py` → **38 passed**
  (was 36). The 13 loop/task/binding suites → **254 passed, 3 skipped**. The 8 launchability
  consumers → **186 passed, 1 xpassed**.
- `ruff check` and `black --check` clean on every touched file.
- `openspec validate --all --strict` → **42 passed, 0 failed**.
- **Live on 8010**, restarted onto current code: a blocked task's firings refused twice with
  `"loop queue is stalled: no claimable task among 1 open (1 blocked)"`, both `JobRun`s `skipped`,
  `firing_active: false`, `queue: {"blocked": 1}`; then release → `run-424f7dda`, builder,
  **completed, exit 0, 8 s**.
- **Live on 8010**, Finding A: `firing_active: true`, `JobRun` `in_progress` with `session_id: null`,
  `waiting_reason: "Runner CLI 'probe-norunner' was not found in PATH."`; after restart, `failed` /
  `false`.

**NOT tested — do not claim otherwise:**

- **The launchability fix was never re-verified live.** The probe agent was archived during cleanup,
  so the new reason is asserted only by unit tests. Task **1.6** of the new change covers this.
- **Nothing in `diagnose-and-clear-a-broken-loop` groups 2–7 is implemented.** 2 of ~40 tasks are
  ticked, both decisions rather than code.
- **No UI was opened in a browser all session.** The board run 3 is building is vitest-only.
- **`mypy` was not run** on any touched file.
- **The §4a orphaned-release defect was never reproduced** — it is read-from-source only.

## Git state

- **Branch:** `autonomous/2026-08-20-open-specs`. **HEAD:** `264a299`. **Pushed** — 0 unpushed.
- **Working tree is dirty, and none of it is mine.** `hub/ui/src/App.tsx`,
  `hub/ui/src/__tests__/App-mount.test.tsx`, `hub/ui/src/__tests__/dependencyBoardView.test.tsx`,
  `hub/ui/src/components/tasks/DependencyBoardView.tsx` — run 3's iteration 6, wiring the dependency
  board into the tasks tab (task 8.11). **Do not revert, stash or stage these.**
- `master` is 16 ahead of `origin/master` and must not be pushed.
- **31 commits since this session began** (`be78d66..HEAD`): **15 mine**, 16 run 3's. Counted, not
  estimated — an author filter does not separate us, because the driver commits as the same git user
  on this machine. Run 3's are the ones whose subjects start `Land task-dependencies`, `Record run 3`
  or `Release the branch`.

## Run 3 — live, and the coordination that keeps us apart

- **Armed until 19:00**, firing every **5 minutes**. Iteration 6 started 16:14:37 and is in flight.
- It has landed `task-dependencies` section 8 tasks 8.1–8.9 and 8.12 across four iterations.
- **`.claude/autonomous/STATE.json` carries a claim** (`concurrent_session_claim`, and the head of
  `next_action`) reserving `hub/hub/scheduler.py`, `run_reconciliation.py`, `launchability.py`,
  `run_task_binding.py`, `api/v1/agents.py`, `api/v1/jobs.py`, `api/v1/inbound_queue.py` and
  `hub/tests/test_scheduler.py`, and forbidding `loop-notices-and-reacts` this run.
- **The claim must be re-asserted if an iteration drops it** — each iteration rewrites STATE.json
  wholesale. It asks the run to carry the paragraph forward; verify it is still there before editing
  any claimed file.
- **If you are NOT going to keep fixing these files, release the claim** so the run can take
  `loop-notices-and-reacts`.

## Next steps

1. **Implement group 4 of `diagnose-and-clear-a-broken-loop` — a refused firing must create no
   conversation.** Start with task 4.1: a failing test in `hub/tests/test_scheduler.py` that fires a
   stalled loop three times and asserts three conversations exist (measured: five firings → five
   conversations, three of them refused). Then move `new_conversation`/`name_conversation` from
   `hub/hub/scheduler.py:817-829` past the stop check (~868) and the stall check (~956-985). Assert
   the **property**, never the ordering — `loop-notices-and-reacts` will restructure those branches.
   Highest value first because it scales with the 5-minute cron: twelve empty threads an hour.
2. **Then groups 5 and 7** — both self-contained, no open questions, no UI.
3. **Group 3** is now just a derivation fix in `hub/hub/api/v1/jobs.py:228-234`.
4. **Task 1.6** — re-verify the launchability fix live on 8010 with a fresh probe agent.
5. **Task 1.5** — delete the now-redundant runner-merge blocks at `api/v1/agents.py:191-198` and
   `api/v1/inbound_queue.py:157-173`.

## Open questions for the user

- **Is `loop-becomes-a-flow` approved?** Reviewed this session (`openspec/explorations/2026-08-21-reviewing-loop-becomes-a-flow.md`),
  still unapproved, 60 tasks assume it. Its D4 rung 2 has a **contradiction that will stop a flow
  resuming its own work** and wants one sentence before anyone implements the ladder.
- **21 human-only verification tasks** are queued across three changes and need the operator at a
  live Hub: `agent-created-documents` §6 (6), `corpus-aware-documents` §8 (7),
  `task-dependencies` §11 (8).
- **Archive the three complete changes?** Answered "not yet" on 2026-08-21 morning.
- Standing since 0062–0064: register this repo as a project; retire `openspec/specs/`; delete
  `proj-adf8a200`.
- **Should `ui_stale` be made unskippable?** It cried wolf for a day because only
  `refresh_ui_bundle.py` writes the stamp and a correct commit can omit it.

## Read on resume

- `openspec/changes/diagnose-and-clear-a-broken-loop/tasks.md` — **first.** The work queue; group 4
  is next step 1.
- `openspec/changes/diagnose-and-clear-a-broken-loop/design.md` — D1–D6, including why group 3 shrank
  and why `failed` was reused.
- `openspec/explorations/2026-08-21-what-a-flow-fires-into.md` — §2a is the measured evidence for
  findings 3–7, with the verbatim API responses.
- `.claude/autonomous/STATE.json` — the claim, and run 3's position. Check it before editing any
  claimed file.
- `hub/hub/scheduler.py:805-830` and `:936-1020` — conversation creation, the refusal points, and the
  discarded `ScheduleResult`. Groups 2 and 4 both live here.
- `openspec/explorations/2026-08-21-reviewing-loop-becomes-a-flow.md` — only if the operator returns
  to approving that change.
