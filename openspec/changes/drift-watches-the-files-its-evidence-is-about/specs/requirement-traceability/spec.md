## ADDED Requirements

### Requirement: A footprint watches the files its evidence is about

A footprint SHALL record, for drift, only the files its evidence is about: the path its locator names, the files changed by the commit an operator's locator names, and the files changed on its line of work since that line left the main line.

A footprint that recorded the whole tree would make one commit to any file a drift candidate for
every piece of evidence on that branch. The question drift asks — *which one was wrong?* — is then
asked about work nobody touched, and a feature that asks it forty times for one commit is switched
off.

A footprint that can name no such file SHALL watch nothing, and SHALL say so: the footprint reports
where what it watches came from, and a list of accepted evidence that watches nothing SHALL be
available together with the reason. Recording evidence SHALL NOT be refused because it watches
nothing.

A footprint recorded before the footprint recorded what it watches SHALL NOT be scanned for drift,
and SHALL be listed as watching nothing for that reason.

#### Scenario: A change to a file the evidence is not about raises nothing

- **WHEN** evidence whose locator names one file is accepted
- **AND** a later commit changes only a different file
- **THEN** no drift candidate is raised for that evidence

#### Scenario: A change to the named file raises a candidate

- **WHEN** evidence whose locator names one file is accepted
- **AND** a later commit on the line of work it is compared against changes that file
- **THEN** a drift candidate is raised naming that file

#### Scenario: Work on a branch is watched by what it changed

- **WHEN** an agent's evidence is footprinted at a commit that is not yet on the main line
- **THEN** the footprint watches the files changed between the point that line left the main line
  and that commit

#### Scenario: Evidence that names nothing is listed, not silently ignored

- **WHEN** accepted evidence names no file and no commit, and its work changed nothing off the main
  line
- **THEN** it watches nothing
- **AND** it appears in the list of unwatched evidence with the reason that it names no file

#### Scenario: The recorder sees what is watched

- **WHEN** evidence is recorded and a footprint is captured
- **THEN** the response reports where the watched files came from and how many there are
