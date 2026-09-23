# Test guide — a Claude run is told its AgentWeave tools by their full names

## Agent-verifiable

1. **Claude runs get callable names.** Tasks 1.1 and 1.4 fail today, pass after.
2. **Other runners and the run-less route are unchanged.** Controls 1.2, 1.3.
3. **The prefix set cannot drift from the command builder.** Task 1.6.

## Human-only

1. F139 is intermittent. Task 3.2's repeated drive gives a rate, not a proof: read each transcript
   and judge whether any agent still reached for the host tool, and whether the sentence naming it
   reads as clear rather than as noise.
