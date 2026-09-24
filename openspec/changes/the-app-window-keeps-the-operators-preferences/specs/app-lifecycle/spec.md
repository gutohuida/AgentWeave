## ADDED Requirements

### Requirement: The app window keeps what the app stored between launches

The native desktop window SHALL keep what the application stores in the browser between one launch and the next, in a location beneath the product's own home directory, and SHALL NOT discard it when the window closes.

A desktop application that forgets its preferences each time it is closed reads as broken, whatever
it stores. The loss is wider than any single preference: the appearance, the open project, the
layout of the navigation, and text the operator typed and has not sent all live in the same store.

The location SHALL be one the product names and owns, so that a later reset can find it. Credentials
the application holds only for the life of a window session SHALL remain scoped to that session.

Each profile SHALL keep its own stored window state, inside that profile's own data, so that one
profile's window never reads or writes another's. `agentweave reset` SHALL remove the stored window
state of the profile it targets, and only that profile's. When reset cannot remove it, because a
window still holds it open, reset SHALL say so, name what remained, and SHALL NOT report success.

#### Scenario: A preference survives closing and reopening the window

- **WHEN** the operator changes a preference in the native window, closes the window, and opens the
  application again
- **THEN** the preference is as they left it

#### Scenario: An unsent draft survives closing and reopening the window

- **WHEN** the operator types into a conversation's composer without sending, closes the window, and
  opens the application again
- **THEN** the text is still in that conversation's composer

#### Scenario: A window that cannot open its profile still falls back

- **WHEN** the native window cannot be created because its stored profile cannot be opened
- **THEN** the system reports what could not be created
- **AND** falls back to the browser-window behavior

#### Scenario: Two profiles keep separate window state

- **WHEN** the operator opens the app window for profile `a` and for profile `b`
- **THEN** each window keeps its state in its own profile's data
- **AND** a preference changed in one does not appear in the other

#### Scenario: Reset clears the targeted profile's window state only

- **WHEN** the operator confirms `agentweave reset --profile a` while profiles `a` and `b` both have
  stored window state
- **THEN** profile `a`'s stored window state is removed
- **AND** profile `b`'s is untouched

#### Scenario: Reset that cannot remove held window state does not report success

- **WHEN** the operator confirms `agentweave reset` while an app window of that profile still holds
  its stored state open
- **THEN** reset names what could not be removed and tells the operator to close the window
- **AND** it exits with a failure status and does not report the data destroyed
