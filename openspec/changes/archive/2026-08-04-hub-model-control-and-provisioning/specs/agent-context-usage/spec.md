## ADDED Requirements

### Requirement: Context-window size is resolved in a stated order

The size of the context window used to express usage SHALL be resolved in this order:

1. the window the provider itself reports for the model that ran the turn;
2. the window the model catalog declares for that model;
3. unknown.

A window MUST NOT be resolved from a default that does not describe the model in use.

#### Scenario: A self-reported window wins

- **WHEN** the provider reports the context window for the model that ran the turn
- **THEN** usage is expressed against that reported window

#### Scenario: The catalog fills a missing report

- **WHEN** the provider reports no context window and the catalog declares one for that model
- **THEN** usage is expressed against the catalog's declared window

#### Scenario: A substitute default is not used

- **WHEN** neither the provider nor the catalog supplies a window for the model that ran the turn
- **THEN** no window is assumed

### Requirement: Unknown context usage is reported as unknown

When the context window for a turn cannot be resolved, the Hub SHALL report usage as unknown. It
MUST NOT present a proportion, a percentage, or a pressure state derived from an unresolved window.

A condition that pauses autonomous turns MUST NOT be raised from an unresolved window.

#### Scenario: No percentage is shown for an unknown window

- **WHEN** the context window for a model cannot be resolved
- **THEN** the interface reports usage as unknown rather than as a proportion

#### Scenario: An unresolved window does not pause execution

- **WHEN** the context window for a model cannot be resolved
- **THEN** no context-pressure condition is raised for that turn

#### Scenario: Reported usage never exceeds its own window

- **WHEN** usage is expressed as a proportion of a context window
- **THEN** that window is one the provider reported or the catalog declared for the model that ran
  the turn

### Requirement: A conversation whose model changed reports usage per turn

Usage SHALL be attributed to the model that ran each turn, because a conversation may contain turns
run under different models with different context windows.

A conversation-level figure MUST NOT assume that every turn shares one context window.

#### Scenario: Turns are measured against their own model

- **WHEN** a conversation contains turns run under two models with different context windows
- **THEN** each turn's usage is expressed against the window of the model that ran it

#### Scenario: The current pressure describes the current model

- **WHEN** the operator changes a conversation's model and sends a further message
- **THEN** the reported context pressure describes the newly chosen model
