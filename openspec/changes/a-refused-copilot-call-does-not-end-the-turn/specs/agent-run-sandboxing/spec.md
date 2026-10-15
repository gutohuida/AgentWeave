## ADDED Requirements

### Requirement: A Copilot turn's stop reason is recorded

The Hub SHALL log the stop reason Copilot returns for every prompt of a Copilot turn, and SHALL record the turn's last stop reason on the run's terminal lifecycle event and closing status row.

Copilot answers every prompt with a stop reason. Today the Hub reads it only to tell a cancelled turn
apart and keeps nothing. A turn that a refusal stopped and a turn the agent finished then look
alike: both say `end_turn`, both are `completed` with exit 0, and the record cannot say which. The
reason is recorded with the run's own events, not in a new column, and a runner that returns no
stop reason adds nothing to them.

#### Scenario: A completed turn names its stop reason

- **WHEN** a Copilot turn's prompt returns the stop reason `end_turn`
- **THEN** the Hub's log names that stop reason for that run
- **AND** the run's completion event and its closing status row carry `end_turn` as its stop reason

#### Scenario: A runner with no stop reason adds nothing

- **WHEN** a run of a runner that returns no stop reason ends
- **THEN** its terminal lifecycle event carries no stop reason field, rather than an empty one

### Requirement: A Copilot turn that a refusal ended does not end silently

When the last thing in a Copilot turn's prompt is the Hub's or the operator's refusal of a parent-level tool call, and the prompt then returns `end_turn`, the Hub SHALL send that turn at most one follow-up prompt in the same session. That prompt SHALL carry the refused call and the refusal's reason, and SHALL tell the agent to continue another way or to ask. When no follow-up is sent, or the follow-up also ends on a refusal, the Hub SHALL show on the run that the turn ended on a refusal.

Copilot's approval protocol carries no reason with a refusal. The agent is told only "The user
rejected this tool call.", and Copilot's own runtime then ends the turn. Nothing the Hub sends ends
it. A Claude agent, refused through the Hub's approval tool, is given the reason and continues. The
follow-up prompt is the only place the Hub controls where Copilot can be given the same reason. It
is bounded, it is shown on the timeline, and it is never sent after the operator stopped the run or
after the turn failed.

A refusal is parent-level when the tool call it answered was not made inside a subagent. A
subagent's refusal ends only the subagent, and Copilot's parent turn carries on by itself, so the
Hub adds nothing. Agent text the Hub keeps on the timeline, or a new parent-level tool call started
after the refusal, means the refusal was not the last thing in the turn; so does nothing else, and
nothing that arrives after the prompt returned counts. Of several refusals, only the latest can be
the last thing. An agent that acknowledged the refusal in text and stopped has answered it, and is
not continued.

The follow-up costs what any prompt costs. It is counted on the same turn's usage.

#### Scenario: A judge refusal that ended the turn is continued with its reason

- **WHEN** the Hub's judge refuses a parent-level tool call in a Copilot turn
- **AND** the agent produces nothing after the refusal and the prompt returns `end_turn`
- **THEN** the Hub sends one follow-up prompt in the same Copilot session, naming the refused call
  and the judge's reason
- **AND** the timeline shows that the turn was continued after a refusal, before the agent's reply
- **AND** the run is recorded as one turn, whose usage includes the follow-up

#### Scenario: An operator's refusal that ended the turn is continued with the operator named

- **WHEN** the operator does not approve a parent-level tool call on its card, by denying it or by
  letting the card expire
- **AND** the agent produces nothing after the refusal and the prompt returns `end_turn`
- **THEN** the follow-up prompt says that the operator did not approve the call

#### Scenario: A subagent's refusal is left to Copilot

- **WHEN** a tool call made inside a Copilot subagent is refused
- **THEN** the Hub sends no follow-up prompt for it
- **AND** the run is not marked as having ended on a refusal

#### Scenario: A refusal the agent answered is not continued

- **WHEN** the agent writes text, or makes another parent-level tool call, after a refusal
- **AND** the prompt then returns `end_turn`
- **THEN** the Hub sends no follow-up prompt

#### Scenario: A stopped turn is not continued

- **WHEN** the operator stops a Copilot run, or the turn times out or fails, after a refusal
- **THEN** the Hub sends no follow-up prompt
- **AND** the run's outcome is the one the stop, timeout or failure gives

#### Scenario: A stop that arrives as the prompt returns is honoured

- **WHEN** the operator stops a Copilot run after a refusal, and the stop is requested after the
  Hub last checked for one but before the follow-up would be sent
- **THEN** the Hub sends no follow-up prompt
- **AND** the run is recorded as stopped

#### Scenario: A Hub shutdown during the follow-up ends the run as any shutdown does

- **WHEN** the Hub shuts down while the follow-up prompt is running
- **THEN** the run ends as any run cut off by a shutdown ends
- **AND** the follow-up is not recorded as having failed in its place

#### Scenario: The follow-up is bounded and its limit is visible

- **WHEN** the follow-up prompt also ends on a parent-level refusal
- **THEN** the Hub sends no further prompt
- **AND** the timeline shows that the turn ended on a refusal, naming the call and the reason
- **AND** the run's completion event records that it ended on a refusal

#### Scenario: A follow-up that fails leaves the turn as it was

- **WHEN** the follow-up prompt cannot be sent, or fails or times out before it returns
- **THEN** the run keeps the outcome its first prompt had
- **AND** the timeline shows that the follow-up failed and that the turn ended on a refusal
- **AND** a quota refusal, or an error Copilot reports for the session itself, during the follow-up
  still fails the run, as it would fail any prompt

#### Scenario: A task turn that ended on a refusal says why

- **WHEN** a task run's turn ends on a refusal that was not continued
- **THEN** what the Hub surfaces about the dropped task names the refused call and its reason

## MODIFIED Requirements

### Requirement: No Copilot hook decides a call or a turn

The Hub SHALL NOT install, for an agent whose tool calls it answers over Copilot's approval protocol, a Copilot hook that allows, denies or rewrites a tool call or that forces a turn to continue, and SHALL NOT trust the agent's workspace folder on Copilot's behalf.

A hook that answers a permission pre-empts the approval protocol: the request never reaches the Hub.
That takes the decision away from the Hub's own judge, from the operator's cards and from the record
of decisions, and a denial made there is one the operator never sees.

A hook that decides before a tool runs lets the call through when it is slow, so it cannot serve as
a denial control.

A hook that forces a turn to continue after the agent stopped is a backstop. The operator-in-the-loop
design deliberately has none: an agent that needs an answer asks, and a turn that ends without asking
has ended.

One case is not the agent stopping: a turn that Copilot's runtime ended because the last thing in it
was a refusal the Hub or the operator gave, which the approval protocol could not give a reason for.
The Hub's own bounded follow-up prompt for that turn, carrying the refusal's reason, is not a hook
and not a backstop. It is the reason the refusal could not carry, delivered in the only place
Copilot accepts it. The case is recognised only from the Hub's own record of a refusal it gave, and
never from what the agent wrote: no reading of the agent's text, however much it reads like a
question, decides whether a turn continues. Every other turn that ends has ended.

Trusting the workspace folder would load the repository's own hooks and servers into the run,
including hooks written for a different CLI. Not trusting it on Copilot's behalf includes not passing
on a trust setting the Hub did not choose: one present in the environment the Hub was started from,
or in the agent's own environment settings, SHALL be removed from the run's environment.

#### Scenario: The agent's Copilot home holds no deciding hook

- **WHEN** the Hub writes a Copilot agent's configuration
- **THEN** it contains no hook for permission requests or for the moment before a tool runs
- **AND** it contains no hook that stops or continues an agent or subagent

#### Scenario: A write reaches the Hub's approval channel

- **WHEN** a Copilot run under the posture the Hub answers asks to write a file
- **THEN** the request reaches the Hub's approval channel
- **AND** the decision is recorded as every other decision is

#### Scenario: A turn that ends is not continued by the Hub

- **WHEN** a Copilot agent ends its turn without asking the operator anything
- **AND** the last thing in the turn was not a refusal the Hub or the operator gave a parent-level
  tool call
- **THEN** the turn ends, and nothing the Hub installed or sends makes it continue

#### Scenario: A turn that ends on a question is not continued

- **WHEN** a Copilot agent's last text in a turn reads like a question to the operator
- **AND** the agent did not call the tool for asking the operator
- **AND** no refusal the Hub or the operator gave was the last thing in the turn
- **THEN** the Hub sends no follow-up prompt, and the turn has ended

#### Scenario: A turn a refusal ended is continued only by the Hub's bounded follow-up

- **WHEN** a Copilot turn ends because the last thing in it was the Hub's or the operator's refusal
  of a parent-level tool call
- **THEN** the only thing that continues it is the Hub's single follow-up prompt carrying the
  refusal's reason
- **AND** no hook takes part

#### Scenario: The repository's hooks do not load

- **WHEN** a Copilot run starts in a repository that carries its own hooks
- **THEN** the run's environment does not mark the workspace as trusted
- **AND** the agent's Copilot configuration names no trusted folder

#### Scenario: A trust setting from elsewhere is not passed on

- **WHEN** the environment the Hub was started from, or the agent's own environment settings, mark
  Copilot's workspace as trusted
- **AND** a Copilot run starts, under any posture
- **THEN** the run's environment does not mark the workspace as trusted
