## ADDED Requirements

### Requirement: The app window keeps what the app stored between launches

The native desktop window SHALL keep what the application stores in the browser between one launch and the next, in a location beneath the product's own home directory, and SHALL NOT discard it when the window closes.

A desktop application that forgets its preferences each time it is closed reads as broken, whatever
it stores. The loss is wider than any single preference: the appearance, the open project, the
layout of the navigation, and text the operator typed and has not sent all live in the same store.

The location SHALL be one the product names and owns, so that a later reset can find it. Credentials
the application holds only for the life of a window session SHALL remain scoped to that session.

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
