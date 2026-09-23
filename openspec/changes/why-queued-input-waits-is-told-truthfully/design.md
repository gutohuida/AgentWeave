# Design — why queued input waits is told truthfully

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

- **Which task:** the controlling entry, as `_attempt_turn` picks it — the first queued entry
  within the budget (`turn_scheduler.py:340`, `controlling`) — and its task by `run_task_binding.task_named_by`.
  Where it names no task, the conversation's bound task decides the trigger's workspace
  (`binding_for_conversation`, `run_task_binding.py:559`). R2 should confirm that this is the order
  `resolve_bound_task` uses, and use that function rather than restating it if it reads nothing it
  should not.
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
- `GET /queue/{agent}/status`: D3 adds `tasks_held_by_a_running_turn` (a read) and
  `takes_task_workspace` (a filesystem probe on a resolved root). The route already calls
  `resolve_project_workspace` inside a `try` that turns `ProjectWorkspaceError` into a reason
  (`:168-172`). D3 runs only where that resolved, and a failure in `takes_task_workspace` SHALL
  fall through to D4 rather than raise: the status route is a diagnostic and must not 500 because
  one of its checks failed.

## Residual

- No later briefing tells the sender what became of a held message (F361's second clause). The
  send answer is the moment the sender reads; a follow-up is a larger change.
- F376 (a chain never reset without a flow) is why chains reach the budget at all; not here.

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change from the code at `404c7d5`.
