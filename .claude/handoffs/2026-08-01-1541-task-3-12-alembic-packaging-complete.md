# Handoff: Phase 3 task 3.12 complete — alembic.ini packaging + a real migration bug fixed

**Date:** 2026-08-01T15:41:28+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `07d657d`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1506-pilot-mode-removed-committed.md`
**Status:** chunk complete — session end. Two commits landed this chunk (`07d657d` is the
substantive one; the pilot-mode-removal handoff commit `ab75b7d` predates this chunk). Read
this file in full — it stands alone; the previous handoff's substance (pilot-mode removal)
is unrelated to this chunk's work.

## Goal

Same overarching goal as the whole chain: rebuild the AgentWeave Hub into a local-first
application that owns agent execution directly (the `hub-native-experience` OpenSpec change,
`openspec/changes/2026-07-30-hub-native-experience/`). This chunk picked up task 3.12 from
that change's own queue (Phase 3, "Native runtime, packaging, and crash recovery"), the
task immediately after the prior chunk's pilot-mode-removal detour: **"Ship `alembic.ini` in
`package-data` — a pip install currently logs 'alembic.ini not found … skipping migrations'
and runs unmigrated."**

## Current state

**Fully done, tested three different ways, committed at `07d657d`.** Two distinct problems
were found and fixed, not one:

**Problem 1 (the task as stated): `alembic.ini` wasn't shippable.** It lived at
`hub/alembic.ini` — the *distribution root*, a sibling of the `hub` package directory, not
inside it. Since `[tool.setuptools.packages.find] include = ["hub*"]` only packages the
`hub` package tree itself, a file sitting outside that tree can never be included via
`package-data` (which only works for files *within* a package). Fixed by moving it to
`hub/hub/alembic.ini` (inside the package) and adding `"alembic.ini"` to
`[tool.setuptools.package-data]`. This also required changing `script_location` from
`hub/migrations` (a value that only ever worked because it happened to be interpreted
relative to whatever the current working directory was at invocation time — Docker's `/app`,
the Makefile's `hub/`, or a dev shell's `hub/`) to Alembic's `%(here)s` token
(`script_location = %(here)s/migrations`), which resolves relative to the ini file's own
location regardless of CWD — the only way this can work correctly for a `pip install
agentweave-hub && agentweave-hub` invoked from an arbitrary directory.

**Problem 2 (found only because Problem 1's fix let it surface): migration 0001 has no
existence guard.** Every migration from 0004 onward already checks
`inspector.get_table_names()` before creating a table (an idempotency pattern established
early in this repo's migration history), but 0001 (`add_agent_outputs`) never did. Since
`init_db()` always runs `Base.metadata.create_all()` *before* `_run_alembic_upgrade()`, and
`create_all()` — on any database whose tables didn't already exist — creates every table
using the *current* model definitions (including `agent_outputs`), migration 0001's own
unconditional `CREATE TABLE agent_outputs` then fails with "table already exists" on literally
every fresh deployment, dev or production. `_run_alembic_upgrade()`'s try/except (by design,
so dev mode doesn't crash on schema drift) silently swallows this, meaning
`alembic_version` never gets stamped at all — not just for this migration, but permanently,
since alembic thinks it's still at the unversioned base state. This was **not a new bug
introduced by anything in this session** — it's been present since 0001 was written
(2026-03-14 per its own `Create Date`) — but it was only found because verifying Problem 1's
fix required actually watching a fresh install's migration run to completion, at which point
it became clear the "alembic.ini not found" warning had been masking this second failure the
whole time (once alembic.ini is found, the very next thing that happens is 0001 failing, and
that failure was *also* silently swallowed). Confirmed this exact bug was live on the actual
local dev Hub's own `data/agentweave.db`: its `alembic_version` table was completely empty
despite the database otherwise having the fully-current schema (built via `create_all()`
alone, since every past session's `_run_alembic_upgrade()` call had silently failed against
it too — this explains an odd finding from the *previous* chunk, where dropping the pilot
columns from that same dev DB required a manual `ALTER TABLE` because the real migration
0013 never actually got a chance to run against it). Fixed by adding the same
`inspector.get_table_names()` guard to 0001 that 0004+ already use.

**Verified three independent ways**, not just via the existing test suite (see Verification
below for exact commands): the full `pytest` suite; a from-scratch wheel build + install
into a throwaway venv + running `init_db()` against a brand-new database in a directory
containing no source checkout at all; and a direct CLI-style invocation
(`alembic -c hub/alembic.ini upgrade head`) matching exactly what Docker and the Makefile now
run. All three confirm `alembic_version` correctly lands at `0013` (current head) with no
warnings. The actual local dev Hub was restarted at the end of this chunk and its real
`data/agentweave.db` — broken this way for the entire session's prior history — finally
stamped correctly for the first time.

## Files touched

All 9 files committed together at `07d657d` ("Complete Phase 3 task 3.12: package
alembic.ini so migrations work post pip-install"):

- `hub/alembic.ini` → `hub/hub/alembic.ini` (git-tracked rename). Content change:
  `script_location = hub/migrations` → `script_location = %(here)s/migrations`. Finished.
- `hub/hub/db/engine.py` — `_run_alembic_upgrade()`'s `alembic_cfg_path` calculation changed
  from `Path(__file__).parent.parent.parent / "alembic.ini"` (three levels up, assuming the
  old distribution-root location) to `Path(__file__).parent.parent / "alembic.ini"` (two
  levels up, matching the new in-package location); comment updated accordingly. Finished.
- `hub/hub/migrations/versions/0001_add_agent_outputs.py` — wrapped `create_table`/
  `create_index` in an `if "agent_outputs" not in inspector.get_table_names():` guard (and
  the mirror check in `downgrade()`); added a docstring explaining why this guard exists and
  what breaks without it. Finished.
- `hub/pyproject.toml` — added `"alembic.ini"` as the first entry in
  `[tool.setuptools.package-data]`'s `hub` list. Finished.
- `hub/Dockerfile` — removed the now-redundant separate `COPY alembic.ini ./` step (the file
  ships automatically via the existing `COPY hub/ ./hub/` step now that it lives inside the
  package); changed `CMD`'s `alembic upgrade head` to `alembic -c hub/alembic.ini upgrade
  head`. Finished.
- `hub/Dockerfile.dev` — identical change to `Dockerfile`. Finished.
- `hub/Makefile` — `dev:` target's `alembic upgrade head` → `alembic -c hub/alembic.ini
  upgrade head` (this Makefile's own header comment says "Run from the hub/ directory", so
  the relative path is correct as written). Finished.
- `hub/tests/test_migrations.py` — `ALEMBIC_INI` constant path updated from
  `Path(__file__).parent.parent / "alembic.ini"` to `Path(__file__).parent.parent / "hub" /
  "alembic.ini"`; comment above it updated. No test *logic* changes were needed beyond this
  path fix — all pre-existing assertions in this file already passed once the path and the
  0001 guard were both correct. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.12 checked off with a
  long findings entry (worth reading directly — covers both problems, the verification
  methodology, and the exact fix shape for each). Finished.

**Not touched, pre-existing untracked, not to be modified:** the six `.claude/handoffs/*.md`
files from earlier sessions (listed in every `git status` this session and every prior one).

**Not a tracked file change, but a real environment state change:** the local dev Hub's
`hub/data/agentweave.db` (gitignored, never tracked) went from a never-successfully-migrated
state (`alembic_version` empty) to correctly stamped at `0013`, as a side effect of
restarting the dev Hub with this chunk's code — not something committed or requiring a
commit, just noting it so a future session doesn't misdiagnose this DB's history.

## Key decisions

1. **Used Alembic's `%(here)s` token instead of a plain relative `script_location`.** First
   attempt used `script_location = migrations` (plain relative path, assuming Alembic
   resolves `script_location` relative to the ini file's own directory). This is wrong —
   Alembic resolves plain relative `script_location` values relative to the *current working
   directory* at invocation time, not the ini file's location. Confirmed via a real test
   failure (`CommandError: Path doesn't exist: migrations.`) when running the test suite from
   `hub/` as CWD. Alembic 1.18.4 (the installed version) supports the `%(here)s` template
   token specifically to solve this — it substitutes the ini file's own absolute directory
   regardless of CWD, which is the only value that't correct for a `pip install
   agentweave-hub && agentweave-hub` run from an arbitrary directory. *Rejected:* overriding
   `script_location` explicitly in Python (`_run_alembic_upgrade()` already does this pattern
   for `sqlalchemy.url`) — this would fix the Python-level path but not the Docker/Makefile
   CLI-invocation paths, which don't go through that function at all.
2. **Fixed migration 0001's missing existence guard as part of this task, not deferred.**
   The *previous* chunk (pilot-mode removal) found this exact same underlying bug
   incidentally while verifying migration 0013, and deliberately deferred fixing it as
   "pre-existing, unrelated, out of scope" (see that chunk's own handoff, Current State
   section). This chunk revisited that same bug and fixed it, because — unlike in the
   previous chunk — it now sits directly athwart this task's own stated goal: shipping
   `alembic.ini` is meaningless if the very first migration it would run always fails
   silently regardless. *Rejected:* stopping at "alembic.ini now ships correctly" and
   leaving 0001 broken — that would leave task 3.12 technically-file-shipped but
   functionally still unmigrated for every real deployment, which is the exact symptom the
   task was filed to fix.
3. **Verified via a real built-and-installed wheel, not just the test suite.** The test
   suite's own fresh-file-db tests (`test_alembic_upgrade_head_fresh_file_db`, etc.) run
   against the *source checkout*, which never actually exercises whether the packaged
   distribution is self-contained — a passing test suite could still ship a broken wheel if,
   e.g., `package-data` globs were subtly wrong. Built a real wheel with `py -m build
   --wheel`, inspected its zip contents directly for `hub/alembic.ini`, installed it into a
   throwaway venv (`py -m venv`), and ran `init_db()` from a directory with zero relation to
   this source tree. This is the only verification method that actually proves the stated bug
   ("a pip install ... runs unmigrated") is fixed, as opposed to proving the source-tree
   tests pass.

## Constraints and user directives (verbatim)

- User, this chunk: **"continue"** — a single-word instruction given right after the
  previous chunk's handoff was written and reported, authorizing proceeding with that
  handoff's own stated "Next steps" (task 3.12) without further discussion. No other
  directive was given this chunk; all decisions above were made using judgment consistent
  with the standing directives below.
- Carried forward, still in force (from every prior handoff in this chain): **"Yeah and
  always commit the changes."** — this chunk's 9 files committed on completion, staged
  explicitly by path (a first `git add` attempt included a stale pre-rename pathspec and
  correctly errored without staging anything; corrected and re-run). **"After every
  threshold of implementation you must run the skill `/handoff`"** — this file is that.
  **"Before starting a new implementation revise the entire session for the spec"** — this
  task's investigation read `tasks.md`'s 3.12 entry in full, then traced through
  `pyproject.toml`, `engine.py`, `alembic.ini`, `Dockerfile`/`Dockerfile.dev`, `Makefile`, and
  `test_migrations.py` before writing any code. **"let's make sure it works with claude and
  codex first locally"** — not touched this chunk (no runner-specific work). Project
  `CLAUDE.md` rules still apply (never commit `.agentweave/tasks/`, `messages/`, `agents/`,
  `session.json`, `transport.json`; stage explicitly, never `git add -A`).

## Dead ends

- **Plain relative `script_location = migrations`** — see Key Decision 1. Failed with
  `CommandError: Path doesn't exist: migrations.` when the test suite ran from `hub/` as
  CWD, since Alembic resolves plain relative `script_location` against CWD, not the ini
  file's directory. Not a wasted cycle beyond one test run — the fix (`%(here)s`) was found
  and applied immediately after.
- **Testing the wheel install with a temp SQLite path via `alembic -x db_url=...`** — the
  `-x` flag's value isn't wired into `hub/hub/migrations/env.py` at all (that file reads
  `settings.database_url` from `hub.config`, driven by pydantic-settings' own `DATABASE_URL`
  env var / `.env` file resolution, not any `-x` argument). Abandoned in favor of setting the
  `DATABASE_URL` environment variable directly before invoking alembic, which worked
  immediately.
- **Windows path vs. Git-Bash `/tmp` confusion during wheel-install verification** — Python
  processes launched from this Bash tool don't understand Git-Bash's `/tmp` mount the same
  way the shell does; every Python-side file operation against a `/tmp/...` path failed with
  `FileNotFoundError`/`unable to open database file` until translated via `cygpath -w` to a
  real Windows path (`C:\Users\huida\AppData\Local\Temp\...`) first. Not a real bug, just a
  tooling quirk worth remembering for any future cross-shell verification in this
  environment.

## Verification

**Ran and passed, this chunk:**
- `py -m pytest tests/ -q` from `hub/` → **329 passed, 4 skipped** (identical count to the
  previous chunk's final state — this task added no new tests, only fixed path/guard logic
  that pre-existing tests already covered once correct).
- `py -m pytest tests/test_migrations.py -q` in isolation, run twice: once after the
  `script_location`/path fixes alone (4 failures — `CommandError`/`NoSuchTableError`-style,
  from Key Decision 1's dead end), and again after the `%(here)s` fix (all passing) — the
  intermediate failing run is itself part of the verification trail, not a discarded mistake.
- `py -m ruff check hub/ tests/` (from `hub/`) → clean.
- `py -m black --check hub/ tests/` (from `hub/`) → clean, no reformatting needed.
- **Real wheel build + install verification** (from `hub/`, exact commands):
  `py -m build --wheel --outdir <tmp>` → inspected the `.whl`'s zip contents directly via
  Python's `zipfile` module, confirmed `hub/alembic.ini` and all 13
  `hub/migrations/versions/*.py` files present → `py -m venv <tmp-venv>` →
  `<tmp-venv>/Scripts/python.exe -m pip install <wheel>` → from a directory containing no
  AgentWeave source at all, `DATABASE_URL="sqlite+aiosqlite:///data/verify.db"
  <tmp-venv-python> -c "import asyncio; from hub.db.engine import init_db;
  asyncio.run(init_db())"` → then directly inspected the resulting SQLite file's
  `alembic_version` table via `sqlite3` — landed at `('0013',)`, the current head, with no
  "alembic.ini not found" warning printed. Repeated this full build-install-run cycle twice:
  once before the 0001 guard fix (confirmed `alembic_version` stayed empty — proving Problem
  2 was real and distinct from Problem 1), and once after (confirmed it stamps correctly).
- **CLI-style invocation matching Docker/Makefile**: from `hub/` as CWD, ran
  `DATABASE_URL="sqlite+aiosqlite:////tmp/cli_fresh_test.db" py -m alembic -c
  hub/alembic.ini upgrade head` against a brand-new file — full 0001→0013 chain logged and
  completed with exit code 0.
- **Live verification against the actual local dev Hub**: restarted it (stopped the prior
  PID, started a fresh `python -m uvicorn hub.main:app` from `hub/`), confirmed via the
  startup log that all of 0001→0013 ran, and directly queried
  `hub/data/agentweave.db`'s `alembic_version` table afterward — landed at `('0013',)`, the
  first time this specific database has ever been correctly stamped (it had accumulated its
  full schema via `create_all()` alone across many prior sessions, per the previous chunk's
  own incidental discovery of this same bug).

**NOT tested this chunk:**
- An actual Docker build (`docker build .` / `docker compose up --build`) was **not** run —
  the Dockerfile/Dockerfile.dev changes were reasoned through carefully (traced exactly what
  `COPY hub/ ./hub/` copies and where, matched against the build-context assumption) but not
  built and run end-to-end in a real container. If the user wants Docker-path confidence
  before relying on this, running `cd hub && docker compose up --build` and checking the
  container logs for a clean `alembic upgrade head` line (no "already exists" or "not found")
  would close that gap.
- Migration 0001's `downgrade()` path was not exercised (no test calls `alembic downgrade`
  for 0001 specifically; same gap noted in the previous chunk's handoff for migration 0013).
- The Makefile's `dev` target itself (`make dev` from `hub/`) was not run as `make` — the
  equivalent underlying `alembic -c hub/alembic.ini upgrade head` command it now runs was
  verified directly instead (see above), which exercises the same code path but not the
  Makefile wrapper syntax itself.
- `agentweave-hub` (the actual installed console-script entry point,
  `hub.main:run`) was not invoked directly — `init_db()` was called directly instead. These
  should be equivalent (`hub.main:run` presumably calls `init_db()` during its own startup
  the same way the FastAPI lifespan does locally) but the entry-point wrapper itself wasn't
  exercised.

## Git state

- Branch `hub-native-experience`, **HEAD `07d657d`** — one commit, "Complete Phase 3 task
  3.12: package alembic.ini so migrations work post pip-install", 9 files changed
  (93 insertions, 34 deletions), including a detected rename (`hub/alembic.ini` →
  `hub/hub/alembic.ini`).
- Working tree clean except the six pre-existing untracked `.claude/handoffs/*.md` files
  from earlier sessions (unrelated, unchanged) — this new handoff file and `LATEST.md`'s
  pointer update will be committed in a separate follow-up commit after this file is
  finalized, matching the chain's established two-commit-per-checkpoint pattern.
- No upstream configured — nothing pushed, not requested, unchanged from every prior
  handoff in this chain.
- **Live process state:** dev Hub uvicorn running fresh (PID not re-checked as of writing
  this file, but restarted and confirmed healthy during this chunk's own verification, after
  all of this chunk's code changes). `agentweave-watch` process state not touched or
  re-checked this chunk (last known state: PID 25768, confirmed running as of the *previous*
  chunk's session-start investigation — not re-verified since).

## Next steps

1. **Nothing is blocking** — this chunk is fully complete and committed. The next queued
   item in `openspec/changes/2026-07-30-hub-native-experience/tasks.md` is **task 3.15**:
   "Add `--app` to open a chromeless browser app-mode window at the Hub URL" (3.13 and 3.14
   are already done, folded into an earlier task's entry per the file's own notes). Read that
   task's entry in full before starting — not investigated at all this session, a
   CLI/browser-launch feature, different shape of work than 3.12's packaging fix.
2. Two items from the previous chunk's own handoff remain open and were not touched this
   chunk (carried forward, not re-investigated): whether `spec/agentweave-spec.html` should
   be updated for the pilot-mode removal, and — now resolved as of *this* chunk — the
   migration-0001 idempotency question is no longer open (it's fixed).
3. If the user wants Docker-path confidence for this chunk's Dockerfile changes specifically
   (see Verification's "NOT tested" section), running an actual `docker build`/
   `docker compose up --build` and checking the container's own startup logs would close
   that one remaining verification gap.
4. Per the standing directive, continue committing each completed task/checkpoint without
   waiting for a fresh ask, staged explicitly by path.

## Open questions for the user

- Carried forward from the previous chunk, still unresolved: **should
  `spec/agentweave-spec.html` be updated for the pilot-mode removal?** Not touched this
  chunk either (unrelated to task 3.12's scope).
- Carried forward, unresolved, not urgent: should anything be pushed to a remote? No
  upstream configured for this branch.
- Carried forward from 3.5–3.11, still not resolved: the "ability to question the user"
  comment from an earlier T3-parity discussion (not touched this chunk).
- Carried forward: task 3.20 (stale Hub UI bundle) — still unfixed as a general mechanism;
  not touched this chunk (no frontend changes this task).
- **New:** does the user want the Docker build path actually exercised (see Verification's
  "NOT tested" section) before trusting this chunk's Dockerfile changes in a real deploy?

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — 3.12's entry is long and
  worth reading directly; 3.15 onward is the next unstarted work.
- `hub/hub/alembic.ini` — the new canonical location; note `script_location =
  %(here)s/migrations`, not a plain relative path — don't "simplify" this back to a plain
  relative value without re-reading Key Decision 1 above.
- `hub/hub/migrations/versions/0001_add_agent_outputs.py` — the existence-guard fix; its own
  docstring explains why the guard exists in more detail than this handoff repeats.
- `hub/hub/db/engine.py` — `_run_alembic_upgrade()`, in case any future packaging change
  needs to touch this path-calculation logic again.
- `hub/Dockerfile` and `hub/Dockerfile.dev` — if the open Docker-verification question above
  gets a "yes," start here; both files' `CMD` lines are the two spots that would show a
  failure first.
