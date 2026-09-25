# Design — a task is attended only by a turn that will reach it

## Operator review, 2026-09-24

The Opus adversarial review and the operator's decisions are in
`spec-queue/tracks/reviews/B1-2026-09-24.md` §1 (verdict: approve with fixes). Applied here:

- **Operator decision (F158 input):** a refused **work** head is surfaced as `unstaffed` with the
  refusal's own words, mirroring the review arm, and the firing no longer re-briefs it (D3, D4). The
  refusal F158 keeps (its D2, refuse the turn on conflict) names the prerequisite task, the checkout
  path and the merge command; this change carries those words whole to the loop's stall reason, so
  F158's refusal stalls visibly instead of churning one briefing per firing.
- **HIGH (held / paused / spent budget):** R3's "the re-briefing drives the pass that counts the
  head" was false whenever `_attempt_turn` returns before the trigger (the hold at
  `turn_scheduler.py:388-392`, the token budget at `:394-395`, the closed conversation at `:350`),
  so a held or paused assignee with a refused head was re-briefed on every firing. The operator's
  decision removes the re-briefing for a refused head altogether, which closes this whatever holds
  the agent. Test 1.4c pins it: held, paused-equivalent and budget-spent, three firings, no new entry.
- **MEDIUM:** the head is read through B11's F133 `select_turn(...).controlling`
  (`hub/hub/inbound_queue.py`, built first), not a second copy of the selection rule (D1, task 2.0).
- **LOW:** a transient refusal meeting a crash-counted head reads as refused (residual); the
  agent-wide `agent in running` exception is worded into the `agent-loops` delta.

**Built on one operator decision** besides the requirements that already exist (`agent-loops:1356`,
`agent-flows:821`, `agent-flows:851`): D3, refused input is not attendance, and a refused head is
surfaced rather than re-briefed (2026-09-24, above).

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
  conversation ride with it (`:361-371`). **The head is `select_turn(entries, hop_budget, cap).controlling`**
  (review 2026-09-24, MEDIUM): B11's F133 factors that selection out of `_attempt_turn` into
  `hub/hub/inbound_queue.py` as a pure function, and it is built before this change. `task_attendance`
  groups the project's queued rows by agent, in `sequence` order (the order `queued_entries` returns,
  so the grouping is the scheduler's), and calls it once per agent with the budget and cap read from
  `project_limits`. There is then one statement of "which entry an agent's next turn starts with",
  and a later change to it (a kind rule, a cap) reaches both readers. `run_task_binding` already
  imports from `inbound_queue` (`run_task_binding.py:32`), so no import cycle is added. Nothing behind a refused head is delivered until the head
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
| Resume arm (`:1848`) | `agent in running or attendance.attends(task.id, agent)` → in flight (F370, F368). Else, where `attendance.refusal(task.id, agent)` is set → in flight **and** `unstaffed` with D4's refused-work sentence, added to the set that keeps a surfaced row from making the firing read busy (today `wedged_reviews`, renamed `surfaced_rows`, `scheduler.py:1678`, `:2039`), and `continue`: no briefing (operator, 2026-09-24). Else brief, as today. |
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
- **Resume arm (operator, 2026-09-24): surfaced, as the review arm is, and not re-briefed.** A
  refused work pair is not in flight, and it is not briefed either. The firing records it in
  `in_flight` (so the board still reads the assignee as holding it, F63, as the review arm does) and
  in `unstaffed` with D4's refused-work sentence, which carries the refusal's words; F64's rule
  promotes it to the stall reason when nothing else is claimed.
  - *Why not re-brief, as R1–R3 had it.* R3 argued the re-briefing is what drives a pass that counts
    the refused head toward `DELIVERY_ATTEMPT_LIMIT` (`turn_scheduler.py:594-658`). The review showed
    that argument fails wherever `_attempt_turn` returns before the trigger: a provider hold
    (`:388-392`, which B3's paused agents join through `agents_held`), a spent token budget
    (`:394-395`), a closed conversation (`:350`). Those count nothing, so a held assignee with a
    refused head was re-briefed on every firing for the whole hold — F370's pile-up back. And where
    the pass does reach the trigger and the refusal is about the task itself (F158's D2: the
    checkout's catch-up merge conflicts), each briefing meets the same refusal, so the loop queued
    one briefing per firing and abandoned one per three passes, forever, with only a
    `queue_entry_abandoned` warning (`:654-659`) — the churn the operator ruled out.
  - *What retries the head now.* Every pass for that agent still tries it: the run-end re-drain,
    any new input the agent is sent (`api/v1/messages.py:318` and the other `schedule_agent`
    callers). So `agent-conversation-workspace` *Repeated delivery failure does not wedge
    an agent* still holds: every attempt counts, and the head is given up at the limit. What stops is
    the firing manufacturing attempts that the operator is the only one able to make succeed.
  - *The operator's exits.* The sentence names them: fix what the refusal names and withdraw that
    input (`DELETE /entries/{id}`, `api/v1/inbound_queue.py:258`) so the next firing briefs the
    agent once more; or reject the task. Withdrawing is what makes the fix take effect:
    a refused head's `waiting_reason` is cleared only by a delivery (`inbound_queue.py:191`), so
    without it the next firing would surface the stale refusal again.
  - *A head given up at the limit* leaves no pair; the next firing briefs once, that briefing meets
    the refusal in the firing's own pass (`scheduler.py:3471`), and the firing after surfaces it. At
    most one briefing per abandoned head, bounded by passes something else drives, never by firings.

*Rejected, the review's narrower fix:* keep the re-briefing and treat refused as not-attending only
where a pass can reach the head (`agent in running or attends or (held and has_turn)` plus a budget
guard). It stops the held pile-up but keeps F158's churn, and it needs a guard per early return of
`_attempt_turn`, a list that grows (B3's pause joined it this week).

## D4 — Sentences

- `_wedged_review_reason` (`scheduler.py:2195-2225`) says *"no turn is running on that task and none
  is queued"* (`:2216`). After D2 that can be false: a third agent's message, or suspended or
  refused input, may be queued. It becomes *"no turn of theirs is running on that task and none
  queued for them will start on its own"*. (R2: R1's *"nothing is waiting to be delivered to
  them"* was false in F371's own hop-99 leg, where the reviewer's suspended entry is exactly that.) The title-shortening fit (`:2220-2224`) is unchanged.
- A new `_refused_review_reason(task, reviewer, refusal)`: *"{reviewer} is named on {task.id}
  ({title!r}) as its reviewer, and delivering the review to them was refused: {refusal} Fix what it
  names, review it yourself, or send it back with revision_needed."* Fitted to
  `JOB_RUN_ERROR_SUMMARY_CHARS` (500, `models.py:1367`) by shortening the title first and then the
  refusal, so the remedy is never cut (the rule `_wedged_review_reason`'s docstring states for the
  title, `:2207-2211`). Title before refusal (changed 2026-09-24): the refusal is the only part
  that says what to fix, and F158's names a prerequisite, a path and a command.
- A new `_refused_work_reason(task, agent, refusal, refused_here)` (operator, 2026-09-24): *"{agent}
  holds {task.id} ({title!r}), and delivering its turn to them was refused: {refusal} No firing will
  retry it. Fix what it names, then withdraw that input from {agent}'s queue so the next
  firing briefs them again, or reject the task."* Where `refused_here` is false, the middle clause
  reads *"and its briefing is queued behind input for them whose delivery was refused: {refusal}"*.
  Same fit, title first. It states no cause of its own: the refusal is the trigger's
  (`agent_trigger.py:1019-1023` for a checkout that could not be prepared), and F158's revision
  writes that sentence to name the prerequisite task, the checkout path and the merge command; this
  function carries it whole. Test 1.4d gives it a 300-character refusal and asserts the refusal
  survives uncut beside a 200-character title. It does not say "ask them again": the same dispatch meets the same refusal.
  Where `refused_here` is false (the refused head is another entry of theirs, R3), the middle clause
  reads *"and the review is queued behind input for them whose delivery was refused: {refusal}"*,
  and the remedy *"Fix what it names or withdraw that input, review it yourself, or send it back
  with revision_needed."*

## D5 — Availability is unchanged

`_roster_availability` asks *will something move this agent onto this task*, and a refused entry is
still input a pass will try. `agent-flows:910`'s rule ("a turn running or queued within the
project's hop budget") is kept word for word. The resume arm and availability therefore differ on
a refused entry on purpose: the assignee is not free (its input is still queued for that task), and
the task is not in flight (nobody is working it), so the firing surfaces it with the refusal
(D3, operator 2026-09-24). Both are true.

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
- **A transient refusal can make a crash-counted head read as refused** (review 2026-09-24, LOW). A
  head whose `delivery_attempts` a crashed run raised (`return_run_entries`) and which then meets a
  transient refusal (D8's one-writer-per-checkout, `agent_trigger.py:994-1000`, `transient=True`)
  has both columns set, so it reads as refused and its task is surfaced with the D8 sentence, which
  names the other agent's running turn. It clears on the next delivery; the sentence is true while
  it stands. Not fixed: telling the two apart needs a column recording whether the last refusal
  counted, and no finding asks for it.

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
- **B11's F133** (no-spec, `select_turn` in `hub/hub/inbound_queue.py`) is built **first**: D1 reads
  the head through it. Task 2.0 stops the build if it is absent.
- **B1's `a-task-checkout-catches-up-with-its-approved-prerequisites`** (F158, REVISING) writes the
  refusal this change surfaces for a work head; its revision names the prerequisite task, the
  checkout path and the merge command. Neither edits the other's files. Order does not matter for
  correctness: before F158 is built the surfaced sentence carries today's
  *"Could not prepare the checkout for task …"* (`agent_trigger.py:1019-1023`). F158's sentence
  should stay under about 300 characters so that D4's fit never has to cut it (the frame around it
  is about 200 with a short title).

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
- **Operator review, 2026-09-24** (`spec-queue/tracks/reviews/B1-2026-09-24.md` §1): applied the
  operator's F158 input (a refused work head is surfaced as `unstaffed` with its refusal, not
  re-briefed; D2, D3, D4 `_refused_work_reason`), which also closes the review's HIGH (a held,
  paused or budget-spent assignee re-briefed on every firing; test 1.4c); the head read through
  F133's `select_turn(...).controlling` (D1, task 2.0); the transient-refusal residual; the running
  exception worded into the `agent-loops` delta. Re-checked at HEAD `61d553e`: `scheduler.py:1678`,
  `:1699`, `:1792`, `:1796`, `:1848`, `:2039`, `:2195`, `:3471`; `turn_scheduler.py:333-395`,
  `:475`, `:605`, `:654-659`; `agent_trigger.py:989-1023`; `api/v1/inbound_queue.py:258-272`
  (withdraw schedules nothing, so the next firing's briefing is what delivers after a fix).
