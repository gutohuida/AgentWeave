# Design — drift is scanned and answered on the document

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
| **Code corrected** | `implementation_corrected` | The implementation was wrong and has been put back. |
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

### D4 — A candidate is answered once

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
- **An answer silences that exact change, whatever the answer says (R3).** `resolve_drift` stores
  `resolved_fingerprint = observed` for all three resolutions (`requirement_evidence.py:1221`), and
  `detect_drift` skips a later change equal to it (`:1160-1163`). So *Code corrected* pressed before
  the code is put back, or *Spec updated* pressed for a specification that is never changed, silences
  the candidate for good. Not changed here (it is `resolve_drift`'s existing contract); the tooltips
  are worded in the past tense (*"has been put back"*, *"has been changed"*) so the button asserts a
  fact, and the drive (3.1) reverts the file before pressing *Code corrected*. Recorded as a
  candidate finding in the bundle record.
- **A project-wide scan from a document** may raise candidates elsewhere. The sentence in D2 says
  how many, and the rail's coverage bars refresh through the broadcast.

## Open Questions

1. **Does F132 need its severity raised in this change?** Recommended no: its rule was *"becomes B
   the day any caller of detect ships"* because detect-without-resolve strands a gate. This change
   ships both, so the finding closes instead. Record that on the finding at IMPL.

## Round log

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
