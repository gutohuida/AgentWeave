## Context

`hub/hub/runner_parsing.py` currently creates `ContextUsageSample` values for the context meter.
Those values answer “how full is this session's context window?” and may be emitted repeatedly in
one run. Treating them as spend would double count turns and conflate cached context with billable
or generated tokens. `Run` is the durable turn boundary, so accounting belongs in a separate row
keyed one-to-one to `Run.id`.

All turn starts now flow through `hub/hub/turn_scheduler.py`. Queue entries already distinguish
operator and agent origins, but scheduled jobs are currently stamped as operator entries even
though they start without an operator action. Budget enforcement therefore requires an explicit
scheduled origin and a persisted run initiator.

## Goals / Non-Goals

**Goals:**

- One immutable normalized accounting outcome per run: measured usage or unavailable.
- Idempotent aggregation from durable rows, not counters maintained by side effect.
- Accurate operator/autonomous classification at the queue-to-run boundary.
- Token-budget enforcement before an autonomous queue entry is delivered.
- Clear display semantics for unavailable data, allowance, and API-equivalent currency.

**Non-Goals:**

- Billing, invoicing, subscription-plan inference, or claiming what an operator was charged.
- Model price catalogs maintained by AgentWeave. Only runner-reported monetary telemetry is stored.
- Retrofitting historical runs that predate the migration.
- Making OpenCode directly launchable in the Hub; its parser is normalized now so the accounting
  contract is ready when its runner path is added.
- Hop-budget or agent-budget redesign.

## Decisions

### 1. A one-to-one `TurnUsage` row is the accounting source of truth

`turn_usage.run_id` is unique and records availability, normalized token dimensions, runner,
model, optional API-equivalent USD, optional allowance payload, and observation time. Aggregates
are SQL sums over measured rows. An unavailable row is meaningful evidence that the turn happened
but the runner supplied no usable telemetry; it is not omitted and it does not contribute a zero.

The normalized `total_tokens` is `input + output` when a runner does not supply a trustworthy
total. Cache and reasoning dimensions remain visible breakdowns but are not added again when they
are already subsets of input/output.

### 2. Accounting samples are separate from context samples

`ParsedLine` carries both `usage` (the existing context-window sample) and `accounting` (turn
totals). The execution loop retains the newest complete accounting sample and writes once after
the process ends. Claude's final `result.usage` is preferred, with `modelUsage` as a fallback;
Codex's `turn.completed.usage` is the direct-stream equivalent of its persisted `token_count`
request delta; OpenCode's completed step telemetry maps directly. This avoids counting partial
assistant events multiple times.

### 3. Initiator is decided from the selected queue batch

Queue origin types are `operator`, `agent`, and `job`. A selected batch containing an operator
entry is operator-initiated; otherwise it is autonomous. Scheduled jobs use `job`, fixing their
current misleading operator label. `Run.initiator` persists the decision for auditability.

### 4. Budget enforcement happens before atomic queue delivery

The scheduler computes project usage and checks the optional project budget after selecting the
conversation batch but before `trigger_agent_directly` delivers any entry. If exhausted and the
batch is autonomous, it returns `token budget exhausted`; entries remain queued and therefore
survive until the budget changes or operator input arrives. An operator batch bypasses only this
token-budget gate, not launchability, isolation, or hop-budget checks.

The threshold is exhausted when `used_tokens >= token_budget`. An operator turn that runs while
exhausted is still accounted and may increase the overage; the budget is a guard on autonomy, not
a hard process quota.

### 5. The API returns facts plus a display preference

`GET /api/v1/accounting` returns project totals, agent totals, the budget state, and recent turn
records. Each summary distinguishes `measured_turns` and `unavailable_turns`. If a latest runner
allowance exists, `display.kind` is `allowance`; otherwise runner-reported cost yields
`api_equivalent`; otherwise the display is tokens or unavailable. The frontend does not invent
prices or reinterpret subscription usage.

`PATCH /api/v1/accounting/budget` accepts a positive integer or `null`. Zero and negative values
are invalid because `null` is the unambiguous disabled state.

## Risks / Trade-offs

- Runner schemas evolve. Parsing is defensive and fixture-tested; missing or malformed telemetry
  degrades to unavailable instead of failing the run.
- A one-row-per-run design intentionally discards intermediate accounting snapshots. That is the
  correct trade for immutable turn totals and avoids double counting.
- Existing runs will have no accounting row. Aggregates report only observed post-migration turns
  and expose unavailable counts for new runs whose telemetry is missing; they do not guess history.

