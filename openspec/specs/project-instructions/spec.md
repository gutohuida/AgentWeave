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

#### Scenario: User saves instructions
- **WHEN** the stored instructions have been read, the user edits the textarea and clicks Save
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

### Requirement: Save cannot write instructions that were never read
The Instructions screen SHALL NOT issue a write of instruction content for a project whose stored instructions have not been read successfully.

The route accepts the empty string on purpose — clearing a project's instructions is a legitimate
thing for an operator to ask for — so the store cannot distinguish an intended clear from a client
sending state it never loaded. The client is therefore the only place the distinction exists, and it
is the client that must not send the second.

This is stated as an outcome rather than as a property of a control. A screen that renders no Save
control while the read has not succeeded satisfies it, and so does one that renders an inert control;
what neither may do is let a write leave.

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
  saves
- **THEN** the edited content is written and the outcome is reported as it is for any other save
