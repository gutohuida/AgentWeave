# Deployment Handoff — 2026-06-18

## Release

- **CLI:** v0.38.1
- **Hub:** v0.32.0
- **Date:** 2026-06-18
- **Audit merge commit:** `c2797d3` — `Merge audit/2026-q2-hardening into master (v0.38.0 / Hub v0.32.0)`
- **Patch commit:** `b269b4e` — `fix(cli): restore Python 3.8 runtime compat and Linux-only fd leak test`

## What was done

1. Merged the `audit/2026-q2-hardening` branch into `master` as a single merge commit (`c2797d3`).
2. Tagged and released **CLI v0.38.0** and **Hub v0.32.0**:
   - `v0.38.0` on `master`
   - `hub-v0.32.0` on `master`
3. Published `agentweave-ai==0.38.0` to PyPI.
4. Created GitHub releases for `v0.38.0` and `hub-v0.32.0`.
5. After CI failed on Python 3.8 (PEP 585 type syntax) and macOS (`/proc`-based test), shipped **CLI v0.38.1**:
   - Added `from __future__ import annotations` to `src/agentweave/cli.py` and `src/agentweave/watchdog.py`.
   - Changed `tests/test_cli_watch.py::test_cmd_start_does_not_leak_fd_on_posix` to Linux-only.
   - Added `UP006` / `UP037` to the ruff ignore list to keep the patch minimal.
   - Bumped CLI version to `0.38.1` and updated `CHANGELOG.md`.
6. Pushed `master` and `v0.38.1` tag to GitHub.
7. Published `agentweave-ai==0.38.1` to PyPI.
8. Created GitHub release for `v0.38.1`.

## Changes since v0.37.1 / Hub v0.31.2

### CLI v0.38.0 / v0.38.1
- Security and reliability hardening from 12 audit PRs (PR 0.5 – PR 12), including API-key leak fixes, Git/HTTP transport reliability, atomic file operations, UTC-aware datetimes, subprocess timeouts/encoding, dead-code removal, code-quality sweep, UUID length fix, and expanded test coverage.
- Python 3.8 runtime compatibility restored in v0.38.1.

### Hub v0.32.0
- Input validation hardening (role IDs, create schemas, string length caps, unsafe `work_dir`, bounded `limit`).
- `/agent/trigger` path safety, SSE ticket auth, N+1 query elimination, request body size cap.
- Automatic Alembic migrations on startup and `job_runs.error_summary` capped to `String(500)`.
- Hub UI security/performance improvements (SSE auth, sessionStorage API key, `<ErrorBoundary>`, SSE-driven polling).
- First Hub UI test suite (Vitest/jsdom) and BOLA isolation tests.

## Verification

- `ruff check src/` passes.
- `black --check src/` passes.
- `mypy src/` passes (warns that mypy 2.1 no longer supports `python_version = 3.8`, but succeeds).
- `pytest tests/` passes (523 passed).
- `pytest hub/tests/` passes (177 passed, 4 skipped).
- `python -m build` succeeds for `agentweave-ai==0.38.1`.
- GitHub Actions `CI` workflow passes on the `v0.38.1` patch commit across all matrix jobs (Python 3.8–3.12 on Ubuntu, macOS, Windows).

### Note on the `Publish to PyPI` workflow
The `Publish to PyPI` workflow for `v0.38.1` shows as **failed** because the release was uploaded to PyPI manually before the workflow ran; the subsequent automated upload received HTTP 400 from PyPI since the files already exist. The package is live on PyPI (see below), so the failure is cosmetic for this release.

## Releases

- CLI v0.38.1: https://github.com/gutohuida/AgentWeave/releases/tag/v0.38.1
- CLI v0.38.0: https://github.com/gutohuida/AgentWeave/releases/tag/v0.38.0
- Hub v0.32.0: https://github.com/gutohuida/AgentWeave/releases/tag/hub-v0.32.0
- PyPI: https://pypi.org/project/agentweave-ai/0.38.1/
