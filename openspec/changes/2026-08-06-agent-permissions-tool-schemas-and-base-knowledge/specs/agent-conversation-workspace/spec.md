## ADDED Requirements

### Requirement: A conversation opens at its most recent activity

Opening or switching to a conversation SHALL place the view at its newest entry, and SHALL resume
following new output.

The most recent activity is what an operator opening a conversation is looking for; landing on the
oldest entry of a long history buries it.

#### Scenario: Opening a conversation with history

- **WHEN** the operator opens a conversation that already has entries
- **THEN** the view is positioned at the newest entry

#### Scenario: Switching conversations

- **WHEN** the operator switches from one conversation to another
- **THEN** the newly shown conversation is positioned at its newest entry
- **AND** following of new output is active

---

### Requirement: Following tracks the entries the conversation renders

Whether the view follows new output SHALL be determined by the conversation entries actually
displayed, not by any other stream.

Following that observes a different source than the one being rendered will either fail to move when
content arrives or move when nothing visible has changed.

#### Scenario: New conversation content is followed

- **WHEN** the view is at the bottom and a new entry is added to the conversation
- **THEN** the view moves to keep the newest entry visible

---

### Requirement: A suspended conversation offers a way back to the newest entry

While following is suspended, the conversation SHALL offer a control that returns the view to the
newest entry and resumes following.

That control SHALL appear only while following is suspended. It is not a toggle: it expresses
"return me to the newest entry", and following remains governed by scroll position.

#### Scenario: The control appears only when suspended

- **WHEN** the view is following new output
- **THEN** no return-to-newest control is shown

#### Scenario: The control returns and resumes

- **WHEN** following is suspended and the operator activates the return-to-newest control
- **THEN** the view moves to the newest entry
- **AND** following resumes
