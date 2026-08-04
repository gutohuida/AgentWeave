## Why

AgentWeave's database is already project-scoped, and the conversation rail was deliberately shaped
as a project collection, but the running product can still represent only one usable project.
`hub/hub/db/models.py::Project` has no working directory; `hub/hub/db/engine.py` bootstraps one
global `proj-default`; browser authentication derives that project from one `ApiKey`; and runtime
filesystem consumers in `agent_trigger.py`, `workspace.py`, `worktrees.py`, and `session_sync.py`
use the Hub process's `Path.cwd()`.

This is now a correctness blocker, not only a missing feature. The planned file-authoritative
specification program needs a trustworthy project directory, and a second project under the current
runtime would read, run, and create worktrees in the first process directory. Frontend query keys
such as `['tasks']`, `['agents']`, and `['specs']` also lack project identity, so switching without a
full boundary migration would leak cached state across projects.

The local-only product decision resolves the former multi-tenant question: there is one local
operator, projects are directories, and run-bound agent identity remains the security boundary for
agent actions.

## What Changes

- Give every project a stable database identity bound to one canonical absolute local directory,
  with a non-secret `.agentweave/project.json` marker for explicit relocation recovery.
- Add project collection, open-existing, create-new, settings, and relocation APIs. Missing
  directories remain visible and repairable; project/source deletion is not introduced.
- Convert the automatically discovered bootstrap secret into an instance-local operator credential
  that can access the project collection. Project identity moves into explicit operator resource
  paths; run-token agent APIs remain project-bound and unchanged.
- Make bare `agentweave` register/open its invocation directory through the already-running local
  instance (or through the same post-health path after starting one), then open that project's URL.
- Route every runtime filesystem operation through a project workspace resolver. Remove Hub
  `Path.cwd()` project assumptions, the global `.agentweave/session.json` roster fallback, and
  arbitrary absolute `work_dir` escape.
- Provide one instance-level operator SSE stream whose server-stamped envelope includes
  `project_id`. Prefix every project-scoped frontend query key with that identity.
- Populate the existing rail adapter with all projects and their live agents. Move project-scoped
  destinations into Overview, Tasks, Spec, Jobs, Activity, and Environment tabs in the content
  area; apply the existing agent identity color consistently to tasks and activity.
- Migrate the legacy `proj-default` and its API key without deleting any related records. An
  unbound legacy project is bound only through an explicit bare invocation or locate action, never
  to the Hub process directory.

## Resolved Product Choices

- Keep the invisible, automatically discovered bearer credential for the local operator in this
  change. It already has loopback, Host, and Origin protection; HttpOnly session/CSRF migration adds
  no multi-project value and is deferred.
- Refuse new operator input while a project's directory is unavailable. Existing queued entries
  remain durable; scheduled/autonomous work pauses and resumes after repair.
- Place unanswered Questions on Overview, Logs in Activity, and Quality, Instructions, Runners,
  Charters, worktrees, diagnostics, and settings in Environment.
- Retain explicit Docker mode only for directories visible beneath one configured mounted workspace
  root. Native mode remains the primary product path.
- Defer project archive/unregister and all permanent deletion. Confirmed instance `reset` remains
  the only destructive database lifecycle action and never deletes source directories.

## Non-Goals

- Remote access, user accounts, organizations, permissions, sharing, or federation.
- A second Hub/runtime per project.
- Deleting, moving, cloning, initializing git in, or otherwise managing project source directories.
- Automatically adopting copied project markers.
- Restoring removed collaboration CLI commands or project-specific API-key ceremony.
- Implementing specification identity, evidence, authoring, or gates; this change supplies their
  directory prerequisite only.
- Retiring Docker or the Hub name.

## Capabilities

### New Capabilities

- `local-project-workspace`: stable directory-backed project identity, collection/lifecycle APIs,
  instance-local operator access, project-correct runtime paths, multi-project SSE/cache isolation,
  and project workspace navigation.

### Modified Capabilities

- `app-lifecycle`: bare invocation opens/registers its current directory in the single local
  instance; status reports the instance's project collection rather than one bootstrap label.
- `agent-conversation-workspace`: navigation's collection contains every registered project and
  may offer create/open/switch behavior; project/conversation destinations are URL-backed.

## Impact

- **Backend:** `Project`/credential migrations, project/workspace services, project routes, auth
  dependencies, SSE manager/envelopes, run/worktree/workspace/session consumers, startup and
  scheduler unavailable-workspace behavior.
- **CLI:** native startup/scaffold/open/status paths; no new collaboration subcommand.
- **Frontend:** configuration/bootstrap, API routes, every project-scoped query/mutation key, SSE,
  navigation state, rail collection, project tabs, settings, tasks, and activity.
- **Packaging:** optional configured Docker workspace-root mount; no new service or secret.
- **Docs/specs:** app lifecycle, project workflow, navigation, environment variables, and Docker
  limitations.
