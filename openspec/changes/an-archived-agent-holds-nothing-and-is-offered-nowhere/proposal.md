# Proposal — an archived agent holds nothing and is offered nowhere

**Round 1, 2026-09-20 (day window); re-derived against the code by Round 2, 2026-09-20.**
Findings: **F185 (B)**, **F181 (C)**, **F390 (C)**. The remedy was decided on 2026-09-19
(`spec-queue/DECISIONS.md:637`) — *clear an archived agent's bindings at source* — so R1's job was
the directory and the exploration, not the argument. **R2 re-opened the code independently and
corrected four claims in this proposal**; what changed is listed in `design.md`'s Round 2 section.
R3 has not run.

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
   carries — **R2 widened what it covers**: whether this change accepts a `hub/ui/src` bundle
   refresh at all, which would reach the operator's live app, and which now covers two halves —
   disabling that picker for an archived agent while surfacing the server's sentence, and rendering
   what archive/unarchive say, which nothing does today (`design.md` D9). The change is complete
   and shippable without either half.
5. **`Agent.runner_id` is deliberately *not* cleared**, though the decision said "bindings" in the
   plural. `list_agents` derives an archived agent's runner and display model from the live binding
   and from nothing else (`agents.py:517-524`, `:568-569`), and the agent's own settings page
   resolves an archived agent through `?lifecycle=archived` — so clearing it would blank that row
   with no fallback. **R2 corrected the reason R1 gave for this.** R1 argued the two bindings differ
   in kind ("a runner records what it ran with"); they do not — `TurnUsage`
   (`db/models.py:1235-1248`) already records the runner and model of every run and survives
   archival untouched, and `patch_agent` treats the two bindings identically. The asymmetry is a
   display dependency, not a principle, and it has a price: **F390 and tasks group 5 exist because
   of it.** `design.md` D3 states the trade on those terms for R3 to weigh.

## What changes

0. `PATCH /agents/{name}` refuses to bind a charter to an archived agent, naming unarchiving as the
   repair. Clearing a binding stays permitted. Without this, nothing below stays fixed.
1. `agent_lifecycle.archive` releases the charter binding. An archived agent holds no charter, so
   `charters.py:95-98` can no longer name one — the wall is removed at source rather than by a
   filter at each reader.
2. The archive response states which charter it released; the unarchive response states that no
   charter is bound, that archival is why, and that reopening does not restore it. **R2: no screen
   renders either response today** — `useArchiveAgent`'s `onSuccess` takes no argument
   (`hub/ui/src/api/agents.ts:214-241`), so the body is discarded. These are true API facts that no
   operator can currently read, which is why this change does **not** claim to tell the operator
   anything; `design.md` D9 states why the group is kept anyway and folds rendering it into the one
   operator decision below.
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
- **No UI change, no bundle refresh — and R2 priced that.** Nothing under `hub/ui/src` reads
  `/agents/launchability` (zero call sites; a drive measured 41 requests with the agent rail open
  and none to that route), so F181's fix here is **preventive** rather than user-visible. The
  archive/unarchive responses only gain fields, and nothing reads those either. The cost of holding
  the line at the API is that two operator-facing halves stay undone — the archived agent's
  `CharterPicker`, and rendering what archive/unarchive now say — and both are folded into the one
  decision this change carries.
- **Affected specs:** `agent-configuration` (MODIFIED), `runner-registry` (MODIFIED + ADDED),
  `agent-charter` (ADDED).
- **Shares no file with item 2 of today's `DIRECTION.md`** (`hub/hub/config.py`), nor with
  `a-refused-capability-reaches-the-operator` or `an-unstaffed-review-names-its-holders`.
- **Behaviour change an operator can notice:** an agent's charter binding does not survive
  archival. That is the decided remedy, and it is stated in the spec rather than left implicit.
