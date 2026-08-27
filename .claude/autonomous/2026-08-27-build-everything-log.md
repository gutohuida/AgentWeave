# Autonomous run, 2026-08-27 — build everything decided

**Branch:** `autonomous/2026-08-27-build-everything-decided`
**Parent:** `master` @ `a2f61c3` — cut 2026-08-27 ~00:30 local
**Runner:** `claude` / `claude-sonnet-5` / `unattended-full-access`
**Stop at:** 2026-08-27T08:00:00+01:00
**Driver:** Windows Scheduled Task (`AgentWeaveAutonomousSession`) — survives the interactive
session ending, which `ScheduleWakeup` and `CronCreate` do not.
**State:** `.claude/autonomous/STATE.json` — 23 queue items, `current: Q1-R1`.

Newest entry at the **bottom**.

---

## Limits, stated before any work so a later process inherits them

1. **Stay on this branch.** No commits, merges or rebases onto `master`. Master was merged and
   CI-verified by the operator immediately before this run was armed; it is not this run's to move.
   No PRs — the standing directive is **push, no PRs**.
2. **Nothing outward-facing.** No publish, no release, no force-push, no history rewriting. Pushing
   *this* branch every iteration is required, not optional: it is what makes the work durable.
3. **Nothing destructive.** No deleting projects, databases, or kept reproductions.
4. **Never mark work complete on the strength of a plan existing.** This matters more when nobody is
   checking, not less.
5. **Every claim is measured or labelled unverified.**
6. **Decisions that are genuinely the operator's get written down, not guessed** — they collect in
   `STATE.json`'s `decisions_for_user`, which is what the operator reads first.

The full 14 limits and 39 dead ends live in `STATE.json`. Read them before the first unit of work;
seven of the dead ends were added the night this run was armed and have already cost time once.

---

## Iteration 0 — arming (interactive, operator awake)

Not a work iteration. Recorded so the morning knows what state the run started from.

**What the operator decided, in one place.** All eight open findings were answered on 2026-08-26 and
the decisions are recorded with their rejected alternatives in
`openspec/explorations/2026-08-26-what-is-still-unanswered.md`. Every queue item below cites that
file rather than restating it. Two of the eight answers changed the shape of the item they answered:
F58 became per-task worktrees (and is **out of scope tonight** — it needs its own exploration), and
F61's chosen fix was **withdrawn** because it rested on "role", a concept the product does not own
and that CLAUDE.md forbids recreating.

**The round discipline, decided 2026-08-27 and binding on this run.** A change with no artifacts yet
gets three separate rounds before any implementation — explore-then-propose, compare-to-code-and-fix,
compare-and-fix-again — each its own queue item and its own commit. A change that already has
artifacts gets one round: compare it to the codebase and confirm the spec is good. Rounds must not be
collapsed; the point is that the second and third readings happen with the first already written
down. **A round that finds nothing must enumerate what it checked** — "looks fine" means the round
did not happen.

**Green at arming, and unusually well established.** CI run `33022066377` passed all eight matrix
cells on `master`: `ui-test`, `hub-test`, and `test` across {ubuntu, windows, macos} × {3.11, 3.12}.
That is the first time this code has ever run on Linux, macOS or Python 3.12 — before tonight it had
only ever been green on Windows/3.11 locally, because CI triggers only on `master` pushes and PRs,
and 80 commits had accumulated on a feature branch. **Any red from here is this run's own.**

**One inherited defect cleared before arming.** `/health` reported `ui_stale` and
`AW_CHECK_UI_BUNDLE=1 test_ui_build_stamp.py` genuinely failed: the stamp recorded
`src_commit: 3ec36e5`, but `38a2394` changed four files under `hub/ui/src` afterwards while
recording the pre-change commit. Rebuilt and re-recorded (`bf04ad8`) — bundle bytes unchanged, only
the stamp moved. A loop that starts on inherited red cannot tell its own breakage from what it was
handed.

**What a reviewer should distrust about this entry:** nothing was built in it. It records
preparation only.

---

## Iteration 1 onwards

*(appended by the driver, one entry per iteration)*

---

## Iteration 1 — Q1-R1: reachable-by-a-human, explore then propose (2026-08-27T01:01:11+01:00)

Confirmed branch and `git log` matched `STATE.json` before starting: current branch is
`autonomous/2026-08-27-build-everything-decided`, cut from `master@a2f61c3` with one prep commit
(`174abb8`) on top. No reconciliation needed.

**Explored every path Q1-R1 named, before writing anything**, and one it didn't:

- `hub/hub/utils.py:25` `persist_event` — confirmed it writes `severity` verbatim
  (`entry = EventLog(..., severity=severity)`, `:49`), no normalisation.
- All 21 `persist_event` call sites: 20 use `"info"`/`"warn"`/`"error"`; exactly one
  (`run_divergence.py:613`) uses `"warning"`.
- `EventRow.tsx` `SEVERITY_CHIP` (:37-42) and `SEVERITY_BORDER` (:44-47) — key on `error`/`warn`/
  `info`/`debug` (chip) and `error`/`warn` (border) only. `"warning"` matches neither map.
- `ActivityLog.tsx` `SEVERITY_FILTERS` (:31) and its strict-equality filter (:165) — same hole.
- `events.py:42-43` (`GET /events/history`) and `logs.py:58-59` (`GET /logs`) — both filter
  `EventLog.severity ==` exactly.
- **Not named in the queue item, found by reading `persist_event`'s callers exhaustively**:
  `hub/hub/api/v1/logs.py:85` (`POST /logs`) passes `severity=body.severity` straight from an
  external request body; `schemas/logs.py:15,25` bounds it only to 64 characters, no enum. This is
  why the exploration's "normalise in `persist_event`, not just the one call site" recommendation is
  the only fix that actually closes the input surface — an API boundary fix alone would still leave
  every internal call site free to drift.
- `conversation_titles.py:168-224` `generate_conversation_title` — confirmed fully wired: gated on
  `project.conversation_title_mode == "generate"` (:185), called from `agent_trigger.py` at run
  completion, declines correctly on an operator-set title (:181, :213) and an unsupported runner CLI
  (:189-190).
- `db/models.py:96,103`, `api/v1/projects.py:87-89`, `ui/src/api/projects.ts:88-89` — field exists
  end to end. `PUT /projects/{id}/settings` (`projects.py:446-496`) already validates and persists
  both `conversation_title_mode` and `conversation_title_runner_id`, including the cross-project
  runner check at :485-496 — confirmed no backend work is needed for this half.
- `ProjectSettingsPanel.tsx` — zero references to either field, confirmed by grep.
  `projectSettingsPanel.test.tsx:23-24,146-147` fixtures `conversation_title_mode: 'generate'` with
  no control in the panel that could produce that value.

**Design choice made while proposing, not left to the exploration's account**: rather than
inventing a new capability, searched `openspec/specs/*/spec.md` for existing requirements this
change makes newly true. Found `agent-capability-plane`'s "Operator-facing severity values are the
ones the operator's view understands" (already states the general rule, pinned by only one
scenario — a refused action) and `conversation-lifecycle`'s "Title generation is a project setting,
off by default" (documents the setting, never requires it be operator-reachable). Both are modified
in place rather than duplicated as new requirements.

**Ran `openspec new change reachable-by-a-human`**, then wrote `proposal.md`, `design.md`, two
spec deltas (`agent-capability-plane`, `conversation-lifecycle`), and `tasks.md` (3 groups, tests
opening each phase per the method reminder, mutation checks 1.7 and 2.5 named explicitly).
`npx openspec validate reachable-by-a-human --strict` passes.

**What this round did NOT do**: no code was touched. Per the round discipline, R1 is explore-then-
propose only; R2 and R3 are separate queue items and separate commits.

Committed `3b80f99`. Next: Q1-R2 — compare the proposal to the code claim-by-claim and fix drift.

*What a reviewer should distrust about this entry*: the exploration and the proposal were written
by the same pass with no independent check yet — that is exactly what R2 exists to catch.


