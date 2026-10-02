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

Direct HTTP SHALL be the application contract. MCP SHALL be a thin adapter over that contract with the same operations, validation, governance, attribution, and typed failure meaning, and the Hub's call command SHALL be that same adapter program run in a call mode rather than a second adapter. An adapter MUST NOT duplicate queue, budget, identity, or lifecycle business rules, MUST NOT hold a governance or waiting rule that the contract does not itself impose on every caller, and MUST NOT silently convert failures into empty or successful results.

Two ways into the one adapter exist because MCP is convenient where it is permitted, and some
environments forbid MCP servers while still allowing a run to execute an ordinary local command.
The call command is the adapter's own program, run once per call, and it reaches the contract with
the run's own credential exactly as the MCP server does. Because it is the same program and not a
restatement of it, an operation, a waiting rule or a failure meaning cannot differ between the two.
The application's command-line interface is **not** one of them: it manages the local application
instance and carries no agent capabilities.

Equal capability is a property of behaviour, not of the route list, and two things broke it until
2026-09-09 in ways a comparison of persisted effects could not see. Both are stated below because
the rule they produced is general, not because either is still open.

A governance rule lives in one adapter and not in the contract: archiving scheduled work always puts
that exact request to the operator, regardless of the run's permission posture, when it is reached
through the adapter and never when it is reached directly. The difference is not in what is
persisted; it is in what the caller is required to do first.

And asking the operator is a call that waits, while the contract offers no way to wait and does not
disclose the deadline it itself stamps on the wait. Everything else that wait depends on is already
the contract's — the answers' order, the distinction between an answer the operator declined to give
and one that never arrived, the parking of the asking run's work, and the report that the wait has
ended — so what is missing is not the semantics but the two facts a direct caller needs to
participate in them. A deadline the system enforces against a caller is a deadline that caller is
entitled to know.

So a rule that governs one adapter's callers governs the contract's callers. Where a rule cannot be
moved, the adapter holding it is not thin and the capability is not equal, and that is a defect
rather than a division of labour.

#### Scenario: One operation has one persisted result

- **WHEN** equivalent valid actions are performed through HTTP, through MCP, and through the call
  command
- **THEN** their persisted effects have equivalent content and attribution

#### Scenario: Failure meaning survives adaptation

- **WHEN** the application API returns validation, denied, not-found, or conflict failure
- **THEN** MCP callers and call-command callers receive the same failure meaning

#### Scenario: A governance rule reaches every caller

- **WHEN** an agent action requires the operator's explicit direction before it takes effect
- **THEN** that direction is required of a caller reaching the action directly over HTTP, on the
  same terms as a caller reaching it through an adapter

#### Scenario: Archiving scheduled work is directed, on either path

- **WHEN** an authenticated run archives a scheduled job
- **THEN** the operator's explicit direction for that job is required first, whichever access path
  the run used
- **AND** a standing allowance to create or manage scheduled work does not satisfy it

#### Scenario: A call that waits, waits for every caller

- **WHEN** an authenticated run asks the operator a question through the capability plane
- **THEN** the contract provides that caller a way to wait for the answers, to receive them in the
  order asked, to tell an answer the operator declined to give from one that never arrived, and to
  report that it has stopped waiting
- **AND** none of these depends on which access path the run used

#### Scenario: The caller is told the deadline it is held to

- **WHEN** a run starts a wait by asking the operator, and the system records when that wait expires
- **AND** the system later judges that run's report of the wait ending against that expiry
- **THEN** the expiry is disclosed to the run that started the wait

#### Scenario: The CLI offers no agent capability

- **WHEN** an agent attempts to affect shared state through the application's own command-line
  interface
- **THEN** no such command exists

#### Scenario: The call command is the adapter's own program

- **WHEN** the operations the call command can perform are listed from the program a run is given
- **THEN** they are exactly the operations the MCP adapter serves, less the endpoint the harness
  itself calls for approvals
- **AND** each is performed by the same code the MCP adapter runs for it

#### Scenario: No full project credential is present

- **WHEN** the Hub starts an agent with either adapter available
- **THEN** the process receives its run credential
- **AND** it does not receive a project/operator API key

### Requirement: A run whose harness cannot use MCP is told how to reach the plane

A turn started without the tool-protocol surface SHALL be told, before the operator's message, that the capability plane is reachable through the Hub's call command, how an operation is called with it, and where the available operations are described, and SHALL NOT be instructed to present the run credential in any command it writes.

The system holds everything such a run needs and, until 2026-09-09, said the opposite. The run
credential and the Hub's own address are placed in the spawned process's environment; the notice
prepended to the turn stated that no AgentWeave tool surface was available and instructed the agent
to report what it would have sent instead. An agent that is authenticated and told it is not will
not try, and the operator saw a turn that declined to do reachable work for a stated reason that was
false.

**Told is not the same as able, and only the first was required until 2026-09-27.** Driven
2026-09-09, no permission posture on a Claude harness let such a run make the HTTP request it was
told to make under its own power: the default `workspace` posture read a URL's path out of the shell
command and refused it as outside the workspace (F300, since fixed), and on the `cli` path
`acceptEdits` has no approver at all, so a command that needs approval is denied for want of anything
to answer it (F301). A measurement on 2026-09-10 corrected F301's first reading: the harness's
refusals were its reasons a command *needs approval*, not reasons it is forbidden, and on a path with
no answerer needing approval is denial.

**Why the HTTP form is no longer what a run is told.** Following it requires the agent to write its
credential, or a reference the shell expands to it, into a command. A harness records the commands a
run executes, and one records them as events the system stores, so the credential ends up in stored
text, which the credential requirement above forbids. And the shell a run is given decides which
forms of a request can be typed at all: measured on Windows PowerShell 5.1, an argument beginning
`@` does not parse, and a JSON argument passed to a program loses its inner quotes. The call command
removes both problems. It reads the credential from its own environment, and it takes its arguments
from a file, so the command a run writes names an operation and a file and nothing else. The HTTP
contract is unchanged, and remains the contract; it is simply not an instruction a run is given.

This is the deployment the equal-capability requirement was written for: MCP forbidden by policy,
ordinary local commands permitted. Capability that exists and is unreachable because it was never
described is not capability.

What is named is a command, never a value. The notice is prepended to the turn prompt, which is the
durable record of the turn, so a credential written into it is a credential written into stored
text.

Where a runner's own sandbox may keep its shell from reaching the Hub, and that has not been
measured, the text says so and tells the run to report an unreachable result rather than retry.
Stating reachability as a fact the system does not know would be the same kind of unfounded claim the
next requirement forbids.

The description of operations is the same description the MCP path is given, rendered for this
access path. It is not a separate list. One source of truth for what the plane offers means an
operation added to the plane cannot be described to one kind of caller and hidden from the other.

#### Scenario: A run without MCP is told the plane is reachable

- **WHEN** a turn begins on an access path that offers no MCP tool surface
- **THEN** the text delivered ahead of the operator's message states that the capability plane is
  reachable through the call command, how an operation's arguments are passed to it, and where the
  operations are described
- **AND** it does not state that the agent has no way to send messages, create or update tasks, or
  ask the operator

#### Scenario: A run whose shell may not reach the Hub is told so

- **WHEN** a turn is described the call command on a runner whose shell sandbox may not allow network
  access to the Hub
- **THEN** the text states that the call command may be unable to reach the Hub from that shell
- **AND** it tells the run to report an unreachable result in its reply rather than retry

#### Scenario: The credential is named and not disclosed

- **WHEN** any text is delivered to a run describing how to reach the plane
- **THEN** it does not contain the credential's value
- **AND** it does not instruct the run to write the credential, or a reference that expands to it,
  into a command

#### Scenario: One description of the operations, two renderings

- **WHEN** an operation is available on the capability plane
- **THEN** a run on an access path with MCP and a run on an access path without MCP are each told
  that operation is available, in the form their access path uses

### Requirement: A run is told the access path it actually has

The system SHALL NOT tell a run that a tool-protocol surface is available unless it has grounds to believe the run's harness will honour the surface it was given, SHALL NOT tell a run that a tool-protocol surface is absent unless it has grounds to believe that it is, and SHALL describe the plane's call command whenever it lacks grounds to believe the surface will be honoured.

Providing a harness with a tool-protocol server is not the same as that harness offering it. A
deployment may forbid tool-protocol servers by policy while permitting ordinary local commands; a
run there receives the configuration, cannot use it, and is told in its first line to call tools
that are not present. That is the same defect as telling a run it has no capability when it does,
and it is the more likely of the two to be met, because it is what an unconfigured run gets.

**The prohibition is symmetric, and it was not.** Until 2026-09-20 this requirement forbade
asserting presence without grounds and said nothing about asserting absence, so a notice that told
every new agent it had no tool-protocol tools was compliant with the words while being false in
fact: the grounds for describing the surface come from a *previous* run of the same agent reporting
its adapter online, and the injection that provides the surface is decided separately and
unconditionally. Every agent's first turn therefore held the tools it was told it did not have.
Absence and presence are the same kind of claim about the same unobserved fact, and neither is
available without grounds. Describing the call command is not an assertion about the tool surface and
remains the correct thing to do whenever there are no grounds to assert the surface — including
when the system has grounds to believe the surface is absent, which is the case where the call
command is the run's only path.

**Grounds are the latest test, not any success.** Until 2026-09-27 one run of an agent whose adapter
had ever reported online was grounds for every later run of that agent, for ever, while each harness
reports on every run whether it started the server. A policy that arrived after the first success was
never noticed. Grounds are now the outcome of the most recent run of the agent that tested it:
the adapter reporting online is a positive test, and a harness's own report that the server failed or
was left out, or a wait for the adapter that ended without it, is a negative one. The harness's own
report outweighs the adapter's, because the adapter reports when its process starts, before the harness
has finished connecting to it. A report the system
does not recognise is not grounds. A run whose harness starts the server before the system sends the
run its first prompt tests itself, and is described from its own result.

This binds every text the system places ahead of the operator's message, not only the first line of
the turn. A run's canonical context is placed there too, and it describes the same operations from
the same decision about the same access path; a claim of absence removed from one and left in the
other has not been removed. Where the system has no grounds either way, neither text asserts, and
both describe.

An explicit statement by the operator about a run's access path remains authoritative, with one
exception. This requirement governs what the system asserts on its own, not what it is told. The
exception is a run that tested itself before its first prompt and found the surface absent: that run
is told the call command, whatever the operator stated, because the statement is about what the agent
is given and usually has, and the run's own test is a measurement of what its harness did this time.
Telling a run tools it has just been measured not to hold is the defect this requirement exists to
prevent. The statement still decides what the run is given, so the next run is given the surface and
tests it again.

Correcting what a run is told must not quietly change what that run may do. The access path decides
more than the wording of a notice today: it decides whether the tool-protocol server is provided at
all, and therefore whether the run's file and shell requests are checked against its workspace or
accepted without a path check. A run moved from one description to a truer one, and thereby from a
checked posture to an unchecked one, has been made less safe by a change about honesty. The
containment a run gets is the operator's to decide, and it is decided separately from what the run
is told.

#### Scenario: A truer description does not silently widen permission

- **WHEN** the system changes which access path it attributes to a run
- **THEN** the containment applied to that run's own file and shell actions is not changed as an
  undeclared consequence of that attribution

#### Scenario: No grounds means no assertion

- **WHEN** a turn begins and the system has no grounds to believe the run's harness will offer the
  tool-protocol surface it was configured with
- **THEN** the text delivered ahead of the operator's message describes reaching the plane through
  the call command
- **AND** it does not state that tool-protocol tools are available

#### Scenario: No grounds means no denial either

- **WHEN** a turn begins and the system has no grounds about whether the run's harness will offer
  the tool-protocol surface it was configured with
- **THEN** the text delivered ahead of the operator's message does not state that the run has no
  tool-protocol tools, for this turn or at all
- **AND** it still describes reaching the plane through the call command

#### Scenario: A run holding the tools is not told it is empty

- **WHEN** a turn begins on a run that was provided a tool-protocol server, and no previous run of
  that agent has reported the server online
- **THEN** the text delivered ahead of the operator's message makes no claim that the tool-protocol
  surface is unavailable
- **AND** the run's canonical context, which is delivered ahead of the operator's message in the
  same turn, makes no such claim either

#### Scenario: A later negative test withdraws earlier grounds

- **WHEN** an earlier run of an agent reported its adapter online
- **AND** a later run of that agent was tested and its harness did not start the server
- **THEN** the next turn of that agent that is described from history is described with the call
  command

#### Scenario: A report the system does not recognise is not grounds

- **WHEN** a harness reports the server's state with a value the system does not recognise
- **THEN** that run does not give grounds to describe the tool-protocol surface

#### Scenario: A run that tests itself is described from its own result

- **WHEN** a run's harness starts the tool-protocol server before the system sends that run its
  first prompt
- **THEN** the system waits, for a bounded time, for that run's adapter to report online
- **AND** the run's first prompt describes the tool-protocol surface if it did, and the call command
  if it did not, whatever earlier runs of the agent reported

#### Scenario: The operator's own statement is honoured

- **WHEN** the operator has stated which access path a run uses
- **AND** the run did not test itself before its first prompt and find the surface absent
- **THEN** that statement decides the access path

#### Scenario: A run's own negative test outweighs the operator's statement for that run

- **WHEN** the operator has stated that an agent uses the tool-protocol surface
- **AND** a run of that agent tests itself before its first prompt and its adapter does not report
  online within the wait
- **THEN** that run's first prompt describes the call command
- **AND** the next run of that agent is still given the tool-protocol server

### Requirement: Operator-facing severity values are the ones the operator's view understands

Events persisted for the operator's attention SHALL use the severity vocabulary the operator's views
filter and style by. The persistence layer SHALL enforce this by normalising any severity value
against an enumerated set before writing, rather than relying on every caller to pass an already-
correct value. Any live notification of the same event, such as a real-time broadcast to connected
views, SHALL carry the same normalised value, not the caller's original string.

A severity that no view recognises is worse than none: the row renders unmarked and is hidden by the
filter intended to reveal it, so the events most needing attention are the ones least likely to be
seen.

#### Scenario: A refused action is recorded

- **WHEN** the system records that an agent's action was refused
- **THEN** the stored severity is one the operator's activity view filters and styles by

#### Scenario: A caller supplies a severity outside the enumerated set

- **WHEN** any caller, internal or external, persists an event with a severity value that is not in
  the enumerated set the operator's views understand
- **THEN** the value that is actually written is a value from the enumerated set, not the caller's
  original string

#### Scenario: An externally-submitted event cannot bypass the vocabulary

- **WHEN** an event is submitted through an API that accepts a caller-supplied severity string
- **THEN** the same normalisation applies as for events persisted from within the system

#### Scenario: A live broadcast matches the persisted value

- **WHEN** an event with a severity outside the enumerated set is submitted through an API that both
  persists the event and broadcasts it to connected views in real time
- **THEN** the severity carried by the broadcast is the same normalised value that was written, not
  the caller's original string

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

### Requirement: Document creation is a plane operation with the plane's identity rules

Creating a specification document SHALL be offered on the agent capability plane under the same
terms as every other effect: authenticated by the run credential, attributed to the run, and refusing
any identity supplied by the caller.

It SHALL be reachable identically over HTTP and MCP, so that a client using one is not offered a
capability a client using the other lacks.

#### Scenario: An unauthenticated creation is refused

- **WHEN** document creation is called without a valid run credential
- **THEN** it is refused

#### Scenario: A creation is attributed to the calling run

- **WHEN** an agent creates a document
- **THEN** the resulting record attributes the creation to that run

#### Scenario: The operation exists on both surfaces

- **WHEN** the plane's operations are enumerated
- **THEN** document creation appears over both HTTP and MCP

### Requirement: Creating a document is not gated by a standing project allowance

Document creation SHALL be available to an agent without an operator first enabling it for the
project.

The plane already distinguishes two classes of effect. Scheduled jobs require a standing allowance
because a job is an instruction that invokes a model repeatedly, so an agent that creates one commits
spend the operator did not authorise per occurrence. Tasks, messages, questions and evidence require
none, because they cost nothing to hold and nothing to discard. A document belongs to the second
class.

A capability disabled by default is a capability that is never exercised, and the failure this
allowance would guard against — volume — has no evidence behind it yet.

#### Scenario: Creation works in a project with agent jobs disabled

- **WHEN** an agent creates a document in a project where scheduled agent jobs are not allowed
- **THEN** the creation succeeds

### Requirement: A capability refused for project state reaches the operator durably

Where the Hub refuses an agent capability because of project-level state the agent cannot itself change, it SHALL open a record of that refusal on an operator surface that outlives the refused run, and that record SHALL name the state, its current value, what changing it would allow, and where the operator changes it.

A refusal that exists only in the agent's own transcript reaches nobody. Measured on the operator's
own flow: an agent was refused `create_flow` because scheduled agent work was not allowed for the
project, the project's permission requests held **zero rows**, and the operator — who had said they
were leaving — returned to nothing. The agent fell back to hand-driven messages 37 seconds later and
no task in the flow ever reached approval.

The record SHALL NOT be one whose lifetime is bounded by the refused run or by a waiting caller's
deadline. The state that caused the refusal is true or false independently of any turn, so a record
that is swept when the run ends cannot carry the decision it exists to obtain.

The record SHALL NOT be bound to the refused run's conversation, and SHALL NOT cause any surface to
report that the refused run, its conversation or its loop is waiting on the operator. The refused
call does not wait, so nothing about it is waiting; a record that says otherwise is the same false
statement in a different place.

The operator's answer SHALL be delivered to the agent that was refused, and that agent SHALL be woken
for it, even when the run that was refused has already ended.

The Hub SHALL NOT infer from an answer's text whether the operator agreed. The operator is never
confined to a record's offered answers, so an answer's intent is not a thing the Hub can read; the
refusal SHALL instead report what the operator said.

Where the most recent record for that state has been resolved — answered or declined — the Hub
SHALL open at most one further record for it, and that further record SHALL state that it is the
last the Hub will open. Once a record opened that way is itself resolved, the Hub SHALL NOT open
another for that state. A decision the operator has given twice is settled; a decision they gave
once may have been given in error, and an offered answer written in the past tense can be read as
an instruction to act rather than a report that they have. The bound SHALL be derived from how many
records exist for that state, never from what any answer said.

Where the record cannot be opened, the refusal SHALL still be returned, and SHALL name the state,
its value and where it is changed, without claiming a record was opened or that the operator has
been asked. Losing the record is a degradation; losing the refusal would leave the caller with less
than it had before this requirement existed.

The refused call SHALL NOT wait for the answer, and the caller SHALL NOT be instructed to poll for
it. A decision that may arrive after the run has ended cannot be waited for inside the run.

The record and its delivery SHALL be the same whichever access path the refused call used, and no
adapter SHALL hold any part of this rule.

#### Scenario: The first refusal opens the record

- **WHEN** an authenticated run's call is refused because scheduled agent work is not allowed for the
  project
- **THEN** a question of record is opened for the operator, attributed to the refused agent, naming
  the setting, its current value, what enabling it would allow, and where it is changed
- **AND** an event is broadcast so the operator's view updates without a reload
- **AND** the refusal returned to the caller carries that record's identifier

#### Scenario: The record outlives the run

- **WHEN** the run that was refused ends before the operator has answered
- **THEN** the record remains open and unanswered on the operator's surface

#### Scenario: An answer given after the run has ended reaches the agent

- **WHEN** the operator answers the record after the refused run has ended
- **THEN** the answer is queued for the agent that was refused and that agent is woken for it

#### Scenario: The refused call does not wait

- **WHEN** the call is refused for that state
- **THEN** the refusal is returned immediately, and it does not instruct the caller to poll or to
  repeat the call once a decision exists

#### Scenario: A second refusal opens no second record

- **WHEN** a further call is refused for the same project state while the record is still unanswered
- **THEN** no second record is opened, and the refusal carries the existing record's identifier

#### Scenario: Refusals arriving together open one record between them

- **WHEN** two calls are refused for the same project state at the same moment, each finding no
  existing record before either has opened one
- **THEN** exactly one record exists for that state afterwards, and both refusals carry its
  identifier

#### Scenario: A resolved record is superseded once

- **WHEN** the operator has resolved the most recent record for that state — by choosing an offered
  answer, by writing their own, or by declining it
- **AND** a further call is refused for that state
- **THEN** one further record is opened, reporting what the operator said and stating that it is the
  last the Hub will open for that state

#### Scenario: The bound is two, however the answers were given

- **WHEN** the record opened after a resolution has itself been resolved
- **AND** a further call is refused for that state
- **THEN** no new record is opened, and the refusal reports what the operator said without claiming
  they have been asked again

#### Scenario: A written answer is bounded the same way as a chosen one

- **WHEN** the operator answers a record in their own words rather than by choosing an offered
  answer
- **AND** a further call is refused for that state
- **THEN** the same record is opened, or not opened, as it would have been had they chosen an
  offered answer

#### Scenario: The refusal reports the answer rather than judging it

- **WHEN** a call is refused for a state whose record the operator has already answered
- **THEN** the refusal carries the operator's own answer, and does not assert that they agreed or
  refused

#### Scenario: Only the agent that was refused first is woken

- **WHEN** a second agent is refused for the same state while one record is open, and the operator
  then answers it
- **THEN** the answer is delivered to the agent named on the record, and the second agent is not woken
  by it

#### Scenario: The refused run is not reported as waiting

- **WHEN** a record has been opened for that state and the refused run is still working
- **THEN** no surface reports that run, its conversation or its loop as waiting on the operator
- **AND** no surface reports the refused **agent** as waiting on the operator on account of that
  record
- **AND** the record is still open on the operator's surface

#### Scenario: The refusal survives the record failing to open

- **WHEN** a call is refused for that state and the record cannot be opened
- **THEN** the refusal is still returned, naming the state, its value and where the operator changes
  it
- **AND** it carries no record identifier and does not claim the operator has been asked
- **AND** it tells the caller to raise the state with the operator rather than to poll or repeat the
  call

#### Scenario: An operator's own call opens nothing

- **WHEN** the same call is made by the operator rather than by an authenticated run
- **THEN** it is not gated by that state and no record is opened

#### Scenario: The record is the same on either access path

- **WHEN** equivalent calls are refused for that state over HTTP and through an adapter
- **THEN** the record opened, the event broadcast and the failure's meaning are equivalent

### Requirement: A refusal names the state that caused it, never an approval nobody requested

A refusal caused by project-level state SHALL name that state and its current value, and SHALL NOT describe an approval, allowance or decision that the system has not actually opened.

The shipped sentence — *"Scheduled work from agents requires operator approval or an enabled
allowance"* — is false in both halves: no approval is requested, and *"an enabled allowance"* names
nothing the agent can locate or ask for. An agent reading it is told to wait for something nobody was
asked for, which is worse than a plain refusal because it sends the operator looking for an approval
that was never going to arrive.

The refusal SHALL carry a machine-readable code, and the identifier of the record where one was
opened, in addition to the sentence, so a caller need not parse prose to know a decision is pending.

The record's identifier SHALL also appear in the sentence itself. A structured refusal body is
available to an adapter, but only the sentence reaches the agent whose turn was refused, so anything
that agent must know cannot live in the structure alone.

Where no record was opened, the refusal SHALL say so plainly rather than omitting the identifier
silently. A sentence that names a record the caller cannot find is the same class of falsehood as
the sentence this requirement replaces.

The refusal SHALL state what the caller may do instead, and SHALL state that the operator's answer
will arrive as input rather than as a result of this call.

#### Scenario: The refusal names the setting and its value

- **WHEN** a call is refused because scheduled agent work is not allowed for the project
- **THEN** the refusal names that setting and its current value

#### Scenario: The refusal does not promise an approval that was not opened

- **WHEN** a refusal is returned for that state
- **THEN** it does not claim that an approval or allowance decision is available unless a record for
  it has been opened

#### Scenario: The refusal is machine-readable as well as readable

- **WHEN** a refusal is returned for that state and a record was opened
- **THEN** its body carries a code naming the kind of refusal and that record's identifier
- **AND** an adapter's caller receives the sentence intact

#### Scenario: The sentence alone is enough to act on

- **WHEN** an agent reached the refused call through an adapter that surfaces only the failure's
  sentence
- **THEN** that sentence names the state, the record opened for the operator, and that the call must
  not be polled or repeated

#### Scenario: A refusal with no record still names what to do

- **WHEN** a refusal is returned for that state and no record was opened
- **THEN** its body carries the code and no record identifier
- **AND** the sentence names the state and tells the caller to raise it with the operator directly

### Requirement: A message addressed to the operator is refused with where the operator reads

A message an agent addresses to a reserved operator name SHALL be refused with a reason that states the operator is not a message recipient and names the ways an agent does reach the operator.

The operator is not on the roster, and no agent can hold the names reserved for them, so such a
message is never a mistyped peer. A refusal that says only "no agent by that name" leaves the agent to
guess another name.

The reason SHALL say that the agent's reply is what the operator reads in the conversation, that a
result can be recorded on a task through its notes, and that a question needing the operator's answer
goes through the question tool. The system SHALL NOT add any mechanism that reads an agent's text to
decide it was addressed to the operator.

#### Scenario: An agent addresses the operator

- **WHEN** an agent sends a message whose recipient is a reserved operator name, in any letter case
- **THEN** the message is refused and nothing is queued
- **AND** the reason names the reply, the task notes and the question tool

#### Scenario: A mistyped peer is still told it is unknown

- **WHEN** an agent sends a message to a name that is neither an agent nor reserved
- **THEN** the refusal says no agent by that name exists, as before

### Requirement: An agent writes to a task only the fields its tool carries

An agent's update of a task SHALL accept the task's status, its notes and the requirements it serves, and SHALL refuse, before changing anything, any other field an operator may set, whichever access path the agent uses.

Who holds a task, its priority and its description are the operator's statements about the work.
An agent able to set the holder could take another agent's work, or name itself on finished work in
the same request that sends it to review. The tool an agent is given has never offered these fields,
and a direct request that could write them was a capability the adapter did not have.

The refusal SHALL name the fields it refused and say that an agent moves its task with status and
notes and links it to the requirements it serves. The question tool and the message tool are
unaffected.

An agent SHALL be able to link its task to a requirement without restating the task's status, over
either access path: a status an agent may not set (a block is observed, never asserted by an agent)
must not stand between it and a link it may record.

#### Scenario: An agent tries to take a task

- **WHEN** an agent's run updates a task naming a new holder, over either access path
- **THEN** the update is refused and the task is unchanged, including any status the same request asked for
- **AND** the refusal names the holder field

#### Scenario: An agent links its task to a requirement

- **WHEN** an agent's run updates its task naming a requirement the project declares
- **THEN** the link is recorded as that agent's, over either access path

#### Scenario: An agent links a requirement without moving its task

- **GIVEN** an agent's task that is blocked
- **WHEN** the agent's run links the task to a requirement and names no status
- **THEN** the link is recorded as that agent's
- **AND** the task's status and its reason for being blocked are unchanged

#### Scenario: The operator is unaffected

- **WHEN** the operator updates a task's holder, priority or description
- **THEN** the update is applied as before

### Requirement: A run's tool surface, approval channel and plane access are decided separately

For every run, the Hub SHALL resolve three separate values, and SHALL take the run's approval channel from the transport the run uses rather than from whether the Hub's tool server is provided, except where that channel is carried by the tool server. The three values are: whether the Hub's tool server is provided to the run (its tool surface), which channel, if any, lets the Hub answer the run's tool calls (its approval channel), and how the run is given access to the capability plane (its plane access). The plane access is over the tool protocol exactly when the tool server is provided.

A single value used to answer all three. For some runners the three move together. For others they do not:
- A peer that asks the Hub over its own protocol can have its calls approved whether or not the Hub's tool server
  was provided to it.
- A harness whose only approver is a tool on the Hub's tool server cannot.

A run's approval channel SHALL be withdrawn by a change to its tool surface **only** where that channel is carried by
the tool surface. The operator's statement that a run has no tool-protocol surface SHALL remove the tool server. It
SHALL NOT remove an approval channel that does not depend on the tool server.

A run's permission posture at rest SHALL be decided from its approval channel. A posture that names the Hub as the
answerer SHALL be the default only where the run has an approval channel. What the run is told about its access
remains decided separately, from grounds, as before. Resolving these three values SHALL NOT widen any run's
containment.

#### Scenario: A harness whose approver is a Hub tool loses it with the tool server

- **WHEN** the operator states that a Claude run has no tool-protocol surface
- **THEN** that run is given no tool server and no approval channel
- **AND** its default posture is the one that needs no answerer

#### Scenario: A peer that asks over its own protocol keeps its approvals

- **WHEN** the operator states that a Codex run on its app-server transport has no tool-protocol surface
- **THEN** that run is given no tool server
- **AND** the Hub still answers that run's approval requests under the posture the operator chose

#### Scenario: A transport with no live approvals has no approval channel

- **WHEN** a Codex run uses its exec transport
- **THEN** its approval channel is none, whatever its tool surface is

#### Scenario: The default case is unchanged

- **WHEN** a Claude run, or a Codex run on its app-server transport, starts with no statement from the operator about
  its access
- **THEN** it is given the tool server, an approval channel, and plane access over the tool protocol, exactly as before
  the values were separated

### Requirement: Whether a run's harness started the Hub's tool server is recorded per run

For every run given the Hub's tool-protocol server, the system SHALL record whether that run's harness started it, as one of started, failed, or left out, letting the harness's own recognised report decide over the adapter reporting online and the adapter reporting online decide over a wait that ended without it, in whatever order they arrive, and SHALL record for every run which surface the run was told to reach the plane through.

The adapter reports online as soon as its process starts, before the harness has finished connecting
to it. That proves the harness started the program, not that the harness offers its tools: a harness
that started the server and then failed to connect to it has already produced that report. So the
harness's own account of the server, where it gives one the system recognises, is what the run is
recorded by, and the adapter's report decides only where the harness says nothing recognisable. A
positive that could never be withdrawn by the harness's own later failure would be the permanent
grounds this requirement exists to remove, rebuilt one level down.

Only the harness starting the program may produce the adapter's report: the call command is the same
program, started by the run rather than by its harness, and a call through it reports nothing about
the server. A run that ended before any source could report was not tested, and is recorded as
untested rather than as a negative. Recording never fails the run it records.

A runner that has no way to report a negative keeps its last recorded test, which may be an old
positive. That is stated rather than guessed around: for such a runner a guessed negative would point
the run at a path its own sandbox may not let it use.

#### Scenario: The adapter reporting online records a positive test

- **WHEN** the adapter of a run that was given the server reports online
- **THEN** that run is recorded as having started the server

#### Scenario: The harness leaving the server out records a negative test

- **WHEN** a run's harness reports the servers it started and the Hub's server is not among them
- **THEN** that run is recorded as having left the server out

#### Scenario: The harness's own failure outweighs the adapter's report

- **WHEN** a run's adapter reports online and that run's harness reports that the server failed, in
  either order
- **THEN** that run is recorded as failed

#### Scenario: A run that never reached its harness's report is untested

- **WHEN** a run ends before its harness reported its servers and before its adapter reported online
- **THEN** that run is recorded as untested
- **AND** it does not count as the latest test of its agent

#### Scenario: A call through the call command is not a positive test

- **WHEN** a run whose harness did not start the tool-protocol server calls an operation through the
  call command
- **THEN** that run is not recorded as having started the server

#### Scenario: The surface a run was told is recorded

- **WHEN** a run's first prompt is composed
- **THEN** the run records whether it was told the tool-protocol surface or the call command

### Requirement: The call command carries the run's authority without showing it

The call command SHALL read the run's credential and the Hub's address from its own process environment only, SHALL NOT accept either as an argument or from a file, and SHALL take an operation's arguments from a file the run names, never from the command line.

A run that needs its credential in a command puts it into text the harness records. A command that
reads it from its own environment leaves the command naming only an operation and a file of
arguments, and the harness's record of that command holds no secret.

#### Scenario: A call writes no secret into the command

- **WHEN** a run calls an operation through the call command
- **THEN** the command the run executed contains no credential and no reference that expands to one

#### Scenario: A call without a run credential is refused before any request

- **WHEN** the call command runs in a process whose environment holds no run credential
- **THEN** it reports that the call is not bound to a run, and makes no request

#### Scenario: A refusal keeps its meaning

- **WHEN** the Hub refuses an operation called through the call command
- **THEN** the command reports the refusal's status and reason in a form the run can read, and exits
  unsuccessfully

#### Scenario: A question waits through the call command

- **WHEN** a run asks the operator a blocking question through the call command
- **THEN** the command waits for the answers on the same terms as the tool-protocol adapter, and
  reports the wait ended when its deadline passes unanswered

