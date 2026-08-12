# local-project-workspace Specification

## Purpose
TBD - created by archiving change 2026-08-03-local-multi-project-workspace. Update Purpose after archive.
## Requirements
### Requirement: Projects have stable directory-backed identity

Each project SHALL have a stable project identifier and one canonical absolute working directory.
The identifier SHALL survive project rename and explicit directory relocation. The system MUST
reject two active project records resolving to the same canonical directory.

A registered directory SHALL contain a versioned, non-secret AgentWeave project marker carrying its
stable project identifier. The marker MUST NOT contain credentials, settings, or an absolute path.

#### Scenario: The same directory is opened twice

- **WHEN** an operator opens a directory already registered through an equivalent path
- **THEN** the existing project is selected
- **AND** no duplicate project is created

#### Scenario: A project directory is relocated

- **WHEN** an unavailable project's marked directory is opened at a new path and it has no active
  run or worktree mutation
- **THEN** the existing project is rebound to the new canonical directory
- **AND** every task, conversation, run, agent, and setting retains the same project identifier

#### Scenario: A marker was copied

- **WHEN** a marked directory and the existing registered directory are both available
- **THEN** the copy is reported as an identity conflict
- **AND** it is not merged or adopted without an explicit register-copy-as-new action

### Requirement: Project paths are resolved safely by the server

The system SHALL canonicalize project directories server-side and SHALL route every project
filesystem operation through one project workspace resolver. It MUST reject filesystem roots, the
Hub data directory, nested AgentWeave worktree directories, traversal, control characters, and
symlink or junction escapes.

No project-aware runtime operation SHALL use the Hub process working directory as project identity.

#### Scenario: Two projects run concurrently

- **WHEN** agents in two projects run at the same time
- **THEN** each process, context file, workspace search, and worktree operation uses only its own
  project's directory or isolated worktree

#### Scenario: A relative subdirectory escapes

- **WHEN** an execution or path request resolves outside the project or effective worktree root
- **THEN** it is refused before any file or process operation occurs

### Requirement: Project creation and opening are explicit and bounded

The operator SHALL be able to open an existing directory or explicitly create and register one new
directory. Opening MUST NOT create the target directory. Creating MUST create exactly the requested
new directory and MUST refuse an existing non-empty target.

Creation SHALL be expressed as an existing parent directory plus a name for the new project. The
created directory SHALL be that name within that parent, and the project SHALL take that same name.
The operator SHALL NOT be required to compose a filesystem path in order to create a project.

The parent directory MUST already exist. Creation SHALL NOT create intermediate directories.

A project name offered at creation MUST be a single path segment. A name that is empty, that contains
a path separator, that is a traversal segment, or that the host filesystem rejects SHALL be refused
with a message naming the problem, and MUST NOT be silently rewritten into an acceptable one.

Before the operator confirms, the interface SHALL show the absolute path that will be created,
derived from the same values that are submitted.

Registration SHALL atomically create the project, seed its default runners and starter charters,
and write its identity marker. It SHALL NOT initialize git, start an agent, create a specification,
or otherwise modify project source.

#### Scenario: An existing directory is opened

- **WHEN** the operator chooses Open and supplies an available unregistered directory
- **THEN** it is registered without changing its source content beyond AgentWeave runtime metadata
- **AND** it becomes the selected project

#### Scenario: A new directory is created from a parent and a name

- **WHEN** the operator chooses Create, supplies an existing parent directory and the name `my-app`
- **THEN** exactly `my-app` is created within that parent and registered
- **AND** the project is named `my-app`

#### Scenario: The target is shown before it is created

- **WHEN** the operator has supplied a parent and a name
- **THEN** the absolute path that will be created is displayed before confirmation

#### Scenario: A name that is not a directory name is refused

- **WHEN** the operator supplies a project name containing a path separator or a traversal segment
- **THEN** creation is refused with a message naming the problem
- **AND** no directory is created, and the name is not rewritten into an acceptable one

#### Scenario: Marker creation fails

- **WHEN** the identity marker cannot be written during a new registration
- **THEN** the project transaction is rolled back or reported as incomplete with a repair action
- **AND** no silently unusable project is presented as ready

### Requirement: The local operator reaches a project collection without project authentication

The local application SHALL maintain one automatically discovered instance-local operator
credential. It SHALL authorize access to the project collection but SHALL NOT select or imply one
project. Operator project resources SHALL carry explicit project identity in their route.

Run-bound agent credentials SHALL remain scoped to their recorded run, agent, and project and MUST
NOT accept caller-selected project identity.

#### Scenario: The operator lists projects

- **WHEN** the local app authenticates with its automatically discovered instance credential
- **THEN** it can list every registered project and its safe summary
- **AND** no login or project-key selection is required

#### Scenario: An agent attempts cross-project access

- **WHEN** a run credential calls an agent operation while naming another project
- **THEN** the supplied identity is rejected or ignored
- **AND** the operation remains bound to the run's recorded project

### Requirement: Project settings are managed as one validated resource

Each project SHALL expose its name, hop budget, per-turn delivery cap, agent budget, token budget,
and agent-job allowance through project-scoped settings. Updates SHALL be validated and SHALL take
effect through the existing scheduling and budget services.

Directory relocation MUST be a distinct guarded action and MUST NOT be a generic settings field.

#### Scenario: Project limits are changed

- **WHEN** the operator saves valid project limit settings
- **THEN** subsequent queue, agent-creation, accounting, and job decisions use those values

#### Scenario: Invalid settings are submitted

- **WHEN** a setting is outside its accepted range or type
- **THEN** the complete invalid update is rejected with field-specific diagnostics

### Requirement: Unavailable project directories preserve state and pause execution

A project whose directory is missing, unreadable, not a directory, or in identity conflict SHALL
remain visible with that state. Its stored history, tasks, and conversations SHALL remain readable.

New operator input and new process starts MUST be refused while unavailable. Existing queued entries
and enabled jobs SHALL remain durable; autonomous and scheduled work SHALL pause and be reconsidered
after successful repair.

#### Scenario: A directory disappears

- **WHEN** a registered project directory becomes unavailable
- **THEN** the project remains visible with a repairable state
- **AND** no new agent process starts for it

#### Scenario: The directory is repaired

- **WHEN** the project is successfully rebound or becomes available again
- **THEN** its queued work is reconsidered under current budgets and hop limits
- **AND** jobs and entries have not been silently disabled or deleted

### Requirement: One live operator stream identifies every project event

The local app SHALL receive one operator event stream for the instance. Every project-scoped event
SHALL include a `project_id` stamped by the server from trusted context. The stream SHALL carry
updates for inactive projects so their navigation state remains live.

#### Scenario: An inactive project changes

- **WHEN** an agent or scheduled job changes a project that is not selected
- **THEN** the one operator stream emits an event carrying that project's identifier
- **AND** its rail summary updates without switching to it

#### Scenario: A caller supplies a false project field

- **WHEN** an event-producing operation includes an untrusted project value in its payload
- **THEN** the operator envelope uses the authenticated or recorded project identity instead

### Requirement: Frontend server state is isolated by project

Every project-scoped query, mutation, invalidation, URL destination, and persisted draft SHALL carry
the stable project identifier. Switching projects while requests are in flight MUST NOT allow one
project's response or event to populate another project's view.

#### Scenario: A delayed response crosses a switch

- **WHEN** the operator switches from project A to project B before project A's request completes
- **THEN** the response remains cached only under project A
- **AND** project B's rendered state is unchanged

#### Scenario: Navigation reloads

- **WHEN** a project view or agent conversation URL is reloaded
- **THEN** the same project and AgentWeave destination are restored
- **AND** no provider session identifier is used as navigation identity

### Requirement: Project views live inside the selected project

Navigation SHALL list registered projects and their live agents. Opening a project SHALL expose
Overview, Tasks, Spec, Jobs, Activity, and Environment within the content area; adding another
project view MUST NOT add a navigation-rail destination.

Overview SHALL surface unanswered questions, Activity SHALL contain logs, and Environment SHALL
contain quality, instructions, runners, charters, worktrees, diagnostics, budgets, and settings.

#### Scenario: Two projects are shown

- **WHEN** two projects are registered
- **THEN** both and their agents appear in the rail
- **AND** opening either project shows only its own project views and data

#### Scenario: Project pages leave the rail

- **WHEN** the rail is inspected
- **THEN** tasks, spec, jobs, activity, environment, questions, logs, quality, instructions,
  runners, and charters are not top-level rail destinations
- **AND** their functionality remains reachable from the selected project

### Requirement: Agent identity color remains project-consistent

An agent's assigned color SHALL be the same in navigation, conversation, task assignment, and
activity within its project. Color MUST always be accompanied by the agent name, and lookup MUST use
both project and agent identity.

#### Scenario: The same agent appears across surfaces

- **WHEN** an agent is shown in the rail, conversation, a task assignee, and activity
- **THEN** each surface uses the same project-assigned color and textual name

### Requirement: Legacy single-project state migrates without deletion

An existing unbound `proj-default` and its related records SHALL be preserved. On the first explicit
open, exactly one unbound legacy project SHALL bind to that directory instead of creating a second
project. The existing bootstrap secret SHALL become the instance operator credential without
changing its value.

The system MUST NOT bind legacy state to the Hub process directory implicitly.

#### Scenario: An existing installation is opened

- **WHEN** a pre-change installation with one unbound project invokes AgentWeave from its project
  directory
- **THEN** that project is bound to the directory
- **AND** its agents, conversations, tasks, runs, settings, and credential continuity are preserved

#### Scenario: Hub starts directly after migration

- **WHEN** the Hub starts without an invocation directory
- **THEN** the legacy project remains unbound and repairable
- **AND** no package, data, or process directory is guessed as its workspace

### Requirement: Docker registrations are limited to a mounted workspace root

When AgentWeave runs in explicit Docker mode, it SHALL accept only project directories visible
beneath a configured container workspace root. A host path that is not mounted MUST produce a typed
mount diagnostic. The system MUST NOT mount the Docker socket or guess host/container path mappings.

#### Scenario: A mounted project opens in Docker

- **WHEN** a project directory is visible beneath the configured container workspace root
- **THEN** it can be registered using its container-visible canonical path

#### Scenario: A host-only path is submitted

- **WHEN** a directory exists on the host but is not visible within the container workspace root
- **THEN** registration is refused with the required mount information

### Requirement: The operator can browse for a project directory

The Hub UI SHALL let the operator browse the filesystem visible to the Hub process to choose a
project directory, rather than requiring an absolute path to be typed from memory.

What browsing returns SHALL be directly usable in the mode it was invoked from, without the operator
editing it. Because browsing yields a directory that exists, in create mode it SHALL supply the
parent directory rather than the project directory itself.

#### Scenario: Browsing supplies a usable value in create mode

- **WHEN** the operator browses for a directory while creating a project
- **THEN** the chosen directory becomes the parent, and the operator supplies only a name
- **AND** the operator is not required to edit the chosen path

#### Scenario: Browsing supplies a usable value in open mode

- **WHEN** the operator browses for a directory while opening a project
- **THEN** the chosen directory is the project directory, and no further editing is required

### Requirement: Directory listing is authenticated and bounded

The directory-listing endpoint SHALL require the same authentication as every other Hub endpoint.

The endpoint SHALL NOT follow a symbolic link out of the directory being listed.

Where a workspace root is configured, listings SHALL remain within it and a request outside it SHALL
be refused with a stated reason. Where no workspace root is configured, any directory the Hub
process can read MAY be listed.

#### Scenario: An unauthenticated listing is refused

- **WHEN** a directory listing is requested without valid authentication
- **THEN** the request is refused and no directory contents are returned

#### Scenario: A symlink does not escape the listing

- **WHEN** a listed directory contains a symbolic link pointing outside it
- **THEN** the listing does not traverse that link

#### Scenario: A configured workspace root bounds browsing

- **WHEN** a workspace root is configured and a directory outside it is requested
- **THEN** the request is refused with a stated reason

### Requirement: A project directory can be chosen through the host's own folder dialog

Where the Hub runs directly on the operator's machine, choosing a project directory SHALL be
possible through the host operating system's own folder-selection dialog, returning a real
filesystem path.

The Hub SHALL report whether this is available before offering it, so the operator is never offered
a dialog that cannot open. Availability depends on the host and on the Hub not running in a
container.

Opening the dialog MUST NOT block the Hub's handling of other requests. The Hub SHALL remain
responsive while a dialog is open.

Where the dialog is unavailable, directory selection SHALL remain possible by browsing
Hub-visible directories and by typing a path directly. Neither of those paths is removed by this
requirement.

#### Scenario: The dialog returns a real path

- **WHEN** the operator chooses a directory through the host dialog
- **THEN** the Hub receives that directory's filesystem path
- **AND** the path is usable to register a project without further translation

#### Scenario: Availability is known before it is offered

- **WHEN** the directory-selection interface is displayed
- **THEN** the host dialog is offered only where the Hub reports it available

#### Scenario: A containerised Hub does not offer it

- **WHEN** the Hub runs in a container
- **THEN** the host dialog is reported unavailable
- **AND** browsing Hub-visible directories remains offered

#### Scenario: The Hub stays responsive

- **WHEN** a host dialog is open
- **THEN** the Hub continues to serve other requests

#### Scenario: Typing a path is unaffected

- **WHEN** the host dialog is available
- **THEN** the operator can still type a directory path directly

### Requirement: Cancelling, timing out, and failing are distinct outcomes

Directory selection through the host dialog SHALL distinguish the operator cancelling, the request
timing out, and the dialog failing to open.

Cancelling SHALL leave the operator's current input unchanged and MUST NOT be reported as an error.
A timeout and a failure SHALL each be reported in terms naming what happened, and SHALL leave the
other selection methods available.

A request for a dialog while one is already open MUST NOT open a second dialog.

#### Scenario: Cancelling is not an error

- **WHEN** the operator cancels the host dialog
- **THEN** no error is reported
- **AND** any directory path already entered is unchanged

#### Scenario: A timeout is reported as a timeout

- **WHEN** a dialog request exceeds the Hub's waiting period
- **THEN** the outcome is reported as a timeout
- **AND** the other selection methods remain available

#### Scenario: A failure to open is reported as such

- **WHEN** the host dialog cannot be opened
- **THEN** the outcome names the failure
- **AND** the other selection methods remain available

#### Scenario: A second request does not open a second dialog

- **WHEN** a dialog is requested while one is already open
- **THEN** no second dialog is opened
