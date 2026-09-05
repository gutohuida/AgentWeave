## ADDED Requirements

### Requirement: A run that has ended releases the queue behind it
The system SHALL re-evaluate every agent holding queued input in a project whenever a run in that project reaches a terminal status, and SHALL do so regardless of whether the bookkeeping that follows the terminal status succeeds.

Three kinds of work wait behind a running run: input that arrived for that agent while it was busy
and was never delivered; input the run was carrying that it handed back on failing; and another agent
parked behind a hold the run was carrying, such as the checkout of a task. A run ending is what frees
all three, and nothing else does on a timer — the re-evaluation is reachable only from a run ending
and from unrelated operator actions such as opening the project or saving its settings.

For the second of the three this restates a guarantee the system already owes: *Repeated delivery
failure does not wedge an agent* requires that returning an input to the queue cause delivery to be
attempted again without further operator action. That requirement is stated over returned input
alone; this one is stated over the queue behind the run, so that all three are released by the same
rule and for the same reason.

The release SHALL therefore be a consequence of the run having ended and not of anything that runs
after it. A run may end and then fail while recording its outcome, reporting abandonment,
broadcasting its lifecycle event, or persisting its terminal status line.
Where that happens the run is correctly terminal and the input behind it is correctly queued, and an
operator sees a message that never runs, with no error naming it and no surface saying it is waiting.

A run that is already terminal when such a failure occurs SHALL keep its recorded outcome — a later
bookkeeping failure MUST NOT relabel a run that ended cleanly as having failed. Preserving the
outcome and releasing the queue are separate questions, and answering both from a single condition
is what produces a stranded input.

This SHALL hold on every execution path the system uses to run a turn, and no path may rely on a
Hub restart to satisfy it. Restart reconciliation examines runs still recorded as running and does
not examine a run that ended, so it cannot recover input stranded this way.

#### Scenario: A failure after a run ends still releases its queue

- **WHEN** a run reaches a terminal status and the work that follows recording it raises
- **AND** input for that agent is queued behind the run
- **THEN** the queued input is delivered to a successor run without any further operator action

#### Scenario: Input that was never delivered is released too

- **WHEN** input arrived for an agent while it was busy, so it was queued rather than delivered and
  nothing has returned it
- **AND** the run it was waiting behind reaches a terminal status and the work that follows raises
- **THEN** it is delivered without the operator opening the project, saving settings, or relocating
  the workspace

#### Scenario: An agent parked behind an ended run's hold is re-evaluated

- **WHEN** a run holding a task's checkout ends and the work that follows recording its outcome raises
- **AND** a second agent has input queued that was refused while that checkout was held
- **THEN** the second agent is re-evaluated as a consequence of the first run ending

#### Scenario: A cleanly-ended run keeps its outcome

- **WHEN** a run reaches a terminal status and later bookkeeping raises
- **THEN** the run still reports the outcome it reached, rather than being relabelled as failed

#### Scenario: The release holds on the app-server path

- **WHEN** a run executed over the app-server transport reaches a terminal status and the work that
  follows recording it raises
- **THEN** input queued behind that run is delivered to a successor run, exactly as it is for a run
  executed over a process transport

### Requirement: Every started run reaches a terminal status without a restart
The system SHALL bring every run whose execution ends inside the process that started it to a terminal status, on every execution path and without requiring a restart, and SHALL record why when the run ended abnormally.

This is bounded to a run whose execution ends while the process that started it is still there to
observe it, including an execution that ends by raising. A run whose Hub was killed under it is not
in scope and is recovered by reconciliation at the next start — the corpus already carves that case
out, under *A run's terminal status line is persisted*, for the same reason: there was no process to
write the outcome. A run whose execution raised is the opposite case, and has no such excuse.

An agent is refused a new turn while it has a run recorded as running. A run whose execution failed
without recording an outcome therefore stops that agent from ever running again: every later trigger
is queued rather than executed, with no error anywhere the operator looks, and the only recovery is
restarting the Hub. That is an unbounded outage produced by a single failed turn.

Where an execution path ends a run abnormally, the failure SHALL be recorded against the run and
logged, so the outage is diagnosable rather than merely survivable.

Deliberate cancellation SHALL still propagate after the run has been marked, so that callers
depending on cancellation semantics are not silently deprived of them.

#### Scenario: A failure after the spawn ends the run

- **WHEN** a run's execution raises after its runtime has started and before it records an outcome
- **THEN** the run reaches a terminal status and carries the reason it ended

#### Scenario: The agent is not wedged by a failed turn

- **WHEN** a run's execution has failed in that way
- **THEN** the agent accepts and executes a subsequent turn without the Hub being restarted

#### Scenario: The guarantee holds on the app-server path

- **WHEN** a run executed over the app-server transport raises after its runtime has started
- **THEN** it reaches a terminal status exactly as a run executed over a process transport does
