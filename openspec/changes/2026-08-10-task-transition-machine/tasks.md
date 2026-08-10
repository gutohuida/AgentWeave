# Tasks — task transition machine (B1)

Written to the standing directive of 2026-08-10: every task states whether the **agent** can verify
it or whether it needs the **operator**, and section 7 is the guide for the operator's half.

## 1. The transition map

- [ ] 1.1 Create `hub/hub/task_transitions.py` declaring the map from `design.md` D5 as edges that
      carry their permitted actor kinds. One declaration, no second copy of the status list.
- [ ] 1.2 Define the actor type the service takes: kind (`run` | `operator`) plus an optional run id.
      This is what D2 replaces the bare `Optional[str]` with.
- [ ] 1.3 Add `hub/tests/test_task_transitions.py` asserting the map's key set equals
      `TASK_STATUSES` in `src/agentweave/constants.py:280` **and** `_TASK_STATUSES` in
      `hub/hub/schemas/tasks.py:15`, so a ninth status cannot be added without declaring its edges.
      *Agent-verifiable: the test fails when a status is added to one list only.*
- [ ] 1.4 Unit-test the map directly: every legal edge accepted for its declared actors, a
      representative illegal edge refused, `in_progress → approved` refused, and every
      operator-only edge refused for a run. *Agent-verifiable.*

## 2. The history table

- [ ] 2.1 Add the `TaskTransition` model to `hub/hub/db/models.py` — `id`, `project_id`, `task_id`
      (FK `tasks.id`), `from_status`, `to_status`, `actor_kind`, `run_id` (nullable), `created_at`;
      index `(task_id, created_at)`.
- [ ] 2.2 Write the migration after `0051_add_queue_entry_spec_document`, **guarded for a missing
      `tasks` table** in the manner of `0033`/`0034` (`CLAUDE.md`), with a `downgrade` that drops the
      table. No data migration — the table starts empty (D8).
- [ ] 2.3 Bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py`. Both are required by `CLAUDE.md`.
      *Agent-verifiable: `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py`.*
- [ ] 2.4 Verify the migration applies from an early revision, not only from `0051` — the guard in
      2.2 exists because upgrades reach it with only that revision's tables. *Agent-verifiable.*

## 3. The service

- [ ] 3.1 Implement `record_transition` and the reads the rules need — most recent transition into a
      given status, and full history for a task. **No update or delete path** (D4).
- [ ] 3.2 Implement the legality check: refuse an undeclared edge, and refuse a declared edge whose
      permitted actors exclude the caller. The refusal carries the current status and the set
      reachable *by that actor*.
- [ ] 3.3 Implement author/reviewer separation: refuse `approved`, `rejected` or `revision_needed`
      from `under_review` when the requesting run is the run that recorded the move into `completed`.
      Read it from the history, never from `Task.updated_by_run_id` — that column is the thing that
      gets overwritten.
- [ ] 3.4 Implement the same-status no-op (D7): succeed, record nothing.
- [ ] 3.5 Add a test asserting no application code path updates or deletes a `task_transitions` row.
      *Agent-verifiable — grep-style assertion over the Hub package, in the spirit of the existing
      source-contract tests in `hub/ui/src/__tests__/hubVisualLanguage.test.ts`.*

## 4. Wiring it in

- [ ] 4.1 Change `update_task_for_actor` (`hub/hub/api/v1/tasks.py:172`) to take the explicit actor
      (D2) and to route every status change through the service. Non-status fields keep their
      current behaviour.
- [ ] 4.2 Update the operator route (`hub/hub/api/v1/tasks.py:214`) to pass an operator actor, and
      the agent route (`hub/hub/api/v1/agent_actions.py:234`) to pass a run actor. After this, no
      caller infers operator-ness from a null run id.
- [ ] 4.3 Map refusals to their status codes: **409** for an illegal transition, **403** for an
      actor rule (D6), each with a detail naming the reason and the reachable set.
- [ ] 4.4 Keep `Task.updated_by_run_id` written as today. It stays the materialised latest writer;
      the history is what the rules read. Removing it is not in this change.
- [ ] 4.5 Confirm the SSE `task_updated` broadcast still fires on an accepted transition and does
      **not** fire on a refusal. *Agent-verifiable.*

## 5. The MCP surface

- [ ] 5.1 Verify a refusal reaches the agent as a tool failure: `_hub_request`
      (`hub/hub/mcp_server.py:132-162`) already raises `HubAPIError` on non-2xx, so this is a test,
      not new code. Assert it is not converted into an empty or successful result.
- [ ] 5.2 Assert the failure text survives `_readable_detail` with the reachable set intact — a
      refused agent's only feedback is that string, and an unreadable one produces blind retries.
- [ ] 5.3 If anything about the map or statuses ends up restated in `hub/hub/mcp_server.py`, add the
      agreement test `CLAUDE.md` requires. Prefer not restating it at all.

## 6. Fallout and agent verification

- [ ] 6.1 Run `pytest hub/tests/` and triage every failure: each is either a fixture making a move
      the map forbids (fix the fixture) or evidence the map is too strict (fix the map, with a note
      in `design.md` D5). Expected per the Risks section — not a surprise.
- [ ] 6.2 Run `pytest tests/` — the CLI's `TASK_STATUSES` is read by 1.3 and should be untouched
      otherwise.
- [ ] 6.3 End-to-end against a running Hub in `testbed/`, **not the repo root**: an agent run
      completes a task, the same run's approval is refused with 403, a second run's approval
      succeeds, and the history shows both runs. *Agent-verifiable via the API.*
- [ ] 6.4 Confirm a task created before the migration transitions normally and starts its history at
      that transition, with nothing invented before it (D8). *Agent-verifiable.*
- [ ] 6.5 Update `openspec/specs/` via `openspec-sync-specs` once the behaviour is real — not before.

## 7. Human-only verification — the operator's guide

None of the below can be verified by the agent: each is a judgement about whether the refusal is
*usable*, or an operator-role action the agent cannot authentically perform.

- [ ] 7.1 **Does a refusal tell you what to do next?** In `testbed/`, drive an agent to approve its
      own completed task. Read the error it receives in the conversation.
      **Expect:** it names the current status and what the actor can move to, and the agent
      self-corrects rather than retrying the same call.
      **Failure looks like:** the agent retries identically, or reports a generic failure with no
      status named.
- [ ] 7.2 **Is the lifecycle workable in a single-operator project?** Take a task from `pending` to
      `approved` yourself through the UI, with no second agent involved.
      **Expect:** every step is available to you, including approving work you completed.
      **Failure looks like:** any point where you are stuck and the only exit is editing the
      database.
- [ ] 7.3 **Is early rejection reachable where you would want it?** Reject a task from `pending`, and
      again from `in_progress`.
      **Expect:** both succeed for you and are recorded as operator actions.
      **Failure looks like:** a refusal — meaning the operator-only edges did not land.
- [ ] 7.4 **Is reopening honest?** Approve a task, then reopen it to `revision_needed`.
      **Expect:** it reopens and the original approval is **still in the history**, not replaced.
      **Failure looks like:** the earlier transitions vanish or are rewritten.
- [ ] 7.5 **Does `completed → under_review` earn its place?** After using the lifecycle for a few
      real tasks, judge whether the separate review hop is meaningful or an empty formality an agent
      always performs twice in a row.
      **Expect:** a decision, recorded in `design.md` — collapsing it is a map edit (Risks).
      **This one has no pass/fail; it is the question the design flagged and only use can answer.**

## 8. Closeout

- [ ] 8.1 All of section 7 answered by the operator, with 7.5's decision written into `design.md`.
- [ ] 8.2 `pytest hub/tests/`, `pytest tests/`, and `npx openspec validate --changes --strict` green,
      with real output recorded.
- [ ] 8.3 Archive via `openspec-archive-change` — **not** before 8.1. A plan existing is not a task
      complete (`CLAUDE.md`).
