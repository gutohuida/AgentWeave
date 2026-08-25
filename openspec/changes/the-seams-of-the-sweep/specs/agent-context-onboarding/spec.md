## ADDED Requirements

### Requirement: A withheld capability is stated as plainly as a granted one

Canonical turn context SHALL state the capabilities an agent does **not** hold, alongside those it
does, and SHALL say what to do instead. Announcing a capability only when it is granted SHALL NOT be
treated as sufficient.

The reasoning is already recorded in the code: *a capability an agent does not know it holds is one
it does not use, and one it guesses at is a 403 in the middle of a turn it has already spent.* That
principle is currently applied in one direction only. Measured cost: a reviewer spent a full turn —
a genuine review, running the suite twice and writing a reproducer — before discovering it could not
record the verdict.

Saying what to do instead is load-bearing rather than courteous. Unable to record its verdict, that
reviewer wrote the review to a file inside its own worktree, which is isolated by design, so its
conclusion landed on a branch nobody reads.

#### Scenario: An agent without evidence-decision authority
- **WHEN** canonical context is assembled for an agent not granted evidence-decision authority
- **THEN** the context SHALL state that evidence decisions belong to the operator here
- **AND** SHALL state where to put a verdict instead

#### Scenario: An agent with evidence-decision authority
- **WHEN** canonical context is assembled for an agent granted that authority
- **THEN** the existing granted-capability guidance SHALL be emitted unchanged

#### Scenario: A readable capability that is not writable
- **WHEN** an agent can list a queue it is not permitted to answer
- **THEN** the context SHALL say so before the turn spends effort on it
