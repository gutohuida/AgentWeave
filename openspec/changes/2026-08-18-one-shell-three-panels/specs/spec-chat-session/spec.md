# spec-chat-session

## MODIFIED Requirements

### Requirement: A specification document opens beside a conversation

A specification document SHALL open in a keyed tab within the conversation's panel shell, alongside
the conversation rather than in a separate screen, and the operator SHALL be able to close it and
recover the full width for the conversation. The shell MAY host other tabs beside it; opening or
switching to another tab MUST NOT close or discard an open document, only change which tab is shown.

The document **attached** to a conversation — the one an agent writes into while exploring — SHALL
remain part of the addressed destination, so that reloading or sharing the location restores both the
conversation and the document attached to it. Closing the tab that *displays* a document MUST NOT
detach the document from the conversation: tidying the panel is not an edit to what the agent is
working on.

More than one document MAY be open for reading at the same time, independently of which one is
attached to the conversation.

A document panel available in any conversation is what makes the relationship between a thread and a
document a link the operator makes, rather than a category the thread was born into — which is what
"a thread's phase derives from the document open in it" requires. A separate specification screen
forces the opposite: a thread is a specification thread because of where it was opened. This remains
true with the shell generalized to host other content: the document is still reached from the
conversation it is a link from, never from a separate screen.

#### Scenario: Opening a document from a conversation

- **WHEN** the operator opens a specification document while in a conversation
- **THEN** the document is shown in its own tab in the shell beside that conversation
- **AND** the conversation remains usable without leaving it

#### Scenario: The attached document survives a reload

- **WHEN** the operator reloads with a document attached to the conversation
- **THEN** the same conversation is open with the same document still attached to it

#### Scenario: Closing the document's tab does not detach it

- **GIVEN** a conversation with a document attached and that document's tab open
- **WHEN** the operator closes the tab
- **THEN** the document remains attached to the conversation
- **AND** the composer still names it as the attached document

#### Scenario: Reading one document while another is attached

- **GIVEN** a conversation with one document attached
- **WHEN** the operator opens a different document for reading
- **THEN** both are readable, and the attached document is unchanged

#### Scenario: Switching to another tab does not close the document

- **WHEN** the operator has a document open and switches the shell to another tab
- **THEN** the document's tab remains open
- **AND** switching back to it shows the same document, not a picker

#### Scenario: Closing every tab restores the conversation's full width

- **WHEN** the operator closes every open tab in the shell
- **THEN** the conversation occupies the full available width
- **AND** no specification navigation remains on screen
