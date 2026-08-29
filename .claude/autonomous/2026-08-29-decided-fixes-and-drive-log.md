# Autonomous run — 2026-08-29, decided fixes and a drive

**Branch:** `autonomous/2026-08-29-decided-fixes-and-drive` from `master` at `b2d565e`
**Runner:** `claude` (Opus 5) · **Posture:** `unattended-full-access`
**Armed:** 2026-08-29 ~12:35 local · **Stop at:** 2026-08-29 20:00 local
**Brief:** `.claude/autonomous/STATE.json` · **Findings:** `scripts/drive/FINDINGS.md`

Newest entry at the **bottom**.

---

## Iteration 0 — arming (interactive session, operator present then departing)

The operator's words: *"Schedule a autonomous run to fix those issues and then drive a e2e loop and
fix issues that you can. Run untill 20:00. After scheduling run a handoff in this session."*

### What "those issues" are, and why none of them needs a decision

Four findings, every one with the operator's own decision already behind it. The brief quotes each
decision at the queue item so the run implements rather than re-litigates:

| | Decision, in the operator's words |
|---|---|
| **F116** | New this session. Fix shape is the one the finding names; pre-authorised as D1. |
| **F111 + F3** | *"No it does not belong in the product."* Self-registration is removed, not reworded. |
| **F113** | *"Clean."* — `blocking` gets the closure finding; the additive alternative is rejected and recorded as rejected. |
| **F115** | *"Worktree is a cwd — fix the honesty."* Native mode does **not** confine writes. |

F115's decision was taken with `AskUserQuestion` in the last minute before the operator left,
specifically because it was the one thing that would have stalled the run.

### Limits set for this run

Beyond the standing directives (all quoted in `STATE.json.limits`), two matter most:

1. **Do not merge to master.** This session merged 34 commits to master today with the operator
   present and CI green on all nine cells. An unattended run pushes its branch and stops there.
2. **The 17:00 rule.** The operator asked for the fixes *and* a drive. If the queue has not reached
   `E2E-DRIVE` by 17:00 local, park the spec loop in flight at a clean boundary — a completed round,
   committed — and start the drive anyway. Reaching the drive is part of the ask.

### What was prepared so the run would not have to

- **The four findings are written up in full** in `FINDINGS.md`, each with its live reproduction:
  F115 has four run rows and the sqlite query that proves all four recorded the same
  `workspace_dir`; F116 has both request shapes and both responses; F113 has the three-call
  reproduction; F111 has the search that proves no shipped client calls the route.
- **A working drive harness exists** — `scripts/drive/t_row13_row14.py`, written and run this
  session, with the two traps documented in-file (the question schema has no `status` string, and
  permission posture travels in `overrides`). The run reuses it rather than rediscovering them.
- **Green-at-arming is CI, not a local run.** Run `33247142872` at `c994af5` passed all nine cells
  including both 3.12 legs, which cannot be reproduced on this machine. Everything committed since
  touches only `scripts/drive/*.md` and two new drive scripts no test imports.
- **The F109 flake is named in `known_flakes`** with its three affected tests, so a red cell there
  is re-run rather than misattributed — and with an explicit *do not re-propose the fix*, because
  the operator declined it today.

### Four pre-authorised defaults

So the run does not park on a question at 3pm: D1 (proceed with forbidding extras), D2 (drop the
`contact_mode` column only if nothing live reads it), D3 (**not** pre-authorised as a design — if
no honest detection point fires in *default* posture, ship F115's other three parts and write part
2 up as its own finding, because a detector that misses the case the finding is about reads as
coverage), D4 (the stray root files are gone; nothing to do).

### Driver

Windows Scheduled Task, not `ScheduleWakeup` and not `CronCreate` — both die with the interactive
session, measured 2026-08-15 when a nine-hour run got forty minutes. Each firing is a fresh
`claude -p` process that reads `STATE.json`, does one iteration, commits, pushes, exits.

### What a reviewer should distrust in this entry

Nothing was implemented at arming. The claim that the four decisions are settled rests on this
session's transcript, and the F115 decision in particular was taken in one question with the
operator on their way out — if the implementation surfaces a consequence the question did not
cover, that is the place to look first.
