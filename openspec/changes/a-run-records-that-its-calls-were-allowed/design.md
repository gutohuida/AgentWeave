# Design — a run records that its calls were allowed

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
  no MCP), and of every run before this ships. Not backfilled, for the same reason
  `outside_workspace_writes` is not (`models.py` comment on that column): a backfilled zero would
  claim every old run was watched.
- A count: the approver was asked at least once. `{"allowed": 12, "refused": 0}` is the sentence F52
  lacked: this run asked twelve times and was never refused.

Operator-card decisions count as whatever the operator answered, because the approver reports them
too; the route already knows which ones those are (`_operator_already_refused`) and counts them
without re-recording the refusal event.

## D2 — First sight, then exact at the end

`hub/hub/permission_tally.py` holds `_counts: dict[run_id, Counter]` in the Hub process.

- `note(run_id, allowed)`: increments; if this is the first decision **of that kind** for the run,
  writes the row's current counts in its own session (at most two such writes per run).
- `flush(run_id)`: writes the exact counts and drops the entry. Called in both execution paths'
  `finally`, beside `outside_writes.flush()` (`agent_trigger.py:2714`, `:3254`), and like it,
  best-effort.
- Nothing here may raise into a turn or a route: every entry point catches and logs, on the terms
  `outside_write_record.py`'s docstring sets out.

**What the route returns when this raises:** `record_permission_decision` already returns 202 and
its caller discards the response (`agent_actions.py:987`); `note` cannot raise out of it, so the
route's answer is unchanged. The Codex callback is inside the approval loop; `note` swallowing its
own errors is what keeps a failed count from failing an approval.

**A second Hub process** (none today; one Hub owns a database) would hold a separate tally. Out of
scope; the first-sight writes still make the "was it ever" facts durable.

## D3 — Codex

`codex_run_turn` gains `on_decision(method, subject, allowed)` beside `on_refusal`, called at the
point the decision is final (`codex_appserver.py:1082`), for every decision including the operator's.
The Codex callback in `agent_trigger.py` calls `permission_tally.note`. Codex is undrivable
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
