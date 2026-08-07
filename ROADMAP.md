# AgentWeave Roadmap

Where the product is going, and where the detail lives.

**The authoritative statement of direction is
[`openspec/explorations/2026-08-02-product-direction.md`](openspec/explorations/2026-08-02-product-direction.md).**
Read it before proposing anything structural. It exists specifically so that the scope deliberately
removed on 2026-08-02 is not quietly restored by someone who did not know it was removed.

---

## The product

AgentWeave is a **locally-installed application, and that is the only way to use it.** Install it,
run it, and it owns the agent processes on your machine. There is no no-Hub product and no CLI-only
collaboration mode.

The diagnosis behind that narrowing, in the product owner's words: *"I think I jumped the gun with
the architecture trying to make everything at once, local dev, online cooperation, company wide hub
etc."* Trying to satisfy three deployment models at once made the simplest path — one developer, one
machine, a few agents — carry the ceremony of all three.

What AgentWeave has that a single-agent coding tool does not, and what it is actually for:

1. **Multi-agent collaboration** — several agents on one project, addressable, with inter-agent
   communication in the runtime rather than bolted on.
2. **Spec-driven development with the agents** — requirements, tasks, runs and evidence connected to
   each other and to the conversation. This is the differentiator, not a side feature.
3. **Governance and quality gates** — review separation, echo-chamber protection, verification
   before completion.

**The organising constraint is ease of use.** Where a capability and a barrier conflict, the barrier
loses.

---

## What exists today

- **A local app.** `agentweave` starts it on the current directory; the CLI does only what cannot be
  done from inside the app (`doctor`, `status`, `stop`, `reset`). Five commands, down from 56.
- **Hub-owned execution.** Claude and Codex spawn from the Hub, stream over SSE, and are the only
  two wired to a real spawn path — others are refused with a stated 501.
- **Multiple projects** in one local instance, each a directory with its own agents, conversations
  and settings.
- **Runners, agents and charters** as three separate concepts, bound in the UI.
- **A run-scoped agent capability plane.** Each run gets a short-lived credential; identity is never
  accepted from a request body or header. MCP and direct HTTP are two adapters over the same
  actions.
- **Operator-in-the-loop.** Permission postures answered from the conversation, blocking structured
  questions with batching, and a backstop for a question an agent forgot to ask.

## What is next

1. **The specification program.** The largest gap and the stated differentiator: an agent currently
   has no way to participate in a specification at all — no tool to propose a change to a
   requirement, attach evidence, or record a verification outcome. It needs its own decomposition
   and should no longer be treated as the last slice.
2. **Governance and quality gates, agent-facing.** `update_task` can move a status, but nothing can
   request a review, submit evidence, or ask whether a gate is satisfied.

Both are named in the direction document. Everything else is smaller.

## Deferred, not abandoned

- **Federation.** A hub returns far in the future as a place to connect your *local* agents to
  agents belonging to *other* users — federation between local installs, not a company server. It
  waits until the local experience is worth federating. Do not build for it; do not paint the design
  into a corner that forbids it.
- **A general-purpose CLI.** May be revived if a reason appears. With collaboration inside the app,
  there is currently no evident one.

---

## Where the detail lives

| Question | Where |
|---|---|
| Why is the architecture like this? | `openspec/explorations/2026-08-02-product-direction.md` |
| What does capability X do today? | `openspec/specs/<capability>/spec.md` |
| What is being built right now? | `openspec/changes/<date>-<name>/` |
| What was built, and why that way? | `openspec/changes/archive/` |
| What shipped in which release? | [`CHANGELOG.md`](CHANGELOG.md) |

The phase-by-phase history that used to live in this file — transports, proxy agents, roles, pilot
mode, declarative config — described subsystems that have since been removed. It is preserved in the
changelog and the change archive, which is where history belongs.
