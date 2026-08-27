# Autonomous run — 2026-08-27, the rest of the work

**Branch:** `autonomous/2026-08-27-the-rest-of-the-work`, cut from `master` @ `a90cad6`
**Runner:** `claude`, model `claude-opus-5`, `unattended-full-access`
**Stop at:** 17:00 local. **Driver:** Windows Scheduled Task `AgentWeaveAutonomousSession`, one fresh
headless process per firing, every 5 minutes.

Newest entry at the **bottom**. Written for a human who was not watching.

## Iteration 0 — what was prepared, and what was decided before the run started

Prepared in an attended session on the morning of 2026-08-27, so the loop meets no question that
thirty seconds of operator time could have answered.

**The state of the world at arming.** `master` is at `a90cad6` and fully CI-green — run
`33052879055`, all nine cells including `hub-test` on Linux, which is the cell that had been red on
the overnight branch. It carries: last night's 12 work commits, the width-test race fix, the F70 and
F71 fixes the operator decided this morning, both in-flight openspec changes synced into
`openspec/specs` and archived, and this run's own brief. `openspec/changes/` holds nothing active,
so any change this run creates is its own.

**The round discipline is the point of this run.** The operator restated it twice this morning —
once as a requirement (*"If any spec is needed and explore follow the same pattern explore/propose
-> review -> review"*) and once as a reminder mid-preparation (*"Dont forget the explain/propose
review review pattern"*) — and asked for it to be recorded as a standing pattern, saying *"Take not
of this pattern I liked a lot."* It is `method_reminders[0]` and `limits[0]` in `STATE.json`, and
every change in the queue is expanded into its rounds rather than left as one item. **Never drop a
round to save time. Drop the last item in the queue instead.**

**Three decisions taken with the operator awake:**

1. **F58 goes all the way through implementation.** The operator was told plainly that this is the
   one item that can damage a repository — approving one task merged 13 files and 16 commits,
   including another task's unreviewed test — and was offered a stop-at-reviewed-proposal option.
   They chose full implementation. *Rejected:* stopping after the two review rounds for sign-off.
   The condition of that choice is the blast-radius limit written into `F58-IMPL` and repeated in
   `limits`: exercise it only against a throwaway project or an existing drive project, never
   against `proj-5e960453` (this repository) or `proj-18e5d4e0` (ledger-stress, which carries state
   other findings depend on), and stop rather than rewrite history in a repository this run did not
   create.
2. **Order: F58, Q4, Q5, approval-authority, Q8, then e2e.** The operator was told ~7.5 hours fits
   two or three changes and not five, and chose this order knowing it will not finish. *Rejected:*
   starting with the two already-scoped changes (Q4/Q5) to bank completed work early.
3. **Opus for everything.** *Rejected:* Sonnet-5, which is what ran last night and did well; and a
   split of Sonnet for implementation with Opus for the review rounds, which was rejected for adding
   a per-item model switch the driver would have to get right unattended.

**Two stalls found and removed during preparation, both of which would have cost the run:**

- **`parent_sha` cannot name its own commit.** The brief has to be committed before it has a SHA, so
  pinning `parent_sha` to the commit carrying the brief chases its own tail one commit at a time.
  Left as it was, the loop would have cut its branch from a tree holding *last night's* queue and
  worked the wrong list, silently. Resolved by branching from `origin/master` with `parent_sha` as a
  floor, plus a self-check naming what a correctly-cut `STATE.json` looks like — 22 items, `current:
  F58-EXPLORE`.
- **The driver refuses to run unless the branch already exists.** `run-iteration.ps1` stops with
  *"Current branch does not match STATE.json branch"* when they differ. The brief originally told
  the loop to cut its own branch on the first iteration, which would have deadlocked **every**
  firing — the loop could never reach the instruction telling it to fix the condition preventing it
  from running. So the branch is cut here, in the attended session, before the driver is installed.

**What is not verified.** The trial Hub on 8010 is up and answers `{"status":"ok"}`, but it is
running code from before this morning's work (`hub_started_on_sha` is `7219090`, now a distant
ancestor). Any item that drives it live must restart it first with `environment.restart_hub` and
confirm the **project list**, not `/health` — a Hub on a stale database still answers `ok`.

**Queue:** 22 items. `F58-EXPLORE` → `F58-R1/R2/R3/IMPL` → `Q4` ×4 → `Q5` ×4 → `QA` ×4 → `Q8` ×4 →
`QE2E`. The last is the operator's explicit fallback — *"If it finishes way earlier do another
e2e-loop with fixes"* — and is gated on every item above it being closed.

**Expect this queue to be unfinished at 17:00.** It is ordered so that stopping anywhere leaves
complete changes rather than a row of half-written proposals. `decisions_for_user` opens with the
pre-authorisation that says so, so no iteration needs to ask.
