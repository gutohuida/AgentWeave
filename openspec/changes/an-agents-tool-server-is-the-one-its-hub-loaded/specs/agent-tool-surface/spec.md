## ADDED Requirements

### Requirement: The tool server a run is given is the one its Hub loaded

The Hub SHALL give every run it spawns the tool server program it held when it started, and SHALL NOT give a run whatever the server's source file on disk holds at the moment that run spawns.

A Hub's routes are fixed when it starts; the program that calls them on an agent's behalf must be
fixed at the same moment. Where the two are read at different times, an edit to the source reaches
running agents before the Hub has the routes it calls, and an edit that is only half-written reaches
them as a server that fails to start. Neither is visible to the operator as a change they made.

Where the Hub cannot make the program it holds available to a run, it SHALL refuse to start that run
with a reason naming the failure, and SHALL NOT fall back to the source file on disk. A fallback
would make the guarantee hold only on machines where nothing goes wrong, and the operator could not
tell which kind of run they had.

The copy SHALL live outside the project's repository, so that it is never part of any agent's
workspace and never appears as a change to the project.

#### Scenario: An edit to the server's source does not reach a run until the Hub restarts

- **WHEN** the tool server's source file changes on disk after the Hub started
- **AND** the Hub then spawns a run that is given the tool server
- **THEN** that run is given the program the Hub held at start
- **AND** the changed source reaches runs only after the Hub restarts

#### Scenario: A missing copy is restored rather than replaced by the source on disk

- **WHEN** the copy the Hub gives its runs has been deleted or altered since the Hub started
- **AND** the Hub spawns a run that is given the tool server
- **THEN** the run is given the program the Hub held at start

#### Scenario: A copy that cannot be made refuses the run with its reason

- **WHEN** the Hub cannot make the program it holds available to a run
- **THEN** the run is not started
- **AND** the reason names the failure to prepare the tool server
- **AND** the run is not given the source file on disk instead

#### Scenario: The served-surface check reads the program runs are given

- **WHEN** the tool surface is verified by spawning the server
- **THEN** the program spawned is the one the Hub gives its runs
