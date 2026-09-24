# Test guide — a Claude run is told its AgentWeave tools by their full names

## Agent-verifiable

1. **Claude runs get callable names.** Tasks 1.1 and 1.4 fail today, pass after.
2. **Other runners and the run-less route keep bare names.** Controls 1.2, 1.3; for Codex the preamble
   says the harness *may* prefix them (task 1.2, operator review 2026-09-24).
3. **The prefix set cannot drift from the command builder.** Task 1.6.
4. **A first Claude run is warned about the host tool too.** Task 1.1a and 1.4's control: the HTTP
   form carries the host-`SendMessage` sentence and no prefixed name.

## Human-only

1. F139 is intermittent. Task 3.2's repeated drive gives a rate, not a proof: read each transcript
   and judge whether any agent still reached for the host tool, and whether the sentence naming it
   reads as clear rather than as noise.
