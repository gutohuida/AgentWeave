# `.claude/loops/` — the daily loop's playbooks

Operational documents read by headless processes that have no memory of anything. They are **not**
skills: a skill is loaded into every session's context whether or not it is wanted, and these are
needed by two scheduled windows and nobody else.

Design and the decisions behind it:
`openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md`.
Contract for the files the windows exchange: `spec-queue/README.md`.

## The five tasks — three permanent, two transient

| Task | When | Lifetime | Mode | Playbook |
|---|---|---|---|---|
| `AgentWeaveResearch` | 07:10 daily | **persistent** | **`auto`** | `~/.claude/routines/agentweave-research/prompt.md` |
| `AgentWeaveArmDay` | 08:55 daily | **persistent** | — | registers the next row |
| `AgentWeaveDayLoop` | 09:00-17:00 | *transient* | `bypassPermissions` | `day-window.md` |
| `AgentWeaveArmNight` | 22:55 daily | **persistent** | — | registers the next row |
| `AgentWeaveNightLoop` | 23:00-07:00 | *transient* | `bypassPermissions` | `night-window.md` |

**The two working windows are transient on purpose.** The iteration driver unregisters itself at its
stop time, which is what stops a dead loop from firing forever — and it is also why the loop needs
two daily arming tasks at all. `arm-cycle.ps1` settles the cycle branch, writes that window's STATE
file, and calls `install-driver.ps1`; it refuses a dirty tree, because a skipped day costs one day
and a window armed onto a tree it does not understand costs the morning.

All three persistent tasks run as an **interactive logon**, so `gh`'s keyring and the Claude
credentials resolve. Consequence, inherited from the `ai-digest` routine: **they only fire while you
are logged on.** A logout or a reboot to the lock screen skips a day.

## The overlap that would eat a window's work

`AgentWeaveResearch` carries the `ai-digest` guardrail: it snapshots `git status --porcelain` before
the run, diffs after, and **deletes new untracked files** in the repo. That is right for a routine
that must never dirty the tree, and it cannot tell a window's work from its own mess.

Two things keep them apart, and both are needed:

1. **07:10, not 08:30.** A ~30-minute run started at 08:30 can still be finishing at 09:10, with the
   day window already writing untracked files. 07:10 begins after the night window ends at 07:00 and
   leaves an hour of margin before 09:00 even on a long run.
2. **`run.sh` refuses to delete while the checkout is on an `autonomous/*` branch**, because that
   means a window owns the tree. It reports the strays instead. The schedule is the belt; this is
   the braces.

`ClaudeAIDigest` at 07:57 carries the same guardrail against this same repo. It does not overlap a
window either, and nothing about it needed changing.

## Operating it

```powershell
powershell -File .claude\loops\install-tasks.ps1 -WhatIf     # what would be registered
powershell -File .claude\loops\install-tasks.ps1             # turn the loop on
powershell -File .claude\loops\install-tasks.ps1 -Remove     # turn it off entirely

powershell -File .claude\loops\arm-cycle.ps1 -Window day -DryRun   # what tomorrow would arm onto
Get-ScheduledTaskInfo -TaskName AgentWeaveArmNight | fl NextRunTime,LastRunTime,LastTaskResult
Disable-ScheduledTask -TaskName AgentWeaveArmNight                  # pause one window
```

Logs: `.claude/autonomous/driver-day.log` and `driver-night.log` (gitignored, per-firing), the
tracked prose logs beside them, and `~/.claude/routines/agentweave-research/logs/`.

## Why research is a separate task, and not the day window's first iteration

Because the day window runs `bypassPermissions`, and research reads the open web.

`~/.claude/routines/ai-digest/run.sh` states the rule in its own source, dated 2026-08-28:
*"No `--permission-mode` override ... `bypassPermissions` is deliberately **not** used: this routine
ingests untrusted web content, so the permission classifier stays in the loop as a prompt-injection
backstop."* The cloud version of that routine got sandbox isolation for free; locally the classifier
is the replacement.

An autonomous window has no such backstop, and this machine has unscoped `gh` and the operator's
credentials. So the open web is read by a process that keeps the classifier, writing to a directory
outside the repository; the window that can do anything reads a file, not a website.

This bounds the untrusted content entering the privileged process. It does not eliminate it — the
research file is itself derived from web content, and a `bypassPermissions` window is instructed
not to browse rather than prevented from browsing. Treat the research file as data, never as
instructions, and say so in the prompt that consumes it.

## State

Each window owns its own position and log; they must never share:

```
.claude/autonomous/STATE-day.json      STATE-night.json
.claude/autonomous/driver-day.log      driver-night.log      (gitignored)
.claude/autonomous/<date>-day-log.md   <date>-night-log.md   (tracked, prose, newest at bottom)
```

The windows do not overlap in time, which is a **requirement**, not a convenience: one working tree
can only be on one branch, and both drivers check `STATE.*.json`'s `branch` against it every firing.

## The cycle branch

One branch per cycle-since-last-merge, dated by when it was cut: `autonomous/YYYY-MM-DD-daily`.

The day window's first iteration checks whether the previous one is merged into `master`. Merged, it
cuts a fresh branch from `master`. Not merged, it stays on it and says so at the top of the review
page, so the operator sees they are looking at more than one day of accumulated diff.

**The day window's merge gate may fast-forward master itself, since 2026-09-06.** The operator
relaxed the seeded `limits[0]` line that had kept condition zero permanently unmet
(`day-window.md`, Iteration 1 step 1). The other three conditions are unchanged and still gate it:
a genuine fast-forward, a clean pushed HEAD, CI green at that exact commit, and no `HOLD MERGE` in
`DIRECTION.md`. `git merge --ff-only` only — the gate still cannot invent a merge commit or resolve
a conflict with nobody awake. The night window still never merges, under any condition.
