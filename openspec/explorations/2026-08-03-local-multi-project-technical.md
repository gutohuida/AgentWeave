# Technical exploration: local multi-project workspace

**Date:** 2026-08-03
**State:** ready for an approval-gated proposal
**Scope:** technical design only; no runtime behavior is implemented by this document

## Executive conclusion

AgentWeave should run one local application instance that owns a collection of directory-backed
projects. A project is a durable database identity bound to one canonical local directory, not an
authentication tenant and not whichever directory the Hub process happens to use as `cwd`.

Bare `agentweave` remains the only entry point. Invoking it from a directory opens or registers that
directory in the already-running instance, selects the resulting project, and opens the same app
window. The UI may also register an existing absolute directory or explicitly create a new one.

The implementation must change the project boundary end to end:

- replace project-scoped browser credentials with one invisible instance-local operator
  credential;
- put the selected project explicitly in operator API routes and every frontend query key;
- resolve runs, worktrees, workspace paths, context files, and future specification files through
  the registered project directory;
- provide one operator SSE stream whose events carry `project_id`;
- populate the existing collection-shaped navigation rail with all projects and their agents; and
- move project-scoped views out of the rail and into project tabs.

This successor is a prerequisite for file-authoritative specifications. It should be proposed and
implemented as one vertical change because partially switching any one of authentication, cache
identity, SSE, or filesystem resolution creates cross-project leaks.

## Current technical shape

### Backend and persistence

- FastAPI, async SQLAlchemy, Alembic, and SQLite/PostgreSQL support are already established.
- `Project` exists and nearly all collaboration records already carry `project_id`.
- `Project` stores hop, delivery, agent, job, and token budget settings, but no directory.
- startup creates one global `proj-default` and one `ApiKey` bound to it.
- every ordinary REST dependency derives project identity from that key.
- run credentials are separately bound to a `Run`, agent, and project through the capability plane;
  that security boundary is correct and remains.

### Runtime and filesystem

The Hub still contains one-project assumptions that are unsafe once a second project exists:

- `agent_trigger.py` uses `Path.cwd()` as `repo_root`;
- workspace path listing and worktree APIs use `Path.cwd()`;
- session-sync worktree cleanup uses `Path.cwd()`;
- agent configuration may fall back to `.agentweave/session.json` under the Hub process directory;
- context materialization is relative to the resulting global/override workspace; and
- operator-supplied `work_dir` can select an unrelated directory for non-writing agents.

Docker mounts only the Hub database volume. It cannot see arbitrary host project directories.

### Frontend

- the rail adapter is deliberately collection-shaped, but `buildRailProjects()` receives exactly
  one project from the authenticated status response;
- the rail already separates project-name navigation from expand/collapse and links agents directly
  to conversations;
- top-level project views remain rail entries instead of project content tabs;
- `configStore` persists one `apiKey` and one `projectId` in session storage;
- most React Query keys omit `projectId`, for example `['tasks']`, `['agents']`, and `['specs']`;
- SSE tickets and streams are project-scoped through the current API key; and
- navigation is in React component state rather than a URL, so selection is not deep-linkable and
  reload can return to a stale/default project.

### Existing product decisions

- the product is local-only; there are no remote users, accounts, organizations, or project roles;
- one local operator principal is distinct from run-bound agent principals;
- future federation must not be made impossible, but no federation behavior is in scope;
- navigation lists live entities (projects and agents), while project views belong in content; and
- the conversation and composer already key durable identity/drafts by project.

## Domain boundaries

| Concern | Owner | Rule |
|---|---|---|
| Instance lifecycle | CLI + local Hub | one process/database serves all registered projects |
| Local operator principal | instance | invisible local credential, not bound to a project |
| Agent principal | run capability plane | remains run-, agent-, and project-bound |
| Project identity/settings | Hub database | stable ID survives rename and directory relocation |
| Project working tree | local filesystem | canonical directory is resolved from the project row |
| Project marker | `.agentweave/project.json` | binds a moved local directory back to stable project ID |
| Navigation selection | browser URL + UI state | project ID is explicit and reload-safe |
| Live updates | instance operator SSE | every event identifies its project |
| Worktree isolation | project workspace service | one worktree namespace beneath each project root |

## Project identity and directory contract

### Stable identity

Generate a project ID (`proj-<stable-random-id>`) independent of name and path. Names need not be
globally unique; the UI disambiguates duplicates with an abbreviated directory. IDs are never
derived from a path because directory rename or relocation must not rewrite every foreign key.

Add these fields to `projects`:

- `working_directory`: canonical absolute path used for access;
- `path_key`: platform-normalized uniqueness key;
- `directory_state`: last observed `available`, `missing`, `not_directory`, `unreadable`, or
  `identity_conflict`;
- `last_opened_at` and `last_seen_at`; and
- optional `archived_at` only if hiding a project is included in the proposal.

`path_key` is derived, never accepted from the client. Resolve an existing directory strictly,
normalize separators and case according to the host, and apply the same algorithm on registration,
lookup, relocation, and migration. On Windows, aliases differing only by case or junction target
must resolve to one registration.

### Portable local marker

Registration writes a bounded marker at `.agentweave/project.json`:

```json
{"version": 1, "project_id": "proj-..."}
```

The marker carries identity only—no secret, path, settings, or database state. It allows an
explicitly reopened moved directory to rebind to its existing database project. AgentWeave already
uses `.agentweave/` for runtime context and worktrees; this adds no new top-level state family.

Opening a directory follows this algorithm:

1. validate and canonicalize the path;
2. if `path_key` already exists, select that project and refresh its observed state;
3. otherwise read a safe marker without following an escaping link;
4. if the marker names an existing project whose old path is unavailable, and no run or worktree
   operation is active, rebind it and record a relocation event;
5. if the marker names an existing project whose old path is still available, report a copied-marker
   conflict and require an explicit “register this copy as new project” action; and
6. otherwise create a project transactionally, seed default runners and starter charters, write the
   marker atomically, and return it selected.

If database creation succeeds but marker writing fails, roll back the database transaction. If an
external failure makes full rollback impossible, return a typed incomplete-registration diagnostic
rather than silently creating an unopenable project.

### Create versus open

- **Open** accepts an existing directory and never creates it.
- **Create** accepts an explicitly named new directory whose parent exists, creates exactly that
  directory, then registers it. It must refuse a non-empty existing target rather than treating the
  request as consent to adopt it.
- neither operation runs agents, initializes git, creates specifications, or modifies source files
  beyond the identity marker and normal `.agentweave` runtime directories.
- project removal and source-directory deletion are non-goals. A later archive/unregister feature
  may hide database state but must never delete the working directory.

### Missing and relocated directories

Missing projects remain in the rail with a clear unavailable state. Their history, tasks, agents,
and conversations stay readable, but filesystem reads, new runs, and scheduled autonomous turns
are refused with a typed `project_workspace_unavailable` result. Operator input may remain queued
only if the UI states that it cannot run until the directory is repaired; the proposal should pick
one consistent behavior and test it.

Relocation is blocked while the project has a running process or a mutating worktree operation.
Existing agent worktrees under the old root must be released or reported for manual recovery before
rebinding. Agent branches are never deleted merely because the root moved.

## Project workspace service

Introduce one backend service used by every filesystem consumer:

```text
resolve_project_workspace(project_id) -> ProjectWorkspace
ProjectWorkspace.root                # canonical project directory
ProjectWorkspace.resolve(relative)   # contained, symlink-safe resolution
ProjectWorkspace.agent_root(agent)   # primary root or isolated worktree
```

It loads the project row, revalidates availability/marker identity at use time, and fails closed.
No project-aware route may call `Path.cwd()`.

Migrate these consumers together:

- direct agent trigger and queued-turn execution;
- worktree creation, listing, conflict detection, and release;
- composer workspace path listing;
- runtime context materialization;
- future specification indexing/watching;
- project instructions or other filesystem-backed artifacts; and
- any diagnostics that inspect git or repository state.

Remove arbitrary absolute `work_dir` selection. If subdirectory execution remains useful, represent
it as a validated repository-relative path resolved through `ProjectWorkspace.resolve()`. Writing
agents continue to use their isolated worktree root.

Replace the `ProjectSession`/filesystem fallback in agent context with Hub-owned project, agent,
runner, charter, instructions, and quality records. At minimum this successor must remove the
global `.agentweave/session.json` fallback so one directory can never populate another project's
roster. Any still-needed legacy session data must be explicitly project-bound and migration-only.

## Local operator boundary and API shape

### Invisible instance credential

The browser still needs protection from cross-origin and DNS-rebinding requests even though the
operator performs no login. Convert the generated `aw_live_*` bootstrap secret from a project key
to an instance-local operator credential:

- it is created once in the Hub data directory and returned only by the existing loopback-, Host-,
  and Origin-guarded setup endpoint;
- the browser obtains it automatically and never asks the operator to choose/paste a project key;
- it authorizes the local operator to list and select all projects; and
- it does not supply project identity.

Use a new `OperatorKey`/instance-credential table or an equally explicit model. Do not make
`ApiKey.project_id` nullable and overload null with “administrator”; that obscures the security
contract. Migrate the existing bootstrap secret into the operator credential, then retire
project-scoped operator API keys. Run capability tokens remain unchanged.

The setup endpoint returns instance metadata only. Project selection comes from `/projects`, not
from whichever project happened to own the first key.

### Explicit operator routes

Use an instance collection plus project-scoped resource paths:

```text
GET    /api/v1/projects
POST   /api/v1/projects/open
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
POST   /api/v1/projects/{project_id}/relocate
GET    /api/v1/projects/{project_id}/agents
GET    /api/v1/projects/{project_id}/tasks
...
```

One dependency authenticates the local operator; a second resolves and authorizes the explicit
project resource. Existing agent action routes stay separate and infer project solely from the run
credential. Never allow an agent request to choose `project_id`.

Project summaries should include name, path display, directory state, last opened time, budget
settings, aggregate live state, and agents with color/status. This lets the rail render one
collection without an N-project fan-out.

### Settings

The project settings API owns:

- name;
- hop budget;
- per-turn delivery cap;
- agent budget;
- token budget; and
- whether agents may manage scheduled jobs.

Validate all settings in one schema and reuse the existing scheduling/budget services. Directory
relocation is a distinct action with stronger preconditions, not a generic PATCH field.

## CLI lifecycle

Bare `agentweave` captures its invocation directory before doing anything else.

### Instance already running

1. read the invisible operator credential from the Hub data directory;
2. call the loopback `projects/open` endpoint with the invocation directory;
3. receive the stable project ID and selection URL; and
4. open/focus the app at `/?project=<id>`.

### Starting a new instance

1. scaffold instance database/credential and run migrations;
2. start the Hub without assuming a bootstrap project;
3. wait for health;
4. call the same `projects/open` endpoint; and
5. open the returned project URL.

This single post-health path avoids a special `AW_LAUNCH_DIRECTORY` environment contract and works
identically whether the process was already running. Foreground mode performs registration from its
startup helper before opening the window.

Direct `agentweave-hub` startup is allowed to have zero projects and shows the add/open-project
empty state. It must never register the package directory or `Path.cwd()` implicitly.

`agentweave status` reports the instance plus registered-project count and last-opened project by
querying the local API. `stop` and confirmed `reset` remain instance-wide. Reset deletes Hub state,
not project directories or source content; leftover non-secret markers may be adopted on reopen.

## Migration from `proj-default`

The migration adds nullable directory fields first. On the first subsequent bare invocation:

- if there is exactly one unbound legacy project, bind that existing row to the invocation
  directory and preserve every related record;
- if the directory already has a marker for that project, accept it idempotently;
- if the Hub was started directly and no invocation directory is supplied, leave the project
  unbound and show a “Locate project directory” repair action; and
- never bind the legacy project to the installed package, Hub data directory, or process `cwd`.

Default runners and starter charters are seeded per newly created project using the existing seed
helpers. Existing projects are not reseeded beyond their current idempotent marker flags.

The old project-scoped API key becomes the instance operator key without changing its value, so an
open browser session can reconcile automatically. Frontend bootstrap clears the old stored project
binding after fetching the project collection.

## SSE and cache isolation

### One operator event stream

Create one instance-level operator SSE ticket and stream. Every event envelope includes
`project_id`; instance lifecycle events such as `project_created`, `project_updated`,
`project_relocated`, and `project_state_changed` do as well.

The SSE manager may continue maintaining project channels for agent/internal consumers, but every
project broadcast also fans out to authenticated operator subscribers with the project ID stamped
by the server. Event payloads must not trust a caller-supplied project field.

One stream is preferable to reconnecting on selection because the rail shows live state for all
projects and inactive projects may change through scheduled jobs or running agents.

### Query keys

Every project-scoped React Query key starts with project identity, for example:

```text
['project', projectId, 'tasks']
['project', projectId, 'agents']
['project', projectId, 'agent', agent, 'conversation', conversationId]
['project', projectId, 'specs']
```

The project collection uses `['projects']`. SSE invalidation uses the envelope's project ID, so an
event from project A cannot refresh or overwrite project B's cache. Reconnect still invalidates all
queries once to reconcile missed events.

Mutations capture their project ID in arguments rather than reading a mutable global selection at
completion time. This avoids the project equivalent of the stale-closure chat bug.

## Navigation and project workspace UI

### URL-backed destination

Keep the small existing navigation model; a new routing dependency is unnecessary. Serialize the
destination into URL search parameters and synchronize with `history.pushState`/`popstate`:

```text
/?project=<id>&view=overview
/?project=<id>&view=tasks
/?project=<id>&agent=<name>&conversation=<id>
```

Provider session IDs never appear. Invalid/missing project IDs fall back to the last opened
available project, then the first available project, then the empty state. Selection updates
`last_opened_at` and persists as a preference, not as authentication.

### Rail

Feed the rail directly from the project-summary collection. It lists only projects and their agents
with live state. Project name navigates; expander only toggles. Collapsed state is persisted by
stable project ID. Duplicate names show a subdued directory hint.

Add/open controls belong at the project collection level. They must clearly distinguish “open
existing directory” from “create new directory” and preview the exact absolute path before the
backend writes anything.

### Project content tabs

The project destination owns tabs for at least:

- Overview;
- Tasks;
- Spec;
- Jobs;
- Activity; and
- Environment.

Environment groups runners, charters, project instructions, worktrees/conflicts, diagnostics, and
budget/settings surfaces without adding rail destinations. Questions, logs, and quality should be
placed deliberately in Overview/Activity/Environment during proposal review rather than kept as
top-level exceptions. Adding a future project view changes the tab model only, not the rail.

Agent conversations continue occupying the full content area and retain the one-action return to
their containing project. Project/agent/conversation drafts are already isolated correctly.

### Agent identity color

Use the existing project-stable `Agent.color_index` and shared color helper in:

- rail agents;
- conversation timeline entries;
- task assignee displays and selectors; and
- activity actors/filters.

Name text always accompanies color. Because agent names are unique only within a project, every
lookup takes `(project_id, agent_name)`.

## Runtime concurrency and failure handling

- runs from different projects may execute concurrently because scheduler locks already key by
  `(project_id, agent)`; verify this explicitly;
- a project missing its directory pauses scheduled/autonomous turns with an attributed event,
  without disabling jobs in the database;
- queue entries survive temporary unavailability and resume only after explicit/open-time workspace
  repair;
- shutting down the instance terminates active runs across every project, as today;
- worktree branch names may repeat across projects because git repositories are distinct;
- context files are materialized inside the effective project/agent workspace and cleaned without
  touching another project; and
- all error messages return stable project ID plus a safe display path, never secrets.

## Docker boundary

Arbitrary host-directory projects cannot work in the current container: only the database volume is
mounted. The proposal must state this rather than pretending parity.

Recommended scope:

- native local mode is the supported directory-backed product path;
- explicit Docker mode remains usable only for project roots mounted beneath one configured
  container workspace root;
- Docker registration rejects host paths it cannot access and reports the required mount; and
- no Docker socket mounting, host-path translation heuristics, or remote filesystem protocol is
  introduced.

If product review prefers to retire Docker app mode entirely, do so as a separate explicit breaking
decision; do not silently break it inside this change.

## Security

- retain loopback binding by default and the existing Host/Origin DNS-rebinding checks;
- scope the instance credential to local operator APIs and never inject it into agent processes;
- continue injecting only short-lived run credentials into agents;
- canonicalize paths server-side and reject NUL/control characters, non-directories, inaccessible
  roots, broad filesystem roots, Hub data directory, and nesting inside another registered
  project's `.agentweave/worktrees`;
- use atomic marker writes and refuse symlink escapes;
- do not expose arbitrary file reads through project registration or path APIs;
- require typed confirmation for creating a directory and relocating/replacing identity; and
- record project creation, relocation, settings changes, and identity-conflict resolution in the
  event log.

The local operator boundary is intentionally not a multi-user authorization model. Future
federation can add an authorization layer above explicit project resource IDs; it does not require
changing project identity or filesystem resolution.

## Implementation sequence

### Phase 1: persistence and workspace service

- add directory/lifecycle columns and operator credential storage;
- implement canonicalization, marker, open/create/relocate services;
- add project CRUD/settings schemas and migrations;
- seed new projects transactionally; and
- cover legacy `proj-default` binding.

No runtime consumer switches until the service and migration fixtures pass.

### Phase 2: operator API and CLI lifecycle

- add instance project collection and explicit project routes;
- migrate browser authentication to the invisible operator credential;
- update bare CLI invocation for the uniform post-health open flow;
- support zero-project startup and status; and
- retain run-token agent APIs unchanged.

### Phase 3: runtime filesystem isolation

- replace every Hub `Path.cwd()` project assumption;
- migrate run spawn, context, workspace paths, worktrees, release/conflict checks, and diagnostics;
- remove/contain arbitrary `work_dir`;
- remove global session-file roster fallback; and
- test concurrent runs in two real repositories.

### Phase 4: SSE and frontend data identity

- add instance operator SSE with server-stamped project envelopes;
- make every query/mutation key project-scoped;
- implement project collection hooks and switching reconciliation; and
- add URL-backed destinations and reload/back-forward behavior.

### Phase 5: rail, tabs, settings, and identity color

- populate the collection rail and project management controls;
- move project views into content tabs;
- build unavailable/relocation/settings states;
- apply agent color to tasks and activity; and
- complete responsive, keyboard, and reduced-motion checks.

### Phase 6: cleanup and live verification

- remove obsolete project-scoped operator-key code and one-project adapters;
- reconcile affected specs and documentation;
- run full suites/build/strict validation; and
- live-verify two projects plus migration and missing-directory recovery from `testbed/`.

## Testing strategy

| Area | Automated tests | Live verification |
|---|---|---|
| Path identity | Windows/POSIX normalization, case, symlink/junction, duplicate, root rejection | open same directory through aliases |
| Marker lifecycle | atomic write, moved directory, copied marker, rollback failure | move one throwaway project and reopen it |
| Migration | legacy DB/key fixtures, unbound startup, idempotent bind, preserved foreign rows | upgrade a copied pre-change database |
| Project API | collection/create/open/settings/relocate, operator vs run auth | invoke bare CLI from two directories |
| Runtime isolation | two repo roots, context/worktrees/path search, queued/scheduled turns | run different agents concurrently in both |
| Cache isolation | all query keys include project, mutation switch races, draft preservation | switch rapidly while requests complete |
| SSE | events stamped by server, inactive-project rail updates, reconnect reconciliation | keep both projects active and observe one stream |
| Navigation | URL reload/back/forward, invalid IDs, collection rail, tab reachability | app-window navigation at narrow/wide widths |
| Identity color | rail/conversation/task/activity exact mapping with name text | compare the same agent across all surfaces |
| Docker | mounted-root success and inaccessible-host-path typed failure | explicit container smoke test if retained |

Focused tests should run phase by phase. Before archive run the full CLI, Hub, and frontend suites,
frontend production build, changed-file Ruff/Black checks, strict OpenSpec validation, and
`git diff --check`.

Live tests must use directories beneath `testbed/` and clean them afterwards. They must never run
`agentweave` at this framework repository root or leave root `.agentweave/`, `agentweave.yml`, or
`spec/` state.

## Evidence and coverage limits

This exploration is based on current source inspection of project models/bootstrap, auth/setup,
SSE, direct triggers, session fallback, worktrees, workspace paths, scheduler behavior, frontend
configuration/navigation/query keys, Docker packaging, and the authoritative OpenSpec requirements.

It does not prove:

- the exact cross-platform canonical path algorithm on every filesystem;
- whether current Docker support should remain a product promise;
- the final information architecture for Questions/Logs/Quality within project tabs; or
- whether browsers should receive a bearer secret or a same-site HttpOnly session derived from it.

Those are proposal decisions or implementation experiments, identified below rather than assumed.

## Decisions rejected

- **One API key per project and switch keys in the browser:** rejected because projects are local
  directories, not tenants; it makes collection listing and one live rail needlessly complex.
- **A mutable global `current_project` backend setting:** rejected because concurrent tabs, jobs, and
  agent runs would race. Project identity must travel with every resource/request.
- **Keep unscoped React Query keys and clear the cache on switch:** rejected because in-flight
  responses can repopulate the wrong project and inactive-project state cannot remain live.
- **One SSE connection per project:** rejected because the rail needs all projects and connection
  count grows unnecessarily.
- **Continue using Hub process `cwd`:** rejected because it cannot represent more than one project
  and can target the installed package or Hub data directory.
- **Derive project ID from a path hash:** rejected because relocation would change identity.
- **Guess relocation from git remote/name:** rejected because repositories can share remotes and
  non-git projects are valid.
- **Automatically adopt a copied identity marker:** rejected because two directories would claim one
  mutable project identity.
- **Let the browser choose arbitrary files after registration:** rejected because registration is
  not a general filesystem-read capability.
- **Hide project-scoped pages under both rail entries and tabs during migration:** rejected because
  two navigation models prolong ambiguity; migrate them in one UI phase.

## Open questions for proposal review

- [ ] Choose the local browser credential presentation: keep the automatically discovered bearer
      credential, or exchange it once for a SameSite HttpOnly operator session. Both preserve the
      instance-local operator model; the latter reduces JavaScript secret exposure but adds CSRF
      mechanics and test migration.
- [ ] Decide whether operator input queues while a project directory is missing or is refused until
      repair. Autonomous and scheduled turns must pause either way.
- [ ] Place Questions, Logs, and Quality within Overview, Activity, or Environment so no
      project-scoped rail exceptions remain.
- [ ] Confirm Docker's supported mounted-root contract or explicitly defer/retire Docker app-mode
      parity.
- [ ] Decide whether project archive/hide belongs in this proposal. Permanent deletion of project
      records or working directories does not.

The project-directory, explicit-route, cache-key, runtime-isolation, and single-operator-stream
decisions are resolved and should not be reopened by the proposal.

## Ready for proposal

Create one `local-multi-project-workspace` change. Its requirements should cover:

1. stable directory-backed project identity and safe create/open/relocate behavior;
2. collection/settings APIs under an instance-local operator principal;
3. project-correct runtime/worktree/filesystem resolution;
4. server-stamped multi-project live events and cache isolation;
5. collection navigation plus project content tabs; and
6. migration, unavailable-directory recovery, and agent-color consistency.

The proposal must resolve the five review questions above before approval. Only after this change
lands should the first file-authoritative specification child be proposed.
