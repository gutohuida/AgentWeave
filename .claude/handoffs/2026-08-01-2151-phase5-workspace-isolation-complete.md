# Handoff: Phase 5 workspace isolation complete

**Date:** 2026-08-01T21:51:47+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `6a6088e`
**Agent:** Codex (GPT-5.6)
**Previous handoff:** `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This chunk completed Phase 5,
workspace isolation, so the inbound scheduler introduced in Phase 6 can run concurrent writing
agents without allowing them to overwrite one another silently.

## Current state

Phase 5 is fully closed. Every writing agent now receives a validated, per-agent linked Git
worktree on `agentweave/<agent>` before its first Hub-owned process starts. Read-only agents may
share the primary checkout. Isolation fails closed when Git or worktree provisioning is unavailable,
and a caller cannot use `work_dir` to bypass it for a writing agent.

At run completion, dirty work is snapshotted to the agent branch with an internal Git identity.
Authenticated worktree endpoints list active isolated checkouts and report pairwise merge conflicts
with both agent names and paths. Removing an agent snapshots dirty state, removes only the linked
checkout, preserves its branch, reports unmerged commits through persisted/SSE events, and excludes
that retained branch from the active-worktree list. The implementation is committed in `6a6088e`;
the task-5.6 checkbox is the only tracked post-commit change and should be committed immediately
after this handoff is written.

## Files touched

- `hub/hub/worktrees.py` — new isolation core: validated paths/refs, provisioning, dependency links,
  snapshots, safe release, active-worktree discovery, and pairwise conflict detection. Finished.
- `hub/hub/api/v1/worktrees.py` — new authenticated active-worktree and conflict-report endpoints.
  Finished.
- `hub/hub/api/v1/__init__.py` — mounts the worktree router. Finished.
- `hub/hub/api/v1/agent_trigger.py` — provisions isolation before spawn, uses the worktree as cwd,
  fails closed, prevents `work_dir` bypass, and snapshots after a turn. Finished.
- `hub/hub/api/v1/session_sync.py` — validates agent names and releases removed agents' worktrees
  while persisting/broadcasting unmerged-work status. Finished.
- `hub/tests/conftest.py` — prevents unrelated Hub tests from provisioning worktrees in the real
  checkout. Finished.
- `hub/tests/test_worktrees.py` — new disposable-repository coverage for provisioning, dependency
  sharing, snapshots, release, retained branches, conflict reports, API responses, and containment.
  Finished.
- `hub/tests/test_agent_trigger.py` — verifies pre-spawn isolation, primary-checkout use for readers,
  bypass rejection, and failure-closed behavior. Finished.
- `hub/tests/test_session_sync.py` — new roster reconciliation and safe-release integration tests.
  Finished.
- `src/agentweave/config.py` — adds typed `read_only` parsing/serialization and generated-YAML
  support. Finished.
- `src/agentweave/cli.py` — carries `read_only` into session activation. Finished.
- `src/agentweave/constants.py` — permits `read_only` in agent configuration. Finished.
- `src/agentweave/session.py` — syncs and exposes `read_only`, including true-to-false transitions.
  Finished.
- `src/agentweave/validator.py` — validates `read_only` as boolean. Finished.
- `docs/reference/agentweave-yml.md` — documents the `read_only` field and its safety boundary.
  Finished.
- `tests/test_config.py` — covers YAML parsing, type rejection, serialization, and generated-file
  round trips for `read_only`. Finished.
- `tests/test_session.py` — covers clearing `read_only` during reconciliation. Finished.
- `tests/test_validator.py` — covers invalid `read_only` types. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — tasks 5.1–5.6 closed with
  implementation and verification evidence. Finished; task 5.6 line is pending its checkpoint commit.
- `.claude/handoffs/LATEST.md` — pre-existing dirty pointer from the interrupted session; updated to
  point at this handoff. Session-note state, deliberately not included in the implementation commit.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — this handoff. Finished.

## Key decisions

1. **Writing-agent isolation fails closed.** The interrupted implementation fell back to the primary
   checkout when the directory was not a Git repository or provisioning failed. Rejected because it
   violated the spec's MUST and silently recreated the lost-update problem Phase 5 exists to solve.
   A trigger now returns HTTP 409 without spawning.
2. **A custom `work_dir` cannot override a writer's worktree.** Preserving that override for writers
   would make isolation optional per request. It remains available to declared read-only agents.
3. **Branches survive removal; active checkout discovery does not equate branches with agents.**
   Deleting a branch could discard unmerged work, while listing every retained branch made removed
   agents appear active. Release removes only the linked checkout; active discovery parses
   `git worktree list --porcelain` and release events identify retained commits.
4. **Turn-end snapshots use a local internal Git identity.** Depending on the operator's global
   `user.name`/`user.email` made conflict detection fail on otherwise valid installations. The
   identity is supplied only to the snapshot command and does not alter repository/global config.
5. **Reused branches fast-forward only when already ancestral to primary HEAD.** This gives a
   re-added agent current project state after its prior work was merged, while branches carrying
   unique unmerged commits are preserved exactly instead of being reset or rebased implicitly.
6. **Dependency sharing is explicit and best-effort.** Only `node_modules`, `.venv`, and `venv` are
   linked. Windows hosts without symlink permission continue with an isolated checkout and may
   install dependencies locally; isolation itself never degrades.

## Constraints and user directives (verbatim)

- "It was underway and it my tokens expired... Continue phase 5."
- "ok continue"
- "Yeah and always commit the changes."
- "After every threshold of implementation you must run the skill `/handoff`"
- From the prior phase's still-applicable working style: "Only stop if there is actually a blocking
  issue... don't need to be conservative on the changes... if there is genuinely a best approach
  you can scrap anything that already exists. Also apply these new rules when creating handoffs.
  Do a little bit less handoffs then previously but still do them."
- Repository rule: never commit runtime `.agentweave/` state; stage exact paths rather than
  `git add -A`.
- The task ledger's working protocol remains binding: re-read `proposal.md`, `design.md`, and each
  affected spec before starting a phase; verify against scenarios; create one handoff per phase.

## Dead ends

- The first resume patch targeted a nonexistent `TestAgentConfig` class and applied nothing. The
  actual class is `TestConfigDataclasses`; subsequent patches used live file structure.
- The interrupted code accepted/documented `read_only` at the low-level validator but omitted it
  from `AgentConfig` and `_activate_agents`, so real YAML configuration silently dropped it. Tests
  exposed this before the parser/session/generator path was completed.
- The interrupted `list_agent_branches()` used all `refs/heads/agentweave/*`, causing a safely
  retained branch to appear as an active removed agent. It now derives active agents from registered
  linked worktrees only.
- Snapshots initially depended on operator Git identity and failed with “Author identity unknown.”
  Per-command identity fixed it without mutating user config.
- Reusing a released, already-merged branch initially restored its old tree and missed newer primary
  commits. An ancestry-gated fast-forward fixed it without overwriting unique work.
- A first config edit accidentally nested the existing empty-`cli` validation beneath the new
  `read_only` type error. Immediate inspection caught and corrected it before the next test run.
- One test insertion temporarily moved two quality-template assertions into the new read-only test;
  Ruff/pytest caught the undefined variable and the assertions were restored to their original test.
- Broad mypy invocation still reports the repository's existing Hub typing/stub debt. A focused run
  with skipped imports passed for the new worktree module and its two API modules; no attempt was made
  to repair unrelated type errors.

## Verification

Ran and passed after the final implementation changes:

- `py -m pytest tests/ -q` — **991 passed, 4 skipped**.
- `cd hub; py -m pytest -q` — **396 passed, 4 skipped**, with four pre-existing Alembic warnings.
- Targeted CLI tests (`tests/test_config.py tests/test_session.py tests/test_validator.py`) — passed.
- Targeted Hub tests (`tests/test_worktrees.py tests/test_agent_trigger.py tests/test_session_sync.py`)
  — passed.
- `py -m ruff check` across every touched Python file — passed.
- `py -m black --check --fast` across every touched Python file — passed.
- `py -m mypy --follow-imports=skip --ignore-missing-imports hub/hub/worktrees.py
  hub/hub/api/v1/worktrees.py hub/hub/api/v1/session_sync.py` — passed.
- `git diff --check` before the implementation commit — passed.

Not tested:

- No live Hub-owned Claude/Codex process was spawned in an actual project worktree; spawn behavior
  uses mocked PTY/Pipe sessions against real disposable Git repositories.
- No two real agents ran concurrently. The overlap scenario is verified by independent real
  worktrees writing and snapshotting conflicting versions of the same file, followed by a real
  `git merge-tree` conflict report.
- No dashboard component renders conflicts yet; Phase 5 exposes the required information through
  authenticated API endpoints. Later conversation/workspace UI phases can consume it.
- Dependency symlink creation may be unavailable on Windows without Developer Mode/admin rights;
  the test verifies shared content when the host permits the link and the code deliberately falls
  back to per-worktree dependency installation otherwise.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `6a6088e Phase 5: isolate writing agents with git worktrees`.
- No upstream is configured; commits remain local and unpushed.
- At handoff creation, implementation files are committed. The tracked task-5.6 checkbox and
  `.claude/handoffs/LATEST.md` are dirty; this new handoff plus the same older handoffs and
  `.claude/skills/aw-spec-reindex/` are untracked session/tooling artifacts. Only the task ledger
  should be staged for the checkpoint commit; do not sweep the older untracked paths into Git.

## Next steps

1. Re-read `openspec/changes/2026-07-30-hub-native-experience/design.md` Decisions 3–6 and
   `openspec/changes/2026-07-30-hub-native-experience/specs/agent-inbound-queue/spec.md`, then inspect
   the existing `Message`, `Run`, crash-reconciliation, and direct-trigger paths before designing
   Phase 6 task 6.1's queue-entry model. Do not implement the model before those reads; the phase
   protocol requires them and the atomic-drain/recovery invariants determine the schema.
2. Execute the whole of Phase 6 (tasks 6.1–6.12) unless a genuinely blocking issue arises, preserving
   the ordering constraint that queue delivery and run creation commit atomically.
3. Run `/handoff` once at the Phase 6 boundary (task 6.13), not after each subtask.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — authoritative ledger and Phase 6
  task sequence.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — Decisions 3–6 define queue
  semantics, atomic drain, hop budget, and agent budget.
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-inbound-queue/spec.md` — Phase 6
  requirements and scenarios.
- `hub/hub/db/models.py` — queue-entry and run/delivery schema integration point.
- `hub/hub/api/v1/agent_trigger.py` — direct execution path the scheduler must invoke without
  bypassing Phase 5 isolation.
- `hub/hub/run_reconciliation.py` — interrupted-run reconciliation that must return delivered
  entries.
