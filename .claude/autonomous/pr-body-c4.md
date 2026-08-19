## Summary

Draft PR to get CI running on the autonomous work from `autonomous/2026-08-18-panels-loops-and-app`. **Not ready for review or merge** — opened per operator instruction solely so `ci.yml` finally runs (it never has, on any of these commits: confirmed via `gh run list` before this PR existed).

Two openspec changes are being driven on this branch:

- `2026-08-18-one-shell-three-panels` — panel shell/tabs. Agent-verifiable work essentially complete; 5 remaining tasks are human-only (7.1-7.5).
- `2026-08-18-a-loop-writes-its-own-queue` — a loop's own queue. Backend spine solid; several agent-verifiable tasks still open (A4.5, A5.1-A5.3, B6.2-B6.4) plus human-only sections.

66 commits ahead of `master`, 91 files changed (+15000/-1281), 5 new migrations.

## Current known state — DO NOT MERGE

- `hub` pytest: 2440 passed / 12 skipped / 1 xpassed (green)
- `vitest`: 1070 passed / 105 files (green)
- eslint/tsc/ruff/black: clean
- **Browser suite (Playwright) is currently RED: 8 of 53 failing**, with fixes in flight this session. A real defect was found on a task that had been marked done (an active-tab steal in `ConversationView.tsx`) plus a false-green Playwright test that hid it, plus suite order-dependence. See `.claude/autonomous/2026-08-18-panels-loops-and-app-log.md` for the full review.

This PR exists to surface CI signal (Linux/macOS/py3.12) while those fixes land as further commits on this same branch. It will be updated, not merged, until the browser suite is genuinely green and both specs' agent-verifiable tasks are done.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
