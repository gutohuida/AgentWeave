## ADDED Requirements

### Requirement: A Copilot reviewer may be told to consult Copilot's review agents

Where an agent bound to a `copilot` runner is given a review turn and the operator has chosen Copilot review agents for that agent, the review turn's context SHALL name those agents and the changes to hand them, and SHALL state that the verdict remains the reviewer's to record.

The reviewer remains an agent on the roster, resolved as every reviewer is. A Copilot review agent is
a tool that reviewer may use, not a reviewer. It cannot record a verdict, and resolving it as one
would be a second reviewer resolution.

The review agents on offer SHALL be those Copilot lets its main agent run as subagents: code review,
security review, and the critic. The choice SHALL be off by default, because each consultation is a
further billed model call.

The changes named SHALL run from where the work under review diverged from the branch approval merges
into, to the commit under review. Where that point cannot be determined, or is the commit itself,
the context SHALL name the commit alone and say to review that commit's own changes, and the review
turn SHALL still take place.

The choice SHALL be shown to the operator as it is stored, and SHALL be presented only for an agent
bound to a `copilot` runner. A stored choice SHALL be read as a list of offered agents: anything else
it holds SHALL NOT be named in the context.

Nothing else in the review context SHALL change. In particular, the verdict instruction SHALL stay as
it is.

#### Scenario: A reviewer with review agents chosen is told to consult them

- **WHEN** a Copilot agent whose operator chose code review is given a review turn
- **THEN** its context names the code-review agent by the exact name Copilot dispatches it by,
  and the range of changes to hand it
- **AND** says how to recover when the agent's model is not available on the operator's plan
- **AND** says not to describe a review the agent did not give
- **AND** says that the verdict is the reviewer's own and is recorded only by updating the task

#### Scenario: Without a choice the review context is unchanged

- **WHEN** a Copilot agent with no review agents chosen is given a review turn
- **THEN** its review context is the same as it is without this change

#### Scenario: An ordinary turn never names review agents

- **WHEN** a Copilot agent with review agents chosen is given a turn that is not a review
- **THEN** no review agent is named

#### Scenario: A reviewer on another runner is unaffected

- **WHEN** an agent bound to a runner other than `copilot` is given a review turn
- **THEN** no Copilot review agent is named, whatever its configuration holds

#### Scenario: Only the offered agents can be chosen

- **WHEN** an operator chooses a Copilot agent that is not among those offered
- **THEN** the choice is refused

#### Scenario: A stored choice outside the offer is not named

- **WHEN** an agent's stored configuration names a review agent that is not offered, or is not a list,
  because it was written by a route that does not check it
- **THEN** the review context names only the offered agents it holds, and none when it is not a list

#### Scenario: A review goes ahead without a divergence point

- **WHEN** a Copilot reviewer with review agents chosen is given a review turn for a project with no
  branch that approval merges into
- **THEN** the review turn takes place
- **AND** its context names the commit alone

#### Scenario: A divergence point that cannot be computed does not stop the review

- **WHEN** determining the divergence point fails for any reason, including the version-control
  command timing out
- **THEN** the review turn takes place with its context naming the commit alone
- **AND** nothing prepared for the review is left behind unreleased

#### Scenario: The choice is shown as stored

- **WHEN** the operator chooses code review for a Copilot agent and reopens its settings
- **THEN** code review is shown as chosen

### Requirement: A Copilot review turn records which review agents actually ran

Where a Copilot review turn's context named Copilot review agents, the run's stream SHALL record at the end of the turn which Copilot subagents ran in it, including that none did, as an event that stays visible when diagnostics are hidden.

A reviewer's own words about what its review agents found are not evidence that they ran: a
reviewer can claim a consultation that never happened. The Hub SHALL NOT judge the reviewer's prose;
it SHALL state, from the subagent events Copilot reported in that turn, what ran and what was named
but did not run, so that a claim and the record of what happened are read side by side.

#### Scenario: A review agent that was named but not run is reported

- **WHEN** a Copilot review turn whose context named the code-review agent ends without Copilot
  reporting any subagent
- **THEN** the run's stream records that the code-review agent was asked for and that no subagent ran

#### Scenario: A review agent that ran is reported with its outcome

- **WHEN** a Copilot review turn whose context named the code-review agent ends after Copilot
  reported that agent completing
- **THEN** the run's stream records that it ran, how it ended and the model it ran on

#### Scenario: The report is made when the turn fails too

- **WHEN** a Copilot review turn whose context named review agents fails or is stopped
- **THEN** the run's stream still records which subagents ran

#### Scenario: Without named review agents nothing is reported

- **WHEN** a Copilot turn ends whose context named no review agent, including every turn that is not
  a review
- **THEN** no report of review agents is recorded
