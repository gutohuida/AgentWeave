## ADDED Requirements

### Requirement: A run's recorded workspace says where it started, not where its writes landed

The directory recorded for a run SHALL mean the directory that run was started in, and SHALL NOT be read as a statement that the run's writes stayed inside it.

A workspace is a working directory. It is the process's `cwd` and the root of the agent's own branch;
it is not a wall, and nothing in the product makes it one. Whether a write stays inside is decided by
the path the model chose to spell — a relative path stays, an absolute one does not — and by whether
the run's permission posture happened to be one that checks. Two runs of the same agent, given the
same instruction in different words, were measured landing on opposite sides of that line while
recording the same directory.

Any consumer that needs to know whether a run's work is inside its recorded directory SHALL consult
the record of writes that left it, and SHALL NOT infer it from the recorded directory alone.

Where an outside write is recorded, the destination SHALL be identified as a workspace kind and name,
in the same two-field form every reported checkout already uses. A destination given as a bare path
puts the reader back where the finding began: unable to tell whether the write landed in the
project's own directory, in another agent's checkout, or in a task's.

#### Scenario: The recorded directory is where the run started

- **WHEN** a run is started in a workspace
- **THEN** the directory recorded for it is that workspace
- **AND** it remains that directory whether or not the run wrote outside it

#### Scenario: Containment is not inferred from the recorded directory

- **WHEN** a consumer needs to know whether a run's work is confined to its recorded directory
- **THEN** it reads the record of writes that left the workspace
- **AND** does not treat the recorded directory as an answer on its own

#### Scenario: A destination is named as a workspace

- **WHEN** a write outside the run's workspace is recorded
- **THEN** the destination is identified by workspace kind and name
- **AND** a path that belongs to no workspace is identified as such rather than left unclassified
