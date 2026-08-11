# A permission request never outlives the run that raised it

## Why

The operator approves a tool call and the tool does not run. Reported verbatim on 2026-08-10:

> "When the permissions are not to allow all and a agent needs to delete or execute something even
> if he asks via agentweave and we give a positive answer it still doesn't allow it to run."

Diagnosed 2026-08-11; the full investigation, including four eliminated leads and a live probe, is in
`openspec/explorations/2026-08-10-operator-approval-not-honoured.md`. The cause is a seam, not a
protocol error:

1. `mcp_server._ask_operator` bounds its wait at `AW_DECISION_TIMEOUT` (default 120s). On expiry it
   returns a **local** denial and writes nothing back. The row stays `status="pending"`.
2. `_report_decision` (`agent_actions.py:513-547`) logs a `permission_denied` event and **never
   touches the row** — it is not given the request id, only `tool_name`/`tool_use_id`.
3. `list_permission_requests` filters `status == "pending"` (`permissions.py:57`), so **the card is
   still on screen** minutes after the run stopped waiting.
4. The operator clicks Allow. `decide_permission_request`'s guard is `row.status != "pending"`
   (`permissions.py:86`) — it *is* pending, so the guard does not fire. The row becomes `"allowed"`
   and the API returns **200**.
5. The operator has seen an approval succeed. Nothing runs, and nothing says why.

The guard's own message — *"this request was already {status}; the run has moved on"* — is the author
anticipating exactly this. It never fires, because on this path nothing ever sets a terminal status.

**The intended behaviour is already written down.** `db/models.py:1157-1159`, on `PermissionRequest`
itself:

> "The row outlives the answer so a denial stays visible after the fact; `decided_at` distinguishes
> an answer from a timeout, **which also writes a terminal status rather than leaving the row pending
> forever.**"

`"expired"` is already a documented status value on that model. This is an unimplemented contract on
one path, not a design gap.

**Why only Claude.** `agent_trigger.py:1451` is the only line in the codebase that expires a row, and
it is the Codex path, which runs in-process with a database session. `mcp_server.py` is spawned
standalone and may import only stdlib plus fastmcp, so it has no session — and silently went without
the equivalent write.

**A second symptom, same cause.** `conversations.py:268-269` counts a pending permission request as a
reason a conversation is waiting on the operator. A row that is never closed pins its conversation as
waiting **permanently**, long after the run ended.

Now, because this is the operator-in-the-loop story — a listed shipped capability — failing at its
final step. An operator who cannot trust an approval sets yolo and leaves it there, which is the
opposite of what the permission surface is for. It also blocks task 9.1 of the already-archived
`2026-08-10-task-transition-machine`, so an unverified claim is sitting in the archive.

## What Changes

- **The run tells the Hub when its wait ends.** A new agent-facing endpoint closes a request the run
  has stopped waiting on. Called best-effort from `_ask_operator`'s timeout path, under the same rule
  as `_report_decision`: reporting never alters or delays the decision, and an unreachable Hub must
  not turn an answered request into an unanswered one.
- **The Hub expires pending requests whose run has ended**, at both run-end sites
  (`agent_trigger.py:1270` and `:1656`). This is the load-bearing half: a killed run never reports,
  so best-effort reporting alone would leave the defect reachable.
- **A decision on a request nobody is waiting for is refused**, closing the residual race where the
  operator clicks at t=119s against a run that gave up at t=120s. The existing 409 becomes reachable
  rather than theoretical.
- **An expired request reads as expired** rather than vanishing. The operator needs to learn the
  agent gave up; a card that silently disappears teaches nothing and looks like a bug.
- **The seam gets tests.** No test currently exercises `/permission-requests` as an actual HTTP
  route — the MCP side is tested against a stubbed `_hub_request`
  (`test_permission_approver.py:355`) and the UI against mocked hooks, which is precisely why the
  divergence between the run's view and the operator's view was invisible.

**No migration.** `status` already permits `"expired"` and `run_id` is already indexed, so the
Hub-side sweep is a cheap query against an existing index.

## Capabilities

### New Capabilities

None. This implements a contract the shipped model already documents.

### Modified Capabilities

- `agent-run-sandboxing`: gains a requirement that a permission request's lifetime is bounded by the
  wait it represents — the row reaches a terminal status when the run stops waiting, whichever way
  that happens, and a decision on a request nobody is waiting for is refused rather than silently
  accepted. Extends the existing "Every permission decision is answered" and "A refused action is
  visible to the operator" requirements to cover the request's own fate, which neither currently
  says anything about.

## Impact

**Changed:** `hub/hub/mcp_server.py` (`_ask_operator` timeout path), `hub/hub/api/v1/agent_actions.py`
(new expiry endpoint), `hub/hub/api/v1/agent_trigger.py` (two run-end sites),
`hub/hub/api/v1/permissions.py` (decision refused when nobody waits), and the permission request card
plus its API types in `hub/ui/src/`.

**Unchanged:** the database schema, the approval protocol, the CLI flags, and the Codex path, which
already does the right thing and is the model for the fix.

**Tests:** new HTTP-level coverage of the request lifecycle; `test_permission_approver.py` gains the
timeout-writes-back case it could not previously see.

## Non-Goals

- **Not changing the timeout's length or making it adaptive.** `AW_DECISION_TIMEOUT` is per-agent and
  already configurable; the defect is what happens at the boundary, not where the boundary is.
- **Not adding a way to re-ask.** If an operator misses the window the agent may ask again; a
  resurrect-and-retry path is a larger design with its own race.
- **Not touching the Codex path's behaviour**, only its test coverage.
- **Not reworking the conversation attention model.** Fixing the row's lifecycle fixes the stuck
  "waiting" symptom at its source.
- **Not adding a free-text operator reason** — deliberately absent today
  (`permissions.py:25-28`) and out of scope here.
