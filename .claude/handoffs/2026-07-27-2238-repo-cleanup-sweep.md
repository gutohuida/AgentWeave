# Handoff: Repo-wide cleanup sweep — lint gap, dead code, gitignore, versions, generated skills

**Date:** 2026-07-27T22:38+0100 · **Branch:** `master` · **HEAD:** `968b8db`
**Agent:** Claude Code (Opus 5, `claude-opus-5`)
**Previous handoff:** `.claude/handoffs/2026-07-27-2144-spec-root-rename.md`
**Status:** chunk complete — all cleanup work done and verified, **nothing committed**

> **This is a different work thread from the previous handoff.** The spec-root-rename thread
> and its parallel AgentWeave-1.0 thread
> (`.claude/handoffs/2026-07-26-2230-spec-rev9-consistency-pass.md`, 22 unapplied findings)
> are both still live and untouched by this session. Their uncommitted files are still sitting
> in this working tree — see "Files I did NOT touch" below, and do not attribute them to me.

## Goal

The user asked: "Scan this project and find ways to clean it up." I audited the repo, reported
findings ranked by severity, and then applied them top-down as the user approved each tier.

The *why*: this repo has drifted in the ways a fast-moving multi-package project does — CI only
ever linted one of three Python trees, generated artifacts got committed and then went stale,
and version numbers were copy-pasted into prose. None of it was breaking the build, which is
exactly why it accumulated.

## Current state

**All approved cleanup is done and verified. Nothing is committed.** The working tree now
carries my cleanup changes layered on top of two earlier sessions' uncommitted spec work.

Completed, in the order the user approved them:

1. **Finding #1 (packaging) — RETRACTED, was a false alarm.** I claimed
   `templates/skills/references/html-spec-conventions.md` was missing from the wheel because
   `pyproject.toml`'s `package-data` doesn't list that subdirectory. Wrong: I had inspected
   `dist/agentweave_ai-0.38.1-py3-none-any.whl`, and `references/` was only added in v0.40.0
   (commit `4f86937`), so it didn't exist at that version. Building the current tree with an
   **unmodified** `pyproject.toml` produces a wheel that **does** contain the file — it ships via
   MANIFEST.in's `recursive-include` plus setuptools' `include_package_data`, which defaults to
   true for pyproject-configured projects. I reverted `pyproject.toml` to HEAD and kept only a
   guard test.
2. **Finding #2 (lint coverage gap) — done.** 149 ruff errors → 0 across `src/`, `hub/`, `tests/`.
   CI and the Makefile now lint and format-check all three trees.
3. **Findings #4/#5 (dead code) — done.** 757 lines of unreferenced Hub UI plus 6 dead functions
   in `src/`.
4. **Finding #6 (.gitignore) — done.** 126 → 111 lines before the skills block was added.
5. **Finding #7 (stale versions) — done.**
6. **Finding #3 (generated skills) — done, user chose "stop committing them".**

**Known-red, pre-existing, NOT caused by this session:** 3 failures in
`hub/tests/test_migrations.py` (`test_alembic_upgrade_head_fresh_file_db`,
`test_alembic_0008_alters_text_to_string_500`, `test_init_db_runs_alembic_for_file_db`).
I verified these fail identically at HEAD via `git stash`. `make test-all` was already red.

## Files touched

All paths relative to `C:\Users\huida\Documents\projects\AgentWeave`.

### Config / CI (mine, finished)

- `.github/workflows/ci.yml` — lint step `ruff check src/` → `ruff check src/ hub/ tests/`;
  format step `black --check src/` → `black --check src/ hub/hub/ hub/tests/ tests/`.
  mypy scope deliberately left at `src/` only.
- `Makefile` — same widening for `lint` and `format`; added a new `format-check` target and added
  it to `.PHONY`.
- `pyproject.toml` — added `[tool.ruff.lint.isort] known-first-party = ["agentweave", "hub"]` and
  `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls` for `fastapi.Depends/Query/Path/Security`.
  **`[tool.setuptools.package-data]` and `[build-system] requires` are untouched at HEAD values** —
  I edited them early, then reverted when finding #1 turned out to be wrong.
- `.gitignore` — see "Key decisions" 4 and 6. Net: removed ~15 dead lines, fixed the `openspec/`
  contradiction, added a 22-entry generated-skills block.

### Lint fixes (mine, finished)

Substantive, hand-made:
- `hub/hub/db/engine.py` — `AIJob`/`JobRun`/`ProjectInstructions` are imported for their
  SQLAlchemy mapper-registration side effect, feeding `Base.metadata.create_all` at line ~114.
  Ruff's autofix would have deleted them and silently stopped those tables being created. Rewrote
  as an explicit `# noqa: F401` block with a comment saying why.
- `hub/hub/api/v1/jobs.py` — removed dead `CroniterBadCronError` import + rebind; added `from e`
  to 4 raises.
- `hub/hub/api/v1/agents.py` — hoisted duplicated `CONTACT_MODES` out of two functions into module
  constant `_CONTACT_MODES` (line ~42); added `import contextlib` and one `contextlib.suppress`;
  2 ternary simplifications; `from exc` on the role-not-found raise; **reverted** a `dict()`
  simplification (see Dead ends).
- `hub/hub/api/v1/tasks.py`, `hub/hub/mcp_server.py` — `from e` / `from exc` on raises.
- `hub/hub/api/v1/setup.py` — `ApiKey.revoked == False` → `ApiKey.revoked.is_(False)`; collapsed a
  trailing `if/return True/return False`.
- `hub/hub/api/v1/agent_chat.py` — collapsed a nested `if` into one 4-clause condition and dedented
  its body (lines ~126-145).
- `hub/hub/api/v1/agent_trigger.py` — collapsed nested `if` for `work_dir` validation.
- `hub/hub/sse.py` — added `import contextlib`, one `suppress`, one `# noqa: SIM105` with reason.
- `hub/tests/test_auth.py` — 2× `assert False` → `raise AssertionError(...)`.
- `hub/tests/test_jobs.py` — try/except-ImportError probe → `importlib.util.find_spec("croniter")`.
- `hub/tests/test_mcp_server.py`, `tests/test_hub_commands.py`, `tests/test_activate.py` — dropped
  unused `result =` assignments (4 in test_activate, by exact line number).
- `tests/test_cli.py`, `tests/test_watchdog.py` — renamed ambiguous loop var `l` → `line` (3 sites).
- `tests/test_hub_commands.py` — added `# noqa: SIM117` with a comment; see Dead ends.

Formatting-only (my `black` run, no logic change):
- `hub/hub/api/v1/__init__.py`, `hub/hub/api/v1/spec.py`, `hub/hub/db/models.py`,
  `hub/hub/scheduler.py`, `hub/hub/schemas/agents.py`
- `hub/hub/migrations/versions/0001`–`0009` (9 files, ±1 line each, import sorting only)
- `hub/tests/conftest.py`, `test_agent_chat.py`, `test_agents.py`, `test_bola.py`,
  `test_migrations.py`, `test_setup.py`, `test_spec.py`, `test_sse.py`, `test_tasks.py`
- `tests/test_cli_watch.py`, `tests/test_jobs.py`, `tests/test_mcp_server.py`, `tests/test_task.py`

### Dead code removal (mine, finished)

- `hub/ui/src/components/agents/AgentPromptPanel.tsx` (398 lines) — **deleted**, `git rm`
- `hub/ui/src/components/agents/AgentMessageSender.tsx` (275 lines) — **deleted**
- `hub/ui/src/components/agents/AgentTimeline.tsx` (72 lines) — **deleted**. Its data hook
  `useAgentTimeline` in `hub/ui/src/api/agents.ts` is **still live** — `AgentActivityTab.tsx:23`
  uses it. Do not delete the hook.
- `hub/ui/src/hooks/useApiConfig.ts` (6 lines) — **deleted**
- `hub/ui/src/lib/utils.ts` (6 lines, the `cn` helper) — **deleted**
- `hub/ui/package.json` + `package-lock.json` — `npm uninstall clsx tailwind-merge` (only `cn` used them)
- `src/agentweave/context_builder.py` — removed `write_agent_context_file`; ruff then removed the
  now-unused `AGENT_CONTEXT_DIR` import. **`AGENT_CONTEXT_DIR` itself is still used widely
  elsewhere** (cli.py, watchdog.py, diagnostics.py, mcp/server.py) — only this import went.
- `src/agentweave/diagnostics.py` — removed `worst_status` and the `STATUS_ORDER` dict it alone used
- `src/agentweave/locking.py` — removed `wait_for_unlock`. `is_locked` stays — it is directly tested.
- `src/agentweave/utils.py` — removed `list_json_files`
- `src/agentweave/validator.py` — removed the `ValidationError` class
- `src/agentweave/watchdog.py` — removed `_extract_claude_session_id`

### Version fixes (mine, finished)

- `hub/hub/__init__.py` — was hardcoded `__version__ = "0.1.0"`; now reads
  `importlib.metadata.version("agentweave-hub")` with a `"0.0.0+dev"` fallback.
- `hub/hub/main.py` — FastAPI `version="0.1.0"` → `version=__version__`, plus
  `from . import __version__`. This is user-visible in the OpenAPI `/docs` page, which was
  advertising 0.1.0 while `hub/pyproject.toml` said 0.35.0.
- `src/agentweave/__init__.py` — dev fallback `"0.39.0"` → `"0.0.0+dev"`.
- `CLAUDE.md` — version line now points at the two pyproject files instead of stating
  "v0.40.0 (CLI + Hub v0.33.0)"; also removed the 3 deleted UI components and `useApiConfig`
  from the directory tree.
- `AGENTS.md` — removed "(v0.15.0)" from the header intro; removed 2 `AgentPromptPanel` references
  (the tree at ~line 102 and the component table at ~line 296). **Left 2 references intact** at
  ~lines 397 and 425 — those are inside dated historical sections describing past bug fixes, and
  are accurate as history.

### Generated skills (mine, finished)

- **`git rm --cached`** (untracked, files kept on disk) for 8 generated skills:
  `.claude/skills/{aw-collab-start,aw-delegate,aw-done,aw-relay,aw-review,aw-revise,aw-status,aw-sync}/SKILL.md`
- `.gitignore` — added a 22-entry block listing every `.claude/skills/<name>/` that has a matching
  template in `src/agentweave/templates/skills/`, with a comment and a regeneration one-liner.

### New files (mine, untracked)

- `tests/test_packaging.py` — 4 tests. Builds a real wheel via `python -m build` and asserts every
  `.md`/`.json` under `src/agentweave/templates/` appears in it, that no `__pycache__`/`.pyc`
  leaks in, and that the skill reference doc specifically ships. Skips cleanly if `build` is
  missing. **I `pip install build` into `.venv` to run these** — it is not in the `dev` extra, so
  these will skip in CI unless added.
- `hub/tests/test_version.py` — 2 tests: `hub.__version__` is not the stale `"0.1.0"` literal, and
  the FastAPI app version matches the package version.

### Files I did NOT touch — pre-existing uncommitted work from earlier sessions

Verified byte-for-byte unchanged by me: their `git diff --stat` numbers still match the previous
handoff exactly. **Do not attribute these to this session, and do not commit them without asking.**

- `docs/guides/aw-spec-workflow.md` (+20)
- `src/agentweave/templates/skills/aw-spec-apply.md` (37), `aw-spec-archive.md` (27),
  `aw-spec-explore.md` (11), `aw-spec-propose.md` (87), `aw-spec-technical-explore.md` (+13)
- `src/agentweave/templates/skills/references/html-spec-conventions.md` (105)
- `tests/test_skill_templates.py` (+4)
- `src/agentweave/templates/roles/spec.md` (32) and `hub/hub/data/roles/spec.md` (32) — these two
  are identical twins that must be edited together; they hold interleaved edits from two earlier
  sessions
- `spec/agentweave-spec.html` (713 changed lines) — under the standing "leave it" directive
- Untracked and left alone: `spec/README.md`, `spec/system-map.html`, `spec/roadmaps/`,
  `validate_spec.py`, `kimi-export-session_-20260725-135928.md`, `.claude/handoffs/`

## Key decisions

1. **Retract finding #1 rather than ship a fix for a non-bug.** I had already edited
   `pyproject.toml` (recursive `templates/**/*` glob + `setuptools>=62.3` bump) before testing the
   claim properly. When the test passed against the *original* declaration, I reverted the file to
   HEAD. *Rejected:* keeping the recursive glob anyway as "more robust" — it would have been a
   change justified by a defect that does not exist, and it narrowed the include to `.md`/`.json`.
   I kept `tests/test_packaging.py` because the `package-data` list genuinely is non-exhaustive
   and nothing else would notice if MANIFEST.in or `include_package_data` changed.

2. **Configure B008 away rather than "fix" 55 sites.** All 55 were FastAPI `Depends()` in argument
   defaults — the documented framework idiom, not the mutable-default trap B008 targets. Used
   `extend-immutable-calls`. *Rejected:* per-file-ignores for `hub/hub/api/` — coarser, and would
   have masked real B008s in those files.

3. **Set `known-first-party` before re-running isort.** The first `ruff --fix` pass sorted
   `from hub.config import ...` into the third-party block in `hub/tests/test_migrations.py`.
   Added the isort config and re-ran, which corrected it.

4. **Consolidate `.gitignore` rather than delete rules blindly.** A blanket `.agentweave/` at the
   old line 124 was silently subsuming four earlier rule blocks (old lines 60-71, 82-89, 102-103),
   including four `!` negations that **can never fire** — git cannot re-include a file inside an
   ignored directory. Verified every claim with `git check-ignore -v` before removing anything.

5. **Keep two `try/except/pass` blocks instead of `contextlib.suppress`.** Both are in
   per-iteration hot loops (`hub/hub/sse.py` broadcast per-subscriber,
   `hub/hub/mcp_server.py` read-receipt per-message) where `suppress` allocates a context manager
   each pass. Marked `# noqa: SIM105` with the reason inline. The two non-loop sites were converted.

6. **For finding #3, the user chose "stop committing generated skills" (option 2 of 2).**
   *Rejected:* option 1, regenerate and keep committing — every template edit would need a matching
   regenerated commit forever, which is what produced the drift in the first place.
   **Critically: I did NOT blanket-ignore `.claude/skills/`.** Only 8 of the 16 skill directories
   are generated from templates. The other 8 (`aw-deploy`, `aw-jobs`, `check-build`,
   `copilot-test-setup`, `openspec-apply-change`, `openspec-archive-change`, `openspec-explore`,
   `openspec-propose`) are hand-written with no template and **must stay tracked** — a blanket
   ignore would have silently dropped them from version control.

7. **Left mypy scoped to `src/`.** Widening it to `hub/` is a separate, much larger job
   (`disallow_untyped_defs = true` is on). Not attempted.

8. **Applied black to `hub/` and `tests/` (18 files, 436 lines).** Necessary to make the widened
   `black --check` in CI pass. Pre-existing non-compliance: 19 files were already unformatted at
   HEAD. `src/` was already clean, which is why CI never caught it.

## Constraints and user directives (verbatim)

From this session:
- **"Scan this project and find ways to clean it up"** — the originating request.
- **"start at the top"** — work the reported findings in the order given.
- **"okay the second"** — for finding #3, choose option 2: stop committing generated skills.

Carried forward from `.claude/handoffs/2026-07-27-2144-spec-root-rename.md` and still in force:
- `.claude/handoffs/` → **"Leave as-is"** (untracked, not gitignored). I did not gitignore it.
- v0.x `spec/agentweave-spec.html` edits → **"Leave it"**. **"Do not re-ask unprompted."** Obeyed.
- `kimi-export-session_-20260725-135928.md` → leave. Obeyed — I flagged it under finding #8 as a
  cleanup candidate but did **not** delete it, and the user has not responded to that.

Global (from this environment): **commit or push only when the user asks.** The user has not asked.
`968b8db` is still unpushed on master. Nothing from this session is committed or staged for commit
(the `git rm --cached` deletions ARE staged in the index — see Git state).

## Dead ends

- **Bulk string-replace on `tests/test_activate.py` over-matched.** I replaced
  `"result = subprocess.run("` repo-wide in that file to clear 4 flagged F841s; it hit 9 sites,
  including ones whose `result` **was** asserted on, producing 11 `F821 Undefined name` errors.
  Caught it with `ruff --select F821`, reverted the file with `git checkout`, and redid it by
  exact line number from ruff's output. **Lesson: never bulk-replace to satisfy a line-scoped
  lint rule; drive it off the reported line numbers.**
- **`dict(active_task_counts_res)` for ruff's C416 broke 10 hub tests.** SQLAlchemy's `Result`
  exposes `.keys()`, so `dict()` takes the mapping protocol path and tries to subscript it →
  `TypeError: 'ChunkedIteratorResult' object is not subscriptable`. Reverted to the dict
  comprehension with `# noqa: C416` and an explanation at `hub/hub/api/v1/agents.py` ~line 262.
  **C416 is not safe on SQLAlchemy Results.**
- **Parenthesized multi-context `with` is a syntax error on Python 3.8/3.9.** I collapsed a nested
  `with` in `tests/test_hub_commands.py` for SIM117; CI runs `tests/` on the full 3.8–3.12 matrix.
  Reverted to nested + `# noqa: SIM117`. Afterwards I swept all of `src/` and `tests/` with
  `ast.parse(..., feature_version=(3, 8))` to confirm nothing else 3.10+ slipped in — clean.
- **Ruff's E712 suggestion `not ApiKey.revoked` would raise at runtime** on a SQLAlchemy column
  expression. Used `.is_(False)` instead.
- **A third version test I wrote had to be deleted.** It compared installed metadata against
  `hub/pyproject.toml` and failed locally (`0.34.1` vs `0.35.0`) because the editable install
  predates the last version bump. That tests install freshness, not code — it would fail for
  anyone who bumped without reinstalling.
- **`pytest tests/ hub/tests/` in one invocation fails collection** with 32 errors — duplicate
  module basenames (both trees have `test_mcp_server.py` etc.). They must be run separately, which
  is what the Makefile already does. Not a regression.

## Verification

**Ran and passed:**
- `.venv/Scripts/python.exe -m pytest tests/ -q` → **570 passed, 3 skipped** (baseline before my
  changes was 566 passed, 3 skipped; +4 is `tests/test_packaging.py`)
- `.venv/Scripts/python.exe -m pytest hub/tests/ -q` → **183 passed, 4 skipped, 3 failed**
  (baseline at HEAD: 181 passed, 4 skipped, **the same 3 failed**; +2 is `hub/tests/test_version.py`)
- `.venv/Scripts/ruff.exe check src/ hub/ tests/` → **All checks passed** (was 149 errors)
- `.venv/Scripts/black.exe --check src/ hub/hub/ hub/tests/ tests/` → **129 files unchanged**
- `.venv/Scripts/mypy.exe src/` → **Success: no issues found in 26 source files**
- `cd hub/ui && npx tsc --noEmit` → clean, no output
- `cd hub/ui && npm run build` → built in ~1.5s, 430 modules
- `cd hub/ui && npx vitest run` → **11 files, 61 tests passed**
- `ast.parse(feature_version=(3,8))` across all of `src/` and `tests/` → all parse
- `git check-ignore` spot-checks after every `.gitignore` edit: 8 paths that must stay ignored do;
  `openspec/config.yaml` and `src/agentweave/cli.py` stay visible; generated skills ignored;
  hand-written skills visible
- `git status --porcelain -uall` before/after the `.gitignore` rewrite → **identical untracked list**
- Confirmed the 3 `test_migrations.py` failures are pre-existing by `git stash`-ing my changes to
  that file and re-running

**NOT tested:**
- **Nothing was run in CI.** All verification is local on Windows/Python 3.11. The widened CI lint
  and format steps have never executed on the runner.
- **The Hub was never started.** The `hub/hub/main.py` version change is verified only by
  `create_app().version` returning `0.34.1` in-process — I did not open `/docs`, run Docker, or
  hit any endpoint.
- **The Hub UI was never opened in a browser.** Deleting 3 components is backed by grep + `tsc` +
  build + vitest, not by visual confirmation that no route regressed.
- **`agentweave init` was never run**, so the now-ignored `.claude/skills/` were never regenerated.
  The 8 stale generated skills are still sitting on disk in their old form.
- Python **3.8/3.9/3.10/3.12** were not run — only the 3.8 *grammar* check above.
- The wheel built by `tests/test_packaging.py` was **not installed** into a clean env.
- No `mypy` on `hub/`. No eslint on the UI (it is broken — see Open questions).

## Git state

- Branch `master`, HEAD `968b8db`, **dirty**. **1 unpushed commit** (`968b8db`, from the previous
  session's spec-root rename). Nothing from this session is committed.
- **The index is not clean**: 13 deletions are staged from `git rm` / `git rm --cached` —
  5 deleted UI files and 8 untracked-but-kept generated skill files. Everything else is unstaged.
- Modified, unstaged: 71 paths (mine + the earlier sessions' spec work — see "Files touched").
- Untracked: `.claude/handoffs/`, `hub/tests/test_version.py`, `tests/test_packaging.py`,
  `kimi-export-session_-20260725-135928.md`, `spec/README.md`, `spec/roadmaps/`,
  `spec/system-map.html`, `validate_spec.py`.
- Branch `agentweave-1-0` still has unpushed `21aeea0` from the previous session. Untouched here.

## Next steps

1. **Regenerate the 8 stale generated skills.** They are now gitignored but the on-disk copies are
   still the drifted versions — so `/aw-review` in this repo still runs the pre-quality-config
   workflow with no echo-chamber guard, and the 14 `aw-setup-*`/`aw-spec-*` skills have no local
   copy at all. Run `agentweave init --force` from the repo root, then `git status` to confirm it
   dirtied nothing tracked. **Check first** what else `--force` overwrites — it also rewrites
   `.agentweave/README.md`, role files, and root context files, and `CLAUDE.md`/`AGENTS.md` have
   my uncommitted edits in them.
2. **Decide how to commit this session's work.** It is large and mixed. Suggested split:
   (a) lint config + CI/Makefile widening + all lint fixes + black; (b) dead-code removal (src +
   UI + deps); (c) `.gitignore` consolidation + generated-skills untracking; (d) version fixes +
   the 2 new test files. Keep all four **separate from** the earlier sessions' spec files.
3. **Add `build` to the `dev` extra in `pyproject.toml`** if `tests/test_packaging.py` should
   actually run in CI. Right now it silently skips without it.
4. **Fix or delete `npm run lint`.** `hub/ui/` has **no eslint config file of any kind**, and the
   script still passes `--ext`, removed in eslint 9. The command has never worked, yet CLAUDE.md
   documents it. Either add an `eslint.config.js` flat config or drop the script and the doc line.
5. **Investigate the 3 pre-existing `hub/tests/test_migrations.py` failures.** They predate this
   session and make `make test-all` red.
6. **Unfinished from the previous handoff** — still open, untouched by me: the entangled
   `spec.md` role-template edits, `aw-spec-archive.md:81` pointing at `spec/specs/`, the
   `_discover_spec_files()` Hub-sync gap at `src/agentweave/watchdog.py:36-51`, and whether to
   track `spec/README.md` / `spec/system-map.html` / `spec/roadmaps/`.

## Open questions for the user

- **Finding #8 was never answered:** delete `kimi-export-session_-20260725-135928.md` (112 KB,
  untracked, not ignored — note `.gitignore` covers `kimichanges.md`/`kimiwork.md` but not this
  pattern), and relocate `validate_spec.py` out of the repo root? Both are the user's files and
  I did not touch them. The prior handoff's standing directive is "leave" the kimi export.
- Should `.claude/skills/` generated entries also be removed from disk, or left so the local
  skills keep working until the next `agentweave init`?
- Commit strategy for this session — one commit or the 4-way split in next step 2?
- Should mypy be widened beyond `src/`? It would be a large job.

## Read on resume

- `.claude/handoffs/2026-07-27-2144-spec-root-rename.md` — the previous thread; its uncommitted
  files are still in this tree and must not be swept into a cleanup commit.
- `.gitignore` — the consolidated `.agentweave/` rule, the `openspec/*` + `!openspec/config.yaml`
  pair, and the 22-entry generated-skills block with its regeneration one-liner.
- `pyproject.toml` — the new `[tool.ruff.lint.isort]` and `[tool.ruff.lint.flake8-bugbear]`
  sections; confirm `package-data` is still at HEAD values.
- `hub/hub/db/engine.py` — the `# noqa: F401` side-effect import block; the comment there is the
  reason it must never be "cleaned up".
- `hub/hub/api/v1/agents.py` (~line 262) — the `# noqa: C416` SQLAlchemy `Result` trap.
- `tests/test_packaging.py` and `hub/tests/test_version.py` — the two new test files, both untracked.
