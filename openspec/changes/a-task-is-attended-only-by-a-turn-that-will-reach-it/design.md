# Design — a task is attended only by a turn that will reach it

**Built on no operator decision.** Every choice below follows from requirements that already exist
(`agent-loops:1356`, `agent-flows:821`, `agent-flows:851`). The one judgement call is D3 (refused
input is not attendance). If the operator rejects it, D3's alternative is stated there, and only
the scenarios naming a refused delivery leave the delta.

`a-flow-stages-its-review-in-the-dispatch` (S13, F327) is designed on top of D1 and must be built
after this change.

## Context, re-derived on HEAD `404c7d5`

| Reader | Line | Question it means | What it asks today |
|---|---|---|---|
| `_roster_availability` | `scheduler.py:1162`, `:1179` | will a turn move this agent onto this task | pairs, queued, within the hop budget (`task_agent_pairs_with_a_turn_queued`, `run_task_binding.py:313-355`) — correct |
| `decide_firing` F70 guard | `scheduler.py:1792` | is anyone on this task right now | `task.id in on_it`: any agent, any depth |
| `decide_firing` F154 surfacing | `scheduler.py:1796` | is the named reviewer on it | `task.id not in on_it`: any agent, any depth (F371) |
| `decide_firing` resume arm | `scheduler.py:1848` | is the assignee's turn on this task already coming | `agent in running or (agent in held_agents and on_it.get(task.id) == agent)`: first-row map (F370), and only for a held agent (F368) |

`on_it` is `tasks_with_a_turn_pending_or_running` (`run_task_binding.py:268-310`): a map built with
`setdefault` over an unordered select (`:299-306`), then overlaid with the running map (`:309`).

Measured on this HEAD (throwaway test, deleted): F370's helper answer was
`{'task-width-f370': 'aaa-peer'}` with the assignee's own `job` entry queued, and three firings left
four `job` entries for the held assignee. F371 answered `in_flight` with `stall_reason None` for
both the third-agent leg and the hop-99 leg. F368 left four `job` entries after three firings with
`schedule_agent` answering `token budget exhausted`.

## D1 — One helper, keyed by pair

```python
ATTENDING_RUNNING = "running"
ATTENDING_QUEUED = "queued"
ATTENDING_REFUSED = "refused"

@dataclass(frozen=True)
class Attending:
    how: str                 # one of the three above
    review: bool             # the input names the task as the one it reviews (review_task_id)
    refusal: Optional[str]   # the agent's refused head's words, only when how == ATTENDING_REFUSED
    refused_here: bool       # R3: that refused head is one of this pair's own entries

@dataclass(frozen=True)
class TaskAttendance:
    pairs: Mapping[Tuple[str, str], Attending]      # (task_id, agent) -> strongest statement

    def attends(self, task_id, agent) -> bool       # running or queued
    def attended(self, task_id) -> bool             # attends(task_id, a) for some a
    def has_turn(self, task_id, agent) -> bool      # input queued within budget, refused or
                                                    # not, IGNORING running pairs: D5's question
    def refusal(self, task_id, agent) -> Optional[str]

async def task_attendance(session, project_id) -> TaskAttendance
```

- **Running pairs** from `Run.status == "running"` and `Run.task_id` (the query
  `tasks_held_by_a_running_turn` makes, `run_task_binding.py:377-386`), as pairs rather than a map.
- **Queued pairs** from `InboundQueueEntry.state == "queued"`, `agent IS NOT NULL`,
  `hop_depth <= hop_budget` (budget from `inbound_queue.project_limits`, the reader
  `turn_scheduler._attempt_turn` uses at `:337`, so the two cannot disagree), each entry contributing
  a pair for `task_id` and for `review_task_id` (both columns, as today, `:302-306`).
- **`review` is an OR over the pair's contributing entries** (R2): a pair with both a work entry and
  a review entry for one task is a review turn. S13 reads this flag to close the pool, and letting
  the strongest entry's flag win would drop a review turn behind a work entry.
- **Strongest wins per pair**: running > queued > refused, where queued/refused is decided by the
  agent's head (R3, below), not by the pair's own entries.
- **But `has_turn` is kept apart from that collapse** (R2). It answers from the queued rows alone
  (a separate `queued_pairs` set inside `TaskAttendance`, refused or not), never from a running
  pair. Folding a running pair into it would change availability: a running agent's task on a
  non-live loop with nothing queued would become a *reachable* holding, and rung 3 then names that
  agent by the `booked` clause instead of `running` (`_rung_3_clause_kind`, `scheduler.py:1305-1316`,
  checks `booked` before `running`). D5 promises byte-identical availability, so the running half
  must not reach it.
- **Refused** (D3): the entry's `delivery_attempts > 0` **and** `waiting_reason IS NOT NULL`. Both,
  because each alone means something else: `return_run_entries` raises `delivery_attempts` for a
  run that crashed and leaves `waiting_reason` cleared (`inbound_queue.py:225-297`; the delivery
  that preceded it cleared it, `:191`, `:204`), and that input is redelivered by the run-end
  re-drain; a transient refusal writes `waiting_reason` (`turn_scheduler.py:474-475`) and counts
  nothing, and it clears on its own (`:660-667`).
- **Read at the agent's head, not per entry** (R3). `_attempt_turn` tries one entry per agent: the
  first queued entry within the budget by `sequence` (`turn_scheduler.py:333`, `:340`;
  `queued_entries` orders by `sequence`, `inbound_queue.py:93`), and only entries in that entry's
  conversation ride with it (`:361-371`). Nothing behind a refused head is delivered until the head
  is delivered or given up. So where an agent's head is refused, **every** queued pair of that agent
  is refused, carrying the head's words; where the head is not refused, every queued pair is queued,
  whatever an older rider's row says. R2's per-entry rule with "one un-refused entry makes the pair
  queued" was wrong exactly where D3 matters: the resume arm's one re-briefing is a **new
  conversation** whenever the acting agent is not the job's own resumable one (`scheduler.py:3345-3384`),
  so it does not ride with the refused head, is not refused itself, and would make the pair
  `queued` on the next firing — in flight, no further briefing, no further pass, the head stuck at
  its count and the briefing behind it forever. F368's shape, silent. `Attending` gains
  `refused_here: bool` (the refused head is one of this pair's own entries), so a sentence can say
  "delivering it was refused" only when it was, and otherwise "it waits behind input for {agent}
  whose delivery was refused". `has_turn` is untouched by this (queued rows, refused or not).

`tasks_held_by_a_running_turn` stays. Its caller in `agent_trigger.py:990` asks *may this turn
start*, and its docstring (`:363-371`) warns against a third meaning on one query.
`tasks_with_a_turn_pending_or_running` and `task_agent_pairs_with_a_turn_queued` are deleted; each
had one production caller (`scheduler.py:1699`, `:1162`).

*Rejected:* a parameter on the old map helper (F370's own sketch, "one parameter or a sibling
function"). The map is the defect; any parameter keeps a shape that cannot say "two agents".
*Rejected:* counting suspended input for the held arm (F370's sketch wanted the pairs "without the
budget bound", because a suspended briefing is still a copy). A flow's own briefing is always queued
at hop 0 (`scheduler.py:3409`, `:3741`), and so is a divergence response
(`run_divergence.py:257-262`). So the only suspended input naming a task is a peer message, which is
not a briefing. Excluding it costs at most one briefing, at hop 0, which then counts. It never
repeats.

## D2 — Which reader asks which question

| Reader | After |
|---|---|
| F70/F167 guard (`:1792`, *"Never while a turn is on the task"*; made reachable by Round 5's evidence term, `6117d15`) | `attendance.attended(task.id)` — anyone running or queued, no suspended, no refused. A refused turn is not "a turn on the task" the recovery must wait for. Records `wedge_deferred = True` when it clears `wedged_review`. |
| F154 surfacing (`:1796`) | `not wedge_deferred and not attendance.attends(task.id, task.assignee)` (F371). The reason is D4's refused sentence where `attendance.refusal(task.id, task.assignee)` is set, else `_wedged_review_reason`. |

**Why `wedge_deferred` (R3).** Today both readers ask the same task-level question, so a wedge the
guard defers is never surfaced: `task.id in on_it` holds, so `task.id not in on_it` does not. Once
the surfacing asks the pair question and the guard keeps the task question, an **author** holder
(F70/F142/F167's case) with a third agent's turn on the task would be deferred by the guard and then
surfaced by F154 as *"{author} is named on … as its reviewer"* — the false sentence F167's comment
says strands the task, and a second answer to a row the guard just said to wait on. A deferred
wedge stays `in_flight` silently, as today, and the next firing decides.
| Resume arm (`:1848`) | `agent in running or attendance.attends(task.id, agent)` (F370, F368). |
| Availability (`:1162`, `:1179`) | `attendance.has_turn(task_id, assignee)` — D5. |

**The held qualifier goes from the resume arm.** `agent in held_agents and` was there because the
arm's only known reason for a queued-but-unstarted turn was the hold (D6 of
`a-spent-allowance-holds-the-queue`). F368 names the others. The hold still matters where it is
read elsewhere: the default-agent branch (`:1869-1870`) and the free list (`_roster_availability`,
`:1148`). `held_agents` stays in `decide_firing` for the default-agent branch.

**A running assignee still short-circuits** (`agent in running`), agent-wide, as today: a run
carrying no `task_id` is still work being done (`decide_firing`'s own comment at `:2051-2054`).

## D3 — Refused input is not attendance

A turn whose last delivery was refused is not being taken. The next attempt is made only when a
pass reaches that agent, and nothing schedules one on its own (`turn_scheduler.py:665`,
`agent_trigger.py:2643`).

- **Review arm:** counted as attended, a flow-staffed review whose dispatch was refused read
  `in_flight` until the entry was given up — F327's middle row. With D3 it is surfaced on the next
  firing with the refusal's words. (S13 then removes the staging that left the task `under_review`
  at all; D3 is what makes S13's pool rule safe, see that change.)
- **Resume arm:** a refused work entry is **not** in flight, so the firing briefs the assignee as it
  does today. That is deliberate. Today's re-briefing is the only thing that drives a pass for that
  agent, which counts the refused head and, at `DELIVERY_ATTEMPT_LIMIT`, gives up on it
  (`turn_scheduler.py:594-630`). Treating it as in flight would leave the head counted once and then
  never tried again, with the flow reporting in flight: F368's shape, silent instead of noisy.
  (R3) That argument holds only with D1's head rule: a re-briefing that does not ride with the
  refused head is still behind it, so the pair stays refused and the next firing drives the next
  pass, until the head is given up at the limit and the pass moves on (F320). Cost kept from today:
  where the refusal is about the task itself, each briefing behind the head meets it in turn, so
  entries still accumulate faster than they are given up (one per firing, one given up per three
  passes). That is today's behaviour for this row, not new; the alternative is the operator's (count
  refused input as attendance, below, or surface it as the review arm does).

*Alternative, if the operator rejects D3:* count refused input as attendance. The review arm then
keeps F327's `in_flight` window until the entry is given up, and the resume arm strands a refused
head as described. The scenarios naming a refused delivery leave both deltas.

## D4 — Sentences

- `_wedged_review_reason` (`scheduler.py:2195-2225`) says *"no turn is running on that task and none
  is queued"* (`:2216`). After D2 that can be false: a third agent's message, or suspended or
  refused input, may be queued. It becomes *"no turn of theirs is running on that task and none
  queued for them will start on its own"*. (R2: R1's *"nothing is waiting to be delivered to
  them"* was false in F371's own hop-99 leg, where the reviewer's suspended entry is exactly that.) The title-shortening fit (`:2220-2224`) is unchanged.
- A new `_refused_review_reason(task, reviewer, refusal)`: *"{reviewer} is named on {task.id}
  ({title!r}) as its reviewer, and delivering the review to them was refused: {refusal} Fix what it
  names, review it yourself, or send it back with revision_needed."* Fitted to
  `JOB_RUN_ERROR_SUMMARY_CHARS` (500, `models.py:1367`) by shortening the refusal first and then
  the title, so the remedy is never cut (the rule `_wedged_review_reason`'s docstring states for the
  title, `:2207-2211`). It does not say "ask them again": the same dispatch meets the same refusal.
  Where `refused_here` is false (the refused head is another entry of theirs, R3), the middle clause
  reads *"and the review is queued behind input for them whose delivery was refused: {refusal}"*,
  and the remedy *"Fix what it names or withdraw that input, review it yourself, or send it back
  with revision_needed."*

## D5 — Availability is unchanged

`_roster_availability` asks *will something move this agent onto this task*, and a refused entry is
still input a pass will try. `agent-flows:910`'s rule ("a turn running or queued within the
project's hop budget") is kept word for word. The resume arm and availability therefore differ on
a refused entry on purpose: the assignee is not free (its input is still queued for that task), and
the task is not in flight (nobody is working it), so the firing briefs it. Both are true.

## D6 — Tests that move, deliberately

- `test_a_review_nobody_is_doing.py:448-501` — five predicate tests call
  `tasks_with_a_turn_pending_or_running` directly. Rewritten against `task_attendance`: running
  turn, either column, withdrawn/delivered ignored, empty. The same assertions, expressed as pairs.
- `test_a_task_nothing_will_move_holds_nobody.py:318-322` asserts the old helper's masking as a
  premise. The premise goes; the test's real assertion (`DEV not in await _free()`) stays.

## What each route returns when this raises

`decide_firing` is read by the firing (`_do_fire_job`), by the board (`api/v1/jobs.py:380`)
and by `run_job`'s in-flight answer (`jobs.py:1335`). `task_attendance` is two reads and a settings read; a
failure is a database error, which each caller already meets from `tasks_with_a_turn_pending_or_running`
at the same point. Nothing here adds a new raise, and no route's status changes.

## Residuals, not fixed here

- **Input in a closed conversation counts as queued.** `_attempt_turn` answers
  *"conversation is unavailable"* for a controlling entry whose conversation is not open
  (`turn_scheduler.py:344-350`), counts nothing and returns — so the agent's whole queue waits.
  Under D2 such an entry makes its task in flight. Before, the firing re-briefed into a new
  conversation that queued behind the same dead head. Neither moves the task. Candidate finding for
  the orchestrator; not filed here.
- **In flight does not say why the turn has not started.** A task in flight on a queued turn that
  the token budget stops reads the same as one about to start. The queue status route answers why.

## Collisions with other changes (R2)

- **`pressing-run-names-the-reason-that-held`** (unarchived) and `run_job`'s in-flight answer.
  `run_job` re-asks `decide_firing` (`jobs.py:1318-1337`) and, for `DECISION_IN_FLIGHT`, answers
  *"Every task on this loop's queue is already being worked … nothing is wrong"* (`jobs.py:1494`),
  qualified only for **held** agents (`_held_in_flight_reasons`, `:1339-1357`). D2 makes an idle,
  unheld assignee whose briefing is queued but blocked (token budget, conversation unavailable) in
  flight, so a Run press on F368's staging would now read *"already being worked"* where today it
  re-briefs. The pile-up stops; the press's sentence is then false for that row. No textual overlap
  with that change (it edits `_loop_flow_busy_reason` and `run_job`'s `not success` branch). Build
  that change first; this one adds task 1.14 pinning the press's answer on F368's staging and
  recording what it says. Whether the press should name the queue's reason is a candidate finding
  (R2), not fixed here.
- **B3 `an-agent-can-be-paused-and-keeps-its-input`** puts paused agents into `agents_held`. D2
  removes `agent in held_agents and` from the resume arm only; `held_agents` stays read by the
  default-agent branch and by `_roster_availability`'s free list, which is what the pause relies on.
  A paused assignee whose briefing is queued within the budget reads in flight and is not re-briefed,
  as that change wants, without a pause branch here. No textual overlap.
- **B1's `a-flow-stages-its-review-in-the-dispatch`** reads `Attending.review`; see D1's OR rule.

## Round log

- **R1, 2026-09-24** (bundle B1): wrote this change. Re-measured F370, F371 (both legs) and F368 at
  `404c7d5`.
- **R2, 2026-09-24** (bundle B1): re-derived against the code. Two corrections: `has_turn` excludes
  running pairs (D1, else rung 3's `booked`/`running` clause precedence moves and D5 is not
  byte-identical); D4's new sentence no longer claims nothing is waiting for the reviewer (false in
  the hop-99 leg). Noted under D3: a non-transient **agent-wide** refusal (no runner bound, CLI
  missing) writes `waiting_reason` but never counts (`turn_scheduler.py:506-508`), so such input
  stays `queued` — attended — by D3's criterion. Deliberate: it is F96's wait-for-the-repair input,
  and the resume arm should not pile briefings on it; for a hand-staffed reviewer whose runner was
  unbound, the review reads in flight until the repair. Kept as a residual, not a D3 change.
- **R3, 2026-09-24** (bundle B1): re-derived against the code, including Round 5's F167 gate
  (`6117d15`). Two corrections. (1) Refusal is read at the agent's **head** (D1): R2's per-entry
  rule let the resume arm's one re-briefing, queued in a new conversation behind a refused head,
  mark the pair `queued`, so the flow read in flight with nothing ever retried — the silent F368
  D3 exists to prevent. (2) `wedge_deferred` (D2): once F154 asks the pair question and the F70/F167
  guard keeps the task question, a deferred author wedge would be surfaced naming the author as
  reviewer. Held on re-reading: `on_it`'s three readers and no fourth (`grep on_it hub/hub`); the one
  writer of `waiting_reason` (`turn_scheduler.py:475`) and its one clearer (`inbound_queue.py:191`);
  `has_turn` from queued rows only; `decide_firing`'s callers (`jobs.py:380`, `:1335`, the firing).
