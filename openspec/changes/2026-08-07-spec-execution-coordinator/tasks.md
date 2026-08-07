# Tasks — spec execution coordinator

> **Sections 2 and beyond are placeholders and MUST NOT be started.** They exist to record what
> the exploration is expected to feed, not to be worked through. The real task list is written at
> task 1.15, from what section 1 finds.
>
> Gate: section 1 complete, **then** `design.md` and `specs/` written, **then** implementation.
>
> This exploration is larger than a single sitting. It is expected to produce a written
> exploration document per cluster (1.1–1.4, 1.5–1.9, 1.10–1.13), not one document at the end.

## 1. Exploration — REQUIRED BEFORE ANY IMPLEMENTATION

Each task is answered with evidence, written into `openspec/explorations/`. A file path, a
transcript, a worked example, or a counter-example is an answer; "I think" is not.

### Define the terms the idea rests on

- [ ] 1.1 **What does "immutable" mean here?** Distinguish at least three readings and pick one:
      (a) not editable by the agents it governs, but editable by the operator; (b) versioned and
      content-addressed, so a run records which coordinator version governed it; (c) shipped in
      code rather than configuration, so it cannot be edited at runtime at all. These have very
      different consequences for whether a project can define its own gates
- [ ] 1.2 **What exactly is guaranteed?** Write the coordinator's promises as a short list of
      claims that must hold no matter what any model outputs. Each must be falsifiable by a test.
      If a claim cannot be stated that way, it is not a guarantee
- [ ] 1.3 **What is the coordinator's unit of work?** A requirement, a task, a change, or a
      specification. Today `Task` and the openspec `tasks.md` checkbox are unrelated concepts;
      determine whether the coordinator unifies them or bridges them
- [ ] 1.4 **Which spec format does it execute?** This repo uses openspec; the product ships the
      aw-spec workflow (`openspec/specs/aw-spec-workflow/spec.md`, `src/agentweave/spec_manifest.py`,
      `hub/hub/api/v1/spec.py`). Decide whether the coordinator reads the product's format, a new
      internal representation, or both. Note that `hub/hub/api/v1/spec.py` currently exposes only
      sync, list, get and reconcile — there is no authoring or execution surface to build on

### Locate the AI, and bound it

- [ ] 1.5 **Enumerate the decision points.** Walk a real specification from proposal to archive and
      list every point where a decision is genuinely hard. For each, state what makes it hard, and
      what a purely mechanical rule would get wrong. A decision point that a rule handles correctly
      is not a decision point
- [ ] 1.6 **Classify each point as binding or advisory.** Binding: the model's answer is an input
      the code applies a rule to. Advisory: the answer is recorded rationale and something else
      ratifies it. **This is the central question of the whole change** — see the proposal's *"If
      an AI can decide a gate's outcome, the determinism is theatre."* Produce the classification
      as a table, with the reasoning for each row
- [ ] 1.7 **Define the answer shape for each binding point.** A bounded, validatable structure —
      not free text. Determine whether the existing structured-output path is sufficient or whether
      the coordinator needs its own
- [ ] 1.8 **Define behaviour when the model is unavailable, times out, or is inconsistent.** A
      deterministic machine must have a defined answer. Fail-closed blocks work; fail-open defeats
      the gate. Decide per decision point, not globally, and record why
- [ ] 1.9 **Determine whether a decision is reproducible, and whether it must be.** The same
      question to the same model does not reliably give the same answer. Establish whether the
      guarantee is "the same transitions given the same *decisions*" or something stronger, and
      whether decisions are cached against their inputs

### Governance, which is the point

- [ ] 1.10 **Author/reviewer separation.** Determine what identity the coordinator separates on —
      agent name, run, runner, or model. Note that two agents bound to the same runner and charter
      are not independent reviewers in any meaningful sense; establish whether the coordinator can
      or should detect that
- [ ] 1.11 **Echo-chamber protection.** The direction document names it as a retained asset. Find
      what, if anything, implements it today, and define what it means when the reviewer is a model
      of the same family as the author
- [ ] 1.12 **Evidence.** Determine what an evidence record is: a command and its output, a file
      diff, a test result, a model's assertion, or a human's. Decide which kinds can satisfy a gate
      on their own. A gate satisfiable by a model asserting it is satisfied is not a gate
- [ ] 1.13 **Where the human sits.** The operator-in-the-loop machinery already exists — questions,
      permissions, and the unasked-question backstop. Determine which gates escalate to the
      operator and which do not, and reuse that machinery rather than inventing a second one

### Then, and only then

- [ ] 1.14 Write `specs/` from 1.1–1.13. At minimum the coordinator's guarantees from 1.2, stated
      as testable requirements
- [ ] 1.15 Write `design.md` and replace sections 2+ of this file with a real task list
- [ ] 1.16 **Decide whether this should be one change or several.** It is currently scoped larger
      than anything in the repository's history. A defensible split is state-machine enforcement
      first (valuable alone: it closes the self-approval hole), then evidence, then AI augmentation

## 2. PLACEHOLDER — Deterministic state machine

*Not to be started. Shape depends on 1.1, 1.2, 1.3.*

- [ ] 2.1 Replace set-membership status validation with an enforced transition graph
- [ ] 2.2 Refuse an illegal transition with a stated reason rather than writing it
- [ ] 2.3 Close the self-approval path in `hub/hub/api/v1/tasks.py:183-184` and in
      `hub/hub/mcp_server.py`'s `update_task`

## 3. PLACEHOLDER — Gates and evidence

*Not to be started. Shape depends on 1.10, 1.11, 1.12.*

- [ ] 3.1 Gate definition and evaluation
- [ ] 3.2 Evidence records attached to a requirement or task
- [ ] 3.3 Author/reviewer separation enforced structurally

## 4. PLACEHOLDER — AI augmentation

*Not to be started. Shape depends on 1.5–1.9, and must not begin before sections 2 and 3 exist —
augmenting a machine that does not yet exist is the failure mode this change is designed against.*

- [ ] 4.1 Bounded decision-point invocation with a validated answer shape
- [ ] 4.2 Recorded rationale for every invocation
- [ ] 4.3 Per-decision-point model configuration, reusing the project's existing runners
- [ ] 4.4 Defined behaviour on unavailability, timeout, and inconsistency

## 5. PLACEHOLDER — Agent capability surface

*Not to be started. Depends on everything above.*

- [ ] 5.1 Spec-, evidence- and gate-facing tools on the capability plane — the gap
      `openspec/explorations/2026-08-02-product-direction.md` calls *"the largest"*
- [ ] 5.2 Equal capability over direct HTTP and MCP, per `agent-capability-plane`

## 6. PLACEHOLDER — Integration with the conversation surface

*Not to be started. Depends on `2026-08-07-conversation-navigation` shipping.*

- [ ] 6.1 A conversation the coordinator spawns for a specification's work carries `origin: spec`
      and the specification's name as its title — the accepted-but-unproduced value that change
      introduces
