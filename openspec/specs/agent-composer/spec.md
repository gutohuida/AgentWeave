# agent-composer Specification

## Purpose

The conversation composer helps operators reference workspace files and skills, invoke built-in
commands, and redirect the next turn to another configured agent without leaving the conversation
surface or violating immutable conversation scope.

## Requirements

### Requirement: Composer trigger detection
The composer SHALL detect three trigger kinds from the current text and cursor position:
`path` (`@`), `skill` (`$`), and `slash-command` (`/`). Detection SHALL return
`{kind, query, rangeStart, rangeEnd}` on a match and `null` otherwise.

`slash-command` SHALL only match when the trigger character is the first character of the
current line. `path` and `skill` SHALL be detected by walking backward from the cursor to the
nearest whitespace boundary and inspecting that token's first character; they SHALL match at any
position within a line, not only at line start.

#### Scenario: Slash command mid-sentence is not a trigger
- **WHEN** the composer text is `"see https://example.com/foo"` with the cursor placed immediately after `/foo`
- **THEN** detection returns `null` — `/` is not the first character of its line

#### Scenario: Slash command at line start is a trigger
- **WHEN** the composer text is `"/mod"` with the cursor at the end
- **THEN** detection returns `{kind: "slash-command", query: "mod", rangeStart: 0, rangeEnd: 4}`

#### Scenario: Path mention mid-line is a trigger
- **WHEN** the composer text is `"see @src/comp"` with the cursor at the end
- **THEN** detection returns `{kind: "path", query: "src/comp", rangeStart: 4, rangeEnd: 13}`

#### Scenario: No open trigger after a completed token
- **WHEN** the composer text is `"@src/composer.tsx looks good"` with the cursor at the end
- **THEN** detection returns `null` — the `@`-token ended at the first whitespace after it

### Requirement: Trigger range replacement
Accepting a menu result SHALL replace exactly the matched `[rangeStart, rangeEnd)` span with the
selected value and SHALL return both the resulting text and the new cursor position, placed
immediately after the inserted value. A value containing whitespace SHALL be quote-escaped in the
inserted text.

#### Scenario: Replacement repositions the cursor after the inserted value, not at text end
- **WHEN** the composer text is `"@src/comp then check the tests"`, the open trigger spans `[0, 9)`, and the accepted value is `src/components/agents/Composer.tsx`
- **THEN** the cursor is immediately after `Composer.tsx`, not at the end of the whole string

#### Scenario: A path containing whitespace is quote-escaped on insertion
- **WHEN** the accepted value is a path `docs/release notes.md`
- **THEN** the inserted text is the quoted, escaped form, not the raw unquoted path

### Requirement: Keyboard-navigable trigger menu
While a trigger is open, the composer SHALL render a menu of matching results that supports moving
the active selection with the arrow keys, accepting the active result with Enter or Tab, and
dismissing the menu with Escape. Dismissal SHALL leave the typed text unmodified and SHALL return
keyboard focus to the composer input.

#### Scenario: Escape dismisses without altering text or focus
- **WHEN** a trigger menu is open over the text `"@src/comp"` and the user presses Escape
- **THEN** the menu closes, the text is unchanged, and the composer input retains focus

#### Scenario: Arrow-key navigation changes the active result without accepting it
- **WHEN** a trigger menu has more than one result and the user presses the down arrow
- **THEN** the next result becomes active and no text is inserted

### Requirement: Workspace path listing endpoint
The Hub SHALL expose an endpoint that lists workspace paths under the Hub process's working
directory, honoring `.gitignore`, nested `.gitignore` files, and global excludes. If the working
directory is not a git repository, the endpoint SHALL return an empty list rather than an error.

#### Scenario: Listing excludes gitignored paths
- **WHEN** `.gitignore` excludes `node_modules/` and that directory exists
- **THEN** the response includes no path under `node_modules/`

#### Scenario: Listing on a non-git working directory returns empty, not an error
- **WHEN** the Hub's working directory contains no `.git`
- **THEN** the endpoint responds successfully with an empty path list

### Requirement: Trigger result sources
The `path` trigger SHALL source results from the workspace path listing endpoint. The `skill`
trigger SHALL use the same endpoint filtered to `.claude/skills/`, stripping that prefix and any
`.md` suffix. For `.claude/skills/<name>/SKILL.md`, the displayed value SHALL be `<name>` rather
than `<name>/SKILL`. The `slash-command` trigger SHALL use a fixed composer-defined list requiring
no backend request.

#### Scenario: Skill results are scoped to the skills directory
- **WHEN** paths include `.claude/skills/aw-status.md` and `src/index.ts`
- **THEN** `$` results include `aw-status` and exclude `src/index.ts`

#### Scenario: No skills directory yields no skill results, not an error
- **WHEN** no listed path is under `.claude/skills/`
- **THEN** a `$` trigger returns zero results and the normal empty state

#### Scenario: Generated skill directories display the skill name
- **WHEN** paths include `.claude/skills/aw-status/SKILL.md`
- **THEN** a `$` trigger displays `aw-status`, not `aw-status/SKILL`

### Requirement: In-place agent selector
The composer SHALL offer a searchable selector listing every configured agent and showing each
agent's launchability from `GET /api/v1/agents/launchability`. Selecting a different agent SHALL
NOT alter the current conversation's `agent`; the next message SHALL start a new conversation
targeting the selected agent.

#### Scenario: Selecting a different agent starts a new conversation
- **WHEN** conversation C belongs to `claude` and the operator selects `codex` then submits
- **THEN** the submission targets `codex` with no `conversation_id`
- **AND** conversation C's agent remains `claude`

#### Scenario: A non-launchable agent is visibly distinguished, not hidden
- **WHEN** `minimax` is present but not authorized
- **THEN** the selector lists `minimax` with an indicator reflecting that state
