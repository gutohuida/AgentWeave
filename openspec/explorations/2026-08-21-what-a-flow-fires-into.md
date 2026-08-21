# Exploration — What a flow fires into (2026-08-21)

**Status:** OPEN. Three findings verified by reading the live code paths; none fixed.
**Follows:** `2026-08-21-the-loop-becomes-a-flow.md` §9, whose open questions this works through.
**Why now:** `loop-becomes-a-flow` is proposed at 0/60 and unreviewed. Its central move — the flow
**selects the agent at firing time** from a ladder, rather than carrying one chosen at creation —
is the part that changes what firing can encounter. Everything below is about that change and
nothing else.

---

## 0. First, §9 is partly stale

Two of §9's six bullets were settled later in the same session and never written back. Anyone
reading §9 today would think they are still open:

| §9 bullet | Actually |
|---|---|
| *"Parallelism (§6). The scope question."* | **DECIDED.** A flow may start every task whose dependencies are met. Width comes from the graph, not a setting. |
| *"How does a flow know who should review?"* | **DECIDED.** The ladder: declared reviewer, else anyone not running and holding no active task, else surface. |

Both are recorded as key decisions 10 and 9 of handoff 0069. The remaining four bullets are real,
and three of them are what this document is about.

The exploration should be amended rather than left disagreeing with itself — but that edit is not
made here, because §9 is a section of a document a run may be reading. Noted for whoever touches it
next.

---

## 1. The change in one sentence

A loop's agent is chosen **once, by the operator, at creation**, and `AIJob.agent` is `NOT NULL`.
A flow's agent is chosen **every firing, by the ladder, from the roster**.

So a loop can only ever fire the agent an operator deliberately picked. A flow can fire **any roster
row the ladder's second rung reaches** — "anyone not running and holding no active task" — including
one nobody ever configured to run. That is not a flaw in the ladder; it is the ladder working. It
does mean the firing path now has to survive inputs it has never actually been given.

The three findings below are what it does with them today.

---

## 2. Finding A — a firing that cannot launch leaves the loop card reading "firing", indefinitely

**Verified by reading, not run.**

The fire path does not call `trigger_agent_directly`. It sets `run.status = "in_progress"`
(`hub/hub/scheduler.py:997`), commits, and then calls `schedule_agent`
(`hub/hub/scheduler.py:1015`).

`schedule_agent` *does* reach the trigger, and the trigger *does* refuse an agent with no runner
bound — a 409 raised at `hub/hub/api/v1/agent_trigger.py:299`. `turn_scheduler.py:93` catches it and
returns `ScheduleResult(waiting_reason=exc.detail)`.

**`scheduler.py:1015` discards that return value.** Nothing reads it. So:

- the `JobRun` stays `in_progress`, because only `finalize_job_run_for_conversation` moves it and
  that needs a real `Run` to end — and no `Run` was ever created;
- no event is persisted. The `TriggerAgentError` handler at `turn_scheduler.py:94` persists
  `queue_agent_paused` **only** for `workspace_unavailable`, and this is not that;
- `_batch_loop_summaries` builds `firing_active_jobs` from exactly
  `JobRun.status == "in_progress"` (`hub/hub/api/v1/jobs.py:228-234`).

That last one is the sting. The loop card does not go quiet — it reads **firing**, and keeps reading
firing. The operator is not told nothing; they are told the wrong thing, and told it continuously.

**There is a reaper, and it is not enough.** `reconcile_stale_job_runs`
(`hub/hub/run_reconciliation.py:102`) flips exactly these rows to `failed`, and its docstring names
this exact case — *"an agent with no runner bound is the live example this was diagnosed against on
the trial Hub: `job-0b490274`, agent `claude-1`, `runner_id` NULL"*. So the situation is known and
was met once already.

But the reaper runs **on Hub start**. Nothing calls it on a timer. For an unattended flow — the
entire point of the feature — the Hub does not restart, so "reconciled at startup" means "wrong
until someone notices and restarts", which is the state the reaper was written to end.

**And no guard stops the next firing.** The already-running guard is group 1 of
`loop-notices-and-reacts`, unbuilt. So the cron keeps firing, each firing queues another entry for
the same unlaunchable agent, and each strands the same way — which is the same shape as the measured
*"5 firings during 1 turn → 5 queued briefings for the same task"*. **At the 5-minute driver interval
this accumulates twelve times an hour.**

### Why the flow makes this worse rather than merely inheriting it

Today this requires an operator to bind a loop to an agent they never gave a runner — a mistake, and
a visible one, made once at creation.

Under the ladder, rung two selects **from the roster by availability**. An agent with no runner bound
is *maximally available*: it is never running and never holds a task, because nothing can start it.
So the unbound agent is not merely reachable — **it is disproportionately likely to be chosen**, and
it stays chosen every tick, because the condition that made it eligible is the same condition that
makes it fail.

That is the finding. The ladder's cheapest candidate is the one that cannot run.

---

## 3. Finding B — an unbound runner is reported as a missing CLI named after the agent

**Verified by reading.**

`inbound_queue.py` recomputes a `waiting_reason` at read time, and its comment (lines 179-182) shows
the discard in Finding A was already known: *"a turn can be refused inside the trigger, where the
reason was raised and then discarded, leaving the operator with '1 waiting' and no explanation to
reason from."*

Just above it, lines 148-154 record a fix for a masking bug — probing without the bound `Runner`
record fell through to `RUNNER_CLI["native"] is None`, whose fallback is **the agent's own name**, so
`codex-spec` was reported as `Runner CLI 'codex-spec' was not found in PATH`.

**That fix covers the bound case only.** Trace the unbound one:

- `runner_row` is `None` when `agent_row.runner_id` is falsy (`inbound_queue.py:166-170`), so the
  `if runner_row is not None` at line 171 does not fire and `config["runner"]` is never set;
- `get_agent_config` (`hub/hub/launchability.py:294-319`) merges only `session.json`'s
  `agents.<name>` entry and `Agent.config`. **It never reads `Agent.runner_id`.** For a Hub-created
  agent with no session sync, it returns `{}`;
- `probe_agent` then takes `runner = config.get("runner", "native")`
  (`hub/hub/launchability.py:49`) and `cli = RUNNER_CLI.get(runner) or name` (line 62).

So the reason reads **`Runner CLI 'claude-1' was not found in PATH.`** — the same masked message the
comment above says was fixed, in the branch the fix did not cover. The operator is sent to look for a
binary named after their agent. The actual answer, *"this agent has no runner bound"*, is a NULL
column away and is the message `agent_trigger.py:302` already writes for the same condition.

**Under the flow this message is not merely unhelpful — it names the wrong subject.** The operator did
not choose this agent; the ladder did. So they are given a CLI-not-found error about an agent they
never selected, for a firing they did not configure, on a loop card that says it is firing.

Findings A and B compose into: *the flow appears to be working, and when the operator investigates,
the explanation is false.*

---

## 4. Finding C — `agent-loops` §626 collapses exactly what a flow needs shown

`openspec/specs/agent-loops/spec.md:626` — **"Consecutive firings of one loop occupy one row"**:

> a run of consecutive conversations created by the same loop SHALL be presentable as a single row,
> expandable to the firings it stands for. A loop left running fills the list with threads the
> operator never began; naming each one is not sufficient once there are enough of them.

The stated rationale is **repetition** — many near-identical threads, none individually interesting.
That rationale is sound for a loop, where consecutive firings are one agent doing the same thing
again.

A flow's consecutive firings are **different agents doing different tasks**: worker does task 3,
reviewer reviews task 3, worker does task 4. Collapsing those into *"Flow X — 3 firings"* discards
precisely the sequence the operator opened the list to see. The requirement keys on **same loop**,
but its justification is **same work** — and under a flow those two stop coinciding.

The three existing scenarios all survive, incidentally: none of them asserts that firings from one
loop *must* collapse, only what collapsing must preserve when it happens.

**CORRECTION (same session, on reading the change rather than only the current spec): this is already
fixed in the proposal, and Finding C is therefore not a finding against `loop-becomes-a-flow`.**

`openspec/changes/loop-becomes-a-flow/specs/agent-loops/spec.md:27-57` already modifies this
requirement to read *"created by the same loop **and belonging to the same agent**"*, adds *"A change
of agent SHALL break the run. Consecutive firings by different agents are different events — under a
flow, an implementer followed by a reviewer is the ordinary case, and collapsing them together would
hide the handover that is the most informative thing on the list"*, and carries a scenario for it.

That is the same resolution this section arrived at independently, which is mild evidence the change
is thinking clearly — but it was already written, and this document originally claimed it was not.
The error was reading `openspec/specs/agent-loops/spec.md` and §9 without checking the delta.

**What survives:** the defect is real in the *current* corpus, so it is live until this change lands.
Nothing more.

---

## 5. §9's remaining question — "busy" versus "no eligible agent at all"

§9 asks whether these are worth distinguishing, and says only the second is worth surfacing. The code
already draws the line, in `schedule_agent`'s waiting reasons: `"agent is already running"` is
transient and self-clearing; `"hop budget exhausted"`, `"token budget exhausted"` and the runner
refusal are not.

So the distinction needs no new concept — it needs the ladder to **not treat unlaunchable as
available**, which is Finding A's second half. An agent that cannot be started should never reach
rung two. Once it cannot, "nobody is eligible" becomes a real state that can be surfaced honestly,
instead of being silently filled by the worst candidate.

---

## 6. What this suggests for `loop-becomes-a-flow`

Not tasks — the change is unreviewed and the operator has not read it. Stated so the review can
accept or reject them:

1. **The ladder's second rung must filter on launchable, not merely idle.** `probe_agent` already
   answers this and is read-only. Without it, rung two prefers the agent that cannot run.
2. **`schedule_agent`'s `ScheduleResult` must stop being discarded at `scheduler.py:1015`.** A firing
   that queued but did not start is not `in_progress`, and the waiting reason is already computed —
   it is thrown away one line from where it would be recorded.
3. **`reconcile_stale_job_runs` needs a trigger other than Hub start** if flows are to run
   unattended, or the firing path must stop creating rows only that function can clean up. The second
   is better: the reaper is for crashes, and this is not a crash.
4. **`get_agent_config` should carry `Agent.runner_id`**, so the unbound case stops falling through
   to the agent-name fallback. This one is a small fix with value independent of the flow.
5. ~~**§626 should key collapse on the agent, not the loop.**~~ **Already done** in the change's
   `agent-loops` delta — see the correction in §4. Listed only so a reader of this list does not go
   looking for it.

Items 2, 3 and 4 are **loop bugs today**, not flow bugs. They are only listed here because the flow
is what makes them reachable without an operator mistake.

---

## 7. Still open

- **Is item 3 the flow's problem at all?** A periodic reaper is a scheduler-wide change and would
  touch the loop suite. Deferring it means an unattended flow can misreport for hours; taking it
  means `loop-becomes-a-flow` grows a section that is not about flows.
- **What does rung two do when every eligible agent is unlaunchable?** "Surface" is rung three, but
  rung three was written for *"nobody is free"*, which reads to an operator as *wait*. *"Three agents
  are free and none can start"* is a different sentence and wants a different one.
- **None of this is measured.** Every finding above is read from source. The trial Hub on 8010 was
  not driven, no firing was made to fail, and the loop card was not observed reading "firing" against
  a stranded row. Finding A's docstring evidence (`job-0b490274`) is someone else's earlier
  observation, not this session's.
