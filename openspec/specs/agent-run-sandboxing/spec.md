# agent-run-sandboxing

## Purpose

Defines the sandbox posture the Hub imposes on a spawned agent run, independent of whatever
configuration happens to exist on the machine the Hub process runs on. Originated by
`openspec/changes/2026-08-06-claude-non-yolo-permission-mode`.

## Requirements

### Requirement: A non-yolo Claude run's sandbox posture is set by the Hub, not the host machine

The Hub SHALL pass an explicit, non-bypass permission mode to every non-yolo Claude run it spawns. A
non-yolo Claude run's actual permission behavior MUST NOT depend on the config file of the machine the
Hub process happens to run on.

#### Scenario: Non-yolo Claude run gets an explicit permission mode

- **WHEN** the Hub spawns a Claude agent whose run is not `yolo`
- **THEN** the spawned command line includes an explicit non-bypass permission mode flag

#### Scenario: Yolo Claude run is unaffected

- **WHEN** the Hub spawns a Claude agent whose run is `yolo`
- **THEN** the spawned command line includes `--dangerously-skip-permissions`
- **AND** does not include the non-yolo permission mode flag

### Requirement: A sandboxed non-yolo Claude agent can still use the Hub's own MCP tools

When a non-yolo Claude run has the Hub's own MCP server configured, the Hub SHALL allowlist that
server's tools explicitly, so the agent's general sandbox does not also block AgentWeave's own tooling.

#### Scenario: Hub's own MCP tools remain usable under the sandbox

- **WHEN** the Hub spawns a non-yolo Claude agent with its own MCP server configured
- **THEN** the spawned command line allowlists that server's tools
- **AND** an action outside that allowlist is still refused

#### Scenario: No allowlist is added when there is nothing to allowlist

- **WHEN** the Hub spawns a non-yolo Claude agent with no MCP server configured
- **THEN** the spawned command line does not include an MCP tool allowlist flag

### Requirement: The default posture lets an agent work inside its own workspace

The permission posture the Hub imposes by default SHALL permit an agent to do work within its own
workspace without further configuration.

The Hub MUST NOT impose by default a posture whose decisions can only be resolved by an operator
prompt, unless a surface exists through which an operator can actually answer that prompt. A posture
that defers every decision to an absent answerer denies everything and is indistinguishable from a
broken run.

Isolation SHALL continue to be carried by the agent's workspace boundary, not by withholding
permission inside it.

#### Scenario: A newly created agent can edit files in its own workspace

- **WHEN** the Hub spawns a non-yolo agent that has been given no permission configuration
- **AND** that agent writes a file inside its own workspace
- **THEN** the write succeeds
- **AND** no approval was required from an operator

#### Scenario: A posture requiring an answer is not imposed by default

- **WHEN** no operator-facing approval surface exists for a provider
- **THEN** the Hub does not default that provider's runs to a posture that asks for approval

#### Scenario: The workspace boundary is unchanged

- **WHEN** an agent acts under the default posture
- **THEN** its ability to affect anything outside its own workspace is unchanged by that posture

### Requirement: The operator chooses a conversation's permission posture

The operator SHALL be able to select the permission posture used for a conversation's runs, from the
postures the provider supports, and that selection SHALL take effect on the next run of that
conversation.

The selection MUST reach the spawned command. A control that is displayed but does not change what
the run receives is a defect, not a cosmetic issue.

Postures SHALL be presented in terms of what they allow, not by the provider's internal flag spelling.

#### Scenario: A selected posture reaches the run

- **WHEN** the operator selects a permission posture for a conversation and sends a message
- **THEN** the spawned command carries that posture
- **AND** does not also carry the default posture

#### Scenario: Selecting the most restrictive posture restores refusals

- **WHEN** the operator selects the posture that requires approval for every action
- **AND** the agent attempts a write
- **THEN** the write does not succeed

#### Scenario: A posture is described by what it permits

- **WHEN** the permission postures are presented to the operator
- **THEN** each is labelled by the access it grants rather than by its provider flag value

### Requirement: A posture exists in which the workspace boundary is enforced per tool call

The Hub SHALL offer a permission posture under which each of a run's tool calls is decided against
the run's own workspace, rather than permitted in advance.

Under that posture a tool call confined to the run's workspace is allowed, and one reaching outside
it is refused with a reason stating what was refused and why. The comparison SHALL be made on fully
resolved paths, so that a relative traversal or a symbolic link cannot escape a boundary that an
unresolved comparison would have accepted.

The boundary enforced SHALL be the same one the agent is told it is working in. A boundary that is
described in one place and enforced from another can disagree, and the agent is given no way to tell
which is real.

Where the boundary cannot be established, the posture SHALL refuse rather than permit. An
unknown boundary is not an absent one.

#### Scenario: Work inside the workspace proceeds

- **WHEN** a run under this posture acts on a path inside its own workspace
- **THEN** the action is allowed

#### Scenario: Work outside the workspace is refused with a reason

- **WHEN** a run under this posture acts on a path outside its own workspace
- **THEN** the action is refused
- **AND** the refusal states what was refused and why

#### Scenario: Traversal and links cannot escape

- **WHEN** a path reaches outside the workspace only after relative traversal or link resolution
- **THEN** it is refused

#### Scenario: An unestablished boundary refuses

- **WHEN** the run's workspace cannot be determined
- **THEN** actions under this posture are refused

#### Scenario: Collaboration is not a filesystem decision

- **WHEN** a run under this posture uses the Hub's own tools
- **THEN** those calls are allowed

---

### Requirement: Every permission decision is answered, and answering never depends on the Hub

The Hub SHALL answer every permission request a run raises, including requests whose shape it does
not recognise, for which the answer is refusal.

A decision SHALL be reached without requiring a response from any other process. An unanswered
request does not fail a run, it suspends it indefinitely, so a decision path that can time out, be
refused a connection, or wait on a restart is a decision path that can hang a turn forever.

#### Scenario: An unrecognised request is answered

- **WHEN** a permission request is raised whose shape is not recognised
- **THEN** it is refused rather than left unanswered

#### Scenario: Decisions survive an unavailable Hub

- **WHEN** the Hub cannot be reached while a run is deciding a permission request
- **THEN** the request is still answered

---

### Requirement: A refused action is visible to the operator

Where a run's action is refused by the enforced boundary, the Hub SHALL make that refusal visible to
the operator.

An agent that is silently refused appears merely to have chosen differently. The operator is the only
participant who can widen a boundary or redirect the work, and cannot do either without knowing a
refusal happened.

Reporting a refusal MUST NOT alter or delay the decision it reports. Visibility is an observation of
a decision already reached, never a precondition of reaching it.

#### Scenario: A refusal reaches the operator

- **WHEN** an action is refused under the enforced boundary
- **THEN** the operator can see that the refusal happened

#### Scenario: Failed reporting changes nothing

- **WHEN** a refusal cannot be reported
- **THEN** the decision is unchanged
- **AND** the run continues

---

### Requirement: Introducing an enforced posture does not change existing runs

The default posture SHALL NOT change as a consequence of an enforced posture becoming available, and
runs that do not select it SHALL be spawned exactly as before.

A posture that decides each tool call is new machinery on the path of every action. Adopting it is a
deliberate choice, made per conversation, not a change imposed on every existing agent's next run.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default is unchanged

- **WHEN** a non-yolo run is spawned with no posture selected
- **THEN** it uses the same default posture as before the enforced posture existed

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform

### Requirement: A permission request does not outlive the wait it represents

A permission request SHALL reach a terminal status whenever the run that raised it stops waiting —
by answering, by timing out, by being stopped, or by ending for any other reason. It SHALL NOT
remain pending once nothing is waiting on it.

Reaching that terminal status SHALL NOT depend on the run successfully reporting it. A run that is
killed, crashes, or cannot reach the Hub still stops waiting, and the request SHALL still be closed.

Reporting that a wait has ended MUST NOT alter or delay the decision the run already reached. As with
reporting a refusal, this is an observation of something already true.

#### Scenario: A request whose wait timed out is closed

- **WHEN** a run's wait for an operator decision runs out
- **THEN** the request reaches a terminal status rather than remaining pending

#### Scenario: A request outliving its run is closed

- **WHEN** a run ends while a permission request it raised is still pending
- **THEN** that request reaches a terminal status

#### Scenario: A killed run's request is still closed

- **WHEN** a run is stopped or dies without reporting that its wait ended
- **THEN** its pending permission requests are still closed

#### Scenario: Closing twice is harmless

- **WHEN** a request's wait is reported as ended after the request has already been closed
- **THEN** the request is unchanged and no error is surfaced to the run

### Requirement: A decision is refused once nobody is waiting for it

The Hub SHALL refuse an operator decision on a permission request that is no longer pending, and
SHALL say that the run has moved on.

An accepted decision is a record that the operator authorised an action. Recording an approval for a
call that already proceeded without it — or was already refused — states an authority that was never
exercised, which is worse than refusing the decision outright.

#### Scenario: Deciding a closed request is refused

- **WHEN** an operator submits a decision for a request that has already reached a terminal status
- **THEN** the decision is refused and the operator is told the run has moved on

#### Scenario: A refused decision does not alter the record

- **WHEN** a decision on a closed request is refused
- **THEN** the request's status, decision time, and decider are unchanged

### Requirement: The operator can see that an agent stopped waiting

A permission request that ended without an operator decision SHALL remain visible to the operator and
SHALL be presented as expired, distinctly from one they answered.

The operator is the only participant who can widen the wait or be present for the next one, and
cannot do either without learning that an agent gave up. A request that disappears silently withholds
exactly that.

An expired request SHALL NOT be answerable.

#### Scenario: An expired request is shown as expired

- **WHEN** a permission request expires without an operator decision
- **THEN** it remains visible to the operator, marked as expired rather than removed

#### Scenario: An expired request offers no decision

- **WHEN** the operator views an expired permission request
- **THEN** it presents no way to allow or deny it

#### Scenario: An expired request is distinguishable from an answered one

- **WHEN** the operator views a permission request that expired and one they decided
- **THEN** the two are visibly different

### Requirement: The operator can clear an expired request they have seen

The Hub SHALL let the operator dismiss an expired permission request, after which it is no longer
presented to them. Dismissing SHALL NOT change what the agent was told or who authorised what.

Expired requests accumulate deliberately, because a run of missed decisions is something the
operator should see building up. A pile that cannot be cleared stops being a signal, so
acknowledgement has to be possible without pretending a decision was made.

A request that is still pending SHALL NOT be dismissable. The run is still waiting on it, and
clearing it from view would refuse it by neglect while appearing to be housekeeping.

#### Scenario: An expired request is cleared once seen

- **WHEN** the operator dismisses an expired permission request
- **THEN** it is no longer presented to them, and its status and decision record are unchanged

#### Scenario: A request still being waited on cannot be cleared

- **WHEN** the operator attempts to dismiss a request that is still pending
- **THEN** the attempt is refused, and the request remains presented for a decision

#### Scenario: Dismissing twice is harmless

- **WHEN** an already-dismissed request is dismissed again
- **THEN** it is unchanged and no error is surfaced
