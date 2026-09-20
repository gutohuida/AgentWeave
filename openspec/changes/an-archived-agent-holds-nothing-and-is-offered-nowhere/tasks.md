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

- [ ] 1.1 `hub/hub/agent_lifecycle.py` — `archive(agent)` sets `agent.charter_id = None` alongside
      `lifecycle` and `archived_at`. Extend the docstring with why: nothing runs an archived agent,
      so a bound charter governs nothing and only walls off the charter's deletion behind a name
      the default roster does not show (F185). Name the one thing it does **not** release —
      `runner_id` — and why (`design.md` D3), so the next reader does not "finish" the job.
- [ ] 1.2 `hub/hub/agent_lifecycle.py` — `unarchive(agent)` docstring states that the charter
      binding released on archive is **not** restored, and points at the response sentence in 2.2.
      No behaviour change in this function.
- [ ] 1.3 `hub/tests/test_agent_archival.py` — archiving an agent bound to a charter leaves
      `charter_id` NULL on the row, and leaves `runner_id` unchanged. *Mutation: delete the
      `charter_id = None` line; the first assertion must fail and the second must still pass.*
- [ ] 1.4 `hub/tests/test_charters_api.py` — F185's reproduction, end to end through the API:
      create a charter, create an agent bound to it, `POST /agents/{name}/archive` → 200,
      `GET /agents` omits it, `DELETE /charters/{id}` → **204**. *Mutation: as 1.3; the DELETE must
      go back to 409.*
- [ ] 1.5 `hub/hub/api/v1/charters.py` — no query change (an archived agent can no longer hold a
      charter). Add a comment above the `bound` select stating that invariant and naming
      `agent_lifecycle.archive` as what maintains it, so a future reader does not restore the
      binding without revisiting this route.
- [ ] 1.6 `hub/hub/api/v1/agents.py` `patch_agent` — refuse binding a charter to an archived agent
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
- [ ] 1.7 `hub/tests/test_agents.py` — `PATCH /agents/{archived}` with a `charter_id` is refused
      and the row is unchanged; the same call with `charter_id: null` succeeds; the same call with
      a `charter_id` on an **open** agent still succeeds. *Mutation: drop the lifecycle check; the
      first case must fail and the other two must pass.*
- [ ] 1.8 `hub/tests/test_charters_api.py` — the invariant itself, driven rather than asserted on a
      snapshot: after an archive and an attempted re-bind, no row in `agents` has both
      `lifecycle = 'archived'` and a non-NULL `charter_id`.

## 2. The archive and unarchive responses state the binding's fate (design D2, D9)

> **R2: nothing renders any of this today.** `useArchiveAgent` is the only client of both routes and
> its `onSuccess` takes no argument (`hub/ui/src/api/agents.ts:214-241`), so the response body is
> discarded. Every field and sentence below is a true API fact that **no operator can currently
> read**, and this group's tests will pass without that changing. The group is kept deliberately —
> `design.md` D9 says why — but it MUST NOT be described as telling the operator anything.

- [ ] 2.1 `hub/hub/api/v1/agents.py` `archive_agent` — read `agent_row.charter_id` **before**
      calling `archive_agent_row`, and return it in the response as `released_charter_id` alongside
      `charter_id: None`, plus a sentence naming the charter (by name, resolved from the `Charter`
      row) when one was released. No sentence when nothing was bound.
      **R3: this response is the only place the released charter's identity will exist.** Archival
      persists no event and broadcasts nothing (`design.md` D10) — there is no `agent_archived`
      event kind anywhere in the tree — so once `useArchiveAgent` discards the body the fact is
      irrecoverable from the Hub. Do not delete this field as dead payload on the strength of D9.
- [ ] 2.2 `hub/hub/api/v1/agents.py` `unarchive_agent` — response carries `charter_id: None`
      explicitly and the standing sentence, **as revised by R2**: *"No charter is bound. Archiving
      releases an agent's charter and unarchiving does not restore it. An agent with no charter
      still runs — bind one only if this agent should have one."* Use this wording, not R1's.
      R1's sentence ended *"so bind one before this agent's next turn"*, which implies a charter is
      required — `design.md` D8 measured the opposite — and never said the release is permanent,
      which is the one thing the operator's rider asked unarchive to say. Every clause of the
      revised sentence is true of an agent that never had a charter: its state, then the rule, then
      the product's behaviour, then a conditional rather than an instruction.
- [ ] 2.3 `hub/tests/test_agent_archival.py` — archive names the charter it released; archive of an
      unbound agent names none; unarchive carries `charter_id: None` and the standing sentence, and
      the same sentence comes back for an agent that never had a charter. Assert the revised
      wording from 2.2, including that it does **not** contain "before this agent's next turn".
      *Mutation: move the `charter_id` read in 2.1 to after the archive call; the "names the
      charter" assertion must fail.*
- [ ] 2.4 **No UI change is made, and R2 established what that costs.** Measured 2026-09-20:
      `useArchiveAgent` (`hub/ui/src/api/agents.ts:214-241`) serves both routes, types the response
      `{ name: string; lifecycle: string }`, and its `onSuccess` **takes no argument** — it
      invalidates the roster queries and returns, so the body is discarded rather than
      under-typed. Its only non-test caller is `AgentSettingsPage.tsx:224`. Re-confirm this at
      build time; if a component has begun rendering the raw response, this becomes a real UI task
      and the change acquires a bundle refresh (`make ui`) — **it does not have one today.**
- [ ] 2.5 Record the half-discharge in the change's own record, not only here: the operator's rider
      asked that unarchiving *say* the bindings are gone, and after this group the API says it while
      the app shows nothing. Whoever builds this SHALL state that in the commit message and SHALL
      NOT set `**Status:** fixed` on any finding on the strength of group 2 alone. Rendering it is
      part of the one operator decision this change carries (`design.md` D7, D9), not a separate
      follow-up to be invented at build time.

## 3. Already-archived agents (design D5)

> **This migration rewrites rows in the operator's live database** the next time they restart
> `:8000` (`.claude/rules/db-migrations.md`). It clears `charter_id` on agents they archived
> earlier, and the downgrade cannot put it back. That is the decided remedy, not a side effect —
> say it in the review page, not only here.

- [ ] 3.1 `hub/hub/migrations/versions/0105_clear_archived_agent_charter_bindings.py`, down-revision
      `0104` — `UPDATE agents SET charter_id = NULL WHERE lifecycle = 'archived'`. Guard for a
      missing `agents` table the way `0033`/`0034` do, because an upgrade from an early revision
      reaches this migration with only that revision's tables.
- [ ] 3.2 Same file — `downgrade()` is a documented no-op: the cleared bindings are not recoverable
      and the migration must not pretend otherwise.
- [ ] 3.3 No `models.py` change — `Agent.charter_id` is already nullable
      (`hub/hub/db/models.py:219-221`). Confirm this rather than assume it.
- [ ] 3.4 Bump the head assertions in `hub/tests/test_migrations.py` **and**
      `hub/tests/test_project_persistence.py` to `0105`.
- [ ] 3.5 `hub/tests/test_migrations.py` — a data test, not a schema test: seed an archived agent
      with a non-NULL `charter_id` at `0104`, upgrade, assert NULL; seed an **open** agent with a
      binding and assert it survives. *Mutation: drop the `WHERE lifecycle = 'archived'` clause;
      the second assertion must fail.*

## 4. Launchability applies the roster's lifecycle filter (design D6, closes F181)

- [ ] 4.1 `hub/hub/api/v1/agents.py` `get_agents_launchability` — add
      `lifecycle: Literal["open", "archived", "all"] = Query("open")`, matching `list_agents`'
      signature exactly.
- [ ] 4.2 Same function — apply the filter **after** `session_agents_meta` has taken names from both
      sources and **before** the per-name loop (which does a `get_agent_config` and a `Runner`
      lookup per agent), using the same "an agent with no row cannot have been archived, so it
      counts as open" rule as `agents.py:359-369`. Extend the docstring with one paragraph pointing
      at `list_agents`' reasoning rather than restating it.
- [ ] 4.3 `hub/tests/test_agents.py` (or the launchability test module R2 identifies) — archive an
      agent, then: default probe omits it; `?lifecycle=archived` returns it; `?lifecycle=all`
      returns both; an archived name present *only* in session config is omitted too.
      *Mutation: move the filter onto the `Agent` query instead; the session-config case must fail.*
- [ ] 4.4 The probe/spawn agreement, driven as one sequence in the same test: for every agent the
      default probe reports `runnable: true`, `POST /agent/trigger` does not refuse it as archived.
      This is the assertion F181 actually violates — write it as the loop over the response, not as
      a single hand-picked agent.
- [ ] 4.5 Confirm again at build time that nothing under `hub/ui/src` calls
      `useAgentLaunchability` (measured zero call sites on 2026-09-20). If that has changed, the
      default's effect on that screen must be looked at before shipping.

## 5. The third site — `runners.py` (design D4). **Cut this group first.**

- [ ] 5.1 `hub/hub/api/v1/runners.py` `delete_runner` — select `Agent.name` **and**
      `Agent.lifecycle`, and qualify each archived holder inline in the refusal, e.g.
      `Runner is bound to agent(s): a1, b2 (archived). Unbind before deleting; an archived agent is
      listed under Agents with the archived filter.` Open-only holders keep today's sentence
      unchanged.
- [ ] 5.2 `hub/tests/test_runners_api.py` — three cases: only-archived holder, mixed, only-open
      holder (the third asserts today's sentence is unchanged). *Mutation: drop the lifecycle
      column from the select; the first two must fail and the third must pass.*
- [ ] 5.3 Set `**Status:** fixed <sha>` on **F390** in `scripts/drive/FINDINGS.md` in the same
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
