## ADDED Requirements

### Requirement: Busy-agent behaviour is documented across timing scenarios

The investigation findings for Blocker 2 SHALL document what currently happens when the watchdog spawns a second trigger for an agent while the first is still running. The findings SHALL include a behaviour matrix covering each runner across at least three timing scenarios, and SHALL explicitly state the current behaviour for session-file races, token usage, and message archival.

#### Scenario: Behaviour matrix covers all runners

- **WHEN** the Blocker 2 findings document is reviewed
- **THEN** it SHALL include a behaviour matrix with one row per runner the dev loop uses (opencode, kimi, codex)
- **AND** one column per timing scenario (mid-run overlap, near-finish overlap, three-queued overlap, shutdown overlap)
- **AND** every cell SHALL record observed subprocess count, session-file state, token usage, and message archival outcome

#### Scenario: Policy recommendation is justified

- **WHEN** the Blocker 2 findings document is reviewed
- **THEN** it SHALL recommend one of: per-agent mutex with queue, skip-if-busy, or coalesce
- **AND** the recommendation SHALL be justified by specific cells in the behaviour matrix rather than by general principle
- **AND** the findings SHALL call out any runner-specific quirk that would require the policy to differ per runner