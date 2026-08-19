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

## Iteration 1 — P1, agent creation scoped to the clicked project (2026-08-19T23:31+01:00)

**Done, verified, committed.**

**What was wrong.** `App.tsx` derives `selectedProjectId` from the current destination (the effect
at lines 118-123). Every rail action that opens a project-scoped surface therefore navigates first
— `onOpenProject`, `onOpenEnvironment`, `onOpenAgentSettings`, `onOpenSpecDocument`, all of them.
`onAddAgent` was the single exception: it called `setAgentCreateProjectId(id)` and nothing else. The
dialog it opened reads `useCreateAgent`, `useCharters` and `useProviderLaunchability`, and all three
resolve the *selected* project — so the agent was created wherever the operator happened to be
standing, and they were then navigated to the project they had clicked, to an agent that was not in
it. The operator hit this for real with a `Spec` agent and read the resulting 409 as a global
name collision; it was a true "already exists in this project" message about the wrong project.

**The fix** is one line plus its reasoning: `onAddAgent` now calls
`navigateTo(projectDestination(id))` before opening the dialog — the identical expression
`onOpenProject` already uses at line 454, not a second ad-hoc path. This is what the operator chose
when asked: create in the clicked project *and* switch to it.

**Why the existing tests never caught it.** `agentCreationUi.test.tsx` mocks `useCreateAgent`
wholesale, so it cannot observe which project a request would address. It passed for the entire
life of the bug and still passes. The defect was in the wiring, so the new test is at the wiring
level: `src/__tests__/agentCreateProjectScope.test.tsx` mounts the real `App` over a two-project
rail and asserts the clicked project becomes the scoped one.

**Mutation-checked, not merely green.** With the fix reverted, exactly one test failed by name —
`selects the clicked project, so the dialog addresses it and not the selected one` — while the
other two continued to pass, which is the correct signature: the dialog still opens, and clicking
the already-selected project was never broken. Fix restored and re-run before committing.

**Measured:** `tsc --noEmit` clean; vitest **1155 passed / 116 files** (1152 before, +3 new);
`eslint src --max-warnings=0` clean; bundle rebuilt and refreshed through
`scripts/refresh_ui_bundle.py`, committed with the source as CLAUDE.md requires.

**Not done, deliberately.** The defence-in-depth option in the brief — threading an explicit
`projectId` prop into the dialog and its three hooks — was **not** taken. Navigation makes the
selection correct before the operator can submit, and the behaviour is now covered. Threading a
fourth copy of the project id through four call sites is exactly the kind of duplication that
drifts. Recorded here so the choice is visible rather than looking like an oversight.

**What a reviewer should distrust.** This was verified in jsdom, not in a browser against a live
Hub. The assertion is on `selectedProjectId`, which is one step short of asserting the POST URL —
justified because all three hooks derive the URL from exactly that value, but it is an inference,
not a captured request. A browser check against a real Hub is still owed, and is blocked tonight by
the no-restart limit.

**Driver verified live.** The scheduled task fired at 23:28:03 and stood down with
`Heartbeat is 1.7 min old (grace 25) - a live session holds the branch`. The interlock works; the
2026-08-15 failure mode (a session-bound scheduler dying with the session) does not apply here.
