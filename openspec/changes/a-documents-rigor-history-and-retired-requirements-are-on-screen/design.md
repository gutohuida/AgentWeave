# Design — a document's rigor history and retired requirements are on screen

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B6-2026-09-24.md` §4) approved this change;
the operator approved it with the review's fixes applied ("What the operator decided").

- **No SHALL is contradicted.** *"Demotion is always available"* still holds, with a reason
  required in the app only (D2).
- **LOW, applied.** The rigor mutation also invalidates `specRigorHistory` on success (D4, test
  1.10). Today `useSetSpecRigor` goes through `useSpecMutation`, whose `onSuccess` invalidates only
  `specDocuments` and `specs` (`api/spec.ts:244-256`). So the pressing tab's history would wait for
  the SSE round-trip.
- The change closes **F211** and **F429** (the app records every rigor change with an empty reason,
  D2).

**Built on the recommended answer to this change's one product question: a demotion made in the app
requires a reason** (D2). If the operator prefers the reason optional everywhere, D2 keeps the
reason field and drops the empty-reason block; the history still shows *"no reason given"*.

Also built on a **scope recommendation for F211's second route**: `GET /spec/requirements/{identifier}`
gets a caller for retired requirements only (D3). For an active requirement its tasks are already
linked from the coverage row and its evidence is bundle B5's surface; a second, parallel evidence
list here would be two views of one thing that can disagree. If the operator wants a full
requirement drawer instead, it belongs after B5's change, reusing B5's `EvidencePieces`.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

On `404c7d5`:

| Route | Returns | Order |
|---|---|---|
| `GET /documents/{path}/rigor-history` (`spec.py:536-559`) | `{events: [{id, from, to, actor_kind, actor, reason, created_at}]}`; 404 unknown document | `spec_rigor.history_for`: `created_at, id` **ascending** (`spec_rigor.py:181-187`) |
| `GET /spec/requirements?document=&include_retired=` (`:738-773`) | `{requirements: [{id, identifier, key, document_id, state, digest, anchor}]}`; 404 unknown document | `identifier` ascending (a string sort: `FR-10` before `FR-2`) |
| `GET /spec/requirements/{identifier}?document=` (`:776-819`) | `{requirement, tasks: [{id, title, status, assignee}], evidence: [evidence view], coverage}`; 404 unknown; 422 ambiguous without `document` | tasks: `Task.created_at` (`requirement_links.py`, `tasks_for_requirement`); evidence: `produced_at, id` (`requirement_evidence.py:847-853`) |
| `POST /documents/{path}/rigor` (`:426-467`) | document view; 409 `RigorRefusedError` with `blocking` | broadcasts `spec_updated {path, rigor}` |

`SpecPhaseBar.tsx:62-92` posts `{rigor, expected_digest}` on the select's `onChange` (`:184`) — no
reason. `useSetSpecRigor` already accepts `reason` (`api/spec.ts:298-309`) and sends `reason ?? ''`.

Coverage omits retired requirements (`requirement_coverage.py:224-230`); after F214
(`requirement_coverage._state`), the detail route reports a retired requirement nobody serves as
`retired`, and one with linked work or evidence as whatever those say.

## Decisions

### D1 — History, newest first, under the Enforcement control

`useSpecRigorHistory(path)` → key `['project', pid, 'specRigorHistory', path]`. A *History (n)*
toggle beside the select; open, it lists events **newest first** — the component reverses the
route's ascending order explicitly, in one place, with a comment. Each line: `sketch → gate` ·
*operator* · the reason, or *no reason given* · relative time with the absolute time as a title.
Hidden when `n == 0`.

### D2 — A rigor change is confirmed with a reason; a demotion needs one

Changing the select no longer posts. It opens an inline row: *"Change enforcement from Gate to
Sketch?"*, a reason input, **Confirm** and **Cancel**. Rigor order `sketch < contract < gate`
(`SpecRigor`'s three values); when the target is lower, **Confirm** is disabled until the reason is
non-blank, with the hint *"Say why — this is the record that makes lowering a gate legitimate."*
Confirm posts `{rigor, reason, expected_digest}`. The existing refusal display (`:202-215`) is kept.
Cancel restores the select to `document.rigor`.

### D3 — Retired requirements, and the work still pointing at them

`useSpecRequirements(path)` → `GET /spec/requirements?document=<path>` (retired included by
default), key `['project', pid, 'specRequirements', path]`. `SpecRetiredRequirements` filters
`state == 'retired'` and renders nothing when there are none. Collapsed: *"N retired requirements"*.
Expanded: one row per requirement, **sorted by the numeric part of the identifier** (the route's
string sort puts `FR-10` before `FR-2`; the component sorts on purpose and says so), naming
`FR-n` and its key. Expanding a row calls `useSpecRequirement(identifier, path)` →
`GET /spec/requirements/{identifier}?document=<path>` and lists:
- its tasks (title, status, assignee), each opening the Tasks tab filtered to it through the panel's
  existing `onOpenTasks`;
- its evidence, read-only, in the route's order (oldest first): summary, author, `review_state`, and
  the latest review's reason;
- its coverage state (`retired` when nothing serves it).

Always passing `document` means the 422 ambiguity is unreachable from this screen.

### D4 — Refresh

`useSpecEvents` invalidates `specRigorHistory`, `specRequirements` and `specRequirement` on
`spec_updated`. The rigor route broadcasts it; a save that retires a requirement broadcasts it
(`spec.py:514-516`, `agent_actions.py:1669`).

The pressing tab does not wait for that broadcast (operator review, LOW). `useSetSpecRigor` adds its
own `onSuccess` that invalidates `['project', pid, 'specRigorHistory', path]` for the path it
changed, alongside what `useSpecMutation` already invalidates. The shared helper is left as it is,
so no other mutation changes.

### D5 — What the routes answer when what they call raises

All three are reads; an unknown document or identifier is 404 before any work, and a database error
is a 500 the component shows as *"Could not load …"* with the body — not a spinner that never ends
(the F197 shape). The rigor write is unchanged.

## Goals / Non-Goals

**Goals:** the demotion audit trail is readable where demotion happens, and it records reasons;
retired requirements and the work they still carry are reachable.

**Non-Goals:** a requirement drawer for active requirements (see preamble); a server-side rule that
demotion must carry a reason (the API stays as it is — an HTTP caller is already outside the app's
path, and changing a route's contract is a separate question); showing retired requirements' old
statements (the index stores no statement, `SpecRequirement` columns).

## Risks / Trade-offs

- **B5's `a-document-moves-forward-only-through-its-checks` edits `SpecPhaseBar.tsx`** too: the
  Approve button's `onError` (`:136-145` region). This change edits `onRigor` (`:62-92`) and the
  Enforcement select (`:178-215`). Different regions; whichever lands second rebases (R2).
- **The select stops acting on change.** An operator used to one click now confirms. The confirm is
  inline and one more click, which is the cost of the record.

## Open Questions

1. **Demotion requires a reason in the app?** Recommended yes (D2).

## Round log

### Operator review fixes — 2026-09-24

Applied the review's §4 LOW at HEAD `d2b9c32`: D4's own-tab invalidation and test 1.10. Re-read
`useSpecMutation` (`api/spec.ts:244-256`) and `useSetSpecRigor` (`:298-309`).

### Round 3 — 2026-09-24 (B6 R3)

Re-derived `history_for` (ascending), `list_requirements` (string sort), `requirement_detail` → `_requirement` → `spec_index.resolve`: identifiers are unique per document (`uq_spec_requirements_document_identifier`), so passing `document` makes a retired `FR-n` resolve to one row and the 422 is unreachable, as D3 says. `onOpenTasks` is already a `SpecDocumentPanel` prop (`:42`, passed to the coverage bar at `:240`). Nothing disagreed.

### Round 2 — 2026-09-24 (B6 R2)

Re-derived: `rigor_history` (`spec.py:536-559`), `history_for` (`spec_rigor.py:181-187`,
`created_at, id` ascending), `list_requirements` (`spec.py:738-773`, `order_by(identifier)`, a string
sort; `include_retired` defaults `True`), `requirement_detail` and `_requirement` (`:776-819`,
`:376-398`: 404 unknown document or identifier, 422 ambiguous only without `document`),
`onRigor`/the select (`SpecPhaseBar.tsx:62-92`, `:178-196`), `useSetSpecRigor` (`api/spec.ts:298-309`,
sends `reason ?? ''`). All held. F169 confirmed fixed (`TaskDetailDrawer.tsx:366`, `:406`;
`taskApprovalReportAndPending.test.tsx`; ledger status fixed). Added the `SpecPhaseBar` collision
with B5.

### Round 1 — 2026-09-24 (B6 R1)

F211 re-verified by grep (`rigor-history`, `spec/requirements`: zero hits in `hub/ui/src`). Found in
R1: the app records every rigor change with an empty reason (`SpecPhaseBar.tsx:65-70`). F169
confirmed fixed (`TaskDetailDrawer.tsx`, `taskApprovalReportAndPending.test.tsx`; `58477dc`,
`f473510`).
