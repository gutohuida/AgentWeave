# Design

## Decision 1 — `acceptEdits` becomes the non-yolo default, and permission becomes a conversation control

`2026-08-06-claude-non-yolo-permission-mode` chose `manual` so that a run's posture came from the
Hub's own flag rather than from whatever `~/.claude/settings.json` happened to say on the host. That
reasoning still holds; the *value* was wrong. `manual` delegates each decision to an operator who has
no way to answer, so in practice it denies everything that needs approval — which is every write.

`acceptEdits` keeps the Hub in control of posture while producing a run that can do work. It is not a
weakening of the sandbox: the agent is already confined to its own git worktree by
`worktrees.resolve_agent_workspace`, and that boundary is unchanged. What changes is that the agent
can now act *within* its boundary.

Three modes are offered, in operator language rather than CLI spelling:

| Value | Label | Meaning |
|---|---|---|
| `acceptEdits` | Edit files | Default. Work in the agent's own workspace. |
| `manual` | Ask first | Every action needs approval — with no approval surface, effectively read-only. |
| `bypassPermissions` | Full access | No permission checks at all. |

`manual` is retained rather than removed because it is the only way to get a deliberately inert run,
and because it becomes genuinely useful once the deferred Hub-answered approver exists.

### Why this rides the model-catalog machinery

`ComposerModelControls` renders **every** provider control with `kind === 'enum'`, and the override
path — `validate_overrides` → `/agent/trigger` → `Conversation.runtime_overrides` →
`render_control_args` → argv — is entirely control-id agnostic. A single `ControlDescriptor` therefore
produces a composer pill, per-conversation persistence, server-side validation, and argv rendering
with no new endpoint, column, or component. That is the whole reason to model permission as a control
rather than as a bespoke setting.

`_enum()` is deliberately **not** used for the values: it derives labels via
`id.replace("_", " ").capitalize()`, which would render `acceptEdits` as "Acceptedits". The
descriptors are written out with explicit `ControlValue` labels.

### The ordering bug this exposes

`_build_claude_command` splices `control_args` in early and appends its own permission flag later, so
today an operator's override would be silently overridden by the hardcoded value. Both the
`--permission-mode` and the `--dangerously-skip-permissions` branches are therefore guarded on whether
the override already supplies `permission_mode`. Without that guard the control would appear to work
in the UI and do nothing — the worst failure mode available.

## Decision 2 — tool schemas carry their enums, sourced from the validators

The fix is not to document the valid values in prose; it is to put them in the schema, where every
client already looks. `Literal[...]` on the parameter makes FastMCP emit `"enum": [...]`, which reaches
Claude and Codex identically over the same stdio server.

The values are imported from the Hub's own schema modules (`_MESSAGE_TYPES`, `_TASK_STATUSES`,
`_PRIORITIES`) rather than retyped. A `Literal` needs compile-time constants, so the module defines the
literal alias next to an assertion that it matches the runtime list — drift then fails a test rather
than silently reintroducing the bug.

`update_task(status)` is the most important of the four and the only one with no default: a model
*must* supply a value from an eight-state lifecycle it was never shown. It is the next failure that
would have been reported.

The error surface is fixed too. `HubAPIError` currently renders a stringified Python list of Pydantic
error dicts; an agent trying to self-correct has to parse that. Reducing it to the `msg` sentence is
what let the Codex agent recover on its second attempt, and it should not have to.

## Decision 3 — autoscroll follows what is rendered, and opening lands at the newest turn

Keying the effect on `lines` was a latent bug from when the conversation view *was* the output log.
Re-keying on `timelineEntries` matches `AgentActivityTab`, which already does this correctly for its
own tab and serves as the in-repo reference.

Opening position is a genuine gap rather than a regression — no code ever scrolled on open. It is
implemented as an instant (non-smooth) scroll on conversation identity change, so opening a long
history does not animate through it.

The jump-to-bottom button is a *different control* from the pause/resume toggle the
`agent-conversation-workspace` spec forbids. That toggle duplicated intent already expressed by scroll
position; a jump affordance expresses a new intent ("take me back") and appears only when following is
suspended, so it cannot become a second source of truth for whether to follow.

## Decision 4 — context tells an agent where it is, and what its tools accept

Two additions and one deletion.

**"Your workspace"** carries the absolute working directory, the fact that it is an isolated worktree
on branch `agentweave/<agent>`, and that peers work in sibling worktrees. This is the fix for the
actual file-write failure: an agent that knows its cwd resolves paths against it instead of guessing
the project root. `effective_work_dir` already exists in `trigger_agent_directly`; it is threaded into
the renderer rather than recomputed, so the text cannot disagree with the process.

A read-only agent runs in the shared repo root rather than a worktree, so the section states which
case applies rather than asserting isolation unconditionally.

**"Your tools"** is generated from the same `Literal` aliases as Decision 2, so the context and the
schema cannot drift. It exists because naming a tool without its valid values is what produced the
Codex failure — and because four job tools are currently invisible to agents entirely.

**The deletion** is ``- Canonical runtime context: `.agentweave/context/{agent}.md` ``. It points at a
file whose contents the agent has already been given, and following that pointer caused the first
permission denial of the operator's test. A pointer to already-delivered content is pure downside.

## Decision 5 — charters are instructions, so they are corrected in place

Charter text is inlined into the model context by `_render_hub_agent_context`, so a charter that says
"Read `roles.json`" is a live instruction to read a file the Hub never creates — not stale
documentation. The seeded set is corrected rather than deleted, because the charters' *substance*
(scope, responsibilities, handoff rules) is still exactly what the runner/agent/charter model wants;
only their startup ritual and their references to removed subsystems are wrong.

The common opener is replaced with the truth: the roster, project instructions, and charter all arrive
in the turn context, and nothing needs to be read to begin. Charters are seeded per project at
creation, so this corrects new projects; existing projects keep their stored copies, which is correct
— they are operator-editable documents, and silently rewriting them would be worse than leaving them.

## Risks

- **Agents can now write by default.** Intended. The worktree is the boundary and is unchanged; `manual`
  remains available for an inert run.
- **`bypassPermissions` is one click away in the composer.** It is labelled "Full access" rather than
  by its CLI spelling, and it is a per-conversation choice rather than a persistent setting.
- **Charter edits are broad prose changes across 21 files.** They are seed data with no code depending
  on their wording; the risk is limited to the text an agent reads.
