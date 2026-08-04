## ADDED Requirements

### Requirement: The conversation is a single plane, not stacked boxes

The conversation SHALL read as one continuous surface. Its header and the region containing its
composer MUST NOT be drawn as filled bands closed by dividing rules.

The header SHALL sit on the same ground plane as the stream, separating itself from scrolled content
by translucency rather than by a fill and a border. The transition from the stream to the composer
region SHALL be a fade to the ground plane rather than a drawn edge.

#### Scenario: No band encloses the header

- **WHEN** an agent conversation is open
- **THEN** the header carries no fill distinct from the ground plane and no dividing rule beneath it

#### Scenario: No band encloses the composer

- **WHEN** an agent conversation is open
- **THEN** the region containing the composer carries no fill distinct from the ground plane and no
  dividing rule above it

#### Scenario: Scrolled content stays legible behind the header

- **WHEN** the operator scrolls the stream upward beneath the header
- **THEN** the header remains readable and the content passing behind it does not compete with it

### Requirement: The composer is the conversation's only lifted surface

The composer SHALL be presented as a surface lifted above the ground plane: its own fill, its own
outline, a soft shadow, and the application's content radius. It SHALL indicate focus by treating
the whole surface, not only its text area.

No other element of the conversation region SHALL be lifted in the same way.

#### Scenario: The composer reads as lifted

- **WHEN** an agent conversation is open
- **THEN** the composer is bounded by its own surface, outline, shadow, and content radius

#### Scenario: Focus is expressed on the surface

- **WHEN** the operator focuses the composer's text area
- **THEN** the composer surface indicates focus

#### Scenario: Nothing else competes with it

- **WHEN** the conversation region is displayed
- **THEN** the header, banners, and continuity line are not drawn as lifted surfaces

### Requirement: Turn-level controls sit with the turn's state

Turn-level controls SHALL be presented in the conversation header, beside the agent's identity and
run state. These are the controls that fold the conversation's turns and stop a running turn.

Lower-frequency conversation actions — switching or starting a conversation, preparing a handoff,
and opening agent details — SHALL remain in an overflow menu.

#### Scenario: Stopping a turn is immediate

- **WHEN** a turn is running
- **THEN** a control to stop it is visible in the header beside the running-state indication
- **AND** reaching it requires no menu

#### Scenario: Folding is immediate

- **WHEN** a conversation has more than one turn
- **THEN** a control to fold its turns is visible in the header

#### Scenario: Infrequent actions stay behind the menu

- **WHEN** the operator looks for conversation switching, handoff, or agent details
- **THEN** they are found in the overflow menu rather than on the surface

### Requirement: The stream is bounded to the reference measure

Conversation entries SHALL be laid out in a centred column bounded to the measure and gutters of the
approved design mock, with the mock's spacing between entries.

#### Scenario: The column matches the reference

- **WHEN** the conversation is displayed at a wide viewport
- **THEN** entries are centred within the mock's bounded measure rather than filling the viewport
- **AND** the spacing between entries matches the mock

### Requirement: Conversation disclosures respond to the pointer

The work disclosure and the folded-turn control SHALL present the hover and pressed treatments
required of every activatable element, and the work disclosure SHALL be drawn as a bounded surface
rather than as an outline alone.

#### Scenario: The work disclosure answers the pointer

- **WHEN** the operator hovers the work disclosure's summary
- **THEN** it takes on a hover treatment
- **AND** its expanded and collapsed states are distinguishable at a glance

#### Scenario: A folded turn answers the pointer

- **WHEN** the operator hovers a folded turn
- **THEN** it takes on a hover treatment indicating it can be reopened

## MODIFIED Requirements

### Requirement: Only high-frequency controls remain visible

The conversation header SHALL expose fold-all and, while the agent is running, stop beside the
current turn's state. The resting composer SHALL expose only submit, the active-agent indicator,
and context usage.

New conversation, conversation selection, durable handoff, and agent details SHALL be reachable
from one overflow menu that is fully operable by keyboard.

An action that is unavailable SHALL be presented disabled with its reason rather than omitted, so
that the menu's contents do not shift between agents.

#### Scenario: The resting control set is minimal

- **WHEN** a conversation is open and the agent is idle
- **THEN** the composer exposes submit, the active-agent indicator, and context usage
- **AND** the header exposes fold-all when the conversation has more than one turn
- **AND** no provider-session selector, handoff button, or scroll toggle is exposed on the surface

#### Scenario: Stop appears with the running state

- **WHEN** the agent is running
- **THEN** a stop control is visible in the header beside the running-state indication
- **AND** no stop control is duplicated in the composer

#### Scenario: The overflow menu is operable by keyboard alone

- **WHEN** the operator opens the overflow menu and moves through it using the keyboard
- **THEN** new conversation, conversation selection, handoff, and agent details are each reachable
  and activatable
- **AND** dismissing the menu returns focus to its trigger

#### Scenario: An unavailable action is disabled with its reason

- **WHEN** an action such as handoff is unavailable for the current agent
- **THEN** the action remains in the overflow menu in a disabled state
- **AND** its reason is available to the operator

#### Scenario: Agent details do not replace the conversation

- **WHEN** the operator activates agent details from the overflow menu
- **THEN** details for the current agent open without unmounting or navigating away from the
  conversation
- **AND** closing the details returns focus to the invoking control
