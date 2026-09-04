# Design

## Context

Two execution paths end a run: `_execute_run` (PTY/pipe, Claude and `codex exec`) and
`_execute_codex_appserver_run` (JSON-RPC app-server). Both have the same three-part tail — write the
terminal status and commit, do the post-turn bookkeeping, then call
`redrain_queued_agents(project_id)` — and in both the release is the last statement of the `try`.

`redrain_queued_agents` (`turn_scheduler.py:520`) selects the distinct agents in the project holding
`state == "queued"` entries and calls `schedule_agent` on each. It is the only thing that starts a
turn for input that arrived while an agent was busy, and it is reachable from exactly four places
outside these two functions: project open, settings save, workspace relocate
(`api/v1/projects.py:315`, `:527`, `:588`), and the deferred drain
`run_reconciliation.drain_deferred_schedules`, which fires once, on the first request after a Hub
start that reconciled something. There is no periodic tick. This is stated in the code at
`agent_trigger.py:1908` and is the fact the whole change turns on.

## Goals / Non-Goals

**Goals.** Make the release of queued input a consequence of a run having ended, on both paths.
Give the app-server path the terminal-status guarantee the PTY path already has.

**Non-Goals.** Introducing a periodic drain tick (a much larger design, and it would hide this class
of defect rather than fix it). Changing what `redrain_queued_agents` does. Fixing F285 or F287.
Changing delivery-attempt accounting.

## Decisions

### D1 — The release is ungated in the handler; `already_terminal` keeps only its first job

`_execute_run`'s handler computes one flag (`:2305-2313`) and uses it for two unrelated questions. Split
them: the status relabel stays gated (do not overwrite a cleanly-ended run's status because later
bookkeeping raised — the existing comment argues this correctly), and the redrain at `:2358` moves
out of the `if not already_terminal:` block to run on every exception.

This is the smallest change that matches the code's own stated intent: the comment above that
redrain already claims to be *"[u]nconditional, where this was gated on `returned`"*. It was made
unconditional with respect to one gate while sitting inside another.

**Alternative rejected — put the release in `finally`.** Superficially the right home: "whatever
happened, release". But `_execute_run`'s `finally` block carries an explicit warning
(`:2364-2368`) that a cancelled task raises `CancelledError` at its *first* await point, which is
why the block's only `await` is deliberately last and holds nothing that must happen. A redrain in
`finally` would be skipped under exactly the cancellation case the handler was widened to catch, and
it would silently demote the two synchronous releases already there.

**Alternative rejected — release immediately after the terminal commit.** It would close the window
by removing it. But the successor turn would then start while this run's `evaluate_run_end`,
abandonment report and terminal broadcast are still unwritten, so a task-checkout decision could be
taken against a half-written boundary. Keep the happy-path release where it is; add the failure-path
one.

### D2 — A second redrain is acceptable, bounded, and does charge something

The one new overlap is an exception raised *by* `redrain_queued_agents` itself at `:2281`: the
handler would then call it again. **D1 introduces this overlap rather than inheriting it** — today
the gate prevents it, because a run that reached `:2281` is already terminal, so `already_terminal`
is `True` and the handler's redrain is skipped.

**R2 re-derived the accounting and R1 had the mechanism wrong.** R1 wrote that *"`schedule_agent`
charges a delivery attempt when it delivers"*. Nothing charges on delivery: `mark_delivered` sets
`entry.state = "delivered"` and increments nothing (`inbound_queue.py:154`). There are exactly two
charge sites, and neither is a delivery — `inbound_queue.py:211`, where a *failed run returns* an
entry it was carrying, and `turn_scheduler.py:462`, where a schedule is *refused* non-transiently
(`not transient and not agent_wide and …`, `:378-406`).

That matters, because R1's two-bucket split — already delivered, or not yet reached — is a false
dichotomy. There is a third bucket, and it is the charging one: an entry the first redrain **reached
and refused** non-transiently. It stays `queued`, it was charged once, and the second call's query
selects it and charges it again. `DELIVERY_ATTEMPT_LIMIT` is `3` (`inbound_queue.py:178`), so one
run boundary can burn two of an entry's three allowances. This is the same accounting F114 and F96
already litigated in this file — *"the operator's own attempts to find out why nothing was happening
were what consumed the allowance"* — so it is an in-family cost, not a novel one.

The decision stands: **release twice rather than not at all.** The overlap needs an exception raised
inside `redrain_queued_agents`/`schedule_agent` that is not a `TriggerAgentError` — a database
failure, essentially — *and* an entry already refused non-transiently in the same sweep, whereas the
defect being fixed needs only one raise anywhere in a hundred-line window. The residual is named
here rather than argued away, and task 3.7 asserts its bound. The cheap alternative — having
`redrain_queued_agents` swallow per-agent errors so the first call cannot raise partway — would
remove the overlap entirely and is deliberately not taken: it is a change to `redrain_queued_agents`,
which this change lists as a non-goal, and it would hide the same class of failure one layer down.

### D3 — The app-server path shares the PTY path's handler, in one helper

`_execute_codex_appserver_run` gains `except (Exception, asyncio.CancelledError)` between its outer
`try` (`:2536`) and its `finally` (`:2873`). The body is not written twice. Both handlers call one
new coroutine: mark the run `failed` only where the row is still `running` — `expire_pending_for_run`,
`record_turn_usage(sample=None)`, `finalize_job_run_for_conversation`, `return_run_entries`, commit,
`_report_abandoned_entries`, a `run_failed` broadcast carrying `_transport_failure_fields(exc,
conversation_id)`, a `queue_entry_queued` per returned entry — then release the queue
unconditionally per D1. Each call site keeps only its `logger.exception` and the `CancelledError`
re-raise.

**R3 overturned R1's and R2's decision here, because the argument was about the wrong code.** D3
read: *"Deliberately duplicated … The two tails differ in what they can say about the failure —
`_transport_failure_fields` versus `_runtime_failure_fields`, a real `exit_code` versus a synthetic
one, `active_ptys` versus `active_app_server_runs`."* It justified duplicating the **handlers** by
citing differences between the **success tails**. R3 measured both objects.

*The tails it cited.* Stripped of comments and blank lines, `:2169-2281` is 40 statements and
`:2807-2872` is 41. `diff` returns **one hunk, of one line**: the app-server broadcast passes
`**_runtime_failure_fields(outcome, lifecycle_event)` and the PTY one passes nothing. "A real
`exit_code` versus a synthetic one" is not a difference between the tails at all — both pass
`exit_code=exit_code`; the difference is upstream, in what that variable was set to.

*The handler it actually proposed to duplicate.* All three differentiators are absent from it.
`_runtime_failure_fields` takes a `TurnOutcome`, which an exception does not supply and which is not
even guaranteed to be bound when one is raised — so the app-server path's own pre-spawn `except`
already uses `_transport_failure_fields(exc, conversation_id)` at `:2723`, the same helper the PTY
handler uses at `:2344`. Neither handler passes `exit_code` at all. And
`active_ptys`/`active_app_server_runs` are in the two `finally` blocks (`:2362`, `:2874`), which
already exist, already differ, and were never part of what D3 proposed to copy.

What is left after removing the three is a ~30-line body differing in one string: `runner`, a
parameter of `_execute_run` and the literal `"codex"` on the other path (`:2798`). That is a helper
argument, not a reason to write terminal-status logic twice. D3's own Risks entry conceded
*"[d]uplication between the two handlers can drift"*; the cheapest way not to litigate drift is not
to create it.

**What the duplication argument was right about,** and what the helper does not touch: the two paths
genuinely differ in their `finally` blocks and in what their *success* tails can say about an
outcome they have. The helper covers the failure path, which is where they are the same, and one of
its arguments is the runner name because that is the only thing that varies.

### D4 — The regression test injects the exception, and injects it *inside* the window

The window is "an exception between the terminal commit (`:2175`) and the release (`:2281`)". The
test makes one deterministically, then asserts that an entry queued behind that run is delivered to
a successor run with no further request made.

**R3 correction: R1 and R2 both named injection points that fire *before* the window, so a test
written to this decision as it stood would have passed without the fix.** Neither named call site is
unique to the window on a run that reaches it:

- `record_agent_output` is called at `:2014`, once **per streamed output event**, long before the
  terminal commit. "Raise once" raises on the run's first line of output.
- `_broadcast_run_lifecycle` is called at `:1939` as `run_started`, on every PTY run, before the read
  loop even begins.

Either raise lands in the handler with the run row still `running`, so `already_terminal` is `False`
and today's code already redrains — the case that works. The test would be green before the change
and after it. That is the same failure shape as the fixture-ordering rule in `CLAUDE.md`: a test
whose setup cannot reach the behaviour it claims to cover.

The injection is therefore **predicated on the call being the in-window one**. Patch
`record_agent_output` to raise only for `kind == "status"` — `:2235` is the only status row
`_execute_run` writes and `:2854` the only one on the app-server path — or patch
`_report_abandoned_entries`, whose `:2195` call is the only one a run reaching the tail executes
(`:1893` and `:2337` are in branches such a run did not take). Whichever is used, the test asserts
positively that the run had already reached a terminal status when the raise happened, so a later
change that moves the injection out of the window fails the test instead of silently weakening it.

Not `maybe_generate_title`, which is also in the window: it swallows every `Exception` itself
(`conversation_titles.py:230-238`), so patching it to raise would produce a test that passes without
the code under test ever seeing the exception.

This matters for a second reason. CI's actual failure came from the in-memory `StaticPool` artefact
(F285), and when that is fixed the exception disappears with it. A test that reproduced F286 through
F285 would go green for the wrong reason. The injected-exception test survives either fix.

## Risks / Trade-offs

- **A release running after a failure touches more state than before.** Mitigated by what
  `redrain_queued_agents` is: a query for queued entries plus `schedule_agent`, which refuses a busy
  agent and returns "queue is empty" for one with nothing waiting.
- **The new app-server handler could relabel a run some other writer just finished.** The same
  `run.status != "running"` guard the PTY handler uses covers this, and it is the reason that guard
  exists.
- **One shared handler means one place to get wrong (D3).** The failure body now runs on both paths,
  so a mistake in it is a mistake twice. Mitigated by the requirement being stated once and asserted
  by a test per path, which is what the duplication was previously relying on anyway — and by the
  helper taking the runner name rather than branching on it internally.

## Migration Plan

None. No schema change, no data change, no UI change.
