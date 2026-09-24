# Design — the coverage bar takes the evidence decision it asks for

No operator decision governs this change. It is S5 slice (a). It reads better after
`evidence-is-decided-after-the-run-that-recorded-it` ships (it renders that change's refusal and
field), but it does not depend on it: without it, the field is absent and treated as `false`, and a
mid-run decision simply succeeds as it does today.

## What the routes return (HEAD `404c7d5`)

- `GET /spec/evidence?identifier=FR-n&document=<path>` → `{"evidence": [...]}` from
  `requirement_evidence.for_requirement` (`:847-853`), **ordered `produced_at` ascending, then id** —
  oldest first. Each row is `_evidence_view` (`spec.py:1108-1144`): `id`, `summary`, `kind`,
  `locator`, `actor_kind`, `actor`, `run_id`, `task_id`, `review_state`, `latest_review`
  `{decision, reason, actor_kind, actor, created_at}`, `produced_at`, `footprint`
  `{kind, branch, commit_sha, reachable_from_main, outside_workspace_writes}` (`footprint_view`,
  `:1147-1170`). An unknown identifier → 404; an identifier two documents declare without
  `document` → 422 (`_requirement`), which the bar avoids by always passing its own path.
- `POST /spec/evidence/{id}/decision {decision, reason}` → 200 `_evidence_view` with the new review;
  404 for an id of another project; 422 `unknown_decision`; 403 for the grant (never, for the
  operator); after this bundle's F358 change, 409 `recording_run_live`. When integration after the
  decision raises, the route still answers 200 with the decision standing — **measured in R1** (a
  scratch test made `retry_integration` raise; 200, `review_state: accepted`, stored `accepted`).

## D1 — where the decision lives

Options considered:

| Option | For | Against |
|---|---|---|
| (a) in the coverage bar's expanded rows | it is the screen that says a decision is waiting; per-requirement is how coverage is computed | one more click (open the bar, open the row) |
| (b) a project-wide "Evidence awaiting review" queue | one place for everything | a new screen, a new route shape (`GET /spec/evidence` has no state filter), and it is not what any sentence on screen points at |
| (c) the task drawer's awaiting-evidence entries | where the approval refusal names the pieces | the drawer entry carries only `evidence_id`; no route reads one piece by id |

Recommended **(a)**, because it answers the sentence where it is said. (c) is Open Question 1.

The component, `EvidencePieces`, takes `{path, identifier}` and owns its query and mutation, so a
second mount (the drawer) needs no refactor.

Rendering, per piece, in **the route's order (oldest first, `produced_at` then id —
`requirement_evidence.for_requirement`, `:845-851`)**, with the last piece marked *latest* — meaning
**most recently recorded**, and nothing more (R2). R1 said the label tells the operator which piece a
merge would take; it cannot. The merge reduces per **task**, across every requirement the task
serves, per **branch**, by footprint `observed_at` (`task_integration._targets` `:240-266`,
`integration_targets` `:270-287`) — and this bundle's footprint change replaces that reduction with
the descendant commit per line of work. This list is per **requirement**, across tasks, by
`produced_at`. The newest piece here can belong to another task, or lose to a descendant on its
branch. So the label claims only the order the route returns.

- `summary` (or *"no summary"*), `actor` (`operator` / agent name), `locator` when present.
- The footprint: `commit_sha[:12]` on `branch`, or *"no commit"* (a `paths` footprint), and — when
  `outside_workspace_writes` is a non-empty list — *"this run also wrote outside this tree"*.
- `task_id` when present. `review_state`; for a decided piece, the latest review's actor and reason.
- For `awaiting`: **Accept**; **Reject** opens a one-line reason input and is disabled while empty.

## D2 — refusals

`useDecideEvidence` rejects with `ApiError`; the component renders
`readableApiError(error, 'The Hub refused this decision.')` under the piece. Where
`recording_run_live` is `true` on the row, the buttons are disabled and the row reads *"still being
recorded by run <id>; decide once it ends"*.

## D3 — refresh

- Backend: after the commit in both decision routes, and after
  `integrate_what_was_waiting_for_this_evidence`, broadcast `spec_updated` with
  `{"evidence": id, "requirement": identifier}` — the shape the agent record route already sends
  (`agent_actions.py:1224-1228`). `useSpecEvents` (`api/spec.ts:152-178`) already invalidates
  `specCoverage` on `spec_updated`, filtered by the trusted `project_id` the SSE manager stamps.
- Frontend: the mutation's `onSuccess` invalidates `['project', pid, 'specCoverage']`,
  `['project', pid, 'specEvidence', path, identifier]`, and `['project', pid, 'task']` and
  `['project', pid, 'tasks']`. R2 listed `api/tasks.ts`: the prefix `task` covers
  `[…, 'task', id, 'integrations']` (`:162`), `'transitions'` (`:194`) and `'integration-preview'`
  (`:229`); the prefix `tasks` covers the lists and boards (`:277`, `:298`, `:333`, `:353`). No other
  task-scoped key moves when evidence is decided.
- `useSpecEvents` also invalidates `['project', pid, 'specEvidence']` on `spec_updated`, so a piece an
  agent records while the row is open appears.
- The broadcast carries no `path`. Both `spec_updated` consumers tolerate that
  (`api/spec.ts:158-178` guards `d?.path`; the rename follower returns early without one, `:195-196`)
  — checked by R2, and the same property B6's drift change relies on for `path: null`.

## What each route returns when what it calls raises

- Decision route: `decide` raising → mapped status, nothing committed, no broadcast. Integration
  raising → caught (`task_integration.py:700-706`), 200. The broadcast goes **after** integration so
  a subscriber's refetch sees any merge; `sse_manager.broadcast` does not raise on a slow consumer
  (`sse.py:91-94`).
- List route: `_requirement` → 404/422; the component shows the sentence in place of the list.

## Cross-bundle

- `drift-is-scanned-and-answered-on-the-document` (B6) edits one string in `SpecCoverageBar.tsx`
  (the *Drifting* sentence) and mounts `SpecDriftPanel` beneath the bar. This change edits the bar's
  expanded rows. Whichever lands second rebases; both declare it.
- `a-documents-rigor-history-and-retired-requirements-are-on-screen` (B6, F211) mounts beside the
  bar and reads `GET /spec/requirements[/{identifier}]`; it states that B5 owns the evidence list for
  active requirements. This change reads `GET /spec/evidence`, so the two do not share a route.
- `drift-watches-the-files-its-evidence-is-about` (B6) adds keys to `footprint_view`. `EvidencePieces`
  renders only the keys named in D1, so extra keys are harmless.

## Open questions

1. **The drawer as a second mount.** The approval refusal's awaiting entries
   (`TaskDetailDrawer.tsx:108`) name `evidence_id` and `identifier` but not the document path, so
   `EvidencePieces` cannot be mounted there as written. Options: (a) add `document` (path) to the
   gate's awaiting entry and to `verdict_evidence_sentence`'s pieces, then mount it; (b) a
   `GET /spec/evidence/{id}` route; (c) leave the drawer pointing at the document. Recommended (a) as
   a follow-up change, because F357's `ask_user` question would then name where to go.
2. **Reject reason required** — **decided by R2: required in the UI only.** A rejection without a
   reason reaches the author as *"rejected"* with nothing to act on; an API client (and a granted
   agent through `decide_evidence`) keeps today's contract, so no route or test changes for it.

## Round log

- **R1, 2026-09-24.** Re-verified F215 (no `spec/evidence` caller in source or bundle); read the
  list and decision routes' real order and failure answers; measured the decision route under a
  raising integration.
- **R2, 2026-09-24.** Route order, both routes' missing broadcast, the integration wrap
  (`task_integration.py:672-707`) and the query keys re-derived — hold. One claim disagreed: the
  *newest* label does not say which piece a merge takes (different grouping, key and — after change
  4 — rule); relabelled *latest* = most recently recorded. Open Question 2 answered. B6's edits to
  `SpecCoverageBar.tsx` (one *Drifting* string; a panel mounted beneath) and `SpecPhaseBar.tsx`
  (rigor select and history) touch no region this change edits.
