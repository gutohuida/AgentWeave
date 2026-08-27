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
