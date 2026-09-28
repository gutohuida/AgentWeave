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
bound to a `copilot` runner.

Nothing else in the review context SHALL change. In particular, the verdict instruction SHALL stay as
it is.

#### Scenario: A reviewer with review agents chosen is told to consult them

- **WHEN** a Copilot agent whose operator chose code review is given a review turn
- **THEN** its context names the code-review agent and the range of changes to hand it
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

#### Scenario: A review goes ahead without a divergence point

- **WHEN** a Copilot reviewer with review agents chosen is given a review turn for a project with no
  branch that approval merges into
- **THEN** the review turn takes place
- **AND** its context names the commit alone

#### Scenario: The choice is shown as stored

- **WHEN** the operator chooses code review for a Copilot agent and reopens its settings
- **THEN** code review is shown as chosen
