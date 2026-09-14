# Test guide — a task nothing will move holds nobody

## Agent-verifiable

| What | How | Task |
|---|---|---|
| A task outside every loop holds nobody, in each of the five live statuses | pool test, parametrised | 1.2 |
| A task in a loop that has not ended holds its assignee | pool test | 1.3 |
| A paused loop's task still holds | pool test, `AIJob.enabled = False` | 1.4 |
| An ended loop's task, or a `loop_id` naming no loop, holds nobody | pool test, three cases | 1.5 |
| A turn queued for the assignee holds its task; one for somebody else does not | pool tests, `task_id` and `review_task_id` | 1.6, 1.7 |
| D4's pile-up test still holds inside a loop, and its opposite holds outside | re-staged ladder test and its sibling | 2.1, 2.2 |
| LoopEngine's board staffs its review | `decide_firing` on the reproduced shape | 3.1 |
| A bookmark-holder takes new work | `decide_firing` | 3.2 |
| The guard, the Run route and the board agree with the walk | guard test, `POST …/run`, the loops board | 3.3–3.5 |
| The roster still counts the task | `GET` agents | 3.6 |
| Real routes, a real Haiku turn, with the control and the paused/ended cases | drive on a fresh drive Hub | 5.2–5.4 |

## Human-only

1. **LoopEngine, after your next restart of `:8000`.** That restart also applies migration `0103`.
   Within a few firings, the flow should stop recording *"could not staff this step"* and start a
   review with `dev` or `dev_2`. The Architect should stay unavailable while its `under_review` task
   waits on you.

   **Watch the first half hour's usage.** Two agents may start at once, on the weekly window.
2. **Does a paused loop holding its agents match what you meant by pausing?** Pause a loop whose
   agent is assigned one of its tasks, and watch whether another flow will give that agent work. It
   will not. If you expected it to, the fix is one clause (design D2).
3. **Do bookmarks still read right on the board?** The eight free-floating tasks keep their status
   and assignee, and the roster still counts them. Judge whether an agent shown with four active
   tasks while it works a fifth reads as sensible, or needs a word on the card. That would be a UI
   change for later, not this one.

## Known and accepted

- **A review nobody is doing, inside a live loop, still holds its reviewer** (design D5). This is
  LoopEngine's Architect. It is surfaced by name every tick (F154), and freeing it is an operator
  question about reviews: option (d).
- **A paused loop's agents stay unavailable to other flows while the pause lasts** (design D2). This
  is deliberate, and it is flagged to the operator.
- **An out-of-loop assignment no longer reserves its agent**, unless input about that task is
  queued for it (design, *Risks*).
- **New orphans are still created.** Stopping them is `who-owns-a-loops-queue`: owner, admission,
  amend and a non-blocking question. This change makes them cost nothing. It does not make them
  stop.
- **The unstaffed sentence still names nobody.** That is F352's visibility half, in
  `an-unstaffed-review-names-its-holders`. It must be re-derived against this change's definition
  first.
