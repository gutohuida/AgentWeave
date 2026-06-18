# 2026 Q2 Hardening Release

**CLI:** v0.38.0 (shipped 2026-06-18) + v0.38.1 (patch, 2026-06-18)  
**Hub:** v0.32.0 (shipped 2026-06-18)  
**Audit branch:** `audit/2026-q2-hardening` → merged to `master` in commit `c2797d3`

---

## What this release was about

This was the big security-and-reliability audit that ran through the entire AgentWeave codebase: CLI core, Hub backend, transport layer, and Hub UI. The goal was to harden the framework against real operational risks — API-key leaks, data-loss paths, path traversal, mass assignment, silent failures — while keeping the public API surface unchanged and significantly increasing test coverage.

The work was executed as **12 PRs** (PR 0.5 through PR 12) on a dedicated audit branch, then merged to `master` as a single merge commit and released as **CLI v0.38.0 / Hub v0.32.0**. A follow-up **CLI v0.38.1** patch fixed Python 3.8 compatibility and a macOS-only CI failure.

---

## Headline achievements

| Category | Count | Highlights |
|---|---|---|
| Critical security fixes | 1 | SPA API-key leak eliminated — live project key no longer injected into Hub dashboard HTML |
| Data-loss / corruption fixes | 8 | GitTransport aborts on `ls-tree` failures, local outbox for at-least-once delivery, atomic archive/move operations, `os.replace` + `lock()` for local transport and task operations |
| Security hardening | 12 | Path-traversal protection, create-schema mass-assignment removal, string-length caps, unsafe `work_dir` rejection, SSE ticket auth, API key removed from SSE URL and `localStorage` |
| Medium bug fixes | 23 | UTC-aware datetimes, subprocess timeouts/encoding, atomic `transport.json`, automatic Alembic migrations, N+1 query elimination, request body cap |
| Test coverage | +108 new tests | New suites for logging handlers, runner, locking, HTTP transport, git transport, Hub jobs/chat/MCP/agents, BOLA isolation, migrations, and first Hub UI tests |
| Code quality | 16+ | Dead-code removal (~277 lines), standardized `Optional[X]` types, standardized print/logging helpers, UUID length fix |

**Total:** 60+ distinct issues closed across CLI, Hub, transport, and UI.

---

## Impact by area

### CLI (v0.38.0 / v0.38.1)
- **Security:** live API key no longer leaks through Hub SPA; `transport.json` written atomically with `chmod 600`; downloaded assets verified with SHA256.
- **Reliability:** GitTransport and HttpTransport retry/backoff paths; atomic file moves; subprocess calls get timeouts and UTF-8 encoding.
- **Compatibility:** v0.38.1 restored Python 3.8 runtime support by adding `from __future__ import annotations` where PEP 585 generics were used.

### Hub backend (v0.32.0)
- **Validation:** role IDs, agent names, subjects, content, IDs, and `work_dir` all validated and bounded.
- **Auth:** SSE streams moved from `?token=` query param to short-lived signed tickets; REST endpoints require `Authorization` header.
- **Performance:** `list_agents` N+1 eliminated with bulk queries.
- **Operations:** Alembic migrations run automatically on startup; `job_runs.error_summary` capped at 500 chars.

### Hub UI (v0.32.0)
- **Security:** API key stored in `sessionStorage`, theme only in `localStorage`; SSE uses `fetch()` with Bearer header.
- **Performance:** output polling replaced with SSE-driven updates; App routing rewritten to mount only the active page.
- **Quality:** `<ErrorBoundary>` at root, shared agent-status helpers, extracted components, first Vitest/jsdom test suite.

### Transport layer
- **GitTransport:** timeout on all git calls, local outbox for failed pushes, lock-protected seen-set, microsecond-precision timestamps.
- **HttpTransport:** retry 5xx/429/`URLError`, exponential backoff with `Retry-After`, response body cap, redacted `api_key=` in error output.
- **LocalTransport/Messaging:** atomic moves, POSIX 0600 permissions, `lock()` around archive operations.

---

## Release artifacts

- CLI v0.38.1: https://github.com/gutohuida/AgentWeave/releases/tag/v0.38.1
- CLI v0.38.0: https://github.com/gutohuida/AgentWeave/releases/tag/v0.38.0
- Hub v0.32.0: https://github.com/gutohuida/AgentWeave/releases/tag/hub-v0.32.0
- PyPI: https://pypi.org/project/agentweave-ai/0.38.1/

---

## Detailed changes

See [changes.md](changes.md) for the full changelog excerpt covering v0.38.0, Hub v0.32.0, and the v0.38.1 patch.
