## ADDED Requirements

### Requirement: The Copilot catalog offers Auto and validates what Copilot would not

The catalog SHALL describe `copilot` with `auto` as its default model, followed by the models the installed Copilot CLI documents, and SHALL refuse a model outside that list before a Copilot process starts.

Copilot accepts any model name it is sent, and it silently replaces a model the account's plan does
not allow. The Hub's validation is therefore the only check a model name gets. `auto` SHALL be
labelled "Auto". Each Copilot model SHALL declare its context window as unknown unless the Hub knows
it, because Copilot reports the window of the model it actually ran. The Copilot entry SHALL declare
the same four permission postures, with the same labels, as the other providers, with Workspace
only as the default, and an Effort control. Workspace only is the default because a Copilot run has
no sandbox of its own: the Hub decides every permission request, and it decides a run that states
no posture as Workspace only.

#### Scenario: Auto is the default

- **WHEN** the catalog is read
- **THEN** its `copilot` entry lists `auto`, labelled "Auto", as the default model

#### Scenario: An undeclared model is refused before spawning

- **WHEN** a Copilot run is requested with the model `bogus-model`
- **THEN** the Hub refuses the request naming the models `copilot` declares
- **AND** no Copilot process is started

#### Scenario: The same postures as the other providers

- **WHEN** the catalog's `copilot` entry is read
- **THEN** its Permissions control offers Edit files, Workspace only, Ask me and Full access
- **AND** its default is Workspace only
