## ADDED Requirements

### Requirement: What creation collects is decided by whether it changes the first turn

Agent creation SHALL offer a setting when the agent's first turn would be materially different
without it, and SHALL leave every other setting to the agent's configuration destination.

This capability already fixes *what* creation collects — a project-unique name, a launchable
provider, a model the catalog declares, and an optional charter. What it does not state is the rule
by which anything new is placed, so each future setting would be argued individually and creation
would grow by accretion.

The rule governs what is **offered**, not what is **required**. A charter is offered because it
shapes the first turn, and remains optional under the existing no-charter contract; nothing here
tightens that.

A setting with a workable default, which can be changed before it takes effect, MUST NOT be added to
creation. Lengthening creation is friction at the first moment an operator uses the product, and
buys nothing that the configuration destination cannot provide later.

#### Scenario: A setting affecting the first turn is offered

- **WHEN** a setting would materially change how the agent's first turn behaves
- **THEN** creation offers it

#### Scenario: A defaulted setting is left to configuration

- **WHEN** a setting has a workable default and can be changed before it takes effect
- **THEN** creation does not offer it
- **AND** it is available on the agent's configuration destination

#### Scenario: Offering does not imply requiring

- **WHEN** a setting is offered at creation
- **THEN** it may still be optional
- **AND** an existing optional contract for it is preserved
