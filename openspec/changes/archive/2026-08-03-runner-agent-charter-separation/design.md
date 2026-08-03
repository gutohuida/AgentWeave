## Context

Today "role" conflates three things behind one word and one file format:

1. **What an agent is allowed to run** — informally captured in `src/agentweave/constants.py`'s
   `RUNNER_TYPES`/`RUNNER_CONFIGS` (now just `claude` and `codex`, after single-runtime dropped
   OpenCode/Kimi/Copilot) and consumed by `hub/hub/runner_commands.py`/`launchability.py`.
2. **Which identity appears in the roster** — the Hub `Agent` row (`hub/hub/db/models.py:59`): name,
   color, contact mode, self-registration state, plus a freeform `config` JSON blob that runner
   settings and (formerly) role assignment leaked into.
3. **What behavior an agent follows** — a fixed list of ~21 hardcoded personas
   (`get_available_roles()`'s fallback in `src/agentweave/roles.py`), assigned via
   `.agentweave/roles.json`, a file format whose only writer (`agentweave roles add/set`) was
   deleted by `openspec/changes/archive/2026-08-03-single-runtime`. Content still renders — Hub's
   `_load_role_content` (`hub/hub/api/v1/agents.py:622`) falls back to bundled templates at
   `hub/data/roles/*.md` when the (now-dead) `.agentweave/roles/{role}.md` tier is absent — but
   *assignment* is inert: nothing populates `.agentweave/roles.json` in the single-runtime product.

Meanwhile `openspec/specs/agent-tool-surface/spec.md`'s "The Hub supplies state; the tool surface
carries intent" requirement already promises an agent "its charter" at turn start. That word exists
in a shipped spec and nowhere in the implementation.

## Goals / Non-Goals

**Goals:**
- Separate runner (execution capability), agent (roster identity), and charter (authored behavior)
  into independent, composable Hub DB records.
- Give the operator a working way to assign behavior to an agent again — this capability has been
  silently absent since single-runtime shipped.
- Make `agent-tool-surface`'s "charter" scenario verifiable against a real implementation.
- Preserve the value of the existing 21 role guides as starting content, without preserving the
  role-list-as-fixed-enum mechanism or the file-based assignment format.

**Non-Goals:**
- No migration of `.agentweave/roles.json` data — nothing currently writes it, so there is nothing
  to migrate (consistent with single-runtime's "no external install base to protect" stance).
- No change to which CLIs are supported (`claude`, `codex` remain the only two runners; this change
  makes *runner* a first-class record type, it does not add new provider integrations).
- No multi-charter-per-agent composition in this change (e.g. layering a "backend" charter with a
  "security-conscious" charter). One agent has one active charter. Composable charters are a future
  extension if demand appears.
- No change to `project-instructions` (still prepended ahead of charter content, unchanged contract).

## Decisions

**Charter and Runner are Hub DB tables, not config-file or hardcoded-dict state.**
Mirrors the precedent already set by `project-instructions` (moved from
`.agentweave/project_instructions.md` to a Hub DB table + UI editor in an earlier change). A
`Charter` row: `id`, `project_id`, `name`, `content` (markdown), `created_at`, `updated_at`. A
`Runner` row: `id`, `project_id`, `name`, `cli` (`claude`|`codex`), `flags` (JSON list), `model`
(optional). `Agent` gains nullable `runner_id` and `charter_id` foreign keys, replacing the relevant
keys inside its freeform `config` JSON.
*Alternative considered*: keep runners as a hardcoded dict (they only have two values today) and
build charters only. Rejected — the proposal's own umbrella slice explicitly frames this as a
three-way separation, and a DB-backed `Runner` costs little now while leaving room for per-runner
model/flag variants (e.g. two `claude` runners with different default models) without another
migration later.

**Seed charters once from the existing 21 role guides, then delete the source files.**
On first boot after this change, if a project has zero `Charter` rows, seed them from
`hub/data/roles/*.md` (name = role label, content = guide body). This is a one-time data seed, not
an ongoing fallback tier — `_load_role_content`'s three-tier file lookup is deleted entirely, along
with `hub/data/roles/*.md` itself, `templates/roles/*.md`, and `src/agentweave/roles.py`.
*Alternative considered*: start with zero charters and let the operator author from scratch.
Rejected as a worse first-run experience — the 21 guides are decent starting content and this way
nothing of value is lost.

**`GET /api/v1/agents/context` (`_render_hub_agent_context`) resolves charter by the agent's
`charter_id`, not by a `role` query parameter matched against a fixed list.**
An agent with no assigned charter gets project instructions plus a generic "no charter assigned"
notice (mirrors the existing "Registered undeclared agent receives provisional context" scenario in
`agent-context-onboarding`) rather than an error — this keeps `GET /agent-context` non-fatal for
newly self-registered agents, matching current behavior for undeclared agents.

**Charter authoring UI reuses the `project-instructions` Instructions-screen pattern**: a list view
(charters + runners) with create/edit forms, textarea + Save, no new component primitives. Placed
alongside the existing Instructions screen in the Hub UI, not on the Agents page (charters and
runners are project-level resources an agent points to, not agent-embedded fields), with a
runner/charter picker on each `AgentCard`/agent detail view to bind an agent to one of each.

**`src/agentweave/context_builder.py` is deleted, not adapted.**
It exists only to assemble local-file role/project context for the CLI-local execution paths that
single-runtime already removed (`.agentweave/roles.json`, `.agentweave/context/<agent>.md`,
`ROLES_DIR`). Grepping its current callers (`src/agentweave/session.py`) shows they're already
calling into `roles.py`, which this change deletes — `context_builder.py` has no reason to survive
if its one remaining caller's dependency is gone. All context assembly happens Hub-side
(`_render_hub_agent_context`), consistent with single-runtime's "Hub owns everything" direction.

## Risks / Trade-offs

- **[Risk]** Two new subsystems (runner registry + charter) in one change is a lot of surface for one
  successor. → **Mitigation**: sequence as independently-verifiable phases (DB models → charter
  CRUD+UI → runner CRUD+UI → context-serving cutover → delete legacy `roles.py`/file formats →
  regression + live verify), matching the phase discipline used by every prior successor in this
  umbrella (see `agent-capability-plane`, `single-runtime` tasks.md for the pattern).
- **[Risk]** Deleting `_load_role_content`'s bundled-template fallback removes the only code path
  that currently makes role content resolve even without a Hub DB row. → **Mitigation**: the seed
  step (first-boot charter population from `hub/data/roles/*.md`) runs before the fallback is
  deleted, in the same phase, verified by a regression test that asserts every previously-bundled
  role has a corresponding seeded charter.
- **[Risk]** An operator with a leftover `.agentweave/roles.json` from before single-runtime shipped
  (containing real, if currently-inert, role assignments) gets that data silently dropped with no
  migration or warning. → **Mitigation**: none — accepted per this change's Non-Goals and consistent
  with single-runtime's stated stance. Worth one line in the proposal's release notes if this project
  ever ships release notes to end users; not a code change.
- **[Trade-off]** One charter per agent (no composition) is simpler to implement and reason about
  but means an operator wanting "backend dev who also does security review" must write one combined
  charter rather than layering two. Accepted for this change; revisit only if real usage demands it.

## Open Questions

- Should `Runner` support flags/model overrides in this change, or ship with just `cli` (claude vs
  codex) and defer flag/model customization to a later change? Leaning toward including it now since
  the DB row exists either way and an empty `flags`/`model` is a valid default — but flagging this as
  worth confirming against actual current `RUNNER_CONFIGS` flag usage during phase 0 investigation
  rather than deciding definitively here.
