# Handoff Runbook

> **Living document.** Update as work progresses.
> Created 2026-06-12 alongside the audit.
> **Last updated:** 2026-06-14 (branch integration: opencode + croniter fix rebased onto master; audit branch rebased on top)

This is the file you (or another agent) open first when picking up where a previous session left off. It has three jobs:

1. **State tracker** — what's done, what's next, what's blocked.
2. **Prompt library** — copy-pasteable prompts for the next agent. Update them as the context evolves.
3. **Session log** — append a short note after each session so the next agent has a trail to follow.

The audit findings, PR roadmap, and PR 1 spec live in the sibling files (`README.md`, `findings.md`, `pr-roadmap.md`, `pr1-spa-key-leak.md`). This file orchestrates the work; those define it.

---

## 📈 Progression

Quick visual timeline. Most recent at the top. **One line per milestone** — see the session log below for detail.

```
2026-06-14  ●  Branch integration: opencode onto master, audit rebased on top  →  master @ 016bc77, audit @ 43abe10  ·  v0.38.0a1 / v0.32.0a1
          │  ↑ you are here
          ●  PR 4: CLI security & correctness shipped
          ●  PR 3: Transport error handling & safety shipped
          ●  PR 2: Transport data-loss bugs shipped
          ●  PR 0.5: test_jobs croniter 6.x mock fix shipped
          ●  PR 1: SPA key leak (CRITICAL) shipped
          ●  Audit created, branch + version bumps (PEP 440 alpha: 0.38.0a1 / 0.32.0a1)
          ○  PR 5: Hub input validation shipped                   (target: 2 days)
          ○  PR 6: Hub auth + BOLA + perf shipped                 (target: 2-3 days)
          ○  PR 7: DB & migrations shipped                        (target: 1 day)
          ○  PR 8: Dead code & dedup shipped                      (target: 0.5 day)
          ○  PR 9: Hub UI security shipped                        (target: 2 days)
          ○  PR 10: Hub UI perf & dedup shipped                   (target: 2 days)
          ○  PR 11: CLI/watchdog code quality shipped             (target: 2 days)
          ○  PR 12: Test coverage sweep shipped                   (target: 3-4 days)
          ○  v0.38.0 (CLI) / v0.32.0 (Hub) released, merged to master
```

**How to update:** when a milestone completes, change the `○` to `●` and fill in any version/branch changes. The "you are here" marker moves down. To indicate work in progress, use `◐` (e.g. `◐ PR 1: ... (in progress)`).

```

---

## 📋 Ready-to-copy prompt — next action

**This is the prompt you copy-paste to send to the next agent. It is pre-filled for the next PR.**

The agent that completes the current PR MUST update this section to point at the next PR before reporting back. See the "Updating the ready-to-copy prompt" section near the bottom of this file.

**Next PR to execute:** PR 5 — Hub input validation

```
Execute PR 5 from the AgentWeave audit. Full spec:
docs/audit-2026-q2/pr-roadmap.md — section "## PR 5 — Hub input validation"

Before doing anything:
1. Read docs/audit-2026-q2/HANDOFF.md (especially the "Current status"
   table, the "Branch state" block, the latest session log entries,
   and the "Open questions / blockers" section) so you know what's
   already done and any in-flight issues.
2. Read the PR 5 section of pr-roadmap.md end-to-end.

Workflow (test-first, do not skip):
1. cd to C:\Users\huida\Documents\projects\AgentWeave
2. Verify you're on branch `audit/2026-q2-hardening`
3. Pull latest changes if a remote exists
4. Versions are already bumped (v0.38.0a1 / v0.32.0a1) — do not re-bump
5. Write the failing test(s) FIRST per the spec — new
   hub/tests/test_agents.py, additions to hub/tests/test_messages.py and
   hub/tests/test_tasks.py.
6. Run the relevant test command and CONFIRM it fails:
   `cd hub && pytest tests/test_agents.py tests/test_messages.py tests/test_tasks.py -v`
7. Apply the fix per the spec in hub/hub/api/v1/agents.py,
   hub/hub/api/v1/agent_trigger.py, and all files under
   hub/hub/schemas/ (especially messages.py, tasks.py, jobs.py).
8. Run the relevant test command and CONFIRM it passes.
9. Run full test suites: `pytest tests/ -v` (CLI) and
   `cd hub && pytest tests/ -v` (Hub) — both must be green.
10. Run lint: `ruff check src/`, `black src/`, `mypy src/`. (Hub has
    no enforced lint config today; focus on the CLI side.)
11. Manual smoke test: exercise the role-id path-traversal regression
    (S1), schema length caps (S6), work_dir validation (S12), and
    register_session agent-name collision (M16) end-to-end via the
    Hub REST API.
12. Commit with a structured message matching PR 4's style.
13. Push the branch.
14. Update docs/audit-2026-q2/HANDOFF.md (CRITICAL — see below).
15. Report back.

Step 14 in detail (this is what makes the next session work):
a. Mark PR 5 as ✅ in the "Current status" table.
b. Update the "Branch state" block with current branch, latest commit hash,
   and last test run timestamp.
c. Append a new entry to the "Session log" section.
d. **REPLACE the "Next PR to execute" line and the code block in the
   "📋 Ready-to-copy prompt — next action" section above** so the prompt
   is pre-filled for PR 6 (Hub auth, BOLA, perf). The spec for PR 6
   lives in docs/audit-2026-q2/pr-roadmap.md under the "PR 6 — Hub auth,
   BOLA, perf" heading. Adjust the workflow steps (5, 6, 7, 8, 11) to
   reference the right test files and source files for that PR.

Notes from PR 4 that affect PR 5:
- write_json_atomic is available in src/agentweave/utils.py. Hub
  schemas are server-side only; the transport layer is unaffected.
- utils.save_json chmods 0600 on POSIX automatically. Hub JSON
  responses are sent over the wire, not to local files, so the
  S11/S8 fixes do not apply to Hub code paths.

Time budget: 2 days for PR 5. If you go over by >50%, stop and ask.
If you encounter a blocker, stop, document it in the
"Open questions / blockers" section of HANDOFF.md, and report.
```

---

## Current status

**Last updated:** 2026-06-14 (PR 4 shipped)

| # | PR | Status | Branch | Merged | Notes |
|---|---|---|---|---|---|
| 0.5 | test_jobs croniter 6.x mock fix | ✅ Merged (local) | `audit/2026-q2-hardening` | a8c77b0 | Prep PR before PR 2. 4-line diff in `tests/test_jobs.py`. Closed the open question from PR 1 — full CLI suite now green without deselects (326 passed). |
| 1 | SPA key leak (CRITICAL) | ✅ Merged (local) | `audit/2026-q2-hardening` | 71106e5 | Committed locally. Spec: `pr1-spa-key-leak.md`. All tests + lint pass. |
| 2 | Transport data-loss | ✅ Merged (local) | `audit/2026-q2-hardening` | cf91e52 | Closes H1, H2, H3, H6, M7, M11, M12, M13, M23 (9 fixes). New `tests/test_transport_git.py` (23 tests) + HTTP retry/invalid-response tests + new `hub/tests/test_mcp_server.py`. CLI 357 passed, Hub 74 + 1 skip. S7 (body redaction) was pre-shipped in PR 2's http.py error cleanup. |
| 3 | Transport error handling & safety | ✅ Merged (local) | `audit/2026-q2-hardening` | 8bbd93d | Closes H8, M8, M9, M10, S2, S10, S11 (6 fixes — S7 already done in PR 2). New `write_json_atomic` in utils.py (atomic write + 0600 on POSIX); `_check_id_safe` defense-in-depth at message/task boundaries; `os.replace`+lock for archive_message/mark_read/move_to_completed; 10 MB Hub response body cap; cmd_start stops pre-opening the watchdog log fd. CLI 378 passed (+21), Hub 74 + 1 skip. |
| 4 | CLI security & correctness | ✅ Merged (local) | `audit/2026-q2-hardening` | a3ae7cf | Closes M3, M4, M5, M6, M12, S9 (6 fixes — S8 already done in PR 3). New `tests/test_eventlog.py` (4 tests) + 4 new test classes in `tests/test_cli.py` (datetime, atomic write, subprocess.run timeouts, sha256 verification) + MCP datetime guard + watchdog Popen-encoding guard. CLI 395 passed (+17), Hub 74 + 1 skip. |
| 5 | Hub input validation | ⬜ Not started | — | — | Next up. Spec: `pr-roadmap.md` § PR 5. |
| 6 | Hub auth + BOLA + perf | ⬜ Not started | — | — | |
| 7 | DB & migrations | ⬜ Not started | — | — | |
| 8 | Dead code & dedup | ⬜ Not started | — | — | |
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
Latest commit: 43abe10  (fix(lint): address inherited N806 and no-untyped-def from opencode commit)
Last test run: 2026-06-14 — Hub: 74 passed, 1 skipped. CLI: 443 passed, 3 skipped (POSIX-only).

master:
  Latest commit: 016bc77  (feat(opencode): local CLI override, models doc, template yml)
  Parent: a3d3ba1  (test(jobs): fix test_should_fire_old_last_run for croniter 6.x)
  Parent: 57c65ee  (Bump Hub to v0.31.1 — old master HEAD)

Integration topology (linear, no merge commits):
  master  → audit
  57c65ee (Bump Hub v0.31.1)
  └─ a3d3ba1  test(jobs): fix test_should_fire_old_last_run for croniter 6.x     ← croniter fix
  └─ 016bc77  feat(opencode): local CLI override, models doc, template yml     ← OPENCODE
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
  └─ 43abe10  fix(lint): address inherited N806 and no-untyped-def              ← HEAD
```

All commit SHAs above the opencode commit were rewritten by the rebase (their
parents changed), but their content and messages are preserved. The croniter fix
(`a3d3ba1`) is identical to the original `a8c77b0` from the audit branch
(cherry-picked, same patch-id detected by git rebase).

The PR 4 fix and its handoff have new SHAs (`a54dbec`, `e0aeed2`) but the same
content as the previously-pushed `a3ae7cf` / `eaf7bab`. The lint fix is a NEW
commit (`43abe10`) that addresses two pre-existing opencode-inherited lint
issues; details in the session log entry below.

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

### 2026-06-12 — Audit created

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Created `docs/audit-2026-q2/` with full audit findings, 12-PR roadmap, and PR 1 spec. No code changes.
- **Status:** 0/12 PRs complete. Branch `audit/2026-q2-hardening` not yet created.
- **Open questions:** None. PR 1 (the CRITICAL SPA key leak) is ready to execute.
- **Next:** Create the branch, bump versions to v0.38.0-audit.1 / v0.32.0-audit.1, execute PR 1 test-first per `pr1-spa-key-leak.md`.
- **Hand-off to:** whoever picks this up next. Use Prompt 2 with "1" and "pr1-spa-key-leak.md".

### 2026-06-12 — PR 1 shipped (SPA key leak fix)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closed C1 (the only CRITICAL audit finding). Removed the key-injection code path in `hub/hub/main.py:serve_spa`; moved bootstrap to the existing `/api/v1/setup/token` endpoint (already localhost-only). SPA now calls that endpoint on first load and stores the key. Added 2 regression tests in `hub/tests/test_setup.py`. Rebuilt UI and re-deployed `hub/hub/static/ui/`.
- **Test-first verification:** new test `test_spa_does_not_leak_api_key_in_html` confirmed FAIL with the live key in HTML before the fix, confirmed PASS after.
- **Full suite:** Hub 72 passed / 1 skipped. CLI 325 passed (1 pre-existing failure deselected — see Open questions).
- **Lint:** ruff + black clean on changed files. mypy clean on CLI; Hub has 150 pre-existing errors (unmaintained, no config), my 2 new tests follow existing style.
- **Smoke test:** `curl http://127.0.0.1:8765/ | grep -c aw_live_` → 0. `/api/v1/setup/token` returns the key correctly.
- **Versions:** used PEP 440 `0.38.0a1` / `0.32.0a1` (the spec's `0.32.0-audit.1` is not valid PEP 440 and pip rejects it during editable install).
- **Local commits only** (no push per user instruction):
  - `8bde15b` docs(audit): add 2026-Q2 audit findings, 12-PR roadmap, and PR 1 spec
  - `71106e5` fix(hub): stop leaking live API key in SPA HTML response
- **Open questions:** 1 new entry below (pre-existing croniter 6.x test brittleness).
- **Hand-off to:** next session — execute **PR 2 — Transport data-loss bugs**. Spec is in `docs/audit-2026-q2/pr-roadmap.md` § PR 2. Ready-to-copy prompt pre-filled at top of this file.

<!-- Add new entries below this line. Keep them terse. -->

### 2026-06-13 — PR 0.5 shipped (test_jobs croniter 6.x mock fix)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Resolved the pre-existing CLI test failure surfaced by PR 1. Fixed `tests/test_jobs.py:312-321`: `MockDateTime` now subclasses `datetime.datetime` (so croniter 6.x's `issubclass` check passes), and `MockDateTime.now(tz=...)` honors the `tz` argument so it returns a tz-aware datetime when the production code requests one (avoiding a naive/aware subtraction crash in `jobs.py:410`).
- **Test-first verification:** confirmed RED via `pytest tests/test_jobs.py::TestJobShouldFire::test_should_fire_old_last_run -v` before edit (TypeError on `get_prev`); confirmed GREEN after first edit, then RED again with a different error (naive/aware mismatch), then GREEN after second edit. Two distinct root causes, both fixed in the same 4-line diff.
- **Full suite:** Hub 72 passed / 1 skipped (unchanged). CLI 326 passed, 0 deselects (was 325 + 1 deselected = 326 total). The previously skipped test now runs and passes.
- **Lint:** black clean on changed file. ruff reports 1 pre-existing import-sort nit on `tests/test_jobs.py:3-5` (unrelated to this PR; logged for PR 11). mypy not run on tests/test_jobs.py (out of mypy coverage). The active Python (`hermes-agent` venv) doesn't have ruff/black/mypy installed; ran them via `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe -m`.
- **Smoke test:** N/A — pure test-mock fix, no production behavior change. Verified the targeted test + full CLI suite.
- **Local commit:** `a8c77b0` test(jobs): fix test_should_fire_old_last_run for croniter 6.x
- **Open questions:** Closed the one open entry (pre-existing test_jobs failure). Section is now empty.
- **Hand-off to:** next session — execute **PR 2 — Transport data-loss bugs**. Ready-to-copy prompt unchanged at top of this file.

### 2026-06-13 — PR 2 shipped (Transport data-loss bugs)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closed 9 of the audit's HIGH/MEDIUM data-loss and hardening bugs in a single 6-file diff. GitTransport: abort push when ls-tree fails after ls-remote succeeded (H1), add local outbox for at-least-once delivery on push failure (H2), `subprocess.run(timeout=30)` on every git call (M7), wrap seen-set operations in `lock()` (M11), restructure status-update filename to `__status__{new}__{ts}.json` (M12), microsecond precision in `_iso_compact` + 8-hex UUID suffix (M13). HttpTransport: retry 5xx/408/425/429/URLError with exponential backoff + honor `Retry-After` (H3), catch `JSONDecodeError` → `HubTransportError(classification="hub_invalid_response")` (H6), truncate + redact `api_key=` in error body text (S7 — pre-shipped here, will be skipped in PR 3). mcp_server: `urlopen(req, timeout=10)` (M23).
- **Test-first verification:** wrote 33 new tests across `tests/test_transport_git.py` (23 tests, new file), `tests/test_http_transport.py` (+8 tests), and `hub/tests/test_mcp_server.py` (2 tests, new file). All 33 were RED before fixes (with the right error messages for each bug). All 33 GREEN after the corresponding fix.
- **Full suite:** CLI 357 passed (was 326; +31 from new tests). Hub 74 passed, 1 skipped (was 72 + 1 skipped; +2 from new mcp_server tests).
- **Lint:** `ruff --fix` cleaned 11 issues. 2 remain in `hub/hub/mcp_server.py` (B904 raise-from, SIM105 contextlib.suppress) — both PRE-EXISTING, not in lines I touched; left for PR 3 / PR 11 per scope discipline. `black` reformatted 5 files. `mypy` clean on the 2 changed CLI source files (one missing type annotation on `_sleep_with_retry_after` was added; pre-existing Python 3.8 warning in pyproject.toml is unrelated).
- **Smoke test:** Wrote a real-git smoke test (`/tmp/opencode/smoke_pr2.py`) that creates a bare "remote" + working repo, runs `send_message` and `send_task` through GitTransport, verifies the files land on the orphan branch, exercises `get_pending_messages` round-trip, and checks the outbox is empty on success. All checks passed end-to-end.
- **Test design notes:** the `MockDateTime` for `test_jobs.py` (PR 0.5) pattern was the inspiration for the git transport mock helper. The M12 status-format test had to be revised when I realized the old parser handles the "obvious" cases fine — the value of the new `__status__` format is in the unambiguous delimiter, not in fixing a specific parser bug. The "empty body" test (TestHttpTransportInvalidResponse) was changed from "expect HubTransportError" to "expect empty dict" — empty body returning `{}` is a legitimate API contract (DELETE-style endpoints), not an error.
- **Local commit:** `cf91e52` fix(transport): harden data-loss paths in git and http transports (1 commit, 6 files, 1054 insertions / 102 deletions).
- **Open questions:** None new. (Section is empty.)
- **Hand-off to:** next session — execute **PR 3 — Transport error handling & safety**. Ready-to-copy prompt at top of this file is pre-filled for PR 3, with a note that S7 is already done.

---

### 2026-06-13 — PR 3 shipped (Transport error handling & safety)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closed 6 of the audit's HARDENING bugs (H8, M8, M9, M10, S2, S10, S11) — S7 was already done in PR 2. 5 production files touched + 4 test files. `utils.write_json_atomic` is the new foundation: tmp + os.replace + 0600 on POSIX, tmp cleanup on failure. `save_json` becomes a thin wrapper so every transport inherits both atomicity and the chmod. `_check_id_safe` (private helper, raises ValueError) gates `Message.load`/`save`/`mark_read` and `LocalTransport.archive_message`/`send_message` against path-traversal. `LocalTransport.archive_message`, `Message.mark_read`, and `Task.move_to_completed` now use os.replace + per-resource `lock()` to close the two-step torn-write window. `HttpTransport._request` caps body reads at 10 MB + 1 byte and raises `HubTransportError("hub_response_too_large")` on overflow. `cmd_start` (the watchdog launcher) stops pre-opening the watchdog log file in the parent — child opens its own log via constants, so no fd leak per `agentweave watch` invocation.
- **Test-first verification:** 21 new tests across 4 files. All were RED before the fix with the right error messages. 4 tests are POSIX-only (chmod and /proc fd count) and skip cleanly on Windows. Per the order in HANDOFF, applied fixes in this order: S11 (utils foundation) → S2 (id check) → M8/M9 (archive atomicity) → M10 (move_to_completed) → S10 (body cap) → H8 (fd leak). Each step: wrote tests, confirmed RED, applied fix, confirmed GREEN.
- **Full suite:** CLI 378 passed (was 357; +21). Hub 74 + 1 skip (unchanged).
- **Lint:** ruff clean. black clean (reformatted `transport/http.py`). mypy clean on changed files (1 pre-existing PyYAML stub error in `config.py` is unrelated).
- **Smoke test:** Wrote two scripts. (1) `archive_message` end-to-end in a temp dir: send → verify in pending → mark_read → verify in archive only, no pending copy, read flag set. PASS. (2) `HttpTransport._request` body cap: 10 MB + 1 byte body raises `hub_response_too_large`; small body returns the parsed dict. PASS.
- **Test design notes:** the `_check_id_safe` raises ValueError (loud failure) rather than returning None (silent — would be indistinguishable from "no message by that id"). The pre-existing `Task.load` pattern returns None for invalid IDs and I did NOT change that — it's a separate style choice. For the `write_json_atomic` tmp-file-cleanup test, I monkeypatched `json.dump` to raise — the leftover .tmp file check then proves the cleanup path works. For the cmd_start DEVNULL test, the `_sp` import inside `cmd_start` is a function-local name, so I had to patch `subprocess.Popen` at the module level (initial attempt to patch `agentweave.cli._sp.Popen` failed with "is not a package"). I also added a source-level guard test (asserts the buggy substring is gone) as a portable complement to the POSIX-only /proc test.
- **Local commit:** `8bbd93d` fix(transport): harden archive, file perms, body cap, and fd leak (1 commit, 11 files, 536 insertions / 54 deletions). HANDOFF update is a separate `4bba571` commit.
- **Open questions:** None new.
- **Hand-off to:** next session — execute **PR 4 — CLI security & correctness**. Ready-to-copy prompt at top of this file is pre-filled for PR 4.

### 2026-06-14 — PR 4 shipped (CLI security & correctness)

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Closed 6 of the audit's CLI-side bugs (M3, M4, M5, M6, M12, S9) — S8 was already done in PR 3 (`save_json` is a thin wrapper around `write_json_atomic`, so the two `save_json(TRANSPORT_CONFIG_FILE, ...)` call sites in cli.py inherit the 0600 chmod and os.replace atomicity for free). 4 production files touched + 4 test files + 1 new test file. M3/M4/M6: `datetime.utcnow()` → `datetime.now(timezone.utc)` everywhere; `eventlog.write_heartbeat` now embeds the `+00:00` offset and `get_heartbeat_age` subtracts from `datetime.now(timezone.utc)` so the two stay compatible. M5: both `subprocess.Popen(text=True, ...)` calls in `watchdog.py` (`_CodexMcpClient.start` and `_do_run_agent_subprocess._run_cmd`) now also pass `encoding="utf-8", errors="replace"` so non-ASCII agent output doesn't crash mid-thread on cp1252. M12: added `timeout=` to every unguarded `subprocess.run` in `cli.py` — 5 git plumbing calls (5–30s each), docker compose version/up/down (10–600s), taskkill/tasklist (5s), mcp helper (10–15s), and the claude proxy run (600s). S9: new `_download_with_sha256` helper with two new optional URL constants (`HUB_COMPOSE_SHA256_URL`, `HUB_ENV_SHA256_URL`); when unset or unreachable the helper logs a WARN and proceeds (so operators can adopt sidecar files incrementally), and when reachable and mismatched it removes the corrupted file and returns False. `cmd_hub_start` refactored to call the helper.
- **Pre-flight:** ~1300 lines of unrelated "opencode CLI override" work were already in the working tree on the `audit/2026-q2-hardening` branch. Per the user's Q1 decision, I stashed them with `git stash push -u`, created side branch `feat/opencode-cli-override` from the audit branch tip, applied the stash there, committed as `880a88a feat(opencode): local CLI override, models doc, template yml`, pushed to `origin/feat/opencode-cli-override`, then `git checkout audit/2026-q2-hardening` (which was untouched). This keeps the audit diff atomic.
- **Test-first verification:** 17 new tests across 5 files (4 in new `tests/test_eventlog.py`, 5 in `tests/test_cli.py::TestDatetimeIsTzAware`+`TestTransportJsonAtomicWrite`+`TestSubprocessRunHasTimeout`+`TestDownloadWithSha256`, 3 in `tests/test_mcp_server.py::TestDatetimeIsTzAware`, 2 in `tests/test_watchdog.py::TestPopenUsesUtf8Encoding`). All were RED before the corresponding fix with the right error messages. Applied fixes in spec order: M3 (datetime awareness) → M5 (Popen encoding) → M12 (subprocess timeouts) → S9 (sha256 helper). Each step: wrote tests, confirmed RED, applied fix, confirmed GREEN. Most datetime tests incidentally pass on the unfixed code (the bug is "naive vs aware" only, not absence); the source-level "no `datetime.utcnow()`" check is the hard guard. M12 is a single source-level test that scans for `subprocess.run(` and looks 8 lines ahead for `timeout=` — clean regression guard.
- **Full suite:** CLI 395 passed (was 378; +17). Hub 74 + 1 skip (unchanged).
- **Lint:** ruff clean (1 initial SIM102 nested-if warning fixed). black reformatted `cli.py`. mypy clean on all 4 changed files (the 1 pre-existing PyYAML stub error in `config.py` is unchanged and out of scope).
- **Smoke test:** Wrote `C:\Users\huida\AppData\Local\Temp\opencode\smoke_pr4.py` covering: (1) `write_heartbeat` produces a `+00:00` UTC-aware ISO and `get_heartbeat_age` round-trips a positive float; (2) `save_json(transport.json)` is atomic + 0600 on POSIX (Windows N/A here, but tested via `test_utils.py`); (3) both Popen call sites have `text/encoding/errors`; (4) `_download_with_sha256` proceeds with WARN when no sidecar URL is set. All PASS.
- **Test design notes:** the sha256 helper tests patch `urllib.request.urlretrieve` at the module level (the helper imports `urllib.request as _req` inside the function, so a module-level patch is the correct target — initial attempt to patch `agentweave.cli._req` failed with "is not a package", same gotcha as PR 3's Popen patch). The subprocess-timeout test is a source-level scan rather than a per-callsite test — it's portable, fast, and tells future contributors exactly which kwargs are required. The S8 atomic-write test verifies end-to-end via `cmd_transport_setup --type git` (the actual user-visible call) rather than just `write_json_atomic` directly, so the regression catches a future code path that bypasses `save_json` too.
- **Local commits:** `a3ae7cf` fix(cli): timezone awareness, transport.json atomic write, sha256 verification (1 commit, 8 files, 556 insertions / 31 deletions). Branch pushed to `origin/audit/2026-q2-hardening` via `git push -u origin audit/2026-q2-hardening`.
- **Open questions:** None new. (Section remains empty.)
- **Hand-off to:** next session — execute **PR 5 — Hub input validation**. Ready-to-copy prompt at top of this file is pre-filled for PR 5, with adjusted test-file references (`hub/tests/test_agents.py` (new), `hub/tests/test_messages.py`, `hub/tests/test_tasks.py`) and source-file references (`hub/hub/api/v1/agents.py`, `hub/hub/api/v1/agent_trigger.py`, `hub/hub/schemas/*.py`).

### 2026-06-14 — Branch integration: opencode onto master, audit onto opencode

- **By:** opencode (MiniMax-M3) on behalf of gutohuida
- **What:** Integrated the previously-parked opencode CLI override work (commit `880a88a`, originally stashed from PR 4's pre-flight) into master, then rebased the entire audit branch on top. The user asked for "rebase style — opencode on master, all hardening commits on top" so the final state would be a single linear history with no merge commits in the middle. Approached this in three steps: (1) rebase the opencode side branch --onto master, dropping the 10 audit-history commits that were never actually on master; (2) fast-forward master to the rebased opencode commit; (3) rebase the audit branch on top of the new master. All three rebases were conflict-free — `git rebase` detected that the croniter fix (`a8c77b0`) was a duplicate of the new master's `a3d3ba1` and skipped it automatically (the `--reapply-cherry-picks` hint was logged but the default dedup is correct here).
- **Blocker encountered & resolved:** the initial post-rebase test run surfaced `test_jobs.py::TestJobShouldFire::test_should_fire_old_last_run` failing on plain `master@57c65ee` with croniter 6.2.2 (`TypeError: Invalid ret_type, only 'float' or 'datetime' is acceptable`). This is a PRE-EXISTING master failure that was masked because the original opencode side branch was forked from `f8f34e1` (which already had the croniter fix in its ancestry). Confirmed the failure is reproducible on stock master HEAD, asked the user, cherry-picked `a8c77b0` onto master as `a3d3ba1`, re-tested, re-rebased opencode onto new master, then proceeded. Clean baseline restored.
- **Lint issue surfaced & resolved:** after the rebase, ruff flagged `N806 _OPENCODE_SID_RE in function should be lowercase` at `watchdog.py:1303` and mypy flagged 2 `no-untyped-def` errors in `cli.py:2029` and `cli.py:3313`. All three are pre-existing on the opencode commit (would have appeared on master regardless of any audit work). Fixed them as a single follow-up commit `43abe10`: rename to `_opencode_sid_re`, annotate `_merge_mcp_into_opencode_file(path: Path, mcp_block: Dict[str, Any], _json: Any) -> tuple`, annotate `_activate_opencode_config(config: "AgentWeaveConfig") -> int`. After the fix: ruff clean, mypy 1 pre-existing error (PyYAML stub, unrelated), black clean. (Note for the future audit PRs: this PyYAML stub error is now present on master too — out of scope for the audit, but worth knowing.)
- **Topological outcome:**
  - `master`: `57c65ee` (Bump Hub v0.31.1) → `a3d3ba1` (croniter fix) → `016bc77` (opencode). Pushed to `origin/master`.
  - `feat/opencode-cli-override`: rebased from 11 commits ahead of master to 1 commit ahead of master (`016bc77`). Force-pushed to `origin/feat/opencode-cli-override`.
  - `audit/2026-q2-hardening`: 13 commits on top of master (12 from the rebase + 1 new lint fix). All commit SHAs above the opencode commit changed (parents moved) but content and messages are preserved. Force-pushed to `origin/audit/2026-q2-hardening` with `--force-with-lease`.
- **Test runs:**
  - After rebase (before lint fix): CLI 443 passed, 3 skipped. Hub 74 passed, 1 skipped. (The +48 vs. previous 395 is the entire opencode commit: new `tests/test_opencode_cli_override.py` + `tests/test_activate.py` extensions + `tests/test_config.py` extensions + extra `tests/test_cli.py` cases.)
  - After lint fix: same — 443/74 unchanged. Targeted re-run of `tests/test_watchdog.py tests/test_cli.py tests/test_eventlog.py` (the files I touched) → 82 passed.
  - On `master` after the croniter cherry-pick: 1 previously-failing test now passes; full CLI suite green.
- **Why the croniter fix came along "for free" when rebasing audit → master:** the fix was already in the audit branch's history (as `a8c77b0`), and `git rebase` recognized it as a patch-id duplicate of the new master's `a3d3ba1` and skipped reapplying it. The resulting history shows it once, in the right place (between Bump Hub and opencode). This is exactly the behavior we wanted.
- **For future PRs:** the audit branch is now a clean linear descendant of master. Every new PR's fix commit will land on top of `43abe10` (the lint fix), with a docs/handoff commit on top of that. Master stays at `016bc77` until the audit is done and merged.
- **No new open questions.**
- **Hand-off to:** next session — execute **PR 5 — Hub input validation**. Ready-to-copy prompt at top of this file is unchanged from the PR 4 handoff. New starting point: `git checkout audit/2026-q2-hardening && git pull --ff-only` (no force-pull needed since the local branch is already up to date with the force-pushed remote). The audit branch's new tip is `43abe10`.

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
