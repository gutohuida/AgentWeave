# Design — why queued input waits is told truthfully

## Operator review, 2026-09-24

The Opus adversarial review is in `spec-queue/tracks/reviews/B1-2026-09-24.md` §4 (verdict: approve
with fixes); the operator took no separate decision on this change. Applied here:

- **MEDIUM: D3 spawned git inside the polled status route, unguarded.** R2's D3 called
  `resolve_turn_workspace_inputs`, which runs `_integration_base` → `branch_exists` and
  `_prerequisite_commits` → `merge_targets` (`task_workspace.py:150-160`): raw
  `task_integration._git` spawns, F424's class (a `TimeoutExpired` becomes a 500, or blocks the
  loop for up to 60 s). D3 needs only the checkout's `task_id`, which `takes_own_checkout(task)`
  (`task_workspace.py:58-83`) answers from the row alone. D3 now calls that and drops base and
  prerequisites, and the whole of D3 is wrapped so that any exception falls through to D4.
- **LOW:** Collisions now names B3's F77 change, which edits `create_message_for_actor`'s refusal
  branch in the function whose return type D1 changes.

**Built on no operator decision.** D2 departs from ROUNDS.md's one-line sketch of S1 ("with a
written `waiting_reason`"); the reason is stated there. If the operator wants the entry written as
well, D2's alternative is the one extra write it names.

## D1 — The sender of a held message is told

`create_message_for_actor` (`hub/hub/api/v1/messages.py:32-319`) already knows the answer: it
computes `hop_depth` (`:77`) and compares it with `hop_budget` (`:57`, `:299`) to emit
`queue_chain_suspended`. It returns `msg`, and both send routes return that as `MessageResponse`
(`create_message`, `:322-352`; `agent_actions.send_peer_message`, `agent_actions.py:201-224`).

- `create_message_for_actor` returns the message and a `held: Optional[HeldByBudget]` (depth,
  budget). Both routes build the response from it.
- `MessageResponse` (`schemas/messages.py:52-65`) gains `held_by_hop_budget: Optional[bool] = None`
  and `delivery_note: Optional[str] = None`. `None` on every listed message, because the list
  routes do not compute it and `False` would be a claim.
- The note, built once in `messages.py` so the route and the tool cannot word it differently:
  *"Recorded as {msg.id}, but not delivered: this chain of messages has reached the project's hop
  budget ({depth} of {budget}). {recipient} receives it only if the operator continues the chain or
  raises the budget. Sending it again queues it at the same depth. Do not tell anyone it was
  delivered; if it matters now, ask the operator with ask_user."*
- `mcp_server.send_message` (`:236-244`) returns `{"success": True, "message_id": …}` as today and,
  when `result.get("held_by_hop_budget")`, adds `"held_by_hop_budget": True` and
  `"delivery_note": result.get("delivery_note")`. No import; the mcp-server rule's import
  restriction holds. `success` stays `True`: the message exists and can still be delivered
  (the delta says why a failure would be the wrong answer).

**Is `ask_user` itself held at that depth?** `ask_user` creates a question for the operator, not a
queue entry; a question is not bounded by the hop budget. R2 should confirm from `mcp_server.py`'s
`ask_user` and the question route that nothing in that path reads `turn_depth`.

**The operator's own send is never held** (`by_operator` → depth 0, `messages.py:58-63`), so the
operator's composer, which also posts to `POST /messages`, is unaffected.

## D2 — The held entry's `waiting_reason` is not written

The entry's reason is derivable from `hop_depth` and the project's budget, and every surface that
shows it derives it: the queue status (`inbound_queue.py:136-137`), the recipient's timeline
(`agent_chat.py:218`, `hop_budget_exceeded`), and the release control (`AgentTimeline.tsx:901`).
A stored copy is stale the moment the operator raises the budget
(`agent-conversation-workspace` *Raising the budget releases what it was holding*), and would then be
the fallback D4 labels as a past refusal, which it never was. `return_run_entries`' docstring records
the same judgement for the provider hold (`inbound_queue.py:253-254`: *"a stored copy would outlive
it (F97)"*).

*Alternative, if the operator wants it:* `entry.waiting_reason = "hop budget exhausted"` beside
the `queue_chain_suspended` emit (`messages.py:299`), cleared by `release_entry` (`inbound_queue.py:358-384`) and by the budget change.
Two writers to keep in step, for a reader that already has the fact.

## D3 — The checkout-holder refusal is checked now

The D8 refusal is raised in `trigger_agent_directly` when
`worktrees.takes_task_workspace(repo_root, config, task_id)` and
`tasks_held_by_a_running_turn(...)[task_id]` names another agent (`agent_trigger.py:989-1001`). The
status route can ask both: it already resolves the project workspace (`inbound_queue.py:159-172`) and
the agent's config (`:146`).

- **Which task** (R2, corrected; review 2026-09-24, narrowed). The trigger binds the turn by
  `resolve_bound_task(conversation=…, queue_entry_ids=<the selected entries>)`
  (`run_task_binding.py:402-440`, which reads only), then asks for the checkout's `task_id` — `None`
  for a grandfathered task or an id that cannot become a ref — and only then `takes_task_workspace`
  and the holder (`agent_trigger.py:966-1001`). The trigger gets that `task_id` from
  `resolve_turn_workspace_inputs`, which also computes the base and the prerequisites with raw git
  spawns (`task_workspace.py:150-160`); the route needs none of them. It computes the same `task_id`
  as `bound.id if task_workspace.takes_own_checkout(bound) else None` — the predicate
  `resolve_turn_workspace_inputs` itself asks first (`:146`), and whose docstring names it as the one
  implementation for exactly this reason (`:58-67`). The route runs it on the same **selected** set
  `_attempt_turn` would deliver: `select_turn(...).selected`, the function B11's F133 factors out of
  `_attempt_turn` (`turn_scheduler.py:340-367`); **this change is built on it** (see Collisions). A
  **review** controlling entry skips D3: a review turn never reaches the D8 check (the
  `elif review_context is not None` branch at `agent_trigger.py:948` pre-empts it).
- **The one git spawn left** is `worktrees.is_git_repo` inside `takes_task_workspace`
  (`worktrees.py:119-138`): guarded (`OSError`/`SubprocessError` answer `False`) and bounded at
  `_GIT_TIMEOUT_SECONDS` (30, `:68`). The route awaits `takes_task_workspace` through
  `asyncio.to_thread`, so a slow git delays this status read and not the Hub.
- **Wrapped whole.** Everything D3 does — `resolve_bound_task`, `takes_own_checkout`,
  `takes_task_workspace`, `tasks_held_by_a_running_turn` — runs inside one `try`; any exception is
  logged at warning level and the route falls through to D4. The status route is a diagnostic and
  must not 500 because one of its checks failed.
- **Where:** after the provider-hold and token-budget checks and the launchability probe, as one
  more live check before the fallback. The sentence is the trigger's own, moved into a shared
  function (`checkout_held_sentence(holder, task_id)`) so the two cannot drift.
- **When the check finds no holder,** the route falls through to D4.

The existing F97 test (`test_task_turn_collision.py:495-550`) stages exactly the live case (the
holder still running) and keeps passing, now from the live check rather than from the stored copy.

## D4 — The fallback says it is the last attempt's

`reason = next(entry.waiting_reason …)` (`inbound_queue.py:178`) becomes
`f"the last delivery attempt was refused: {stored}"`. F97's purpose (a reason rather than none) is
kept; the claim becomes one about the past. Where D3 would have named a holder and found none, this
is what the operator reads, with the old holder's name inside a sentence that says it is a record.

## What each route returns when the function it calls raises

- `POST /messages` and `POST /agent-actions/messages`: nothing new raises. `project_limits` is read
  already.
- `GET /queue/{agent}/status`: D3 adds `resolve_bound_task` and `tasks_held_by_a_running_turn`
  (reads), `takes_own_checkout` (no I/O) and `takes_task_workspace` (one guarded `git rev-parse`, off
  the loop). The route already calls `resolve_project_workspace` inside a `try` that turns
  `ProjectWorkspaceError` into a reason (`:168-172`). D3 runs only where that resolved, and **any**
  exception inside D3 falls through to D4 rather than raise (review 2026-09-24). No git spawn that
  can raise is on this route.

## Collisions with other changes (R2)

- **B11's F133** (no-spec, *queue status recomputes the reason*): the status route's token-budget
  branch reads every queued entry where the scheduler reads the selected turn. B11 recommends one
  shared read-only selection used by both. D3 needs exactly that selection. **Build order: F133's
  shared function lands strictly before this change** (as B11's no-spec fix); this change's task 2.0
  checks it exists and stops if it does not. F133 is carried by B11 only, not here.
- **B3 `an-agent-can-be-paused-and-keeps-its-input`** edits `get_queue_status` too (the pause
  reason). Order in the route: running → hop budget → pause/provider hold → token budget →
  launchability → workspace → **D3's holder check** → D4's labelled fallback → attempt count. D3 is
  placed after the pause, as B3's record asks.
- **B2 `stop-clears-a-run-an-earlier-hub-left-running`** rewrites the *"agent is already running"*
  sentence at the top of the same route (`inbound_queue.py:129`). Text only, a different branch;
  whichever lands second keeps the other's sentence.
- **B2 `a-retried-firing-records-how-its-work-ended`** edits the withdrawal route in the same file
  (`inbound_queue.py:259-272`) and the scheduler's refusal bookkeeping, not `get_queue_status` and
  not `waiting_reason`'s storage. No overlap; noted because the prompt listed it.
- **B11 `input-the-hub-accepted-is-answered-as-accepted`** (F349): `messages.py:318`, as recorded in
  the proposal.
- **B3's F77 change** (`a-message-to-the-operator-is-told-where-the-operator-reads`) edits `create_message_for_actor`'s refusal branch (`api/v1/messages.py`), the
  function whose return type D1 changes to `(msg, held)` (review 2026-09-24, LOW). Whichever lands
  second carries the other's edit: F77's refusal still raises before any `held` is computed, and D1's
  two callers unpack the pair.

## Residual

- No later briefing tells the sender what became of a held message (F361's second clause). The
  send answer is the moment the sender reads; a follow-up is a larger change.
- F376 (a chain never reset without a flow) is why chains reach the budget at all; not here.

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5`.
- **R2, 2026-09-24** (bundle B1): re-derived against the code. D3's "which task" corrected: the
  trigger binds through `resolve_bound_task` over the **selected** entries and asks
  `resolve_turn_workspace_inputs` before `takes_task_workspace`; the route must do the same, on the
  selection B11's F133 factors out (build F133 first); a review controlling entry skips D3. D1's open
  check answered: `ask_user` is not bounded by the hop budget — its answer is queued at hop 0
  (`api/v1/questions.py:168`, `:203`) and `agent_actions.py` reads no `turn_depth`. `MessageResponse`
  consumers: the SSE `message_created` payload is `_msg_dict` (`messages.py:418`), independent of the
  schema; the schema is `from_attributes`, so the routes must build the response with the two fields
  set rather than return the ORM row. Held on re-reading: `messages.py:57-77`, `:299-319`;
  `agent_actions.py:201-224`; `mcp_server.py:236-244` posts to `/api/v1/agent-actions/messages`; the
  status route's fallback at `inbound_queue.py:178`.
- **R3, 2026-09-24** (bundle B1): re-derived against the code. No correction. Held: `waiting_reason` has one writer (`turn_scheduler.py:475`, a refusal's words) and one clearer (`inbound_queue.py:191`), so D4's *"the last delivery attempt was refused"* is true of every stored value; the status route's order and fallback (`api/v1/inbound_queue.py:127-178`). Neighbour checked: B2's `an-undelivered-message-says-how-its-last-attempt-ended` is about a given-up entry's last **run** in the conversation view, not this route; no overlap.
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B1-2026-09-24.md` §4): D3 narrowed to
  `takes_own_checkout` (no base, no prerequisites, so no raw git spawn), `takes_task_workspace`
  awaited off the loop, and all of D3 wrapped to fall through to D4; B3's F77 named in Collisions.
  Re-checked at HEAD `61d553e`: `task_workspace.py:58-83`, `:123-160`; `worktrees.py:68`, `:119-138`,
  `:763-773`; `agent_trigger.py:948-1001`; `api/v1/inbound_queue.py:97-196`.
