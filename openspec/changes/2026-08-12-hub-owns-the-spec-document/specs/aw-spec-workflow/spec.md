# aw-spec-workflow

Every requirement of this capability is removed. It described an authoring flow delivered through the
`aw-spec-*` skills, and that delivery channel fails twice over: **nothing installs the skills** — no
code writes `.claude/skills/` — and even when something did, `.claude/skills/` is read by Claude
Code, so a Codex agent could never invoke them under any circumstances, while the seeded charter
instructed every agent to use them.

The procedure moves into the phase machine, the format contract into schema validation, and the
judgment into the charter, which is where the parts of a skill file that are genuinely different
kinds of knowledge each belong. The per-section disposition is recorded in §6 of
`openspec/explorations/2026-08-12-spec-hub-integration.md`; the charter harvest shipped in commit
`2909137`.

## REMOVED Requirements

### Requirement: Idea exploration focuses on discovery before execution planning

**Reason**: Split by kind. The *obligation* — a document cannot reach `proposed` while exploration is
unfinished — becomes a phase entry condition in `spec-document-authority`, because an obligation the
model is asked to honour is a suggestion. The *skill* at interviewing moves to
`hub/hub/data/charters/spec.md`, which reaches both runners and which the operator can edit.

### Requirement: Technical exploration plans how the work will be built

**Reason**: Technical exploration is dropped by operator decision (exploration §1.12). Its useful
half — grounding requirements in the codebase rather than guessing — is a charter behaviour, not a
separate phase with its own document.

### Requirement: Technical exploration includes AgentWeave execution strategy

**Reason**: Dropped with technical exploration, and doubly obsolete: it described loading session,
team, role and quality configuration, all of which belong to the deleted CLI role subsystem. Agent
assignment is now a roster concern.

### Requirement: Proposal generation uses prior exploration when available

**Reason**: Superseded by the document itself. Exploration no longer produces separate discovery
notes that a later step must remember to read — the document exists from the first moment of
`exploring` and is the same document that is proposed, so there is nothing to carry across.

### Requirement: Documentation describes the expanded AW-Spec flow

**Reason**: Documents a flow that is removed. The flow that replaces it is stated in
`spec-document-authority` and rendered by the Hub.

### Requirement: AW-Spec authoring maintains the project manifest

**Reason**: The Hub now writes the document and the index in one operation. Requiring the *agent* to
maintain the index made the index only as reliable as the agent's compliance with a written
instruction.

### Requirement: AW-Spec provides deterministic manifest repair

**Reason**: Repair addressed drift between an external writer and the index. The Hub is now the only
writer, so that drift is not produced. The deterministic checks this requirement mandated — unique
safe paths, a home that resolves, acyclic parents, compatible kind and status — become Hub
validation.

### Requirement: The spec role routes instead of duplicating procedures

**Reason**: Its subject is routing an agent to skills, and there are no skills to route to. This
requirement was rewritten in the previous session to forbid routing to mechanisms a project lacks;
the general form of that fix is that the procedure lives in the Hub and needs no routing at all.

### Requirement: AW-Spec metadata guidance is kind-aware

**Reason**: Guidance for an agent hand-writing document metadata. Under JSON in, HTML out the agent
does not write metadata — the Hub renders it, and the payload schema states which fields a document
kind requires.

### Requirement: Setup and documentation recognize manifest-based spec trees

**Reason**: Described setup writing skill files and documentation describing them. Setup installs no
skills, and the specification surface is reached through the Hub rather than through a documented
directory convention.
