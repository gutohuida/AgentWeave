# spec-chat-session

## MODIFIED Requirements

### Requirement: A specification document opens beside a conversation

A specification document SHALL open as the `spec` panel within the conversation's panel shell,
alongside the conversation rather than in a separate screen, and the operator SHALL be able to close
it and recover the full width for the conversation. The shell MAY also host the `loop` and `files`
panels beside it; opening either of those MUST NOT close or discard an open document, only change
which panel is currently shown.

The open document SHALL be part of the addressed destination, so that reloading or sharing the
location restores both the conversation and the document open in it, together with whichever panel
was active.

A document panel available in any conversation is what makes the relationship between a thread and
a document a link the operator makes, rather than a category the thread was born into — which is
what "a thread's phase derives from the document open in it" requires. A separate specification
screen forces the opposite: a thread is a specification thread because of where it was opened. This
remains true with the panel shell generalized to host other content beside the document: the document
is still reached from the conversation it is a link from, never from a separate screen.

#### Scenario: Opening a document from a conversation

- **WHEN** the operator opens a specification document while in a conversation
- **THEN** the document is shown in the shell's `spec` panel beside that conversation
- **AND** the conversation remains usable without leaving it

#### Scenario: The location survives a reload

- **WHEN** the operator reloads with a document open beside a conversation
- **THEN** the same conversation and the same document are open, in the `spec` panel

#### Scenario: Closing the document

- **WHEN** the operator closes the document panel
- **THEN** the conversation occupies the full available width
- **AND** no specification navigation remains on screen

#### Scenario: Switching to another panel does not close the document

- **WHEN** the operator has a document open and switches the shell to the `loop` or `files` panel
- **THEN** the document remains open, attached to the conversation
- **AND** switching back to the `spec` panel shows the same document, not a picker
