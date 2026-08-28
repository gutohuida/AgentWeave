# 2026-08-27 — fix and drive

Branch `autonomous/2026-08-27-fix-and-drive`, cut from `bbe00a7`. Stop at 2026-08-28T08:00+01:00.

Purpose, in the operator's words on arming: *"fix whatever you can fix and run a e2e-loop to find
errors and fix them."* Finding defects is the goal, not a side effect.

---

## Iteration 1 — BASELINE: every finding gets a status, and the open severity-A list

**2026-08-27T22:07+01:00 · commit `f8e0cf0` · queue item `BASELINE` → done**

### Reconciliation on arrival

STATE claimed the branch had to be cut. It was already cut and pushed — `9cf10dd`
("chore(autonomous): branch cut from bbe00a7, run armed for 08:00"), tree clean, local and
`origin/autonomous/2026-08-27-fix-and-drive` at the same sha. Nothing to reconcile beyond that;
`next_action`'s first clause was already satisfied, so this iteration did its second clause.

### What was done

`scripts/drive/FINDINGS.md` had 72 findings and no status field. Each `## F<n>` now carries a
`**Status:**` line immediately under its header, and a new `## Open severity-A baseline,
2026-08-27` section sits at the top of the file.

### Method, and the trap in it

The obvious method — `git log --all --grep="F<n>"` — is wrong here, and I only found out by
reading the commits it returned. F1, F2, F3, F4 and F6 are also finding numbers in a **different**
series: the operator-UX findings in `.claude/autonomous/2026-08-16-operator-ux-findings.md`, worked
through as `Q4-spec-ux-fixes` phases and referenced again by the `N6` review commits. An
unrestricted grep attributes `027506c "Q4-spec-ux-fixes: IMPLEMENT phase 1 (F2)"` to this file's
F2, which is about a UTC clock wearing a local label. It is not the same F2.

The fix: for each finding, find the commit that *first wrote its section* —

```
git log --all --reverse -S "## F<n> " -- scripts/drive/FINDINGS.md
```

— and only consider mentions at or after that commit's timestamp. That removes every false
attribution above, because the other series predates this file's sections. 3,211 commits scanned;
the per-finding mention lists are in `.claude/autonomous/scratch/mentions.txt` and the birth
commits in `births.json`.

Eleven findings could not be settled from commit subjects alone and were decided by reading their
own prose plus the fixing commit's body: F14, F15, F20, F26, F35, F37, F47, F61, F62, F66, and F3.
Two of those changed the answer I would otherwise have written:

- **F14** looked fixed — `7fcd172` names it. Its body says what actually shipped: a *derived*
  `awaiting_answer_reason` that reports the wait without moving the task's status. The task-state
  half is untouched, which is exactly why STATE lists F14's fix shape as an open operator decision
  blocking F60's parked half. Recorded as **partially fixed**, not fixed.
- **F35** looked fixed — `29ab883` shipped a refusal naming the field, its shape and an example.
  `78459e4` then **reverted** it on the operator's call, preferring the declared schema, and
  removed the machinery rather than leaving unreachable safeguard code behind ("a safeguard nobody
  can reach is worse than none, because it is counted"). Recorded as closed by decision, not by
  repair.

F60's guard was traced to its actual origin rather than assumed: `git log -S` on the docstring puts
`_asker_is_gone` in `033ec4c` (2026-08-10), sixteen days **before** F60 was filed. So the guard
STATE says is "already shipped" is not a response to the finding at all — it predates it.

### The baseline

Severity A still open — three, and only one wholly open:

| Finding | State |
|---|---|
| **F12** | open, no commit anywhere references it. Queued as `F12-SPEC`/`F12-IMPL`. |
| **F52** | partially fixed `68459ea`; the rest does not reproduce, central inference disproved by `0cda570`, last axis eliminated live by `57eb92b`. Out of scope. |
| **F60** | partially fixed `033ec4c` (which predates it); remaining half parked for F14, an operator decision. |

`F9 (A-)` is not a defect. The other seventeen A's are fixed with a named commit:
F1 F5 F10 F23 F27 F41 F43 F45 F49 F51 F54 F56 F57 F58 F70 F71 F72.

Open below A: F3 F15 F20 F21 F42 F47 F61 F62 F65 F66 F68, plus F53's second half and F14's
task-state half.

### Verification

Not a code change, so there is no test to watch fail. What was checked instead:

- **72 status lines for 72 headers**, asserted in the script that wrote them (it also asserts no
  finding number in the status table is unused).
- **Every sha cited resolves to a commit.** All 52 shas appearing in the new status lines and the
  baseline table were run through `git cat-file -t`; all 52 answer `commit`. Seventeen other
  7-hex-looking strings elsewhere in the file do *not* resolve — they are commits in throwaway test
  repositories and one `api_equivalent_usd_micros` value — and none of them are in the lines this
  iteration added.
- The one claim that would be embarrassing to get wrong — that the `Q4-spec-ux-fixes` F-numbers are
  a different series — was confirmed by reading `da31ca6`'s body, which describes "all six operator
  UX findings" and names F2's root cause as `SpecFrame.tsx`'s theme override. Not this file's F2.

### Honest limit on what this measures

Every "fixed" here means *a commit that says it fixed it exists and its body describes the right
defect*. It does **not** mean the fix was re-driven live tonight. This repository's dominant
failure mode is a change that passes its tests and cannot fire in production (F41 is literally a
finding about that, and F38's fix was dead for a week), so the baseline is a bookkeeping floor, not
a proof of correctness. The section says so in the file.

**Next:** `E2E-1` — the operator's headline ask. Full-surface `e2e-loop` sweep against a fresh
throwaway project outside this repository, fixing what it finds, every fix carrying a test watched
to fail.

---

## Iteration 2 — E2E-1, first pass: three defects found, three fixed, three filed

**2026-08-27T22:47+01:00 · commits `03855bb`, `a33db58`, `d1561f5` · queue item `E2E-1` → in progress**

### Reconciliation on arrival

STATE, branch and `git log` agreed: `2643663` at the tip, tree clean, local and origin level.
Nothing to reconcile.

### Seams driven this iteration — so the next firing does not repeat them

| Matrix row | Verdict |
|---|---|
| 1 Projects | driven — `POST /projects/open`, settings read, `main_branch` auto-detected as `master` correctly |
| 2 Runners | driven — 2 seeded, a third pinned to `claude-haiku-4-5-20251001` created, launchability probed (all three runnable) |
| 3 Agents | driven — `author`/`builder`/`reviewer` registered and bound to runner + charter |
| 4 Charters | partly — the 9 starters confirmed seeded; create/edit/delete **not reached** |
| 5 Conversations | driven — three real turns, transcripts read |
| 7 Tasks | partly — materialisation and the transition machine's refusals; the full board **not reached** |
| 9 Spec flow | **driven end to end** — create → content → close → propose → approve → tasks materialise |
| 10 Evidence | driven — recorded, footprinted, duplicate-checked; **drift not reached** |
| 17 Integration | **not reached** — blocked behind F76 |
| 6, 8, 11–16, 18, 19 | **not reached** |

Rows 11–19 are the next firing's work. Nothing here was marked covered on the strength of a 200.

### What was found

Three defects, all fixed, each with a test watched to fail. Three more filed and deliberately not
fixed.

**F73 — `ui_stale` is a false positive on any Windows checkout, and no rebuild clears it.**
Found in Step 3, before driving a single screen, which is the only reason the UI rows would have
meant anything. `/health` said the bundle was stale on a tree where `git diff` against the stamp's
own commit was empty. `ui_source_fingerprint` hashed raw working-tree bytes, and with
`core.autocrlf=true` nine tracked files stood CRLF on disk against LF in the index. Demonstrated
by flipping one file's line endings — a change `git diff` reports as nothing — and watching the
fingerprint move and move back. **The bundle was not stale**: rebuilt and diffed against a
snapshot, every byte identical, only the stamp moved. Now hashes `git hash-object` output, so both
sides agree on git's own normalisation.

**F74 (severity A) — evidence from a task-bound run does not carry the task.** The headline find.
`builder` was triggered with `task_id`, did the work, and called `record_evidence` without
repeating the task. The row landed with `task_id` NULL; `commit_for_task_review` selects on exactly
that column; the task's own review turn refused with *"has no recorded evidence, so there is no
commit to review"* — which is false, and points the operator at the agent instead of at the gap.
Three places in the Hub's own database named the task, including the branch the Hub itself created
(`agentweave/task/task-a0409448ee8e`). `record()` now falls back to `runs.task_id`.

**F75 — a reviewer's confirmation is refused as a duplicate of the author's claim.** Caused by
F74's fix, and worth stating plainly: `duplicate_of` returns None when any part of its key is
missing, so the check written for F7 **had never once fired in production for agent evidence**.
Filling `task_id` switched it on, and the first thing it did was silence the reviewer. Actor is now
part of the key.

**F76 (severity A) — filed, not fixed. A hand-dispatched review turn dead-ends.** The reviewer did
good work — re-ran the suite, wrote a comparison script, checked negative amounts and rounding
boundaries, concluded APPROVED — and then found four closed doors: it could not move the task
(assigned to its author), could not accept evidence (no grant), could not record its own (F75), and
could not message the operator (F77). Every one of those refusals is individually excellent; the
`under_review` one is the best-written refusal in the product. The gap is that the composition has
no exit. Diagnosed precisely: `scheduler.py:767-780` staffs the task before a flow's review turn,
and `POST /agent/trigger` with `review_task_id` does not — two dispatch paths for one operation,
one of which leaves the reviewer unable to finish. **Not fixed because the repair shape is a
product decision** (staff it / refuse up front / give reviewers a verdict channel); added to
`decisions_for_user` rather than guessed.

**F77 — an agent has no way to address the operator.** `send_message` to `Operator` 404s.
`ask_user` blocks and is for questions. Recorded, not decided — it touches the deliberately-retired
question-detection backstop.

### What held, which matters as much

- **F71's fix works.** The footprint captured the agent's real commit on `agentweave/task/…` with
  `reachable_from_main: false` — not the operator's checkout.
- **F10's fix works.** The reviewer got its own detached checkout at `.agentweave/reviews/reviewer`.
- **The spec lifecycle gates hold and explain themselves.** Proposing from an unclosed exploration:
  *"exploration has not been closed; the operator decides when it is complete"*. A no-op rigor
  change, an illegal transition, and a review with no evidence all refused with the remedy stated.
- **Task materialisation is correct**, and the document's `reviewer` field is resolved at review
  time rather than stored — checked in `review_turn.resolve_declared_reviewer`, not assumed.

### Friction worth recording

- Spec routes live at `/projects/{id}/project/documents` — a doubled path segment that cost two
  calls and an OpenAPI dump to find.
- `POST /documents/propose` reports a **content** refusal as `200` with a `blocking` list and a
  **lifecycle** refusal as `409`. Same refused operation, two shapes; a client checking the status
  code believes the first one worked.
- The agent burned three identical `ToolSearch` calls before `read_spec_document` resolved.

### Verification

Not just the suites. `03855bb` was proven by rebuild-and-diff; `a33db58` and `d1561f5` were proven
**live against a restarted Hub** — fresh evidence carried the task with the agent again naming
none, and the review turn that returned 409 returned 200. 135 evidence/review tests pass; ruff,
black and mypy clean.

### State left behind

`proj-46b602c1f3cb` (`aw-e2e1` at `C:\Users\huida\Documents\aw-e2e1`) is **kept on purpose** —
an approved document, a materialised task, two evidence rows spanning the fix, and a task worktree
carrying real commits. Rebuilding that is the expensive part of the next sweep. No jobs and no
loops exist in any project; confirmed by API, not assumed.

**Next:** continue `E2E-1` at the unreached rows — loops/jobs, questions, permissions, dependencies,
worktrees, accounting, resilience. Do not re-drive rows 1, 2, 3, 5, 9.


---

## Iteration 3 — 2026-08-27T23:40:53+01:00

`E2E-1` continued. Branch `autonomous/2026-08-27-fix-and-drive`, matching `STATE.json` at entry
(`232dffd`). Hub started on this branch's code at `127.0.0.1:8011` against `%TEMP%/f52hub/f52.db`,
confirmed by the project list rather than `/health`, and restarted onto the fixed code three times
so every fix below was proven against a live Hub and not only in pytest.

### Rows driven this iteration

| Row | Outcome |
|---|---|
| **8 Dependencies** | **driven end to end** — clean, no defects |
| **17 Integration** | **driven end to end** — the agent's work reached `master` |
| **13 Questions** | **driven** — ask/park/answer and ask/decline; the timeout path not driven |

Rows 1, 2, 3, 5, 9, 10 were driven in iteration 2 and were not repeated. Still unreached: 6 inbound
queue (seen in passing, not driven), 11 jobs/loops, 12 flows, 14 permissions, 15 checkpoints,
16 worktrees, 18 accounting, 19 resilience.

### Row 8 — dependencies. Nothing wrong with it.

An `A -> B -> C` chain, driven through every branch of `dependency_gate`: the gate refuses
`-> in_progress` and not `-> assigned`, so a whole wave can be routed ahead of time; an unmet
prerequisite and a `rejected` one are reported separately with different remedies; a cycle is
refused naming both tasks; a self-dependency is refused; the board reports `gated`,
`gated_on_rejected` and `running_on_regressed` correctly, including the last one *after* regressing
an approved prerequisite under a running dependent. Reopening a rejected middle task and
re-approving it releases the chain. Removing a dependency clears the gate, and removing it twice is
a stated 404 rather than a silent success.

**Recorded as clean deliberately.** The sweep exists to find defects and this row produced none —
that is a result, not a failure to look.

### Row 17 — integration. The whole loop closed, for the first time in this sweep.

`task-a0409448ee8e`, carrying the previous iteration's real agent commits, went
`completed -> under_review -> approved`, and the Hub merged `70474c2` into `master` as `d6735a3`,
carrying the earlier snapshot `9b2d781` along with it. Verified in the repository rather than from
the API: `calc.py` and `test_calc.py` are on `master` with the agent's `Decimal`/`ROUND_HALF_UP`
implementation in them. `integration-preview` refused correctly beforehand — *"no accepted evidence
names a commit"* — until the evidence was accepted, then reported `will_merge: true` with the target
named. This is the first end-to-end pass from specification document through requirement, task,
agent turn, evidence, operator acceptance, approval and merge.

### Three defects, all fixed, each with a test watched to fail

**F78 (A) — the operator cannot clear a task's assignee, and the API reports that they did.**
`f1d0c6f`. Found *while* driving row 17: F70's guard refused the review move and named two remedies,
*"Assign a different reviewer, or clear the assignee to review it yourself"*. Following the second
returned `200 OK` with the author still in the response body, and the same refusal on the next call.
`TaskUpdate.assignee` is `Optional[str] = None` and the service read it as
`if body.assignee is not None`, so `null` and *omitted* were the same value. `escalation_agent`,
eleven lines below it in the same schema, already solves this with `model_fields_set` and says in a
comment that clearing it *"is a thing the operator must be able to do"*. The pattern was in the
file, unapplied to the field a hard guard depends on. The undocumented escape that did work —
`{"assignee": ""}` — wrote an **empty string** into the column, which survives only because every
reader tests Python truthiness, while four `Task.assignee.isnot(None)` queries would have counted it
as a live holder. One of them is `_agents_that_are_free`, which is the capacity leak F70 exists for.

**F79 (A) — a task the operator has decided about still takes new runs.** `eba8620`. The headline
find, and it arrived unlooked-for: seconds after the merge above, a trigger came back with *"an
older conversation's queued input is being delivered first (run run-acbd6c2138b1)"* — a run I had
not started, on the task I had just approved. An entry queued at 21:38 while the task was
`completed` sat through the operator approving it at 21:55 and the merge, and was delivered at
22:07 bound to approved, merged work — writing `assignee = builder` back onto the card F78's fix had
just let me clear. **The two findings compose into undoing each other.** Reproduced with no queue
and no restart: triggering on an approved task was accepted and the board then read `approved` /
`assignee: author` / `assignee_status: running`.

The rule is not missing — `TERMINAL_FOR_BINDING`'s own docstring states it — it was enforced on
conversations and on neither of the two other things that can name a task. Fixed with two
dispositions, both of which `resolve_bound_task` already uses for a task *deleted* since a
delegation was sent: the operator naming a decided task now is refused `409` at the route; a queued
entry whose task has since been decided is released beside the conversations, because refusing at
delivery would make `turn_scheduler` abandon the operator's message after three attempts over a
decision about something else. `review_task_id` untouched — inspecting decided work is what a
review is for.

**F80 (B) — `asker_waiting` is computed on one question route and hardcoded on the other four.**
`0afa915`. `GET /questions` computes it; create, detail, answer and decline returned the ORM row, so
Pydantic filled it from the schema default `True` — not stale but constant, and the constant means
*someone is still waiting*. `answer_question` computes the fact for itself twenty lines above the
return and then contradicts it.

### The method note worth keeping

**F79's refusal was first written where it could never fire.** It went into `resolve_bound_task`'s
explicit-`task_id` branch, where it read naturally and passed a unit test. `POST /agent/trigger`
does not run a turn — it queues an entry — so the task always arrives there as a *delegation*, and
`trigger_agent_directly`'s only caller never passes `task_id` at all. Only the live drive caught it:
the trigger still returned `200`. The refusal moved to the route, and its tests were rewritten over
HTTP for exactly that reason.

That is the third instance in two iterations. Iteration 2's carry-forward predicted this shape — *"a
guard that is present, tested, and unreachable"* — and this one was authored and caught inside a
single sitting. **The passing pytest is not the evidence; the live call is.**

F80's fix made the same class of mistake in the other direction: applied mechanically to all four
`return question` statements, it also hit `ask_question_for_actor`, a shared helper whose caller
reads `conversation_id` off the row it returns. The suite caught that one.

### Verification

- F78: 3 tests, 2 watched to fail; both mutation directions checked.
- F79: 7 tests, 4 watched to fail; every guard mutation-checked individually — dropping the
  `state == "queued"` filter, also clearing `review_task_id`, and widening the band to include
  `under_review` each fail a named test.
- F80: 5 tests, 3 watched to fail; hardcoding the field `False` instead fails the two guard tests,
  so the fix cannot have merely inverted the constant.
- Suites: 1049, then 1223, then 1625 passed across the task/binding/trigger/scheduler/review/agent
  selection, plus 430 on the combined F78/F79/F80 surface and 102 question tests. ruff, black and
  mypy clean.
- **Live**, against a Hub restarted on the fixed code each time: `assignee: null` clears and a
  priority-only PATCH leaves the holder alone; the trigger on an approved task returns `409` while
  the same call on an `under_review` task returns `200` and starts a run; queueing an entry against
  a task and then approving it leaves the entry with `task_id: None`; the list and detail routes now
  agree on `asker_waiting`.

### State left behind

`proj-46b602c1f3cb` keeps everything worth keeping: a document, an approved and **merged** task, a
second task (`task-72457167c198`, `calc.discount`) completed through a real `ask_user` round trip
whose answer visibly shaped the code, the `DEP-A/B/C` chain in assorted states, accepted evidence,
and one answered and one declined question. No job and no loop exists in either project — confirmed
by the API, not assumed. Tree clean, three commits pushed.

**Next:** row 14 permissions, row 11 jobs/loops (disable in the same iteration), row 6 inbound
queue, row 12 flows.

---

## Iteration 4 — 2026-08-27 23:46 → 2026-08-28 01:00 (+01:00)

**Rows 14 and 11 driven. Six defects found, six fixed — three of them severity A, and one of the
three was found by accident while proving another.** Every fix carries tests that were watched to
fail, every guard was mutation-checked individually, and every one was proven against a Hub
restarted on the fixed code.

| Row | Outcome |
|---|---|
| **14 Permissions** | **driven end to end** — allow, deny, expire, dismiss, re-decide. One defect (C). |
| **11 Jobs & loops** | **driven end to end** — create, seed, arm, fire, claim, work, stop, disable. Five defects. |

Rows still unreached: 6 inbound queue, 12 flows, 15 checkpoints, 16 worktrees, 18 accounting,
19 resilience, and row 13's timeout half.

### Row 14 — permissions. It works, and the record of it does not.

A manual-posture run put a `Write` to the operator; approving it wrote the file, denying it did not,
and letting one expire produced *"no operator answered within 20s"* and an expired card the operator
can dismiss. Re-deciding a decided card is a stated `409`. All correct.

**F81 (C) — one refusal, two rows.** `f59e293`. Pressing Deny once left two identical
`permission_denied` events a second apart, same `tool_use_id`: `decide_permission_request` records
the operator's decision, and the run then reports the same decision back through
`record_permission_decision`, which exists for refusals the *harness* makes. Two warn rows for one
refusal reads exactly like an agent that tried twice. Fixed on the Hub rather than in the reporter —
the card is the join — because the reporter is the process that may import only stdlib and fastmcp,
and because F79 already paid for putting a guard where the intent is legible rather than where the
traffic arrives.

### Row 11 — jobs and loops. Five defects, three of them severity A.

The happy path does work: a loop fired on its cron, claimed its task, the agent worked it, and the
board's `agent_capacity` walked `next -> held -> working` correctly while the busy guard held off a
second firing for the six minutes the turn took. Nearly everything around that path was broken.

**F82 (B) — a loop reports the queue the same call just seeded.** `afb9884`. `POST /jobs` with
`initial_tasks` returned `"queue": {}, "current_tasks": []` for a loop that had a pending task in it
one call later. Two independent causes: the block was hand-assembled with literals, *and* it was
assembled above the loop that creates the tasks. `_batch_loop_summaries` is what every other route
answers this with — and `loops.py`'s own header says of a neighbouring field that every route gets
it "from the same query, so no second implementation can drift from this one." `create_job` was the
surface that sentence had not reached.

**F83 (A) — a loop created enabled with `initial_tasks` never reaches the scheduler.** `0757be5`.
This took the longest to see, because everything reported success. `enabled: true`, a `next_run`,
`enabled = 1` in the row — and no firing, ever. Bisected to one variable: the same loop *without*
`initial_tasks` registered fine.

APScheduler's job store is a separate synchronous engine on the same SQLite file, and `create_job`
handed the job over while its own session still held a transaction, so the store's insert failed
with `database is locked`. Then three layers of silence: `add_job` caught it and returned `False`,
`create_job` did not read the return, and the whole block sat in
`except Exception: pass  # Scheduler might not be initialized yet`. One helper now commits before
the handoff and logs a refusal instead of swallowing it.

**F84 (A) — an operator who stops a loop stops nothing.** `0757be5`. The headline find. I stopped a
loop the way the API offers, got `200` with `ending_state: "stopped"`, and watched it fire **twelve
more times over the next seventeen minutes**, once a minute, every one a real agent turn recorded
`completed`. A loop ends two ways and both must leave four facts; the scheduler set all four, the
operator's route set two, and the two it omitted were *when* it stopped and *the stopping*.
`hub/hub/loop_ending.py` now states an ending once.

Its quieter half: `stopped_at` was left NULL, so the two refusals that quote it both printed *"at an
unknown time"* about an ending the Hub had performed a minute earlier.

**F85 (A) — a loop stages a review it cannot start, wedges the task, and fails on it forever.**
`3e07726`. Found by watching the happy path continue. Firing two, on a task the agent had completed
without recording evidence:

```
history [('failed', '23:14:00'), ('completed', '23:07:00')]
error_summary: task ... has no recorded evidence, so there is no commit to review.
task afterwards: under_review, assignee: author     (it was completed a minute earlier)
```

The selection is staged before the turn is dispatched, so the status move and the reviewer
assignment are already committed when the trigger refuses. The task is then wedged in `under_review`
naming an agent that never ran — F70's shape, reached by a new route, which costs the project that
agent for every *other* task too — and the next firing repeats it. **The word "evidence" did not
appear in `scheduler.py` at all**: the ladder answered *who* reviews, and nothing answered *whether
there is anything to review*.

The walk now asks `commit_for_task_review`, the same function the trigger refuses with, and reports
an unreviewable task as `unstaffed` with the reason — which F64 already raised onto the loop card,
where a queued entry and a failed `JobRun` never appeared.

**F86 (B) — an unattended loop inherits "ask me first" from a conversation hours old.** `25ea74c`.
Not looked for: while waiting on F85's live proof, the probe loop fired and then did nothing for
eight minutes, opening permission cards and timing them out one at a time — `Edit`, `Bash`,
`PowerShell`, each *"no operator answered within 120s"* — and then recorded itself `completed`
having been refused everything it tried. My own interactive row-14 drive two hours earlier had set
`manual` on a builder conversation, and `inherit_runtime_overrides` carried it into a scheduled
firing. That function withholds exactly one posture, `bypassPermissions`, and its comment gives the
reason: reaching runs started by a peer or a job *"by a route the operator cannot see, is not what
choosing it meant."* Only the permissive extreme had been considered; the blocking one fails the
same test and is worse unattended.

### Two method notes worth keeping

**One test's premise was changed, deliberately, and it is the most consequential decision of the
iteration.** `test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` *required* the
firing to dispatch a doomed review, so the operator could see what was attempted. That is a
defensible position argued in the test's own docstring — and driving it priced it: a wedged task, an
agent lost from the pool, and a failure every minute. The test now asserts the stronger property
(nothing dispatched, nothing mutated) and records in its docstring why it changed. Four other tests
that failed were fixture gaps and now record evidence through a shared helper. **A failing existing
test is a claim to be adjudicated, not an obstacle to route around** — and the adjudication belongs
in the test file, where the next person meets it.

**The mutation check earned its keep twice, in opposite directions.** F81's empty-`tool_use_id`
guard passed every mutation at first: the test had not built the card the guard defends against, so
the guard was invisible and would have been deleted by the next reader as dead code. And F84's
scheduler handoff — clearing `job.enabled` without telling APScheduler — passed the entire
row-reading suite, because a row-level test cannot see a stale registration. That was the original
bug wearing a different coat, one layer out, and only a mutation found it.

### Verification

- F81: 4 tests, all four guards mutation-checked individually.
- F82: 2 tests; both the literal block and the wrong ordering fail the seeded test.
- F83: 6 tests asserting `session.in_transaction()` at handoff — the fact that decides whether the
  store can write, not "was the scheduler called", which it always was.
- F84: 8 tests across two files; four mutations, each failing a named test.
- F85: 5 new tests, 3 dispositions mutation-checked; 5 existing tests adjudicated.
- F86: 5 tests; both scoping mutations fail a named test.
- Suites: 587 passed across loop/job/firing/review/flow/board/claimability; 260 loop+job; 33
  agent-actions; 14 override-inheritance. Then the **whole Hub suite: 3399 passed, 84 skipped,
  1 xpassed, 0 failed** in 18m33s — up from 3349 at arming, the 50 being the tests iterations 2-4
  added. CLI suite 440 passed / 3 skipped. ruff, black and mypy clean over CI's own path lists.
  No UI or CLI source changed this iteration, so no bundle rebuild was needed.
- **Live**, against a Hub restarted on the fixed code each time: one `permission_denied` row per
  refusal; a seeded loop reporting `{"pending": 2}` on creation; `live-fix-seeded` present in
  `apscheduler_jobs` immediately; a stop returning `enabled: false` with a real `stopped_at` and an
  empty scheduler store; an evidence-less task left `completed` with the firing recorded `skipped`
  and repeated skips coalescing into `tick_count` rather than one row a minute; and two job
  conversations carrying `runtime_overrides: null` with no permission card raised at all.

### State left behind

`proj-46b602c1f3cb` gains seventeen jobs, **every one disabled** — confirmed by the API *and* by
reading `apscheduler_jobs`, which is empty. `task-1b7af6b595e6` is left wedged in `under_review`
from before F85's fix and is a useful specimen: the fix stops new rows arriving in that state but
does not retrospectively free this one, and the walk correctly reports it in-flight rather than
re-staffing it. Tree clean, five commits pushed.

**Next:** row 6 inbound queue, row 12 flows, row 13's timeout half.

## Iteration 5 — 2026-08-28 01:21 → 02:25 (+01:00)

**Rows 6, 12 and row 13's remaining half driven. One defect found and fixed — severity A, and it
lives in the reporting rather than in the mechanism.** Reconciliation on arrival: STATE, branch and
`git log` agreed at `2218cdf`, tree clean.

| Row | Outcome |
|---|---|
| **6 Inbound queue** | **driven end to end** — batching, delivery cap, ordering, withdraw, hop-budget hold + release + refusal, abandonment after three attempts. One defect (A), in what happens *after* an abandonment. |
| **12 Flows** | **driven, width included** — one firing staffed two independent tasks onto two agents at once. No defect. |
| **13 Questions (timeout half)** | **driven** — a blocking `ask_user` timed out, the task parked to `blocked` with its reason, and answering it released the task and resumed the same conversation. No defect. |

Rows still unreached: 15 checkpoints, 16 worktrees, 18 accounting, 19 resilience.

### Row 6 — the queue works. What it says when it gives up does not.

Everything in the mechanism held, and held well:

- **Batching and the cap.** With `turn_delivery_cap=2`, four entries queued behind a running turn
  were delivered two, then one — and the transcript proves the agent saw both of the first two in
  one prompt, in arrival order (*"The operator has queued two requests: 1. QUEUED-A… 2. QUEUED-B"*).
- **Withdraw.** A withdrawn entry was never delivered; withdrawing it twice, and withdrawing a
  delivered entry, are both a stated `409`.
- **Hop budget.** With `hop_budget=1`, a two-hop chain held at depth 2 and the status said
  `hop budget exhausted`. `release` re-based it to 0, recorded `released_from_depth: 2`, and the
  turn started. Releasing an entry that is *inside* the budget is a `409` that says so and points
  at the queue status instead.
- **Abandonment.** A leftover entry at one attempt reached `DELIVERY_ATTEMPT_LIMIT` over two more
  scheduling attempts and was abandoned with a `queue_entry_abandoned` warn event naming the cause.

**F87 (A) — a message the Hub gives up on disappears, and the record of it says nothing.**
`46458ae`. What the operator sees the second after the abandonment:

```
GET /queue/author/status  ->  {"waiting_count": 0, "waiting_reason": null, "delivery_attempts": 0}
```

Which is precisely what a *successful* delivery leaves behind. Three surfaces and all three silent:
the conversation (`_queued_entries_for` selects `state == "queued"`, and an abandoned entry is
`withdrawn`, so the message left the thread it was addressed to); the queue card (`useSSE`'s
handler says *"The queue card is where that shows"* — and `useQueuedEntries` fetches
`?state=queued`, so the invalidation that event triggers is the refetch that removes the row); and
the activity log, the only durable record, where `summaryForEvent` had no case and the default
branch reads `error/message/summary/title` while the payload's field is `reason` — so the row read
`queue_entry_abandoned` and nothing else.

The thread keeps it now: a third `delivery_state`, `abandoned`, rendered in place at the timestamp
it arrived, tagged **not delivered** with the reason and no controls. Keyed on `abandoned_reason`
rather than on the `withdrawn` state, because an operator's own withdrawal reaches that same state
and putting one of those back would re-show a message they chose to take away — tested both ways.

### Row 12 — width works, and the first measurement of it was wrong

The first flow ran three independent tasks strictly **serially**, one per firing, all to the job's
default agent — against `create_flow`'s own docstring, *"Each firing starts every task whose
prerequisites are met and for which an agent is available, so independent work runs in parallel."*

That looked exactly like this corpus's signature defect and it was not one. Calling `decide_firing`
directly against the live database rather than inferring from the board:

```
free []        running set()        selections []
```

`_agents_that_are_free` excludes an agent holding any task in `LIVE_STATUSES`, and all three agents
were holding leftovers from earlier iterations — including the deliberately wedged `under_review`
specimen. Width was bounded by available agents, which is the documented bound working. **The board
could not have told me that**; one direct call to the decision function could, and did, in one step.

Rejecting the two stale holdings and re-running gave `free ['builder', 'reviewer']` and then the
real answer, in one firing: `in_progress: 2`, two tasks, two agents, two `JobRun` rows sharing one
`fired_at` — design D13's shape exactly.

### Row 13 — the timeout half

`question_timeout_seconds = 60` on `builder`, a run bound to a task, one blocking `ask_user`, and
nobody answering. At 60s the tool gave up, the run ended `completed`, and:

```
task: blocked   blocked_reason: "Waiting on your answer: Should ROW13 use tabs or spaces?"
event: task_blocked
```

Answering it afterwards emitted `task_unblocked`, returned the task to `in_progress`, queued the
answer as an operator entry and resumed the *same* conversation. The whole round trip holds.

### The method note worth keeping

**When the board disagrees with the docstring, call the decision function, not the API again.**
Row 12 would have been filed as a severity-A width defect on the evidence the product surfaces
provide — three independent tasks, three idle-looking agents, four firings, one task each. The
board reports the *outcome* of `decide_firing`; only `decide_firing` reports its inputs. Six lines
of async probe against the live database turned a wrong finding into a correct "no defect, and here
is the bound that produced it".

### Verification

- F87: 3 Hub tests + 6 UI tests, each watched to fail. Four mutations, each failing a named test —
  including one that **passed** under mutation at first, because the withdraw control is a bare
  `close` icon and the test looked for text. That is F81's lesson again: a guard no test can see is
  a guard the next reader deletes. The assertion now keys on the button's `title`.
- Suites: whole Hub suite **3402 passed / 84 skipped / 1 xpassed / 0 failed in 18m28s (3399 at iteration 4, plus this iteration's three); CLI suite 440 passed / 3 skipped**; UI **1421 passed across 139 files** (1415 at arming,
  plus this iteration's six); `ruff`, `black` and `mypy` clean over CI's own path lists;
  `npm run lint` clean. `npm run build` + `refresh_ui_bundle.py`, bundle and stamp committed with
  the source.
- **Live**, against a Hub restarted on the fixed code: the entry the Hub dropped at 23:14 is back
  in `conv-d3d63affa16c`, `delivery_state: "abandoned"`, `hop_budget_exceeded: null`, with its
  reason — and the operator's own withdrawal from earlier the same iteration is still correctly
  absent from `conv-b9fc97d600f1`.

### State left behind

`proj-46b602c1f3cb` gains two more jobs (19 total), **every one disabled** — confirmed by the API
*and* by `apscheduler_jobs`, which is empty. `builder`'s `question_timeout_seconds` was set to 60
for row 13 and has been **restored to NULL**; leaving it would have timed out a real question in a
later drive. Two stale `in_progress` tasks (`task-0faf9e6f5222`, `task-467758bf4625`) were moved to
`rejected` to free their agents, which is why `free` is now non-empty. `task-1b7af6b595e6` is still
the deliberate wedged `under_review` specimen. Tree clean, two commits pushed.

**Next:** row 15 checkpoints, row 16 worktrees.

---

## Iteration 6 — 2026-08-28 02:22 → 03:30 (+01:00)

**E2E-1, rows 15 and 16. Three severity-A defects, all three fixed, all three proved live — and
all three of the same kind.** Every one was a mechanism the suite tested thoroughly against a state
the product never actually produces. That is not three coincidences; it is one blind spot with
three exits, and it is the headline of this iteration.

### F88 (A) — two grants the operator can confer, and neither had ever done anything

`a42f978`. Row 15 began ordinarily: a real turn on `author`, a real checkpoint
(`ckpt-d4ba5292443a`, probes passed), a real cutover to a successor that picked the work up and
carried on. Then the grants:

```
PATCH /agents/builder -> {"can_read_checkpoints": true, "can_recall": true}
builder, live turn:      recall("out-e3b591766336")
  -> 404 No recorded observation by that id is available to you.
```

`checkpoint_access` computes `capability ∩ visibility`, and `checkpoints.visibility` shipped
defaulting to `"private"` with **no caller anywhere passing anything else** and no route, tool or
control able to change one. The visibility side of that intersection has been closed for every
checkpoint that has ever existed, in every project. Both grants were conferrable and inert, and the
refusal is deliberately indistinguishable from "no such record", so nothing told the operator.

The repository had already diagnosed this exact shape once, about `can_accept_evidence`, and
written the sentence down above `GRANT_FIELDS`: *"a capability enforced everywhere and grantable
nowhere is a refusal of everyone."* Same sentence, one column over.

The fix follows the spec rather than inventing a policy — `conversation-checkpoint` says *"a
checkpoint MAY additionally restrict itself"*, which makes restriction the exception, not the birth
state. Default `project`; migration `0097` backfills, because every stored `private` is the absent
default rather than anybody's decision. Closed-by-default survives: both reader grants still are.

A second half surfaced while fixing the first. `can_read_checkpoints` still granted nothing on its
own, because no agent-facing tool returns a checkpoint — and the spec's own scenario requires that
state to exist (*"the checkpoint remains readable"*), the canonical context promised it in as many
words, and `submit_checkpoint_notes`' docstring tells an agent a reviewer reads its notes. So
`list_checkpoints(agent=None)` and `read_checkpoint(checkpoint_id)` now exist over the agent-actions
namespace, identity from the run's minted credential.

### F89 (A) — turning on automatic checkpointing killed the turn that triggered it

`7cecd71`. Continuing row 15 into automatic mode. `reviewer` on `automatic`/`tokens 5000`, asked to
say one word. It said it, the transcript recorded `Completed`, and four minutes later:

```
running runs: [('run-cabd138d5be1', 'reviewer', 'conv-738f939e6999')]
agents:       author idle | builder idle | reviewer running
events:       run_started ... context_warning ... context_warning(null)   <- nothing after
```

No `run_completed`, ever. `builder` wedged identically on first try, and *its* checkpoint came out
`unwritten` with `worker_invocation_id = None` — which is the thread. `_record` opens its own
session and swallows failures by design, so a `None` there means another connection could not
write. `checkpoint_trigger.consider` holds its read transaction across `run_worker`, a ~20s CLI
spawn, and SQLite gives no concurrency to a connection waiting behind one: every other writer times
out at 5s with `database is locked`, including the live turn's own finalisation.

`run_worker`'s docstring already stated the rule — *"the spawn does not hold a session open across a
call that can take minutes"* — and passing primitives is not enough if the caller's transaction is
open around the call. The fix is one `await db.commit()` before the spawn, and the probe renders its
prompt before committing so it cannot reopen one.

**This also corrected a wrong conclusion of mine.** Before the fix the conversation stayed open
after its checkpoint, and the obvious reading was that `automatic` can never cut over — `cut_over`
refuses a run in progress and the trigger fires mid-run. Wrong: generation takes ~20s, an ordinary
turn ends inside that window, and on the fixed code both conversations archived and handed to
successors with `origin: "handoff"`. The refusal was the wedge, not the design. What remains
unmeasured, and is therefore not claimed, is the turn that outlasts its own generation.

### F90 (A) — a turn held back by another agent's turn is never let go again

`a053553`. Row 16, design D8's *"a task's checkout takes one writing turn at a time"*. `builder`
holding a task, `reviewer` triggered on the same one: refused, correctly, and classified
**transient** so the entry waits rather than counting towards abandonment. Then builder finished:

```
t+100s  author idle | builder idle | reviewer idle
        GET /queue/reviewer/status -> {"waiting_count": 1, "waiting_reason": null,
                                       "delivery_attempts": 0}
```

An unrelated `PATCH /queue/settings`, writing the same four values back, delivered it instantly.
`turn_scheduler`'s comment on the transient branch says the entry *"stays queued, and the next tick
tries again"* — **there is no tick**, and the run-completion event reschedules only the agent whose
run it was, which by construction is not the parked one. Every terminal exit of a run now redrains
the project's queued agents, *instead of* scheduling its own — a re-drain is a strict superset,
since `schedule_agent` answers "queue is empty" for an agent with nothing waiting. The first
version did both and `test_a_pre_spawn_failure_schedules_the_agent` caught the double-schedule by
counting the calls, which is the sort of assertion worth having. Project-scoped on purpose: a run
ending frees whatever it held, and the task checkout is only today's instance of that.

### The pattern, which is the finding above the findings

Three defects, three suites that could not see them, and the same reason each time:

| | what the test does | what the product does |
|---|---|---|
| F88 | passes `visibility="project"` explicitly | stores `private`, always, everywhere |
| F89 | spawns with nothing else writing | spawns *because* a live turn is streaming |
| F90 | calls `schedule_agent` for the challenger by hand | never calls it |

F90's is the sharpest: the step the test performs on the product's behalf **is** the step the
product omits. When a test has to do something for the code to reach the state under test, that
"something" is the question — ask who does it in production before believing the green.

### Row 16, and one wrong finding avoided

Worktree listing, per-agent workspace, conflicts (a real one detected between `author`'s branch and
a task branch over `README.md`), the D8 refusal, and removal all hold. Rejecting
`task-294f3af9448b` removed its checkout, kept its branch, and dropped it from the listing.

The twelve task checkouts sitting on disk are **not** a leak: release fires at `approved`/`rejected`
and ten of the twelve belong to tasks that never reached either. Two `approved` ones had been
re-provisioned by later turns bound to them — which F79 has since made a `409`, so that path is
closed and only the pre-fix residue remains. I was one step from filing this, and the archaeology
said no.

### Verification

- F88: 7 Hub tests (5 unit + 2 route-level), watched to fail — the default under mutation, the
  access filter, the status filter, and the `agent` parameter, which **survived its first
  mutation** and needed the test strengthened to assert that an ungranted caller naming the owner
  still gets `[]`.
- F89: 1 Hub test, watched to fail `[True, False] != [False, False]`.
- F90: 1 Hub test, watched to fail with all five redrain calls removed.
- Migration `0097`: 2 tests including the guard, watched to fail; head assertions bumped in
  `test_migrations.py` and `test_project_persistence.py`.
- Suites: CLI **440 passed / 3 skipped**. `ruff`, `black`, `mypy` clean over CI's path lists.
  **No UI change this iteration**, so no bundle rebuild. Hub-suite result recorded below.
- Live, against a Hub restarted on each fix in turn: F88 — `builder` granted lists, reads and
  recalls `author`'s checkpoint, `reviewer` ungranted gets `[]` and a 404. F89 — both runs
  `run_completed`, both conversations archived, both successors opened. F90 — the instant `builder`
  went idle, `reviewer` went `running` and answered.

### State left behind

`proj-46b602c1f3cb`: 19 jobs and 17 loops, **every one disabled**, confirmed by the API and by
`apscheduler_jobs` being empty. `builder` and `reviewer` had `checkpoint_mode` set to `automatic`
for row 15 and are **back to NULL**; `builder`'s two grants are **back to false**. The project's
`checkpoint_runner_id` and `checkpoint_model` are now set to the cheap Haiku runner and left that
way deliberately — without them no checkpoint can be generated at all, which is what made every
loop creation return a `continuity_warning`. `task-294f3af9448b` (ROW16) is `rejected` and its
checkout gone. `task-1b7af6b595e6` is still the deliberate wedged specimen. All three agents idle.

**Next:** row 18 accounting, row 19 resilience.

---

## Iteration 7 — 2026-08-28 03:51 → 05:0x — rows 18 and 19, the last two

Iteration 6 wrote its log and its four fix commits and died before committing its state file; that
wrap-up is `eaff101`, carried forward unchanged. The branch was reconciled against `git log` first:
`c1acd1f` was the head, one commit ahead of what STATE.json's queue entry named.

**E2E-1's row list is now complete.** Rows 18 (accounting) and 19 (resilience) both drove, and both
produced defects. Five findings, five fixes, every one proved live against a restarted Hub.

### F91 (A) — restarting the Hub spent the operator's message

`643027b`. The sharpest of the five, and the one with the longest reach. Trigger a turn, kill the
Hub mid-run, restart:

```
02:54:45  builder -> run-41977e93fb94, entry-24d8b3025c2d delivered, attempts 0
02:55:06  restart -> run_interrupted, returned_entry_ids: [entry-24d8b3025c2d]
          GET /queue/builder/status
          -> "delivery failed 2 times; 1 attempt left"
```

**Two** attempts for one restart, against a limit of three. Then the entry sat `queued` with every
agent idle until an unrelated `PATCH /queue/settings` delivered it. Three restarts with a run in
flight and a message the operator typed is withdrawn with *"the Hub stopped retrying"*.

Only one attempt is legitimate. The second comes from `reconcile_interrupted_runs`, which re-drains
the agents it repairs — from inside `lifespan()`, which is to say **before the Hub has served a
single request**. In native mode the callback address is observed from a real connection, so there
is none yet, and `trigger_agent_directly` refuses with *"retry once the Hub has served at least one
request."* That refusal was classified terminal, and `schedule_agent` charges terminal refusals a
delivery attempt.

`TriggerAgentError.transient` is documented as asking *"does this refusal describe a condition that
clears on its own?"* The refusal's own last sentence is the answer. **The repository had already
written the sentence that names the defect, twice, about this exact field.**

Fixed in two halves because either alone is insufficient: the refusal is `transient` so nothing is
charged, and the re-drain is *deferred* — `bound_address.known()` is new, and `main.py`'s
address-observing middleware drains the parked agents on the first request the Hub serves, the
precise moment the postponed condition clears. Without the second half this is F90 again: a
transient refusal records nothing and waits for a tick that does not exist.

Live on the fix, identical experiment: **one** attempt, and the message ran fourteen seconds later
in `run-64f340ce6161` with no operator action where before it needed one.

### F93 (A) — a runner binary that is present but broken wedges its agent

`a38813e`. Row 19's *corrupt or withhold a runner binary*. `_execute_run` wraps its spawn in
`except FileNotFoundError` **and nothing else**. A missing binary is one way a spawn fails and not
the common one on Windows: a corrupt file raises `OSError`, a denied one `PermissionError`,
pywinpty's own failures neither. All of them escaped the coroutine.

Driven with a 31-byte text file named `claude.exe`, first on the Hub's `PATH` so `shutil.which`
finds it and launchability passes:

```
03:08:58  trigger author -> 200, "status": "running"
03:09:08  trigger author -> 200, "waiting_reason": "agent is already running"
03:09:33  RUN  running · pid None · ended_at None · error None
          agents [author running, ...]  ·  turn_usage rows: 0  ·  events: none at all
```

The row stayed `running` **with no pid**, forever. The trigger guard then refused that agent every
subsequent turn, and the exception went to asyncio's unretrieved-task handler where nothing reads
it. The operator's remedy for a broken runner was to bounce the whole product.

`except Exception` — the branch body was already correct for any cause — and `CancelledError` is a
`BaseException` in 3.8+, so real cancellation still propagates. Live on the fix: `failed` carrying
the OS's own message, an accounting outcome, `run_failed` broadcast, the entry retried to the cap
and abandoned with a stated reason, agent idle.

### F92 (B) — a reconciled run is billed to nobody, beside a total that claims completeness

`a38813e`. `usage-accounting`'s first requirement is *"exactly one accounting outcome for every
Hub-owned run after that run ends"*. Measured:

```
completed    73   missing 0
interrupted   3   missing 3     <- all of them, one after 13 minutes of streaming
aggregate: {"measured_turns": 72, "unavailable_turns": 0}
```

`unavailable_turns: 0` is not silence. It is a positive claim that nothing is unmeasured, made over
three turns that are. Two paths ended a run without recording one — reconciliation, and
`_execute_run`'s catch-all, the last of its five terminal sites without one. Both now record an
explicitly `unavailable` outcome; reconciliation recovers the runner from the agent's binding and
records `None` rather than guessing. Live after the fix: **9 unavailable turns**, visible.

### F94 (B) — kill an agent and the product says `exit 4294967295`, again

`18b3856`. Killing a running agent is otherwise handled well — `failed`, a *measured* accounting
outcome, the entry returned, a retry run that completed. What the operator was told:

```
GET /agents/reviewer/timeline -> "Run failed (exit 4294967295)"
```

That is verbatim the loop-8 finding `readable_exit_code` exists for, whose docstring says *"an
operator seeing it has no reason to connect it to the process they just killed"*. The fix shipped
into `_transport_failure_fields` and `_runtime_failure_fields` — **both Codex paths**. The pty path,
the default runner, passes the process's own number into `_broadcast_run_lifecycle`, and the
timeline summary is derived from that payload. `run.error` is `NULL` beside it, so a ten-digit
number was the whole explanation.

Rendering now happens **inside `_broadcast_run_lifecycle`** rather than at each caller, which is how
this path came to miss it. Live: `"Run failed (exit -1)"`, with `runs.exit_code` still raw per D3.

### F95 (A) — a project can be moved exactly until its first turn, and never again

`0266f22`. Row 19's *drive a project whose working directory has moved*. Detection is right:
`directory_state` flipped to `missing` in seconds and a trigger was refused with a typed error
naming the path. The repair was not:

```
POST /relocate -> 422 "project cannot be relocated while a run or worktree mutation is active"
```

**Nothing was active.** One run has ever existed in `aw-f52` and it is `completed`; its one agent is
idle. What blocked the move was `.agentweave/worktrees/builder`, left by that completed turn.

`_guard_relocation` refused whenever either checkout root held anything. Task 6.9's observation
behind it is correct — a linked worktree is held together by two absolute paths and moving the
project invalidates both — but an agent worktree is **permanent**, so "a checkout exists" is a fact
about history, not activity. The spec's condition is *"no active run or worktree mutation"*. And
refusing never un-broke anything: the operator has already moved the directory by the time they
ask, so all the refusal preserved was a Hub pointing at a path that is gone — with no stated
remedy, because no control anywhere removes an agent worktree.

Now: gate on active runs, and **repair** — `git worktree repair` over every checkout under
`worktrees/`, `tasks/` and `reviews/`, on both relocation routes, best-effort. Live:

```
before  git worktree list -> .../aw-f52/.agentweave/worktrees/builder [prunable]
        git -C <checkout> status -> fatal: not a git repository
POST /relocate -> 200, directory_state "available"
after   git worktree list -> .../aw-f52-moved2/.agentweave/worktrees/builder  (no "prunable")
        POST /agent/trigger builder -> run-4e266e6f1c74, completed, exit 0
```

**Two existing tests pinned the defect and were replaced, not deleted.** Both `mkdir`'d the blocking
state by hand — which is the tell. A test that has to build the blocking state itself has never
asked how often the product builds it; here the answer was "always, permanently, after the first
turn".

### What drove clean, and is worth saying so

Row 18's budget half holds exactly as specified. With `token_budget` 1000 against 12.68M measured:
an operator trigger ran immediately; an agent-origin entry created by `builder` calling
`send_message` stayed `queued` with `waiting_reason: "token budget exhausted"` and
`delivery_attempts: 0` — correctly transient, so pausing an agent does not spend its message; and
clearing the budget to `null` delivered it unprompted. All three spec scenarios.

Killing an agent process recovers correctly in every respect except what it says (F94). Directory
loss is detected and reported correctly; only the repair was broken (F95).

### The pattern, again, and it is the same one

Iteration 6's carry-forward said: *when a test has to set something up for the code to reach the
state under test, ask who does that in production.* F95 is that rule catching a test that was not
merely blind but **actively wrong** — two tests asserting the refusal that is the defect, each
building `.agentweave/worktrees/writer` by hand because that is what the guard reacts to. Nobody
asked what else builds it. Every completed turn does.

The second pattern is F91's and F94's, and it is new: **a rule applied at N call sites holds at N-1
of them.** `readable_exit_code`'s rule was applied at the two Codex builders and missed the Claude
one; both fixes moved the rule to the join — `_broadcast_run_lifecycle` for rendering,
`bound_address.known()` for the address question that was spelled out twice and asked nowhere a
third time.

### Verification

- F91: 3 Hub tests, 2 watched to fail (the deferral, the `transient` classification).
- F92: 3 Hub tests, 2 watched to fail, including one pinning that a measured outcome is never
  overwritten by an unavailable one.
- F93: covered by F92's crash-path test, watched to fail as `assert 'running' == 'failed'` — which
  is how F93 was found in the first place.
- F94: 1 Hub test, watched to fail.
- F95: 3 Hub tests, both halves of the fix mutation-checked separately.
- CLI **440 passed / 3 skipped**. `ruff`, `black`, `mypy` clean over CI's path lists. No UI change,
  so no bundle rebuild. Full Hub-suite result recorded below.

### State left behind

`proj-46b602c1f3cb` (aw-e2e1): all three agents idle, `token_budget` back to `null`, 19 jobs and 17
loops still all disabled, `task-1b7af6b595e6` still the deliberate wedged specimen. The corrupt
`claude.exe` used for F93 is **deleted** and the Hub restarted without it on `PATH`.

`proj-a1736a6a596b` (aw-f52) now lives at `C:\Users\huida\Documents\aw-f52-moved2`, relocated by the
product itself as F95's live proof, with its `builder` checkout repaired and a turn completed there.
It is a throwaway; the path change is deliberate and recorded.

**Full Hub suite, run after every fix in this iteration was in place: 3422 passed / 84 skipped /
1 xpassed / 0 failed (19m41s).** 3349 at arming, so the 73 additional passes are this run's own
tests plus iterations 2-6's; nothing regressed.
