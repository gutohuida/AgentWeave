# Design — a document moves forward only through its checks

**Built on the recommended answer to F113's status-code question** (ROUNDS S6: "`propose` lists every
blocker"): the open exploration becomes an entry in `propose`'s `200` `blocking` list. If the operator
answers otherwise — keep `409 explore_not_closed` on `propose` — D2 is dropped, D1's function still
returns the closure entry, and `propose` raises it before the completeness findings exactly as today;
D3 and D4 are unaffected.

## What the code does today (HEAD `404c7d5`)

| Route | Calls | Checks |
|---|---|---|
| `POST /documents/propose` (`spec.py:1552-1582`) | `spec_service.propose` (`spec_service.py:747-786`) | payload present (`no_payload`, 422), payload valid (`payload_invalid`, 422), `spec_completeness.check` (`200` + `blocking`), then `transition` → `explore_not_closed` (409) |
| `POST /documents/phase?to=proposed` (`spec.py:1585-1635`) | `spec_lifecycle.transition` (`:1607`) | phase map, actor, `explore_closed_at` |
| `POST /documents/phase?to=approved` | same | phase map, `approval_is_the_operators` |

`transition` (`spec_lifecycle.py:270-356`) checks, in order: unknown phase, unchanged phase, phase
map, approval actor, archive actor, archive-would-orphan, explore-not-closed. The UI sends only
`approved`, `exploring` and `archived` through the phase route (`SpecPhaseBar.tsx`), and `proposed`
only through `propose`, which it offers only once exploration is closed (`:125-134`).

## D1 — `phase_blockers`

```python
async def phase_blockers(session, workspace, document, to_phase) -> List[Dict[str, Any]]:
    """Every reason `to_phase` may not be reached yet, or [] (F207, F113).

    'Not yet' only: a move the phase map forbids, or an actor who may not make it, is not a
    blocker — `transition()` refuses those, as the authority it already is.
    """
```

For `to_phase in (PROPOSED, APPROVED)`: read and validate the payload exactly as `propose` does
today (the two `SaveRefusedError` raises move here, so the phase route answers them with the same
422), then `spec_completeness.check` with `board_served` and `approved_document_paths` as today. For
`PROPOSED`, append — **first** — `{"code": "explore_not_closed", "where": "exploration", "message":
"exploration has not been closed; the operator decides when it is complete"}` when
`document.explore_closed_at is None`. The sentence is `transition`'s own; R2 decides whether to
extract it as a constant both use.

`propose` becomes: `blocking = await phase_blockers(...)`; if non-empty, return it; else
`transition(...)`; `rerender_phase`. `transition` keeps its `explore_not_closed` refusal, so the
state can never be reached by a caller that skips `phase_blockers`.

## D2 — `propose` answers "not yet" in one shape (F113)

`POST /documents/propose` on an incomplete document with an open exploration answers `200` with
`blocking` naming both the closure and every completeness finding. `explore_not_closed` no longer
arrives as `409` from this route. This is the behaviour change F113 names; the one test pinning the
old status (`test_spec_documents_api.py:323-335`) flips, deliberately.

The UI is unaffected: it never shows Propose with exploration open. An API client gets one branch
for "not yet".

## D3 — the phase route runs the same checks (F207)

In `set_phase`, **after** confirming the move is in the phase map and before `transition`:

```python
if to in (PROPOSED, APPROVED) and (document.phase, to) in spec_lifecycle.TRANSITIONS:
    blocking = await spec_service.phase_blockers(session, workspace, document, to)
    if blocking:
        raise HTTPException(409, detail={"code": "document_incomplete",
            "message": f"this document cannot move to {to} yet: " + "; ".join(...codes...),
            "blocking": blocking})
```

Ordering matters. `test_spec_capability_kind.py:80` walks a `current` document through every target
expecting `illegal_transition`; running the checks first would answer `document_incomplete` for a
move that is illegal whatever the content. Gating on the phase map keeps every existing
`illegal_transition`, `unknown_phase` and `phase_unchanged` answer.

**Why the phase route answers 409 while `propose` answers 200.** Each route keeps one shape for
"not yet": `propose` has always reported blockers with `200` and the UI reads that body; the phase
route has always refused with `409` + `{code, message}` and its callers read that. Changing either
route's success/failure status for this would break the clients each already has.

**Why check at approval too.** A `proposed` document is still writable (`spec_service.py:165-169`
refuses only `approved`), and adoption registers documents at whatever phase their metadata states
(`spec_adoption.PHASES`). Neither path runs `propose`. Approval is where the payload becomes tasks
(`spec_tasks.materialise_quietly`, `spec.py:1618-1624`), so it is the last point where completeness
is a gate rather than a report.

**What the route returns when a called function raises.** `phase_blockers` → `SaveRefusedError` →
422 with `{message, code}` (the mapping `propose_document` uses, `spec.py:1564-1568`). Nothing is
written before it runs. `transition` → `PhaseError` → 409 as today. `materialise_quietly` and
`rerender_phase` are unchanged.

## D4 — the app shows an approval refusal

`SpecPhaseBar`'s Approve calls `setPhase.mutate({path, to: 'approved'})` with no `onError`
(`SpecPhaseBar.tsx:136-145`). Give it one that parses `detail.blocking` (the same `JSON.parse(raw)`
pattern `onRigor` uses, `:62-90`) into the existing `blocking` list, falling back to
`readableApiError`. `onPropose` (`:39-45`) also gains a `catch` for the 422s, which today reject
unhandled.

## Open questions

1. **Does the approval check apply to documents approved before this ships?** No: it runs only on
   the transition. An already-approved document is not re-checked. Recommended as written.
2. **Adoption at `proposed`** — see proposal *Out of scope*; B6.

## Round log

- **R1, 2026-09-24.** Re-verified F207 and F113 against `404c7d5`; found the approval-time hole
  (proposed documents stay writable; adoption places documents at `proposed`); wrote D1-D4.
