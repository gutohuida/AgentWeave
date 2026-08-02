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
substrate*: `switch`, `set-session`, `watch`, transport setup, the messaging and task commands, and
the CLI-side MCP server that exists only so agents can reach a local filesystem session.

**Open:** exactly which commands survive as launcher/diagnostics. Needs a decision before the
single-runtime change can be written.

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
