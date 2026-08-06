## ADDED Requirements

### Requirement: Composer controls are unbounded

A control in the composer's control row SHALL be rendered as its label and icon alone. It MUST NOT
draw a border, an outline, or a filled box around itself at rest.

Hover and press SHALL be expressed by changing the control's own text and icon prominence, and MAY
add a background fill. They MUST NOT introduce a border or outline that was not present at rest.

Gaining or losing emphasis MUST NOT change a control's size or displace any neighbouring control.

Keyboard focus is exempt: a visible focus indicator SHALL remain, because it serves a different
purpose from hover styling and is required for keyboard operation.

#### Scenario: A control at rest has no box

- **WHEN** the composer's control row is displayed and no control is hovered, pressed, or focused
- **THEN** no control renders a border, outline, or filled box

#### Scenario: Hover does not draw a box

- **WHEN** the operator hovers a composer control
- **THEN** its text and icon prominence changes
- **AND** no border or outline appears that was not present at rest

#### Scenario: Emphasis does not move anything

- **WHEN** a composer control gains or loses emphasis
- **THEN** its size is unchanged
- **AND** no neighbouring control is displaced

#### Scenario: Keyboard focus stays visible

- **WHEN** a composer control receives keyboard focus
- **THEN** a focus indicator is visible

### Requirement: Selection controls are pill-shaped and sized to their content

A composer control that opens a list of choices SHALL be pill-shaped: its corner radius SHALL make
its ends fully rounded at its own height, for any label length.

Both the control and the list it opens SHALL take their width from their content. Neither SHALL
declare a fixed or minimum width that leaves whitespace beyond what the longest item needs.

A list MAY declare a maximum width. Content exceeding it SHALL be truncated with the full value
remaining available, and MUST NOT widen the list further.

#### Scenario: A short label yields a short control

- **WHEN** a selection control's current value is a short label
- **THEN** the control's width fits that label and its padding
- **AND** does not extend to a fixed minimum

#### Scenario: The list fits its longest item

- **WHEN** a selection control's list is opened
- **THEN** the list's width is that of its longest item
- **AND** no fixed minimum width is applied

#### Scenario: Ends stay fully rounded

- **WHEN** a selection control is displayed with any label
- **THEN** its ends are fully rounded at its height

#### Scenario: An over-long item truncates rather than widening

- **WHEN** a list item exceeds the list's maximum width
- **THEN** the item is truncated
- **AND** its full value remains available
- **AND** the list does not widen

### Requirement: The composer surface does not react to focus

The composer's surface MUST NOT change its border, outline, shadow, or add a ring when focus enters
it or when the operator is typing.

The caret and the placeholder are the indication of where typing goes. A control *within* the
composer is unaffected by this requirement and keeps its own focus indicator.

#### Scenario: Clicking into the composer changes nothing around it

- **WHEN** the operator focuses the composer's text area
- **THEN** the composer surface's border, outline, shadow, and ring are unchanged

#### Scenario: Typing changes nothing around it

- **WHEN** the operator is typing in the composer
- **THEN** the composer surface's appearance is unchanged from its resting state

#### Scenario: Controls keep their own focus indicator

- **WHEN** a control inside the composer receives keyboard focus
- **THEN** that control shows a focus indicator

### Requirement: Model selection shows which provider a model belongs to

Where the composer offers a choice of model, each choice SHALL be accompanied by a visual mark
identifying the provider it belongs to, and the control's current value SHALL show that provider's
mark alongside the model's label.

A provider mark SHALL be resolved from the provider identity the model catalog declares. A provider
for which no mark is available SHALL fall back to a readable text label and MUST NOT be given
another provider's mark.

Provider marks MUST NOT introduce a second icon system, a webfont, or a network request to render.
A provider name MUST NOT be hardcoded in the composer's control components.

#### Scenario: The current model shows its provider

- **WHEN** the composer's model control displays its current value
- **THEN** the provider's mark is shown alongside the model's label

#### Scenario: An unknown provider degrades to a label

- **WHEN** a model's provider has no available mark
- **THEN** a readable text label identifies the provider
- **AND** no other provider's mark is shown

#### Scenario: Marks need no second icon system

- **WHEN** provider marks are rendered
- **THEN** they resolve without a second icon system, a webfont, or a network request

#### Scenario: The composer stays provider-agnostic

- **WHEN** the composer's control components are inspected
- **THEN** no provider name is hardcoded in them
