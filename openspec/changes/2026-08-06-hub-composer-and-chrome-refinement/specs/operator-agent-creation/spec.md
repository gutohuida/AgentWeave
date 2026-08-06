## ADDED Requirements

### Requirement: Provider choice is presented by provider identity

Where the operator chooses an agent's provider, each provider SHALL be presented with its own visual
mark alongside its name.

A provider for which no mark is available SHALL be presented with its name alone and MUST NOT be
given another provider's mark. A mark MUST NOT be the only thing distinguishing one provider from
another — the provider's name SHALL always be present.

Provider marks MUST NOT introduce a second icon system, a webfont, or a network request to render.

Presenting a provider's mark MUST NOT change which providers are offered. Launchability remains the
sole determinant of whether a provider can be chosen.

#### Scenario: Providers are shown with their marks

- **WHEN** the operator opens the provider choice
- **THEN** each provider is shown with its mark and its name

#### Scenario: A provider without a mark still reads correctly

- **WHEN** a provider has no available mark
- **THEN** it is shown with its name
- **AND** is not given another provider's mark

#### Scenario: Marks do not gate availability

- **WHEN** a provider is launchable but has no mark
- **THEN** it remains selectable

#### Scenario: Marks need no second icon system

- **WHEN** provider marks are rendered
- **THEN** they resolve without a second icon system, a webfont, or a network request
