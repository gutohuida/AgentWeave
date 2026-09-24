# Proposal — drift is scanned and answered on the document

**Round 1, 2026-09-24** (bundle B6, slice S5b, part 2 of 2). Findings: **F129 (B)** and **F132
(C)**, plus **F430 (B)** (a candidate answered twice) and, by the operator's review of 2026-09-24
(`spec-queue/tracks/reviews/B6-2026-09-24.md` §2), **F436 (B)** (any answer silences the change for
good). F216 (the drift row names nothing its reader has seen) was fixed in Round 4c (`a7b2df1`,
`spec.py:1000-1058` now carries `requirement: {identifier, document}` and `evidence: {summary,
locator, actor, actor_kind}`); this change is the surface that reads those fields. **Depends on
`drift-watches-the-files-its-evidence-is-about`**, which must ship first: this change makes drift
reachable, and reachable drift over whole-tree footprints raises a candidate for every piece of
evidence on a branch at every commit (measured in that change's design). **Nothing here is
implemented yet.**

## Why

Drift works and nobody can reach it. `POST /spec/drift/detect` is the only writer of a
`RequirementDrift` row; `POST /spec/drift/{id}/resolve` is the only way one closes. Neither appears
in `hub/ui/src` (re-verified on `404c7d5`: `grep -rn "spec/drift" hub/ui/src` → nothing), and
neither has an agent route or MCP tool (`agent_actions.py`, `mcp_server.py`: no drift). Meanwhile:

- the coverage bar ships a **Drifting** bucket whose sentence is an instruction —
  *"Someone needs to say which one was wrong"* (`SpecCoverageBar.tsx:12-14`) — with nothing to press
  (F129);
- the approval gate's remedy for a drifting `gate` requirement is *"resolve the drift candidate"*
  (`requirement_gate.py:60-62`), an action no surface offers. `detect_drift` skips evidence that
  already has an open candidate (`requirement_evidence.py:1131`), so re-scanning is no escape: one
  detect call from anywhere makes a `gate` requirement un-approvable through the app (F132). The
  trap has not sprung only because detect is unreachable too. F132 records that *"whoever builds a
  drift caller owns raising this finding's severity in the same change"*; this change ships detect
  and resolve together, which is what F132 asks for, so the trap closes instead.

## What Changes

- **A drift strip on the document** (`SpecDocumentPanel`), beneath the coverage bar: the document's
  open candidates, each naming the requirement (`FR-n`), the files that moved (`was` → `now`), the
  evidence that was verified (summary and author), and when; three answers per candidate; a
  **Scan for drift** action; and a line naming how much accepted evidence here is not watched, and
  why (from the first change's `unwatched`).
- **`GET /spec/drift` takes `document` and `state`** query filters, so the strip asks for exactly
  what it shows. The order stays `created_at` ascending.
- **A candidate is answered once.** `resolve` on a candidate that is no longer open is refused
  **409 `drift_not_open`**, naming how and by whom it was answered. Today a second answer silently
  overwrites the first (`resolve_drift`, `requirement_evidence.py:1190-1222`, has no state check).
- **"Code corrected" does not silence the change it says was undone (F436).** That answer stores no
  resolution fingerprint, so if the change is still there, or comes back, the next scan asks again.
  *Spec updated* and *No change* keep their fingerprint. This is a MODIFIED delta on
  *"A changed implementation raises a candidate, never an edit"*.
- **The drift list has a stable order.** `GET /spec/drift` orders by `created_at, id`, so candidates
  from one scan do not tie, and a backend test pins the order.
- **Scanning and answering tell every open screen.** `detect` and `resolve` broadcast
  `spec_updated`; the UI invalidates drift and coverage on it. Today neither broadcasts, so a second
  tab keeps showing *Drifting* after the question is answered.
- **The gate's remedy names who answers it and where**: *"… the operator answers the drift
  candidate on the document, saying whether the specification or the implementation was wrong; an
  agent cannot answer it"*, in the shape `ACCEPT_OR_GRANT` already uses (`requirement_gate.py:77-80`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `requirement-traceability` — adds *"Drift is raised and answered where the operator reads the
  requirement"*; modifies *"A changed implementation raises a candidate, never an edit"* (an
  *implementation corrected* resolution records no fingerprint).

## Impact

- `hub/hub/api/v1/spec.py` — `list_drift` (filters; `created_at, id` order), `detect_drift` and `resolve_drift` routes
  (broadcast; 409 mapping).
- `hub/hub/requirement_evidence.py` — `resolve_drift` refuses a non-open candidate, and stores no
  fingerprint for `implementation_corrected`.
- `hub/hub/requirement_gate.py` — `REMEDY[DRIFTING]`.
- `hub/ui/src/api/spec.ts` — `useSpecDrift`, `useDetectDrift`, `useResolveDrift`; `useSpecEvents`
  invalidates `specDrift`.
- `hub/ui/src/components/spec/SpecDriftPanel.tsx` (new), mounted in `SpecDocumentPanel.tsx`;
  `SpecCoverageBar.tsx`'s *Drifting* sentence points at it (one string).
- UI bundle refresh (`scripts/refresh_ui_bundle.py`), committed with the source.

Cross-bundle: **B5** (F215, evidence decision + coverage bar) also edits `SpecCoverageBar.tsx`. This
change touches one string there; whichever lands second rebases that line.

**Still does not ship without `drift-watches-the-files-its-evidence-is-about`** (operator, 2026-09-24,
which set that change back to REVISING). That change is also to MODIFY *"A changed implementation
raises a candidate, never an edit"*; whichever archives second restates it over the first (task 0.4).
