# hub-workspace-shell

## ADDED Requirements

### Requirement: A command palette reaches conversations, agents, documents, and tasks without navigating the tree

The Hub SHALL offer a keyboard-activated command palette that searches, within the current project,
its conversations, agents, spec documents, and tasks, and navigates to the selected result on
activation.

The palette SHALL be reachable by a fixed keyboard shortcut from anywhere in the Hub, and SHALL NOT
open while the operator's focus is in a text input or the composer and the triggering key is typed
without its required modifier.

Dismissing the palette without a selection MUST NOT navigate anywhere or otherwise change what is
displayed.

#### Scenario: The palette opens on its shortcut

- **WHEN** the operator activates the palette's keyboard shortcut from anywhere in the Hub
- **THEN** a searchable overlay opens listing conversations, agents, spec documents, and tasks from
  the current project

#### Scenario: Typing in a text field does not open the palette

- **WHEN** the operator's focus is in a text input or the composer and they type the palette's
  trigger key without its modifier
- **THEN** the palette does not open
- **AND** the typed character reaches the focused field

#### Scenario: Selecting a result navigates to it

- **WHEN** the operator selects a conversation, agent, spec document, or task from the palette
- **THEN** the Hub navigates to that destination
- **AND** the palette closes

#### Scenario: Dismissing without selecting changes nothing

- **WHEN** the operator dismisses the palette without selecting a result
- **THEN** the Hub's displayed destination is unchanged
