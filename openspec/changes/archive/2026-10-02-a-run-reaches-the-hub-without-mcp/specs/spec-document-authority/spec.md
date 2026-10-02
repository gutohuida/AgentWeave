## MODIFIED Requirements

### Requirement: Authoring assistance is scoped away from performing discovered implementation work

WHEN an agent's turn is triggered with a specification document open, THEN the spawned run SHALL NOT be granted the ability to write or edit files in the project workspace for that turn, regardless of the document's phase or rigor, and regardless of the run's configured permission posture (including a posture that would otherwise skip permission prompts entirely), except that a run told to reach the capability plane through the Hub's call command SHALL keep the ability to write that command's arguments files inside its own calls directory.

The turn's context SHALL state that discovered implementation work is to be proposed — for example,
by creating a task — rather than performed directly. A turn triggered with no specification document
open is unaffected.

**The one write a specification turn keeps (2026-09-28).** A specification turn exists to write and
submit a document, and submitting it is a call to the capability plane. A run told to reach the plane
through the call command passes every call's arguments as a JSON file in its calls directory, so a
specification turn with no way to write that file cannot submit what it wrote. The arguments file is
data in a directory the Hub owns and the repository ignores. Writing it implements nothing, which is
what this requirement exists to prevent.

Where the system itself answers the run's file-write requests, it SHALL allow that one write and
refuse every other write for the turn, whatever the posture. Where nothing answers them and the
harness cannot confine a write tool to one directory, the harness's file-creation tool remains
available for that turn and its other writes are decided by the run's posture. That is a weakening,
and it is stated rather than hidden: the alternative is a specification turn that cannot submit its
document. A run told the tool-protocol surface keeps no write tool at all, as before.

#### Scenario: A file-editing attempt during a spec-authoring turn is unavailable, not merely discouraged

- **WHEN** an agent is triggered with a specification document open and, in the course of the turn,
  identifies a code change needed to fix a discovered problem
- **THEN** the run has no file-write tool available to make that change directly, or, if it was told
  the call command and the system answers its write requests, that write is refused
- **AND** the turn's context states that the discovery should be recorded as a proposed task instead

#### Scenario: The restriction holds even under a permission posture that skips prompts

- **WHEN** an agent told the tool-protocol surface is triggered with a specification document open
  and a permission posture that would otherwise let every tool call proceed without a prompt
- **THEN** the run still has no file-write tool available for that turn

#### Scenario: A specification turn told the call command can submit its document

- **WHEN** an agent told the call command is triggered with a specification document open, and
  writes a JSON arguments file inside its own calls directory to submit the document
- **THEN** that write is allowed
- **AND** where the system answers the run's write requests, a write anywhere else in the turn is
  refused

#### Scenario: A turn with no document open is unrestricted

- **WHEN** an agent is triggered with no specification document open
- **THEN** its tool surface is exactly what it would be without this requirement in effect
