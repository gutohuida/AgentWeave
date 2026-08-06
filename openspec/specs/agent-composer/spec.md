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

### Requirement: Composer controls are unbounded

A composer control (model, effort, conversation routing, target agent) SHALL draw no border or fill
at rest. Hovering it MUST NOT draw a border or fill; emphasis SHALL be expressed as background,
text, or icon prominence instead.

Gaining emphasis MUST NOT change a control's box dimensions.

#### Scenario: A control at rest has no box

- **WHEN** a composer control is displayed without interaction
- **THEN** it draws no border and no fill

#### Scenario: Hover does not draw a box

- **WHEN** the operator hovers a composer control
- **THEN** no border appears
- **AND** the control's background, text, or icon becomes more prominent instead

#### Scenario: Emphasis does not move anything

- **WHEN** a composer control gains hover or active emphasis
- **THEN** its box dimensions are unchanged
- **AND** neighbouring controls do not shift

#### Scenario: Keyboard focus stays visible

- **WHEN** a composer control receives keyboard focus
- **THEN** its focus indicator is shown regardless of the borderless resting/hover treatment

### Requirement: Selection controls are pill-shaped and sized to their content

A composer selection control's trigger and its option list SHALL each be sized to their own content,
not to a fixed minimum. The trigger SHALL be fully rounded at its own height.

An option list MAY declare a maximum width; a label exceeding it SHALL truncate rather than widen the
list.

#### Scenario: A short label yields a short control

- **WHEN** a composer control's current value is a short label
- **THEN** the control's width reflects that label, not a larger fixed minimum

#### Scenario: The list fits its longest item

- **WHEN** a control's option list is shown
- **THEN** its width is derived from its content, not a fixed minimum width

#### Scenario: Ends stay fully rounded

- **WHEN** a composer control's label length changes
- **THEN** its ends remain fully rounded at its own height

#### Scenario: An over-long item truncates rather than widening

- **WHEN** an option list declares a maximum width and an item's label exceeds it
- **THEN** the label truncates
- **AND** the list does not widen past its maximum

### Requirement: The composer surface does not react to focus

The composer's own surface SHALL NOT change its border, shadow, or ring in response to focus moving
into it or text being typed within it. The surface's resting treatment SHALL be sufficient to read as
a distinct surface without a focus reaction.

Controls within the composer are unaffected by this requirement and keep their own focus indicators.

#### Scenario: Clicking into the composer changes nothing around it

- **WHEN** the operator clicks into the composer's text input
- **THEN** the composer surface's border, shadow, and ring are unchanged

#### Scenario: Typing changes nothing around it

- **WHEN** the operator types into the composer
- **THEN** the composer surface's border, shadow, and ring remain unchanged

#### Scenario: Controls keep their own focus indicator

- **WHEN** a control inside the composer receives keyboard focus
- **THEN** that control's own focus indicator is shown

### Requirement: Model selection shows which provider a model belongs to

The composer's model control SHALL show the mark of the model's provider, both for the currently
selected model and for each offered option. Where a provider has no known mark, its name SHALL be
shown as a text label instead.

This SHALL NOT require hardcoding a provider's identity into the composer: the mark SHALL be resolved
by the catalog's provider identity, keeping the composer provider-agnostic per the existing model
catalog contract.

#### Scenario: The current model shows its provider

- **WHEN** the composer displays the currently selected model
- **THEN** that model's provider mark is shown alongside it

#### Scenario: An unknown provider degrades to a label

- **WHEN** a model's provider has no known mark
- **THEN** the provider's name is shown as text instead
- **AND** no broken or incorrect mark is shown

#### Scenario: Marks need no second icon system

- **WHEN** a provider mark is rendered
- **THEN** it is implemented within the application's existing icon system, not a second one

#### Scenario: The composer stays provider-agnostic

- **WHEN** the composer's source is inspected
- **THEN** it contains no hardcoded provider name, model identifier, or control value

### Requirement: The model picker is searchable and organised by provider

The composer's model picker SHALL support finding a model by typing part of its name, its
identifier, or its provider's name — not only a leading match. Results SHALL be grouped so that
every entry is attributable to its provider at a glance.

Searching MUST NOT surface a model that would not otherwise be selectable. An empty result SHALL
state that nothing matched and offer a way back to the full list.

#### Scenario: A model is found by typing part of its name

- **WHEN** the operator types a substring that appears in the middle of a model's name
- **THEN** that model is found

#### Scenario: Typing a provider's name reaches its models

- **WHEN** the operator types a provider's name
- **THEN** that provider's models are found

#### Scenario: Entries are attributable to a provider at a glance

- **WHEN** the model picker is open
- **THEN** each entry's provider is identifiable without further interaction

#### Scenario: Search reaches nothing extra

- **WHEN** a search is active
- **THEN** only models otherwise selectable are shown

#### Scenario: An empty search is not a dead end

- **WHEN** a search matches nothing
- **THEN** the picker states that nothing matched
- **AND** offers a way to return to the full list

### Requirement: Frequently-used models are reachable without searching

The operator SHALL be able to mark and unmark a model as a favourite from within the picker. A
favourited model SHALL be presented before non-favourited ones. This marking SHALL persist across
conversations and across reloads.

Favouriting MUST NOT change which model is an agent's default or currently resolved model — it SHALL
affect presentation order only.

#### Scenario: A marked model is reachable immediately

- **WHEN** the operator opens the model picker
- **THEN** any favourited model appears before non-favourited ones

#### Scenario: A marking survives a reload

- **WHEN** the operator favourites a model and reloads
- **THEN** that model is still presented as a favourite

#### Scenario: Marking changes nothing but ordering

- **WHEN** the operator favourites a model
- **THEN** no agent's default or resolved model changes as a result

#### Scenario: Marking is reversible in place

- **WHEN** the operator unmarks a favourited model
- **THEN** it returns to its unfavourited presentation order

### Requirement: The model picker is fully operable from the keyboard

The operator SHALL be able to open the model picker, narrow it by typing, move between results, and
select or dismiss it, using only the keyboard. Dismissing SHALL leave the current selection
unchanged.

#### Scenario: The picker is driven entirely by keyboard

- **WHEN** the operator uses only the keyboard
- **THEN** they can open the picker, narrow results by typing, move between them, and select one

#### Scenario: Dismissing selects nothing

- **WHEN** the operator dismisses the picker via the keyboard
- **THEN** the previously selected model is unchanged

---

### Requirement: The composer addresses the conversation it belongs to

A message submitted from a conversation SHALL be delivered to that conversation's agent. The
composer MUST NOT offer a control that redirects a submission to a different agent.

#### Scenario: A submission targets the current agent

- **WHEN** the operator submits a message from agent `A`'s conversation
- **THEN** the submission targets `A`

#### Scenario: No redirect control is offered

- **WHEN** the composer's control row is displayed
- **THEN** it contains no control for selecting a different recipient agent
