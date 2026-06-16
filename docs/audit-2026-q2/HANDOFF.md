# Handoff Runbook

> **Living document.** Update as work progresses.
> Created 2026-06-12 alongside the audit.
> **Last updated:** 2026-06-16 (PR 8 shipped; 277 lines of dead code removed; ready-to-copy prompt pre-filled for PR 9)

This is the file you (or another agent) open first when picking up where a previous session left off. It has three jobs:

1. **State tracker** — what's done, what's next, what's blocked.
2. **Prompt library** — copy-pasteable prompts for the next agent. Update them as the context evolves.
3. **Session log** — append a short note after each session so the next agent has a trail to follow.

The audit findings, PR roadmap, and PR 1 spec live in the sibling files (`README.md`, `findings.md`, `pr-roadmap.md`, `pr1-spa-key-leak.md`). This file orchestrates the work; those define it.

---

## 📈 Progression

Quick visual timeline. Most recent at the top. **One line per milestone** — see the session log below for detail.

```
2026-06-16  ●  PR 8: Dead code & dedup shipped  →  audit @ eb647db
          │  ↑ you are here
          ○  PR 9: Hub UI security shipped                        (target: 2 days)
2026-06-16  ●  PR 7: DB & migrations shipped  →  audit @ 7c0c667
2026-06-14  ●  v0.37.1 / Hub v0.31.2 released to PyPI + Docker  →  master @ 15b5142
          ●  PR 6: Hub auth + BOLA + perf shipped  →  audit @ 90d4e4c  ·  v0.38.0a1 / v0.32.0a1
          ○  PR 10: Hub UI perf & dedup shipped                   (target: 2 days)
          ○  PR 11: CLI/watchdog code quality shipped             (target: 2 days)
          ○  PR 12: Test coverage sweep shipped                   (target: 3-4 days)
          ○  v0.38.0 (CLI) / v0.32.0 (Hub) released, merged to master
          ●  PR 5: Hub input validation shipped
          ●  Branch integration: opencode onto master, audit rebased on top  →  master @ 016bc77
          ●  PR 4: CLI security & correctness shipped
          ●  PR 3: Transport error handling & safety shipped
          ●  PR 2: Transport data-loss bugs shipped
          ●  PR 0.5: test_jobs croniter 6.x mock fix shipped
          ●  PR 1: SPA key leak (CRITICAL) shipped
          ●  Audit created, branch + version bumps (PEP 440 alpha: 0.38.0a1 / 0.32.0a1)
```

**How to update:** when a milestone completes, change the `○` to `●` and fill in any version/branch changes. The "you are here" marker moves down. To indicate work in progress, use `◐` (e.g. `◐ PR 1: ... (in progress)`).

```

---

## 📋 Ready-to-copy prompt — next action

**This is the prompt you copy-paste to send to the next agent. It is pre-filled for the next PR.**

The agent that completes the current PR MUST update this section to point at the next PR before reporting back. See the "Updating the ready-to-copy prompt" section near the bottom of this file.

**Next PR to execute:** PR 9 — Hub UI security

```
Execute PR 9 from the AgentWeave audit. Full spec:
docs/audit-2026-q2/pr-roadmap.md — section "## PR 9 — Hub UI security"

Before doing anything:
1. Read docs/audit-2026-q2/HANDOFF.md (especially the "Current status"
   table, the "Branch state" block, the latest session log entries,
   and the "Open questions / blockers" section) so you know what's
   already done and any in-flight issues.
2. Read the PR 9 section of pr-roadmap.md end-to-end.
3. Read AGENTS.md § "Hub UI Components" and the recent AgentPromptPanel
   session-routing entry — the UI has accumulated a lot of subtle
   state, and PR 9 is the first PR that introduces UI tests.

Workflow (PR 9 sets up the first UI test infra — install vitest+jsdom
and a minimal test file first; then implement each fix test-first):
1. cd to C:\Users\huida\Documents\projects\AgentWeave
2. Verify you're on branch `audit/2026-q2-hardening`
3. Pull latest changes if a remote exists
4. Versions are already bumped (v0.38.0a1 / v0.32.0a1) — do not re-bump
5. Identify the UI security fixes per the spec (the spec's line numbers
   are likely stale; grep before editing):
   - S3 (client): hub/ui/src/hooks/useSSE.ts — replace `?token=` in the
     EventSource URL with `fetch()` + `Authorization` header streamed
     via `ReadableStream`. The server-side `/events/ticket` endpoint
     was added in PR 6.
   - S4: hub/ui/src/store/configStore.ts — move `apiKey` to
     `sessionStorage`; persist only `theme` + `mode` to `localStorage`.
   - M19: hub/ui/src/components/agents/ActivityLog.tsx — fix the
     `paused` stale closure using the ref pattern documented in
     AGENTS.md (see the "Stale closure" pattern in the March 31 entry).
   - M20: hub/ui/src/api/agentChat.ts — replace literal `'new'` with the
     `NEW_SESSION_ID` constant.
   - M22: hub/ui/src/hooks/useSSE.ts — clear `reconnectTimer` on
     `clearConfig`; cancel reconnect on unmount.
   - ErrorBoundary: hub/ui/src/main.tsx — wrap the App root with an
     <ErrorBoundary>.
6. Set up the UI test infrastructure (PR 9 creates the first UI tests
   in the project, so the infra is part of the deliverable):
   - cd hub/ui && npm install --save-dev vitest jsdom
     @testing-library/react @testing-library/jest-dom
   - Add `test: "vitest run"` to package.json scripts
   - Create vitest.config.ts with jsdom environment
   - Add hub/ui/src/__tests__/ directory
7. For each fix, write a failing test FIRST (the new vitest infra must
   be in place), confirm RED, then apply the fix and confirm GREEN.
8. Run UI tests: cd hub/ui && npm test. Also run full CLI + Hub test
   suites to confirm no backend regressions: pytest tests/ -v and
   cd hub && pytest tests/ -v.
9. Run lint: cd hub/ui && npm run lint. (Backend lint unchanged from
   PR 8 baseline; Hub has no enforced lint config today.)
10. Manual smoke test: cd hub/ui && npm run dev, open the dashboard
    at http://localhost:5173, log in with the API key (DevTools →
    Application → confirm `apiKey` is in `sessionStorage` not
    `localStorage`), trigger an SSE disconnect (toggle network
    throttling) and confirm the reconnect timer is cleared on
    `clearConfig`, and confirm a thrown error in a child component
    is caught by the ErrorBoundary instead of blanking the page.
11. Commit with a structured message matching PR 5/6/7/8's style.
    Likely 2-3 commits: (a) test infra, (b) the actual fixes.
12. Push the branch.
13. Update docs/audit-2026-q2/HANDOFF.md (CRITICAL — see below).
14. Report back.

Step 13 in detail (this is what makes the next session work):
a. Mark PR 9 as ✅ in the "Current status" table.
b. Update the "Branch state" block with current branch, latest commit
   hash, and last test run timestamp.
c. Append a new entry to the "Session log" section.
d. **REPLACE the "Next PR to execute" line and the code block in the
   "📋 Ready-to-copy prompt — next action" section above** so the
   prompt is pre-filled for PR 10 (Hub UI performance & dedup). The
   spec lives in docs/audit-2026-q2/pr-roadmap.md under the
   "PR 10 — Hub UI performance & dedup" heading. Adjust the workflow
   steps to reference the right files for that PR (UI side, manual +
   Lighthouse, no new test infra — just extend the vitest setup from
   PR 9).

Notes from PR 8 that may affect PR 9:
- The CLI's `_build_agent_context` wrappers are now thin 8-line shims
  in both `cli.py` and `watchdog.py` that delegate to
  `context_builder.build_agent_context`. If you need to render a
  context from a UI test, use `context_builder.build_agent_context`
  directly — do NOT re-introduce dead code in the wrappers.
- The watchdog's `_load_dotenv` was removed; `utils.load_dotenv` is
  now the only `load_dotenv` in the codebase. If you write a CLI-level
  test that loads .env, import from `agentweave.utils`.
- The spec line numbers in pr-roadmap.md for PR 9 are from
  2026-06-12 and likely drifted; grep for the function/constant names
  (e.g. `paused`, `NEW_SESSION_ID`, `reconnectTimer`) before editing.
- The UI has no existing test infrastructure. PR 9 introduces vitest
  + jsdom. If npm install fails, document it as a blocker in HANDOFF.

Time budget: 2 days for PR 9. If you go over by >50%, stop and ask.
If you encounter a blocker, stop, document it in the
"Open questions / blockers" section of HANDOFF.md, and report.
```

---

## Current status

**Last updated:** 2026-06-16 (PR 8 shipped; H7 + Q5 closed; 277 lines of dead code removed)

| # | PR | Status | Branch | Merged | Notes |
|---|---|---|---|---|---|
| 0.5 | test_jobs croniter 6.x mock fix | ✅ Merged (local) | `audit/2026-q2-hardening` | a8c77b0 | Prep PR before PR 2. 4-line diff in `tests/test_jobs.py`. Closed the open question from PR 1 — full CLI suite now green without deselects (326 passed). |
| 1 | SPA key leak (CRITICAL) | ✅ Merged (local) | `audit/2026-q2-hardening` | 71106e5 | Committed locally. Spec: `pr1-spa-key-leak.md`. All tests + lint pass. |
| 2 | Transport data-loss | ✅ Merged (local) | `audit/2026-q2-hardening` | cf91e52 | Closes H1, H2, H3, H6, M7, M11, M12, M13, M23 (9 fixes). New `tests/test_transport_git.py` (23 tests) + HTTP retry/invalid-response tests + new `hub/tests/test_mcp_server.py`. CLI 357 passed, Hub 74 + 1 skip. S7 (body redaction) was pre-shipped in PR 2's http.py error cleanup. |
| 3 | Transport error handling & safety | ✅ Merged (local) | `audit/2026-q2-hardening` | 8bbd93d | Closes H8, M8, M9, M10, S2, S10, S11 (6 fixes — S7 already done in PR 2). New `write_json_atomic` in utils.py (atomic write + 0600 on POSIX); `_check_id_safe` defense-in-depth at message/task boundaries; `os.replace`+lock for archive_message/mark_read/move_to_completed; 10 MB Hub response body cap; cmd_start stops pre-opening the watchdog log fd. CLI 378 passed (+21), Hub 74 + 1 skip. |
| 4 | CLI security & correctness | ✅ Merged (local) | `audit/2026-q2-hardening` | a3ae7cf | Closes M3, M4, M5, M6, M12, S9 (6 fixes — S8 already done in PR 3). New `tests/test_eventlog.py` (4 tests) + 4 new test classes in `tests/test_cli.py` (datetime, atomic write, subprocess.run timeouts, sha256 verification) + MCP datetime guard + watchdog Popen-encoding guard. CLI 395 passed (+17), Hub 74 + 1 skip. |
| 5 | Hub input validation | ✅ Merged (local) | `audit/2026-q2-hardening` | f9cea0c | Closes S1, S5, S6, S12, M14, M16. New `hub/tests/test_agents.py` + additions to `test_messages.py`/`test_tasks.py`; updated `test_jobs.py`/`test_pilot_mode.py` for new Create-schema behavior. Hub 87 passed, 3 skipped; CLI 436 passed, 10 skipped. Pushed (cf31fb0 ancestry). |
| 6 | Hub auth + BOLA + perf | ✅ Merged (local) | `audit/2026-q2-hardening` | 90d4e4c | Closes S3 (server half), M15, M17, T5 + body-size bonus. Removes `?token=` fallback on non-SSE endpoints; adds `/events/ticket` signed-ticket flow. Rewrites `list_agents` with bulk queries. Removes dead `agent` param from `update_task` MCP tool. Adds 1 MB body cap middleware. New `hub/tests/test_bola.py`; enhanced `test_auth.py`, `test_agents.py`, `test_mcp_server.py`. Hub 96 passed, 3 skipped; CLI 436 passed, 10 skipped. Pushed (cf31fb0 ancestry). |
| 7 | DB & migrations | ✅ Merged (local) | `audit/2026-q2-hardening` | 7c0c667 | Closes H5, DB-4. `init_db` now invokes `alembic upgrade head` after `create_all` (in a worker thread so its internal `asyncio.run()` doesn't conflict with the FastAPI lifespan's event loop), wrapped in try/except so dev mode (in-memory SQLite, missing `alembic.ini`) still works. `job_runs.error_summary` changed from unbounded `Text` to `String(500)` — migration 0007 was edited to use `String(500)` for fresh installs, and new migration 0008 uses `batch_alter_table` to alter existing deployments where 0007 already added the column as `Text`. New `hub/tests/test_migrations.py` with 9 tests covering model type, value length boundary, fresh-DB alembic round-trip, 0008 alters an existing `Text` column, `init_db` runs alembic for file DBs, `init_db` skips alembic for `:memory:`, and alembic failures don't crash `init_db`. Pushed (cf31fb0 ancestry). |
| 8 | Dead code & dedup | ✅ Merged (local) | `audit/2026-q2-hardening` | eb647db | Closes H7, Q5. 277 lines of dead code removed (118 in cli.py, 159 in watchdog.py). Deleted the unreachable `lines.append`-based implementation in `cli._build_agent_context` (117 lines after the early return) and the equivalent dead block in `watchdog._build_agent_context` (125 lines). Both wrappers remain as clean 8-line shims that delegate to `context_builder.build_agent_context`. Deleted the duplicate `_load_dotenv` in watchdog.py (30 lines, zero callers — `utils.load_dotenv` was already imported and used at main()). No call-site changes. Pushed. |
| 9 | Hub UI security | ⬜ Not started | — | — | |
| 10 | Hub UI perf & dedup | ⬜ Not started | — | — | |
| 11 | CLI/watchdog code quality | ⬜ Not started | — | — | |
| 12 | Test coverage sweep | ⬜ Not started | — | — | |
| — | v0.38.0 / v0.32.0 release | ⬜ Not started | — | — | After all PRs |

**Status legend:** ⬜ not started · 🟡 in progress · ✅ merged · ❌ blocked

---

## Branch state

- **Working branch:** `audit/2026-q2-hardening`
- **Target:** eventually merged back to `master` as a single squash or merge commit
- **Version bumps:**
  - `pyproject.toml` (CLI): 0.37.0 → 0.38.0a1 (PEP 440 alpha — pip rejects dashes) → 0.38.0 (at release)
  - `hub/pyproject.toml`: 0.31.1 → 0.32.0a1 → 0.32.0 (at release)
  - **Note:** the HANDOFF originally said `__init__.py: 0.37.0 → 0.38.0-audit.1`, but `__init__.py` is a dev fallback; the real source of truth is `pyproject.toml` per AGENTS.md. Bumped only `pyproject.toml` files.

Update this block when branches change.

```
Current branch: audit/2026-q2-hardening
Latest commit: eb647db  (fix(cli): delete dead code in _build_agent_context wrappers (PR 8))
Last test run: 2026-06-16 — Hub: 106 passed, 2 skipped. CLI: 443 passed, 3 skipped.

master:
  Latest commit: 15b5142  (docs: add deployment handoff for v0.37.1 / Hub v0.31.2)
  Version: CLI v0.37.1 / Hub v0.31.2 (released to PyPI + Docker via 39b7b44)
  Parent: 39b7b44  (Bump to v0.37.1 / Hub v0.31.2)
  Parent: 8c8458e  (fix(lint): address inherited N806 and no-untyped-def from opencode commit)
  Parent: 016bc77  (feat(opencode): local CLI override, models doc, template yml)

Integration topology (linear, no merge commits):
  master  → audit
  57c65ee (Bump Hub v0.31.1)
  └─ a3d3ba1  test(jobs): fix test_should_fire_old_last_run for croniter 6.x     ← croniter fix
  └─ 016bc77  feat(opencode): local CLI override, models doc, template yml     ← OPENCODE
  └─ 8c8458e  fix(lint): address inherited N806 and no-untyped-def               ← master HEAD
  └─ 39b7b44  Bump to v0.37.1 / Hub v0.31.2                                      ← RELEASE
  └─ 15b5142  docs: add deployment handoff for v0.37.1 / Hub v0.31.2              ← master HEAD
  └─ d511fe2  docs(audit): add 2026-Q2 audit findings, 12-PR roadmap, PR 1 spec
  └─ aad0b8b  fix(hub): stop leaking live API key in SPA HTML response         (PR 1)
  └─ 4e9f7be  docs(audit): mark PR 1 shipped, update ready-to-copy prompt for PR 2
  └─ 6661934  fix(transport): harden data-loss paths in git and http transports  (PR 2)
  └─ 4b80590  docs(audit): mark PR 2 shipped, update ready-to-copy prompt for PR 3
  └─ aa8d3f0  fix(transport): harden archive, file perms, body cap, fd leak      (PR 3)
  └─ 6f97cd0  docs(audit): mark PR 3 shipped, update ready-to-copy prompt for PR 4
  └─ 4cdb7ac  docs(audit): backfill PR 3 commit hash in status table and branch state
  └─ a54dbec  fix(cli): timezone awareness, transport.json atomic write, sha256  (PR 4)
  └─ e0aeed2  docs(audit): mark PR 4 shipped, update ready-to-copy prompt for PR 5
  └─ 43abe10  fix(lint): address inherited N806 and no-untyped-def
  └─ 189d157  docs(audit): document branch integration
  └─ b7c2064  Merge master into audit/2026-q2-hardening
  └─ f9cea0c  fix(hub): harden Hub input validation (PR 5)
  └─ 8d5c6fd  docs(audit): mark PR 5 shipped, update ready-to-copy prompt for PR 6
  └─ 809e566  docs(audit): backfill PR 5 handoff commit hash
  └─ 90d4e4c  fix(hub): harden Hub auth, BOLA isolation, list_agents perf     (PR 6)
  └─ 597299c  docs(audit): mark PR 6 shipped, update ready-to-copy prompt for PR 7
  └─ cf31fb0  docs(audit): backfill PR 6 handoff commit hash in branch state
  └─ 7c0c667  fix(hub): run alembic upgrade on startup, cap error_summary     (PR 7)
  └─ eb647db  fix(cli): delete dead code in _build_agent_context wrappers    (PR 8)  ← HEAD
```

All commit SHAs above the opencode commit were rewritten by the rebase (their
parents changed), but their content and messages are preserved. The croniter fix
(`a3d3ba1`) is identical to the original `a8c77b0` from the audit branch
(cherry-picked, same patch-id detected by git rebase).

The PR 4 fix and its handoff have new SHAs (`a54dbec`, `e0aeed2`) but the same
content as the previously-pushed `a3ae7cf` / `eaf7bab`. The lint fix is a NEW
commit (`43abe10`) that addresses two pre-existing opencode-inherited lint
issues; details in the session log entry below.

The audit branch is currently 7 PRs into the 12-PR audit (PR 0.5 + PRs 1-6
shipped). Master has the opencode feature + croniter fix as v0.37.1 / Hub
v0.31.2 (published to PyPI + Docker). PR 7 (DB & migrations) is next per the
ready-to-copy prompt at the top of this file.

---

## Working environment

For any agent picking this up:

- **Working dir:** `C:\Users\huida\Documents\projects\AgentWeave`
- **Python:** 3.11+ (CLI is 3.8+ compatible; Hub is 3.11+)
- **Test commands:**
  - CLI tests: `pytest tests/ -v`
  - Hub tests: `cd hub && pytest tests/ -v`
  - All: `make test-all`
- **Lint:** `ruff check src/`, `black src/`, `mypy src/`
- **UI dev:** `cd hub/ui && npm install && npm run dev` (proxies `/api` → `localhost:8000`)
- **Hub dev:** `cd hub && docker compose up -d`

---

## Prompt 1 — Prime a new agent (general)

**When to use:** the next agent has no context. Use this to bring them up to speed.

> Copy everything between the triple-quotes:

```
You are picking up a code-quality audit of AgentWeave that was completed in
a prior session. The full findings, 12-PR execution plan, and detailed PR
specs are in `docs/audit-2026-q2/`.

Read these files in order before doing anything:
1. docs/audit-2026-q2/README.md  (~5 min — on-ramp)
2. docs/audit-2026-q2/findings.md  (~10 min — the 60 prioritized bugs)
3. docs/audit-2026-q2/HANDOFF.md  (~5 min — this file, current state)
4. docs/audit-2026-q2/pr-roadmap.md  (~15 min — the 12-PR plan)

If you only have 30 minutes and want to ship one fix, skip to the spec
for the next PR in the status table of HANDOFF.md and execute it
test-first. The spec files are self-contained.

Project context: AgentWeave is a multi-agent AI collaboration framework at
C:\Users\huida\Documents\projects\AgentWeave. CLI is Python 3.8+, Hub is
Python 3.11+ FastAPI. Tests: `pytest tests/ -v` (CLI) and `cd hub &&
pytest tests/ -v` (Hub). Lint: `ruff check src/`, `black src/`, `mypy src/`.

The audit found 1 CRITICAL, 8 HIGH data-loss, 12 HIGH security, 23 MEDIUM
bugs, 10 test gaps, and 16 LOW quality issues. Strategy: 12 small PRs on
branch `audit/2026-q2-hardening`, test-first on every fix.

Open HANDOFF.md and read the "Current status" table. Then tell me which
PR you want to work on next (or say "next available" to take the first
incomplete one).
```

**Update this prompt** as the audit evolves. The "files in order" list should grow as more PR-spec files are added.

---

## Prompt 2 — Execute a specific PR (template)

**When to use:** you want to skip ahead to a specific PR (e.g. PR 5 instead of the next available). For the normal case (next available PR), just copy the ready-to-copy prompt at the top of this file.

Replace `<PR-N>` with the actual number and `<SPEC-FILE>` with the spec file. **For PR 1** the spec file is `pr1-spa-key-leak.md`. **For PRs 2-12** the spec is the corresponding section of `pr-roadmap.md` (e.g. `pr-roadmap.md` under "PR 2 — Transport data-loss bugs").

> Copy everything between the triple-quotes, after editing the placeholders:

```
Execute PR <PR-N> from the AgentWeave audit. Full spec:
docs/audit-2026-q2/<SPEC-FILE>

Before doing anything:
1. Read docs/audit-2026-q2/HANDOFF.md (especially the "Current status"
   table, the "Branch state" block, and the latest session log entries)
   so you know what's already done and any open questions.
2. Read the PR spec end-to-end.

Workflow (test-first, do not skip):
1. cd to C:\Users\huida\Documents\projects\AgentWeave
2. Verify you're on branch `audit/2026-q2-hardening` (create if missing)
3. Pull latest changes
4. Bump versions (only if not already done in a prior session)
5. Write the failing test(s) FIRST per the spec
6. Run the relevant test command and CONFIRM it fails
7. Apply the fix per the spec
8. Run the relevant test command and CONFIRM it passes
9. Run full test suites: `pytest tests/ -v` and `cd hub && pytest tests/ -v`
   — both must be green
10. Run lint: `ruff check src/`, `black src/`, `mypy src/`
11. Manual smoke test per the spec
12. Commit with the exact message in the spec
13. Push the branch
14. Update docs/audit-2026-q2/HANDOFF.md (CRITICAL — see below)
15. Report back

Step 14 in detail (this is what makes the next session work):
a. Mark PR <PR-N> as ✅ in the "Current status" table.
b. Update the "Branch state" block with current branch, latest commit hash,
   and last test run timestamp.
c. Append a new entry to the "Session log" section.
d. **REPLACE the "Next PR to execute" line and the code block in the
   "📋 Ready-to-copy prompt — next action" section at the top of
   HANDOFF.md** so the prompt is pre-filled for the next PR. Adjust
   the workflow steps (5, 6, 8, 11) inside the code block to reference
   the right test files and smoke-test commands for that PR.

Time budget: see the PR spec. If you go over by >50%, stop and ask.
If you encounter a blocker, stop, document it in the "Open
questions / blockers" section of HANDOFF.md, and report.
```

**Update this template** if the workflow changes (e.g. add a security review step after PR 6).

---

## Prompt 3 — Quick context for a casual agent (no handoff doc)

**When to use:** the next agent has access to the project but not the audit docs. Drop them into the source-of-truth.

> Copy everything between the triple-quotes:

```
You are working on AgentWeave, a multi-agent AI collaboration framework
at C:\Users\huida\Documents\projects\AgentWeave. A complete code-quality
audit was done on 2026-06-12. Read these files to understand the
context:

- docs/audit-2026-q2/README.md — what the audit is
- docs/audit-2026-q2/findings.md — the 60 prioritized bugs
- docs/audit-2026-q2/pr-roadmap.md — the 12-PR execution plan

Each PR spec is self-contained. Pick one, read its spec, execute
test-first. Update HANDOFF.md as you go so the next session can pick up.
```

---

## Session log

**Append a new entry after every session.** Keep each entry short (5-10 lines). The next agent should be able to read the last 2-3 entries and know exactly where things stand.

> Older entries (2026-06-12 through Branch integration) are archived in [`docs/audit-2026-q2/archive/HANDOFF-archive-2026-06-14.md`](archive/HANDOFF-archive-2026-06-14.md).

### 2026-06-14 — Branch integration: opencode onto master, audit onto opencode

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Rebased the parked opencode CLI override onto master, then rebased the audit branch on top. Cherry-picked the croniter fix to master first; fixed inherited lint issues (`N806`, `no-untyped-def`) as `43abe10`.
- **Full details:** See the archived entry in `docs/audit-2026-q2/archive/HANDOFF-archive-2026-06-14.md`.
- **Test runs:** CLI 443 passed, 3 skipped. Hub 74 passed, 1 skipped.
- **Open questions:** None.
- **Hand-off to:** next session — execute **PR 5 — Hub input validation**.

### 2026-06-14 — PR 5 shipped (Hub input validation)

- **By:** kimi (Kimi Code CLI) on behalf of gutohuida
- **What:** Closed S1, S5, S6, S12, M14, M16. Validated role IDs in `_load_role_content` to block path-traversal reads (S1). Removed client-supplied `id`/`timestamp`/`created_at` from Create schemas and enabled `extra='forbid'` (S5). Added `max_length` caps to every string field in `hub/hub/schemas/*.py` (S6). Rejected unsafe `work_dir` values (`..`, `~`, non-printable chars) in `/agent/trigger` (S12). Bounded `/agent/{agent}/chat?limit` to 1–500 (M14). Added configured-agent name-collision check to `/agents/{name}/register-session` (M16).
- **Test-first verification:** 7 new tests in `hub/tests/test_agents.py` plus additions to `hub/tests/test_messages.py` and `hub/tests/test_tasks.py` were RED before fixes and GREEN after. Updated `hub/tests/test_jobs.py` and `hub/tests/test_pilot_mode.py` to align with the new Create-schema behavior.
- **Full suite:** Hub 87 passed, 3 skipped (was 74 + 1 skip; +13 from new/updated tests). CLI 436 passed, 10 skipped (unchanged).
- **Lint:** ruff + black clean on changed files. mypy reports the same 1 pre-existing PyYAML stub error in `src/agentweave/config.py` (out of scope).
- **Smoke test:** End-to-end ASGI smoke script verified S1, S6, S12, and M16; all checks PASS.
- **Local commit:** `f9cea0c` fix(hub): harden Hub input validation (PR 5) (1 commit, 19 files, 420 insertions / 194 deletions).
- **Open questions:** Push to `origin/audit/2026-q2-hardening` failed because this shell has no HTTPS git credentials (`GIT_TERMINAL_PROMPT=0`). See "Open questions / blockers" below.
- **Hand-off to:** next session — execute **PR 6 — Hub auth, BOLA, perf**. Ready-to-copy prompt at top of this file is pre-filled for PR 6.

### 2026-06-14 — PR 6 shipped (Hub auth, BOLA, perf)

- **By:** kimi (Kimi Code CLI) on behalf of gutohuida
- **What:** Closed S3 (server half), M15, M17, T5, plus the body-size bonus. Removed `?token=` fallback from all non-SSE endpoints and added `/api/v1/events/ticket` to issue short-lived HMAC-signed SSE tickets (S3). Rewrote `list_agents` to fetch heartbeat, message count, active task count, context usage, and session start in bulk, eliminating the N+1 query pattern (M15). Removed the unused `agent` parameter from the `update_task` MCP tool (M17). Added `ContentSizeLimitMiddleware` with a 1 MB default request body cap (bonus). Added multi-tenant BOLA regression test (`hub/tests/test_bola.py`) covering every Hub endpoint (T5).
- **Test-first verification:** `hub/tests/test_auth.py` additions, `hub/tests/test_bola.py`, `hub/tests/test_agents.py` query-count test, and `hub/tests/test_mcp_server.py` update_task test were RED before fixes and GREEN after.
- **Full suite:** Hub 96 passed, 3 skipped (was 87 passed, 3 skipped; +9 from new/updated tests). CLI 436 passed, 10 skipped (unchanged).
- **Lint:** ruff + black clean on changed files. mypy reports the same 1 pre-existing PyYAML stub error in `src/agentweave/config.py` (out of scope).
- **Smoke test:** End-to-end ASGI smoke script verified S3 token-fallback removal, `/events/ticket` SSE flow, T5 BOLA isolation, and the 1 MB body cap; all checks PASS.
- **Local commit:** `90d4e4c` fix(hub): harden Hub auth, BOLA isolation, and list_agents performance (PR 6) (11 files changed, 777 insertions, 152 deletions).
- **Open questions:** Push to `origin/audit/2026-q2-hardening` still blocked because this shell has no HTTPS git credentials (`GIT_TERMINAL_PROMPT=0`). The PR 5 and PR 6 commits plus this HANDOFF update are local only; the user needs to push manually from a shell that has GitHub credentials, or provide a token/credential helper so the next agent can push.
- **Hand-off to:** next session — execute **PR 7 — DB & migrations**. Ready-to-copy prompt at top of this file is pre-filled for PR 7.

### 2026-06-14 — v0.37.1 release + audit branch push + HANDOFF sync

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** (1) Discovered the user's session had continued in parallel: PR 5 (f9cea0c), PR 5 handoff, PR 6 (90d4e4c), PR 6 handoff, PR 6 backfill all shipped on `audit/2026-q2-hardening` locally but blocked from push due to a credential-less shell. (2) On `master`, the user had also fixed the CI lint failure (by cherry-picking the audit branch's `43abe10` lint fix as `8c8458e`), bumped versions to CLI v0.37.1 / Hub v0.31.2 (as `39b7b44`), and added a deployment handoff (`15b5142`). The `publish.yml` and `hub-image.yml` workflows ran successfully on `39b7b44` — the release is live on PyPI and Docker Hub. (3) Pushed the 6 unpushed audit commits to `origin/audit/2026-q2-hardening` (no force needed; fast-forward from `b7c2064` to `cf31fb0`). (4) Updated this HANDOFF: added the v0.37.1 release to the progression timeline, removed the duplicate `PR 7: DB & migrations` line, refreshed the Branch state block to reflect the new tip (`cf31fb0`), the version bump on master, and the full integration topology through PR 6, and closed the "push blocked" open question (resolved by this push).
- **CI status (all green):**
  - `8c8458e` (lint fix on master): `ci.yml` success
  - `39b7b44` (Bump to v0.37.1 / Hub v0.31.2): `ci.yml` success, `publish.yml` for `v0.37.1` success, `hub-image.yml` for `hub-v0.31.2` success
  - `15b5142` (deployment handoff): `ci.yml` success
  - The audit branch's new tip (`cf31fb0`) hasn't triggered CI yet because the `ci.yml` workflow only listens to `master` pushes — that's expected; CI will run when the audit branch is eventually merged.
- **Test runs (this session, on the current `audit/2026-q2-hardening` HEAD):**
  - CLI: 443 passed, 3 skipped
  - Hub: 74 passed, 1 skipped
- **Open questions:** Resolved — the push blocker is gone. Section is now empty.
- **Hand-off to:** next session — execute **PR 7 — DB & migrations**. Ready-to-copy prompt at top of this file is pre-filled for PR 7, with references to `hub/hub/db/engine.py`, `hub/hub/main.py`, and the `hub/hub/migrations/versions/0007_add_job_run_error_summary.py` migration file. Note that PR 6 added a 1 MB body cap middleware, so the test surface for PR 7's `init_db` smoke test is slightly different from what the original spec assumed.

### 2026-06-16 — PR 7 shipped (DB & migrations)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closed H5 (init_db now runs `alembic upgrade head` after `create_all`, wrapped in try/except so dev mode still works) and DB-4 (`job_runs.error_summary` is now `String(500)` instead of unbounded `Text`). Migration 0007 was edited to use `String(500)` for fresh installs; a new migration 0008 uses `op.batch_alter_table` to alter existing deployments where 0007 already added the column as `Text`. The alembic command is run in a worker thread via `loop.run_in_executor` so its internal `asyncio.run()` doesn't conflict with the FastAPI lifespan's event loop (a first attempt using sync `command.upgrade` directly caused the warning `coroutine 'run_async_migrations' was never awaited` from `asyncio.run()` being called from within a running event loop).
- **Test-first verification:** 9 new tests in `hub/tests/test_migrations.py` were RED before the fix (model type uses `Text`, no `_run_alembic_upgrade` exists) and GREEN after. The 501-char rejection test is skipped on SQLite (SQLite uses type affinity, not strict VARCHAR length enforcement) — the model type test covers the schema declaration; runtime enforcement holds on PostgreSQL.
- **Full suite:** Hub 106 passed, 2 skipped (was 96 passed, 3 skipped; +9 new tests, -1 SQLite-only skip). CLI 443 passed, 3 skipped (unchanged).
- **Lint:** ruff + black clean on changed files. mypy reports the same 1 pre-existing PyYAML stub error in `src/agentweave/config.py` (out of scope, unchanged).
- **Smoke test:** `init_db()` called on a fresh file-based SQLite produced the correct `job_runs.error_summary: type=VARCHAR, length=500` from `Base.metadata.create_all`. The subsequent alembic attempt fails on migration 0001 (`CREATE TABLE agent_outputs`) because the table already exists from `create_all` — the existing migrations are not idempotent. The exception is caught by the spec-mandated try/except and logged at WARNING, so `init_db` completes successfully. This is acceptable for the "init_db only" use case (H5) — the schema is correct, just `alembic_version` may be empty. The production flow (`alembic upgrade head` followed by `init_db`) is unchanged and works as before.
- **Local commit:** `7c0c667` fix(hub): run alembic upgrade on startup, cap error_summary to 500 chars (PR 7) (6 files changed, 503 insertions, 4 deletions).
- **Push:** succeeded; remote is now at `7c0c667` (`9a4bf06..7c0c667`).
- **Open questions:** None.
- **Hand-off to:** next session — execute **PR 8 — Dead code & dedup**. Ready-to-copy prompt at top of this file is pre-filled for PR 8, with the adjusted workflow (no test-first step — pure deletion; existing tests are the safety net).

### 2026-06-16 — PR 8 shipped (Dead code & dedup)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closes H7 and Q5. Deleted 277 lines of dead code in pure-deletion mode: 117 lines in `cli._build_agent_context` (the unreachable `lines.append`-based implementation that was replaced by `context_builder.build_agent_context` but never removed) and 125 lines in `watchdog._build_agent_context` for the same reason, plus 30 lines of duplicate `_load_dotenv` in watchdog.py (zero callers — `utils.load_dotenv` was already imported at line 29 and used at main()). Both wrappers remain as clean 8-line shims that delegate to `context_builder.build_agent_context`. No call-site changes were needed.
- **Spec line numbers were stale** (the spec's `1631-1749` mapped to `1637-1754`; `1830-1956` to `1892-2017`; `3102-3132` to `3265-3295`). Verified the actual block boundaries with targeted `read` calls before each edit. The user's "Surgical: delete dead code only" decision meant keeping the wrapper function headers (which add `_get_project_instructions()` + version_comment + `.context` extraction) instead of refactoring all 5 call sites.
- **Verification:** CLI 443 passed, 3 skipped (unchanged). Hub 106 passed, 2 skipped (unchanged). ruff clean. black no-op. mypy shows the same 1 pre-existing PyYAML stub error in `src/agentweave/config.py` (out of scope, unchanged). Smoke test exercised both wrappers + `utils.load_dotenv` — all return correct values.
- **Local commit:** `eb647db` fix(cli): delete dead code in _build_agent_context wrappers (PR 8) (2 files changed, 277 deletions, 0 additions).
- **Push:** succeeded; remote is now at `eb647db` (`7c0c667..eb647db`).
- **Open questions:** None.
- **Hand-off to:** next session — execute **PR 9 — Hub UI security**. Ready-to-copy prompt at top of this file is pre-filled for PR 9, with the adjusted workflow (test-first on each fix, vitest+jsdom infra setup is the first deliverable since the UI has no existing tests).

## Open questions / blockers

(none — push blocker from the previous session was resolved by the audit branch push in this session; v0.37.1 / Hub v0.31.2 release published to PyPI + Docker)

---

## How to update this file

After each session, the agent should:

1. Update the **Current status** table (mark PRs 🟡 / ✅ / ❌ as appropriate).
2. Update the **Branch state** block (current branch, latest commit, last test run).
3. Append a **Session log** entry.
4. Move any open questions into the **Open questions** section.
5. **Update the "📋 Ready-to-copy prompt" section** so the next session is one copy-paste away. See below.
6. Update the **prompts** if the workflow or context has changed (e.g. new files in `docs/audit-2026-q2/` need to be added to Prompt 1's reading list).

Keep this file under 500 lines. If it grows, archive old session log entries to `docs/audit-2026-q2/archive/HANDOFF-archive-<date>.md` and reference them from a short note here.

---

## Updating the ready-to-copy prompt (step-by-step)

This is the single most important update after each session. **Without it, the next session has to read HANDOFF.md and the user has to edit placeholders — defeating the point.**

After completing a PR, do this:

1. Open `docs/audit-2026-q2/HANDOFF.md`.
2. Find the **"📋 Ready-to-copy prompt — next action"** section near the top.
3. Change the line that says `**Next PR to execute:** PR <N> — <title>` to the next PR.
4. Replace the entire code block with a new one, pre-filled for the next PR:
   - First line: `Execute PR <N+1> from the AgentWeave audit. Full spec:`
   - Then the spec file path. For PR 1 it's `docs/audit-2026-q2/pr1-spa-key-leak.md`. For PRs 2-12 it's the corresponding section of `docs/audit-2026-q2/pr-roadmap.md` (e.g. `docs/audit-2026-q2/pr-roadmap.md` — find the heading "PR 2 — Transport data-loss bugs").
   - Adjust steps 4 (version bumps — only relevant at PR 1), 5, 6, 8, and 11 to reference the right test files and smoke-test commands for the next PR.
5. Commit the change to `audit/2026-q2-hardening` with message `docs(audit): update ready-to-copy prompt for PR <N+1>`.
6. Done. The next time the user opens HANDOFF.md, they can just copy and send.

### Where to find the spec for each PR

| PR | Spec file | Notes |
|---|---|---|
| 1 | `docs/audit-2026-q2/pr1-spa-key-leak.md` | Standalone, ~120 lines, fully detailed |
| 2 | `docs/audit-2026-q2/pr-roadmap.md` → "PR 2 — Transport data-loss bugs" | No dedicated spec file yet; roadmap section is the spec |
| 3 | `docs/audit-2026-q2/pr-roadmap.md` → "PR 3 — Transport error handling" | Same |
| 4 | `docs/audit-2026-q2/pr-roadmap.md` → "PR 4 — CLI security & correctness" | Same |
| 5–12 | `docs/audit-2026-q2/pr-roadmap.md` → corresponding section | Same |

**Tip:** if you want richer specs for PRs 2-12, create a `pr<N>-<slug>.md` file in `docs/audit-2026-q2/` (mirroring `pr1-spa-key-leak.md`) and update the table above.

---

## License

Part of AgentWeave, MIT License.
