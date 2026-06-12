# AgentWeave Audit — 2026 Q2

> **Status:** Planning complete, execution not yet started.
> **Created:** 2026-06-12 by `opencode` (MiniMax-M3) on behalf of `gutohuida`.
> **Branch:** `audit/2026-q2-hardening` (not yet created).
> **Target release:** v0.38.0 (CLI) / v0.32.0 (Hub).

A full-codebase audit of AgentWeave covering the CLI core, Hub backend, transport layer, and Hub UI, plus test coverage. The goal is to ship a v0.38.0 release that hardens security, eliminates data-loss paths, and fills test gaps — without changing the public API surface.

---

## How to pick this up

If you (or another agent) are reading this in a new session, follow these steps in order:

1. Read this file completely (~5 minutes).
2. **Open `HANDOFF.md` first** — it has the current status, branch state, and copy-pasteable prompts ready to send to the next agent.
3. Skim `findings.md` for the consolidated prioritized bug list (~10 minutes).
4. Read `pr-roadmap.md` to see the 12-PR execution plan (~15 minutes).
5. Start with the next PR in the HANDOFF.md status table — read its spec end-to-end before writing any code.
6. Each PR is self-contained. Stop after any PR and the codebase is still shippable.

If you have **only 5 minutes**: read the "Headline numbers" and "Quick start" sections below, then jump to HANDOFF.md.

If you have **only 30 minutes and want to ship one fix**: open HANDOFF.md, copy Prompt 2, fill in the PR number and spec filename, send it.

---

## Headline numbers

| Severity | Count | Notes |
|---|---|---|
| **CRITICAL** | 1 | SPA key leak — any unauthenticated `GET /` returns a working API key |
| **HIGH (data loss / corruption)** | 8 | Git transport can wipe the entire orphan branch; HTTP transport has no retry; several silent-drop paths |
| **HIGH (security)** | 12 | Path traversal in 2 places, mass assignment, unbounded inputs, key in SSE URL, key in localStorage, etc. |
| **MEDIUM (bugs)** | 23 | N+1 queries, sync MCP blocking event loop, deprecated `datetime.utcnow`, missing timeouts, no alembic auto-run |
| **MEDIUM (test gaps)** | 10 | `tests/test_git_transport.py` does not exist; `hub/hub/api/v1/agent_chat.py` has no tests; no BOLA test |
| **LOW (code quality)** | 16 | ~100 `print()` calls in `cli.py`, 240 lines of dead code, mixed `Optional[X]` / `X \| None`, duplicate context builders |

**Total:** 1 CRITICAL + 8 HIGH data-loss + 12 HIGH security + 23 MEDIUM + 16 LOW = **60 distinct issues** across 1 CRITICAL fix, 8 data-loss fixes, 12 security fixes, 4 transport hardening PRs, 4 UI fixes, 2 quality PRs, and 4 test-coverage PRs, plus 1 release prep.

---

## Quick start

```bash
cd C:\Users\huida\Documents\projects\AgentWeave
git checkout -b audit/2026-q2-hardening

# Bump versions to signal audit work in flight
#   hub/pyproject.toml: 0.31.1 → 0.32.0-audit.1
#   src/agentweave/__init__.py: 0.37.0 → 0.38.0-audit.1
```

Then execute PR 1 (the SPA key leak fix) following `pr1-spa-key-leak.md`. That alone closes the only CRITICAL issue.

---

## Strategy

- **Branch:** `audit/2026-q2-hardening`, all 12 PRs target it, one final PR back to `master`.
- **Test-first on every fix:** write a failing test that demonstrates the bug, confirm it fails, then apply the fix, confirm it passes. This is non-negotiable for the CRITICAL and HIGH issues.
- **One PR per area:** 12 small PRs, independently reviewable and revertable. Burnout-safe: stop after any PR and the codebase still ships.
- **Pacing:** 10-20 hrs/week → 8-9 weeks for all 12 PRs.
- **No public API changes:** all fixes are internal hardening. The user-facing CLI/Hub/API surface is unchanged.

---

## The 12 PRs (one per area)

| # | PR | Area | Severity closed | Estimated time |
|---|---|---|---|---|
| 1 | SPA key leak fix | Security | 1 CRITICAL | 0.5 day |
| 2 | Transport data-loss bugs | Transport | H1-H6, M11-M13, M23 | 3-4 days |
| 3 | Transport error handling | Transport | H8, M1-M3, M7-M8, S7, S10 | 2 days |
| 4 | CLI security & correctness | CLI | M3-M6, M12, S2, S8-S9 | 2-3 days |
| 5 | Hub input validation | Hub | S1, S5-S6, S12, M14, M16 | 2 days |
| 6 | Hub auth, BOLA, perf | Hub | S3 (server half), M15, M17, T5 | 2-3 days |
| 7 | DB & migrations | Hub | H5, M4, T7 | 1 day |
| 8 | Dead code & dedup | Quality | H7, duplicates | 0.5 day |
| 9 | Hub UI security | UI | S3 (client half), S4, M19-M20, M22, ErrorBoundary | 2 days |
| 10 | Hub UI performance & dedup | UI | M21, UI quality | 2 days |
| 11 | CLI/watchdog code quality | Quality | print→logging, function splits, mixed styles | 2 days |
| 12 | Test coverage sweep | Tests | T1-T10 | 3-4 days |

Full details in `pr-roadmap.md`.

---

## Working environment checklist

For a new agent picking this up:

- **Working dir:** `C:\Users\huida\Documents\projects\AgentWeave`
- **Python:** 3.11+ (CLI is 3.8+ compatible; Hub is 3.11+)
- **Test commands:**
  - CLI tests: `pytest tests/ -v`
  - Hub tests: `cd hub && pytest tests/ -v`
  - All: `make test-all`
- **Lint:** `ruff check src/`, `black src/`, `mypy src/`
- **UI dev:** `cd hub/ui && npm install && npm run dev` (proxies `/api` → `localhost:8000`)
- **Hub dev:** `cd hub && docker compose up -d` (or `docker compose -f docker-compose.build.yml up --build -d` for hot-reload)

---

## Hand-off checklist

When picking up where another agent left off, confirm:

- [ ] On branch `audit/2026-q2-hardening` (not `master`)
- [ ] Latest commit is the end of an in-progress PR (check `git log --oneline -5`)
- [ ] No uncommitted changes (`git status` is clean) — or document them
- [ ] `pytest tests/ -v` and `cd hub && pytest tests/ -v` both pass
- [ ] Read the relevant PR document in `pr-roadmap.md` or `pr1-spa-key-leak.md` before resuming

---

## Files in this directory

| File | Purpose | Length |
|---|---|---|
| `README.md` | This file — on-ramp for new agents | ~150 lines |
| `HANDOFF.md` | **Living runbook.** Status table, branch state, copy-pasteable prompts, session log. Update this as work progresses. | ~200 lines |
| `findings.md` | Consolidated prioritized bug list with file:line references | ~350 lines |
| `pr-roadmap.md` | 12-PR execution plan with file changes + test plans | ~500 lines |
| `pr1-spa-key-leak.md` | Standalone detailed plan for PR 1, ready to execute | ~120 lines |
| `audit-reports/01-cli-core.md` | Raw explore agent report: CLI core audit | ~300 lines |
| `audit-reports/02-hub-backend.md` | Raw explore agent report: Hub backend audit | ~400 lines |
| `audit-reports/03-transport.md` | Raw explore agent report: Transport layer audit | ~300 lines |
| `audit-reports/04-tests-and-ui.md` | Raw explore agent report: Tests + Hub UI audit | ~400 lines |

---

## License

This audit documentation is part of the AgentWeave project and follows the same MIT License as the rest of the codebase.
