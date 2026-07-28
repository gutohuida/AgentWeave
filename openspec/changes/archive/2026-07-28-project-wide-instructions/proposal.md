## Why

Projects using AgentWeave need a way to define rules that apply to every agent — coding conventions, commit policies, branching rules — that vary per project and must be enforced consistently across all roles. Today there is no mechanism for this; rules must be duplicated into each role guide or communicated out-of-band.

## What Changes

- `agentweave init` creates an empty `.agentweave/project_instructions.md` placeholder
- Hub DB gains a `ProjectInstructions` table storing per-project instruction content
- Hub API gains `GET /PUT /api/v1/project/instructions` endpoints
- Hub `_load_role_content` prepends DB instructions before role guide content when returning context to agents (HTTP transport)
- Hub UI gains an "Instructions" screen: markdown textarea, Save button, and a disclaimer that changes take effect on next agent session
- `aw-collab-start` skill reads `.agentweave/project_instructions.md` before the role guide (local transport path)
- Hub is the source of truth when HTTP transport is active; file is source of truth for local transport

## Capabilities

### New Capabilities

- `project-instructions`: Per-project instruction content stored in Hub DB and served prepended to every agent's role guide; editable via Hub UI and readable locally as `.agentweave/project_instructions.md`

### Modified Capabilities

## Impact

- `hub/hub/db/models.py` — new `ProjectInstructions` model
- `hub/hub/db/engine.py` — table creation
- `hub/hub/api/v1/agents.py` — `_load_role_content` prepends instructions; new `/context` response includes prepended content
- New `hub/hub/api/v1/instructions.py` — GET/PUT endpoints
- `hub/hub/main.py` — register new router
- `hub/ui/src/` — new Instructions screen, sidebar nav entry, React Query hook
- `src/agentweave/cli.py` — `agentweave init` creates placeholder file
- `src/agentweave/templates/skills/aw-collab-start.md` — new step to read project instructions file
