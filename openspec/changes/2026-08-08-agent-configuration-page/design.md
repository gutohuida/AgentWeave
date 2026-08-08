## Context

Project settings are already a destination: `App.tsx:263-273` maps an `environmentSection` to a
page and suppresses `ProjectTabs` for that tab, so the section list replaces the tab strip rather
than nesting inside it. Agent configuration has no equivalent — it is `AgentInfoTab.tsx`, a tab
rendered inside an agent's conversation, mixing four unrelated things: live status, a session list,
two editable bindings, and two timeout fields.

Two forces make this the moment to change it.

`2026-08-07-conversation-handoff-rework` introduces agent-level settings with no home: automatic
checkpoint mode, cutover and notes thresholds, a generating runner and model, and two access grants.
Its section 8 assumes a surface that does not exist.

And the existing surface is partly fictional. `agents` has no `role` or `yolo` column;
`schemas/agents.py:44-47` declares both anyway, and `AgentInfoTab.tsx:110-153` renders them. Because
`yolo` is `bool = False` with no backing state, the badge is a permanent **Disabled**.

## Goals / Non-Goals

**Goals:**

- Make agent configuration a destination with its own section navigation and a back control.
- Separate configuration from observation, which are currently interleaved in one tab.
- Establish a stated rule for what is set at creation versus later.
- Remove agent fields that no longer have backing state.
- Define sections so the checkpoint change's settings land without restructuring.

**Non-Goals:**

- Defining the checkpoint settings themselves. Their semantics belong to
  `2026-08-07-conversation-handoff-rework`; this change provides the container.
- Runner and charter *management*. Those are already destinations (`RunnersPage`, `ChartersPage`);
  this page binds an agent to them, it does not edit them.
- Agent deletion. Raised repeatedly as an open question and still unanswered; out of scope here.
- Redesigning project settings. Its pattern is followed, not changed.

## Decisions

### Agent configuration is a destination, not a tab inside a conversation

A conversation is transient and there may be many of them; an agent's configuration is durable and
singular. Nesting the second inside the first means configuration is reached *through* an unrelated
piece of work, and inherits whatever conversation happens to be selected.

The project pattern already resolves this and is followed: a section list replaces the tab strip
rather than nesting inside it, and the destination is addressable in the URL so configuration can be
linked to and returned to.

Navigation is by back control rather than the left panel, matching project settings. The rationale
there applies unchanged: a settings surface is somewhere you go and come back from, not somewhere
you browse laterally.

### Status and sessions are observation and do not move

`AgentInfoTab` mixes four things. Status, `latest_status_msg`, `last_seen` and the session list are
observations about a running agent — they change without anyone configuring anything, and they are
useful *while working*, which is exactly where they already are.

Only the settings move. Splitting on this line keeps the conversation useful and keeps the settings
page free of things that change under the reader.

### Sections are named for what an operator is trying to do

| Section | Holds |
|---|---|
| Identity | name, description |
| Execution | runner binding, model, default permission posture |
| Charter | charter binding |
| Interaction | permission timeout, question timeout |
| Context | automatic checkpointing, thresholds, generating runner and model |
| Access | checkpoint read grant, observation recall grant |
| Workspace | worktree, working directory |

**Context** and **Access** are defined here and populated by
`2026-08-07-conversation-handoff-rework`. They exist in this change as sections with the settings
that already exist; the checkpoint change adds to them without moving anything.

The split between **Execution** and **Interaction** is deliberate: one is what the agent runs as,
the other is how long it waits for a human. They were adjacent in the old tab under a heading —
*"Roles & Configuration"* — that named a concept that no longer exists.

### A setting with no backing state is not displayed

`role` and `yolo` are removed from `schemas/agents.py` and from the UI. Neither has a column;
`yolo` is a literal `False`, so its badge cannot report anything else, and `role` is always `None`,
so its section never renders at all.

`CLAUDE.md` already states that role-derived API and UI fields must not be recreated. They were not
recreated — they were never fully removed. This change completes that removal rather than
introducing a new rule.

The stale enum comment on `runner` (`schemas/agents.py:48-50`) naming
`"native" | "claude_proxy" | "kimi" | "manual"` is corrected at the same time: runners are registry
records now, and a comment describing a deleted enum is a trap for the next reader.

**Removal must be verified, not assumed.** These fields are non-functional, so removing them should
change no behaviour — but "should" is what this project has repeatedly found to be wrong. Consumers
are located before removal.

### What is set at creation is decided by whether it affects the first turn

Creation collects name, provider, model and charter today (`AgentCreateDialog.tsx:128-217`). Rather
than growing that dialog by intuition, the boundary is stated:

> A setting is **offered** at creation if the agent's **first turn** would be materially different
> without it. Everything else is set on the configuration page.

The rule governs what is *offered*, not what is *required*. `operator-agent-creation` already
states that a charter "MAY be selected but MUST NOT be required", with a defined no-charter contract
granting full project scope — that stays exactly as it is. Charter is offered at creation because it
shapes the first turn; it is not mandatory, because a working default exists.

Runner and model are the stronger cases: they are required today, because no default is right for
every agent and an agent cannot run without them.

Thresholds, timeouts, and access grants fail the test: they have workable defaults, they can be
changed before they ever matter, and adding them to creation makes the first thing an operator does
with AgentWeave longer for no gain. Friction at creation is the barrier this product exists to
remove.

This is a rule, not a list, so a future setting is placed by applying it rather than by argument.

### The page is reached from the agent, and returns to where it came from

Entry is from the agent — its row in navigation, and its conversation header. Leaving returns to the
originating context rather than to a fixed location, because an operator who opened settings from a
conversation is mid-task in that conversation.

## Risks

- **`role` and `yolo` may have consumers.** Both are on a response schema, so anything reading the
  agent list could depend on their presence, including tests. Non-functional does not mean
  unreferenced.
- **Two destinations for one agent.** The conversation and the settings page both belong to an
  agent, so navigation must make clear which is being shown and how to move between them without
  losing the conversation.
- **Sections defined ahead of their contents.** *Context* and *Access* are specified before the
  checkpoint change fills them. If that change's settings turn out not to fit, the sections were
  named wrongly — mitigated by naming them for operator intent rather than for the settings.
- **Scope pull toward agent deletion.** A settings page is where an operator expects to find it, and
  it is a standing open question. Deferring it will read as an omission.

## Open questions

- Does the agent settings page belong under the project's `environment` destination alongside
  runners and charters, or as its own destination hanging off the agent? The first groups
  configuration together; the second keeps the agent as the organising object.
- Should binding a runner or charter link through to that record's own page, and if so does the back
  control return to agent settings or to where the operator originally came from?
