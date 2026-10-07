# Design — drift is scanned and answered on the document

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B6-2026-09-24.md` §2) approved this change
with fixes, and the operator decided (same file, "What the operator decided"):

- **This change carries F436** (operator: carry it). *Code corrected* stores no silencing
  fingerprint — new **D8**, a MODIFIED delta on `requirement-traceability`'s *"A changed
  implementation raises a candidate, never an edit"*, tests 1.13–1.14, and the drive (3.1) no
  longer reverts the file before pressing *Code corrected*.
- **Order ties (LOW).** `list_drift` orders by `created_at` only (`spec.py:988`), so candidates
  raised by one scan can tie. It becomes `order_by(created_at, id)`, pinned by a backend test
  (new **D9**, test 1.15). Until now only the UI fixture pinned the order.
- **It still does not ship without `drift-watches-the-files-its-evidence-is-about`**, which the
  operator set back to REVISING. The preamble below stands.
- It closes **F430** (a candidate answered twice, D4) and **F436** (D8), besides F129 and F132.
- **Collision.** The review (§1, third HIGH) also asks the first change for a MODIFIED delta on the
  same requirement. Whichever archives second restates the whole requirement over the first's text
  (task 0.4).

**Built on the recommended answer to F217's basis decision (option C) and on
`drift-watches-the-files-its-evidence-is-about` having shipped.** If the operator answers F217 with
A, this change is unchanged except that the unwatched line also names *"agent evidence is watched
only on its own branch"*. If the first change does not ship, this change must not ship either: it
would put a scan button on top of a whole-tree comparison.

Also built on a recommendation for F129's one design question — **the scan stays manual**. F129
itself argued it: a scan runs `git ls-tree` per distinct ref plus the reachability refresh, and the
route's own comment makes the operator's scan *"the moment to re-answer reachability"*
(`spec.py:963-964`). An automatic cadence changes two things at once. If the operator wants one
later, it is a scheduler change on top of this.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

On `404c7d5`:

| Route | Returns | Broadcast | What is missing |
|---|---|---|---|
| `POST /spec/drift/detect` (`spec.py:956-974`) | `{raised: [ids]}` | none | no caller |
| `GET /spec/drift` (`:977-1058`) | `{drift: [...]}`, all rows, every state, `created_at` asc | — | no filter; no caller |
| `POST /spec/drift/{id}/resolve` (`:1061-1084`) | `{id, state, resolution}`; 404 unknown; 422 `unknown_resolution` / `resolution_is_the_operators` | none | no caller; re-resolving overwrites |

`resolve_drift` (`requirement_evidence.py:1190-1222`) checks the actor and the enum, never the
state, and overwrites `resolution`, `resolved_by`, `resolved_at`, `resolved_digest` and
`resolved_fingerprint` — so a second answer from a stale tab replaces the first, and the fingerprint
that stops re-raising is the second's.

The UI: `SpecDocumentPanel.tsx:235-246` mounts `SpecPhaseBar`, `SpecCoverageBar`,
`SpecProposalsPanel`, `SpecDocumentTasksLink` in that order. `useSpecEvents` (`api/spec.ts:151-181`)
invalidates `specs`, `specDocuments`, `specCoverage`, `specProposals` and the open document on
`spec_updated`. The panel's existing amber *"spec manifest drift"* banner (`:248-283`) is a
different thing — index/manifest disagreement — and keeps its name; the new strip is titled with
the coverage bar's word, *Drifting*, so the two are not confused.

## Decisions

### D1 — The strip shows this document's open candidates, in the route's order

`useSpecDrift(path)` → `GET /spec/drift?document=<path>&state=candidate`, query key
`['project', projectId, 'specDrift', path]`. Rendered by `SpecDriftPanel` beneath the coverage bar
when any of: open candidates, `unwatched` entries for this document, or the coverage totals show
accepted evidence (`verified + drifting + stale > 0`, from the `useSpecCoverage` query the bar
already made). Otherwise it renders nothing.

Each row, oldest first (the order the route returns — the component does not re-sort):
`FR-n` · the moved paths, each `was → now` as 7-character ids (`now: null` reads *removed*) ·
*verified by* the evidence summary and its author · the candidate's age. Then three buttons:

| Button | Sends | Tooltip |
|---|---|---|
| **Spec updated** | `specification_updated` | The implementation is right; the specification has been changed to match it. |
| **Code corrected** | `implementation_corrected` | The implementation was wrong and is being put back. The next scan asks again while the change is still there. |
| **No change** | `no_change_required` | The change does not affect what this requirement says. |

A refusal from resolve is shown on the row (the `describeError` shape `SpecProposalsPanel.tsx:165-176`
uses), not swallowed.

### D2 — Scan is one button, and says what it found

**Scan for drift** posts `detect` and shows *"Scanned the project: N new — M on this document"*
(M = raised ids present in the refetched list). Scanning is project-wide because `detect_drift` is;
the sentence says so rather than implying it scanned one document. An error body is shown.

### D3 — Unwatched evidence is named with its remedy

One line under the rows: *"K pieces of accepted evidence here are not watched for drift"*,
expandable to each `FR-n`, summary and reason: `names_no_file` → *"it names no file or commit — put a file path or a commit id (not a command)
in the locator to have it watched"* (R3: the first change does not parse commands); `recorded_before_watching` → *"recorded before drift watched
files — record it again to have it watched"*; `no_footprint` (added by the first change in R2) →
*"the Hub could not read the workspace when it was recorded — record it again"*. `unwatched` gains the same `document` filter as
`drift`.

### D4 — A candidate is answered once (F430)

`resolve_drift` refuses when `candidate.state != "candidate"`:
`EvidenceRefusedError("this candidate was already answered: <resolution>, by <resolved_by>",
code="drift_not_open", http_status=409)`. The route maps `exc.http_status or 422`, the shape
`decide_evidence` already uses (`spec.py:913-917`).

### D5 — Both writes broadcast

After commit, `detect` broadcasts `spec_updated` `{"path": null, "drift": true}` **always** — the
reachability refresh it performs can move a requirement's integration answer even when nothing is
raised. `resolve` broadcasts the same after commit. `useSpecEvents` adds
`invalidateQueries(['project', projectId, 'specDrift'])`; the mutations invalidate `specDrift` and
`specCoverage` on success too, so the pressing tab does not depend on the SSE round-trip.
`useSpecDocumentRename` returns early when `d.path` is falsy (`api/spec.ts:196`), so a null path is
safe there.

### D6 — The gate remedy is performable where it is shown

`REMEDY[DRIFTING]` becomes *"the implementation changed after it was verified — the operator answers
the drift candidate on the document, saying whether the specification or the implementation was
wrong; an agent cannot answer it, so ask"*. `resolution_is_the_operators` already makes the last
clause true (`requirement_evidence.py:1202-1207`).

### D8 — *Code corrected* does not silence the change it says was undone (F436, operator review)

Today `resolve_drift` stores `resolved_fingerprint = candidate.observed` for every resolution
(`requirement_evidence.py:1221`), and `detect_drift` skips a later change equal to the latest
resolution's fingerprint (`:1161-1162`, through `_resolved_for`, `:1181-1187`). So any answer
silences that exact change for good, true or not.

The fix is one line in `resolve_drift`: `resolved_fingerprint` is `None` when
`resolution == "implementation_corrected"`, and `candidate.observed` otherwise. The column is already
nullable (`models.py:2651`). The claim of *Code corrected* is that the code went back. If it did,
`_changed` finds nothing and nothing is raised. If it did not, or the same change comes back later,
the next scan raises a new candidate, which is the truth. `resolved_digest` is still recorded.

`_resolved_for` reads only the **latest** resolution for the evidence (`order_by(resolved_at.desc())`,
`.first()`). So after *Code corrected* the scan no longer compares against any earlier fingerprint
either. That is intended: the latest answer is the operator's current word on this evidence.

The other two answers keep their fingerprint. *No change* means "this change is fine", and must stay
silent. *Spec updated* is followed by a rewording, and a reworded requirement is skipped before any
comparison (`evidence.digest != requirement.digest`, `:1136`). The residual is *Spec updated*
pressed and the specification then never changed: that change stays silenced. The operator's
decision carries only *Code corrected*, and this is recorded in Risks.

### D9 — The route's order has a tiebreak, and a backend test pins it

`list_drift` orders `RequirementDrift.created_at` only (`spec.py:988`). One scan adds all its
candidates in one transaction, so their `created_at` values can be equal, and their order is then
the database's choice. The route becomes `.order_by(RequirementDrift.created_at, RequirementDrift.id)`.
Test 1.15 pins ascending order on the route itself (the F190 rule). Before this, only the UI fixture
(1.7) stated the order, and reversing the route would fail no test.

### D7 — What each route answers when what it calls raises

- `detect`: `refresh_reachability` and `detect_drift` reach git only through `_git`/`tree_entries`,
  which answer `None`; a database error is an unhandled 500 **before** commit and before broadcast,
  so nothing half-written is announced. The strip shows the body.
- `list_drift` with an unknown `document`: 404 `no specification document at <path>`, as
  `coverage` answers (`spec.py:711-713`). An unknown `state` value: 422 naming the two values
  (`candidate`, `resolved`).
- `resolve`: 404 unknown id; 409 `drift_not_open`; 422 enum/actor — all before commit.

## Goals / Non-Goals

**Goals:** an operator can raise, read and answer drift without an HTTP client; the gate's remedy
can be performed on the surface that shows it.

**Non-Goals:** an agent-side drift surface (resolution is the operator's by design; the remedy tells
an agent to ask); automatic scanning; bulk answers; superseding a candidate when its requirement is
reworded (noted in the first change's design).

## Risks / Trade-offs

- **B5 edits the coverage bar.** This change edits one string in `SpecCoverageBar.tsx`. Whichever
  change lands second rebases it. B5's `the-coverage-bar-takes-the-evidence-decision-it-asks-for`
  also adds one `invalidateQueries` line (`specEvidence`) to `useSpecEvents`, as D5 here does
  (`specDrift`); both are additive lines in one block (R2).
- **An answer used to silence that exact change, whatever the answer said (R3; F436, now carried).**
  R3 found that `resolve_drift` stores `resolved_fingerprint = observed` for all three resolutions
  (`requirement_evidence.py:1221`), and `detect_drift` skips a later change equal to it
  (`:1161-1162`). R3 left that contract alone and made the drive revert the file first. The
  operator's review decided to carry F436 instead (D8): *Code corrected* stores no fingerprint, so a
  premature or mistaken *Code corrected* is asked again on the next scan. **Residual:** *Spec updated*
  pressed for a specification that is then never changed still silences that change, because it
  keeps its fingerprint. A real rewording makes the evidence stale and skipped anyway (`:1136`). The
  operator's decision covers *Code corrected* only; the *Spec updated* tooltip stays in the past tense
  so the button states a fact.
- **Re-raise after *Code corrected* is repeated by design.** Pressing *Code corrected* on a change
  that stays in the tree gives a new candidate on every scan until the code goes back or the
  operator answers otherwise. That is the point of D8. Scans are manual, so it does not repeat on
  its own.
- **A project-wide scan from a document** may raise candidates elsewhere. The sentence in D2 says
  how many, and the rail's coverage bars refresh through the broadcast.

## Open Questions

1. **Does F132 need its severity raised in this change?** Recommended no: its rule was *"becomes B
   the day any caller of detect ships"* because detect-without-resolve strands a gate. This change
   ships both, so the finding closes instead. Record that on the finding at IMPL.

## Round log

### Operator review fixes — 2026-09-24

Applied the review's §2 at HEAD `d2b9c32` (see the top section). Re-read `resolve_drift`
(`requirement_evidence.py:1190-1222`), `_resolved_for` (`:1181-1187`), the fingerprint skip
(`:1161-1162`), `RequirementDrift.resolved_fingerprint` (nullable, `models.py:2651`), and
`list_drift`'s `order_by` (`spec.py:988`). Added D8, D9, the MODIFIED delta, tests 1.13–1.15 and
task 0.4. Changed the drive.

### Round 3 — 2026-09-24 (B6 R3)

Re-derived `resolve_drift` (`:1190-1222`), `_resolved_for`, `open_drift_for`, the three drift routes,
the coverage route's 404 (`spec.py:711-713`) and `totals` (`requirement_coverage.py:143-161`), and
`sse_manager.broadcast` (`sse.py:71-95`, cannot raise past the commit). Held. Changed: the
`names_no_file` remedy now says *a file path or commit id, not a command* (the first change's rule
1 does not parse commands); *Spec updated*'s tooltip no longer says *"or will be"*, and the drive
reverts the file before *Code corrected*, because any answer silences that exact change (Risks).

### Round 2 — 2026-09-24 (B6 R2)

Re-derived: `detect`/`list_drift`/`resolve` routes (`spec.py:956-1084`), `resolve_drift`
(`requirement_evidence.py:1190-1222`, no state check: confirmed), `EvidenceRefusedError.http_status`
(`:77-80`), the resolve route's fixed 422 (`spec.py:1078-1081`, so task 2.1's mapping change is
needed), `REMEDY[DRIFTING]` (`requirement_gate.py:60-62`), `useSpecEvents` (`api/spec.ts:151-181`).
`spec_updated` with `path: null` is already broadcast by `spec/adopt` (`spec.py:1415`) and both
consumers guard on a falsy path (`api/spec.ts:168`, `:196`): safe. F216's fields confirmed at
`spec.py:1017-1052` (`a7b2df1`, ledger status fixed). Added the third `unwatched` reason and B5's
`useSpecEvents` line. Nothing else disagreed.

### Round 1 — 2026-09-24 (B6 R1)

F129 and F132 re-verified on `404c7d5` by grep (no `spec/drift` in `hub/ui/src`, no drift in
`agent_actions.py` or `mcp_server.py`) and by reading `requirement_gate.py:60-62` and
`requirement_evidence.py:1131`. F216 confirmed fixed at `spec.py:1000-1058` (`a7b2df1`).
