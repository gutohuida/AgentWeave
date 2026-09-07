## ADDED Requirements

### Requirement: A save that would blank stored instructions is confirmed first
The Instructions screen SHALL obtain the operator's confirmation before issuing a write that would replace non-empty stored instructions with nothing, and SHALL issue no such write until that confirmation is given.

Nothing in AgentWeave keeps a copy of a project's instructions. The store is a single row per
project, replaced in place on save; there is no history, no revision and no restore. So a save that
blanks stored content is unrecoverable, and it is reached by the same single click as a save that
changes one word.

The confirmation is asked on that path and no other. A confirmation the operator meets on every save
is a confirmation they learn to dismiss, which would leave the destructive path no better protected
than it is now and every other path worse.

What "non-empty" is measured against is the content that was actually read for the currently
selected project — not a value the screen holds without having loaded it, and not the operator's own
earlier keystrokes. Where the read has not succeeded, no write may leave the screen at all, which
the requirement below already states; this requirement adds a condition to writes that are otherwise
permitted and removes none.

Content that is only whitespace is nothing for this purpose, on both sides of the comparison: a
textarea holding a stray newline destroys stored instructions exactly as an empty one does.

Declining the confirmation writes nothing, changes nothing stored, and leaves the operator's own
editor state as they left it.

#### Scenario: Clearing loaded instructions asks before writing

- **WHEN** a project's stored instructions have been read and are non-empty, and the operator empties
  the editor and saves
- **THEN** no request that writes instruction content is issued
- **AND** the operator is asked to confirm, in a statement that identifies the project, says how much
  content would be discarded, and says that nothing keeps a copy of it

#### Scenario: Whitespace is not content

- **WHEN** the operator leaves only whitespace in the editor and saves over non-empty stored
  instructions
- **THEN** the confirmation is asked, as it is for an entirely empty editor

#### Scenario: Declining leaves the stored instructions untouched

- **WHEN** the operator declines the confirmation
- **THEN** no request that writes instruction content is issued
- **AND** reading the project's stored instructions afterwards by any means returns what they were
- **AND** what the operator typed is still in the editor

#### Scenario: Confirming performs the ordinary save

- **WHEN** the operator confirms
- **THEN** the content is written exactly as it was typed
- **AND** the outcome is reported as it is for any other save

#### Scenario: A save that blanks nothing is not interrupted

- **WHEN** the operator saves content that is not empty, or saves an empty editor for a project whose
  stored instructions are already empty
- **THEN** the save is issued directly and no confirmation is asked

#### Scenario: The comparison uses the content that was read, not the screen's state

- **WHEN** a project's instructions have been read successfully and a later read of the same
  project's instructions fails, and the operator then empties the editor and saves
- **THEN** the confirmation is asked, measured against the content that was last read successfully

## MODIFIED Requirements

### Requirement: Hub UI provides instructions editor
The Hub UI SHALL provide an "Instructions" screen which, once the project's stored instructions have been read, presents them in a markdown textarea with a Save button and a session disclaimer.

The condition on the read having succeeded is load-bearing. Without it the screen promises a
pre-filled textarea on every navigation — a promise it cannot keep when the read does not succeed,
and keeping it anyway is what presents an empty editor over stored content. What the screen owes
when the read has *not* succeeded is stated by the two requirements added by
`2026-09-06-an-unread-editor-cannot-overwrite`.

All three scenarios carry that condition, the disclaimer included: the disclaimer is rendered inside
the same block as the textarea, so a screen that states a failure instead of an editor does not show
it, and an unconditional scenario would require it in exactly the state it is correctly absent from.

**The save scenario gains a second condition in this change.** Read without it, it requires every
click on Save to persist — which is no longer true of the one click that would blank non-empty
stored instructions, and that click is now governed by *A save that would blank stored instructions
is confirmed first*. The condition is written as what the save does rather than as an exception for
a dialog, so the requirement stays a statement about saving and not about a particular control.

#### Scenario: User saves instructions
- **WHEN** the stored instructions have been read, the user edits the textarea and clicks Save, and the edit does not replace non-empty stored instructions with nothing
- **THEN** content is persisted via PUT and UI confirms success

#### Scenario: Disclaimer shown
- **WHEN** the stored instructions have been read and the textarea is presented
- **THEN** a notice reads "Changes take effect when agents start a new session"

#### Scenario: Existing instructions loaded on open
- **WHEN** user navigates to the Instructions screen and the stored instructions are read successfully
- **THEN** the textarea is pre-filled with the current saved content
