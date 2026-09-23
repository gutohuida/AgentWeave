## ADDED Requirements

### Requirement: An agent that will run but cannot collaborate SHALL say so where its runner is bound

The application SHALL show, at the control where the operator binds an agent's runner, the Hub's collaboration-readiness reason whenever the Hub reports that agent runnable but not collaboration-ready. It SHALL show nothing for an agent reported collaboration-ready, and nothing for a report that does not apply to the agent.

The reason shown SHALL be the Hub's own sentence, so that the condition to fix is named where it can be fixed.

#### Scenario: A runner that opted out of its tool transport is named at the binding control

- **GIVEN** an agent the Hub reports as runnable and not collaboration-ready, with a reason
- **WHEN** the operator opens that agent's execution settings
- **THEN** the runner control states that the agent will run but cannot collaborate
- **AND** the statement carries the Hub's reason

#### Scenario: A collaboration-ready agent shows no warning

- **GIVEN** an agent the Hub reports as runnable and collaboration-ready
- **WHEN** the operator opens that agent's execution settings
- **THEN** no collaboration warning is shown

#### Scenario: An agent that cannot run is not also told it cannot collaborate

- **GIVEN** an agent the Hub reports as not runnable
- **WHEN** the operator opens that agent's execution settings
- **THEN** only the statement that it cannot run is shown
