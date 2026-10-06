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
"a task may serve several requirements; every requirement needs a task". The file seeds only
projects not yet seeded (`db/engine.py` `_seed_default_charters`, `charters_seeded`), so existing
projects keep the old line until the operator edits their charter. Nothing enforces it any more.
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
- `requirement_links[].state` is the requirement's lifecycle (`active`/`retired`,
  `api/v1/tasks.py:209`), not coverage, so the chip does not read it. `useRequirementChips` reads
  each linked document's coverage through `useSpecCoverage(path)` (`ui/src/api/spec.ts:298`), the
  query the document view uses: same cache, so the card cannot disagree with it, and it is already
  invalidated on evidence decisions and `spec_updated` (`spec.ts:287`, `:324`). No backend change.
  Each chip gets a tone class by coverage state:
  - `verified`: positive;
  - `evidence_awaiting_review`: pending;
  - `rejected`: the existing rejected tone;
  - any other state, or none (a retired requirement has no document-coverage row): neutral.
- With more than four chips, one line above them counts by state ("3 verified · 1 rejected · 4
  open"), with `data-testid="task-requirement-summary-<id>"`.
- The drawer is unchanged. It shows lifecycle state and the rejection reason, not coverage.
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
- **[A flow stalls on a refused review.]** The reviewer's `update_task` is refused with the
  remedy. Nothing routes that refusal to send-back automatically: the reviewer has to choose
  `revision_needed`, which F495 returns to the author (`task_transition_service.py:690`). The
  review briefing does not warn it either (`review_turn.verdict_evidence_sentence` speaks only of
  awaiting evidence). That gap already exists at `gate` and is filed as F497, not built here.
  Drive step (d) shows the refusal through the operator path, and a unit test covers the tool path.

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

## Review round (task 0.1, 2026-10-05 night, at `a89d093`)

Every cited `file:line` re-read; one `mode=ro` query on `:8000`.

Folded in:
- **R1 (would not fire).** D5 said the chips read `requirement_links[].state`. That field is
  `SpecRequirement.state` (`active`/`retired`, `api/v1/tasks.py:209`), and the drawer treats it
  so (`TaskDetailDrawer.tsx:721`). Built as written, no chip could ever show `verified`. D5 now
  reads `useSpecCoverage`, and the awaiting tone uses the real key `evidence_awaiting_review`
  (`requirement_coverage.py:51`). Tasks 5.1-5.2 say so.
- **R2 (overclaim).** "Refusals already route to send-back" has no code behind it: only
  `apply_transition` raises `GateUnsatisfiedError` (`task_transition_service.py:678`), and nothing
  catches it into `revision_needed`. Risks reworded. The reviewer briefing's silence on a
  rejected requirement already exists at `gate`, so it is F497 (backlog), not this change.
- **R3 (measurement).** On `:8000` the two 77-requirement documents have 48 and 33 linked tasks
  (max 3 requirements per task), not 32. Proposal corrected.
- **R4.** The refusal's list of reasons in *Approval is refused while a gated requirement is
  unverified* now includes "evidence that was reviewed and rejected".
- **R5.** The charter rewording reaches only newly seeded projects. D1 says so.

Confirmed as cited: `spec_completeness.py:39`, `:249-258`. The constant is read nowhere else
(`git grep`, tests reference only the code). `requirement_gate.py` `:344-364`, `:613`, `:628-630`,
`:642-643`, `:676-683`, `REMEDY[REJECTED]` `:53`. `requirement_coverage._state` `:184-214`.
`evaluate` has two callers, `apply_transition` and the land route (`api/v1/tasks.py:1679`), so the
land route inherits D2. `approval_held_for_operator`'s early return (`:791`) is correct for a
rejected-only refusal (not operator-only). Test anchors `:133`, `:146`, `:625`, `:510`, `:905`,
`:190`, `:242`, `:334` exist. The policy requirement's delta keeps every main-spec scenario.

Rejected: retired requirements carrying rejected evidence would also block at `sketch`. `gate`
does the same today, and no claim of this change depends on it.

## Open Questions

None.
