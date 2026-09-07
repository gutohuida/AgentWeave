# Sidequest run — 2026-09-07

Two spec loops the operator asked for, run **apart from** the daily FILL/DECIDE/FIX cycle.

## Iteration 0 — set up by the interactive session, 2026-09-07 afternoon

Not an agent iteration. This entry exists so the first firing has context.

### Why this run is separate from the daily cycle

The operator asked for two spec loops on subjects unrelated to the cycle's queue, and asked that
they run now rather than waiting for tomorrow's FILL window: *"You can schedule those loops as
something apart to run now. They don't need to fall inside the normal scheduler for agentweave
work."*

The daily cycle owns the main checkout at `C:\Users\huida\Documents\projects\AgentWeave` on
`autonomous/2026-09-07-daily`. `AgentWeaveArmNight` fires at **22:55 tonight** and arms the FIX
window onto whatever branch that checkout is on, and `arm-cycle.ps1` refuses to arm onto a dirty
tree. A second unattended process in the same working tree would therefore either steal the branch
or poison the arming. So this run lives in a **separate git worktree** on its own branch, with its
own state file, its own driver log and its own scheduled task. The two cannot see each other.

| | daily cycle | this run |
|---|---|---|
| checkout | `…\AgentWeave` | `…\AgentWeave-sidequest` |
| branch | `autonomous/2026-09-07-daily` | `autonomous/2026-09-07-sidequest` |
| state | `STATE-day.json` / `STATE-night.json` | `STATE-sidequest.json` |
| task | `AgentWeaveArmDay` / `AgentWeaveArmNight` | `AgentWeaveSidequest` |
| driver log | `driver.log` | `driver-sidequest.log` |

Branched from `8ee61b1`, the cycle branch's head at the time.

### What the two subjects are

1. **AgentWeave where MCP is blocked and Copilot is the house CLI.** The operator's own company
   constraint. Seed: `openspec/explorations/2026-09-07-agentweave-without-mcp-and-with-copilot.md`.
2. **What is actually separable from this repo**, with a folder per surviving candidate in the
   parent directory and a spec loop inside each. Seed:
   `openspec/explorations/2026-09-07-what-is-actually-separable.md`.

Both seeds were written from surveys that read the code on 2026-09-07. **Both contain a claim that
was spot-checked and found FALSE, left in and labelled**, so no round treats a seed as settled.

### The headline finding from the setup, before any round has run

The 2026-09-06 exploration this run was asked to validate is **wrong on seven claims**, including
both halves of its central recommendation. Most importantly: it recommended extracting the two
mechanisms with the *least* production evidence and recommended against the one with the *most*,
and the reason it gave for declining that one was a market argument, not a separability argument —
which is not the question the operator asked. Detail in the second seed's Part 1.

### Found while surveying, unrelated to either subject and already fixed

`scripts/drive/aw.py:15` carried a live `aw_live_` Hub key as a hardcoded default in a **tracked**
file, in a repository `gh repo view` reports **PUBLIC**. Default removed on the cycle branch at
`2d4131b`. Removal does not unpublish it — the value is in git history and must be treated as
disclosed. Rotation is the operator's call and is the first row in `decisions_for_user`.

### Next

`next_action` is `S-1`. Read `STATE-sidequest.json` for the queue and the limits, then do exactly
that one item.
