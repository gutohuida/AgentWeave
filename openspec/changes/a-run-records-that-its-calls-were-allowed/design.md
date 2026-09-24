# Design — a run records that its calls were allowed

## Operator review, 2026-09-24

Opus adversarial review, `spec-queue/tracks/reviews/B11-2026-09-24.md` §8: **APPROVE WITH FIXES**;
the operator approved it with the fixes applied (review header: *"Every other change had its fixes
applied and was approved"*). Fixes folded in below, re-verified on `09127ba`:

- **The count must not delay an allowed call** (MEDIUM). `approve_tool_call` calls `_report_decision`
  synchronously (`hub/hub/mcp_server.py:1709`), which POSTs through `_hub_request`'s
  `urlopen(request, timeout=10)` (`mcp_server.py:184`) and only then returns the decision to Claude.
  So the caller *does* wait for the route's answer, and a first-sight database write inside the
  request would sit on the tool-call path, against this change's own *"SHALL NOT alter or delay"* and
  `agent-run-sandboxing` `spec.md:175` (*"Reporting a refusal MUST NOT alter or delay the decision it
  reports"*). **Now:** the route only counts in memory; the first-sight write runs in FastAPI
  `BackgroundTasks`, after the 202 is sent (D2), with a test that the handler does not await it
  (task 1.9). The docstring at `agent_actions.py:987` (*"the caller is not waiting on this and
  discards the response"*) is false in its first half and is corrected (task 2.3).
- **A late first-sight write could overwrite the exact flush** (MEDIUM). **Now:** every write is
  monotonic, `max` per key against the row's stored counts, and a `note()` after `flush()` for the
  same run is dropped (D2); task 1.10 tests it.
- **`NULL` also means every call was pre-allowed** (LOW), and the route path and Codex's in-process
  path are stated (D1, D3).

**Built on the recommended answer to B11's F389 question** (ROUNDS.md D13, *"event per allow?"*):
**no event per allow; a per-run count instead.** If the operator answers "not needed", this change is
withdrawn and F389 is closed as accepted (D4, option d).

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| The route persists refusals only, and says why | `hub/hub/api/v1/agent_actions.py:969-1010` |
| An operator-answered refusal is skipped here (the card recorded it) | `agent_actions.py:989-990` |
| The Claude approver reports every decision it reaches, allowed or not | `hub/hub/mcp_server.py:1589` (`_report_decision`) |
| Codex's loop reports refusals only, by a callback | `hub/hub/codex_appserver.py:1083-1100`; the callback `agent_trigger.py:2979-3014` |
| Manual (operator-card) decisions are already rows, and listable since F231 | `permission_requests` table; `pending_only=false` (UI-1) |
| The first-sight-then-flush pattern, with its reasons | `hub/hub/outside_write_record.py:1-29`, `:163` (`flush`) |
| Where each execution path flushes that recorder | `agent_trigger.py:2714`, `:3254` |
| The spec's refusal rule excludes an event per allow, and says it is not a rule about every record | `openspec/specs/agent-run-sandboxing/spec.md:321-340` |

## D1 — One nullable JSON column

`Run.permission_decisions: Optional[dict]`, shape `{"allowed": int, "refused": int}`.

- `NULL`: no decision reached the Hub. True of a run with no approver (`acceptEdits`, full access,
  no MCP), of a run whose every call was **pre-allowed** (a call the runtime's own allow rules admit
  never reaches `approve_tool_call`, so nothing is reported), and of every run before this ships.
  `NULL` therefore says "the Hub observed no decision", never "nothing was allowed". Not backfilled, for the same reason
  `outside_workspace_writes` is not (`models.py` comment on that column): a backfilled zero would
  claim every old run was watched.
- A count: the approver was asked at least once. `{"allowed": 12, "refused": 0}` is the sentence F52
  lacked: this run asked twelve times and was never refused.

**How a Claude decision reaches the row.** `approve_tool_call` decides inside the MCP tool-server
process and reports through `_report_decision` (`mcp_server.py:1589`, called at `:1709`): a POST to
`/agent-actions/permission-decisions` under the run's own bound credential, so the route knows the
run from `actor.run_id`, never from the body. That POST is best-effort (`_report_decision` swallows
every failure); a decision whose report is lost is not counted, which is why the count is "decisions
the Hub observed" and not "decisions made". **Codex decides in-process** (D3): its approval loop runs
inside the Hub, so its decisions reach the tally by a direct call, not a POST.

Operator-card decisions count as whatever the operator answered, because the approver reports them
too; the route already knows which ones those are (`_operator_already_refused`) and counts them
without re-recording the refusal event.

## D2 — First sight, then exact at the end

`hub/hub/permission_tally.py` holds `_counts: dict[run_id, Counter]` in the Hub process.

- `note(run_id, allowed) -> bool`: increments **in memory only** and returns whether this is the
  first decision **of that kind** for the run (at most two such per run). It never touches the
  database, so the decision path gains no write.
- `write_counts(run_id)`: opens **its own** session (the request's session is closed by the time a
  background task runs) and writes the counts **monotonically**: it reads the row's stored JSON and
  stores `max(stored[k], current[k])` for each key, in one transaction. No write can lower a count.
- **The route schedules the first-sight write with FastAPI `BackgroundTasks`**: when `note` returns
  `True`, `record_permission_decision` adds `write_counts(run_id)` to its `BackgroundTasks`, which
  Starlette runs after the 202 has been sent. The approver's `urlopen` returns as fast as it does
  today.
- `flush(run_id)`: writes the exact counts (through the same monotonic `write_counts`), drops the
  entry, and marks the run closed. A `note()` for a closed run is dropped. Called in both execution
  paths' `finally`, beside `outside_writes.flush()` (`agent_trigger.py:2714`, `:3254`), and like it,
  best-effort.
- **Why both rules.** A first-sight background write can run *after* the flush (the POST carrying a
  run's first allow can still be in flight when the run ends). A plain overwrite would replace
  `{"allowed": 12, ...}` with `{"allowed": 1, ...}`; `max` makes that write a no-op. Dropping notes
  after the flush keeps a straggling POST from re-creating an entry nothing will ever flush.
- Nothing here may raise into a turn or a route: every entry point catches and logs, on the terms
  `outside_write_record.py`'s docstring sets out.

**What the route returns when this raises:** `note` is an in-memory increment that catches its own
errors, and `write_counts` runs after the response is sent, so a failing count cannot change the 202
or the `recorded` body. The caller does wait for that answer: `_report_decision` blocks on it for up
to its 10-second timeout before Claude receives the decision, which is why nothing slow may be added
to the handler. The docstring's *"the caller is not waiting on this"* (`agent_actions.py:987`) is
false and is corrected in task 2.3. (The refusal event the route already writes inline predates this
change and is not moved by it.)

**Pending counts do not survive a Hub restart**: they live in memory. What survives is what the
first-sight writes stored, which is exactly the "at least one allowed / at least one refused"
guarantee the spec asks for.

**A second Hub process** (none today; one Hub owns a database) would hold a separate tally. Out of
scope; the first-sight writes still make the "was it ever" facts durable, and `max` keeps two
writers from lowering each other.

## D3 — Codex

`codex_run_turn` gains `on_decision(method, subject, allowed)` beside `on_refusal`, for every
decision including the operator's. Codex decides **in-process**: the approval loop runs inside the
Hub (`codex_appserver.py:1070-1105`), so there is no POST and no `BackgroundTasks`. To keep the count
off the decision path, `on_decision` is called **after** `await session.respond(msg_id, decision)`
(`codex_appserver.py:1105`), not where `on_refusal` is awaited today (before the respond). The
callback in `agent_trigger.py` (beside `_on_refusal`, `:2979`) calls `permission_tally.note` and,
when it returns `True`, hands `write_counts` to `asyncio.create_task` (the task held in a set until
done), so the loop does not wait on the database. Codex is undrivable
(2026-08-29), so this half is tested, not driven.

## D4 — The options

| Option | What it would break | What it releases |
|---|---|---|
| **(a) A per-run count, first sight + flush (this change)** | Nothing; one nullable column. | "Asked and allowed" becomes a stored fact. |
| (b) An event per allowed call | Buries refusals, and adds a write per tool call to a database that already reports lock contention. | The same fact, at a cost the spec rules out for the refusal record. |
| (c) A count written on every call | A write per tool call. | The same fact, exact under a crash. |
| (d) Nothing; accept the gap | — | — |

## Open questions

1. Surface the count on the run's card now, or leave it API-only? Recommended: API-only; a surface
   is a separate UI decision.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: `record_permission_decision` persists refusals only (`agent_actions.py:991-1009`)
  and the approver reports allows too (`mcp_server.py:1589-1605`, `allowed: decision["allow"]`), so a
  count has a source. **Clarified:** `note()` must run **before** the `_operator_already_refused` early
  return (`agent_actions.py:989-990`), or operator-answered refusals are never counted, which D1
  promises they are. No other claim disagreed.
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §8), applied on
  `09127ba`: first-sight write moved to `BackgroundTasks` (task 1.9); monotonic `max` writes and
  notes after flush dropped (task 1.10); `agent_actions.py:987` docstring corrected (task 2.3);
  `NULL` = pre-allowed stated (D1); the POST under the run credential and Codex's in-process path
  stated (D1, D3), with Codex's `on_decision` after the respond (task 1.7). Citations re-checked:
  `agent_actions.py:969-1010`, `:987`, `:989-990`; `mcp_server.py:184`, `:1589`, `:1709`;
  `codex_appserver.py:1070-1105`; `agent_trigger.py:2714`, `:2979`, `:3254`; sandboxing
  `spec.md:175`, `:321-340`.
