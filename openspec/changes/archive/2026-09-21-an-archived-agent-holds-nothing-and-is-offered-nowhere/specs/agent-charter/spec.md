## ADDED Requirements

### Requirement: Deleting a held charter is refused, and every holder it names is one the operator can find

Deleting a charter that an agent is bound to SHALL be refused with a message naming every holder
and the repair, and every agent it names SHALL be one the project's default roster shows.

The repair it names — unbind the agent, then delete — works only if the operator can reach the
agent. The default roster excludes archived agents on purpose, so a refusal naming an archived
holder names a repair on a record the operator cannot locate from the sentence they were given.
Measured: a charter bound to an agent that was then archived could not be deleted, and the agent
the refusal named was absent from the roster with nothing in the message saying why.

This requirement SHALL be satisfied by an archived agent holding no charter at all, rather than by
the delete route filtering archived holders out of its own query. A filter at the reader would
leave the charter deleted while an archived agent still referenced it, and the reader's filter is
the pattern that produced this defect: the roster's lifecycle filter was added once, at one site,
and every later site that selected agents by a binding was written without it.

A charter with no holder SHALL be deleted without a refusal, and the refusal SHALL NOT be weakened
for an open holder: naming the holder and the repair is what makes it actionable.

#### Scenario: A charter held by an open agent is refused with the holder and the repair

- **WHEN** an operator deletes a charter bound to an agent in the default roster
- **THEN** the deletion is refused
- **AND** the message names that agent and how to unbind it
- **AND** performing that repair makes the deletion succeed

#### Scenario: A charter whose only holder was archived is deletable

- **WHEN** an operator archives the only agent bound to a charter and then deletes that charter
- **THEN** the charter is deleted
- **AND** the operator is not asked to unbind anything

#### Scenario: Every name in the refusal appears in the default roster

- **WHEN** a charter deletion is refused with a list of holders
- **THEN** each named agent is present in the project's default agent roster
