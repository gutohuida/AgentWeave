# Exploration — enforcing the development cycle, and where hooks may sit

**Date:** 2026-08-10
**Status:** thinking document. No change proposed yet; it reshapes the sequencing of B1/B3/B4.
**Raised by the operator:**

> "Today the task progress, testing, assignment all depends on agents remembering to deal with the
> tasks. How can we make it enforced by agentweave? Also, should we start considering claude/codex
> hooks? What about when I implement a different technology that doesn't have hooks. Hooks are cool
> but we should[n't] rely on them 100% yet because it's not something implemented by everyone."

> "What I want is a mix of AI managing workflow with enforced agentweave rules in the development
> cycle."

---

## The finding underneath both questions

**A run does not know what task it is working on.** `Run` (`hub/hub/db/models.py:700-728`) carries
project, agent, session, conversation, pid, heartbeat — and no task. The `task_id` at
`models.py:420` belongs to `Message`, not `Run`.

The link exists in exactly one weak form: `send_message` takes an optional `task_id`
(`hub/hub/mcp_server.py:173`), so a *delegation* may name a task. It is optional, it is not
validated against what the receiving run then does, and it never reaches the `Run` record.
`request_agent(name, template, task)` (`mcp_server.py:425`) takes `task` as **free text**, not an
id. The trigger path (`hub/hub/api/v1/agent_trigger.py`) has no task concept.

So the ledger depends on agents remembering **because the runtime holds no link that would let it
know instead.** This is not a discipline problem to be solved with better charter wording. It is a
missing edge in the data model.

## Three properties, currently conflated

| Property | Question it answers | Status |
|---|---|---|
| **Validity** | Is this move legal, and is the actor allowed to make it? | **B1, proposed** (`2026-08-10-task-transition-machine`) |
| **Liveness** | Did a move happen at all, when reality changed? | **Nothing. This is the operator's question** |
| **Fidelity** | Does the record match what actually occurred? | Follows from liveness plus B3's evidence |

B1 makes it impossible to record a *wrong* transition. It does nothing about a *missing* one — an
agent that does the work and never touches the ledger passes every check B1 introduces, because it
never asks for anything.

Worth stating plainly: **B1 is necessary and not sufficient**, and shipping it will not make the
board trustworthy on its own.

## Four tiers of enforcement, none of which needs a hook

Ordered strongest first. "Universal" means: works for Claude, Codex, and a runner that does not
exist yet, because it sits at a boundary AgentWeave owns rather than inside the agent.

### Tier 1 — Derive it rather than ask for it (universal)

The strongest enforcement is removing the need to remember. If AgentWeave spawns a run *for* a
task, AgentWeave moves that task to `in_progress` itself. The agent is never asked, so it cannot
forget, and the transition is attributed to the run that actually started.

Requires the missing binding: a task id on `Run`, populated at trigger time from whatever caused
the run (a delegation's `task_id`, an operator starting work on a board item, a scheduled job).

This is the tier that removes the largest share of the problem, and it is mostly plumbing.

### Tier 2 — Gate the run boundary (universal)

AgentWeave owns process start and exit for every runner — that is the whole premise of the product
(`Run` exists "as the Hub's record of owning a spawned run"). At exit it can observe: this run was
bound to task X, and X took no transition. That run is not clean.

What to do with that is a design choice — raise it to the operator, queue a reconciliation turn,
mark the run as having diverged. The point is that the observation is **available outside the
agent**, which is what makes it enforcement rather than instruction.

This is the tier that answers "liveness" directly.

### Tier 3 — Gate the capability plane (universal)

Every agent effect already goes through the Hub API, with MCP as a thin adapter over the same
contract (`openspec/specs/agent-capability-plane/spec.md`). So task state can become a
**precondition** of things the agent wants: taking new work while holding a stale task, submitting
checkpoint notes against a divergent ledger, delegating work whose task never moved.

This inverts the incentive. Bookkeeping stops being a chore that can be skipped at no cost and
becomes a gate on the agent's own progress.

### Tier 4 — Salience (universal, weak, free)

Turn-start state injection already exists. Injecting "you have held task X in `in_progress` since
14:02 with no transition" does not enforce anything, but it removes *forgetting* as a failure mode
and gives the model what it needs to manage itself — which is the half of the mix the operator
asked for.

## Where hooks sit — and the rule

**The repo has already answered this question once, in another domain.**
`hub/hub/runner_commands.py:19-21`: Claude permission posture is stated explicitly by the Hub
"rather than from whatever `~/.claude/settings.json` says on the machine the Hub runs on." Hooks
live in that same file. Building enforcement on them would reverse a decision already taken
deliberately, for exactly the reason the operator gives.

Three further problems with hooks as a foundation:

1. **Per-machine, per-user.** A teammate's checkout has none of them unless AgentWeave writes into
   their home directory, which is invasive and unversioned.
2. **Runner-specific and unevenly shaped.** Claude Code's hook model and Codex's are not the same
   surface, so a rule expressed as a hook must be written twice and will drift.
3. **A future runner may have none**, and would become structurally second-class the moment a
   capability lived only there.

**Proposed rule: no capability may exist only in a hook.**

A hook is permitted to make an existing, independently-enforced rule fire **sooner** — at the
offending tool call rather than at run end — or **more pleasantly**, as a message inside the agent's
own transcript rather than a rejection after the fact. Remove the hook and the identical rule still
fires at the boundary, just later. Under that rule, hooks become a latency and ergonomics
optimisation that can be adopted per-runner, and no runner is disadvantaged by lacking them.

This is worth writing into the capability-plane spec, not just this document, because it is the kind
of constraint that gets forgotten and then violated by a convenient shortcut.

## The division of labour the operator asked for

| The AI decides | AgentWeave enforces |
|---|---|
| What to work on next, and how to decompose it | That the transition is legal (B1) |
| Whether the work is genuinely done | That it is attributed, append-only (B1) |
| What evidence is worth capturing | That it *happened* when reality changed (tiers 1–2) |
| When to stop and ask the operator | That it was earned (B4 gates) |
| How to interpret an ambiguous requirement | That the actor was entitled to make it (B1) |

The AI proposes; the runtime disposes. Neither half is advisory: the AI is not told which transition
to make, and the runtime does not judge whether the work was good.

## What this implies for the change sequence

- **B1 stands as proposed and does not need to grow.** Its author/reviewer rule reads the run
  recorded *on the transition*, so it works without a run→task binding. Folding the binding in would
  make it bigger without making it more correct.
- **A new change sits between B1 and B3** — the run→task binding plus run-boundary reconciliation
  (tiers 1 and 2). It is the missing prerequisite for B3's evidence having anything to attach to:
  evidence is produced *by a run*, about *a task*, and that edge does not currently exist.
- **Tier 3 is mostly B4.** Completion gates and "you may not do X while the ledger is stale" are the
  same mechanism pointed at different preconditions.
- **The hook rule belongs in `agent-capability-plane`** as a requirement, and should land with
  whichever change first has cause to touch that spec.

## Open questions

1. **What should a divergent run actually do?** Refusing to end a run is not possible — the process
   exits. The realistic options are: mark the run diverged and surface it, auto-queue a
   reconciliation turn, or block the *next* run for that agent until it is resolved. The third is
   the strongest and the most annoying.
2. **Can one run be bound to more than one task?** A run that fixes three related board items is
   normal. If binding is one-to-one, agents will work around it; if many-to-many, "did the task
   move" becomes ambiguous.
3. **Is an unbound run legitimate?** Exploration, questions, and conversation are real work with no
   task. If unbound runs are allowed, an agent can evade tier 2 by never binding — so binding may
   need to be something the *runtime* decides, not the agent.
4. **Does auto-`in_progress` fight the operator?** If AgentWeave moves a task the moment a run
   starts, a run the operator triggered to merely *look* at something has changed the board.
   Related to question 3.
5. **How does this interact with B1's open question** — whether `in_progress → completed` should be
   restricted to the assignee? A run→task binding makes assignee enforcement natural, where today it
   would be guesswork.
