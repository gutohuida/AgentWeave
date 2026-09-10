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

### Requirement: One dismissal keystroke dismisses one thing

A dismissal keystroke SHALL be answered by exactly one control — the innermost one that owns it — and a surface that dismisses on that keystroke SHALL NOT do so when a control nearer the operator has already handled it.

A control that handles a dismissal keystroke SHALL mark the keystroke as handled, so that the
surfaces containing it can tell. A surface cannot know what is nested inside it, and a nested
control cannot know what contains it; the keystroke itself is the only thing both can see.

Nesting is the ordinary case, not an exotic one. A panel holds a menu; a panel holds an input that
cancels; a panel holds a browser that closes. In every one of those the operator pressing Escape is
dismissing the thing they are looking at, and the surface behind it is the context they expect to
come back to. A surface that leaves with the control being dismissed takes the operator's place with
it, and there is nothing on screen afterwards to say what happened.

The cost is worse than an extra click, and it is why this is stated once here rather than repaired
per screen. A nested control that owns the key **cannot be observed to work at all** while the
surface around it also acts: the code runs, does exactly what it was written to do, and is unmounted
by the same keystroke. That failure is invisible to anything except operating the product.

This requirement is about who answers, not about where a listener is bound or which mechanism marks
the keystroke. A surface may listen wherever it needs to.

#### Scenario: Dismissing a menu inside a panel leaves the panel open

- **WHEN** the operator opens a menu belonging to a control inside a panel that itself dismisses on
  Escape, and presses Escape
- **THEN** the menu closes
- **AND** the panel is still open

#### Scenario: Cancelling an input inside a panel leaves the panel open

- **WHEN** a panel that dismisses on Escape is showing a control that cancels itself on Escape, and
  the operator presses Escape while that control has focus
- **THEN** that control is cancelled
- **AND** the panel is still open, showing what it showed before the control appeared

#### Scenario: A panel opened over another panel dismisses only itself

- **WHEN** a secondary panel is open over the panel that opened it, and both dismiss on Escape, and
  the operator presses Escape
- **THEN** the secondary panel closes
- **AND** the panel that opened it is still open

#### Scenario: With nothing nearer, the panel still dismisses

- **WHEN** the operator presses Escape while a panel is open and nothing inside it has claimed the
  keystroke
- **THEN** the panel dismisses, exactly as it did before

### Requirement: An action that asks for something leaves the keyboard in what it asked with

A menu action whose effect is to present a control expecting the operator's input SHALL leave keyboard focus in that control once the menu has closed, and SHALL NOT return focus to the control that opened the menu.

A menu returning focus to its trigger is right for an action that leaves nothing on screen: it is
where the operator was, and it is where they can act next. It is wrong for an action whose whole
purpose is to ask a question, because the field holding the answer is then the one place the
keyboard is not.

**The failure is silent, which is what makes it worth a requirement rather than a fix.** The
operator types and nothing appears; the control they are actually typing into is a button, so their
keystrokes activate it; and the action they were completing sits waiting on input the product will
not accept from them. Nothing is written wrongly and no error is shown, so there is no moment at
which the product says anything is wrong.

This applies to the action, not to the menu. A menu that offers both kinds of action SHALL
distinguish them: an action that presents nothing keeps returning focus to the trigger, and only the
action that asks stands the restoration down.

#### Scenario: Choosing an action that asks a question puts the keyboard in the answer

- **WHEN** the operator chooses a menu action that presents a control expecting their input
- **THEN** keyboard focus is in that control once the menu has closed
- **AND** what they type next appears in it

#### Scenario: An action that asks nothing returns the keyboard where it was

- **WHEN** the operator chooses a menu action that presents no control expecting input
- **THEN** keyboard focus returns to the control that opened the menu

#### Scenario: Typing an answer does not operate the menu that asked for it

- **WHEN** the operator types an answer containing spaces into the control a menu action presented
- **THEN** the menu does not re-open
- **AND** the surface behind that control does not stop answering the pointer because a menu re-opened
  over it
