# Agent capability plane — deltas

## ADDED Requirements

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
