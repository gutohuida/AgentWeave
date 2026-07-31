## ADDED Requirements

### Requirement: Typography is self-hosted and variable

The interface SHALL render its intended typefaces without depending on a third-party network
request. Font assets MUST be served from the Hub's own origin, and the UI typeface MUST be a
variable font. Numeric readouts that update live MUST use tabular figures.

#### Scenario: Intended fonts render without external network access

- **WHEN** the interface loads on a machine with no access to third-party font hosts
- **THEN** the intended UI and monospace typefaces render
- **AND** no visible fallback substitution or text reflow occurs after first paint

#### Scenario: Live numbers do not jitter

- **WHEN** a numeric value updates in place
- **THEN** its digits do not change horizontal position due to glyph width

### Requirement: Icons render from a single system without blocking

The interface SHALL use exactly one icon system, and icon rendering MUST NOT depend on a
render-blocking third-party stylesheet or font download.

#### Scenario: Icons are present at first paint

- **WHEN** the interface loads
- **THEN** icons render without an interval during which their space is blank

#### Scenario: One icon system is in use

- **WHEN** the interface source is inspected
- **THEN** exactly one icon system is referenced

### Requirement: Interactive surfaces have consistent motion and state feedback

Interactive elements SHALL provide hover, pressed, and keyboard-focus treatments drawn from a
shared, named motion scale. Values that change continuously SHALL animate to their new state
rather than jumping. All motion MUST be suppressed when the operator has requested reduced motion.

#### Scenario: A control acknowledges interaction

- **WHEN** an operator hovers, presses, or focuses an interactive control via keyboard
- **THEN** the control renders a distinct, animated treatment for that state

#### Scenario: A continuous value glides

- **WHEN** a progress or usage value changes
- **THEN** it transitions to the new value over a duration from the shared motion scale

#### Scenario: Reduced-motion preference is honoured

- **WHEN** the operating system requests reduced motion
- **THEN** transitions are suppressed and final states render immediately

### Requirement: Live state is driven by the event stream, not by polling

Client views SHALL derive live state from the server-sent event stream. The interface MUST NOT
poll REST endpoints on a fixed interval to discover state that the event stream already reports.

#### Scenario: Views update from events

- **WHEN** a task, message, agent status, or run output changes on the server
- **THEN** connected views reflect the change on receipt of the corresponding event

#### Scenario: No interval polling remains for streamed entities

- **WHEN** the client data layer is inspected
- **THEN** no fixed-interval refetch is configured for an entity covered by the event stream

#### Scenario: Stream loss is visible and recoverable

- **WHEN** the event stream disconnects
- **THEN** the interface indicates that live updates are interrupted
- **AND** it reconnects and reconciles state without an operator action

### Requirement: Controls change appearance without changing layout

An interactive control SHALL occupy identical space in every visual state. Space for the control's
outline and decoration SHALL be reserved at rest, whether or not that decoration is visible, so that
gaining or losing emphasis never displaces the control or its neighbours.

A control's internal spacing SHALL be visually equal across states, accounting for any space
reserved by its outline.

#### Scenario: Emphasis does not displace anything

- **WHEN** an operator hovers, presses, or focuses a control that has no visible outline at rest
- **THEN** the control gains its outline and emphasis
- **AND** neither the control nor any neighbouring element changes size or position

#### Scenario: Spacing reads the same with and without a visible outline

- **WHEN** controls with and without visible outlines are placed together
- **THEN** their label insets appear equal

### Requirement: Controls express press physically

A raised control SHALL read as lit from above at rest and as depressed while pressed. Its resting
elevation SHALL be removed while pressed and while disabled.

#### Scenario: Pressing inverts the control's shading

- **WHEN** an operator presses a raised control
- **THEN** its resting top-edge highlight is replaced by a corresponding inset shadow
- **AND** its resting elevation is removed for the duration of the press

#### Scenario: Elevation is tinted, not neutral

- **WHEN** a control carries both a colour and an elevation
- **THEN** its elevation is tinted by that colour rather than rendered in neutral grey

#### Scenario: Disabled controls are unelevated and unreactive

- **WHEN** a control is disabled
- **THEN** it carries no elevation and does not respond to pointer interaction

### Requirement: Corner radius distinguishes chrome from content

The interface SHALL define a single radius scale derived from one base value, and SHALL apply it so
that interface chrome reads as crisper than content surfaces. Content surfaces presenting a
substantial, self-contained result SHALL be more strongly rounded than the controls around them.

Decoration nested inside a rounded element SHALL use a radius reduced by the thickness separating
them, so that concentric edges remain parallel.

#### Scenario: Chrome and content are distinguishable by radius alone

- **WHEN** a content card is displayed among interface controls
- **THEN** the card is visibly more rounded than the controls

#### Scenario: Nested corners stay parallel

- **WHEN** a rounded decoration is inset within a rounded element
- **THEN** the inner radius is reduced by the separating thickness
- **AND** no gap of differing curvature appears between them

### Requirement: Iconography is subordinate to its label

An icon accompanying a text label SHALL be rendered less prominently than that label unless it has
been deliberately emphasised. Icons SHALL be optically aligned with their labels rather than
aligned only by their bounding boxes.

#### Scenario: An icon does not compete with its label

- **WHEN** an icon is placed beside a text label without explicit emphasis
- **THEN** it renders at reduced prominence relative to the label

#### Scenario: Deliberate emphasis is preserved

- **WHEN** an icon is explicitly given a colour or prominence
- **THEN** the default subordinate treatment does not override it

### Requirement: Pointer targets are adequate on coarse pointers

On coarse pointer devices every interactive control SHALL present a touch target meeting the
platform minimum, without altering its visual size on fine pointer devices.

#### Scenario: Small controls remain reachable by touch

- **WHEN** a visually small control is presented on a coarse pointer device
- **THEN** its interactive area meets the platform minimum target size

#### Scenario: Touch accommodation does not inflate the desktop interface

- **WHEN** the same control is presented on a fine pointer device
- **THEN** its visual size is unchanged by the coarse-pointer accommodation
