# runner-registry Specification

## Purpose

Define project-scoped, Hub-owned runner records that separate reusable execution capability from
agent identity and provide explicit, operator-managed agent bindings.
## Requirements
### Requirement: Runners are project-scoped Hub records

The Hub SHALL persist runner definitions as project-scoped database rows, each identifying a
supported CLI (`claude`, `codex` or `copilot`), optional launch flags, and an optional default model.
A runner SHALL NOT be represented only as an in-memory or hardcoded mapping.

The set of supported CLIs SHALL be enforced identically by the request validator and by the
database, so a CLI the validator accepts is never refused by a database constraint.

#### Scenario: Runner is created

- **WHEN** an operator creates a runner naming a supported CLI
- **THEN** the Hub persists it as a project-scoped record with a stable identifier

#### Scenario: A Copilot runner is created

- **WHEN** an operator creates a runner naming `copilot`
- **THEN** the Hub persists it as a project-scoped record with a stable identifier
- **AND** the database accepts the row

#### Scenario: Only supported CLIs are accepted

- **WHEN** an operator attempts to create a runner naming a CLI other than `claude`, `codex` or `copilot`
- **THEN** the Hub rejects the request

### Requirement: Built-in runners are seeded on first use

A project with zero runner records SHALL be seeded with one default runner per supported CLI before
any agent can be bound to a runner.

#### Scenario: First boot seeds default runners

- **WHEN** a project has no runner records and the Hub starts
- **THEN** the Hub creates a default `claude` runner, a default `codex` runner and a default `copilot` runner for that project

#### Scenario: A project that already has runners is not re-seeded

- **WHEN** a project already has at least one runner record and the Hub starts
- **THEN** the Hub creates no runner for it, including no `copilot` runner

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

A runner's model SHALL be a model the catalog declares for that runner's provider, or an alias the catalog declares for that provider, or unset, and runner management SHALL offer that choice as a selection over the declared models and aliases rather than as free-typed text.

The Hub SHALL refuse a request that sets a runner's model to one its provider does not
declare, as a model or as an alias. A declared alias is recorded as written, not as the model it
currently stands for.

An unset model is a valid, spawnable state meaning the provider's own default, and runner management
SHALL offer it as a named choice alongside the declared models. Where a runner's model is asked to be
cleared, the Hub SHALL clear it, and SHALL NOT answer a request that left the model unchanged as
though it had changed it. A request that carries no model at all leaves the runner's model as it was;
these are different requests and the Hub SHALL distinguish them.

Where a runner already records a model the catalog does not declare, that model SHALL remain among
the offered choices, selected, and marked as unrecognised, so that opening the runner for editing
cannot silently re-point it at a different model. Runner management SHALL also mark such a runner
where runners are listed, so that which runners need attention is legible without opening each one.
A declared alias is not such a model.

A model the catalog does not declare is refused where it is newly *set*, and only there. Where a
request carries the model a runner already records, the Hub SHALL accept it, because that request
changes nothing about the runner's model and refusing it would make an existing runner uneditable
in every other respect as well.

#### Scenario: Runner management offers declared models

- **WHEN** the operator creates or edits a runner and selects its provider
- **THEN** the models offered are those the catalog declares for that provider, and its declared
  aliases
- **AND** no free-typed model field is presented

#### Scenario: A declared alias is accepted and recorded as written

- **WHEN** a runner is created or edited with an alias its provider declares
- **THEN** the request is accepted
- **AND** the runner records the alias, not the model it currently stands for
- **AND** the runner is not marked as unrecognised

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

- **WHEN** a runner is submitted with a model its provider does not declare, as a model or as an
  alias
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

### Requirement: Runner management offers each declared alias as a choice of its own

Wherever the operator chooses a model for a provider, the interface SHALL offer each alias the catalog declares for that provider as a choice distinct from the identifiers, and SHALL label it as following the provider's latest model, naming the model the catalog currently records it as standing for.

Choosing an alias and choosing the identifier it currently stands for have the same effect today and
different effects after the provider moves the alias. The label SHALL make that difference readable.

#### Scenario: Aliases are offered beside identifiers

- **WHEN** the operator creates a runner or an agent and selects a provider that declares aliases
- **THEN** each declared alias is offered as its own choice
- **AND** its label says it follows the latest model and names the model it currently stands for

#### Scenario: A runner recording an alias opens with it selected

- **WHEN** the operator opens a runner that records an alias for editing
- **THEN** the alias is the selected choice
- **AND** the runner is not presented as having an unrecognised model

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

No agent is exempt from this by how it came to exist. Every agent is created by the operator or
by a governed agent request; there is no self-registered agent that manages its own execution, so
there is no population for which an absent runner is legitimate rather than unbound.

**The probe SHALL report the same set of agents the roster offers.** An agent the roster excludes
by lifecycle SHALL NOT appear in a launchability report that did not ask for that lifecycle, and
the probe SHALL take the lifecycle selector the roster takes, with the same default. Reporting an
archived agent as runnable is the probe and the spawn disagreeing about the same agent in the other
direction: triggering it is refused with the reason it is archived, one call after the probe said
it could run.

The lifecycle exclusion SHALL be applied after every source of agent names has contributed, not to
the agent query alone. A name reaches this report from the session configuration as well as from
the agent table, and a filter on one source lets the same agent back in through the other. An agent
with no agent-table row cannot have been archived and SHALL count as open.

An agent excluded by lifecycle SHALL be excluded from the report entirely rather than reported with
a lifecycle reason inside its verdict. Lifecycle is the roster's fact and the roster states it; a
second statement of it inside the probe would be a second vocabulary for one condition.

#### Scenario: An agent with a runner bound
- **WHEN** launchability is probed for an agent that has a runner bound
- **THEN** the verdict SHALL describe that runner
- **AND** the agent SHALL be reported launchable if that runner is launchable

#### Scenario: An agent with no runner bound
- **WHEN** launchability is probed for an agent with no runner bound
- **THEN** the verdict SHALL say that no runner is bound and what would fix it
- **AND** SHALL NOT name a CLI after the agent

#### Scenario: The probe and the spawn agree
- **WHEN** an agent is reported launchable
- **THEN** triggering it SHALL use the same runner the probe described

#### Scenario: An archived agent is not reported as launchable
- **WHEN** launchability is probed for a project holding an archived agent, without asking for that lifecycle
- **THEN** the archived agent SHALL NOT appear in the report
- **AND** no agent in the report SHALL be one that triggering would refuse as archived

#### Scenario: An archived agent is probed when explicitly asked for
- **WHEN** launchability is probed for the archived lifecycle
- **THEN** the archived agent SHALL appear with the verdict its bound runner supports

#### Scenario: An archived agent known only to the session configuration is excluded too
- **WHEN** launchability is probed and an archived agent's name is also present in the project's session configuration
- **THEN** that agent SHALL still be absent from the default report

### Requirement: A refusal that names a runner's holders names where to reach each one

Deleting a runner that agents are bound to SHALL be refused, and the refusal SHALL name every
holder together with enough to reach it: where a named holder is archived, the refusal SHALL say so
and SHALL say where an archived agent is found.

A refusal naming a repair the operator cannot locate is a wall, not a refusal. The default roster
excludes archived agents deliberately, so a bound-delete refusal that names one without qualifying
it sends the operator to a list the name is not in. The same shape was met once already on the
charter route and cost the operator the deletion.

The archived state SHALL be stated as part of the holder's name in the refusal rather than as a
separate count, so that an operator reading one sentence knows which of the named agents they will
not find.

#### Scenario: A runner held only by an archived agent
- **WHEN** an operator deletes a runner whose only bound agent is archived
- **THEN** the refusal SHALL name that agent as archived
- **AND** SHALL state where an archived agent can be found

#### Scenario: A runner held by both an open and an archived agent
- **WHEN** an operator deletes a runner bound to one open and one archived agent
- **THEN** the refusal SHALL name both
- **AND** SHALL qualify only the archived one

#### Scenario: A runner held only by open agents
- **WHEN** an operator deletes a runner bound only to agents in the default roster
- **THEN** the refusal SHALL name them without any archived qualification

### Requirement: A runner offered for choosing names its model

Wherever the operator chooses a runner from a list, each choice SHALL name the model that choice will run, as the operator reads it, once, alongside the runner's name and provider.

Runners of one provider may share a name and differ only in their model, and the model is what the
choice decides. A choice that leaves the model out offers the operator identical options that have
different effects.

The model a choice will run is the runner's own model, except where a setting beside the list
overrides the model for that use, in which case it is the overriding model. A runner whose name
already ends with its model's label is not labelled with the model a second time.

The model SHALL be named by the catalog's label where the catalog declares it, as the provider's
default where the runner records no model, and by the recorded identifier, marked as unrecognised,
where the catalog does not declare it.

#### Scenario: Two runners with one name are told apart

- **WHEN** a project holds two runners of one provider with the same name and different models
- **AND** the operator opens any list offering a runner to choose
- **THEN** the two choices read differently
- **AND** each names its own model

#### Scenario: A runner named after its model names it once

- **WHEN** a runner's name already ends with the label of the model it runs, as the Hub names the
  runners it creates
- **THEN** its choice names that model once

#### Scenario: An overriding model is the one named

- **WHEN** the operator chooses the runner that writes checkpoints
- **AND** the project sets a checkpoint model
- **THEN** each choice names the checkpoint model, not the runner's own

#### Scenario: A runner with no model names the provider's default

- **WHEN** a runner records no model
- **THEN** its choice names the provider's default as its model

#### Scenario: An unrecognised model is named as such

- **WHEN** a runner records a model the catalog does not declare
- **THEN** its choice names that model and marks it as unrecognised

### Requirement: A Copilot runner is spawned as its own executable

The Hub SHALL spawn a Copilot run by the Copilot CLI's native executable, never through an npm or script shim, and SHALL say which path it looked for when it cannot find one.

A shim runs a second process in front of the CLI. Stopping the shim can leave the CLI running. The
Hub SHALL resolve, in order:

1. a runner's pinned executable;
2. a `copilot` on `PATH` that is itself a native executable;
3. the platform binary inside the npm package that a `copilot` shim on `PATH` belongs to.

#### Scenario: An npm-installed Copilot on Windows

- **WHEN** `copilot` on `PATH` is the npm `copilot.cmd` shim
- **THEN** the Hub spawns `node_modules\@github\copilot\node_modules\@github\copilot-win32-x64\copilot.exe` beside it
- **AND** the spawned command's first argument is that executable, not the shim

#### Scenario: A Copilot agent is triggered

- **WHEN** an operator triggers an agent bound to a `copilot` runner on a machine where the Copilot CLI is installed and signed in
- **THEN** the Hub does not refuse the turn as an unsupported runner
- **AND** the spawned Copilot process is configured with the Hub's `agentweave` MCP server

#### Scenario: A shim whose platform binary is missing

- **WHEN** a `copilot` shim is on `PATH` and its package holds no binary for this platform
- **THEN** launchability reports the runner not present
- **AND** the reason names the path the Hub looked for

### Requirement: A Copilot runner below the supported version is refused

The Hub SHALL refuse to run a turn on a Copilot CLI older than its supported minimum version, 1.0.81, reading the version the CLI reports in its protocol handshake, and SHALL fail that turn before any session is created.

The version the Hub reads SHALL be the version that runs. The Hub SHALL spawn the CLI with automatic
updates disabled, so a cached newer package cannot run in place of the version it checked.

#### Scenario: An old CLI is refused

- **WHEN** a Copilot turn starts and the CLI reports version 1.0.75
- **THEN** the run fails with a reason naming 1.0.75, the supported minimum and how to update
- **AND** no Copilot session was created for the conversation

#### Scenario: A supported CLI proceeds

- **WHEN** a Copilot turn starts and the CLI reports version 1.0.88
- **THEN** the turn proceeds to create or load its session

#### Scenario: A missing version is treated as too old

- **WHEN** the CLI's handshake reports no version
- **THEN** the run fails as for a version below the minimum

### Requirement: A Copilot turn that fails after its prompt ends as a failed turn, not a failed start

Once a Copilot turn's prompt has been sent, the Hub SHALL record any failure of that turn as the run's failed outcome, keeping what the turn wrote, and SHALL NOT treat it as a turn that never started.

A failure after the prompt includes an error answer to the prompt, the Copilot process ending, the
turn timing out, and an error Copilot reports for the session's own agent during the turn. Copilot
can report such an error and still say the turn ended normally. The Hub SHALL then record the turn
as failed with Copilot's message, unless the turn was stopped. An error Copilot reports for a
subagent the turn started SHALL be recorded in the run's timeline and SHALL NOT by itself fail the
turn. A failure before the prompt SHALL still be
recorded as a failure to start. When that failure is Copilot reporting that it is not signed in
or is too old, the Hub SHALL record that verdict for the runner before the input is retried. The
retry is then held instead of failing the same way again.

#### Scenario: The prompt is answered with an error after the agent worked

- **WHEN** a Copilot turn has written a file in its worktree and its prompt is then answered with an error
- **THEN** the run ends failed with that error
- **AND** the worktree is snapshotted as for any finished turn

#### Scenario: A session error with a normal ending

- **WHEN** Copilot reports a session error during a turn and then ends the turn normally
- **THEN** the run ends failed with the session error's message

#### Scenario: A subagent's error with a normal ending

- **WHEN** Copilot reports an error for a subagent the turn started, and then ends the turn normally with no error for the session's own agent
- **THEN** the run does not end failed on that account
- **AND** the subagent's error appears in the run's timeline

#### Scenario: A sign-in failure holds the input

- **WHEN** a Copilot turn fails because Copilot is not signed in
- **THEN** the runner is reported not authorized with the `copilot login` sentence
- **AND** the operator's input stays queued without a delivery attempt being counted against it

### Requirement: Copilot launchability is read from Copilot itself

The Hub SHALL decide whether a Copilot runner is authorized by asking the Copilot CLI, and SHALL NOT decide it from GitHub token variables in the Hub's own environment.

The Copilot CLI keeps its sign-in in the operating system's credential store. A token variable in the
environment overrides that sign-in instead of proving it exists. The Hub SHALL reach its verdict
without a model call. It SHALL report a CLI that is not signed in, and a CLI below the supported
version, as not authorized, each with a reason that says what to do. A verdict the Hub has not yet
computed SHALL NOT make a Copilot agent uncreatable. In that case the run's own handshake is the
binding check. A verdict that the CLI is not signed in or is too old SHALL be checked again on the
next read of it, so that signing in or updating is seen without waiting for the verdict to age.

#### Scenario: A signed-in Copilot with no token variables

- **WHEN** the Hub's environment has no `GH_TOKEN`, `GITHUB_TOKEN` or `COPILOT_GITHUB_TOKEN` and the Copilot CLI is signed in
- **THEN** a Copilot runner is reported launchable

#### Scenario: A Copilot CLI that is not signed in

- **WHEN** the Copilot CLI refuses to create a session because no sign-in exists
- **THEN** a Copilot runner is reported not authorized
- **AND** the reason says to run `copilot login`

#### Scenario: Signing in is seen at once

- **WHEN** the Hub holds a verdict that the Copilot CLI is not signed in, and the operator then runs `copilot login`
- **THEN** the next read of the verdict starts a new check
- **AND** a read after that check completes reports the runner launchable

#### Scenario: The verdict is still being computed

- **WHEN** an operator creates a Copilot agent before the Hub has finished its first Copilot probe
- **THEN** creation is not refused on that account

