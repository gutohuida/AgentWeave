## Context

The detailed source audit and decision record is
`openspec/explorations/2026-08-03-local-multi-project-technical.md`. This design carries its resolved
architecture forward.

Almost every durable collaboration table already has `project_id`, and `turn_scheduler.py` keys
active scheduling by project and agent. The missing boundary is above and below those records:
operator auth selects one project implicitly, while filesystem operations select one process
directory implicitly. The frontend mirrors that split with a collection-shaped rail but globally
named cache keys.

The change must land vertically. Adding only project CRUD would expose multiple rows while runs
still share `Path.cwd()`. Adding only UI switching would permit stale responses to populate the
wrong project. Adding only directory fields would leave auth and SSE unable to reach the collection.

## Goals / Non-Goals

### Goals

- One local instance opens any number of registered directory-backed projects.
- Stable project identity survives rename and explicit directory relocation.
- Every operator request, query cache entry, live event, and filesystem access has explicit project
  identity.
- Agents retain the existing run-bound least-privilege capability plane.
- Bare invocation remains the only normal entry point and gains no registration ceremony.
- Missing/moved directories fail safely without losing collaboration history.
- The rail contains live entities only; all project views are reachable inside project content.

### Non-Goals

- Multi-user authorization, remote filesystems, federation, or cross-machine reconciliation.
- Source-directory deletion or implicit file/project creation beyond an explicitly requested new
  directory and the identity marker.
- Project archive/unregister.
- Specification-program implementation.
- A new frontend routing framework.

## Decisions

### 1. Project ID is durable; canonical path is a unique binding

`Project.id` remains the foreign-key identity. Add canonical `working_directory`, derived
`path_key`, observation state, and last-open/last-seen timestamps. Names may repeat.

Canonicalization resolves the existing directory strictly, applies host case/separator rules, and
rejects filesystem roots, the Hub data directory, and nested AgentWeave worktree directories.
`path_key` has a unique constraint. It is never client-supplied.

A versioned `.agentweave/project.json` marker contains only `project_id`. On open, path match wins;
otherwise an existing marker can rebind a project only when the old path is unavailable and no run
or worktree mutation is active. A live old path plus the same marker is a copied-marker conflict;
registering the copy as new requires explicit confirmation and replaces the copy's marker.

Rejected: path hashes as IDs. A move would rewrite identity and every link.

### 2. Open and create are separate, bounded operations

Open accepts an existing directory and creates only the marker/runtime metadata needed for
registration. Create accepts a nonexistent child of an existing directory, creates exactly that
directory, then registers it. It refuses an existing non-empty target.

Registration, default-runner seeding, starter-charter seeding, and marker creation are one logical
transaction. Marker failure rolls back the new project; partial rollback returns a typed repair
diagnostic.

There is no delete endpoint. Instance reset leaves source directories and their non-secret markers
untouched.

### 3. One project workspace service owns filesystem resolution

All consumers call `resolve_project_workspace(project_id)`. The returned service revalidates the
directory/marker and resolves contained relative paths without following an escape. It provides the
primary repository root and the effective isolated agent worktree root.

Direct trigger, queued execution, context materialization, workspace path search, worktree APIs,
session cleanup, git diagnostics, and later spec indexing migrate together. No project-aware code
uses `Path.cwd()`.

Absolute `work_dir` is removed. If subdirectory execution is retained, the API accepts a
repository-relative path and resolves it through the workspace service. Writing agents still run in
their isolated worktree.

### 4. Unavailable projects preserve state but start no new work

A missing/unreadable/conflicting directory remains listable. History, tasks, and conversations are
readable. New operator input is refused with `project_workspace_unavailable`; autonomous and
scheduled starts pause, emit an attributed diagnostic, and leave queued entries/jobs durable.

After an explicit successful open/relocate repair, scheduling re-evaluates queued autonomous work.
No job is silently disabled and no entry is withdrawn.

### 5. Local operator credential is instance-scoped; agent credentials are unchanged

Create an explicit instance/operator credential model. Migrate the existing bootstrap `aw_live_*`
value into it so browser sessions reconcile without user action. The guarded `/setup/token` path
continues to expose it only to the local app. It authorizes project collection and operator routes
but conveys no project identity.

Operator resources live below `/api/v1/projects/{project_id}/...`; collection/open/create live at
`/api/v1/projects`. A dependency authenticates the operator, then a project resolver validates the
path ID. Agent action routes continue deriving project and actor from the short-lived run token and
never accept caller-selected project identity.

Rejected: nullable `ApiKey.project_id` meaning administrator. A separate model makes the boundary
testable and avoids an overloaded null privilege.

### 6. Bare invocation always opens its invocation directory after health

The CLI captures the original directory. Whether the instance was already running or was just
started, it reads the local operator credential and calls the same open-existing endpoint after a
health check. It opens `/?project=<id>&view=overview`.

Startup no longer bootstraps `proj-default` unconditionally. Direct `agentweave-hub` may start with
zero projects. For migration only, the first open binds the single unbound legacy project rather
than creating another, preserving all foreign rows.

This avoids a persistent `AW_LAUNCH_DIRECTORY` environment variable and prevents the installed
package/process directory from becoming a project accidentally.

### 7. One operator SSE stream carries server-stamped project identity

The operator obtains an instance-level short-lived SSE ticket. Each event envelope has
`project_id`; the server stamps it from the broadcast channel, never payload input. Project
collection events use the affected project ID.

Internal/agent project channels may remain, but each broadcast also fans out to operator
subscribers. One stream keeps inactive-project rail state live and avoids reconnecting on every
selection.

### 8. Every frontend server-state identity begins with project ID

Project queries use `['project', projectId, resource, ...]`; the collection uses `['projects']`.
SSE invalidates using its envelope project ID. Mutations receive project ID as an immutable
argument, so switching while a request is in flight cannot redirect its response or invalidation.

On upgrade, clear or ignore old unscoped query state. Composer drafts already use project identity
and are preserved.

### 9. URL parameters are the navigation source

Use the existing `WorkspaceDestination` model with `history.pushState`/`popstate`; do not add a
routing dependency. Project, view, agent, and AgentWeave conversation ID serialize in search
parameters. Provider session IDs remain absent.

Invalid destinations fall back to the last-opened available project, then the first available
project, then the zero-project state. A project switch is navigation, not authentication.

### 10. The rail is a collection; project views are tabs

`GET /projects` returns summaries with directory/live state and agents, so the rail needs no
per-project fan-out. It renders only projects and agents. Open/create controls operate on the
collection.

Project content provides Overview, Tasks, Spec, Jobs, Activity, and Environment. Overview includes
unanswered Questions; Activity includes Logs; Environment contains Quality, Instructions, Runners,
Charters, worktrees/conflicts, diagnostics, budgets, and settings. Existing page components are
recomposed rather than reimplemented.

Agent color uses the existing `(project_id, Agent.color_index)` identity in rail, conversation,
task assignee, and activity, always alongside text.

### 11. Docker requires an explicit mounted workspace root

Native local mode is primary. Docker accepts registrations only beneath a configured container
workspace root mapped from a host root. Inaccessible host paths return a typed mount diagnostic.
No Docker-socket access or host/container path guessing is introduced.

## Data and API Migration

1. Add nullable project path/state fields and the instance credential table.
2. Copy the surviving bootstrap credential value into the instance table without changing it.
3. Allow zero projects on a fresh database; keep an existing `proj-default` unbound until first
   explicit open/locate.
4. Bind that single legacy project transactionally on first open and preserve all rows.
5. Introduce explicit operator project routes and migrate UI/CLI consumers.
6. Remove project-scoped operator-key lookup after all operator routes have moved; run tokens stay.
7. Remove global session-file fallback and obsolete one-project frontend adapter/state.

No destructive downgrade is promised after multiple projects exist. Rollback is normal git revert
plus database backup restoration; source directories are unaffected.

## Risks / Trade-offs

- **Large route migration:** nearly every operator API is project-scoped. Mitigate with one router
  dependency contract and route-parity tests before UI migration.
- **Path canonicalization differs by platform:** use table-driven unit tests plus Windows junction
  and POSIX symlink live checks; never accept client normalization.
- **Copied `.agentweave` directories:** fail visibly and require explicit new identity rather than
  merging histories.
- **In-flight frontend races:** project-prefixed keys and immutable mutation arguments prevent
  cross-project writes; add delayed-response switch tests.
- **Dormant autonomous work after repair:** one repair hook rechecks all queued agents in the
  project, respecting budgets and hop limits.
- **Docker expectations:** document mounted-root limits and test both success and typed failure.
- **Legacy session concepts remain in code:** remove only the global filesystem fallback in this
  change; any wider dead `ProjectSession` cleanup must be separately evidenced or made an explicit
  task, not assumed.

## Open Questions

None. The exploration's five product choices are resolved in `proposal.md`. Any implementation
discovery that changes these contracts requires a proposal/design revision and renewed approval.
