# Handoff: Runner/Agent/Charter separation complete

**Date:** 2026-08-03T19:13:00+01:00 · **Branch:** hub-native-experience · **HEAD:** 4aaa828
**Agent:** Codex gpt-5.6-sol (T3 Code)
**Previous handoff:** `.claude/handoffs/2026-08-03-1900-legacy-roles-removed.md`
**Status:** successor complete and archived

## Goal completed

The `runner-agent-charter-separation` successor is fully implemented, verified, documented, and
archived. Runner, Agent, and Charter are independent Hub-owned records, and the legacy fixed-role
runtime has been removed.

## Final chunk

- Fixed the final runtime integration gap: every Hub trigger now renders canonical context from
  current Hub session, agent, and charter state, materializes it inside the effective workspace,
  and supplies that file to the bound runner. A typed 409 is returned if materialization fails.
- Added a regression proving a bound charter reaches the runner's system-prompt context file.
- Updated `AGENTS.md` and `CLAUDE.md` for the shipped Runner/Agent/Charter architecture.
- Live-verified a fresh Hub in `testbed/live-runner-charter/`: two default runners and 21 starter
  charters seeded; a real Codex run read a unique custom-charter marker; an unchartered agent got
  the no-charter notice; and an agent without a runner returned the typed waiting result.
- Annotated umbrella task 16.2 as partially reconciled and archived the successor as
  `openspec/changes/archive/2026-08-03-runner-agent-charter-separation/`.
- Removed the empty root `.agentweave/logs/events.jsonl` residue recreated by tests; the framework
  repository has no root `.agentweave/`, `agentweave.yml`, or `spec/` state.

## Verification

- CLI: 349 passed, 3 skipped.
- Hub: 490 passed, 4 skipped.
- Frontend: 286 passed.
- Frontend production build passed; existing duplicate-case and chunk-size warnings remain.
- Changed-file Ruff and Black checks passed.
- `openspec validate --all --strict`: 20/20 passed after archive (21/21 before archive).
- `git diff --check` passed.

## Commits in this successor

- `610870c`, `c6ec436` — runner registry, trigger binding, and UI.
- `dbdf486` — charter registry and canonical context.
- `beb809c` — specification reconciliation.
- `1513314` — legacy role removal.
- `4aaa828` — final runtime context fix, verification, docs, and archive.
- Checkpoint commits: `d9a4240`, `abdfc68`, plus the commit containing this handoff.

## Remaining project work

- The runner/agent/charter successor itself has no remaining tasks.
- The larger `2026-07-30-hub-native-experience` umbrella still has open work; task 16.2 remains
  intentionally partial because other umbrella delta specs are not yet reconciled.
- Preserve these unrelated untracked files unless their owner asks otherwise:
  - `src/agentweave/templates/skills/handoff.md`
  - `src/agentweave/templates/skills/resume.md`
  - `tests/test_handoff_resume_templates.py`

## Resume prompt

Resume from `4aaa828` plus the immediately following checkpoint commit. The
`runner-agent-charter-separation` successor is complete and archived; inspect the remaining
`2026-07-30-hub-native-experience` tasks before selecting the next successor. Preserve the three
unrelated untracked handoff/resume files and do not create AgentWeave state at the repository root.
