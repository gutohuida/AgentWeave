# Tasks — task transition machine (B1)

Written to the standing directive of 2026-08-10: every task states whether the **agent** can verify
it or whether it needs the **operator**, and section 7 is the guide for the operator's half.

## 1. The transition map

- [x] 1.1 Create `hub/hub/task_transitions.py` declaring the map from `design.md` D5 as edges that
      carry their permitted actor kinds. One declaration, no second copy of the status list.
      *Done: 8 statuses, 18 edges. `allowed_map_for()` also serves D13's endpoint from the same
      declaration, so the client cannot hold a second copy either.*
- [x] 1.2 Define the actor type the service takes: kind (`run` | `operator`) plus an optional run id.
      This is what D2 replaces the bare `Optional[str]` with.
      *Done: frozen `Actor` that refuses a run without a run id **and** an operator carrying one —
      the second check is what makes the D2 privilege escalation unstateable rather than merely
      unlikely.*
- [x] 1.3 Add `hub/tests/test_task_transitions.py` asserting the map's key set equals
      `TASK_STATUSES` in `src/agentweave/constants.py:280` **and** `_TASK_STATUSES` in
      `hub/hub/schemas/tasks.py:15`, so a ninth status cannot be added without declaring its edges.
      *Done, and confirmed non-vacuous: both sets resolve to the same 8 through real imports.*
- [x] 1.4 Unit-test the map directly: every legal edge accepted for its declared actors, a
      representative illegal edge refused, `in_progress → approved` refused, and every
      operator-only edge refused for a run.
      *Done — 51 tests. Beyond the listed cases they also pin the structural invariants: no
      self-edge (D7 is the service's job, not an edge), no edge to an undeclared status, the
      operator's set a superset of the agent's everywhere, and the operator still refused an
      undeclared move (D9).*

## 2. The history table

- [x] 2.1 Add the `TaskTransition` model to `hub/hub/db/models.py` — `id`, `project_id`, `task_id`
      (FK `tasks.id`), `from_status`, `to_status`, `actor_kind`, `run_id` (nullable), `created_at`;
      index `(task_id, created_at)`.
- [x] 2.2 Write the migration after `0051_add_queue_entry_spec_document`, **guarded for a missing
      `tasks` table** in the manner of `0033`/`0034` (`CLAUDE.md`), with a `downgrade` that drops the
      table. No data migration — the table starts empty (D8).
- [x] 2.3 Bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py`. Both are required by `CLAUDE.md`.
      *Agent-verifiable: `pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py`.*
- [x] 2.4 Verify the migration applies from an early revision, not only from `0051` — the guard in
      2.2 exists because upgrades reach it with only that revision's tables. *Agent-verifiable.*

## 3. The service

- [x] 3.1 Implement `record_transition` and the reads the rules need — most recent transition into a
      given status, and full history for a task. **No update or delete path** (D4).
- [x] 3.2 Implement the legality check: refuse an undeclared edge, and refuse a declared edge whose
      permitted actors exclude the caller. The refusal carries the current status and the set
      reachable *by that actor*.
- [x] 3.3 Implement author/reviewer separation: refuse `approved`, `rejected` or `revision_needed`
      from `under_review` when the requesting run is the run that recorded the move into `completed`.
      Read it from the history, never from `Task.updated_by_run_id` — that column is the thing that
      gets overwritten.
- [x] 3.4 Implement the same-status no-op (D7): succeed, record nothing.
- [x] 3.5 Add a test asserting no application code path updates or deletes a `task_transitions` row.
      *Agent-verifiable — grep-style assertion over the Hub package, in the spirit of the existing
      source-contract tests in `hub/ui/src/__tests__/hubVisualLanguage.test.ts`.*

## 4. Wiring it in

- [x] 4.1 Change `update_task_for_actor` (`hub/hub/api/v1/tasks.py:172`) to take the explicit actor
      (D2) and to route every status change through the service. Non-status fields keep their
      current behaviour.
- [x] 4.2 Update the operator route (`hub/hub/api/v1/tasks.py:214`) to pass an operator actor, and
      the agent route (`hub/hub/api/v1/agent_actions.py:234`) to pass a run actor. After this, no
      caller infers operator-ness from a null run id.
- [x] 4.3 Map refusals to their status codes: **409** for an illegal transition, **403** for an
      actor rule (D6), each with a detail naming the reason and the reachable set.
- [x] 4.4 Keep `Task.updated_by_run_id` written as today. It stays the materialised latest writer;
      the history is what the rules read. Removing it is not in this change.
- [x] 4.5 Confirm the SSE `task_updated` broadcast still fires on an accepted transition and does
      **not** fire on a refusal. *Agent-verifiable.*

## 5. Creation, and levelling the transports

Found by the 2026-08-10 scan; the machine was walkable around before this section existed.

- [x] 5.1 Restrict creation to the entry statuses `pending` and `assigned` in
      `create_task_for_actor` (`hub/hub/api/v1/tasks.py:65-70`) — the single `Task(` construction
      site, so one place covers every caller.
- [x] 5.2 Narrow `AgentTaskCreate.status` (`hub/hub/api/v1/agent_actions.py:71`) and
      `TaskCreate.status` (`hub/hub/schemas/tasks.py`) to the entry statuses, so the refusal is a
      schema error where it can be and a service error where it cannot.
- [x] 5.3 Confirm creation records **no** transition (D10), and that a created task's first history
      entry is its first actual move. *Agent-verifiable.*
- [x] 5.4 Test that `POST /agent-actions/tasks` with `status: "approved"` is refused — this is the
      hole the scan found, and the test is the proof it is shut. *Agent-verifiable.*
- [x] 5.5 Assert HTTP and MCP agree on create: neither exposes a status the other does not
      (`agent-capability-plane`). MCP's `create_task` (`hub/hub/mcp_server.py:206`) exposes none
      today, so this is satisfied by narrowing HTTP — verify, do not widen MCP.

## 6. The MCP surface

- [x] 6.1 Verify a refusal reaches the agent as a tool failure: `_hub_request`
      (`hub/hub/mcp_server.py:132-162`) already raises `HubAPIError` on non-2xx, so this is a test,
      not new code. Assert it is not converted into an empty or successful result.
- [x] 6.2 Assert the failure text survives `_readable_detail` with the reachable set intact — a
      refused agent's only feedback is that string, and an unreadable one produces blind retries.
- [x] 6.3 If anything about the map or statuses ends up restated in `hub/hub/mcp_server.py`, add the
      agreement test `CLAUDE.md` requires. Prefer not restating it at all.

## 7. The operator's status control

Without this, D9's operator-only edges exist in the API and nowhere in the product. The board is
read-only today: `useUpdateTask` (`hub/ui/src/api/tasks.ts:34`) has no callers.

- [x] 7.1 Add the actor-scoped map endpoint decided in **D13**: returns the caller's own
      `{from_status: [reachable...]}` from the same declaration the service enforces. Not a field on
      the task response, and not per-task — see D13 for why both were rejected. One React Query hook
      fetches it; the card derives its options by looking up its own status.
- [x] 7.2 Add a status action to `hub/ui/src/components/tasks/TaskCard.tsx` offering **only** the
      operator-legal transitions from the current status, wired to the existing `useUpdateTask`.
- [x] 7.3 Surface a refusal usefully if one still occurs — a stale board can offer a move that
      became illegal. The 409/403 detail is already written for humans; show it rather than a
      generic failure.
- [x] 7.4 Component test: a task in each status offers exactly the operator-legal set and nothing
      else; a task in `approved` offers `revision_needed` and not `in_progress`.
      *Agent-verifiable via vitest.*
- [x] 7.5 `npm run build`, copy `hub/ui/dist` over `hub/hub/static/ui`, confirm with `diff -rq`
      (`CLAUDE.md`). Replace the directory rather than copying into it — stale hashed assets
      otherwise survive and the diff fails.

## 8. Fallout and agent verification

- [x] 8.1 Run `pytest hub/tests/` and triage failures: each is either a fixture making a move the
      map forbids (fix the fixture) or evidence the map is too strict (fix the map, with a note in
      `design.md` D5). **Expected to be small** — a scan found only `test_codex_appserver.py`
      mentions `approved`/`under_review`, incidentally. If it is large, the map is wrong.
- [x] 8.2 Run `pytest tests/` — the CLI's `TASK_STATUSES` is read by 1.3 and should be untouched
      otherwise.
- [x] 8.3 Run `npx vitest run` and `npx tsc --noEmit` for section 7.
- [x] 8.4 End-to-end: an agent run completes a task, the same run's approval is refused with 403, a
      second run's approval succeeds, and the history shows both runs.
      *Done through the real ASGI app (`test_task_transitions_api.py`), over both routes. **The
      uvicorn instance on :8010 was deliberately not restarted** — it still runs pre-change code.
      What a live restart would have added over the ASGI tests is the migration meeting real data,
      and that was checked directly instead: a copy of the operator's database (alembic **0026**,
      7 real tasks) upgraded cleanly to 0052, kept all 7 rows, created the table, and backfilled
      nothing.*
- [x] 8.5 Confirm a task created before the migration transitions normally and starts its history at
      that transition, with nothing invented before it (D8).
      *Done twice: as a unit test, and against the live-data copy where `task_transitions` came out
      with **0 rows** beside 7 pre-existing tasks.*
- [x] 8.6 Update `openspec/specs/` via `openspec-sync-specs` once the behaviour is real — not before.

## 9. Human-only verification — the operator's guide

None of the below can be verified by the agent: each is a judgement about whether the refusal is
*usable*, or an operator-role action the agent cannot authentically perform. Every step uses the
status control from section 7 — before it exists, none of these are runnable.

- [ ] 9.1 **Does a refusal tell you what to do next?** In `testbed/`, drive an agent to approve its
      own completed task. Read the error it receives in the conversation.
      **Expect:** it names the current status and what the actor can move to, and the agent
      self-corrects rather than retrying the same call.
      **Failure looks like:** the agent retries identically, or reports a generic failure with no
      status named.
- [ ] 9.2 **Is the lifecycle workable in a single-operator project?** Take a task from `pending` to
      `approved` yourself, using only the card's status control and no second agent.
      **Expect:** every step is offered when you need it, including approving work you completed.
      **Failure looks like:** any point where the control offers nothing and the only exit is
      `curl` or the database.
- [ ] 9.3 **Does the control offer the right moves and no others?** At each status, read what it
      offers.
      **Expect:** it matches the map's operator column — no move that would be refused, and no
      missing one you wanted.
      **Failure looks like:** an offered move that then fails, which is the specific thing D11 set
      out to avoid.
- [ ] 9.4 **Is early rejection reachable where you would want it?** Reject a task from `pending`,
      and again from `in_progress`.
      **Expect:** both succeed and are recorded as operator actions.
      **Failure looks like:** the option is absent — meaning the operator-only edges did not land.
- [ ] 9.5 **Is reopening honest?** Approve a task, then reopen it to `revision_needed`.
      **Expect:** it reopens and the original approval is **still in the history**, not replaced.
      **Failure looks like:** the earlier transitions vanish or are rewritten.
- [ ] 9.6 **Does `completed → under_review` earn its place?** After using the lifecycle for a few
      real tasks, judge whether the separate review hop is meaningful or an empty formality an agent
      always performs twice in a row.
      **Expect:** a decision, recorded in `design.md` — collapsing it is a map edit (Risks).
      **This one has no pass/fail; it is the question the design flagged and only use can answer.**

## 10. Closeout

- [ ] 10.1 All of section 9 answered by the operator, with 9.6's decision written into `design.md`.
- [x] 10.2 `pytest hub/tests/`, `pytest tests/`, `npx vitest run`, `npx tsc --noEmit`, and
      `npx openspec validate --changes --strict` green, with real output recorded.
- [x] 10.3 `hub/hub/static/ui` refreshed and `diff -rq` clean (7.5).
- [ ] 10.4 Archive via `openspec-archive-change` — **not** before 10.1. A plan existing is not a task
      complete (`CLAUDE.md`).
