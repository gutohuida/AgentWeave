# Handoff Runbook

> **Living document.** Update as work progresses.
> Created 2026-06-12 alongside the audit.
> **Last updated:** 2026-06-13 (PR 0.5 shipped)

This is the file you (or another agent) open first when picking up where a previous session left off. It has three jobs:

1. **State tracker** — what's done, what's next, what's blocked.
2. **Prompt library** — copy-pasteable prompts for the next agent. Update them as the context evolves.
3. **Session log** — append a short note after each session so the next agent has a trail to follow.

The audit findings, PR roadmap, and PR 1 spec live in the sibling files (`README.md`, `findings.md`, `pr-roadmap.md`, `pr1-spa-key-leak.md`). This file orchestrates the work; those define it.

---

## 📈 Progression

Quick visual timeline. Most recent at the top. **One line per milestone** — see the session log below for detail.

```
2026-06-13  ●  PR 0.5: test_jobs croniter 6.x mock fix shipped  →  1.5/12 PRs  ·  branch: audit/2026-q2-hardening  ·  v0.38.0a1 / v0.32.0a1
          │  ↑ you are here
          ●  PR 1: SPA key leak (CRITICAL) shipped
          ●  Audit created, branch + version bumps (PEP 440 alpha: 0.38.0a1 / 0.32.0a1)
          ○  PR 2: Transport data-loss bugs shipped               (target: 3-4 days)
          ○  PR 3: Transport error handling shipped               (target: 2 days)
          ○  PR 4: CLI security & correctness shipped             (target: 2-3 days)
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

**Next PR to execute:** PR 2 — Transport data-loss bugs

```
Execute PR 2 from the AgentWeave audit. Full spec:
docs/audit-2026-q2/pr-roadmap.md — section "## PR 2 — Transport data-loss bugs"

Before doing anything:
1. Read docs/audit-2026-q2/HANDOFF.md (especially the "Current status"
   table, the "Branch state" block, the latest session log entries,
   and the "Open questions / blockers" section) so you know what's
   already done and any in-flight issues.
2. Read the PR 2 section of pr-roadmap.md end-to-end.

Workflow (test-first, do not skip):
1. cd to C:\Users\huida\Documents\projects\AgentWeave
2. Verify you're on branch `audit/2026-q2-hardening`
3. Pull latest changes if a remote exists
4. Versions are already bumped (v0.38.0a1 / v0.32.0a1) — do not re-bump
5. Write the failing test(s) FIRST per the spec — start with
   tests/test_transport_git.py (new file) and additions to
   tests/test_http_transport.py
6. Run the relevant test command (e.g. `pytest tests/test_transport_git.py -v`)
   and CONFIRM it fails
7. Apply the fix per the spec (src/agentweave/transport/git.py,
   src/agentweave/transport/http.py, hub/hub/mcp_server.py:70)
8. Run the relevant test command and CONFIRM it passes
9. Run full test suites: `pytest tests/ -v` and `cd hub && pytest tests/ -v`
   — both must be green
10. Run lint: `ruff check src/`, `black src/`, `mypy src/`
11. Manual smoke test: pick the most data-loss-prone code path (e.g.
    the new local outbox in GitTransport.send_task) and exercise it
    end-to-end with a local repo
12. Commit with the exact message in the spec
13. Push the branch
14. Update docs/audit-2026-q2/HANDOFF.md (CRITICAL — see below)
15. Report back

Step 14 in detail (this is what makes the next session work):
a. Mark PR 2 as ✅ in the "Current status" table.
b. Update the "Branch state" block with current branch, latest commit hash,
   and last test run timestamp.
c. Append a new entry to the "Session log" section.
d. **REPLACE the "Next PR to execute" line and the code block in the
   "📋 Ready-to-copy prompt — next action" section above** so the prompt
   is pre-filled for PR 3 (Transport error handling). The spec for PR 3
   lives in docs/audit-2026-q2/pr-roadmap.md under the "PR 3 — Transport
   error handling" heading. Adjust the workflow steps (5, 6, 8, 11) to
   reference the right test files and smoke-test commands for that PR.

Time budget: 3-4 days for PR 2. This is the largest PR. If you go over
by >50%, stop and ask. If you encounter a blocker, stop, document it in
the "Open questions / blockers" section of HANDOFF.md, and report.
```

---

## Current status

**Last updated:** 2026-06-13 (PR 0.5 shipped)

| # | PR | Status | Branch | Merged | Notes |
|---|---|---|---|---|---|
| 0.5 | test_jobs croniter 6.x mock fix | ✅ Merged (local) | `audit/2026-q2-hardening` | a8c77b0 | Prep PR before PR 2. 4-line diff in `tests/test_jobs.py`. Closed the open question from PR 1 — full CLI suite now green without deselects (326 passed). |
| 1 | SPA key leak (CRITICAL) | ✅ Merged (local) | `audit/2026-q2-hardening` | 71106e5 | Committed locally. Spec: `pr1-spa-key-leak.md`. All tests + lint pass. |
| 2 | Transport data-loss | ⬜ Not started | `audit/2026-q2-hardening` | — | Next up. Spec: `pr-roadmap.md` § PR 2 |
| 3 | Transport error handling | ⬜ Not started | — | — | |
| 4 | CLI security & correctness | ⬜ Not started | — | — | |
| 5 | Hub input validation | ⬜ Not started | — | — | |
| 6 | Hub auth + BOLA + perf | ⬜ Not started | — | — | |
| 7 | DB & migrations | ⬜ Not started | — | — | |
| 8 | Dead code & dedup | ⬜ Not started | — | — | |
| 9 | Hub UI security | ⬜ Not started | — | — | |
| 10 | Hub UI perf & dedup | ⬜ Not started | — | — | |
| 11 | CLI/watchdog code quality | ⬜ Not started | — | — | Includes the test_jobs.py ruff import-sort nit (pre-existing) |
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
Latest commit: a8c77b0  (PR 0.5: test(jobs): fix test_should_fire_old_last_run for croniter 6.x)
Last test run: 2026-06-13 — Hub: 72 passed, 1 skipped. CLI: 326 passed, 0 deselects.
```

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
