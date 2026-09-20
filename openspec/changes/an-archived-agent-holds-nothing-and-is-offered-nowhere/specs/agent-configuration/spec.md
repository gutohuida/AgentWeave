## MODIFIED Requirements

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
conversation, as a message recipient, as a task assignee, and in any report of which agents can be
launched. It MUST nonetheless remain reachable when explicitly asked for, because its own
configuration is where unarchiving happens — an agent that could be archived but never found again
would be deleted in all but name.

**Archival SHALL release the agent's charter binding.** A charter is instruction for turns the
agent takes, and nothing runs an archived agent, so a charter left bound governs nothing. What it
does instead is hold the charter hostage: a charter held only by an archived agent cannot be
deleted, and the refusal names an agent the default roster does not show, so the operator is
stopped by a name they cannot find. The release SHALL happen where an agent becomes archived, not
at each reader of the binding — a reader-by-reader filter leaves the next reader to be found by an
operator.

**An agent that was archived before this behaviour existed SHALL be indistinguishable from one
archived after it.** Releasing the binding only for future archivals would leave the defect
standing on exactly the databases where it was met.

**Archiving SHALL state which charter it released**, and **unarchiving SHALL state that no charter
is bound and that archival is why.** Reopening MUST NOT restore the binding, so the product SHALL
say so rather than leaving the operator to discover it at the agent's next turn. The sentence
unarchiving states MUST be true of an agent that never had a charter bound: it states the rule and
the agent's current state, and MUST NOT assert that this agent's charter was removed. It MUST NOT
imply that a charter is required before the agent can run, because an agent with no charter is
fully usable, and it MUST state that unarchiving does not restore the released binding rather than
leaving that to be inferred from the rule.

**Archiving and unarchiving SHALL each be recorded as an event, and SHALL each be announced to open
clients.** A response body is read by the client that made the request and by nobody else, so a fate
stated only there is stated to one reader and then lost — and the released charter's identity exists
nowhere else once the binding is cleared. Recording SHALL NOT depend on any client reading the
response, and SHALL happen whether or not a charter was bound, so that "no charter was released" is
a recorded fact rather than an absence. The announcement is what tells a second open client its
roster changed; every other agent lifecycle transition already makes one, and archival is the one
that does not. Recording a transition is not the same as displaying it: a client that does not
recognise the announcement SHALL be unaffected by it, and rendering the transition where an operator
reads it is not required here.

**Binding a charter to an archived agent SHALL be refused, naming unarchiving as the repair.**
Releasing the binding at archival is undone by any route that can re-bind one afterwards, and the
agent's own configuration offers exactly that. Clearing a binding SHALL remain permitted on an
archived agent, because clearing is not re-binding and refusing it would break a repair the product
already names.

An agent's runner binding SHALL NOT be released by archival. The reason is the display and not a
difference in the bindings' meaning: an archived agent's configuration reports the runner and model
it was bound to, that report is derived from the live binding and from nothing else, and releasing
it would blank what the agent was configured to run on the one surface that still shows it. Each run's own
accounting outcome separately records what it ran on — completely for a measured turn, and as much
as could be determined for one that ended without telemetry — and archival does not touch those
records.

A consequence of holding the runner binding SHALL be carried rather than hidden: an archived agent
can still be named as a runner's holder, which is why the runner-deletion refusal is required to
qualify it (see `runner-registry`).

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

#### Scenario: Archiving releases the charter binding

- **WHEN** an operator archives an agent bound to a charter
- **THEN** the agent holds no charter afterwards
- **AND** the response names the charter it released

#### Scenario: A charter held only by an archived agent can be deleted

- **WHEN** an operator deletes a charter whose only holder has been archived
- **THEN** the charter is deleted
- **AND** no refusal names the archived agent

#### Scenario: An agent archived before the release behaviour existed holds no charter either

- **WHEN** the Hub starts against a database holding an agent archived with a charter still bound
- **THEN** that agent holds no charter
- **AND** its charter can be deleted without unbinding anything by hand

#### Scenario: Unarchiving says no charter is bound

- **WHEN** an archived agent is unarchived
- **THEN** the response states that no charter is bound and that archiving releases one
- **AND** the response states that unarchiving does not restore the released binding
- **AND** the response does not require a charter to be bound before the agent can run
- **AND** the binding the agent held before archival is not restored

#### Scenario: An agent that never had a charter is not told one was removed

- **WHEN** an agent that was never bound to a charter is unarchived
- **THEN** every clause of the response is true of that agent
- **AND** nothing in it asserts that this agent's charter was released

#### Scenario: A charter cannot be bound to an archived agent

- **WHEN** an operator binds a charter to an archived agent
- **THEN** the request is refused with unarchiving named as the repair
- **AND** the agent still holds no charter

#### Scenario: Clearing a binding on an archived agent is still allowed

- **WHEN** an archived agent's charter binding is set to none
- **THEN** the request succeeds

#### Scenario: Archiving records what it released

- **WHEN** an agent is archived
- **THEN** the Hub records an event for the transition, naming the agent and the charter released
- **AND** the event is recorded whether or not a charter was bound
- **AND** the recorded fact does not depend on any client reading the response

#### Scenario: Unarchiving records the transition too

- **WHEN** an archived agent is unarchived
- **THEN** the Hub records an event for the transition, naming the agent
- **AND** the event does not assert that a charter was restored

#### Scenario: Another open client is told the roster changed

- **WHEN** an agent is archived or unarchived while a second client has the project open
- **THEN** the Hub announces the transition to that client
- **AND** a client that does not recognise the announcement is unaffected by it

#### Scenario: Archival does not release the runner binding

- **WHEN** an agent bound to a runner is archived
- **THEN** its configuration still reports the runner and model it was bound to

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
