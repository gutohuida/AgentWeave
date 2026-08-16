# Delete a project through the product, not through SQL

## Why

Q1 of the 2026-08-16 autonomous run needed to remove ten stale test projects and found no way to do
it: every `@router.delete` in `hub/hub/api/v1/` handles a runner, a job, an inbound-queue entry, a
chat task-link, an agent-actions job, or a charter — none handles a project, and
`ProjectLifecycleService` has `open_existing`, `create_new`, and `relocate`, no `delete`. Honouring
"remove these test projects" meant stopping the Hub, taking a file-copy backup of `agentweave.db`,
and running a one-shot script that swept 7,788 rows across 26 tables by hand
(`.claude/autonomous/2026-08-16-app-and-test-reform-log.md`, Entry 1). That is not a repeatable
answer, and the operator will reach for "remove this project" again the next time they spin up a
throwaway test project — which this run's own queue does routinely (`Q4b`'s own verify step needs a
throwaway project to delete against).

**The constraint that matters more than the feature:** a project's `working_directory` is the
operator's real working tree — actual source code, on disk, outside anything AgentWeave owns. A
delete that reaches the filesystem is the worst bug this product could ship. This proposal is scoped
so that is structurally true, not merely intended: the delete path never imports anything that opens
a path under `working_directory`, and that absence is what the mutation-checked test in `tasks.md`
proves.

## What Changes

- **`DELETE /api/v1/projects/{project_id}`**, instance-operator authenticated (same dependency as
  `list_projects`/`open_project`, not a per-project agent credential — deleting a project is an
  instance-level decision, not something a bound agent inside that project can request of itself).
- **`ProjectLifecycleService.delete(project_id)`**, alongside its existing `open_existing`,
  `create_new`, `relocate`. Removes every database row scoped to the project via a generic sweep over
  every table that declares a `project_id` column (`design.md` D2) — never an ORM cascade
  relationship, since only 11 of the 27 project-scoped tables have one declared today. Never touches
  `working_directory` on disk (D4), and never deletes the `.agentweave/project.json` marker inside it
  (D5) — both stated explicitly, not left implicit.
- **Refuses while a run is active**, using the exact guard `_guard_relocation` already applies to
  relocation: `Run.status == "running"` for the project (D3). No new concept — the codebase already
  decided that "a run in flight" blocks a structural project mutation. An open conversation does
  **not** block (D3) — it is history, not an in-progress operation.
- **A UI delete control** in the project's Settings environment section
  (`ProjectSettingsPanel.tsx`, which already hosts the relocate control), behind a confirmation that
  requires typing the project's name (D7) — the same friction level Q4b's `detail` field specifies
  for an irreversible action. This is a new pattern for the codebase, not a reuse of an existing one
  — D7 says why a lighter existing pattern (the single-click confirm `delete_runner` uses) is not
  proportionate here.
- **The empty-collection state.** Deleting the operator's last project must leave the app in a
  defined state, not an undefined one. D6 finds no such state exists today, decides what it should
  be, and reuses the rail's existing empty rendering rather than building a new screen.

## Impact

**Behaviour** — a project (and everything scoped to it — agents, runners, charters, conversations,
messages, tasks, runs, spec documents, evidence, event logs, everything Q1's raw sweep enumerated) can
be removed through the product. The workspace directory it pointed at is untouched, always.

**Schema** — none. Every table the delete touches already exists; this proposal adds no column and no
migration. (Confirmed in `design.md` D1: the delete is a data-plane operation over the existing
schema, not a schema change.)

**API** — one new route. No existing route's behaviour changes.

**UI** — one new control, in an existing settings surface, using the existing `Icon`/`Button`
components and the existing `SettingsSection`/`SettingsRow` layout primitives. No new component
system.

## Non-Goals

- **Not soft-delete or an undo window.** The operator asked for delete; recoverability was not
  requested and is not designed here. If wanted later, it is a different, larger feature (a trash
  state, a retention window) and should be proposed on its own.
- **Not deleting or touching the `.agentweave/project.json` marker inside the workspace directory.**
  Decided explicitly in D5, with the reasoning for leaving it alone rather than removing it.
- **Not a bulk-delete or multi-select UI.** One project at a time, matching every other destructive
  control this product has today.
- **Not changing what blocks a *relocation*.** `_guard_relocation`'s existing behaviour is read as
  precedent, not modified.
