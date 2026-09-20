# Proposal — an archived agent holds nothing and is offered nowhere

**Round 1, 2026-09-20 (day window).** Findings: **F185 (B)**, **F181 (C)**. The remedy was decided
on 2026-09-19 (`spec-queue/DECISIONS.md:637`) — *clear an archived agent's bindings at source* —
so R1's job was the directory and the exploration, not the argument. It is queued for R2 and R3.

## Why

`agent_lifecycle.archive` (`hub/hub/agent_lifecycle.py:64-67`) sets `lifecycle` and `archived_at`
and nothing else. Every binding the agent held on the way in it still holds on the way out, and two
queries read those bindings without asking whether the agent is still in the roster:

- **F185 (B).** `charters.py:95-98` selects `Agent.name WHERE Agent.charter_id == charter_id` with
  no lifecycle predicate. Delete a charter held only by an archived agent and the answer is
  `409 "Charter is bound to agent(s): aq2. Unbind before deleting."` — then `GET /agents` does not
  show `aq2`, because the roster's one lifecycle filter (`agents.py:253-266`) correctly hides it.
  **The operator is stopped by a name they cannot find**, with nothing in the sentence saying the
  holder is archived or that `?lifecycle=archived` is where it lives.
- **F181 (C).** `get_agents_launchability` (`agents.py:159-243`) iterates
  `select(Agent).where(Agent.project_id == project_id)` with no lifecycle predicate and reports an
  archived agent `runnable: true` — one call after `POST /agent/trigger` refused the same agent
  with *"is archived and cannot be triggered"* (`agent_trigger.py:661`, `:1370`). The route's own
  docstring says it feeds *"the agent/runner selector"*, and `list_agents` states in prose that its
  one filter *"is what removes them from every surface that offers an agent"*. This is the second
  surface that offers an agent, and it is outside that filter.

The roster's own comment names the failure mode this change closes: *"Adding the filter at each call
site instead would mean one missed site leaves an archived agent selectable."* Two sites were
missed. R1 found a third (below).

## What R1 found that the findings did not say

1. **The same wall stands at a third site — now filed as F390 (C).** `runners.py:175-183` is `charters.py:95-98`
   with one word changed — `Runner is bound to agent(s): {names}. Unbind before deleting.`, no
   lifecycle predicate. An archived agent walls off deletion of its runner exactly as it walls off
   its charter. It is handled here rather than left for a fourth round to rediscover, but it is
   **the one part of this change that is safe to cut** if the operator wants the blast radius held
   to `DIRECTION.md`'s three files (`design.md`, D4).
2. **A data migration is required, or the fix cannot fire where it matters.** Clearing the binding
   in `archive()` only helps agents archived *afterwards*. Every agent already archived — including
   on the operator's live `:8000` database — keeps its `charter_id` and keeps walling its charter.
   `design.md` D5; migration `0105`.
3. **`/agents/launchability` still has no reader** (measured 2026-09-20: `useAgentLaunchability`
   is defined at `hub/ui/src/api/agents.ts:376-385` and has **zero** call sites in `hub/ui/src`).
   So F181's fix is API-only — **no UI bundle refresh, nothing reaches `:8000`'s app** — and F181's
   severity C is confirmed rather than assumed. This is also why it must be fixed now: whoever
   wires the indicator up (F178) inherits an archived agent in the selector.
4. **Releasing the binding on archival does not survive `PATCH /agents/{name}`.** That route
   accepts `charter_id`, validates only that the charter exists in the project, and has no
   lifecycle check anywhere (`agents.py:2472-2478`) — so one ordinary API call, the same one the
   settings page's `CharterPicker` makes, puts an archived agent back into F185's state. Without
   the refusal this change adds, the fix is undoable by the surface that shipped with it
   (`design.md` D7). **One operator decision comes out of this** and is the only one the change
   carries: whether to also disable that picker for an archived agent and surface the server's
   sentence — a `hub/ui/src` change, therefore a bundle refresh, therefore the operator's live app.
   The change is complete and shippable without it.
5. **`Agent.runner_id` is deliberately *not* cleared**, though the decision said "bindings" in the
   plural. `list_agents` reads the bound runner to render an agent's runner and model
   (`agents.py:518`, `:568-569`), and the agent's own settings page resolves an archived agent
   through `?lifecycle=archived`. Clearing `runner_id` would blank what an archived agent ran with
   on the one screen that still shows it. `design.md` D3 states the distinction it rests on: a
   charter governs turns the agent will never take again; a runner records what it ran with.

## What changes

0. `PATCH /agents/{name}` refuses to bind a charter to an archived agent, naming unarchiving as the
   repair. Clearing a binding stays permitted. Without this, nothing below stays fixed.
1. `agent_lifecycle.archive` releases the charter binding. An archived agent holds no charter, so
   `charters.py:95-98` can no longer name one — the wall is removed at source rather than by a
   filter at each reader.
2. The archive response states which charter it released; the unarchive response states that no
   charter is bound and that archival is why. Reopening does not restore the binding, and the
   product says so rather than letting the operator find out at the next turn.
3. Migration `0105` clears `charter_id` for every already-archived agent.
4. `get_agents_launchability` gains the roster's lifecycle filter — the same `lifecycle` query
   parameter, the same default, applied in the same place, after every source has contributed a
   name, for the reason `list_agents` already gives.
5. `runners.py`'s bound-delete refusal names an archived holder *as archived*, with where to reach
   it — **F390**. (Cuttable — see above.)

## Impact

- **Affected code:** `hub/hub/agent_lifecycle.py`, `hub/hub/api/v1/agents.py`,
  `hub/hub/api/v1/charters.py` (comment + invariant test only), `hub/hub/api/v1/runners.py`,
  one new migration.
- **No UI change, no bundle refresh.** Nothing under `hub/ui/src` reads
  `/agents/launchability`, and the archive/unarchive responses only gain fields.
- **Affected specs:** `agent-configuration` (MODIFIED), `runner-registry` (MODIFIED + ADDED),
  `agent-charter` (ADDED).
- **Shares no file with item 2 of today's `DIRECTION.md`** (`hub/hub/config.py`), nor with
  `a-refused-capability-reaches-the-operator` or `an-unstaffed-review-names-its-holders`.
- **Behaviour change an operator can notice:** an agent's charter binding does not survive
  archival. That is the decided remedy, and it is stated in the spec rather than left implicit.
