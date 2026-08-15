# agent-configuration Specification

## Purpose
An agent's configuration is a destination of its own, not a dialog and not a panel inside a
conversation. It divides into sections named for what an operator is trying to do — identity,
execution, charter, interaction, context, access, workspace — and it holds only settings:
observations about a running agent stay with the conversation, where they are useful.

An agent is archived, never deleted, because every run the Hub records is attributed to one. What
creation collects is bounded by whether it changes the first turn; everything else is here.
## Requirements
### Requirement: Agent configuration is a destination rather than a surface inside a conversation

The Hub SHALL present an agent's configuration as its own addressable destination, and MUST NOT
require an operator to open a conversation to reach it.

A conversation is transient and an agent may have many; its configuration is durable and singular.
Reaching configuration through a conversation makes it depend on which conversation happens to be
selected, and places durable settings behind a transient surface.

The destination MUST be linkable and MUST survive a reload, so configuration can be returned to
directly.

#### Scenario: Configuration is reached without opening a conversation

- **WHEN** the operator opens an agent's configuration from navigation
- **THEN** the configuration destination opens
- **AND** no conversation is required to have been selected

#### Scenario: The destination is durable

- **WHEN** the operator reloads while viewing an agent's configuration
- **THEN** the same agent's configuration is shown

### Requirement: Configuration navigation replaces the surrounding navigation with a return control

An agent's configuration SHALL present its sections in place of the surrounding navigation, and
SHALL offer a control returning to the context the operator came from.

This follows the project's own settings pattern, where a section list replaces the tab strip rather
than nesting inside it. A settings surface is somewhere an operator goes and comes back from, not
somewhere they browse laterally, so the lateral navigation is what gives way.

Returning SHALL lead to a **fixed** target — the agent's most recent conversation — regardless of
where the operator entered from. This matches the return control the project's own configuration
already offers, which names one destination rather than describing where the operator has been. A
remembered origin makes the same control mean different things on different visits, and there is
nothing on screen that says which; a named, fixed target can be read before it is used.

Both entry points therefore lead to the same place, which is the place the operator is going to
work next in either case.

#### Scenario: Sections replace lateral navigation

- **WHEN** an agent's configuration is shown
- **THEN** its sections are presented in place of the surrounding navigation

#### Scenario: Returning leads to the agent's conversation

- **WHEN** the operator opens configuration from a conversation and then returns
- **THEN** the agent's most recent conversation is shown

#### Scenario: The target does not depend on where the operator entered from

- **WHEN** the operator opens configuration from navigation and then returns
- **THEN** the agent's most recent conversation is shown, the same target as from a conversation

### Requirement: Configuration is separated from observation

An agent's configuration destination SHALL present only settings, and observations about a running
agent SHALL remain with the agent's conversation.

Status, the latest status message, last-seen time and the session list change without anyone
configuring anything, and they are useful while working rather than while configuring. Mixing them
with settings produces a surface that changes under the reader and a conversation stripped of the
context it needs.

No setting SHALL be editable from more than one surface.

#### Scenario: Observations are not on the configuration destination

- **WHEN** an agent's configuration is shown
- **THEN** live status and session history are not presented there

#### Scenario: Observations remain available while working

- **WHEN** the operator is working in an agent's conversation
- **THEN** that agent's status and sessions remain available there

#### Scenario: A setting has one home

- **WHEN** a setting is presented on the configuration destination
- **THEN** it is not also editable elsewhere

### Requirement: Configuration sections are named for operator intent

An agent's configuration SHALL be divided into sections named for what an operator is trying to do,
covering identity, execution, charter, interaction, context, access, and workspace.

Naming sections after operator intent rather than after data shape is what allows a later capability
to add settings without the section having to be renamed or restructured. *Context* and *Access* are
defined here and are populated further by conversation checkpointing.

A section MUST NOT be named for a concept the product no longer has.

#### Scenario: A new setting joins an existing section

- **WHEN** a capability introduces an agent-level setting for automatic checkpointing
- **THEN** it is presented within the context section
- **AND** no section is renamed or restructured to accommodate it

#### Scenario: Bindings are bound, not edited

- **WHEN** the operator views the runner or charter an agent is bound to
- **THEN** the binding can be changed
- **AND** the runner or charter record itself is not edited from this destination

### Requirement: An agent carries a description written for the operator

An agent SHALL carry an optional operator-written description of what it is for, editable from the
identity section and returned with the agent's summary.

The description MUST NOT be injected into any agent's turn context. The charter is where an agent's
behaviour is stated; a second field that also shaped behaviour would leave two places to look when
an agent acts wrongly, and only one of them would be a contract.

A blank description SHALL be stored as no description, so that "cleared" and "never written" are
one state rather than two a reader has to distinguish.

#### Scenario: The operator records what an agent is for

- **WHEN** the operator writes a description in the identity section
- **THEN** it is saved against the agent and shown when the section is next opened
- **AND** the agent's turn context is unchanged

#### Scenario: Clearing a description

- **WHEN** the operator empties an agent's description
- **THEN** the agent has no description
- **AND** it is indistinguishable from an agent whose description was never written

### Requirement: An agent is archived rather than deleted

The Hub SHALL allow an agent to be archived and unarchived, and MUST NOT offer any means of
permanently deleting one.

Everything the Hub records is attributed to the run that produced it, and every run is attributed to
its agent. Deleting an agent would either cascade through that history, destroying the record of
work that genuinely happened, or orphan it. This capability follows the position already taken for
conversations, where archival is refused rather than allowed to strand something permanently.

Archival MUST be reversible, and MUST preserve the agent's history: its conversations remain
readable, and its runs and messages retain their attribution.

An agent with a run in progress MUST NOT be archived, nor one holding undelivered inbound queue
entries. Both are refused with the reason rather than resolved: stopping a live run from a settings
page destroys work with no undo, and archiving over a queued entry strands it permanently, because
nothing delivers to an archived agent.

An archived agent MUST NOT be offered wherever a working agent is offered, including for a new
conversation, as a message recipient, and as a task assignee. It MUST nonetheless remain reachable
when explicitly asked for, because its own configuration is where unarchiving happens — an agent
that could be archived but never found again would be deleted in all but name.

An agent MUST NOT be able to send a message to an archived agent. The send SHALL fail with a
response carrying three things: that the recipient is archived, what to do instead, and the content
the sender submitted, restated verbatim. This is the contract `agent-capability-plane` already
states for an archived conversation, for the same reason — a blocked send that returns only an
error forces the agent to reconstruct its own message from a context it may have moved past.
Opening a new conversation instead would not help: nothing runs an archived agent, so the entry
would sit queued forever.

#### Scenario: Archiving is refused over undelivered messages

- **WHEN** an operator archives an agent holding undelivered inbound queue entries
- **THEN** the request is refused with the reason
- **AND** the entries remain queued

#### Scenario: An archived agent is still reachable when asked for

- **WHEN** an archived agent's configuration is requested
- **THEN** the agent resolves
- **AND** unarchiving is offered there

#### Scenario: A peer send to an archived agent is refused with its own content

- **WHEN** an agent sends a message to an archived agent
- **THEN** the send fails
- **AND** the response states that the recipient is archived, says what to do instead, and restates the submitted content
- **AND** no queue entry is created for the archived agent

#### Scenario: An archived agent is not offered as a working agent

- **WHEN** an agent is archived
- **THEN** it is not offered for a new conversation, as a message recipient, or as a task assignee

#### Scenario: History survives archival

- **WHEN** an agent is archived
- **THEN** its conversations remain readable
- **AND** its runs and messages retain their attribution

#### Scenario: Archiving is refused during a run

- **WHEN** an operator archives an agent with a run in progress
- **THEN** the request is refused with the reason
- **AND** the agent remains active

#### Scenario: Archival is reversible

- **WHEN** an archived agent is unarchived
- **THEN** it is offered as a working agent again

#### Scenario: No permanent deletion is offered

- **WHEN** an operator views an agent's configuration
- **THEN** no action permanently deletes the agent

### Requirement: An agent's workspace states where it works and whether that place is its own

The workspace section SHALL state the directory an agent's turn runs in, and whether that
directory is the agent's own isolated checkout or the project checkout it shares.

Reading it MUST NOT provision anything. An agent that has never run SHALL be told where it will
work rather than shown an empty section, because a section that renders blank is indistinguishable
from one that failed to load.

Where an agent's isolation cannot be prepared, the section SHALL state the reason — the same
condition that would otherwise surface only as a refused turn.

#### Scenario: An agent that has never run

- **WHEN** the operator opens the workspace section for an agent with no checkout yet
- **THEN** the directory it will work in is stated
- **AND** no checkout is created by opening the section

#### Scenario: A workspace that cannot isolate

- **WHEN** an agent's project directory cannot provide an isolated checkout
- **THEN** the section states why
- **AND** it says so before a turn is refused over it

### Requirement: An agent has a default permission posture

An agent SHALL carry an optional default permission posture, chosen from the same postures the
per-run permission control offers and presented with the same labels, editable from the execution
section.

The Hub SHALL apply that default to any run whose conversation has not chosen a posture — including
runs started by a peer message or a schedule, where no operator is present to choose one. A
conversation's own choice SHALL take precedence over it.

An agent's stored autonomy flag is the older two-valued spelling of this same setting, not a second
setting. Writing the posture SHALL update that flag so the two cannot disagree, and clearing the
posture SHALL clear it, since an agent left at full access after full access was cleared would
contradict what the operator was told.

Where the posture is shown at rest — the composer's permission control — it SHALL show what the run
will actually do, and showing it SHALL NOT record it as a choice made for that conversation.

#### Scenario: An unattended run has an answer

- **WHEN** a peer message triggers an agent whose conversation states no posture
- **AND** the agent has a default posture
- **THEN** the run is spawned under that posture

#### Scenario: A conversation overrides the default

- **WHEN** the operator chooses a posture for one conversation
- **THEN** that posture is used for its runs
- **AND** the agent's default is unchanged

#### Scenario: The autonomy flag follows the posture

- **WHEN** an operator sets an agent's default posture to full access
- **THEN** the agent's stored autonomy flag reads as set
- **AND** clearing the posture clears the flag

### Requirement: A setting with no backing state is not presented

The Hub SHALL NOT present an agent setting that has no state behind it, and SHALL NOT expose such a
field on the agent's API representation.

An agent's stored record has no role state. It was nonetheless carried on the response schema and
rendered. A field that no store can ever populate is a claim that something is configurable when it
is not.

The Hub SHALL also not present a setting as a **read-only badge** when that setting has an editable
home elsewhere in the agent's configuration. An autonomy flag is a real stored setting that selects
the run's permission posture, so it belongs where a posture is chosen and can be changed — not
duplicated as an observation that reports a value the operator cannot act on. Reporting a setting
without offering to change it is the mirror of the first failure: the first offers a control with no
state, the second shows state with no control.

The operator MUST NOT be asked to choose a persona or organizational role, which
`operator-agent-creation` already requires of creation and which applies equally to configuration.

#### Scenario: A field without stored state is absent from the API

- **WHEN** an agent is returned by the API
- **THEN** no field is present that has no corresponding stored state

#### Scenario: No persona or role is configurable

- **WHEN** an agent's configuration is shown
- **THEN** no persona or organizational role is offered

#### Scenario: A stored autonomy flag keeps driving the run after leaving the summary

- **WHEN** an agent whose stored configuration sets an autonomy flag is triggered
- **THEN** the flag still selects the run's permission posture
- **AND** the flag is absent from the agent's summary representation

### Requirement: The operator can grant an agent the authority to accept evidence

The system SHALL let the operator confer, and withdraw, an agent's authority to accept or reject requirement evidence.

Authority over what ships is the operator's to give. A capability enforced in the system but
settable nowhere is one no agent can ever hold, which makes the enforcement a refusal of everyone.

The grant SHALL be presented separately from capabilities that only widen what an agent can read.
Accepting evidence decides whether work is allowed to merge; grouping it with reading tells the
operator it is a kind of reading.

The surface SHALL say what the grant does not confer — that a granted agent still cannot accept
evidence it produced itself.

A project that has granted no agent SHALL still be able to accept evidence, as the operator.

#### Scenario: The operator grants acceptance

- **WHEN** the operator grants an agent the authority to accept evidence
- **AND** reads that agent's configuration back
- **THEN** the grant is shown as held

#### Scenario: The grant is withdrawable

- **WHEN** the operator withdraws the grant
- **THEN** the agent is refused when it next decides evidence

#### Scenario: Granting is not conferred by a charter

- **WHEN** an agent is bound to a charter describing a reviewer
- **THEN** it holds no acceptance authority until the operator grants it

