## MODIFIED Requirements

### Requirement: Fields the Hub can determine are computed, never requested from a model

A checkpoint's identity, lineage, changed files, ledger, and runtime state SHALL be computed by the
Hub, and the generating model SHALL be asked only for judgement.

The division is verifiability. What the Hub can check, it must not delegate: a model asked for a
timestamp it could not obtain invented one, and a model asked for pending work reported none from a
worktree that is always clean because the Hub commits every turn.

Computed: conversation, agent, runner, model, timestamps, trigger, lineage, files changed derived
from the conversation's own commits, tasks assigned to the agent, open questions, permission
decisions, and runtime overrides in force.

The changed-file list SHALL be derived from the project's repository rather than from the workspace
any individual turn ran in, and the Hub SHALL resolve that repository itself rather than accept it
from whoever asks for a checkpoint. Both halves are load-bearing. A conversation's turns can run in
several checkouts once work is isolated per task, and a task's checkout is removed when the task
reaches a terminal status — so resolving each turn to the checkout it ran in would report nothing
for exactly the finished work a checkpoint most needs to describe, while the repository the
checkouts belong to can still read every one of their commits. And a repository supplied by the
caller is a repository a caller can omit: every caller did, and the changed-file list was silently
empty in every checkpoint produced.

Where the project's repository cannot be resolved, the checkpoint SHALL still be produced, carrying
no changed-file list. A checkpoint that reports nothing is worse than one that reports everything;
a checkpoint that does not exist is worse than both.

Written by the model: objective, current state, decisions and their rejected alternatives, dead ends
and their symptoms, next actions whose first step is executable without a further decision, and
risks not to repeat.

Tasks are project-scoped and carry no conversation, so the task list a checkpoint carries is the
agent's whole list. The record MUST state this rather than imply the list is conversation-specific.

#### Scenario: The envelope is complete even when generation produces nothing

- **WHEN** the worker returns no usable output
- **THEN** the computed fields are still populated
- **AND** the record states that its written half is absent

#### Scenario: A computed field is not solicited from the model

- **WHEN** a checkpoint is generated
- **THEN** the prompt does not ask the model for changed files, tasks, questions, or timestamps

#### Scenario: A checkpoint reports the files its turns changed

- **WHEN** a checkpoint is generated for a conversation whose turns committed work
- **THEN** the changed-file list names those files
- **AND** nothing outside the Hub had to supply the repository for that to happen

#### Scenario: Work from a released task checkout is still reported

- **WHEN** a checkpoint covers a turn that committed in a task's checkout, and that checkout has
  since been released
- **THEN** the changed-file list still names the files that turn changed

#### Scenario: A project whose repository cannot be resolved

- **WHEN** a checkpoint is generated for a conversation whose project workspace is unavailable
- **THEN** a checkpoint is still produced
- **AND** it carries no changed-file list
