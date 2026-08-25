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

#### Scenario: Every operator grant, not only the one that was noticed
- **WHEN** canonical context is assembled for any agent
- **THEN** each capability the operator can grant or withhold SHALL be stated in whichever direction applies
- **AND** a grant SHALL NOT be announced when held and silent when withheld

The audit this requirement asked for found the principle applied to one grant of three. The other
two — reading a peer's checkpoints, and recalling the observations a checkpoint cites — appeared in
neither direction: the recall tool was listed among the agent's tools with no mention that a grant
is required, beside a tool that did say so.

#### Scenario: A refusal that is indistinguishable from absence
- **WHEN** a capability's refusal is reported as "not found" rather than as a refusal
- **THEN** the boundary SHALL be stated in context before the turn meets it

This is why the withheld direction matters even where nothing is granted. A refusal that announced
itself would confirm the record exists, so it correctly cannot; the consequence is that an agent
which meets the boundary unprepared concludes the record is missing rather than that it is not
permitted to see it, and reports a broken system in good faith.
