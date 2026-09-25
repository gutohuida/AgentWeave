## ADDED Requirements

### Requirement: An approved document offers the operator its flow, or a way to start one

Where the app shows an approved change document, it SHALL show the flow that declares that document
when an unarchived one exists, and SHALL let the operator open it. When none exists, it SHALL offer to
start one, asking for the flow's name, default agent, message, stop condition and cadence, with the
defaults stated, and SHALL create it as a flow declaring that document. The first firing SHALL happen
at the next scheduled time, and the offer SHALL say so.

The offer SHALL NOT be shown for a document that is not approved, nor for a capability document.

#### Scenario: A document with a flow links to it

- **GIVEN** an approved change document declared by an unarchived flow
- **WHEN** the operator opens the document
- **THEN** the flow is named on the document, and opening it shows the flow's own view

#### Scenario: A document without a flow offers to start one

- **GIVEN** an approved change document that no unarchived flow declares
- **WHEN** the operator starts a flow from it, choosing an agent and keeping the other defaults
- **THEN** a flow is created that declares the document, stops when its queue empties, and fires every 5 minutes
- **AND** it has not fired yet; its first firing is at the next scheduled time

#### Scenario: A document already claimed is refused with the reason

- **GIVEN** a document another unarchived loop already declares
- **WHEN** a flow is started from it
- **THEN** the start is refused with a reason naming the loop that holds it
