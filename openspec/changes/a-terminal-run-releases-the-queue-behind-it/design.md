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

### D3 — The app-server path gets a handler of the same shape, not a shared helper

`_execute_codex_appserver_run` gains `except (Exception, asyncio.CancelledError)` with the same
structure as `_execute_run`'s: `logger.exception`, relabel to `failed` only if the row is still
`running`, release unconditionally, re-raise `CancelledError`.

Deliberately duplicated rather than factored into a helper the two share. The two tails differ in
what they can say about the failure — `_transport_failure_fields` versus `_runtime_failure_fields`,
a real `exit_code` versus a synthetic one, `active_ptys` versus `active_app_server_runs` — and a
shared helper would have to be parameterised on each of those. The invariant to hold is stated in
the spec and asserted by tests on both paths; that is what makes the duplication safe, not a shared
call site. A later change may factor them; this one should not, because the risk of getting the
merge wrong is larger than the duplication it removes.

### D4 — The regression test injects the exception; it does not depend on F285

The window is "an exception between the terminal commit and the release". The test makes one
deterministically by patching a bookkeeping call that sits inside it — `_broadcast_run_lifecycle` or
`record_agent_output` as `agent_trigger` resolves them — to raise once, then asserts that an entry
queued behind that run is delivered to a successor run without any further request.

Those two, and not `maybe_generate_title`, which is also in the window: it swallows every `Exception`
itself (`conversation_titles.py:230-238`), so patching it to raise would produce a test that passes
without the code under test ever seeing the exception.

This matters: CI's actual failure came from the in-memory `StaticPool` artefact (F285), and when
that is fixed the exception disappears with it. A test that reproduces F286 through F285 would go
green for the wrong reason. The injected-exception test survives either fix.

### D5 — The app-server half is verified by test, not by a live drive

The operator cancelled the Codex drive plan on 2026-08-29; Codex is not driven here. The app-server
path is exercised by the existing `_fake_run_turn` harness (`hub/tests/test_agent_trigger.py:126`)
and its in-flight poll helper (`:68`), which is enough to assert both halves — that a raise after
the terminal write still releases the queue, and that a raise before it leaves the run terminal
rather than `running`. The PTY half is additionally drivable live and should be driven.

## Risks / Trade-offs

- **A release running after a failure touches more state than before.** Mitigated by what
  `redrain_queued_agents` is: a query for queued entries plus `schedule_agent`, which refuses a busy
  agent and returns "queue is empty" for one with nothing waiting.
- **The new app-server handler could relabel a run some other writer just finished.** The same
  `run.status != "running"` guard the PTY handler uses covers this, and it is the reason that guard
  exists.
- **Duplication between the two handlers (D3) can drift.** Accepted, with the spec requirement as
  the thing that holds them together and a test per path.

## Migration Plan

None. No schema change, no data change, no UI change.
