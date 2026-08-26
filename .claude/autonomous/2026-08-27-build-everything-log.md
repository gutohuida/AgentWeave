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
