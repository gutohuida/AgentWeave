# CLAUDE.md's "trial Hub" section is stale — a proposed correction

Not an exploration of an idea; a factual correction proposal, held here rather than applied to
CLAUDE.md directly, per `decisions_for_user.N3` in this branch's `STATE.json` ("propose a
corrected CLAUDE.md section as a diff on the branch, but NOT rewrite the file's governing prose
unilaterally -- CLAUDE.md is the operator's instrument"). Nothing in this file changes CLAUDE.md.

## What CLAUDE.md says today

````
### The trial Hub — fixed 2026-08-16

| | |
|---|---|
| **Port** | `8010` |
| **Database** | `~/.agentweave/hub/profiles/beta/agentweave.db` |
| **PID file** | `~/.agentweave/hub/hub-8010.pid` (per-port; the default instance keeps `hub.pid`) |
| **This repo registered as** | `proj-5e960453`, working directory the repo root |

Start it — **from `hub/`, not the repo root** (see the trap below):

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///$HOME/.agentweave/hub/profiles/beta/agentweave.db" agentweave --port 8010
```
````

## What is actually true, verified live at 2026-08-18T07:30+01:00

- `GET http://127.0.0.1:8010/health` returns `{"status":"ok"}`.
- `GET http://127.0.0.1:8010/api/v1/projects` (Bearer `hub/.env`'s `AW_BOOTSTRAP_API_KEY`) returns
  three projects: `proj-5e960453` (AgentWeave, this repo), `proj-b44fac0c` (Throwaway (taste
  pass), `testbed/throwaway-taste-project`), `proj-ff695d96` (aw-loop10,
  `C:\Users\huida\Documents\aw-loop10`).
- The database actually serving port 8010 is **`<repo>/hub/data/agentweave.db`**, not
  `~/.agentweave/hub/profiles/beta/agentweave.db`. This is the fix this run's own Q1 made
  (`.claude/autonomous/2026-08-18-the-app-feels-alive-log.md`, iteration 1): the `beta` profile
  copy was stale (last touched 2026-08-17T02:41, still shows the notify-window document as
  `approved` where every other copy says `archived`) and nothing has served it since.
- `~/.agentweave/hub/hub-8010.pid` (content `12296`) is itself stale -- that process is not
  running. The port is actually held by `~/.agentweave/hub/hub-trial-8010.pid` (content `23540`),
  a file CLAUDE.md's table does not mention. The PID has changed at least twice since Q1's
  original 27792 launch, consistent with at least one restart during this run's later iterations
  (Q6's done_note records restarting 8010 to verify the console-flash fix).
- `~/.agentweave/hub/profiles/trial/` is a fourth, separate database that CLAUDE.md never
  mentions at all. It held only `proj-ff695d96` before Q1 and was the actual problem Q1 diagnosed
  (the taste-pass fixtures existed only in the unserved `hub/data/agentweave.db`, not in whatever
  8010 was serving that night).

In short: four databases exist (`hub/data/agentweave.db`, `profiles/beta`, `profiles/trial`,
`profiles/dev` -- the last untouched by this run and not investigated here), CLAUDE.md names one
of them, and it is not the one actually live.

## Proposed replacement text

````
### The trial Hub — fixed 2026-08-16, database corrected 2026-08-18

| | |
|---|---|
| **Port** | `8010` |
| **Database** | `<repo>/hub/data/agentweave.db` (holds this repo's live trial fixtures) |
| **PID file** | `~/.agentweave/hub/hub-trial-8010.pid` (per-launch-script; `hub-8010.pid` and
  `hub.pid` are from other launches and may be stale -- check `Get-Process -Id <pid>` before
  trusting any of them) |
| **This repo registered as** | `proj-5e960453`, working directory the repo root |

Other databases under `~/.agentweave/hub/profiles/` (`beta`, `trial`, `dev`) are earlier or
divergent copies, not the live one. Confirm which database a running instance actually serves
with `GET /api/v1/projects` before trusting any doc, this one included -- these paths have moved
before and will again.

Start it — **from `hub/`, not the repo root** (see the trap below):

```bash
cd hub
DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/agentweave.db" agentweave --port 8010
```
````

## Why this is worth fixing

This run's own `decisions_for_user.N3` already flagged the drift; `known_debts` in this branch's
`STATE.json` records the same divergence being hit and worked around live during Q1. Left
uncorrected, the next session (interactive or autonomous) reads CLAUDE.md, points `DATABASE_URL`
at `profiles/beta`, and loses the same afternoon this run spent finding the right one -- the
`hub_start_detached` / `databases` block this run added to its own `STATE.json.environment` is a
workaround for exactly this gap, not a fix for it.

## What this file does not do

- It does not edit CLAUDE.md. That stays the operator's call, per N3's own default.
- It does not investigate `profiles/dev` — out of scope for what N3 asked for.
- It does not decide whether the *product* should collapse these four databases into one
  discoverable location (that would be a real change, not a doc fix) -- purely a documentation
  correction proposal.
