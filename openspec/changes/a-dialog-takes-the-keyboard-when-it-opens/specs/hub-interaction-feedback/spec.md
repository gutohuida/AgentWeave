## ADDED Requirements

### Requirement: A dialog takes the keyboard when it opens and gives it back when it closes

A dialog SHALL move keyboard focus into itself when it opens, and SHALL return focus to the control that opened it when it closes; a confirmation whose action cannot be undone SHALL open with focus on the choice that changes nothing.

A dialog that leaves the keyboard on the control that opened it answers the operator's next key with
that control, which sits behind the dialog where they cannot see it. A second Enter repeats the
action the dialog is asking about, and a screen reader never announces the question.

The choice that receives focus in a confirmation SHALL be marked explicitly rather than inferred from
the order the choices are drawn in, so that restyling a dialog cannot move the keyboard onto its
destructive choice.

Where every control in a dialog is unavailable, the dialog itself SHALL hold focus, so that the
keyboard is still inside the dialog and not behind it. Where the control holding focus becomes
unavailable while the dialog waits on the action it started, the dialog itself SHALL take focus.

This applies to every modal dialog the app draws, whether it asks a question, collects a form, or
connects the app to a Hub.

Where something inside a dialog is designed to take focus when the dialog opens, the dialog SHALL
still record, before that happens, where focus was, so that closing the dialog returns it there.

#### Scenario: Opening a confirmation puts the keyboard on Cancel

- **WHEN** the operator opens a confirmation whose action cannot be undone
- **THEN** keyboard focus is on the choice that changes nothing
- **AND** pressing Enter closes the dialog without taking the action

#### Scenario: Opening a dialog with a field puts the keyboard in the field

- **WHEN** the operator opens a dialog that asks them to type something
- **THEN** keyboard focus is in that field

#### Scenario: A dialog whose controls are all unavailable still holds the keyboard

- **WHEN** a dialog opens while every control in it is unavailable
- **THEN** keyboard focus is inside the dialog

#### Scenario: Closing a dialog returns the keyboard to what opened it

- **WHEN** the operator closes a dialog they opened from a control
- **THEN** keyboard focus is on that control

#### Scenario: A form dialog puts the keyboard in its first field and gives it back

- **WHEN** the operator opens a dialog that creates or edits a charter, a runner or a job, and then
  closes it with Escape
- **THEN** keyboard focus was in the dialog's first field while it was open
- **AND** keyboard focus is on the control that opened the dialog once it has closed

#### Scenario: A control disabled under the keyboard does not drop it behind the dialog

- **WHEN** the operator confirms a dialog's action and the control they used becomes unavailable
  while the action is pending
- **THEN** keyboard focus is inside the dialog
