# Design — an unstaffed review names its holders

**2026-09-15: read `proposal.md`'s top banner first.** D4 and D5 below (and the `own_review_remedy`
/ length-fit passages inside D2) moved verbatim to
`openspec/changes/a-refusal-names-a-remedy-that-works/design.md` — kept here only as history. D1,
the rest of D2, D3 and D6 are what remains to build, and they need re-deriving against
`F352-free`'s decision (option (f), reachability, `4b59ee0`) before any of it is trustworthy: this
text still argues from option (e), which did not ship.

**2026-09-19: that re-derivation is done — `## Round 5` at the end, read it before D1.** The
decision to name the holdings survives; the case R1 built for it does not, and neither does its
remedy. **D1 as originally written would silently revert `4b59ee0`** (see the R5 block inside it);
D2's clause 3 now filters by reachability and names each holding's loop; the freeing clause gains
the remedy (f) created, archiving the loop that holds them, and is forbidden from suggesting pause.
The `OPERATOR QUESTION` in `proposal.md` is closed and should no longer be read as open.

**2026-09-21, R8: the paragraph above is partly superseded — do not build from it.** Its *"names
each holding's loop"* and *"archiving the loop that holds them"* were both removed by R6 (R6-3); the
remedy is rejecting only. R8 then changed three more things D2 below still reads as current: the
**hold precedes the holdings clause**, the holdings clause reads **`is booked for`** rather than
`holds`, and the join is written out (capitalised remedy, conditional rejecting sentence,
hold-aware tail). The build instruction is `tasks.md` 2.3's R8 block; the argument is `## Round 8`.

R1, 2026-09-14. Line numbers are at `2d5674c`. R2, 2026-09-14, re-derived at `e8ea490`: every
decision it changed is marked **R2**, and *Round 2* at the end lists what changed and why. R3,
2026-09-14, re-derived at `fb469e2`: marked **R3**, listed in *Round 3* at the end. REV,
2026-09-14, at `82b58df`: marked **REV**, listed in *Round 4* at the end. **REV stopped the
change**, and it is unbuilt (proposal.md, top).

## Context

Rung 3 of the reviewer ladder is the only thing an operator is shown when a flow cannot staff a
review. The facts behind it are computed on the same call: who is running, and who holds which task
in a live status (`_agents_that_are_free`, `scheduler.py:977-1040`). The ladder discards them
(`scheduler.py:1136-1168`) and returns a sentence written for the general case. The sentence then
travels, unchanged, to three places:

| where | how | what the operator sees |
|---|---|---|
| `FiringDecision.unstaffed` → `stall_reason` (`scheduler.py:1655`) | F64's promotion of `unstaffed[0][1]` | the loop board's amber line, one line, CSS `truncate`, no tooltip (`LoopsIndexTab.tsx:237-244`) |
| `JobRun.error_summary` (`scheduler.py:2762`) | the stall row, incremented while equal (`:923`) | the run history |
| `review_unstaffed` event (`scheduler.py:1944-1995`) | persisted and broadcast, once per fact (`:1978`) | the activity feed, `no agent could review <task>: <reason>` (`eventSummary.ts:79-80`) |

The divergence restaff (`run_divergence.py:440-451`) calls the same ladder and surfaces the same
`choice.reason`.

## Decisions

### D1 — one availability read, two consumers

`_agents_that_are_free` becomes a projection of a new `_roster_availability(session, project_id)`,
which returns one record per **non-archived** agent in name order:

```
AgentAvailability(name, has_runner: bool, running: bool, holdings: tuple[(task_id, status), ...])
```

The record is built from the same three queries the function runs today:
- `Run.status == "running"`;
- `Task.assignee` over `LIVE_STATUSES`, now selecting `Task.id` and `Task.status` too, with holdings
  ordered by task id;
- the roster, now **without** the `runner_id IS NOT NULL` filter, which moves into the projection.

The pool is `[a.name for a in availability if a.has_runner and not a.running and not a.holdings]`.
That is the predicate the function has today, and `agent-flows` states it. **No agent enters or
leaves the pool because of this change**, and the existing ladder, width and busy-guard tests are
the proof that it does not.

> **R5 — STOP. The three paragraphs above are false as of `4b59ee0`, and implementing them as
> written would revert (f).**
>
> They were true when R1 wrote them. They are not true now, and this is the most serious thing R5
> found, because it is a *silent* regression: it reverts a shipped behaviour while every sentence
> around it still reads correctly.
>
> - The function does **not** read `Task.assignee` over `LIVE_STATUSES` and stop. It reads that as
>   the *band*, then filters by reachability — `loop_id in live or (task_id, assignee) in queued`
>   (`scheduler.py:1146-1150`) — and its own docstring says so: *"the roster's `LIVE_STATUSES` is
>   read here only as the band a holding must be in, not as the whole test"* (`:1089-1092`).
> - So the pool is **not** `not a.holdings`. An agent holding three live tasks that nothing will
>   move is in the pool today. Under the predicate written above it would not be.
> - **The claim "No agent enters or leaves the pool because of this change" is therefore the
>   opposite of the truth**, and the tests named as proof would catch it — including
>   `test_the_loopengine_shape_staffs_its_review`, which asserts the pool is *not* empty in exactly
>   the shape D1's predicate would empty. That is the one mercy here: this cannot ship green.
>
> **Corrected shape.** The record carries the reachability verdict, not a raw holding list, because
> two consumers need two different things from it and only one of them is the pool:
>
> ```
> AgentAvailability(name, has_runner, running, held, holdings: tuple[Holding, ...])
> Holding(task_id, status, loop_id, reachable: bool)
> ```
>
> - the **pool** is `[a.name for a in availability if a.has_runner and not a.running and not a.held
>   and not any(h.reachable for h in a.holdings)]` — the predicate the code has today, restated, so
>   D1's "no agent enters or leaves" claim becomes true again;
> - **clause 3** prints `[h for h in a.holdings if h.reachable]` (R5-3).
>
> **R6 added `held`, and R5 missing it is the same mistake R5-0 is about.** `_agents_that_are_free`
> does not read one running source, it reads two: `select(Run.agent).where(... status ==
> "running")` **`| await agents_held(session, project_id)`** — one expression,
> `scheduler.py:1114-1122`. A usage-held agent holding nothing has `running=False` and no reachable
> holding, so without `held` on the record it returns to the pool and
> `a-spent-allowance-holds-the-queue` D6 is reverted along with `4b59ee0`. `held` is a separate
> field rather than folded into `running` because **clause 4 has to tell them apart** (D2): an
> agent that is held is not running a turn, and saying it is states a false cause.
>
> Keeping the unreachable holdings on the record rather than filtering them out of the query is
> deliberate: the reachability arms are already computed for the pool, and a second query to find
> out which of an agent's tasks are unreachable would be the third opinion this decision exists to
> prevent. Nothing prints them today. **Do not add a surface that does** without deciding what an
> operator is supposed to do with a task nothing will move — that is `R4`/`F218`'s territory, not
> this change's.

*Why one read:* the function's own docstring argues that *"a third opinion about whether an agent
is busy cannot appear here"*. A sentence built from a second query would be exactly that third
opinion, able to name an agent the pool thought free. *Rejected:* building the sentence at the call
site from `decide_firing`'s precomputed `free` and `running`. The divergence restaff has neither
precomputed, so it would need its own copy.

**R2: three callers, and one read per ladder.** The projection has three callers, not two:
`_loop_flow_busy_reason` (`scheduler.py:298`), `decide_firing`'s pool (`:1298`), and rung 2
(`:1137`). All three keep the projection unchanged. Inside `resolve_reviewer`, the read must happen
**once**. Rung 2 walks the projection of the records, and rung 3 describes the same records. Calling
`_agents_that_are_free` for rung 2 and then `_roster_availability` for rung 3 would be two reads, the
third opinion this decision exists to prevent.

**R2: an empty roster says so.** Rung 3 is reachable with no record at all: a project whose agents
are all archived, or that has none. The clauses are then empty, and the sentence says *"the project
has no agent on its roster"* in their place, before the remedy.

### D2 — what rung 3 says, and in what order

> **R8 (2026-09-21): the clause order and wording below are superseded by `## Round 8`** (R8-1,
> R8-2, R8-3, R8-4, R8-5). The order is now excluded, no runner, **held, booked**, running; clause
> 3's verb is `is booked for`. The reasoning below is kept; where it argues for *holds before
> held*, R8-1 is the answer.

For each record, the **first** of these that holds becomes that agent's clause:

1. **excluded** — `"{name} {clause}"`, where the clause is the caller's reason for this agent (D3);
2. **no runner** — `"{name} has no runner bound"`;
3. **holds** — `"{name} holds {id} ({status})"`, listing up to three held tasks and then
   `"and N more"`;
4. **held** — `"{name} is waiting for its provider's usage limit to reset"`;
5. **running** — `"{name} is running a turn"`.

**R6 added clause 4, and it is not optional.** `openspec/specs/agent-flows/spec.md` already carries
a shipped SHALL: where an agent was passed over because its queue is held, the reason *"SHALL name
the hold among the grounds, and SHALL NOT state that every agent is running a turn, holding work or
excluded."* R1–R5's four-clause list has no hold in it, so the sentence it builds would both drop a
required ground and tell the operator a held agent is running a turn. The clause sits **after**
holds and **before** running: holds is the actionable one, and of the two wait-states a hold names
a specific external cause that clears on its own schedule, which is more use than "busy".

**R6 removed the loop id from clause 3.** R5 added it for one purpose — to let the operator aim the
archive remedy — and R6 removes that remedy (below), so the loop id now costs 21 characters per
holding and buys nothing. It was also unprintable in the case that matters: a holding reachable
only through the queued arm can have `loop_id` NULL, and the clause would read `in None`.

**R5 — clause 3 changed twice, and both changes come from (f).**

- **It lists only *reachable* holdings.** Under the rule this change was written against, every live
  assigned task made its assignee unavailable, so "what this agent holds" and "why this agent cannot
  review" were the same list. Under (f) they are not: a task makes its assignee unavailable only if
  `loop_id in live or (task_id, assignee) in queued` (`scheduler.py:1146-1150`). A task outside
  that set holds nobody — that is the whole of what (f) decided — so naming one here would state a
  reason that is not one. **The list is the pool's own predicate, not `LIVE_STATUSES`.**
- **Each holding names its loop**, which R1–R4 did not carry. That is not decoration: under (f) the
  dominant arm is `loop_id in live`, so *which* loop holds an agent is what decides whether the
  operator can free it, and for which review — see the remedy below. Budget cost is measured in the
  R5 table; where it does not fit, the loop is the first thing dropped, because a holding without
  its loop is still true while a name without its holding is not.

**The sentence and the roster will now disagree, and the sentence must not pretend otherwise.**
`_agents_that_are_free`'s own docstring is explicit that the roster's "active task" count
(`api/v1/agents.py`) answers *what does this agent hold* and still counts every live task, while the
pool answers *may a flow give this agent work* (D5, `scheduler.py:1089-1092`). Under the old rule
those two produced the same number. Under (f) they routinely differ, so an operator reading
*"dev holds 1 task"* here and *"dev — 4 active"* on the roster sees a contradiction between two
surfaces that are both correct. The clause therefore reads **holds**, and the remedy sentence says
the list is what something will still move; the roster is not changed to match, because D5 decided
on purpose that it answers the other question.

Clauses are in name order. Every record matches one of the four. **R3** corrected R1's reason for
that, *"the pool is empty by construction at rung 3"*, which is false: the author can be free, and
then it is in the pool and merely excluded. What rung 3 guarantees is narrower. Every pool member is
in `exclude`, because rung 2 would have returned any other, and `only_taken` would have deferred
one in `unavailable` (`scheduler.py:1137-1159`). So a pool member takes clause 1, and every other
record fails the pool predicate, which leaves no runner, a holding, or a running turn.

The order is chosen for the operator, not for the code. Exclusion is a fact about this task and
outlasts everything else, so it wins. An agent with no runner can never be staffed, so that fact
comes before any holding. Holdings are the standing cause, and F352's whole finding is about them.
Running comes last because it is transient, and an agent mid-turn usually holds the task it is
working on, so it is named by that task instead. That choice also keeps the reason stable across
ticks (D4). A reason naming whoever is mid-turn would change on every turn boundary, and each change
is recorded as news.

**The sentence leads with the names.** It is `could not staff this step: no reviewer is free. `
followed immediately by the clauses, then the remedy. It has no general sentence before the names,
because the board shows about 80 characters of it. **REV** replaced R1's *"nobody is free"*, which is
false whenever the author holds nothing: a just-finished author's `completed` task is not live, and
in a one-agent project the only agent is free. *"No reviewer"* is true, because the author is not
one, and its clause says so. It costs 4 characters (budget table below).

**The remedy depends on the task's status.** Rung 3 is reached for `completed` tasks, and for
`under_review` rows the F70 recovery and the divergence restaff carry to the ladder. **One helper,
`own_review_remedy(task)`, writes it**, and D5's dispatch refusal calls the same helper (R2). It is
public, without a leading underscore, because `agent_trigger` imports it from `scheduler`. That is
the rule `enter_selected_task`'s docstring states for the same situation.
- **`completed`:** *Land it, on the task, to review it yourself*. This is F163's action, in the
  drawer for exactly this status (`TaskDetailDrawer.tsx:345`).
- **`under_review`:** *decide it yourself: approve, reject, or send it back with revision_needed*.
  `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`), so naming Land it there would
  name an action that refuses.
- **Both:** *rejecting a held task that is no longer wanted frees its agent*. The operator can take
  `rejected` from every status that holds an agent. `LIVE_STATUSES` is pending, assigned,
  in_progress, revision_needed and under_review (`task_transitions.py:218-228, 338`), and each has
  an operator `rejected` edge (`:100-146`). That is what freed `tester` on LoopEngine at 22:33.
  **REV:** *"frees its agent"* is false for an agent holding several tasks (`dev_2` held five), and
  the clause is option (e)'s remedy, true only while the definition of free stays as it is. The
  wording becomes *"rejecting held tasks that are no longer wanted can free their agents"*, and the
  OPERATOR QUESTION's answer re-derives it.

  **R5 re-derived it against (f) and proposed archiving the loop as a second remedy. R6 REMOVES
  that**, and the removal is the main thing R6 does. R5's reasoning was that `live` excludes an
  archived loop (`scheduler.py:1126-1130`) and `POST /jobs/{job_id}/archive` sets
  `loop.archived_at` (`api/v1/jobs.py:1198`), so archiving frees the agents that loop was holding.
  Three things are wrong with it, and any one of them is disqualifying for a change whose entire
  subject is remedies that work:

  - **It is not guaranteed to free anybody.** Reachability is an **OR**: `loop_id in live or
    (task_id, assignee) in queued` (`scheduler.py:1146-1150`). Archiving the loop withdraws the
    first arm and nothing else — a queued turn naming that `(task, assignee)` survives it
    (`run_task_binding.py:342-353` selects on `state == "queued"` and hop depth; archiving
    withdraws nothing), and the agent stays held. The remedy would be false precisely when the
    operator acted on it.
  - **It is inapplicable in the case that is left.** R5-1 narrowed the remaining rung-3
    circumstance to agents holding **in-loop** work. For those the loop that holds them *is* the
    loop whose review is stuck, and archiving it stops the work the sentence is asking the operator
    to unblock. The remedy applies least often in the situation the change now exists for.
  - **It cannot be aimed.** The clause would print a loop id, but `POST /loops/{id}/archive`
    **refuses a live loop** (`api/v1/loops.py:171-175`, 400 while `ending_state is None`). The only
    archive that works on a live loop is keyed on the **job** id, and `Loop.id != Loop.job_id`.
    Printing an identifier the working control does not accept is F353 exactly.

  **So the remedy is the reject clause and nothing else** — true, operator-reachable from every
  status that makes an agent unavailable, and unchanged since REV. This is the "materially smaller
  change" R6's review argued for: R5 tried to add value and added a false sentence.

  **Pausing frees nobody, and the sentence must never suggest it.** `_agents_that_are_free` is
  explicit: *"A **paused** loop still holds, because re-enabling it briefs the assignee on the
  task again"* (`scheduler.py:1084-1085`). Pause is the control an operator reaches for first and
  the one that looks like it should work, so the tests assert the string "pause" never appears in
  a rung-3 reason.

  Wording, with the status half from `own_review_remedy` unchanged before it:
  *" Rejecting held tasks that are no longer wanted can free their agents."* — **a new sentence,
  not a `;` continuation. R6-8, measured:** `own_review_remedy` returns a complete sentence ending
  in a period (`scheduler.py:1921-1923`: `"Land it, on the task, to review it yourself."`), so
  R1-R5's *"rung 3 appends `; rejecting …`"* produces `…to review it yourself.; rejecting held
  tasks…`. Every round wrote the clause with a leading `;` and none of them concatenated the two
  strings to look at the result. The helper is not changed — `review_dispatch_refusal` shares it —
  so the join is rung 3's, and it is a space and a capital.
- **Any other status (REV).** The divergence screens out only `blocked` (`run_divergence.py:746`),
  and `run_advanced_its_task` counts only the run's own transitions. So if the operator moves a
  task to `revision_needed` or `rejected` while its review run is live, that run's end still
  reaches `_answer_failed_review` and `resolve_reviewer`, and neither sentence above is true.
  **Decided here:** the divergence restaff does not staff a task whose status is no longer
  `completed` or `under_review`, because there is no review left to staff. It returns `None` at the
  same screen as `blocked`. The helper then asserts it is given one of the two statuses, and a test
  drives the operator move mid-run. This changes `run_divergence`'s behaviour, so it needs the
  verification round a restart of this change requires (*Round 4*).

**R3: the helper writes the status half only, and rung 3 appends the freeing clause.** R2 left
open whether *"rejecting a held task … frees its agent"* was part of what `own_review_remedy`
returns. D5 ends the dispatch refusal with the same helper. That refusal answers an operator who
named one reviewer, and whether anyone else is free has no bearing on it, so the clause there would
be noise. The helper returns the `completed` or `under_review` sentence and nothing else. Rung 3
appends `; rejecting a held task that is no longer wanted frees its agent.` The measured strings
below already concatenate the two, so the budget is unchanged.

**R2: the `completed` remedy does not promise an approval.** R1 wrote *"Land it, on the task,
approves it"*. That is false in the common case.
- `land_task` evaluates the approval gate before it moves anything (`tasks.py:1543-1545`).
- `_check_unaccepted` (`requirement_gate.py:493-541`) refuses when evidence naming a commit is still
  waiting to be judged and nothing else would merge. It is rigor-independent.
- A task at rung 3 has evidence naming a commit **by construction**: the arm refuses anything else
  first (`scheduler.py:1538-1548`).
- A flow's review is usually what would judge that evidence. So on a repository project with a main
  branch, Land it **usually** refuses with *accept or grant* until someone decides the evidence.
- LoopEngine's two landings at 22:33 worked only because every piece of their evidence had already
  been decided. Read mode=ro: `task-611ae46fe0fb` had 1 accepted and 2 rejected, and
  `task-c8d4a3d70c19` had 3 accepted, all decided by `tester` at 21:21 and 21:41 without moving
  either task.

**R3: "usually", not "until".** R2 wrote that Land it refuses *until someone decides the evidence*.
The code says it refuses only where all three of these hold. Each is read from code, and none was
driven:
- **Evidence governs the merge.** A flow created through the operator's `POST /jobs` with both
  `spec_document_id` and `work_needs_evidence: false` is accepted (`api/v1/jobs.py:672-681`). Only
  the agents' `create_flow` refuses the declaration. For such a flow, `evidence_governs` answers
  from the declaration before it looks at the document (`task_integration.py:378-381`), so
  `merge_targets` returns the task's branch tip. Awaiting evidence then reaches `_check_unaccepted`
  as an advisory, not a refusal (`requirement_gate.py:538-540`), and Land it approves. Rung 3 is
  still reachable there: the document passes `scheduler.py:1492`, and evidence naming a commit is
  what passes `:1538`.
- **Nothing already accepted would merge.** Work sent back through `revision_needed` and completed
  again can carry earlier accepted evidence. That is the mixed case, also an advisory.
- **The project has a main branch, and its workspace resolves as a repository.** Otherwise
  `_merge_situation` returns `None` and the check does not run (`requirement_gate.py:393-418`).

The spec's *"the gate may refuse"* was already right, and the wording does not move.

*"To review it yourself"* is true either way. The drawer renders a gate refusal where the button
is (`TaskDetailDrawer.tsx:335-369`), naming what approval still needs.

*Rejected:* a structured `holders` field on the event beside the sentence. The board renders
`stall_reason`, a string, and a second field would give two accounts of one fact. The sentence is
what every surface already carries.

**Length: the sentence is bounded, because one route would fail on it.** `JobRun.error_summary` is
declared `String(500)` (`models.py:1349`), and SQLite does not enforce that. **The response does:**
`JobRunResponse.error_summary` is `Field(max_length=500)` (`schemas/jobs.py:88`), and
`GET /jobs/{job_id}/history` answers `List[JobRunResponse]` (`api/v1/jobs.py:1197`). A stall reason
longer than 500 characters would be stored without complaint, and it would turn the job's history
route into a response-validation 500 for as long as that row is among the rows it returns. With
four agents and three holdings each, D2's sentence reaches that length. So:

- **Rung 3 builds within 500 characters.** If the whole sentence fits, it is used. Otherwise
  clauses are added in name order while prefix, clauses, the tail
  `"; and N more agents are excluded, busy or unbound"` and the remedy still fit. The remedy is
  always kept. The result is deterministic and is the same string on every surface.
- **R3: a holds clause that would not fit names fewer of its tasks before its agent is counted.**
  Each time a holds clause is added, it is tried with three named tasks, then two, then one,
  and the rest are counted as `and N more`. Only when even the one-task form would not fit is the
  agent left to the tail. R2's claim that *"at least one agent is always named"* rested on task
  ids being 17 characters, and they are not always:
  - `TaskCreate.id` (`schemas/tasks.py:17, 72`) and the agents' `AgentTaskCreate.id`
    (`agent_actions.py:94`) both accept a caller-chosen id of up to 64 characters.
  - With three such held tasks and a 32-character name, one clause measures **300**, over both
    budgets (297 and 267). Under R2's rule, a roster whose first agent in name order held them
    would have named nobody. That is F352's defect, returning in a corner.
  - With the fallback, the widest clause is **219** at two named tasks and **135** at one (a
    32-character name, 64-character ids, `revision_needed`, 1,000 more;
    `%TEMP%\f352r3\len4.py`). Both fit the smaller budget, so at least one agent is always named
    and R2's claim becomes true.
  - **Not observed:** the `:8000` database's 50 tasks all have 17-character ids, and its longest
    agent name is 9 characters (mode=ro, `%TEMP%\f352r3\ids.py`).
- **R2, measured budget** (`%TEMP%\f352r2\len3.py`):

  | piece | characters |
  |---|---|
  | prefix `could not staff this step: nobody is free. ` (**REV:** `no reviewer is free`, 47, so every budget and total below moves by 4; LoopEngine's `under_review` shape becomes 493, and still fits) | 43 |
  | `completed` remedy | 109 |
  | `under_review` remedy | 139 |
  | tail | 50 at most |
  | clause budget with a tail, `completed` / `under_review` | 297 / 267 |
  | widest single clause (a 32-character name, three held `revision_needed` tasks, "and 2 more") | 159 |
  | **R3:** the same with 64-character task ids, at three / two / one named task | 300 / 219 / 135 |
  | LoopEngine's four agents, as `completed` / as `under_review` | 459 / 489 |
  | task 2.6's shape | 402 |

  The 32-character name is the routes' limit, not the column's. `Agent.name` is `String(64)`
  (`models.py:200`), but every route that writes one caps it at 32: `OperatorAgentCreate`
  (`agents.py:92`), `AgentRequest` (`:78`), and `register_agent` and session sync through
  `validate_agent_name`. No route renames an agent (**R3**, grep).

  With R3's fallback, at least one agent is always named, and LoopEngine's whole roster is named.
  **R1's wording
  would not have named it.** With an honest remedy in R1's phrasing
  (*"…approves it or says what approval still needs. Rejecting a task an agent holds…"*), the
  LoopEngine sentence measures 514, and `tester` would have collapsed into the count. R1's 483
  fitted only because its remedy promised the approval above.
- **Every `JobRun.error_summary` write is fitted to the column (R2: at the model, not at two call
  sites).** The column is `String(500)` (`models.py:1349`), SQLite does not enforce it, and
  `JobRunResponse` does (`schemas/jobs.py:88`). R2 confirmed the mechanism with the real schema
  class (`%TEMP%\f352r2\route.py`): a `response_model=List[JobRunResponse]` route answers 200 at
  500 characters and **500 at 501**.
  - One constant, `JOB_RUN_ERROR_SUMMARY_CHARS = 500`, beside `JobRun`, is read by the column, by
    the schema's `max_length`, and by `fit_error_summary(text)`. The helper leaves text that fits
    unchanged, and cuts longer text to 499 characters plus `…`.
  - `JobRun` gets `@validates("error_summary")`, which applies the helper. That is the column
    enforcing its own declared length, which SQLite will not. It is the first `@validates` in
    `hub/hub`. It is chosen over wrapping each call site because there are eight writes today
    (`scheduler.py:2580, 2609, 2762, 2923, 2966, 3062`, `api/v1/jobs.py:81` and
    `run_reconciliation.py:222`), and the next one would be written without the wrapper.
  - **R3: it fires on every write this column receives, measured.** A `DeclarativeBase` model
    with `@validates` fitted both a constructor keyword and an assignment. The real `JobRun` did
    the same through the attribute `set` event with `retval=True`, which is the hook `@validates`
    installs. That covers `api/v1/jobs.py:81`'s `JobRun(error_summary=...)`, and all seven
    assignments (`%TEMP%\f352r3\val.py`). The validator runs in Python when the attribute is set,
    so an async session changes nothing. Its only blind spot is a Core `update()`/`insert()`, and
    a grep finds none against `job_runs` in `hub/hub`. The column is nullable, so the helper passes
    `None` through, and 2.12 asserts it.
  - *Rejected (R3):* a `TypeDecorator` fitting at bind time. It would also catch a Core statement.
    But it leaves the attribute unfitted in memory until the row is expired, so the object and the
    row would hold two values, and a response built from the object would still carry 600
    characters. `@validates` fits the value the object holds, which is what the route reads.
  - `_stall_run_to_increment` (`:923`) compares `latest.error_summary` with
    `fit_error_summary(stall_reason)`. The stored value is fitted, so comparing the raw reason would
    never match its successor, and D6 of `loop-notices-and-reacts` would record one row per tick.
- **R2 answered R1's open check: an existing reason already passes 500 today.** Computed, not
  observed:
  - **`_wedged_review_reason`** (`scheduler.py:1744-1748`) reaches `error_summary` through F64's
    promotion (`:1655`) and the stall write (`:2762`). It measures 551 characters with a
    32-character reviewer and a 256-character title, and passes 500 once the title reaches 206
    characters. The title is quoted with `!r`, so escapes grow it: 256 backslashes make the
    sentence 807 characters long.
    The model-level fit would cut its remedy off the end, so **the function shortens the quoted
    title to what fits** (with `…`), and the sentence keeps its remedy.
  - **`schedule_result.waiting_reason`** (`:2923`, `:3062`) is the `detail` of any non-transient
    `TriggerAgentError`. Several embed exception text: git's stderr and two absolute paths
    (`agent_trigger.py:966, 970`), and `str(exc)` (`:607, 806, 853, 867, 1116`). These are unbounded
    by construction. The fit covers them, and cutting them loses only the tail of a git message.
    **REV: not only a git message.** A non-transient refusal becomes a terminal failure
    (`turn_scheduler.py:658-672`), and the guard's own sentence reaches `waiting_reason` this way
    through `agent_trigger.py:852`. Today's evidence-branch sentence measures **534** at a 64-character
    id and a 32-character name, and R2's D5 shape measured **583** (`%TEMP%\f352rev\len.py`). The
    fit would have cut the remedy off the end. D5 is now worded to fit (D5, *REV*).
  - `_job_agent_skip_reason` (`:2580`), the stop reasons (`:2609`), both `_safe_error_summary`
    copies (`scheduler.py:2966` and `api/v1/jobs.py:81`, each already `[:500]`) and the
    reconciliation constant are bounded.
  - **Observed:** the `:8000` database's longest `error_summary` is 276 characters over 43 rows,
    and the trial Hub's 3 rows are empty (mode=ro, `%TEMP%\f352r2\len.py`). Nothing has failed yet.
    Filed as **F367 (C)** and retired by this change.

### D3 — the exclusion carries its reasons

`resolve_reviewer(exclude=..., excluded_because=...)` is replaced by `exclude: Mapping[str, str]`,
mapping each agent to the clause that says why it is excluded.

- `decide_firing` (`scheduler.py:1550-1584`) builds `{author: "is the one that completed this
  task"}`, or `{a: "has worked on this task" for a in agents_that_may_have_authored(...)}`. Byte for
  byte, these are the clauses it passes today.
- `run_divergence` (`:430-446`) builds the mapping in three layers, each overwriting the one
  before (**R2**; R1 had the order wrong):
  1. on the operator-completed branch, `agents_that_may_have_authored` → `"has worked on this task"`;
  2. the silent reviewers and `run.agent` → `"reviewed this task and recorded no verdict"`;
  3. on the agent-completed branch, the recorded completer → `"is the one that completed this
     task"`.
- Rung 1b (`scheduler.py:1124-1133`) reads `exclude[resolution.agent]` where it read
  `excluded_because`.

**R2: why the silent reviewer overwrites "has worked".** R1 laid the author clause over the silent
reviewers. On the operator-completed branch, that erases the one fact this decision exists for.
`agents_that_may_have_authored` is the union of the transitions, the **assignee**, the agents of
**runs bound to the task**, and the evidence recorders (`task_transition_service.py:329-332`). The
silent reviewer is the assignee, and its review run is bound to the task, so it is always in that
set. Under R1's order, it would read *"has worked on this task"*, which is not false but loses
the fact. R1's own scenario (*"states that the agent which gave no verdict reviewed the task without
recording one"*) would then fail on exactly the branch F316 was about. A recorded completer still
wins over both: it is the fact the corpus is keyed on (`scheduler.py:1550-1555`).

*Why:* `run_divergence` puts the silent reviewer into the same set as the author, under one
clause, *"is the one that completed this task"*. Today that clause is generic prose. Under D2 it
would become `"rv is the one that completed this task"`, a false statement about a named agent.
`agent-flows` already forbids that for the operator-completed case (*"The second resolution's
surfaced reason does not claim an agent completed the work"*).

*Rejected:*
- **An extra `also_excluded` mapping beside the set.** It gives three parameters for one idea.
- **Accepting either a set or a mapping.** It gives two shapes for one parameter.

The mapping is one statement of who is excluded and why. The 14 test call sites that pass a set
(`test_reviewer_ladder.py`, 12, and `test_a_flow_names_what_it_cannot_staff.py:472, 482`) are
updated, along with the two runtime callers.

**R2: a missed call site fails loudly only where it reaches a named exclusion.** R1 said a missed
call site "fails loudly". A set reaching `exclude[name]` does raise `TypeError`. But
`candidate in exclude` works on both shapes, so a set only fails where a test reaches rung 1b or
rung 3 with an excluded agent. Nothing else catches it either: CI runs `mypy src/` only
(`.github/workflows/ci.yml:77`), never over `hub/`. Task 2.1 therefore lists every call site by line,
and IMPL greps for `exclude=` before ticking it.

### D4 — once per fact means once per task

`_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) adds the task to its query:
`EventLog.data["task_id"].as_string() == task_id`, newest first, `limit(1)`. That makes it the
newest record **for this task** in this loop, which its own docstring already claims to read.

*Measured:* 347 of LoopEngine's 357 `review_unstaffed` events repeat their own task's previous
reason. The one stretch with a single unstaffed task (22:35–22:55 UTC) recorded once. The rule
works for one task and fails for two.

*Why SQLAlchemy's JSON path and not a Python scan:* the scan is unbounded over a loop's history (357
rows here and growing), and the JSON path compiles to SQLite's `JSON_EXTRACT`, which is built into
the SQLite that Python 3.11 ships. No runtime code uses a JSON path yet. The note in migration
`0083` avoids `json_extract` *in a migration*, for data-shape reasons that do not apply to a column
written only by `persist_event`. **IMPL proves this with a test against real SQLite, not a mock.**
If the path cannot be made to work, the fallback is a bounded Python scan, and R2 or IMPL records
the switch.

**R2: it works.** `EventLog.data` is a SQLAlchemy `JSON` column (`models.py:1018`), and
`persist_event` writes the payload dict into it (`utils.py`, `data=data or {}`). R2 ran the query
against the Hub's own models on `sqlite+aiosqlite:///:memory:` under `py -3.11`
(`%TEMP%\f352r2\jp.py`). It used four `review_unstaffed` rows alternating between two tasks, the
way LoopEngine's did. The statement compiles to
`JSON_EXTRACT(event_logs.data, '$."task_id"') = :task_id` and returns the right newest row for each
task, and no row for a task with none. A grep finds no other `.as_string()` in `hub/hub`, so R1's
*"no runtime code uses a JSON path yet"* holds. The fallback is not needed.

*Interaction with D2:* the reason now changes whenever the named holdings change. That is a changed
fact, and `agent-loops` requires it recorded again. D2 keeps the reason from changing on every turn
boundary.

### D5 — the refusals name what the refused actor can do

The guard's **decision** does not change: same edges, same actors bound, same exceptions. Only the
sentences change.

**`_guard_reviewer_is_not_the_author`** (`task_transition_service.py:443-464`, both branches) is
reached by three audiences:

| audience | how | the assignee it judges |
|---|---|---|
| the operator | `PATCH …/tasks/{id}`, including the drawer's status menu | committed, or set by the same request |
| an agent | `update_task` over MCP; `PATCH /agent-actions/tasks/{id}` over HTTP | committed over MCP; **over HTTP also set by the same request** (R2, F366) |
| a flow or a dispatch | `enter_selected_task` writes the reviewer, then transitions as `operator()` (`scheduler.py:816-828`) | **staged by this call**, then discarded by the rollback (F334) |

**The sentence must be true in all three**, and the guard cannot tell a staged value from a
committed one. SQLAlchemy's attribute history is cleared by any autoflush between the assignment
and the guard. So the sentence describes the move, not the row. It follows this shape: *"Cannot move
task T to 'under_review' held by 'dev': 'dev' is the agent recorded as completing it, and a task
under review is held by its reviewer, so the move would make its author its reviewer."* That is true
whether `dev` was already there or was being written in. It does not say *"is assigned to"*. **R2**
changed R1's *"with 'dev' holding it"* to *"held by 'dev'"*: the first reads as a statement about the
row now, which is F334's defect again. The second names the state the move would produce.
**REV:** *"move task T to 'under_review' held by 'dev'"* still parses as *"task T, held by dev"*.
The shape is now *"Cannot move task T to 'under_review' with 'dev' as its holder: …"*, which
attaches the holder to the move.

**Then the remedy, chosen by `actor.is_operator`.** The flow's staging arrives as `operator()`
(F47), and its sentence lands in the queue entry's `waiting_reason` and `abandoned_reason`, which
the operator reads. So the operator wording serves both. The guard only ever judges a `completed`
task, because `under_review` is entered from `completed` alone (`task_transitions.py:134-137`). So
Land it is always the right remedy **here**.
- **Operator:** *Land it, on the task, to review it yourself. To have another agent review it, one
  API request can name that agent as the assignee and send the task to review.* The second half is
  the one-request form `task-lifecycle-governance` already guarantees (*"Naming a reviewer in the
  same request succeeds"*).
  - **R2** removed *"it releases the hold and approves it"*: the approval gate can refuse (D2).
  - **R2** also says *"API"* outright. The drawer renders Assignee read-only
    (`TaskDetailDrawer.tsx:380-395`), so an unqualified *"in the same request"* reads as a control
    in the app, which is F353's defect.
- **Agent:** *None of your tools changes who holds a task, so this is not yours to fix. Leave it
  `completed`. The operator can land it, or a flow or the operator can staff a reviewer who is not
  its author.*

**REV replaced both remedies.**
- **The operator's second half produced a wedge.** The PATCH writes the assignee and the transition
  (`tasks.py:1266-1339`), and it queues no turn. Review turns are queued only by the dispatch
  (`agent_trigger.py:1502`), the divergence (`run_divergence.py:266, 467`) and the flow
  (`scheduler.py:2863, 3193`). In a flow, the next firing finds the task `under_review` held by a
  non-author with no turn and surfaces F154's *"Nothing will move it on its own"*
  (`scheduler.py:1370-1393`). That is the 63 named-reviewer-idle events LoopEngine recorded. The
  request that gets another agent to review is the dispatch. The operator's remedy is now: *Land
  it, on the task, to review it yourself, or dispatch another agent's review turn (POST
  /agent/trigger with review_task_id).* The dispatch refuses a task with no evidence naming a
  commit (`agent_trigger.py:1446-1448`), but the guard judges only `completed` tasks. A flow puts
  those under review only after its arm required that evidence (`scheduler.py:1538-1548`), and an
  operator PATCH on a task without it meets the dispatch's own refusal, which names what is missing.
  So the remedy is never a silent dead end. That is a code read, and the round that restarts this
  change drives it.
- **The agent's claim about its tools was false.** MCP `create_task` takes an `assignee`
  (`mcp_server.py:248-251`). `send_message` with a `task_id` binds a run, and binding sets the
  assignee of an unassigned task (`run_task_binding.py:475-476`). An HTTP agent reaches this refusal
  through the route that accepts `assignee` (`agent_actions.py:276-289`), and test 4.4 goes through
  that very route. What is true is narrower: no task tool the agent is offered **reassigns** a task
  that already has a holder. The agent's remedy is now: *None of the task tools you are offered
  reassigns a task. Leave it completed; the operator can land it or dispatch a reviewer who is not
  its author.*
- **Both fit 500 at the worst ids** (`%TEMP%\f352rev\len2.py`, measured with the REV wording at a
  64-character id and a 32-character name, and at LoopEngine's 17 and 9):

  | branch | worst | typical |
  |---|---|---|
  | author, operator | 395 | 302 |
  | author, agent | 454 | 361 |
  | evidence, operator | 449 | 356 |
  | evidence, agent (text above, before REV trimmed *"so this is not yours to fix"*) | 508 | 415 |

  The agent branch never reaches `error_summary`, because only the flow's and the dispatch's
  staging reach the queue entry, and both arrive as `operator()`. It is trimmed anyway, so no
  sentence depends on that. The evidence branch's explanation is shortened to *"'dev' recorded
  evidence for it and no agent is recorded as completing it, so it counts as the author, and an
  author's verdict is refused."* An agent-loops scenario pins the operator branch under 500 at the
  worst ids.

**R2: the agent sentence no longer says "no agent can".** R1's wording was *"No agent can change
who holds a task"*, and F366 makes that false.
- `PATCH /agent-actions/tasks/{id}` takes the operator's `TaskUpdate` (`agent_actions.py:276-289`),
  and `update_task_for_actor` writes `assignee` for any actor (`tasks.py:1266-1275`).
- An agent over HTTP can therefore send `{assignee: <another agent>, status: under_review}` and
  succeed. Worse, a refusal telling it that it cannot would sit one request away from being
  disproved.
- What **is** true is the offered surface. The MCP `update_task` carries `status` and `notes`
  (`mcp_server.py:307`). The HTTP rendering lists the fields the adapter sends,
  `fields=("status", "notes")` (`agents.py:1003-1008`), and every agent without MCP is shown that
  rendering (`launchability.py:392-400`).

*"None of your tools changes who holds a task"* is a claim about the surface. It makes no claim
about the route, and it does not advertise the route's hole. Whether the route should take
`assignee` at all is F366's own loop. **Neither this sentence nor the operator's names the hole to
an agent.**

The trailing *"Left as is, the task is claimable by nobody and 'dev' counts as busy…"* is dropped.
It describes the state the refused move *would* have produced. Read after a refusal, it describes a
state that does not exist, and the agents on LoopEngine quoted it as though it did.

`actor` becomes read, **for wording only**. The docstring's paragraph *"`actor` is deliberately
unread"* is amended to say so. The rule still binds every actor.

**`review_dispatch_refusal`** (`agent_trigger.py:497-514`) is reached only by the operator's
`POST /agent/trigger` with `review_task_id`, an API-only route (F336).
- The author branch drops *"or clear the assignee to review it yourself"*. Clearing the assignee is
  unrelated to that refusal, which is about the *reviewer* being the completer. It gains
  `own_review_remedy(task)`, the helper D2's rung 3 uses.
- The evidence-author branch gains the same helper, for consistency.

**R2: the dispatch refusal's remedy depends on the status, as rung 3's does.** R1 gave both
branches *"Land it"* unconditionally, and that is wrong for one reachable state. (**R3:** the
helper returns the status sentence only; the freeing clause is rung 3's, D2.)
`review_dispatch_refusal` admits `WITH_REVIEWER_LOOP_TASK_STATUSES` as well as the reviewable ones
(`agent_trigger.py:480`). Its D9 check refuses only a *different* holder (`:487-491`). So the author
branch is reached for an `under_review` task that nobody holds, or that is held by the very reviewer
being dispatched. `land` refuses `under_review` with a 409 (`tasks.py:1519-1530`). One helper for
both surfaces is also what keeps them from drifting into two accounts of the same remedy.

**REV: two more sentences carry F353's defect, and two comments D5 makes false.**
- The D9 refusal, *"Reassign the task if 'x' should take it over"*, appears twice:
  `review_dispatch_refusal` (`agent_trigger.py:494`) and the dispatch path (`:840`). Its reader is
  the operator, who has no reassign control. `under_review`'s only edges are `approved`,
  `revision_needed` and `rejected` (`task_transitions.py:138-142`), so no move hands a review to
  another agent. A PATCH of the assignee alone queues no turn, which is the wedge above. The
  sentence becomes *"… Let the review in flight finish, or decide it yourself"*, followed by
  `own_review_remedy`'s `under_review` sentence.
- `agent_trigger.py:847-849` says the guard's sentence *"already names both remedies and the cost
  of doing nothing"*, and `task_transition_service.py:405-406` says the operator *"clear[s] or
  reassign[s] `assignee` first, which is what the refusal asks for"*. Both join task 4.6.

### D6 — the board line shows the whole reason on hover

Add `title={loop.stall_reason}` to the truncated `<p>` (`LoopsIndexTab.tsx:237-244`). It is one
attribute and calls nothing new, so it is compatible with any running `:8000` by construction. It is
committed only if it was driven in Chromium against the served bundle (`day-window.md`, *A day that
builds*). Otherwise it is left for the night, and the Python half stands without it.

*Rejected:* expanding the line, or a drawer for the loop. That redesigns a surface, which is not this
change's business.

## What this change does not do

- **It does not change who is free** (proposal, *OPERATOR QUESTION*). D1 keeps the predicate byte
  for byte.
- **It does not add an assignee control or a review-dispatch control to the app** (F336 names the
  second as a product decision). The sentences stop naming controls that do not exist, and name the
  one that does.
- **It does not edit `hub/hub/mcp_server.py`.** Nothing here needs it, and on a build day it may not
  be edited (F354).
- **It does not close F366.** `PATCH /agent-actions/tasks/{id}` (`agent_actions.py:276-289`)
  takes the operator's `TaskUpdate`, `assignee` included, and `update_task_for_actor` writes it for
  any actor (`tasks.py:1266-1275`). MCP `update_task` carries no assignee (`mcp_server.py:307`). R2
  re-read this and it holds: an agent over HTTP can reassign any task. That is code read, not
  driven. `agent-capability-plane` forbids that surface difference. **R2 decided that R1's sentence
  was not true enough to say**, and D5 now describes the offered surface instead. Closing the
  route is F366's own loop. It is not folded in here: refusing `assignee` to agents is a change to
  what an agent may do, with its own argument, and it would edit none of this change's lines.

## Risks

- **The sentence is long.** It is still one line on the board, and D6 gives the whole of it on
  hover. It leads with names, and the event feed renders it whole.
- **Holdings churn records.** A flow whose agents keep picking up and finishing live work changes
  the reason often. Each change is recorded, which is the rule. That is bounded by one per task per
  firing, the pre-F154 rate, and only while the task is actually unstaffable.
- **Test churn from D3.** There are 14 call sites. They are mechanical. A missed one fails loudly
  only where it reaches a named exclusion (R2), so 2.1 lists them.
- **The first `@validates` in `hub/hub` (R2).** A validator that silently shortens a value is a
  pattern a reader may not expect. The docstring on the constant says what it does and why, and
  test 2.9 exercises it through the real route.

## Round 2 — what the code disagreed with

R2 re-derived each decision against the code at `e8ea490`, and did not re-read R1's argument. It
answered R1's four open checks and found five disagreements. Each is fixed above, in the proposal,
in the deltas and in `tasks.md`.

**R1's four checks, answered.**
1. *Can an existing `error_summary` already pass 500?* **Yes, computed:** `_wedged_review_reason`
   at a 206-character title and a 32-character reviewer. Dispatch refusals carrying git stderr are
   unbounded by construction. None is observed yet (`:8000` max 276). This is F367, and the fit
   moved to the model (D2).
2. *Does D5's "no agent can change who holds a task" survive F366?* **No.** The agent sentence now
   describes the offered surface (D5).
3. *Does D4's JSON path work on real SQLite?* **Yes, run:** it compiles to `JSON_EXTRACT` and
   selects per task (D4).
4. *D3's call sites?* Two runtime callers and 14 test call sites, as R1 counted. The "fails loudly"
   claim was overstated (D3).

**Five disagreements.**
1. **The `completed` remedy promised an approval that `land` refuses** whenever evidence naming a
   commit awaits judgment. At rung 3, such evidence exists by construction (D2).
2. **R1's example would not have named LoopEngine's whole roster** once its remedy was made
   honest: 514 characters. The wording was tightened and the budget measured (D2).
3. **The divergence overlay erased "recorded no verdict"** on the operator-completed branch,
   failing R1's own scenario (D3).
4. **The dispatch refusal named Land it for an `under_review` task**, which `land` refuses with a
   409. It now shares rung 3's status-aware helper (D5).
5. **The guard's sample sentence, *"with 'dev' holding it"*, still read as a claim about the row**
   (D5). Also, *"in the same request"* read as an app control, so it now says API.

**Also found:** `_agents_that_are_free` has three callers, not two, and rung 3 can meet an empty
roster (D1).

## Round 3 — what the code disagreed with

R3 re-derived the change against the code at `fb469e2`, starting from where R2 had not traced.
Each disagreement is in the argument or in how a test is built, not in a conclusion. Every
decision's outcome stands, and two of R2's claims become true that were not.

**Checked, and it holds.**
- **`@validates` is the right home, and it reaches every write** (D2). This was measured on a
  constructor keyword and on an assignment, and on the real `JobRun`. No Core statement writes
  `job_runs`. A `TypeDecorator` was weighed and rejected, because it would leave the in-memory value
  unfitted. The helper must pass `None` through.
- **No import cycle.** `agent_trigger.py:126` already imports four names from `scheduler` at module
  level, and `scheduler` imports nothing from `agent_trigger`. Adding `own_review_remedy` to that
  import changes nothing about the graph.
- **The guard only ever judges a `completed` task.** `apply_transition` refuses an illegal edge
  (`task_transition_service.py:593`) before any guard runs (`:595-606`), and `under_review` is
  entered from `completed` alone (`task_transitions.py:134-137`). So D5's operator remedy, Land it,
  never meets a status where `land` answers 409.
- **No UI string, no `openspec/specs` text and no doc quotes either sentence.** `eventSummary.ts:79-80`
  renders `reason` without reading it. The existing tests assert fragments that D2's and D5's
  wording keep: `could not staff this step`, `review it yourself`, `is the one that completed this
  task` and `has worked on this task`. 4.6 lists them.

**Six disagreements.**
1. **Land it does not always refuse at rung 3** (D2). R2's *"until someone decides the evidence"*
   is false for three cases:
   - a flow the operator created with `work_needs_evidence: false`, which merges its branch tip;
   - the mixed case, where accepted evidence would already merge;
   - a project whose merge situation does not resolve.

   The remedy's wording was chosen to be true either way, and it is. The argument now says
   "usually".
2. **One clause can overflow both budgets** (D2). Task ids are caller-chosen up to 64 characters on
   both the operator's and the agents' create routes. Three of them under a 32-character name make
   a 300-character clause, and R2's rule would then name nobody. A holds clause now names fewer
   tasks before its agent is counted, at 219 characters with two tasks and 135 with one. This is not
   observed on `:8000`.
3. **"The pool is empty by construction at rung 3"** (D1/D2) is false, because the author can be
   free. What is true is that every pool member is excluded, and the four clauses still cover every
   record.
4. **The freeing clause does not belong to the dispatch refusal** (D2/D5). The helper returns the
   status sentence only, and rung 3 appends the clause.
5. **Three comments state the old remedy in the present tense:**
   - `api/v1/tasks.py:1259-1268`: *"the remedy it names -- assign a different reviewer"*, and
     *"The guard immediately below names two remedies -- reassign, or 'clear the assignee…'"*;
   - `schemas/tasks.py:124-127`;
   - the F78 test's docstring, `test_reviewer_is_not_the_author.py:377-378`.

   After D5 each would be a false statement about the guard. F78's behaviour, clearing the
   assignee and then entering review, stays and stays tested. Only its description of the guard
   moves. They are added to 4.6.
6. **Task 2.6 cannot reach rung 3 as written unless its holdings sit outside the flow.**
   `_loop_candidates` walks `Task.loop_id == loop.id` (`scheduler.py:708-709`). An `in_progress`
   task in the queue whose assignee is idle is resumed as a selection (`:1421-1466`), so the firing
   claims work and never stalls. An `under_review` task in the queue held by a non-author with no
   turn joins `wedged_reviews` with F154's own sentence (`:1392-1393`), and that sentence can be the
   one F64 promotes (`:1655`). LoopEngine's
   backlog had `loop_id` NULL, and 2.6 now says so.

## Round 4 — REV, the adversarial review (2026-09-14): stopped

REV was an Opus subagent, reading this change, DIRECTION.md 2026-09-14, the build row in
DECISIONS.md, `day-window.md` *A day that builds*, the six findings, and the cited code. Its verdict
was **SPLIT**, with **STOP** as the fallback if the window would not split on its own authority.
The window took the fallback: the change is stopped, specced and unbuilt, and the split goes to the
operator (proposal.md, top; `decisions_for_user`). What follows is what REV found. Every item marked
*fixed* is fixed in these files, and the round that restarts either half verifies them.

**Scope.**
1. **DIRECTION's stop clause covers this change.** It attaches to R1 finding the operator's
   question, not to the change containing it. O-3 listed the fix as *F352 + F353*.
2. **The rung-3 half presupposes option (e).** Its freeing clause is (e)'s remedy, and under (d)
   the sentence would name holdings that are not reasons. So the (d) change would MODIFY this
   change's new `agent-flows` requirement. The proposal's *"built for the sentence that option will
   need"* was false, and is removed.
3. **The separable half** is D4 and D5, with `own_review_remedy`, the model fit (2.5, 2.12) and
   2.13. F353 was re-observed on LoopEngine, so the build row covers it in its own right. F365 was
   measured on LoopEngine data but is not on O-3's list. F334 and F367 ride with it, one for
   editing the same sentence and the other because the new guard sentence depends on it.

**Truth in every reachable state.**
4. **The rung-3 prefix, *"nobody is free"*, was false** when the author holds nothing. It is now
   *"no reviewer is free"*, in D2 (*fixed*).
5. **`own_review_remedy` was undefined for `revision_needed` and `rejected`.** A live review run
   whose task the operator moves still reaches `resolve_reviewer` at its end. Decided: the
   divergence stops staffing a task that has left the review statuses (D2, task 2.14, *fixed in the
   text*; it changes behaviour, so the restarting round verifies it).
6. **Blocker for the built half: D5's operator remedy produced the wedge it explained.** The
   assignee-and-status PATCH queues no turn. The remedy now names the dispatch (D5, the
   `task-lifecycle-governance` delta, 4.1, 4.3, *fixed*).
7. **The agent sentence's "none of your tools changes who holds a task" was false** for
   `create_task` and for a bound `send_message` on an unassigned task. It is now *"none of the task
   tools you are offered reassigns a task"* (*fixed*).
8. **The guard sentence overflowed.** Today's evidence branch is 534 characters at the worst ids,
   and R2's shape was 583. It reaches `error_summary` through a terminal dispatch failure, so the
   fit would have cut the remedy. It is reworded to 395–449 characters on the operator branch, with
   a SHALL and task 2.13 (*fixed*).
9. **"Held by 'dev'" still read as a claim about the row.** It is now *"with 'dev' as its holder"*
   (*fixed*).
10. **Note: once per task has an edge in both directions.** A stall that cleared and returned with
    the same reason, with no other record for that task in between, is not recorded again. The
    docstring (`scheduler.py:1918-1919`) says a returned condition *"is news again"*. That was
    already untrue for a loop with one stuck task, whose newest record was its own. D4 does not make
    it worse, but it makes it uniform. **Left to the restarting round:** compare only records newer
    than the task's last transition, or amend the docstring. Not decided here, because it changes
    what `agent-loops` counts as one fact.
11. **Note:** 3.3 changes one task's reason only if the agent it frees is not the other task's
    author. The test fixture must keep that agent off both tasks' author sets.

**`@validates` on `JobRun`: acceptable.** REV confirmed by grep that no Core `update()`, `insert()`
or raw SQL writes `job_runs`. Both constructors (`scheduler.py:2562, 3163`) pass no
`error_summary`, and the eight ORM writes are as D2 lists them. It is the first `@validates`, not
the first custom column behaviour (`UTCDateTime`, `models.py:28`). The existing idiom, truncating at
the call site (`_safe_error_summary`, two copies), is what D2 generalises. Rows already stored
longer than 500 are not repaired, and none exists (max 276, observed). Test 2.12's mutation is
sound. Test 2.9 must read the length before the fit, from the event or `stall_reason`, or the
validator hides a broken bound. 2.13 says the same for the guard sentence.

**Also fixed:** 2.6's author holds a live task outside the loop, so mutation (b) can fail. 4.5 and
4.7 gained mutations. 4.6 gained two comments D5 makes false (`agent_trigger.py:847-849`,
`task_transition_service.py:405-406`). 4.9 is new, for the D9 refusal's *"Reassign the task"* at
`agent_trigger.py:494` and `:840`: the operator has no reassign control, and `under_review` has no
edge that hands a review over.

**Sampled line references held** (REV, code-read): `scheduler.py` 298, 816, 923, 1137,
1161-1168, 1298, 1550-1584, 1655, 1744-1748 and 1913-1941; `tasks.py` 1259-1275, 1473 and
1519-1545; `task_transition_service.py:443-464`; `agent_trigger.py:480-504`; `schemas/jobs.py:88`;
`models.py:1349`; the eight write sites; `run_divergence.py:430-446`; `mcp_server.py:307`;
`schemas/tasks.py:17, 72`.

## Round 5 — the re-derivation against (f), 2026-09-19

The round `F352-free`'s decision asked for, and the one the STOPPED note at the top of
`proposal.md` says has to happen before a line is implemented: *"rung-3's naming needs re-deriving
against (f), from scratch"*. Run interactively at the operator's instruction (*"Go do the round"*),
as a fresh comparison of the proposal against the code — not a re-reading of R1–R4.

**The decision to name the holdings survives. The case R1 built for it does not, and neither does
its remedy.**

### R5-0 — D1 as written reverts `4b59ee0`. This is the finding that matters most

D1 specifies the pool as `not a.holdings` over `Task.assignee` in `LIVE_STATUSES`, and asserts
*"No agent enters or leaves the pool because of this change"*. Both were true at R1. **Neither is
true now.** `_agents_that_are_free` reads `LIVE_STATUSES` only as the band and then filters by
reachability (`scheduler.py:1146-1150`), exactly as its docstring says (`:1089-1092`). An agent
holding three live tasks nothing will move is in the pool **today** and would be out of it under
D1's predicate.

So the change that exists to *describe* the staffing rule would, implemented literally, **undo the
rule** — and it would do so while every sentence around it still read correctly, which is the shape
of regression that survives review. It is caught here by comparing the decision against the code
rather than against R1's account of the code, which is what this round is for.

It cannot ship green: `test_the_loopengine_shape_staffs_its_review` asserts the pool is non-empty
in precisely the shape D1's predicate empties. But a round that only ran the suite would have
learned this as a mysterious red at implementation time, with the design still reading as correct.

D1 is amended in place with the corrected record shape.

### R5-1 — the incident in *Why* cannot happen any more, and a shipped test proves it

`hub/tests/test_a_task_nothing_will_move_holds_nobody.py::test_the_loopengine_shape_staffs_its_review`
stages exactly the shape `proposal.md`'s *Why* describes — a flow's completed task, its author
excluded, every other agent holding only a task assigned outside the loop — and asserts
`decision.selections == [(task.id, B, True)]` and **`decision.unstaffed == ()`**. The review is
staffed. Under (f) the `loop_id`-NULL holdings on `dev` and `dev_2` are reachable-free, so the pool
is not empty and rung 3 is never reached.

So the change's own motivating narrative — *"a flow stood still for most of a night … every firing
recorded the same `review_unstaffed` sentence"* — is a wedge **(f) has already fixed**. This does
not retire the change: rung 3 is still reachable whenever every non-excluded agent is running, held,
or holding *in-loop* work, and when it is reached the sentence still names nobody, which is F352
entire. But the *Why* must be re-grounded on that narrower circumstance instead of inheriting a
snapshot that no longer reproduces. **A change whose stated reason cannot recur is one a future
round will reopen.**

### R5-2 — three of the five findings *Why* names are already closed

Verified in the tree, not in the archive's prose:

- **F365 shipped.** `_review_unstaffed_already_stands` is scoped to this task's own newest record
  (`scheduler.py:2120-2153`), and its docstring credits `a-refusal-names-a-remedy-that-works` D3.
  `proposal.md` still argues for this under *What changes* as work to do.
- **F367 / the `error_summary` fit shipped.** `JOB_RUN_ERROR_SUMMARY_CHARS` and
  `fit_error_summary` are in `hub/hub/db/models.py:1336-1348`.
- **F353 and F334's remedy half** moved to the same sibling and archived 2026-09-16.

`tasks.md` §3 is already struck as MOVED. `proposal.md` was not swept with it, and still presents
all five as this change's work. **Only F352's visibility half remains**, and the file should say so
in one line rather than leave a reader to discover it.

### R5-3 — clause 3 must filter by reachability, and R1–R4 never said so

Under the rule this change was written against, "what this agent holds" and "why this agent cannot
review" were the same list, so D2 could say `"{name} holds {id} ({status})"` over live assigned
tasks and be right. Under (f) they are different lists: unavailability is
`loop_id in live or (task_id, assignee) in queued` (`scheduler.py:1146-1150`). Printing a holding
outside that set states a reason that (f) explicitly decided is not one. D2 amended.

### R5-4 — the sentence will contradict the roster, by design, and has to be unambiguous

`_agents_that_are_free`'s docstring (D5, `scheduler.py:1089-1092`) says the roster's active-task
count answers a different question **on purpose** and still counts every live task. Under (e) the
two agreed; under (f) they routinely differ, so *"dev holds 1 task"* here beside *"dev — 4 active"*
on the roster is two correct surfaces disagreeing. New under (f), unaddressed by R1–R4. D2 amended;
the roster is deliberately not changed to match.

### R5-5 — the freeing clause is (e)'s remedy, and the right one is named nowhere

REV already caught that *"frees its agent"* is false for an agent holding several tasks. The deeper
problem is that the clause is the whole remedy, and under (f) it is no longer the best one:

- **Archiving the loop frees every agent holding only its tasks, at once.** `live` excludes a loop
  with `archived_at` set (`scheduler.py:1126-1130`); `POST /jobs/{job_id}/archive` sets
  `loop.archived_at` (`api/v1/jobs.py:1190-1197`); the operator has the control
  (`JobsPage.tsx:42,49`). **This remedy is created by (f)** — under (e) a live assigned task held
  its agent whatever became of its loop.
- **It must name the other loop**, since archiving the stuck review's own loop stops the firing
  that needs staffing. Hence the loop attribution added to clause 3.
- **Pausing frees nobody** (`scheduler.py:1084-1085`, *"A paused loop still holds"*), and it is the
  control an operator reaches for first. Suggesting it would be a fresh F353 — committed by the
  change whose subject is F353's defect class. D2 now forbids it and requires a test.

### R5-6 — the OPERATOR QUESTION section is dead text and must go

`proposal.md:174-223` presents options (a)–(e) and *"Recommended: (d)"*. The decision was **reject
(d), take (f)** — an option the list does not contain. Leaving a recommendation for a rejected
option in the file is how a later round re-litigates a closed decision, which is the failure the
round log exists to prevent. Retire it to one paragraph naming (f) and pointing at the
`F352-free` row.

### R5-7 — citation drift, four places

- The rung-3 sentence is at `scheduler.py:1307-1314`, not `:1161-1168` as `proposal.md:68` and R4's
  sampled-references list both say. It has also gained D6's `waiting` clause since R1 quoted it, so
  the quoted text in *Why* is no longer what the code emits.
- `F352-free`'s decision cites the reachability predicate at `scheduler.py:1138`; that is now the
  `session.execute` line, and the predicate is `:1146-1150`.
- D2's *"`scheduler.py:1137-1159`"* for the pool walk is now `:1262-1285`.
- R4's sampled references were verified against the tree of 2026-09-14 and five of them have moved.
  **Re-verify the whole list at implementation time rather than trusting this round's four.**

### What R5 did not check

- No test was run. Nothing here was executed; every claim is a code read plus one shipped test's
  assertions read from source.
- The budget table (D2's character counts) was **not** recomputed for the longer clause 3 or the
  longer remedy. Both grow, the 500-character `error_summary` bound is real and now enforced at the
  model, so **the table is the first thing the implementation round must redo** — this round changed
  the strings without re-measuring them.
- Whether `task_agent_pairs_with_a_turn_queued`'s hop-budget arm can make a holding appear and
  disappear between two firings, which would make the sentence unstable across ticks in the way D2's
  ordering argument tries to avoid. Named here because it is reachable from (f) and nobody has
  looked.

## Round 6 — the adversarial review of R5, and what it cost, 2026-09-19

An independent adversarial review (Opus subagent, read-only), commissioned by the operator under
their standing rule that one runs before any `APPROVED` row. It was aimed explicitly at **R5**, on
the grounds that R5 was written by the same model in the same session and was the least
independently checked part of the change. Verdict: **DO NOT APPROVE**. Its four load-bearing
findings were re-verified against the code before being applied here; all four held.

**R5 re-derived D1 against one of the two changes that had landed on `_agents_that_are_free`, and
missed the twin.** That is the honest summary. The rest follows from it.

### R6-1 — the usage hold: a second silent revert, in the same expression R5-0 quotes

`_agents_that_are_free` builds `running` from two sources ORed together —
`select(Run.agent).where(... "running")` **`| await agents_held(...)`**, `scheduler.py:1114-1122`.
`agents_held` appears nowhere in this change's five files. D1's record therefore returns a
usage-held agent with `running=False` and no reachable holding, i.e. **to the pool**, reverting
`a-spent-allowance-holds-the-queue` D6 exactly as the original D1 reverted `4b59ee0`.

`hub/tests/test_a_held_agent_is_busy.py` did not exist at REV's tree (`82b58df`) and shipped in
`e1eca5b`, so R1–R4 could not have seen it. **Catching what landed since was R5's entire purpose,
and R5 had this expression on screen.** D1 amended: `held` is a field on the record.

### R6-2 — the change deleted a shipped SHALL and told the operator something false

`openspec/specs/agent-flows/spec.md` carries: where an agent was passed over because its queue is
held, the reason *"SHALL name the hold among the grounds, and SHALL NOT state that every agent is
running a turn, holding work or excluded."* Today's code honours it (`scheduler.py:1291-1312`, the
`roster_held` query and its `waiting` clause). D2's four clauses had no hold, so a held agent would
have read *"X is running a turn"* — false — and the hold would have been named nowhere.

D2 gains **clause 4**. The delta spec's clause list gains it too, with a paragraph saying it may
not be folded into "running".

Three shipped tests break and none was listed: `test_a_held_agent_is_busy.py:370-381`
(substring on the hold clause), `:384-390` (**`assert choice.reason == _TODAY`**, exact equality),
and the `error_summary` fit test. The same three pass `exclude={AUTHOR}` as a **set**, so D3's
`Mapping[str, str]` makes them raise `TypeError`. R3's claim that *"the existing tests assert
fragments that D2's wording keep"* is false against today's tree. Tasks added.

### R6-3 — the archive remedy is removed, and this is R6's main act

R5 added it as the remedy (f) created. It fails three ways, each disqualifying on its own for a
change whose subject is remedies that work: reachability is an **OR** so archiving frees nobody
held through the queued arm; the remaining rung-3 case is in-loop holdings, where the loop to
archive is the stuck one the delta forbids naming; and `POST /loops/{id}/archive` refuses a live
loop, so the printed loop id is not the identifier the working control takes.

Removing it also removes the loop id from clause 3 — R5 added that only to aim the archive — which
recovers 21 characters per holding. See R6-4.

**The lesson worth carrying: R5 went looking for something to add.** The re-derivation it was asked
for was subtractive, and the one decision it originated is the one that had to come out.

### R6-4 — the budget, which R5 explicitly declined to re-measure

R5 added a loop id per holding and 43 characters of remedy and left D2's table alone, saying so.
The review measured the flagship LoopEngine shape at **559** (`completed`) and **589**
(`under_review`) against the 500 bound — so the fit fired on the main case, not a corner, and
task 2.4's "drop the loop id first" then produced *"archiving the loop that holds them"* naming no
loop, violating this change's own delta.

R6 removes both additions, which restores the budget to roughly R5's starting point. **It is still
not re-measured, and task 2.4 still says to measure it first.** Clause 4 adds a per-agent string
that did not exist before; it is shorter than what came out, but "shorter than" is not a
measurement.

### R6-5 — group 2's fixtures were never re-derived

Task 2.6, the flagship test, stages four agents whose held tasks all have `loop_id` NULL (R3's own
fix). Under (f) those holdings are unreachable, so R5-3 forbids naming them **and** the firing
never reaches rung 3 at all — `test_a_task_nothing_will_move_holds_nobody.py:307-322` stages that
shape and asserts `decision.unstaffed == ()`. The test asserts three mutually exclusive things and
its mutations cannot fail. 2.9, 2.9b, 2.10 and 2.11 never say whether their holdings are reachable.
R5 announced *"every task in this group was rewritten"* for group 1 and gave group 2 two notes.
Fixed.

### R6-6 — a build-order hazard that would have fired unattended

`own_review_remedy` ships with a bare `assert task.status in ("completed", "under_review")`
(`scheduler.py:1916-1919`). The screen that keeps a diverged non-review task away from it is task
**2.14**, which has not shipped — `run_divergence.py` has no `under_review` guard and calls
`resolve_reviewer` at `:441-447`. So task 2.3, which makes rung 3 call the helper, turns an
operator's mid-run status move into an unhandled `AssertionError` inside the scheduler. 2.14 is now
ordered before 2.3 with the constraint stated.

### R6-7 — twenty-two drifted citations

The review re-checked every citation that is a build instruction or a load-bearing argument and
found 22 stale, including six of the twelve `test_reviewer_ladder.py` call-site lines (and a
thirteenth site uncounted), all three `test_a_held_agent_is_busy.py` sites missing entirely, and
R5's own two new citations. Corrected in `tasks.md` where they are instructions. **R5's advice to
re-verify the rest at implementation time was right and is repeated here**: this file's line
numbers have now been wrong at three consecutive rounds.

### What R6 did not do

- **Ran no tests.** Every claim is a code read. "These three tests go red" is derived from reading
  their assertions, not observed.
- **Did not re-measure the budget** (R6-4). Task 2.4 owns it.
- **Did not re-derive `test-guide.md`**, which still reads as if the operator question were open.
  Task added; the file is otherwise untouched since R4.
- **Did not open** `task_transition_service.py`, `agent_trigger.py`, `requirement_gate.py` or
  `turn_scheduler.py` — the review grepped them and did not read them either, and D5's content
  moved to the archived sibling, taken on trust by both rounds.
- **Left open** R5's own unexamined question: whether `task_agent_pairs_with_a_turn_queued`'s
  hop-budget arm makes a holding flicker between firings. R6-3 shows that same OR already causes
  trouble, which raises rather than lowers the priority of looking.

## Round 6, measured — the budget table R5 and R6 both deferred, 2026-09-19

Task 2.4 said "do this first" twice and neither round did it. Done now, from the **real** strings
(`own_review_remedy`, `scheduler.py:1921-1923`) rather than reconstructed ones, under R6's
five-clause set with the loop id and the archive remedy removed.

**Components**

| piece | chars |
|---|---|
| prefix `could not staff this step: no reviewer is free. ` | 48 |
| remedy, `completed` | 44 |
| remedy, `under_review` | 74 |
| reject clause (R6-8 form, leading space + capital) | 70 |
| held clause, 5-character name (**R6's new clause 4**) | 55 |
| one holding, 17-character task id, `(pending)` | 27 |

**Totals**

| shape | `completed` | `under_review` |
|---|---|---|
| LoopEngine: 4 agents, 5 named holdings, 17-char ids | **410** | **440** |
| the same plus one usage-held agent | 467 | 497 |
| 3 agents (1 held, 1 excluded), one holding each | 307 | 337 |
| 5 agents | 399 | 429 |
| 6 agents | 445 | 475 |
| **7 agents** | 491 | **521 — over** |
| **8 agents** | **537 — over** | 567 — over |
| LoopEngine shape, 29-char task ids | — | **500 — exactly at the bound** |
| LoopEngine shape, 45-char task ids | — | 580 — over |

**What this settles.**

- **R6's removals bought about 150 characters.** The review measured R5's version of the flagship
  shape at 559/589; it is now 410/440. The fit no longer fires on the main case, which was R6-4's
  whole complaint.
- **The fit still has to exist and still has to be right.** It fires at **seven agents** on an
  `under_review` task, and the `under_review` remedy is 30 characters more than the `completed`
  one, so the two statuses cross the bound at different roster sizes. A project with eight agents
  is not exotic.
- **Caller-chosen ids are the sharper edge**, exactly as R3 said: at the LoopEngine shape, 29-char
  ids land *precisely* on 500. R3's "name at least one agent" floor is therefore load-bearing and
  must keep its test.
- **Clause 4 costs 55 characters for a 5-character name** and is unavoidable — it is a shipped
  SHALL. It is the single most expensive per-agent clause, so a project with several held agents
  reaches the fit sooner than the table's one-held rows suggest. Not measured: every agent held at
  once, which is the shape a provider outage produces.

**Still not measured:** the tail string (`"; and N more agents are excluded, busy or unbound"`)
against a real fit, because the fit algorithm is not written yet. Task 2.4 keeps its instruction —
these numbers are the input to it, not a substitute for it.

### R6-8 — `.;`, found by concatenating the two halves for the first time

`own_review_remedy` returns a complete sentence ending in a period. Every round from R1 to R6 wrote
rung 3's addition as *"; rejecting held tasks…"*, so the joined string reads
`…to review it yourself.; rejecting held tasks…`. Five rounds specified the two halves separately
and none of them printed the result. Fixed: the clause is a new sentence — space, capital. The
helper is untouched, because `review_dispatch_refusal` shares it.

The test instruction now says to assert **the joined string**, which is the only reason this was
findable.

## Round 8 — a fresh verification of groups 2, 5 and 6, 2026-09-21

Independent, adversarial, at the operator's request after R5, R6 and R6-measured/R6-8 each found a
hidden regression. Compared groups 2, 5, 6 and D1 (as amended), D2, D3, D6 and the delta against the
tree at `7e2f663`, re-deriving rather than re-reading. There is no `## Round 7` in this file; "R7"
exists only as the 2026-09-19 annotation in `tasks.md` 1.2. The next number is therefore 8.

**What changed in the tree since 2026-09-19**, `git log --since=2026-09-19 -- hub/hub/scheduler.py
hub/hub/api/v1/jobs.py hub/hub/api/v1/agents.py`: `f663898` (group 1, this change), `831ac16`
(`a-loop-staffs-the-agent-it-names`: `_agents_a_loop_may_staff`, the busy guard and `decide_firing`
now draw a documentless loop's pool as empty — `resolve_reviewer` still reads the project-wide
roster, which is right, because only a flow reviews), and six `agents.py`-only commits (F185, F302,
dead-code annotations). None touches rung 3, the ladder or `own_review_remedy`. `4b59ee0`'s
reachability and `a-spent-allowance-holds-the-queue`'s hold are both intact in `_roster_availability`
(`scheduler.py:1102-1172`) and in the projection (`:1227-1234`), and group 1's pool walk
(`:1358-1374`) repeats the projection exactly.

**Checks run.** `openspec validate an-unstaffed-review-names-its-holders --strict`: valid, before and
after this round's edits. Regression guard `py -3.11 -m pytest hub/tests/test_a_held_agent_is_busy.py
hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q`: **57 passed** in 36.3 s (42 s wall),
before any edit. No product code was changed by this round.

### R8-1 — HIGH — R6's clause order silently reverts the shipped hold. Same class as R5-0 and R6-1

R6 placed the hold **after** the holdings clause: *"excluded, no runner, holds, HELD, running"*.
Today, `resolve_reviewer` names the hold whenever **any** held, bound, non-excluded agent exists,
**regardless of what it holds** — `roster_held = any(record.held and record.has_runner and
record.name not in exclude …)` (`scheduler.py:1394-1396`). Under R6's order an agent that is both
usage-held and holding one reachable task takes the holdings clause, and the hold is named
**nowhere** in the sentence. That breaks the shipped SHALL (`openspec/specs/agent-flows/spec.md:873-875`,
*"an agent was passed over because its queue is held … SHALL name the hold among the grounds"*),
reverts behaviour the code has today, and no shipped test would notice: the hold tests at
`test_a_held_agent_is_busy.py:370-404` stage held agents that hold nothing.

It is also a false remedy. The rejecting sentence would sit beside that agent's tasks, and rejecting
them frees nothing — the agent is still held (`not record.held` is its own term of the projection).
The delta's own *"that way SHALL have the stated effect for every agent the reason named"* forbids it.

D2's stated reason for the order (*"holds is the actionable one"*) is exactly what fails here: for a
held agent the holdings are **not** actionable. **Fixed:** the order is excluded, no runner, held,
booked, running (`tasks.md` 2.3 R8 block; delta renumbered, a precedence paragraph and a scenario
added); `tasks.md` 2.15 gains the held-and-booked case with R6's order as its mutation.

### R8-2 — MEDIUM — a SHALL in the delta with no task behind it; `holds` is the roster's word

D2's R5 paragraph decided the sentence and the roster disagree on purpose and that *"the remedy
sentence says the list is what something will still move"*; the delta carries it as a SHALL
(*"worded so that a reader is not told the two disagree about the same fact"*, `specs/agent-flows/spec.md`,
the paragraph after the reachability one). No task ever wrote that wording — 2.3's clause remained
`"{name} holds {id} ({status})"`, and the rejecting sentence says nothing of the kind. `holds` is
the word the delta itself gives the roster's question (*"what an agent holds"*), so printing a
subset under it is the contradiction. **Fixed** by the verb, not by a gloss: `"{name} is booked for
{id} ({status})"` — *something will bring this agent back to this task*, which is (f)'s definition.
Measured both: the verb costs 8 characters per booked agent; the cheapest gloss sentence cost 44
once and put LoopEngine-plus-one-hold at 536. The rejecting sentence becomes *"Rejecting booked
tasks that are no longer wanted can free their agents."*

### R8-3 — MEDIUM — the other join nobody concatenated

R6-8 found `.;` by concatenating the `completed` join. The `under_review` remedy is
`"decide it yourself: approve, …"`, **lowercase** (`scheduler.py:2020`); after the clauses' `". "`
it starts a sentence in lowercase. Every round measured and printed only the `completed` string.
**Fixed:** 2.3 capitalises the helper's first character at rung 3's join (the helper is shared, so
it is not changed); 2.8 asserts the exact string with `". Decide it yourself:"`, and its new
mutation (drop the capitalisation) fails only because the assertion is exact.

*Not fixed, outside this directory:* the shipped `review_dispatch_refusal` already prints
`"… Let the review in flight finish. decide it yourself: …"` for an `under_review` task
(`api/v1/agent_trigger.py:503, 848`). Worth a finding; it is the archived sibling's sentence.

### R8-4 — LOW/MEDIUM — the rejecting sentence was unconditional

With no booked agent — everyone else held, running or unbound, or a one-agent project — the sentence
still said *"Rejecting held tasks … can free their agents"*, a remedy with no agent it applies to.
**Fixed:** appended only when some record took the booked clause; delta and 2.17 carry it.

### R8-5 — MEDIUM — the fit can drop the hold, reverting the shipped SHALL by length

2.4 fits clauses in name order and counts the rest under *"excluded, busy or unbound"*. A held agent
late in name order on a large roster is counted, and the hold is then named nowhere — the shipped
SHALL again, reached through the budget rather than the clause list. **Fixed:** the tail reads
*"…excluded, busy, waiting for a usage limit or unbound"* when it counts a held agent (78 characters
at N=999; the fit reserves the actual tail length). Delta scenario and 2.9 (iv) added.

### R8-6 — HIGH (test integrity, F190's shape) — 2.6's REV mutation cannot fail under (f)

REV added *"the author also holds one live task outside the loop"* so that mutation (b) (holds before
excluded) could fail. Under (f) a task outside every loop with nothing queued is **unreachable**;
rung 3 prints nothing for it, so the author's clause reads the same in either order and (b) is a
no-op. R6 rewrote the non-author fixture and said the author's task *"stays as it is"* — it cannot.
**Fixed:** every holding in 2.6 (the author's included) lives in a second live loop the test never
fires (reachable, not walked, so R3's claim-instead-of-stall caveat cannot arise); 2.9, 2.9b and 2.7
say the same. 2.6 also now states what the route returns — **409**, with `detail` equal to the stall
row's `error_summary` (`scheduler.py:3114-3135`, `api/v1/jobs.py:1363-1367`) — and that the job's
agent must be the author, neither running nor held, or `_loop_flow_busy_reason`
(`scheduler.py:312-352`) refuses before `decide_firing` runs. The delta scenario *"A task nothing will
move is not named as a reason"* had no test in group 2; 2.6 gains one, with a mutation that ignores
`reachable`.

### R8-7 — HIGH — 2.14 as placed would disable divergence handling for all ordinary work

*"At the same screen as `blocked`"* (`run_divergence.py:753-754`) is a screen every run passes. A
status screen there returns `None` for every work run whose task is `assigned` or `in_progress` —
the normal divergence case. **Fixed:** the screen goes inside the review branch (`:769-773`), before
`_answer_failed_review`. Its test asserted *"no `review_unstaffed` is recorded"*, which cannot fail:
divergence never emits `review_unstaffed` (only a firing does, `scheduler.py:3053`); it emits
`run_diverged` (`run_divergence.py:835-842`). Rewritten with a free agent, so the mutation restaffs
and fails **before** 2.3 lands — which is what makes the "2.14 before 2.3" order buildable.

*What the raise would do:* `evaluate_run_end` is awaited bare after the run row commits
(`api/v1/agent_trigger.py:2420, 3006`) and in `run_reconciliation.py:126`'s loop at Hub start. An
`AssertionError` from `own_review_remedy` would skip the F43 handover at run end and, at start,
abort the remaining evaluations and the `schedule_or_defer` after them.

### R8-8 — MEDIUM (F190's shape) — 2.10 cannot fail once 2.4 exists

Its reason must exceed 500, and 2.4 makes every rung-3 reason ≤ 500, so raw and fitted are equal and
the mutation is a no-op. The comparison it guards already shipped (`scheduler.py:975`, not `:923`)
and nothing tests it. **Rewritten** as a direct test of `_stall_run_to_increment` with a 600-character
reason.

### R8-9 — LOW — citations and a missed call site, again

2.1's list omitted `test_a_task_nothing_will_move_holds_nobody.py:684` — group 1's own 1.4 test,
which passes a set and reaches rung 3, so it raises `TypeError` under a `Mapping`. It is the fourth
consecutive round at which the list was incomplete. Also: `test_a_flow_names_what_it_cannot_staff.py`
`:472, :482` (not `:471, :478`), `decide_firing`'s exclusion at `:1808-1843`, `models.py:1367-1379`
and `:1413`. 2.1 now records the grep count: 21 call sites.

### R8-10 — LOW — 2.3 still carried the pre-REV prefix

`could not staff this step: nobody is free.` — the prefix REV replaced as false. D2 and
R6-measured's table use `no reviewer is free.`; the build instruction never got it. Fixed.

### R8-11 — MEDIUM — 6.3 drives a remedy R6 removed

6.3 still told the drive to archive the holding loop because *"the second is the remedy the sentence
now prints"* — R6-3 removed it and the delta forbids it. Its other R5 check was self-defeating (an
unreachable-only holder in the pool is staffed, so no rung-3 reason exists to not-name it). Two
bullets drive D5's refusals, which archived with the sibling. **Fixed:** replaced with a drive of the
rejecting remedy the sentence does print, and of the unreachable holder being staffed.

### R8-12 — FLAG — group 5 ships a UI bundle to the operator's live app

5.1 edits `hub/ui/src/components/spec/LoopsIndexTab.tsx` (the stall `<p>`, `:237-244`, unchanged), so
5.2's refresh changes `hub/hub/static/ui`, which the operator's `:8000` serves from this checkout on
their next reload. The committed bundle is current with `hub/ui/src` (stamp `src_commit 46dd58e`,
built 2026-09-13; last `hub/ui/src` commit `1731522`, 2026-09-13), so tonight's rebuild would carry
only the attribute. The `title` calls nothing new. It is the operator's call whether a night may
commit a bundle; 5.4's gate is otherwise sound. 5.1's test now names the existing test file and a
mutation that sets `title` to the stripped text.

### R8-13 — budget, re-measured with the R8 strings (scratchpad `r8len2.py`)

| piece | characters |
|---|---|
| prefix `could not staff this step: no reviewer is free. ` | 48 |
| `". "` + remedy, `completed` / `under_review` | 46 / 76 |
| rejecting sentence (conditional) | 72 |
| tail / hold-aware tail, at N=999 | 51 / 78 |
| clause budget with the hold-aware tail, `completed` / `under_review` | 256 / 226 |
| widest booked clause (32-char name, 64-char ids, `revision_needed`), 3 / 2 / 1 named | 311 / 227 / 143 |
| held clause / excluded clause, 32-char name | 83 / 75 |

| shape (17-char ids) | `completed` | `under_review` |
|---|---|---|
| LoopEngine (author + 3 booked, 5 named holdings) | 432 | 462 |
| the same plus one usage-held agent | 488 | **518 — over** |
| five / six agents, one holding each | 408 / 458 | 438 / 488 |
| seven agents | **508 — over** | **538 — over** |

R3's floor holds: the widest one-task clause (143) fits inside the smallest clause budget (226), so at
least one agent is always named. The fit fires one roster size earlier than R6-measured's table.

### Routes, and what they return when the function they call raises

- `POST /jobs/{id}/run` on a rung-3 stall: **409**, `detail` = the stall row's fitted reason, on the
  first firing and on the counted ones. If `decide_firing` **raises**, `_do_fire_job` marks the run
  row `failed` with the exception text (`scheduler.py:3314-3337`) and returns `False`; the route then
  re-derives through `_loop_in_flight_decision`, which calls `decide_firing` again, raises again, and
  the route's own `except` writes a **second** failed row and answers **500** (`api/v1/jobs.py:1407-1414`).
  A scheduled firing gets only the first failed row and a log line. Nothing in groups 2/5/6 can raise
  there once 2.14 is in: `decide_firing` reaches the ladder only for `completed` and the F70
  `under_review` row, both accepted by `own_review_remedy`, and `exclude[...]` is indexed only for
  names in it.
- `GET /jobs/{id}/history`: bounded by the shipped `@validates`; the remaining failure mode is a
  silently cut remedy, which 2.9's second mutation now catches.
- The divergence path has no route; see R8-7 for what a raise there does.

### What R8 did not do

- Implemented nothing and ran no test beyond the guard. Every test described above is specified, not
  observed; each must still be watched failing under its mutation.
- Did not re-derive `test-guide.md` (task 6.5 owns it; it still describes option (e)).
- Did not audit D1's R2 paragraph citations (`:298`, `:1298`, `:1137`) — stale, but group 1 is built
  and tasks 1.2's R7 note already records the correct callers.
- Did not drive anything. No Hub was started or called; `:8000` and `:8010` were not touched.

## Round 9 — a scoped verification of R8-1 to R8-5, 2026-09-22

Named by `spec-queue/DIRECTION.md` `## 2026-09-22` item 1: R8-1..R8-5 and the `tasks.md` / delta text
they changed, against today's tree, re-derived. R8-6 onward, `is booked for` (settled) and group 5's
bundle rule (settled) were out of scope and not reopened. Run by the day window (Opus); no
`APPROVED` row is written here.

**What moved since `7e2f663`.** `git log 7e2f663..HEAD -- hub/ src/`: `d5d605c` (F223, `get_job`'s
`source` key, `api/v1/jobs.py` only), `a5e5a49` (`mcp_server.py`), `45d769f`, `b630252` (tests and
`conftest.py`), `542418e` (`templates/__init__.py`). None touches `scheduler.py`'s ladder,
`own_review_remedy`, `run_divergence.py` or `agent_trigger.py`. Every line R8 cites for these five
fixes still reads as cited: `roster_held` at `scheduler.py:1394-1396`, the helper's lowercase
return at `:2020`, its callers at `agent_trigger.py:503, 511, 521, 848`, the shipped SHALL at
`openspec/specs/agent-flows/spec.md:874`, the three hold tests at `test_a_held_agent_is_busy.py:370-404`.

**Checks run.** Regression guard `py -3.11 -m pytest hub/tests/test_a_held_agent_is_busy.py
hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q`: **57 passed** before any edit (37.5 s)
and 57 passed after. `openspec validate … --strict`: valid before and after. R8-13's strings
re-measured from scratch: prefix 48, `". "` + remedy 46 / 76 (capitalised), REJECT 72, tails 51 / 77
(N=12) / 78 (N=999), held clause at a 32-character name 83, widest one-task booked clause 143 — all
equal to R8's. No product code changed.

### What was re-derived and holds

- **R8-1, the precedence.** Excluded, no runner, held, booked, running mirrors `roster_held`'s own
  three conditions exactly (`held and has_runner and name not in exclude`): an excluded or unbound
  held agent takes the earlier clause and was never counted as a hold today either, so the order
  reproduces today's hold-naming rather than approximating it. At rung 3 every record takes some
  clause — a free record that is not excluded would have returned `available`, or `deferred` if
  taken — so the five clauses partition the roster. Checked the analogous case R8's argument
  suggests, a *running* agent that is also booked (booked precedes running): not a defect.
  `is booked for` stays true, rejecting the booked tasks does free it once its turn ends, which
  *"can free"* claims, and no shipped SHALL requires the running ground to be named.
- **R8-3.** The lowercase return and all four shipped callers confirmed; `capitalize_first` at rung
  3's join is the right place, as the helper is shared.
- **R8-4.** REJECT conditional on a booked clause: consistent with the delta both ways — an
  excluded, unbound or held agent that also holds reachable tasks takes the earlier clause, and
  rejecting its tasks would not free it, so the delta's *"that way SHALL have the stated effect for
  every agent the reason named"* is what the condition implements. 2.17's mutation fails as stated.
- **R8-5.** The hold-aware tail's condition (*"any agent left to the tail took the held clause"*)
  uses the same precedence, so an excluded held author does not trigger it, matching today. The
  fit must compute the tail for the specific remainder at each step, which *"reserve the tail's
  actual length"* says; the first clause still fits at 226.

### R9-1 — LOW — R8's empty-roster join starts a sentence in lowercase, and has no test

2.3's R8 block wrote the empty roster as `PREFIX + "the project has no agent on its roster. " + …`.
The prefix ends in `". "`, so this is R8-3's defect on the one join R8 itself added — and the delta
scenario *"An empty roster is stated"* has had no task at any round. **Fixed:** capital `T` in 2.3;
new task **2.18** asserts the whole string with `==`, with the lowercase as its mutation.

### R9-2 — LOW — 2.15 asked for the wrong clause by number

2.15 still said the held agent is *"named by clause 4 and not by clause 5"* — R6's numbering. R8
renumbered the delta (held 3, booked 4, running 5) and added a parenthetical saying the names
matter, but left the sentence, which read literally now asks for the *booked* clause. **Fixed:**
reworded by name.

### R9-3 — LOW — 2.1's grep count is 25, not 24, and was at `7e2f663` too

R8 wrote *"21 call sites … plus three docstring/comment hits … A different count means the tree
moved."* The grep also returns `main.py:245` (`_git_last_commit_iso(…, exclude=("__tests__",))`,
2026-08-14), so an implementer following it would conclude the tree moved when it has not. The 21
`resolve_reviewer` call sites are correct. **Fixed:** noted in 2.1.

### R9-4 — FILED — R8-3's shipped half was never filed

R8-3 called the lowercase `"… finish. decide it yourself: …"` in `review_dispatch_refusal` *"worth a
finding"*; no finding existed. **Filed as F407** (D, source-read, not yet seen live).

### R9-5 — LOW, NOT FIXED — REJECT can refer to booked tasks the fitted sentence never names

R8-4 decides REJECT *before* fitting, which is what lets 2.4 reserve its 72 characters. With the fit
in name order, a roster whose early names are held, excluded or unbound can fill the clause budget
before any booked agent is reached — e.g. `under_review`, four held agents with five-character names
(56 each) ahead of three booked ones: three held clauses fit in 226, and the sentence ends
*"; and 4 more agents are excluded, busy, waiting for a usage limit or unbound. Decide it yourself: …
Rejecting booked tasks that are no longer wanted can free their agents."* Nothing in it is
*booked*. It is not false — the remedy has the stated effect, and the delta's SHALLs are met — but
it points at tasks the reader cannot see in the sentence. Only reachable past 500 characters.

Two cures, neither applied, because each changes the fit's arithmetic, and R5, R6 and R6-measured
each shipped a fix that a later round found had broken something: (a) drop REJECT when no booked
clause survives the fit (the reservation stays, so the sentence only shortens — but it hides a true
remedy); (b) one tail rule naming the grounds actually present among the counted agents, in clause
order, which would subsume R3's tail and R8-5's hold-aware one (costs ~10 characters at the
longest; the 143-character first clause still fits). **Recommendation: (b), or accept as is — the
DECIDE session's call.** Not blocking groups 2, 5 or 6.

### Result

R8-1 to R8-5 hold against today's tree: the five fixes are correct and nothing since `7e2f663`
touches them. Three LOW text defects fixed (R9-1..R9-3), one shipped-code finding filed (F407), one
LOW design question left open for the DECIDE session (R9-5).
