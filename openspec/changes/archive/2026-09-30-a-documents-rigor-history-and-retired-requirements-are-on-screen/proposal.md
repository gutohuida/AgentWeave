# Proposal — a document's rigor history and retired requirements are on screen

**Round 1, 2026-09-24** (bundle B6, slice S5d). Findings: **F211 (C)**, and **F429 (C)** (the app records every rigor change with an empty reason, found in R1 and filed at the 2026-09-24 daily review). The slice's other finding,
**F169**, is already fixed (`58477dc` + `f473510`, UI-1: `TaskDetailDrawer` renders the approving
response's `approval_report`, test `taskApprovalReportAndPending.test.tsx`). **Nothing here is
implemented yet.**

## Why

Three operator routes have no client (re-verified on `404c7d5`: `grep -rn "rigor-history\|spec/requirements"
hub/ui/src` → nothing):

- **`GET /documents/{path}/rigor-history`** (`spec.py:536-559`). The route and the model that write it argue
  their own legitimacy from it: *"Demotion is legitimate because this exists"* (`:542`, and
  `SpecRigorEvent`'s docstring, `models.py:2048-2053`). The audit trail that
  justifies letting the operator lower a gate is on no screen. Worse, R1 found the trail is
  **empty of reasons** for every change made in the app: the Enforcement select posts a rigor change
  the moment it changes, with no reason field (`SpecPhaseBar.tsx:62-70`, `:178-196`), so
  `SpecRigorEvent.reason` is `""` for all of them — while the spec requires each change to be
  *"recorded append-only with the actor, the reason, and the digest"*
  (`spec-document-authority/spec.md:959-962`).
- **`GET /spec/requirements`** (`spec.py:738-773`) is the only read that includes **retired**
  requirements. Coverage excludes them (`requirement_coverage(include_retired=False)` by default,
  `requirement_coverage.py:224-230`), so a retired requirement disappears from every screen — while
  its links and evidence are kept on purpose (*"A removed requirement is retired, not deleted"*,
  `spec_index.py:10`).
- **`GET /spec/requirements/{identifier}`** (`spec.py:776-819`), *"the other half of a navigation
  that only went one way"*. For an active requirement that navigation is now on screen by other
  routes: the coverage row links its tasks (`SpecCoverageBar.tsx`, `linked_task_ids`), and bundle
  B5's `the-coverage-bar-takes-the-evidence-decision-it-asks-for` lists its evidence. For a
  **retired** one nothing shows the work that still points at it, and this route is the one that can.

## What Changes

- **Rigor history under the Enforcement control** (`SpecPhaseBar`): a *History (n)* toggle listing
  each change — from → to, who, the reason, when — newest first.
- **A rigor change asks for its reason.** Changing the Enforcement select opens an inline confirm
  with a reason field; a **demotion** (to a lower rigor) cannot be confirmed with an empty reason; a
  promotion may be. The reason is sent as the route already accepts (`RigorRequest.reason`). The API
  is unchanged — only the app's own path stops recording blank reasons.
- **Retired requirements are listed on the document** (`SpecRetiredRequirements`, new, mounted after
  the coverage bar): *"N retired requirements"*, collapsed; each row names `FR-n` and its key, and
  expands to the tasks and evidence that still point at it, read from
  `GET /spec/requirements/{identifier}?document=<path>`, with its coverage (`retired`, since F214).
- **The views refresh**: `useSpecEvents` invalidates the new query keys on `spec_updated`, which the
  rigor route already broadcasts (`spec.py:464-466`). The rigor mutation also invalidates the
  history itself on success, so the tab that made the change does not wait for the broadcast
  (operator review, `spec-queue/tracks/reviews/B6-2026-09-24.md` §4).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-document-authority` — adds *"A document's rigor history is on its screen, and the app
  records why"*.
- `requirement-traceability` — adds *"A retired requirement stays reachable from its document"*.

## Impact

- UI only: `hub/ui/src/api/spec.ts` (three hooks), `SpecPhaseBar.tsx`, new
  `SpecRetiredRequirements.tsx`, `SpecDocumentPanel.tsx` (mount); bundle refresh.
- No backend change. No agent-plane change (rigor is the operator's alone by construction,
  `spec.py:435-437`).

Cross-bundle: **B5** owns the evidence list for active requirements and edits `SpecCoverageBar.tsx`;
this change mounts beside it and does not touch that file.
