# Run→task binding — deltas

## ADDED Requirements

### Requirement: A conversation carries the binding, and its runs inherit it

The system SHALL record a task binding on the conversation, and SHALL bind a run started in that
conversation to it when nothing more specific applies.

Work spans more turns than a run does. With the binding held only per run, a conversation's first
turn is checked at its boundary and every later turn is not — including the turn where the agent
actually stops, which is the only one at which "did this ever reach the ledger?" has a useful
answer.

An input that names its own task SHALL take precedence and SHALL rebind the conversation, so that
delegating different work into an existing thread is not silently attributed to the old task.

Each run SHALL still record the task it was bound to. Transitions and divergences are attributed to
a run, and an integrity record that had to be joined through a conversation to say what it was about
would depend on a row that may be archived.

#### Scenario: A follow-up turn is checked like the first

- **WHEN** work is started on a task in a conversation
- **AND** the operator sends a further message into that conversation
- **THEN** the run that message starts is bound to the same task
- **AND** it is subject to the run-boundary check

#### Scenario: Naming a different task rebinds the conversation

- **WHEN** an input naming a task is delivered into a conversation bound to another task
- **THEN** the run is bound to the newly named task
- **AND** the conversation's binding becomes that task

#### Scenario: An unbound conversation stays unbound

- **WHEN** a conversation has no binding and its inputs name no task
- **THEN** its runs are unbound and are not checked

#### Scenario: The run's own record is unchanged

- **WHEN** a run inherits its binding from its conversation
- **THEN** the run records the task it was bound to
- **AND** transitions it causes are attributed to it as before

### Requirement: A conversation's binding can be released

The system SHALL let the operator release a conversation's binding, and SHALL release it
automatically when the bound task reaches a status from which no further work is expected.

A binding SHALL NOT be released by inferring what the operator now seems to be discussing. A wrong
inference silently stops checking runs, and a mechanism that quietly stops enforcing is worse than
one that never started.

#### Scenario: The operator releases a binding

- **WHEN** the operator releases a conversation's binding
- **THEN** subsequent runs in that conversation are unbound

#### Scenario: Finished work releases its conversation

- **WHEN** a bound task reaches a status from which no further work is expected
- **THEN** the conversation's binding is released

#### Scenario: Changing subject does not release a binding

- **WHEN** the operator discusses something else in a bound conversation without releasing it
- **THEN** the binding is unchanged
- **AND** runs continue to be checked

### Requirement: A task recorded as waiting is not divergent

The system SHALL NOT record a divergence for a run whose bound task is waiting on a person.

Divergence means work was dropped with no account of why. A waiting task has an account, and it
names someone who can act on it. Answering a divergence with a retry would restart an agent that is
still waiting for the same thing.

#### Scenario: A run that ended waiting is not divergent

- **WHEN** a bound run ends and its task is recorded as waiting
- **THEN** no divergence is recorded
- **AND** no run is started in response

#### Scenario: The task still shows as needing attention

- **WHEN** a task is waiting on a person
- **THEN** the operator can see that it is waiting, and what for

#### Scenario: Once released, the check applies again

- **WHEN** a waiting task is released and a later bound run ends without moving it
- **THEN** that run is divergent as normal
