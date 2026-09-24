# Proposal — the coverage bar takes the evidence decision it asks for

**Round 1, 2026-09-24** (bundle B5, spec track S5 slice (a)). Finding: **F215 (B)**. Re-verified on
HEAD `404c7d5`: still open. Nothing here is implemented.

## Why

The document panel's coverage bar tells the operator a decision is theirs and gives them nothing to
decide with. `SpecCoverageBar.tsx:22-26` ships the state *"Awaiting review — Evidence exists for the
current wording and nobody has decided about it yet."*; the bar is mounted on the document panel
(`SpecDocumentPanel.tsx:240`). The route that decides — `POST /spec/evidence/{id}/decision`
(`hub/hub/api/v1/spec.py:892-926`) — and the route that lists evidence — `GET /spec/evidence`
(`:862-889`) — have **no caller** in `hub/ui/src` (R1 grep: `spec/evidence` appears nowhere under
`hub/ui/src` or `hub/hub/static/ui`). So an operator using only the app cannot accept their own
project's evidence, and accepted evidence is what approval merges
(`task_integration.integration_targets`, `:270-286`).

It has become sharper since F215 was filed:

- **The approval gate refuses on it.** `requirement_gate._check_unaccepted` (`:493-541`) refuses
  approval while evidence that would merge sits unaccepted, and its remedy is *accept the evidence*.
- **Reviewers now send the operator to it.** Round 5's `review_turn.verdict_evidence_sentence`
  (F357, commit `1b58a2b`, `review_turn.py:178-235`) tells an ungranted reviewer to `ask_user` the
  operator *"to decide the evidence named above"*, naming each piece by id. The operator receives the
  question and has no screen on which to act on it.

## What Changes

- **Each coverage row with evidence lists it and can decide it** (design D1). Opening the bar's
  detail already lists each requirement; a row whose `evidence_count` is above zero gains an
  *Evidence* toggle that fetches `GET /spec/evidence?identifier=<FR-n>&document=<path>` and lists each
  piece: summary, who recorded it, locator, the commit and branch its footprint names, the task, its
  state and the latest review's reason, in the route's order with the most recently recorded
  marked *latest*. A piece that is `awaiting` has **Accept** and **Reject**; Reject
  requires a reason.
- **A refusal is shown, not swallowed** (D2). The Hub's sentence is rendered beside the piece — the
  grant refusal, and `recording_run_live` once `evidence-is-decided-after-the-run-that-recorded-it`
  ships. Where the view carries `recording_run_live: true`, the buttons are held with that sentence.
- **Deciding refreshes what depends on it** (D3). Both decision routes broadcast `spec_updated`
  (neither does today: `spec.py:892-926`, `agent_actions.py:1309-1349`), and the mutation also
  invalidates the task queries, because accepting can merge approved work
  (`integrate_what_was_waiting_for_this_evidence`).

## Out of scope

- **Drift** — the bar's other instruction, *"Someone needs to say which one was wrong"*
  (`SpecCoverageBar.tsx:13-15`), is S5 slice (b), bundle **B6** (F129, F132, F216, F217).
- **Audit reads** (F211: `GET /spec/requirements[/{identifier}]`, `rigor-history`) are B6 slice (d).
  This change deliberately reads `GET /spec/evidence`, F215's own route, so it does not become F211's
  first caller by the back door.
- **Deciding from the task drawer**, where the approval refusal lists awaiting pieces by id
  (`TaskDetailDrawer.tsx:108`). Design Open Question 1.
- Recording evidence as the operator from the screen (`POST /spec/evidence`), and the retention
  route. F215 lists them; neither is asked for by a sentence on screen.

## Impact

- `hub/ui/src/api/spec.ts` (two hooks), `hub/ui/src/components/spec/SpecCoverageBar.tsx`, a new
  `hub/ui/src/components/spec/EvidencePieces.tsx`; the committed bundle (`hub/hub/static/ui`) —
  `.claude/rules/hub-ui.md` applies, and a committed bundle reaches `:8000` on reload
- `hub/hub/api/v1/spec.py` and `hub/hub/api/v1/agent_actions.py` (a broadcast after each decision)
- `openspec/specs/requirement-traceability` (one ADDED requirement)
