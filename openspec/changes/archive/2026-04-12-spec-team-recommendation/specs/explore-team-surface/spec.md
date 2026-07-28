## ADDED Requirements

### Requirement: opsx:explore surfaces team recommendation at closure
When an explore session reaches a natural conclusion point — i.e., the conversation has converged enough that a proposal could be written — `opsx:explore` SHALL offer to generate a team recommendation alongside (or instead of) the proposal offer.

#### Scenario: Team recommendation offered at proposal-ready moment
- **WHEN** the explore conversation has crystallized a clear project scope
- **THEN** the skill SHALL offer: "This feels solid enough to propose. Want me to create a proposal — and also recommend a team for this project?"

#### Scenario: Team recommendation offered standalone
- **WHEN** a user asks "what team would I need for this?" during exploration
- **THEN** the skill SHALL generate an inline team recommendation (roles + brief reasoning) based on what has been explored so far, without requiring a formal proposal first

---

### Requirement: opsx:explore team recommendation is spec-unconstrained
The team recommendation produced by `opsx:explore` SHALL be derived from the project scope and decisions made during exploration — not filtered by which agents are currently in the session.

#### Scenario: Recommendation includes roles beyond current session
- **WHEN** the current session has only one agent (e.g., architect)
- **THEN** the recommendation SHALL still suggest all roles the project warrants, regardless of what is currently configured

#### Scenario: Gap is surfaced, not hidden
- **WHEN** the current session is missing roles the project needs
- **THEN** the recommendation SHALL explicitly call out the gap: "You currently have X; this project also needs Y and Z"
