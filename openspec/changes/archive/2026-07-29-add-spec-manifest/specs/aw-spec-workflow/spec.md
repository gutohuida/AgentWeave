## ADDED Requirements

### Requirement: AW-Spec authoring maintains the project manifest

AW-Spec skills that create, rename, move, archive, or materially update an HTML spec SHALL update
`spec/index.json` in the same workflow. They MUST refresh intrinsic fields from HTML and MUST
preserve or deliberately update the semantic `home`, `parent`, and `order` fields.

The skills MUST NOT rely on the manifest to discover existing specs and MUST NOT approve a change
spec while manifest errors affecting that change remain unresolved.

#### Scenario: Proposal creates a change spec

- **WHEN** `aw-spec-propose` creates `spec/changes/<name>/spec.html`
- **THEN** it adds or refreshes the corresponding manifest entry
- **AND** assigns the semantic parent requested by the relevant roadmap or user context

#### Scenario: Archive moves a change spec

- **WHEN** `aw-spec-archive` moves a completed change into the archive tree
- **THEN** it updates the manifest path and relationships in the same operation
- **AND** it does not create or merge into an obsolete `spec/specs/` library

### Requirement: AW-Spec provides deterministic manifest repair

The framework SHALL package an `aw-spec-reindex` skill for Claude and Codex surfaces. The skill
SHALL scan safe HTML independently of the manifest, validate HTML intrinsic metadata, refresh
existing intrinsic fields, preserve valid relationships, add unfiled documents, and investigate
missing documents before removing entries.

The skill MUST treat HTML as authoritative for title, kind, and status; MUST treat the manifest as
authoritative for valid home, parent, and order relationships; and MUST report any semantic choice
it cannot safely infer.

#### Scenario: Reindex repairs mechanical drift

- **WHEN** a repair request identifies unfiled documents and intrinsic metadata conflicts
- **THEN** `aw-spec-reindex` deterministically adds the files and refreshes intrinsic fields from
  their HTML
- **AND** preserves all still-valid semantic relationships

#### Scenario: Reindex encounters ambiguous deletion

- **WHEN** a manifest entry points to a missing document and repository evidence does not establish
  whether deletion was intentional
- **THEN** the skill does not silently discard the entry
- **AND** asks the user or records the unresolved drift

### Requirement: The spec role routes instead of duplicating procedures

The packaged spec role SHALL contain identity, ownership boundaries, approval and escalation rules,
and explicit guidance about which AW-Spec skill to invoke for each workflow stage. Detailed HTML
authoring and manifest-repair procedures SHALL live in their respective skills and support files
rather than being restated in the always-loaded role.

The CLI role template and Hub packaged role MUST remain behaviorally equivalent.

#### Scenario: Agent starts with the spec role

- **WHEN** an agent receives the spec role guide
- **THEN** it can select the appropriate explore, technical-explore, propose, apply, archive, or
  reindex skill
- **AND** it is not given a second inline copy of the HTML convention procedure

#### Scenario: Role distributions are compared

- **WHEN** tests load the CLI and Hub copies of the spec role
- **THEN** their normative routing, boundaries, and escalation behavior match

### Requirement: AW-Spec metadata guidance is kind-aware

The shared HTML conventions SHALL define `living` for baseline, system-map, and roadmap documents
and `draft` or `approved` for change-spec documents. Approval metadata and the implementation gate
MUST apply to change specs and MUST NOT be described as required approval state for non-change
documents.

#### Scenario: Agent authors a roadmap

- **WHEN** an AW-Spec skill creates or updates a roadmap
- **THEN** it emits kind `roadmap` with status `living`
- **AND** does not add a change-spec approval gate

#### Scenario: Agent authors a change spec

- **WHEN** `aw-spec-propose` creates a change spec
- **THEN** it emits kind `change-spec` with status `draft`
- **AND** `aw-spec-apply` continues to require explicit status `approved`

### Requirement: Setup and documentation recognize manifest-based spec trees

Setup guidance and user documentation SHALL detect project specs through safe recursive discovery
and the manifest rather than assuming `spec/spec.html`. They SHALL explain the HTML-only Hub view,
the manifest's hybrid maintenance model, drift repair, explicit pruning, and archive behavior.

#### Scenario: Existing project uses a named baseline

- **WHEN** setup inspects a project whose baseline is `spec/agentweave-spec.html`
- **THEN** it recognizes that a project spec already exists
- **AND** does not instruct the user to create a competing `spec/spec.html`

#### Scenario: User reads archive guidance

- **WHEN** the user reads the AW-Spec archive workflow
- **THEN** it describes moving the completed HTML change and updating the manifest
- **AND** does not claim that HTML workflow artifacts are merged into `spec/specs/`
