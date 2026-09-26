# Design — the coverage bar takes the evidence decision it asks for

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B5-2026-09-24.md`, section 3: APPROVE WITH
FIXES) and the operator's decision 3 on it changed this design:

- **A row greyed as "still being recorded" is refreshed when the run ends (new D4).** Nothing
  broadcasts when a run ends or its footprints are re-pointed: `_restamp_evidence_footprints`
  (`agent_trigger.py:1769-1801`) broadcasts nothing, and `refetchOnWindowFocus` is `false`
  (`ui/src/main.tsx:11`), so a greyed row stayed grey until the operator reopened it. D4 broadcasts
  `spec_updated` after the liveness registry is cleared in each transport's `finally`
  (`agent_trigger.py:2706-2713`, `:3250-3254`) — not at `run_completed`, which fires before the
  clear and would race it. Test 1.9.
- **Accept says on the row that it may merge into main (operator decision 3; D1).** Accepting runs
  `integrate_what_was_waiting_for_this_evidence` (`task_integration.py:672-707`), which merges the
  commit for every approved task serving the requirement that has not merged it
  (`tasks_awaiting_this_commit`, `:618-669`). The row now says so beside Accept, for every awaiting
  piece whose footprint names a commit. Test 1.3a.
- **Verified, unchanged:** the list route's order (`for_requirement`, oldest first), the query keys,
  and the broadcast using the id captured before integration.

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
  decision raises **with a task actually waiting**, the route answers **500 today** while the
  decision stands (stored `accepted`) — **measured by R3**; R1's 200 was measured with nothing
  waiting, so the raise was never reached. `evidence-is-decided-after-the-run-that-recorded-it` D6
  fixes it (the response is built before integrating). Until that lands, D2's error rendering shows
  a failure for a decision that was recorded; the refetch on the next `spec_updated` or reopen
  corrects the row.

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
- **Beside Accept, when the footprint is `git` with a `commit_sha` (operator decision 3):** *"Accepting
  may merge commit `<sha[:12]>` into main for an approved task that serves this requirement and is
  waiting on it."* It says *may* because the row cannot know, and should not claim, whether such a
  task exists: `tasks_awaiting_this_commit` (`task_integration.py:618-669`) selects **approved tasks
  linked to the requirement** that have no `merged` row for that commit — not the piece's own
  `task_id` — and `integrate` itself asks git whether the commit is already in main. A piece with no
  commit (a `paths` footprint, or none) can merge nothing (`:642-643` returns `[]`), so it carries no
  such sentence. Rejecting never merges (`:693-695`).

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

## D4 — the row un-greys when the recording run ends (operator review)

`recording_run_live` (the F358 change) is true while `run_liveness.run_is_live(run_id)`
(`run_liveness.py:69-71`). The run leaves the registry in each transport's `finally`:
`run_liveness.active_ptys.pop(run_id, None)` (`agent_trigger.py:2707`) and
`run_liveness.active_app_server_runs.discard(run_id)` (`:3251`). Nothing tells an open view that
happened, so the greyed row never refreshes on its own.

- **Which runs.** `run_liveness` gains `runs_that_recorded_evidence: Set[str]`. The agent-plane
  record route adds `actor.run_id` to it after its commit, beside its existing broadcast
  (`agent_actions.py:1222-1227`). The operator's record route has no run and adds nothing. Only
  those runs can have greyed a row, so no other run end broadcasts anything.
- **Where.** In both `finally` blocks, **synchronously**, next to the registry clear:
  `recorded = run_id in runs_that_recorded_evidence; runs_that_recorded_evidence.discard(run_id)`.
  Then, **after** `await outside_writes.flush()`, if `recorded`: `await sse_manager.broadcast(project_id,
  "spec_updated", {"run_ended": run_id})`, wrapped in `try/except Exception` with a warning. The
  block's comment (`:2708-2713`) says the flush is its only `await` so nothing that must happen is
  skipped when the task is cancelled. This broadcast is placed after the flush on purpose. If a
  cancellation skips it, a row stays grey until the next `spec_updated` or a reopen, which is
  today's behaviour. The flush keeps its guarantee.
- **Why not at `run_completed`.** That event is chosen inside the run's `try` (`:2419`, `:3113`) and emitted before the
  `finally` clears the registry. A view refetching on it can read `recording_run_live: true` again,
  and then nothing refreshes it a second time.
- **The payload carries no `path` and no `evidence`.** Both `spec_updated` consumers tolerate that
  (`api/spec.ts`, `d?.path` guarded; see D3). `useSpecEvents` invalidates `specCoverage` and, with
  this change, `specEvidence`, which is what un-greys the row.
- **Shared seam with the F358 change.** `evidence-is-decided-after-the-run-that-recorded-it` re-queues
  agents refused `recording_run_live` at the same point, after the registry clear. Whichever change
  lands second adds its step beside the first one's, in the same place.
- A Hub restart empties the set, and also every live run, so nothing is left greyed. The next
  fetch reads `recording_run_live: false`.

## What each route returns when what it calls raises

- Decision route: `decide` raising → mapped status, nothing committed, no broadcast. Integration
  raising → caught (`task_integration.py:700-706`) and rolled back, which expires the loaded rows;
  today the route then 500s reading them (R3, measured). With the F358 change's D6 the response is
  built before integrating, and **this change's broadcast must carry the id captured before the
  integration call**, never `evidence.id` read after it — reading it after is the same 500. The
  broadcast goes **after** integration so a subscriber's refetch sees any merge; `sse_manager.broadcast` does not raise on a slow consumer
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
- **R3, 2026-09-24.** Re-derived the list route's order (`for_requirement`, `produced_at` then id),
  the missing broadcasts and the query keys — hold. **Ran** the decision route under a raising
  integration with a task waiting: **500**, decision stored (R1's 200 did not reach the raise). The
  fix is carried by the F358 change (D6); this change's broadcast is told to use the captured id, and
  task 1.1a pins it.
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B5-2026-09-24.md` §3, operator
  decision 3). Added D4 (a `spec_updated` after the run leaves the liveness registry, only for runs
  that recorded evidence) and the *may merge into main* sentence beside Accept. Re-verified at HEAD
  `d0da83d`: `_restamp_evidence_footprints` `agent_trigger.py:1769-1801` (no broadcast); the two
  `finally` blocks `:2706-2713`, `:3250-3254`; `refetchOnWindowFocus: false` `ui/src/main.tsx:11`;
  `integrate_what_was_waiting_for_this_evidence` `task_integration.py:672-707`;
  `tasks_awaiting_this_commit` `:618-669`; the record route's broadcast `agent_actions.py:1222-1227`.
  Tests 1.3a, 1.9, 1.9a added.
