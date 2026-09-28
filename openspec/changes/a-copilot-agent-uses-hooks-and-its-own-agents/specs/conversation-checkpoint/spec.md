## ADDED Requirements

### Requirement: A compaction the runner performed counts as reaching the threshold

Where a runner reports that it compacted a conversation's context, the Hub SHALL act on that conversation as it acts when the conversation crosses its checkpoint threshold, under the configuration that conversation already has, without consulting the threshold.

The threshold exists so that the Hub acts before the runner compacts on its own. When the runner has
already compacted, the premise for waiting is gone. Continuing on a summary nobody authored is the
defect this capability exists to remove, and the Hub now knows it happened.

Every other condition SHALL still apply. Checkpointing that is off stays off. A conversation already
handed over is not handed over again. Nothing is generated when nothing has happened since the last
checkpoint. A configuration that involves the operator is warned, not billed.

Notes SHALL NOT be requested in response to a compaction. Notes written after compaction are written
from the runner's summary, which is what the checkpoint exists to replace.

A conversation whose warning the operator dismissed SHALL NOT be warned again in response to a
compaction. The final warning exists to precede the loss, and after it the stream's record of the
compaction is the notice.

A compaction the runner reports as failed SHALL NOT count.

A checkpoint produced this way SHALL be recorded as produced by context pressure, so that every
surface that offers a threshold checkpoint offers it too.

A compaction SHALL be acted on even when the conversation is already being considered for a reading
at the moment it arrives. It SHALL then be considered after that consideration ends, and never at the
same time as it.

#### Scenario: Acting alone hands over after a compaction

- **WHEN** a conversation configured to act alone is compacted by its runner below its threshold
- **THEN** a checkpoint is generated and the conversation is handed over

#### Scenario: A configuration that involves the operator warns after a compaction

- **WHEN** a conversation configured to involve the operator is compacted by its runner
- **THEN** the conversation is reported as due for a checkpoint
- **AND** no checkpoint is generated

#### Scenario: Checkpointing that is off ignores a compaction

- **WHEN** a conversation whose checkpointing is off is compacted by its runner
- **THEN** no checkpoint is generated and no warning is raised

#### Scenario: A dismissed conversation is not warned again by a compaction

- **WHEN** a conversation whose warning was dismissed is compacted by its runner
- **THEN** no warning is raised and no checkpoint is generated

#### Scenario: A handed-over conversation spends nothing on a compaction

- **WHEN** a reopened conversation that was already handed over is compacted by its runner
- **THEN** no notes are requested, no checkpoint is reported as due, and none is generated

#### Scenario: No notes are requested after a compaction

- **WHEN** a conversation is compacted by its runner
- **THEN** no request for checkpoint notes is queued for it

#### Scenario: A failed compaction does not count

- **WHEN** a runner reports a compaction that did not succeed
- **THEN** the conversation is treated as though no compaction happened

#### Scenario: The checkpoint is offered where threshold checkpoints are

- **WHEN** a checkpoint is produced in response to a compaction
- **THEN** it is recorded as produced by context pressure

#### Scenario: A compaction that arrives mid-consideration is not lost

- **WHEN** a runner reports a compaction while a context reading for the same conversation is still
  being considered
- **THEN** the compaction is considered once that consideration has ended
- **AND** the two are never considered at the same time
