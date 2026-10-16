## ADDED Requirements

### Requirement: A calls directory in an isolated workspace starts the turn empty

At the start of each turn whose workspace is isolated to it (the agent's own worktree, a task's
checkout, which admits one writing turn at a time, or a review checkout), the Hub SHALL remove every
file and directory left inside that workspace's calls directory. It SHALL remove a link or junction
found there, directly or inside a subdirectory, as a link, without touching what it points to. The
Hub SHALL NOT empty the calls directory of a workspace that other agents' runs may be using at the
same time. These are the project directory, which read-only agents and projects that are not
repositories use, and a working directory the operator named.

An arguments file is scratch for one call. A new conversation cannot see a file an earlier turn left,
so it follows the example name it was given. A harness's file-creation tool refuses that name because
the file exists, and the run spends a turn recovering a file it never wrote. Emptying a shared
directory would trade that cost for a worse one: deleting the arguments file of another agent's run
between its write and its call.

A failure to remove a leftover file SHALL NOT refuse the turn. The leftover costs the run a retry,
not a safety property, because each call and each write is judged by its own path whatever else the
directory holds. Failing to make the directory real is still refused as before.

#### Scenario: A writing agent's next turn finds no earlier arguments file

- **WHEN** an earlier turn of an agent left `.agentweave/calls/1.json` in the agent's own worktree
- **AND** the agent's next turn starts
- **THEN** the calls directory is a real, empty directory when the run is spawned

#### Scenario: A link inside the calls directory is removed as a link

- **WHEN** the calls directory holds a link or junction to a directory elsewhere at turn start
- **THEN** the link is removed, and the contents of the directory it pointed to are unchanged
- **AND** the calls directory is empty when the run is spawned

#### Scenario: A link inside a subdirectory of the calls directory is not followed

- **WHEN** the calls directory holds a subdirectory that holds a link or junction to a directory
  elsewhere at turn start
- **THEN** the subdirectory and the link are removed, and the contents of the directory the link
  pointed to are unchanged

#### Scenario: A shared project directory keeps its arguments files

- **WHEN** a read-only agent's turn starts in the project directory
- **AND** that directory's calls directory holds a file
- **THEN** the file is still there when the run is spawned

#### Scenario: A file that cannot be removed does not refuse the turn

- **WHEN** removing a leftover arguments file fails at turn start
- **THEN** the Hub logs a warning naming the file
- **AND** the turn is started
