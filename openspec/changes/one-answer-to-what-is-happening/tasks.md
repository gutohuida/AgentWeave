## 1. Bind review runs (D1, D2)

- [ ] 1.1 Test: a run started to review a task records that task. Fails today — `binding_from_entries`
      reads only `entry.task_id` and every review entry has it NULL.
- [ ] 1.2 Test: binding a review leaves the task's status and assignee unchanged. Pins the inertness
      the design asserts, so a later edit to `bind_run_to_task` cannot silently start a task under review.
- [ ] 1.3 Test: a turn delivering both a work item and a review item binds to exactly one, and the
      same input always produces the same binding.
- [ ] 1.4 Test: the review checkout value and the bound-task value remain distinct — neither derived
      by reinterpreting the other.
- [ ] 1.5 `binding_from_entries` accepts `review_task_id` as a second source of "names a task",
      preserving earliest-queued-wins ordering and the divergence-source pairing from the same entry.
- [ ] 1.6 Confirm `bind_run_to_task` needs no change for a review: `allowed_targets('under_review',
      run)` excludes `in_progress`, and the `not task.assignee` guard is a no-op for a staffed review.
      Record the finding either way — a change here is a design deviation, not a detail.
- [ ] 1.7 Verify a review run now reaches `run_advanced_its_task` rather than short-circuiting on
      `if not run.task_id: return True`, and that a review recording a verdict passes it
      (verdict transitions carry `origin='actor'`).
- [ ] 1.8 Confirm F38's `note_turn_that_produced_nothing` no longer fires for review runs, and that
      its existing tests still describe reachable behaviour for the unbound runs that remain.
- [ ] 1.9 Mutation check: revert 1.5 only; confirm 1.1 fails by name. Restore and re-confirm green.

## 2. How a verdict-less review is answered (D3, D4, D5, D6)

- [ ] 2.1 Test: a review that ends with no verdict on a task whose policy is `retry` starts no
      further run by that policy.
- [ ] 2.2 Test: a review that ends with no verdict on a task whose policy is `escalate`, with an
      escalation agent named, does not reassign the task by that policy and starts no run by it.
- [ ] 2.3 Test: a work run on the same task with the same policy still retries and still escalates —
      the carve-out is for reviews, not a removal of the policy.
- [ ] 2.4 Test: a **declared** reviewer that gives no verdict is surfaced and no other agent is
      fired; the operator is told which declared reviewer gave no verdict, naming the task.
- [ ] 2.5 Test: an **availability-picked** reviewer that gives no verdict is replaced by re-resolving,
      and the agent that failed is excluded.
- [ ] 2.6 Test: an availability-picked review failing with no other eligible agent surfaces, naming
      the task, and leaves the flow's job enabled and scheduled.
- [ ] 2.7 Test: the agent that moved a task to `completed` is never resolved as its reviewer, on
      first resolution and after a failure.
- [ ] 2.8 Test: a run started in response to a failed review is given the checkout of the work under
      review. **Fails today** — `_queue_response` builds `new_entry(..., task_id=task_id)` with no
      `review_task_id`, which is finding F10 reproduced.
- [ ] 2.9 Test: a response to a run that was *not* a review prepares no review checkout.
- [ ] 2.10 A review run reaching the boundary with no verdict records a `RunDivergence` and does not
      enter `_apply_policy`.
- [ ] 2.11 `_queue_response` carries `review_task_id` when the diverged run was itself a review.
- [ ] 2.12 Re-resolution for a failed availability-picked review, excluding the failed agent, through
      the existing reviewer resolution — not a second one.
- [ ] 2.13 Surfacing for a failed declared reviewer, carrying the declared name and the reason.
- [ ] 2.14 Mutation checks by name: removing the review carve-out fails 2.1 and 2.2; removing
      `review_task_id` from the response entry fails 2.8; removing the failed-agent exclusion fails 2.5.

## 3. Audit the "is it running" call sites (D10)

- [ ] 3.1 Enumerate every site computing `Run.status == "running"`, with its scoping and its caller.
- [ ] 3.2 For each, write down which question it asks and whether it is the same question as the
      board's. `agent_auth` (live run for credentials) and `conversation_titles` (deliberately records
      no `Run`) are expected to be legitimately different — confirm rather than assume.
- [ ] 3.3 Record the outcome per site in `design.md` under D10, including the sites that do **not**
      move and why. A site left alone with no stated reason is an open hole, not a decision.

## 4. One owned determination of capacity (D8, D9)

- [ ] 4.1 Test, in **Python**, over the determination itself rather than a renderer: each of the four
      capacities from its own source. This is the coverage F49 lacked — five vitest cases over the
      renderer and none over the derivation, so an unreachable branch shipped and stayed.
- [ ] 4.2 Test: a task under review whose run has ended and has nothing running is not presented as
      working.
- [ ] 4.3 Test: an agent mid-turn on one task while holding a second that nothing is running does not
      make the second read as worked — the over-report the current agent-fallback concedes to.
- [ ] 4.4 Test: no module outside the owning module reads the firing decision's cannot-staff
      collection. Source-scanning, in the idiom `test_nothing_pushes` already uses for
      `task_integration.py`'s never-push guarantee.
- [ ] 4.5 New module `hub/hub/task_attribution.py` taking the spec's own vocabulary, with one entry
      point answering the capacity for a `(task, agent)` pair from four distinct sources.
- [ ] 4.6 `FiringDecision` stops exposing the merged cannot-staff collection publicly; the owning
      module becomes its only reader.
- [ ] 4.7 Remove the ~90-line derivation and the agent-fallback from `hub/hub/api/v1/jobs.py`; the
      renderer consumes the determination and renders.
- [ ] 4.8 Rename `agent_role` to `agent_capacity` across the Pydantic schema, `hub/ui/src/api/jobs.ts`,
      `JobCard.tsx` and the vitest cases. Values unchanged.
- [ ] 4.9 Mutation checks by name, one per capacity branch, as F63 and F64 were: collapsing `held`
      into `working` fails 4.2; removing the per-source split fails 4.3; deleting the encapsulation
      fails 4.4.
- [ ] 4.10 `cd hub/ui && npm run build` then `make ui` (or `python scripts/refresh_ui_bundle.py`),
      committing `hub/ui/src` and `hub/hub/static/ui` together per CLAUDE.md.

## 5. Pin what already holds (D7)

- [ ] 5.1 Test: the crash path and the silence path stay disjoint — `return_run_entries` acts only on
      a failed run's delivered entries and the boundary check is skipped for them, while a completed
      run with no verdict reaches the boundary. Nothing states this today and a future edit could
      merge them, which is how F45 would return.
- [ ] 5.2 Test: a re-delivered review entry keeps `review_task_id`, so the checkout survives requeue.
- [ ] 5.3 Confirm re-delivery remains bounded by `DELIVERY_ATTEMPT_LIMIT` and that a withdrawn entry
      still carries its `abandoned_reason`.

## 6. Verify live, not only against fixtures

- [ ] 6.1 Restart the trial Hub on port 8010 from source on this branch, against the beta profile
      database. **Confirm the project list, not only `/health`** — a stale-database start answers
      `{"status":"ok"}` while serving a different world.
- [ ] 6.2 Drive a real review to a verdict on the trial Hub; confirm `run.task_id` is set on the
      review run and no divergence is recorded.
- [ ] 6.3 Drive a review that ends without a verdict; confirm the `RunDivergence` row exists, the
      task did not move, and the card presents the reviewer as held rather than working.
- [ ] 6.4 Drive a failed **availability-picked** review; confirm re-resolution excludes the failed
      agent and the responding reviewer's workspace is the checkout of the work under review.
- [ ] 6.5 Drive a failed **declared** reviewer; confirm it surfaces and no substitute is fired.
- [ ] 6.6 Set a task's policy to `retry`, fail its review, and confirm nothing is retried — the
      carve-out firing in production, not only in a fixture.
- [ ] 6.7 Leave no job enabled in any project when finished, and record in `scripts/drive/FINDINGS.md`
      anything the drive surfaced that this change does not cover.

## 7. Sweep

- [ ] 7.1 `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q`, both green, run
      **after** the final commit rather than before it.
- [ ] 7.2 `py -3.11 -m ruff check src/ hub/ tests/` and `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`.
- [ ] 7.3 `cd hub/ui && npx tsc --noEmit`, `npm run lint`, `npx vitest run`.
- [ ] 7.4 `npx openspec validate one-answer-to-what-is-happening --strict`.
- [ ] 7.5 Confirm the new test count matches the tests added, so a silently skipped module is visible.
