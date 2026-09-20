<!--
R2 (2026-09-20). Two corrections to this delta, recorded here rather than in the requirement prose
because this file's requirement bodies become the corpus at archive time and process notes must not.

1. The first requirement's third SHALL clause. R1 rewrote the live text "and SHALL describe the
   plane's direct HTTP form instead when it has no such grounds" as "when it has grounds for
   neither". That silently narrowed a surviving obligation: once grounds for *absence* exist
   (design D3 names F340 as the change that would obtain them), "grounds for neither" is false and
   the HTTP-form obligation lapses -- in exactly the case where HTTP is the run's only path.
   Restored to the live breadth as "whenever it lacks grounds to believe the surface will be
   honoured", which is the live semantics plus the new absence clause, and nothing else.

2. The scope sentence added to the symmetry paragraph. The prohibition has to bind every text the
   system places ahead of the operator's message, not only the turn-start notice, because the run's
   canonical context carries the same claim from the same value and reaches the model the same way
   (proposal Impact; design D6).

Diffed clause by clause and scenario by scenario against openspec/specs/agent-capability-plane/
spec.md: both requirement headers match exactly, the second requirement's SHALL line is
byte-identical to the live one, all three of the first requirement's live scenarios and all three of
the second's survive verbatim, and nothing else was dropped or reworded.
-->

## MODIFIED Requirements

### Requirement: A run is told the access path it actually has

The system SHALL NOT tell a run that a tool-protocol surface is available unless it has grounds to believe the run's harness will honour the surface it was given, SHALL NOT tell a run that a tool-protocol surface is absent unless it has grounds to believe that it is, and SHALL describe the plane's direct HTTP form whenever it lacks grounds to believe the surface will be honoured.

Providing a harness with a tool-protocol server is not the same as that harness offering it. A
deployment may forbid tool-protocol servers by policy while permitting ordinary local API calls; a
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
available without grounds. Describing the HTTP form is not an assertion about the tool surface and
remains the correct thing to do whenever there are no grounds to assert the surface — including
when the system has grounds to believe the surface is absent, which is the case where the HTTP form
is the run's only path.

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
- **THEN** the text delivered ahead of the operator's message describes reaching the plane over HTTP
- **AND** it does not state that tool-protocol tools are available

#### Scenario: No grounds means no denial either

- **WHEN** a turn begins and the system has no grounds about whether the run's harness will offer
  the tool-protocol surface it was configured with
- **THEN** the text delivered ahead of the operator's message does not state that the run has no
  tool-protocol tools, for this turn or at all
- **AND** it still describes reaching the plane over HTTP

#### Scenario: A run holding the tools is not told it is empty

- **WHEN** a turn begins on a run that was provided a tool-protocol server, and no previous run of
  that agent has reported the server online
- **THEN** the text delivered ahead of the operator's message makes no claim that the tool-protocol
  surface is unavailable
- **AND** the run's canonical context, which is delivered ahead of the operator's message in the
  same turn, makes no such claim either

#### Scenario: The operator's own statement is honoured

- **WHEN** the operator has stated which access path a run uses
- **THEN** that statement decides the access path

### Requirement: A run whose harness cannot use MCP is told how to reach the plane

A turn started on an access path without MCP SHALL be told, before the operator's message, that the capability plane is reachable over HTTP, and SHALL be told the plane's base address, the name of the environment variable holding its run credential, how that credential is presented, and where the available operations are described.

The system holds everything such a run needs and, until 2026-09-09, said the opposite. The run
credential and the Hub's own address are placed in the spawned process's environment; the notice
prepended to the turn stated that no AgentWeave tool surface was available and instructed the agent
to report what it would have sent instead. An agent that is authenticated and told it is not will
not try, and the operator saw a turn that declined to do reachable work for a stated reason that was
false.

**Told is not the same as able, and only the first is required here.** Driven 2026-09-09, no
permission posture on a Claude harness let such a run make the request under its own power: the
default `workspace` posture read a URL's path out of the shell command and refused it as outside
the workspace (F300), and on the `cli` path `acceptEdits` has no approver at all, so a command that
needs approval is denied for want of anything to answer it (F301). **The reason recorded for F301
was wrong and is corrected here.** It read that the harness *statically refuses* an interpolated
credential; measurement on 2026-09-10 refuted that — with the approval gate removed those same
commands execute, and a bare literal request naming no variable at all is denied identically. The
refusals are the harness's reasons a command *needs approval*, not reasons it is forbidden, and on
a path with no answerer needing approval is denial. The conclusion is unchanged: unreachable by the
agent's own tools on the `cli` path.

The first of those no longer holds where the `workspace` posture's approver runs. A run is told this
HTTP form on its first turn, before the system has grounds to describe MCP, while that posture is
deciding its shell commands, and a shell command naming the run's own Hub address is now allowed
there (`agent-run-sandboxing`, *"A network address in a shell command is decided as a network
address"*). The plane is genuinely reachable from that process environment — the MCP adapter reaches
it from exactly there — so the notice is true.

This is the deployment the equal-capability requirement was written for: MCP forbidden by policy,
ordinary local API calls permitted. Capability that exists and is unreachable because it was never
described is not capability.

What is named is a variable, never a value. The notice is prepended to the turn prompt, which is the
durable record of the turn, so a credential written into it is a credential written into stored
text. The agent can already read its own environment, so naming the variable discloses nothing it
does not hold; interpolating the value would breach the credential requirement above.

The description of operations is the same description the MCP path is given, rendered for this
access path. It is not a separate list. One source of truth for what the plane offers means an
operation added to the plane cannot be described to one kind of caller and hidden from the other.

#### Scenario: A run without MCP is told the plane is reachable

- **WHEN** a turn begins on an access path that offers no MCP tool surface
- **THEN** the text delivered ahead of the operator's message states that the capability plane is
  reachable, and identifies the plane's base address, the environment variable holding the run
  credential, how that credential is presented on a request, and where the operations are described
- **AND** it does not state that the agent has no way to send messages, create or update tasks, or
  ask the operator

#### Scenario: The credential is named and not disclosed

- **WHEN** any text is delivered to a run describing how to reach the plane
- **THEN** it contains the name of the environment variable holding the run credential
- **AND** it does not contain the credential's value

#### Scenario: One description of the operations, two renderings

- **WHEN** an operation is available on the capability plane
- **THEN** a run on an access path with MCP and a run on an access path without MCP are each told
  that operation is available, in the form their access path uses
