# project-instructions Specification

## Purpose
Per-project instruction content stored in Hub DB and served before every agent's charter guidance; editable via Hub UI. `openspec/changes/single-runtime` removed the local-file mirror and its `agentweave init` placeholder — the Hub DB is now the only source.

## Requirements
### Requirement: Hub stores project instructions per project
The Hub DB SHALL store project-wide instruction content in a `ProjectInstructions` table scoped by `project_id`.

#### Scenario: Empty instructions on new project
- **WHEN** a project has no instructions saved
- **THEN** `GET /api/v1/project/instructions` returns `{ "content": "" }`

#### Scenario: Save instructions via Hub API
- **WHEN** a PUT request is made to `/api/v1/project/instructions` with `{ "content": "..." }`
- **THEN** the content is persisted and subsequent GET returns the same content

---

### Requirement: Hub prepends instructions to charter content
The Hub SHALL prepend project instructions before charter content in every direct
`GET /api/v1/agents/context` response and before charter guidance in full agent context.

#### Scenario: Instructions exist — prepended to charter
- **WHEN** project instructions are non-empty and an agent requests direct or full charter context
- **THEN** project instructions appear before the charter content

#### Scenario: No instructions — charter returned unchanged
- **WHEN** project instructions are empty or no instruction row exists
- **THEN** direct charter lookup returns the charter content unchanged

---

### Requirement: Hub UI provides instructions editor
The Hub UI SHALL provide an "Instructions" screen which, once the project's stored instructions have been read, presents them in a markdown textarea with a Save button and a session disclaimer.

The condition on the read having succeeded is load-bearing. Without it the screen promises a
pre-filled textarea on every navigation — a promise it cannot keep when the read does not succeed,
and keeping it anyway is what presents an empty editor over stored content. What the screen owes
when the read has *not* succeeded is stated by the two requirements below.

All three scenarios carry that condition, the disclaimer included: the disclaimer is rendered inside
the same block as the textarea, so a screen that states a failure instead of an editor does not show
it, and an unconditional scenario would require it in exactly the state it is correctly absent from.

The save scenario carries a second condition: the click it requires to persist is one that does not
blank stored content. That click is governed by *A save that would blank stored instructions is
confirmed first*. The condition is written as what the save does rather than as an exception for a
dialog, so the requirement stays a statement about saving and not about a particular control.

The condition names whitespace explicitly, in the same words as the condition on *Save cannot write
instructions that were never read* and on *A save that would blank stored instructions is confirmed
first*. Identical words are deliberate: a requirement is read on its own and cannot borrow a
neighbour's definition of "nothing", so two requirements that mean the same thing in different words
disagree the moment either is read alone — a shorter form here would demand that a save replacing
four hundred lines with a single newline persist on the click, while the other requirement demands
that same save be confirmed first.

#### Scenario: User saves instructions
- **WHEN** the stored instructions have been read, the user edits the textarea and clicks Save, and the edit does not replace stored instructions containing more than whitespace with content that is empty or only whitespace
- **THEN** content is persisted via PUT and UI confirms success

#### Scenario: Disclaimer shown
- **WHEN** the stored instructions have been read and the textarea is presented
- **THEN** a notice reads "Changes take effect when agents start a new session"

#### Scenario: Existing instructions loaded on open
- **WHEN** user navigates to the Instructions screen and the stored instructions are read successfully
- **THEN** the textarea is pre-filled with the current saved content

---

### Requirement: An unread instructions editor is not presented as the project's instructions
The Instructions screen SHALL present an editable instructions textarea only when the currently selected project's stored instructions have been read successfully, and SHALL state the failure in the section when the read fails.

A project whose instructions are empty and a project whose instructions could not be read are
different situations, and the screen has to be able to tell the operator which one they are looking
at. Presenting the second as the first is not merely uninformative: it invites the operator to act
on content that is not theirs and is not there.

Failure means the operator can see that something failed without opening a console or a log, is told
what failed in a sentence that is useful even when the transport produced no server response to
quote, and can retry the read from that surface without reloading the application.

A read that has not completed yet is not a failure and is presented as loading, which is what the
screen already does.

A successful read that a later background read fails does not remove the content already on screen:
what is displayed remains the content that was read, so that a refetch cannot take an editor away
from an operator who is typing into it.

#### Scenario: A failed read does not render an empty editor

- **WHEN** the request for the project's instructions fails, whether by transport failure or by an
  error response, and its retries are exhausted
- **THEN** no editable instructions textarea is presented
- **AND** the section states that the instructions could not be loaded, in a form assistive
  technology announces
- **AND** the operator is offered a way to retry the read without reloading the application

#### Scenario: A failed read reports something useful with no server response to quote

- **WHEN** the request fails without producing a response body, as a dropped connection does
- **THEN** the stated failure still names what could not be loaded and says that nothing stored has
  been changed

#### Scenario: A retry after the failure restores the editor

- **WHEN** the operator retries from the failure surface and the read succeeds
- **THEN** the textarea is presented, pre-filled with the stored content

#### Scenario: A read still in flight is presented as loading, not as failed

- **WHEN** the request for the project's instructions has not settled
- **THEN** the screen presents its loading state and states no failure

#### Scenario: A background read failure does not take away a loaded editor

- **WHEN** the instructions have been read successfully and presented, and a later read of the same
  project's instructions fails
- **THEN** the textarea and its content remain on screen

#### Scenario: Another project's instructions are never shown for this one

- **WHEN** the selected project changes while the screen stays open, and the newly selected
  project's instructions cannot be read
- **THEN** no textarea presents the previously selected project's content

---

### Requirement: A save that would blank stored instructions is confirmed first
The Instructions screen SHALL obtain the operator's confirmation before issuing a write that would replace stored instructions containing more than whitespace with content that is empty or only whitespace, and SHALL issue no such write until that confirmation is given.

Nothing in AgentWeave keeps a copy of a project's instructions. The store is a single row per
project, replaced in place on save; there is no history, no revision and no restore. So a save that
blanks stored content is unrecoverable, and it is reached by the same single click as a save that
changes one word.

The confirmation is asked on that path and no other. A confirmation the operator meets on every save
is a confirmation they learn to dismiss, which would leave the destructive path no better protected
than it is now and every other path worse.

The stored side of that comparison is the content that was actually read for the currently
selected project — not a value the screen holds without having loaded it, and not the operator's own
earlier keystrokes. Where the read has not succeeded, no write may leave the screen at all, which
the requirement below already states; this requirement adds a condition to writes that are otherwise
permitted and removes none.

Whitespace is not content, on either side of the comparison. A textarea holding a stray newline
destroys stored instructions exactly as an empty one does, and stored content that is only
whitespace is not a loss worth interrupting a save for. The statement above says this in its own
words rather than defining it once and borrowing it: a requirement is read on its own, and a
neighbouring requirement that said only "with nothing" would be in direct conflict with this one
over a save that writes a single newline.

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
  stored instructions are already empty or contain only whitespace
- **THEN** the save is issued directly and no confirmation is asked

#### Scenario: The comparison uses the content that was read, not the screen's state

- **WHEN** a project's instructions have been read successfully and a later read of the same
  project's instructions fails, and the operator then empties the editor and saves
- **THEN** the confirmation is asked, measured against the content that was last read successfully

---

### Requirement: Save cannot write instructions that were never read
The Instructions screen SHALL NOT issue a write of instruction content for a project whose stored instructions have not been read successfully.

The route accepts the empty string on purpose — clearing a project's instructions is a legitimate
thing for an operator to ask for — so the store cannot distinguish an intended clear from a client
sending state it never loaded. The client is therefore the only place the distinction exists, and it
is the client that must not send the second.

This is stated as an outcome rather than as a property of a control. A screen that renders no Save
control while the read has not succeeded satisfies it, and so does one that renders an inert control;
what neither may do is let a write leave.

The last scenario below is the positive complement of this prohibition — it says the ban lifts once
the read succeeds — and it carries a condition, word for word the same as the one on the save
scenario of *Hub UI provides instructions editor*, that holds the lift back from the one save that
blanks stored content. Without it, an edit that empties the editor is still an edit, and this
requirement would demand on the plain reading that such a save be written on the click while *A save
that would blank stored instructions is confirmed first* demands it not be — a pair that declining
the confirmation makes demonstrably incompatible on one concrete sequence, not merely awkward
together.

#### Scenario: The failed-read surface issues no write

- **WHEN** the read of a project's instructions has failed and the operator interacts with the
  screen
- **THEN** no request that writes instruction content is issued for that project

#### Scenario: A read still in flight issues no write

- **WHEN** the read of a project's instructions has not settled — whether on first attempt or
  during a retry — and the operator interacts with the screen
- **THEN** no request that writes instruction content is issued for that project

#### Scenario: Stored instructions survive the failed read

- **WHEN** the read fails, the operator interacts with the screen, and the stored instructions are
  read afterwards by any means
- **THEN** their content is what it was before the failure

#### Scenario: Saving works again once the read succeeds

- **WHEN** the read succeeds, whether on first attempt or after a retry, and the operator edits and
  saves, and the edit does not replace stored instructions containing more than whitespace with
  content that is empty or only whitespace
- **THEN** the edited content is written and the outcome is reported as it is for any other save
