# hub-interaction-feedback Specification

## Purpose
How the Hub answers a pointer and a keyboard: what every activatable element owes the operator in
resting, hover, pressed, and focused states, and how emphasis is allowed to change.

Separated from `hub-workspace-shell` by `2026-08-04-hub-contextual-navigation` because it is not
about layout. The shell decides what is on screen and where; this decides whether what is on
screen answers when touched. Stating it once keeps every surface from inventing its own answer.

## Requirements

### Requirement: Every activatable element responds to the pointer and to focus

Every activatable element SHALL present a visible resting state, a hover state, a pressed state, and
a visible focus indicator when focused by keyboard. This applies to controls, navigation rows, list
rows, tabs, cards, and disclosures.

An element that changes the application's state when clicked MUST NOT be visually inert under the
pointer.

#### Scenario: A navigation row answers the pointer

- **WHEN** the operator hovers a project, an agent, a project view, or a configuration section
- **THEN** that row takes on a hover treatment distinguishing it from the rows around it

#### Scenario: Pressing is distinguishable from hovering

- **WHEN** the operator presses an activatable element
- **THEN** its appearance changes again, distinctly from its hover appearance
- **AND** it returns to the hover appearance when released with the pointer still over it

#### Scenario: Keyboard focus is visible

- **WHEN** the operator moves focus to an activatable element with the keyboard
- **THEN** a focus indicator is drawn that is visible against the surface behind it

### Requirement: Where the operator is differs from where the pointer is

A selected or current element SHALL be distinguishable from a merely hovered element. The two states
MUST NOT resolve to the same appearance.

The current element SHALL remain identifiable while the pointer is elsewhere.

#### Scenario: The selected row stays legible under an unrelated hover

- **WHEN** one configuration section is selected and the operator hovers a different one
- **THEN** both are distinguishable from the unselected rows
- **AND** they are distinguishable from each other

#### Scenario: Selection survives the pointer leaving

- **WHEN** the pointer leaves the navigation region entirely
- **THEN** the current destination remains marked

### Requirement: Gaining emphasis never moves anything

An element changing between its resting, hover, pressed, and selected states MUST NOT change its own
size or position, and MUST NOT displace any neighbouring element.

#### Scenario: A row does not shift when hovered

- **WHEN** the operator moves the pointer across a list of rows
- **THEN** no row, and no text within a row, moves by any amount

### Requirement: A row may reveal its secondary actions on hover

A row that reveals secondary actions only while hovered or focused SHALL reserve their layout space
at rest, so revealing them displaces nothing. Those actions MUST remain reachable by keyboard.

#### Scenario: Actions appear without disturbing the row

- **WHEN** the operator hovers a row carrying secondary actions
- **THEN** those actions become visible
- **AND** the row's other content does not move

#### Scenario: Hidden actions are not lost to the keyboard

- **WHEN** the operator tabs into a row whose secondary actions are not currently drawn
- **THEN** those actions can be reached and activated

### Requirement: State changes are eased, and easing is never the only signal

Transitions between interaction states SHALL be eased using the application's shared duration and
easing tokens rather than switching instantly.

When the operator has asked for reduced motion, transitions SHALL be suppressed while every state
remains distinguishable by its appearance alone.

#### Scenario: A state change is eased

- **WHEN** an element enters or leaves its hover state
- **THEN** the change is eased over the application's fast duration

#### Scenario: Reduced motion loses the animation, not the information

- **WHEN** the operator has requested reduced motion
- **THEN** interaction states change without animating
- **AND** hover, pressed, and selected states remain distinguishable from one another and from rest

### Requirement: Interaction states resolve from shared semantic tokens

Resting, hover, pressed, and selected treatments SHALL resolve from semantic tokens defined for both
the light and dark themes. A surface MUST NOT hard-code a colour for an interaction state, and the
same kind of element SHALL use the same tokens wherever it appears.

#### Scenario: The same row reads the same everywhere

- **WHEN** a navigation row, a configuration section row, and a list row are compared in either theme
- **THEN** their hover, pressed, and selected treatments are drawn from the same tokens

#### Scenario: Every state token is defined in both themes

- **WHEN** the production stylesheet is checked
- **THEN** every token referenced by an interaction state has a value in both light and dark themes
