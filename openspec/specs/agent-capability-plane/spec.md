# agent-capability-plane

## Purpose

One least-privilege, run-authenticated application contract for agent-caused effects and scoped
reads, shared identically by HTTP and MCP. Established by `openspec/changes/agent-capability-plane`.

**Reconciled 2026-08-07.** The equal-capability requirement below previously named "ordinary
commands" as a third adapter. No such command exists — the CLI was reduced to local instance
management — and `openspec/explorations/2026-08-02-product-direction.md` states that the reduced CLI
is not an agent capability adapter.
## Requirements
### Requirement: A live run credential is the only agent authentication

The system SHALL mint an unguessable credential for each Hub-owned run, store only a non-reversible
digest, and accept the credential only while that exact run is active. Authentication SHALL derive
the project, agent, and run from the matched row. The credential MUST NOT be exposed in output,
events, command arguments, or API responses.

#### Scenario: Active run resolves to one actor

- **WHEN** an agent request carries a valid credential for a running run
- **THEN** the server derives that run's project and agent
- **AND** the request supplies no actor identity

#### Scenario: Terminal run is revoked

- **WHEN** a credential belongs to a completed, failed, stopped, or interrupted run
- **THEN** the agent request is refused

#### Scenario: Credentials cannot cross privilege planes

- **WHEN** a project API key is presented to the agent API or a run credential is presented to an
  operator API
- **THEN** authentication is refused

### Requirement: The agent API is a least-privilege allowlist

The agent application API SHALL expose only peer messaging, shared task-ledger reads/writes,
operator questions and their answers, governed agent requests, and governed scheduled-work
mutations. It MUST NOT expose inbound queue/history, roster, project settings, agent configuration,
charter/scope, credentials, or other operator capabilities.

#### Scenario: Outbound intent is available

- **WHEN** an authenticated run messages a peer, works with the shared task ledger, or asks the
  operator a question
- **THEN** the permitted effect or read succeeds under the same validation as the operator system

#### Scenario: Coordination and configuration are absent

- **WHEN** an authenticated run tries to read undelivered input or alter project/agent configuration
- **THEN** no agent API operation provides that capability

#### Scenario: New operator APIs are denied by default

- **WHEN** an operator-only route is added without an explicit agent capability
- **THEN** a run credential cannot call it

### Requirement: Actor identity cannot be supplied or overridden

Agent-action payloads SHALL contain no project, agent, sender, assigner, requester, or run identity
field. Every affected service SHALL use only the authenticated actor. Caller headers or extra body
fields MUST NOT change attribution.

#### Scenario: Impersonation is structurally unavailable

- **WHEN** an agent constructs a valid action request
- **THEN** there is no supported field by which it can select another actor

#### Scenario: Override attempts do not change the actor

- **WHEN** a caller adds identity-like headers or unknown body fields
- **THEN** the effect is either rejected as invalid or remains attributed to the authenticated run

### Requirement: Every agent-caused effect retains run attribution

The system SHALL ensure every message, task creation/update, question, scheduled-work mutation, and
agent request caused by the agent plane durably identifies the responsible agent and run. Event logs MUST NOT be the
only source of that attribution. Historical/operator effects MAY remain unattributed where no run
exists.

For **task status** specifically, last-writer attribution is insufficient: approval is a judgement
about work a different run performed, so a single mutable field cannot express the question of
whether author and reviewer differ. Task status attribution SHALL therefore be an append-only
sequence, one record per accepted transition, each naming its own responsible run. A materialised
"latest responsible run" MAY be retained for convenience but MUST NOT be the only durable record.

#### Scenario: Persisted effect names its run

- **WHEN** an authenticated run causes an allowed effect
- **THEN** the resulting durable record identifies that run
- **AND** its project and agent are consistent with the authenticated actor

#### Scenario: Updates retain the latest responsible run

- **WHEN** an authenticated run updates a mutable task or job
- **THEN** the record identifies the run responsible for that update

#### Scenario: Task status attribution survives a later transition

- **WHEN** one authenticated run moves a task to `completed` and a later run moves it to another
  status
- **THEN** the run responsible for the earlier transition is still identifiable
- **AND** the later transition has not overwritten it

### Requirement: HTTP and MCP access have equal capability

Direct HTTP SHALL be the application contract. MCP SHALL be a thin adapter over that contract with
the same operations, validation, governance, attribution, and typed failure meaning. An adapter MUST
NOT duplicate queue, budget, identity, or lifecycle business rules and MUST NOT silently convert
failures into empty or successful results.

Two adapters exist rather than one because MCP is convenient where it is permitted and some
environments forbid MCP servers while still allowing ordinary local API calls. The command-line
interface is **not** one of them: it manages the local application instance and carries no agent
capabilities.

#### Scenario: One operation has one persisted result

- **WHEN** equivalent valid actions are performed through HTTP and through MCP
- **THEN** their persisted effects have equivalent content and attribution

#### Scenario: Failure meaning survives adaptation

- **WHEN** the application API returns validation, denied, not-found, or conflict failure
- **THEN** MCP callers receive the same failure meaning

#### Scenario: The CLI offers no agent capability

- **WHEN** an agent attempts to affect shared state through a command-line invocation
- **THEN** no such command exists

#### Scenario: No full project credential is present

- **WHEN** the Hub starts an agent with either adapter available
- **THEN** the process receives its run credential
- **AND** it does not receive a project/operator API key

### Requirement: A turn that ends on an unasked question is surfaced to the operator

The system SHALL durably record, and show the operator, any run that completes having produced a
trailing question without opening a question of record.

An agent that ends a turn on an unanswered question has stopped working and is waiting for an answer
that cannot arrive, because nothing was ever asked. From the operator's side this is
indistinguishable from a completed turn. Detection is the only available remedy: no provider
protocol permits requiring that a turn end through a particular tool.

#### Scenario: A completed run ends in a question and opened no question row

- **WHEN** a run completes, its final assistant text ends in a question, and the run opened no
  question of record
- **THEN** a pending record of the unasked question is stored, carrying the agent, the run, the
  conversation and the question text
- **AND** an event is broadcast so the operator's view updates without a reload

#### Scenario: The run asked properly

- **WHEN** a run completes having opened a question of record
- **THEN** no unasked-question record is created, regardless of how its final text ends

#### Scenario: The run did not end in a question

- **WHEN** a run completes and its final assistant text does not end in a question
- **THEN** no unasked-question record is created

#### Scenario: The turn is about to continue

- **WHEN** a run completes ending in a question and the agent still has queued input
- **THEN** no unasked-question record is created, because the next turn starts on its own

#### Scenario: The run did not complete

- **WHEN** a run ends in any status other than completed
- **THEN** no unasked-question record is created

### Requirement: The operator can convert an unasked question into a real one

The system SHALL offer the operator, for each pending unasked question, an action that re-prompts the
agent to ask that same question through the question tool, and an action that dismisses it.

Answering the detected question directly is not possible: the turn has ended and no tool call is
waiting on a value. Re-prompting is the only action that restores the intended flow.

#### Scenario: The operator re-prompts the agent

- **WHEN** the operator chooses to have the question asked properly
- **THEN** the record moves out of pending
- **AND** the agent is triggered with an instruction naming that question and requiring it be asked
  through the question tool with its required structure

#### Scenario: The operator dismisses it

- **WHEN** the operator dismisses a pending unasked question
- **THEN** the record moves out of pending and the operator is not shown it again

#### Scenario: A record is acted on twice

- **WHEN** an action is taken on a record that is no longer pending
- **THEN** the request is refused rather than silently repeated

### Requirement: Operator-facing severity values are the ones the operator's view understands

Events persisted for the operator's attention SHALL use the severity vocabulary the operator's views
filter and style by.

A severity that no view recognises is worse than none: the row renders unmarked and is hidden by the
filter intended to reveal it, so the events most needing attention are the ones least likely to be
seen.

#### Scenario: A refused action is recorded

- **WHEN** the system records that an agent's action was refused
- **THEN** the stored severity is one the operator's activity view filters and styles by

### Requirement: An agent can ask several questions in one turn

The question tool SHALL accept a list of questions and hold the turn until every one has been
answered or the wait expires.

An agent needing several decisions before it can start would otherwise block its turn once per
question and interrupt the operator once per question, or decide some of them itself. Asking together
is one interruption and one wait.

Where the asking run is no longer waiting — it expired, ended, or the question was not blocking —
the answers SHALL reach the agent as **one** delivery for the batch rather than one per answer, and
that delivery SHALL happen only once every question in the batch has been answered or declined. An
answer delivered on its own has the agent act on part of a decision while the operator is still
making the rest, which is the interruption asking together exists to prevent.

The delivery SHALL carry every question in the batch, in the order they were asked, each with its
answer or with the fact that the operator declined it. It SHALL include an answer that was recorded
while the asking run was still waiting but which that run never received. Where the batch produced no
answers at all, nothing SHALL be delivered.

Recording an answer SHALL NOT wait for the batch. Each answer SHALL be persisted, reported, and
SHALL release any task it had parked when the operator gives it.

#### Scenario: A batch is asked and answered

- **WHEN** an agent asks several questions in one call
- **AND** the operator answers all of them
- **THEN** the tool returns every answer, each identified with the question it answers

#### Scenario: The wait expires with a batch partly answered

- **WHEN** the wait expires before every question in a batch is answered
- **THEN** the tool returns without an answer for the unanswered ones and states plainly that they
  went unanswered

#### Scenario: A single question is still a single question

- **WHEN** an agent asks one question
- **THEN** it behaves exactly as an unbatched question does, with no extra step for the operator

#### Scenario: Each question keeps its required structure

- **WHEN** any question in a batch is submitted without its header, its options, or its
  multi-select flag
- **THEN** the call is rejected rather than partially accepted

#### Scenario: Answers to a batch whose asker has gone arrive together

- **WHEN** the asking run is no longer waiting and the operator answers the first question of a
  batch
- **THEN** nothing is delivered to the agent
- **WHEN** the operator resolves the remaining questions
- **THEN** exactly one delivery reaches the agent, carrying every question and its answer in the
  order asked

#### Scenario: A decline completes a batch and is delivered as a decline

- **WHEN** the operator answers some questions of a batch and declines the rest
- **THEN** the batch is delivered
- **AND** the declined questions are named as declined rather than omitted

#### Scenario: An answer the asking run never received is still delivered

- **WHEN** the operator answers a question while its asking run is waiting
- **AND** that run ends before the batch completes
- **AND** the operator then resolves the remaining questions
- **THEN** the delivery carries the earlier answer as well as the later ones

#### Scenario: A batch resolved entirely by declines delivers nothing

- **WHEN** every question in a batch is declined and none is answered
- **THEN** no delivery is made to the agent

#### Scenario: An answer is recorded before its batch completes

- **WHEN** the operator answers one question of a batch and the batch is not yet complete
- **THEN** that answer is recorded and any task it had parked is released
- **AND** it survives a reload of the operator's view

#### Scenario: A waiting asker is not sent the batch twice

- **WHEN** the asking run is still waiting and the operator answers every question in the batch
- **THEN** the tool call returns the answers
- **AND** no delivery is queued to the agent

### Requirement: The operator answers a batch one question at a time

The operator SHALL be shown one question of a batch at a time, told which step they are on and how
many there are, and advanced to the next once the current one is answered.

Showing a batch at once turns a conversation into a form, and a count of outstanding questions
displayed where a step count belongs misrepresents how much is left.

Where a batch's answers are held until it completes, the operator SHALL be told that the answers go
to the agent together. Without it, a part-answered batch is indistinguishable from answers that were
discarded: the operator answers, sees nothing happen, and has no way to tell that the agent is
waiting on the rest. This statement is about what has been sent and is distinct from the step
counter, which is about position.

#### Scenario: The step counter reflects position within the batch

- **WHEN** the operator is answering a batch
- **THEN** the displayed count is their position within that batch and its total, not the number of
  questions outstanding across the project

#### Scenario: Answering advances to the next question

- **WHEN** the operator answers the question on screen and others in its batch remain
- **THEN** the next unanswered question in that batch is shown

#### Scenario: The answer is recorded against the question that was displayed

- **WHEN** the operator answers
- **THEN** the answer is recorded against the question they were shown

#### Scenario: An answer survives an interruption

- **WHEN** the operator answers part of a batch and their view is reloaded
- **THEN** the answers already given are still recorded, and the batch resumes at the first
  unanswered question

#### Scenario: A held batch says that its answers travel together

- **WHEN** the operator has answered part of a batch whose asker is no longer waiting
- **THEN** the panel states that the answers reach the agent together once the batch is finished

### Requirement: How long an agent waits for the operator is a per-agent setting

Each agent SHALL carry its own limit for how long it waits on a permission decision and on an answer
to a question, and an agent with no limit set SHALL use the system default.

How long a wait is reasonable depends on the agent and on whether the operator is watching. A single
compiled-in number serves neither the agent being supervised closely nor the one left running while
the operator is elsewhere.

#### Scenario: A configured wait governs the run

- **WHEN** an agent with its own waiting limits starts a run
- **THEN** that run waits for the operator for the configured time rather than the default

#### Scenario: An unconfigured agent is unchanged

- **WHEN** an agent with no waiting limits set starts a run
- **THEN** it waits for the system default, exactly as it did before the setting existed

#### Scenario: A limit outside the permitted range is refused

- **WHEN** a waiting limit is set below the minimum or above the maximum
- **THEN** the change is refused and the stored value is unchanged

#### Scenario: An unreadable setting does not break the run

- **WHEN** a run's waiting limit cannot be read or understood
- **THEN** the run uses the default rather than failing

#### Scenario: A run in flight keeps the rules it started under

- **WHEN** an agent's waiting limit is changed while one of its runs is already in progress
- **THEN** that run continues under the limit it started with

### Requirement: Durable per-agent settings are edited on the agent, not in the composer

Settings that belong to an agent rather than to one conversation SHALL be presented on the agent's
own surface, reachable from a conversation without leaving it.

The composer's controls are per-conversation and chosen at the moment of sending. Mixing durable
per-agent configuration into them would make it unclear which choices persist, and adding a third
settings location would make it unclear where to look.

#### Scenario: The operator changes a durable setting mid-conversation

- **WHEN** the operator opens the agent's settings from a conversation
- **THEN** the setting is presented there
- **AND** the conversation is not discarded or reset

#### Scenario: Per-conversation controls stay per-conversation

- **WHEN** the operator views the composer's controls
- **THEN** they offer only choices scoped to that conversation, not durable agent settings

### Requirement: A send to an archived conversation fails with a recoverable instruction

An agent's `send_message` SHALL fail when the recipient's target conversation is archived, and the
failure response MUST carry three things: that the conversation is archived, an instruction to send
to a new conversation instead, and the content the agent submitted, restated verbatim.

Restating the content is the point of the requirement, not a courtesy. A blocked send that returns
only an error forces the agent to reconstruct its own message from a context it may have already
moved past; returning the content makes the retry mechanical.

The archived conversation MUST NOT receive the message, and no inbound queue entry MUST be created
against it. The failure MUST NOT silently redirect the message to a different conversation — the
agent decides where its message goes.

#### Scenario: The failure names the cause and the remedy

- **WHEN** an agent sends a message whose recipient conversation is archived
- **THEN** the send fails
- **AND** the response states that the conversation is archived and instructs the agent to send to a new conversation

#### Scenario: The submitted content is returned

- **WHEN** a send to an archived conversation has failed
- **THEN** the response restates the content the agent submitted, verbatim

#### Scenario: Nothing is written to the archived conversation

- **WHEN** a send to an archived conversation has failed
- **THEN** that conversation has no new message and no new inbound queue entry

#### Scenario: The message is not silently rehomed

- **WHEN** a send to an archived conversation has failed
- **THEN** no other conversation has received the message

#### Scenario: The same contract holds over HTTP and MCP

- **WHEN** the send is attempted over the direct HTTP API and over the MCP adapter
- **THEN** both fail
- **AND** both carry the cause, the instruction, and the restated content

### Requirement: No capability may exist only in a hook

Every rule the system enforces on agent behaviour SHALL be enforced at a boundary the system owns —
the capability plane, the run boundary, or the data model — independently of any runner-specific
hook mechanism.

A runner hook MAY make an already-enforced rule fire **sooner**, at the offending operation rather
than at run end, or **more pleasantly**, as a message inside the agent's own transcript rather than a
rejection after the fact. Removing every hook SHALL leave the identical rule in force, differing only
in when and how it is reported.

Hooks are per-machine, per-user, unevenly shaped across runners, and absent from runners that do not
have them. A capability that lived only in a hook would be missing from a teammate's checkout, would
have to be written twice and drift, and would make any future runner without hooks structurally
second-class. The system already states runner configuration explicitly rather than reading whatever
the host machine's settings say; this requirement holds that line for behavioural rules.

#### Scenario: A rule survives the removal of its hook

- **WHEN** a rule is enforced and every runner-specific hook is removed
- **THEN** the rule is still enforced
- **AND** the only difference is when it fires or how it is reported

#### Scenario: A runner without hooks is not less governed

- **WHEN** an agent runs under a runner that has no hook mechanism
- **THEN** every rule that binds agents under other runners binds it identically

#### Scenario: A new capability cannot be introduced as a hook alone

- **WHEN** a capability is added whose enforcement exists only in a hook
- **THEN** it does not satisfy this requirement

### Requirement: A task named on a delegation is runtime state, not message decoration

When an agent delegates work naming a task, the system SHALL treat that task as state governing the
resulting run, not solely as a field on the delegated message. The named task SHALL be validated
against the delegating run's project at the time of the call.

Attribution of the resulting binding SHALL derive from the authenticated run, as with every other
agent-caused effect; a caller SHALL NOT be able to assert on whose behalf a binding is made.

#### Scenario: A named task governs the receiving run

- **WHEN** an authenticated run delegates work naming a task in its project
- **THEN** the task is carried to the run that receives the delegation
- **AND** it is not only recorded on the message

#### Scenario: A task outside the caller's project is refused

- **WHEN** an authenticated run names a task that does not belong to its project
- **THEN** the call is refused
- **AND** no binding is created

#### Scenario: The binding's origin is the authenticated run

- **WHEN** a binding results from a delegation
- **THEN** the run and agent it is attributed to are the authenticated ones
- **AND** no value supplied by the caller can change that

### Requirement: An agent cannot declare its own work blocked or unblocked

No agent-facing operation — over HTTP or MCP — SHALL move a task into or out of the status meaning
it is waiting on a person. That status SHALL be reached only by the system observing an unanswered
question, or by the operator.

This is the same rule, for the same reason, as an agent's inability to bind its own run or to set
its own task's divergence policy: a state the subject can assert is not a state that constrains it.
Of all the statuses, this is the one an agent under a completion gate has most reason to want — it
is the account that excuses an unfinished task — so it is the one that must be earned by actually
having asked a person something they have not yet answered.

#### Scenario: The agent surface offers no blocking operation

- **WHEN** an agent enumerates the operations available to it
- **THEN** none of them moves a task into or out of the waiting status

#### Scenario: Requesting the status directly is refused

- **WHEN** an agent requests the waiting status for a task through any available operation
- **THEN** the request is refused
- **AND** the task is unchanged

#### Scenario: Asking a real question is the only route

- **WHEN** an agent asks the operator a blocking question and its run ends unanswered
- **THEN** its bound task is recorded as waiting
- **AND** the record identifies the question it is waiting on

### Requirement: The operator may decline a question

The system SHALL let the operator close an outstanding question without answering it, and SHALL
record that they did.

Declining SHALL be available to the operator only. An agent SHALL NOT decline a question, including
one it asked itself: an agent able to close its own question could clear the record of having asked
without anyone having decided anything.

A question that has already been answered SHALL NOT be declinable.

#### Scenario: An outstanding question can be closed unanswered

- **WHEN** the operator declines an outstanding question
- **THEN** the question is no longer outstanding
- **AND** it carries no answer

#### Scenario: An answered question cannot be declined

- **WHEN** a question that has been answered is declined
- **THEN** the request is refused
- **AND** the recorded answer is unchanged

#### Scenario: The agent surface offers no way to decline

- **WHEN** an agent enumerates the operations available to it
- **THEN** none of them declines a question

### Requirement: A waiting agent is told that its question was declined

Where an agent is waiting on a question, the system SHALL end that wait when the question is
declined, rather than leaving it to expire, and SHALL report the decline distinctly from both an
answer and an expiry.

A decline and an expiry mean different things. An expiry means nobody was there; a decline means
someone was there and chose not to answer, which tells the agent the decision is now its own. An
agent left to time out spends the interval waiting for something already decided and then arrives at
a weaker conclusion than the one available.

The report SHALL NOT present a decline as an answer. What an agent does with a decline is its own
judgement, and the system SHALL NOT require any particular response to one.

#### Scenario: A decline ends the wait

- **WHEN** an agent is waiting on a question and the operator declines it
- **THEN** the wait ends without waiting for the expiry
- **AND** the agent is told the question was declined

#### Scenario: A decline is not reported as an answer

- **WHEN** an agent receives the outcome of a declined question
- **THEN** the outcome states that no answer was given
- **AND** it is distinguishable from a question that expired unanswered

#### Scenario: A mixed batch reports each outcome

- **WHEN** an agent asked several questions together and the operator answers some and declines others
- **THEN** each question's outcome is reported individually

### Requirement: An agent can read a specification document

The system SHALL provide an agent with a way to read a specification document, and that capability
SHALL be described in the surface the agent is told it has.

Documents are written into the project's own directory, while a working agent's checkout is an
isolated one branched before the document existed. An agent is therefore told which document governs
its work and, without this, has no way to open it — leaving it to implement from another agent's
paraphrase, with no way to detect divergence from what was approved.

The document SHALL be returned as structured content rather than as its rendered form. The rendering
exists for a person; returning it spends an agent's context on markup and leaves it to re-derive
what the structure already states.

Each requirement returned SHALL carry the identifier the system minted for it, so that an agent
quotes the same identifier that tasks, evidence and gates use.

Acceptance criteria SHALL be returned grouped under the requirement they demonstrate, rather than as
a separate list to be joined by the reader.

Reading SHALL be permitted in every phase. Reading is not authoring, and every gate in this area
governs writing or approving. A capability that is refused depending on state is one an agent
concludes it does not have.

The document's phase SHALL be returned, so that how settled it is can be judged rather than assumed.

Content that cannot be matched to a minted identifier SHALL still be returned, accompanied by a
statement of the problem. A document carrying no structured content SHALL be reported as such rather
than as a document with no requirements.

#### Scenario: An agent reads the document it is implementing

- **WHEN** an agent reads a specification document by path
- **THEN** it receives the requirements with their identifiers, statements and obligations
- **AND** each requirement carries its own acceptance criteria
- **AND** the document's phase is stated

#### Scenario: Reading is allowed before approval

- **WHEN** an agent reads a document that has not been approved
- **THEN** the document is returned
- **AND** its phase says it is not approved

#### Scenario: A document with no structured content is reported honestly

- **WHEN** an agent reads a document carrying no structured content
- **THEN** the response states that, rather than reporting an empty set of requirements

#### Scenario: The capability appears in the described surface

- **WHEN** an agent is told what it can do
- **THEN** reading a specification document is among the capabilities described

### Requirement: A task states what its requirements say

A task SHALL carry, for each requirement it serves, the wording of that requirement as the document
currently states it, alongside its identifier.

An identifier and a location within a document are only actionable by a reader that can open the
document. Carrying the wording makes a task independently actionable, and is what a task's own
description must otherwise duplicate and can then contradict.

The wording SHALL be read from the document rather than stored alongside the requirement's identity,
so that it cannot come to disagree with what the document says.

Reading the wording SHALL NOT be per task: a board serving many tasks from one document SHALL read
that document once.

Where the wording cannot be obtained, the task SHALL still be returned with its identifiers. A task
board SHALL NOT fail because a project's directory is unavailable.

#### Scenario: A task carries its requirements' wording

- **WHEN** a task serving requirements is read
- **THEN** each requirement's current statement is present alongside its identifier

#### Scenario: An unavailable document does not fail the board

- **WHEN** tasks are read and the project's directory cannot be reached
- **THEN** the tasks are returned with their identifiers
- **AND** no error is raised

### Requirement: An agent can record, read and decide requirement evidence

The system SHALL offer agents tools to record evidence against a requirement, to read the evidence a project holds, and to accept or reject it.

Evidence is what opens integration. A system that gates merging on accepted evidence and offers no
way for an agent to produce any has built a pipeline only its operator can drive, one HTTP call at a
time.

Deciding SHALL be a single operation covering both acceptance and rejection. Offering only
acceptance would make rejection unreachable from the agent plane while the underlying operation
allows it, which is the surface disagreement this capability exists to prevent.

Reading SHALL be offered alongside deciding. A decision names a specific piece of evidence, so an
agent with no way to discover what evidence exists cannot decide anything, and the capability to
decide is decorative without it.

The evidence an agent reads SHALL identify who produced it. An agent may not decide evidence it
produced itself, so one that cannot see the producer discovers that rule only by being refused.

Recording SHALL state, where the agent will read it, that evidence is what allows approved work to
merge. The consequence of recording nothing is reported to the operator and never to the agent that
could have prevented it.

Constrained values SHALL be constrained identically on both surfaces, and open ones SHALL stay open.
A tool that accepts less than its route makes the plane narrower than the system, which this
capability forbids in either direction.

#### Scenario: An agent records evidence

- **WHEN** an agent records evidence against a requirement it has satisfied
- **THEN** the evidence is held against that requirement
- **AND** it awaits a decision

#### Scenario: An agent reads what is awaiting a decision

- **WHEN** an agent asks for the evidence a project holds
- **THEN** it receives it, including who produced each piece

#### Scenario: A granted agent accepts another agent's evidence

- **WHEN** an agent the operator has granted acceptance decides evidence another agent produced
- **THEN** the decision is recorded

#### Scenario: An agent cannot decide its own evidence

- **WHEN** an agent decides evidence it produced itself
- **THEN** the system refuses
- **AND** says another agent or the operator decides

#### Scenario: An ungranted agent is refused

- **WHEN** an agent without the grant decides evidence
- **THEN** the system refuses
- **AND** says the capability is the operator's to confer

#### Scenario: Rejection is available

- **WHEN** an agent with the grant rejects evidence
- **THEN** the rejection is recorded, as an acceptance would be

