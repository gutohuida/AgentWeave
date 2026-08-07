# Spec execution coordinator — skeleton, gated on exploration

> **STATUS: SKELETON. DO NOT IMPLEMENT.**
>
> This change has a proposal and an exploration task list. It deliberately has **no `design.md`
> and no `specs/`**, because the architecture is not known yet and writing it now would encode
> assumptions instead of findings.
>
> **Gate:** Section 1 of `tasks.md` — the exploration — must be completed, and `design.md` and
> `specs/` written from what it finds, **before any task in section 2 or later is started**.
>
> Unlike `2026-08-07-conversation-handoff-rework`, this change is **not** gated behind another
> change. It is gated on its own unanswered questions, which are architectural rather than
> mechanical. It is also considerably larger than either change written alongside it, and the
> exploration may well conclude that it should be split.
>
> **`openspec validate --changes` fails on this change, and that failure is the gate working.**
> It reports *"Change must have at least one delta"* because `specs/` is deliberately absent. Do
> **not** silence it by writing placeholder requirements. The failure clears when task 1.14 writes
> the real specs, and not before.
>
> Do not mark any task complete on the strength of this document existing.

## Why

**Governance and quality gates are a stated product pillar and are currently unenforced.**

`openspec/explorations/2026-08-02-product-direction.md` names three differentiators — multi-agent
collaboration, spec-driven development with the agents, and *"governance and quality gates: review
separation, echo-chamber protection, verification before completion."* It also states that the
specification program *"should no longer be treated as the last slice."* It has been next since
2026-08-02 and is unstarted.

What exists today, traced 2026-08-07:

- **The task lifecycle is documentation, not a machine.** `CLAUDE.md` draws
  `pending → assigned → in_progress → completed → under_review → approved`. Nothing enforces it.
  `hub/hub/api/v1/tasks.py:183-184` is `if body.status is not None: task.status = body.status` —
  a direct assignment with no transition check. The Pydantic validator on the update schema
  (`hub/hub/schemas/tasks.py:106-110`, and the same shape on create at `:72-76`) checks
  **membership in a set**, not a **transition**, so `pending → approved` in a single call is valid
  input at every layer that inspects it.
- **An agent can approve its own work.** The MCP tool `update_task(task_id, status)`
  (`hub/hub/mcp_server.py:245`) accepts any member of `TaskStatus`. There is no reviewer concept,
  no author/reviewer separation, and no check that a review happened.
- **`Task` has nowhere to record why a gate passed.** Its fields are `requirements`,
  `acceptance_criteria`, `deliverables` and `notes` — four free-form JSON blobs. No evidence
  record, no verification outcome, no reviewer, no gate state.
- **No agent-facing surface touches specs, reviews, evidence or gates.** Of the 13 MCP tools, none
  do. `hub/hub/api/v1/spec.py` has four routes and all of them read: `POST /specs/sync`,
  `GET /specs`, `GET /spec`, `POST /specs/reconcile`.

So the pillar exists as vocabulary — a status enum, a lifecycle diagram, an
`openspec/specs/aw-spec-workflow/spec.md` describing an authoring flow — with no component that
*guarantees* anything.

## The idea

Stated by the operator, 2026-08-07:

> *"A spec coordinator, something that will control the execution of the specs and tasks but it
> should be a deterministic code augmented by AI. I want to control the execution flow, the gates,
> etc with a deterministic immutable code that guarantees certain conditions empowered by some AI
> rationale. The user will config which AI it will use and it will only augment parts of the code
> that are hard to make decisions or that we actually need intelligence for."*

This inverts the usual arrangement. In the common design, a model orchestrates and calls tools;
what happens is whatever the model decided, and a "gate" is a prompt asking it nicely. Here:

```
   COMMON SHAPE                      THIS SHAPE
   ────────────                      ──────────

   model decides the flow            code decides the flow
        │                                 │
        ├─ calls a tool                   ├─ reaches a point needing judgement
        ├─ calls a tool                   │      │
        └─ declares itself done           │      └─ asks a model, bounded
                                          │         question, bounded answer
   the gate is a prompt                   ├─ records the answer and its rationale
   the guarantee is vibes                 └─ applies its own rule to the answer

                                     the gate is code
                                     the model is an advisor at named points
                                     the model cannot alter the machine
```

The load-bearing words in the operator's statement, each of which becomes an exploration question
rather than an assumption:

- **deterministic** — the same inputs produce the same transitions
- **immutable** — the machine is not editable by the thing it governs
- **guarantees certain conditions** — the coordinator's promises hold regardless of model behaviour
- **augmented, only where intelligence is needed** — AI is called at enumerated points, not
  everywhere
- **the user configs which AI** — model selection is operator configuration

## What Changes

**This section is provisional.** It records the direction the exploration is testing, not
decisions. Every bullet is subject to being overturned by section 1 of `tasks.md`.

- A coordinator owns the execution of a specification's work: which task may start, who may work
  it, what must be true before it advances, and what must exist before it is called done.
- Task state becomes a **transition graph enforced in code**, replacing today's set-membership
  check. Illegal transitions are refused with a stated reason rather than silently written.
- **Author and reviewer separation is structural**, not advisory: the coordinator refuses to accept
  a review from the identity that produced the work.
- **Evidence becomes a record**, attached to a requirement or a task, so "verification before
  completion" is a query rather than a claim.
- **AI decision points are enumerated, bounded, and recorded** — each call has a defined question,
  a constrained answer shape, a recorded rationale, and a defined behaviour when the model is
  unavailable or disagrees with itself.
- **Model selection is per decision point**, configured by the operator, reusing the project's
  existing runners.
- The agent capability plane gains spec-, evidence- and gate-facing tools — the gap the direction
  document names as *"the largest"*.

## The question the exploration exists to answer

**If an AI can decide a gate's outcome, the determinism is theatre.**

This is the central tension and it is not resolved. A coordinator whose gates are enforced in code
but whose gate *outcomes* come from a model has moved the judgement, not constrained it. Yet a
coordinator that never asks a model cannot judge whether a change actually satisfies a requirement
— which is exactly the *"hard to make decisions"* case the operator wants AI for.

The likely resolution is a distinction between **binding** and **advisory** decisions — some model
outputs are inputs to a rule the code applies, others are recorded rationale that a human or a
structural check must still ratify. Which decisions fall on which side is the single most important
output of the exploration, and it is deliberately not decided here.

## Capabilities

**Not yet determined.** Filling this in is an output of the exploration, not an input to it.

Candidates, to be confirmed or rejected: a new `spec-execution` capability for the coordinator
itself; a new `quality-gates` capability for gate definition and evaluation; deltas on
`agent-capability-plane` for the spec/evidence/gate tools; a delta on `agent-tool-surface` for how
they are described to agents. `openspec/specs/aw-spec-workflow/spec.md` describes the shipped
authoring flow and may or may not be the coordinator's input format — task 1.4.

## Impact

**Not yet determined.** Two things are already established:

- `hub/hub/api/v1/tasks.py` and `hub/hub/schemas/tasks.py` currently permit any status transition,
  and cannot continue to if the coordinator is to guarantee anything.
- `hub/hub/mcp_server.py`'s `update_task` is the agent-facing path to that same unguarded write.

**Related, already decided elsewhere:** `2026-08-07-conversation-navigation` adds
`Conversation.origin` with `spec` as an accepted value and no producer. That is this change's
attachment point — a conversation the coordinator spawns for a specification's work is where
`origin: spec` becomes real.

## Prior exploration

None specific to the coordinator. The surrounding direction is in
`openspec/explorations/2026-08-02-product-direction.md` (sections 1b, 3 and 4) and
`openspec/explorations/2026-08-03-specification-authority-technical.md`. Both should be read before
section 1 begins; neither answers the questions in it.
