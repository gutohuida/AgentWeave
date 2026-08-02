# Exploration — Product direction: local-only, spec-centred, easy to use

**Date:** 2026-08-02
**Status:** Direction stated by the product owner. Not yet decomposed into changes.
**Purpose:** Durable record of *why* the architecture is being narrowed, so future sessions do not
re-derive it or quietly restore the scope being removed.

---

## The diagnosis

AgentWeave had too many barriers and was hard to use. The stated cause is not any single feature but
scope: local development, online cooperation between users, and a company-wide hub were all being
built at once. Trying to satisfy three deployment models simultaneously produced a system where the
simplest path — one developer, one machine, a few agents — carried the ceremony of all three.

> "I think I jumped the gun with the architecture trying to make everything at once, local dev,
> online cooperation, company wide hub etc."

## The direction

**AgentWeave becomes a locally-installed application, and that is the only way to use it.** The
model is T3 Code: install it, run it, it owns the agent processes on your machine. There is no
no-Hub product and no CLI-only collaboration mode.

What AgentWeave keeps that T3 does not have, and what the product is actually *for*:

1. **Multi-agent collaboration** — several agents working the same project, addressable, with
   inter-agent communication as a first-class part of the runtime rather than a bolt-on.
2. **Spec-driven development with the agents** — a hard focus. Requirements, tasks, runs, and
   evidence connected to each other and to the conversation. This is the differentiator, not a
   side feature.
3. **Governance and quality gates** — review separation, echo-chamber protection, verification
   before completion.

All three must be integrated into the overall architecture and experience, not offered as separate
surfaces the user has to assemble.

**The organising constraint is ease of use.** Where a capability and a barrier conflict, the barrier
loses.

## What is deferred, not abandoned

The hub returns "waaay in the future" as a place where you connect your *local* agents and
collaborate with agents belonging to *other users* — federation between local installs, not a
company server. It is postponed until the local experience is good enough to be worth federating.

The CLI may be revived later. Its purpose is currently unclear: with collaboration inside the app,
there is no evident reason to drive AgentWeave from a terminal.

> "I don't know why would someone use the CLI and what for. Maybe I'll revive it in the future."

## Consequences for the current plan

These follow from the direction and change work already scoped. Recorded here so they are not
missed.

### 1. The CLI reduces; it does not simply vanish

The distinction matters. A locally-installed Python app still needs an entry point — `uv tool
install agentweave`, then a command that launches it. What goes is the CLI as a *collaboration
substrate*.

**Decided 2026-08-02** (delegated by the product owner). The governing principle:

> The CLI does only what **cannot be done from inside the app**: start it, diagnose why it will not
> start, stop it, and recover it when it is wedged.

Everything that manipulates collaboration state belongs to one of the two real audiences — the app
UI for the human and an agent capability plane. Agents may reach that plane through MCP or direct
HTTP, depending on what their environment permits. Those are adapters over the same capabilities,
not separate product surfaces. `cli.py` currently has **56** `cmd_*` functions; **5** survive.

| Surviving | Purpose |
|---|---|
| `agentweave` (bare) | Launch the app on the current directory. The primary entry point, equivalent to `npx t3`. Replaces `init`, `activate`, `quick`, and `start` — an unregistered directory is offered on launch rather than requiring a separate ceremony. |
| `agentweave doctor` | Environment readiness: Python, runner CLIs on PATH, ports, database, permissions. Kept precisely because "hard to use" is the problem being solved — this is where a failed install explains itself. |
| `agentweave status` | Is it running, on what port, against which project. |
| `agentweave stop` | Stop a running instance. |
| `agentweave reset` | Destroy local state and start clean. The escape hatch when something is wedged; successor to `hub-destroy`. |

Plus `--version` and `--help`.

Removed, by group: collaboration (`switch`, `relay`, `delegate`, `run`, `inbox`, `msg-*`, `reply`,
`task-*`, `question-*`, `agents-list`, `agent-request`, `checkpoint`, `summary`, `log`, `yolo`,
`sync-context`, `spec-push`) → app UI and MCP; `roles-*` → dies with runner/charter separation;
`transport-*` and `agent-set-session` → die with the single runtime; `jobs-*` → app UI, with the
existing MCP job tools covering agents; `agent-configure` / `agent-set-model` → app UI;
`mcp-setup` → becomes automatic, per `agent-tool-surface`'s "one tool surface, configured
automatically"; `update-template` → app UI.

Naming note: `start`/`stop`/`status` currently mean *collaboration session* lifecycle. Removing
those frees the names for app lifecycle, which is what a user would expect them to mean.

### 1b. Agent capabilities are API-first; MCP is one adapter

**Correction decided 2026-08-02:** agents need to read selected shared state as well as cause
effects. MCP must not be the only access path: company policy may prohibit MCP servers while still
allowing ordinary local API calls. The product therefore has one canonical agent capability plane
with at least two equivalent adapters:

1. direct HTTP API calls; and
2. MCP tools that delegate to the same application operations or HTTP endpoints.

The React UI is another client of the application API, but it is an operator surface and does not
inherit agent permissions. The reduced CLI is not an agent capability adapter.

Part of this is **already implemented**. Phase 7 collapsed the CLI-side MCP server into a
compatibility re-export; `src/agentweave/mcp/server.py` now carries no tools of its own. Every tool
in `hub/hub/mcp_server.py` calls an existing `/api/v1` HTTP endpoint through `_hub_request`, so MCP
is already an HTTP adapter rather than an independent state implementation. The remaining work is
to make this relationship an explicit, tested contract and replace the soon-to-be-removed CLI
command fallback with first-class direct HTTP access. Deleting the compatibility shim is only the
small mechanical part of that work.

Turn-start injection remains important: queued inbound entries, the roster, the agent charter, and
project instructions should arrive without an initial fetch. It is an onboarding and delivery
guarantee, **not a ban on reads during a turn**. Agents must be able to retrieve information that is
too large, dynamic, or demand-driven to inject safely — for example task details, specification
requirements, evidence, gate state, and the answer to a question they asked.

The read boundary is least privilege rather than grammatical shape. `get_*` and `list_*` are valid
when the information is needed for the agent's work and scoped to the current project/run. Reads
that bypass delivery or governance remain invalid: an agent must not inspect another agent's
undelivered queue, secrets, hidden operator state, or configuration outside its scope. Mutations
remain attributable and governed.

Current surface (12 tools): `send_message`, `create_task`, `list_tasks`, `get_task`, `update_task`,
`ask_user`, `get_answer`, `request_agent`, `create_job`, `delete_job`, `toggle_job`, `run_job`.

Gaps against the stated differentiators:

- **Specification (largest gap).** Spec-driven development with the agents is the hard focus, yet an
  agent has no way to participate in a specification at all. Needs intent-shaped tools for proposing
  a change to a requirement, attaching evidence to a requirement, and recording a verification
  outcome. Blocked behind the specification program's own decomposition.
- **Governance.** `update_task` can move a status, but there is no way to request a review, submit
  evidence, or ask whether a gate is satisfied. Quality gates are a stated differentiator and have
  no agent-facing surface.

**The existing specification is internally inconsistent.** `agent-tool-surface` first limits the
surface to causing effects, then explicitly requires agents to read the task ledger and receive
answers. The latter is the intended behaviour. A successor delta must replace the effect-only
sentence with the least-privilege read boundary above while preserving the prohibition on reading
queued or undelivered entries around the delivery system.

### 1c. Direct API parity needs an identity boundary

The HTTP routes already cover far more than the 12 MCP tools, but endpoint existence is not yet the
same as a supported agent API:

- parity is not enumerated or tested as a capability matrix;
- response/error contracts are not documented for non-MCP callers;
- the approved non-MCP fallback is still CLI commands, which the single-runtime change removes;
- several agent effects accept identity in request bodies or headers while authentication uses a
  project-wide bearer key.

That last point is a security/design gap. `hub/hub/auth.py::_project_from_api_key` authenticates a
project, not an agent or run. `hub/hub/mcp_server.py` adds `X-AgentWeave-Agent` and
`X-AgentWeave-Run`, but a caller holding the same project key can assert different values. Job
mutations validate the pair against a live run; messaging, tasks, and questions do not share one
uniform run-principal dependency.

The target should issue an ephemeral, least-privilege credential when the app starts a run. That
credential binds project, agent, run, expiry, and allowed capabilities. Both direct HTTP and MCP
use it; neither accepts caller-selected attribution. The local operator/UI uses a distinct local
operator principal. The exact token format is a design detail for the capability-plane proposal,
not a reason to retain multi-tenant authentication.

The single-runtime change must not delete the CLI command fallback until direct HTTP parity and
run-bound attribution exist. This is a dependency, not a reason to keep the collaboration CLI.

### 2. Remote deployment leaves scope, and RQ-1 dissolves in its current form

Docker was previously "demoted to a deployment option for remote and multi-user installations."
Local-only removes that. The consequence is larger than it looks: **RQ-1 — operator identity versus
project-scoped authentication — was a question about multi-tenancy, and local-only mostly answers
it.** One operator on their own machine does not need to authenticate to their own app, and projects
become directories rather than tenants.

This likely *unblocks* the multi-project slice and makes it much cheaper than the earlier estimate,
which assumed an operator-identity design. It should be re-examined rather than left marked
"blocked on research."

**Constraint:** do not paint the design into a corner that makes future federation impossible — but
do not build for federation either. Deferred means deferred.

### 3. The specification program moves up in priority

It was sequenced late because it was the least defined. But it is the stated differentiator, and
local-only simplifies **RQ-2 — specification file authority** as well: portable files on one local
filesystem with the database as an index, no multi-user concurrency, no external reconciliation
across machines. The hard part shrinks to identifier stability and external edits by the user's own
tools.

It still needs its own decomposition. It should no longer be treated as the last slice.

### 4. Governance and quality gates are retained assets

Review separation, echo-chamber protection, the task lifecycle, and verification are existing
capability. They are part of the target product, not legacy to be cleaned up. Approval gates
surfaced in the conversation remain the intended integration point.

### 5. Ease of use is a review criterion, not a task

Every slice should be checked against the diagnosis that started this: does it remove a barrier, or
add one? The `init`/roles ceremony was previously identified as the sharpest friction point, and
runner/agent/charter separation is the slice that addresses it — which raises its priority relative
to accounting.

## What this does not change

The `2026-08-02-agent-conversation-workspace` change is unaffected. Its surface is app-only already,
and a local-only product makes the conversation more central rather than less. It remains the first
slice to implement.
