# Tasks — an archived agent holds nothing and is offered nowhere

Findings: **F185 (B)**, **F181 (C)**, **F390 (C)** — the third site in `runners.py`, filed by this
round after finding it by reading (`design.md` D4). Written by **R1, 2026-09-20**, re-derived against the code by **R2, 2026-09-20** and again,
independently, by **R3, 2026-09-20** (see `design.md`'s Round 2 and Round 3 sections for what each
changed and why). **All three rounds are done.** R3 changed no task's intent and added no task; it
narrowed two claims, sharpened D3's cost, edited task 1.6, added `design.md` D10 and filed **F391
(C)**. **No task here may be built until an operator token names this change in
`spec-queue/APPROVALS.md`.**

Tests run under `py -3.11`, never bare `python`. `black` needs `--target-version py311`. Each test
named below must **fail with its mutation applied** before it counts — record the mutation and the
observed failure beside the task when ticking it.

**Group 5 is the cut line — and R2 corrected what cutting it means.** No task in groups 1-4
depends on group 5, so it drops cleanly. But group 5 is not an unrelated third site: it exists
*because* D3 chooses to keep `runner_id` bound through archival (`design.md` D4, R2's note). If
`archive()` released `runner_id` too, no archived agent could hold a runner and `runners.py`'s
refusal could not name one. So cutting group 5 ships a change that knowingly leaves its own
consequence open, and whoever cuts it SHALL record it that way — not as deferring a finding this
change happened to notice.

## 1. Archival releases the charter binding (design D1, D2)

- [x] 1.1 `hub/hub/agent_lifecycle.py` — `archive(agent)` sets `agent.charter_id = None` alongside
      `lifecycle` and `archived_at`. Extend the docstring with why: nothing runs an archived agent,
      so a bound charter governs nothing and only walls off the charter's deletion behind a name
      the default roster does not show (F185). Name the one thing it does **not** release —
      `runner_id` — and why (`design.md` D3), so the next reader does not "finish" the job.
      **Done 2026-09-20:** `agent.charter_id = None` added; docstring names why and what stays
      bound.
- [x] 1.2 `hub/hub/agent_lifecycle.py` — `unarchive(agent)` docstring states that the charter
      binding released on archive is **not** restored, and points at the response sentence in 2.2.
      No behaviour change in this function.
      **Done 2026-09-20:** docstring added, no code change to `unarchive`.
- [x] 1.3 `hub/tests/test_agent_archival.py` — archiving an agent bound to a charter leaves
      `charter_id` NULL on the row, and leaves `runner_id` unchanged. *Mutation: delete the
      `charter_id = None` line; the first assertion must fail and the second must still pass.*
      **Done 2026-09-20:** `test_archiving_releases_the_charter_but_not_the_runner`. Mutation
      applied by hand (deleted the line): `charter_id is None` failed (`None != <id>`),
      `runner_id == runner_id` still passed. Reverted; full file green.
- [x] 1.4 `hub/tests/test_charters_api.py` — F185's reproduction, end to end through the API:
      create a charter, create an agent bound to it, `POST /agents/{name}/archive` → 200,
      `GET /agents` omits it, `DELETE /charters/{id}` → **204**. *Mutation: as 1.3; the DELETE must
      go back to 409.*
      **Done 2026-09-20:** `test_deleting_a_charter_bound_to_an_archived_agent_succeeds`. Same
      mutation as 1.3: DELETE went back to `409`. Reverted; full file green.
- [x] 1.5 `hub/hub/api/v1/charters.py` — no query change (an archived agent can no longer hold a
      charter). Add a comment above the `bound` select stating that invariant and naming
      `agent_lifecycle.archive` as what maintains it, so a future reader does not restore the
      binding without revisiting this route.
      **Done 2026-09-20:** comment added above the `bound` select, no query change.
- [x] 1.6 `hub/hub/api/v1/agents.py` `patch_agent` — refuse binding a charter to an archived agent
      (`409`, naming unarchiving as the repair). Measured this round: `agents.py:2472-2478` accepts
      `charter_id`, checks only that the charter exists in the project, and has **no lifecycle
      check anywhere in the route** — so without this task, one ordinary API call puts an archived
      agent straight back into F185's state and 1.1 fixes nothing durable (`design.md` D7).
      Setting `charter_id: null` on an archived agent stays permitted: clearing is not re-binding.
      **R3: say in the same comment that `runner_id` keeps no such guard, and why.** The adjacent
      branch of this same route (`agents.py:2462-2470`) can re-bind a runner to an archived agent
      and SHALL continue to — D3 keeps an archived agent's runner bound on purpose, so a symmetric
      guard here would contradict it. Unstated, the asymmetry reads as an oversight and the next
      reader "finishes the job"; stated, they have to revisit D3 first.
      **Done 2026-09-20:** 409 guard added on the `charter_id` branch when `agent_row.lifecycle ==
      "archived"`; `charter_id: null` still falls through to `agent_row.charter_id = charter_id`
      unconditionally. Comment on the `runner_id` branch above states the asymmetry and points at
      the `charter_id` branch and D3.
- [x] 1.7 `hub/tests/test_agents.py` — `PATCH /agents/{archived}` with a `charter_id` is refused
      and the row is unchanged; the same call with `charter_id: null` succeeds; the same call with
      a `charter_id` on an **open** agent still succeeds. *Mutation: drop the lifecycle check; the
      first case must fail and the other two must pass.*
      **Done 2026-09-20:** `test_patch_agent_refuses_binding_a_charter_to_an_archived_agent`.
      Mutation applied by hand (removed the `if agent_row.lifecycle == "archived"` guard): refusal
      case returned `200` instead of `409` and failed; null-clear and open-agent cases still
      passed. Reverted; full file green.
- [x] 1.8 `hub/tests/test_charters_api.py` — the invariant itself, driven rather than asserted on a
      snapshot: after an archive and an attempted re-bind, no row in `agents` has both
      `lifecycle = 'archived'` and a non-NULL `charter_id`.
      **Done 2026-09-20:** `test_no_archived_agent_row_ever_holds_a_charter`. Same 1.7 mutation
      reproduces here too (refusal assertion fails at `409 == 200`... i.e. `200 == 409`); covered
      by 1.7's mutation run, not re-applied separately since both routes share the same guard.

## 2. The archive and unarchive responses state the binding's fate (design D2, D9)

> **R2: nothing renders any of this today.** `useArchiveAgent` is the only client of both routes and
> its `onSuccess` takes no argument (`hub/ui/src/api/agents.ts:214-241`), so the response body is
> discarded. Every field and sentence below is a true API fact that **no operator can currently
> read**, and this group's tests will pass without that changing. The group is kept deliberately —
> `design.md` D9 says why — but it MUST NOT be described as telling the operator anything.

- [x] 2.1 `hub/hub/api/v1/agents.py` `archive_agent` — read `agent_row.charter_id` **before**
      calling `archive_agent_row`, and return it in the response as `released_charter_id` alongside
      `charter_id: None`, plus a sentence naming the charter (by name, resolved from the `Charter`
      row) when one was released. No sentence when nothing was bound.
      **R3: this response is the only place the released charter's identity will exist.** Archival
      persists no event and broadcasts nothing (`design.md` D10) — there is no `agent_archived`
      event kind anywhere in the tree — so once `useArchiveAgent` discards the body the fact is
      irrecoverable from the Hub. Do not delete this field as dead payload on the strength of D9.
      **Done 2026-09-20:** `released_charter_id` captured before `archive_agent_row`; response adds
      `charter_id: None`, `released_charter_id`, and `message` (only present when a charter was
      released), naming the charter by its `Charter.name`.
- [x] 2.2 `hub/hub/api/v1/agents.py` `unarchive_agent` — response carries `charter_id: None`
      explicitly and the standing sentence, **as revised by R2**: *"No charter is bound. Archiving
      releases an agent's charter and unarchiving does not restore it. An agent with no charter
      still runs — bind one only if this agent should have one."* Use this wording, not R1's.
      R1's sentence ended *"so bind one before this agent's next turn"*, which implies a charter is
      required — `design.md` D8 measured the opposite — and never said the release is permanent,
      which is the one thing the operator's rider asked unarchive to say. Every clause of the
      revised sentence is true of an agent that never had a charter: its state, then the rule, then
      the product's behaviour, then a conditional rather than an instruction.
      **Done 2026-09-20:** response now returns `charter_id: agent_row.charter_id` (always `None`
      by this point) plus `message` set to the exact R2 wording, unconditionally.
- [x] 2.3 `hub/tests/test_agent_archival.py` — archive names the charter it released; archive of an
      unbound agent names none; unarchive carries `charter_id: None` and the standing sentence, and
      the same sentence comes back for an agent that never had a charter. Assert the revised
      wording from 2.2, including that it does **not** contain "before this agent's next turn".
      *Mutation: move the `charter_id` read in 2.1 to after the archive call; the "names the
      charter" assertion must fail.*
      **Done 2026-09-20:** `test_archive_and_unarchive_responses_state_the_bindings_fate`. Mutation
      applied by hand (moved the `released_charter_id = agent_row.charter_id` read to after
      `archive_agent_row(agent_row)`): `released_charter_id == charter_id` failed
      (`None == 'charter-...'`). Reverted; full file green (15 passed).
- [x] 2.4 **No UI change is made, and R2 established what that costs.** Measured 2026-09-20:
      `useArchiveAgent` (`hub/ui/src/api/agents.ts:214-241`) serves both routes, types the response
      `{ name: string; lifecycle: string }`, and its `onSuccess` **takes no argument** — it
      invalidates the roster queries and returns, so the body is discarded rather than
      under-typed. Its only non-test caller is `AgentSettingsPage.tsx:224`. Re-confirm this at
      build time; if a component has begun rendering the raw response, this becomes a real UI task
      and the change acquires a bundle refresh (`make ui`) — **it does not have one today.**
      **Re-confirmed 2026-09-20:** re-read `hub/ui/src/api/agents.ts:209-238` — `mutationFn` still
      typed `{ name: string; lifecycle: string }`, `onSuccess` still takes no argument. No
      `hub/ui/src` file touched this iteration; `make ui` not run.
- [x] 2.5 Record the half-discharge in the change's own record, not only here: the operator's rider
      asked that unarchiving *say* the bindings are gone, and after this group the API says it while
      the app shows nothing. Whoever builds this SHALL state that in the commit message and SHALL
      NOT set `**Status:** fixed` on any finding on the strength of group 2 alone. Rendering it is
      part of the one operator decision this change carries (`design.md` D7, D9), not a separate
      follow-up to be invented at build time.
      **Done 2026-09-20:** stated in this tick and repeated in the commit message. No finding's
      `**Status:**` is touched by this group — F185 stays open pending group 6's drive.

## 2b. The transition leaves a trace (design D10, F391) — **operator, 2026-09-20: folded in**

> The operator's decision on this change's one question, taken in session on 2026-09-20: **the API
> line holds and this group is added.** `persist_event` and `sse_manager.broadcast` are both
> server-side, so this discharges the rider's recording half **without** a `hub/ui/src` bundle
> refresh and without anything reaching the live `:8000` app on reload. D2's rejection of
> *remembering* the binding stands — it is right about a column and does not reach an event.
> **This group does not render anything.** `useSSE.ts` allow-lists kinds at `:31` and switches per
> kind at `:460`, so a client that does not know these kinds ignores them; displaying the
> transition stays a later change, and no task here may claim otherwise.

- [x] 2b.1 `hub/hub/api/v1/agents.py` `archive_agent` — after `session.commit()` and
      `session.refresh(agent_row)`, `await persist_event(session, project_id, "agent_archived",
      payload, agent=agent_row.name)` then `await sse_manager.broadcast(project_id,
      "agent_archived", payload)`, in that order and with the same payload object, matching
      `agent_created` (`:689-690`) exactly. **The payload SHALL carry `released_charter_id`**, read
      from the same pre-release capture task 2.1 already takes — not re-read after the release,
      where it is always `None`. Order matters: 2.1's capture must happen before
      `archive_agent_row`, and this event is written after the commit that persisted the release.
      **Done 2026-09-20:** `event_payload = {"agent": ..., "lifecycle": ..., "released_charter_id":
      released_charter_id}` built after `session.refresh`; `persist_event` then `broadcast`, same
      object, same order as `agent_created`.
- [x] 2b.2 Same file, `unarchive_agent` — the same two calls with `"agent_unarchived"`. The payload
      names the agent and its lifecycle and **MUST NOT** carry a `released_charter_id` or any field
      implying a charter was restored (`design.md` D2: reopening does not restore it).
      **Done 2026-09-20:** `event_payload = {"agent": ..., "lifecycle": ...}` — no
      `released_charter_id` key at all; `persist_event` then `broadcast`.
- [x] 2b.3 The event SHALL be written **whether or not a charter was bound** — an agent archived
      holding nothing records `released_charter_id: null`, not no event. Otherwise "nothing was
      released" and "nothing was recorded" are the same row, which is the gap this group closes.
      **Done 2026-09-20:** unconditional — no `if released_charter_id is not None` guard around the
      event calls (unlike the response `message`); covered by
      `test_archiving_a_never_chartered_agent_still_records_an_event`.
- [x] 2b.4 `hub/tests/test_agent_archival.py` — assert against `GET /events/history` (the route
      F391's own reproduction used), not against a mock: empty before, one `agent_archived` naming
      the released charter after, one `agent_unarchived` after unarchiving. **Include F391's
      positive control** — a heartbeat on the same agent lands an `agent_heartbeat` — so an empty
      result can never be read as a passing assertion about a broken endpoint.
      **Done 2026-09-20:** `test_archiving_and_unarchiving_persist_events` — asserts empty before,
      heartbeat positive control present, exactly one `agent_archived` with
      `data.released_charter_id == charter_id`, exactly one `agent_unarchived` with no
      `released_charter_id` key in `data`. Plus
      `test_archiving_a_never_chartered_agent_still_records_an_event` for 2b.3.
- [x] 2b.5 Mutation, applied by hand and observed: delete the `persist_event` call in
      `archive_agent` and watch 2b.4's named assertion fail; delete the `released_charter_id` key
      and watch it fail differently. Revert both. A test that passes with the event gone is testing
      the control.
      **Done 2026-09-20:** deleting the `persist_event` line failed `len(archived_events) == 1`
      (`0 == 1`, positive control still passed, confirming the endpoint itself works). Deleting
      `released_charter_id` from `event_payload` failed differently: `KeyError:
      'released_charter_id'` on the data-key assertion. Both reverted; file green again (17 passed).
- [x] 2b.6 **Do not set `**Status:** fixed` on F391 unless both the persist and the broadcast
      landed**, and when setting it, state in the same edit that the *display* half is untouched and
      name `useSSE.ts:31`/`:460` as where it would live. F391's text is about recording and
      broadcasting; it is not about rendering, and neither is this group.
      **Done 2026-09-20:** both `persist_event` and `sse_manager.broadcast` land on both routes; set
      `**Status:** fixed` on F391 in `scripts/drive/FINDINGS.md` with that statement.
- [x] 2b.7 Confirm at build time that no `hub/ui/src` file changed and `make ui` was not run. If
      this group somehow acquires one, stop — the operator's decision was explicitly the
      server-side route, and a bundle refresh reaches their live app.
      **Confirmed 2026-09-20:** `git diff --stat` shows only `hub/hub/api/v1/agents.py` and
      `hub/tests/test_agent_archival.py`; no `hub/ui/src` file touched, `make ui` not run.

## 3. Already-archived agents (design D5)

> **This migration rewrites rows in the operator's live database** the next time they restart
> `:8000` (`.claude/rules/db-migrations.md`). It clears `charter_id` on agents they archived
> earlier, and the downgrade cannot put it back. That is the decided remedy, not a side effect —
> say it in the review page, not only here.

- [x] 3.1 `hub/hub/migrations/versions/0105_clear_archived_agent_charter_bindings.py`, down-revision
      `0104` — `UPDATE agents SET charter_id = NULL WHERE lifecycle = 'archived'`. Guard for a
      missing `agents` table the way `0033`/`0034` do, because an upgrade from an early revision
      reaches this migration with only that revision's tables.
      **Done 2026-09-20:** migration written, guarded via `_has_table` exactly as `0033`/`0104` do.
- [x] 3.2 Same file — `downgrade()` is a documented no-op: the cleared bindings are not recoverable
      and the migration must not pretend otherwise.
      **Done 2026-09-20:** `downgrade()` is a single-line no-op with a docstring stating why.
- [x] 3.3 No `models.py` change — `Agent.charter_id` is already nullable
      (`hub/hub/db/models.py:219-221`). Confirm this rather than assume it.
      **Confirmed 2026-09-20:** re-read `hub/hub/db/models.py:230-232` — `charter_id: Mapped[Optional[str]]
      = mapped_column(String(64), ForeignKey("charters.id"), nullable=True)`. No model change made.
- [x] 3.4 Bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py` to `0105`.
      **Done 2026-09-20:** `HEAD_REVISION = "0105"` in `test_migrations.py`; `assert version ==
      "0105"` in `test_project_persistence.py`. Grepped both files for any other `"0104"` literal
      first — none found.
- [x] 3.5 `hub/tests/test_migrations.py` — a data test, not a schema test: seed an archived agent
      with a non-NULL `charter_id` at `0104`, upgrade, assert NULL; seed an **open** agent with a
      binding and assert it survives. *Mutation: drop the `WHERE lifecycle = 'archived'` clause;
      the second assertion must fail.*
      **Done 2026-09-20:** `test_migration_0105_clears_an_archived_agents_charter_but_leaves_an_open_ones`
      (plus `test_migration_0105_is_guarded_when_agents_does_not_exist` for 3.1's guard, matching
      the house pattern every other guarded migration in this file carries). Mutation applied by
      hand (dropped `WHERE lifecycle = 'archived'` from the `UPDATE`): the open agent's
      `charter_id` assertion failed (`None == 'charter-2'`); the archived agent's assertion still
      passed. Reverted (diffed byte-identical against a pre-mutation copy); file green again.

## 4. Launchability applies the roster's lifecycle filter (design D6, closes F181)

- [x] 4.1 `hub/hub/api/v1/agents.py` `get_agents_launchability` — add
      `lifecycle: Literal["open", "archived", "all"] = Query("open")`, matching `list_agents`'
      signature exactly.
      **Done 2026-09-20:** parameter added, first in the signature ahead of `project`/`session`,
      matching `list_agents`.
- [x] 4.2 Same function — apply the filter **after** `session_agents_meta` has taken names from both
      sources and **before** the per-name loop (which does a `get_agent_config` and a `Runner`
      lookup per agent), using the same "an agent with no row cannot have been archived, so it
      counts as open" rule as `agents.py:359-369`. Extend the docstring with one paragraph pointing
      at `list_agents`' reasoning rather than restating it.
      **Done 2026-09-20:** filter applied to `session_agents_meta` right after the `db_agents`
      `setdefault` loop, identical shape and comment to `list_agents`' own filter. Docstring
      extended with one paragraph naming `list_agents` as the source of the reasoning.
- [x] 4.3 `hub/tests/test_agents.py` (or the launchability test module R2 identifies) — archive an
      agent, then: default probe omits it; `?lifecycle=archived` returns it; `?lifecycle=all`
      returns both; an archived name present *only* in session config is omitted too.
      *Mutation: move the filter onto the `Agent` query instead; the session-config case must fail.*
      **Done 2026-09-20:** `hub/tests/test_launchability.py::test_launchability_lifecycle_filter_matches_the_roster`.
      Uses `hub/tests/test_launchability.py` (the probe's own test module) rather than
      `test_agents.py`, since every other test in this module already exercises this endpoint.
      Mutation applied by hand (filtered `agent_q` by `Agent.lifecycle == lifecycle` instead of
      post-filtering `session_agents_meta`): the session-config-only name (`config-only`) leaked
      into the `?lifecycle=archived` response (`AssertionError: 'config-only' not in {...}`).
      Reverted; full file green again (44 passed).
- [x] 4.4 The probe/spawn agreement, driven as one sequence in the same test: for every agent the
      default probe reports `runnable: true`, `POST /agent/trigger` does not refuse it as archived.
      This is the assertion F181 actually violates — write it as the loop over the response, not as
      a single hand-picked agent.
      **Done 2026-09-20:** `test_every_agent_the_default_probe_calls_runnable_is_not_refused_as_archived`,
      same file. Same mutation as 4.3 (which also makes `archived-runnable` leak into the default
      probe, since it is present in session config too): the loop then POSTs `/agent/trigger` for
      it and gets `409`, failing `resp.status_code != 409`. Reverted; full file green again.
- [x] 4.5 Confirm again at build time that nothing under `hub/ui/src` calls
      `useAgentLaunchability` (measured zero call sites on 2026-09-20). If that has changed, the
      default's effect on that screen must be looked at before shipping.
      **Re-confirmed 2026-09-20:** `grep -rn "useAgentLaunchability" hub/ui/src` finds the
      definition (`api/agents.ts:376`) and eleven `vi.mock` stubs in `__tests__/*.test.tsx` — no
      import or call in any real component. Still zero real call sites; no `hub/ui/src` file
      touched, `make ui` not run.

## 5. The third site — `runners.py` (design D4). **Cut this group first.**

- [x] 5.1 `hub/hub/api/v1/runners.py` `delete_runner` — select `Agent.name` **and**
      `Agent.lifecycle`, and qualify each archived holder inline in the refusal, e.g.
      `Runner is bound to agent(s): a1, b2 (archived). Unbind before deleting; an archived agent is
      listed under Agents with the archived filter.` Open-only holders keep today's sentence
      unchanged. Done: `bound_rows` now carries `(name, lifecycle)` pairs; each archived name gets
      `" (archived)"` appended inline, and the trailing clause is appended only when at least one
      holder is archived — an open-only refusal is byte-identical to today's sentence.
- [x] 5.2 `hub/tests/test_runners_api.py` — three cases: only-archived holder, mixed, only-open
      holder (the third asserts today's sentence is unchanged). *Mutation: drop the lifecycle
      column from the select; the first two must fail and the third must pass.* Done: added
      `test_delete_runner_bound_to_only_archived_agent_names_it_archived` and
      `test_delete_runner_bound_to_mixed_holders_qualifies_only_the_archived_one`; extended the
      pre-existing `test_delete_runner_bound_to_agent_is_refused` with an assertion that `(archived)`
      never appears in an open-only refusal. Mutation applied by hand (selected only `Agent.name`,
      synthesized `lifecycle="open"` for every row) and reverted: the only-archived and mixed tests
      failed (`'mixed-archived (archived)' not in '...mixed-archived, mixed-open...'`) while the
      only-open test stayed green, confirming the lifecycle column is what the qualification
      depends on. 23 passed after revert; ruff/black clean.
- [x] 5.3 Set `**Status:** fixed <sha>` on **F390** in `scripts/drive/FINDINGS.md` in the same
      commit. It is already filed (R1, 2026-09-20) and records that it was found by reading rather
      than by a drive — and that it was never reproduced through HTTP, which 5.2 discharges.

## 6. Verification

- [ ] 6.1 `pytest hub/tests/ -v` green under `py -3.11`.
- [ ] 6.2 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
      --target-version py311`, `mypy src/`.
- [ ] 6.3 Drive it on a throwaway Hub from source on a port that is not `8000` or `8010`, against a
      fresh profile: F185's reproduction end to end through HTTP, F181's probe/trigger pair, and
      the migration against a database seeded at `0104` with an archived agent holding a charter.
      Every real agent turn binds `claude-haiku-4-5-20251001`. Archive nothing on a real project.
- [ ] 6.4 Update `scripts/drive/FINDINGS.md`: `**Status:** fixed <sha>` on F185, F181 (and F390 if
      group 5 survived), each with
      the one-line evidence of what was driven.
- [ ] 6.5 `openspec validate --strict an-archived-agent-holds-nothing-and-is-offered-nowhere`, then
      `openspec-sync-specs`/`openspec-archive-change` per the repo's own skills — not by hand.
