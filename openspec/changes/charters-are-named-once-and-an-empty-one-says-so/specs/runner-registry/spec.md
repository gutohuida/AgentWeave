## ADDED Requirements

### Requirement: A runner's name is unique within its project

The Hub SHALL refuse to create or rename a runner to a name another runner in the same project already has, SHALL say which name is taken, and SHALL NOT fail when a name it generates itself is taken.

A runner is chosen by its name wherever an agent is bound to one. Two runners with one name cannot be
told apart at that moment. Names are compared exactly, as agent names are: two names that differ only
in letter case are different names.

When the Hub creates a runner on the operator's behalf (creating an agent by provider and model finds
or creates a runner and names it), it SHALL give the runner a free name, adding a distinguishing
suffix when the name it would use is taken, rather than refusing the agent or failing. A create that
loses a race for a name to a concurrent request SHALL be refused as a conflict the caller can retry,
and SHALL leave neither the runner nor the agent behind.

Runners that already share a name when this rule arrives SHALL be kept, not deleted: the oldest keeps
the name and each later one is given a distinguishing suffix that no other runner in the project
holds, within the length a runner name may have, so that every agent stays bound to the runner it was
bound to.

#### Scenario: Creating a runner under a taken name is refused

- **WHEN** an operator creates a runner with a name another runner in the project already has
- **THEN** the request is refused, naming the taken name
- **AND** no runner is created

#### Scenario: Renaming a runner to a taken name is refused

- **WHEN** an operator renames a runner to a name another runner in the project already has
- **THEN** the request is refused, naming the taken name
- **AND** the runner keeps its name

#### Scenario: The same name in two projects is allowed

- **WHEN** two projects each have a runner with the same name
- **THEN** both runners exist

#### Scenario: Names differing only in case are different names

- **WHEN** an operator creates a runner named `Fast` in a project that has a runner named `fast`
- **THEN** the runner is created

#### Scenario: A runner the Hub names itself takes a free name

- **WHEN** an operator creates an agent by provider and model, no runner for that provider and model exists, and another runner already holds the name the Hub would give the new one
- **THEN** the agent is created
- **AND** its new runner carries that name with a distinguishing suffix
- **AND** the runner that held the name is unchanged

#### Scenario: Existing duplicates are renamed, not removed

- **WHEN** a project already holds several runners with one name as this rule takes effect
- **THEN** the oldest keeps the name and each later one carries a distinguishing suffix
- **AND** every agent is still bound to the same runner as before
