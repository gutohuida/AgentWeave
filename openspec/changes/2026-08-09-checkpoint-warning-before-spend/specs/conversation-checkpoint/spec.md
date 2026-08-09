## ADDED Requirements

### Requirement: Crossing the threshold warns before it spends

The Hub SHALL warn that a checkpoint is due, and SHALL NOT generate one, when a conversation
configured to involve the operator crosses its threshold. Generation SHALL wait until the operator
asks for it.

Generation is a billed model call. Producing one unasked means an operator who would rather keep
working has already paid for a summary they are about to discard, and pays again on the turn after
that.

The warning SHALL offer both taking the checkpoint and dismissing the warning. A dismissed warning
SHALL NOT reappear for that conversation, so that choosing to keep working is respected rather
than re-asked.

Where checkpointing is configured to act alone, the threshold SHALL still generate and hand over
without asking, because acting alone is what that configuration means.

A checkpoint SHALL still be generated at the moment the operator asks for it rather than promised
for later, because it can only be written from the context that is about to be lost.

#### Scenario: The threshold warns rather than generating

- **WHEN** a conversation configured to involve the operator crosses its threshold
- **THEN** the conversation is reported as due for a checkpoint
- **AND** no checkpoint is generated

#### Scenario: A dismissed warning stays dismissed

- **WHEN** an operator dismisses a checkpoint warning
- **THEN** that conversation does not warn again
- **AND** no checkpoint is generated for it automatically

#### Scenario: Acting alone still acts

- **WHEN** a conversation configured to act alone crosses its threshold
- **THEN** a checkpoint is generated and the conversation is handed over
- **AND** no warning is required first

#### Scenario: A successor is warnable again

- **WHEN** a conversation whose warning was dismissed is succeeded
- **THEN** the successor may warn on its own threshold
