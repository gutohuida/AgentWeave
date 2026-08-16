# Design — spec surface legibility

## D1. Order the phases so each later fix stands on a corrected foundation

F2 (theme wiring) before F1 (colour): recolouring modal chips and phase chips on top of the wrong
background would make the mismatch more visible, not less, and any screenshot taken for the human-only
review would need retaking once F2 landed. F3/F6 (coverage + ticket ceiling, backend-only) do not
depend on either and can run in parallel with F1/F2 in review terms, but are sequenced after them in
`tasks.md` only because they are independently smaller and de-risk the round. F4 before F5: the
drawer's whole point is room to show what the card cannot — building it before F4 exists would mean
building it once now and touching it again to add requirement chips.

## D2. F2 — which name wins, and how the two are pinned together

**Decision: rename `spec_render.py`'s neutral variables to match `SpecFrame.tsx`'s existing override
names, not the reverse.** Renaming the *override* would mean editing `SpecFrame.tsx`, which is also
the mechanism the retired skill-authored documents used and is exercised by
`hubVisualLanguage.test.ts` today; renaming the *renderer* touches one file that already has no other
consumer (`spec_render.py`'s `_STYLE` constant is private to this module — confirmed by
`grep -rn "_STYLE" hub/hub/` returning only its own definition and use).

Mapping (documented once, in `spec_render.py`'s docstring, since nothing else states it):

| today (`spec_render.py`) | becomes | reasoning |
|---|---|---|
| `--aw-bg` | `--bg` | direct match, same role |
| `--aw-fg` | `--fg` | direct match |
| `--aw-muted` | `--muted` | direct match |
| `--aw-rule` | `--border` | same role — the neutral hairline colour |
| `--aw-chip-bg` | `--surface-2` | a chip is a lifted block, which is what `--surface-2` means in the Hub's own ramp |
| `--aw-code-bg` | `--surface` | code/pre is a lifted block one step lighter than a chip |
| `--aw-accent` | **unchanged** | `SpecFrame.tsx`'s own comment: "the document's accent, warn, done and danger hues are left alone... not the Hub's to recolour." Renaming it would contradict the boundary the override already states. |

**Pinning test:** a new assertion (`hub/ui/src/__tests__/hubVisualLanguage.test.ts`, alongside the
existing `index.css`↔`HUB_NEUTRALS` pin, or a Python-side test reading `spec_render.py`'s `_STYLE`
string) that every key `HUB_NEUTRALS[mode]` supplies (`bg`, `surface`, `surface2`, `border`, `fg`,
`muted`) appears as a custom property name inside `_STYLE`. This is what makes F2 more than a
one-time fix — a future rename on either side fails a test instead of silently reopening the navy
background.

**Verification beyond the pin:** if `scripts/uishot.py` (Q4a) is available by the time this ships,
capture the document in both themes and assert (via Playwright's `page.evaluate`) that the frame's
computed `background-color` equals `HUB_NEUTRALS[mode].bg`, converted to the same colour space. This
is the concrete instance of Q4a's own note: "finding 2 ... becomes MEASURABLE ... via
`page.evaluate` + `getComputedStyle`." If the harness is unavailable, the pinning test alone still
proves the wiring is connected; it does not independently prove the *rendered pixel* matches, which
is why both are listed and the second is marked agent-verifiable-if-available rather than required.

## D3. F1 — what gets coloured, and what does not

Three targets, chosen because each is a place the operator named ("what you needed to look at popped
with colour") and each already has a `class` to hang a rule on:

1. **`.aw-modal` (MUST/SHOULD/MAY).** `MUST` takes `--aw-accent` (the strongest existing hue,
   already used for links — reused rather than inventing a fourth colour for "most important").
   `SHOULD` takes a new `--aw-warn` (amber-family, defined alongside `--aw-accent` as the document's
   own literal, per D2's boundary — not Hub-overridden). `MAY` stays `--aw-fg` at normal weight — the
   absence of colour is itself informative once the other two carry it.
2. **`.aw-requirement`'s left border**, currently a flat `--border`. Takes the same modal-derived
   colour as its own `.aw-modal` span, so a requirement's importance is visible without reading the
   word — this is the literal "popped with colour" behaviour the operator described from the older
   documents.
3. **The phase/rigor chips in the document header**, currently both `--surface-2` background. `phase`
   keeps neutral (it is a workflow state, not a judgement); `rigor` (`sketch`/`gate`/… — the values
   `RIGOR_META` already names) takes a tone from a small fixed mapping the renderer already has the
   value to key off (no new data needed).

**Deliberately not done:** colouring the acceptance table by requirement, or colouring based on live
coverage state. The latter would require the renderer to know coverage at render time, which it does
not today (`render_document()` receives only the payload, not a `CoverageReport`) — threading that
through is a materially larger change (coverage changes on every evidence decision, so the document
would need re-rendering on events it does not currently listen for) and was not what the operator
asked for. Recorded as a future option, not built here.

## D4. F3 — where `rejected` sits in the precedence, and what integration says about it

Inserted between `verified` and `in_progress`:

```
drifting > stale > evidence_awaiting_review > verified > rejected > in_progress > not_started > unserved
```

Above `in_progress`/`not_started`/`unserved` because a rejected claim is *more* informative than "no
attempt yet" — it is a fact about the requirement, not the absence of one. Below `verified` because
the existing logic already checks `accepted` first and short-circuits to `VERIFIED`: if *any*
current-digest evidence was accepted, the requirement is verified regardless of an earlier rejected
attempt on the same digest, which is correct — a second, successful try should read as success, not
be shadowed by the first, failed one. `rejected` only fires when every current-digest evidence row is
rejected and none is awaiting or accepted.

**Integration for a `rejected` requirement stays `not_applicable`** — no code change to
`_integration()` needed. Before this fix, `not_applicable` next to `in_progress` read as "actively
being worked on, not merged yet." After it, `not_applicable` next to the new, explicit `rejected`
reads correctly: nothing was integrated because nothing was accepted. The ambiguity was entirely in
`state`, not `integration` — confirmed by re-reading the operator's complaint, which named the
`in_progress` label, not the `not_applicable` one, as the misleading half.

**Reused pattern, not a new query shape.** `hub/hub/api/v1/tasks.py`'s `_attach_requirements()`
already computes `has_rejected_evidence` per requirement, scoped to the requirement's *current*
digest, for exactly the reason stated in its own comment ("a requirement whose only evidence was
rejected reads identically to one nobody has ever attempted"). `requirement_coverage.py`'s `_state()`
already has `evidence` filtered to `current = [item for item in evidence if item.digest == digest]`
in scope; the new check is `rejected = [item for item in current if item.review_state == REJECTED]`,
using the constant already imported from `requirement_evidence`. No new join, no new table read.

## D5. F3 — is this a rename or a new state, for existing callers

**A new state, not a relabelling of `in_progress`.** `PRECEDENCE`, `CoverageReport.totals`, and every
test enumerating the seven states change shape (eight now). This is a deliberate breaking change to
the coverage contract, scoped by `requirement_coverage.py`'s own docstring, which already says two
implementations disagreeing would be invisible until compared — the fix is inside the one function
everything calls, so nothing downstream can disagree with it by construction. `B4`'s gate (mentioned
in the module docstring as a caller) is checked in `tasks.md` phase 3 to confirm it does not key off
`in_progress` in a way this narrows incorrectly.

## D6. F6 — the ceiling number, derived rather than picked

From the findings document's own table: approved tickets carried 6, 2, and 1 requirements; an earlier,
rejected batch carried 5 and 4. The single-requirement ticket (`task-553c2c37`) is the shape the
operator's complaint implies is right — one demonstrable thing, one ticket. Two related requirements
in one ticket (`task-0d3c8cb5`, approved, never named as a problem) is evidence that 2 is an accepted
normal case, not a violation. **Ceiling: a task may name at most 3 requirements.** Set at 3 rather than
2 because the evidence contains no complaint about a 2-requirement ticket and no example of an
uncomplained-about 3-requirement one either — 3 is the smallest number that does not retroactively
flag the one ticket the operator did not name as a problem, while still refusing the 4-, 5- and
6-requirement tickets that were named. A named module-level constant
(`MAX_REQUIREMENTS_PER_TASK = 3`), not a magic number in the check, so a future ruling can change it
in one place.

**Where it is enforced:** `spec_completeness.check()`, alongside `task_without_requirement` — same
function, same blocking point (`propose()` already refuses on any finding this function returns), so
no new enforcement mechanism is introduced. **Where it is prevented:** the Spec Author charter's "How
to slice the work" section gets a new bullet stating the number, so the refusal is the exception, not
the normal authoring loop — an agent that never reads the charter still gets refused at `propose()`
either way.

## D7. F4 — which direction(s), and where a click lands

**Task → requirement (built in full).** A chip per `requirement_ids` entry on `TaskCard.tsx`'s header
row (not inside the expansion — the operator's complaint was that the connection is invisible even
before expanding). Clicking switches the workspace destination to `{ tab: 'spec', document:
<resolved path> }` and, since `SpecFrame` already exposes `scrollToSection`
(`SpecFrameHandle.scrollToSection`) and `SpecDocumentPanel` already threads a `pendingFragment` from
in-frame link clicks, the same prop is given an initial value from the destination so a cross-tab
click scrolls to the anchor, not just opens the document. This needs the destination to carry a
fragment, which it does not today (`projectDestination()` only carries a document path) — `design.md`
scopes this as one added optional field (`anchor?: string | null`) on the `project`/`tab: 'spec'`
destination variant, read once on mount, the same as `pendingFragment` already is for in-frame
navigation.

Resolving a requirement's `document_id` to the *path* `projectDestination` needs: `requirement_links`
already carries `document_id`, and the Spec document list (`useSpecDocuments` or equivalent, already
used by `SpecDocumentPicker.tsx`) maps ids to paths client-side — no new endpoint.

**Requirement → task (built, coarser).** `SpecCoverageBar.tsx`'s existing `N task(s)` text (line
147-151 today) becomes a link that switches to the Tasks tab filtered to `linked_task_ids`. The board
has no id-based filter today (only the assignee filter chips) — this needs one more piece of state
(`activeTaskIds: string[] | null`) alongside `TasksBoard.tsx`'s existing `activeFilter`, not a new
filtering *mechanism*.

**Not built:** opening a specific task's drawer directly from a coverage row. Landing on the filtered
board and letting the operator open the one they want (usually one, given the new F6 ceiling) is
proportionate to what was asked; a second click is not the friction the operator complained about.

## D8. F5 — drawer vs. modal, and what it must not regress

**A right-side drawer, not a centred modal.** A centred modal covering the whole board loses the
column context ("which status is this in") that a Jira-style ticket keeps visible at the edge; a
drawer can be closed by clicking the board behind it, which a modal's own backdrop already does in
this codebase (`AgentCreateDialog.tsx`'s pattern), so no new interaction convention is introduced,
only a different geometry.

**Everything the inline expansion held moves in, unchanged in behaviour**: description, acceptance
criteria, deliverables, notes, the status-transition menu (`useAllowedTransitions`), the blocking-
reason input, the divergence-policy control. This is a location change, not a rewrite of any of
those — `tasks.md` phase 6's tests are behaviour-parity tests (every control that worked inline still
works in the drawer) precisely because a relocation is the one kind of change most likely to silently
drop a handler.

**Card itself stays exactly as collapsed today** — title, status, assignee, F4's new requirement
chips, an explicit "open" affordance. The card was never the operator's complaint; only its expanded
state was.

**Machine-checkable proxy for "does not clip"**, per Q4a's own note on this finding: inside the open
drawer, `element.scrollHeight <= element.clientHeight` for the body region, driven with a task carrying
a long description across a representative sample of viewport widths. This proves nothing about
*layout quality* — only that content is not physically cut off — which is exactly the boundary
between what this change can self-verify and what needs the operator's eyes, per `tasks.md`'s split.
