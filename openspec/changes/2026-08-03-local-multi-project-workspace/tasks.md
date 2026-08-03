# Implementation plan

## Working protocol — read before starting any phase

1. Re-read `proposal.md`, `design.md`, and all three delta specs before each phase.
2. Tests open every phase; implementation does not begin until the phase's failing contract is
   demonstrated.
3. Every project-aware API, cache key, event, and filesystem path must carry explicit project
   identity. A compatibility shortcut that restores implicit global selection is not allowed.
4. Use `testbed/` for live projects. Never run AgentWeave or create `.agentweave/`,
   `agentweave.yml`, or `spec/` at this framework repository root.
5. End every phase with focused verification and a durable `/handoff`.
6. A task becomes done only after its implementation and stated verification pass.

## 0. Persistence, canonical paths, and migration

- [x] 0.1 Write migration/model tests for nullable legacy binding, unique canonical `path_key`,
      project directory states, timestamps, and the separate instance operator credential.
- [x] 0.2 Add the Alembic migration and typed project/operator models; migrate the existing
      bootstrap credential value without changing it or deleting project data.
- [x] 0.3 Write table-driven path tests for Windows/POSIX case and separators, symlinks/junctions,
      duplicate aliases, filesystem roots, Hub data, and nested AgentWeave worktrees.
- [x] 0.4 Implement canonical path and `ProjectWorkspace` resolution with typed unavailable and
      identity-conflict errors.
- [x] 0.5 Write marker/open/create/relocate tests, including copied marker, moved missing project,
      active-run/worktree refusal, atomic marker failure rollback, and explicit register-copy-as-new.
- [x] 0.6 Implement the versioned marker and transactional project lifecycle service; seed default
      runners and starter charters for a genuinely new project.
- [x] 0.7 Verify every identity/directory scenario in `local-project-workspace`.
- [x] 0.8 `/handoff`.

## 1. Operator project API and settings

- [x] 1.1 Write auth/route tests proving the instance credential lists all projects, explicit
      project paths isolate resources, unknown project IDs fail, and run credentials cannot choose
      another project.
- [x] 1.2 Add project collection/open/create/get/settings/relocate routes and shared operator/project
      dependencies. Return project summaries with agents, live/directory state, path display, and
      budget settings.
- [x] 1.3 Move operator resource routers beneath explicit project paths while preserving their
      response contracts; add parity tests for tasks, agents, conversations, jobs, specs, and logs.
- [x] 1.4 Implement settings validation for name, hop/delivery/agent/token budgets and agent-job
      allowance through existing services.
- [x] 1.5 Update setup bootstrap to return the instance credential and no implicit authenticated
      project; remove completed project-key auth paths without affecting run tokens.
- [x] 1.6 Verify the collection, settings, and operator/agent boundary scenarios.
- [x] 1.7 `/handoff`.

## 2. CLI lifecycle and legacy binding

- [x] 2.1 Write CLI tests for first start, already-running instance, foreground start, zero-project
      direct Hub start, legacy `proj-default` binding, status counts, and open failure.
- [x] 2.2 Refactor native scaffold/start so bare invocation captures its directory and uses one
      post-health project-open call before opening the project URL.
- [x] 2.3 Replace bootstrap project labels in status with live instance/project-collection state;
      retain instance-wide stop and confirmed reset without touching project directories.
- [x] 2.4 Implement idempotent first-open binding of one unbound legacy project and the UI/API locate
      repair path for a directly started Hub.
- [x] 2.5 Verify the modified `app-lifecycle` scenarios and migration against a copied pre-change DB.
- [x] 2.6 `/handoff`.

## 3. Runtime and filesystem isolation

- [x] 3.1 Write two-repository tests for direct/queued runs, context materialization, workspace path
      listing, worktree create/list/conflicts/release, git diagnostics, and concurrent agents.
- [x] 3.2 Replace every project-related Hub `Path.cwd()` call with `ProjectWorkspace`; make worktree
      operations project-rooted and context files effective-workspace-rooted.
- [x] 3.3 Remove absolute `work_dir`; if subdirectory execution remains, accept only a contained
      repository-relative path. Add traversal/symlink escape tests.
- [x] 3.4 Remove the global `.agentweave/session.json` roster fallback and render canonical context
      from Hub-owned project/agent/runner/charter/instruction state without cross-project leakage.
- [ ] 3.5 Write unavailable-directory tests: new operator input refused, existing queue retained,
      autonomous/scheduled starts paused with events, repair re-evaluates work without disabling jobs.
- [ ] 3.6 Implement unavailable/repair scheduling behavior and safe relocation guards.
- [ ] 3.7 Verify project-correct runtime paths and no cross-project file/process effects.
- [ ] 3.8 `/handoff`.

## 4. Multi-project SSE and frontend data identity

- [ ] 4.1 Write backend tests for an instance operator ticket/stream, server-stamped `project_id`,
      inactive-project events, collection lifecycle events, and reconnect behavior.
- [ ] 4.2 Implement operator SSE fan-out while retaining internal project channels and stamping
      identity outside caller payloads.
- [ ] 4.3 Write frontend contract tests that enumerate every API hook and fail if a project-scoped
      query/mutation key lacks project ID; include delayed response and rapid-switch races.
- [ ] 4.4 Migrate API clients, React Query keys, invalidation, and mutations to explicit project
      arguments/routes. Clear/ignore legacy unscoped cache state.
- [ ] 4.5 Migrate `configStore` bootstrap from one authenticated project to one instance credential
      plus project collection/selection; preserve project-keyed composer drafts.
- [ ] 4.6 Implement one operator SSE connection and project-aware invalidation, including full
      reconciliation on reconnect.
- [ ] 4.7 Verify no cache/event from project A changes project B's rendered state.
- [ ] 4.8 `/handoff`.

## 5. URL navigation, rail, tabs, and project management

- [ ] 5.1 Write URL/navigation tests for reload, back/forward, invalid project fallback, project
      switching, direct agent conversation, and no provider session IDs.
- [ ] 5.2 Synchronize `WorkspaceDestination` with URL search parameters using browser history, without
      adding a routing dependency.
- [ ] 5.3 Write rail tests for multiple projects, duplicate-name path hints, live agent/directory
      state, independent expand/navigation controls, persisted collapse, and open/create actions.
- [ ] 5.4 Feed the rail from the project-summary collection and build explicit open-existing/create-new
      flows with path preview and typed errors.
- [ ] 5.5 Write project-tab reachability tests proving Tasks, Spec, Jobs, Activity, and Environment
      require no rail entry; Overview contains Questions, Activity contains Logs, and Environment
      contains Quality/Instructions/Runners/Charters/worktrees/diagnostics/settings.
- [ ] 5.6 Recompose existing pages into the project tab shell and remove their top-level rail entries.
- [ ] 5.7 Build missing-directory/locate/settings views and preserve one-action conversation return.
- [ ] 5.8 Apply `Agent.color_index` consistently to task assignees/selectors and activity actors,
      with name text; add exact mapping tests across rail/conversation/task/activity.
- [ ] 5.9 Verify modified `agent-conversation-workspace` and referenced `hub-visual-language`
      navigation/color scenarios, including keyboard, narrow/wide, and reduced-motion behavior.
- [ ] 5.10 `/handoff`.

## 6. Docker, cleanup, documentation, and closeout

- [ ] 6.1 Write Docker configuration tests for an explicitly mounted workspace root and typed refusal
      of inaccessible host paths; implement/document the configured root without path guessing.
- [ ] 6.2 Remove obsolete one-project adapters, bootstrap-project assumptions, completed auth code,
      and dead session fallback; use repository search to account for every remaining `Path.cwd()`
      and project-scoped `ApiKey` reference.
- [ ] 6.3 Update README, CLI/environment/configuration docs, AGENTS.md/CLAUDE.md architecture notes,
      and UI copy for local project workflow and Docker limits.
- [ ] 6.4 Live-verify under `testbed/`: migrate one legacy project, open/create a second, run agents
      concurrently, switch during output, move/repair one directory, observe one SSE stream, and
      confirm no framework-root state appears.
- [ ] 6.5 Run complete CLI, Hub, and UI suites; frontend production build; changed-file Ruff/Black;
      strict OpenSpec validation; and `git diff --check`.
- [ ] 6.6 Sync implemented deltas into current specs, reconcile the umbrella phase-10 notes, and
      archive only after every task and scenario is verified.
- [ ] 6.7 `/handoff`.
