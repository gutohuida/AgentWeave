# spec-document-authority

## ADDED Requirements

### Requirement: The rendered document shares the Hub's theme, not a colour scheme of its own

The document the Hub renders SHALL take its neutral colours (background, foreground, muted text,
borders, and the two lifted-surface tones used for chips and code) from the same set of inherited CSS
custom properties the embedding shell already sets when it stamps the Hub's active theme onto the
document. The document MUST NOT define a second, independently-named set of neutral tokens that the
shell's theming has no way to reach.

The document's own semantic hues — used to carry meaning within the specification itself, such as
distinguishing a mandatory requirement from an optional one — remain the document's own and are not
overridden by the embedding shell.

This MUST continue to be achieved without any external resource reference (no stylesheet link, no
network fetch) — inherited custom properties and inline styles only.

#### Scenario: The document's background matches the Hub's active theme

- **WHEN** the Hub is in light mode and a specification document is opened
- **THEN** the document's rendered background is the Hub's light neutral background, not a colour the
  document chose independently
- **AND** switching the Hub to dark mode changes the document's rendered background to match

#### Scenario: The document's own semantic colours are not recoloured by the shell

- **WHEN** the document renders a mandatory requirement with distinct colour from an optional one
- **THEN** that distinction is visible identically in both the Hub's light and dark modes

### Requirement: The rendered document visually distinguishes requirement strength and document phase

A rendered document SHALL give a requirement's modal obligation (mandatory, recommended, optional) a
visually distinct treatment, not uniform styling, so a reader can distinguish requirement strength by
scanning rather than by reading every word.

#### Scenario: A mandatory requirement is visually distinct from an optional one

- **WHEN** a document contains requirements with different modal obligations
- **THEN** each is rendered with a treatment distinct to its obligation
- **AND** the treatment is consistent for every requirement sharing that obligation

### Requirement: Coverage distinguishes rejected evidence from work that has not been judged

Coverage reporting SHALL report a requirement whose only evidence against its current wording was
rejected as a distinct state from a requirement with no evidence, and distinct from a requirement
whose linked work is still under way. This state SHALL rank below `verified` and above the states
that describe the absence of an attempt, so that a subsequent, accepted submission against the same
wording is reported as `verified`, not shadowed by an earlier rejection.

#### Scenario: A requirement with only rejected evidence is reported distinctly

- **WHEN** a requirement's only evidence against its current wording was rejected, and no other
  evidence is awaiting review or accepted
- **THEN** its coverage state is reported as rejected, not as work in progress or as unserved

#### Scenario: A later accepted submission supersedes an earlier rejection

- **WHEN** a requirement whose only prior evidence was rejected later receives evidence against the
  same wording that is accepted
- **THEN** its coverage state is reported as verified

### Requirement: A declared task's requirement span is capped, and the Hub enforces it

The Hub SHALL refuse a document's transition to `proposed` when any task it declares names more
requirements than a stated ceiling. The ceiling MUST be named in the refusal.

#### Scenario: A task naming too many requirements blocks the transition

- **WHEN** a document contains a declared task naming more requirements than the ceiling permits
- **THEN** the transition to `proposed` is refused
- **AND** the offending task and the ceiling are named

#### Scenario: A task at the ceiling is not refused

- **WHEN** a document contains a declared task naming exactly the ceiling's number of requirements
- **THEN** that task does not, on its own, block the transition
