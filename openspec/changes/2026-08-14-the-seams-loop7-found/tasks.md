# Tasks — the seams loop 7 found

Phased so each phase ends green and is independently shippable. Order is forced by D15: 1 before 2,
3 before 4, 6 last.

**One migration across all six** — `0072`, in phase 4. Head moves `0071 → 0072` and **both** head
assertions move with it.

## 1. Evidence is footprinted against the commit that contains it

- [x] 1.1 Extract `_apply_footprint(session, evidence, taken, existing=None)` in
      `hub/hub/requirement_evidence.py`; refactor `capture_footprint` (:164-185) to call it, so one
      place maps a `Footprint` onto a row (D5).
- [x] 1.2 New `restamp_run_footprints(session, *, project_id, run_id, root, commit_sha=None,
      main_branch=None) -> int`. Outer-join `RequirementEvidence → EvidenceFootprint` on
      `project_id`, `run_id`, `actor_kind == "agent"`. **Outer**, so it creates the footprint that
      `resolve_project_workspace` failing at record time left absent (D5).
- [x] 1.3 Compute the `Footprint` **once per run**, not per row. Reuse `tree_entries` (:205),
      `is_reachable_from` (:256), `is_reachable_from_main` (:283).
- [x] 1.4 Fall back to the worktree's `HEAD` when `commit_sha` is `None` — a `None` snapshot is not a
      skip (D3).
- [x] 1.5 Idempotence guard: skip a row already `kind == "git"` at that `commit_sha`.
- [x] 1.6 **Write a fresh `reachable_from_main`, including `False`.** Do *not* reuse
      `refresh_reachability`'s upgrade-only rule (D4) — this is a different commit.
- [x] 1.7 Re-stamp regardless of review state (D2); do not touch `EvidenceReview`.
- [x] 1.8 Call it from `hub/hub/api/v1/agent_trigger.py` at both snapshot sites — after
      `run.snapshot_commit_sha = snapshot_sha` (~:1333 exec, ~:1759 app-server), inside the existing
      session block, covered by its `await db.commit()`.
- [x] 1.9 New `hub/tests/test_evidence_restamp.py`: names the snapshot commit not its parent;
      recomputes `entries` and reachability; creates the footprint recording could not; falls back to
      `HEAD`; no-op when unchanged; leaves another run's rows alone; corrects an accepted row and
      leaves its review untouched.
- [x] 1.10 `test_integration_targets_the_snapshot_commit_after_a_restamp` — landed in
      `test_evidence_restamp.py`, not `test_task_integration.py`: it needs a real worktree with dirty
      work, and that suite deliberately uses branch-switching in one directory instead.
- [x] 1.11 **`hub/tests/test_evidence_footprint_root.py` must pass unchanged** — every test there
      pre-commits the agent's work, which is why none of them caught this. Change the code, not them.

## 2. A skipped integration can be retried

- [x] 2.1 `_integrate` → public `integrate_task(session, task, actor)` in
      `hub/hub/task_transition_service.py`, now returning its results.
      `apply_transition:244-245` calls it unchanged.
- [x] 2.2 New `retry_integration(session, task, actor)` refusing unless `task.status == "approved"`
      (`IntegrationRetryRefusedError`, 409). The one place that rule lives (D6).
- [x] 2.3 No refusal when the newest outcome is already `merged` — `integrate` self-guards with
      `ALREADY_INTEGRATED` (D6).
- [x] 2.4 `POST /tasks/{task_id}/integrations/retry` in `hub/hub/api/v1/tasks.py`, returning the same
      shape as the `GET` at :340. Emit `task_integration_retried` **after** the commit —
      `persist_event` commits.
- [x] 2.5 Agent plane gains **both** `GET /tasks/{task_id}/integrations` and the retry in
      `hub/hub/api/v1/agent_actions.py`, scoped to `actor.project_id`. Read included because an agent
      that can retry but not read retries blind.
- [x] 2.6 New `task_integration.tasks_skipped_for_want_of_a_main_branch(session, project_id, *,
      limit=50)`.
- [x] 2.7 Drive it from `projects.py:update_project_settings` **after** `session.commit()` (~:462),
      before `redrain_queued_agents`, in its own `try`/`except` so a git failure cannot undo the save
      (D8). Only when `main_branch` is non-empty and changed.
- [x] 2.8 UI: `useRetryTaskIntegration()` in `hub/ui/src/api/tasks.ts`;
      `TaskIntegrationNote.tsx` dedupes to the newest row per `(commit_sha, target_branch)` and
      renders "Try again" on a `skipped`/`failed` newest row — except `NO_MAIN_BRANCH`, which links to
      settings, because retrying there would only skip again.
- [x] 2.9 `hub/ui/src/hooks/useSSE.ts`: allowlist `task_integration_retried` and invalidate the
      task's integrations key.
- [x] 2.10 Tests in `hub/tests/test_task_integration.py`: retry merges work a skip left behind;
      refuses a non-approved task; after a merge records `ALREADY_INTEGRATED` and merges nothing;
      `apply_transition` still integrates through the public function (pins the rename); the agent
      plane can read and retry; refuses another project's task; a settings save retries only the
      tasks that wanted a branch; leaves a dirty-checkout skip alone; a settings save survives a
      failing retry.
- [x] 2.11 Cross-phase: `test_retry_merges_the_snapshot_commit_after_a_restamp`.
- [x] 2.12 Rebuild `hub/hub/static/ui`, confirm with `diff -rq`.

## 3. A dead runtime says what happened

**Cannot be split** — the error fields, the stderr drain and the method tracking are one change, or
the error has fields nothing fills.

- [x] 3.1 `AppServerError` gains `exit_code`, `method`, `stderr_tail`, composed into the message so
      `str(exc)` alone carries all three (D9).
- [x] 3.2 `self._pending: Dict[int, _Pending]` (method + future) replaces the bare future dict at
      :605, so the in-flight method cannot drift from its future.
- [x] 3.3 `_drain_stderr` task started in `spawn` beside `_reader_task`, cancelled in `close`,
      appending to a bounded `deque`. Handle `ValueError`/`LimitOverrunError` on a pathological line.
      **This also fixes a live bug** — `stderr` is piped at :547 and read nowhere, so it can fill and
      block the child.
- [x] 3.4 Use the enriched error at **both** raise sites — the reader-loop `finally` (:579-585) and
      the loop-exit check (~:784), which is the common path.
- [x] 3.5 `TurnOutcome` gains `exit_code`. Do **not** feed it into `Run.exit_code` — the synthetic
      `0`/`1` is load-bearing for `AgentOutputPanel`'s handoff detection.
- [x] 3.6 `run_failed` at `agent_trigger.py:1708-1710` gains `exit_code`, `method`,
      `conversation_id`, via `getattr` (the same `except` catches `FileNotFoundError`/`OSError` too).
- [x] 3.7 **`hub/tests/test_codex_appserver.py`'s purity assertions must not be edited.**
      `decide_approval` stays pure; all new state is on `AppServerProcess` and in `run_turn`.
- [x] 3.8 New `hub/tests/test_codex_appserver_process.py`: names the exit code and pending method;
      the tail is bounded; stderr is drained so a chatty child cannot block; the error reads as one
      sentence for existing handlers.
- [x] 3.9 `test_codex_appserver_run_turn.py` and `test_agent_trigger.py` cases for the enriched
      failure.

## 4. A failed run cannot wedge its agent

- [x] 4.1 Migration `0072_add_queue_delivery_attempts.py`, `down_revision = "0071"`, **guarded for a
      missing `inbound_queue_entries`** in the `0071` style. Adds `delivery_attempts INTEGER NOT NULL
      DEFAULT 0` and `abandoned_reason TEXT NULL`.
- [x] 4.2 Matching fields on `InboundQueueEntry` (`hub/hub/db/models.py` ~:512).
- [x] 4.3 Bump the head assertions in **both** `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`.
- [x] 4.4 `RESUME_RETRY_LIMIT = 2`, `DELIVERY_ATTEMPT_LIMIT = 3` in `hub/hub/inbound_queue.py`, with
      the reasoning from D11 written at the constants.
- [x] 4.5 `return_run_entries` counts the attempt, clears `delivered_at`, then requeues or abandons.
      **Keep its `List[str]` return** — that is what keeps `test_interrupted_run_returns_delivered_entries`
      passing unchanged.
- [x] 4.6 At `RESUME_RETRY_LIMIT`, clear that conversation's `provider_session_id` so the next
      delivery is a `thread/start` (D10).
- [x] 4.7 At `DELIVERY_ATTEMPT_LIMIT`, abandon: `state="withdrawn"`, `withdrawn_at`,
      `abandoned_reason` embedding phase 3's diagnostic text. Reuse `withdrawn`; do **not** add a
      fourth state (D12).
- [x] 4.8 Do **not** clear `conversation_id` and do **not** bump `arrived_at` (D12). Abandoned rows
      keep `delivered_in_run_id`.
- [x] 4.9 New `abandoned_for_run(db, run_id)`.
- [x] 4.10 All three requeue sites report abandonment: `agent_trigger.py:1153`,
      `agent_trigger.py:1706`, `run_reconciliation.py:51`.
- [x] 4.11 New warn events `queue_entry_abandoned` and `conversation_session_reset`; add both to
      `useSSE.ts` and the queue-status invalidations.
- [x] 4.12 `delivery_attempts`/`abandoned_reason` on `QueueEntryResponse`, `delivery_attempts` on
      `QueueStatus`. Keep `get_queue_status`'s existing reason precedence — a missing CLI explains
      the wait better than a retry count — and synthesise the attempts sentence only when nothing
      else fired.
- [x] 4.13 **`hub/tests/test_inbound_queue.py:87` and `:201` must pass unchanged**, as must
      `hub/tests/test_run_reconciliation.py`.
- [x] 4.14 New `hub/tests/test_delivery_attempts.py`: counts the attempt; the 2nd failure clears the
      provider session; the next delivery starts a new thread; the 3rd abandons with a reason; an
      abandoned entry stops controlling the queue so a fresh conversation runs; the run that ate it is
      still named; events persist; queue status reports attempts only when nothing else explains the
      wait; `return_run_entries` still returns only requeued ids.

## 5. `requirement_ids` is readable

- [x] 5.1 `requirement_ids: List[str] = Field(default_factory=list)` on `TaskResponse`
      (`hub/hub/schemas/tasks.py:188-234`).
- [x] 5.2 Fill it in `_attach_requirements`'s final loop (`hub/hub/api/v1/tasks.py:132-134`) from
      `requirement_links` — **zero extra queries**.
- [x] 5.3 Identifiers, not row ids (D13). Exclude unresolved references.
- [x] 5.4 UI: types in `hub/ui/src/api/tasks.ts`; `TaskCard.tsx:466-471` relabels the existing block
      "Requirements (as written)" and adds a "Serves" block above it listing the checked links.
- [x] 5.5 Tests in `hub/tests/test_requirement_links.py`: the response returns the identifiers it
      accepts; they round-trip through create and get; they are identifiers not row ids; unresolved
      references are omitted; the agent plane carries them.
- [x] 5.6 Vitest: `TaskCard` renders checked links alongside the free-text requirements.
- [x] 5.7 Rebuild `hub/hub/static/ui`, confirm with `diff -rq`.

## 6. The bundle staleness warning can be cleared

- [x] 6.1 `ui_source_fingerprint(ui_src, *, exclude=("__tests__",))` in `hub/hub/main.py` — sha256
      over `git ls-files -s` with the pathspec already used at :86, plus a `+dirty:` component from
      `git status --porcelain` when non-empty.
- [x] 6.2 `read_ui_build_stamp(ui_dist)` reading `hub/hub/static/ui/ui-build-stamp.json`.
- [x] 6.3 `_compute_ui_staleness_warning` keeps its signature. **Stamp absent → fall through to
      today's date comparison byte for byte** (D14) — this is what keeps the existing tests unedited.
      Matching → silent. Differing → warn, saying so when the source is dirty.
- [x] 6.4 Replace `lru_cache(maxsize=1)` (:99-101) with a 30-second TTL plus
      `_reset_ui_staleness_cache()` for tests, so a rebuild clears without a Hub restart.
- [x] 6.5 `scripts/refresh_ui_bundle.py` and a `make ui` target: copy `hub/ui/dist` →
      `hub/hub/static/ui`, `diff -rq` to confirm, then write the stamp **after** the copy so a
      `rm -rf && cp -r` cannot drop it.
- [x] 6.6 **The existing five tests in `hub/tests/test_ui_staleness.py` must pass unedited.** Add:
      absent stamp falls back to the date comparison; a matching stamp clears the warning; a stamp
      naming other source still warns; a types-only change clears after re-stamping with no bundle
      change; an uncommitted edit is reported; the warning clears within the TTL without a restart.
- [x] 6.7 `test_the_committed_bundle_carries_a_parseable_build_stamp` in
      `hub/tests/test_repo_hygiene.py`, unconditional and cheap.
- [x] 6.8 A stricter bundle-matches-source hygiene test **gated behind `AW_CHECK_UI_BUNDLE=1`**, so
      CI can enforce it without blocking a branch mid-edit. This avoids reversing CLAUDE.md's stated
      "`test_ui_staleness.py` does not check this repo's copy".
- [x] 6.9 Update `CLAUDE.md`'s bundle-refresh rule to name `make ui`.

## 7. Corrections to the record

- [x] 7.1 Correct finding 5 in
      `openspec/explorations/2026-08-14-loop7-evidence-drives-but-a-skipped-merge-is-terminal.md`:
      `requirement_ids` was never on `TaskResponse`; the links **are** exposed as `requirement_links`.
      A write-only asymmetry, not missing data. The finding stands; its severity drops.

## 8. Verification — agent-verifiable

- [x] 8.1 `pytest hub/tests/ -q` and `pytest tests/ -q` **separately**, Python311 interpreter.
- [x] 8.2 `ruff check hub/ src/`; `black --target-version py311` on every file touched.
- [x] 8.3 `npx tsc --noEmit`; `npx vitest run`. (`npm run lint` does not work here.)
- [x] 8.4 `npx openspec validate --changes --strict`.
- [x] 8.5 `npm run build` + the bundle refresh; `diff -rq` identical. Required after phases 2, 5, 6.
- [x] 8.6 Mutation checks, because a vacuous assertion has bitten this codebase three times:
      deleting the re-stamp call must fail `test_restamp_names_the_snapshot_commit_not_its_parent`;
      restoring the unconditional requeue must fail
      `test_the_third_failure_abandons_the_entry_with_a_reason`.
- [x] 8.7 Needed updating in the end: only `test_codex_appserver_run_turn.py`'s `_FakeSession`,
      which gained `returncode`/`stderr_tail`/`process_ended_error` — the fake should implement the
      interface rather than the production code carrying a `getattr` guard for it. No test asserting
      the old bare `run_failed` payload existed, and `test_operator_projects_api.py` was unaffected.

## 9. Verification — human-only

**Ran 2026-08-14 as loop 8** (project `aw-loop8`, findings in
`openspec/explorations/2026-08-14-loop8-a-dead-runtime-eats-the-message.md`).

- [x] 9.1 **Re-run `/e2e-loop` from zero.** Pass condition: a builder records evidence mid-turn and
      the footprint names the **snapshot** commit — **no reject/re-record cycle at all**. That round
      trip is what phase 1 exists to remove, and its absence is the proof.
      **PASSED.** All five footprints named `b8b8664`, the builder's own snapshot; blob-verified
      against the commit, and the parent held only `README.md`. The verifier reviewed that commit and
      raised no commit-mismatch complaint. It rejected FR-3 on merit (a `Decimal("NaN")` hole),
      which is the review gate working, not the round trip this phase removes.
      D3's fallback also observed: a turn that committed its own work re-stamped to `HEAD`.
- [x] 9.2 Approve a task with no main branch set, then set one in settings. The merge must happen
      **without** walking the task back through `revision_needed`.
      **PASSED.** `NO_MAIN_BRANCH` skip, then naming `master` in settings merged on save
      (`fcb0f51`). Transitions: `pending → assigned → in_progress → completed → under_review →
      approved`, no walk-back.
- [ ] 9.3 Kill a Codex app-server mid-turn three times. The agent must unwedge on its own and the
      operator must be told, rather than four silent failures.
      **FAILED — left unchecked deliberately.** The agent does unwedge (`idle` after every failure),
      but a *mid-turn* death never reaches `return_run_entries`: the entry stays `delivered` with
      `delivery_attempts = 0`, so it is neither retried nor abandoned and the operator's input is
      lost silently. Reproduced twice. `RESUME_RETRY_LIMIT`/`DELIVERY_ATTEMPT_LIMIT` are
      structurally unreachable on this path — see finding 1. On the *pre-spawn* path the machinery
      works (reset-at-2 recovered a genuinely unresumable session on attempt 3), but nothing drives
      attempts 2 and 3 on its own — finding 2.
- [ ] 9.4 Does an abandoned queue entry read as "the Hub gave up" clearly enough to act on?
      **Not reachable to judge:** no entry was ever abandoned, for the reason in 9.3. Still the
      operator's call once finding 1 is fixed.
- [ ] 9.5 Does "Try again" read as safe, given it merges into the main branch?
      Still the operator's call. Data point from outside: the retry route merged correctly from a
      genuine `CHECKOUT_DIRTY` skip, but the skip's own text says *"commit or stash them and the
      next approval will merge"*, which provably does nothing — finding 3.
- [x] 9.6 Is `make ui` a workflow you would actually run, or will the stamp rot?
      **Answered from outside: it will rot as written.** `make` is absent from both Git Bash and
      PowerShell on this machine, and the warning names only `make ui` — finding 6. The mechanism
      itself is sound: an uncommitted types-only edit raised `ui_stale` within the TTL and reverting
      cleared it, with no Hub restart, and the uncommitted case was called out by name.

## 10. User test guide

**Setup.** A git-backed project, an approved document declaring tasks, a builder agent, and a second
agent granted evidence acceptance.

1. **Ask the builder to implement a task and record evidence when it finishes.**
   - *Expect:* the evidence's commit contains the builder's files. Previously it named the commit
     from before the turn, and a strict reviewer would reject it.
2. **Ask the granted agent to review and accept.**
   - *Expect:* it accepts without a commit-mismatch complaint.
3. **Before approving, clear the project's main branch. Approve the task.**
   - *Expect:* "Not merged — this project has no main branch set", and a link to settings rather than
     a Try again button.
4. **Set the main branch in settings.**
   - *Expect:* the merge happens on save. No task reopening, no walking backwards through
     `revision_needed`.
5. **Make the project checkout dirty, approve another task, then commit and click Try again.**
   - *Expect:* a Try again button this time, and a merge when you press it.
6. **Look at a task card.**
   - *Expect:* a "Serves" block listing the requirement identifiers it is linked to, alongside the
     free-text requirements.
7. **Point a codex runner at a binary that exits non-zero and trigger three turns.**
   - *Expect:* the run error names the exit code and the method — not just "app-server process
     ended". By the third, the entry is abandoned with a reason and the agent accepts new input again.
8. **Make a types-only change under `hub/ui/src`, rebuild, `make ui`, commit.**
   - *Expect:* `/health` stops reporting `ui_stale` within thirty seconds, with no Hub restart.

**Where it would go wrong:** if step 1 still shows a stale commit, check the run reached the snapshot
path — a run that fails before `snapshot_worktree` never re-stamps, which is correct but looks
identical from the evidence list.
