# Approvals

The only file the FIX window (23:00-07:00) reads to learn what the operator said. Written by the
DECIDE session, not by hand and not by either scheduled window. Format and semantics: `README.md`
in this directory.

```
- APPROVED  <change-name>   optional note
- REVISING  <change-name>   what needs to change
- REJECTED  <change-name>   why
ORDER: <change-name>, <change-name>, F156      (optional, that night only)
NOTHING TONIGHT                                 (optional, stops the window)
```

Newest day first. Days below the newest are history and are not read.

---

## 2026-09-03

Review page: `review/review-2026-09-03.html`. **One change proposed, taken through all three rounds.**
Rounds 2 and 3 each broke the round before them, and round 3's defect was measured rather than argued.

**No real token is written below.** The day window proposed this change and must not appear to have
approved its own work, so the line is a blank to fill, not a row. Write the token between the `-` and
the change name, in a DECIDE session:

- __________  a-blocked-agent-workspace-holds-its-input
- __________  a-write-outside-the-workspace-is-recorded   (carried forward, still undecided — see below)

`a-blocked-agent-workspace-holds-its-input` — **F188 (A)**. Two refusals stop an agent from running.
One holds the operator's message until they perform the repair; the other destroys it on the third
schedule. They are eleven lines apart in the same function and the difference is a keyword argument —
and the Continue button the conversation view offers for exactly this situation *is itself a schedule*,
so the operator's attempts to find out why nothing is happening are what consume the allowance. **F114
reproduced verbatim at a site the F114 fix did not reach.**

The obvious repair — flag the site — **breaches a requirement that shipped 2026-08-28**, because one
`except` covers two workspaces: the task checkout (where other input really could have run, and
counting is right) and the agent's own worktree (which blocks the agent's whole ordinary population).
So the site states *which* workspace it could not prepare and the scheduler answers the starvation
question, being the only party holding the queue. Read against the archived change's own task 1.2a,
this **completes** a decision deferred six days ago rather than reversing one.

- **Round 2** found R1's design D3 rested on `takes_task_workspace` reducing to "the entry names a
  task". It does not — **naming a task is not taking a task's checkout**. Grandfathered tasks, refused
  ids, and deleted or decided tasks all run in the blocked directory while naming a task, so R1's
  helper would have counted the attempt and destroyed the head having released nothing: **F188
  surviving its own fix on every project old enough to have grandfathered tasks.** Measured under
  `py -3.11` at HEAD. Four smaller corrections; tasks 24 → 28.
- **Round 3** measured R2's task 3.0 and it is false: extracting the predicate the obvious way turns
  `test_task_workspace_scheme.py` red, because its source scan looks for the substring
  `.workspace_scheme =`, which is a prefix of `.workspace_scheme ==`. Today's resolver survives only
  because it happens to be written `!=`. Four more corrections — a decided task can still inherit its
  thread's live binding (so the code was right and only the argument was wrong), the `selected`
  exclusion needed a fact rather than an enumeration, a review with no commit is a false yes (new D3b),
  and `D3a` collided with a shipped `D3a` cited by both files this change edits (renamed D8). Plus the
  thing no round had looked at: `turn_scheduler.py:225-233`, a shipped comment **inside the branch being
  edited**, asserts the exact claim this change falsifies, and task 5.2's grep could never reach it.
  Tasks 28 → 32.

Cost if approved: **32 tasks** across 6 phases — phase 1 is a reproduction gate, phase 6 is three drive
legs. Four files, all Python: `agent_trigger.py`, `turn_scheduler.py`, `worktrees.py`,
`task_workspace.py`. **No migration, no API shape change, no UI.** `openspec validate --strict` passes.
Nothing under `hub/hub/`, `hub/ui/` or `src/` is committed from today.

`a-write-outside-the-workspace-is-recorded` — carried forward unchanged, still **undecided rather than
rejected**, still with no row until you write one. It is R3-complete at 54 tasks. It collides with
`a-blocked` on `agent_trigger.py` and `worktrees.py`, and touches `AgentTimeline.tsx` on top, so
approving both means ordering them and eating a committed-bundle conflict. Its task 4.2 migration
number **is already correct** — fixed to `0101` on 2026-09-02 and still right, since head is still
`0100_loop_work_needs_evidence.py`.

**A correction to the 2026-09-02 carry-forward, measured this morning.**
`runner-model-is-chosen-from-the-catalog` is **done, not pending**. It was built and archived on
2026-09-02 by the night window (`7df21ea`, 29 of 29 tasks closed), and nothing by that name remains in
`openspec/changes/`. Both items approved on 2026-09-01 have now shipped. Do not re-approve it.

**If you approve nothing, the FIX window has nothing it is allowed to build** — and that is new
tonight. Source 1 (implemented changes needing only archiving) is **empty**: both open changes sit at
zero completed tasks. Source 2 lands on **F271**, then **F188**, then **F274**, but the playbook's own
rule is that a finding with no proposal is a note to tomorrow rather than work — F271 and F274 have no
proposal, and F188's is not approved, which source 3 does not reach. Source 3 is empty unless you write
a row. `ORDER:` and `NOTHING TONIGHT` are both available, and `NOTHING TONIGHT` is an honest answer if
you would rather the branch stopped growing before it is merged.

Today's drive filed **F274 (A)** — a turn's terminal label and its "Worked for Ns" line vanish once the
agent-scoped 50-event timeline window moves past that run, which four ordinary triggers in the agent's
*other* conversations achieve. That is **F190's own symptom, live, against the change that closed
F190**, found by driving the served bundle rather than the Python transcription phases 6 and 7 used.
The route is **not in breach** — `agent-stream-events/spec.md:363-366` blesses it — the gap is that no
requirement says the events must cover the turns the client renders. It has no proposal and wants no
row here; it is tomorrow's spec loop. Also **F275 (C)**: an abandoned operator message renders after the
failures it caused.

Four things on the review page are **not** work and want no row: whether the three-day, 167-commit
branch merges; F271's blank-a-non-empty-PUT question; `f272-harness-guard`, still the only open decision
that blocks work; and `findings-ledger-retirement`, new — nothing in the cycle retires a ledger row when
the change that fixes it is archived, which is how the open severity-A count read "one" for a week while
F188 sat in it.

---

## 2026-09-02

Review page: `review/review-2026-09-02.html`. **No new change was proposed today.** The spec-loop
slot went to repairing an already-approved one, because last night's phase-0 gate falsified the
premise of its design D6 (task 0.3) and `DIRECTION.md`'s governing sentence is that a broken
approved design outranks a new proposal. Two rounds ran; the row below is what came out.

The day window wrote this section with **blanks** rather than tokens, because it did the work and
must not appear to have approved it. **The operator filled them in on 2026-09-02 at 20:40, in a
DECIDE session.** The row below is a real row. Leaving a change out entirely is undecided, not
rejection — but note that only the newest section is read, so an omitted row here means the FIX
window sees no approval for it tonight, whatever last night's section says.

- APPROVED  a-turn-says-how-it-ended   operator, 2026-09-02 20:40, in session -- the phase 0 condition is satisfied; rounds RA and RB repaired D6; phases 1-7 unblocked

ORDER: a-turn-says-how-it-ended

`a-write-outside-the-workspace-is-recorded` has **no row**, which is undecided rather than
rejected. It is deliberate: it collides with `a-turn` on three files, one of them the committed
UI bundle, so approving both for one night means ordering them and eating a bundle conflict every
iteration. It reappears on tomorrow's review page unchanged.

The `ORDER:` line is load-bearing, not decoration. Without it the default queue applies, and its
source 2 -- open findings, A before B before C -- reaches **F271** before it ever reaches this
approved row. F271's repair is half a plain fix and half a product decision the window may not
make, so the night would spend itself on the half it is not allowed to finish. `ORDER:` sends it
straight to the 41 open tasks of the change that has been through eight rounds of review.

`a-turn-says-how-it-ended` -- F190 (A). You approved this on 2026-09-01 **conditionally**: observed
first. Phase 0 ran last night against a live Hub and the gate did its job -- **task 0.3 falsified
round 3b's premise**, and task 0.7 returned the change to a round rather than letting it proceed.
Phases 1-7 were blocked in the tasks file itself. Two rounds ran today:

- **Round RA** re-derived design D6 against nine files and found that signal 1 *does* fire, for the
  run that finished, written by a producer round 3b never looked for (`runner_parsing.py:346-356`,
  persisted at `agent_trigger.py:1925-1938`). D6's purpose survives on a narrower argument -- it
  extends signal 1 to runs that did **not** complete, plus a durable exit code -- and loses two
  attributions. **Scope not narrowed; phases 1-7 unblocked.** Three tasks added, five rewritten.
- **Round RB** re-derived RA's argument independently, confirmed every fact by a stronger route, and
  corrected its **scope**: `status_event("completed")` occurs exactly once in the whole Hub, inside
  the Claude-only parser, so signal 1 has never fired for a Codex run of either transport. RA's
  headline retraction is right for Claude and wrong for Codex. Four tasks corrected, one added, and
  **one task withdrawn** -- 4.5a offered two fixes as equivalents and RB ran both; one fails in
  exactly F269's case. RB changed **nothing** about designs D1-D5, D7, D6's purpose/writer/exit-code
  argument, or F190's headline, and that is stated on the review page rather than left implicit.

Cost if approved: **41 open tasks** across phases 1-7, including phase 7's separate verifying round.
Both rounds implemented and ran code to test their own claims and reverted all of it; nothing under
`hub/hub/`, `hub/ui/` or `src/` is committed from today. `openspec validate --strict`: valid.

`a-write-outside-the-workspace-is-recorded` -- carried forward unchanged and still undecided rather
than rejected. It collides with `a-turn` on three files, so approving both for one night means
ordering them. Its task 4.2 migration number was corrected to `0101` and must be re-derived if
another migration lands first.

**If you approve nothing**, the FIX window falls to the default queue: source 1 (implemented changes
needing only archiving) is **empty**, source 2 lands on **F271 (A)** -- today's drive finding, whose
repair is half a plain fix and half a product decision the window may not make -- and source 3 is
`a-turn`, approved last night and unblocked today. `ORDER:` and `NOTHING TONIGHT` are both available.

Three things on the review page are **not** work and want no row here: whether the two-day branch
should merge, F271's blank-a-non-empty-PUT question, and whether the FIX window may write a proposal
when its queue empties five hours early -- which is what happened last night.

---

## 2026-09-01

Review page: `review/review-2026-09-01.html`. One change proposed, taken through all three rounds.
Write its row below in the contract's form — the status token goes between the `-` and the change
name. Leaving the row out entirely is undecided, not rejection. **No real token is written here:**
the day window proposed this change and must not appear to have approved its own work, so the line
below is a blank to fill, not a row.

- APPROVED  runner-model-is-chosen-from-the-catalog   operator, 2026-09-01 17:40, in session
- APPROVED  a-turn-says-how-it-ended   operator, 2026-09-01 20:15, in session -- CONDITIONAL, see below

`a-turn-says-how-it-ended` -- F190 (A). Approved with a condition the operator stated when
approving: **observed first, and tested after implementation by a new round.** The contract here has
only three tokens and no way to say "approved with a precondition", so the condition is encoded as
blocking structure inside the change instead:

- **Phase 0 is a gate.** It says, in the tasks file itself: if phase 0 has not been completed and
  recorded, do phase 0 and stop. A window reaching this change with no observation record performs
  the six observations, writes them up, and ends its turn. Nothing is implemented.
- **Phase 7 is a separate round.** Implementation does not close the change and task 6.7 no longer
  retires F190; a sitting that did not write the code re-runs phase 0's observations against the
  built product and closes it.
- **Phase 0 can falsify the design.** Task 0.3 in particular: rounds 2 and 3 disagree about whether
  a single-run conversation is affected, and if the indicator releases cleanly there, the round 3b
  finding is wrong and the change returns to a round rather than proceeding.

Why the condition is right, in one line: four rounds of review each found the defect nearest the
code that sitting happened to read, three of them read the same gate expression, and none of them
checked where its inputs come from. Every claim in the change is derivation; none is observation.

Note also that `DECISIONS.md` **D-7 is OPEN** and groups response-shape changes as ones "no window
took unattended". This change is a BREAKING envelope. The phase 0 gate is what makes an unattended
window safe to let near it; D-7 itself is still undecided.

`runner-model-is-chosen-from-the-catalog` — F173 (A). The runner screen free-types the model against
a shipped requirement that says it must offer the catalog's, and swallows the backend's refusal
entirely. 29 tasks across the API, the picker, the error surface, tests and a drive; retires F173
(A), F219 (C) and F220 (C). Round 2 and round 3 each changed it — the argument in section 4 of the
review page.

If you approve nothing, the FIX window falls to the default queue and lands on open findings, A
first — which is F173 again, by the finding route and without this design. `ORDER:` and
`NOTHING TONIGHT` are both available.

Two decisions on the page are **not** work and want no row here: ratifying the `fastmcp<4` ceiling,
and leaving F188/F190 unproposed as direct repairs.

---

ORDER: a-turn-says-how-it-ended, runner-model-is-chosen-from-the-catalog

**Why this order.** `a-turn`'s phase 0 is a gate: it observes and stops, touching no product code,
so it cannot collide with anything and cannot run long. Putting it first spends perhaps an hour to
learn whether the design is *right* — task 0.3 can falsify it outright, since rounds 2 and 3
disagree about whether a single-run conversation is affected. Learning that tonight is worth more
than learning it after the change is built. `runner-model` then gets the rest of the window; it is
approved unconditionally, disjoint from everything else in flight, and is the item that actually
ships.

**Both touch `hub/ui/src`, and that is safe only because of the order.** `hub/hub/static/ui` is a
committed build artefact and two UI changes in flight conflict on it every time. Phase 0 writes no
UI, so there is exactly one UI change tonight.

`a-write-outside-the-workspace-is-recorded` has **no row** and is therefore undecided, not rejected
— it is R3-complete but never approved, and it collides with `a-turn` on three files. Do not build
it tonight. Before anyone does, fix its task 4.2: it names migration `0100`, and
`hub/hub/migrations/versions/0100_loop_work_needs_evidence.py` already exists, so it must be `0101`.

If the window finishes both, the next most valuable thing is **F188** — the last severity-A finding
with no change and no design (see `DECISIONS.md`, *Not decisions*). Spec it; do not repair it
directly.
