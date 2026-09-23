## ADDED Requirements

### Requirement: A message addressed to the operator is refused with where the operator reads

A message an agent addresses to a reserved operator name SHALL be refused with a reason that states the operator is not a message recipient and names the ways an agent does reach the operator.

The operator is not on the roster, and no agent can hold the names reserved for them, so such a
message is never a mistyped peer. A refusal that says only "no agent by that name" leaves the agent to
guess another name.

The reason SHALL say that the agent's reply is what the operator reads in the conversation, that a
result can be recorded on a task through its notes, and that a question needing the operator's answer
goes through the question tool. The system SHALL NOT add any mechanism that reads an agent's text to
decide it was addressed to the operator.

#### Scenario: An agent addresses the operator

- **WHEN** an agent sends a message whose recipient is a reserved operator name, in any letter case
- **THEN** the message is refused and nothing is queued
- **AND** the reason names the reply, the task notes and the question tool

#### Scenario: A mistyped peer is still told it is unknown

- **WHEN** an agent sends a message to a name that is neither an agent nor reserved
- **THEN** the refusal says no agent by that name exists, as before

## REMOVED Requirements

### Requirement: A turn that ends on an unasked question is surfaced to the operator

**Reason**: Retired by the operator on 2026-08-20 and deleted by migration
`0082_drop_unasked_questions`. A guess about whether trailing prose is a question is not something
the product makes on the operator's behalf, and `CLAUDE.md` forbids reintroducing it. The requirement
described behaviour the code no longer has.

**Migration**: None. An agent that needs an answer calls the question tool; a turn that ends without
calling it has ended.

### Requirement: The operator can convert an unasked question into a real one

**Reason**: Its subject — the pending unasked-question record — was deleted with the backstop by
migration `0082`. No record exists to re-prompt from or dismiss.

**Migration**: None.
