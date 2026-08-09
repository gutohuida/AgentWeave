## MODIFIED Requirements

### Requirement: Crossing the threshold warns before it spends

The Hub SHALL warn that a checkpoint is due, and SHALL NOT generate one, when a conversation
configured to involve the operator crosses its threshold. Generation SHALL wait until the operator
asks for it.

Generation is a billed model call. Producing one unasked means an operator who would rather keep
working has already paid for a summary they are about to discard, and pays again on the turn after
that.

The warning SHALL offer both taking the checkpoint and dismissing the warning. A dismissed warning
SHALL NOT reappear for that conversation while there is still room to keep working, so that
choosing to keep working is respected rather than re-asked.

A conversation whose warning was dismissed SHALL be warned once more when its context approaches
the point at which the provider will compact it, and that final warning SHALL NOT be dismissible.
A dismissal means the operator wants longer, not that they want the conversation summarised by
something else; without this the capability's own defect returns through the one door dismissal
leaves open.

The final warning SHALL be raised only where the proportion of the context window in use is known.
Where no window can be resolved there is no approach to detect, and choosing a denominator in
order to have one would report a proportion the conversation does not have.

Where checkpointing is configured to act alone, the threshold SHALL still generate and hand over
without asking, because acting alone is what that configuration means.

A checkpoint SHALL still be generated at the moment the operator asks for it rather than promised
for later, because it can only be written from the context that is about to be lost.

#### Scenario: The threshold warns rather than generating

- **WHEN** a conversation configured to involve the operator crosses its threshold
- **THEN** the conversation is reported as due for a checkpoint
- **AND** no checkpoint is generated

#### Scenario: A dismissed warning stays dismissed while there is room

- **WHEN** an operator dismisses a checkpoint warning
- **AND** the conversation has not approached the provider's compaction point
- **THEN** that conversation does not warn again
- **AND** no checkpoint is generated for it automatically

#### Scenario: A dismissed conversation is warned once more near the window

- **WHEN** a conversation whose warning was dismissed approaches the point at which the provider
  will compact it
- **THEN** it is warned again
- **AND** that warning cannot be dismissed
- **AND** no checkpoint is generated in order to raise it

#### Scenario: An unknown window raises no final warning

- **WHEN** a conversation whose warning was dismissed has no resolvable context window
- **THEN** no final warning is raised
- **AND** no proportion is inferred from a substituted window

#### Scenario: Acting alone still acts

- **WHEN** a conversation configured to act alone crosses its threshold
- **THEN** a checkpoint is generated and the conversation is handed over
- **AND** no warning is required first

#### Scenario: A successor is warnable again

- **WHEN** a conversation whose warning was dismissed is succeeded
- **THEN** the successor may warn on its own threshold
