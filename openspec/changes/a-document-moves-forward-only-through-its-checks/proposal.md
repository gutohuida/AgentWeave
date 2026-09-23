# Proposal — a document moves forward only through its checks

**Round 1, 2026-09-24** (bundle B5, spec track S6). Findings: **F207 (C)** and **F113 (B)**. Both
re-verified on HEAD `404c7d5`: still open. Nothing here is implemented.

## Why

**F207 — a second door into `proposed` skips the checks.** `POST /documents/propose`
(`hub/hub/api/v1/spec.py:1552-1582`) runs `spec_service.propose` (`hub/hub/spec_service.py:747-786`),
which reads the payload, validates it, and runs `spec_completeness.check` before it lets
`spec_lifecycle.transition` move the document. `POST /documents/phase?to=proposed`
(`spec.py:1585-1635`) calls `spec_lifecycle.transition` directly (`:1607`), and `transition`
(`spec_lifecycle.py:270-356`) checks only the phase map, the actor and `explore_closed_at`. F207
measured an empty document reaching `proposed` and then `approved` in two calls. The requirement
*"Document validity is checked by the Hub"* (`spec-document-authority/spec.md:182`) says the Hub
SHALL refuse a transition to `proposed` on those checks — on one route it does not.

**The same hole at approval, found in R1.** `proposed → approved` runs no completeness check on any
route. A document proposed complete can become incomplete while it is `proposed`: `save_document`
refuses writes only to an **approved** document (`spec_service.py:165-169`). And a document can be
adopted **at** `proposed` from its own file metadata (`spec_adoption.PHASES`, `:44-50`) without the
checks ever running. So "it was proposed" does not mean "it is complete" at the moment of approval,
and approval is what materialises tasks from the payload (`spec.py:1618-1624`).

**F113 — `propose` promises every blocker and omits one.** Its docstring says *"report every check
that refuses it"*. An incomplete document with an open exploration is answered `200` with the
completeness findings; the open exploration arrives separately as
`409 explore_not_closed` (`spec_lifecycle.py:332-336`), and only once the others are fixed. F113
measured the round trip it causes.

## What Changes

- **One function says what blocks a move** (design D1). `spec_service.phase_blockers(session,
  workspace, document, to_phase)` returns the completeness findings for `proposed` and `approved`,
  plus `explore_not_closed` for `proposed` when exploration is open, in one list of
  `{code, where, message}`.
- **`propose` lists the closure with the rest** (D2, F113). `POST /documents/propose` answers `200`
  with `blocking` that includes `explore_not_closed` where it applies. `transition()` keeps its
  refusal as the authority behind the list. The route's `409` remains for moves that are not "not
  yet" (`illegal_transition`, `phase_unchanged`).
- **The phase route runs the same checks** (D3, F207). `POST /documents/phase` with `to=proposed` or
  `to=approved` refuses with `409 {"code": "document_incomplete", "message": …, "blocking": [...]}`
  when `phase_blockers` is non-empty. Reopen and archive are unchanged.
- **The app shows an approval refusal** (D4). The Approve button in `SpecPhaseBar.tsx:136-145` calls
  `setPhase.mutate` with no error handler, so today any refusal vanishes. It renders the `blocking`
  list the same way a blocked proposal does.

## Out of scope

- Adoption placing a document at `proposed` or `approved` from its metadata (a third door). D3 makes
  an adopted-at-`proposed` incomplete document unapprovable, which closes its consequence; whether
  adoption itself should refuse is B6's corpus-writes slice (F206/F205's neighbourhood).
- F205's dead `proposed → archived` edge — B6.

## Impact

- `hub/hub/spec_service.py`, `hub/hub/api/v1/spec.py` (`propose_document`, `set_phase`)
- `hub/ui/src/components/spec/SpecPhaseBar.tsx`; the committed bundle
- `hub/tests/test_spec_documents_api.py:323-335` flips from `409` to `200 + blocking` on purpose
- Seven test helpers step through `/documents/phase?to=proposed` then `approved`
  (`test_spec_board_task_convergence.py`, `test_spec_capability_kind.py`,
  `test_spec_criteria_reach_the_task.py:207`, `test_spec_declared_tasks.py:87`,
  `test_spec_task_dependencies.py:67`, `test_task_spec_document_context.py:152`, and
  `test_spec_documents_api.py`); each passes after only if its fixture document is complete
- Drive harnesses under `scripts/drive/` that use the phase route (ten files) may need complete
  fixtures; they are not CI
- `openspec/specs/spec-document-authority` (MODIFIED: *Document validity is checked by the Hub, not
  asserted by its author*)
