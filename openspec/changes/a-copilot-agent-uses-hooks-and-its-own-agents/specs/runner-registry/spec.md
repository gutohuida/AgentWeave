## ADDED Requirements

### Requirement: A Copilot runner may reach its model with the operator's own API key

A `copilot` runner MAY name the model provider `anthropic` and the name of an environment variable of the Hub's own process that holds that provider's API key, and the Hub SHALL then start the runs it backs against that provider with that key, SHALL NOT store the key, and SHALL refuse a runner of any other CLI, or any other provider, that names one.

The key stays where the operator keeps credentials today, the Hub's own environment. The runner holds
only the variable's name, as a proxy runner already does. A value submitted where a variable name
belongs SHALL be refused before it is stored, with a sentence saying to set the key in the Hub's
environment and to name the variable.

The runner's model SHALL be set, because the provider cannot choose one, and SHALL be a model
identifier the catalog declares for that provider. A shorthand the catalog publishes for a model is
not an identifier the provider accepts, and SHALL be refused for such a runner.

Everywhere the Hub asks which models a runner may use, it SHALL answer with the provider's for a
runner that names one: when the runner is created or edited, when the runner is reported, and when a
single run asks for a different model. A single run of such a runner SHALL NOT change its model.

A `copilot` runner that names no provider SHALL NOT inherit a provider from the Hub's own
environment. A provider setting present in the environment the Hub was started from SHALL be removed
from such a run's environment, so that an operator's shell cannot silently move a runner onto
another provider.

A runner that names a provider SHALL be reported launchable only when its key variable is set in the
Hub's environment. When it is not, the report SHALL name the variable and SHALL NOT require a GitHub
sign-in. This SHALL hold on every surface that reports whether a runner or an agent can run.

Runner management SHALL state that the provider is reached with an API key, and that a subscription
sign-in such as a Claude Max plan cannot be used.

The key SHALL NOT appear in any runner response, agent context, recorded run event, error or
diagnostic. The key is in the run's own environment, where the CLI needs it, and so is visible to
what the CLI starts; what those report back is redacted like any other recorded output.

#### Scenario: A provider runner starts against the provider

- **WHEN** a run starts for a `copilot` runner naming a provider, a key variable that is set, and a
  declared model
- **THEN** the run's environment names that provider and model and carries the key read from the
  variable

#### Scenario: A pasted key is refused before it is stored

- **WHEN** an operator submits a runner whose key-variable field holds something other than an
  environment variable name
- **THEN** the request is refused with a sentence saying to put the key in the Hub's environment and
  name the variable
- **AND** nothing is stored

#### Scenario: Only Copilot runners take a provider

- **WHEN** an operator submits a `claude` or `codex` runner naming a provider
- **THEN** the request is refused

#### Scenario: Only a supported provider is accepted

- **WHEN** an operator submits a `copilot` runner naming a provider other than `anthropic`
- **THEN** the request is refused with a stated reason

#### Scenario: The model is the provider's

- **WHEN** a provider runner is submitted with a model the catalog does not declare for that
  provider, with a shorthand rather than an identifier, or with no model
- **THEN** the request is refused with a stated reason

#### Scenario: A provider runner's model is recognised

- **WHEN** a provider runner with a declared model is reported
- **THEN** its model is not flagged as unrecognised

#### Scenario: A single run cannot change a provider runner's model

- **WHEN** a run of an agent bound to a provider runner asks for a different model
- **THEN** the request is refused with a stated reason

#### Scenario: An ambient provider does not leak into a subscription runner

- **WHEN** the Hub's environment carries Copilot provider settings
- **AND** a run starts for a `copilot` runner that names no provider
- **THEN** the run's environment carries none of them

#### Scenario: A missing key is named, not required from GitHub

- **WHEN** a provider runner's key variable is not set in the Hub's environment
- **THEN** the runner, and every agent bound to it, is reported not launchable, naming the variable
- **AND** the report does not ask for a GitHub sign-in

#### Scenario: The key is not repeated anywhere

- **WHEN** a provider runner has been created and a run it backs has recorded events whose text
  contains the key
- **THEN** the key's value appears in no runner response, agent context, recorded event, error or
  diagnostic

#### Scenario: A subscription cannot back a provider runner

- **WHEN** the operator opens a Copilot runner's provider settings
- **THEN** they are told that an API key is required and that a subscription sign-in such as a
  Claude Max plan cannot be used
