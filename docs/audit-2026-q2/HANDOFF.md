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
2026-06-14  ●  PR 5: Hub input validation shipped  →  audit @ f9cea0c  ·  v0.38.0a1 / v0.32.0a1
          │  ↑ you are here
          ○  PR 6: Hub auth + BOLA + perf shipped                 (target: 2-3 days)
          ○  PR 7: DB & migrations shipped                        (target: 1 day)
          ○  PR 8: Dead code & dedup shipped                      (target: 0.5 day)
          ○  PR 9: Hub UI security shipped                        (target: 2 days)
          ○  PR 10: Hub UI perf & dedup shipped                   (target: 2 days)
          ○  PR 11: CLI/watchdog code quality shipped             (target: 2 days)
          ○  PR 12: Test coverage sweep shipped                   (target: 3-4 days)
          ○  v0.38.0 (CLI) / v0.32.0 (Hub) released, merged to master
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

**Next PR to execute:** PR 6 — Hub auth, BOLA, perf

```
Execute PR 6 from the AgentWeave audit. Full spec:
docs/audit-2026-q2/pr-roadmap.md — section "## PR 6 — Hub auth, BOLA, perf"

Before doing anything:
1. Read docs/audit-2026-q2/HANDOFF.md (especially the "Current status"
   table, the "Branch state" block, the latest session log entries,
   and the "Open questions / blockers" section) so you know what's
   already done and any in-flight issues.
2. Read the PR 6 section of pr-roadmap.md end-to-end.

Workflow (test-first, do not skip):
1. cd to C:\Users\huida\Documents\projects\AgentWeave
2. Verify you're on branch `audit/2026-q2-hardening`
3. Pull latest changes if a remote exists
4. Versions are already bumped (v0.38.0a1 / v0.32.0a1) — do not re-bump
5. Write the failing test(s) FIRST per the spec — new
   hub/tests/test_bola.py, additions to hub/tests/test_auth.py.
6. Run the relevant test command and CONFIRM it fails:
   `cd hub && pytest tests/test_bola.py tests/test_auth.py -v`
7. Apply the fix per the spec in hub/hub/auth.py, hub/hub/main.py,
   hub/hub/api/v1/agents.py, and hub/hub/mcp_server.py.
8. Run the relevant test command and CONFIRM it passes.
9. Run full test suites: `pytest tests/ -v` (CLI) and
   `cd hub && pytest tests/ -v` (Hub) — both must be green.
10. Run lint: `ruff check src/`, `black src/`, `mypy src/`. (Hub has
    no enforced lint config today; focus on the CLI side.)
11. Manual smoke test: exercise the token-fallback removal (S3),
    BOLA isolation across projects (T5), the new /events/ticket SSE
    flow, and the request body-size cap bonus end-to-end via the
    Hub REST API.
12. Commit with a structured message matching PR 5's style.
13. Push the branch.
14. Update docs/audit-2026-q2/HANDOFF.md (CRITICAL — see below).
15. Report back.

Step 14 in detail (this is what makes the next session work):
a. Mark PR 6 as ✅ in the "Current status" table.
b. Update the "Branch state" block with current branch, latest commit hash,
   and last test run timestamp.
c. Append a new entry to the "Session log" section.
d. **REPLACE the "Next PR to execute" line and the code block in the
   "📋 Ready-to-copy prompt — next action" section above** so the prompt
   is pre-filled for PR 7 (DB & migrations). The spec for PR 7
   lives in docs/audit-2026-q2/pr-roadmap.md under the "PR 7 — DB & migrations"
   heading. Adjust the workflow steps (5, 6, 7, 8, 11) to reference
   the right test files and source files for that PR.

Notes from PR 5 that affect PR 6:
- Create schemas now reject client-supplied IDs (extra='forbid'), so any
  new test fixtures that previously passed "id" to /messages, /tasks, or
  /jobs will need to omit it.
- Registering a session for a configured agent now returns 409; use unique
  agent names in tests unless you are explicitly exercising the collision.

Time budget: 2-3 days for PR 6. If you go over by >50%, stop and ask.
If you encounter a blocker, stop, document it in the
"Open questions / blockers" section of HANDOFF.md, and report.
```

---

## Current status

**Last updated:** 2026-06-14 (PR 5 shipped)

| # | PR | Status | Branch | Merged | Notes |
|---|---|---|---|---|---|
| 0.5 | test_jobs croniter 6.x mock fix | ✅ Merged (local) | `audit/2026-q2-hardening` | a8c77b0 | Prep PR before PR 2. 4-line diff in `tests/test_jobs.py`. Closed the open question from PR 1 — full CLI suite now green without deselects (326 passed). |
| 1 | SPA key leak (CRITICAL) | ✅ Merged (local) | `audit/2026-q2-hardening` | 71106e5 | Committed locally. Spec: `pr1-spa-key-leak.md`. All tests + lint pass. |
| 2 | Transport data-loss | ✅ Merged (local) | `audit/2026-q2-hardening` | cf91e52 | Closes H1, H2, H3, H6, M7, M11, M12, M13, M23 (9 fixes). New `tests/test_transport_git.py` (23 tests) + HTTP retry/invalid-response tests + new `hub/tests/test_mcp_server.py`. CLI 357 passed, Hub 74 + 1 skip. S7 (body redaction) was pre-shipped in PR 2's http.py error cleanup. |
| 3 | Transport error handling & safety | ✅ Merged (local) | `audit/2026-q2-hardening` | 8bbd93d | Closes H8, M8, M9, M10, S2, S10, S11 (6 fixes — S7 already done in PR 2). New `write_json_atomic` in utils.py (atomic write + 0600 on POSIX); `_check_id_safe` defense-in-depth at message/task boundaries; `os.replace`+lock for archive_message/mark_read/move_to_completed; 10 MB Hub response body cap; cmd_start stops pre-opening the watchdog log fd. CLI 378 passed (+21), Hub 74 + 1 skip. |
| 4 | CLI security & correctness | ✅ Merged (local) | `audit/2026-q2-hardening` | a3ae7cf | Closes M3, M4, M5, M6, M12, S9 (6 fixes — S8 already done in PR 3). New `tests/test_eventlog.py` (4 tests) + 4 new test classes in `tests/test_cli.py` (datetime, atomic write, subprocess.run timeouts, sha256 verification) + MCP datetime guard + watchdog Popen-encoding guard. CLI 395 passed (+17), Hub 74 + 1 skip. |
| 5 | Hub input validation | ✅ Local (push pending) | `audit/2026-q2-hardening` | f9cea0c | Closes S1, S5, S6, S12, M14, M16. New `hub/tests/test_agents.py` + additions to `test_messages.py`/`test_tasks.py`; updated `test_jobs.py`/`test_pilot_mode.py` for new Create-schema behavior. Hub 87 passed, 3 skipped; CLI 436 passed, 10 skipped. Push blocked: HTTPS auth unavailable in this shell. |
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
Latest commit: f9cea0c  (fix(hub): harden Hub input validation (PR 5))
Last test run: 2026-06-14 — Hub: 87 passed, 3 skipped. CLI: 436 passed, 10 skipped.

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
  └─ 43abe10  fix(lint): address inherited N806 and no-untyped-def
  └─ f9cea0c  fix(hub): harden Hub input validation (PR 5)                      ← HEAD
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

## Open questions / blockers

1. **Push blocked for PR 5.** `git push origin audit/2026-q2-hardening` failed with:
   ```
   fatal: could not read Username for 'https://github.com': terminal prompts disabled
   ```
   This shell has no HTTPS git credentials configured (`GIT_TERMINAL_PROMPT=0`).
   The fix commit `f9cea0c` and this HANDOFF update are local only. The user
   needs to push manually from a shell that has GitHub credentials, or provide
   a token/credential helper so the next agent can push.

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
