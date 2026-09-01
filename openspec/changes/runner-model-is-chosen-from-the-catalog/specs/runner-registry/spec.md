## MODIFIED Requirements

### Requirement: A runner's model is drawn from the catalog

A runner's model SHALL be a model the catalog declares for that runner's provider, or unset, and runner management SHALL offer that choice as a selection over the declared models rather than as free-typed text.

The Hub SHALL refuse a runner carrying a model its provider does not declare.

An unset model is a valid, spawnable state meaning the provider's own default, and runner management
SHALL offer it as a named choice alongside the declared models. Where a runner's model is asked to be
cleared, the Hub SHALL clear it, and SHALL NOT answer a request that left the model unchanged as
though it had changed it. A request that carries no model at all leaves the runner's model as it was;
these are different requests and the Hub SHALL distinguish them.

Where a runner already records a model the catalog does not declare, that model SHALL remain among
the offered choices, selected, and marked as unrecognised, so that opening the runner for editing
cannot silently re-point it at a different model.

#### Scenario: Runner management offers declared models

- **WHEN** the operator creates or edits a runner and selects its provider
- **THEN** the models offered are those the catalog declares for that provider
- **AND** no free-typed model field is presented

#### Scenario: The provider's default is a choice, and clearing is honoured

- **WHEN** the operator sets a runner that has a model back to the provider's default
- **THEN** the runner records no model
- **AND** runs it backs launch on the provider's own default model

#### Scenario: A request that changes nothing is not reported as a change

- **WHEN** a request asks to change a runner's model and the Hub does not change it
- **THEN** the Hub does not answer as though the change was made

#### Scenario: An undeclared model is refused

- **WHEN** a runner is submitted with a model its provider does not declare
- **THEN** the request is refused with a stated reason

#### Scenario: Existing runners keep working

- **WHEN** a runner already records a model the catalog does not declare
- **THEN** that runner remains readable and its agents remain listable
- **AND** the operator is told the model is unrecognised when editing it
- **AND** that model is still offered and still selected, so saving the runner unchanged keeps it

## ADDED Requirements

### Requirement: Runner management presents the refusal it received

Where the Hub refuses a runner create or edit, runner management SHALL present the refusal's own sentence to the operator, beside the control that was refused.

The operator's ability to read the stated reason is the outcome this exists to produce. A refusal
that reaches no surface is indistinguishable from a control that does nothing: the dialog stays
open, the button returns to rest, nothing is created, and pressing it again does the same thing
forever.

The dialog SHALL remain open with the operator's input intact when a submission is refused, so the
refusal can be acted on rather than retyped.

#### Scenario: A refused create shows its reason

- **WHEN** the operator submits a new runner and the Hub refuses it
- **THEN** the operator is shown the refusal's own sentence
- **AND** the dialog remains open with the entered values intact

#### Scenario: A refused edit shows its reason

- **WHEN** the operator saves an edited runner and the Hub refuses it
- **THEN** the operator is shown the refusal's own sentence

#### Scenario: A refused delete shows its reason

- **WHEN** the operator deletes a runner that is bound to an agent
- **THEN** the operator is shown the refusal's own sentence naming the agents to unbind
