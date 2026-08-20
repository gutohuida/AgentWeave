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

## Iteration 4 — P4, timestamps corrected at the Hub's serialisation boundary (2026-08-20T00:38+01:00)

**Done, verified, committed.** Moved the naive-datetime fix from the UI's read side
(`hub/ui/src/lib/hubTime.ts`) to the Hub's DB boundary, per handoff 0060's decision.

**Root cause, confirmed rather than assumed.** Every timestamp column in
`hub/hub/db/models.py` is declared `DateTime(timezone=True)`, but SQLite has no timezone
storage — SQLAlchemy round-trips a value written aware as **naive** once it has actually
gone through the DBAPI. Three separate call sites (`agent_status.py:22`,
`api/v1/agents.py:528`, `scheduler.py:83`) already carried a manual
`if x.tzinfo is None: x = x.replace(tzinfo=timezone.utc)` workaround for their own
in-process comparisons — independent confirmation the bug is real and was already being
fought piecemeal.

**The fix.** `hub.db.models.UTCDateTime`, a `TypeDecorator` wrapping
`DateTime(timezone=True)`, relabels a naive `process_result_value` as UTC once, at the
ORM boundary. Every `mapped_column(DateTime(timezone=True))` in `models.py` (77
occurrences, mechanically replaced) now uses it — so every Pydantic response schema field
*and* every raw `.isoformat()` call downstream (session_sync.py, spec.py, tasks.py,
checkpoints.py, usage_accounting.py, …, audited by grep) inherits the fix without being
touched individually. This is the "one place, not thirty call sites" version of the fix —
considered and rejected an alternative that would have added a `UTCDateTime` Pydantic
field type to each of ~8 schema files and ~4 inline `api/v1` schemas instead; the
TypeDecorator is strictly more complete (raw `.isoformat()` call sites aren't reachable
from a Pydantic-only fix) and touches one file.

**Client side.** `hubDate()` is now a thin `new Date(value)` pass-through — the
`${value}Z`-guessing `hasTimezone()` heuristic is deleted, since the Hub now always
labels. Kept as a named function (not inlined at its ~15 call sites) specifically because
`hubTime.test.ts`'s existing sweep test ("every Hub timestamp is parsed through hubDate")
already enforces a single seam; deleting the function would have meant deleting that
guard too. Rewrote the two tests that asserted the retired guessing behavior
(`reads a bare Hub timestamp as UTC`, `does not mistake the date's own hyphens for an
offset`) since a bare-string contract that hubDate no longer holds isn't something to
keep testing; kept the aware-passthrough and explicit-offset tests, now trivial but still
a real regression guard.

**New test, mutation-checked.** `hub/tests/test_timestamp_serialization.py`: (a) an ORM
round-trip through a **second** session (`async_session_factory()` again, not the one
that wrote the row — forces a real SQLite read rather than returning the identity map's
in-memory object) asserts `tzinfo is not None`; (b) `GET /api/v1/projects/proj-test/runners`
against the default-seeded runners asserts the JSON `created_at`/`updated_at` strings
carry a UTC offset. Reverted `process_result_value` to a no-op `return value`: both tests
failed with the exact naive-string assertion error shown in the log (`'...389460' has no
UTC offset`); restored via re-editing (not `git checkout --`, which the first attempt used
and which wiped the *entire* file back to HEAD, not just the mutation — caught by
`grep -c UTCDateTime` immediately after and redone from the `Edit` calls, not from git
history).

**Measured.** `pytest hub/tests/` full suite, `-n 4`, in one command this time rather than
chunked (STATE.json's "~7min, exceeds 600s" note was for the un-parallelised run) —
**2471 passed, 75 skipped, 1 xpassed** in 174s, exit 0. `npx vitest run` —
**1165 passed / 118 files** (1167 before; −2 is exactly the two retired hubDate tests).
`tsc --noEmit` clean. `npx eslint src --max-warnings=0` clean. `ruff check hub/hub
hub/tests` clean. `black` clean (reformatted `models.py` once — `UTCDateTime()` is
shorter than `DateTime(timezone=True)`, so several wrapped `mapped_column(...)` calls
collapsed to one line; committed as black left them).

**UI bundle rebuilt and committed with its source** via
`python scripts/refresh_ui_bundle.py` after `npm run build`, per CLAUDE.md — `hub/hub/static/ui`
and `hub/ui/src` are in the same commit.

**What a reviewer should distrust.** The `.isoformat()` call-site audit (grep across
`hub/hub/**/*.py` for `.isoformat()` and manual read of every hit) was thorough but is a
point-in-time claim, not an enforced invariant — nothing stops a future raw SQL query or
a new column that bypasses `UTCDateTime` from reintroducing a naive value; there is no
lint rule or test sweeping *every* `DateTime(...)` declaration the way `hubTime.test.ts`
sweeps the client. Worth a follow-up if this surfaces again. Not verified live in a
browser against a running Hub — same no-restart limit as P1/P2/P3.

**Next.** `current` set to `P5` — close the D15 name-reuse hole (a new agent taking an
archived agent's name inherits the archived agent's creator privilege). Operator decision
already recorded in STATE.json: strip the inherited privilege on reuse, keep names
reusable. `verify`: a test that creates an agent, gives it a creator-privileged artifact,
archives it, recreates the same name, and asserts the new agent cannot reach the old
artifact.

## Iteration 5 — P5, closing the D15 authority hole (2026-08-20T01:03+01:00)

**The literal scenario in the queue item does not reproduce, confirmed rather than assumed.**
"Create an agent, archive it, recreate the same name" cannot happen through the API today:
`ix_agents_project_name` (`hub/hub/db/models.py:294`) is an unconditional unique index on
`(project_id, name)` with no exemption for archived rows, and nothing lets an existing agent be
renamed to free its name either. `hub/tests/test_tasks.py`'s pre-existing D15 test already
recorded this exact finding on 2026-08-19 (`2026-08-18-a-loop-writes-its-own-queue`'s A5.3) —
independently re-verified this iteration by reading the index definition and the agent-mutation
routes in `hub/hub/api/v1/agents.py`, not by trusting the earlier note. Per the pre-authorised
guidance for a queue item that turns out to be blocked or wrong, this is recorded rather than
worked around: the *real*, still-open gap A5.3 documented — one layer down from the roster — is
what this iteration closes instead.

**The real gap.** `_authorize_loop_task_creation` (`hub/hub/api/v1/tasks.py`) decides who may add
a task to a loop's queue by comparing `actor.agent` to `AIJob.agent` as bare strings — and
`actor.agent` is itself just `Run.agent` (`agent_auth.py::get_agent_actor`), never looked up
against the `agents` table. Whoever a *name* belongs to now, not whoever currently holds it as a
live, open `Agent` row, controlled the loop. `hub/hub/api/v1/agent_trigger.py`'s two independent
spawn paths (`trigger_agent_directly`, used by queued/scheduled delivery via `turn_scheduler.py`
and `scheduler.py::_do_fire_job`; and the `POST /agent/trigger` route, which duplicates its own
checks rather than calling the other — an existing pattern in this file, not one introduced here)
never checked `Agent.lifecycle` either, so an archived agent could still be triggered directly by
name and mint a new "running" `Run` — silently violating `agent-configuration`'s spec text
("nothing runs an archived agent") along the way, not just the loop-authority question.

**The fix, two parts.**
1. `trigger_agent_directly` and `trigger_agent` (`agent_trigger.py`) both now refuse with 409 if
   the named agent's `Agent.lifecycle == "archived"`, checked immediately alongside the existing
   "has no runner bound" guard. This is the one choke point both spawn paths share with
   scheduled/queued delivery, so it closes "an archived agent runs at all" everywhere at once —
   confirmed by tracing `turn_scheduler.schedule_agent` and `scheduler.py::_do_fire_job` back to
   `trigger_agent_directly`, not assumed from the file's docstring claiming it.
2. `_authorize_loop_task_creation` (`tasks.py`) now additionally looks up the `Agent` row behind
   `job.agent` after the existing name match, and refuses the same way if that row exists and
   reads `lifecycle == "archived"`. Deliberately **not** refused when no `Agent` row exists at
   all under that name — that shape (a `Run` with an identity string but no persisted roster
   entry) is the existing, legitimate contract every `_active_run`-style test fixture in this
   codebase already relies on, confirmed by re-running the full suite after the first version of
   this check (which refused on `creator_row is None` too) and finding it broke four unrelated,
   correct tests in `test_agent_actions_coordination.py` and `test_agent_actions_governed.py` —
   caught by the full-suite run this iteration insisted on, not by the targeted files alone.
   Loosened to "refuse only on a positively-archived row" and re-ran; all four passed again with
   no other regressions.

**The pre-existing D15 test, flipped rather than left recording the gap.** Its own docstring said
"if this assertion ever starts failing with a 403, the gap has been closed; update this test... to
say so rather than treating the failure as a regression" — done:
`test_d15_a_run_claiming_an_archived_agents_name_inherits_its_loop_authority` is now
`test_d15_an_archived_creators_run_no_longer_controls_its_loop`, asserting 403 and that no task
was created, with the docstring rewritten to describe what closed it. One bug caught while doing
this: the original fixture set `Agent.archived_at` but never `Agent.lifecycle`, so it was not
actually archived by the model's own definition (`agent_lifecycle.archive()` sets both together,
always) — the rewritten fixture sets `lifecycle = "archived"` too, matching real archival.

**Mutation-checked, both fixes.** `_authorize_loop_task_creation`'s new lookup-and-refuse block
was removed; the D15 test failed exactly as expected (`201 == 403`); restored, D15 test green
again. The `trigger_agent` route's archived check was replaced with a no-op `pass`; the new
`test_trigger_refuses_an_archived_agent` failed exactly as expected (`200 == 409`); restored,
green again.

**Measured.** Targeted run first (`test_tasks.py`, `test_agent_trigger.py`,
`test_agent_archival.py`, `test_jobs.py`, `test_jobs_crud.py`, `test_scheduler.py`) — 142 passed.
Full suite, `-n 4`, one command (per P4's established baseline) — **2472 passed, 75 skipped, 1
xpassed** in 150s (2471 before this iteration; +1 net, matching the one genuinely new test — the
D15 test was rewritten in place, not added). `ruff check` on the four touched files clean.
`black --check` clean. `mypy hub/hub/api/v1/tasks.py hub/hub/api/v1/agent_trigger.py` — zero
errors attributable to either file (the 296 reported are pre-existing, in the same shape P4 already
documented as baseline noise elsewhere in the import graph). No UI files touched, so no bundle
rebuild.

**What a reviewer should distrust.** `_require_agent_job_allowance` (`hub/hub/api/v1/jobs.py`),
the other function A5.3 named alongside `_authorize_loop_task_creation`, was deliberately left
untouched after reading it closely: unlike the loop-creator check, it does not compare against any
stored "creator" field — it gates whether the *current* caller's own run is live and the project
allows agent-originated job mutations at all, and it already requires `Run.status == "running"`.
Its exposure to an archived identity is closed as a side effect of fix #1 above (no new running
Run can be minted for an archived name), not because it was independently changed — worth
rechecking if a future change gives it its own creator-comparison logic. Not verified live in a
browser — this iteration is backend-only, so the no-Hub-restart limit that blocked P1-P4's live
verification does not apply here in the first place; there is no UI surface to check.

**Next.** `current` set to `P6` — unpin `hub/tests/browser/conftest.py`'s hard-coded
`DEFAULT_PROJECT_ID = 'proj-5e960453'` so the browser suite is not tied to this one machine's
trial Hub. Operator decision already recorded: make it an env var defaulting to the current value,
keep the `FORBIDDEN_PROJECT_IDS` guard at line 52 intact, and do **not** run the suite against a
live Hub tonight — `pytest tests/browser --collect-only` is enough to prove it still imports and
skips cleanly.

## Iteration 6 — P6, and the fixture-scoping gap it actually needed (2026-08-20T01:12+01:00)

**The literal 'do' was already done, confirmed rather than assumed.** `conftest.py`'s
`project_id` fixture (`os.environ.get("AW_HUB_PROJECT_ID", DEFAULT_PROJECT_ID)`, with the
`FORBIDDEN_PROJECT_IDS` guard) already existed before this branch started —
`git merge-base --is-ancestor 7657c42 afb63f5` confirms the commit that added it (2026-08-18,
`7657c42`) is an ancestor of this run's own parent SHA. Per the pre-authorised guidance for a
queue item that turns out to be blocked, wrong, or already done, this is recorded rather than
worked around or silently ticked without checking further.

**The real gap, found by grepping the fixture's actual usage.** Only `test_job_loop_block.py`
consumed the `project_id` fixture. `test_loops_index.py` (`PROJECT_ID = "proj-5e960453"`,
module-level) and `test_human_only_halves.py` (`LOOP_PROJECT = "proj-5e960453"`) each kept an
independent hardcoded copy of the same identity and used it directly in their own `page.goto`
calls, entirely bypassing the fixture — so setting `AW_HUB_PROJECT_ID` changed the URL for one
test file and silently did nothing for the other nine loops-related tests across two files. This
is exactly the "identity that should travel, hard-coded to one place" disease the queue item's
own note named, just one layer deeper than the note's evidence (which only read `conftest.py:54`)
had looked.

**Fix.** Removed both hardcoded module constants. Threaded `project_id: str` (the existing
fixture) through `test_loops_index.py`'s `_open_bare`/`_open_loops_tab` helpers and all 6 test
functions that call them, and through `test_human_only_halves.py`'s `_open_loops_index` helper
and the 3 test functions that call it. Verified each is a real, not dead, parameter by reading
every edited call site's f-string — `project_id` lands in the `page.goto` query string in both
files, not merely accepted and ignored.

**What was deliberately left alone.** `test_panel_shell.py`, `test_files_tab.py`, and
`test_human_only_halves.py`'s own `SPEC_PROJECT` all hardcode a *second*, genuinely distinct
fixture identity — `proj-b44fac0c`, the operator's disposable "Throwaway (taste pass)" project,
carrying its own agent (`q2verify`), conversation, and specification document that the default
project does not have. Folding this into the same fix would have meant guessing at a second env
var's name and default under time pressure rather than doing it deliberately; recorded instead as
new queue item **P7**, same shape as P6, sized to reuse this iteration's approach directly.
`conftest.py`'s module docstring now names both identities and states which env var reaches which
— previously `AW_HUB_PROJECT_ID` was not documented in prose at all, only in the fixture's own
one-line body.

**Verified.** `pytest tests/browser --collect-only` — 63 collected, 0 errors (same count as
before the edit — nothing was accidentally dropped). `pytest tests/browser` with no `AW_HUB_URL`
set — 63 skipped, the existing collection-time skip in `conftest.py` (untouched this iteration).
`ruff check`, `black --check`, and `mypy` all clean on the three touched files
(`conftest.py`, `test_loops_index.py`, `test_human_only_halves.py`). Not run against a live Hub —
forbidden by the standing limits and unnecessary for this change, which is pure test-file
plumbing with no product code touched. No UI files touched, so no bundle rebuild.

**What a reviewer should distrust.** This iteration's own scoping call — that `proj-b44fac0c` is
a "genuinely distinct" identity rather than more of the same disease — rests on reading each
file's docstring, not on running the suite against a second real Hub to confirm the two fixture
projects really are independent in practice. If a future Hub happens to seed both identities from
the same seed data, P7 might turn out simpler than its own `do` describes.

**Next.** `current` set to `P7` — unpin the second hardcoded fixture identity, `proj-b44fac0c`,
the same way this iteration unpinned the default project. Add a second env var (e.g.
`AW_HUB_SPEC_PROJECT_ID`) alongside `AW_HUB_PROJECT_ID` in `conftest.py`, expose it as a fixture,
thread it through `test_panel_shell.py`, `test_files_tab.py`, and `test_human_only_halves.py`'s
`SPEC_PROJECT`. After P7 the queue is empty again; `stop_when_queue_empties` is `false`, so the
next iteration needs to decide — and record — whether to idle-checkpoint or find/propose further
work.

## Iteration 7 — P7, and the queue's actual end (2026-08-20T01:36+01:00)

**P7, done.** Threaded the second hardcoded fixture identity (`proj-b44fac0c`, "Throwaway (taste
pass)") through every call site the same way iteration 6 threaded `project_id`. Added
`spec_project_id` (env `AW_HUB_SPEC_PROJECT_ID`, default unchanged) to `conftest.py`, removed the
independent `PROJECT_ID`/`SPEC_PROJECT` constants from `test_panel_shell.py`, `test_files_tab.py`,
and `test_human_only_halves.py`, and threaded the fixture through every helper and test function —
including `test_files_tab.py`'s two module-level compiled regexes (`PATHS_ROUTE`/`FILE_ROUTE`),
which depended on the old constant and had to move into per-call functions taking `project_id` as
an argument, since a fixture value cannot be closed over at import time.

**Verified.** `pytest tests/browser --collect-only` — 63 collected, 0 errors, same count as before
(nothing dropped). `pytest tests/browser` with no `AW_HUB_URL` — 63 skipped, unchanged. `ruff`
clean on all four touched files. `black --check` flagged one line-length collapse in
`test_panel_shell.py`'s `_open` signature after the added parameter; applied and reconfirmed clean.
`mypy` reports the same 4 pre-existing `no-untyped-def` errors as the unmodified branch tip (verified
by `git stash`-ing this iteration's changes and re-running mypy against the original files) — same
shape, just shifted line numbers from the edits; nothing new. Not run against a live Hub, per the
standing limit — pure test-file plumbing, no product code touched.

**The queue is now actually empty — P1 through P7, all `done`.** Per the "Next" note carried from
iteration 6 and the pre-authorised guidance (`stop_when_queue_empties: false`), this iteration had
to decide, and record, what happens next rather than stopping. Chose to look for real unfinished
business already named in the run's own history before inventing anything new:

1. **`openspec/changes/portable-project-identity` (P2's change) was implemented and verified last
   iteration but never synced or archived.** `openspec status --change --json` showed all four
   artifacts (`proposal`, `design`, `specs`, `tasks`) `done`, `tasks.md` fully checked off, and
   `actionContext.mode: repo-local` — no workspace-planning restriction applies. Read the delta
   spec (`specs/local-project-workspace/spec.md`) against the main spec at
   `openspec/specs/local-project-workspace/spec.md`: the main spec was missing the adoption
   sentence on the "Projects have stable directory-backed identity" requirement, its two new
   scenarios ("A directory carries an identifier this database has never registered", "A project is
   deleted and its directory is reopened"), and a sharpened WHEN clause on the existing "A marker
   was copied" scenario that distinguishes case 2 (this database already holds the marker's id)
   from the new case 3 (adoption). Applied all three edits by hand (the delta's own MODIFIED-section
   intent, not a wholesale replacement — the other two untouched scenarios in that requirement, plus
   every other requirement in the file, were left exactly as they were). `openspec validate --all
   --strict` — 34/34 passed before archiving, 33/33 after (the archived change itself no longer
   counts as a separate validation item). Archived to
   `openspec/changes/archive/2026-08-20-portable-project-identity/`.

2. **P4's own log entry named an open finding**: nothing swept every `DateTime(...)` declaration in
   `hub/hub/db/models.py` the way `hub/ui/src/__tests__/hubTime.test.ts` sweeps the client, so a
   future column written as `mapped_column(DateTime(timezone=True))` directly would silently bypass
   `UTCDateTime` and reintroduce the naive-timestamp bug P4 fixed. Added
   `test_every_orm_datetime_column_uses_the_utc_correction` to
   `hub/tests/test_timestamp_serialization.py` — the server-side mirror of the client sweep, walking
   `models.py`'s own source text rather than importing it (a static sweep, not a runtime one, same
   reasoning the TS version gives for using Vite's source graph instead of introspecting the mounted
   module). Confirmed the sweep isn't vacuous (`len(utc_datetime_uses) > 30`, currently ~35) before
   trusting an empty offenders list. Mutation-checked: rewrote one column
   (`Project.created_at`, line 70) from `UTCDateTime()` to `DateTime(timezone=True)` via a small
   Python script (not an `Edit` call — `mapped_column(UTCDateTime()...)` appears 30 times in the
   file and Edit's exact-match requirement can't target one occurrence without pasting surrounding
   context for every line), reran the new test alone, watched it fail by name naming line 70 and the
   exact offending text, then reverted the same way and confirmed `git diff --stat` showed no
   residual change before rerunning the full file green.

**What was deliberately NOT invented.** No new queue item was manufactured past these two. Grepped
this log file for language like "open finding" / "worth rechecking" / "future iteration" turned up
nothing beyond what's covered above; the one remaining loose thread from P5
(`_require_agent_job_allowance`'s exposure being closed only as a side effect, "worth rechecking if
a future change gives it its own creator-comparison logic") is conditional on a change that hasn't
happened and isn't actionable today.

**CI.** Pushed both this iteration's P7 commit and the archive/sync commit, then the sweep-test
commit. `gh run list --branch autonomous/2026-08-19-project-portability` shows the four most recent
completed runs on this branch all green (5m30s-7m45s), and the push just now triggered a fifth,
in progress at the time of this entry. `gh run list --branch master --workflow ci.yml` confirms
master's own CI is unaffected and green — this branch's draft PR (#7) has been exercising CI the
whole run, exactly as iteration 1 set out to arrange.

**Measured.** Targeted: `pytest hub/tests/test_timestamp_serialization.py
hub/tests/test_project_lifecycle.py hub/tests/test_project_persistence.py` — 22 passed. Full
`hub/tests/` suite was NOT re-run this iteration (last measured at 2472 passed / 75 skipped / 1
xpassed in iteration 5, unaffected by anything touched here — none of this iteration's three
commits touch product code the full suite would newly exercise beyond what the targeted run
already covers). `ruff check`, `black --check` clean on every touched file. No UI files touched,
so no bundle rebuild.

**What a reviewer should distrust.** The decision to treat "sync + archive P2's change" and "close
P4's named finding" as legitimate `stop_when_queue_empties: false` follow-on work, rather than
scope creep past a queue the operator actually wrote, rests on both being explicitly recorded as
unfinished business in this run's own prior iterations — not invented from scratch. If that
reasoning is wrong, both are easily separable: the archive commit and the sweep-test commit are
each self-contained and revertable independently of P1-P7.

**Next.** The named queue is fully closed and its two recorded loose threads are closed with it.
No further work is queued. The next iteration should re-run `openspec list` and grep this log for
new findings before assuming there is nothing left — but if genuinely nothing surfaces, idle-
checkpointing (verify the branch, confirm CI, extend the heartbeat, stop) is the correct outcome
per the pre-authorised guidance, not manufacturing a queue item to fill the window.

## Iteration 8 — idle checkpoint, queue confirmed still empty (2026-08-20T01:48+01:00)

Followed iteration 7's own instruction literally rather than trusting its conclusion secondhand.
`git branch --show-current` / `git log --oneline` / `git status` confirm the branch, its four most
recent commits, and a clean tree all match STATE.json exactly — no reconciliation needed.

`openspec list` — "No active changes found." `ls openspec/changes/ | grep -v archive` — empty.
`openspec validate --all --strict` — 33/33 passed (down from 34 pre-archive, as expected: the
archived `portable-project-identity` change no longer counts as a separate item). Grepped the
full log (all 565 lines, not just iteration 7's entry) for `open finding|worth rechecking|future
iteration|not yet|todo|TODO|deferred|not done|still open|unresolved`. Every hit traced to already-
closed, deliberate decisions recorded inline at the time: P1's choice not to thread a defence-in-
depth `projectId` prop (log line ~97), P2's choice not to run the full suite/browser check because
P2 has no UI surface of its own (log line ~177), and P5's `_require_agent_job_allowance` thread,
which is conditional on a change that has not happened and is not actionable today (log line
~535). Nothing new.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs on this branch all `completed success`, 5m30s-7m45s each. Branch remains fully green.

**Conclusion.** The queue is genuinely empty and stays empty. Per the pre-authorised guidance,
this is an idle checkpoint: verify branch, confirm CI, extend the heartbeat, stop — not manufacture
a queue item to fill the window. `stop_at` is 2026-08-20T08:00:00+01:00; six hours remain. Next
iteration should repeat this same check (branch state, `openspec list`, log grep, CI) before
assuming the same conclusion still holds — new work could arrive from the operator, or CI could
regress, between now and then.

## Iteration 9 — idle checkpoint, queue still empty (2026-08-20T02:08+01:00)

Repeated iteration 8's check from scratch rather than trusting it secondhand. `git branch
--show-current` / `git log --oneline -5` / `git status` all match STATE.json exactly (`87b266b`
"Release the branch to the driver" at HEAD, clean tree) — no reconciliation needed.

`openspec list` — "No active changes found." `openspec validate --all --strict` — 33/33 passed,
same count as iteration 8's post-archive baseline; nothing new proposed since.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs all `completed success` (5m50s-7m45s), same set iteration 8 saw. `gh pr view 7` — still
`OPEN`, mergeable `MERGEABLE`, zero comments, zero reviews — no operator activity on the draft PR
since it opened.

**Conclusion.** Nothing changed since iteration 8. Queue stays empty; no work manufactured.
Idle-checkpointing again per the pre-authorised guidance: verify, confirm CI, extend the heartbeat,
stop. `stop_at` is 2026-08-20T08:00:00+01:00; just under six hours remain. Next iteration should
repeat the same four checks (branch/log state, `openspec list`, log grep for new findings, CI)
rather than assume this conclusion is permanent.

## Iteration 10 — idle checkpoint, queue still empty (2026-08-20T02:28+01:00)

Repeated the standing check from scratch, not trusted secondhand. `git branch --show-current` /
`git log --oneline -5` / `git status` all match STATE.json exactly (`3915ae4` "Release the branch
to the driver" at HEAD, clean tree) — no reconciliation needed.

`openspec list` — "No active changes found." `openspec validate --all --strict` — 33/33 passed,
same count as iterations 8-9's post-archive baseline.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs all `completed success` (5m50s-7m24s), same set iteration 9 saw (newest at 2026-08-20T01:09Z,
before iteration 9 even ran) — no new push has landed since the sweep-test commit. `gh pr view 7
--json comments,reviews,mergeable,mergeStateStatus` — zero comments, zero reviews, `MERGEABLE`,
`CLEAN`. No operator activity on the draft PR.

**Conclusion.** Nothing changed since iteration 9. Queue stays empty; no work manufactured.
Idle-checkpointing again: verify, confirm CI, extend the heartbeat, stop. `stop_at` is
2026-08-20T08:00:00+01:00; about five and a half hours remain. Next iteration should repeat the
same checks rather than assume this conclusion is permanent — the operator may act on the draft PR
or add new work at any point before the window closes.

## Iteration 11 — idle checkpoint, queue still empty (2026-08-20T02:48+01:00)

Repeated the standing check from scratch, not trusted secondhand. `git branch --show-current` /
`git log --oneline -5` / `git status` all match STATE.json exactly (`9a1fac0` "Release the branch
to the driver" at HEAD, clean tree) — no reconciliation needed.

`openspec list` — "No active changes found." `openspec validate --all --strict` — 33/33 passed,
same count as iterations 8-10's post-archive baseline.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs all `completed success` (5m50s-7m24s), same set iteration 10 saw — no new push has landed
since the sweep-test commit. `gh pr view 7 --json comments,reviews,mergeable,mergeStateStatus` —
zero comments, zero reviews, `MERGEABLE`, `CLEAN`. No operator activity on the draft PR.

**Conclusion.** Nothing changed since iteration 10. Queue stays empty; no work manufactured.
Idle-checkpointing again: verify, confirm CI, extend the heartbeat, stop. `stop_at` is
2026-08-20T08:00:00+01:00; about five hours remain. Next iteration should repeat the same checks
rather than assume this conclusion is permanent — the operator may act on the draft PR or add new
work at any point before the window closes.

## Iteration 12 — idle checkpoint, queue still empty (2026-08-20T03:08+01:00)

Repeated the standing check from scratch, not trusted secondhand. `git branch --show-current` /
`git log --oneline -5` / `git status` all match STATE.json exactly (`ecea4de` "Release the branch
to the driver" at HEAD, clean tree) — no reconciliation needed.

`openspec list` — "No active changes found." `openspec validate --all --strict` — 33/33 passed,
same count as iterations 8-11's post-archive baseline.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs all `completed success` (5m40s-6m44s), same set iteration 11 saw — no new push has landed
since the sweep-test commit. `gh pr view 7 --json comments,reviews,mergeable,mergeStateStatus,state`
— zero comments, zero reviews, `OPEN`, `MERGEABLE`, `CLEAN`. No operator activity on the draft PR.

**Conclusion.** Nothing changed since iteration 11. Queue stays empty; no work manufactured.
Idle-checkpointing again: verify, confirm CI, extend the heartbeat, stop. `stop_at` is
2026-08-20T08:00:00+01:00; about five hours remain. Next iteration should repeat the same checks
rather than assume this conclusion is permanent — the operator may act on the draft PR or add new
work at any point before the window closes.

## Iteration 13 — idle checkpoint, queue still empty (2026-08-20T03:28+01:00)

Repeated the standing check from scratch, not trusted secondhand. `git branch --show-current` /
`git log --oneline -5` / `git status` all match STATE.json exactly (`e503021` "Release the branch
to the driver" at HEAD, clean tree) — no reconciliation needed.

`openspec list` — "No active changes found." `openspec validate --all --strict` — 33/33 passed,
same count as iterations 8-12's post-archive baseline.

`gh run list --branch autonomous/2026-08-19-project-portability --limit 5` — five most recent CI
runs all `completed success` (6m11s-7m38s), same set iteration 12 saw — no new push has landed
since the sweep-test commit. `gh pr view 7 --json comments,reviews,mergeable,mergeStateStatus,state,commits`
— zero comments, zero reviews, `OPEN`, `MERGEABLE`, `CLEAN`, same commit list as before. No
operator activity on the draft PR.

**Conclusion.** Nothing changed since iteration 12. Queue stays empty; no work manufactured.
Idle-checkpointing again: verify, confirm CI, extend the heartbeat, stop. `stop_at` is
2026-08-20T08:00:00+01:00; about four and a half hours remain. Next iteration should repeat the
same checks rather than assume this conclusion is permanent — the operator may act on the draft PR
or add new work at any point before the window closes.
