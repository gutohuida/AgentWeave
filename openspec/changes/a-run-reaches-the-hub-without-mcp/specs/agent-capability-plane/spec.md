## MODIFIED Requirements

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

#### Scenario: The application's CLI offers no agent capability

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
was left out, or a wait for the adapter that ended without it, is a negative one. A report the system
does not recognise is not grounds. A run whose harness starts the server before the system sends the
run its first prompt tests itself, and is described from its own result.

This binds every text the system places ahead of the operator's message, not only the first line of
the turn. A run's canonical context is placed there too, and it describes the same operations from
the same decision about the same access path; a claim of absence removed from one and left in the
other has not been removed. Where the system has no grounds either way, neither text asserts, and
both describe.

An explicit statement by the operator about a run's access path remains authoritative. This
requirement governs what the system asserts on its own, not what it is told.

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
- **THEN** that statement decides the access path

## ADDED Requirements

### Requirement: Whether a run's harness started the Hub's tool server is recorded per run

For every run given the Hub's tool-protocol server, the system SHALL record whether that run's harness started it, as one of started, failed, or left out, from the first source that reports it, and SHALL record for every run which surface the run was told to reach the plane through.

A positive report is final for the run: the adapter reporting online is direct evidence that the
harness started the program, and a slower source that later says otherwise does not overwrite it.
Because it is final, only the harness starting the program may make it: the call command is the same
program, started by the run rather than by its harness, and a call through it reports nothing about
the server. A
negative record may still become positive if the adapter reports online late. A run that ended before
any source could report was not tested, and is recorded as untested rather than as a negative.

#### Scenario: The adapter reporting online records a positive test

- **WHEN** the adapter of a run that was given the server reports online
- **THEN** that run is recorded as having started the server

#### Scenario: The harness leaving the server out records a negative test

- **WHEN** a run's harness reports the servers it started and the Hub's server is not among them
- **THEN** that run is recorded as having left the server out

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
