## Why

`openspec/changes/single-runtime` deleted every CLI command that wrote to `.agentweave/roles.json`
(`agentweave roles add/set/available`, `src/agentweave/cli.py`'s `cmd_roles_*` family). The
role-*assignment* mechanism `src/agentweave/roles.py` operates on — `load_roles_config`,
`add_role_to_agent`, `set_agent_roles`, all keyed to that file — now has zero surviving writer
anywhere in the product. An operator has no way left to give an agent a role. Role *content* still
renders (`hub/hub/api/v1/agents.py::_load_role_content` falls back to Hub-bundled templates at
`hub/data/roles/*.md` when the now-dead `.agentweave/roles/{role}.md` tier is absent), but which
roles exist is a fixed list of ~21 hardcoded personas (`get_available_roles()`'s fallback list in
`src/agentweave/roles.py`) that mixes three concerns an operator cannot independently vary: what an
agent is allowed to run (a CLI on PATH), what shared identity it presents in the roster, and what
behavior guide it follows.

Separately, `openspec/specs/agent-tool-surface/spec.md`'s "The Hub supplies state; the tool surface
carries intent" requirement already promises every agent "its charter" at turn start — that
requirement shipped with `agent-capability-plane`. No "charter" concept exists anywhere in the
codebase (`grep -ri charter --include=*.py` returns nothing); the spec is already ahead of the
implementation it describes.

CLAUDE.md and AGENTS.md both flag the multi-role system as "slated for replacement by
runner/agent/charter separation" and warn against building new role-system work before it lands.
This is the last item on the Hub-native-experience slice table's "ready to propose" list from
`openspec/changes/archive/2026-08-02-agent-conversation-workspace/design.md` (row: "Runner / agent /
charter separation — Reusable execution capability vs. addressable identity vs. behaviour").

## What Changes

- Introduce three separated concepts, replacing the single overloaded "role":
  - **Runner**: reusable execution capability — which CLI to spawn (`claude`, `codex`), with what
    flags. Already exists informally as `RUNNER_TYPES`/`RUNNER_CONFIGS` in
    `src/agentweave/constants.py` and `hub/hub/runner_commands.py`/`launchability.py`; this change
    gives it a first-class, Hub-DB-backed identity instead of a hardcoded Python dict.
  - **Agent**: addressable identity in the roster (name, color, contact mode) — the existing `Agent`
    Hub DB model (`hub/hub/db/models.py`), decoupled from any fixed behavior.
  - **Charter**: authored behavior — the instructions an agent follows, replacing the fixed 21-entry
    role-guide list with operator-authored content, stored in the Hub DB and editable through a Hub
    UI (mirroring how `project-instructions` already moved from file to DB-backed Hub UI editor).
- A charter authoring UI in the Hub: create/edit/assign charters to agents, replacing
  `agentweave roles add/set/available` entirely (that surface stays deleted, per single-runtime — no
  CLI command is reintroduced).
- `GET /api/v1/agents/context` (and the sibling `/agent-context` runtime path) serves the assigned
  charter content instead of `_load_role_content`'s three-tier role-file lookup. The Hub-bundled
  `hub/data/roles/*.md` templates seed the initial charter set on first run rather than being a
  runtime fallback tier.
- **BREAKING**: `src/agentweave/roles.py`, `VALID_ROLE_IDS`/`RUNNER_ROLE_*` constants tied to the
  fixed role list in `src/agentweave/constants.py`, `templates/roles/*.md`, and `.agentweave/roles/`,
  `.agentweave/roles.json` as file formats are removed. No migration path from the old file format —
  consistent with single-runtime's "no external install base to protect" stance (nothing currently
  writes `.agentweave/roles.json` for there to be data to migrate).
- Agent creation/configuration (currently `agent.config` freeform JSON on the Hub `Agent` row) gains
  explicit `runner_id` and `charter_id` associations instead of implicit dict keys.

## Capabilities

### New Capabilities
- `runner-registry`: Hub-DB-backed definitions of reusable execution capability (CLI, flags, model
  parameters) that an agent can be bound to, replacing the hardcoded `RUNNER_CONFIGS` dict as the
  sole source of truth for what a runner is.
- `agent-charter`: authored behavior content assignable to agents, with a Hub UI for
  create/edit/assign, replacing the fixed role-guide list and its dead `.agentweave/roles.json`
  assignment mechanism.

### Modified Capabilities
- `agent-context-onboarding`: the "Layered project and role context" requirement's "Role files remain
  stable contracts" scenario is re-scoped from role-guide files to charter content, and "Role context
  lookup compatibility" is re-scoped from a fixed role-ID lookup to a charter-ID lookup. The
  underlying layering behavior (stable guidance + generated facts + project instructions + live
  session state) is preserved — only the source and identifier space of the "stable guidance" layer
  changes.

`agent-tool-surface`'s "Hub supplies state; the tool surface carries intent" requirement already
promises an agent "its charter" and needs no textual change — this change makes that promise real by
giving `agent-charter` a backing implementation; no requirement wording changes as a result.

## Impact

- **Removed**: `src/agentweave/roles.py` (432 lines), `templates/roles/*.md` (21 guide files),
  `.agentweave/roles.json`/`.agentweave/roles/` file formats, `VALID_ROLE_IDS` and role-list constants
  in `src/agentweave/constants.py`.
- **Changed**: `hub/hub/api/v1/agents.py` (`_load_role_content`, `_render_hub_agent_context`, the
  `/context` and `/agent-context` routes), `hub/hub/db/models.py` (`Agent` model gains
  `runner_id`/`charter_id`, or a new `Charter`/`Runner` table), `src/agentweave/context_builder.py`
  (currently reads `.agentweave/roles.json` and `ROLES_DIR` — becomes dead code or a thin Hub-API
  client), `src/agentweave/session.py` (role-assignment sync at agent-add time).
- **New Hub UI**: a charter authoring screen, likely alongside the existing Instructions screen
  (`hub/ui/src/components/layout/` project-instructions pattern).
- **Docs**: `AGENTS.md`/`CLAUDE.md`'s multi-role deprecation note is resolved, not just flagged.
