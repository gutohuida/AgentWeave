# Deployment Handoff — 2026-06-14

## Release

- **CLI:** v0.37.1
- **Hub:** v0.31.2
- **Date:** 2026-06-14
- **Commit:** `39b7b44` — `Bump to v0.37.1 / Hub v0.31.2`

## What was done

1. Cherry-picked `43abe10` (lint fix) from the audit branch onto `master` to fix CI failures introduced by the opencode feature commit.
2. Pushed the lint fix to `master` and verified CI passed.
3. Bumped versions:
   - `pyproject.toml`: `0.37.0` → `0.37.1`
   - `hub/pyproject.toml`: `0.31.1` → `0.31.2`
4. Updated `CHANGELOG.md` with v0.37.1 release notes.
5. Updated `CLAUDE.md` and `README.md` version references.
6. Committed and pushed the version bump to `master`.

## Changes since v0.37.0 / Hub v0.31.1

### CLI
- Per-agent opencode CLI override via `AgentConfig.cli`.
- Free-form `opencode:` block in `agentweave.yml`.
- Added `agentweave.template.yml` and `docs/guides/opencode-models.md`.
- Fixed `test_should_fire_old_last_run` for croniter 6.x.
- Fixed inherited ruff N806 and mypy no-untyped-def warnings.

### Hub
- Version bumped to v0.31.2 for release parity. No Hub-specific functional changes.

## Verification

- `ruff check src/` passes.
- `pytest tests/` passes (364 passed, 10 skipped).
- GitHub Actions CI passed on the version bump commit.
  - `CI` workflow: success
  - `Publish Hub Docker image` workflow: success

## Releases

- CLI: https://github.com/gutohuida/AgentWeave/releases/tag/v0.37.1
- Hub: https://github.com/gutohuida/AgentWeave/releases/tag/hub-v0.31.2
