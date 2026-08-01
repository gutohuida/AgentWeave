# Handoff: pilot mode removed entirely across CLI, Hub, and Hub UI — committed

**Date:** 2026-08-01T15:06:58+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `d86798d`
**Agent:** Claude Code / Sonnet 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-08-01-1735-hub-native-idle-checkpoint-awaiting-user.md`
**Status:** chunk complete — session end. This is a full, tested, committed removal —
not a partial pass. Read this whole file before resuming; it stands alone (the previous
handoff's substance, tasks 3.6–3.11, is unrelated to this chunk's work).

## Goal

The user (carried forward from the previous handoff, verbatim): "I think pilot mode agents
are a thing of the past. We can remove that." This chunk scoped and executed that removal —
pilot mode was a per-agent boolean meaning "manual control, don't auto-execute this agent,"
made redundant by the `hub-native-experience` work (the Hub now owns agent execution
directly; Hub-managed session continuity is already solved by the existing session picker
from tasks 3.5–3.7). The broader goal (rebuilding the Hub into a local-first app that owns
agent execution — `openspec/changes/2026-07-30-hub-native-experience/`) is unchanged; this
chunk was a user-directed detour from that change's own task sequence (3.12 onward), not
part of it — pilot-mode removal was never one of that change's numbered tasks.

## Current state

**Fully done, tested, committed at `d86798d`.** Two scope decisions were confirmed with the
user via `AskUserQuestion` before implementation:
1. Remove the "register a `--resume` session ID" mechanism entirely alongside pilot mode
   (it was pilot-specific manual tooling; Hub-managed session continuity doesn't need it).
2. Write a real Alembic migration to drop the DB columns, not just stop using them.

The removal touched ~66 files across CLI (`src/agentweave/`), Hub backend (`hub/hub/`), Hub
UI (`hub/ui/`), tests, docs, and 4 currently-active (non-archived) OpenSpec spec files.
Archived OpenSpec changes (e.g. `openspec/changes/archive/2026-04-12-pilot-mode/`) and
`CHANGELOG.md`/`README.md`/`ROADMAP.md`'s own historical entries were deliberately left as
historical record, not deleted — README/ROADMAP entries were reworded to say "removed"
rather than silently vanishing.

**One thing explicitly NOT done, flagged for the user:** `spec/agentweave-spec.html` — a
large, versioned, exhaustive HTML technical spec with ~15 genuine pilot-mode references
(field tables, CLI command tables, MCP tool tables, DB schema tables) — was deliberately left
untouched. It wasn't in the original removal plan's file list (found only via a later
broader grep) and looks like it wants its own revision-history entry (the file has a
version-tracked changelog table at its own top) rather than a folded-in edit. Not started.

**A second, unrelated finding, also flagged, also not fixed:** the actual local dev Hub SQLite
DB (`hub/data/agentweave.db`) has a pre-existing bug, discovered while verifying migration
0013 live: migration `0001_add_agent_outputs.py` does an unconditional `CREATE TABLE
agent_outputs` with no existence guard (unlike migration 0004+, which all check
`inspector.get_table_names()` first). Because this specific dev DB's tables were originally
created via `Base.metadata.create_all()` (which already had `agent_outputs`), alembic has
apparently failed on `CREATE TABLE agent_outputs already exists` on *every single startup*
against this file for a long time — silently swallowed by `_run_alembic_upgrade()`'s
try/except (by design, per its own docstring, so dev mode doesn't crash). This means
`alembic_version` was empty and every past migration in this repo's history never actually
applied to this specific file via the normal app-start path — only `create_all()`'s
whatever-the-model-looked-like-then output did. Fixed *for this one dev DB* by hand-running
the two `ALTER TABLE agents DROP COLUMN ...` statements directly (matching migration 0013)
rather than fixing the root cause, since fixing migration 0001's idempotency is a separate,
unscoped task. **Migration 0013 itself is correct and fully verified** — the test suite's
fresh-file-db tests (`test_alembic_upgrade_head_fresh_file_db`,
`test_init_db_runs_alembic_for_file_db`) exercise the full 0001→0013 chain on a truly fresh
file and pass, proving the migration chain works when 0001 isn't fighting a pre-populated
table. This dev-DB-specific hand-patch is not committed anywhere (it's a local SQLite file
mutation, not a code change) and doesn't need to be — it only matters for this machine's own
live-testing.

## Files touched

66 files, all committed in one commit `d86798d` ("Remove pilot mode entirely"). By area:

**CLI (`src/agentweave/`)** — `session.py` (removed `get_agent_pilot`/`set_agent_pilot`,
`sync_agents()`'s pilot branch), `cli.py` (removed `_generate_kimi_agent_yaml`,
`_refresh_kimi_pilot_yaml`, `_activate_kimi_pilot`, `cmd_session_register`, the whole
`session register` argparse subcommand + its `main()` routing branch, `cmd_agent_configure`'s
`--pilot`/`--no-pilot` handling and args, the `declared` dict's `pilot` key, reworked the
"piloted agents" launch-instructions print block to just claude_proxy agents), `constants.py`
(`VALID_AGENT_CONFIG_KEYS`), `validator.py` (pilot boolean check), `config.py`
(`AgentConfig.pilot` field + serialization + `_format_agent_block`/`generate_agentweave_yml`
call sites + the generated-yml doc-comment block), `diagnostics.py` (kimi context-injection
description, `agent_pilot_mode` warning), `context_builder.py` (`_agent_flags()`'s pilot
flag), `watchdog.py` (both pilot skip-guard blocks — ping path and direct-trigger path),
`mcp/server.py` (removed the whole `register_session` MCP tool + its section header),
`transport/http.py` (`HttpTransport.register_session()`), `transport/base.py` (abstract
`register_session()`), `templates/skills/aw-setup-agent.md`, `agentweave.template.yml`. All
finished, no partial work.

**Hub backend (`hub/hub/`)** — new migration
`migrations/versions/0013_drop_agent_pilot_columns.py` (drops `pilot` +
`registered_session_id` from `agents`, uses `batch_alter_table(..., recreate="never")` — see
Key Decisions #2 for why plain `recreate="never"` was needed, not the default recreate
behavior), `db/models.py` (removed both columns, reworded `Agent` docstring),
`schemas/agents.py` (removed both fields from `AgentSummary`), `launchability.py`
(`probe_agent()`'s pilot branch removed from `runnable`/`reason`, `get_agent_config()`'s
pilot merge + docstring paragraph removed), `scheduler.py` (`_job_agent_skip_reason()`'s
pilot branch removed, docstring reworded), `api/v1/agents.py` (deleted `POST
/{name}/pilot` and `POST /{name}/register-session` endpoints entirely, `list_agents()`'s
pilot/registered_session_id kwargs removed, `_runner_summary()`'s pilot flag removed),
`api/v1/session_sync.py` (removed the pilot-flag-sync loop, but — see Key Decisions #1 —
**re-added** an Agent-row-creation loop without the pilot write, because removing row
creation entirely broke an unrelated `"registered"` field), `mcp_server.py` (removed the
Hub-side `register_session` MCP tool). All finished.

**Hub UI (`hub/ui/src/`)** — `api/agents.ts` (removed `pilot`/`registered_session_id` from
`AgentSummary`, deleted `useSetPilotMode` + `useRegisterSession` hooks, removed now-unused
`useMutation` import), `components/agents/AgentCard.tsx` (removed the PILOT badge),
`components/agents/AgentOutputPanel.tsx` (simplified `handoffUnavailable` to just
`runner === 'manual'`), `components/agents/AgentInfoTab.tsx` (removed the entire two-branch
Pilot Mode section, `useState`/`useSetPilotMode`/`useRegisterSession` imports and usages, the
`RegisteredSessionRow` component — kept `SessionRow`, used by the unrelated Sessions
section). Rebuilt via `npm run build` in `hub/ui/`; the new bundle
(`index-rifmKIui.js`/existing `index-24oRMlrp.css`, CSS hash unchanged since its content
didn't change) was copied into `hub/hub/static/ui/assets/` to replace the stale
`index-CSmOWOMA.js`, matching what the Dockerfile's `COPY --from=ui-builder` does for real
deployments. All finished, `tsc --noEmit` and `vitest run` (196 tests) both clean.

**Tests** — deleted `tests/test_cli_pilot.py` (4 tests, no salvage needed — the whole
mechanism it tested is gone) and `hub/tests/test_pilot_mode.py` (7 tests), but first moved
`test_trigger_unsupported_runner_reports_501` (the one non-pilot test in that file) into
`hub/tests/test_agent_trigger.py` so its coverage wasn't lost. Trimmed pilot-specific tests
from `hub/tests/test_scheduler.py` (2 tests), `hub/tests/test_launchability.py` (1 test),
`tests/test_session.py` (2 tests), `tests/test_config.py` (`test_load_opencode_with_pilot`
deleted outright, several fixtures/assertions trimmed), `tests/test_validator.py`,
`tests/test_context_builder.py`, `tests/test_init.py`, `tests/test_activate.py`. Dropped
now-unnecessary `pilot=None`/`pilot: a.pilot` references from `tests/test_diagnostics.py` and
`tests/test_opencode_cli_override.py` (both `Namespace`/`AgentConfig` constructions that
would otherwise error since the attribute no longer exists). Renamed
`tests/test_cli.py`'s `TestPilotLaunchCommands` → `TestManualLaunchCommands` (the tests
themselves cover `_build_codex_launch_command`/`_build_opencode_launch_command`, which are
retained — only the class name was pilot-flavored, not the behavior tested). **Found and
fixed 6 test failures that weren't in the original removal plan** (the plan's Explore-agent
research missed these three files entirely): `hub/tests/test_agents.py` (2 tests directly
exercising the deleted `/register-session` endpoint — deleted), `hub/tests/test_agents_self_registered.py`
(1 test asserting `data["registered"] is True` for a plain declared agent — this is what
surfaced the session_sync.py behavior gap in Key Decision #1, fixed by restoring row
creation, not by changing the test), `hub/tests/test_mcp_server.py` (2 tests exercising the
deleted Hub-side `register_session` MCP tool — deleted), and `hub/tests/test_migrations.py`
(hardcoded `"0012"` version-string assertions in 2 tests, bumped to `"0013"` since that's now
head — this one **is** an expected/correct change, not a bug found, just a mechanical
version-string update).

**Docs** — deleted `docs/guides/pilot-mode.md` entirely + its `mkdocs.yml` nav entry; edited
`docs/reference/cli-commands.md`, `docs/reference/hub-api.md`, `docs/reference/mcp-tools.md`,
`docs/reference/agentweave-yml.md`, `docs/getting-started/configuration.md`,
`docs/getting-started/migration.md`, `docs/architecture/watchdog.md` (deleted its whole
"Pilot Mode Handling" section), `docs/index.md`, `docs/guides/context-files.md`,
`docs/guides/dashboard.md`, `docs/guides/faq.md`, `README.md` (3 spots: agent-card feature
bullet, the whole "Pilot Mode (manual session control)" section, an MCP tools table row;
plus the Roadmap table's Pilot Mode row reworded to `🗑️ Removed`, not deleted), `ROADMAP.md`
(Phase 11 section annotated "REMOVED" with a one-line reason, not deleted),
`.claude/skills/copilot-test-setup/SKILL.md` (3 stray `pilot: false` example lines). Added a
new `## [Unreleased]` section at the top of `CHANGELOG.md` documenting the removal (no
version bump was done — that's a release decision, out of scope here). **Left untouched
deliberately:** `spec/agentweave-spec.html` (see Current State), all archived OpenSpec
changes, prior handoff files, `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
(a historical findings log of already-completed tasks — not live requirements).

**OpenSpec (current, non-archived specs)** — also reworded, since these are supposed to
track live requirements, not history: `openspec/specs/agent-conversation-handoff/spec.md`
(handoff-disabled scenario, dropped the pilot clause — matches the `AgentOutputPanel.tsx`
code change), `openspec/specs/opencode-config/spec.md` (deleted the whole "opencode agent
with pilot mode" requirement+scenario), `openspec/specs/runtime-diagnostics/spec.md`
(reworded the "Trigger queued for pilot or manual agent" scenario to just "manual agent" —
note: this requirement's surrounding prose describes an old message-queuing trigger model
that tasks 3.10/3.11 already superseded with direct execution; that staleness is
pre-existing and NOT fixed here, out of scope for this chunk),
`openspec/specs/agent-context-onboarding/spec.md` (dropped "pilot" from a "pilot/yolo
markers" phrase).

## Key decisions

1. **`session_sync.py` needed a partial revert mid-verification.** My first pass deleted the
   entire pilot-flag-sync loop in `sync_session()`, assuming it existed *only* to write
   `Agent.pilot`. Running the full Hub test suite surfaced
   `test_get_agent_context_declared_agent` failing on `data["registered"] is True` — turns
   out the old loop's real (undocumented) side effect was ensuring an `Agent` DB row exists
   for *every* session-synced agent, not just pilot ones, and `GET /agents/agent-context`'s
   `"registered"` field is literally `agent_row is not None`. Fixed by keeping row creation
   (via `short_id()`, same pattern as before) but dropping only the `pilot=` write. *Lesson
   for future similar removals in this codebase:* a helper's stated docstring purpose
   ("sync pilot flags") is not reliable evidence of its only real effect — verify against the
   full test suite, not just the file's own tests, before deleting a whole block.
2. **Migration 0013 needed `batch_alter_table(..., recreate="never")`, not the default.**
   First attempt used plain `batch_alter_table("agents")` (matching migration 0008's
   precedent for `ALTER COLUMN`), which failed in `test_alembic_upgrade_head_fresh_file_db`
   with `NoSuchTableError: projects` — SQLite's default batch strategy recreates the whole
   table (rename-copy-drop) to handle FK/constraint changes, which requires reflecting the
   `agents` table's FK target (`projects`), a table that doesn't exist yet in an
   alembic-only migration context (it's created separately by `Base.metadata.create_all`,
   per the test file's own docstring). Since the installed SQLite (3.45.1) natively supports
   `ALTER TABLE ... DROP/ADD COLUMN` (available since 3.35), `recreate="never"` forces the
   direct-ALTER path and avoids the FK-reflection problem entirely. *Rejected:* using plain
   `op.drop_column()` without batch mode at all — Alembic's SQLite dialect doesn't support
   unbatched `drop_column` regardless of the underlying SQLite version's actual capability.
3. **Two scope decisions confirmed via `AskUserQuestion` before writing any code** (see
   Constraints below for the verbatim answers) — both were needed because the plan's own
   Explore-agent research surfaced a real entanglement (session-registration force-enabling
   pilot as a side effect) that made "just remove the boolean" ambiguous.
4. **`spec/agentweave-spec.html` deliberately left untouched**, not silently forgotten — it
   wasn't part of the plan's file list (found later via a broader repo-wide grep after the
   plan was already approved), and its own internal structure (a versioned revision-history
   table at the top) suggests it wants a dedicated update pass with its own changelog row,
   not a fold-in edit mid-unrelated-task. *Rejected:* editing it anyway since it was "just
   sitting there" — that would silently expand scope beyond what was reviewed at
   `ExitPlanMode`.
5. **The pre-existing dev-DB alembic bug (migration 0001's missing existence guard) was
   hand-patched for this one local file, not fixed at the source.** Fixing `0001_add_agent_outputs.py`
   to check `inspector.get_table_names()` first (matching every migration from 0004 onward)
   is a real, valid, small fix — but it's a pre-existing bug unrelated to pilot-mode removal,
   discovered only incidentally while live-verifying migration 0013. Flagged for the user
   rather than fixed opportunistically, per the standing principle of not silently expanding
   scope mid-task.

## Constraints and user directives (verbatim)

- User (this session, in response to the watchdog/testing status report): **"Scope and
  remove pilot mode now"** — the authorization for this entire chunk's work.
- User, when asked the session-registration entanglement question: **"Remove both entirely
  (Recommended)"** — confirmed removing session-registration alongside pilot mode, not just
  the boolean flag.
- User, when asked the DB-migration question: **"Write a migration to drop the column(s)
  (Recommended)"** — confirmed a real Alembic migration over leaving dead columns.
- User, at plan approval: **"go on"** — approval to proceed with the reviewed plan exactly as
  written (file `C:\Users\huida\.claude\plans\unified-exploring-catmull.md`, still on disk).
- Carried forward, still in force (from every prior handoff in this chain): **"Yeah and
  always commit the changes."** — this chunk's 66 files were committed on completion,
  staged explicitly by path (not `git add -A`), without waiting for a fresh ask. **"After
  every threshold of implementation you must run the skill `/handoff`"** — this file is that.
  **"Before starting a new implementation revise the entire session for the spec."**
  **"let's make sure it works with claude and codex first locally"** — Copilot second (not
  touched this chunk). Project `CLAUDE.md` rules still apply (never commit
  `.agentweave/tasks/`, `messages/`, `agents/`, `session.json`, `transport.json`).
- User, earlier this session (watchdog question): **"No, I'm not starting any watchdog.
  Check if there is any running if not start one (is it necessary?) we're testing the jobs
  right now right? What else needs testing before moving to the next task?"** — resolved:
  a watchdog was already running (PID 25768), confirmed unnecessary for job-firing under
  HTTP transport (the Hub's own APScheduler fires jobs directly per task 3.10), and the dev
  Hub (stale since before 3.9) was restarted with the user's explicit "Yes, restart it now"
  answer to a follow-up question — this happened *before* the pilot-mode work began, not
  part of it, but explains why the dev Hub was already fresh going into this chunk (later
  restarted twice more during this chunk's own verification, each time after further code
  changes).

## Dead ends

- **Assuming `session_sync.py`'s pilot-sync loop had no other purpose** — see Key Decision 1.
  Cost one full test-suite run to discover; fixed without re-litigating the whole file.
- **Plain (non-`recreate="never"`) `batch_alter_table` for migration 0013** — see Key
  Decision 2. Failed in the fresh-file-db test with a `NoSuchTableError` on the FK target
  table; not a dead end in the sense of wasted implementation, just wasted one test-run
  cycle before the right batch-mode option was found.
- **Trusting the plan's Explore-agent file list as exhaustive for Hub-side tests** — it
  missed `hub/tests/test_agents.py`, `hub/tests/test_agents_self_registered.py`, and
  `hub/tests/test_mcp_server.py` entirely (all three had real pilot-dependent tests). Only
  caught by actually running the full test suite rather than trusting the research pass —
  worth remembering for any future large removal in this repo: research-agent file lists are
  a starting point, not a checklist to consider complete without a full-suite run.

## Verification

**Ran and passed, this chunk:**
- `py -m pytest tests/ -q` from repo root → **988 passed, 4 skipped** (was 992 collected;
  4 fewer net due to `test_cli_pilot.py`'s 4 deleted tests, no new failures).
- `py -m pytest tests/ -q` from `hub/` → **329 passed, 4 skipped**, after fixing the 6
  failures described above (was 342 before this chunk per the last 3.11 handoff; net down
  due to test deletions, not failures — final run is fully green).
- `py -m ruff check hub/ tests/` (from `hub/`) → clean.
- `py -m ruff check src/ tests/` (from repo root) → clean (one pre-existing unrelated
  `test_cli_watch.py` import-sort warning, confirmed via `git status` to be untouched by
  this session — not fixed, not introduced here).
- `py -m black --check hub/ tests/` (from `hub/`) → clean (one file reformatted — the new
  migration `0013_drop_agent_pilot_columns.py` — already applied and re-verified clean).
- `py -m black --check src/ tests/` (from repo root) → clean, no reformatting needed.
- `cd hub/ui && npx tsc --noEmit` → clean (caught and fixed one unused-import error:
  `useMutation` in `api/agents.ts` after both mutation hooks using it were deleted).
- `cd hub/ui && npm run build` → succeeds; new bundle copied into
  `hub/hub/static/ui/assets/`, replacing the stale one.
- `cd hub/ui && npm run test` (vitest) → **196 passed** across 22 test files, no failures.
- **Live verification against the actual running dev Hub**: restarted it 3 times total this
  chunk (once before starting pilot-mode work per the user's separate "yes restart it now"
  answer, then twice more after later code fixes during this chunk's own verification pass).
  Confirmed `GET /api/v1/agents` returns `401` (auth-gated, i.e. the app fully started) each
  time. Directly inspected the live SQLite DB's `agents` table schema before and after a
  hand-applied column drop (see Current State) to confirm the schema change is real, not
  just theoretical.

**NOT tested this chunk:**
- `npm run lint` (ESLint) — pre-existing config breakage (`ESLint couldn't find an
  eslint.config.(js|mjs|cjs) file` — this repo still has an old `.eslintrc.*`-style setup
  incompatible with the installed ESLint 9.x). Confirmed pre-existing via a bare rerun,
  not something this chunk introduced or attempted to fix.
- A real end-to-end click-through of the Hub UI's agent detail panel confirming the Pilot
  Mode section is visually gone (only `tsc`/`vitest`/build succeeding were verified, not a
  live browser check).
- `agentweave doctor` was not re-run against a real project to confirm the CLI-side
  `diagnostics.py` changes (removed `agent_pilot_mode` warning) behave correctly outside
  the unit-test suite.
- Migration 0013's `downgrade()` path was not exercised at all (no test calls
  `alembic downgrade`); only `upgrade()` is covered by the fresh-file-db tests.
- The pre-existing migration-0001-idempotency bug (see Current State) was not fixed, so
  it was not verified whether fixing it would have any other side effects on this specific
  dev DB or others.

## Git state

- Branch `hub-native-experience`, **HEAD `d86798d`** — one commit, "Remove pilot mode
  entirely", 66 files changed (590 insertions, 2241 deletions).
- Working tree clean except the six pre-existing untracked `.claude/handoffs/*.md` files
  from earlier sessions (unrelated, unchanged) — this new handoff file and `LATEST.md`'s
  pointer update will be committed in a separate follow-up commit after this file is
  finalized, matching the chain's established two-commit-per-checkpoint pattern.
- No upstream configured — nothing pushed, not requested, unchanged from every prior
  handoff in this chain.
- **Live process state:** dev Hub uvicorn running fresh (last restarted during this chunk's
  own verification, reflects all of this chunk's code). The `agentweave-watch` process
  (PID 25768 as of session start) was not touched this chunk — not re-verified as still
  running at session end.

## Next steps

1. **Nothing is blocking** — this chunk is fully complete and committed. The natural next
   step is `openspec/changes/2026-07-30-hub-native-experience/tasks.md`'s task 3.12 ("Ship
   `alembic.ini` in `package-data`" — a pip install currently logs "alembic.ini not found …
   skipping migrations" and runs unmigrated), which was queued before this pilot-mode
   detour and never started.
2. If the user wants `spec/agentweave-spec.html` updated for the pilot-mode removal, that
   needs its own pass — read the file's own revision-history convention at its top first
   (it expects a new dated row with a CLI/Hub version pair, not a silent diff).
3. If the user wants the pre-existing migration-0001-idempotency bug fixed (unrelated to
   pilot mode, found incidentally), it's a small, well-understood fix: add an
   `inspector.get_table_names()` guard to `hub/hub/migrations/versions/0001_add_agent_outputs.py`
   matching the pattern every migration from 0004 onward already uses. Not started, not
   scoped beyond identifying the exact bug and its exact fix shape.
4. Per the standing directive, continue committing each completed task/checkpoint without
   waiting for a fresh ask, staged explicitly by path.

## Open questions for the user

- **Should `spec/agentweave-spec.html` be updated for this removal?** Not scoped or started
  — flagged in Current State and Next Steps. If yes, treat it as its own small task with a
  new revision-history row, not a quick edit.
- **Should the pre-existing migration-0001 idempotency bug be fixed?** Found incidentally,
  not part of this chunk's scope, not fixed. A real but small and unrelated fix.
- Carried forward, unresolved, not urgent: should anything be pushed to a remote? No
  upstream configured for this branch.
- Carried forward from 3.5–3.11, still not resolved: the "ability to question the user"
  comment from an earlier T3-parity discussion (not touched this chunk).
- Carried forward: task 3.20 (stale Hub UI bundle) — this chunk's own UI rebuild-and-copy
  step is a manual instance of exactly that structural problem; still unfixed as a general
  mechanism (the Hub doesn't auto-detect/auto-rebuild a stale bundle).

## Read on resume

- `C:\Users\huida\.claude\plans\unified-exploring-catmull.md` — the approved removal plan
  this chunk executed; useful to compare against what actually happened (two deviations
  found during execution: the `session_sync.py` partial-revert and the migration's
  `recreate="never"` fix, both documented above, neither in the original plan).
- `hub/hub/migrations/versions/0013_drop_agent_pilot_columns.py` — the new migration; read
  its docstring for why `recreate="never"` matters before touching any future migration on
  the `agents` table.
- `hub/hub/api/v1/session_sync.py` — the `sync_session()` function; the Agent-row-creation
  loop here is subtler than it looks (see Key Decision 1) — don't remove it again without
  re-checking `GET /agents/agent-context`'s `"registered"` field dependency.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — task 3.12 is the queued
  next step on the change this session's work was itself a detour from.
- `spec/agentweave-spec.html` — if the open question above gets a "yes," start by reading
  its own top-of-file revision-history table convention before editing anything.
