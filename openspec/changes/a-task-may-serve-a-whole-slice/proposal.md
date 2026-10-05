## Why

**Tier 1.** Source: `openspec/explorations/2026-09-29-specs-that-evolve-by-slice.md`, section
*2026-10-05: re-grounded at `9dd11cc`* (operator decisions Q14 and Q15, and the split of C1 into C1a
and C1b). Sibling: `2026-10-05-a-spec-is-written-one-slice-at-a-time` (C1a, archived), which made a
slice small. This change lets a slice be built as a few tasks instead of many.

A slice of about a dozen requirements cannot be a few tasks today:
- **A task may name at most three requirements.** Proposing a document is refused when any task
  names more (`MAX_REQUIREMENTS_PER_TASK = 3`, `hub/hub/spec_completeness.py:39`, `:249-258`). So 12
  requirements need at least 4 tasks, and in the two real LoopEngine runs (`:8000`, read `mode=ro`)
  77 requirements became 32 tasks, each reviewed on its own.
- **The ceiling's safeguard does not hold on any real document.** The ceiling kept a task small so
  that one rejected requirement could not be approved over. But rejected evidence blocks approval
  only at `gate` rigor. `contract` reports it and lets approval through
  (`hub/hub/requirement_gate.py:676-683`), and `sketch` is skipped before any requirement is read
  (`_enforced_requirements`, `:344-364`; the early return, `:642-643`). Every document on record is
  `sketch`. So the FR-11 incident (a task approved over a requirement whose evidence was rejected)
  can still happen everywhere.

The operator decided (2026-10-05):
- Q15: remove the ceiling. A requirement that no task serves is still refused.
- Q14: rejected evidence blocks task approval at every rigor.

## What Changes

- **The per-task requirement ceiling is removed.** A task may name any number of the document's
  requirements. A requirement served by no task still blocks proposal, unchanged.
- **A rejected requirement blocks task approval at every rigor.** A task can't be approved while
  any requirement it serves is `rejected`, meaning every piece of evidence recorded for its current
  wording was reviewed and rejected. This applies at `sketch` and `contract` as it already does at
  `gate`, with the same typed refusal and the same remedy text ("record evidence that satisfies the
  current wording"). Everything else is unchanged:
  - `sketch` does not block on unverified, not-started or stale requirements;
  - `contract` still only reports them.
- **A `sketch` approval records the policy that governed it.** It was null. Now that the
  rejected-evidence rule governs a `sketch` approval, the transition's policy digest records the
  linked requirements' states, as `contract` and `gate` already do.
- **The unaccepted-evidence refusal's "rejected evidence does not cause it" is scoped.** That
  sentence is true of the unaccepted-merge refusal and stays. It is reworded so it no longer reads
  as "rejected evidence never blocks approval".
- **The task card shows each requirement's coverage state.** Each requirement chip takes its
  state's tone: verified, awaiting review, rejected, or not yet evidenced. A card serving more than
  four requirements adds a one-line count by state, so a whole-slice task can be read at a glance.
- **Behaviour change on `:8000`.** On its next restart, a task serving a `sketch` requirement whose
  evidence was all rejected stops being approvable until new evidence is recorded. No migration.
- **Non-goals:**
  - an operator override of the rejected block;
  - blocking on unverified requirements below `gate`;
  - slice-end review;
  - running acceptance criteria;
  - changing how coverage states are computed;
  - authoring guidance on task size (C1a's guidance already says "a few tasks").

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `task-lifecycle-governance`:
  - "Approval is refused while a gated requirement is unverified": a rejected requirement refuses at
    every rigor.
  - "A transition records the policy that governed it": a `sketch` approval records its policy.
  - "Approval is refused while evidence that would merge sits unaccepted": the rejected-evidence
    sentence is scoped to that refusal.
- `spec-document-authority`: "A declared task's requirement span is capped, and the Hub enforces it"
  is removed.
- `requirement-traceability`: "A task card shows where each requirement it serves stands" is added.

## Impact

- **Hub:**
  - `spec_completeness.py`: the ceiling and its finding are removed.
  - `data/charters/spec.md:101`: the charter's "at most 3 requirements" line is reworded.
  - `requirement_gate.py` `evaluate`: a rejected check at every rigor, above the `sketch` early
    return, plus the `sketch` policy digest.
  - The tests that pin the old behaviour are rewritten:
    - `test_spec_completeness.py:133`, `:146`;
    - `test_approval_refuses_unaccepted_evidence.py:625`;
    - `test_task_integration.py:510`;
    - `test_requirement_gate.py:905`.
  - These stay green unchanged:
    - `test_requirement_gate.py:190` (contract reports unverified);
    - `:242` (sketch reports nothing);
    - `:334` (gate's rejected remedy).
- **UI:** `TaskCard.tsx` requirement chips plus `useRequirementChips`. The bundle is refreshed, and
  it reaches `:8000` on its next reload.
- **Agents:** a reviewer whose approval is refused on a rejected requirement gets the remedy. It is
  not an operator-only hold (`requirement_gate.py` `approval_held_for_operator`), so the reviewer
  sends the task back for revision as it does for any refused approval.
