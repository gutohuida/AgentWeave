## Context

- **The ceiling.**
  - Defined at `spec_completeness.py:39`. The finding is at `:249-258`, code `task_too_coarse`, and
    it blocks proposal.
  - It was a size proxy: a small task meant a single rejection could not be buried under other
    approved work.
- **The gate.** `requirement_gate.evaluate` (`:613`) is the only approval check, called from
  `task_transition_service.apply_transition`.
  - Its repository checks and its liveness check run first, above the early return
    `if not enforced: return refusal, ""` (`:642-643`).
  - `_enforced_requirements` (`:344-364`) drops `sketch` documents. So a task whose documents are
    all `sketch` returns there, with no requirement read and a null policy digest.
  - For `contract` and `gate`, each linked requirement's coverage state is read from
    `requirement_coverage` (the same computation the document view uses).
    - `gate`: a state other than `verified` goes to `blocking`.
    - `contract`: it goes to `reported` and never refuses (`:676-683`).
- **What `rejected` means.** `requirement_coverage._state` (`:184-214`) returns `REJECTED` only
  when every piece of evidence at the requirement's current digest is rejected. A pending or
  accepted row wins first. So recording new evidence moves the state to `awaiting_review`, which is
  the author's own way out.
- **Holds.** `approval_held_for_operator` returns an operator-only hold only for remedies no agent
  can take (`_operator_only_remedy`). A rejected requirement's remedy, "record evidence", belongs
  to the author. A flow's reviewer is therefore still staffed: its approval is refused with the
  remedy, and it sends the task back.

## Goals / Non-Goals

**Goals:**
- A slice can be a few tasks, each serving several requirements.
- No task is approved over a rejected requirement, at any rigor.
- The card shows which of a task's requirements stand where.

**Non-Goals:**
- An operator override.
- Blocking on unverified requirements below `gate`.
- Slice-end review.
- Running criteria.
- Changing coverage states.

## Decisions

**D1. Remove the ceiling outright.** The constant, the `task_too_coarse` finding and its tests are
deleted. Nothing else reads the constant (grep: `spec_completeness.py` only). The seeded charter's
line "a single task may name at most 3 requirements" (`data/charters/spec.md:101`) is reworded to
"a task may serve several requirements; every requirement needs a task".
- *Rejected: raise it to about 6.* The operator chose removal (Q15). Any number would need its own
  measurement, and C1a's guidance already steers size.
- *Kept:* `requirement_without_task` (a requirement served by no task), unchanged.

**D2. A rejected check at every rigor, inside `evaluate`, above the `sketch` early return.**
- A new step reads the coverage state of **every** requirement the task links (all rigors) through
  the same `requirement_coverage` call, grouped by document as the loop below already does.
- Each `REJECTED` one goes to `refusal.blocking`, with `REMEDY[REJECTED]`, the same entry shape
  `gate` produces today.
- The existing loop then runs for `contract` and `gate` as before. It must not add a second
  `blocking` entry for a requirement already blocked as rejected under `gate`, and must not add a
  `reported` copy of one under `contract`. The step's identifiers are passed in to skip.
- *Why above the early return:* the same reason the repository checks sit there (`:628-630`): an
  early return that fires on every default project makes any check after it dead.
- *Why `blocking` and not a new list:* the refusal is the same claim `gate` already makes about a
  rejected requirement ("unproven, and here is how to prove it"), with the same remedy. A second
  list would need its own rendering on every surface: the drawer, the tool error, the hold.
- *Rejected: a separate check in `apply_transition`.* The spec requires one enforcement point,
  ("SHALL NOT exist as a second enforcement point").
- *Cost:* a `sketch` approval now reads coverage for the task's documents. That is one coverage
  call per linked document, made only when the task links requirements. A task linking none still
  returns before any read.

**D3. A `sketch` approval records its policy.** When the task links requirements, the policy digest
covers every linked requirement (identifier, state, integration, rigor), `sketch` included. A task
linking none keeps a null digest.
- *Why:* "A transition records the policy that governed it". The rejected rule now governs `sketch`
  approvals, and a null digest would claim nothing did.
- `test_requirement_gate.py:905` (`test_an_ungated_approval_records_no_policy`) is rewritten.
  - Null stays the answer for a task linking nothing.
  - A `sketch` task linking requirements records a digest.
- *Rejected: keep null for `sketch`.* The handoff noted this need, and the requirement settles it.

**D4. Scope the unaccepted-evidence sentence.** "Rejected evidence SHALL NOT cause the refusal" in
"Approval is refused while evidence that would merge sits unaccepted" stays true of that refusal:
rejected evidence is never unaccepted evidence awaiting judgement. It gains a clause pointing at
the rejected-requirement refusal, so the two do not read as contradictory.
- The two tests pinning "rejected evidence approves" are rewritten:
  - `test_approval_refuses_unaccepted_evidence.py:625`: approval is now refused, by the rejected
    rule and not by the unaccepted rule;
  - `test_task_integration.py:510`: the rejected evidence's requirement gets a second, accepted
    piece of evidence that names no commit, so the task is approvable and the assertion "merges
    nothing from rejected evidence" still holds.

**D5. The card shows coverage per requirement.**
- `useRequirementChips` already reads `requirement_links` (each has `state` and
  `has_rejected_evidence`). Each chip gets a tone class by state:
  - `verified`: positive;
  - `awaiting_review`: pending;
  - `rejected`: the existing rejected tone;
  - any other state: neutral.
- With more than four chips, one line above them counts by state ("3 verified · 1 rejected · 4
  open"), with `data-testid="task-requirement-summary-<id>"`.
- The drawer is unchanged: it already lists every link with its state.
- *Rejected: collapsing the chips.* Hiding requirements on a whole-slice task is what the card must
  not do.

## Risks / Trade-offs

- **[`:8000`'s existing `sketch` tasks stop being approvable when their evidence was all
  rejected.]** That is the intent (Q14), and the remedy is in the refusal. The proposal states it.
  The read-only count of such tasks on `:8000` is taken before the build (task 1.1) and recorded
  there.
- **[A requirement shared by two tasks.]** One task's rejected evidence blocks the other task too,
  because coverage is per requirement. That is correct: the requirement is not met. The remedy
  ("record evidence…") is open to either task's author.
- **[A flow stalls on a refused review.]** The reviewer is refused with the remedy, and refusals
  already route to send-back (F495 made that return the task to its author). Drive step (d)
  shows the refusal through the operator path, and a unit test covers the tool path.

## Migration Plan

None. No schema change. Rollback is a revert.

## Acceptance drive (written and failing before the build)

Drive D, `testbed/drive-slices/drive_d.py` on `:8010`, stub provider, no spend:

| Step | What happens | Expected |
|---|---|---|
| (a) | `planner` creates and submits a `sketch` change document with **one task serving five requirements**; the operator proposes it | Proposed. **Before the build: refused, `task_too_coarse`.** |
| (b) | The operator approves it | One task is created |
| (c) | `planner` records evidence for requirement `r1` on that task, and the operator rejects it | The evidence is rejected |
| (d) | The operator moves the task to `under_review` and approves it | **409, naming `r1`, `rejected`, and the remedy.** The task stays `under_review` |
| (e) | `planner` records new evidence for `r1`, the operator accepts it, and the operator approves again | 200, `approved`, and a non-null policy digest |

## Open Questions

None.
