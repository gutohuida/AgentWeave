## ADDED Requirements

### Requirement: Adopting a document that already exists on disk

The Hub SHALL create a `spec_documents` row for a specification file that exists in the project's
`spec/` tree and has no row, deriving the document's identity from the file's own content. The
adopted document MUST thereafter be indistinguishable from one created through the Hub, so that
phase transitions, requirement indexing, coverage, evidence and task materialisation all operate on
it.

#### Scenario: A file with a payload block is adopted

- **WHEN** the operator adopts a path under `spec/` that holds a document carrying a readable
  `aw-spec-payload` block, and no `spec_documents` row exists for that path
- **THEN** a row is created whose `title` and `kind` are the payload's own `title` and `kind`
- **AND** the response reports the document's identifier and the path adopted

#### Scenario: An adopted document supports requirement indexing

- **WHEN** a document declaring requirements is adopted
- **THEN** its requirements are indexed against the new row
- **AND** each requirement is resolvable by its identifier through the existing requirement lookup

#### Scenario: An adopted document accepts a phase transition

- **WHEN** a change-spec document in `exploring` is adopted and the operator then closes exploration
  on it
- **THEN** the transition succeeds against the adopted row

### Requirement: Adoption never modifies the file

Adoption SHALL be read-only on disk. No adoption path may write, truncate, rename or delete a
specification file, whatever the outcome of the adoption.

#### Scenario: The file is byte-identical after a successful adoption

- **WHEN** a document is adopted successfully
- **THEN** the file's bytes are identical to what they were before the call

#### Scenario: The file is byte-identical after a refused adoption

- **WHEN** an adoption is refused for any reason
- **THEN** the file's bytes are identical to what they were before the call

#### Scenario: A corpus is unchanged after corpus-wide adoption

- **WHEN** corpus-wide adoption runs over a directory of documents
- **THEN** every file in that directory is byte-identical to what it was before the call

### Requirement: Phase is derived from the document's own status

Adoption SHALL take the adopted document's phase from the `aw-spec-status` metadata the renderer
writes into the file, because the payload block does not carry it. Where that metadata is absent,
names no known phase, or names a phase the document's kind may not be in, adoption SHALL fall back
to the phase a newly created document of that kind would receive: `current` for a `capability`
document, `exploring` otherwise.

#### Scenario: A capability document adopts at its recorded phase

- **WHEN** a document whose `aw-spec-status` is `current` and whose payload `kind` is `capability` is
  adopted
- **THEN** the row's phase is `current`

#### Scenario: A document with no status metadata falls back by kind

- **WHEN** a document carrying a valid payload but no `aw-spec-status` metadata is adopted
- **THEN** the row's phase is `current` if its payload `kind` is `capability`, and `exploring`
  otherwise
- **AND** the response reports that the phase was defaulted rather than read

#### Scenario: A document with an unrecognised status is defaulted, not accepted

- **WHEN** a document whose `aw-spec-status` names no known phase is adopted
- **THEN** the row's phase is the kind-derived default
- **AND** the response reports the unrecognised value

#### Scenario: A phase the document's kind may not hold is defaulted, not refused

- **WHEN** a document whose `aw-spec-status` names a known phase that its own kind may not be in is
  adopted — a `capability` document in any phase other than `current`, or a document of any other
  kind in `current`
- **THEN** the row's phase is the kind-derived default
- **AND** the response reports the value the file carried
- **AND** the document is adopted rather than refused

### Requirement: A file with no readable payload is refused

Adoption SHALL refuse a file from which no payload block can be read, rather than inventing an
identity for it. The Hub has no title or kind for such a file, and a guessed name would enter a
file that outlives the machine that guessed it.

#### Scenario: A document with no payload block is refused

- **WHEN** the operator adopts a path holding an HTML file with no `aw-spec-payload` block
- **THEN** the adoption is refused with a reason naming the missing payload
- **AND** no `spec_documents` row is created for that path

#### Scenario: A document with an unparseable payload block is refused

- **WHEN** the payload block is present but is not valid JSON, or is not a JSON object
- **THEN** the adoption is refused with a reason naming the unreadable payload
- **AND** no `spec_documents` row is created for that path

### Requirement: An already-tracked path is refused with its disagreements reported

Where the adopted path already has a `spec_documents` row, adoption SHALL refuse and SHALL report
every field on which the file and the row disagree. Adoption MUST NOT update an existing row from a
file: resolving that disagreement is a separate operator decision.

#### Scenario: An already-adopted path is refused

- **WHEN** the operator adopts a path that already has a row
- **THEN** the adoption is refused
- **AND** the existing row is unchanged

#### Scenario: The disagreement between file and row is reported

- **WHEN** an adoption is refused because a row exists, and the file's title, kind or phase differ
  from the row's
- **THEN** the response names each differing field with both the file's value and the row's value

#### Scenario: Agreement is reported as no disagreement

- **WHEN** an adoption is refused because a row exists, and the file and row agree on title, kind
  and phase
- **THEN** the response reports no differing fields

### Requirement: A corpus is adoptable in one operation

The Hub SHALL offer adoption of every adoptable document in the project's `spec/` tree in a single
operation, so that a project whose database was created after its files — a clone, a migration, or a
restored machine — is recoverable without one call per document.

#### Scenario: Every untracked document with a payload is adopted

- **WHEN** corpus-wide adoption runs over a `spec/` tree containing untracked documents that carry
  payload blocks
- **THEN** a row is created for each of them
- **AND** the response lists each adopted path

#### Scenario: Unadoptable documents are reported, not fatal

- **WHEN** corpus-wide adoption encounters a document with no readable payload, or a path that
  already has a row
- **THEN** that document is skipped with a stated reason
- **AND** the remaining adoptable documents are still adopted

#### Scenario: Corpus-wide adoption is repeatable

- **WHEN** corpus-wide adoption is run twice in succession with no intervening change
- **THEN** the second run adopts nothing, reports every path as already tracked, and creates no
  duplicate rows

### Requirement: Adoption only reaches documents inside the project's spec tree

Adoption SHALL resolve every path through the project workspace and SHALL refuse any path that
escapes the project's `spec/` tree, on the same terms as existing document discovery.

#### Scenario: A path outside the spec tree is refused

- **WHEN** the operator adopts a path that resolves outside the project's `spec/` directory
- **THEN** the adoption is refused
- **AND** no row is created

#### Scenario: A path escaping the workspace is refused

- **WHEN** the adopted path traverses outside the project workspace root
- **THEN** the adoption is refused before the file is read

### Requirement: An adopted document becomes indexable

Once adopted, a document SHALL be filed into `spec/index.json` by the existing reindex operation,
carrying its real title and kind rather than being reported as unindexable.

#### Scenario: A previously unfiled document is filed after adoption

- **WHEN** a document that reindex previously reported as `unindexable_document` is adopted, and
  reindex is then run
- **THEN** the document appears in `spec/index.json` with the title and kind from its payload
- **AND** it is no longer reported as unindexable

#### Scenario: An adopted document reports its filed state

- **WHEN** the specification tree is listed after an adopted document has been filed
- **THEN** that document's entry carries a non-null document identifier and its phase
