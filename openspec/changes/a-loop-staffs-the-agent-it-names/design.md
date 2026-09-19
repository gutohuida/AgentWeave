# Design — a loop staffs the agent it names

**Round 1, 2026-09-19.** Explored against the tree at `ddf73aa`. Every line number in this document
was read, not recalled; where one is load-bearing the surrounding code is quoted.

**This change must be written against `an-unstaffed-review-names-its-holders` group 1, which builds
first.** That change re-expresses `_agents_that_are_free` as a projection over a new
`_roster_availability`. Every decision below is stated so it holds over either shape, but the task
list is not, and R2 should check that it still does.

## Context

`_agents_that_are_free(session, project_id)` (`hub/hub/scheduler.py:1064`) answers *may a flow give
this agent work*: a non-archived agent with a runner bound, not running, not held by a provider
allowance, and holding no task anything will move. It is **project-scoped**, and it has three
callers — `grep -n "await _agents_that_are_free("` returns `:348`, `:1263`, `:1444` and nothing
else.

Design **D12** of `loop-becomes-a-flow` narrowed the old whole-firing busy guard so a flow could
staff a second agent for independent work while its job's agent was mid-turn. That was right for a
flow. It was implemented project-wide, and `_loop_flow_busy_reason`'s own docstring records the
consequence (`:335-338`):

> Where neither holds, the pool is **project-scoped**, so a loop naming one agent is not
> single-agent as far as this guard can tell: a documentless loop whose agent is mid-turn can hand
> its next pending task to a free sibling (finding F128, the operator's open decision).

**The corpus never permitted that.** `agent-flows:11` — *"A flow is a loop that declares a
specification document"* — says a loop declaring no document "SHALL be unaffected by [the flow
requirements] and SHALL behave exactly as it does today", with the scenario *"WHEN a loop declares
no specification document THEN every firing fires the job's own agent, as before"*. And
`agent-loops:791` explicitly hands the question over rather than answering it: *"This requirement
does not state which agent a firing staffs when another agent in the project is free.
`agent-flows` governs that."* So the rule exists, in the capability that claims it, and the
implementation departed from it.

Two facts make the departure matter rather than merely differ. An `Agent` row carries
`charter_id` (`hub/hub/db/models.py:219`), `runner_id` (`:216`) and
`can_read_checkpoints`/`can_recall`/`can_accept_evidence` (`:254-268`) — so a substitution swaps
behaviour text, runner and authority together. And nothing tells the operator: the job form takes
an agent and the loop list shows one.

## Goals / Non-Goals

**Goals:**

- A documentless loop fires the agent its job names, or fires nobody.
- A flow is bit-for-bit unchanged, including its width.
- The narrowing is a **scope filter over availability**, never a new rule about whether an agent can
  take a turn.
- Every operator-visible sentence that today says *"no other agent is free"* stops saying it where
  it is no longer the reason.

**Non-Goals:**

- Re-homing tasks a past substitution already assigned (see D6).
- Giving a flow a roster of its own.
- A per-job width flag — a flow already *is* the width case.
- Any UI change; with the pool narrowed, `job.agent` becomes true as presented.
- F127's status code, already fixed in `c8e3bbd`.

## Decisions

### D1 — The narrowing is a new named question, not a parameter on `_agents_that_are_free`

Add `_agents_a_loop_may_staff(session, loop, *, default_agent)` to `scheduler.py`. It calls the
existing availability read and filters the result; it never re-derives availability.

*Why not a `limit_to=` parameter on `_agents_that_are_free`:* that function answers a question about
a **project** and knows nothing about loops. Its docstring already draws exactly this line —
*"The roster and the pool differ on purpose (design D5) … They were never the same question"*
(`:1089-1092`) — and pushing a loop concept inside it makes a third question share one name.

*Why not filter inline at each call site:* the rule would then exist in two places and could drift
between them, which is the failure `_agents_that_are_free`'s own *"a third opinion … cannot appear
here"* paragraph (`:1093-1094`) exists to prevent.

*Why it survives group 1:* after that change `_agents_that_are_free` becomes a projection over
`_roster_availability`. A filter sitting **above** the pool is unaffected by which of the two it
reads.

### D2 — For a documentless loop the pool is **empty**, not `{job.agent}`

The job's own agent never comes from the pool. `decide_firing`'s ordinary-work arm reaches the
default agent through its own branch (`:1601-1618`), tested against `running`, `held_agents` and
`taken` and **deliberately not** against `free` — the comment at `:1609-1616` states why, and names
the test that caught the alternative. The pool is read only in the `else` below it (`:1620`), which
is reached exactly when the default agent is already taken, running or held.

So for a documentless loop the pool's correct content in every case where it is consulted is
nothing. Saying `{job.agent} ∩ free` would be the same set by a longer route, and would invite a
future reader to think the default agent is selected from the pool.

**What this removes, deliberately: width for loops.** A documentless loop with two startable tasks
and a free agent today staffs a sibling for the second. After this change the second waits for the
next firing. That is `agent-flows:11` — width is a flow capability, and a loop is not a flow.

*Alternative rejected:* keep a one-element pool so a loop could still run two tasks through one
agent in a firing. `schedule_agent` refuses a second concurrent start for one agent, and design D6
(one agent to one task per firing) already forbids it, so the element would never be selectable.

### D3 — `_loop_flow_busy_reason` collapses to `_loop_agent_busy_reason` for a documentless loop

The guard (`:343-350`) refuses when the job's agent is busy **and** either the loop holds no open
task or the pool is empty. With D2 the pool is empty by construction, so a documentless loop is
refused whenever its agent is busy — which is the pre-D12 behaviour, and what `agent-loops:791`'s
first sentence requires without qualification.

**This is the accepted cost.** A loop pinned to a busy agent now waits, including on the operator's
live instance, where loops that keep moving by substituting will start idling.

### D4 — Two operator-visible sentences stop naming a reason that is no longer true

`run_job` answers 409 with `f"{busy_reason}, and {why}. Nothing was started."`
(`hub/hub/api/v1/jobs.py:1353-1360`), where `why` is one of:

- *"no other agent is free to take this loop's work"* — **false for a documentless loop once the
  pool is scoped.** A sibling may well be free; it is simply not this loop's agent. Design D8's own
  comment (`jobs.py:1352-1354`) gives the standard this breaks: *"Telling the operator nobody else
  is free when somebody is would send them to free an agent, which changes nothing."*
- *"this loop's queue holds no open task for another agent to take"* — the trailing clause is
  equally wrong for a loop; the queue simply holds no open task.

For a documentless loop the sentence becomes, in substance, *"this loop runs only `<agent>`"*. The
flow wording is untouched. **The exact strings are task-level work and are not fixed here**; what
is decided is that the loop and flow cases must not share one sentence.

### D5 — `resolve_reviewer` stays project-scoped, in both its callers

Reviewer resolution is a flow capability. A documentless loop never reaches it from the walk —
`:1653` sends the task to `awaiting_landing` before the review arm, on design D5 / finding F161
grounds. Its other caller is `run_divergence.py:441`, recovering a review turn that recorded no
verdict; for a loop task that review can only have been dispatched by the operator's own hand, and
substituting a project-wide reviewer there is the operator's act being honoured, not a loop staffing
itself. Narrowing it would leave a hand-dispatched review with no possible reviewer, since a loop
names one agent and the resolver excludes the author.

### D6 — Existing substituted assignments are left alone

The walk resumes a task through `task.assignee` (`:1573-1577`), not through the pool, so rows a past
substitution created keep being worked by whoever holds them. Re-homing them would be a data
migration over live rows on the operator's instance, and would interrupt turns in flight to fix
history rather than behaviour.

### D7 — "Documentless loop" is `loop.spec_document_id is None`

The same discriminator the review arm already uses (`:1653`), and the one `agent-flows:11` mandates:
*"The distinction SHALL be the presence of the declared document and nothing else."* No new column,
no new flag.

## Risks / Trade-offs

- **A loop's second startable task now waits, and nothing records that it waited.** The `else`
  branch's `continue` (`:1621-1625`) records nothing — *"Width is bounded by available agents
  (design D5) and this is that bound being reached, not a fault."* For a loop the bound becomes
  "one agent", so the same silence now covers a new case. → **Mitigation:** the board reads the same
  walk and `jobs.py:355` re-asks the busy guard on a stalled decision, so the *loop-level* sentence
  stays right. R2 should check whether a per-task record is owed here, since F23's whole lesson is
  that a bare `continue` is how a working flow reads as broken.
- **The operator's live loops start idling.** → Accepted with the decision, and recorded in the
  proposal as behavioural BREAKING. The loops keep their schedule and resume when their agent frees.
- **Group 1 lands first and rewrites the same function.** → D1 places the filter above the pool so
  either shape works, but the task list must be re-derived against the tree after group 1 builds.
- **`agent-loops:791`'s allowance-hold paragraph and two of its scenarios are conditioned on
  *"no other agent in the project is free"*.** After this change that condition is not necessary for
  a documentless loop, so the spec delta must relax it rather than leave a requirement the code no
  longer meets. → The delta is part of this change, not a follow-up.

## Open Questions

1. **Does a loop's skipped second task deserve a record?** See the first risk. R2 owns deciding
   whether this is F23's silence arriving through a new door or the documented width bound behaving
   as designed.
2. **Does `agent-loops:791` need its unconditional first sentence restated, or only its
   hold paragraph relaxed?** The first sentence — *"The Hub SHALL refuse a firing whose loop agent
   already has a running turn"* — is already unconditional and already describes the post-change
   behaviour. The conditioning lives in the paragraph and scenarios below it. R2 should check
   whether relaxing those is enough, or whether the deferral sentence to `agent-flows` should also
   change now that `agent-flows` answers it explicitly.
