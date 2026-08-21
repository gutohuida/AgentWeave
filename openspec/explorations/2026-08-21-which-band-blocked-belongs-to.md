# Exploration — Which band `blocked` belongs to (2026-08-21)

**Status:** ANSWERED and **FIXED** (§5 item 1), reproduced by execution first. §4a is **not** fixed —
see §5's closing paragraph and §7.
**Answers:** `loop-notices-and-reacts` task 3.4 — *"Decide which band `blocked` belongs to and record
the reasoning where the classification lives. It is claimable by the loop yet means 'waiting on a
person', and today's four sets disagree about it — this is the one classification the existing code
does not answer."*

**The answer: `blocked` does not belong in the claimable band.** It belongs with `completed` and
`under_review`, in the band that stalls the firing. The reasoning below is what task 3.4 asks to be
recorded, and the defect in §4 is why this is not a tidying question.

---

## 1. What `blocked` actually means here

Narrower than the word suggests, and the narrowness is the whole answer.

- **It is not agent-assertable.** `mcp_server.py:36-41` withholds it from `TaskStatus` deliberately:
  *"a run does not declare itself to be waiting on a person, the runtime observes that it is… An
  agent that could assert `blocked` could claim to be waiting on someone it never asked."*
- **It is reachable only from `in_progress`** (`task_transitions.py:120`) — *"a task nobody has
  started is not blocked, it is pending."*
- **Exactly one thing enters it:** `park_task_for_question`
  (`hub/hub/run_task_binding.py:375-408`), when a run ends with an open `Question`. It writes
  `blocked_reason` from the question and stamps `question.blocked_task_id`.
- **Exactly one thing leaves it on its own:** `release_block_for_question`
  (`run_task_binding.py:422-454`), when that question is answered *or declined*, moving the task to
  `in_progress`.
- **A `blocked_reason` is mandatory** (`hub/hub/schemas/tasks.py:152`).

So `blocked` does not mean "stuck". It means: **a specific question was asked of a person, that
question is recorded, and its answer is the thing that resumes the work.** And because answering
moves the task straight out, a task *sitting* in `blocked` is, by construction, one whose question is
**still unanswered**.

That last sentence decides the band.

## 2. The band, and why it is the same one as `completed`

`_loop_stall_reason` (`scheduler.py:340`) already states the rule for the gap it governs:

> `completed` and `under_review` are what remain in that gap, and they belong there: both mean
> **"someone else's turn"**.

`blocked` means *someone else's turn* in the most literal sense in the codebase — the someone is
named, the turn is a `Question` row, and the handover is enforced by a status the agent is not
allowed to set. It is a better member of that band than `under_review`, where "someone else" is only
implied.

The comparison that settles it is `revision_needed`, which went the *other* way on 2026-08-20 —
made claimable rather than left stalling. That was right, and for a reason that does not transfer:
a reviewer sending work back means **the agent's turn has come round again**, and firing it is what
resumes the work. Nothing outside the loop has to happen first.

For `blocked`, something outside the loop must happen first, and firing the agent cannot cause it.

The test is: *does firing an agent make progress possible?* `revision_needed` yes. `blocked` no — the
answer is what makes progress possible, and the answer arrives through
`release_block_for_question`, which moves the task to `in_progress` and makes it claimable **on the
very next tick, automatically**. Nothing is lost by stalling; the release path is already the
recovery path.

## 3. What the other three sets say, and why they are not really in disagreement

Task 3.4 says the four sets disagree. They do, but only one of them is the odd one:

| Set | `blocked`? | Reading |
|---|---|---|
| `CLAIMABLE_LOOP_TASK_STATUSES` (`scheduler.py:257`) | **in** | the outlier |
| `_ACTIVE_TASK_STATUSES` (`api/v1/agents.py:60`) | out | an agent holding a blocked task holds no work it can do — correct |
| `_LIVE_TASK_STATUSES` (`checkpoints.py:62`) | out | same, and identical in content |
| `TERMINAL_FOR_BINDING` (`run_task_binding.py:276`) | out | correct, and load-bearing: the binding must survive so the answer returns to the thread that asked |

Three of the four already treat `blocked` as *not the agent's turn*. Only the claim set disagrees,
and §4 is what that costs.

## 4. The defect — `blocked` routes around the spin fix

The spin fixed on 2026-08-20 was: *a firing that claims nothing, on a queue that is not drained,
spawns an agent to do nothing, forever.* The fix is `_loop_stall_reason`, and `_do_fire_job`
consults it **only when the claim returned nothing** (`scheduler.py:936-937`).

A `blocked` task is claimable, so the claim returns **something**. The stall check is never reached.
The chain, all read from source:

1. A run ends with an unanswered question → task is `blocked`, `blocked_reason` set,
   `question.blocked_task_id` set (`run_task_binding.py:399-407`).
2. Next tick, `_first_startable_candidate` walks `CLAIMABLE_LOOP_TASK_STATUSES`, which includes
   `blocked`. `dependency_gate.evaluate` guards `blocked -> in_progress`, but it evaluates
   **prerequisites**, not question state — so a task whose dependencies are met is returned.
3. `claimed_task is not None`, so `_loop_stall_reason` is skipped entirely.
4. The status is left alone — line 971 transitions only `pending` — and `assignee` is set.
5. `_compose_loop_briefing` (`scheduler.py:502-530`) emits title, description and acceptance
   criteria. **It never mentions `blocked_reason`, the open question, or the task's status.** The
   agent is handed a blocked task rendered exactly like a fresh one.
6. The agent is fired, cannot proceed, and has not been told why.

So the loop spawns an agent per tick against a task that provably cannot advance — the same shape as
the bug just fixed, in the one status the fix's own analysis flagged as unresolved.

### 4a. And the second question orphans the release

Step 6's most likely agent behaviour is to ask again. Follow that:

`park_task_for_question` begins `if STATUS_BLOCKED not in allowed_targets(task.status, actor.kind):
return None` (`run_task_binding.py:394`). `TRANSITIONS["blocked"]` is
`{in_progress, assigned, rejected}` — **`blocked` is not a target of itself**. So the call returns
`None` early and `question.blocked_task_id` is **never set** on the second question.

`release_block_for_question` opens with `if not question.blocked_task_id: return None`
(`run_task_binding.py:441`).

**Therefore: the operator answering the second question releases nothing.** The task stays `blocked`.
Only answering the *first* question — the older one, the one no longer in front of them — releases
it. Each subsequent tick can add another orphaned question to the pile.

Every individual piece here is correct and well-reasoned. The defect is entirely in their
composition, and it exists only because `blocked` is claimable.

**MEASURED, 2026-08-21.** Reproduced before fixing, in the order this session's other three loop
bugs were. Two attempts, and the failed one is the more informative:

- A **behavioural** reproduction (a loop whose only task is `blocked`, fired three times) **hung**
  against the unfixed code, twice, at ~3 s CPU. That is not contention — it is the bug. The test
  supplies its mock with two reads, enough for the one firing that should reach a spawn; unfixed,
  **all four firings spawned**, the mock ran dry inside an awaited background task, and the await
  never returned. The hang *is* the reproduction, just an unreadable one.
- A **mechanism** reproduction then measured it cleanly in **0.31 s**:
  `assert "blocked" not in CLAIMABLE_LOOP_TASK_STATUSES` →
  `AssertionError: assert 'blocked' not in ('in_progress', 'blocked', 'assigned', 'pending',
  'revision_needed')`.

After the fix the behavioural test passes in the same run as everything else — `test_scheduler.py`
**31 passed in 12.82 s**, up from 28 (two new tests, plus a third parametrization as `blocked` joined
the derived gap). The hang not recurring is itself the confirmation that firings stopped spawning.

### And then driven on a live Hub, 2026-08-21

The trial Hub on 8010 was restarted onto the fixed code and a loop was built to reach this state by
hand: one task walked `pending → assigned → in_progress → blocked` through the operator API, with a
`blocked_reason` of *"Which database should the migration target?"*.

**Fired twice. Both refused, identically:**

```json
{"detail": "loop queue is stalled: no claimable task among 1 open (1 blocked)"}
```

Both `JobRun`s recorded `skipped` with that reason as their `error_summary` (`run-81dcbffe`,
`run-52048b07`, read from the `job_runs` table). `firing_active: false`. `current_task: null`. And
**no agent run was created** — verified against the `runs` table, not an endpoint.

**Visibility survived exactly as predicted.** The loop's queue summary still read
`{"blocked": 1}`, because `queue_counts` carries no status filter while the current-item derivation
shares the claim's tuple. The blocked task stops being *current* and stays *counted*, which is what
keeps the board and the firing agreeing.

**Recovery, also measured.** Releasing the block (`blocked → in_progress`) cleared `blocked_reason`
by itself — `release_reason` doing its job — and the very next firing claimed the task and spawned a
real agent: `run-424f7dda`, agent `builder`, **completed, exit 0, 8 seconds**. So stalling costs
nothing and the recovery needs no help from the loop, which was the whole argument in §2.

**Side by side with the Finding A probe** in `2026-08-21-what-a-flow-fires-into.md` §2a, the contrast
is the point: a *stalled* firing records `skipped`, leaves `firing_active` false, and spawns nothing;
a *stranded* one records `in_progress`, leaves the card reading "firing" until the Hub restarts, and
also spawns nothing. Same absence of an agent, opposite stories told to the operator.

## 5. What to change

Small, and mostly deletion. **Items 1, 2 and 4 are done; 3 is a note for whoever writes group 3.**

1. ✅ **Remove `"blocked"` from `CLAIMABLE_LOOP_TASK_STATUSES`** (`scheduler.py:259`). The queue then
   stalls on it, `_loop_stall_reason`'s existing message reports it in the per-status breakdown
   (`"no claimable task among N open (1 blocked, …)"`), and the loop recovers by itself the tick
   after the answer arrives.
2. ✅ **Fix the docstrings that will become wrong.** `_claim_loop_task` (`scheduler.py:311`) and the
   comment at `scheduler.py:967` both name `blocked` as a resume case, and
   `_first_startable_candidate:277` lists it among the statuses one transition from `in_progress`.
3. **Task 3.3's literal changes.** The claimable set becomes
   `pending assigned in_progress revision_needed` — so the assertion written before the refactor must
   be written against the *corrected* literal, or the refactor will faithfully preserve this bug.
   Worth saying explicitly in 3.3, since its whole purpose is to stop behaviour changing under a
   refactor and here the behaviour change is the point.
4. ✅ **The derived-gap test needs its expectation widened.**
   `test_a_stalled_loop_queue_is_neither_claimable_nor_drained` derives the gap from `TRANSITIONS`;
   after this, the gap is `completed`, `under_review`, `blocked`. Widening it by hand is fine —
   deriving *which* gap members are correct is the judgement this document is making.

**A separate, smaller fix — DELIBERATELY NOT TAKEN, and still open.** `park_task_for_question`
returning `None` for an already-`blocked` task should still stamp `question.blocked_task_id`. The
task is already parked for a question; a second question about the same task should also be able to
release it. That closes §4a independently of the band decision.

It is left undone for two reasons. Item 1 closes the **loop's** route into §4a — the loop no longer
fires an agent at a blocked task, so it can no longer manufacture the second question. And the fix
changes what a `Question`/`Task` binding means, which is a semantic change to the operator-in-the-loop
path rather than a scheduling one, and belongs to whoever owns that decision.

**§4a therefore remains reachable** by any route that runs an agent on a blocked task without the
loop: a manual trigger, or an operator triggering the agent directly. The symptom is unchanged —
answer the newest question and nothing is released.

## 6. Where the reasoning should live

Task 3.4 says *"record the reasoning where the classification lives"*. Once group 3 lands, that is
the band definition in the new classification module. Until then it is
`CLAIMABLE_LOOP_TASK_STATUSES`'s own comment block (`scheduler.py:237-256`), which already carries
this kind of per-status reasoning for `revision_needed` and `assigned`.

The sentence to carry across, in whichever place: **`blocked` is not claimable, because a task in
`blocked` has an unanswered question, and firing an agent cannot answer it.**

## 7. Still open

- **Should the briefing mention a task's status at all?** §4 step 5 assumes it should not need to,
  because a stalled task is never briefed. If any "not the agent's turn" status ever becomes
  claimable, the briefing silently misrepresents it — this is a general weakness that §5's fix hides
  rather than removes.
- **Does `blocked` interact with the flow's reviewer ladder?** `_ACTIVE_TASK_STATUSES` excludes it,
  so an agent holding only blocked tasks reads as free and is eligible for rung two. That is probably
  right — it genuinely has no work it can do — but it is untested and pairs with the availability
  problem in `2026-08-21-what-a-flow-fires-into.md` §2.
- **`blocked -> completed` is absent by design** (`task_transitions.py:122-125`), so a task unblocked
  by an operator's answer must pass back through `in_progress`. Nothing here disturbs that, but it
  means §5's stall depends on `release_block_for_question` being the *only* automatic exit. It is,
  today.
