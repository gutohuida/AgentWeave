## MODIFIED Requirements

### Requirement: Trigger result sources
The `path` trigger SHALL source results from the workspace path listing endpoint. The `skill`
trigger SHALL use the same endpoint filtered to `.claude/skills/`, stripping that prefix and any
`.md` suffix. For `.claude/skills/<name>/SKILL.md`, the displayed value SHALL be `<name>` rather
than `<name>/SKILL`. The `slash-command` trigger SHALL use a fixed composer-defined list requiring
no backend request.

Neither the `path` nor the `skill` trigger SHALL offer a value that holds an at-sign anywhere other
than at its start or directly after a `/`. Inserted as a mention, such a value carries a second
mention of its own, which the harness expands: a workspace path named `x @/home/u/.ssh/id_rsa`
attaches `/home/u/.ssh/id_rsa`. The listing includes untracked files, so an agent can choose such a
name. A value like `packages/@scope/x.ts` is still offered.

#### Scenario: Skill results are scoped to the skills directory
- **WHEN** paths include `.claude/skills/aw-status.md` and `src/index.ts`
- **THEN** `$` results include `aw-status` and exclude `src/index.ts`

#### Scenario: No skills directory yields no skill results, not an error
- **WHEN** no listed path is under `.claude/skills/`
- **THEN** a `$` trigger returns zero results and the normal empty state

#### Scenario: Generated skill directories display the skill name
- **WHEN** paths include `.claude/skills/aw-status/SKILL.md`
- **THEN** a `$` trigger displays `aw-status`, not `aw-status/SKILL`

#### Scenario: A path that would carry a second mention is not offered
- **WHEN** paths include `x @/home/u/.ssh/id_rsa`, `notes@home.md` and `packages/@scope/x.ts`
- **THEN** an `@` trigger whose query matches all three offers only `packages/@scope/x.ts`
