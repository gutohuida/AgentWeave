# Handoff: project portability shipped, and this repo's original identity restored

**Date:** 2026-08-20T08:45:47+01:00 · **Branch:** `master` · **HEAD:** `158c917`
*(Written on `autonomous/2026-08-19-project-portability` at `770a51d`, then cherry-picked onto
`master` so the chain stays where the next session will look for it.)*
**Agent:** Claude Opus 5 (1M context) (Claude Code, interactive + an unattended overnight driver)
**Previous handoff:** `.claude/handoffs/handoff-0060-2026-08-19-2255-loop-traceability-shipped-and-v1-1-0-published.md`
**Status:** chunk complete. PR #7 **merged** to master as `13dd6e0`. This handoff sits on `master`. Working tree clean, nothing
unpushed, no openspec changes in flight.

## Goal

The session began as a support call, not a plan: the operator could not add this repository to
their own Hub. The Add-project dialog returned a raw JSON blob ending in
`project_identity_conflict`. Diagnosis found **three** separate defects, and the operator named the
theme that tied them together, verbatim: *"I should be able to open any agentweave project from any
agentweave app that I want."*

The *why* matters for judgement calls later: a project's identity is supposed to live with the
**folder**, not with whichever database happened to see it first. Every defect below is a place
where that principle had leaked.

## Current state

**Everything is shipped and merged.** `origin/master` is at `13dd6e0`. Seven queue items closed
(P1–P7; P7 was found by the loop itself). 25 files, **+1,219 / −373** excluding the committed UI
bundle and the run's own logs.

**You are on `master`, and it is current.** It was two commits behind during the session; that was
resolved at the end, when this handoff was cherry-picked onto it. The work branch
`autonomous/2026-08-19-project-portability` is merged and can be deleted whenever you like.

**The merge was a real merge commit, not a squash** (`parents: a3439c4 770a51d`), despite the plan
being to squash. Consequence: master's history now contains all 58 branch commits, including **19
"Idle checkpoint" and 26 "Release the branch to the driver"** bookkeeping commits. Nothing is
broken by this; it is only noise in `git log`. Recorded so nobody later mistakes it for corruption.

**What shipped:**

1. **P1 — agent creation went to the wrong project.** `App.tsx` derives `selectedProjectId` from
   the current destination, so every rail action that opens a project-scoped surface navigates
   first. `onAddAgent` was the only one that did not. The dialog reads `useCreateAgent`,
   `useCharters` and `useProviderLaunchability`, all of which resolve the *selected* project — so
   the agent was created wherever the operator was standing, and they were then navigated to the
   project they had clicked, to an agent that was not in it. This is what the operator hit with a
   `Spec` agent; they read the 409 as agent names being global. They are not — it was a truthful
   "already exists in this project" about the **wrong** project.
2. **P2 — the headline.** `open_existing` now **adopts** an orphaned marker instead of refusing it.
   A folder whose marker names a project the current database has never seen gets a row created
   **under that same id**, seeded with runners and charters, and opened. Shipped as openspec change
   `2026-08-20-portable-project-identity`, since archived.
3. **P3** — tests for the previous evening's `apiErrorCode` helper and the `register_copy_as_new`
   affordance.
4. **P4 — better than briefed.** Instead of patching serialisation call sites, a `UTCDateTime`
   `TypeDecorator` in `hub/hub/db/models.py` relabels SQLite's naive datetimes as UTC once at the
   DB boundary, replacing three ad-hoc fix-ups (`agent_status.py`, `api/v1/agents.py`,
   `scheduler.py`) and every `.isoformat()` downstream.
5. **P5 — the loop refused to tick the item as written, correctly.** It reports that D15's literal
   scenario (recreate an archived agent's name) **does not reproduce** — the unique index already
   blocks it — and fixed the real gap one layer down: `_authorize_loop_task_creation` compared
   agent names as bare strings without consulting the agents table, so a run minted under an
   archived name kept that name's loop authority. It also stopped archived agents being triggered
   at all.
6. **P6/P7** — the browser suite's two hard-coded fixture identities (`proj-5e960453`,
   `proj-b44fac0c`) are now threaded through every call site, so the suite is no longer pinned to
   one machine.
7. **The adoption event** (added this morning, after the run). The loop recorded adoption with
   `logger.info`, which reaches whoever reads server output and nobody else. There is now a
   `project_adopted` `EventLog` row alongside it.

**Live state of the operator's machine — changed this morning, and none of it is in git:**

- The **port 8000 Hub was restarted** and now runs the merged code. It is detached via
  `Win32_Process.Create` (parent gone), started from a new wrapper
  `C:\Users\huida\.agentweave\hub\start-hub-8000.bat`. Log: `%TEMP%\agentweave-hub-8000.log`.
- **`proj-4190ae17` was deleted** and this repo is back to **`proj-5e960453`** on the 8000 Hub,
  restored via the adoption path — the first live exercise of P2.
- `~/.agentweave/hub/.env` had `AW_BOOTSTRAP_PROJECT_ID` and `AW_BOOTSTRAP_PROJECT_NAME` removed.
  Backup: `~/.agentweave/hub/.env.backup-2026-08-20`. **The existing "Default Project" row still
  exists and still needs deleting in the UI** — removing the variable only stops it being
  re-seeded.
- The port **8010 Hub was never touched** and is still healthy.

## Files touched

Everything below is **committed and merged**; the working tree is clean.

**Hub (Python):**

- `hub/hub/project_lifecycle.py` — case 3 of `open_existing` adopts the marker's project id,
  seeds the project, logs, and writes a `project_adopted` event. Imports `persist_event`. **Finished.**
- `hub/hub/db/models.py` — new `UTCDateTime` `TypeDecorator`; every `DateTime(timezone=True)`
  column converted to it. **Finished.**
- `hub/hub/api/v1/tasks.py` — part of the P4 timestamp sweep. **Finished.**
- `hub/hub/api/v1/agent_trigger.py` — P5; archived agents can no longer be triggered into a new
  running `Run`. **Finished.**

**The complete list of Hub Python files changed by the merge is exactly those four**
(`git diff --name-only afb63f5..13dd6e0 -- hub/hub/ | grep -v static/ui`). Verified, not recalled.

**Hub (tests):**

- `hub/tests/test_project_lifecycle.py` — three new tests: adoption under the original id,
  delete-then-reopen restoring the same id, and `test_adoption_leaves_a_trace_the_operator_can_find`.
  The pre-existing `test_copied_marker_conflicts_until_explicitly_registered_as_new` is
  **untouched, zero deleted lines** — it is the proof the copy guard survived. **Finished.**
- `hub/tests/test_timestamp_serialization.py` — **new**, P4. **Finished.**
- `hub/tests/test_agent_trigger.py`, `hub/tests/test_tasks.py` — P4/P5 coverage. **Finished.**
- `hub/tests/browser/conftest.py`, `test_files_tab.py`, `test_human_only_halves.py`,
  `test_loops_index.py`, `test_panel_shell.py` — fixture identities parameterised (P6/P7).
  **Finished but NOT RUN — see Verification.**

**Hub UI:**

- `hub/ui/src/App.tsx` — `onAddAgent` now calls `navigateTo(projectDestination(id))` before opening
  the dialog. **Finished.**
- `hub/ui/src/api/client.ts` — `apiErrorCode` helper alongside `readableApiError`. **Finished.**
- `hub/ui/src/components/projects/ProjectManagerModal.tsx` — uses `readableApiError`; offers a
  `register_copy_as_new` button on `project_identity_conflict`. **Finished.**
- `hub/ui/src/lib/hubTime.ts` — client-side compensation retired where `UTCDateTime` made it
  redundant. **Finished.**
- `hub/ui/src/__tests__/agentCreateProjectScope.test.tsx` — **new**, mounts real `App` over a
  two-project rail. `apiErrorCode.test.ts`, `projectManagerIdentityConflict.test.tsx` — **new**.
  `hubTime.test.ts` — updated. **Finished.**
- `hub/hub/static/ui/` — committed bundle, refreshed via `scripts/refresh_ui_bundle.py`. **Finished.**

**openspec:**

- `openspec/changes/archive/2026-08-20-portable-project-identity/` — proposal, design, tasks, spec
  delta. Archived.
- `openspec/specs/local-project-workspace/spec.md` — delta synced.

**Run bookkeeping (not product code):**

- `.claude/autonomous/STATE.json`, `.claude/autonomous/2026-08-19-project-portability-log.md`,
  `.claude/autonomous/STATE-2026-08-18-run2-final.json`.

## Key decisions

1. **Adopt an orphaned marker rather than refuse it.** *Rejected:* keeping the refusal and relying
   on `register_copy_as_new`. *Reason for rejecting:* at case 3 the Hub knows no project in this
   database is bound to the path **and** none holds the marker's id — nothing collides. The only
   thing the refusal protected against was a copy whose original lives in a database this Hub
   cannot see and has no authority over. Real copy detection lives in `_guard_relocation` (case 2)
   and is untouched.
2. **Keep the `register_copy_as_new` affordance** after adoption shipped. *Reason:* a genuine copy
   whose original is still registered here still hits `_guard_relocation`, and that operator still
   needs the remedy.
3. **P1: create in the clicked project AND switch selection to it.** *Rejected:* leaving selection
   alone and threading an explicit `projectId` prop into the dialog and its three hooks. *Reason:*
   a fourth copy of the project id through four call sites is exactly what drifts — and the drift
   is how this bug happened. Navigation makes selection correct before the operator can submit.
   The defence-in-depth prop threading was **deliberately not done**.
4. **P5: strip inherited privilege on name reuse.** *Rejected:* blocking reuse of archived names.
   *Reason:* the operator archives and recreates under the same name; a permanent name reservation
   would be worse than the hole.
5. **P6: unpin the browser suite rather than run it.** *Reason:* running it would seed fixtures into
   the operator's live trial Hub, and testing the night's UI changes would have needed a bundle
   rebuild and a Hub restart — both forbidden overnight.
6. **Adoption is silent, but writes an event.** *Rejected:* an interstitial asking the operator to
   confirm. *Reason:* they asked to open a folder; it opened. The event makes it findable afterwards.
7. **`start-hub-8000.bat` sets `DATABASE_URL` explicitly.** *Reason:* `hub.config` reads
   `env_file=".env"` relative to the **process working directory**, so the Hub silently lands on a
   different database if started from elsewhere.

## Constraints and user directives (verbatim)

- *"I should be able to open any agentweave project from any agentweave app that I want"*
- *"we can get rid of default project, agentweave should come clean"*
- *"I think I clicked to create an agent in one project but it was actually creating into another
  project. Something weird there. If you cannot reproduce leave it aside and I'll hit that
  eventually again"*
- *"Do those steps for me. Restart the hub."*
- Overnight limits, still worth honouring by default: **do not restart, stop, or reconfigure the
  Hub on port 8010**; do not touch `hub/data/agentweave.db`; do not delete `.agentweave/` or
  `spec/` at the repository root.
- Standing, from `CLAUDE.md`: never mark a task complete on the strength of a plan existing; commit
  `hub/ui/src` and `hub/hub/static/ui` together via `scripts/refresh_ui_bundle.py`; stage paths
  explicitly.

## Dead ends

- **Restarting the Hub detached with an inline `set DATABASE_URL` inside `cmd.exe /c "..."`** —
  `Win32_Process.Create` returned `ReturnValue 0` and a PID, and the process died seconds later
  with no trace, because `pythonw.exe` discards output. Nested-quote mangling. **Fixed by a `.bat`
  wrapper**; do not go back to the inline form.
- **Diagnosing that death as "slow startup."** A `until curl` health loop sat for 180s against a
  process that was already gone. Check the process exists before polling its port.
- **`curl -d '{"path":"C:\\Users\\..."}'` from Git Bash** — fails with
  `JSON decode error ... Invalid \escape`; the shell mangles Windows paths. Use a Python
  `urllib.request` heredoc instead. This worked reliably all session.
- **`pytest tests/test_projects_api.py`** — no such file. The real names are
  `test_operator_projects_api.py`, `test_project_delete_api.py`, `test_project_lifecycle.py`,
  `test_project_persistence.py`, `test_project_workspace*.py`.
- **`ruff` / `black` are not on PATH** in Git Bash here. Use `py -3.11 -m ruff` / `py -3.11 -m black`.
- **Opening the folder before deleting the old project row** returns a marker-validation refusal,
  because the path still belongs to the old id. That is correct behaviour, not a regression — the
  order is delete, then restore marker, then open.

## Verification

**Ran, and passed:**

- `py -3.11 -m pytest hub/tests/ -q --ignore=tests/browser` → **2,474 passed, 12 skipped, 1 xpassed**
  (13m30s). Run this morning, after the adoption-event commit.
- `py -3.11 -m pytest tests/test_project_lifecycle.py tests/test_project_persistence.py
  tests/test_operator_projects_api.py tests/test_project_delete_api.py tests/test_project_workspace.py
  tests/test_project_workspace_unavailable.py -q` → **86 passed, 2 skipped**.
- `npx vitest run` → **1,155 passed / 116 files**. `npx tsc --noEmit` clean.
  `npx eslint src --max-warnings=0` clean.
- `py -3.11 -m ruff check` and `black --check` on the changed Python files — clean.
- `npx openspec validate --specs --strict` → **33 passed, 0 failed**.
- **CI on PR #7: all 9 checks green** — Linux/Windows/macOS × Python 3.11/3.12, plus `hub-test`,
  `ui-test`, `build`. Independent of the loop.
- **Two mutation checks**, both by reverting and watching a named test fail, then restoring:
  P1's `selects the clicked project…` and the adoption event's
  `test_adoption_leaves_a_trace_the_operator_can_find`.
- **Live, against the running 8000 Hub:** `POST /api/v1/projects/open` on this repo returned
  `proj-5e960453`, `directory_state: available`; `event_logs` gained
  `evt-1aa66bec / project_adopted`; `GET /api/v1/projects/proj-5e960453/project/specs` returned all
  three files from `spec/` despite the database holding **zero** `spec_documents` rows.

**NOT tested — do not claim otherwise:**

- **The browser suite (`hub/tests/browser/`) has still not been run since the 1.1.0 merge.** P6/P7
  changed five files in it and are verified by **collection only**. This is the single largest
  untested surface.
- **No UI was driven in a real browser this session.** P1 and the `register_copy_as_new` affordance
  are verified in jsdom only. P1's assertion is on `selectedProjectId`, one step short of a
  captured request URL.
- **The `project_adopted` event has never been seen rendered** in the Activity view. The row exists;
  that it displays sensibly is an assumption.
- `vitest` was last run **before** the adoption-event commit. That commit is Python-only, so this is
  almost certainly fine, but it was not re-run.

## Git state

- **Branch:** `autonomous/2026-08-19-project-portability` at `770a51d`. Clean, fully pushed.
- **`origin/master`:** `13dd6e0` (merge commit, parents `a3439c4` and `770a51d`).
- **Local `master`:** up to date with origin and carrying this handoff. It was two commits behind
  during the session; that was resolved when this handoff was moved onto it.
- Uncommitted paths: none. Unpushed commits: none.
- **Untracked and outside the repo** (will not appear in `git status`, and are real changes to the
  operator's machine): `~/.agentweave/hub/start-hub-8000.bat`,
  `~/.agentweave/hub/.env` (edited), `~/.agentweave/hub/.env.backup-2026-08-20`.
- `.agentweave/project.json` now reads `proj-5e960453`; it is gitignored.
  `.agentweave/project.json.trial-8010-backup` still holds the same id and is now redundant.

## Next steps

1. **Delete the "Default Project" row** in the 8000 Hub UI (`proj-default`, working directory
   `C:\Users\huida\Documents`). The `.env` edit stops it being re-seeded but does not remove it.
   This is the last step of the operator's *"agentweave should come clean"*.
2. **Resolve the dual-claim hazard.** Both databases now have `proj-5e960453` bound to this repo:
   `~/.agentweave/hub/data/agentweave.db` (port 8000) and `hub/data/agentweave.db` (port 8010).
   Reading from both is harmless; running agents from both would collide on `.agentweave/worktrees`
   and run state. Decide which Hub is the real one and retire the other.
3. **Run the browser suite.** `cd hub && AW_HUB_URL=http://127.0.0.1:8000 py -3.11 -m pytest
   tests/browser -v`. It is now unpinned, so it can point at 8000. Expect fallout: it has not run
   since the 1.1.0 merge and five of its files were edited blind.
4. **Look at the adoption event in the Activity view** and confirm it reads sensibly.

## Findings not acted on

- **The `UTCDateTime` docstring overstates what P4 did.** It says the type exists *"instead of at
  each of the three call sites (`agent_status.py`, `api/v1/agents.py`, `scheduler.py`) that used to
  do it themselves"* — but the merge never touched those three files, and all three **still**
  contain their own `if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)`
  (`agent_status.py:22`, `api/v1/agents.py:528`, `scheduler.py:83`). Functionally harmless — the
  guard makes them no-ops now that values arrive aware — but a future reader will trust the
  docstring. Either delete the three fragments or reword the docstring. Found while validating
  this handoff, on 2026-08-20; **not fixed**.

## Open questions for the user

- **`D-a13`** — should the Hub carry an agent's "please add this task" request and hand the operator
  a one-click accept? Open since the message-fix decision, carried through handoffs 0060 and this one.
- **`D-naming`** — `openspec/explorations/2026-08-18-candidate-names.md` and
  `2026-08-18-does-the-name-still-fit.md` remain unresolved, with more UI built on the current name
  every session.
- **Whether the openspec corpus should migrate to `spec/`.** New information this session makes this
  decidable: discovery walks `spec/` on every request, so **the files are the documents** and they
  travel with the folder. What does *not* travel is per-database — `phase`, `document_id`, and the
  requirements/tasks/evidence/coverage graph. `spec/index.json` (the manifest, currently absent —
  every document reads `state: "unindexed"` with a `home_ambiguous` diagnostic) is a plain file and
  *would* travel, carrying title, kind, parent and order. So: files + `index.json` give the whole
  readable corpus anywhere; re-establishing phases and the requirement graph is the real cost.

## Read on resume

- `hub/hub/project_lifecycle.py` — `open_existing`'s three cases and `_guard_relocation`; the centre
  of everything this session did.
- `openspec/changes/archive/2026-08-20-portable-project-identity/design.md` — why the refusal was
  reasonable when written and why it is not now.
- `.claude/autonomous/2026-08-19-project-portability-log.md` — per-iteration reasoning; **each entry
  ends with what to distrust**.
- `hub/hub/spec_documents.py` — `compute_state`/`discover`/`read_index` and `INDEX_RELATIVE =
  "spec/index.json"`; the evidence behind the corpus-migration question above.
- `hub/tests/browser/conftest.py` — how the suite is now parameterised, and how to run it.
- `hub/hub/db/models.py` — the `UTCDateTime` docstring states the SQLite naive-datetime problem in full.
