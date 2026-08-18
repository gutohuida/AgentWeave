# local-project-workspace

## ADDED Requirements

### Requirement: A project can be deleted from the Hub without touching its workspace

The operator SHALL be able to remove a project and every Hub-owned record scoped to it. Deletion
SHALL remove database rows only. It MUST NOT delete, move, or write to the project's registered
working directory or any file within it, including the project's own identity marker.

The system MUST refuse deletion while any run for the project is active (`status == "running"`). An
existing conversation, message, task, or any other record scoped to the project SHALL NOT itself
block deletion.

Deletion SHALL be irreversible and MUST require the operator to confirm by supplying the project's
current name before it proceeds.

Deleting the operator's only remaining project SHALL leave the interface in a defined, non-error
state that still offers a way to add a project.

#### Scenario: A project with no active run is deleted

- **WHEN** the operator confirms deletion of a project with no run in `status == "running"`
- **THEN** the project and every database record scoped to it are removed
- **AND** the project no longer appears in the project collection

#### Scenario: The workspace directory survives deletion

- **WHEN** a project pointing at a directory containing files is deleted
- **THEN** that directory and every file within it, including the project's identity marker, still
  exist afterward, unchanged

#### Scenario: An active run blocks deletion

- **WHEN** deletion is requested for a project with a run in `status == "running"`
- **THEN** the deletion is refused
- **AND** no database record for the project is removed

#### Scenario: An open conversation does not block deletion

- **WHEN** deletion is requested for a project that has conversations and no active run
- **THEN** the deletion proceeds

#### Scenario: Deleting the last project leaves the interface usable

- **WHEN** the operator deletes their only remaining project
- **THEN** the interface shows no project selected and no error
- **AND** an affordance to add a new project remains available

#### Scenario: Confirmation requires the project's name

- **WHEN** the operator opens the delete confirmation for a project
- **THEN** the deletion is not available until they enter that project's current name
