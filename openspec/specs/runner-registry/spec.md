# runner-registry Specification

## Purpose

Define project-scoped, Hub-owned runner records that separate reusable execution capability from
agent identity and provide explicit, operator-managed agent bindings.

## Requirements

### Requirement: Runners are project-scoped Hub records

The Hub SHALL persist runner definitions as project-scoped database rows, each identifying a
supported CLI (`claude` or `codex`), optional launch flags, and an optional default model. A runner
SHALL NOT be represented only as an in-memory or hardcoded mapping.

#### Scenario: Runner is created

- **WHEN** an operator creates a runner naming a supported CLI
- **THEN** the Hub persists it as a project-scoped record with a stable identifier

#### Scenario: Only supported CLIs are accepted

- **WHEN** an operator attempts to create a runner naming a CLI other than `claude` or `codex`
- **THEN** the Hub rejects the request

### Requirement: Built-in runners are seeded on first use

A project with zero runner records SHALL be seeded with one default runner per supported CLI before
any agent can be bound to a runner.

#### Scenario: First boot seeds default runners

- **WHEN** a project has no runner records and the Hub starts
- **THEN** the Hub creates a default `claude` runner and a default `codex` runner for that project

### Requirement: An agent is bound to at most one runner

Each Hub `Agent` record SHALL reference at most one runner record. Triggering an agent with no
bound runner SHALL fail with a typed, actionable error rather than falling back to an undeclared
default.

#### Scenario: Agent triggers using its bound runner

- **WHEN** the Hub triggers an agent that has a bound runner
- **THEN** it spawns the CLI, flags, and model that runner record specifies

#### Scenario: Agent has no bound runner

- **WHEN** the Hub receives a trigger for an agent with no runner bound
- **THEN** it refuses the launch and returns a typed error naming the missing binding

### Requirement: Runner management is available through the Hub UI

The Hub UI SHALL provide a screen to list, create, edit, and delete runner records, and to bind an
agent to a runner from the agent's detail view.

#### Scenario: Operator creates a custom runner variant

- **WHEN** an operator creates a second `claude` runner with a different default model
- **THEN** both runners are available for binding to any agent independently

#### Scenario: Operator binds an agent to a runner

- **WHEN** an operator selects a runner for an agent in the Hub UI
- **THEN** the agent's runner binding updates and subsequent triggers use the newly bound runner

### Requirement: A runner's model is drawn from the catalog

A runner's model SHALL be a model the catalog declares for that runner's provider, or unset, and runner management SHALL offer that choice as a selection over the declared models rather than as free-typed text.

The Hub SHALL refuse a request that sets a runner's model to one its provider does not
declare.

An unset model is a valid, spawnable state meaning the provider's own default, and runner management
SHALL offer it as a named choice alongside the declared models. Where a runner's model is asked to be
cleared, the Hub SHALL clear it, and SHALL NOT answer a request that left the model unchanged as
though it had changed it. A request that carries no model at all leaves the runner's model as it was;
these are different requests and the Hub SHALL distinguish them.

Where a runner already records a model the catalog does not declare, that model SHALL remain among
the offered choices, selected, and marked as unrecognised, so that opening the runner for editing
cannot silently re-point it at a different model. Runner management SHALL also mark such a runner
where runners are listed, so that which runners need attention is legible without opening each one.

A model the catalog does not declare is refused where it is newly *set*, and only there. Where a
request carries the model a runner already records, the Hub SHALL accept it, because that request
changes nothing about the runner's model and refusing it would make an existing runner uneditable
in every other respect as well.

#### Scenario: Runner management offers declared models

- **WHEN** the operator creates or edits a runner and selects its provider
- **THEN** the models offered are those the catalog declares for that provider
- **AND** no free-typed model field is presented

#### Scenario: The provider's default is a choice, and clearing is honoured

- **WHEN** the operator sets a runner that has a model back to the provider's default
- **THEN** the runner records no model
- **AND** the answer carries the model as it now stands rather than the one the runner had
- **AND** runs it backs launch on the provider's own default model

#### Scenario: A request carrying no model at all leaves the model alone

- **WHEN** a request updates a runner and carries no model field
- **THEN** the runner's model is unchanged
- **AND** the request is answered differently from one that asked for the provider's default

#### Scenario: An undeclared model is refused

- **WHEN** a runner is submitted with a model its provider does not declare
- **AND** the runner does not already record that model
- **THEN** the request is refused with a stated reason

#### Scenario: Existing runners keep working

- **WHEN** a runner already records a model the catalog does not declare
- **THEN** that runner remains readable and its agents remain listable
- **AND** the operator is told the model is unrecognised when editing it
- **AND** that runner is marked as unrecognised where runners are listed
- **AND** that model is still offered and still selected, so saving the runner unchanged keeps it

#### Scenario: A legacy runner can still be saved

- **WHEN** the operator opens a runner whose model the catalog does not declare, changes its name,
  and saves it with that model still selected
- **THEN** the save is accepted and the runner keeps its unrecognised model
- **AND** moving that runner to a *different* model the catalog does not declare is still refused

---

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

---

### Requirement: A runner's flags may select a transport, and unset means the safe default

A runner's flags MUST be allowed to carry sentinel values that select how the Hub starts a run
rather than arguments passed to the runner's CLI. A sentinel SHALL NOT be forwarded to the CLI as
an argument.

A runner whose flags are unset SHALL receive the Hub's default transport for its CLI, and that
default SHALL be the one whose tool surface the agent can actually call. Selecting a degraded
transport SHALL require an explicit sentinel.

#### Scenario: An unconfigured runner gets the working default

- **WHEN** a runner is created with no flags
- **THEN** runs it backs use the Hub's default transport for that CLI

#### Scenario: A transport sentinel never reaches the CLI

- **WHEN** a runner's flags contain a transport sentinel
- **THEN** the command the Hub builds does not contain that sentinel as an argument

#### Scenario: Opting out is explicit

- **WHEN** a runner's flags contain the opt-out sentinel for its CLI's default transport
- **THEN** runs it backs use the alternative transport

### Requirement: Launchability reports the runner that would actually be spawned

An agent's reported launchability SHALL be derived from the runner bound to it whenever one is
bound, regardless of how the agent came to exist. The probe and the spawn SHALL NOT be able to
disagree about the same agent.

Today the bound-runner merge is gated on the agent not having self-registered. That exemption's
intent — a self-registered agent manages its own execution and legitimately has no runner — is
sound, but it is written as an assumption and never enforced: an agent that is both self-registered
and bound to a runner is reachable through two ordinary API calls. Such an agent is reported
unlaunchable, naming a CLI after the agent itself, while triggering it works normally. The probe is
the one the operator sees.

#### Scenario: A self-registered agent with a runner bound
- **WHEN** launchability is probed for a self-registered agent that has a runner bound
- **THEN** the verdict SHALL describe that runner
- **AND** the agent SHALL be reported launchable if that runner is launchable

#### Scenario: An agent with no runner bound
- **WHEN** launchability is probed for an agent with no runner bound
- **THEN** the verdict SHALL say that no runner is bound and what would fix it
- **AND** SHALL NOT name a CLI after the agent

#### Scenario: The probe and the spawn agree
- **WHEN** an agent is reported launchable
- **THEN** triggering it SHALL use the same runner the probe described
