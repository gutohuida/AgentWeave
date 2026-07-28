## 1. OpenSpec Schema — Register team artifact

- [x] 1.1 N/A — spec-driven schema is in the openspec package; aw-spec skills operate independently
- [x] 1.2 N/A — same reason

## 2. team.md Template

- [x] 2.1 Create `src/agentweave/templates/skills/aw-spec-team.md` — template with four sections: Recommended Team (table), Role Reasoning, Gap Analysis, Setup Commands
- [x] 2.2 Add staleness note at top of template (generation date blockquote)
- [x] 2.3 Include instructions for how to read current session roles from `.agentweave/roles.json` for the gap analysis

## 3. Update aw-spec-explore skill

- [x] 3.1 In `src/agentweave/templates/skills/aw-spec-explore.md`, add a closing section: when the conversation reaches proposal-ready state, offer to create a proposal AND a team recommendation
- [x] 3.2 Add instruction: team recommendation is unconstrained — reason from spec outward, not from current session inward
- [x] 3.3 Add instruction: if user asks "what team would I need?", generate an inline recommendation without requiring a formal proposal first
- [x] 3.4 Add instruction: explicitly surface the gap — "you currently have X, this project also needs Y and Z"

## 4. Update aw-spec-propose skill

- [x] 4.1 In `src/agentweave/templates/skills/aw-spec-propose.md`, add `team.md` to the artifact generation sequence (after `tasks.md`)
- [x] 4.2 Add instruction: read `roles.json` from `.agentweave/` to populate gap analysis if available, fall back gracefully if not
- [x] 4.3 Add instruction: team generation is spec-unconstrained — derive from proposal scope, not current session
- [x] 4.4 Document standalone regeneration: if `team.md` already exists and user asks to regenerate, update only `team.md` without touching other artifacts
