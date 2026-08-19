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

## Iteration 2 — P2, adopt an orphaned project marker (2026-08-19T23:53+01:00)

**Done, verified, committed.** This is the item the operator named as the point of the night:
"I should be able to open any agentweave project from any agentweave app that I want."

**Openspec first, per the queue item and STATE.json's `pre_authorised`.** Ran
`/openspec-propose` against capability `local-project-workspace` (the queue text said
`local-multi-project-workspace`; that capability does not exist — `openspec/specs/` only has
`local-project-workspace`, the one archived from `2026-08-03-local-multi-project-workspace`. Used
the real name.). `openspec new change` rejects a name starting with a digit, so the change is
`openspec/changes/portable-project-identity/` rather than a date-prefixed name — consistent with
this repo's existing archived changes, whose date prefixes are applied by the archive step, not
present at proposal time.

Wrote `proposal.md`, `design.md`, and a delta `specs/local-project-workspace/spec.md` that adds
two scenarios to "Projects have stable directory-backed identity" — orphaned-marker adoption, and
delete-then-reopen — and narrows the existing "A marker was copied" scenario's WHEN clause to
state explicitly that it fires only when the opening database already holds a row for the marker's
id (case 2). `npx openspec validate --changes --strict` passed before any implementation code was
touched, as the brief required.

**Design decision worth flagging for review:** adoption is recorded with a `logger.info` line
(`event="project_adopted"`, id, path) rather than a new table or column. The codebase's own
observability pattern for this kind of thing is stdlib `logging` (`CLAUDE.md` "Logging" section);
no project-lifecycle event table exists today, and one new code path did not seem to justify
starting one. If the operator wants adoption surfaced in the UI later (e.g. a project badge), that
needs a real schema decision and is out of scope here — recorded as an Open Question in design.md.

**Implementation.** `hub/hub/project_lifecycle.py` `open_existing`: the marker-present branch now
has three shapes instead of two-and-a-raise:
- `marked_project is not None`, not `register_copy_as_new` → unchanged (guard, observe, return).
- `marked_project is not None`, `register_copy_as_new` → unchanged (falls through to the
  brand-new-id path below, exactly as before).
- `marked_project is None`, not `register_copy_as_new` → **new**: construct `Project(id=marker
  ["project_id"], ...)`, seed via the existing `_seed_new_project`, observe, write marker, commit,
  log, return. This is case 3 — the only branch this change touches.
- `marked_project is None`, `register_copy_as_new` → unchanged (falls through to the same
  brand-new-id path; register-copy-as-new never had a reason to look at the orphan's id).

Traced all four combinations against the pre-change code before writing the fix, specifically to
confirm the register-copy-as-new behaviour for a marker whose project *is* absent (a combination
the old code handled but no test exercised) is unchanged by the refactor.

**Tests, mutation-checked.** Two new tests in `hub/tests/test_project_lifecycle.py`:
`test_orphaned_marker_is_adopted_under_its_own_id` (writes a marker naming a fabricated id no row
exists for, opens it, asserts the returned AND the re-queried project both carry that id, with
runners and charters seeded) and `test_deleted_project_directory_is_adopted_back_under_the_same_id`
(open, delete, reopen the same directory, assert the id survives and reseeding happened). Reverted
`project_lifecycle.py` via `git stash` and reran: both new tests failed with the old
`ProjectIdentityConflict`, the other 10 tests in the file untouched — the correct signature.
Restored and reran green. The existing case-2 guard test,
`test_copied_marker_conflicts_until_explicitly_registered_as_new`, was run unedited and stayed
green — it doubles as task 3.2's "case 2 still refused" coverage, so no near-duplicate test was
added; recorded in `tasks.md` instead.

**Measured:** `pytest hub/tests/test_project_lifecycle.py hub/tests/test_project_persistence.py -v`
via the Python 3.11 interpreter at `C:\Users\huida\AppData\Local\Programs\Python\Python311\
python.exe` (the plain `python` on this shell's PATH lacks `pytest_asyncio` — the driver's own
prior runs must have used a different interpreter than the shell default; worth a decisions-for-
user note if it recurs) — **19 passed** (17 before, +2 new). `ruff check` clean on both changed
files. `black --check` initially flagged one line in the new test (over the line-length limit);
reformatted and reconfirmed clean. `npx openspec validate --changes --strict` — 1 passed / 0 failed
— reran after implementation, not just before.

**Not done, and why.** `tasks.md` sections 1-4 are all checked, each with what was actually
verified noted inline rather than left as a bare checkbox — no task was marked complete on the
strength of a plan existing. Not run: the full `hub/tests/` suite, `mypy`, `eslint`/`tsc` (this
iteration touched no TypeScript), and no browser check — P2 has no UI surface of its own; the
Add-project dialog that calls `open_existing` was already exercised and fixed in `75c7685`, and
retesting it live is blocked tonight by the no-Hub-restart limit exactly as it was for P1.

**What a reviewer should distrust.** The adoption log line is unverified beyond "the call site is
reached" — no test asserts on log output or its format, since nothing downstream parses it yet.
The `orphan_id` fixture (`"proj-orphanedid01"`) is a hand-typed string, not one `short_id()` would
produce; harmless for what the test checks (id equality, row existence) but worth knowing if a
future test wants to assert format validity too.

**Next.** `current` set to `P3` — tests for the two things committed interactively before this run
began (`apiErrorCode`, the `register_copy_as_new` UI affordance). No blockers carried forward from
P2 beyond the Open Question already in `design.md`.

## Iteration 3 — P3, tests for tonight's committed UI fixes (2026-08-20T00:10+01:00)

**Done, verified, committed.** Both things `75c7685` shipped before this branch existed —
`apiErrorCode` (`hub/ui/src/api/client.ts`) and the `register_copy_as_new` remedy button in
`ProjectManagerModal.tsx` — were green under `tsc` and the existing suite but had no test of their
own. They do now, in two new files.

**`src/__tests__/apiErrorCode.test.ts`** mirrors the shapes `taskIntegration.test.ts` already
covers for `readableApiError` (string detail, object detail with `code`+`message`, Pydantic array,
unparseable text), plus the cases specific to a code-matcher: a non-string `code`, an object detail
with no `code` field, a non-`ApiError` value, and `null`. All of those must return `null` — only
the one shape carrying a genuine string `code` should return it.

**`src/__tests__/projectManagerIdentityConflict.test.tsx`** follows the existing
`projectManagerDirectoryPicker.test.tsx` pattern (mock `useOpenProject`/`useCreateProject` with a
controllable `error`, mount the real modal). Four cases: no button with no error; no button on a
refusal whose code is not `project_identity_conflict` (the sentence still renders, per
`readableApiError` — the two are independent); no button in **create** mode even on that exact
code, since `isIdentityConflict` is gated `!isCreate && ...` and the conflict can only arise when
*opening* an existing folder; and the button present on the matching code, clicking it resubmits
via the mocked `mutate` with the typed path plus `register_copy_as_new: true` — asserted on the
actual call arguments, not inferred.

**Mutation-checked, not merely green — twice.**
- `apiErrorCode` patched to always `return null` immediately after its signature: exactly
  `'reads the code out of an object-shaped detail'` failed; the other 7 (all asserting `null`) kept
  passing, which is the correct signature — a matcher that always says "no code" only breaks the
  one test expecting a code back.
- `ProjectManagerModal`'s comparison patched from `'project_identity_conflict'` to `'nope'`:
  exactly `'offers the remedy on a project_identity_conflict refusal...'` failed (the alert text
  still rendered, just no button), the other 3 stayed green. Both mutations reverted via
  `git checkout --` and reconfirmed green before committing.

**Measured:** `tsc --noEmit` clean. `npx vitest run` — **1167 passed / 118 files** (1155/116
before, +12 tests in +2 files). `npx eslint src --max-warnings=0` clean.

**No UI bundle rebuild.** `hub/hub/main.py`'s `ui_source_fingerprint` explicitly excludes
`__tests__` from the git-ls-files pathspec it hashes (line 85: `exclude: Sequence[str] =
("__tests__",)`), so two new files under `src/__tests__/` do not move the fingerprint the stamp
checks against. Confirmed by reading the function rather than assumed. `hub/hub/static/ui` is
unchanged and was not touched.

**What a reviewer should distrust.** Both suites still run only in jsdom against mocked mutations
— no browser check against a live Hub, same limitation as P1 and P2, same reason (no-restart).
The `'not an identity conflict'` case uses a fabricated `validation_error` code rather than one
observed from a real refusal; harmless for what it asserts (button absence) but not a captured
server response.

**Next.** `current` set to `P4` — move the timestamp correction from `hub/ui/src/lib/hubTime.ts`'s
client-side compensation to where the Hub serialises the value. Decision already made in the queue
item; read the file's current two exemptions before touching anything, since at least one is
recorded as genuinely client-side.
