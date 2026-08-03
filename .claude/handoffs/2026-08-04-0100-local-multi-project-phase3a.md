# Handoff: Local multi-project workspace phase 3.1-3.4 complete (partial phase 3)

**Date:** 2026-08-04T01:00:00+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `eb54db7`
**Agent:** Claude Code (Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-08-04-0000-local-multi-project-phase2.md`
**Status:** chunk complete — tasks 3.1-3.4 implemented and verified; tasks 3.5-3.8 (the rest of
phase 3) remain open and are the next work

## Goal

Implement the approved local multi-project workspace change so one local AgentWeave instance can
own multiple directory-backed projects without filesystem, authentication, event, or frontend-state
leakage. This chunk (a deliberate partial slice of phase 3, "Runtime and filesystem isolation")
replaces every project-related Hub `Path.cwd()` call with the project-scoped workspace resolver,
so agent triggers, worktrees, and workspace-path listing are correctly rooted per project instead
of sharing the Hub process's working directory. This directly fixes the root cause the phase 1/2
handoffs flagged as a recurring dead end: test/dev runs leaking `.agentweave/context/*.md` and
`.agentweave/logs/` at the framework repository root.

## Current state

- Tasks 0.1-3.4 are complete and checked off in
  `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`. Tasks 3.5-3.8 are NOT done
  — see "Next steps". Phases 4-6 remain entirely pending.
- No project-aware Hub code calls `Path.cwd()` anymore — verified by
  `grep -rn "Path\\.cwd()" hub/hub` returning nothing. The only remaining `cwd`-adjacent references
  in `hub/hub/` are unrelated: `pty_runner.py`'s own `cwd` *parameter* (already receives the
  resolved path from its caller) and `worktrees.py`'s docstring/parameter naming (already
  parameterized, never implicit).
- `agent_trigger.py`'s `trigger_agent_directly` — shared by both the immediate `/agent/trigger`
  HTTP path and the scheduler's queued-delivery path (`turn_scheduler.py` calls it too, per its own
  docstring) — now resolves `project_workspace.resolve_project_workspace(session, project_id)`
  once and uses `.root` as `repo_root`, instead of `Path.cwd()`. A workspace resolution failure
  (missing/unbound/conflicting directory) raises `TriggerAgentError(409, ...)`.
- `work_dir` (on `TriggerAgentRequest` and `trigger_agent_directly`) is now **project-relative
  only**, resolved through `ProjectWorkspace.resolve_relative()` (existing since phase 0), which
  rejects absolute paths, `..` traversal, control characters, and symlink escapes in one place. The
  old near-unchecked absolute-path acceptance is gone. The `/agent/trigger` route does the same
  resolution early (before queuing) as a fast-fail; `trigger_agent_directly` is the authoritative
  enforcement point for both the immediate and queued paths.
- `hub/hub/api/v1/workspace.py`'s `GET /workspace/paths` and `hub/hub/api/v1/worktrees.py`'s
  `GET /worktrees` and `GET /worktrees/conflicts` now resolve the project's real root the same way,
  returning `409` with the typed workspace error detail when unavailable.
- `hub/hub/api/v1/session_sync.py`'s worktree-release-on-agent-removal step now resolves the
  project workspace too; a resolution failure is swallowed (best-effort, matching the existing
  git-failure handling right above it) rather than failing the roster sync itself.
- `hub/hub/api/v1/agents.py`'s `_get_session_data` no longer has a `.agentweave/session.json`
  filesystem fallback. It reads only the `ProjectSession` DB table now (populated by
  CLI/watchdog `push_session()`). The removed fallback could only ever represent one project (the
  legacy bootstrap one, gated by `AW_BOOTSTRAP_PROJECT_ID`) and would have leaked that project's
  configured agents across every other project's boundary. `json`, `os`, and `Path` imports were
  removed from that file as a result (all now unused there).
- **Test infrastructure change** (in `hub/tests/conftest.py`, affects the whole Hub suite): the
  bootstrap project (`proj-test`) stays deliberately unbound by `init_db()` (no
  `working_directory`) — `test_project_lifecycle.py`'s phase-2 legacy-binding tests exercise
  binding it themselves and would break if some other fixture bound it first. Since virtually
  every agent-trigger/worktree/workspace-path test in the suite now needs
  `resolve_project_workspace` to succeed for `proj-test` to keep passing, a new autouse fixture
  `_default_project_workspace` fakes workspace resolution to *any* project_id at that test's own
  disposable `tmp_path`, by default — mirroring the existing `_no_real_worktree_provision`
  autouse-stub-by-default convention already in that file. A new `bind_project_workspace` fixture
  registers a *real* directory for `proj-test` (via `ProjectLifecycleService.open_existing`, the
  same path a genuine `agentweave` invocation uses) and restores the real resolver for that one
  test, replacing the now-inert `monkeypatch.chdir(repo)` pattern used in 11 places across
  `test_agent_trigger.py`, `test_session_sync.py`, `test_workspace_paths.py`, and `test_worktrees.py`.
- New file `hub/tests/test_project_scoped_runtime.py` (task 3.1's actual two-repository-isolation
  deliverable): registers two real, distinct project directories and proves neither's context file,
  worktree, or workspace listing ever appears under the other's directory or API responses.
  Includes traversal/absolute-path/symlink-escape rejection tests for the new `work_dir` semantics.
- Full suite: 555 passed, 7 skipped (one new skip: the symlink-escape test skips cleanly when this
  Windows environment denies symlink creation without Developer Mode/admin — same documented
  caveat as `test_worktrees.py`'s existing symlink test).

## Files touched

Product files:

- `hub/hub/api/v1/agent_trigger.py` — `repo_root` resolution, `work_dir` project-relative
  resolution (both in `trigger_agent_directly` and the early route-level check in `trigger_agent`),
  updated `TriggerAgentRequest.work_dir` field description. Finished and tested.
- `hub/hub/api/v1/agents.py` — removed the `.agentweave/session.json` filesystem fallback and its
  now-unused `json`/`os`/`Path` imports. Finished and tested.
- `hub/hub/api/v1/session_sync.py` — worktree-release repo_root now resolved via
  `project_workspace`, best-effort on failure. Finished and tested.
- `hub/hub/api/v1/workspace.py` — `GET /workspace/paths` resolves the project workspace; added
  `session` dependency. Finished and tested.
- `hub/hub/api/v1/worktrees.py` — `GET /worktrees` and `GET /worktrees/conflicts` resolve the
  project workspace via a shared `_resolve_repo_root` helper; added `session` dependency. Finished
  and tested.

Test files:

- `hub/tests/conftest.py` — new `_default_project_workspace` (autouse) and `bind_project_workspace`
  fixtures; new imports (`async_session_factory`, `resolve_project_workspace` aliased as
  `_REAL_RESOLVE_PROJECT_WORKSPACE`). Finished and tested.
- `hub/tests/test_agent_trigger.py` — 5 `monkeypatch.chdir(repo)` call sites replaced with
  `await bind_project_workspace(repo)`; one dead `monkeypatch.chdir` removed entirely (the test
  never needed a real directory). Finished and tested.
- `hub/tests/test_session_sync.py` — 3 call sites replaced the same way.
- `hub/tests/test_workspace_paths.py` — 2 call sites replaced.
- `hub/tests/test_worktrees.py` — 1 call site replaced.
- `hub/tests/test_project_scoped_runtime.py` — new file, task 3.1's dedicated two-project
  isolation tests (6 tests + 1 symlink test that skips on this environment). Finished and passing.

Specification file:

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — checked off 3.1-3.4.
  **Not yet committed** — staged for the next commit alongside this handoff, matching the phase
  0-2 pattern (product/test commit, then a separate `handoff:` commit for tasks.md + handoff files).

Phase 0/1/2 files remain dirty and untouched this session (see the phase 1 and phase 2 handoffs
for their detail) — full `git status --short` output is reproduced at the top of this session's
transcript.

## Key decisions

- **`proj-test` stays unbound by default; a new autouse fixture fakes workspace resolution instead
  of binding it for real.** The alternative (bind `proj-test` to a real tmp_path inside the shared
  `app` fixture) would have broken `test_project_lifecycle.py`'s existing phase-2 tests, which
  specifically assert `proj-test` starts unbound. Faking `resolve_project_workspace` itself (not
  touching the `Project` DB row) keeps those two concerns fully independent: the DB row's bound/unbound
  state is real and untouched; only what the API layer sees when it *asks* for the workspace is
  faked by default.
- **The two production modules that call `resolve_project_workspace`** (`agent_trigger.py`,
  `workspace.py`, `worktrees.py`, `session_sync.py`) **import the module, not the function**
  (`from ... import project_workspace`, then `project_workspace.resolve_project_workspace(...)`).
  This is deliberate: it lets tests patch `hub.project_workspace.resolve_project_workspace` once
  and have every caller see the patch, avoiding the classic `from x import y` staleness problem
  where a caller's own bound name is a separate reference unaffected by patching the origin module.
- **`work_dir`'s early route-level check treats any `ProjectWorkspaceError` as a 400.** This
  conflates "project unavailable" (arguably 409) with "invalid relative path" (400) at that one
  early fast-fail point; the authoritative check inside `trigger_agent_directly` still raises the
  correct code for each. Flagged rather than fixed now because task 3.5/3.6 (not yet done) is where
  the "unavailable" policy — refuse new input, with what status/detail — gets its real design pass;
  revisit this exact line then rather than guessing the right shape twice.
- **Session-sync's worktree-release step swallows a workspace-resolution failure silently**,
  matching the existing pattern immediately below it (a git failure during release is logged and
  skipped, not raised) — the roster sync itself is what that endpoint exists for, and must not fail
  because a worktree release, a secondary side effect, couldn't resolve a directory.
- **A dedicated new test file, not folding into existing ones.** `test_project_scoped_runtime.py`
  is the one place that actually proves *two different, real, concurrently-registered* project
  directories stay isolated — no existing file had two real projects at once. Every other touched
  test file only needed the mechanical `chdir` → `bind_project_workspace` swap for its existing
  single-project scenario.

## Constraints and user directives (verbatim)

- "This repo has no AgentWeave session, and must not acquire one."
- "Do the work directly."
- "Write to `openspec/changes/<date>-<name>/`."
- "Nothing under `.agentweave/`, `agentweave.yml`, or `spec/` should exist at the repository root."
- "Also: stage paths explicitly. `git add -A` sweeps in untracked `.claude/handoffs/` scratch."
- User commands in this workstream: `$resume`, `approve`, `continue`. (This chunk was entered via
  `CONTINUE`.)
- Do not invoke shipped `aw-*` product skills against this framework repository.
- Re-read the proposal, design, all three delta specs, and tasks before every phase; demonstrate
  failing contracts before implementation. (Done at the start of this chunk: reread `tasks.md`,
  and the two specs not yet read this session — `proposal.md` and
  `specs/agent-conversation-workspace/spec.md` — before starting; `design.md` and the other two
  specs were already read earlier this session per the phase 2 handoff.)
- Preserve the three protected untracked handoff/resume template files (unchanged, still present:
  `src/agentweave/templates/skills/{handoff,resume}.md`, `tests/test_handoff_resume_templates.py`).
- From standing memory: commit each completed task/checkpoint without asking first (done — one
  commit this chunk, `eb54db7`, correctly titled this time); verify prior session's claimed work
  still functions on every resume (done at the start of this session, before phase 3 work began).
- **New this session, learned the hard way — earlier commit-message mistake:** when composing a
  commit title, always name the *actual current change* (`local multi-project workspace`), not a
  copy-pasted prefix from a different, already-archived change's commit style
  (`runner/agent/charter`). Caught immediately and amended after asking the user first, since it
  was a still-local, unpushed commit — but double-check the title against the actual openspec
  change directory name before committing, not just against `git log`'s recent style.

## Dead ends

- **A shared `MagicMock` `PtySession.spawn` fake reused across two sequential trigger calls hangs
  the second run's background task.** `_fake_pty(lines)` returns
  `MagicMock(return_value=session)` where `session.read.side_effect = [*lines, ""]` — that
  `side_effect` list is a one-shot iterator on the *same* session object every time `spawn()` is
  called. Triggering project A, awaiting its background run to completion, then triggering project
  B with the *same* `fake_spawn` starves project B's read loop (the iterator is already exhausted),
  and the `while agent_trigger._background_runs: await task` loop then waits forever on a task that
  never reaches completion. Symptom: the test process hangs with zero output, even under `-s`,
  because pytest's own stdout capture-to-file is block-buffered (nothing appears until the process
  ends, which it never did without `PYTHONUNBUFFERED=1` forcing a flush during interactive
  debugging). **Fix:** create a fresh `_fake_pty(...)` immediately before *each* trigger call, not
  once for a whole multi-trigger test. This bit twice while writing `test_project_scoped_runtime.py`
  (context-materialization test and concurrent-worktrees test) before the pattern was isolated via
  a minimal standalone repro test outside the real one.
- **`monkeypatch.setattr(worktrees, "resolve_agent_workspace", worktrees.resolve_agent_workspace)`
  is a silent no-op**, not a restore-to-real. By the time a test body executes,
  `worktrees.resolve_agent_workspace` has *already* been overwritten by the autouse
  `_no_real_worktree_provision` fixture to its no-op lambda — reading the attribute at that point
  and reassigning it to itself just keeps the no-op. The correct pattern (already used by
  `test_agent_trigger.py` and now by `test_project_scoped_runtime.py`) is to capture the real
  function in a module-level constant (`_REAL_RESOLVE_AGENT_WORKSPACE = worktrees.resolve_agent_workspace`)
  at collection time, *before* any fixture has run, and monkeypatch back to that captured
  reference, not to whatever the live attribute currently holds.
- **This repo's own `hub/` source directory can shadow the real editable-installed `hub` package**
  when a script or `import hub.main` runs with the repository root as (or ahead of) `sys.path[0]`:
  `AgentWeave/hub/` has no `__init__.py` (only `AgentWeave/hub/hub/` does), so Python can resolve
  bare `import hub` to the outer directory as an implicit PEP 420 namespace package, and
  `hub.main`'s own `from . import __version__` then fails with a confusing
  `ImportError: cannot import name '__version__' from 'hub' (unknown location)`. This was already
  documented in the phase 2 handoff for CLI tests; it resurfaced again this session while debugging
  the hang above (a throwaway repro script run via `python -c "..."` from the repo root hit the
  exact same shadowing). Not a product bug — no real install has a same-named sibling source
  directory on `sys.path` — but worth remembering before assuming any `import hub` failure in a
  quick script means something is actually broken.
- Root `.agentweave/logs/` residue (the same cause noted in phase 1/2's handoffs) did **not**
  reappear after this chunk's changes — confirmed by checking for it after the full suite run and
  finding nothing to clean up, which is expected: this chunk is the actual fix for that root cause
  (task 3.2), not a workaround. If it reappears in a later phase, that would mean a *new*
  cwd-touching call site was introduced, not a regression of this one.

## Verification

Ran and passed, in this order:

- `grep -rn "Path\.cwd()" hub/hub` — zero matches (down from 5 call sites across 4 files at the
  start of this chunk).
- `pytest tests/test_project_scoped_runtime.py -q` (new file, in isolation, after fixing the hang
  above) — 6 passed, 1 skipped (symlink escape test, this environment denies symlink creation).
- `pytest hub/tests -q` (full Hub suite) — 555 passed, 7 skipped, 13 Alembic deprecation warnings,
  ~98s, run twice (once before Black reformatting, once after) with identical pass counts both times.
- `pytest tests -q` (full CLI suite, unaffected by this Hub-only chunk but re-run for completeness
  since it shares this session) — 367 passed, 3 skipped.
- `python -m black --fast --line-length 100` on all product+test files touched this chunk —
  reformatted `agent_trigger.py`, `conftest.py`, and `test_project_scoped_runtime.py`
  (whitespace/line-wrap only); re-ran the full Hub suite afterward, still 555/7.
- `python -m compileall -q hub/hub hub/tests src/agentweave tests` — passed, no output.
- `openspec validate --all --strict --no-interactive` — 21 passed, 0 failed.
- `git diff --check` — passed (harmless CRLF-normalization warnings only, exit code 0).
- Confirmed no forbidden root artifacts: `.agentweave/`, `agentweave.yml`, `spec/` all absent after
  the final test run — and, unlike phase 1/2, nothing needed cleaning up this time (see "Dead
  ends").

Not yet tested by design (unchanged scope from earlier phases, plus this chunk's own remainder):

- **Tasks 3.5-3.8 themselves are simply not implemented yet** — see "Next steps". In particular,
  there is currently **no enforcement that new operator input is refused while a project's
  directory is unavailable** beyond what `resolve_project_workspace` already raises incidentally
  (409/400) when called; the *policy* (refuse new input, keep the queue durable, pause autonomous
  work, re-evaluate on repair) has no dedicated code or tests yet. Do not assume this is handled.
- Live end-to-end exercise under `testbed/` with two real registered projects — everything above is
  unit-level (in-memory SQLite, mocked PTY spawn).
- CLI/Hub frontend behavior, Docker, PostgreSQL — still out of scope until their respective phases.
- Ruff and mypy were not run (same reasoning as phases 1/2).
- Windows symlink test remains skipped where the OS denies link creation (same as noted in the
  phase 1 handoff for a different test file).

## Git state

- Branch `hub-native-experience`; HEAD is `eb54db7`
  (`local multi-project workspace phase 3.1-3.4: project-rooted runtime paths`) — one new commit
  since the phase 2 handoff (`84c5f4a`).
- Worktree is dirty with: `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`
  (this chunk's checkbox updates, not yet committed) plus all phase 0/1/2 files already noted dirty
  in the prior handoffs (untouched this chunk). No files are staged right now.
- `git diff --stat HEAD~2` (i.e. since the phase 2 handoff commit): 54 files changed, 1735
  insertions(+), 731 deletions(-) (up from phase 2's 1356/701 — the delta is this chunk's 11 files
  plus tasks.md).
- No upstream configured; unpushed-commit comparison not applicable.
- Root `.agentweave/`, `agentweave.yml`, `spec/` confirmed absent after this session's work.

**The tasks.md checkbox update and this handoff have not yet been committed.** Per the established
pattern (phase 0/1/2 all did this as a separate `handoff:` commit), the very next action on resume
should be: stage `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md`,
`.claude/handoffs/LATEST.md`, and this handoff file, then commit with a `handoff:` message — do
**not** `git add -A`.

## Next steps

1. Commit the tasks.md checkbox update and this handoff (see "Git state" above).
2. Re-read the approved proposal, design, and the `local-project-workspace` delta spec's
   "Unavailable project directories preserve state and pause execution" requirement before starting
   task 3.5 — that requirement's exact scenarios are what 3.5's tests must cover.
3. Begin phase 3's remainder test-first at task 3.5: write unavailable-directory tests covering (a)
   new operator input refused with a clear diagnostic, (b) an already-queued `InboundQueueEntry`
   remains durable (not silently dropped) when its project's directory later becomes unavailable,
   (c) autonomous/scheduled starts pause with an attributed event rather than erroring loudly, and
   (d) after a successful relocate/repair, queued work is re-evaluated under current budgets/hop
   limits without any job having been silently disabled.
4. Inspect `hub/hub/turn_scheduler.py` (not yet read this session) before implementing 3.6 — that's
   almost certainly where "pause autonomous work for an unavailable project" and "re-evaluate on
   repair" belong, alongside the existing `schedule_agent` call already wired into
   `agent_trigger.py`'s queued path. Also revisit the "Key decisions" note above about
   `agent_trigger.py`'s early `work_dir` check conflating unavailable-vs-invalid under one 400 —
   decide the right split now that 3.5/3.6's design is being worked out for real.
5. Implement 3.6 (scheduling pause/repair behavior, safe relocation guards), then verify (3.7)
   against the full suite plus a live `testbed/` check if time allows, and write phase 3's full
   handoff (3.8) covering the entire phase 0-3 arc.

## Open questions

None. The approved design supplies phase 3's behavior, including the unavailable/repair scenarios
task 3.5/3.6 still need to implement. Any discovery that changes those contracts requires a revised
specification and renewed approval.

## Read on resume

- `openspec/changes/2026-08-03-local-multi-project-workspace/tasks.md` — confirms 3.1-3.4 checked,
  3.5-3.8 not.
- `openspec/changes/2026-08-03-local-multi-project-workspace/specs/local-project-workspace/spec.md`
  — the "Unavailable project directories preserve state and pause execution" requirement (already
  read this session, but re-read at the start of 3.5 per the working protocol).
- `hub/hub/turn_scheduler.py` — not yet read this session; almost certainly where 3.6's
  pause/repair logic belongs.
- `hub/hub/api/v1/agent_trigger.py` — this chunk's `trigger_agent_directly` and the `/trigger`
  route's early `work_dir` check (see "Key decisions" note on its imprecise status-code split).
- `hub/tests/conftest.py` — the new `_default_project_workspace`/`bind_project_workspace` fixtures
  this chunk added; 3.5's unavailable-directory tests will likely need a *third* variant (a project
  that resolves to a directory that then becomes unavailable mid-test) built on the same pattern.
- `hub/tests/test_project_scoped_runtime.py` — this chunk's two-project isolation tests, the
  natural home for 3.5's own unavailable-directory tests if they fit the same shape.
