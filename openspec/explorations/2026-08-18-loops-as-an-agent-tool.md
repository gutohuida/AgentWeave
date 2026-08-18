# Loops fire, but they cannot remember

**Status:** exploration. Decides nothing that is the operator's, and records what they did decide.
Written 2026-08-18 in an interactive design session, ahead of an openspec change. Code claims name
the file and line they came from and were measured, not inferred from the design documents.

**How this came about.** The operator questioned whether a `Loop` earns its place at all:

> "A loop or a job has an agent attached to it. This agent has a charter already. The job makes an
> existing agent loop basically. So I don't know if a loop earns it's place on agentweave."

The code turns out to agree with the doubt — by being missing in exactly the places that matter.

---

## 1. The thesis

A `Loop` has two halves. One is complete. The other was never wired.

```
   SCHEDULING HALF                          MEMORY HALF
   (implemented, exercised)                 (columns exist, nothing writes them)

   cron tick                                Task.loop_id            never written
      │                                        │
      ▼                                        ├─ stop_when_queue_empties  → dead
   _do_fire_job()  scheduler.py:296            │
      │                                     AIJob.last_session_id    never written
      ├─ new Conversation (origin="job")       │
      ├─ JobRun + conversation_id              └─ session_mode="resume"    → silent no-op
      ├─ schedule_agent()
      └─ stop_at / stop_reason  ✓           A firing begins knowing nothing
                                            about any firing before it.
```

**A loop can fire on a schedule and stop at a deadline. It cannot accumulate anything.**

## 2. The evidence

### 2a. `Task.loop_id` — read in five places, written in zero

`tasks.py:427` (filter), `scheduler.py:86` and `:99` (stop-condition counts), `scheduler.py:417`
(event payload), `schemas/jobs.py:71` (a comment). No code path assigns it — not the REST
`TaskCreate` schema (`schemas/tasks.py:38-58`), not MCP `create_task` (`mcp_server.py:212-221`), not
the update path. Every test exercising it builds the row directly in the ORM
(`test_scheduler.py:244`, `test_tasks.py:233,310-312`) because no API would.

**`stop_when_queue_empties` is therefore dead in production.** `_loop_stop_reason`
(`scheduler.py:83-102`) only reports "loop queue is empty" once `ever_count` is non-zero — a
deliberate guard so a loop is not disabled before its work exists. Since `ever_count` can never
become non-zero, the guard is permanently active. One of a loop's two stop conditions does not work,
and nothing reports that.

### 2b. `AIJob.last_session_id` — read in four places, written in zero

`scheduler.py:328`, `jobs.py:69`, `jobs.py:342`, and `JobCard.tsx:323` renders it. Nothing assigns
it, and it has **zero test references anywhere in `hub/tests/`**. So `session_mode="resume"`
resolves to `None` every firing and behaves identically to `"new"`, and the UI can render a
session-id block that never appears.

Two continuity mechanisms, both read-only. That makes it a pattern, not two bugs: the half that
needs no memory is complete; the half that *is* memory is uniformly unwired.

## 3. How this passed a careful design — and the lesson

`2026-08-16-many-named-loops/design.md` **D2** specifies `Task.loop_id` across a page: column type,
why no foreign key, the exact `elif` position in `list_tasks`, why `elif` and not `and`, the React
Query cache key, which UI mechanism the "open its queue" affordance reuses. It never says what
writes the value.

The spec delta has the same shape. The requirement *"A loop's queue is the tasks that name it"* reads:

> **A task MAY be linked to a loop.** The Hub SHALL let a caller of the task list scope the result...

Both its scenarios are read scenarios. **"A task MAY be linked to a loop" is the entire specification
of queue population** — permissive mood, passive voice, no actor.

The mechanism is precise: **D2 modelled `loop_id` on its sibling `Task.spec_document_id` and copied
the read half without the write half.** `spec_document_id` is genuinely written, at
`tasks.py:324,341`. `loop_id` got the filter, index, UI and cache key — everything except that line.

> **A candidate rule for AgentWeave's own validator.** A requirement written in the passive voice
> with no actor cannot be checked for completeness, because there is no subject whose behaviour a
> scenario could describe. **Every requirement about state should have to name who writes it.**
> This is a finding about the spec flow, not only about loops.

## 4. What a loop is for

The operator's own statement of purpose, which drives every design choice below:

> "The loop should be a way to execute something in a period of time were the user can be doing
> another thing. Specing a new feature, testing, sleeping. I don't need to be here driving
> everything. Also the loop helps with **context management** since it's not a single unstopped
> session with more and more polluted context and help with **governance and visibility** since we
> need checkpoints and stages between tasks and executions."

Three purposes, and the second is the one that settles an otherwise open question — see §6.

## 5. The governance model: the queue's author is not its executor

The operator's design, recorded as given:

> "Loops can have their own tasks. A spec is one source. Loops can be attributed to other agents. If
> a loops is created by the architect and attributed to the developer only the creator can create
> new tasks. So either the agent will have to send a message to the architect agent with a
> explanation on why it needs another task or the user will have to talk with the architect to add
> another task. Agent can create loops for themselves but once the loop is defined only with user
> approval then can add more tasks."

```
   CREATOR (e.g. architect)               EXECUTOR (e.g. developer)
   ────────────────────────               ─────────────────────────
   defines the loop                       works the queue down
   authors the queue      ──── loop ────▶ CANNOT add tasks
     ├ spec-materialised tasks            may only ask, with a reason
     └ hand-authored tasks                        │
          ▲                                       │
          └───────────────────────────────────────┘
                 send_message to the creator

   agent-created loop → extending it needs USER approval
```

**Why this matters beyond permissions.** Separating author from executor is what makes termination
safe. A loop whose executor can file its own tasks controls its own stop condition — it can always
add one more and never terminate. Under this model it structurally cannot.

**Two work sources.** Spec-declared tasks are one: `spec_tasks.materialise()` creates the tasks a
document declares when it is approved, idempotent by `(document, key)`. That module exists because
of a measured failure — *"an operator approved nineteen requirements and got nothing"* — and it is
AgentWeave's real work-generation mechanism. Creator-authored tasks are the other.

**On an empty queue with an unanswered request — terminate.** Operator's decision:

> "It should terminate. The architect can create another one. We can track this kind of information
> and improve the loops. Try to find why it only detects a new task at the end of the loop, how many
> tasks were added from the initial process etc. This will give us visibility and governance over
> the process."

The mechanism stays simple and the exception becomes **telemetry**. That is the better trade: a
third "paused pending a request" state would complicate every reader of a loop's status, whereas
"how often did a loop discover work late, and how much" is exactly the data that would improve loop
authoring.

## 6. Continuity: checkpoints, not a resumed conversation

There were two coherent ways to give a firing memory. **The operator's context-management purpose
(§4) settles it.**

| | Resume the conversation | Re-derive from durable state |
|---|---|---|
| Mechanism | fix `last_session_id` so `session_mode="resume"` works | brief each firing from the queue and the prior checkpoint |
| Cost | one write path | more to build |
| Context | **grows without bound across firings** | each firing starts clean |
| Survives compaction / restart | no | yes |
| Operator can see the state | no — it is inside a transcript | yes — fields and artefacts |

Fixing `resume` would rebuild the precise problem loops exist to solve: *"not a single unstopped
session with more and more polluted context."* **Rejected as the continuity mechanism.** It should
still be either fixed or removed, because a shipped, selectable option that silently does nothing is
its own defect (§2b) — but it is not the answer here.

**AgentWeave already has the right mechanism, and it was built for exactly this.**
`checkpoint_generation.py` describes its own purpose as the control-plane literature's **blind
resume**: *"give a reader nothing but the checkpoint and ask it the questions the Hub can already
answer, then compare"*, reading the artefact *"exactly as a successor receives it."* A loop firing
**is** a successor with no memory. Checkpoints even carry a quality gate the obvious alternative
lacks: `compute_envelope` (`checkpoints.py:224`) computes `files_changed`, `tasks` and
`open_questions` deterministically, and a probe grades the written body against them.

**The gap is small and specific.** Checkpoints are *conversation*-scoped — `runs_to_cover(…,
conversation.id, anchor)`, `_open_questions_for(conversation.id)` — and `_tasks_for` scopes by
*agent*. But every firing creates a **new** conversation (`origin="job"`). So:

1. checkpoint chaining must be keyed by **loop**, across conversations, not within one; and
2. the envelope's `tasks` should be **the loop's queue**, not the executing agent's tasks.

## 7. What already exists, and what does not

| Need | Already there | Missing |
|---|---|---|
| Work generation | `spec_tasks.materialise()` on approval | nothing writes `loop_id` |
| Loop-ness | `_loop_opts_in()` (`jobs.py:93`) — any of `purpose`/`stop_at`/`stop_when_queue_empties` | — |
| Agent permission to create recurring work | `_require_agent_job_allowance` (`jobs.py:21`) | — |
| Agent-facing loop creation | — | MCP `create_job` (`mcp_server.py:503-529`) exposes **none** of the three loop fields, so an agent can create a job that runs forever and **cannot create a loop that ends** |
| Asking the creator for more work | `send_message` calls `schedule_agent` (`messages.py:257-259`), so **a message starts the recipient's turn**; it already accepts `conversation_id` | — |
| Addressing the creating session | `Loop.created_by_run_id` → `Run.conversation_id` (`models.py:973,988`) — **resolvable today, no schema change** | — |
| "What stage is the loop in" | `_batch_loop_summaries` (`jobs.py:98`) computes per-loop queue counts in four fixed queries (design D7) | — (operator's decision: a stage **is** task-lifecycle position, derived from statuses — no new concept) |
| Continuity between firings | checkpoints, envelope, probe | loop-scoped chaining; loop-scoped `tasks` in the envelope |

## 8. Open, and carried to the spec

1. **Who exactly writes `Task.loop_id`**, for each of the two sources, stated as a requirement that
   names its actor (§3).
2. **What a firing does with the queue** — claim the next task, or be briefed and choose.
3. **`create_loop` vs widening `create_job`.** Prefer a distinct tool: a separate name teaches the
   concept exists, where an optional argument hides it. Not decided.
4. **Creator identity is now load-bearing** — "only the creator can add tasks" is a permission rule —
   but `AIJob.agent` is a bare `String(64)` with no foreign key, and `scheduler.py:51-56` returns
   `None`, meaning *proceed*, when no agent row matches the name. Archive or rename the creator and
   the permission model loses its author. **Unresolved.**
5. **Loop telemetry** (§5): what is recorded, and where an operator reads it.
6. **Overlapping firings** — prevented, queued, or undefined? See §9.
7. **Spend bounds** for unattended work, and whether a loop's executor may create loops of its own.

## 9. What this exploration did not verify

- **Nothing was driven live.** No loop was created, fired or watched. The last live trial of a
  shipped spec mechanism (the first capability merge, 2026-08-18) found three defects in under an
  hour; a live loop trial should be assumed to find more.
- **Overlapping firings.** Not tested. I did not establish what the Hub scheduler does when a firing
  outlives its cron interval.
- **Whether `resume` ever worked.** `last_session_id` has no write path now; the git history was not
  searched for one that was removed.
- **`openspec/specs/`** was not read for a shipped requirement contradicting §2. The code is
  authoritative for what ships, but a contradicting requirement would be worth knowing about.

## 10. Does a loop earn its place?

Yes — but on the strength of the half that has never worked. A bare `AIJob` is already "an agent on a
schedule"; if that were all a `Loop` were, it would not earn a table. What distinguishes it is that
it **terminates** and **owns a backlog**, and neither is expressible as a cron. Stripped of its
memory, today's `Loop` really is a renamed `AIJob` with one working stop condition and one dead one.
The operator's scepticism was well aimed at what is shipped; the answer is to build the missing half.

**Proposal A from `2026-08-17-architecture-proposals.md` is rejected and should not resurface.** It
proposed `Loop.charter_id` and loops as roster siblings of agents. The charter half is wrong on the
evidence: `agents.py:1060-1064` builds a turn's charter from `agent_row.charter_id`, and a loop
already has an agent which already has one — a second would compete with no precedence rule. The
roster half is wrong for the same reason: if a loop's identity is its agent, listing them as siblings
shows `claude-dev` and `nightly-scan` side by side when the second *is* the first on a cron. A loop
belongs **under** its agent.
