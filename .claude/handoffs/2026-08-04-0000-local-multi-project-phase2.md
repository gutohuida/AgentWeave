# Handoff: Local multi-project workspace phase 2 complete

**Date:** 2026-08-04T00:00:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `37a6854`
**Agent:** Claude Code (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-03-2227-local-multi-project-phase1.md`
**Status:** chunk complete — approved change phase 2 implemented and verified; HEAD unchanged
(nothing has been committed yet — see "Git state")

## Goal

Implement the approved local multi-project workspace change so one local AgentWeave instance can
own multiple directory-backed projects without filesystem, authentication, event, or frontend-state
leakage. Phase 2 makes the CLI's bare invocation open/register its invocation directory as a
project after Hub health, removes the unconditional legacy project bootstrap so a genuinely fresh
install starts with zero projects, and replaces `status`'s `.env`-label read with a live
project-collection query.

## Current state

- Tasks 0.1–2.6 are complete and checked off in
  `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`. Phases 3–6 remain pending.
- Phase 0/1 (persistence, canonical paths, operator project API) is unchanged from the prior
  handoff — see that file for its detail. This handoff covers phase 2 only.
- `agentweave` bare invocation now captures `Path.cwd()` at call time and, after the Hub answers
  healthy (whether it was just started or was already running), calls
  `POST /api/v1/projects/open` with that directory and opens the app at
  `/?project=<id>&view=overview`. This happens in the detached-start branch, the already-running
  branch, and the foreground (`--no-detach`) branch via a threaded helper — all three call the same
  `_hub_resolve_launch_url(port, cwd)` function.
- The open call is unconditional (happens regardless of `--app`); only the *browser window* opening
  is gated by `--app`. This matches design decision 6's "whether the instance was already running
  or was just started, it reads the local operator credential and calls the same open-existing
  endpoint after a health check."
- A directly started Hub (Docker, or a hypothetical native start with no invocation directory —
  `cwd=None`) makes **no** open call at all and opens the bare Hub URL. `_hub_native_scaffold` no
  longer writes `AW_BOOTSTRAP_PROJECT_ID`/`AW_BOOTSTRAP_PROJECT_NAME` into a freshly scaffolded
  `.env`, so a genuinely fresh native install has zero rows in `Project`/`ApiKey` after `init_db()`
  — only one `OperatorCredential` (freshly minted or promoted from `AW_BOOTSTRAP_API_KEY` if set).
- `hub/hub/db/engine.py`'s `init_db()` now gates the old "always bootstrap one Project + ApiKey"
  block on `os.environ.get("AW_BOOTSTRAP_PROJECT_ID") is not None` — i.e. only when a
  pre-multi-project `.env` (or the test suite) explicitly requests the legacy row. This is the one
  substantive behavior change to already-committed phase-0/1 code in this handoff.
- `_seed_operator_credential` (same file) now mints a fresh `OperatorCredential` directly (using
  `settings.aw_bootstrap_api_key` or a generated `aw_live_...` key) when there is no legacy `ApiKey`
  to promote, instead of silently returning with no credential at all. Without this, a zero-project
  fresh install would have no way to authenticate the local app.
- `cmd_status` now calls `_hub_project_status_summary(port)` (fetches the operator token, then
  `GET /api/v1/projects`) and prints `Projects: N registered (most recent: <name>)` — or
  `0 registered` — instead of reading `AW_BOOTSTRAP_PROJECT_ID`/`NAME` out of the `.env` file. The
  old `_hub_project_label()` function was deleted (dead code, no other callers).
- The Hub-side idempotent legacy-binding mechanism (`ProjectLifecycleService._single_unbound_legacy_project`
  in `hub/hub/project_lifecycle.py`) already existed from phase 0 but had **no test coverage**
  anywhere in the suite before this session. It is now covered directly (see "Files touched").
- The frontend still calls the removed implicit project routes (unchanged from phase 1's noted
  intentional mismatch) — phase 4 owns migrating it.

## Files touched

Phase 0/1 files, still dirty from the prior handoff (unchanged this session; listed for
completeness, see the phase-1 handoff for what's in them):

- `hub/hub/db/models.py`, `hub/hub/migrations/versions/0026_add_project_workspace_identity.py`,
  `hub/hub/project_workspace.py`, `hub/hub/project_lifecycle.py` (logic unchanged; only its test
  coverage grew this session — see below)
- `hub/hub/auth.py`, `hub/hub/api/v1/__init__.py`, `hub/hub/api/v1/projects.py`,
  `hub/hub/api/v1/setup.py`, `hub/hub/api/v1/{agent_chat,agent_trigger,events,logs,session_sync,
  status,workspace,worktrees}.py`
- `hub/tests/conftest.py`, `hub/tests/test_operator_projects_api.py`, and the ~35 other
  `hub/tests/test_*.py` files migrated to explicit `/api/v1/projects/proj-test/...` routes
- `hub/tests/test_project_persistence.py`, `hub/tests/test_project_workspace.py`
- `openspec/changes/2026-08-03-local-multi-project-workspace/{proposal,design,tasks}.md` and its
  three delta specs
- `.claude/handoffs/2026-08-03-2118-...md`, `-2151-...md`, `-2227-...md`, `LATEST.md`

Phase 2 files (new this session):

- `hub/hub/db/engine.py` — gated the legacy Project/ApiKey bootstrap on an explicit
  `AW_BOOTSTRAP_PROJECT_ID` env var; `_seed_operator_credential` mints a credential directly when no
  legacy `ApiKey` exists to promote. Finished and tested.
- `src/agentweave/cli.py` — added `_hub_projects_url`, `_hub_open_project`, `_hub_project_app_url`,
  `_hub_resolve_launch_url`, `_hub_project_status_summary`; removed `_hub_project_label`; threaded
  `cwd: Optional[Path]` through `_hub_native_start` and `_wait_and_open_app`; `cmd_hub_start` now
  passes `cwd=Path.cwd()`; `_hub_native_scaffold` no longer writes the two bootstrap-project env
  lines; `cmd_status` uses the new project-status helper. Finished and tested. Ran through Black
  (`--fast`, line-length 100) after editing — see "Verification" for the reformat note.
- `hub/tests/test_project_lifecycle.py` — added
  `test_first_open_binds_the_single_unbound_legacy_project` and
  `test_second_open_after_legacy_binding_creates_a_new_project`, covering the previously-untested
  `_single_unbound_legacy_project` mechanism. Finished, passing.
- `hub/tests/test_migrations.py` — added
  `test_init_db_creates_zero_projects_without_legacy_bootstrap_env`, proving a fresh install with no
  `AW_BOOTSTRAP_PROJECT_ID` in the environment ends up with zero `Project`/`ApiKey` rows and exactly
  one `OperatorCredential`. Finished, passing. (New imports: `engine`, `OperatorCredential`.)
- `tests/test_hub_commands.py` — substantially expanded: updated the two existing
  `mock_native.assert_called_once_with(...)` assertions to include `cwd=Path.cwd()`; replaced the
  `.env`-file-based status tests with mocks of `_hub_project_status_summary`; added
  `TestProjectStatusSummary`, `TestOpenProjectCall`, and `TestNativeStartProjectLifecycle` classes
  (16 new tests) covering every task-2.1 scenario: first start, already-running instance (with and
  without `--app`), foreground start, zero-project direct start, open-call failure, and the
  URL-resolution plumbing. Finished, passing.

Untouched, verified still present and protected:

- `src/agentweave/templates/skills/handoff.md`, `resume.md`, `tests/test_handoff_resume_templates.py`

## Key decisions

- **Legacy bootstrap gated on an explicit env var, not removed outright.** The whole Hub test suite
  (`hub/tests/conftest.py`) depends on `init_db()` creating a `proj-test` row, via
  `os.environ.setdefault("AW_BOOTSTRAP_PROJECT_ID", "proj-test")` set once at conftest import time.
  Rather than break that (and every pre-existing installation's `.env`), the gate is
  "`AW_BOOTSTRAP_PROJECT_ID` present in `os.environ`" — true for the test suite and for any existing
  `.env` written before this change, false for a newly scaffolded `.env` (which no longer writes that
  key). Rejected: removing the bootstrap unconditionally — would have required rewriting all ~35
  migrated test files' fixture assumptions with no corresponding design requirement forcing it (the
  design's "zero projects" language is about *fresh* installs, not existing ones).
- **`_seed_operator_credential` mints a credential when there's nothing to promote**, rather than
  `init_db()` doing it inline. Keeps the "ensure exactly one OperatorCredential exists" invariant in
  one place regardless of which of the two `init_db()` branches ran. Rejected: leaving the old
  early-`return` (no candidate → no credential) — this would leave a zero-project fresh install
  unable to authenticate at all, which nothing else compensates for.
- **The project-open call is unconditional; only the browser window is gated by `--app`.** Read
  literally from design decision 6 ("whether the instance was already running or was just started,
  it reads the local operator credential and calls the same open-existing endpoint"). This means
  `_hub_native_start(app=False)` still performs the HTTP registration side effect. In production this
  is moot — bare invocation is the only reachable path and `main()` always sets `app=True` — but it's
  worth knowing if `_hub_native_start` is ever called directly with `app=False` outside a test.
- **`cwd=None` is the explicit "don't guess a workspace" signal**, used for the always-Docker branch
  of `cmd_hub_start` (untouched this session) and available for any future direct-Hub-start caller.
  `_hub_resolve_launch_url` short-circuits before ever calling `_hub_open_project` when `cwd is None`
  — no token fetch, no HTTP call, no printed warning.
- **Open failures are non-fatal by construction.** `_hub_open_project` catches all exceptions and
  returns `None`; `_hub_resolve_launch_url` treats `None` as "print a warning, open the bare Hub URL."
  A slow, unauthenticated, or offline Hub for this one call must never block `agentweave` from
  opening the app window.
- **CLI unit tests stub `sys.modules["hub.main"]`** rather than relying on the real editable-installed
  `hub` package importing cleanly. See "Dead ends" — this repo's own `hub/` directory (no
  `hub/__init__.py`, only `hub/hub/__init__.py`) can shadow the real package as an empty namespace
  package when cwd is the repo root, which is exactly the cwd these tests run under from
  `pytest tests/test_hub_commands.py` at the repo root.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- User commands in this workstream: `$resume`, `approve`, `continue`.
- Do not invoke shipped `aw-*` product skills against this framework repository.
- Re-read the proposal, design, all three delta specs, and tasks before every phase; demonstrate
  failing contracts before implementation. (Done this session: reread `tasks.md`, `design.md`,
  `specs/app-lifecycle/spec.md`, `specs/local-project-workspace/spec.md` before starting phase 2.)
- Preserve the three protected untracked handoff/resume template files (see "Files touched").
- From standing memory (not this session's chat, but binding across this workstream): commit each
  completed task/checkpoint without asking first; verify prior session's claimed work still
  functions on every resume, and record that directive in every handoff (done above, in Step 2 of
  `/resume`: re-ran `pytest hub/tests -q` before starting new work — 546 passed, matching the
  phase-1 handoff's claim exactly).

## Dead ends

- **`import hub.main` and `importlib.util.find_spec("hub.main")` can silently resolve to the wrong
  thing when the process cwd is the repo root.** This repo's `hub/` directory has no
  `hub/__init__.py` (only `hub/hub/__init__.py` does) — with the repo root on `sys.path` (as happens
  when a script or pytest is invoked with cwd = repo root), plain `import hub` can resolve to
  `AgentWeave/hub/` as an implicit PEP 420 namespace package instead of the real
  editable-installed `agentweave-hub` package (which points at `AgentWeave/hub/hub/`). The symptom
  was `ImportError: cannot import name '__version__' from 'hub' (unknown location)` — appearing
  inside `_hub_native_start`'s own `except ImportError` handler, so it silently printed
  "agentweave-hub is not installed" instead of raising visibly. Reproduced standalone:
  `python -c "import os; os.environ['DATABASE_URL']='...'; import hub.main"` from repo root fails
  the same way; the same import from a subdirectory (or with a clean `sys.path`) succeeds. Fixed in
  the CLI tests by stubbing `sys.modules["hub"]`/`sys.modules["hub.main"]` directly
  (`TestNativeStartProjectLifecycle._stub_hub_main` in `tests/test_hub_commands.py`) rather than
  depending on which package a bare `import hub` happens to resolve to. This is a *test-environment*
  artifact, not a product bug — real installs don't have a same-named sibling source directory on
  `sys.path` — but it's worth knowing if any other CLI test ever needs a real `hub.main` import.
- **`patch("agentweave.cli.threading.Thread")` and `patch("agentweave.cli.uvicorn.run")` don't work**
  — `threading` and `uvicorn` are imported *locally* inside `_hub_native_start`/`_wait_and_open_app`,
  not as `agentweave.cli` module-level attributes, so `agentweave.cli.threading` doesn't exist for
  `patch` to attach to. Fixed by patching their real dotted paths (`"threading.Thread"`,
  `"uvicorn.run"`) instead — this works regardless of how the code under test imports them, since
  both patch targets and the local `import threading`/`import uvicorn` statements resolve to the
  same singleton module object via `sys.modules`.
- **`find_spec("hub.main")` raises `ValueError: hub.main.__spec__ is None`** if `sys.modules["hub.main"]`
  is a bare `types.ModuleType("hub.main")` with no `__spec__` set. The stub needs
  `fake_main.__spec__ = MagicMock()` (or any non-`None` value) for the early
  `_imp_util.find_spec("hub.main") is None` guard in `_hub_native_start` to pass.
- Repeated across this session (same as phase 1's note): running the Hub test suite from the repo
  root leaks an untracked, gitignored `.agentweave/logs/events.jsonl` at the framework root via
  existing `Path.cwd()` runtime behavior. Removed twice this session (after the initial full-suite
  run, and again after the final verification pass). Phase 3 (`3.2`–`3.4`) owns the actual fix.

## Verification

Ran and passed, in this order:

- `pytest hub/tests/test_project_lifecycle.py -q` — 10 passed (2 new legacy-binding tests).
- `pytest hub/tests -q` (full Hub suite, after the engine.py change) — 549 passed, 6 skipped.
- `pytest tests/test_hub_commands.py -q` (full CLI file, after the cli.py + test changes) —
  37 passed.
- `pytest tests -q` (full CLI suite) — 367 passed, 3 skipped.
- `pytest hub/tests -q` (full Hub suite, re-run after CLI changes, since both trees are touched by
  this phase) — 549 passed, 6 skipped, 13 Alembic deprecation warnings, 109.67s.
- `python -m black --fast --line-length 100 hub/hub/db/engine.py hub/tests/test_migrations.py
  hub/tests/test_project_lifecycle.py src/agentweave/cli.py tests/test_hub_commands.py` — reformatted
  `cli.py` and `test_hub_commands.py` (whitespace/line-wrap only); re-ran both affected test files
  afterward and they still passed (367 CLI tests total). `--fast` was used because the installed
  Black (26.5.1) cannot AST-verify against this environment's Python 3.11 — same known quirk noted
  in the phase-1 handoff, not new this session.
- `python -m compileall -q hub/hub hub/tests src/agentweave tests` — passed, no output.
- `openspec validate --all --strict --no-interactive` — 21 passed, 0 failed.
- `git diff --check` — passed (only a harmless CRLF-normalization warning on `cli.py`, not an error;
  exit code 0).
- Confirmed no forbidden root artifacts: `.agentweave/`, `agentweave.yml`, `spec/` all absent after
  cleanup (the leaked `.agentweave/logs/` was removed twice — see "Dead ends").

Not yet tested by design (unchanged from phase 1, still deferred to later phases):

- Live end-to-end exercise of the new `agentweave` bare-invocation → open-project → app-window flow
  against a real running Hub. Everything above is unit-level (mocked HTTP/subprocess/thread calls).
  No `testbed/` live run was performed this session.
- CLI/Hub frontend behavior, Docker, PostgreSQL — still out of scope until their respective phases.
- Ruff and mypy were not run (same reasoning as phase 1: no repository dependency was added solely
  to run them).
- The "UI ... locate repair path for a directly started Hub" half of task 2.4's description was
  **not** built as a UI — only the API-level mechanism (idempotent legacy binding via
  `open_existing`, plus the pre-existing `relocate` endpoint) was verified. A dedicated locate/repair
  *view* is explicitly owned by phase 5 task 5.7 ("Build missing-directory/locate/settings views"),
  and the current frontend cannot even reach project-scoped routes until phase 4 rewires it (noted
  as an intentional mismatch since phase 1). Task 2.4 is checked off in `tasks.md` on the strength of
  the API/CLI mechanism being real and tested, not a UI that doesn't exist yet — flagging this
  explicitly so a future session doesn't assume a locate screen already exists.

## Git state

- Branch `hub-native-experience`; HEAD unchanged at `37a6854` (`handoff: runner agent charter
  separation complete`) — nothing has been committed this session.
- Worktree is dirty with all of phase 0/1's files plus this session's five phase-2 files
  (`hub/hub/db/engine.py`, `src/agentweave/cli.py`, `hub/tests/test_migrations.py`,
  `hub/tests/test_project_lifecycle.py`, `tests/test_hub_commands.py`). Full `git status --short`
  output is reproduced at the top of this session's transcript; nothing is staged.
- `git diff --stat HEAD`: 54 files changed, 1356 insertions(+), 701 deletions(-) (up from phase 1's
  52/884/652 — the delta is this session's five files).
- No upstream configured; unpushed-commit comparison not applicable.
- Root `.agentweave/`, `agentweave.yml`, `spec/` confirmed absent after this session's cleanup.

**A commit has not yet been made for phase 2.** Per standing preference ("commit each completed
task/checkpoint without asking first"), the very next action on resume should be to stage exactly
the five phase-2 files plus the `tasks.md` checkbox update and this handoff/`LATEST.md`, and commit
— do **not** `git add -A` (phase-0/1 files are still legitimately part of the same in-flight change
and were already reviewed in the phase-1 handoff, but staging everything blindly is still the wrong
habit to reinforce). A reasonable split: one commit for phase 2's product+test changes, a second
`handoff:` commit for the tasks.md checkboxes + handoff files, matching the phase 0/1 pattern visible
in `git log`.

## Next steps

1. Commit phase 2 (see "Git state" above for the suggested split), then re-read the approved
   proposal, design, all three delta specs, and `tasks.md` before starting phase 3.
2. Begin phase 3 test-first at task 3.1: write two-repository tests for direct/queued runs, context
   materialization, workspace path listing, worktree create/list/conflicts/release, git diagnostics,
   and concurrent agents — this is the phase that actually fixes the root cause of the leaking
   `.agentweave/` residue noted in "Dead ends" (every project-related Hub `Path.cwd()` call must move
   to `ProjectWorkspace`).
3. Inspect every remaining `Path.cwd()` call in `hub/hub/` (agent_trigger.py, workspace.py,
   worktrees.py, session cleanup, git diagnostics — the exact list is task 3.2's scope) before
   implementing; `hub/hub/project_workspace.py`'s `resolve_project_workspace(project_id)` already
   exists from phase 0 as the target all of these should migrate to.
4. Implement 3.2 (replace `Path.cwd()`), 3.3 (remove absolute `work_dir`, add traversal/symlink
   escape tests), 3.4 (remove the global `.agentweave/session.json` roster fallback).
5. Verify project-correct runtime paths and no cross-project file/process effects (3.7), then write
   phase 3's handoff (3.8).

## Open questions

None. The approved design supplies phase 3's behavior. Any discovery that changes that design
requires a revised specification and renewed approval.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — phase 3's task list
  (3.1–3.8), and confirmation that phase 2 (2.1–2.6) is checked off.
- `openspec/changes/2026-08-03-local-multi-project-workspace/design.md` — decision 3 ("One project
  workspace service owns filesystem resolution") is phase 3's mandate.
- `hub/hub/project_workspace.py` — the existing `resolve_project_workspace` / canonicalization
  service that phase 3's `Path.cwd()` call sites must migrate to.
- `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/workspace.py`, `hub/hub/api/v1/worktrees.py` —
  read these first to inventory remaining `Path.cwd()` call sites before writing phase 3 tests.
- `src/agentweave/cli.py` — this session's changes (search for `_hub_resolve_launch_url`,
  `_hub_open_project`, `_hub_native_scaffold`) if phase 3 or later needs to understand the CLI's
  current project-open flow.
