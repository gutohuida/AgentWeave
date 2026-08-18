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

### 5a. Creator and controller are two different subjects

A first pass at this section asked who may extend a loop the *operator* created, since
`created_by_run_id` is populated from the `X-AgentWeave-Run` header and
`_require_agent_job_allowance` treats the absence of headers as "this is the operator"
(`jobs.py:21-27`) — so an operator-created loop would record no creator at all, leaving the rule with
no subject. The operator dissolved the premise:

> "The operator will never create loops by himself. He will do it with an agent. So we have two
> subjects there. The one who created and the one who controls it. The operator can create a loop
> with the an agent but be the one in control. This mean that any new task or decision should reach
> the operator via the agent he used and only the operator can decide on it. But the operator can
> leave the control to the agent that can decide for himself."

```
   CREATOR ─────────── CONTROLLER ─────────── EXECUTOR
   the agent whose      operator (default)     the attributed agent
   run made the loop    or, if delegated,      works the queue down
                        the creator agent      cannot add tasks

   executor needs work
        └─▶ messages the CREATOR
                ├─ operator-controlled: the creator relays it; only the operator decides
                └─ delegated:           the creator decides for itself
```

So a loop always has a creating agent — loops are made *through* a conversation, never by the
operator directly — and control is a separate, per-loop setting.

**There is an exact precedent for the control field.** `Agent.default_permission_mode`
(`models.py:196`) is nullable with the comment: *"NULL for the built-in default — a row storing
today's default would keep saying it after the default moved. This is the same choice the composer's
Permissions pill makes."* A loop's control setting wants the same shape: nullable, inheriting, with
NULL meaning the current default rather than a stored copy of it. It is the same operator-in-the-loop
posture the product already applies to permissions, pointed at queue extension.

**What this fixes and what it does not.** It removes the missing-subject problem entirely. What
remains is ordinary identity hygiene, described in §8 item 4.

### 5b. A loop is editable, and an edit lands on a boundary

Control is handed over after creation, the operator adds tasks, and a loop's definition changes over
its life. The operator's constraint:

> "But we need enforcements not to break the loop. If I'm editing a loop it only goes after no run is
> active."

**Decided: an edit is always accepted, and applied at the next firing boundary.** The firing in
flight keeps the briefing it started with; the change takes effect when the next one is briefed.

```
   firing N running          edit accepted          firing N+1
   briefed at start   ───────────────────────────▶  briefed with the edit
        │                    stored as pending           │
        └── unaffected ──────────────────────────────────┘
```

Rejected: **refusing the edit while a run is active** (a 409 the operator has to retry, and a long
firing locks them out of their own loop); and **applying it immediately** (no new machinery, but a
firing that re-reads its queue mid-turn would observe a change it was never briefed on). Staging is
the only option that neither blocks the operator nor lets a firing see two different worlds.

The cost is a state the UI must show: **what is pending versus what is live.** A loop with a staged
edit and no visible sign of it is worse than a refused edit.

**The closing window.** Gating on "no run active" protects a firing in flight but not the end: the
queue empties, the loop terminates, and a task added a moment later arrives at a stopped loop.
Decided: **refuse the late task, state why, and offer to carry it into a new loop.** Termination
stays final — consistent with §5's "the architect can create another one" — without discarding work
the operator had already written. Rejected: reviving a terminated loop (a stopped thing becoming live
again is a state change that is hard to render honestly), and holding termination off during an edit
session (which reintroduces the third state §5 deliberately avoided).

**What this needs that does not exist yet.**

| Need | Status |
|---|---|
| "Is a firing active right now?" | Answerable only by a join nobody has written: `JobRun.conversation_id` → `Run.status == "running"`. **`JobRun.status` is only `"fired"` or `"failed"`** (`models.py:1178-1180`) — there is no `"running"`, so a firing in progress is indistinguishable from one that finished. This is the same question the loop panel needs for "is there an active agent right now", so it wants one helper, not two. |
| A per-loop audit trail | `EventLog` (`models.py:907`) exists and `persist_event` already writes loop events, but it is indexed by **project and agent, not loop** — "show me this loop's history" means filtering unindexed JSON. `Loop.updated_by_run_id` records only the most recent writer. |
| Staged edits | No mechanism. New. |

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
4. **Creator identity is now load-bearing.** Until §5 it was provenance — an audit breadcrumb, the
   same `created_by_run_id` a dozen tables carry, that nothing read to make a decision. "Only the
   creator can add tasks" makes it an **authorization check**. The field did not change; the weight
   on it did. Three things follow, none resolved:
   - **The creator is a name at the end of two unenforced hops** — `Loop.created_by_run_id`
     (nullable, no FK) → `Run.agent` (`String(64)`, no FK) → a name. Attribution *is* genuinely
     verified at creation (`jobs.py:31-33`: the run must exist, match the project and the claimed
     agent, and be `running`), but only **once**. Afterwards only the string survives.
   - **Name reuse transfers authority.** Identity here is a name, not a row: archive `arch`, create a
     new agent also called `arch`, and it inherits permission over every loop the old one made.
     Renaming fails the other way — the loop points at a name nobody holds and becomes unextendable
     with nothing explaining why.
   - **The precedent next door fails open.** `scheduler.py:51-56` returns `None` — meaning *proceed* —
     when no agent row matches. A permission check written in that house style would read "creator
     not found" as "allow", which is backwards. Whatever this change does, it must fail closed.

   Note this is **not** a live vulnerability: the Hub is local and single-operator, and the API key is
   the real boundary. It is a field being asked to carry weight it was not built for.
5. **Where the control setting lives** (§5a) — a nullable `Loop` column following
   `Agent.default_permission_mode`'s shape is the obvious candidate, but it is not decided, and
   neither is whether control can be handed over after creation.
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
