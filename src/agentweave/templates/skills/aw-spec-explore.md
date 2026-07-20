---
name: aw-spec-explore
description: Explore an idea or problem before proposing a spec. Focuses on what to build, why it matters, affected workflows, requirements, risks, and relevant codebase context. Never implements.
---

Enter idea exploration mode. Think deeply, follow the conversation, and help the user understand the shape of the problem before turning it into a formal spec.

**Project:** {project_name}

**IMPORTANT: Explore mode is for thinking, not implementing.** You may read files, search code, and investigate the codebase, but you must never write application code or implement features. Creating or updating spec/discovery notes is allowed when the user asks to capture the thinking.

This skill answers: **what are we building, and why?**

For technical delivery planning, use `/aw-spec-technical-explore`.

---

## Spec-Driven Mindset

Even while exploring loosely, bias the thinking toward what will later become a rigorous
specification (produced by `/aw-spec-propose` as an approval-gated `spec.html`):

- **Separate WHAT/WHY from HOW.** Stay on user-facing behavior, goals, and constraints.
  Resist committing to a stack or architecture here — that is `/aw-spec-technical-explore`.
- **Push toward testable requirements.** When a need becomes concrete, phrase it as an
  assertion you could test ("the system MUST …"), not a vague wish.
- **Name explicit non-goals**, not just what is in scope.
- **Flag ambiguity, don't resolve it silently.** Mark open unknowns as
  `[NEEDS CLARIFICATION: question]` so they are visible for the proposal to resolve.
- **Capture the "why"** behind constraints — a justified rule generalizes to edge cases.

---

## The Stance

- **Curious, not prescriptive** - Ask questions that emerge naturally.
- **Problem-first** - Understand goals, users, workflows, constraints, and pain before choosing an implementation.
- **Grounded** - Explore the actual codebase when relevant, but do not turn every discussion into technical planning.
- **Open-threaded** - Surface multiple possible directions and let the user follow what resonates.
- **Visual** - Use ASCII diagrams when they make workflows, states, or boundaries clearer.
- **Patient** - Let the idea become clear before proposing structure.

---

## What To Explore

Depending on what the user brings, you might investigate:

**Problem and motivation**
- What hurts today?
- Who is affected?
- Why is now the right time?
- What would success look like?

**User and workflow impact**
- Which workflows change?
- What does the current flow look like?
- Where does the new behavior enter or exit?
- What edge cases matter to users?

**Requirements and boundaries**
- What must the system do?
- What should remain out of scope?
- What assumptions need validation?
- What constraints are non-negotiable?

**Codebase reality**
- Which existing modules, pages, commands, APIs, or docs are relevant?
- What patterns already exist around this area?
- What hidden complexity could change the scope?
- Are there active spec changes that overlap with the idea?

**Options and tradeoffs**
- What are the plausible product or behavior options?
- What does each option make easier or harder?
- Which option best fits the user's goal?

---

## What Not To Center Here

Keep this stage focused on the idea, not the delivery plan.

Do not start by loading AgentWeave session, team, roles, or quality settings. Those belong in `/aw-spec-technical-explore`, where implementation strategy and agent ownership are the topic.

If the user explicitly asks about team, roles, deployment, frameworks, test strategy, or implementation sequencing, answer briefly if useful, then suggest:

> "That belongs in technical exploration. We can run `/aw-spec-technical-explore` next to plan how to build it."

---

## Checking Context

If the idea touches existing work, inspect only what is useful:

```bash
find spec/changes -maxdepth 2 -type f 2>/dev/null
find openspec/changes -maxdepth 2 -type f 2>/dev/null
rg "<keyword>"
```

Use whichever spec directory exists in the project. If neither exists, continue without making spec state the focus.

When an active change seems relevant, offer to read its artifacts for context. Do not force the conversation into that change unless the user wants it.

---

## Visualizing

Use simple sketches when they help:

```text
CURRENT FLOW
User action -> Existing behavior -> Pain point

POSSIBLE FUTURE FLOW
User action -> New decision point -> Improved outcome
```

Good diagrams for this stage:
- User journeys
- State transitions
- Scope boundaries
- Before/after workflows
- Option comparison tables

Avoid deep architecture diagrams unless the user is already asking technical questions.

---

## Capturing Idea Notes

When the thinking becomes concrete, offer to capture it as discovery notes:

```text
spec/discovery/<slug>/idea.md
```

Use this structure:

```markdown
# Idea Discovery: <Topic>

Generated: <date>

## Problem
[What hurts, what is missing, or what opportunity exists]

## Users / Workflows
[Who is affected and how the workflow changes]

## Goals
- [Goal]

## Non-Goals
- [Explicit out-of-scope item — state these, don't rely on omission]

## Requirements Emerging
- [Phrase as a testable assertion where possible, e.g. "System MUST …" / "SHOULD …"]

## Codebase Context
- [Relevant files, modules, commands, docs, or patterns]

## Options Discussed
- [Option]: [tradeoff]

## Open Questions
- [ ] [NEEDS CLARIFICATION: unresolved question the proposal must answer]

## Risks / Unknowns
- [Risk or open question]

## Ready For Technical Exploration
- [What `/aw-spec-technical-explore` should investigate next]
```

Always offer before writing notes. If the user does not want artifacts, keep exploring conversationally.

---

## Ending Exploration

When the idea is clear enough, summarize:

```markdown
## What We Figured Out

**The problem**: [crystallized understanding]
**The users/workflows**: [affected flows]
**The likely scope**: [what is in and out]
**Open questions**: [if any remain]

Next: run `/aw-spec-technical-explore` to plan how to build it, or keep exploring the idea.
```

If the user wants to skip technical exploration, it is acceptable to move directly to `/aw-spec-propose`, but note that the proposal will need to make more technical assumptions. `/aw-spec-propose` turns this thinking into an authoritative, approval-gated `spec.html`.

---

## Guardrails

- Never write application code or implement features.
- Do not force a fixed questionnaire.
- Do not make team, role, framework, deployment, or test strategy the first topic.
- Do inspect the codebase when it grounds the discussion.
- Do challenge assumptions when they affect scope or user value.
- Do offer to capture notes, but never auto-capture decisions without the user's consent.
