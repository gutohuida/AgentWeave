## ADDED Requirements

### Requirement: Zero-trust review sequence in code_reviewer role
The `code_reviewer` role template SHALL mandate a specific review sequence that forms an independent assessment before consulting the decision doc:
1. Read code first — form independent view of correctness, fit, and coverage
2. Run dependency check — verify every import exists on the real package registry
3. Run AI security checklist — secrets, overly broad permissions, prompt injection vectors
4. Check tests independently — determine what tests should cover, verify they would catch deliberate mutations
5. Read the decision doc — cross-check code against documented intent
6. Check prompt audit trail — does the code match what was asked for (`requirement` field)?

#### Scenario: Reviewer reads code before decision doc
- **WHEN** a code_reviewer agent begins a review task
- **THEN** the agent SHALL form an independent assessment of the code before reading the decision doc

#### Scenario: Doc/code mismatch triggers escalation
- **WHEN** the decision doc claims behavior X but the code implements behavior Y
- **THEN** the reviewer SHALL flag this as a mismatch, set task to `revision_needed`, and notify the PM or `ask_user` if no PM role exists

#### Scenario: Missing doc on non-trivial task triggers revision
- **WHEN** `docs_threshold: non_trivial`, the task is non-trivial, and no decision doc exists at the configured path
- **THEN** the reviewer SHALL set task to `revision_needed` with a note requesting the decision doc

### Requirement: AI security checklist in code_reviewer and security_engineer roles
Both `code_reviewer` and `security_engineer` role templates SHALL include explicit checks for AI-specific failure modes:
- **Package hallucination (slopsquatting)**: verify package name exists on PyPI/npm, check publisher and first-published date; recently registered packages are a red flag
- **Overly broad permissions**: flag IAM wildcards, CORS `*`, file permissions 777, any wildcard scope
- **Prompt injection vectors**: flag any code path that passes external input (user input, file content, API responses) into shell commands, eval(), SQL queries, LLM prompts, or template engines without sanitization
- **Hardcoded secrets**: scan all AI-generated files for API keys, tokens, passwords, connection strings

#### Scenario: Hallucinated package triggers immediate escalation
- **WHEN** a reviewer finds an import that cannot be verified on the real package registry
- **THEN** the reviewer SHALL report to PM and `ask_user` immediately and block approval

#### Scenario: Security finding triggers revision_needed
- **WHEN** a reviewer finds a hardcoded secret, overly broad permission, or prompt injection vector
- **THEN** the reviewer SHALL set task to `revision_needed` and notify the `security_engineer` role if assigned

### Requirement: aw-verify skill for structured review execution
The system SHALL provide an `aw-verify` skill that gives the code reviewer agent a structured, step-by-step review execution workflow:
1. Read quality config and locate the decision doc for the task
2. Read code first — independent assessment
3. Run dependency check (verify all imports)
4. Run AI security checklist
5. Check tests independently
6. Read decision doc — cross-check against code
7. Update task status (`approved` or `revision_needed` with itemized notes)
8. Notify PM/principal with structured outcome

#### Scenario: aw-verify updates task to approved on clean review
- **WHEN** all review checks pass and doc matches code
- **THEN** `aw-verify` SHALL update task status to `approved` and notify the principal

#### Scenario: aw-verify updates task to revision_needed with itemized notes
- **WHEN** one or more review checks fail
- **THEN** `aw-verify` SHALL update task status to `revision_needed` with each issue listed separately (what it is, why it matters, suggested fix)

### Requirement: Echo-chamber guard in review routing
When `echo_chamber_guard` is `warn` or `enforce`, the system SHALL check that the agent assigned to review a task is not the same agent that implemented it.

#### Scenario: Enforce blocks routing to same agent
- **WHEN** `echo_chamber_guard: enforce` and the proposed reviewer is the implementing agent
- **THEN** the routing SHALL be blocked and the user SHALL be asked to assign an alternate reviewer

#### Scenario: Warn allows routing but flags the issue
- **WHEN** `echo_chamber_guard: warn` and the proposed reviewer is the implementing agent
- **THEN** the routing SHALL proceed with a logged warning visible to the user
