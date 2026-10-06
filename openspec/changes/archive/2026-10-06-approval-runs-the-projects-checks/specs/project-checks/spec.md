## ADDED Requirements

### Requirement: A project's checks are configured by the operator only
A project SHALL carry an ordered list of checks, each with a name, a shell command and a timeout in seconds, set only through the operator's project settings; no agent credential SHALL be able to change it through any surface.

A project with no checks configured SHALL behave exactly as before this change: no run starts and no approval is refused for checks. Names are unique within a project. A timeout is between 10 and 3600 seconds, and defaults to 900.

#### Scenario: The operator configures checks
- **WHEN** the operator saves two checks in a project's settings
- **THEN** reading the settings returns both, in order, with their timeouts

#### Scenario: An agent cannot change checks
- **WHEN** a run's credential calls any route that would set a project's checks
- **THEN** the request is refused and the checks are unchanged

#### Scenario: No checks, no change
- **WHEN** a task of a project with no checks moves to `completed` and is then approved
- **THEN** no check run is recorded and approval behaves as it did before this change

### Requirement: Checks run in the background on the work approval would merge
When a task moves to `completed` in a project with checks, the Hub SHALL start a check run in the background, and the transition SHALL NOT wait for it.

The run SHALL execute every check, in order, in a Hub-owned scratch checkout of a commit whose tree is the project's main branch with every commit the task's approval would merge applied (`task_integration.merge_targets`). It SHALL never use the project's root checkout or an agent's checkout. The run is recorded with:
- the main tip it was built on;
- the merged target commits;
- a state: `running`, `passed`, `failed`, `error` or `interrupted`;
- each check's exit code, duration, and the last 4000 characters of its combined output.

A check that exceeds its timeout SHALL have its whole process tree ended and count as failed. A project with no main branch, or a task with nothing to merge, records no run and refuses nothing.

#### Scenario: A failing check is recorded
- **WHEN** a task whose work makes a configured check exit non-zero moves to `completed`
- **THEN** a run is recorded `failed`, naming that check, its exit code and the tail of its output
- **AND** the move to `completed` returned before the run finished

#### Scenario: The run sees main plus the task's work
- **WHEN** main has advanced since the task branched and the task's commit merges cleanly
- **THEN** the files in the scratch checkout are main's with the task's changes applied

#### Scenario: A check that hangs is ended
- **WHEN** a check runs past its timeout
- **THEN** its process tree is ended and the run is recorded `failed` naming the timeout

#### Scenario: The root checkout is untouched
- **WHEN** a check run writes files in its checkout
- **THEN** the project's root checkout has no new or changed files

### Requirement: A check run is never lost silently
A Hub that restarts while a run is `running` SHALL record that run `interrupted` at startup, and a run SHALL be started again for a task whose latest result is `interrupted`, missing or stale (main tip or merge targets changed) when its approval is requested. No more than two runs SHALL execute at once per Hub. At most one run per task SHALL execute at a time; a request for a run already executing joins it.

#### Scenario: A restart interrupts, approval re-runs
- **WHEN** the Hub restarts during a run and the task's approval is then requested
- **THEN** the old run reads `interrupted`, a new run starts, and approval is refused as still running

#### Scenario: Main moved
- **WHEN** a task's checks passed and main has since advanced
- **THEN** requesting approval starts a new run instead of trusting the old result

### Requirement: A check runs with the Hub's environment minus the Hub's credentials
A check SHALL run with the Hub process's environment except variables that carry Hub or run credentials (`AW_RUN_TOKEN`, `AW_API_KEY`, `HUB_API_KEY` and any value beginning `aw_live_`). Its working directory SHALL be the scratch checkout.

#### Scenario: No Hub credential reaches a check
- **WHEN** a check prints its environment
- **THEN** no variable named above and no value beginning `aw_live_` appears in the recorded output
