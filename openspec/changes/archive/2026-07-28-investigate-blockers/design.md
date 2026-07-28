## Context

Three runtime defects block the autonomous dev loop:
1. Context-window tracking is unreliable end-to-end.
2. Forced-reset behaviour is unverified.
3. Triggering a busy agent has unknown behaviour.

This change ships investigation artefacts only — flow diagrams, behaviour matrices, raw evidence — and explicitly does not ship fixes. The fix changes (`fix-context-tracking`, `add-auto-reset-mode`, `add-durable-trigger-retry`) will read the findings produced here and design their respective solutions.

## Goals / Non-Goals

**Goals:**

- Produce per-blocker findings documents that the user can read and approve.
- Capture the actual current behaviour, not assumed behaviour.
- Attach evidence to every non-working observation.

**Non-Goals:**

- Implement any fix.
- Make any code change to AgentWeave or the Hub.
- Change the runtime behaviour of any component.

## Decisions

### Decision: One findings document per blocker

Each blocker gets its own `findings/blocker-N.md` file. This keeps the findings small and easy to review independently, and lets the user approve each one on its own merits.

### Decision: Findings evolve as commits, not as a final document

The agent commits after every meaningful observation, not just at the end. This gives the user a paper trail of what was tested, what was found, and when.

### Decision: Evidence is mandatory for every non-WORKING arrow / non-clean behaviour

A claim that an arrow is `BROKEN` is not useful without the log line, DB query, or observed CLI output that proves it. Every non-working claim SHALL have evidence attached.

## Open Questions

- None. The investigation approach is straightforward; the findings themselves will surface the open questions.