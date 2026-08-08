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
- Agent **deletion**. Decided against rather than deferred — an agent is archived instead, and no
  permanent-deletion route is to be added. See the decision below.
- Redesigning project settings. Its pattern is followed, not changed.

## Decisions

### Agent configuration is a destination, not a tab inside a conversation

A conversation is transient and there may be many of them; an agent's configuration is durable and
singular. Nesting the second inside the first means configuration is reached *through* an unrelated
piece of work, and inherits whatever conversation happens to be selected.

The project pattern already resolves this and is followed: in environment mode the sidebar becomes
the section list plus a back control (`Sidebar.tsx:173-191`), rather than the sections nesting inside
the surrounding navigation.

**The destination is agent-scoped, not an environment section.** `ENVIRONMENT_SECTIONS` entries carry
no subject — `runners`, `charters` and `worktrees` are each one page for a whole collection — so
placing agents there would give one page for every agent, with the agent absent from the URL and
seven sections per agent competing on it. A fourth destination shape is added instead, carrying the
agent.

The apparent inconsistency is the argument for it. Environment holds **shared project resources**: a
runner is bound by many agents, a charter by many agents, a budget by the project. An agent is not a
shared resource — it is the object the product is organised around, since the rail is projects →
agents → conversations. Its settings belong to it for the same reason its conversations do.

Rejected: an `agents` entry in `ENVIRONMENT_SECTIONS`. Consistent with the furniture, inconsistent
with the product, and it cannot address one agent. An environment entry that merely *lists* agents
and links to each one's settings remains available later as a discoverability aid; it is not needed
to make this work.

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

`role` and `yolo` are both removed from `schemas/agents.py` and from the UI, but **for two different
reasons**, and the distinction was established by search (task 1.1) rather than assumed. An earlier
draft of this document asserted both were constants with no backing state. That is true of `role`
and false of `yolo`.

`role` is dead. `agents` has no column, nothing in the Hub reads it for behaviour, and its single
producer was `agents.py`'s summary populating it from `agent_meta`. `CLAUDE.md` already states that
role-derived API and UI fields must not be recreated. They were not recreated — they were never
fully removed. This change completes that removal rather than introducing a new rule.

`yolo` is **live, and stays live**. It is stored in `Agent.config` (documented at `models.py:503`)
and in session config, and it is read at `agent_trigger.py:288` to drive the spawn —
`runner_commands.py` chooses `--dangerously-skip-permissions` over `--permission-mode` from it, and
`codex_appserver._thread_policy` / `decide_approval` select Codex's approval posture from it. It is
also read at `agents.py:210` for the collaboration-readiness refusal. What is removed is only the
**read-only summary field and the badge that rendered it** — an observation of a setting whose
editable home is *Execution*'s default permission posture, where a value can actually be changed
rather than merely reported. `Agent.config["yolo"]` is untouched, and a test asserts it survives
the removal.

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

### Leaving returns to the agent's conversation, at a fixed target

Entry is from the agent — its row in navigation, and its conversation header. Leaving goes to that
agent's most recent conversation.

An earlier draft of this design had the back control return to whatever context the operator came
from. That was wrong on two counts. It departs from the shipped pattern, where "Back to {project}"
goes to a fixed destination (`App.tsx:207`) rather than a remembered one. And it makes the same
control land in different places depending on history, while requiring an origin to be stored and a
fallback for when that origin no longer exists — an archived conversation, or an agent that has
since been archived itself.

A fixed target costs nothing here because the agent *has* an obvious one. Back to the agent's
conversation is predictable, needs no stored origin, and keeps the agent as the organising object on
the way out as well as on the way in.

### Bindings are rebound in place and do not link through

*Execution* and *Charter* show what an agent is bound to and allow rebinding, through the picker
that already exists (`AgentInfoTab.tsx:352,394`). Neither links through to the runner's or charter's
own page.

Rebinding an agent and editing a shared record are different acts with different blast radius: a
runner is bound by many agents, so editing its definition from a surface titled with one agent's
name is how someone changes every agent while believing they are configuring one. Keeping the two
apart also means the back control stays one hop deep, with no navigation stack to maintain.

Editing the record itself remains two clicks away through environment → runners or → charters.

### An agent is archived, never deleted

An agent that is no longer wanted is archived. Hard deletion is not offered, and MUST NOT be added
later without revisiting this decision.

The reason is attribution. Everything in the Hub records the run that produced it, and every run
records its agent — which is how conversations, messages, tasks, and (once
`2026-08-07-conversation-handoff-rework` lands) cross-agent participation are attributed. Deleting an
agent either cascades through that history, destroying the record of work that genuinely happened,
or orphans it. Neither is acceptable for a system whose value is that it remembers.

This follows the house position rather than inventing one. `archivable()`
(`conversations.py:172`) refuses to archive a conversation holding an undelivered queue entry, on
the stated grounds that archiving would strand it permanently — the Hub already prefers refusing to
silently destroying. Agent archival mirrors conversation archival directly: a `lifecycle` column
constrained to `open` or `archived`, exactly as `models.py:255,280` does for conversations.

Archiving is reversible. An archived agent keeps its history, its conversations remain readable, and
it stops appearing where a working agent is offered. It is not triggerable while the agent has a run
in progress, for the same reason a conversation is not.

No `DELETE` route for an agent exists today, so this decision is additive: it is a commitment not to
add one, plus the archival that makes the absence workable.

## Risks

- **`role` and `yolo` may have consumers.** Both are on a response schema, so anything reading the
  agent list could depend on their presence, including tests. Non-functional does not mean
  unreferenced. **Realised, for `yolo`:** it is not non-functional at all — it drives the spawn and
  Codex's approval posture — and two tests asserted it on the list response. Only the response field
  is removed; the stored setting stays.
- **Two destinations for one agent.** The conversation and the settings page both belong to an
  agent, so navigation must make clear which is being shown and how to move between them without
  losing the conversation.
- **Sections defined ahead of their contents.** *Context* and *Access* are specified before the
  checkpoint change fills them. If that change's settings turn out not to fit, the sections were
  named wrongly — mitigated by naming them for operator intent rather than for the settings.
- **Archival has reach.** An archived agent must stop being offered wherever a working agent is
  offered — the rail, the peer-message recipient list, task assignment, the new-conversation
  surface. Missing one leaves an archived agent selectable, which is worse than not archiving.
- **Archival interacts with peer delivery.** Once
  `2026-08-07-conversation-handoff-rework` binds delivery to a conversation, a peer sending to an
  archived agent needs a defined answer. That change already defines the archived-*conversation*
  case; the archived-*agent* case is this change's to state.

## Open questions

None outstanding. The two that stood here — where the destination lives, and whether bindings link
through — were resolved by the operator on 2026-08-08 and are recorded above as decisions, together
with archival replacing deletion.
