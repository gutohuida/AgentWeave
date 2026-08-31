# `.claude/loops/` — the daily loop's playbooks

Operational documents read by headless processes that have no memory of anything. They are **not**
skills: a skill is loaded into every session's context whether or not it is wanted, and these are
needed by two scheduled windows and nobody else.

Design and the decisions behind it:
`openspec/explorations/2026-09-01-a-daily-research-spec-and-build-loop.md`.
Contract for the files the windows exchange: `spec-queue/README.md`.

## The three tasks

| Task | When | Mode | Process | Playbook |
|---|---|---|---|---|
| `AgentWeaveResearch` | 08:30 daily | **`auto`** | one-shot `claude -p` | `~/.claude/routines/agentweave-research/prompt.md` |
| `AgentWeaveDayLoop` | 09:00-17:00 | `bypassPermissions` | iterated driver | `day-window.md` |
| `AgentWeaveNightLoop` | 23:00-07:00 | `bypassPermissions` | iterated driver | `night-window.md` |

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

**Never auto-merge.** Merging is the operator's decision, made awake. That is unchanged.
