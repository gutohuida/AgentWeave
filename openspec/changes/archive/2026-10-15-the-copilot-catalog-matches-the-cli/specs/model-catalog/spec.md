## MODIFIED Requirements

### Requirement: The Copilot catalog offers Auto and validates what Copilot would not

The catalog SHALL describe `copilot` with `auto` as its default model, followed by the models the newest Copilot CLI release it was refreshed against documents, and SHALL refuse a model outside that list before a Copilot process starts.

Copilot accepts any model name it is sent, and it silently replaces a model the account's plan does
not allow. The Hub's validation is therefore the only check a model name gets before a process
starts, and what Copilot reports when its session opens is the only check after. The documented
list SHALL be the one printed by `copilot help config` of the newest Copilot CLI release the catalog
was refreshed against, in that order. When a Copilot session opens, after the Hub's agent is
selected and before the first prompt, the Hub SHALL compare the model and effort it requested with
the ones Copilot then reports for the session. It SHALL report any
difference as a diagnostic, and SHALL record the model Copilot reported as the model the turn ran.
It SHALL NOT report a difference when the requested model is `auto`, because the model Copilot
reports for an Auto session is not the one Auto will choose. It SHALL proceed silently when
Copilot's response does not carry the model or the effort. `auto` SHALL be labelled "Auto". Each
Copilot model SHALL declare its context window as unknown unless the Hub knows it, because Copilot
reports the window of the model it actually ran. The Copilot entry SHALL declare the same four
permission postures, with the same labels, as the other providers, with Workspace only as the
default, and an Effort control. Workspace only is the default because a Copilot run has no sandbox
of its own: the Hub decides every permission request, and it decides a run that states no posture
as Workspace only.

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

#### Scenario: A model the CLI documents is accepted

- **WHEN** `copilot help config` of the release the catalog was refreshed against lists `claude-haiku-5.5`
- **AND** a Copilot run is requested with the model `claude-haiku-5.5`
- **THEN** the Hub accepts the request and starts Copilot with that model

#### Scenario: A model the CLI no longer documents is refused when newly chosen

- **WHEN** the catalog was refreshed against a release that no longer lists `claude-opus-4.7`
- **AND** an operator newly chooses `claude-opus-4.7` for a Copilot run
- **THEN** the Hub refuses the request naming the models `copilot` declares
- **AND** no Copilot process is started

#### Scenario: A substituted model is reported when the session opens

- **WHEN** a Copilot run requests the model `claude-opus-4.7`
- **AND** Copilot's session-start response reports `claude-sonnet-5` as the session's model
- **THEN** the Hub reports a model substitution naming both models before the first prompt is sent
- **AND** the turn's usage records `claude-sonnet-5` as the model that ran
- **AND** the substitution is reported once for that turn

#### Scenario: Auto is not reported as a substitution when the session opens

- **WHEN** a Copilot run requests the model `auto`
- **AND** Copilot's session-start response reports `claude-sonnet-5` as the session's model
- **THEN** the Hub reports no model substitution at session start

#### Scenario: A substituted effort is reported when the session opens

- **WHEN** a Copilot run requests the effort `max` with a model that does not offer it
- **AND** Copilot's session-start response reports `medium` as the session's effort
- **THEN** the Hub reports an effort substitution naming both values and the efforts Copilot offered

#### Scenario: An older Copilot that reports no model is not second-guessed

- **WHEN** Copilot's session-start response carries neither the session's model nor its effort
- **THEN** the Hub reports no substitution and the turn proceeds

#### Scenario: The model reported after agent selection is the one compared

- **WHEN** a Copilot run requests the model `claude-haiku-5.5`
- **AND** Copilot's session-start response reports `claude-haiku-5.5`
- **AND** Copilot's answer to the Hub's agent selection reports `claude-sonnet-5` as the session's model
- **THEN** the Hub reports a model substitution naming `claude-haiku-5.5` and `claude-sonnet-5` before the first prompt is sent

## ADDED Requirements

### Requirement: A conversation keeps a model its catalog has since dropped

A conversation's stored model override SHALL keep working after the catalog stops declaring it, and SHALL be marked as unrecognised; only a newly chosen model SHALL be refused.

A catalog refresh removes models that conversations may already store. Refusing those stored values
would refuse every message the dashboard sends in such a conversation, because the composer sends
the stored overrides back with each message. The Hub SHALL accept an override model equal to the
model the conversation already stores, even when the catalog no longer declares it, and SHALL keep
it. It SHALL refuse a model the catalog does not declare when that model differs from the stored
one. A conversation SHALL report whether its stored model is one its runner's catalog does not
declare, in the same way a runner reports an unrecognised model. Where the dashboard shows a stored
model the catalog does not declare, it SHALL name that model as unrecognised and SHALL NOT present it
as an alias of the default model.

#### Scenario: A stored dropped model still sends

- **WHEN** a conversation stores the model override `claude-opus-4.7`
- **AND** the `copilot` catalog no longer declares `claude-opus-4.7`
- **AND** the operator sends a message carrying the same override
- **THEN** the Hub accepts the message and the conversation keeps `claude-opus-4.7`

#### Scenario: Switching to an undeclared model is still refused

- **WHEN** a conversation stores the model override `claude-opus-4.7`
- **AND** the operator sends a message whose override model is `bogus-model`
- **THEN** the Hub refuses the message naming the models `copilot` declares

#### Scenario: The conversation says its model is unrecognised

- **WHEN** a conversation stores a model override its runner's catalog does not declare
- **THEN** the conversation is reported as having an unrecognised model
- **AND** a conversation with no model override is not

#### Scenario: The composer names an unrecognised stored model as unrecognised

- **WHEN** a conversation's effective model is `claude-opus-4.7`
- **AND** the `copilot` catalog no longer declares `claude-opus-4.7`
- **THEN** the composer's model control reads `claude-opus-4.7 — unrecognised`
- **AND** it does not describe `claude-opus-4.7` as an alias of Auto
