# Autonomous run — project portability, 2026-08-19/20

**Branch:** `autonomous/2026-08-19-project-portability`
**Parent:** `master` at `afb63f5`
**Window:** 2026-08-19T23:26+01:00 → 2026-08-20T08:00+01:00
**Driver:** Windows Scheduled Task → headless `claude -p`. Session-bound drivers are not used; the
2026-08-15 post-mortem is why.

Newest entry at the bottom.

## Limits in force

Quoted from `STATE.json`, which is authoritative:

1. **Do not restart, stop, or reconfigure the Hubs on ports 8000 (PID 28492) or 8010 (PID 26700).**
   The operator is using both. This is the single most damaging thing this run could do.
2. Do not touch `hub/data/agentweave.db`, `~/.agentweave/hub/`, or `~/.agentweave/hub/.env`.
3. Repo source and openspec only.
4. Do not delete `.agentweave/` or `spec/` at the repository root — they are the migration's.
   `.agentweave/project.json` reads `proj-4190ae17`; the backup beside it holds `proj-5e960453`.
5. Stay on this branch. No merges to master, nothing outward-facing beyond pushing this branch and
   one draft PR so CI runs, nothing destructive.
6. Never mark work complete on the strength of a plan existing.
7. Every claim measured, or labelled unverified.

## Entry 0 — setup (2026-08-19T23:26+01:00, interactive)

Written by the interactive session that prepared the run, before handing to the driver.

**How this run came about.** It began as a support call, not a plan. The operator could not add
this repository to their own Hub — the Add-project dialog returned a raw JSON blob ending in
`project_identity_conflict`. Diagnosis found three separate defects, and the operator chose the
queue from them plus carried debt in handoff 0060.

**What was already done interactively, on `master`, before this branch existed:**

- `75c7685` — the Add-project dialog now renders the Hub's sentence via `readableApiError` instead
  of the whole response body, and offers the `register_copy_as_new` remedy the refusal names. New
  `apiErrorCode` helper matches on the code, never the prose. UI bundle rebuilt via
  `scripts/refresh_ui_bundle.py` and committed alongside the source, per CLAUDE.md.
- `afb63f5` — the prepared brief (`STATE.json`), and the prior run's state archived beside it.

**The operator's environment, as found — recorded because two of the six queue items are about it.**
Two Hubs are running: port 8010 (PID 26700) serving `<repo>/hub/data/agentweave.db`, and port 8000
(PID 28492, the desktop shortcut) serving `~/.agentweave/hub/data/agentweave.db`. The repo's marker
named `proj-5e960453`, which exists only in the 8010 database, so the 8000 Hub refused it. The repo
was re-registered on 8000 as `proj-4190ae17` with the operator's explicit approval, after the cost
was stated: it orphans the trial Hub's binding. The previous marker is backed up in place.

**Runway verified at prep, not assumed:** working tree clean; vitest 1152 passed across 115 files;
`tsc --noEmit` clean; `pytest tests/test_project_lifecycle.py tests/test_project_persistence.py`
17 passed; playwright present; no openspec changes in flight.

**Not run at prep, and therefore not a baseline this run may lean on:** the full `hub/tests/` suite,
`ruff`, `black`, and `eslint`. The first iteration that touches Python or lint should establish
these itself, so inherited breakage is never mistaken for its own.

**What a reviewer should distrust in this entry.** Everything above about the two Hubs was measured
tonight (process list, both SQLite files read directly, live API calls). The claim that item P1 is a
real defect was traced by reading the render path end to end and is *not* yet reproduced in a
browser — the first iteration owes a failing test before a fix.
