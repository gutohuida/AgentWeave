## ADDED Requirements

### Requirement: Approval is refused while the work is still being produced

The system SHALL refuse the transition into `approved` while the task has a live turn, meaning a run bound to that task whose process is still alive.

A task's work is not knowable while its turn is live. An agent records `completed` during its turn; the commit that holds its edits is made when the turn ends. Between those two moments the task's branch points at the commit it was cut from, and every question of the form *"which commit is this task's work?"* is answered with a commit that contains none of it. Approving there records that the work is good, merges nothing, and reports the nothing as a fact no retry can alter — so the task reads `approved` while its work sits unmerged and no surface offers a remedy.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements and unmergeable work, and SHALL name the agent whose turn is still running. An operator learning that approval was refused SHALL learn from the same response what it is waiting for.

The refusal SHALL clear itself. It states a fact about a moment, not a defect in the work, so it SHALL require no operator action beyond waiting for the turn to end.

Liveness SHALL be determined by testing the run's process, not by reading its recorded status alone. A run whose process died leaves its recorded status unchanged until the Hub next starts, so a refusal reading only that status would outlive the turn it describes and block approval indefinitely.

**A turn SHALL NOT be blocked by itself.** The run performing the transition SHALL be excluded from the test. A reviewer approves the work it has read from inside its own turn, and that turn is bound to the task it is approving — so counting it would refuse every review the product staffs, and would do so with a refusal the refused party cannot clear: its only remedy is for the turn to end, and it *is* the turn. A refusal whose stated remedy is unavailable to the one being refused is not a governance rule but a dead end.

The refusal SHALL apply wherever the work is resolved from, not only where it was first observed. Both routes by which a task's work is resolved — a commit named by accepted evidence, and the task's own branch tip — read a commit that predates the turn while the turn is live, so a refusal scoped to one of them would leave the same defect reachable through the other. Liveness remains a question about **the task**, on both routes alike: what is tested is whether a live run is bound to the task being approved, not who authored each piece of evidence. Evidence recorded by another task's run against a shared requirement is a merge target for this task and is therefore outside the test — a narrower residual of the same scoping that leaves an unbound run outside it, recorded here so it is a known limit rather than an oversight.

This refusal SHALL be independent of the rigor of any document the task's requirements belong to, for the same reason the unmergeable refusal is: rigor is a claim about how well work must be proven, and this is a claim about whether the work yet exists to be put anywhere.

It SHALL likewise be independent of whether the project's work could be integrated at all. The refusals that ask *what would merge* are silent wherever the system cannot answer that question — no configured main branch, an unresolvable workspace, a directory that is not a repository — because there each is a reason to not know rather than a reason to refuse. This one asks a different question. `approved` is a judgement that work is good, and judging work an agent has not finished producing is false whether or not anything is merged afterwards, so a project where integration cannot be attempted SHALL be refused on the same terms as one where it can.

#### Scenario: A project where integration cannot be attempted is refused on the same terms

- **WHEN** a task in a project with no configured main branch is moved to `approved` while its turn is live
- **THEN** the transition is refused
- **AND** once the turn has ended the same task approves, with the integration recorded as skipped exactly as it would have been before this requirement

#### Scenario: An approval inside the turn is refused

- **WHEN** a task is moved to `approved` while the agent that completed it still has a running turn bound to that task
- **THEN** the transition is refused
- **AND** the task's status is unchanged
- **AND** no integration is attempted or recorded

#### Scenario: The refusal names what it is waiting for

- **WHEN** approval is refused because the turn is still live
- **THEN** the refusal names the agent whose turn is running
- **AND** it is carried in the same typed refusal that reports unverified requirements

#### Scenario: The refusal clears when the turn ends

- **WHEN** the same task is approved after its turn has ended
- **THEN** the transition is permitted
- **AND** the commit that holds the turn's work is what integration merges

#### Scenario: A run whose process died does not block approval

- **WHEN** a task's most recent run is still recorded as running but its process is no longer alive
- **THEN** approval is not refused on account of that run

#### Scenario: A reviewer approves from inside its own review turn

- **WHEN** an agent moves a task to `approved` from within a run bound to that same task
- **THEN** approval is not refused on account of that run
- **AND** any *other* live run bound to the task still refuses it

#### Scenario: An approval on the evidence route is refused inside the turn

- **WHEN** a task whose work is named by accepted evidence is moved to `approved` while a live run is bound to that task
- **THEN** the transition is refused
- **AND** no commit is merged

#### Scenario: A task with no run is unaffected

- **WHEN** a task with no run bound to it is approved
- **THEN** approval proceeds exactly as it did before this requirement

#### Scenario: Rigor does not exempt the refusal

- **WHEN** a task whose linked requirements belong to a `sketch`-rigor document is approved while its turn is live
- **THEN** the transition is refused on the same terms as it would be for a `gate`-rigor document
