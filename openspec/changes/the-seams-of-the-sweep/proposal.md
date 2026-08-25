## Why

A full-surface sweep on 2026-08-25 drove nineteen feature areas against a live Hub with real agents
on two CLIs, and found twelve defects (`scripts/drive/FINDINGS.md`, F27–F38). They share a shape:
**none is a component doing its job badly; every one is a gap between two components that each do
their job correctly.** No unit test catches them because no unit test spans two subsystems.

One is severity A and is the reason this change is now rather than later. A run whose entire prompt
was *"concurrency probe 1: reply CONC-1 only"*, carrying `task_id = NULL`, marked **six unrelated
tasks `completed`**. Because `completed` sits in `BAND_AWAITING_HANDOFF`
(`hub/hub/task_transitions.py:224`), a flow then offers each of them to another agent as reviewable
work; that reviewer finds the code correct — it is, because a *different* agent really did it —
approves, and `task_integration` merges. **The path from "an agent glanced at a list" to "code on
`master`" contains no human and no single false statement.**

This change also picks up F21, carried since 2026-08-24, because its remedy is the same one F32 and
F38 need: telling an agent plainly what it can reach.

## What Changes

Ordered by damage prevented per line changed, not by severity label.

- **A run may only finish work it holds** (F27). Claiming a task binds the run to it; completing a
  task requires that binding. Two conditions in `apply_transition`, beside the dependency and
  requirement gates already there. The operator is unaffected.
- **Nothing is scheduled that can only fail or idle** (F28, F33). A flow adopts the tasks already
  materialised from the document it claims, so build-order stops mattering; a flow with
  `stop_when_queue_empties` stops instead of spawning an agent against an empty queue; a job naming
  an agent that does not exist is refused at creation, where the cron beside it already is.
- **Agents are told what they may *not* do** (F32), and can reach the tools they are given (F21).
  Canonical context states withheld capabilities, not only granted ones.
- **A turn that produced nothing says so** (F38). Recorded from state the Hub already holds — the
  run ended, no `Question` row was written, the deliverable did not advance. **No prose is
  inspected.**
- **The tool with the largest payload gets a refusal that teaches** (F35).
- **The operator is told the truth** (F31, F30, F34). Redaction stops eating the Hub's own
  vocabulary; launchability agrees with what actually spawns; the CLI reports the Hub the project
  really uses.
- **Approval attaches to bytes, not to a path** (F29). Divergence is checked when a document is
  read, not only when it is written.
- **Doors that had one key get another** (F36, F37). An operator can declare a task dependency; a
  document created by mistake can be archived.

**No BREAKING changes.** F27 is the only behaviour change an existing agent could notice, and only
on a path that was never legitimate.

## Capabilities

### New Capabilities
- `turn-outcome-visibility`: a run that ends without advancing its deliverable and without asking
  anything is recorded as such, from state alone — never by inspecting the agent's prose.

### Modified Capabilities
- `run-task-binding`: claiming an unheld task binds the run to it; a run already bound elsewhere is
  refused. Extends the existing *"A run carries at most one task binding"*.
- `task-lifecycle-governance`: the `-> completed` edge requires the acting run to be bound to the
  task it closes.
- `agent-loops`: a flow adopts tasks already materialised from the document it claims; a job must
  name an agent on the roster.
- `loop-firing-accountability`: a flow honouring `stop_when_queue_empties` does not fire against an
  empty queue.
- `agent-context-onboarding`: withheld capabilities are stated as plainly as granted ones.
- `agent-tool-surface`: callable tools are named explicitly; a malformed call is refused with the
  field, the shape wanted, and one example.
- `agent-stream-events`: redaction is bounded so it cannot consume the Hub's own tool names and
  document slugs.
- `runner-registry`: launchability keys on the bound runner, so the probe and the spawn cannot
  disagree.
- `runtime-diagnostics`: `--port` before the subcommand takes effect; a native process is not
  reported as Docker; `doctor` examines the Hub the project is bound to.
- `spec-document-authority`: divergence is reported on read; an unmaterialised document can be
  archived.
- `task-dependencies`: an operator can declare a dependency between two tasks they created.

## Impact

**Hub (`hub/hub/`)** — `task_transition_service.py` (F27), `run_task_binding.py` (F27),
`api/v1/jobs.py` (F28, F33), `scheduler.py` (F28), `spec_tasks.py` (F28, F36),
`api/v1/agents.py` ~1321 (F32), `runner_events.py` (F31), `launchability.py` ~353 (F30),
`spec_lifecycle.py` + `spec_service.py` (F29, F37), `api/v1/tasks.py` (F36), `mcp_server.py` (F35).

**CLI (`src/agentweave/`)** — `cli.py`, `diagnostics.py` (F34). Unchanged constraint: the CLI's own
code imports nothing outside the stdlib.

**Constraint carried into design:** `hub/hub/mcp_server.py` is spawned standalone and may import
**only stdlib + fastmcp**, so F35's refusal shaping must be restated there with a test asserting the
two agree. `approve_tool_call` must keep having no return annotation.

**Migration:** F28 may warrant a one-off data migration back-filling `loop_id`, so flows already
broken repair themselves rather than needing a rebuild.

## Non-Goals

- **Reinstating the retired question backstop.** A completed run whose final text merely *reads*
  like a question was detected and surfaced until 2026-08-20, when it was retired deliberately;
  migration `0082` drops its table. F38's remedy uses state only and does not reintroduce it.
- **Automatically re-delivering a turn that produced nothing.** It would work and it spends money
  without the operator asking. Out of scope.
- **Reducing the per-turn context floor.** The sweep measured a turn whose entire instruction was
  *"reply with exactly: SWEEP-OK"* costing 34,451 input tokens, because context and charter are
  assembled fresh every turn. Real, recorded, and not a defect — not addressed here.
- **F22, F24, F25 and F26**, carried since handoff 0079. Not part of the sweep report.
- **Changing what `completed` requires by way of evidence.** It deliberately requires none, because
  evidence is accepted after review and review follows completion; refusing there would deadlock the
  ordinary path (`requirement_gate` docstring). F27 is fixed by asking *who*, not by asking for more.
