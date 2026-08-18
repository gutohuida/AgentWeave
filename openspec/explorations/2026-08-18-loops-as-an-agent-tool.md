# Loops fire, but they cannot remember

**Status:** exploration. Decides nothing. Written 2026-08-18 in an interactive session, at the
operator's request, ahead of an openspec change. Every claim below names the file and line it came
from; the two headline findings were measured by reading the code, not inferred from the design.

**Why now.** The operator asked whether a `Loop` earns its place in AgentWeave at all:

> "A loop or a job has an agent attached to it. This agent has a charter already. The job makes an
> existing agent loop basically. So I don't know if a loop earns it's place on agentweave."

and then answered their own question with a reframing that is the starting point of this document:

> "So a loop has a overall goal that once completed it finishes. Either queue exhaustion or time
> limit. So I guess it could be one of the tools an agent can use. Create it's own loops and a loop
> has it's own flow of information and execution."

That reframing is right, and the code turns out to agree with it more sharply than expected — by
being missing in exactly the places the reframing predicts.

---

## 1. The thesis

A `Loop` today has two halves. One works completely. The other is not wired at all.

```
   SCHEDULING HALF                          MEMORY HALF
   (fully implemented, exercised)           (columns exist, nothing writes them)

   cron tick                                Task.loop_id            never written
      │                                        │
      ▼                                        ├─ stop_when_queue_empties  → dead
   _do_fire_job()  scheduler.py:296            │
      │                                     AIJob.last_session_id    never written
      ├─ new Conversation (origin="job")       │
      ├─ JobRun + conversation_id              └─ session_mode="resume"    → silent no-op
      ├─ schedule_agent()
      └─ stop_at / stop_reason  ✓           A firing therefore begins knowing
                                            nothing about any firing before it.
```

**A loop can fire on a schedule and stop at a deadline. It cannot accumulate anything.** Every
mechanism intended to carry state from one firing to the next is a read-only column.

That is why the operator's instinct — "a loop has its own flow of information and execution" —
lands on something real. The *execution* exists. The *flow of information* does not.

---

## 2. The evidence

### 2a. `Task.loop_id` — read in five places, written in zero

| Site | What it does |
|---|---|
| `hub/hub/api/v1/tasks.py:427` | filter — `q.where(Task.loop_id == loop_id)` |
| `hub/hub/scheduler.py:86` | count of non-terminal tasks, for the stop condition |
| `hub/hub/scheduler.py:99` | count of *all* tasks ever naming the loop |
| `hub/hub/scheduler.py:417` | `loop_stopped` event payload |
| `hub/hub/schemas/jobs.py:71` | a comment |

No code path assigns it. Not the REST `TaskCreate` schema (`hub/hub/schemas/tasks.py:38-58`), not
MCP `create_task` (`hub/hub/mcp_server.py:212-221`), not the task update path.

Every test that exercises it constructs the row directly in the ORM — `hub/tests/test_scheduler.py:244`,
`hub/tests/test_tasks.py:233,310-312` — because there is no API that would.

**Consequence, and it is not cosmetic.** `stop_when_queue_empties` is dead in production.
`_loop_stop_reason` (`scheduler.py:83-102`) only reports "loop queue is empty" when `ever_count` is
non-zero — a deliberate guard so a loop is not disabled on its first tick before its work exists.
Since `ever_count` can never become non-zero through any real path, the guard is permanently active
and the stop condition never fires. One of a loop's two stop conditions does not work, and nothing
reports that.

### 2b. `AIJob.last_session_id` — read in four places, written in zero

| Site | What it does |
|---|---|
| `hub/hub/scheduler.py:328` | `resume_session_id = job.last_session_id if job.session_mode == "resume" else None` |
| `hub/hub/api/v1/jobs.py:69` | same expression, for the response |
| `hub/hub/api/v1/jobs.py:342` | serialises it |
| `hub/ui/src/components/jobs/JobCard.tsx:323` | renders it when truthy |

Nothing assigns it, and unlike `loop_id` it has **zero test references anywhere in `hub/tests/`**.

**Consequence.** `session_mode="resume"` resolves `resume_session_id` to `None` on every firing and
behaves identically to `"new"`. The operator can select "resume" in the UI, and the UI will render a
session-id block that can never appear. The second continuity mechanism is also a no-op.

### 2c. Why this is a pattern, not two bugs

Both fields are the *statefulness* half of the same feature, and both failed the same way: the
column, the read path, the API surface and the UI were all built, and the single line that writes the
value was never written. The scheduling half — which needs no memory — is complete and correct.

---

## 3. How this got past a careful design

This is worth recording, because the design was not sloppy. `2026-08-16-many-named-loops/design.md`
**D2** specifies `Task.loop_id` in unusual detail: the column type, why there is no foreign key, the
exact `elif` position in `list_tasks`, why `elif` and not `and`, the React Query cache key, and which
existing UI mechanism the "open its queue" affordance reuses. It is a page of careful reasoning.

It never says what writes the value.

The spec delta has the same shape. The requirement is titled *"A loop's queue is the tasks that name
it"*, and its normative content is:

> **A task MAY be linked to a loop.** The Hub SHALL let a caller of the task list scope the result to
> exactly the tasks naming one loop, showing every one of them regardless of status...

Both scenarios are read scenarios. **"A task MAY be linked to a loop" is the entire specification of
queue population** — permissive mood, passive voice, no actor. It reads as though it is covered.

The mechanism of the error is precise and worth generalising: **D2 modelled `loop_id` on its sibling
`Task.spec_document_id`, and copied the read half of that pattern without the write half.**
`spec_document_id` is genuinely written, at `hub/hub/api/v1/tasks.py:324,341`, derived during task
creation from the resolved requirement documents. `loop_id` got the filter, the index, the UI and the
cache key — everything except line 341's equivalent.

> **A lesson for the spec format itself.** A requirement written in the passive voice with no actor
> ("a task MAY be linked to a loop") cannot be checked for completeness, because there is no subject
> whose behaviour a scenario could describe. Every requirement about state should have to name who
> writes it. That is a candidate rule for AgentWeave's own validator, and it is a finding about the
> spec flow, not just about loops.

---

## 4. The reference implementation is already in this repository

`.claude/autonomous/` is a working implementation of exactly the feature under discussion — durable,
terminating, queue-driven work that survives the death of the process running it. It has been driven
across several multi-hour runs, including one that died mid-run and was resumed by a later firing
with nothing lost. Mapping it against `Loop` is the cheapest design evidence available.

| `.claude/autonomous/STATE.json` | `Loop` / `AIJob` today | Gap |
|---|---|---|
| `purpose` | `Loop.purpose` | — |
| `stop_at` | `Loop.stop_at` | — |
| `stop_when_queue_empties` | `Loop.stop_when_queue_empties` | dead (§2a) |
| `stop_reason`, `stopped_at` | same | — |
| `iteration` | `AIJob.run_count` | — |
| `queue[]` — id, title, why, steps, status | `Task` rows via `loop_id` | **unwritable** (§2a) |
| `current` | D7's computed `current_task` | — |
| **`next_action`** — written for a stranger | `AIJob.message`, fixed, replayed verbatim | **no equivalent** |
| **`last_heartbeat`** + takeover grace | nothing | **no equivalent** |
| **`decisions_for_user`** — escalate without stalling | `ask_user`, which **blocks** | **shape mismatch** |
| **`known_debts`** — what was tried and failed | nothing | **no equivalent** |
| `limits` | the agent's charter | — (charter already covers this; see §6) |
| the prose log | `JobRun` + its conversation | partial |

Four gaps are load-bearing.

**`next_action` is the important one.** The driver's own prompt is deliberately short, and says why:

> *"Everything the iteration needs to know is on disk; restating it here would create a second source
> of truth that drifts from the file the session actually maintains."*

`AIJob.message` is the exact inverse: the instruction lives in the job row, is identical on every
firing, and disk holds nothing. The driver's design works because **each iteration rewrites
`next_action` for the next one.** A loop has nowhere to write that.

**`last_heartbeat` is mutual exclusion.** The driver stands down when a heartbeat is fresh, and takes
over when it goes stale. Nothing equivalent guards a `Loop`: if a firing outlives its cron interval,
what happens is undefined. (The Windows task solves its own half with `MultipleInstances IgnoreNew`;
the Hub scheduler has no such setting that I found. **Unverified** — I did not test overlapping
firings, and this should be checked before it is asserted in a spec.)

**`decisions_for_user` is the governance-shaped one.** AgentWeave already has operator escalation —
`ask_user`, permission prompts — and both **block** with a timeout. For a loop firing unattended at
3am, blocking is the wrong default: it burns the firing. The driver's answer is to record the
decision and keep working, and the operator reads a list on return. That is a genuinely different
escalation mode from anything the product has, and it is the one an unattended loop needs.

---

## 5. The design fork

Given §2, there are two coherent ways to give a firing memory, and they are not variations of each
other — they differ in where the state lives and therefore in whether the operator can see it.

```
   A. RESUME THE CONVERSATION              B. RE-DERIVE FROM DURABLE STATE
   ───────────────────────────             ──────────────────────────────
   Fix last_session_id so                  Fix loop_id so the queue is
   session_mode="resume" works.            fillable; brief each firing from
   The agent remembers because it          the queue + a next_action the
   is the same conversation.               previous firing wrote.

   + one line to fix, mechanism exists     + survives compaction and restart
   + no new concepts                       + operator can SEE the state
   + cheapest possible change              + auditable: every firing's
                                             reasoning is a written artefact
   - context grows without bound           - more to build
   - a compaction silently loses it        - the agent must be disciplined
   - state is buried in a transcript,        about writing next_action
     not visible as fields
   - governance-hostile: "what is this
     loop doing" needs reading a chat
```

**The repository has already run this experiment.** The autonomous driver deliberately chose B, and
its own prompt states the reason: *"You are a fresh process with no memory of previous iterations —
everything you need is on disk."* That choice is what let a run die at 07:41 and be picked up by the
next firing at 07:56 having lost nothing. A resumed conversation would not have survived it.

AgentWeave's stated philosophy points the same way. The operator framed this whole thread as
*"governance and visibility"*, and B is the only option where a loop's state is a thing an operator
can look at rather than a transcript they must read. A is cheaper and would make `resume` honest;
it is not a substitute.

**Not decided here.** They are also not exclusive — B is the substance, and A is worth fixing anyway
so that a shipped, selectable option stops silently doing nothing.

---

## 6. What the change will have to settle

Carried forward to the spec, with no answer asserted here:

1. **Who writes `Task.loop_id`?** Candidates: `create_loop` accepts an initial task list; the
   creating agent files tasks into a loop it owns; the loop's first firing is a *planning* firing
   that decomposes `purpose` into tasks. The third is the most autonomous and the hardest to
   supervise; the first is the most legible.
2. **What connects a firing to the queue?** Does a firing *claim* the next task, or is it *briefed*
   on the queue and left to choose? Claiming is more governable; choosing is more capable.
3. **What is in the briefing, and what caps it?** A loop that runs for a month cannot carry every
   prior firing's conclusions into its turn.
4. **Where does the next firing's instruction live?** `AIJob.message` is fixed by design. Something
   has to be writable by the firing itself — the `next_action` equivalent.
5. **Two firings at once** — prevented, queued, or undefined? (See the §4 caveat: unverified.)
6. **Does an agent create loops for itself?** `hub/hub/api/v1/jobs.py:93 _loop_opts_in()` already
   means any one of `purpose` / `stop_at` / `stop_when_queue_empties` on `POST /jobs` makes a job a
   loop — but MCP `create_job` (`mcp_server.py:503-529`) exposes none of the three. **An agent can
   create a job that runs forever and cannot create a loop that ends.** The permission gate already
   exists (`jobs.py:21 _require_agent_job_allowance`), so this is a tool-surface gap, not a safety
   one. Prefer a distinct `create_loop` over widening `create_job`: a separate name teaches the
   concept exists, where an optional argument hides it.
7. **Governance bounds.** May a loop's agent create another loop? What caps unattended spend? What
   happens when a firing fails, or the agent goes off-task? Raised, not answered.
8. **The dangling agent.** `AIJob.agent` is a bare `String(64)`, not a foreign key, and
   `scheduler.py:51-56` returns `None` — meaning *proceed* — when no agent row matches the name. Rename
   or archive an agent and its loops keep firing at a name nobody owns.

---

## 7. On whether a loop earns its place

The operator's original doubt deserves a direct answer.

A bare `AIJob` is already "an agent on a schedule". If that were all a `Loop` were, it would not earn
a table. What distinguishes it is precisely the two things §2 shows are unwired: **it terminates**,
and **it owns a backlog**. Those are real and they are not expressible as a cron.

So the concept earns its place — but *on the strength of the half that has never worked.* Today,
stripped of its memory, a `Loop` really is a renamed `AIJob` plus a `stop_at` that works and a
`stop_when_queue_empties` that does not. The operator's scepticism was well aimed at what is
currently shipped; the answer is to build the missing half, not to retire the concept.

**Proposal A from `2026-08-17-architecture-proposals.md` is rejected** and should not resurface. It
proposed `Loop.charter_id` and loops as roster siblings of agents. The charter half is wrong on the
evidence: `hub/hub/api/v1/agents.py:1060-1064` builds a turn's charter from `agent_row.charter_id`, so
a loop's charter would be a second charter competing for the same turn with no precedence rule — and
a loop already has an agent, which already has one. The roster half is wrong for the same reason: if
a loop's identity is its agent, listing them as siblings shows `claude-dev` and `nightly-scan` side by
side when the second *is* the first on a cron. A loop belongs **under** its agent.

---

## 8. What this exploration did not verify

- **Overlapping firings.** Asserted nowhere; §4 flags it. I did not test what the Hub scheduler does
  when a firing outlives its interval.
- **Whether `resume` ever worked.** `last_session_id` has no write path *now*; I did not search the
  git history for one that was removed.
- **The 30 `openspec/specs/` capabilities** were not read for an existing requirement that contradicts
  §2. The two headline findings rest on the code, which is authoritative for what ships, but a
  contradicting shipped requirement would be worth knowing about.
- **Nothing here was driven live.** No loop was created, fired, or watched during this exploration.
  Given that the last live trial of a shipped spec mechanism (the first capability merge, 2026-08-18)
  found three defects in under an hour, a live trial of a loop should be assumed to find more.
