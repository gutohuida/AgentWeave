## ADDED Requirements

### Requirement: A measured sample identifies the model it measured

A sample with `status: measured` SHALL carry the model identifier for the turn it measured, so that
the stated window-resolution order can reach the catalog.

*Context-window size is resolved in a stated order* already requires the catalog to fill a missing
provider report, and *Unknown context usage is reported as unknown* already forbids substituting a
default. Neither is reachable for a sample that does not say which model ran: the catalog is keyed
by model, so an unidentified sample can only ever resolve to unknown.

Observed consequence of the gap: every `claude` sample carrying `context_tokens` was emitted with
`model: null`, so no Claude agent has ever reported a usable proportion — 329 samples, zero
percentages — while `codex_appserver` samples, which identify their model, always did.

#### Scenario: A measured sample carries its model

- **WHEN** a measured context-usage sample is produced for a turn
- **THEN** it identifies the model that ran that turn
- **AND** the window-resolution order is applied to that model

#### Scenario: An unidentified sample resolves to unknown rather than to a default

- **WHEN** a sample cannot identify the model that ran the turn
- **THEN** usage is reported as unknown
- **AND** no window is assumed from another model or from a default

### Requirement: Window metadata observed for a session persists across later samples that omit it

Once a context window has been resolved for a provider session, the Hub SHALL continue to express
that session's usage against it when a later sample omits the window, rather than reporting unknown.

*Latest observation replaces rather than accumulates* governs token counts: successive samples must
not be summed. It does not require window metadata to be discarded, and discarding it is what turns
a complete picture into an incomplete one.

A runner may report usage and window in separate events. Claude does exactly this: the per-message
`usage` payload carries token counts with no window, while the result payload carries
`modelUsage.contextWindow` with no token count. Replacing one with the other loses whichever half
arrived first.

This requirement governs window and model metadata only. Token counts continue to replace.

#### Scenario: A window reported once continues to apply

- **WHEN** a provider reports a context window for a session
- **AND** a later sample for that session carries token counts but no window
- **THEN** usage is expressed against the previously reported window

#### Scenario: Token counts still replace rather than accumulate

- **WHEN** successive samples carry token counts for the same session
- **THEN** the later count replaces the earlier one
- **AND** the counts are not summed

#### Scenario: A changed model discards the previous window

- **WHEN** a later sample identifies a different model from the one whose window was retained
- **THEN** the retained window no longer applies
- **AND** the window is resolved again for the new model

### Requirement: Every model the catalog offers declares a context window or is stated as unknown

The model catalog SHALL declare a context window for each model it offers, or the resulting usage
SHALL be reported as unknown for that model without falling back to another model's window.

`claude-opus-5` and `claude-fable-5` are currently offered with no declared window, so agents bound
to them cannot report a proportion even once the defects above are corrected. Declaring the windows
is a data completion; the requirement is that an absent one degrades to unknown rather than to a
borrowed value.

#### Scenario: A catalog model without a declared window

- **WHEN** an agent runs on a model the catalog offers with no declared window
- **AND** the provider reports no window
- **THEN** usage is reported as unknown for that turn
- **AND** no other model's window is substituted
