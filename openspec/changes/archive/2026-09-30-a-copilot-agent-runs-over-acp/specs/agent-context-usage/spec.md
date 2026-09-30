## ADDED Requirements

### Requirement: Copilot context mapping

For Copilot runners, the canonical context source SHALL be the latest `usage_update` session update of the turn, with context tokens equal to its `used` and the effective limit equal to its `size`, reported as a measured provider sample.

A `usage_update` with no positive `size` SHALL produce a sample whose status is unavailable, carrying
its `used` tokens, and SHALL NOT borrow a window from the catalog or from another model. The sample
SHALL name the model Copilot reports it is running when Copilot has reported one, and otherwise the
model the turn requested.

The prompt response's `usage` SHALL NOT be used as a context reading. It is cumulative for the
session, not a measurement of the current context.

#### Scenario: Copilot reports its context

- **WHEN** a Copilot turn emits `usage_update` with `used` 12210 and `size` 128000
- **THEN** the context sample is measured, with 12210 context tokens and a 128000-token limit, from the provider

#### Scenario: Copilot reports no window

- **WHEN** a Copilot turn emits `usage_update` with no `size`
- **THEN** the context sample is unavailable, carries the `used` tokens, and names no limit

#### Scenario: Auto resolved a model

- **WHEN** a Copilot turn ran on Auto and Copilot reported that Auto chose `mai-code-1.1-flash`
- **THEN** the context sample names `mai-code-1.1-flash`
