## MODIFIED Requirements

### Requirement: A file can be inserted into the composer in the format the composer already uses

Referencing a file from the file tree or a file's detail tab SHALL insert the same mention format the
composer's own path-completion trigger produces, so a mention inserted from either surface is
indistinguishable in the composed message.

A file whose path the composer's own path trigger would not offer (`agent-composer`, *Trigger result
sources*) SHALL NOT be offered for insertion either, because its mention would attach a file other
than the one shown.

#### Scenario: An inserted mention matches the composer's own format

- **WHEN** the operator inserts a file reference from the shell into the composer
- **THEN** the inserted text is the same mention format the composer's path trigger produces for that
  same file

#### Scenario: A file whose path would carry a second mention cannot be inserted

- **WHEN** the operator opens the detail tab of a workspace file whose path holds an at-sign that is
  neither at its start nor directly after a `/`
- **THEN** the tab offers no action that inserts it into the composer
