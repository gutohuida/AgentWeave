## ADDED Requirements

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

### Requirement: Browsing reaches any location and discloses how to choose one

Browsing Hub-visible directories SHALL let the operator reach any Hub-visible directory without
knowing its path in advance. It SHALL present the available filesystem roots, show the current
location as navigable structure, and allow choosing the current location directly.

This extends "The operator can browse for a project directory", introduced by
`2026-08-04-hub-model-control-and-provisioning`, which must be synced to the main specs before this
change is applied.

Choosing a directory MUST NOT depend on an interaction the interface does not indicate. Where
navigating into a directory and choosing it are distinct actions, each SHALL have its own visible
affordance.

Browsing SHALL be operable from the keyboard alone.

#### Scenario: Roots are reachable without typing

- **WHEN** the operator opens the directory browser
- **THEN** the available filesystem roots can be reached without typing a path

#### Scenario: The current location is navigable structure

- **WHEN** the operator is browsing a directory
- **THEN** the current location is shown as navigable structure
- **AND** an ancestor can be returned to directly

#### Scenario: Choosing has its own affordance

- **WHEN** the operator wants to choose the directory they are viewing
- **THEN** a visible control chooses it
- **AND** no undisclosed interaction is required

#### Scenario: Browsing works from the keyboard

- **WHEN** the operator uses only the keyboard
- **THEN** they can move between entries, enter a directory, return to its parent, and choose a directory
