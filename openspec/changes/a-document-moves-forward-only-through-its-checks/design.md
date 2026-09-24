# Design — a document moves forward only through its checks

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B5-2026-09-24.md`, section 1: APPROVE WITH
FIXES) and the operator's decision 1 on it changed this design:

- **The checks run inside `spec_lifecycle.transition()`, not at the two routes (operator decision
  1).** R1-R3 put `phase_blockers` in `set_phase` and `propose`. The existing requirement *"Approval
  is the operator's decision and no agent can express it"* (`spec-document-authority/spec.md:159-180`)
  already says a phase rule is enforced where the Hub changes the phase, because "a rule checked in
  one place only survives until a second caller of that place is added" — and F207 is that failure.
  R3's "two callers" claim holds at HEAD (`spec.py:1607`, `spec_service.py:781`; the one `.phase =`
  writer is `spec_lifecycle.py:339`), but nothing pinned it. **D3 is rewritten**: `transition()` takes
  a required `workspace` and calls `phase_blockers` itself; `PhaseError` carries the `blocking` list;
  `propose` turns that refusal into its `200` list; `set_phase` answers it as `409` and newly maps
  `SaveRefusedError` to `422`. The requirement's MODIFIED text and a new scenario say the checks hold
  whatever the caller, and test 1.9 calls `transition()` directly.
- **Recorded, no change needed:** no loop, flow or MCP tool moves a document's phase; adoption needs
  a payload (`spec_adoption.py:190-207`); `create_document` writes a stub payload
  (`spec.py:1453-1466`), so test 1.1 answers `409 document_incomplete`, not `422 no_payload`.
- **New test churn named:** `test_spec_archive.py::test_first_approved_at_is_set_once_and_survives_a_reopen`
  (`:281-320`) calls `transition()` to `proposed`/`approved` on a document with no file; it now needs a
  workspace and a complete payload (task 2.3). `test_spec_archive.py:270` only passes the new
  argument.

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
`document.explore_closed_at is None`. The sentence is `transition`'s own; extract it as one module constant both use (R2: two copies of a
refusal sentence drift).

**At `APPROVED`, `import_not_approved` is left out (R2).** It is the one completeness finding about
another document's state rather than this document's shape, and the settled contract already answers
it at approval: `task-dependencies` *"An unresolvable import is preserved and reported"*, decided for
exactly this race (the imported document reopened between propose and approve —
`archive/2026-08-21-task-dependencies/design.md:215-224`) and pinned by
`test_spec_task_dependencies.py::test_an_unresolvable_import_is_preserved_and_reported_not_raised`
(`:267-330`), which proposes a complete document, reopens its import source, approves, and asserts
**200** with the reference recorded as `document_not_approved`. Gating approval on the finding would
reverse that decision and fail that test. It is still reported at `proposed`, as today.

**R3: the exclusion is by code, and it is the right seam.** The alternatives both misfire: passing no
`approved_document_paths` at approval reports *every* import as `import_not_approved`; passing the
imports' own targets as "approved" lies to the pure function. Filtering the one code out of
`check`'s result keeps `spec_completeness` a pure function of its inputs. One consequence, stated
rather than hidden: because a `proposed` document stays writable, an import **added after the
proposal** to a document that was never approved also reaches approval unrefused, and is recorded
by `materialise` as `document_not_approved` — the same outcome, through the same code, as the race.
Every other completeness finding (a dropped task, a new criterion-less requirement, an unresolved
question added after proposing) is refused. **Nothing else reaches `approved` unchecked:**
`transition` has two callers (`spec.py:1607` `set_phase`, `spec_service.py:781` `propose`, which
only targets `proposed`) and nothing else assigns `SpecDocument.phase` (grep `\.phase =` → only
`spec_lifecycle.py:339`). Adoption registers a document *at* `approved` from its metadata
(`spec_adoption.py:235-240`, via `create_document(phase=…)`), but that path materialises no tasks
(`materialise_quietly` has one caller, `spec.py:1624`), so it is B6's registration question, not a
bypass of the gate that makes tasks.

**Who calls it (operator review).** `transition()` does, and nothing else needs to (D3). `propose`
becomes: `transition(...)`; on `PhaseError` with `code == "document_incomplete"` return
`exc.blocking` (the `200` list); any other `PhaseError` propagates as today; then `rerender_phase`.
The list is computed once, by the function that moves the phase, so no caller can reach `proposed`
or `approved` without it. `phase_blockers` stays in `spec_service` beside the payload reading it
reuses (`SaveRefusedError` is that module's); `transition()` imports it at call time, because
`spec_service` imports `spec_lifecycle` at module scope (`spec_service.py:18-28`) — the same
call-time import `transition()` already uses for `SpecRequirement`/`Task` (`spec_lifecycle.py:317`).

## D2 — `propose` answers "not yet" in one shape (F113)

`POST /documents/propose` on an incomplete document with an open exploration answers `200` with
`blocking` naming both the closure and every completeness finding. `explore_not_closed` no longer
arrives as `409` from this route. This is the behaviour change F113 names; the one test pinning the
old status (`test_spec_documents_api.py:323-335`) flips, deliberately.

The UI is unaffected: it never shows Propose with exploration open. An API client gets one branch
for "not yet".

## D3 — `transition()` runs the checks, so every caller does (F207; operator decision 1)

*Rewritten after the operator review. R1-R3 placed the call in `set_phase`, before `transition`;
the operator chose the transition itself, as the existing approval requirement already does for
the actor rule.*

`transition(session, document, *, to_phase, actor, workspace, reason="")` — `workspace:
ProjectWorkspace` is a **required** keyword. A caller that has no workspace cannot move a document
at all, rather than moving it unchecked; a default of `None` would reopen the second-caller hole this
exists to close. After the existing phase-map, actor and archive checks (so every
`unknown_phase`, `phase_unchanged`, `illegal_transition`, `approval_is_the_operators` and
`archive_*` answer is unchanged, and precedes any file read), and **in place of** today's standalone
`explore_not_closed` check (`spec_lifecycle.py:332-336`):

```python
if to_phase in (PROPOSED, APPROVED):
    from . import spec_service  # call-time: spec_service imports this module
    blocking = await spec_service.phase_blockers(session, workspace, document, to_phase)
    if blocking:
        raise PhaseError(
            f"this document cannot move to {to_phase} yet: " + ", ".join(b["code"] for b in blocking),
            code="document_incomplete",
            blocking=blocking,
        )
```

`PhaseError.__init__` gains `blocking: Optional[List[Dict[str, Any]]] = None`, stored as a list
(`[]` for every other refusal). The open exploration is the first entry of that list (D1), so the
explore refusal is not lost, only folded into the one answer: the phase route on a complete document
with exploration open answers `409 document_incomplete` with `blocking == [explore_not_closed]`
instead of `409 explore_not_closed`. Nothing reads that code from the phase route (grep:
`explore_not_closed` appears only in `spec_lifecycle.py:335` and the propose test
`test_spec_documents_api.py:335`, which D2 flips).

**The routes.** `set_phase` (`spec.py:1586-1635`) passes `workspace=workspace` (it already has one,
`:1604`) and its `PhaseError` handler adds `"blocking": exc.blocking` to the detail when non-empty.
It gains an `except spec_service.SaveRefusedError` → `422 {message, code}`, the mapping
`propose_document` already uses (`spec.py:1565-1569`); today the phase route never meets that
exception, so without the clause a payload-less or corrupt document would answer a bare 500.
`propose_document` is unchanged: `propose` now returns the list from the refusal (D1).

**Ordering still matters.** `test_spec_capability_kind.py:80` walks a `current` document through
every target expecting `illegal_transition`; the checks sit after the phase map, so a move that is
illegal whatever the content is still answered as illegal, and an agent asking to approve is still
told approval is the operator's before any file is read.

**Why the phase route answers 409 while `propose` answers 200.** Each route keeps one shape for
"not yet": `propose` has always reported blockers with `200` and the UI reads that body; the phase
route has always refused with `409` + `{code, message}` and its callers read that. Changing either
route's success/failure status for this would break the clients each already has.

**Why check at approval too.** A `proposed` document is still writable (`spec_service.py:165-169`
refuses only `approved`), and adoption registers documents at whatever phase their metadata states
(`spec_adoption.PHASES`). Neither path runs `propose`. Approval is where the payload becomes tasks
(`spec_tasks.materialise_quietly`, `spec.py:1618-1624`), so it is the last point where completeness
is a gate rather than a report.

**What the route returns when a called function raises.** `transition` → `phase_blockers` →
`SaveRefusedError` → 422 with `{message, code}` on both routes (the phase route's new clause above).
Nothing is written before it runs: the refusal is raised before `document.phase` is assigned
(`spec_lifecycle.py:339`). `transition` → `PhaseError` → 409 as today, now with `blocking` when the
code is `document_incomplete`. `materialise_quietly` and `rerender_phase` are unchanged. A
`read_document` `OSError` inside `phase_blockers` is not new: `propose` reads the same file the same
way today.

## D4 — the app shows an approval refusal

`SpecPhaseBar`'s Approve calls `setPhase.mutate({path, to: 'approved'})` with no `onError`
(`SpecPhaseBar.tsx:136-145`). Give it one that parses `detail.blocking` (the same `JSON.parse(raw)`
pattern `onRigor` uses, `:62-90`) into the existing `blocking` list, falling back to
`readableApiError`. `onPropose` (`:39-45`) also gains a `catch` for the 422s, which today reject
unhandled.

## Open questions

0. **(R2) Should approval also refuse an import whose document was reopened after the proposal?**
   Recommended **no** (as written in D1): the task-dependencies contract preserves and reports it, and
   materialisation records the dangling reference. Answering yes flips
   `test_an_unresolvable_import_is_preserved_and_reported_not_raised` and modifies the
   `task-dependencies` requirement *"An imported entry … SHALL be preserved and reported"* in this
   change's deltas.

1. **Does the approval check apply to documents approved before this ships?** No: it runs only on
   the transition. An already-approved document is not re-checked. Recommended as written.
2. **Adoption at `proposed`** — see proposal *Out of scope*; B6.

## Round log

- **R1, 2026-09-24.** Re-verified F207 and F113 against `404c7d5`; found the approval-time hole
  (proposed documents stay writable; adoption places documents at `proposed`); wrote D1-D4.
- **R2, 2026-09-24.** Re-derived every route and function claim; all hold. One disagreement: D3's
  "same checks at approval" would refuse `import_not_approved`, reversing the settled
  task-dependencies race answer and failing
  `test_spec_task_dependencies.py:267-330` — D1 now leaves that finding out at `APPROVED`. The only
  helpers that walk `phase` to `proposed`/`approved` are incomplete by the checks — none states
  `scope.non_goals` and four carry no criteria — in `test_spec_declared_tasks.py:87`,
  `test_spec_task_dependencies.py:67,302`, `test_task_spec_document_context.py:152`,
  `test_spec_criteria_reach_the_task.py:207`; task 2.3 completes them. No agent-plane route reaches `proposed` or `approved` (`transition` has two callers,
  `spec.py:1607` and `spec_service.py:781`, both operator-credentialed). F205 is already fixed
  (`SpecPhaseBar.tsx:146-160`), so the out-of-scope line about it is removed.
- **R3, 2026-09-24.** Re-derived from the code, not from R2's notes. Every route/function claim holds
  (`propose` `:747-786`, `set_phase` `:1585-1635`, `check` `:106-260`). R2's seam for
  `import_not_approved` confirmed as the right one (filter the code, keep `check` pure) and its one
  side effect stated in D1 (a post-proposal import to a never-approved document also passes, and is
  recorded as `document_not_approved`). Confirmed nothing else reaches `approved` unchecked: two
  `transition` callers, one `.phase =` writer, and adoption-at-`approved` materialises nothing. No
  test changed.
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B5-2026-09-24.md` §1, operator
  decision 1). The checks moved from the two routes into `spec_lifecycle.transition()` (D3
  rewritten; D1's caller paragraph added): required `workspace` argument, `PhaseError.blocking`,
  `propose` reads the refusal, `set_phase` maps `SaveRefusedError` to 422. Re-verified at HEAD
  `d0da83d`: `transition` `:270`, the explore refusal `:332-336`, the one `.phase =` writer `:339`,
  the call-time import precedent `:317`; `set_phase` `spec.py:1586`, its `transition` call `:1607`;
  `propose` `spec_service.py:747`, its `transition` call `:781`. Test 1.9 (a direct `transition()`
  call) added; 1.7 now also pins the phase route's new 422 clause; `test_spec_archive.py`'s two
  direct callers added to task 2.3.
