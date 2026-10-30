<!-- followed the top of the file in FINDINGS.md -->
# Findings — driving AgentWeave

Project under test: `ledger-stress` = `proj-18e5d4e0` at `C:\Users\huida\Documents\aw-stress`
Trial Hub `127.0.0.1:8010`. Agents: `builder`/`critic` (Haiku 4.5), `relay` (gpt-5.4-mini).
Settings for the test: `hop_budget=2`, `allow_agent_jobs=true`, `main_branch=master`.

Severity: **A** = wrong behaviour an operator will act on · **B** = wrong/misleading surface ·
**C** = friction or vestige.

---

<!-- followed the top of the file in FINDINGS.md -->
## Open severity-A baseline, 2026-08-27

The start line for the operator's proposed freeze — *fix every severity A that driving can find,
then migrate*. Every `## F<n>` section below now carries a `**Status:**` line, sourced from
`git log --all --grep`/`-S` restricted to commits **at or after the commit that first wrote that
section** (the F-numbers in `Q4-spec-ux-fixes` and `N6` commits belong to a different findings
series — `.claude/autonomous/2026-08-16-operator-ux-findings.md` — and would otherwise produce
false attributions), plus each section's own prose.

**Severity A, still open — three, and only one of them is wholly open:**

| Finding | State | Where it stands |
|---|---|---|
| **F12** — `stop_when_queue_empties` waits for a human, and burns a firing a minute meanwhile | ~~open~~ **fixed** `5237ec5` — **this row was wrong** | The eviction was fixed 2026-08-24 under its own design vocabulary, so the grep-over-commit-messages method used to build this table could not see it and reported it as untouched. The idling that remains was always correct. See F12's own correction. |
| **F52** — the "workspace" posture never sees a git command | **partially fixed** `68459ea`; the rest does not reproduce | The operator-visibility half shipped. Every axis of the underlying refusal is eliminated (`0cda570` disproved its central inference — `record_permission_decision` persists only refusals — and `57eb92b` drove a full live turn that committed). Out of scope: a new git refusal is a **new** finding. |
| **F60** — an unanswered `ask_user` that resolves itself leaves the task reading `completed` | **partially fixed** `033ec4c` | The guard refusing an answer whose asking run has ended was already shipped before F60 was filed. The remaining half is **parked for F14**, whose fix shape is the operator's undecided call. |

`F9 (A-)` is not a defect — it is the merge-on-approval behaviour, recorded because it is the most
consequential thing the product does. Every other A (`F1 F5 F10 F23 F27 F41 F43 F45 F49 F51 F54 F56
F57 F58 F70 F71 F72 F100 F101`) is fixed with a commit named in its `**Status:**` line — `F100`
and `F101`, both filed and fixed on 2026-08-28, are the newest, and each was found by a probe
aimed at the finding before it.

**Open below severity A**, for completeness: `F3` `F15` `F20` `F21` (C/C/C/B, all with the cause
named), `F42` (C), `F47` (C, deliberately deferred — it needs a third actor kind), `F61` (B, fix
chosen by the operator and not implemented), `F62` (C), `F65` (C, queued as `Q4-SPEC`), `F66`
(unrated, a question for the operator), `F68` (B), and `F53`'s second half (B, queued as `Q4-SPEC`).
`F14`'s task-state half is open and blocks `F60`.

**Read this as a floor, not a ceiling.** A short A list measures what *this* corpus of driving has
found, not what is there. Tonight's sweeps exist to lengthen it.

### Movement against the baseline, as of 2026-08-28 03:30

The sweeps did lengthen it, which is the point. **Eleven severity-A findings have been added since
the table above was written, ten of them fixed the same night:**

| Finding | Iteration | State |
|---|---|---|
| **F74** — a task's own evidence rejected as a duplicate of itself | 2 | fixed |
| **F76** — a review started by hand provisions the reviewer and never staffs the task | 2 | **open** — three repairs are live and the choice is the operator's |
| **F78** — the operator cannot clear a task's assignee, and the API reports that they did | 3 | fixed `f1d0c6f` |
| **F79** — a task the operator has decided about still takes new runs | 3 | fixed `eba8620` |
| **F83** — a loop created enabled with `initial_tasks` never reaches the scheduler | 4 | fixed `0757be5` |
| **F84** — an operator who stops a loop stops nothing; it fires for another seventeen minutes | 4 | fixed `0757be5` |
| **F85** — a loop stages a review it cannot start, wedges the task, and fails on it forever | 4 | fixed `3e07726` |
| **F87** — a message the Hub gives up on disappears, and the record says nothing | 5 | fixed `46458ae` |
| **F88** — two grants the operator can confer, and neither had ever done anything | 6 | fixed `a42f978` |
| **F89** — an automatic checkpoint holds the database lock and kills the turn | 6 | fixed `7cecd71` |
| **F90** — a turn held back by another agent's turn is never let go again | 6 | fixed `a053553` |

So the open-A list today is **F12, F76**, plus F52's and F60's partial states unchanged. F76 is open
because its fix shape is a decision, not because nobody has looked at it.

**Revised 2026-08-28: the open-A list is F76 alone.** F12 was verified rather than trusted and
turned out to have been fixed on 2026-08-24 (see its row above and its own section). One remaining
severity A, and it is waiting on a product decision.

**Revised again, later on 2026-08-28: the open severity-A list is empty.** F76's shape was decided
by the operator, specified through three review rounds, implemented and driven live. Driving it
produced one new finding — **F108 (B)**, a permanently refused request answering
`200 {"success": true}` — fixed for review dispatch and open as a class. An empty A list measures
this corpus of driving, not the product; the next sweep is what lengthens it again.

**Revised 2026-09-02: the open severity-A list is one — F271.** Filed by the day window's D-4
drive. It is not a regression against anything above; it is a page nobody had ever driven with its
load failing. Its fix shape is *not* a decision waiting on the operator the way F76's was — the
render-the-error half is a plain repair. Only the second half (should a PUT that blanks non-empty
stored content ask first?) is the operator's call.

**Revised 2026-09-03 (night window, iteration 14): the line above is wrong, and it is wrong in the
direction that hides work.** The queue emptied tonight, so the open severity-A list was rebuilt from
the sections themselves rather than read off this paragraph. **It is two, not one — F271 and
F188** — and four more entries are in a third state this index has no word for.

| Finding | What the section says | What is actually true, measured 2026-09-03 |
|---|---|---|
| **F271** | open | **open**, and unchanged. No proposal, no change directory. |
| **F188** | filed, no `**Status:**` line at all | **open at HEAD, confirmed by reading the code it names** (measured 2026-09-03). `agent_trigger.py:878-883` still raises the worktree refusal with no `agent_wide=True`, while three sibling sites (`:573`, `:594`, `:624`) pass it. Nothing anywhere proposes it. — **Superseded 2026-09-04: retired**, fixed by `467dfea` and driven; see its section. |
| **F140** | *"open, filed not fixed"* | has an **implemented and archived** change — `2026-09-01-a-flow-briefing-names-its-contract` |
| **F142** | *"open, filed not fixed"* | has an **implemented and archived** change — `2026-09-01-a-review-a-flow-cannot-staff-is-named` |
| **F154** | no resolution prose | has an **implemented and archived** change — `2026-09-01-a-review-nobody-is-doing-is-named` |
| **F155** | no resolution prose | has an **implemented and archived** change — `2026-09-01-a-conflict-refusal-names-what-clears-it` |

**Revised 2026-09-03 (day window, D-1): three — F271, F188 and now F274.** The day window's drive
of `a-turn-says-how-it-ended` filed **F274 (A)**: a turn's terminal label and its "Worked for Ns"
line vanish once the agent's fifty-event timeline window moves past that run, which ordinary work in
the agent's *other* conversations does. It is F190's symptom, reproduced live in the served bundle
against the change that closed F190, and the route is not in breach of its spec — the gap is between
two routes. See its own section below. F275 (C) was filed in the same drive.

**Revised 2026-09-04 (night window, iteration 11): two — F271 and F274.** **F188 is retired**, and
retired the way this index says a finding has to be: `a-blocked-agent-workspace-holds-its-input` was
specified through three rounds, built over phases 2–5, and then *driven* — three legs, 33/33, on a
Hub serving the built code, with the leg that could have falsified the fix run deliberately. Its
section carries the evidence and the commit (`467dfea`) that repairs the behaviour. The day window
handed it over on 2026-09-03 because it had no proposal; it has one now, archived.

**Recomputed rather than decremented, because this index's own post-mortem below says a decrement is how the last miscount happened.**
All 40 severity-A headings were scanned mechanically for their `Status` line. The picture is exactly
the 2026-09-03 rebuild minus F188: **F271** and **F274** open, **F140, F142, F154 and F155** still in
the third state (a change naming each was archived on 2026-09-01; none has been driven, so none is
retired), everything else fixed or retired in its own section. Two caveats on that scan, stated
because an unstated one is how this index went wrong before: it reads the heading and the first
`Status`-bearing line, not the section, so a finding whose resolution is buried in prose would read
as open; and `open, filed not fixed` and `FIXED` are one substring apart, so no keyword rule
classifies both — F140 and F142 were classified by hand.

**The four in the third state are recorded as `unverified`, not as retired, and that distinction is
the whole point.** What was measured is that a change naming each of them was archived on
2026-09-01; that is a *plan having existed and been marked done*, which this repository's own rule
says is not evidence a defect is gone. Retiring them needs what F190 got tonight — a drive of the
built product. Do not mark them fixed on the strength of the archive path.

**How the miscount happened is worth more than the count.** Each of the four was retired *as a
change* and nobody walked back to the ledger row that started it; the index was then revised from
the newest finding rather than recomputed, so four stale `open` rows and one missing `**Status:**`
line summed to *"the list is one"*. The same arithmetic will happen again on the next archive —
tonight's own `a-turn-says-how-it-ended` is the first change to close the loop by hand (F190 and
F269 carry `RETIRED 2026-09-03` markers in their own sections), and it only did so because a task
said to.

**F188 is the row this window is handing to the day window.** It is severity A, it is open at HEAD,
and it has no proposal — so by the night window's own rule (`.claude/loops/night-window.md`: *a
finding with no proposal needs the day window first*) it is not this window's to fix, however small
the repair looks. It was invisible for a week because the index said the A list was one.

**Revised 2026-09-06 (night window, N-2): the number is not the defect — the missing *definition*
is, and by this index's own words the open list is six, not two.** This item was queued on the
premise that the index still asserts *"the open severity-A list is one — F271"*. Re-deriving instead
of trusting that premise falsified the premise first: that line is dated 2026-09-02 and is
superseded twice below, on 2026-09-03 and 2026-09-04. The queue item said to re-derive rather than
trust its own detail, and that is what the instruction bought.

What the re-derivation found is worse than a stale number. All **40** severity-A headings were
scanned again, mechanically and reproducibly (`^#{1,4} F\d+ \(A\)`, each section bounded by the next
finding heading of any severity), for their `**Status:**` line *and* the banner above it. **Six
sections say they are open. The paragraph above counts two.** The four in between are the ones this
index invented the phrase "third state" for on 2026-09-03 — and then, the same night, wrote a banner
onto each of them reading *"this entry stays open until somebody re-drives it."* A reader who greps
`**Status:**` gets six; a reader of the index gets two; both are reading this file.

| Finding | What its own section says | What it is blocked on |
|---|---|---|
| **F271** | no `**Status:**` line at all and no retirement banner — open by default, unchanged since filing | **Nobody has specced it.** No proposal and no change directory (`openspec/changes/` holds exactly one, and it is F274's). Half of it is a plain repair — render the load error instead of an empty editor with Save enabled — and half is an operator decision: should a PUT that blanks non-empty stored content ask first? The night window may not answer that, so it is the day window's, per `.claude/loops/night-window.md` step 4.2. |
| **F274** | `**Status:** open, proposed 2026-09-05` | **An approval that was never given.** `2026-09-05-the-conversation-carries-its-own-run-facts` exists — 44 tasks, 8 phases — but `spec-queue/APPROVALS.md`'s 2026-09-05 row carries no status token, because the DECIDE session did not sit down. Specced, unapproved, unbuilt. |
| **F140** | banner *"Unverified, not retired … stays open until somebody re-drives it"*, over a `**Status:** open, filed not fixed` that predates the banner | **Two things at once.** An operator choice between two defensible repairs — the stated reason it was filed rather than fixed — *and* a change naming it, `archive/2026-09-01-a-flow-briefing-names-its-contract`, archived without ever being driven. |
| **F142** | same shape as F140 | Same archived-and-undriven change of its own (`archive/2026-09-01-a-review-a-flow-cannot-staff-is-named`). Its own text says it changes *which* of F140's repairs is worth building, so it cannot be settled before F140 is decided. |
| **F154** | no `**Status:**` line; carries the same *"stays open until somebody re-drives it"* banner | `archive/2026-09-01-a-review-nobody-is-doing-is-named` — archived, never driven. |
| **F155** | same | `archive/2026-09-01-a-conflict-refusal-names-what-clears-it` — archived, never driven. |

Unchanged, and deliberately named here so the next recount does not rediscover them as anomalies:
**F12** (severity-A half fixed `5237ec5`), **F52** (partially fixed; the underlying CLI refusal does
not reproduce), **F60** (`FIXED 2026-08-30`), and the three retired behind banners — **F173**
(2026-09-02), **F188** (2026-09-04), **F190** (2026-09-03).

**The correction is a definition, not arithmetic.** "Open" has been used here to mean two different
things, each defensible alone: *nothing has been built* (two — F271 and F274) or *no drive has shown
the defect is gone* (six). This repository already decides between them — `CLAUDE.md`: *"Never mark a
task complete on the strength of a plan existing"*, restated by this index four paragraphs above as
*"a plan having existed and been marked done … is not evidence a defect is gone."* **So the open
severity-A list is six: F271, F274, F140, F142, F154, F155.** Two was not a miscount; it was the
older definition still standing next to the banner that had already replaced it, which is why
recomputing the *count* on 2026-09-04 did not catch it. **A recount cannot find a definition
error — only re-deriving the rule can.**

**Where this has already mis-steered something.** Today's `spec-queue/APPROVALS.md` reasons off the
two-count and contradicts itself doing so: line 85 tells the operator *"F274 is the only open A"*,
while line 91 of the same page calls F271 *"the one remaining open severity-A row"*. Line 31 offers
F274 as *"the last open severity A with no proposal"*, which F271 also is. That page is **left
exactly as written** — it is the record of a decision session put in front of the operator, and
editing it after the fact would destroy the thing it exists to be — but any window reading it should
read this paragraph alongside it.

**What this does not claim.** Six is what the *sections* say, not a re-drive. Nothing here drove
F140, F142, F154 or F155; the banners' condition is still unmet and this revision does not pretend
otherwise. The cheapest way to make the two-count true is to drive those four — until somebody does,
they are open.

**Revised 2026-09-06 (night window, n7-close): the open severity-A list is still six — but not the
same six. F271 leaves it and F295 joins it: F274, F140, F142, F154, F155, F295.**

**F271 is fixed** `c7e615c`, **shipped in the served bundle** `676eba4`, **and driven in a browser**
`f664f45`. It leaves under the *stricter* of the two definitions above, not the looser one: a change
was built **and** a drive against the served bundle observed the defect gone (31 passed / 0 failed),
with the same inverted harness re-run against the pre-change bundle giving 19 passed / 12 failed and
the baseline column identical in both. Its cross-project variant was closed by construction rather
than by measurement — see F271's own section, which says so rather than folding it into the 31/0.

**F295 was filed earlier today** (split out of F292) and postdates the 2026-09-04 recount, so it has
never appeared on any list on this page. It is severity A, `**Status:** open, not specced, not
fixed`. The count is therefore unchanged by coincidence, and reporting "five" would have been a
different error from the one this section spent 2026-09-04 correcting: not a stale definition, a
stale *census*. There are now **41** severity-A headings, not 40.

The other five are unchanged in every respect. **F274** is specced and unapproved. **F140, F142,
F154, F155** are still the four whose changes were archived without ever being driven, and the
banner condition on each is still unmet — nothing tonight touched them. The definition correction
above stands exactly as written; this revision applies it, it does not revise it.

**How this was arrived at, so the next window can repeat it rather than trust it.** The scan above
was re-run mechanically over all 41 sections. Its first pass reported **five** and was wrong: the
classifier tested for the substring `fixed` in the status line, which F295's *"open, not specced,
not fixed"* matches. **A substring test for `fixed` reads "not fixed" as fixed.** That is worth
leaving written down — it is the same class of error as the definition drift above, an instrument
agreeing with the expected answer, and it was caught only because the heading count came back 41
against a remembered 40.

**Revised 2026-09-08 (DECIDE session): the open severity-A list is five — F274, F142, F154, F155,
F295. F140 leaves it, and it leaves under the stricter definition, not the looser one.**

**F140's re-drive already existed when the banner asking for one was written.** Repair 1 shipped
`1b4c730` (2026-08-30) and was driven live on 2026-08-31 — both Haiku agents made the
`update_task(..., status="completed")` call unprompted, both tasks reached `approved`, both commits
verified ancestors of `master`. That drive is recorded **in this file**, under *"the flow lands its
work"*, two days *before* the 2026-09-03 banner. Re-measured this session:
`_briefing_completion_lines` is **byte-identical** to the version the drive exercised, so the
evidence describes the shipped code and not a since-edited copy.

**The error this makes visible is a third one, distinct from the two above.** 2026-09-04 found a
stale *count*. 2026-09-03 found a stale *definition*. This is a stale **search**: the banner author
checked `openspec/changes/archive/` for a change and did not check this file for a drive, so a
finding was reopened for want of evidence that was already written down twelve thousand lines above.
The rule that follows is not "count again" or "re-derive the definition" — it is **look for the
drive before declaring one is missing**, and the cheapest form of that is grepping this file for the
finding's own number, not for its status line.

**F142 stays open and its reason is narrowed**: not an operator decision, and never one of two
alternatives — F140 was fixed and driven before the choice was ever put to the operator, which makes
F142's *"it changes which of F140's repairs is worth building"* moot. Its fix **shipped** `f3a778f`
(2026-08-31); what is unmet is a drive, and its own change document says so in its own words
(*"Written, compiled, and not driven … that is `DRIVE-1`"*). **F154 and F155 are untouched by this
revision** — their banners' condition is genuinely unmet, and nothing here looked for their drives.
Doing that search is the obvious next thing and was not done.

**Also corrected, in `spec-queue/ROADMAP.md` rather than here: F14 and F60.** Stage 4 listed F60 as
*"not implemented, blocked on F14's task-state half, which is itself an undecided fix shape"*. Both
are **`FIXED 2026-08-30`**, shipped together in `a-task-waits-while-its-run-waits`, and this file's
own status lines have said so since. Verified in code this session: ask-time parking at
`hub/hub/api/v1/agent_actions.py:509-514`, `Question.wait_ended_at` at `hub/hub/db/models.py:1001`,
migration `0099_question_wait_window.py`, drive harness `scripts/drive/t_f14_f60_wait_parks_the_task.py`.
The ledger was right and the plan was wrong — which is the reverse of the usual direction here, and
worth noticing: **`ROADMAP.md` was written 2026-09-08 00:30 and was stale on rows this file had had
correct for nine days.** A newer document is not a more current one.

**Revised 2026-09-08, later the same day (RESUME session): the open severity-A list is three —
F274, F142, F295. F154 and F155 both leave it, and both leave under the stricter definition.**

The revision immediately above ended *"F154 and F155 are untouched by this revision — their banners'
condition is genuinely unmet, and nothing here looked for their drives. Doing that search is the
obvious next thing and was not done."* This is that search. It took about five minutes and it
retired both.

| Finding | Fix | Drive | Re-measured 2026-09-08 |
|---|---|---|---|
| **F154** | `001a07d`, 2026-08-31 | `t_f154_wedged_review.py`, **18/18** on both populations, same day; re-driven 18/18 later | `run_task_binding.py` + `scheduler.py` **byte-identical** `001a07d`→`HEAD`; sentence live at `scheduler.py:1745` |
| **F155** | `0373867`, 2026-08-31 | `t_f155_conflict_remedy.py`, **23/23**, with the falsifying lane 3 run deliberately | `requirement_gate.py` **byte-identical** `0373867`→`HEAD`; sentence live at `requirement_gate.py:263` |

Both fix commits are ancestors of `master`. Both drive harnesses are still on disk. **The
byte-identical check is stronger here than it was for F140**: F140 needed a function-level compare
because its file had moved on; these two files have not been edited at all since the commit the
drive exercised, so `git diff <fix> HEAD -- <file>` is empty and the drive describes today's code
without qualification.

**This is the stale search a third and fourth time, and that is now the finding.** Three findings —
F140, F154, F155 — were carried as open severity-A for five days each because one banner author on
2026-09-03 checked `openspec/changes/archive/` for a change and never grepped this file for the
finding's own number. The four-line rule already written above (*"look for the drive before declaring
one is missing"*) is confirmed by a second independent instance rather than merely restated. **The
count went six → five → three in one day without a single line of product code being written**, which
is the measure of what the missing search cost.

**What did not change.** F274 is specced and unapproved; F142's fix shipped `f3a778f` and genuinely
lacks a drive — its own change document says so — and F295 is unspecced. Those three are open on
their own merits and no search retires them. **F165 (B) and F166 (C), filed out of F155's own drive,
remain open and unqueued**; retiring F155 retires the refusal's wording, not the `_branch_at`
equivalence class underneath it.

**Revised 2026-09-08, third pass (RESUME session): the whole file classified for the first time,
with `scripts/classify_findings.py`.** Every previous census on this page counted the **41 severity-A
sections only**. This one bounds and classifies all **271**. The instrument is committed so the
number can be re-derived rather than believed, and **its own error rates are printed above its
results** — the point of the exercise was never the count.

**The counts deliberately do not live on this page. Run
`py -3.11 scripts/classify_findings.py` and read them off the tool.** They were printed here
once, on 2026-09-08, and **that is itself how a defect was found**: this file is the tool's input,
so writing a census *into* it changed the census. The table published in `c18cb6f` matched the tree
it was measured on (`c18cb6f~1`) and was already stale in the commit that carried it, because the
prose naming `F32`, `F108`, `F161`, `F162`, `F187` and `F272` alongside resolution words fed the
cross-section arm six new matches. **A measurement written into the thing it measures is not a
record of it.** `ROADMAP.md` carries the current figures; that file is not read by the tool.

**The severity-A tail is confirmed independently.** The classifier had no knowledge of this
morning's work and reproduced it: `F142` open, `F52`/`F274`/`F295` in conflict (all three are known
— F52 is bookkeeping nobody retired, F274 and F295 are specced *and approved* but not built), and
every other A resolved. **That agreement is the reason the instrument was then attacked rather than
trusted.**

**Revised 2026-09-09 (night window, iteration 7): the open severity-A list is two — F274 and
F142 — under the looser definition, and still three under the stricter one, because F295's change is
built but not driven.**

F295's fix shipped tonight as `2026-09-07-a-dead-connection-is-never-handed-back-out`: the pool guard
`00d72a8`, the shutdown settle `0f06bea`, nine tests across two files
(`2d399c7`, `9a0fdde`), and a 14-mutation check `2046c4e` in which 11 mutations each named a victim
and every shipped test is named by at least one. The three preceding revisions on this page all
retired findings by *searching* rather than building; this one is the first in the sequence that
retires one with product code.

**It is deliberately not claimed as fully retired.** The stricter definition this page adopted on
2026-09-06 — a change built **and** a drive observing the defect gone — is met only in its first
half. `c1-drive` is a separate open queue item for the same window and is where the second half
happens. Reporting "two" without this paragraph would be the fourth error in the sequence above:
not a stale count, a stale definition, or a stale search, but a **premature** one — the failure mode
that the stricter definition was introduced to prevent, committed by the window that introduced it.
The 41-heading census is unchanged; no new severity-A section was written.

**Revised 2026-09-09 (night window, iteration 8, `c1-drive`): the open severity-A list is two —
F274 and F142 — under *both* definitions. F295's second half is done.**

The paragraph immediately above refused to report "two" because the drive had not happened. It has
now: a Hub started from source on 8011, a real Haiku turn in flight, and `CTRL_BREAK_EVENT` — the
only stop that reaches the lifespan teardown at all, since `agentweave stop` is `taskkill /F`
(`F297`). The process runs the whole teardown and exits in **0.42 s**, against **0.22 s** for the
idle control, with no settle-bound warning, no dead-worker warning, and no `Event loop is closed`.
Reproduced three times; the harness is committed as `scripts/drive/f295_shutdown_drive.py` and
`scripts/drive/f295_restart_reconciles.py`. F295's own section carries the numbers and the two
things the drive found that no round had looked at, one of which is filed as **`F298` (C)**.

**Revised 2026-09-09 (night window, iteration 17, `c3` phase 6): the open severity-A list is one -
F142 - under both definitions.**

F274 is retired, and under the stricter definition: `2026-09-05-the-conversation-carries-its-own-run-facts`
shipped over phases 1-5 (`272adce` server, `503a6ff` client) **and** phase 6 re-ran phase 0's two
reproductions in a browser, on the same Hub, the same profile database, the same conversations and
the same run ids. Both inverted. Conversation A's stopped turn shows `Turn stopped` and
`Worked for 8s` again while its run is *still* outside the timeline map; the ten-turn single
conversation shows ten durations where it showed eight, with **four** of its runs now outside that
map rather than two. The map got worse and the screen got right, which is the shape of a fix that
moved the source rather than widened a window. F274's own section carries the table, the
stop-then-send indicator trace, the `run_interrupted` SSE measurement and the query-cost numbers.

**Task 7.2 of that change asked for something this page should not do.** It said to *correct* the
severity-A summary lines at `FINDINGS.md:96-112`, which name F274 as open. Those lines are dated
revisions - 2026-09-03, 2026-09-04 - in an append-only sequence, and this page's own post-mortem
below is about a count that went wrong by being edited rather than recomputed. Rewriting a dated
entry to say something its date did not say is the same error in a politer form. So the revision is
**appended here** and the historical lines are left exactly as they were written.

**What did not change.** F291 is **not** retired, and task 7.1's instruction to mark it `fixed` is
refused with a measurement rather than skipped: the failing runs' facts do reach the chat response
now, and the screen is byte-for-byte what it was, because `groupIntoTurns` never builds a turn from
an abandoned entry. Its own section carries the re-drive. F142 is unchanged: an implemented and
archived change (`2026-09-01-a-review-a-flow-cannot-staff-is-named`) that nobody has driven.

**F142 is now the only severity-A finding whose fix shipped and whose drive is genuinely owed.**
That is the shortest that sentence has ever been on this page, and it is the obvious next search —
except that unlike F140, F154 and F155, F142's own change document already says the drive is
missing, so this one is a build, not a grep.

**Revised 2026-09-09 (night window, iteration 3): `F142` is driven on both arms and closed, and it
does not take the severity-A list to zero — it moves by one and gains one.** The list is not the
"one" the paragraph above computed, either: the day window's classification pass later the same day
reads the open severity-A set as **`F299`, `F300`, `F301`** — all three are `DAY-3` decision material
and none is buildable unattended — with `F142` itself sitting in *conflict* rather than open. Closing
F142 leaves those three. **And this iteration files a fourth: `F306` (A)**, found by F142's own
row-four drive and living inside F142's repair — an agent that recorded the accepted implementation
evidence for a task was staffed to review it and approved its own work, because the exclusion set
reads three record sources and the evidence table is a fourth it does not read.

So: **F299, F300, F301, F306.** Three of them are the operator's to decide; the fourth is a defect
with a fix shape and no proposal, which makes it day-window material and not this window's to build.
The count is stated here rather than by editing any line above it, for the reason the paragraph two
above gives.

**Revised 2026-09-11 (night window, `n6-close`): the open severity-A list is five — `F299`, `F300`,
`F301`, `F306`, `F312`.** Computed with `py -3.11 scripts/classify_findings.py` over 315 sections,
not read off the paragraph above it. Three things about that line, and only the first is a count.

**`F309` and `F310` are the night's work and neither is on the list.** They were the approved change
`2026-09-10-the-control-that-asks-holds-the-keyboard`, built and driven across 2026-09-10/11, and
both sections now carry a `**Status:**` line naming the **two** commits each of them took — the
split is not bookkeeping, it is the shape of both defects, and a single-commit citation would have
been wrong in both cases. Every earlier revision on this page had to correct a list that went stale
between a filing and its repair; this pair was filed on the morning of 2026-09-10 and repaired
inside the same cycle, so no list above ever had a chance to name them.

**`F312` was never added to any list here, and that is the failure this page keeps having.** The
paragraph immediately above computes the open set as three plus `F306` — it was written on
2026-09-09, and `F312` was filed a day later by a different window. Nothing about it was wrong when
it was written. It simply stopped being true and nobody re-derived it, which is the same shape as
every banner this file has had to withdraw, only slower. That is why the number above is computed
in the sentence that states it.

**Below A, one section is newer than every census line on this page: `F315` (C), appended
2026-09-11 by this window's own drive.** The button that blocks a ticket gives no feedback for the
1.5-3 s the mutation takes, stays enabled, and a second press writes the move again. It is left
standing on purpose — every status move in that menu shares the gap, so it wants a change that owns
optimistic feedback for task mutations rather than a patch to one button.

**Corrected 2026-09-11 (day window, `D-5`), half-repaired the same day at `D-6` (`cb7c86b`): the
open severity-A set has SIX members, and the instrument prints `OPEN=5  CONFLICT=2`.** The revision
above is right about its method and wrong about its number, through no fault of the window that
wrote it — `F316 (A)` was filed by the day window hours later. But recomputing did not surface it
either, and `F317 (B)` says why: that finding's title contains the domain verb for choosing a
reviewer, and the classifier's own-heading arm read the participle as a verdict about the finding
rather than as a description of it. `D-6` repaired that arm and drove the repair over this file, so
the first half of the correction is now structural rather than a sentence: the B, C, D and `?`
census lines did not move at all, and `F316` left the done bucket.

**It did not land on `OPEN`, and the difference matters to anything that queues.** A second and
independent defect holds it at `CONFLICT` — `F318 (B)`, filed the same hour: the cross-section arm
strips quotation one line at a time, so the quotation of `F316`'s title inside `F317`'s own body,
which wraps, is read as a sentence about `F316`. So the reading of record is this. **The open
severity-A set is `F299`, `F300`, `F301`, `F306`, `F312` and `F316`. The instrument prints five of
them under `OPEN` and the sixth under `CONFLICT`.** That is the escalation blind spot 4 exists to
produce and is far better than the silent done verdict it replaced — a human scanning the output
sees the number now — but a window that queues *`OPEN`, A before B before C* and reads no further
will still walk past it. Until `F318` is repaired, **both numbers stay stated here so neither can be
quoted alone**, which is the arrangement the paragraph below spends its length arguing against and
which has now earned two consecutive days of its keep.

**This paragraph was written under `F313`'s rule.** Every verdict was captured before a word of this
close-out was edited and recomputed after, with the requirement that the only sections whose verdict
moves are the two the night repaired. That held. It is worth saying what the *before* run showed,
because it is `F313` again and in this file's own hand: one section sat at `CONFLICT` purely because
last night's new entry wrote *"…the focus defect in the same panel, fixed by the change whose drive
found this"* on a line naming one finding number. A single-number line about a finding's repair is
still indistinguishable from a verdict on a different finding, exactly as `F313` says, and the floor
it describes is where this landed.

**Revised 2026-09-12 (night window, `n8-close`): the open severity-A set is four: `F299`, `F300`,
`F301`, `F312`.** Computed with `py -3.11 scripts/classify_findings.py` after the edit, not read
off the paragraph above. `F306` and `F316` leave the set together, as two findings closed by one
change, `an-agent-that-recorded-the-evidence-is-the-author` (fix `4929ea0`, tests `40bd429`). Each
entry now carries its own Status line and its own evidence. The instrument prints all four under
`OPEN`, and the only severity-A `CONFLICT` left is `F52`, the long-standing one that really is
about its own finding. So the two-number arrangement the correction above had to keep is no longer
needed **for this set**. That is because the section `F318` misread now declares its own state. The
classifier arm itself has not changed, so it still misreads a wrapped quotation, and any future
section can land in the same place.

**Written under `F313`'s rule, and the rule held.** Every verdict was captured before a word here
was edited and recomputed after. The requirement was that exactly two verdicts move, `F306` from
open and `F316` from conflict, and nothing else. Stripped of line offsets, the B, C, D and `?`
verdict lists match across the two runs.

**Below A, this window filed one: `F319` (B).** A review refused on the scheduler path leaves the
refused reviewer holding the task. It has no proposal. Its worst leg, a refusal after the assignee
is staged, has not been verified, and if that leg holds the finding is an A. That makes it the day
window's first spec-loop candidate, not a night build.

**Revised 2026-09-13 (night window, `u8-close`): the open severity-A set is five: `F299`, `F301`,
`F319`, `F325`, `F332`.** Computed with `py -3.11 scripts/classify_findings.py` after the edit.
Before the edit it printed ten. Six of those ten were filed after the paragraph above:
- `F319`, raised to A;
- `F321`, `F323`, `F325`, `F331` and `F332`, filed as A.

Five leave the set together, closed by one change, `a-url-is-not-a-path` (fix `612b9c9`, driven
`f492261`): `F300`, `F312`, `F321`, `F323` and `F331`. Each entry carries its own Status line and
its own evidence. `F331` is the POSIX half. It is tested on CI's Linux job and not driven, and its
entry says so. `F312` and `F300` carry dated corrections: their URL claims held on Windows only.
`F332` is the same class of POSIX escape and is **not** closed by that change.

**Written under `F313`'s rule, and the rule held.** Every verdict was captured before a word here
was edited and recomputed after. The requirement was that exactly those five move from `OPEN` to
`RESOLVED`, and nothing else. Stripped of line offsets, the B, C, D and `?` verdict lists match
across the two runs. The only severity-A `CONFLICT` is still `F52`.

**Revised again 2026-09-13 (night window, `r9-close`): the open severity-A set is four: `F299`,
`F301`, `F325`, `F332`.** `F319` leaves it, closed by `a-refused-review-leaves-nothing-behind`
(fix `6ebcd9f`, driven `1b3d52c`), and `F320` (B) leaves the open B set with it (fix `997ff5d`).
Each carries its own Status line. Under the same rule, the classifier was run before and after:
exactly `F319` and `F320` moved from `OPEN` to `RESOLVED`, and the only new verdict is `F335`, filed
open as D by that change's close-out. Stripped of line offsets, every other list matches. `F326`,
`F327` and `F328` stay open, as that change said they would; so do `F333` and `F334`, which its
drive found.

**Revised 2026-09-15 (night window, `a-task-nothing-will-move-holds-nobody-drive`): the open
severity-A set is five: `F299`, `F301`, `F325`, `F332`, `F352`.** The paragraph above said four. It
was already one short before tonight's edit: `F352` was filed as A on 2026-09-13 and never entered
here, while the classifier counted it. `F352` stays open: the definition half shipped in `4b59ee0`
(reachability, driven and archived tonight), and the visibility half is still
`an-unstaffed-review-names-its-holders`. Under `F313`'s rule, the classifier was run before and after
the edit. Exactly `F372` (B, fixed by the same change) moved from `OPEN` to `RESOLVED`, and the only
new verdict is `F374`, filed open as B by the drive. Stripped of line offsets, every other list
matches, the A lists included.

**Revised 2026-09-15 (night window, `ledger-conflicts`): the classifier prints no `CONFLICT` at
all.** The four were hand-checked from code, git and CI, and each Status line now says what was found,
with its evidence: `F52` is `RETIRED` (closed 2026-08-27; the word was missing), and `F292`, `F335`
and `F338` are open. Three of the four conflicts were false leads from other sections: a line
about `F285`'s fix, a quotation in `F251`, and `F328`'s Status line. Each of those lines was
re-wrapped or re-quoted, and no words were changed. The open severity-A set is still the five above. Under
`F313`'s rule, exactly those four verdicts moved. Stripped of line offsets, every other list
matches.

### Two more defects, found the same day by an adversarial review that was told to falsify

**The first three below were found by me. These two were found by an Opus review agent spawned at
the operator's request and told to attack the instrument, and they are worse than the three.**

**4. The scanner could not see 46 headings, because it demanded a parenthetical.**
`## F77 — an agent has no way to address the operator` has no `(C)`. Two consequences, both measured:

- **26 finding numbers had no section at all** — F66, F67, F69, F72–F86, F130, F131, F132, F145,
  F148, F150, F151, F153. **The ledger holds 297 findings, not 271**, and every census ever run on
  this page — including all three of mine — was blind to 26 of them. **One is open: F77,
  `**Status (2026-10-12, night ledger-sweep-2): fixed** by `a-message-to-the-operator-is-told-where-the-operator-reads` (archived 2026-09-29; operator decision: a refusal only, no `notify_operator`). A send to `Operator`/`operator`/`USER` through the agent plane now answers 404 naming `update_task` and `ask_user`, reason `operator_not_a_recipient`; `hub/tests/test_a_message_to_the_operator.py` passes (50 passed across the six files run this sweep).`, severity C.** No count has ever included it.
- **Far worse: a heading the scanner cannot see does not *end* the previous section.** So an
  em-dash finding's whole body was appended to whichever paren-headed finding came before it.
  **F71's "section" absorbed F72 through F86 — 1,223 lines.**

**Seven verdicts were computed from a marker belonging to a different finding**, and **four were on
the STRONG arm this page called trustworthy**. Re-run after the fix, every one changed:

| | Was | Now | It had been reading |
|---|---|---|---|
| **F65** | RESOLVED | **OPEN** | F67's resolution |
| **F68** | RESOLVED | **OPEN** | F69's |
| **F149** | RESOLVED | **OPEN** | F150's |
| **F135** | RESOLVED | UNCLASSIFIED | F115's `RETIRED IN PART` |
| **F152** | RESOLVED | RESOLVED_ELSEWHERE | F153's |
| **F164** | RESOLVED | UNCLASSIFIED | `## F154 — Status: **FIXED**` |
| **F168** | RESOLVED | UNCLASSIFIED | `## F154 — Status: **FIXED**` |

**F168 is the sharpest.** Its own body says *"Not queued."* two clauses before the foreign marker,
and `if in_res:` gave RESOLVED unconditional precedence. **Three findings with explicit open
markers — F65, F68, F149 — were being counted as resolved.**

**5. The script printed a hardcoded verdict about itself.** One line read
*"RESOLVED_ELSEWHERE: lead only — 3 of 5 hand-checked FALSE"* as a **string literal**, not a
computation. By then the real count was 7 (now 9), and two of them — F185 and F266 — had never been
hand-checked while the header asserted *"Only F161 and F162 are real."* **A self-report that does
not recompute is a claim, not a measurement**, which is the same error as a banner.

**The rule these two produce, and it generalises past this script.** Defects 1–3 were about *what
the text says*. These are about *where the text stops*. **An instrument that segments a document
must be checked against the document's own structure, not only against its vocabulary** — and the
cheapest check is the one that found this: count the same thing two ways and reconcile the
difference. `grep` said 297 heading numbers; the script said 271; nobody reconciled 26 for a day.

### Three defects the instrument had, each found by measurement and not by review

1. **The heading regex demanded exactly `(A)`…`(D)`, so 13 sections were invisible** — `F9 (A-)`,
   `F104 (—)`, `F115 (B?)`, `F123 (C, open)`, `F165 (new, severity **B**)`, `F167 (B, new)`,
   `F266 (C, was B)`, `F290 (RETRACTED, was B)`, `F296 (C, harness)` and four more. Found by a count
   mismatch — 271 by `grep`, 258 by the script — not by reading the code. **A first pass reported 147
   unclassified on the broken regex; the real figure is 111.**
2. **The cross-section arm could not fire.** It reused `Status:`-anchored patterns, but a drive
   record elsewhere says *"F154 stays **FIXED**"*, never *"Status: FIXED"*. So the arm built
   specifically to catch the F140/F154/F155 failure reported **0**, which read as a result and was an
   artefact of its own pattern.
3. **Quoted history was read as current status.** A section that withdraws its own banner *quotes*
   it — *"…so this entry stays open until somebody re-drives it."* — and the classifier matched
   `stays open` inside the quotation. **Every section that narrates its own correction was at risk of
   reading OPEN.** This is the banner disease in software form: believing a sentence without asking
   whether it is being asserted or withdrawn. Fixed by blanking quoted, blockquoted and
   struck-through spans before matching.

**Defect 3 was found because a mutation test failed.** Stripping F154's in-section resolution should
have made it `RESOLVED_ELSEWHERE`; it returned `OPEN` instead, from the quoted banner. Had the
mutation passed, the instrument would have shipped with an inflated open count and nothing would have
contradicted it. **A fourth mutation — injecting `Status: not fixed` — confirmed the negation guard
holds**, which is the trap the 2026-09-06 recount hit.

**The single failure mode behind every error found, in all three defects and in all four hand-checked
false positives: a sentence that mentions finding X while resolving finding Y.** F32's match was
*"rather than fixed alongside F32"*; F108's was *"the drive that closed this also **opened** one"*;
F272's was a *note* being superseded; F187's was *"(F185 is the archived case … not a defect in this
one.)"*. **Prose is not a status field**, and no regex over this file will ever fully be one.

### What this changes

**The excluded population is 111, not ~147, and it is genuinely unread.** Four were sampled at
random earlier today — F215, F222, F237, F281 — and **four of four were real, unfixed defects absent
from `ROADMAP.md`**, including one (F222) whose own docstring calls its state *"the exact governance
failure loops exist to make impossible"*. That sample is small and was not re-drawn; it establishes
that the population is not noise, and nothing more.

**Re-run it with `py -3.11 scripts/classify_findings.py`.** It writes no files and takes about a
second. The three arms are not equally good and the script says so before it says anything else —
use `RESOLVED`-strong as fact, `OPEN` and `UNCLASSIFIED` as a worklist, and `RESOLVED_ELSEWHERE` and
`NOT A DEFECT` as leads that need a human.

**And one observation that outranks any single row of that table.** F88, F89 and F90 were found in
one iteration, in three unrelated subsystems, and every one of them was a mechanism this repository
tests *thoroughly* — against a state the product never produces. F88's access tests pass a
`visibility` value nothing stores. F89's generation tests spawn with nothing else writing, when in
production the only thing that reaches that path is a live turn streaming output. F90's collision
test ends the holder's run with a database write and then performs, by hand, the exact scheduling
call the product omits. **When a test has to set something up for the code to reach the state under
test, ask who does that in production.** If the answer is "nothing", that is the defect, not the
fixture.

---

<!-- followed F42 in FINDINGS.md -->
## The live re-drive, 2026-08-25 — what the fixes did against a running Hub

Task 8.6/8.7. Everything above was unit-verified when it shipped; this is the same set driven
against the trial Hub on port 8010 after restarting it on the new code, in project
`proj-bacb623ca9ba` (`aw-sweep`). `GET /health` returning `{"status":"ok","runtime":"native"}` — the
`runtime` field is new in this change — is what confirms the restart took.

`job-e2c18b2d` ("Hourly test check", 36 firings) was **disabled first**, at the operator's
direction, so nothing fired on the new code during the drive.

| Finding | Verified live | How |
|---|---|---|
| **F27** (A) | **Yes, by a real agent** | See below. |
| **F28** (B) | **Yes** | The flow's queue was `{}` with all five tasks carrying `loop_id = NULL`. Re-declaring the document (`PATCH .../jobs/job-ccb60a3cb3f6`, `spec_document_id: spdoc-3e0dbec860d0`) adopted every one: `{"approved": 2, "completed": 2, "under_review": 1}`. |
| **F29** (B) | **Yes, both surfaces and both directions** | Appending a byte to an approved document made the listing report `diverged: true` and the single read carry recorded/found digests plus the detail. Restoring the file cleared it — content-keyed, not a sticky flag. A `touch` with identical bytes stayed `false`, which is Key decision 5's whole point. |
| **F30** (B) | **Yes** | `architect`, `builder` and `critic` still carry `self_registered = 1` **with** a non-null `runner_id` — the reachable state the finding describes. All three now report `runnable: true` on their real runner instead of `runner=native cli=architect runnable=False`. The probe and the spawn agree. |
| **F31** (B) | **Yes** | All four measured false positives pass through intact (`spread-fairness-metric-fix-for-idle-staff`, `mcp__agentweave__submit_spec_document`, `mcp__agentweave__record_evidence`, `this_is_a_perfectly_ordinary_function_name`); all three credential shapes still redact. Exercised against the module, not a rendered transcript. |
| **F32** (B) | **Yes, both branches** | `dev` (withheld) receives `### You cannot decide evidence` with the three lines including where a verdict goes instead; `rev` (granted) receives `### You can decide evidence`. |
| **F33** (B) | **Yes** | `POST /jobs` with `agent: "nosuchagent"` → **400**, *"agent 'nosuchagent' is not one of this project's agents, so this job could only ever fail. On the roster: author, dev, probe, rev."* Refused at creation instead of failing silently every cron tick. |
| **F34** (B) | Yes, previous session | `status`/`doctor` against port 8010 and profile `beta`. |
| **F35** (C) | Module level | The refusal named the field, the shape and a working example, one at a time. **Then reversed at the operator's direction** — see below. |
| **F36** (C) | **Yes, every path** | `201 added`; cycle → **409** naming both tasks; self-edge → **400**; unknown id → **404** naming both; a repeated edge → **201 `duplicate`**, which the route documents as deliberate ("an operator who clicks twice has not made a mistake"); `DELETE` → **204**. |
| **F37** (C) | **Yes** | `spec/changes/teal-manticore/spec.html`, in `exploring`, archived successfully with `tasks_created: []`. This was a hard refusal before. `GET /spec/drift` is now empty. |
| **F38** (B) | **No — and that is the finding.** | See F41. Fixed here, and the fix re-driven live: the same scenario now records `turn_produced_nothing`. |

### F27, driven by a real agent rather than asserted

The sharpest result of the drive. `task-326f5f62de51` was created, moved to `in_progress` **by the
operator** so that no run held it, and `dev` was triggered with instructions to call
`update_task(task_id, "completed")` and report the result verbatim. It did, and got:

```
Hub rejected PATCH /tasks/task-326f5f62de51 (403): This run cannot complete task
task-326f5f62de51: it is not working any task. A run finishes the task it took, and takes at
most one. To work this task, start a run bound to it — or, if you meant to report on work you
did not do, say so rather than moving its status.
```

The task stayed `in_progress`; `run-041af4d5a3f8` ended with `task_id = NULL`, having never bound.

The old behaviour is preserved in the same agent's earlier transcript rows, which is as close to a
controlled before/after as this gets — an unbound run walking two tasks `pending → assigned →
in_progress → completed`, reasoning aloud: *"these tasks aren't assigned to me... I should assign
them to myself first, mark them as in_progress, and then complete them."* That is F27's exact path,
and it succeeded then. See **F42** for what that reasoning can still achieve, and why.

### What the drive found that unit tests had not

**F41 (A)** — F38's fix cannot fire. Found by driving the case rather than reading the code, then
confirmed against the original subject's own event log. Recorded above, and fixed.

**The fix was then verified the same way it was found**, which is the whole point: a defect whose
lesson is *"the unit tests said yes and production said no"* must not be closed on unit tests alone.
The Hub was restarted on the fix and the identical scenario re-run — a fresh document
(`spec/changes/sapphire-unicorn/spec.html`, `content_digest` populated at creation exactly as
before), `dev` triggered against it with `spec_document` set and told to reply in prose only:

```
turn_produced_nothing   dev   severity=warning
{"run_id": "run-4c14c8077442", "agent": "dev",
 "spec_document": "spec/changes/sapphire-unicorn/spec.html",
 "document_phase": "exploring", "run_exit_status": "completed"}
```

`run-4c14c8077442` completed with `task_id = NULL`, wrote 0 questions, and the document carried
exactly 1 `content` event — the scaffold. Before the fix this produced **nothing**.

The negative cases — a turn that asked, a turn that wrote the document, a turn given no document —
are covered by unit tests only; each would have cost another real run to drive, and none of them was
the case that was broken.

### Dispositions the operator made on 2026-08-25

- **F22** — fixed. `doctor` gained `check_symlink_privilege`, which probes a directory symlink and,
  on this machine, reproduces `WinError 1314` and names the one setting that fixes every worktree
  at once. A warning rather than a failure: the Hub runs correctly without it.
- **F24** — fixed. The run row leads with its own status, coloured by `runStatusColor`, and keeps
  the trigger as a muted qualifier. A refused firing now reads `skipped scheduled`, which is what
  both user test guides tell the operator to look for.
- **F25** — fixed. A `n refused` chip beside `0 runs`, drawn from the history the card already
  holds. Neither count was wrong; naming the refusals is what makes the two agree.
- **F26** — fixed at the source, not in the renderer. `current_tasks[].agent_role` now says which
  of `working`, `next` or `assigned` the name means, because the merge that produces it is the only
  place that still knows — by the time the board sees the name, in-flight work and a firing's
  selections are indistinguishable. The card renders `next: relay` for a completed task's
  prospective reviewer and the bare name, unchanged, for an agent mid-turn.
- **F35** — **reversed.** The seven `submit_spec_document` fields advertise `object`/`array` again.
  `_check_submit_shapes`, `_SUBMIT_SHAPES` and `MalformedCallError` were removed with them rather
  than left in place: the framework validates before the body runs, so with the annotations
  restored nothing could ever have reached them. Leaving them would have created a second F41 in
  the same session that found the first. `test_the_structured_fields_advertise_their_shape` holds
  the choice, and the parameter list records what reversing again would take.
- **F39** — fixed, **and verified live in both directions.** `recall(observation_id)` now carries
  the same grant caveat `decide_evidence` already had, and an `### Other agents' history` section
  states both checkpoint grants in both directions. Against the restarted Hub: an ungranted agent
  reads *"You may read your own checkpoints and no one else's"*; granting both to `rev` switched it
  to *"You may read your peers' checkpoints"* immediately, and withdrawing them switched it back —
  so the operator's switch is reflected in what the agent is told, which is the half
  `test_the_operator_grants_it_and_reads_it_back` exists to protect for the evidence grant. Stated even when both are withheld, which is the half worth defending: `recall`
  answers **not-found** rather than refusing — it has to, or the refusal would itself confirm the
  record exists — so an agent that meets the boundary without being told concludes the record is
  missing rather than that it is not permitted to see it.
- **F40** — **largely fixed, and the cause was not what the finding guessed.** Recorded in full
  because the diagnosis is the useful part.

  The finding proposed that `for task in list(_background_runs): await task` snapshots the set and
  so misses a run scheduled but not yet registered. That is true and it is fixed —
  `_settled_redrain_runs` drains and re-checks until the state the test asserts on actually holds,
  with a bounded deadline that names the run statuses it gave up on. But replacing the snapshot
  alone did **not** make the test green; it made it fail *deterministically* under load, which is
  how the real cause surfaced.

  Running this file immediately after `test_conversation_contract.py` failed every time, with
  `assert 2 == 1` — **two** runs on one conversation, both `failed`, where the isolated run was one
  and `completed`. The cause is the scope of the `PtySession.spawn` patch: the redrain starts its
  run as a background task that spawns *after* the request has returned, and the patch closed at
  the end of the request. Lose that race and the run reaches the real `PtySession.spawn`, fails for
  want of a `claude` binary, and the product then does exactly the right thing —
  `return_run_entries` puts the entry back and a second run picks it up. Two failed runs where the
  test asserted one completed one. Awaiting the settle inside the patch closes it.

  **Measured after both changes:** the deterministic repro is green, and 24 of 25 runs of the
  four-file combination pass, against 4 of 5 before. A full-suite run also went green at
  3103 passed. **One failure in 25 remains and its message was not captured** — the dominant cause
  is fixed and a residual race is not ruled out, so a red run here still deserves reading rather
  than dismissing.

  Two things worth carrying: a narrowly-scoped `patch` around a call that schedules background work
  is a bug of the same shape wherever it appears, and the snapshot idiom itself still survives in
  `test_accounting_budget.py:191` (`test_conversation_contract.py` and `test_agent_trigger.py`
  already loop on the set and are not exposed the same way).

---

<!-- followed F42 in FINDINGS.md -->
## What held, under a full-surface sweep

Recorded because a report listing only defects describes a product that does not exist. Each of
these was driven, not read.

- **The task transition machine.** Every illegal jump refused `409` with a string naming what *is*
  reachable. Every non-entry creation status refused `422` naming the two that are legal. No refusal
  needed a second call to interpret.
- **The requirement gate, at `gate` rigor.** Refused approval, named the requirement, its state, the
  remedy, and the alternative: *"Satisfy them, or lower the document's rigor — which is recorded."*
- **The whole spec → work → evidence → merge chain.** An agent read an approved document, edited in
  its own worktree, ran the suite, and recorded evidence carrying a git footprint with
  `reachable_from_main: false`. A second agent **on a different CLI** reviewed it. Accepting the
  evidence moved coverage to `verified`; approving the task merged `75ebebce` into `master`.
  Verified independently: the fix is correct (old `spread` = 0 on the idle case, new = 2), the suite
  went 6 → 7, and `master` carries the change.
- **`ask_user`.** Two blocking questions, batched, with structured options; the run held open;
  answering released it. Exemplary — see F38 for the half that is not.
- **Permission postures.** `manual` produced a card showing the exact command. Denial by timeout was
  honoured (`expired`, file absent). Explicit approval let the command run and the file appeared.
- **One run per agent.** Two simultaneous triggers: one `running`, one `queued` with
  `waiting_reason: "agent is already running"`. The second ran when the first finished.
- **Stopping a run.** `stopping` → `stopped`, cleanly, mid-flight.
- **`repo_hygiene`.** Wrote five ignore rules into `.git/info/exclude` of a repository the Hub did
  not create. (`.agentweave/project.json` is not among them, and is machine-local — worth adding.)
- **The dashboard.** All thirteen screens rendered with **zero console errors**. Empty board columns
  explain what would land in them. A task that could not merge said exactly why — *"no accepted
  evidence names a commit, so there is nothing to merge"* — and offered `Try again`.

---

<!-- followed F72 in FINDINGS.md -->
## Live drive, 2026-08-27: work is isolated per task (task 8.8) — **no defect found**

Driven against the trial Hub on 8010, restarted from source onto this change's code. The Hub was
confirmed by its **project list**, not `/health`, because a Hub on a stale database still answers
`{"status":"ok"}`. Migrations `0095` and `0096` applied to the beta profile on startup; the database
was backed up to `agentweave.db.bak-pre-0096` first.

Script: `scripts/drive/t_task_isolation.py`. Throwaway projects `proj-1b7c4196a041`
(`drive-f58-2026-08-27`) and `proj-1c3a...` (`drive-f58b-2026-08-27`), both created for this.
Neither `proj-5e960453` nor `proj-18e5d4e0` was touched, which was the condition attached to
implementing this change unattended.

**What the drive did.** Two tasks for one project, each provisioned through `ensure_task_worktree`,
a commit made in each task's own checkout, evidence recorded by the operator naming the *first*
task's commit, then the first task approved.

**What held — the whole point, and worth recording as much as a break would be:**

| Observed | |
|---|---|
| Each task got `.agentweave/tasks/<id>` on `agentweave/task/<id>` | per-task provisioning, live |
| `git branch --contains` on each tip named **only that task's own branch** | the two are siblings of `main`, not of each other — this is F58's absence, stated positively |
| Approval merged `a8e7bbc7189c` and nothing else | "Integrate approved work \<sha>" |
| The second task's commit is **not** on `main`, and `second.py` does not exist in the working tree | **F58 does not reproduce** |
| The approved task's checkout was removed, its branch kept | design D5 |
| The **un**approved task's checkout survived the other's approval | design D5, and task 6.10's decision holding |

**F71's fix was exercised in the same run, and worked.** The operator recorded evidence with the
task's commit sha as `locator`; the footprint captured that commit, on the task's branch, with
`reachable_from_main=False` — the exact field whose wrong value was F71's harm. Under the old
behaviour it would have footprinted the operator's own checkout, sitting on `main`.

**One thing the first attempt got wrong, and it was the drive rather than the product.** The first
run approved a task with no accepted evidence and nothing merged. That is correct behaviour, stated
plainly by the integration record — `outcome: skipped`, *"no accepted evidence names a commit, so
there is nothing to merge"* — and the reason `main_branch` looked unset was that the drive PATCHed a
route that does not exist (405) while `POST /projects/open` had already auto-detected `main`
correctly. Recorded because a reader of the first transcript would otherwise read a skipped
integration as a defect.

**Left live:** both throwaway projects and their repositories, with the task branches intact, so the
state described above is inspectable rather than merely reported.

---

<!-- followed F121 in FINDINGS.md -->
## Row 12 FLOWS and row 16 WORKTREES — driven end to end, and what held

Both rows were `not reached` in every previous sweep. Driven 2026-08-29 on 8011 against this
branch's code, in a fresh git project (`drive-wt-0829`, `proj-dc4d43543bea`) with three Haiku agents.

**Row 16 — worktree isolation held completely.** Two agents, two tasks, both told to edit `calc.py`:

- each got its own checkout at `.agentweave/tasks/<task-id>/` on its own branch;
- both edits landed, on their own branches, as `Auto-snapshot: <agent>'s turn on <task>` commits;
- **`main` was untouched** — `git show main:calc.py` still had only `add` and `sub`;
- `GET /worktrees/conflicts` named both *task* workspaces (not the agents) and the one conflicting
  path, `calc.py`, which is exactly what `ConflictInfo`'s docstring promises;
- `GET /worktrees/<agent>` listed each agent's task checkouts with `provisioned: true` and
  `grandfathered: false`, and provisioned nothing by being read.

**Row 12 — a flow decomposed an approved document and reviewed its own work.**

- Two independent tasks materialised onto the board from the approved document, into the flow's
  queue, with their requirement links intact (`FR-1`, `FR-2`).
- The first firing started **both** in parallel, one per agent — the property that distinguishes a
  flow from a loop, and it works.
- With a third agent present, a later firing resolved `gamma` — idle, holding no work, **not the
  author** — as reviewer for `alpha`'s completed task, moved it to `under_review`, ran a real review
  turn, and `gamma` approved it. The whole ladder, live.

**Refusals that held, each naming what would work instead.** Every one of these was provoked
deliberately:

```
completed -> under_review, author still assigned
  403 "...it is still assigned to 'alpha', the agent recorded as completing it, so the move would
       claim its own author is reviewing it. Assign a different reviewer, or clear the assignee to
       review it yourself. Left as is, the task is claimable by nobody and 'alpha' counts as busy
       for every other review in this project."

completed -> approved
  409 "Cannot move a task from 'completed' to 'approved'. From 'completed' the available
       transitions are: rejected, under_review."

record_evidence, same requirement, same task, same commit, twice
  409 duplicate_evidence "...Recording the same demonstration twice makes the reviewer decide once
       per copy and overstates FR-1's evidence count. If the wording is wrong, say so on that piece;
       if the work has moved on, commit it first so the new evidence names the commit it
       demonstrates."

integration retry on a task in 'completed'
  409 "Cannot retry integration for a task in 'completed': only an approved task has work to
       integrate."
```

The agents *read* the duplicate-evidence refusal correctly — alpha's transcript reasons "evidence
for FR-1 has already been recorded" and moves on rather than retrying.

---

<!-- followed F122 in FINDINGS.md -->
## Row 17 INTEGRATION — driven end to end, and it held

The same sequence covers row 17, which had not been driven on this branch. Beyond the merge itself:

- the *second* target, `HEAD` — gamma's detached review checkout, pointing at the same commit — was
  attempted and **skipped** with `"2da8dc9ad076 is already in main; there was nothing to merge"`
  rather than merged twice;
- `integration-preview` before the accept said `will_merge: false` with the same sentence the
  skipped integration later recorded, so the operator could have predicted the outcome without
  attempting it;
- the refusal on a `completed` task (*"only an approved task has work to integrate"*) and the
  refusal with no accepted evidence are two different sentences for two different causes.

**One blemish, noted not filed:** the merged integration row reads `actor_kind: "operator"` with
`actor: ""`. Same shape as F120 one table over — the record knows what kind of actor it was and does
not name it. Not raised as its own finding because there is exactly one operator per instance today,
so the empty string is unambiguous rather than wrong.

**F75's fix confirmed live.** `gamma`, reviewing `alpha`'s work, recorded its own
`manual_observation` (`ev-1cb189450dc8`) against `FR-1` with the *same digest* as the author's
`implementation` evidence, and it was **accepted, not refused as a duplicate** — while `alpha`
re-recording its own claim in a later turn *was* refused. The rule distinguishes a second author
claim from an independent confirmation, which is exactly what F75 asked for.

<!-- followed F122 in FINDINGS.md -->
## Row 19 RESILIENCE, two of three parts — driven, and both held

**Two concurrent triggers for one agent.** Two `POST .../agent/trigger` calls for `alpha` fired from
two threads, 19 ms apart, into two different conversations. Neither raced, neither was lost, and
each was told something *different and correct*:

```
trigger A  status "queued"  waiting_reason: "an older conversation's queued input is being
                                             delivered first (run run-6a2a3219b785)"
trigger B  status "queued"  waiting_reason: "agent is already running"
```

Both entries then ran, in arrival order, in their own runs:

```
entry-30b613696046  arrived 16:07:32.951  delivered 16:07:33.379  run-6a2a3219b785  ended :43.055
entry-3fbc4defcd68  arrived 16:07:32.970  delivered 16:07:43.305  run-e18f0ca41828  started :43.306
```

`delivery_attempts: 0`, `abandoned_reason: null` on both. `turn_scheduler`'s per-`(project, agent)`
lock is doing exactly what `SURVEY.md` credits it with, and the *reason* the loser was given names
the run that beat it rather than a generic "busy".

**Stopping a run mid-flight.** `POST .../agent/{name}/stop` eight seconds into a real turn:

```
200 {"success": true, "message": "Stop signal sent to beta (run run-c5fb49f86c77).",
     "status": "stopping"}

runs:        status "stopped", exit_code 2, ended 8.2s after it started
event_logs:  run_stopped  severity "info"  exit_code 2
agents:      beta idle within 4 seconds
queue entry: state "delivered", abandoned_reason null
```

`stopped` is its own status, not `failed`, and the event is `info` rather than an error — which is
the right reading of an operator doing something deliberate. This is the same family as **F94**
(*"kill an agent and the product tells you `exit 4294967295`"*): a deliberate stop is now legible.

**Not driven:** killing the Hub with a run in flight (`run_reconciliation`). Left for a later
iteration — it needs the trial Hub restarted mid-turn, and this iteration's Hub was carrying an
unrelated fix under test.

**A stopped run keeps everything it produced** — settled by repeating the stop at twenty-five
seconds rather than eight, because one run could not distinguish "the stop discarded buffered
output" from "there was nothing yet":

```
run-5bc7ea3b2dcb  started 16:09:59.507  stopped 16:10:24.781  exit_code 2
agent_outputs:    20 rows, first at 16:10:08.046, last at 16:10:23.309
```

The last row landed 1.5 s before the stop took effect, and the transcript is complete up to it. The
earlier eight-second stop's empty transcript was therefore honest: this model's first output row
arrives 8.0-8.5 s after start on this machine, every time it was measured today, so that run had
genuinely produced nothing. **No finding** — recorded because an empty transcript after a stop looks
exactly like discarded output, and the next reader deserves the measurement rather than the worry.

<!-- followed F122 in FINDINGS.md -->
## Row 19 RESILIENCE, the third part — the Hub killed with a run in flight. It held.

Driven 2026-08-29 17:45-17:50 on 8011 against this branch, `scripts/drive/t_row19_crash.py`. This
is the half the paragraph above left open. Two specimens, one per agent, both hard kills
(`Stop-Process -Force`, so `lifespan`'s `terminate_all_active_runs()` never ran — a crash, not a
bounce).

**Nothing is orphaned, and that is measured rather than assumed.** The `Run` row's `pid` is the
CLI itself, and it dies with its Hub:

```
hub pids 28980 (py.exe launcher) -> 22604 (python.exe, uvicorn)
  22604 -> 25712 OpenConsole.exe      after Stop-Process -Force: gone
  22604 -> 19688 claude.exe           after Stop-Process -Force: gone   <- runs.pid = 19688
```

This matters because `reconcile_interrupted_runs` **skips** any run whose `pid_alive(run.pid)` is
still true. Had the ConPTY child survived its parent — which is the ordinary Windows expectation,
nothing reaps a grandchild — every crashed run would have stayed `running` forever and wedged its
agent, since `POST /agent/trigger` refuses while a run is in progress. The pseudoconsole closing is
what makes the reconciler's precondition true here, so the good outcome rests on a property of
ConPTY, not on anything the reconciler does.

**The restart tells the truth and then does something about it.** Specimen one, `alpha`, killed 20 s
into a turn:

```
16:46:40.653  run_triggered     run-7b910e688f68
16:46:40.757  run_started
   ~16:47:00   Stop-Process -Force on the Hub
16:47:00.720  run_interrupted   pid 20504, returned_entry_ids ["entry-68dd93ce09b2"],
                                abandoned_entry_ids []          severity warn
16:47:04.115  run_triggered     run-179b80185f46   session_mode "resume"
16:47:04.135  queue_entry_delivered  entry-68dd93ce09b2  <- the SAME entry, redelivered
16:47:30.420  run_completed     exit_code 0
```

Four seconds from the Hub answering again to the operator's message being back in a live turn, with
no operator action at all. That is `_schedule_or_defer`'s deferred re-drain firing off the first
request the restarted Hub served — the path whose docstring says it exists because
`reconcile_interrupted_runs` runs before the Hub knows its own address. It works.

Specimen two, `beta`, reproduced it: `run-63d92186c7b6` -> `interrupted` at restart, `run-5aed9335cb5a`
started within seconds on the same input.

**The redelivered agent is told it is a redelivery.** From the resumed run's own transcript:

> *"The note says 'delivery attempt 2; an earlier attempt was cut off before it finished' — so this
> appears to be something that was interrupted and needs to be completed."*

`inbound_queue.py:116-119` composes that line, and the agent read it and acted on it. A redelivery
that looked like a first delivery would make the agent redo completed side effects silently.

**Accounting records the crash rather than dropping it.** `unavailable_turns` went 2 -> 3 (alpha's
0 -> 1) across the crash, so the interrupted run has exactly one outcome and it is `unavailable`,
not a zero and not an absence — which is `usage-accounting`'s stated rule, reached by the crash
path.

**A trigger arriving during the recovery is queued, not lost or refused:**

```
POST /agent/trigger  200  {"status": "queued", "run_id": null,
                           "waiting_reason": "agent is already running"}
```

It ran as `run-ec7005e6f593` the moment the resumed run ended.

**No finding. Two things worth knowing anyway.**

- **Three crashes withdraw an operator's message.** `return_run_entries` counts a delivery attempt
  per interruption; at `RESUME_RETRY_LIMIT = 2` the conversation's `provider_session_id` is cleared
  (the agent loses its provider-side context) and at `DELIVERY_ATTEMPT_LIMIT = 3` the entry is
  `withdrawn` with `abandoned_reason` set. Both constants carry a written rationale that names this
  case explicitly ("Fewer, and a Hub restart could discard an operator's message"), so this is a
  decided trade-off, not a defect — but an operator whose Hub crash-loops three times loses the
  message, and the only breadcrumb is `delivered_in_run_id` on a withdrawn entry.
- **`pid_alive` is a pid-existence check, not pid+identity**, as its own docstring says. A Hub down
  long enough for the OS to recycle the pid reads the run as still alive and never reconciles it.
  Not reproducible on demand and already written down at `pty_runner.py:142-147`; recorded here
  because this row is the one place the consequence is visible — the run stays `running` and its
  agent is wedged with no way back except another restart.

**What is not covered by this row even now:** a Hub killed while a *permission card* or a *question*
is open (the reconciler calls `expire_pending_for_run`, which this drive never exercised because
both specimens ran in default posture), and a crash while a run holds a task (`divergences_to_evaluate`
is only populated for `run.task_id`, and neither specimen was task-bound).

<!-- followed F122 in FINDINGS.md -->
## Row 19 x row 14 — the Hub killed while an operator's decision is on screen. It held.

The crash drive above ran both specimens in default posture, so `reconcile_interrupted_runs`'
call to `expire_pending_for_run` was never reached. Its comment is the reason it exists — *"a Hub
bounced while an operator decision was on screen leaves a row nobody will ever poll again"* — so
this drives that, `scripts/drive/t_row19_crash_card.py`, 2026-08-29 17:54.

```
17:54:50  card perm-acc79b61af1d  status "pending"   run-2f56b98d86f3  tool Write
   ~:58   Stop-Process -Force on the Hub
17:55:0x  restart
          card perm-acc79b61af1d  status "expired"   decided_at null   decided_by null
          run-2f56b98d86f3        status "interrupted"
          GET /permission-requests  -> the card is gone from the operator's list
POST .../perm-acc79b61af1d/decide {"allow": true}
   409 {"detail": "this request was already expired; the run has moved on"}
17:55:10  perm-3d4bae2c9135  a FRESH card, run-67f5dee85c34, same Write
          {"allow": true} -> 200, and card_crash_note2.txt exists in gamma's worktree 2s later
17:55:15  gamma idle
```

Twenty seconds from crash to the operator being asked the same question again by a live run, and
the stale card cannot be answered into a void — the `409` names *expired* rather than the generic
"already decided", so the operator can tell "I was too slow" from "the Hub died under me".

**`decided_at` is null on an expired card, and that is right.** Nobody decided it. It matters
because a client that asks "is this card still open?" with `!decided_at` reads an expired card as
answerable — **this harness did exactly that on its first run**, and the mistake was invisible
because the list route hides expired rows by default (`pending_only`). Checked against the UI
rather than left as a worry: `permissions.ts` types `status` as the four-value union,
`PermissionRequestCard.tsx:66` selects on `status === 'pending' || status === 'expired'` and
renders the expired one `is-stale` with a dismiss button and no answer buttons. The UI reads the
field that carries the answer. **No finding.**

**A harness bug that would have shipped a false verdict, recorded because it is the more useful
half of this row.** The first run of `t_row19_crash_card.py` posted `{"decision": "allow"}` — the
field is `allow`, a bool — got a `422`, and scored it as *"deciding a dead card is refused"*. It
proved only that the harness could not spell the request. Worse, the same typo then failed to
answer the **fresh** card, which expired 120 s later (`permission_denied`: *"no operator answered
within 120s, so this was not approved"*), and the run completed without writing the file — which
the harness scored as *"the work completed after the crash"* because it was watching the agent go
idle rather than watching the file appear. Two green verdicts, both false, from one typo in a
request body. The re-run asserts the artefact (`os.path.exists`) and the exact status code
(`== 409`, not `>= 300`), which is what a verdict has to do to be worth reading.

That is F116's own lesson arriving from the other side: **F116 forbade extras so a misspelled
field is named rather than absorbed, and here the named refusal was still misread by the client
that caused it.** The `422` did everything right. A drive that only checks "did it refuse?" learns
nothing from a good refusal.

<!-- followed F122 in FINDINGS.md -->
## Row 19 x row 8 — three crashes on one task-bound run: the input is abandoned, and the operator is told

`reconcile_interrupted_runs` has a branch nothing had ever reached:

```python
if run.task_id and not returned_entry_ids:
    divergences_to_evaluate.append(run.id)
```

`returned_entry_ids` is empty only when `return_run_entries` gave up, which is
`DELIVERY_ATTEMPT_LIMIT = 3` — so the branch needs the Hub killed **three times on the same
input**. That is also exactly the case the crash drive above filed as *"an operator whose Hub
crash-loops three times loses the message"*, so `scripts/drive/t_row19_crash_task.py` drives both
at once: a task assigned to `beta`, a run bound to it, and three hard kills in four minutes.

```
entry-06b6c75505dc  task-d1ae1dfe5124  delivered, attempts 0
crash 1 -> state "queued",     attempts 1, provider_session_id 7824ae64-… kept
crash 2 -> state "queued",     attempts 2, provider_session_id NULL      <- RESUME_RETRY_LIMIT
crash 3 -> state "withdrawn",  attempts 3, "delivery failed 3 times; the Hub stopped retrying"
```

Every constant behaved as its comment says, including the middle one nobody would notice: at the
second failure the conversation's provider session is dropped, so the third delivery starts fresh
rather than re-killing the runtime on a session that cannot be resumed.

**The message is gone, and nothing about that is silent.** After the third crash:

| Surface | What it says |
|---|---|
| `GET /tasks/{id}` | `status: "in_progress"`, `has_open_divergence: true` |
| `GET /tasks/divergences/recent` | `div-6c07fa8009fb`, `run_exit_status: "interrupted"`, `task_status_at_end: "in_progress"`, `outcome: "surfaced"` |
| `GET /queue/beta` | the entry, `state: "withdrawn"`, with its `abandoned_reason` |
| `GET /agent/beta/chat/{conv}` | the operator's own message, `delivery_state: "abandoned"`, reason attached |
| `AgentTimeline.tsx:787-808` | renders that as a red **"not delivered"** chip *with the reason beside it* |

The task does not silently sit in `in_progress` looking like work in flight: the divergence is
raised on the crash path, by the same `evaluate_run_end` the ordinary end-of-turn path uses. This
is the S6-adjacent worry answered in the product's favour.

**Two measurements taken because the first reading of them was wrong.**

*Output produced before a crash is not discarded.* The three abandoned runs had **zero** stored
output rows each, next to a completed run of the same work with sixteen — which reads exactly like
a crash eating the transcript. It is not. Killed deliberately *after* rows existed:

```
run-1036804a218c  4 rows at t+9.1s (thinking, text, tool_use, tool_result)
  Stop-Process -Force
  rows immediately after the kill: 4
  rows after the restart:          4
```

`record_agent_output` commits per event, and a committed row survives its Hub. The zero-row runs
were killed **before this model's first output row**, which lands 8.0-8.5 s after start on this
machine — measured twice today, once for the stop half of row 19 and once here.

*An interrupted run's `ended_at` is the restart time, not the crash time.* `reconcile_interrupted_runs`
sets `run.ended_at = now()`, and "now" is whenever the Hub came back:

```
started_at 17:00:28.66   killed ~17:00:37.6   ended_at 17:00:42.29
lived ~9 s; the row claims 13.6 s
```

That is what made the zero-row runs look impossible — their durations are inflated by however long
the Hub was down. **Not a finding today, because `ended_at` is on no response schema and no UI
component reads it** (checked, not assumed). It becomes one the moment a run duration is surfaced:
a Hub that crashes at midnight and restarts at nine reports a nine-hour run. Whoever exposes it
should bound it by the last `agent_outputs` row for the run, which is the only honest upper bound
the Hub still holds.

<!-- followed F122 in FINDINGS.md -->
## Row 19 x row 13 — the Hub killed while `ask_user` is blocking. Nothing expires the question, and nothing needs to.

The card half of this is handled by an explicit pass (`expire_pending_for_run`). Questions get
none: `run_reconciliation.py` does not mention them. That asymmetry is what this drove
(`scripts/drive/t_row19_crash_question.py`), expecting to find a question left claiming an agent
was waiting on it forever. It is not there, and the reason is worth writing down.

```
17:03:16  run-641a10f7c182 starts, calls ask_user, blocks
17:03:27  q-3b7e6cc781f2  "Which colour should the badge be?"  asker_waiting true
   ~:33   Stop-Process -Force on the Hub
17:03:36  restart -> run-641a10f7c182 status "interrupted"
          q-3b7e6cc781f2  still there, still unanswered, asker_waiting FALSE
17:03:40  run-93067b1a17d5, the redelivered turn, asks again
17:03:48  q-7bf5289f85aa  asker_waiting true
          answered "blue" -> the run finished four seconds later
```

`asker_waiting` is derived per read — `created_by_run_id not in (runs whose status != "running")`
(`questions.py:249-270`) — so the reconciler flipping the run to `interrupted` is *itself* the
thing that makes every question that run asked go inert. A derived field cannot be forgotten by a
new code path the way an explicit expiry pass can, which is why the asymmetry is a design rather
than an omission. Two open questions, one dead and one live, are distinguishable by the field
alone.

**And the surfaces read it.** Not assumed — read:

- `QuestionsPanel.tsx:150-151` partitions the unanswered list on `blocking && stillWaiting`, with
  the comment *"asserting it collectively while ignoring it individually is the dishonest half"*:
  the dead question drops out from under the "agents are waiting" banner instead of inflating it.
- `AgentQuestionCard.tsx:70,86-95` renders a **"no longer waiting"** chip with the hover text
  *"The run that asked this has ended. Answering now would reach it as a new message, not as the
  answer it was waiting for."*

Answering the dead one is still allowed (`200`), and that is the right call — the row keeps the
operator's answer, and the reply reaches the agent as an ordinary message rather than vanishing.
The product's honesty here is in labelling it, not in forbidding it.

**No finding.** Recorded because the asymmetry looks like a bug from the code alone: one kind of
operator-facing block is expired explicitly on the crash path and the other is not mentioned. The
answer is that one is stored state and the other is computed from the run, and only driving it
shows which.

<!-- followed F122 in FINDINGS.md -->
## Row 19 x row 11 — a crash mid-firing, and F123

`reconcile_stale_job_runs` is the second half of the startup pass and nothing had driven it either.
Driven 2026-08-29 18:06, `scripts/drive/t_row19_crash_job.py`: a job fired by hand, the Hub killed
eight seconds in, restarted.

**The reconciliation itself is exactly right.** No `JobRun` is left `in_progress`, the firing is
`failed`, and the summary is one an operator can act on rather than a stack trace:

```
run-5d31c6858841  status "failed"  trigger "manual"  tick_count 1
error_summary: "Reconciled on Hub start: no live run behind this firing"
```

It reaches that by the `conversation_id` correlation the two tables share by convention rather
than by constraint — `JobRun` and `Run` have no foreign key — and the correlation held.

<!-- followed F123 in FINDINGS.md -->
## Row 11 LOOPS, second half — a loop fires, works, stalls, drains and stops, and stays stopped

Driven 2026-08-29 on 8011 against this branch, in `drive-wt-0829` (`proj-dc4d43543bea`), one Haiku
agent. Two harnesses: `t_row11_loop.py` (the queue-drained ending) and `t_row11_loop_quiet.py` (the
stop-time ending, plus the quiet window). **19/21 and 12/12** — and both of the first harness's two
BADs are a mis-specified assertion of mine, not a defect; the measurement behind them is real and
is recorded under F121 below.

**The whole ladder, live.** `POST /jobs` with `stop_when_queue_empties` and two `initial_tasks`
created the job, the `Loop` row and both queue entries in one call, and the response reported
`queue: {"pending": 2}` — the seeded queue, not the empty one an earlier version of that route
computed before seeding. One manual fire, then the cron:

```
17:18:15  manual     completed   task A pending -> in_progress -> completed
17:19:00  scheduled  completed   task B pending -> in_progress -> completed
17:20:00  scheduled  skipped     tick_count 2   "task task-c7a2f0dbb4c5 has no recorded evidence…"
17:22:00  scheduled  skipped                    "loop queue is empty"   -> ending
```

Both artefacts exist with exactly the content asked for, each in its own task checkout
(`.agentweave/tasks/<task-id>/loop_r11_{a,b}.txt`, `ALPHAONE` / `ALPHATWO`), on its own
`agentweave/task/<task-id>` branch, and `main` was untouched throughout. **One task at a time**
held: the second was never claimed while the first ran.

**Stalled is not finished, and it says why.** With both tasks `completed` and nothing approved, the
loop ticked twice more and stopped nothing. The skipped row carries a reason an operator can act
on rather than a status word:

> *task task-c7a2f0dbb4c5 has no recorded evidence, so there is no commit to review. Evidence
> naming a commit is what a review turn is given. Until the work that finished this task is
> recorded as evidence naming a commit, no reviewer can be given anything to look at.*

and the second identical tick **incremented `tick_count` to 2 on the same row** instead of writing
a duplicate, which is `loop-notices-and-reacts` design D6 working exactly as its docstring argues.

**The four ending facts, both ways.** Approving both tasks drained the queue and the next tick
ended the loop: `ending_state: "completed"`, `stop_reason: "loop queue is empty"`, `stopped_at`
populated, `job.enabled` false. A second loop created with a `stop_at` **two minutes in the past**
ended on its first firing with `ending_state: "stopped"` — not `completed`, because its queue still
held open work — `stop_reason` naming the time, and **no agent was spawned at all**: the one queued
task was still `pending` afterwards. The stop condition is checked before the spawn, and
`POST /jobs/{id}/run` on it answered `409 loop stop time reached (…)` rather than firing.

**Stopped is true, not merely reported** — which is the property `loop_ending.py`'s own docstring
records going wrong once (a loop that read `stopped` at 23:09 and ran twelve more real turns).
Watched for 160 seconds — three cron ticks — after the time-stop: `run_count` stayed 0, the history
stayed at one row, the agent stayed idle, and the outstanding task was never picked up.

**Three ways to restart an ended loop, all refused, each naming the remedy.**

```
PATCH /jobs/{id} {"enabled": true}
  409 {"code": "loop_ended", "message": "This loop has ended (loop queue is empty) at
       2026-08-29T17:22:00.049752+00:00 and cannot be restarted: its queue is closed, so the next
       firing would stop it again within the minute. Create a new loop with the work instead."}
  ...and it did not half-apply: the job was still disabled afterwards.

POST /jobs/{id}/run
  400 "Job is disabled"

POST /tasks {"loop_id": "<the ended loop>"}
  403 {"code": "loop_stopped", … "offered_task": {…}}   — the operator is refused too, and the
      submitted task is echoed back so it can be resubmitted as a new loop's initial_tasks.
```

Every one of those quotes a real `stopped_at`; the `"an unknown time"` fallback that F13's write-up
found live did not appear once. Two of the three were re-run against the **time-stopped** loop and
answered identically, quoting its own reason and time — so "ended" is one state with one set of
consequences, not two that happen to look alike. (The third differs only in *where* it is caught:
`POST /run` on the time-stopped loop is what ended it, so it answered `409 loop stop time reached`
rather than the `400 Job is disabled` a second press would get.)

<!-- followed F126 in FINDINGS.md -->
## Row 11 LOOPS, third pass — the three stall shapes that had never been driven, and D6's coalescing

`t_row11_stalls.py`, **28 of 28 verdicts held.** Nothing under `hub/` changed; the Hub on 8011
(started 18:06:50, newest `hub/` commit 17:04) served this branch's code throughout.

`_loop_stall_reason` has four branches and iteration 7 drove exactly one of them — the queue whose
tasks are all `completed` and unapproved. The other three are now driven, against a live Hub, with
the **exact** sentence asserted each time rather than a substring:

| shape | set up as | the Hub said |
|---|---|---|
| gate, still workable | A `blocked`, B `pending` depending on A | `loop queue is stalled: 1 still awaiting a prerequisite's approval` |
| gate, permanent | A `rejected`, B still depending on A | `loop queue is stalled: 1 gated on a rejected prerequisite that will not clear on its own` |
| no gate, waiting on a person | dependency removed, B `blocked` | `loop queue is stalled: no claimable task among 1 open (1 blocked)` |

Each arrived as a **409** from `POST /jobs/{id}/run`, and each left the loop alive: `ending_state`
null, `job.enabled` true, `next_run` still set. Skipped is not stopped, and the product means it.
Three further facts came out of the same drive, none of them previously driven:

* **The dependency edge is operator-reachable and symmetric.** `POST /tasks/{B}/dependencies`
  answered 201, and afterwards B's response carried `prerequisites: [A]` while A's carried
  `dependents: [B]` — the graph reads from both ends without a second request.
* **Design D6's coalescing works.** Firing the same stall twice appended **no** second row: the
  existing `JobRun` went `tick_count` 1 → 2 with `fired_at` frozen at the first refusal, and no
  second `job_run_skipped` event was persisted. Change the shape (reject the prerequisite) and a
  **new** row appears while the old one's count stays at 2 rather than being resurrected. A stall
  that lasts an hour therefore leaves one readable row, not twelve identical ones.
* **Zero spend.** Every `JobRun` this loop ever wrote is a `skipped` stall with a null
  `session_id`, and the loop's agent never left `idle`. Four firings, no runner ever touched.

The `blocked` shape needed `blocked_reason` on the PATCH — a 422 that names the field, which is
right. Worth recording only because the first run of the harness omitted it, the task stayed
`in_progress`, and the firing then **claimed it and spent a real turn**. The harness now aborts if
the setup status is not what the shape requires, rather than driving a different scenario than the
one it prints. That accident is what found F127 and F128 below.

One teardown note, not a finding: a loop whose job is merely disabled cannot be archived
(`400 this loop is still running`), because `ending_state` is written only by a firing that meets a
stop condition. The operator's own ending path is `PATCH /jobs/{id}` with `stop_reason`, which
routes through the same `end_loop` a firing uses. Both drive harnesses now tear down that way.

<!-- followed F137 in FINDINGS.md -->
## Row 5 driven live — the conversation thread holds together, 14 checks, 0 failures

**Driven 2026-08-30, iteration 12, on the 8011 Hub, `proj-1964cdedffe2`, agent `driver` bound to
Haiku. New harness `scripts/drive/t_row5_conversations.py`, two real turns.** Recorded because row 5
had never been driven past its API half, and because everything below is only observable once a
provider has actually replied.

Turn 1 plants a codeword and is told to reply `OK`. The operator then renames the conversation and
sends a second message asking for the codeword back. Every check passed:

| what | result |
|---|---|
| trigger names a conversation, run starts | `conv-c0f582c3d4ae`, `status: "running"` |
| the operator's own message is in the transcript | yes, as `kind: "operator_input"` |
| the agent replied | `agent_output` / `output_kind: "text"` → `"OK"`, ~8s |
| the conversation was given a title, not marked operator-set | yes, `title_set_by_operator: false` |
| a provider session was recorded | `374666cc-…` |
| rename accepted, title is exactly what was typed | yes |
| rename flips `title_set_by_operator` | `true` |
| second message stayed in the **same** conversation | yes, same id back |
| **the agent still knew the codeword** | replied `TANGERINE-I12B` |
| the operator's title survived the next turn | yes — the documented `name_conversation` no-op holds |
| one provider session across both turns | `374666cc…` → `374666cc…`, unchanged |
| conversation idle again, context usage measured | `attention: "idle"`, 17.69% of Haiku's window |

The middle one is the row's whole point. Two triggers, separated by an operator rename, resumed the
same provider session — so a conversation in this product is a real thread and not two runs sharing
an id. Nothing in the API half could have shown that.

**One cosmetic note, not filed.** With no `name_conversation` call the title is the first 115
characters of the opening message, cut mid-word: `'…Reply with only the two characters OK. Do not'`.
It is a placeholder doing its job, and the sidebar ellipsises it anyway; recorded only so the next
person to look at titles knows nothing generates one.

<!-- followed F139 in FINDINGS.md -->
## Row 6 driven live — the hop budget holds, and the operator can see and undo it. 12 checks, 0 failures

**Driven 2026-08-30, iteration 12, on the 8011 Hub, `proj-1964cdedffe2`. New harness
`scripts/drive/t_row6_hop_chain.py`. Three runs; the third is the clean one — see F139 for what the
first two found instead, which is why they are not thrown away.**

`t_sweep_queue.py` reaches row 6's mechanics for free by triggering an agent that can never launch.
What that cannot produce is a **hop**: hop depth only increments when one agent's *turn* sends to
another, so the mechanism that stops two agents talking to each other forever had never been driven
from the agent side. The chain: operator → `driver` (hop 0) → `peer` (hop 1) → `driver` (hop 2),
with `hop_budget` tightened to 1.

| what | result |
|---|---|
| the budget can be tightened, and is restored on the way out | 6 → 1 → 6, including on failure |
| `driver`'s message reaches `peer`'s queue at **hop 1** | yes, ~12s |
| it is attributed to the *agent*, not the operator | `origin_type: "agent"`, `origin_agent: "driver"` |
| `peer`'s reply arrives at `driver` at **hop 2** | yes, ~8s |
| the over-budget entry is **held, not discarded** | `state: "queued"` |
| the **timeline** marks it held | `kind: "inbound_peer"`, `hop_budget_exceeded: true` |
| the queue status names the cause | `waiting_reason: "hop budget exhausted"` |
| an **operator** message is accepted while the queue is hop-blocked | 200, `status: "running"` |
| …and is not itself caught by the budget | delivered immediately, hop 0 |
| `release` accepts the entry the budget is actually holding | 200, and it resets `hop_depth` to 0 |
| the released message is then delivered | ~8s, content `PONG-I12E` |
| an entry the queue is **holding** can be withdrawn, and never delivers | `state: "withdrawn"` |

Two details worth keeping. First, the held flag lives on the **timeline**
(`TimelineEntry.hop_budget_exceeded`, `agent_chat.py:85`/`206-208`) and not on the queue listing
(`QueueEntryResponse`, `inbound_queue.py:24-42`), which is right — it is what draws the UI's
"held / Continue" control (`AgentTimeline.tsx:815`) and the queue listing is not that surface. The
first version of this harness read it from the queue route, got `None`, and reported a correctly-held
entry as unmarked. Second, `release` **resets `hop_depth` to 0** rather than raising the budget, so
one operator decision frees one message and the budget still bounds everything after it. That is the
right shape and nothing said so anywhere; it is written down here now.

**Withdrawal has to be driven against a queue that is actually holding.** Triggering an idle agent
and withdrawing immediately loses the race — the entry is delivered inside the same second and the
`409 "already delivered/withdrawn"` reads as a product failure. The harness now occupies the agent
first and withdraws the entry that queues behind the running turn.

---

<!-- followed F164 in FINDINGS.md -->
## DRIVE-3 (2026-08-31) — `approval-waits-for-the-turn-to-end`, driven

Group 7 of the change. Fresh project **`drive3-2026-08-31` = `proj-f44107415869`** at
`C:\Users\huida\Documents\drive3-2026-08-31` — `git init -b master`, one seed commit (`calc.py`,
`.gitignore`), `master` adopted by `POST /projects/open` with no settings round trip. Runner
`Haiku (cheap)`, agents `alpha` and `beta`, `allow_agent_jobs` on. Neither forbidden project
touched. The Hub on 8011 was restarted from this branch first (PID 28704, started **05:10**, was
serving the previous run's code) and confirmed: no `.py` under `hub/hub` or `src` newer than the new
process's start time.

Six runs, every agent turn on Haiku: `t_f162_window.py` lane 1, `t_drive2_loop_lands.py`,
`t_drive1_flow_lands.py`, and `t_f162_window.py` lane 2 (`AW_WIDE=1`) — lanes 1 and 2 twice each,
because the first outing of each failed one assertion belonging to the harness rather than to the
product, and a harness edit is not evidence until it has been run.

### F162 is closed, measured inside the window at 1-second granularity

`t_f162_window.py` lane 1, **17/17**, `OUTCOME: GUARDED`, on two independent runs. The harness's
pass condition was inverted for this run: what it was written to REPRODUCE is now what it fails on,
and `GUARDED` — the outcome it could only hypothesise before — is the pass. The first run scored
16/17 on a harness bug of my own (comparing a `detail` dict against an unwrapped sentence); fixed,
re-run, and the check it was hiding now reads `identical`.

The window was entered, not assumed: at the instant the task first read `completed`, the tip of
`agentweave/task/task-24d6d5aa1175` was still `1ee11f5`, the commit the branch was cut from, and
`alpha` was still busy.

```
t+  47.59s  task reads 'completed'   tip=1ee11f5088b4 (== base)   busy=['alpha']
t+  47.72s  land attempted           409
t+  47.75s  hop 1 (assignee -> null) 200
t+  47.77s  hop 2 (-> under_review)  200
t+  47.89s  hop 3 (-> approved)      409
```

The approval's refusal, verbatim, and the thing an operator actually reads:

> alpha is still running the turn that produces this task's work, so what approving would merge is
> not knowable yet — the task's branch still points at the commit the turn started from. Nothing is
> wrong with the work. Approve once the turn has ended: this clears itself, with nothing for anyone
> to do. Stopping the agent's run ends the turn too.

`409 gate_unsatisfied`, with `unfinished: [{"agent": "alpha", "run_id": "run-…"}]` and
every other category empty. **No integration row was written at all** — the approval did not reach
the point of resolving a merge target, so there is no `ALREADY_INTEGRATED` skip to be stranded by.
Then the turn ended, the tip moved to `6c9cc34`, the same three hops answered 200/200/200, and
`git show master:f162_134506.py` returns `def cube(a): return a ** 3`. The refusal cleared itself,
exactly as its sentence promises.

**The composition inherits it.** `POST /tasks/{id}/land` was driven inside the window too — first,
because it is the only moment the task still reads `completed` — and answered the **same 409**, and the
two sentences compare `identical`. Afterwards the task still read `completed` and was still held by
`alpha`: the refused landing left nothing half-applied, which is `_commit_and_render`'s transaction
boundary observed live rather than in a unit test.

### The window did not narrow — it is refused for the whole of its width

Lane 2 (`AW_WIDE=1`), **6/6**, asks the other half of the question. Closing a window is not the same
as shrinking one, and a single refusal at one instant would not tell them apart. So this lane drives
an ordinary multi-step turn — build the file, mark the task done, *then* keep working — and probes
`POST /land` every five seconds from the moment the task reads `completed` until the tip moves.
`land` is the probe because lane 1 measured it leaving the task exactly as it found it, so probing
costs the window nothing.

```
t+   0.56s  job fired
t+  18.36s  task reads 'completed'   tip=d05400ffdb7f (== base)   busy=['alpha']
   [probe t+ 0.1s] land -> 409  (unfinished)
   [probe t+ 5.4s] land -> 409  (unfinished)
t+  28.05s  the snapshot arrived     tip 052a4b9db0dd
```

**9.7 seconds wide, 409 at both ends, `unfinished` both times.** The window is exactly where it was
— it runs from `update_task(completed)` to the end of the turn, which the product still does not
constrain — and the fix makes all of it refuse rather than making any of it go away. Approving after
the turn ended merged `052a4b9` normally.

One harness assertion had to be loosened to get there, and it is worth saying why rather than just
doing it. The check was `width >= 10`, calibrated on a single sample — the 10.5s this lane measured
on 2026-08-31 06:41 — and the first run here failed it at **8.7s**, on nothing but Haiku having
tidied up faster. Three samples now exist for the same prompt: **10.5s, 8.7s, 9.7s**. The width is
**agent-sized by construction**, so a bound tuned to one turn is an assertion about the model rather
than about the product. Loosened to `>= 5` — two orders above the round trip that would land inside
it — with the measured number printed either way, because the number is the finding.

### F163 is closed: landing a loop's work is one request

`t_drive2_loop_lands.py`, **36/36**. `approve()` in that harness used to be three PATCHes and is now
one `POST /tasks/{id}/land`; what the three used to cost is kept in its docstring rather than
deleted, because the three are the reason the route exists. Both lanes:

- **LANE A** (declaration omitted): one request answered `200` with `status: approved` and
  `assignee: null` — the two facts the three hops used to produce between them. Under LANE A′'s
  deliberately dirty checkout it skipped with `CHECKOUT_DIRTY` and `retryable: true`; cleaning and
  pressing retry merged `5413b41` and put `def power(a, b): return a ** b` on `master`.
- **LANE B** (`work_needs_evidence=True`): the same one request reached `approved`, nothing merged,
  and the reason was the evidence one — *"no accepted evidence names a commit, so there is nothing
  to merge"* — never `NO_TASK_BRANCH`, with no retry offered.

### F161/D21 is closed: a loop does not enter the review arm

Same run, three checks added to LANE A for exactly this population — one agent, one task, nobody
else to ask. When the turn ended, the loop's task rested at **`completed`**, still held by `alpha`,
and `beta` was `idle` throughout. No reviewer was resolved onto it and no second agent was pulled
in. Before group 5 this is the shape that stalled: a completed task offered to a selection a
one-agent mode cannot fill.

### The flow's review leg is untouched — the regression this change most plausibly caused, absent

`t_drive1_flow_lands.py`, **16/20**, re-run because group 5 changed the review arm at the selection
site and the new gate sits on every approval. Both are clean:

- both tasks staffed, worked, and reached `completed` with no operator transition;
- both recorded evidence naming a commit unasked;
- **both reviewers were non-authors** — `power`: alpha → beta, `modulo`: beta → alpha;
- `modulo` reached `approved` **with nobody's hand on it**, and its integration row reads
  `actor_kind: "run"`, `actor: "alpha"`, `outcome: "merged"`, `9773ee1` onto `master`.

That last row is design **D10 proven live**. Since migration `0092` a review run is bound to the
very task it inspects, so a predicate that merely asked "is a live run bound to this task?" would
have refused every review the product staffs — including this one, whose author is a different
agent entirely. The acting run is excluded, a turn is never blocked by itself, and the reviewer's
approval merged. **No refusal anywhere in this drive carried an `unfinished` entry**; the two that
fired were change C's evidence one and F155's conflict one.

The four that did not hold are all the `power` lane and all previously filed:

1. **F155, third consecutive drive.** *"This task's work does not merge cleanly into master:
   drive1_133738.py. Resolve the conflict on the branch, then approve."* Both tasks append to one
   file and `modulo` landed first. F164 already called this the ordinary shape of a flow's parallel
   work rather than a stall artefact; a third occurrence settles it.
2. **F154 verbatim.** With both agents idle and `power` wedged at `under_review`, every firing
   answers `409` *"Every task on this loop's queue is already being worked."*
3. and 4. are the pass condition and the following-firing check, both downstream of (1).

### F164's "intermittent is the wrong word" is itself corrected by this drive

F164 recorded that two consecutive drives had a reviewer write a verdict in prose and never call
`update_task`, and concluded *"two for two makes **intermittent** the wrong word"*. On this drive
the reviewer **did** call it: the transcript carries

> `Error calling tool 'update_task': Hub rejected PATCH /tasks/task-c5d6452745a1 (409): This task's
> work has been recorded and nobody has judged it: FR-1 at 5150e66dcd43. …`

followed by the agent reasoning about it — *"Ah! The task requires evidence to be recorded and
accepted…"*. So the F152 checks fired for the first time on real output: change C's refusal reached
the agent's turn **as prose, not as a dict repr**. Three drives, two misses and one hit, which puts
"intermittent" back in play and makes the harness's F152 assertions no longer vacuous. The
underlying diagnosis (the spawned Claude CLI presents the MCP tools as deferred and the model can
loop on `ToolSearch`) is unchanged and still not the Hub's.

### One new observation, not a defect — the two landing routes stop being interchangeable

Inside the window, hops 1 and 2 are **permitted** and only the approval refuses, which is right:
clearing an assignee and moving to `under_review` assert nothing about whether the work is good.
But the operator is then left at `under_review`, and `POST /land` requires `completed`, so the
one-action route is no longer available to them for that task. The remaining cost is a single
`PATCH {"status": "approved"}` once the turn ends, so nothing is stranded and nothing is worse than
before the route existed. Recorded because it means the recommended route (`land`, which leaves the
task exactly as it found it) and the legacy three-hop route degrade differently under a refusal, and
that asymmetry is worth knowing before anyone documents either.

`master` in the fixture at the end, every merge on it produced by driving the product:

```
d24414e Integrate approved work 052a4b9db0dd   <- lane 2's cube, approved after the turn ended
052a4b9 Auto-snapshot: alpha's turn on task-789cc620f212
d05400f Integrate approved work 6c9cc34b43de   <- lane 1's cube, refused inside the window first
6c9cc34 Auto-snapshot: alpha's turn on task-24d6d5aa1175
1ee11f5 Integrate approved work dffd3ef68871
dffd3ef Auto-snapshot: alpha's turn on task-a7e9b3493c7e
eaa92ce The flow drive's spec document, committed so the next drive's preflight starts clean
773f942 Integrate approved work 9773ee122100   <- the flow's modulo, merged by its REVIEWER's turn
9773ee1 Auto-snapshot: beta's turn on task-b45ec2c16caa
d3ba8f3 Integrate approved work 5413b419c459   <- the loop's power, landed in ONE action
5413b41 Auto-snapshot: alpha's turn on task-436b1128ca4d
5d7e9cc Integrate approved work fcf083ef1274
fcf083e Auto-snapshot: alpha's turn on task-d8bf6c0b7180
922c427 seed
```

---

<!-- followed F164 in FINDINGS.md -->
## Drive 2026-08-31 — F155's remedy, followed end to end (`t_f155_conflict_remedy.py`)

Hub restarted on `127.0.0.1:8011` from `autonomous/2026-08-31-the-turn-must-end-first` at `0373867`.
A **fresh** project (`/projects/open` on a fresh temporary git repository) for every run, as the
autonomous run's limits require. No agent turns: the whole population this refusal addresses is
operator-facing, so no model was bound.

**23/23 checks passed.** The one that matters is lane 2, and it is the one the unit tests
structurally cannot make: **the harness parses the branch to act on out of the refusal's own
sentence** — `recorded from a checkout of ([^\s.,;]+)` — and uses nothing it knows about its own
setup. It resolves the conflict there, records evidence from a checkout of that branch, approves,
and reaches `merged` with the resolved commit on the main branch. A remedy is followable or it is
not, and this is the only way to find out.

Lane 3 drove the **old** remedy against a second task and confirmed the defect is still exactly
what it was: resolve on the branch, approve again, and the refusal comes back **byte-for-byte
identical**. That is the world, not the wording, and it does not change — which is precisely why
the product must stop giving that instruction on this route. Lane 4 confirmed the branch-tip route
keeps the old sentence, because there the commit judged is whatever the branch then points at.

### F155 — Status: **FIXED** (`0373867`, driven 2026-08-31)

The refusal on the evidence route now names the commit it judged, names the branch it was recorded
on distinctly from the branch it would merge into, says that resolving there and retrying will not
clear it and why, states the remedy as a condition on *where the recording is done from* rather
than as a field to supply, says it does not take care of itself, says the fresh evidence need not
be about the same requirement, attributes the commit where another task recorded it, and ends in
the same `ACCEPT_OR_GRANT` clause the sibling refusal uses.

### F165 (new, severity **B**) — an operator's locator-named commit silently fails to supersede

**Status:** fixed 2026-09-26 by `a-footprint-names-the-line-of-work-its-commit-is-on` (`line_of_work`, `reduce_by_ancestry`, migration 0109); driven on Hub :8051: operator evidence at C then D with the checkout detached at C -> both footprints `agentweave/builder`, preview one target (D), approval merged D with C riding along.

Reachable, and proven reachable in `hub/tests/test_conflict_refusal_names_what_clears_it.py`
(`test_an_operator_naming_the_resolved_sha_does_not_supersede`), which is what task 1.3a asked for.

An operator who reads the new remedy and records evidence whose `locator` **is the resolved sha**
goes through `read_footprint(root, at=resolved)` and therefore `_branch_at`, which answers `""`
unless that commit is the tip of exactly one local branch (`requirement_evidence.py:516-529`). The
resolved commit stops being a tip the moment anything is committed on top of it. `""` and
`agentweave/task/…` are distinct keys in `integration_targets`' per-branch reduction, so the fresh
row lands **beside** the stale one instead of replacing it, and the refusal stands with no visible
reason. Recording naming a commit is exactly what F71 made authoritative, so this is the natural
thing for an informed operator to do.

The `a-conflict-refusal-names-what-clears-it` change is prose-only and does **not** fix this. Its
wording steers around it — *recorded from a checkout of that branch* — and deliberately refuses to
promise the branch takes care of itself. The fix, if it is wanted, is a decision about what
`_branch_at` should answer for a commit that is an *ancestor* of exactly one branch, and that is a
change to what a footprint's `branch` means. Not queued.

**Bound measured 2026-08-31 (iteration 15), at the source — the sentinel carries two meanings.**
`_branch_at`'s docstring (`requirement_evidence.py:516-529`) justifies returning `""` by calling it
"names no line of work" and citing `evidence_drift` skipping such a footprint. That precedent is real
in one consumer and absent in the other. `detect_drift` (`:1064-1069`) does skip it — `if not ref or
ref == "HEAD": continue`. But `integration_targets` (`task_integration.py:283-286`) writes
`newest[target.branch]` with **no empty-branch guard**, and `_targets` (`:257-267`) filters only on
`footprint.commit_sha`, so `""` reaches the reduction as an ordinary key. In the merge path `""`
therefore means *one shared line of work* — an equivalence class every branch-unknown footprint on
the task falls into together, resolved last-write-wins by the oldest-first ordering — not *unknown*.
Consequence for the repair: teaching `_branch_at` to answer a descendant branch moves rows out of
that bucket and is the right direction, but it does not decide what the bucket should do with what
stays in it, and nothing has decided that today. A repair touching only `_branch_at` leaves an
undesigned equivalence class behind. Not measured: whether two branch-unknown accepted footprints on
one task are reachable through the product's own routes rather than constructible in a test — that
needs a drive. Severity stays B, still unqueued.

### F166 (new, severity **C**) — the same hole on the agent route, via `footprint_root`'s fallbacks

**Status:** fixed 2026-09-26 by `a-footprint-names-the-line-of-work-its-commit-is-on` (D2/D3: `read_evidence_footprint` seam, task-bound agent falls back to the task branch's tip); driven live with F165, archived.

**Status:** open. `spec-queue/ROADMAP.md:190` records this entry and its sibling as
standing after their parent was withdrawn, and `requirement_evidence.footprint_root`'s three answers
are unchanged. Never specced. [classified 2026-09-09, D-3]

Also reachable, also held by a test
(`test_an_agent_whose_workspace_is_gone_does_not_supersede`). Round 2 recorded that an agent's
footprint is *always* taken in a worktree on the task branch; round 3 corrected it and the test
confirms the correction. `footprint_root` has three answers
(`requirement_evidence.py:299-340`): the recorded run directory **only while it still exists**, then
the per-agent checkout, then `workspace.root` — which is on the main branch. Its own docstring names
both fallbacks as live, including *"a task checkout that has since been released, whose directory is
gone by design"*. On either, the fresh footprint carries a branch the stale row does not, `newest`
gains a second key, and the refusal stands. The third answer is the worst: the project checkout is
on the main branch, so the fresh target merges trivially and displaces nothing while the stale one
goes on refusing.

Severity C rather than B because the population F155 was measured on does not hit it — the agent is
mid-turn on the task it is approving, so its task worktree exists. That is a fact about that drive,
not a guarantee, which is the whole reason it is written down.

### Two product refusals the harness earned by getting it wrong first — both good

Not findings. Recorded because they are the kind of thing a harness author assumes is a bug.

* `PATCH /jobs/{id} {"work_needs_evidence": false}` → **400**, *"a loop declares at creation whether
  its work needs evidence, and it cannot be changed afterwards — create a loop with the declaration
  you want, and offer this loop's tasks to it"*. It says what to do instead, which is the standard
  this whole change is about.
* `PATCH /tasks/{id} {"loop_id": …}` → **403**, *"A task's loop assignment is set at creation and
  cannot be changed afterwards."*

Both were reached by writing the harness the lazy way round; both refusals were legible enough to
fix it in one pass.

---

<!-- followed F172 in FINDINGS.md -->
## Row 1 — what held

Recorded because the sweep's verdict rests on these as much as on the three above. Each was driven.

- **F4's branch adoption.** Opening a git directory sets `main_branch` from the repository without
  the operator confirming anything: `GET /settings` reads `"main"` immediately, and
  `main-branch-suggestion` answers `{suggestion: "main", chosen: "main", is_repository: true}` — no
  degraded window at all, which is the whole point of the 2026-08-24 fix.
- **The settings merge rule.** `PUT /settings` with a single field left all fifteen others exactly
  as they were. This is the defect the route's own comment describes having fixed, and it is fixed.
- **Unknown settings fields are refused, not ignored.** `checkpoint_threshold_tokens: -5` → `422
  extra_forbidden`, naming the field in `loc`. A misspelt field cannot silently do nothing.
- **`/fs/list` is built for a picker, not for an API client.** A missing directory and a file path
  each answer `200` with `entries: []`, a walkable `parent`, and the OS's own `reason`, so the
  operator can see why this rung is empty and keep navigating. A *relative* path is refused outright
  (`400 "path must be absolute"`). That split is the right one and it took a wrong assertion to see.
- **The workspace listing respects git.** Tracked and untracked-but-not-ignored files listed;
  `.gitignore`d ones absent. `GET /workspace/file` reads a tracked file and answers `404 "path not
  found in this workspace: <path>"` for both an ignored file and `../../../Windows/win.ini` — the
  same message for both, which `workspace_file.py:58` argues for deliberately.
- **A vanished directory stays listable.** `GET /projects/{id}` after the folder moved answers `200`
  with `directory_state: "missing"` rather than 404-ing the project out of reach of its own repair.
- **Re-opening the same path is idempotent**, returning the same project id rather than a duplicate.
- **The copy-marker guard fires.** Opening a copy of a registered project refuses `409
  project_identity_conflict`; `register_copy_as_new: true` then succeeds. Both halves driven.
- **The remedy is on the screen.** The dashboard rendered, the dialog opened, the refusal reached
  the operator, and *"Register as a new project"* was there to click — the one thing that turns a
  refusal into a way forward. F171 is about the paragraph next to that button, not the button.
- **A non-git directory is a first-class project.** Opened `200`; `main-branch-suggestion` answers
  `is_repository: false` rather than failing.
- **No console errors** anywhere in the screen half, once the deliberate `409` is discounted.

---

# Full-surface sweep, 2026-09-01 — row 2 of 19: Runners

The night window's `N-2`, second feature area. Driven against the **8011** Hub on the beta profile,
with a fresh git fixture outside the repository and a fresh project per run. Surfaces exercised:
`runners`, `launchability`, `model_catalog`, `runner_commands`, and the `RunnersPage` screen.

**64 API assertions, 13 screen assertions, one real agent turn, five findings.** Harnesses kept:
`scripts/drive/t_sweep_row2_runners.py` (58 or 59 of 64 — five reds are F174, F175 and F176, and the
sixth is F177, which by its nature only fires on a `created_at` tie) and
`scripts/drive/t_sweep_row2_ui.py` (10/13 — the three reds are all F173).

**The row's load-bearing claim was driven, not read.** A runner on `claude-haiku-4-5-20251001`, an
agent bound to it, one real turn (`run-86669729ee1d`, completed, exit 0, 7s). `turn_usage.model` is
`claude-haiku-4-5-20251001` — the model Claude itself reported back, not the one the Hub sent. A
Runner record reaches the provider process intact. Codex runners were created, listed and probed
but never spawned, per the standing operator decision that Codex is undrivable.

**Fixed 2026-09-22, `cb2275a`.** `_guard_relocation` now looks up any other project holding the destination `path_key` and raises `ProjectIdentityConflict(code="project_path_claimed")`. The route answers 409 with the claimant's id, name and `directory_state`, plus the remedy this entry asked for: relocate that project or delete it, then relocate this one. `test_relocate_onto_a_claimed_path.py` reproduces the scenario through the route: before the fix `IntegrityError`, after the 409, with the project left unmoved. **Not re-checked:** `create` and `open`, which this entry found refuse legibly already. The `t_f172_…` drive harness was not re-run, and the UI's rendering of the new code was not seen.

---

<!-- followed F177 in FINDINGS.md -->
## What held, under row 2

Recorded because a sweep that lists only defects describes a product that does not exist.

- **A Runner record reaches the provider intact.** One real Haiku turn, and `turn_usage.model` is
  `claude-haiku-4-5-20251001` as reported by Claude itself. The whole point of the runner concept,
  driven end to end rather than asserted about argv.
- **A fresh project seeds exactly one runner per supported CLI**, both with `model: null`, so an
  unconfigured project runs each CLI's own default rather than a Hub guess.
- **The catalog is internally coherent.** Both providers declare exactly one default model, a
  context window for every model, both controls, a default that is one of that control's own values,
  and a renderable `apply` style — 16 assertions, all green. Codex's `permission_mode` correctly
  renders `style: "none"` (it is answered over app-server, not argv) and its `effort` renders
  `style: "config"`.
- **The catalog needs no project.** `GET /model-catalog` answers on operator auth alone, as its
  docstring argues it should.
- **Cross-project isolation holds.** A runner id from project A, read under project B's scope,
  answers `404 "Runner not found"` — not 403, not the row.
- **The bound-runner delete refusal is exemplary.** `409 "Runner is bound to agent(s): row2-probe.
  Unbind before deleting."` — names the blocker, names the remedy, and the remedy works.
- **A refused PATCH changes nothing.** After `400` on an undeclared model, the stored model is
  still what it was.
- **`flags` round-trip verbatim**, including the `--no-app-server` transport sentinel.
- **Unknown fields are named, not absorbed.** `{"colour":"red"}` gives `422` with `colour` in `loc`.
- **`/runners/launchability` is not shadowed by `/runners/{runner_id}`.** The literal segment is
  declared first and resolves as the collection endpoint; every runner in the project gets a
  verdict, every verdict states a reason whenever it is not runnable, and `runnable` is exactly
  `present and authorized` in all of them.
- **`launchability-by-provider` covers every catalog provider** without needing a runner row to
  exist, which is what agent-creation-by-provider depends on.
- **`probe_agent`'s unbound case is real.** `RUNNER_UNBOUND` (`launchability.py:38-43`) answers
  *"No runner is bound to this agent. Bind one in the Hub UI before it can run."* rather than
  falling through to the agent-name fallback that once sent an operator hunting for a binary named
  after their own agent.
- **No uncaught JavaScript error** on the Runners screen through create, refused create, edit,
  refused edit and cancel — only the two `400`s the drive provoked on purpose.

### Noted, not filed (severity D)

- **`PATCH /runners/{id} {"cli":"codex"}` answers `422 "Extra inputs are not permitted"`.** The
  refusal is right and `RequestModel` does name `cli` in `loc`, so the caller is told which field.
  But the reason given is "unknown field" where the truth is "known field, deliberately fixed after
  creation" — the dialog knows this and disables the CLI select on edit (`RunnersPage.tsx:216`).
  Not held open in the harness; recorded here.
- **`model_unrecognised` is currently unreachable in practice as well as unrendered.** Both write
  paths refuse an undeclared model, so only a row predating the catalog can carry one, and there are
  **zero** such rows across all 71 runners on the 8011 Hub. Its invisibility is part of F173; its
  unreachability is why that half of F173 has no live reproduction.

---

# Full-surface sweep, 2026-09-01 — row 3 of 19: Agents

The night window's `N-2`, third feature area. Driven against the **8011** Hub on the beta profile
(PID 22908, started 01:48:32; nothing under `hub/hub` or `src` newer, and the beta file's mtime
moved on a `GET /projects` while `<repo>/hub/data` did not). Fresh project `proj-13d37dd33731` on a
fresh git fixture outside the repository. Surfaces exercised: `agents`, `agent_lifecycle`,
bindings, canonical context, timeline, `agents/launchability`, and the agent-settings screen.

**85 API assertions, 19 screen assertions, one real agent turn, five findings.** Harnesses kept:
`scripts/drive/t_sweep_row3_agents.py` (83/85 — the two reds are F182 and F181) and
`scripts/drive/t_sweep_row3_ui.py` (15/19 — the four reds are F178 x2, F179 and F180). Both were
run twice, per the standing instruction; the second API pass ran against the state the first left
and scored identically, so unlike rows 1 and 2 the repeat surfaced nothing new here.

**The row's load-bearing claim was driven, not read.** A charter was authored saying *"reply with
exactly the single word ROW3023319"*, an agent was bound to it, and one real turn ran
(`run-ca3ac9b518bd`, completed, exit 0, ~8s, `claude-haiku-4-5-20251001`). The marker came back in
the output. **A Charter record reaches the process that runs**, and the timeline names the runner
and model it used (`Run started (claude, claude-haiku-4-5-20251001)`).

---

<!-- followed F182 in FINDINGS.md -->
## Suspicion, not a finding — no reproduction

`agent_lifecycle.archivable` (`agent_lifecycle.py:46-58`) detects queued work by **joining
Conversation** on `Conversation.agent == agent.name`, while the route's own follow-up query
(`agents.py:2136-2146`) and the scheduler's `inbound_queue.queued_entries`
(`inbound_queue.py:74-88`) both filter on `InboundQueueEntry.agent`. `conversation_id` is nullable
(`models.py:595-597`). If any path ever enqueues without one, or with a conversation belonging to a
different agent, the archivability check would say "archivable" about an agent with undelivered work
— the exact thing its own message exists to prevent. All eight `new_entry` call sites pass a
`conversation_id` today, so **this could not be reproduced** and is recorded only so a future change
to any of them does not have to rediscover the asymmetry.

---

<!-- followed F182 in FINDINGS.md -->
## What held, under row 3

Recorded because a sweep that lists only defects describes a product that does not exist. Each of
these is an assertion in one of the two harnesses, not an impression.

**The create-agent dialog is the counter-example to F173.** Same codebase, one surface over, and it
does everything the Runners dialog does not: the model comes from a `<select>` over the catalog, not
free text; `createAgent.error` is rendered as `role="alert"` with the Hub's own `detail` parsed out
(`AgentCreateDialog.tsx:10-17, 235`); the dialog stays open. Driven — typing an existing agent name
and pressing Create produced *"Agent name 'rid023319' already exists in this project"* on screen
(`row3-04-duplicate-refused.png`). This makes F173 an **omission**, not a missing convention.

**The provider picker uses the launchability it does fetch.** `ProviderPicker`
(`AgentCreateDialog.tsx:83-110`) disables a provider that cannot launch and prints its reason beside
it. Provider-level launchability (`/runners/launchability-by-provider`) has a real consumer; only
the *agent*-level one (F178) does not.

**find-or-create is genuinely atomic and does not duplicate.** Two agents created on the same
`provider` + `model` bound the *same* runner id, and the project's runner count did not move.

**Every binding refusal names the id it could not find**, and none leaks cross-project existence: an
unknown runner, an unknown charter, and a runner belonging to another project all answer
`404 "Runner '<id>' not found"` — the foreign one indistinguishable from the absent one.

**`_exactly_one_capability_source` says which combination is accepted.** Both `runner_id` +
`provider`/`model` together and neither of them answer `422 "Provide either runner_id or both
provider and model, not both or neither"`. That is the shape F175/F182 lack, in the same file.

**The archive lifecycle is complete and correctly filtered.** Archive and unarchive are both
idempotent; `?lifecycle=` accepts `open`/`archived`/`all` and refuses anything else with `422`; an
archived agent leaves the default roster, stays resolvable under `all` (so there is somewhere to
unarchive it from), and cannot be triggered — with a refusal that names unarchiving as the repair.
Archiving an agent whose run has *finished* is permitted; archiving one with queued work is not.

**Canonical context carries the charter.** `GET /agents/agent-context` renders the bound charter's
authored content, names the agent, and for an unknown agent answers `200` with an onboarding
document (team roster, what the agent may not decide, "you are not registered yet") rather than a
`404`. Cross-project, the same call does not leak the charter.

**The timeline is per-agent and starts at creation.** `agent_created` is on it before anything else
happens; an unknown agent's timeline is `[]`, not someone else's; a completed run contributes
`run_triggered`, `queue_entry_queued`, `queue_entry_delivered`, `run_started`, `run_completed`, with
`Run started (claude, claude-haiku-4-5-20251001)` naming the runner and model.

**A known past defect is still fixed.** The turn produced two `context_warning` rows 30 ms apart,
the later one carrying `status: "measured"` with `context_tokens: null`. `context_readings.py`
exists for exactly that (*"what made Claude agents report nothing for 329 samples"*) and picks the
complete row. Worth recording that the failure condition still occurs and the guard still holds.

**An empty agent name is refused `422`** — F176's shape on the runner surface does not repeat here.

### Noted, not filed (severity D)

- `POST /agents/{name}/heartbeat`, `/output`, `/context-usage` and `/compact` take a `{name}` that is
  never checked against a real agent row, unlike every route that goes through `_owned_agent`. These
  are agent-side write paths, not operator ones, and identity is bound by the run credential rather
  than the path — so this is a shape to watch, not a defect.
- The `context_warning` event type is used for a routine 17%-of-window reading. Nothing is wrong; the
  name just describes an alarm the row is not.
- One trap this harness fell into and now carries a comment about: asserting on `page.content()`
  rather than `page.inner_text()`. Searching the HTML for `"bind"` matched `tabindex` and turned
  F180 into a green row until it was checked by hand.

---

# Full-surface sweep, row 4 of 19: Charters

Driven 2026-09-01 (iteration 6) against the 8011 Hub on the beta profile, PID 22908 started
01:48:32, with nothing under `hub/hub` or `src` newer than that. Two fresh projects
(`proj-395817998d65`, then `proj-92ff8c6881f8`), both deleted afterwards. Harnesses kept:
`scripts/drive/t_sweep_row4_charters.py` (60/65, twice) and `scripts/drive/t_sweep_row4_ui.py`
(20/23, twice). Screenshots in `%TEMP%\row4shots`. Every agent turn bound
`claude-haiku-4-5-20251001`.

<!-- followed F187 in FINDINGS.md -->
## What HELD — and one thing this row set out to prove, proved, then had to disprove

**An edit to a bound charter reaches the next turn, including in a resumed conversation.** This was
the row's headline question and the API half cannot answer it. Driven with real turns: author a
charter saying *"reply with exactly the single word ALPHAq1"*, bind it, run a turn (`ALPHAq1` comes
back), `PATCH` the content to `BETAq1`, then run a second turn **in the same conversation** —
`conv-45b7db016716 -> conv-45b7db016716`, `--resume` on provider session
`bd6c486c-9a8e-4a43-8303-85e26a18cd6c` — and ask the agent to quote its `## Charter` section
verbatim. It returned the **new** text, word for word. The claim in `agent_trigger.py:893-895` —
*"an edited charter is therefore visible on the next run"* — holds, and now has a drive behind it.

**The thing that almost became F188, and did not.** The first version of this probe asked turn 2 to
*obey* rather than to *quote*, and in `run-2e5fae78696a` the agent replied with the **superseded**
marker. Its thinking then quoted a charter that was neither version — the new sentence with the old
marker word spliced in. The next run's thinking was more specific still: *"There are two charter
instructions in my system prompt... 1. ALPHAq1... 2. BETAq1."* That reads exactly like the system
prompt accumulating one canonical-context block per resumed turn — a real defect if true, and an
expensive one, since the block is ~7.7 kB.

Three things were measured before writing it up, and the third killed it:

1. **The materialized context file is correct.**
   `.agentweave/worktrees/tq1/.agentweave/context/tq1.md` line 77 carried only the new text,
   written at 02:53:02, immediately before the second spawn.
2. **The session transcript holds no system prompt at all**, so the accumulation could not be
   confirmed from disk. `~/.claude/projects/.../bd6c486c-....jsonl` is 21 rows of user turns,
   attachments and assistant messages; the appended system prompt is not among them.
3. **A three-turn probe counted it.** Charter edited before turn 2 and again before turn 3, then:
   *"Count the number of lines in your system prompt that begin 'Your marker word is'. Then list
   every marker word, in order."* Answer: **`1` / `WORDTHREE`.** One block, the current one.

So there is no accumulation. What the model was reading in turn 2 was **its own earlier reply**,
which had quoted the old charter verbatim inside a thinking block, and which is in the conversation
history where it belongs. The Hub replaces the charter cleanly on resume.

Worth keeping as method, not just as an outcome: an agent's self-report about its own system prompt
is evidence about the *conversation*, not about what the harness delivered. Two runs agreed with
each other and were both wrong about the mechanism. The harness now asks turn 2 to **quote** rather
than to **obey**, and carries a comment saying why.

**Everything else that held:**

- **Seeding is exactly the manifest, byte for byte, once.** Nine charters, names matching
  `hub/hub/data/charters/charters.json`, and `Code Reviewer`'s 4,731 characters identical to
  `code_reviewer.md` on disk. Re-opening the project through `POST /projects/open` re-enters
  registration and does not re-seed — `9 -> 9`.
- **Cross-project isolation is complete and silent about it.** Reading, editing and deleting this
  project's charter id under another project's route all answer `404 Charter not found`, as does
  `GET /agents/context?charter=` — the same wording an unknown id gets, so nothing leaks the fact
  that the charter exists. The charter survived every attempt with its content intact.
- **The bound-delete refusal names the holder and the repair, and the repair works.**
  *"Charter is bound to agent(s): b025056. Unbind before deleting."* — then `PATCH` `charter_id:
  null`, then `DELETE` returns `204`. The whole loop drives. (F185 is the archived case of the same
  refusal, not a defect in this one.)
- **The canonical context is rendered live, not cached.** A `PATCH` to the content is visible in the
  very next `GET /agents/agent-context?agent=` with no restart and no invalidation step.
- **An agent with no charter stays usable and says so.** `"No charter is assigned to this agent."`
  in the rendered context and `"charter"` in `missing` — `agent-charter:58-59` satisfied.
- **`agent-charter`'s three UI requirements are all satisfied by the shipped screen**, which is
  worth saying out loud after row 2 found a shipped requirement with no UI at all (F173). Driven:
  every charter collapsed on first open with no full document on screen (the longest starter is
  8,529 characters and none of it is there); expanding one shows its content with zero dialogs and
  zero textareas, so reading opens nothing that can modify; and opening a second leaves the first
  open — `2` elements at `aria-expanded="true"`. `row4-02-one-expanded.png`,
  `row4-03-two-expanded.png`.
- **An empty-content charter is allowed on purpose and the screen says what that means** — *"This
  charter has no content, so it contributes nothing to an agent's turn."* (`ChartersPage.tsx:171`).
  A permission with a sentence attached, which is the right shape.
- **The 422s are well worded where they reach anyone.** `"String should have at least 1 character"`,
  `"String should have at most 256 characters"` — both name the constraint. F187 is that the screen
  drops them, not that they are bad.

<!-- followed F187 in FINDINGS.md -->
## What the second run bought

Nothing new, for the second row running. Both API passes scored 60/65 against the state the first
left, and both UI passes 20/23. Row 1's F172 and row 2's F177 were each found only by a repeat, so
the technique stays; recording that it fired on two of four rows is the honest number.

---

# Sweep, row 5 of 19: Runs — 2026-09-01

The representative path from `SURVEY.md:26`: **trigger, stop, sessions, reconciliation,
divergence, task binding**. Routes `hub/hub/api/v1/agent_trigger.py` — `POST /agent/trigger`
(:1212), `POST /agent/{agent}/stop` (:1480), `GET /agent/sessions/{agent}` (:2749) — over
`run_task_binding.py`, `run_liveness.py`, `run_divergence.py` and the rule in `turn_scheduler.py`.

Harnesses kept: `scripts/drive/t_sweep_row5_runs.py` (**41/50**, three runs, the last two against
the state the first left) and `scripts/drive/t_sweep_row5_ui.py` (**13/16**, twice). Fixture setup
is `scripts/drive/setup_row5.py`. Five real Haiku turns, three of them stopped mid-sentence.

Two measurements here deliberately leave the Hub's own record and ask the operating system and the
filesystem instead, because row 4 paid for the lesson that a self-report is evidence about the
reporter: whether a stopped process is actually **dead**, and whether the path the screen calls
"where the agent's work happened" actually **exists**. The first vindicated the product; the
second did not.

<!-- followed F192 in FINDINGS.md -->
## What HELD — and the biggest of them was measured against the OS, not the record

- **STOP KILLS THE PROCESS.** Not "the row says stopped" — the process tree is gone. The run's
  `pid` was read straight out of the `runs` table (`33556`, `claude.exe`), its descendants
  enumerated from a live `Win32_Process` snapshot, and after `POST /agent/{agent}/stop` every one
  of them was absent within the polling window. `terminate_process_tree`'s `taskkill /F /T` does
  what its docstring claims on this platform.
- **A stop is recorded as a stop, not as a failure.** `status='stopped'`, `exit_code=2`. The
  comment at `agent_trigger.py:1995-1999` — *"force-terminating a process rarely yields exit code 0,
  so without this check a stop would be misreported as failed"* — now has a drive behind it.
- **One run per agent held under a real concurrent trigger.** A second `POST /agent/trigger` while
  the first was mid-turn returned `200 / status=queued` with `waiting_reason: "agent is already
  running"`, and the queued input **started on its own** once the stop landed: `running: true,
  waiting_count: 0`. A stop does not strand what was queued behind it.
- **Every other refusal on this route names a repair that works.** Archived → *"Unarchive it
  first."*; unknown agent → *"…Create it in the Hub UI, or correct the name — if a scheduled job
  names it, that job will keep failing until the name is fixed."*; unknown task → names the id and
  the project rule; approved task → *"Move it to 'revision_needed' to reopen it, or start the turn
  without naming a task."*; bad `session_mode` → enumerates both; `resume` with no `session_id` →
  names the field. Seven of nine refusals earn their keep; F191 and F192 are the two that do not.
- **F114's fix works where it was applied.** Four messages to an agent with no runner bound, four
  schedules, every entry still `queued` at `delivery_attempts: 0`. That is precisely what F188 asks
  for at the neighbouring site.
- **A message the Hub gave up on reaches the operator.** Driven on screen, not inferred: navigate
  to the dropped entry's *own* conversation and `abandoned_reason` is rendered
  (`AgentTimeline.tsx:805-807`).
- **The project boundary holds.** A conversation id belonging to another project is refused (badly
  worded — F191 — but refused).

<!-- followed F192 in FINDINGS.md -->
## Two harness bugs caught before they became findings

Run 2 of the API harness reported the worktree block *not firing* — the turn started normally. It
was the harness: run 1 had left a **registered** worktree at that path, and planting a file inside
a registered worktree changes nothing, because `ensure_worktree` reads back the branch it expects
and proceeds. The harness now runs `git worktree remove --force` **and `git worktree prune`**, then
asserts the path is absent from `git worktree list` before planting the blocker — so the condition
under test is created rather than assumed.

The second: run 2 answered `200` to *"stopping an agent with no run in progress"*, because a
previous invocation had left the agent blocked inside `ask_user`. Both harnesses now settle the
agent — decline pending questions, stop, drain queued entries — before any assertion that depends
on it being idle. And the UI harness stops on the *first* output row rather than the third, because
a Haiku turn can finish inside the polling window and a stop that arrives late is answered `404`
and measures nothing. Same shape as row 4's polling bug: **a harness that inherits state reports
the product broken.**

<!-- followed F192 in FINDINGS.md -->
## What the second run bought

Nothing new, for the third row running. The API harness scored 41/50 on the run after its own
state, with the same nine reds, and F188 reproduced on both projects. Rows 1 and 2 each found a
defect only a repeat could see; rows 3, 4 and 5 did not. Two of five is the honest number, and the
technique stays.

# Sweep, row 6 of 19: Conversations — 2026-09-01

Driven against the trial Hub on `:8011` (beta profile, this branch's code) with two fresh fixture
projects and real `claude-haiku-4-5` turns. Harnesses kept: `t_sweep_row6_conversations.py`
(79 API assertions, run twice, 75/79 both times, same four reds) and `t_sweep_row6_ui.py`
(15 screen assertions, run twice, 13/15 on the second). Screenshots in `%TEMP%\row6shots`.

The representative path from `SURVEY.md:27` — list, rename, release-task, chat history, lineage,
titles — over `hub/hub/api/v1/agent_chat.py`, `hub/hub/conversations.py` and
`hub/hub/conversation_titles.py`. Lineage was read straight out of sqlite, read-only, because no
route exposes it.

**This row's headline questions all held, and two of them held in a way worth stating outright: a
worker-generated title really does replace the truncated one, and an operator's title really does
survive the next turn's titler.** The three findings are at the seams around them.

<!-- followed F195 in FINDINGS.md -->
## What HELD — including the two things this row existed to ask

- **A worker-generated title actually replaces the truncated one.** Not "the code path exists" —
  driven three times, end to end: `conversation_title_mode: "generate"`, a real Haiku turn, then
  the `conversations.title` column read straight out of sqlite.
  `'In one short sentence, explain what a semaphore does in concurrent programming. Do not use any
  tools.'` became `'Semaphore explained as concurrency synchronization primitive'`; a second
  conversation became `'Write-ahead log in databases'`. The `conversation_titled` event is written,
  and no `Run` row is — which is what the module's docstring says must not happen, because a
  titling run under the agent's name would make the agent look busy and stall its queue.
- **It is what the operator reads.** `row6-04-generated-title.png`: the rail row and the
  conversation header both carry the generated title, not the first message.
- **An operator-set title survives the next turn.** Renamed to `'operator keeps this r6a'`, another
  real turn driven into the same conversation with generation still on, and the title is unchanged
  afterwards. `title_set_by_operator` is checked twice in `generate_conversation_title` — once
  before the spawn and once *after*, on a re-read, so a rename made while the model was thinking
  also wins. Both guards are live.
- **Title generation is off by default** (`conversation_title_mode: "truncate"`), so no project
  pays for a spawn it did not ask for.
- **Lineage survives a checkpoint cutover.** Measured in sqlite, not asked of a route: a new
  conversation founds its own lineage (`lineage_id == id`), and after
  `POST /checkpoints/{id}/cutover` the successor `conv-4d3564b7ec05` carries the predecessor's
  `lineage_id` `conv-2a78c785ef1b`. The predecessor is archived, the successor is titled
  `Continued: ...` and marked `title_set_by_operator` so the titler cannot overwrite it, and the
  screen shows `Continuing Continued: renamed while archived r6a` above the composer.
- **A rename the Hub refuses reaches the operator, in the Hub's own words.** Driven on screen: a
  400-character title typed into the rail's rename input produced *"A title cannot exceed 120
  characters"* rendered under the row (`ConversationRow.tsx:291-301`, `role="alert"` at :295), and the
  refused title was not stored. After six sites where a refusal was swallowed (F169, F173, F178,
  F179, F180, F187) this one is wired correctly — the counter-example that shows the pattern is a
  gap, not a house style.
- **The archived conversations are reachable and counted.** `Show archived (1)` in the agent's row
  menu, backed by `archived_by_agent` on the project-wide response, and `?lifecycle=archived`
  returns exactly the archived rows. An unknown `?lifecycle=` value is a 422 that enumerates the
  three that work.
- **Archiving refuses while a run is live, and says what to do:** *"This conversation has a run in
  progress. Wait for it to finish, or stop it first."* Archiving an already-archived conversation
  is a no-op, not an error; releasing a task from a thread that holds none is a 200, exactly as its
  docstring promises.
- **The project and agent boundaries hold.** A conversation id from another project is 404 on
  rename and on chat history, and the refusal does not disclose that the id exists elsewhere. The
  same id addressed to the wrong *agent* in the right project is also 404.
- **Rename validation is exact.** `'  operator  title  r6a  '` is stored as `'operator title r6a'`;
  whitespace-only is refused *"A title cannot be empty"*; over-long names the limit (120); a body
  with no title at all is a 422.
- **A task binding is recorded and releasable.** A turn carrying `task_id` binds the conversation,
  `DELETE .../conversations/{id}/task` clears it, and the clear reaches the database.

<!-- followed F195 in FINDINGS.md -->
## Considered and NOT filed: `lineage_id` is not on `ConversationResponse`

The harness asserts it and the assertion is red, deliberately, as a marker rather than a finding.
`ConversationResponse` (`agent_chat.py:108-150`) carries sixteen fields and `lineage_id` is not one
of them, so nothing on screen can say "these two threads are the same line of work". On the
evidence that is fine: the operator-facing answer is carried by the `Continued: ` title prefix and
by the checkpoint the successor opens on, both of which were driven and both of which read
correctly. Lineage is a *routing* fact — `conversations.py:218-240` matches a peer's reply on the
sender's lineage so correspondents survive a cutover — and exposing it would be a field with no
reader. Recorded so a later row does not re-derive it.

<!-- followed F195 in FINDINGS.md -->
## A refinement to F190's second half, measured rather than assumed

Row 5 recorded that the `Run {status} (exit {code}).` line at `agent_trigger.py:2135` is only ever
broadcast and never persisted. That is correct, and this row sharpens what it means. Counting
`agent_outputs` by run over the fixture project:

```
run-354d90af3912  completed   status rows: 1   total rows: 3
run-a0a2397be2fb  stopped     status rows: 0   total rows: 0
run-f444fe7b46a8  completed   status rows: 1   total rows: 3
run-07cf8bebd337  stopped     status rows: 0   total rows: 0
... 5 completed runs with one status row each, 5 stopped runs with none
```

A **completed** run does leave a persisted `status` row — but it comes from the stream parser and
its whole content is the word `Completed` (`payload: {"phase": "completed", "summary":
"Completed"}`). It can never say *stopped*, *failed* or *interrupted*, because it is only written
on the path that finished. So F190's conclusion stands unchanged — the terminal label has exactly
one carrier and that carrier is broken — and the reason is narrower than "nothing is persisted".

<!-- followed F195 in FINDINGS.md -->
## Two harness bugs caught before they became findings

Row 5's lesson at two more sites, both the same shape: **a harness that inherits state reports the
product broken.**

1. The UI harness clicked `project-expander-{PROJECT}` unconditionally and **closed** the project
   the operator was already inside, then measured an empty rail and called four things broken. It
   now reads `aria-label`/`aria-expanded` and expands only what is collapsed.
2. The assertion *"the conversation is on the rail by its title, never by its id"* was red against
   the whole sidebar, because an earlier drive left an agent in **another project** literally named
   `conv-probe`. Scoped to `rail-project-{PROJECT}` it is green. Had it been believed, it would
   have been written up as a product defect that does not exist.

<!-- followed F195 in FINDINGS.md -->
## What the second run bought

Nothing new on the API half — 75/79 twice, the same four reds, the second time on a project already
carrying run 1's state. The UI half's second run bought two of its three failures back by fixing
harness bug 1 above, and reproduced F193 identically. Rows 1 and 2 each found a defect only a
repeat could see; rows 3, 4, 5 and 6 did not. Two of six, and the technique stays.

# Sweep, row 7 of 19: Inbound queue — 2026-09-01

Row 7 of the coverage matrix (`SURVEY.md:28`): *per-agent durable queue, hop budget, turn delivery
cap, withdraw*. Six routes under `/queue` (`hub/hub/api/v1/inbound_queue.py`) over
`hub/hub/inbound_queue.py` and `hub/hub/turn_scheduler.py`, driven live against `:8011` on a fresh
project (`row7-r7a`, `proj-9e1979fcc8ac`) with three agents: two bound to a Haiku runner, one
created bound and then unbound through `PATCH /agents/{name} {"runner_id": null}` — `POST /agents`
refuses an unbound agent with a 422, which is why `setup_row7.py` exists beside `setup_row5.py`.

Harnesses kept: `t_sweep_row7_queue.py` (52 API assertions, run twice), `t_sweep_row7_ui.py`
(13 screen assertions), and `t_row6_hop_chain.py` re-run on this fixture for the hop leg. Five
findings, four of them about what a refusal or a write *says*; the queue's mechanics themselves
came through clean.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** Running in the project's primary checkout on an excerpt of the
transcript -- untrusted text -- the titler inherited every built-in tool. It now runs `claude --tools ""`
and `codex exec --sandbox read-only`. Measured with F195's ZEBRA control (Haiku, a directory whose
`CLAUDE.md` demands the prefix): `--tools ""` keeps the project's memory (`ZEBRA B-tree Indexes in
Databases`), while `--restricted` and `--setting-sources ""` both drop it, so neither is used. The
project's own settings hooks still run on a titling call, as in its sessions -- the price of reading its
memory, recorded rather than hidden.

<!-- followed F200 in FINDINGS.md -->
## What HELD — including the one mechanism nothing had ever driven

- **The turn delivery cap works, and the entries it batches actually reach the model.** Never
  measured live before. With `turn_delivery_cap = 2`, an occupied agent, and four operator messages
  queued behind the running turn (`ALPHA`, `BETA`, `GAMMA`, `DELTA`, one conversation), the drain
  produced **exactly two runs of two**, both times:

  ```
  run-30dc05e21e14: 2 entries ['ALPHA', 'BETA']
  run-abb0563affe9: 2 entries ['GAMMA', 'DELTA']
  ```

  and the *agent's own output* for each run mentions both of its words — so `format_turn_prompt` did
  not quietly drop the second entry of a batch. Nothing was abandoned; all four ended `delivered`.
- **The hop budget stops a chain, and the operator can see it and undo it.** `t_row6_hop_chain.py`
  re-run on this fixture: **12/12, first attempt** (F139's tool-name lottery did not fire). Under
  `hop_budget = 1`, `r7a → r7b → r7a` leaves the return message queued at hop 2, the timeline marks
  it `hop_budget_exceeded`, the status route says *"hop budget exhausted"*, an operator message
  injected alongside is **not** caught by the budget, and `release` re-bases it to depth 0 and it is
  delivered within ~8s.
- **F114's fix still holds where it was applied.** Four messages to an unbound agent, four
  schedules: `[('queued', 0), ('queued', 0), ('queued', 0), ('queued', 0)]`. Nothing lost, no
  attempt burned, and the status route says *"No runner is bound to this agent. Bind one in the Hub
  UI before it can run."* — a refusal that names the repair.
- **And the operator reads that sentence on screen.** `row7-04-unbound-waiting.png`: the
  conversation panel shows `QUEUED`, the message, and *"1 waiting — No runner is bound to this
  agent. Bind one in the Hub UI before it can run."*, with the Continue control beside it. Measured
  inside `[data-testid="conversation-workspace"]`, not on the body — see the harness bug below.
- **Withdrawal is clean.** An entry held behind a running turn withdraws with a 200, stays listed in
  state `withdrawn` with `delivered_in_run_id: null`, is found by `?state=withdrawn`, carries no
  `abandoned_reason` (which is what distinguishes an operator withdrawal from a Hub abandonment),
  and a second withdrawal is refused 409.
- **The route and the table agree.** 26 entries read straight out of `inbound_queue_entries` with a
  read-only sqlite connection and compared field by field against `GET /queue/{agent}` — `state`,
  `hop_depth`, `delivery_attempts`, `abandoned_reason`, `delivered_in_run_id`: zero mismatches, and
  no entry the table holds that the route hides.
- **The validation refusals on `/queue/settings` say what would work.** `hop_budget: 0`, `-1`,
  `turn_delivery_cap: 0` and `agent_budget: -5` are each refused 422 with *"Input should be greater
  than or equal to 1"*, naming the field. It is the *absence* of an upper bound that is F196, not
  the lower one.

<!-- followed F200 in FINDINGS.md -->
## Considered and NOT filed: the withdrawn entry that leaves the timeline

`GET /agent/{agent}/chat` does not return an entry the operator withdrew, and the first version of
the harness asserted that it should — one keystroke from filing a deliberate decision as a defect.
The timeline query keys its withdrawn branch on `abandoned_reason IS NOT NULL`
(`agent_chat.py:262-269`), and the comment above it says why: an entry the **Hub** dropped must stay
in the thread (F87), an entry the **operator** withdrew was never delivered and its removal is the
thing they asked for. The assertion now checks the deliberate behaviour instead.

<!-- followed F200 in FINDINGS.md -->
## A harness bug caught before it became a finding

Row 6's fifth lesson at a third site. *"the screen gives the reason the status route already
knows"* was **green against `page.inner_text("body")`** for the unbound agent — because the sidebar
carries an Environment link labelled **Runners**, so `"runner" in text` matches on every page in the
product, including a blank one. Scoped to `[data-testid="conversation-workspace"]` it is still
green, and now for the right reason. Believed as first written, it would have vindicated a sentence
without ever confirming it was on screen — the mirror image of row 6's false red.

<!-- followed F200 in FINDINGS.md -->
## What the second run bought

Nothing new. 42 passed / 10 failed on both runs of `t_sweep_row7_queue.py`, the second on the state
the first left, with the same reds (three of the ten are F196 legs added between the runs; the seven
common to both are identical). Rows 1 and 2 each found a defect only a repeat could see; rows 3–7
have not. Two of seven, and the technique stays.

---

# Sweep, row 8 of 19: Tasks

Driven 2026-09-01 04:29–04:47 +01:00 against the 8011 trial Hub (beta profile, PID 22908, this
branch's code), on a fresh fixture project `proj-f2538b3807fe` built by `setup_row7.py`. Harnesses
kept: `t_sweep_row8_tasks.py` (313 assertions, run twice on the final version, **19 failures both
times, identical**) and `t_sweep_row8_ui.py` (8 assertions, 4 failures). Screenshots in
`%TEMP%\row8shots`.

`SURVEY.md`'s architecture notes call this the most carefully built subsystem in the Hub. The drive
agrees with that assessment, and the three findings are all *outside* the machine: none of them is
a wrong edge, a bypassed gate or a corrupt record. The machine itself came through a total sweep
clean — see "What the machine survived" below, which is the more important half of this row.

<!-- followed F203 in FINDINGS.md -->
## What the machine survived — the larger half of this row

Every one of these was driven in this session, on this build, rather than read.

- **All 30 declared operator edges walked for real**, each on its own freshly created task reached
  only through declared edges, each accepted `200` with the row reading the new status.
- **All 50 non-edges refused**, every one `409`, every one naming the current status, and every one
  listing **exactly** `allowed_targets(from, operator)` — parsed back out of the sentence and
  compared set-for-set, not merely checked for plausibility.
- **No refusal moved anything.** After each from-status absorbed its full run of illegal requests,
  the task still read that status.
- **Published == enforced == observed, at all nine statuses.** `GET /tasks/transitions/allowed` was
  compared three ways: against the declared map, against the set that actually succeeded in LEG 2,
  and against the set the refusals named in LEG 3. This is design D13's whole claim — the client
  never holds a second copy of the map — and it holds exactly.
- **Restating the current status is a no-op that records nothing** (D7), confirmed by counting
  `task_transitions` rows before and after out of sqlite rather than by trusting the 200.
- **The dependency gate**: refuses `pending -> in_progress` with a structured
  `{"code": "dependency_unmet", "unmet": [...], "rejected": [...], "message": ...}` naming the
  prerequisite by id, title and current status; reports a `rejected` prerequisite in a separate
  list with a different remedy in the sentence ("reopen it, or edit the document that declared this
  dependency"); does **not** gate `-> assigned` or `-> rejected`, so a wave can be routed ahead;
  opens the moment the prerequisite is approved.
- **Design D5's exemption, and its mirror.** A dependency declared while a task waits does not stop
  it resuming: `blocked -> in_progress` was accepted `200` with the regressed prerequisite in
  place, and the task came back reading `dependency_state: "running_on_regressed"` — flagged, not
  stopped. The same prerequisite on a task at `pending` still refuses `409`. Both halves of the
  reversal ship together, as the design says they must.
- **The declare route's four refusals**: self (400, "a task cannot depend on itself"), missing
  (404, naming both ids), cycle (409, "so this would make each wait on the other forever"),
  duplicate (201, `outcome: "duplicate"` — a restatement is not a conflict). Removing an edge that
  is not there is 404; removing a real one is 204.
- **The board answers question (c) affirmatively.** A gated card carries
  `dependency_state: "gated"` and a `prerequisites` list with the blocking task's id, title and
  status; the flat `edges` list carries the edge and every edge on it has both ends on the board.
  On screen the badge reads "Waiting on 1 task", with the prerequisite named in its `title`
  tooltip and the edge drawn on the Dependencies view — so the reason is on the card, at badge
  weight, not only in a 409.
- **The picker's arithmetic**: `outstanding` excluded exactly the two terminal statuses and matched
  a count taken independently off the board; `total` matched the board exactly.
- **Isolation**: a foreign task id is 404 on this project's `GET` and `PATCH`, and a cross-project
  dependency is refused 404 naming both ids.
- **The database agrees with the routes.** 415 transition rows read read-only out of
  `task_transitions`: every one an edge the map declares, every one `actor_kind: operator` with
  `actor_agent` and `run_id` null, every one `origin: actor`, and not one restating a status. Task
  statuses matched row-for-row once the list route was paged to the end.

<!-- followed F203 in FINDINGS.md -->
## Considered and not filed

- **No route deletes a task.** There is no `DELETE` on any `*/tasks/{task_id}` and no UI mutation
  for one. This is coherent rather than missing: `rejected` is the lifecycle's answer to "this
  should not have been made", `rejected -> pending` reopens it, `TERMINAL_FOR_BINDING` treats it as
  resolved and the picker's `outstanding` excludes it. The only cost is that a mistyped task stays
  in `total` forever, which is a smaller harm than a delete that destroys a transition history.
  Recorded as an assertion in LEG 8 so a future decision to add one is noticed, not as a defect.
- **Creating a task in a non-entry status is refused 422 by the schema, not 409 by the service.**
  `TaskCreate.validate_status` (`schemas/tasks.py:102-110`) fires first, so
  `InvalidEntryStatusError`'s declared 409 and its "Every other status is reached by transitioning"
  sentence are unreachable on this route. Belt and braces, and the belt still names both entry
  points ("a new task must start at one of ['assigned', 'pending']"), so a caller can correct
  itself. Not filed — but note the contrast with F201, where the schema firing first *does* cost
  the caller the sentence that would have helped.
- **`main.py:406` sends `detail` as an object for the two gates and as a string everywhere else.**
  A client reading `detail` as a string gets `"{'code': 'dependency_unmet', ...}"` unless it handles
  both. `hub/ui/src/api/client.ts:82-93` handles all three shapes (string, object with `message`,
  Pydantic array), so the product's own client is fine. Recorded because a third-party one would
  not be.

<!-- followed F203 in FINDINGS.md -->
## Method

Two runs of the final `t_sweep_row8_tasks.py`, the second on the state the first left: **19
failures both times, the same nineteen**. Rows 1 and 2 each found a defect only a repeat could see;
rows 3–8 have not. Two of eight, and the technique stays.

Row 8's "measure outside the product" leg was the **live OpenAPI** rather than the source — LEG 8
asks the running Hub what routes it serves, so its two failures are facts about the deployed build
and will flip on their own when a route is added. LEG 7 read `tasks` and `task_transitions` out of
the beta database over a read-only sqlite URI, and that is what produced F202: the assertion "the
route reports every task the table holds" was green at 91 tasks and red at 100, and the boundary is
where the finding was. Neither surface alone would have shown it — the route answered `200` both
times.

The transition map in the harness is an **independent transcription** of
`hub/hub/task_transitions.py`, typed by hand rather than imported. A harness that imported the
product's own map would have asserted the product against itself and could not have caught a wrong
edge in either direction.

**Two of the UI harness's legs never executed, and the reason is F202 itself.** The drawer legs —
does the block control collect a reason before sending (F201's screen half), and does the status
control offer only published edges (D13's screen half) — both act on a task the harness creates at
the top of the run. That task is the newest in the project, so the board does not render it, so
there was nothing to click. The harness reported that as a failure with the reason named rather
than skipping quietly, which is right; but it means F201's "the operator in the UI cannot produce
this" is **read from `TaskDetailDrawer.tsx`, not driven**, and the paragraph above says so. On a
project under 100 tasks those legs would run.

One assertion in the UI half was **wrong and was caught before it was believed**: *"the Overview
page does not state a task count capped at 100"* passed, because it looked for the truncated number
near the word "Tasks" and the page renders it as "100 tasks" in a subtitle that check never
reached. The screenshot is what settled it. Row 7's lesson — scope every screen assertion to the
panel under test — has a companion, and this is it: a screen assertion that passes for a reason you
cannot name has measured nothing, and a screenshot is the cheapest way to find out which kind you
are holding.

<!-- followed F203 in FINDINGS.md -->
## Row 8's inherited findings, re-driven the same night

Both of these were queued for row 8 because each has a harness that costs no agent turn and builds
its own project. Run 2026-09-01 ~04:47 +01:00 against the same 8011 build.

- **`t_f154_wedged_review.py` — 18/18.** F154 stays **FIXED**. The firing answers `409` with
  *"beta is named on task-… ('Add one line to README') as its reviewer and is not reviewing it: no
  turn is running on that task and none is queued. Nothing will move it on its own. Ask beta again,
  review it yourself, or send it back with revision_needed."* — on both presses, with no run
  started either time, `stall_reason` carrying the same sentence rather than null, the walk still
  listing the task as current with `agent_capacity: "held"`, and the loop moving again once the
  operator takes one of the three exits. The harness's fifth lane also shows **F167's row reaching
  the same named refusal**: the predicate never asks who the assignee is, so an author-wedged task
  is covered by the sentence even though F70's recovery cannot recognise it. That is unchanged from
  2026-08-31 and is re-measured here, not assumed.
- **`t_f156_preview_promises_the_merge.py` — 21/21.** F156 reproduces **verbatim and stays open**.
  `integration-preview` answered `will_merge: true` with an empty reason over the exact commit the
  gate refused seconds later for a conflict; the drawer's amber *"it cherry-picks &lt;sha&gt; from
  &lt;branch&gt; into &lt;main&gt;"* is rendered from those fields; the preview was byte-identical
  after the refusal, having learned nothing; and the contrast lane's clean task got the same
  `will_merge: true` and merged. One word covered both outcomes and distinguished nothing. This is
  the third consecutive drive to reproduce it, and it is the finding N-3..N-6's spec loop is queued
  behind.

Both projects (`proj-887e34c7724b`, `proj-63e4a31bf689`) and both temporary repositories were
deleted afterwards; the `aw-f155-*` directories left in `%TEMP%` by earlier sessions were not
touched.

---

# Sweep, row 9a of 19: Spec flow — documents, and the phase machine

Driven 2026-09-01 ~04:55–05:10 +01:00 against the `:8011` trial Hub (beta profile, PID 22908, this
branch's code) on two throwaway projects built by `scripts/drive/setup_row7.py`, both deleted
afterwards. Row 9 is the largest row in the coverage matrix; this is the **9a** split named in
`STATE-night.json` — documents (create / adopt / arrange / merge / phase) and the phase machine.
Requirements, coverage, rigor and proposals are **9b**; evidence, decisions, reviews, drift and
reindex are **9c**, and neither was driven here.

Kept: `scripts/drive/t_sweep_row9_documents.py` (**196 PASS / 11 FAIL**, then **195 / 10** on a
second run over the state the first left — the one-assertion difference is the virgin-corpus branch
in leg 6, and the substantive reds are the same set both times) and
`scripts/drive/t_sweep_row9_ui.py` (**2 failing, twice, the same two**). Screenshots in
`%TEMP%\row9shots`.


**FIXED 2026-09-22 (interactive session, Round 2).** The table was complete and unreadable;
`history_for` existed and nothing called it outside tests.

- **`GET /projects/{id}/tasks/{task_id}/transitions`** answers `{"transitions": [...]}`, oldest
  first. Each row carries `sequence`, `from_status`, `to_status`, `actor_kind`, `actor_agent`,
  `run_id`, `origin` and `policy_digest` — the digest that records what governed an approval, and
  that nothing has ever been able to read. `sequence` is in the response because it, not
  `created_at`, is what orders the history: moves staged in one flush share a timestamp.
- **404 for an unknown task, `{"transitions": []}` for one that never moved.** "No history" and
  "no such task" are different answers, and a task older than the table legitimately has the first.
- **The agent plane has it too** (`/agent-actions/tasks/{id}/transitions`), because
  author/reviewer separation is decided from these rows: a reviewer asking "who completed this?"
  should read the record rather than infer it from `updated_by_run_id`, which holds only the latest
  run to touch the task.
- **`task_history(task_id)`** is the MCP read, with the tool surface and
  `docs/reference/mcp-tools.md` carrying it.
- **The operator's screen is the point of the finding**, so `TaskDetailDrawer` gained a History
  section (`TaskTransitionHistory`). It distinguishes what the table distinguishes: the operator
  from a run, and a move the runtime made on a run's behalf (`origin: "runtime"`) from one the run
  chose — rendered "was moved for" rather than "moved". **This is also what keeps the route out of
  `n10`'s clientless set**: the ceiling is 35 and exactly met, so an operator route with no screen
  would have failed `test_no_new_route_without_a_client`. Measured after the change: still 35.
- **Tests:** two in `test_tasks.py` (the history reads the same on both planes; an unknown task is
  a 404 while a never-moved one is an empty list) and four vitest.

<!-- followed F208 in FINDINGS.md -->
## What held — and the machine itself is close to airtight

The larger half of this row, and the right shape for a subsystem this well built.

**The phase machine, walked whole.** Five phases × six targets = 30 ordered pairs, against a map
**transcribed by hand** into the harness rather than imported (row 8's lesson 7 — importing
`TRANSITIONS` would assert the product against itself).

- **All 7 declared edges accepted**, each on a document walked into its from-phase through the real
  routes, and each verified afterwards to be in the phase it claimed.
- **All 23 non-edges refused 409**, every one with the right code: `phase_unchanged` for the four
  self-moves; `unknown_phase` for `current` and for a nonsense target, at every from-phase;
  `illegal_transition` for the rest, each naming **both** phases in its sentence.
- **No refusal moved anything** — re-read after every one of the 23.
- **`current` is exactly as unreachable as it is documented to be.** `to=current` is
  `unknown_phase` from all five phases including `current` itself (the to-phase check runs before
  the same-phase check, so `current -> current` is `unknown_phase` rather than `phase_unchanged`);
  a capability document is created at `current` and refuses all four transitionable targets with
  `illegal_transition`. **There is no exit from `archived` either**: all three attempts refused.

**Every gate around it.** `explore_not_closed` refuses `exploring -> proposed` before exploration is
closed and lets it through after; **reopening genuinely reopens** — the reopened document needs the
operator to close exploration again; `archive_would_orphan_work` refuses and says what to do
instead; and an empty `exploring` document **can** be archived, so F37's edge works even though
F205 says nothing offers it. `first_approved_at`, read **read-only out of sqlite** because no route
exposes it, is set on first approval and **survives a reopen-then-reapprove unchanged** — the
column's own comment made a promise and the promise holds.

**Creation.** A minted path is a valid spec path, `exploring`, `change-spec`, `sketch`. All five
`SPEC_KINDS` create, and `capability` lands in `current` and nothing else does. **F112 stays
fixed**: `kind: "change"` is `409 unknown_kind` listing all five kinds, not the 500 it once was.
Seven unsafe paths — traversal, absolute, uppercase, wrong extension, outside `spec/`, hidden
segment, backslash — all `400`. An unhonourable body field is `422` naming it.

**Adoption.** A document copied onto disk beside the corpus adopts at `201` and **its phase is read
from the file** — an `approved` document adopts as `approved`, not defaulted to `exploring`. Each
refusal lands on its documented status: `document_exists` 409, `file_missing` 422, `payload_absent`
422, unsafe path 400.

**Arrange, once an index exists.** Parent set and cleared; self-parent, unknown parent and a
two-document cycle each `422` from `load_manifest`'s own structural rules; a document not in the
index `404`; an unsafe path `400`. Naming a home wrote `spec/index.json` over 30 documents, and a
recorded home is preserved on a later reindex without restating it.

**Merge.** Into a non-capability document `409 not_a_capability`; from an `exploring` source
`409 source_not_finished`; from a path with no document `404`; naming no source `422`; an
unhonourable field `422`. A real merge from one `approved` and one `archived` change returned
`merged: 2`, left the capability document in `current`, and **left both sources in the phases they
were in**.

**The two planes stay separate.** Read off the **live** OpenAPI, not the source: the agent plane has
no phase route, no `close-exploration` and no `propose`. Approval is not something an agent can
reach by any path the running build serves.

**F202's shape does NOT generalise to this subsystem, and that is a measurement, not an
assumption.** The document list was asked the boundary question rather than read for a `limit`
parameter: at **147 documents** it returned 147, and on the second run at **294** it returned 294.
There is no `limit` or `offset` anywhere in `hub/hub/api/v1/spec.py`. `GET /specs` and
`GET /documents` differ by exactly the files discovery found on disk that the Hub never created —
each carrying `phase: null`, which is what `list_specs` documents — and every tracked path in
`/specs` carries the phase `/documents` gave it. Coverage still answered at 294.

<!-- followed F208 in FINDINGS.md -->
## Considered and not filed

- **`GET /specs` reporting more documents than `GET /documents`.** The first draft asserted the two
  counts were equal and it went red at 148 vs 147. They answer different questions on purpose —
  `/documents` is the Hub's record, `/specs` is disk discovery — and the extra path was the
  payload-less file the adoption leg had just written, carrying `phase: null` exactly as
  `list_specs` says it will. The assertion was wrong; the product was not. Rewritten to assert the
  containment and the shape of the difference, which is what actually holds.
- **The operator plane having no `rename` route.** `POST /agent-actions/spec/documents/rename`
  exists; there is no operator equivalent, and the UI is built to *follow* a rename
  (`hub/ui/src/api/spec.ts:162-171`, *"Follow the document when the agent renames it"*) rather than
  to perform one. Left unfiled because unlike F206's five routes this may be a deliberate division —
  an agent names the document it is exploring — and calling it a defect would be guessing at intent.
  Recorded here so 9b can ask the operator rather than rediscover it.

<!-- followed F208 in FINDINGS.md -->
## Method notes worth carrying

- **The bodyless probe is worth running once per subsystem.** F204 was found by the harness failing
  on its own first call, not by an assertion anyone wrote. Three sibling routes, two of which need
  no body — the odd one out is only visible if you call them the same way.
- **Ask the product what it will accept, then ask the screen what it offers, and compare.** The UI
  harness asks the Hub to archive a *throwaway twin* of each subject before opening the browser, so
  the table in F205 is Hub-behaviour against screen-behaviour rather than screen-behaviour against
  the harness author's belief.
- **Row 8's lesson 8 fired twice more, both times against this harness.** The first UI run clicked
  rows in the tree to open documents; the clicks silently did nothing and the phase pill read
  `exploring` for all six subjects, so *four* assertions "measured" one document six times. And in
  leg 6 every arrange refusal passed — for `409 no usable index`, not for the structural rule each
  was named after. Both were caught by reading the reason for the green, not the green.
- **State the precondition instead of asserting through it.** Run 2 of the API harness reported two
  reds that were facts about run 1 (an index its first run wrote, and a home that is preserved).
  The virgin-corpus checks are now gated on `index.written is None` and say so.
- **`spec/index.json` is the second thing `reindex` rebuilds, and it can silently write nothing.**
  A `200` from that route with `index.written: null` is the normal answer on a corpus with no home
  recorded. Anything downstream that assumes an index exists because reindex succeeded is wrong;
  9c should check that assumption where drift reads the manifest.

---

# Sweep, row 9b of 19 — SPEC FLOW: requirements, coverage, rigor, proposals

Driven 2026-09-01, iteration 12, against the trial Hub on **8011** (beta profile, this branch's
code), fixture project `proj-401c38a75fcd`. Harness:
`scripts/drive/t_sweep_row9b_requirements.py`, **129 passed / 10 failed, twice**, the second run on
the state the first left. Every red below is one of those ten.

Row 9a (documents, phase, adopt/arrange/merge) is the previous section. 9c — evidence, decisions,
reviews, drift, reindex — is still unrun.

<!-- followed F214 in FINDINGS.md -->
## What held — and most of this subsystem is in good shape

The reds above are six narrow things. 129 assertions passed, twice, across the four areas:

**Requirements index.** Identifiers minted on write and reported back by the write; every row
carrying key, digest, anchor, document and state; ordering by identifier; per-document filtering;
`?document=` on an unknown path refused **404** rather than silently answering project-wide.
Retirement is real and reversible-looking: dropping `fr-3` from a payload marks the row `retired`
rather than deleting it, `include_retired=false` hides it, `true` shows it, and the default is
`true`.

**The boundary question, asked of a different table than 9a's.** F202's shape does not generalise
here either: a **120-requirement** document returns 120, and the project-wide list returned **661**
rows in one answer. There is no `limit` or `offset` anywhere in `spec.py`.

**Requirement detail.** For an unambiguous identifier it answers 200 with `tasks`, `evidence` and
`coverage`; coverage is never null for an indexed requirement and **never states a state without an
integration answer** — the invariant `requirement_coverage.py` insists on, checked from outside. A
fresh requirement reads `unserved`; creating a task naming it moves it to `not_started` and the
requirement then names the task, closing the navigation the route exists for. Naming a different
document returns *that* document's same-named requirement rather than guessing.

**Ambiguity is refused, not resolved.** A bare identifier declared by 34 documents is **422** with
"name the document it belongs to". A task naming that identifier is still created — and its create
response says so: `unresolved_requirements: [{"reference": "FR-1", "reason": "ambiguous"}]`. Nothing
is guessed and nothing is silently dropped, which is the whole point of the module.

**Coverage.** Project-wide and per-document from one implementation; state totals and integration
totals each summing to the entry count; `unserved` excluding retired rows (measured against the
active twins of the same name, not assumed); an unknown document 404.

**Rigor, which is the best-defended thing in this row.** Unknown rigor -> 409 `unknown_rigor` listing
the three that exist. Same rigor -> 409 `rigor_unchanged`. Promoting a document with no payload ->
409 `document_not_enforceable`, with `blocking` naming what to fix in the operator's words. Demoting
the same unreadable document is **not** refused for enforceability — the asymmetry the module argues
for, holding in practice. Compare-and-swap works both ways: a stale digest is refused `stale_digest`
and **the rigor did not move**; the current digest lands. `contract -> gate -> sketch` all accepted,
demotion destroyed no requirement rows, and `rigor-history` kept all three steps in order with
actor, reason and timestamp. `rigor-history` on an unknown document is 404.

**No agent plane, confirmed against the live OpenAPI.** No agent-plane rigor route, so an agent
blocked by a gate genuinely cannot lower it; no agent-plane proposal-decision route; no agent-plane
requirements or coverage route.

**Proposals.** A `contract`-rigor write returns `proposals` instead of `identifiers` and **the live
document is untouched**, verified by reading the content before and after. Pending list ordered by
creation, each entry naming its proposer and carrying `resolved_at: null`. Accept on a stale digest
refused; accept on the current digest applies and the live document changes. Accepting twice -> 409;
rejecting twice -> 409; a proposal id under the wrong document -> 404; an unknown id -> 404; resolved
proposals leave the pending list. Reject keeps its reason. A `sketch`-rigor write still writes and
still reports identifiers — the contrast case that proves the gate is the document's property, not
the caller's.

<!-- followed F214 in FINDINGS.md -->
## Considered and not filed

- **Per-document identifier minting is not a defect.** `FR-1` in every document looks alarming and
  is deliberate (`spec_index.py:349`), and the ambiguity refusal that follows from it is the correct
  handling. What is filed is F212 — one *surface* that hands out identifiers it cannot resolve.
- **The `?document=` requirement on the detail route.** Unusable bare in any multi-document project,
  but that is the same design, correctly enforced. It becomes a real problem only in combination
  with F211 (no screen calls it) and F212 (the one list that feeds it drops the document).
- **Rigor's optional `expected_digest`.** Omitting it promotes a document the compare-and-swap had
  just protected — driven both ways: the loser of a real race is refused `stale_digest`, and the
  same document is then promoted by a call that simply omits the digest. This is **not** F207's
  shape: it is one route with one documented, deliberate optionality (*"Optional so a caller that
  has not read the document can still act"*), not a second route bypassing the first's checks. The
  UI always sends one. Recorded because a reader of F207 will want to know it was asked.

<!-- followed F214 in FINDINGS.md -->
## Method notes

- **Two harness bugs, both the same bug, both caught by reading the reason for the green (and the
  red).** Run 1 assumed identifiers were project-unique and produced seven reds that were facts
  about the harness. Run 2 fixed that by picking "the 119th requirement of the biggest document" —
  which stopped being unique the moment the harness ran a second time in the same project. The fix
  that stuck **measures**: count identifiers project-wide, build a document larger than every other
  one, and take the identifiers only it can have. Row 9a's lesson 10 in its sharpest form — *a
  harness that runs twice must state its precondition, not inherit it.*
- **One of the seven false reds hid a real one.** "It is no longer unserved" passed in run 1 —
  because coverage was `None`, and `None.get(...) != "unserved"` is true. A green for a reason you
  cannot name has measured nothing; naming it is what turned the leg into F212's evidence.
- **The bodyless probe found F210**, exactly as it found F204, and the *negative* result on rigor is
  the same probe doing its other job: telling you which routes are fine.
- **Ask both halves of a pair.** F209 exists because accept and reject were driven with the same
  body and compared. Neither call is wrong on its own reading.

---

# Sweep, row 9c of 19 — SPEC FLOW: evidence, decisions, reviews, drift, reindex

Driven 2026-09-01, day window iteration 2, against the trial Hub on **8011** (beta profile, PID
22908, started 01:48; no `.py` under `hub/hub` or `src` is newer than that, checked before anything
was concluded). Row 9a (documents, phase, adopt/arrange/merge) and 9b (requirements, coverage,
rigor, proposals) are the two sections above. **This closes row 9.**

Two harnesses, both kept:

- `scripts/drive/t_sweep_row9c_evidence.py` — the operator plane. **91 passed / 3 failed**, the
  second run on the state the first left; the three reds are F216 and F218 below.
- `scripts/drive/t_sweep_row9c_agent_plane.py` — the agent plane, driven with **real
  `claude-haiku-4-5` turns**. **21 passed / 0 failed, twice.** 9b measured that two of the agent
  plane's five spec routes are evidence, which makes this the one part of row 9 with a real agent
  surface; there is no shortcut to it, because `get_agent_actor` resolves a run credential whose
  plaintext exists only in the spawned process's memory. Six agent turns across the two runs, every
  one `completed`.

Four fixture projects, all deleted afterwards.

<!-- followed F218 in FINDINGS.md -->
## What held — and this is a well-built subsystem behind an absent surface

91 assertions passed on the operator plane and 21 on the agent plane, twice each.

**Recording.** An operator's own observation lands `accepted` with an auto-review naming them; an
agent's lands `awaiting` with its `run_id`, and no prompt persuaded it otherwise. The footprint is
present on both, carrying kind, branch, commit and `reachable_from_main`. **F71 holds in both
directions**: a locator naming a commit the repository does not have is refused
`409 locator_commit_unknown` rather than falling back to `HEAD`, and a locator naming a real *older*
commit is footprinted at that commit rather than the checkout's. Every refusal on its documented
status: unknown identifier 404, unknown document 404, a bare identifier declared twice
`422 "name the document it belongs to"`, a retired requirement `409 requirement_retired` ending
*"there is nothing left to demonstrate"*, and a genuine duplicate
(same requirement + task + commit + actor) `409 duplicate_evidence` naming the row it would repeat
and what to do instead.

**Deciding, and the capability model.** An unknown decision is **422 `unknown_decision` naming both
permitted values** — F8's fix holding, a validation error not an authorisation one. An unknown
evidence id is 404. Decisions are append-only and reversible, and `review_state` follows the latest.
Driven with real agent turns: an **ungranted** agent asked to decide its own evidence changed
nothing; the operator granted `can_accept_evidence` through `PATCH /agents/{name}` and it read back;
a **granted** agent then accepted a peer's evidence and the review names *the agent*, with its run
id, not the operator. The grant is not decorative and the self-acceptance rule is real.

**Reviews.** The trail is complete and ordered — three decisions on one row came back
`accepted, rejected, accepted`, each with actor, reason and timestamp, the operator's reason
verbatim, and the agent's decision carried in the same list as the operator's. 404 on an unknown id.

**Drift, once you can reach it.** A clean scan raises nothing, twice. A commit that only **adds** a
file raises nothing — `_changed` walks the baseline's paths, so a path the footprint never saw
cannot differ from it, which is what the code says it does. A commit **changing** a footprinted path
raises a candidate whose `observed` names **only** that path, with `was` and `now`. Rejected
evidence never becomes a candidate. A resolution records the fingerprint it was given and the same
change is **not** re-raised, while a *new* change to the same file **is** — so the resolution
neither nags nor silences. `422 unknown_resolution` on a bad enum, 404 on an unknown id. A
**reworded** requirement raises no new drift: that is staleness, and the module refuses to ask the
operator the same question in two vocabularies.

**Reindex, and 9a's sharpest lead answered.** 9a asked what downstream assumes an index exists
because reindex answered 200 with `index.written: null`. Driven: **nothing new does.**
`detect_drift` never reads the manifest at all — it reads footprints and git trees — and answered
200 on the unindexed corpus; coverage answered 200. The one route that refuses is
`POST /spec/documents/arrange`, and that refusal is **F208**, already filed and unchanged (*"no
usable index to arrange (absent)"*, `diagnostics: []`, the word "reindex" absent). The lead
resolves to a re-confirmation rather than a new finding. Naming a home wrote `spec/index.json`, a
later bodyless reindex preserved it, and a home naming a path that is not a document did not
silently become the home.

**Retention.** `never` is accepted as a first-class policy; an unknown one is 422 listing all five.

**The bodyless probe, and a clean negative.** F204/F210 are a model whose fields *all* default being
refused anyway. **That shape is absent from 9c, measured rather than read off the signatures.**
`POST /spec/reindex` — every field defaulting — answers **200** with no body at all. The four routes
that refuse a bodyless call each have a genuinely required field, and each names it the moment the
caller sends `{}`: `identifier`, `decision`, `resolution`, `policy`. `POST /spec/drift/detect` takes
no body and answers 200. Nothing here needs F204's one-word fix.

**The two planes stay separate, read off the live OpenAPI.** The agent plane carries exactly five
spec routes and two are evidence; there is **no** agent-plane drift route, no reindex route and no
reviews route. Drift is the operator's judgement and the running build enforces that by not offering
it.

<!-- followed F218 in FINDINGS.md -->
## Considered and not filed

- **`_changed` ignoring added files.** A commit that only adds a file raises nothing. That is what
  the function says it computes (*"which of the footprinted paths no longer look the way they did"*)
  and it cost this harness its first run. Recorded as a measured negative, not a defect.
- **A bodyless call on an unknown evidence id answering 422 rather than 404.** The schema layer is
  ordered ahead of the lookup, which is F201's ordering. Not filed: with a well-formed body the same
  call is a clean 404, measured, so no correct caller ever meets it.
- **44 candidates from one commit.** Folded into F215's cost paragraph rather than filed separately,
  because `read_footprint`'s docstring already states the cause and defers the fix on stated
  grounds. What was missing was the number, and the fact that the queue it creates has no surface.

<!-- followed F218 in FINDINGS.md -->
## Method notes

- **The control needle is what makes a zero mean something.** Leg 8 greps for `spec/coverage`
  first, gets 1, and only then reports six zeros. Without it, "0 hits" is indistinguishable from a
  wrong needle — and it very nearly was: the first draft's six zeros looked identical to the ones a
  broad `grep -il evidence` immediately contradicted with 21 files. The words are in the UI; the
  *routes* are not, and only the narrow needle plus the control tells those apart.
- **Read the reason for the green, and for the red.** The first run's drift leg was red because the
  harness added a file rather than changing one. The product was right and the harness was wrong —
  and chasing it is what produced the added-vs-changed negative above.
- **Drive the plane you cannot fake.** The agent-plane leg costs three real Haiku turns per run and
  found F217, which no operator-plane call could have surfaced: the finding *is* the difference
  between the two planes, so it only exists when both have been driven.
- **Ask the screen what it says, not only what it calls.** F215's teeth are not the six zeros —
  F206 and F211 already established that shape. They are `SpecCoverageBar`'s two sentences, which
  are in the served bundle and instruct the operator to do something the bundle cannot do.

---

<!-- followed F240 in FINDINGS.md -->
## Row 15 WORKTREES — per-agent isolation and conflicts, driven 2026-09-01

Driven on the `:8011` Hub (pid 22908, started 01:48:32; no `.py` under `hub/hub` or `src` newer
than it) against a fixture this harness creates and destroys: `aw-drive-row15`
(`proj-a214ba696422`, a git repository seeded with `calc.py`) plus `aw-drive-row15-nogit`
(deliberately not a repository), three roster agents, one self-registered agent, three real
`claude-haiku-4-5` turns per run. Reproduction throughout:
`scripts/drive/t_sweep_row15_worktrees.py`, **40 passed / 14 failed, twice, the second run on the
state the first left**.

**Prior coverage was read first.** `t_row16_worktrees.py` (old row numbering) drove the mechanism
on 2026-08-29 and the block at `FINDINGS.md:8093` records the result: isolation holds, each task
edits on its own branch, `main` untouched, `GET /worktrees/conflicts` naming both *task*
workspaces and `calc.py`. That harness prints and asserts nothing, and it stops where the conflict
report exists. This one starts there.

### The mechanism, re-driven with assertions — it holds

Recorded first, because a sweep that reports only defects is not a measurement. All of the
following passed twice:

* Reading the surface **provisions nothing**: three reads (`GET /worktrees`,
  `/worktrees/conflicts`, `/worktrees/{agent}`) left the set of directories under
  `.agentweave/{worktrees,tasks,reviews}` identical, and `provisioned` matched `os.path.isdir` of
  the very path the endpoint reported.
* Two parallel task-bound turns each got **their own checkout on their own branch**; `alpha`'s
  function is on `alpha`'s task branch and absent from `beta`'s and from `master`, and the
  converse; `git show master:calc.py` is unchanged by either turn.
* `GET /worktrees/conflicts` named both task workspaces and `calc.py`, and its answer is
  **equal to the paths `git merge-tree --write-tree --name-only` produces here** — checked against
  git rather than against itself.
* `GET /worktrees/{agent}` listed the agent's live task checkout with `provisioned: true` and
  `grandfathered: false`.
* Refusals held: the reserved name `user`, a name with a dot in it, and a 40-character name are
  all 400; an unknown project is 404.
* Releasing a finished task **keeps its branch** and records the release with the unmerged commits
  it is leaving behind: `task_worktree_released ... "unmerged_commits":
  ["0a05f571307f1da100ff5315763b4ffd08d6a375"]`, severity `warn`.
* A **self-registered** agent with `config: {"read_only": true}` shares the project checkout, with
  `isolated: false` and `working_dir` equal to the project root — exactly as designed.
* The one-run-per-task refusal earned its keep by accident. Run 2's `beta` held two live tasks,
  read the wrong one off `list_tasks` and implemented it, then tried to close it — `update_task`
  refused with *"A run finishes the task it took, and takes at most one."* The agent read the
  refusal correctly and closed the task it was actually bound to.

---

<!-- followed F265 in FINDINGS.md -->
## 0.3 — R3b IS WRONG. The single-run indicator releases cleanly, and round 2 was right.

Conversation `conv-2f638d586e54`, one run `run-6d1f53add52e`, allowed to complete:

```
t=  0.0s  running=True  sig1_entry=False sig2_lifecycle=False settled=False  INDICATOR=True   answers=0
t=  0.7s  running=True  sig1_entry=False sig2_lifecycle=False settled=False  INDICATOR=True   answers=0  statusByRun={'run-6d1f53add52e': 'started'}
t=  7.9s  running=True  sig1_entry=True  sig2_lifecycle=False settled=True   INDICATOR=False  answers=1
t=  8.6s  running=False sig1_entry=True  sig2_lifecycle=False settled=True   INDICATOR=False  answers=1
```

The answer text and `signal 1` land on the **same snapshot**, and the indicator goes out on that
snapshot — 0.7 s *before* the roster poll flips `running` to `idle`. That is precisely the atomic
handover `AgentTimeline.tsx:88-113` claims to have been built for, working.

Round 3b's supplementary pass concluded the opposite, on this reasoning: *"`entries` reach
`AgentTimeline` only through `useAgentChatHistory` ... the chat route builds them from persisted
`AgentOutput` rows. A row that is only broadcast never becomes an entry, so
`isSuccessCompletionEntry` has never matched anything, in any state."* Every clause of that is true
except the conclusion. Measured: conversation A's chat entries contain **exactly one** match,
`payload={"version": 1, "phase": "completed", "summary": "Completed"}`.

The mistake is an identification, not a deduction. R3b traced the terminal status line at
`agent_trigger.py:2135` — which is indeed only broadcast — and concluded no such *entry* exists.
The entry that satisfies `isSuccessCompletionEntry` is a **different row from a different writer**:
the stream parser's own `status_event("completed", ...)`, which is persisted. This ledger already
recorded that, in *"A refinement to F190's second half, measured rather than assumed"* above:
completed runs carry one persisted `status` row, stopped runs carry none. Round 3b read the code
and did not read the measurement already in the file it was arguing about.

**Consequence, per task 0.3's own instruction: the change goes back for a round before phase 1.**

**What still stands, on a narrower argument than the proposal makes.** Signal 1 fires only for a run
that *finishes*. For the stopped run below there are zero `status` rows and zero
`isSuccessCompletionEntry` matches, so `lastRunSettled` is False for the whole life of the
conversation and the gate collapses to `isRunning` alone. D6's *purpose* — a working
`lastRunSettled` for runs that do not complete, plus a durable exit code — survives the drive
intact. Only R3b's reason for it ("it has never worked at all") is false, and the proposal's phase 2
should be re-argued from the true premise: it has never worked **for a run that did not complete**.

<!-- followed F265 in FINDINGS.md -->
## 0.4 — CONFIRMED, and caught happening rather than derived

Round 2's correction 1 predicted `anotherRunIsUnderway` overrides `lastRunSettled` in every state
once two or more runs sit in the event window, collapsing the gate to `isRunning`. It does, and the
drive caught the regression live in the very next conversation:

```
conversation B (two runs in the window)
t= 10.7s  running=True  sig1_entry=True  settled=True  another=True   INDICATOR=True   answers=1
t= 11.3s  running=False sig1_entry=True  settled=True  another=True   INDICATOR=False  answers=1
```

Same agent, same instrument, ~40 seconds apart: with **one** run in the window the indicator went
out the instant the answer arrived; with **two** it stayed lit under a finished answer until the
roster poll caught up. That is the exact complaint the 2026-08-18 fix was written to remove
(operator: *"the working indicator ... stays active for a couple more seconds then disappears"*),
reappearing in every conversation on any agent with two or more runs in its event window — which,
after a day's use, is every conversation. The tail measured here is one poll interval (0.6 s in the
harness); on screen it is however long the roster poll takes.

The cause is upstream and is F190's own: `statusByRun` was `'started'` for **every run in every
snapshot of the whole drive** — five runs, five `started`, one of them stopped, one interrupted,
three completed. `anotherRunIsUnderway` asks whether any run other than the last is non-terminal,
and the answer is unconditionally yes.

<!-- followed F265 in FINDINGS.md -->
## 0.2 — CONFIRMED. A stopped turn presents nothing at all.

`t_f190_phase0_observe.py`'s first attempt did **not** observe this and said so: the Haiku turn ended
at 11.3 s and the stop was issued at 14 s, so `POST /stop` returned `404 driver has no run in
progress` and what it measured was a completed run wearing the stop leg's name. Recorded because a
harness that reports the right answer for the wrong reason is the failure mode this whole gate
exists to catch. `t_f190_phase0_stop.py` redoes it with the stop at 4 s and checks the route
returned 200 before believing anything downstream.

Run `run-2ee37e1352f3`, `POST /stop` -> `200 {"status": "stopping"}`. The database is unambiguous:

```
runs:        run-2ee37e1352f3   status=stopped   started 22:21:16.783   ended 22:21:21.295
event_logs:  22:21:21.358762  run_stopped
             22:21:16.841635  run_started
```

and `/agents/driver/timeline` returns them in that order — **newest first**, live, exactly as
`agents.py`'s `reverse=True` sort says. `runStatusByRunId` assigns unconditionally as it iterates,
so the last event it sees is `run_started`, `statusByRun[run] = 'started'`, and
`TERMINAL_LABEL['started']` is `undefined`.

What the operator is left with, read from the route: conversation `conv-de81cf9f9e03` has **one**
chat entry, `[operator_input]`. Their own message, and then nothing — no answer, no label, no trace
that a turn was ever stopped.

**The interrupted case is the same, and was not previously measured.** After 0.6's reconciliation,
`conv-af5d7a6916fc` reports `statusByRun = 'started'` for `run-ac917a010c1d` and
`TERMINAL_LABEL = None`, though `run_interrupted` is the newest event in the whole log. F190 named
three statuses; two of the three are now driven, and the third (`failed`) follows from the same
line.

<!-- followed F265 in FINDINGS.md -->
## 0.5 — CONFIRMED, unchanged from round 1's measurement

A fresh read of both routes after the run ended: label still `None`. `/agents/driver/output` held
**9 rows, 3 of `kind="status"`**, and **zero** of them belong to the stopped run — all three are
the completed runs' `{"phase": "completed", "summary": "Completed"}`. The stopped conversation's
`isSuccessCompletionEntry` match count is **0**.

<!-- followed F265 in FINDINGS.md -->
## 0.6 — CONFIRMED. The reconciliation event carries restart time, not run time.

Run `run-ac917a010c1d` was started, the Hub was killed (`Stop-Process -Force`) with it in flight,
and its process was gone. The row survived as `status=running`, which was read from the database
while nothing was serving it. On restart: `WARNI [hub.run_reconciliation] Reconciled 1 orphaned
run(s) to status=interrupted on Hub start`.

```
Run.started_at              2026-09-01 22:22:13.906755
Run.ended_at                2026-09-01 22:24:01.188495
event run_interrupted       2026-09-01 22:24:01.202550     <- 107.3s after the run started
```

The 107.3 s is the length of the outage, and nothing else — it is not a property of the run. The
event is the **newest row in the entire log**, ahead of every event of every other run, while
`Run.started_at` is untouched at its original value. `reconcile_interrupted_runs`
(`run_reconciliation.py:59`) selects `Run.status == "running"` with **no age bound, no limit and no
project scope**, so the same thing happens to a row from last week.

**Stated as a limit rather than glossed:** this fixture had five runs and the interrupted one was
also the newest by `started_at`, so a `started_at DESC LIMIT n` query would not have missed it
*here*. What is measured is the decoupling — terminal event at restart time, `started_at` old — plus
the code fact that the sweep is unbounded. The miss itself needs more runs than a drive can
usefully spend and was not reproduced. Design D3's reversal rests on the decoupling, which held.

<!-- followed F265 in FINDINGS.md -->
## Housekeeping, and one thing seen in passing

Fixture `proj-83415a23d9d5` deleted after the drive; the project count returned to its prior value.
No job or loop was created, and the sweep for enabled jobs is recorded in the night log.

Seen while building the rig, not a phase-0 observation and not filed as a finding:
`POST /projects/{p}/runners` refuses `model: "claude-haiku-4-5"` with *"'claude-haiku-4-5' is not a
model 'claude' declares"* — the catalog declares only the dated `claude-haiku-4-5-20251001`
(`model_catalog.py:164`). Noted here because the rest of tonight's queue is
`runner-model-is-chosen-from-the-catalog`, and a picker fed from the catalog will therefore offer
dated ids only.

---

<!-- followed F268 in FINDINGS.md -->
## What held, D-1, 2026-09-02 — the independent re-drive of `runner-model-is-chosen-from-the-catalog`

Recorded because a drive that reports only defects describes a different product, and because the
night window's three retirements were **its own author's drive of its own change**. These are the
same claims re-derived from `openspec/specs/runner-registry/spec.md` and from
`GET /model-catalog` — never from the component's source — and driven against the **served bundle**
on the Hub's own port, no Vite dev server anywhere.

- **The picker offers the catalog's models, and only those.** For `claude` and for `codex`, the
  `<select>`'s option values were `[""] + <exactly the ids GET /model-catalog declares>`, in catalog
  order, and every declared model was present by its declared *label* too. Changing the CLI reset
  the selection to the empty `Provider default` value — unset, not that provider's default model.
- **No free-typed model field.** The dialog carries one text input, `placeholder="e.g. Claude Opus"`
  — the Name field, which task 4.2 was explicitly careful to keep.
- **The Add-agent dialog offers exactly the catalog's models** for both providers (no
  `Provider default` entry there, correctly — an agent must have one).
- **F173's error surface holds for a refusal an operator can actually cause from the screen.** The
  night window could only reach it by rewriting the request on the wire, because the model refusal
  is unreachable by construction now. This drive found one that is not: the Name field imposes no
  length cap of its own (300 typed, 300 accepted), so `RunnerCreate.name`'s `max_length=256` answers
  `422` with a **Pydantic list** `detail` — the exact body shape task 3.1's `readableApiError` swap
  exists for. On screen: the dialog stayed open, the 300 characters were still in the field, and the
  `role="alert"` read `String should have at most 256 characters` — prose, not a rendered object.
- **All four model doors refuse, and say what is wrong.** `'claude-fable-5-1' is not a model
  'claude' declares` — including from the composer's per-run override, which is validated before
  anything spawns, so the refusal costs no tokens.
- **A runner with no model is accepted** (`201`), which is the "unset is a valid, spawnable state"
  half of the requirement.
- **Cleanup measured, not assumed.** `DELETE /projects/proj-30e5779191b6` → `204`, and
  `GET /projects` → `[]` afterwards. No job was created; no agent turn was triggered, so nothing
  bound a model and the drive spent no tokens.

One presentation note, deliberately **not** filed as a finding: the `422`'s sentence is Pydantic's
own `msg` and names no field (`String should have at most 256 characters`). With one text input on
screen that is unambiguous today, and inventing a field name in the client would be worse.

<!-- followed F271 in FINDINGS.md -->
## What D-5 measured, 2026-09-02 — the reachability walk N-10 and N-11 both said they had not done

Both night scripts end on the same admission: their passes are **depth-1**, so they ask *"does any
file name this symbol"* and cannot see a subtree that is imported only by other dead code. F260 is
exactly that shape. This walks the import graph from the entry module instead.

Harness: `scripts/drive/d5_reachability_walk.py`, one command, no product code touched, no Hub
started, no database read. It **imports** `n10_route_reachability.py` and `n11_query_error_surface.py`
rather than reimplementing them, so every number below differs from theirs by the module filter and
by nothing else. Both were re-run first on today's tree and reproduce their published figures
exactly (110 / 35 / 107 / 101 / 60).

**The graph.** 170 source files under `hub/ui/src` (tests excluded). **157** are reachable from
`main.tsx` by runtime imports; **13 are not**. The choice of root does not matter — `App.tsx` alone
reaches 155, the two extra being `main.tsx` and `ErrorBoundary.tsx` — and neither do type-only
edges, which add exactly one file. No specifier failed to resolve, which matters: a silent
resolution failure would have manufactured unreachable files.

**Checked against the shipped bundle rather than asserted.** Each unreachable file donated the
literals that occur nowhere else under `src/`, probed in `hub/hub/static/ui/assets/index-x3nWU-L2.js`.
12 of 13 have **every** such literal absent. Twelve reachable files were probed the same way as
controls and every one of their literals is present, so the probe fails loudly rather than inventing
a result — it did fail, twice, and both rules it gained came from that: uniqueness measured by
*substring* (`'whitespace-pre-wrap'` is written once in `src/` and ships inside another module's
class chain, which made `SharedStreamRenderer` read as present), and comments, imports and `type`
declarations stripped first (`accounting.ts` declares `label: 'Rate-limit allowance'` inside a type
union — a string that can never reach the output).

The thirteenth is `components/common/badgeVariants.ts`, and it is settled by the compiler rather
than by the probe: its only importer is `Badge.tsx:3`'s `import type { BadgeVariant }`, which is
erased, so `statusVariant` and `priorityVariant` are called by nothing anywhere. Its literals are
status words shared with half the tree, so no probe could have decided it.

The 13, with what each is:

| Dead file | What it is |
|---|---|
| `api/context.ts` | `requestCompact`, `requestNewSession` — F260's two routes, now derived rather than probed |
| `api/messages.ts` | the messages client — F260 |
| `components/messages/{MessagesFeed,ConversationGroup,MessageCard}.tsx` | F260's components |
| `components/agents/AgentActivityTab.tsx` | imported by nothing — **new** |
| `components/agents/AgentCard.tsx` | imported by nothing — **new** |
| `components/layout/StatusBar.tsx` | imported by nothing — **new**, and see the F259 amendment below |
| `components/layout/SidebarItem.tsx` | imported by nothing — **new** |
| `components/stream/{SharedStreamRenderer.tsx,streamModel.ts}` | reached only from `AgentActivityTab` — **new** |
| `lib/agentStatus.tsx` | reached only from `AgentCard` — **new** |
| `components/common/badgeVariants.ts` | reached only by a type-only import — **new** |

**N-10's 110 becomes 106.** Four route+method pairs are reached only from dead code:
`GET /projects/{id}/messages`, `PATCH /projects/{id}/messages/{id}/read`,
`POST /projects/{id}/agents/{name}/compact` and `POST …/new-session`. So of 155 operator
route+method pairs, **49** are not reached by any code the app loads: 35 with no client anywhere,
10 called by the CLI transport, and these 4. The last group is a category R-1's question (a) did not
have: not *"no client was ever written"* but *"a client was written and its screen was removed"*.
N-10's own bundle probes already showed `/compact` and `/new-session` absent; the walk now says why.

**N-11's 101 becomes 93.** Of 107 call sites outside `api/`, **8** are in dead code — N-11 knew
about 3 (`MessagesFeed`) and flagged them `DEAD`; the other 5 are `AgentActivityTab.tsx:23-24` and
`StatusBar.tsx:15,16,19`. By class: MISREPORT **60 → 54**, SUPPRESSED **16 → 14**, BLANK 24
unchanged, NAMED 1 unchanged. N-11's "57 on a surface an operator can reach" is therefore **54**.

**The ranking, which is the useful output.** Counting unhandled sites was never the interesting
question — F271 is one of these sites and it is severity A, while dozens of others are cosmetic.
What separates them is whether a failed load can be *written back*. Three tests: does the query's
data seed component state; does the file write; and is there an early return naming that data,
which means the write never renders while the fetch is failing.

| Rank | | |
|---|---|---|
| **1** — seeds state, writes it back, **no guard** | **2** | `InstructionsPage.tsx:9` (= F271, driven) · `AgentOutputPanel.tsx:207` (below) |
| **1G** — same, but an early return hides the write | 2 | `AccountingPanel.tsx:22` (guard `:34`) · `ProjectSettingsPanel.tsx:53` (guard `:75`) — F197's terminal skeleton, not a destructive write |
| **2** — the file writes, but nothing seeds state from this query | 23 | an empty picker or an empty list, not an overwrite |
| **3** — no write in the file at all | 27 | read-only misreport |

Rank 1G exists because the first mechanical pass put all four in rank 1 and a hand read moved two
out. That is the pass working as intended: it proposes, and reading decides.

### The one candidate this raises, and it is NOT driven

`AgentOutputPanel.tsx:207` — `const { data: conversations = [] } = useAgentConversations(...)` — is
in rank 1, though for the wrong reason: the writes the script matched are the question mutations,
while the write that actually carries the seeded state is `postTrigger` at `:886`, which is not a
`useMutation` hook and so is invisible to it. Read by hand, four static facts:

1. `:236-243` seeds `pendingOverrides` from the open conversation's `runtime_overrides`. A failed
   conversations load leaves `conversations = []`, so `current` is undefined and `seeded` is `{}`.
2. Nothing guards the composer on that query, so the operator sees pills reading as *no override*.
3. `Composer.tsx:333` and `:336` change a pill by **spreading the local map** —
   `onPendingOverridesChange({ ...pendingOverrides, model: modelId })` — so after a failed load the
   spread starts from `{}`.
4. `agent_trigger.py:1364` assigns `conversation.runtime_overrides = accepted` wholesale, under
   `if body.overrides:` at `:1344`.

Together those say: sending with nothing touched is **harmless** (an empty map becomes `undefined`
via `emptyToUndefined`, and `if body.overrides:` leaves the stored value alone — the turn still runs
under the stored override, resolved at `:639`), but *changing one pill* after a failed load sends
`{effort: X}` alone and **replaces** a stored `{model: …, effort: …}`, silently dropping the model
override the operator set earlier.

**That is a static read of three files and it is not a finding.** It has no F-number for the same
reason N-11 gave none to the `InstructionsPage` suspicion: a static read cannot say what a page
renders. The drive that settles it: a conversation with a persisted `runtime_overrides` on `:8011`,
block `GET …/conversations`, confirm the composer still renders, change the effort pill, send a
Haiku turn, then read `conversation.runtime_overrides` back over the API. F271 came out of exactly
that suspicion-then-drive sequence, and it was worse than the static read predicted.

### F259 amendment, 2026-09-02 (D-5) — its headline names a surface that does not ship

F259's substance is untouched and was measured on the live instance: `msg.read = True` occurs once
in the Hub, nothing in the product calls it, and 82 messages across ten days are unread. Its
**consequence** is misattributed. The finding's title and its middle section put the count on
*"the StatusBar's `N msgs` chip"*, quoting `StatusBar.tsx:25` — and `StatusBar.tsx` is imported by
nothing and absent from the bundle (measured above; `Sidebar.tsx:112` even says in passing that it
"is no longer rendered"). So no operator sees that chip, and the unread count reaches no screen at
all today.

What survives, and is the reason the finding still matters: `GET /status` still computes
`message_counts.pending` from the flag, and `scheduler.py:420` still depends on it — which is F264,
and is where the consequence actually lands. Read F259 as *"nothing ever marks a message read, and
a scheduler decision depends on the flag"*; strike the chip.

The same correction applies to one line of `spec-queue/DECISIONS.md`'s R-1 evidence, which lists
*"four `?? 0` counts in the status bar"* among the 44 sentences said to be on screen
(`StatusBar.tsx:15`). They are not on screen. That block is amended there too.


<!-- followed F273 in FINDINGS.md -->
## What was driven, and what it said

| task | leg | result |
|---|---|---|
| 6.1 | a turn stopped 5s in | **8 checks passed** — `runs[run].status == 'stopped'`, label `'Turn stopped'`, indicator gone |
| 6.2 | the same conversation re-read from all three routes | label, `exit_code=2` and "Worked for 5s" all still there |
| 6.3a | a run whose CLI cannot spawn | **6 checks passed** — status `failed`, label `'Turn failed'`, `exit_code=1`, survives the re-read |
| 6.3b | the Hub's process tree killed mid-run, then restarted | **6 checks passed** — status `interrupted`, label `'Turn interrupted'`, "Worked for 21s" |
| 6.4 | the served bytes | the deleted reducer is **gone from the bundle**; the new read is **in** it (below) |
| 6.5 | teardown | project count back to **23**, **no enabled job or loop in any of the 23** |

The evaluation is `aturn_model.py`, a line-for-line transcription of the built `AgentTimeline.tsx`,
so each row above is what the operator's screen would say — not what the database contains.

<!-- followed F273 in FINDINGS.md -->
## Three things the drive established that the tests did not

**A stopped run's persisted status row says `phase: "completed"`.** Measured:
`{"phase": "completed", "exit_code": 2}` on a run that was stopped. This is deliberate and
documented at `agent_trigger.py:2141-2145` — `phase` means "the run has ended", not "it succeeded",
and it has exactly one reader. Recorded here because it is the kind of thing a later reader will
mistake for the outcome; the outcome is `runs[runId].status`.

**A failed spawn is retried twice, and the indicator stays up across the retries.** The 6.3a turn
produced **three** runs (`run-dd190aa1c9e8`, `run-c20a22f163b6`, `run-4e6adc1ae6db`), each `failed`
with `exit_code=1`. At t=4.7s the newest *turn*'s run had already failed while a *new* run was
`started`, and the indicator correctly stayed up — that is `anotherRunIsUnderway` (the stop-then-send
path) firing on a path nobody wrote it for. Unplanned confirmation, worth more than the planned one.

**An interrupted run is almost never the newest turn.** `run_reconciliation` reschedules the agent
as part of the same startup ("Draining 1 deferred post-reconciliation schedule(s)"), so a fresh run
appears under the interrupted one within ~3 seconds. The first read of 6.3b failed three checks for
this reason and **the harness was wrong, not the product**: it asserted about the newest turn. The
per-turn render was added to `aturn_model.py` and all six then passed, including
`Turn interrupted` + `Worked for 21s` on the interrupted turn while a completed turn sat below it.
This matters for phase 7: an assertion about an interrupted run that reads the *last* turn is
measuring the wrong row.

<!-- followed F273 in FINDINGS.md -->
## 6.4 — the bundle, checked against the served bytes

`npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. `GET /health` went from
`ui_stale: true` to no staleness field at all. Then `curl` of the served
`/assets/index-42oEFtKt.js` (1,106,788 bytes):

| marker | old bundle (`index-x3nWU-L2.js`) | served now |
|---|---|---|
| `run_started:"started",run_completed:"completed",…` — the **deleted** `LIFECYCLE_EVENT_STATUS` reducer | **1** | **0** |
| `ended_at` — `runDurationSeconds` reading the run row's own timestamps | **0** | **2** |
| `Turn interrupted` | 1 | 1 |

Both directions, on the bytes the browser receives. A string-literal grep alone would have proved
nothing here — the change added no new user-visible string — so the marker is the minifier-stable
object literal the change *removed*.

<!-- followed F273 in FINDINGS.md -->
## Not done here, on purpose

**F190 is not retired.** Task 6.7: the operator's condition of approval is that a round which did
not build the change verifies it, and that is phase 7. F269 likewise stays open — 7.1a is the check
that its fix fires, and this phase did not produce a turn whose only output is a status row.

<!-- followed F273 in FINDINGS.md -->
## Teardown

Fixture project deleted (`204`), 24 → **23** projects, the count that predates this drive. Jobs and
loops swept across all 23 **before and after**: none enabled. The fixture working directory
`C:\Users\huida\Documents\drive-aturn-p6-0903` is left on disk (outside this repo, ~1 file).

---

# F190 phase 7 — verified by a round that did not build it, driven 2026-09-03

The operator approved `a-turn-says-how-it-ended` on the condition that a round which did not write
the code verifies it. This is that round. Phase 6 was the implementer checking its own work; it
deliberately left F190 and F269 open (task 6.7) for this.

**Setup, and what was checked before anything was concluded.** Hub on **8011**, started from `hub/`
with `uvicorn hub.main:app` against a profile database of its own, from this branch's source. The
newest `.py` under `hub/hub` and `src` is `db/engine.py` at `02:49:37`; the process started at
`04:57` — **older, so the instance is not stale**, which is the check iteration 9 learned to make
first. Fresh fixture project, deleted afterwards. Every real agent turn on `claude-haiku-4-5`.
`/health` reported no staleness field, so the served bundle matches the committed source.

**The comparison is made on one capture, not across two drives.** `scripts/drive/t_aturn_p7.py`
reads all three routes once per assertion point and feeds the same bytes to both transcriptions:
`f190_model.evaluate(entries, envelope["events"], running)` — the UI as it stood at phase 0 — and
`aturn_model.evaluate(entries, envelope["runs"], running)` — the UI as built. The `events` half of
the envelope is byte-identical to the bare list the route used to return, so the phase-0 model
computes what the old UI would have computed **from today's data** rather than from a remembered
drive. `f190_model.py` was not edited.

<!-- followed F273 in FINDINGS.md -->
## The four observations

| phase 0 | phase 0 model, on today's data | built model, same bytes | verdict |
|---|---|---|---|
| 0.2 a stopped turn | `{"run-11aecfcb0285": "started"}`, label `None` | `stopped`, label `Turn stopped`, `exit=2`, `Worked for 5s` | **moved** |
| 0.5 after a reload | label `None` | label `Turn stopped`, exit code intact | **moved** |
| 0.4 two ended runs | `anotherRunIsUnderway=True`, every run `started` | `False`; each turn draws its **own** run's outcome | **moved** |
| 0.3 a completed run | releases, signal 1 fires, no label | releases, signal 1 fires, no label | **unchanged, as required** |

Three legs, **29 checks, 0 failed**: `stop` 9/9, `two` 9/9, `stopfast` 11/11.

0.5's second half is the one that used to be impossible. `GET /agents/{name}/output` now holds a
`kind="status"` row for the stopped run — `content="Run stopped (exit 2)."`,
`payload={"phase": "completed", "exit_code": 2}` — where phase 0 measured **zero** such rows out of
nine for the agent.

**RB's Codex correction honoured, and not overstepped.** Every run driven here was a Claude runner.
This drive says nothing about Codex; phase 0 has no Codex baseline, and none is read into it.

**Not re-driven:** the interrupted case, which needs a Hub kill and which phase 6 measured. 7.1's
own list does not name it.

<!-- followed F273 in FINDINGS.md -->
## Two things the round found that nobody had asked about

### The isolation test was green for the wrong reason

`test_bola.py` covers this route's cross-project isolation, and phase 1 kept it rather than
deleting it when the response became an envelope — the structural half of task 7.3 is right. Then
it was **mutation-checked instead of read**. Deleting `Run.project_id == project_id` from the
route's run lookup left the file **green, 4 passed**.

Task 1.6 had added a `Run` row to Project A's fixture specifically so `timeline["runs"] == {}`
would not be vacuous, and the reasoning does not hold: Project B owns no event naming that run, so
`run_ids` is empty and the map is `{}` whether or not the predicate is there. A cross-project leak
needs an event **in Project B** naming a run **in Project A**. Written:

```
assert timeline["runs"] == {}, "the timeline's run facts leaked across projects"
E   AssertionError: assert {'run-bola-a': {...'status': 'stopped'}} == {}
```

Predicate restored, 4 passed. The bait is synthetic and no product path is known to write such a
row — which is exactly why the route's own comment calls the predicate *enforcement, not
inference*. There is now a test that enforces it rather than one that agrees with it.

### F269 stopped being uncommon, and the discriminating test did not exist

`scripts/drive/t_aturn_p7_f269.py` stopped runs at 0.3 s, 1.0 s and 3.0 s and read the
conversation each time. Every time, **two entries**:

```
kind=operator_input  output_kind=None    run=run-b891266b04c6
kind=agent_output    output_kind=status  run=run-b891266b04c6  payload={"phase": "completed", "exit_code": 2}
```

No `thinking` row ahead of the status row — so `firstAgentBlockId` is the status entry's block, and
`isSuccessCompletionEntry` matches it, on **every** stopped turn. F269's severity rested on the
opposite ("a stopped or failed run cannot hit it, because it has no `status` row in the first
place") together with the warning that task 2.2 would change that. It did, and this is the
measurement of it.

Two consequences.

**Signal 1 now fires for a stopped run**, which D6 argued for and nothing had watched. Visible in
the drive's own record: the phase-0 model reports `settled=False` on the first read after the stop
and `settled=True` on the reload, from a status row that did not exist before task 2.2.

**The stopped-and-silent turn is where two requirements meet** — it must draw the terminal label
*and* keep its duration line, on a block whose fragment used to return `null`. Task 4.5a's fixture
is a *completed* run, which draws no label, so nothing asserted the two survive together. A test
for the measured shape was added to `timelineRunFacts.test.tsx`; reverting 4.5a's fragment to
`null` kills it and the original 4.5a test both.

**What the drive cannot say, stated rather than glossed.** `aturn_model.py` transcribes the
duration as `runDurationSeconds(runs[runId])` and does **not** transcribe
`reduceTurnBlocks`/`firstAgentBlockId`. So no drive check distinguishes 4.5a's placement fix from a
`thinking` row having taken the slot. The drive establishes *reachability*; the component tests
establish the *fix*. Task 7.1a as written claims the former proves the latter, and it does not.

<!-- followed F273 in FINDINGS.md -->
## Harness notes

`session_mode` accepts only `new` or `resume` (`agent_trigger.py:1226`). A second turn in the same
conversation is requested by naming `conversation_id`; passing `"continue"` returns 400, and a
multi-run leg that does not assert on the second trigger's `run_id` will go on to measure one run
and pass. The leg now asserts it.

**Fourth time this window that the first red result was the apparatus.** The new component test
failed on `getByText('Turn stopped')` — the label is a text node beside `· 01:00` inside the same
element, so an exact-string matcher misses text that renders correctly. The rest of the file
already used `/Turn stopped/`.

<!-- followed F273 in FINDINGS.md -->
## Teardown

Both fixture projects deleted (`204` each); `GET /projects` back to **0**, the count that predates
this drive on this profile database. Jobs and loops swept: none in either project, none enabled.
Fixture working directories `C:\Users\huida\Documents\drive-aturn-p7-0903` and
`...-p7b-0903` are left on disk, outside this repo.

<!-- followed F273 in FINDINGS.md -->
## Retired here

**F190** and **F269**. F190 because the round the operator asked for has now compared the built
product against phase 0's record and every observation moved as specified, with the one case that
had to stay unchanged unchanged. F269 because its fix is asserted by two mutation-killed component
tests — and its severity argument is overturned in the record rather than quietly dropped.

---

# D-1, 2026-09-03 - the day window's ordinary e2e slot, scoped to `a-turn-says-how-it-ended`

Drive Hub `127.0.0.1:8011`, started from `hub/` with
`py -3.11 -m uvicorn hub.main:app --port 8011` on a fresh database
(`%TEMP%\aw0903d1\aw0903d1.db`). Listener pid 7528, started 09:06:13; **zero `.py` files under
`hub/hub` or `src` newer than that**, and `refresh_ui_bundle.py --check` reports the served bundle
was built from the source that is here - so every observation below is of the branch's own code and
the branch's own dashboard.

Fixture: `aturn-p6-0903d1` = `proj-f0b9dc9732d3` at `C:\Users\huida\Documents\drive-0903-d1`, built
by `scripts/drive/setup_aturn_p6.py`. Two agents, both on `claude-haiku-4-5-20251001`:
`p6driver0903d1` (spawns) and `p6fail0903d1` (same model, plus an unknown CLI flag, so it dies at
exit 1 before a model is contacted and costs nothing).

**This is not phase 7.** Phase 7 was the change's own verifying round and evaluated
`scripts/drive/aturn_model.py` - a Python transcription of the built component. This slot drove the
**served bundle in a real browser** for the first time, which is where F274 came from: the model and
the component agree, and the screen still loses the outcome.

<!-- followed F275 in FINDINGS.md -->
## What held

- **The label and the exit code, in the served bundle, inside the window.** The stopped run rendered
  `Worked for 6s` / `Turn stopped - 09:08`; the failing agent rendered ten `Turn failed` labels and
  ten stat lines for its ten in-window turns. Every value came from `Run` - `stopped`/`exit 2`,
  `failed`/`exit 1` - not from an event name. This is the first time any of it has been read off the
  real dashboard rather than off `aturn_model.py`.
- **Durations are the row's, not the tab's.** `Worked for 6s` on a run that ended before any of these
  browser sessions existed.
- **The failing-runner path reports its cause.** `error: unknown option '--aw-p6-no-such-flag'` is on
  screen, in the turn, with the terminal label under it - a refusal that says what went wrong.
- **The extra SSE frame the night predicted is harmless.** `record_agent_output` firing
  `agent_session_changed` when its row is the session's first was visible in the drive as nothing at
  all: no duplicate turn, no flicker, no console error in any of the five browser sessions.
- **Three delivery attempts, then a stop, and the operator is told.** `delivery failed 3 times; the
  Hub stopped retrying` - the message is not silently dropped.
- **`GET /health` and the bundle stamp.** Clean, and `--check` confirmed the served bundle matches
  `hub/ui/src`, so no UI finding here is from a stale build.

<!-- followed F275 in FINDINGS.md -->
## Teardown

`proj-f0b9dc9732d3` is left in place on the **8011** drive Hub only, so D-5 can cite it. No job or
loop was created in this project at any point - nothing is enabled. `p6driver0903d1` is left bound
to the bad-flag runner, which is how F274's reproduction ends; rebind it to `haiku-0903d1` before
reusing the fixture for anything that needs a real turn.

# Filed outside a drive

<!-- followed F380 in FINDINGS.md -->
## D-1, 2026-09-18 — F376/F378 reproduced on the trial Hub (:8010), independent of `:8000`

**Not a new finding.** Per `DIRECTION.md`'s `## 2026-09-18` section, this feeds R1's argument for
`a-refused-capability-reaches-the-operator` — confirming F376's diagnosis still reproduces on a
fresh project, on the trial Hub rather than the operator's real one, before the spec loop reasons
about the repair.

**Harness:** `scripts/drive/d1_0918_refused_capability.py`, a fresh project (`proj-ece4c8c96a80`,
deleted afterward), one runner and one agent bound to `claude-haiku-4-5-20251001`. The agent was
told to call `create_flow` once with a made-up `spec_document_id` and `stop_when_queue_empties=true`
and to echo the tool's error text back verbatim.

**Measured, this run:**
- The transcript (`GET /projects/{id}/agent/{agent}/chat/{conv}`) contains F376's exact sentence:
  `Scheduled work from agents requires operator approval or an enabled allowance`, against the
  `create_flow` tool call, confirming the client-side checks in `create_flow`
  (`hub/hub/mcp_server.py:772-795`) run and pass before the server-side allowance gate in
  `hub/hub/api/v1/jobs.py:568` refuses it — the same order F376 described.
- `select count(*) from permission_requests where agent = 'architect090815'` on
  `~/.agentweave/hub/profiles/trial/agentweave.db` (read-only) is **0**. The refusal wrote no row
  a permission surface could ever show the operator, on a second Hub and a second project — F376's
  "the refusal names an approval path that does not exist" is not specific to `LoopEngine_2` or to
  `:8000`.
- `_require_agent_job_allowance` (`hub/hub/api/v1/jobs.py:32-51`) only gates a call carrying real
  agent+run attribution; an operator-issued call (no `X-AgentWeave-Agent` header) skips the check
  entirely (`if agent is None and run_id is None: return`), so this cannot be reproduced from the
  API alone — a real bound run is required, which is why this drive costs one Haiku turn rather
  than zero.

**Status:** confirms F376 and F378 (both still open); no new severity assigned. 5/5 harness checks
passed. Fixture project deleted, no job left enabled.

**Related:** F376, F378.

---

<!-- followed F388 in FINDINGS.md -->
## D-2, 2026-09-19 — migration 0104 (`subject_key`) drives clean on a fresh profile, and the ordinary question flow is unregressed

Night window's `arc-drive` task, driving commit `3b7718d` (tasks 0.3/0.4/0.5/4.12 of
`a-refused-capability-reaches-the-operator`). Fresh Hub from source, port 8091 (never 8000/8010),
`DATABASE_URL` naming a brand-new `~/.agentweave/hub/profiles/drive0919/agentweave.db` — a database
that had never seen any revision before this run.

`alembic upgrade head` (run implicitly at startup) landed on `0104` from a genuinely empty database:
`SELECT version_num FROM alembic_version` → `0104`. Schema inspection confirmed both artifacts task
0.3 describes: `questions.subject_key` (`VARCHAR(200)`, nullable) and
`ix_questions_open_subject_key`, a unique index on `(project_id, subject_key)` with
`WHERE answered = 0 AND declined = 0 AND subject_key IS NOT NULL` — the partial predicate design
D17 calls for, verified by reading the index's own SQL out of `sqlite_master`, not by trusting the
migration source.

Applying `AW_BOOTSTRAP_API_KEY` at first boot did not take effect — the operator-credential seed
(`hub/hub/db/engine.py:_seed_operator_credential`) only consults it while `OperatorCredential` is
empty, and a first boot without the variable set had already auto-generated and persisted one
before the variable was added on a second start. Not a defect: reading the auto-generated key back
out of `operator_credentials` (a fixture I own, not the operator's data) unblocked the drive in one
query. Worth remembering for the next window that starts a fresh profile: set
`AW_BOOTSTRAP_API_KEY` on the *first* boot of a new profile, or read the row back afterward.

Exercised the ordinary flow against a disposable fixture project (`drive-0919-arc2`, created and
deleted by the script, never touching `proj-5e960453`/`proj-18e5d4e0`): `POST /questions` with the
full `QuestionCreate` payload (`from_agent`, `question`, `blocking`, `header`, two `options` objects
with `label`/`description`, `multi_select`) → `201`, row created with `subject_key` defaulting to
NULL and not surfaced on `QuestionResponse` (by design — the schema was not touched by 0.3-0.5/4.12,
and task 0.3's own commit note says exposing it is out of this slice's scope). `PATCH
/questions/{id}` with `{"answer", "labels"}` (not `answer_labels` — that name only exists on the
response model, an easy payload mistake worth flagging for the next driver) → `200`, `answered:
true`. Nothing about the existing ask/answer path changed shape or behaviour with the new nullable
column and partial index present.

Drive Hub shut down after (`taskkill` on the actual listening PID, which uvicorn's reload/spawn
means is not the PID the launching shell reports — confirmed via `netstat` before and after). No
job or server left enabled.

**Verdict:** migration 0104 and tasks 0.3/0.4/0.5/4.12 drive clean. No finding to file — recorded
here as the drive evidence `arc-drive` exists to produce, per `a-refused-capability-reaches-the-
operator`'s own task list.

<!-- followed F388 in FINDINGS.md -->
## D-3, 2026-09-19 — `unrh-drive`: the roster-availability refactor (tasks 1.1-1.4) drives clean; one documentless-loop path confirms F161 is intact; F388's trap fired a second, harmless time

Night window's `unrh-drive` task, driving commit `f663898` (tasks 1.1-1.4 of
`an-unstaffed-review-names-its-holders`: `_roster_availability`/`Holding`/`AgentAvailability` in
`hub/hub/scheduler.py`, and `resolve_reviewer` reading it once instead of two separate queries).

**F388's trap fired again, harmlessly this time.** Starting the drive Hub the first time — inline
`DATABASE_URL="..." py -3.11 -m uvicorn ...` from `hub/`, the exact shape `CLAUDE.md`'s own
`.claude/reference/hubs.md` example uses — logged a full `0001→0104` migration chain (looking like
proof of a fresh database) but left no file at the intended profile path afterward. Read-only
inspection of the operator's live-instance default path (`~/.agentweave/hub/data/agentweave.db`,
the exact file `F388` names) found its `alembic_version` unchanged at `0103` before and after, with
`event_logs` still growing on its own between two reads taken minutes apart while this session's own
server process was already dead — proof the growth was the operator's own live `:8000` process
(confirmed separately listening, PID 9940) and not this session. No migration reached that file; the
column `0104` would have added is absent. Full account and the working fix (PowerShell `$env:` +
pre-created directory + PID-exact `taskkill`, never `/IM python.exe`) appended to `DEAD-ENDS.md`'s
existing F388 section rather than filed as a new finding — this is corroborating evidence for an
already-open finding, not a new one.

**The actual drive**, once a verified-correct fresh Hub was up (port 8092, profile `drive0919c`,
confirmed via the bootstrap key round-tripping and the intended directory existing): the named
regression files (`test_a_held_agent_is_busy.py`, `test_a_task_nothing_will_move_holds_nobody.py`)
gave **57 passed**, matching `unrh-impl`'s own measurement — nothing moved between the commit and
this drive.

Live pass: a fixture project, a runner, and two agents (`author-agent`, `reviewer-free`). Standing
up a scenario that reaches `resolve_reviewer`'s rung-2 pool walk turned out to need more than this
slice's scope — `decide_firing`'s own comment (`scheduler.py:1697`, design D5/F161) says a
documentless loop **never** calls `resolve_reviewer` at all: *"a loop has one agent and no second
party, so every reviewer this arm could resolve is the author"*. Reaching the pool walk live would
need a spec-document-linked loop (task-requirement links, evidence), which is a materially larger
fixture than a confirmation pass warrants and is `alsn-impl`'s territory, not this one's. Instead,
this drive exercised the *other* live-reachable half of the same refactor: a real one-agent,
documentless loop (`unrh-drive-loop`), fired once for real against Haiku, claimed its pending task
through the refactored `_agents_that_are_free`/roster-availability projection, completed it, and
then — correctly, per F161 — stayed at `completed` rather than moving to `under_review`:
`{"status": "completed", "assignee": "author-agent"}`, with the loop's own `stall_reason` reading
*"A loop does not review its own agent's work, so approving is what puts it in the product."* That
sentence is unchanged output from before this refactor, produced by code this refactor touches
(`decide_firing` at `:1443`, calling into the same roster read as `resolve_reviewer` now does) — live
confirmation that ordinary task-claiming through the re-expressed `_agents_that_are_free` still
works end to end, even though the review-specific branch needed a bigger fixture than this drive
built.

Cleanup: job disabled, drive Hub killed by the exact `netstat`-confirmed listening PID (twice, once
for each start), profile directory and fixture project directory both removed. No project or job
left enabled; operator's `:8000` instance re-verified unchanged (`alembic_version` still `0103`)
after teardown.

**Verdict:** tasks 1.1-1.4 drive clean on the reachable path; the pool-walk branch needs a
spec-linked loop to reach live and was not attempted here — flagged, not silently skipped. No new
finding filed; F388 gained corroborating evidence in `DEAD-ENDS.md`.

<!-- followed F388 in FINDINGS.md -->
## D-4, 2026-09-20 — `alsn-drive`: `a-loop-staffs-the-agent-it-names` (F128's fix) drives clean; a documentless loop pinned to a busy agent now refuses and stalls, a flow in the identical shape is unaffected

Fresh Hub from source, port 8093, brand-new `~/.agentweave/hub/profiles/drive0920/agentweave.db`
(never seen a revision before this run — the startup log showed the full `0001→0104` migration
chain, and the file's existence and mtime were confirmed directly before trusting it, per
`DEAD-ENDS.md`'s F388 practice). Started correctly on the first try: PowerShell `$env:DATABASE_URL`/
`$env:AW_BOOTSTRAP_API_KEY` set before `Start-Process`, target profile directory pre-created.
Fixture project `proj-3c1791d525a7` (never `proj-5e960453`/`proj-18e5d4e0`), three Haiku agents
(`gamma`/`alpha`/`beta`, one runner bound to `claude-haiku-4-5-20251001`). Script:
`scripts/drive/d7_0920_alsn_drive.py`.

**F128's own shape, live, post-fix.** `gamma` put mid-turn on a real Haiku turn (a genuine `running`
status, not a stub), `alpha`/`beta` left idle on purpose so the project-wide free list is genuinely
non-empty — this is exactly the shape that used to substitute a free sibling
(`t_f128_substitution.py`'s 2026-08-29 measurement). A **documentless** loop naming `gamma`, one
unassigned task, Run pressed:

* **409**, not the 200 F128 reproduced: `"gamma005410 is already running a turn, and no other agent
  is free to take this loop's work. Nothing was started."` — F127's re-derived sentence, now correct
  for this shape because `_agents_a_loop_may_staff` (design D1/D2) empties the pool for a
  documentless loop instead of falling through to the project-wide free list.
* the loop's one task kept `status: pending` and gained no `assignee`;
* no conversation was created for the refused firing (`GET /conversations` for the loop: `[]`);
* `GET /projects/{p}/loops/{id}` carries `"stall_reason": "gamma005410 is already running a turn"`,
  `"ending_state": null`, `"firing_active": false`, `"stopped_at": null` — the exact field
  combination `hub/ui/src/components/spec/loopCounts.ts:23`'s `endingBucket()` reads. Evaluated that
  function's own rule by hand against this JSON: `stalled`. **This is the change working as
  designed, not a regression** — the board's `running` count would have dropped by one and its
  `stalled` count risen by one for this loop, which is D2/D3's whole point (a documentless loop
  pinned to a busy agent no longer silently draws another agent's capacity). The frontend function
  itself was not exercised through a browser in this drive (no Vite/UI leg run) — this is a
  code-level confirmation against the pure function's own literal rule, not a screenshot.

**The flow control, same busy shape.** A **spec-linked** loop (`spec_document_id` set to an
arbitrary non-existent string — the route does not validate it against a real `Document` row, only
checks for a conflicting live loop) naming the same busy `gamma`, two unassigned tasks, Run pressed
while `gamma` is still mid-turn: **200**, both tasks moved to `in_progress`, one on `alpha` and one
on `beta` — the ordinary project-wide free list, untouched by this change. The loop's own
`stall_reason` reads `null` and its bucket is `running`. Confirms D1/D7's promise directly: the
scope filter is documentless-only, and a flow's width and staffing are identical to before this
change in the identical adversarial shape that flips a documentless loop to refused.

**13 of 13 verdicts held**, including both directions (documentless refused, flow unaffected) in one
run against one Hub, so neither result is an artifact of a different fixture.

Cleanup: both jobs stopped via `PATCH .../jobs/{id}` with `stop_reason` (the operator's own ending
path), their loops archived, their tasks rejected, agents confirmed `idle` before the fixture
project was deleted (`DELETE /projects/{id}` → 204; an earlier attempt while a real Haiku turn was
still finishing answered 409, which is the delete route doing its job, not a defect — waited for
`idle` and retried). Drive Hub killed by the exact `netstat`-confirmed listening PID (`24504` — the
launching shell's own reported PID, `23164`, was not the real listener, same gap noted in prior
drives). Profile directory and fixture project directory both removed. Operator's `:8000` database
re-verified read-only (`mode=ro`) before and after: `alembic_version` `0103`, `event_logs` count
unchanged at `12888` both times — no activity and no write, confirmed rather than assumed.

**Verdict:** `a-loop-staffs-the-agent-it-names` groups 0-4 and 6 drive clean in the shape F128 was
found in. Group 5 (operator-facing wording) remains unbuilt and out of this window's scope, per
`APPROVALS.md`'s `ORDER` line — the 409 sentence above is F127's pre-existing wording, not this
change's own §5 rewrite. No new finding filed; F128 is ready to close (group 8).

---

<!-- followed F388 in FINDINGS.md -->
## D-1 drive, 2026-09-20 — independent re-derivation on a fresh Hub (:8020, `profiles/drive0920`)

Scoped drive of the three changes last night's window built, re-run on a **new Hub instance** built
from source on this branch's HEAD (`alembic_version` measured `0104` on startup, no manual
migration step), against a **new** project outside the repo, to vary the axis last night's own
in-process drives could not (a second process, a second port, a second day). `netstat` confirmed
only `:8000` listening beforehand; started `:8020` from `hub/` with
`DATABASE_URL=sqlite+aiosqlite:///…/profiles/drive0920/agentweave.db`. `GET /health` →
`{"status":"ok","runtime":"native"}` before driving.

**Scope check first.** Read all three changes' `tasks.md`. `a-refused-capability-reaches-the-
operator` has **only 0.3/0.4/0.5/4.12 ticked** — the actual record (`refuse_for_project_state`,
§1), its callers (§2/§3) and its "reaches the operator" drive (§5) are **all unbuilt**. There is no
live "run refuses a capability" flow to drive yet; what exists is the migration, the model column,
and `ask_question_for_actor`'s new optional `subject_key` kwarg. Drove exactly that, not more.

**1. Migration 0104 / schema, direct read.** `PRAGMA table_info(questions)` on the fresh db shows
`subject_key` present; `sqlite_master` shows
`CREATE UNIQUE INDEX ix_questions_open_subject_key ON questions (project_id, subject_key) WHERE
answered = 0 AND declined = 0 AND subject_key IS NOT NULL`. Matches design D15 exactly (nullable
column, partial unique index, no backfill). **Held.**

**2. Task 4.12, live (not just unit-tested).** `POST /projects/{p}/questions` (the
`ask_question_for_actor` route, `subject_key` omitted, defaults `None`) called twice on the same
fresh project with distinct `from_agent`/`question`/required `options`/`header`/`multi_select` —
both returned **201**, both rows carry `subject_key: null` implicitly (the partial index's own
`WHERE … subject_key IS NOT NULL` is what let both through). Confirms live: two open NULL-keyed
questions coexist, the existing (non-refusal) caller path is genuinely unaffected by the new
column. **Held.**

**3. `a-loop-staffs-the-agent-it-names`, groups 0-4/6/7 — F128's own shape, re-run.** Reused
`scripts/drive/d7_0920_alsn_drive.py` verbatim (last night's own group-7 harness) against the new
Hub/project/day. `gamma` put genuinely mid-turn (`status: running`) on a real
`claude-haiku-4-5-20251001` turn, `alpha`/`beta` idle. A documentless loop naming `gamma`, one
unassigned task, `POST /jobs/{id}/run`: **409**, `"gamma090657 is already running a turn, and no
other agent is free to take this loop's work. Nothing was started."` — task stayed `pending` with
no assignee, no conversation created, loop's own `stall_reason` set and `endingBucket()` (the exact
`loopCounts.ts:23` rule, evaluated by hand against the live JSON) flips to `stalled`. A
spec-linked flow in the identical busy-sibling shape: **200**, both tasks moved to `in_progress` on
the free siblings (`alpha`/`beta`), `gamma` untouched, loop's bucket stayed `running` with no
`stall_reason` — confirming D1/D7's promise that the scope filter is documentless-only. **13/13
verdicts held**, matching last night's own count exactly on independent infrastructure.

**4. `an-unstaffed-review-names-its-holders` group 1 — code-level re-check.** `grep -n "await
_agents_that_are_free(" hub/hub/scheduler.py` on this branch's tip returns **exactly one** site
(`:1257`, inside `_agents_a_loop_may_staff`) — matching `a-loop-staffs-the-agent-it-names` task
0.2's own post-group-1 prediction of "TWO before this group's edits, ONE after," now measured after
both changes are in. `resolve_reviewer` calls `_roster_availability` directly, never
`_agents_that_are_free`. Confirms group 1's consolidation is real on disk, not just in last night's
transcript. Not re-driven live today (already driven live 2026-09-19, `e41b607`, "F388's trap fired
again harmlessly") — budget spent on the two changes above instead, which had *not* yet been driven
independently outside last night's own process.

**Cleanup.** Both alsn-drive fixture jobs stopped (`PATCH … {"stop_reason": …}`), loops archived,
tasks rejected, agents confirmed `idle`, project deleted (`204`, after one `409` while the flow's
real turns were still finishing — waited, retried, same pattern noted in prior drives). The two
small `arc-check*` projects (subject_key probes, no agent turns) deleted immediately (`204`).
Fixture directories removed. `:8020` Hub process killed by its `netstat`-confirmed listening PID.
No job left enabled, no process left running.

**Verdict:** everything driven held, on independent infrastructure from last night's own. No new
finding. `a-refused-capability-reaches-the-operator`'s actual refusal-reaches-operator behavior
(§1/§2/§3/§5) remains unbuilt — there is nothing more of that change to drive until those land.

---

<!-- followed F408 in FINDINGS.md -->
## D-5, 2026-09-23 — F388's fix driven live: the refusal, the named-database line, and the PID kill, all observed against a real process

Group 6 of `a-hub-that-was-not-told-which-database-refuses-to-open-one`, run against `85b4b28`
(groups 1-5 already landed and the full `hub/tests/` suite was green). This entry turns that green
suite into an observed live process, per the change's own framing that a green suite is not proof.
Port 8093, profile directory `testbed/scratch/group6-drive/` (deleted after), never `:8000`/`:8010`.

**6.1 — the refusal, for real.** From `testbed/scratch/group6-drive/` (no `.env` there), with
`DATABASE_URL` unset (`env -u DATABASE_URL`), `py -3.11 -m uvicorn hub.main:app --port 8093` failed
at import time with `hub.config.HubNotToldWhichDatabase`, printing 1.4's message verbatim
("The Hub was not told which database to open. Checked the process environment and a .env file in
the current working directory for DATABASE_URL and found neither. It declined to open
'sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/data/agentweave.db' without being asked to.").
Recorded the real default database's mtime/size (`1790120400 59396096`) before and after: unchanged,
and `~/.agentweave/hub/data/` gained no new file. The refusal is real, not just importable.

**6.2 — the startup line, for real.** Started the same command with `DATABASE_URL` naming a new
file (`.../group6-drive/throwaway.db`) that did not yet exist. The bare, level-less line (no logger
name — `logging.lastResort`, per R2's finding) appeared ahead of the alembic migration chain:
`Hub database: opening C:\Users\huida\...\throwaway.db (existed before this process opened it:
False, pid 23132)`. Killed pid 23132 (6.3, see below), then started the identical command again
against the same now-existing file: the line reappeared with `existed before this process opened
it: True, pid 27296` — the only thing that changed between the two runs.

**6.3 — the PID kill, for real.** `taskkill /F /PID 23132` (the exact pid the line printed)
returned `SUCCESS: the process ... has been terminated`, and a follow-up `tasklist /FI "PID eq
23132"` found nothing — the printed pid is the listening process, not the launching shell, so
`DEAD-ENDS.md`'s "launching shell's pid is not the listening one" trap did not fire here (this is a
direct `uvicorn` invocation, not `agentweave`'s spawn-a-child path). Repeated for the second
instance (pid 27296) at cleanup.

**Cleanup.** `testbed/scratch/group6-drive/` removed after both instances were confirmed dead.
Final check of the real default database: mtime/size unchanged from the pre-drive baseline.

F388 marked `fixed 85b4b28` below — only now, per 6.5, not when the suite went green.

<!-- followed F408 in FINDINGS.md -->
## D-6, 2026-09-23 — `an-unstaffed-review-names-its-holders` group 6: rung-3 staffing, R5's two new claims, driven live

Port 8096, profile `profiles/drive0923/`, `testbed/scratch/unstaffed-drive-032900/` (git-backed,
never deleted mid-drive — kept for the morning to inspect if wanted). Never `:8000`/`:8010`. One
runner bound to `claude-haiku-4-5-20251001`, four agents: `author`, `holder1`, `holder2`,
`unreach`.

**Setup, for real.** A flow (a job whose loop carries `spec_document_id`, via `POST
/project/documents` then `PUT .../content` to add requirements `FR-1`/`FR-2`) with `author`
completing two small real tasks (add `multiply`/`divide` to `calc.py`) through two real Haiku
turns — each produced a real commit on the task's own worktree branch (`d299021`, `92b85aa`,
read from `git log` in `.agentweave/tasks/<id>/`, not asserted). Evidence was then recorded
against each requirement naming that commit (`POST /project/spec/evidence`, operator-recorded,
which `requirement_evidence.record` accepts on arrival) — without a requirement link and recorded
evidence, `commit_for_task_review` refuses with "no commit to review" and rung 3 is never reached;
this was hit once (see the 02:35 history row below) before the requirement/evidence plumbing was
in place, and is recorded rather than silently fixed and forgotten.

A second, real, live (non-archived) loop held `holder1` and `holder2` each on one `pending` task
(reachable — `loop_id` set to that loop). A bare task with no `loop_id` held `unreach`
(unreachable).

**A1/A2 — the exact sentence, on the wire, matching all three surfaces.** With the roster fully
booked, `POST .../jobs/{id}/run` → 409:
`"could not staff this step: no reviewer is free. author is the one that completed this task;
holder1 is booked for task-c0b6866531b5 (pending); holder2 is booked for task-93bead919653
(pending); unreach is booked for task-daff3f589a4b (pending). Land it, on the task, to review it
yourself. Rejecting booked tasks that are no longer wanted can free their agents."`
`GET .../jobs/{id}/history`'s matching row's `error_summary`, and the `review_unstaffed` event's
`data.reason`, were read back byte-identical to that 409 detail — the same three-surface agreement
2.6's unit test asserts, now observed against a real HTTP response and a real event feed rather
than an in-process `app.post`.

**R8(a) — an unreachable-only holder is staffed, not merely "not named".** With only `author` and
`unreach` on the roster and `unreach`'s one task unreachable, the next firing staffed `unreach`
directly: `task-de71566d8dba` moved `completed -> under_review`, `assignee: unreach`, **no stall
at all**. That absence of a 409 is the observable proof design R5-0's projection treats an
unreachable holding as free, not the text of a reason that never got produced.

**R8(b) — rejecting an agent's only booking frees it, and the very next firing proves it.** With
the roster fully booked (the 409 above), `PATCH task-c0b6866531b5 {"status": "rejected"}` (the
operator's own control, `holder1`'s only reachable holding) then re-firing answered **200**, not
409: `task-8fc30ed54650` moved `completed -> under_review`, `assignee: holder1`. The remedy the
sentence prints — "Rejecting booked tasks that are no longer wanted can free their agents" — was
watched working, not merely claimed.

Both review turns ran for real and both approved the work. `GET history` returned 200 throughout,
including after the 470-ish-character reason (well under `JOB_RUN_ERROR_SUMMARY_CHARS`'s 500 in
this fixture's shape — 2.9's twelve-agent test is what forces the budget walk, not reachable here
with three candidates). D4/F365 (two firings, two unstaffed tasks, one event each) was observed
for free: the evidence-missing stall on `task-de71566d8dba` and the booked stall on
`task-8fc30ed54650` each produced exactly one `review_unstaffed` event for two different tasks on
two different firings — never coalesced into one.

**Skipped per R8:** the drawer's status-menu refusal and a real agent's `under_review` refusal
turn (D5's, moved to `a-refusal-names-a-remedy-that-works`, archived 2026-09-16) — not this
change's to drive.

**Teardown.** All three jobs (`job-21aba4c04762`, `job-78bc6ef5cde0`, `job-84e099d2865b`)
`PATCH`ed to `enabled: false`; `GET /jobs` confirmed zero enabled agents afterward. The drive
Hub process (port 8096) and its profile are left in place for the morning; nothing was written to
`:8000` or `:8010` at any point.

<!-- followed F408 in FINDINGS.md -->
## D-1, 2026-09-23 (day window) — last night's two closed changes re-driven independently, fresh port/profile

Scoped drive per `day-window.md` D-1: what the night built, checked from outside its own drive
records. Port 8011 (free per `netstat`), profile `profiles/drive0923d1/`, never `:8000`/`:8010`,
never `proj-5e960453`/`proj-18e5d4e0`. No job left enabled; the one throwaway project
(`proj-7baa80e5c56c`, four `claude-haiku-4-5` agents, no jobs created) and its `testbed/scratch/`
fixture were removed at teardown.

**`a-hub-that-was-not-told-which-database-refuses-to-open-one` — both paths re-observed live,
independently of last night's group-6 drive.**
- Started `py -3.11 -m uvicorn hub.main:app --port 8011` from `hub/` with `DATABASE_URL` unset but
  `hub/.env` present (this machine's normal state): no refusal — `Settings()` took the value from
  `.env`'s relative path, resolved against `hub/` as cwd, and opened
  `hub/data/agentweave.db` (a repo-local scratch path, confirmed gitignored, not the operator's
  `~/.agentweave/hub/data/agentweave.db`). The startup line fired exactly as designed:
  `Hub database: opening C:\...\hub\data\agentweave.db (existed before this process opened it:
  False, pid 21376)`, at `WARNING`, ahead of the alembic chain. Correct behaviour — `.env` is a
  legitimate source and the refusal is only for *no* source — but worth recording as a distinct
  observation from group 6's, which ran from a directory with no `.env` at all.
- Moved `hub/.env` aside and repeated with `DATABASE_URL` still unset: import-time
  `hub.config.HubNotToldWhichDatabase`, message verbatim: *"The Hub was not told which database to
  open. Checked the process environment and a .env file in the current working directory for
  DATABASE_URL and found neither. It declined to open
  'sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/data/agentweave.db' without being asked to.
  Set DATABASE_URL explicitly, or run bare `agentweave` to use that default."* — propagates
  unwrapped before uvicorn binds a socket, matches D2's design exactly. `.env` restored
  immediately after.
- Both processes killed by exact PID (`taskkill /F /PID <n>`), never the blanket `/IM python.exe`
  this finding exists to retire.
- **Not a new defect. Status: disproves nothing, confirms 6.1/6.2 from a second angle (a `.env`
  present vs. absent) on the same day's code.**

**`an-unstaffed-review-names-its-holders` — lighter touch, real but not a full re-drive.** Group 6
drove this exhaustively the same night (D-6 above: two real Haiku turns, three-surface byte
agreement, both R8 claims watched working). Re-running the identical live scenario tonight would
mostly re-spend real agent-turn cost to re-confirm what already matches. Instead:
- `hub/tests/test_a_held_agent_is_busy.py` + `hub/tests/test_a_task_nothing_will_move_holds_nobody.py`
  run fresh on today's `HEAD`, in isolation: **65 passed** (up from D-6's 55 — the added group-6
  tests are in this count), no drift since last night.
- Checked the UI bundle-deferral decision recorded in `e6d1c96` is still exactly what `git log`
  shows: `hub/ui/src` last touched by `e6d1c96` (2026-09-23T03:04), `hub/hub/static/ui`'s last
  commit is still `c18a87b` — the bundle is deliberately uncommitted pending `:8000`'s restart past
  `c18a87b`, matching the commit message and today's `decisions_for_user` carry-forward. Confirmed
  from the drive Hub's own startup warning (`hub/hub/static/ui asserts it was built from
  hub/ui/src as of 2026-09-22T18:07:55+00:00, but the source has changed since`) — the staleness is
  real and intentional, not an oversight.
- **Not driven again live today; no new defect found. Status: n/a (verification only, not a
  finding).**

<!-- followed F448 in FINDINGS.md -->
## Night drive 2026-09-25, part 1 (`scripts/drive/d8_0925_night_drive.py`) — no new finding

Fresh Hub, profile `drive0925`, port 8025, Haiku (`author`). Measured: the fresh database migrated to `0107` and `task_transitions` carries `job_id`; `POST /jobs/{id}/run` on a loop answered `{success, job_id, job_run_id}` (`job_run_id`, not `run_id`); a second press while `author` ran answered 409 "author is already running a turn, and this loop's work goes only to author... Nothing was started."; the task's first transition read `pending→assigned, origin=job, job_id, job_name="drive loop", job_kind="loop"`, the next `origin=runtime` for the run. The run completed; the job was disabled afterwards. NOT yet driven: the UI history drawer render, checkpoint handover, tool-server pin, F133 status route, event-after-commit ordering.

<!-- followed F448 in FINDINGS.md -->
## Night drive 2026-09-25, part 2 (`d8_0925_night_drive2.py`, `d8_0925_night_drive3.py`) — no new finding

Same Hub (`drive0925`, 8025), real HTTP. Measured: a conversation with two ready checkpoints — first `POST /checkpoints/{c1}/cutover` 200 with a successor; the same checkpoint again 409 "already cut over to conv-…"; the other checkpoint of the same conversation 409 "already handed over to conv-… (checkpoint …)"; the checkpoint list carried the record. `POST /conversations/{id}/continue` answered `started: true` on the successor and `waiting_reason: "agent is already running"` on the predecessor (F133 route names a reason). The `conversation_cut_over` broadcast fired only after the 200 (event-after-commit exercised on that route only). UI (Playwright): the task drawer's history read "Loop drive loop moved pending → assigned"; the agent's own move read "author was moved for…" (screenshot `testbed/scratch/drawer0925.png`, not read visually). NOT driven live: the tool-server pin (covered by unit tests only), event-after-commit beyond the cutover route.

<!-- followed F449 in FINDINGS.md -->
## Full-surface sweep 2026-09-25 — seven findings, and what held

Nineteen coverage rows driven by five parallel operators plus row 19 by the orchestrator, on the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku). Projects `sweep0925-A`…`E` under `~/Documents`. Reports: the sweep report Artifact (2026-09-25). Rows 1–6, 8, 11, 13–17 and 19 came back WORKS; 7, 9, 10, 12 WORKS WITH PROBLEMS; Codex paths NOT REACHED (plan cancelled). Reproduced and still open: F21, F113, F125, F134, F183, F248, F284.

<!-- followed F409 in FINDINGS.md -->
## b10 drive, 2026-09-27 (live Hub :8043, profile drive0927, Chromium on the served bundle, Haiku) -- a-loop-is-stopped-archived-and-delegated-from-its-own-tab

Harnesses: `scripts/drive/d0927_loop_tab.py` (Chromium, two tabs, 19 checks) and `scripts/drive/d0927_loop_api.py` (Human-only 3 and 6, over the API). Fresh project, loops with no stop condition and a far-future cron so nothing fired on its own.

- **1 PASS.** The tab shows *runs until stopped by the operator*, a Stop button, and "Additions to this queue are decided by you."
- **2 PASS.** Let alpha decide / Decide them yourself each updated the controller line without a reload (1.75 s and 2.0 s); `GET /loops/{id}` `events` holds two `loop_control_changed`.
- **3 PASS.** Stop from the tab with a reason: badge *Stopped early: <reason>*, Stop gone, `ending_state: stopped`, one `loop_stopped`. Mid-firing (real Haiku turn, `firing_active` true at the stop): the stop was accepted, the firing finished (18 s), the job ended disabled, `run_count` 1, one history row, no second firing.
- **4 PASS.** Archive left the index (3.25 s); Show archived brought it back marked Archived, *stopped early*.
- **5 PASS.** A second browser tab open on the same loop updated to *Stopped early: second tab reason* with no reload (4.75 s) after the first tab stopped it.
- **5a PASS by the curl fallback the guide allows.** A `PATCH` after the ending answered 409 `loop_already_ended` with the sentence "this loop already ended (second tab reason) at ...; its record is left as it was"; the reason and the single `loop_stopped` were unchanged. The in-tab confirm-then-refresh race was not driven by hand (SSE refreshed tab 1 first). Blank reason: badge reads *Stopped early: Stopped by the operator*.
- **6 PASS.** `POST /jobs/{id}/archive` on a running loop's job: 200; loop `stopped`, reason "archived with its job", `archived_at` set; `events` = `loop_archived`, `loop_stopped`.
- **Observation, not a defect of this change.** Every UI update took 1.75-4.75 s after the action (the first run's fixed 1.5 s waits read the previous state; polling fixed the harness, not the product). Also `GET /jobs` showed the archived job b10-D still `enabled: true`; not checked against the pre-change code, so unverified as a regression.
- Teardown: Hub :8043 stopped. Earlier partial runs of the harness left stopped-nowhere loops with enabled jobs in the throwaway profile `drive0927`; nothing can fire (Hub down), profile kept.

<!-- followed F409 in FINDINGS.md -->
## r1a drive, 2026-09-27 (live Hub :8044, profile drive0927c, Chromium on the served bundle, Haiku) -- a-flow-is-configured-from-its-own-tab

Harness `scripts/drive/d0927_r1a_flow_tab.py` (documents seeded `approved` change-specs by `d0927_r1a_doc_seed.py`; the Hub's own propose/approve route needs a complete payload and is not what this change touches).

- **PASS** Spec destination, approved change-spec: *Start a flow…* offered, dialog (agent, message, cron, stop-at) submitted, `Flow: r1a-spec` link on the phase bar 0.5-1.0 s later; Hub `GET /loops` has exactly one loop declaring the document.
- **PASS** Conversation panel: same dialog from the panel's phase bar, flow link 3.5-7.75 s later. A conversation panel exists only once the agent has a conversation; a fresh `?agent=alpha&document=...` with none lands on "New conversation" and drops the document (not this change; noted).
- **PASS** The flow link opens the loop tab in the conversation panel with `document=` absent from the URL.
- **PASS** Agent changed from the tab's Settings: Hub `agent` stays `alpha`, `pending_edit.agent = beta`, a `loop_edit_staged` event; the tab's pending panel says "Edit staged - it applies at the next firing ... In force now: alpha / From the next firing: beta".
- **PASS** Cadence changed from the tab (yearly to every minute); a firing applied the agent: `agent = beta`, `pending_edit` cleared, `loop_edit_applied` in `events`; the tab reads `Default agent: beta`, pending panel gone.
- Harness checks marked BAD in the last run were mine: the Settings read view shows the in-force value by design (the staged value is in the pending panel), and the 5 s freshness bound was my own threshold.
- **Observation, cause not isolated (unverified).** UI freshness after an action varied 0.3 s to 17.5 s: the first staged edit on a freshly opened tab took 6.65 s to show, the next two under 0.3 s (but those two matched text the panel already held, so unreliable); the tab showed the applied agent 17.5 s after the firing. `useSSE` has no debounce; the Hub broadcasts `loop_edit_staged`/`loop_edit_applied`. Not filed as a defect.
- Teardown: Hub :8044 stopped; every job in the profile disabled.

<!-- followed F409 in FINDINGS.md -->
## b5 drive, 2026-09-27 (a-document-moves-forward-only-through-its-checks)

Fresh Hub :8046 from `hub/` (profile drive0927b), Chromium on the served bundle, no agent turns. Harnesses `scripts/drive/d0927_b5_phase_checks.py`, `d0927_b5_approve_refusal.py`.

- **PASS** F207's four calls verbatim: create 201; close-exploration 200; propose 200 with `blocking` (no_requirements, non_goals_empty), document still exploring; `phase?to=proposed` now **409** `document_incomplete` carrying the same two findings (was 200 and `proposed`); `to=approved` 409 `illegal_transition`.
- **PASS** Chromium, Propose on an empty exploring document: the phase bar shows both findings in words, document stays exploring.
- **PASS** Chromium, Approve on a proposed document whose content was then emptied by a saved edit (the write is accepted, reporting the blocking finding): Approve shows the `requirements` finding, document stays proposed.
- Harness note: my first sentence match for the Propose refusal looked for the word "complete" and reported BAD; the screenshot showed the refusal. Harness error, not product.
- Teardown: Hub :8046 stopped; no jobs created.

<!-- followed F409 in FINDINGS.md -->
## b11 drive, 2026-09-27 (a-loop-that-is-gone-lets-go-of-its-document)

Fresh Hub :8047 from `hub/` (profile drive0927d), project proj-523d0cf54f66, no agent turns. Harness `scripts/drive/d0927_b11_successor.py`.

- **PASS** F53's three calls on an approved two-task document: flow one claims it (its queue lists both tasks); flow one archived; flow two created on the same document. `GET /tasks?loop_id=<flow two>` lists both tasks, each now stamped with flow two's loop id; flow one's queue is empty. Flow two carries a `loop_tasks_adopted` event.
- **PASS** F157: a job naming `spec_document_id` with no purpose is 400 `spec_document_id describes a loop; give this job a purpose or a stop condition to make it one`.
- Harness note: my first run passed the document's path rather than its id and bound nothing (queue empty); harness error, not product. Ids come from the approve response.
- Teardown: both jobs archived, none enabled; Hub :8047 stopped. Not driven: UI in Chromium (no UI change in this change).

<!-- followed F409 in FINDINGS.md -->
## r1b drive, 2026-09-27 (live Hub :8048, profile drive0927r1b, Chromium on the served bundle, Haiku) -- a-document-says-how-it-will-be-built-and-approval-starts-it, task 4.2

Fresh project `proj-2a4f643f9593` at `~/Documents/drive-0927-r1b-171817`, agents `author`/`builder`/`worker` all on `claude-haiku-4-5-20251001`. Harness `scripts/drive/d0927_r1b_approval_flow.py`; two harness bugs found mid-run cost a manual continuation (`testbed/scratch/r1b_continue.py`, `r1b_race_probe.py`, untracked) rather than a second full pass, to avoid spending a second pair of Haiku turns.

- **Human-only check 1, real Haiku turns, mixed.** Triggered `author` with `spec_document` set to a fresh empty change-spec and "add one line to CONTRIBUTING.md... interview me about it". Turn 1 (18s) asked six ordinary interview questions (motivation, content, audience, placement) and **never asked how the work would be built** — no mention of a flow, an agent, or a stop condition. Read the actual turn context off the CLI transcript (`~/.claude/projects/...--agentweave-worktrees-author/*.jsonl`) to rule out a missing-injection bug: the "ask how it will be built... 'No flow' is a valid answer" line **was present**, twice (once per turn) — the change wires it correctly; Haiku simply did not act on it unprompted. Told as the operator, in turn 2 (same conversation, `conversation_id` continuation, no explicit field list given beyond "flow, default worker, stop when queue empties, 5 minutes"): the agent wrote the whole document itself, unprompted on structure, and reported "**Delivery**: Flow mode, worker agent, stops when queue empties, fires every 5 minutes" — confirmed via `GET /spec`: `delivery_status: {state: stale, agent: worker, reason: archived}` (worker had been archived by an earlier partial run of the same harness; unarchiving flipped it to `state: ok`). So: **the interview line reaches the model correctly; a real Haiku turn did not ask proactively but did honour an explicit instruction and produced a real `delivery` block on its own**, not written by the harness.
- **Haiku's own document failed propose on an unrelated linkage bug**, not delivery: `requirement_without_task` (`contrib`) and `task_without_requirement` (`add-contrib`) — its requirement and task keys did not match each other. Correct refusal by the completeness gate, not a defect. The harness then wrote a corrected payload with matching keys via `PUT .../documents/{path}/content` (same delivery: flow, worker, stop-on-empty), per the drive's own allowed fallback, to keep going without a third Haiku turn.
- **PASS.** Propose succeeds once the payload is complete and delivery is present (`blocking: []`, phase `proposed`).
- **PASS.** Chromium, no reload: with `worker` open, no stale strip. Archived `worker` via the API while the page stayed open; the strip appeared in 0.25s (SSE-driven), naming worker and "archived", with a `<select>` offering `@author`, `@builder`, `No flow` (worker correctly excluded once archived — `agent_archived` invalidates the agents query too).
- **PASS.** Chose `builder`, clicked Approve: the approval report rendered in 0.25s, listed the created task, and a flow message read "The flow ... was started as builder; it fires at its next tick." The phase bar showed **Flow: Add CONTRIBUTING.md with PR welcome message** with no **Start a flow…** button.
- **PASS, Hub side.** Exactly one loop declares the document, agent `builder`. Its job: `enabled: true`, `next_run` on the exact next 5-minute boundary (measured on a same-shaped probe document since the original job was already torn down by the time this check's harness bug was found — see below — e.g. `2026-09-27T16:30:00Z` against a query at `16:26:45`), `run_count: 0`, `last_run: null` — no run started at approval. `GET /spec`'s `approval_outcome.flow` reads `{state: created, agent: builder, flow_state: running, messages: [...]}`.
- **PASS, optional.** A second document (`mode: none`, no agent turn, cheap): approved, report says "The delivery says no flow: the tasks are on the board, started by hand.", the pointer `… use Start a flow… above.` shows once, and the phase bar offers **Start a flow…** exactly once. `approval_outcome.flow.state == "none"`.
- **Observation, isolated, not filed as a defect.** For roughly 0.3s immediately after clicking Approve, the approval report showed **both** the flow's own message ("The flow ... was started as builder...") **and** the "… use Start a flow… above" pointer at the same time — a real, if brief, internal contradiction. Isolated with a 100ms-sampling probe (`testbed/scratch/r1b_race_probe.py`) on a freshly approved document: `report` and the flow `msg` both appear at t=0.12s, `pointer` clears and `spec-flow-link` appears together at t=0.45s. The flow message comes straight off the mutation's own response; the pointer depends on `useDocumentFlow`'s separate query, which lags behind by a few hundred milliseconds before its own invalidation resolves. Same UI-freshness-lag family already on record for this change area (r1a drive, 2026-09-27: 0.3-17.5s), just visible here because two elements that read different sources sit in the same panel and can momentarily disagree.
- **Harness errors, not product, and now fixed in the tracked script.** (1) The original run assumed the document's path stays the one it was created at; the author renamed it mid-exploration (the tool prose tells it to call `rename_spec_document` once it knows the subject), so the harness's own `close-exploration`/`propose`/`PUT .../content` calls 404'd against the stale path. Fixed with a `resolve_path(doc_id, ...)` lookup against `GET /project/documents` by the document's durable id. (2) `LoopSummary` (`GET /loops`) carries no `job_id` field at all — the field the harness read (`loop["job_id"]`) does not exist on that shape, so the loop-to-job cross-reference was always `None`. Fixed to filter `GET /jobs` by `(job.loop or {}).spec_document_id == doc_id` instead, which is the only surface that ties the two together (confirmed against `JobResponse.loop: Optional[LoopSummary]`).
- Teardown: both jobs in the profile (`job-6a309d1760bc`, `job-5a3139c53c39`) disabled then archived; Hub PID 21560 (listening on :8048) stopped; `netstat` confirms no listener on :8048 afterward.

<!-- followed F409 in FINDINGS.md -->
## a-runner-choice-names-its-model drive, 2026-09-27 (trial Hub :8010, served bundle, no dev server) — no new finding

Task 3.1 names the trial Hub `:8010` explicitly, not a fresh drive Hub, so this drive ran there rather than under the general "Driving" section's per-night port. Started the trial Hub from source (`hub/`, `DATABASE_URL` naming `profiles/trial/agentweave.db`) after confirming no listener held :8010 and no `.py` under `hub/hub` or `src` was newer than the process start. Fresh project `proj-572d52826e3a` (`~/AppData/Local/Temp/drive-twin-proj`), two `claude` runners both named `Twin` — one `claude-opus-5-5`, one `claude-sonnet-5` — and an agent bound to the Opus one. Harness `scripts/drive/d0927_twin_runner_labels.py`, Chromium against the served bundle (no real agent turns run, so the Haiku-binding rule does not apply).

- **PASS.** Agent Settings → Execution's runner select: the two same-named `Twin` runners render as distinct options, `'Twin — Opus 5.5 (claude)'` and `'Twin — Sonnet 5 (claude)'` — the pinned D1 format, verbatim, confirming they are not conflated by name alone. The Hub-created defaults render `'Claude (default) — Provider default (claude)'` / `'Codex (default) — Provider default (codex)'`; the no-runner option reads `'No runner (cannot run)'`.
- **PASS.** Project Settings → title-runner select: same two distinct `Twin` labels, each naming its own model, matching the runner list exactly (no override applied here, per D2).
- **PASS.** Project Settings → checkpoint-runner select, override behaviour: with "Checkpoint model" left unset, the checkpoint-runner select's `Twin` options were identical to the title-runner select's (each naming its own model — the override is a no-op when `checkpoint_model` is null, task 1.3's "own model once cleared" case). After picking `checkpoint_model = claude-sonnet-5` client-side, the checkpoint-runner select re-rendered live: both `Twin` options collapsed to the identical label `'Twin — Sonnet 5 (claude)'` (both now carry the override — losing their distinguishing model label is the expected cost of an override that applies uniformly), `Claude (default)` became `'Claude (default) — Sonnet 5 (claude)'`, and `Codex (default)` became `'Codex (default) — claude-sonnet-5 (unrecognised) (codex)'` (the checkpoint-model picker does not filter by the runner's own CLI's catalog — a real but out-of-scope observation for this change, not filed as a new finding: `a-runner-choice-names-its-model`'s proposal only pins the label format, not cross-CLI validation of the checkpoint-model choice).
- Teardown: project `proj-572d52826e3a` (and its two `Twin` runners, its agent, and the two default runners created with it) deleted via `DELETE /projects/{id}`; trial Hub PID 17028 (listening on :8010) stopped; `netstat` confirms no listener on :8010 afterward.

<!-- followed F459 in FINDINGS.md -->
## an-estimate-that-misses-turns-says-so drive, 2026-09-28 (trial Hub :8010, real `claude-haiku-4-5` turns) — no new finding, one design consequence confirmed live

Task 3.1 names the trial Hub `:8010` explicitly, not a fresh drive Hub. Started it from source (`hub/`, `DATABASE_URL` naming `profiles/trial/agentweave.db`, no `.py` under `hub/hub` or `src` newer than the process start). Fresh project `proj-a7d532f5141f` (`~/Documents/aw-drive-unpriced`), two agents (`spender`, `spender2`) on one `claude-haiku-4-5-20251001` runner.

- **Produced a real `unavailable` turn, not a fixture row.** Triggered `spender` with a slow prompt, then `taskkill /F`'d the Hub process's PID mid-run (confirmed the run's DB row was still `status=running` first). Restarted the Hub from the same database: startup log read `Reconciled 1 orphaned run(s) to status=interrupted on Hub start`, and `turn_usage` gained one `status=unavailable` row with `total_tokens`/`api_equivalent_usd_micros` both null — F92's mechanism, re-driven, not narrated.
- **PASS.** `GET /accounting` on the project (one `unavailable` turn only, nothing measured yet): `project.unpriced_turns == 1`, `unavailable_turns == 1`, `measured_turns == 0`, matching design D1 exactly.
- **PASS.** Ran one more real turn on `spender2` (measured, priced) to get a mixed project: `GET /accounting` now reads `measured_turns: 3, unavailable_turns: 1, unpriced_turns: 1` at the project level, and the `spender` agent alone carries `unpriced_turns: 1` while `spender2` carries `0` — the per-agent split (D1) holds.
- **The rendered label never said "excludes 1 turn" here, and that is the design working as specified, not a bug.** `preferred_display.kind` stayed `"allowance"` throughout (`usage_accounting.py:168-173`: a `claude` runner's turns always carry an `allowance` object, and allowance is checked before `api_equivalent` and wins unconditionally). Opened the Budgets tab in Chromium against the served bundle (`scripts/drive/d0928_unpriced_turns_label.py`): the panel read "Rate-limit allowance available · resets Sep 28, 4:00 AM" — no mention of the unpriced turn anywhere on screen, even though the API's `preferred_display` never carries `unpriced_turns` under `kind: "allowance"` for the UI to render in the first place (design D2: "The `allowance`, `tokens` and `unavailable` kinds are unchanged"). Net effect, worth the operator knowing even though it is not a defect in this change: **on this Hub, every project driven by a `claude` runner will show the "excludes N turns" wording only in the API response, never in the Budgets tab**, because `claude` turns always populate `allowance` and no code path here ever prefers `api_equivalent` display while an allowance is present. Not filed as a new finding — this is exactly what D2 describes, just not stated in the proposal as "practically unreachable in the UI for claude-only projects."
- Teardown: project `proj-a7d532f5141f` deleted via `DELETE /projects/{id}`; fixture directory removed; trial Hub PID stopped; `netstat` confirmed no listener on :8010 afterward. Checked for orphaned `claude.exe` processes before killing anything — the two found were unrelated (one is this very autonomous session's own host process; command lines confirmed via `Get-CimInstance Win32_Process`), so neither was touched.

<!-- followed F459 in FINDINGS.md -->
## a-model-alias-is-a-model-choice drive, 2026-09-28 (trial Hub :8010, real `claude-haiku-4-5` turn) — no new finding, D1 confirmed live

Task 3.1 names the trial Hub `:8010` explicitly. Started it from source (`hub/`, `DATABASE_URL` naming `profiles/trial/agentweave.db`, confirmed no listener held :8010 first and no `.py` under `hub/hub` or `src` newer than the process start). Fresh project `proj-d71a6cb1ea7c` (`%TEMP%\alias-turn-usage-041659`), one `claude` runner created with `model: "haiku"` — the alias, not the full id — bound to a fresh agent. Harness `scripts/drive/d0928_alias_turn_usage.py`, API-level (this change touches no rendering the UI-drive rule requires a browser for; `ModelPicker`/checkpoint-select rendering was already covered by design.md's own R2/R3 rounds and the change's own vitest suite).

- **PASS.** `POST /runners {"model": "haiku"}` → 201, `model: "haiku"`, `model_unrecognised: false` — the alias is accepted and stored exactly as submitted (D1).
- **PASS.** Triggered one real turn (`claude-haiku-4-5`, per the cheap-models rule) and polled `GET /accounting` until it settled: `turn_usage` row landed `status: "measured"`, `model: "claude-haiku-4-5-20251001"` — the full id the CLI actually resolved the alias to — while a follow-up `GET /runners/{id}` still read `model: "haiku"`. This is D1's central claim, measured live rather than only in the design table: the stored choice and the resolved model can differ, on purpose, and neither route silently rewrites the other.
- **Harness assertion error, not a product defect.** The script also asserted `turn_usage.runner == "haiku"`, which failed (`"claude"`). That column is the CLI name (`hub/hub/db/models.py:1270`, `String(32)`), not the runner's model — the assertion was simply wrong about the schema. Fixed in the tracked script; not filed as a finding.
- Teardown: the script's own `finally` block deleted `proj-d71a6cb1ea7c` and removed the fixture directory; confirmed no project named `alias-turn-usage-*` remained afterward. Trial Hub PID 15908 stopped; `netstat` confirmed no listener on :8010 afterward.

<!-- followed F460 in FINDINGS.md -->
## the-codex-models-offered-are-the-ones-its-cli-lists drive, 2026-09-28 (trial Hub :8010, served bundle, no Codex spawn — Codex is undrivable) — no new finding

Task 3 names the trial Hub `:8010` explicitly. Started it from source (`hub/`, `DATABASE_URL` naming `profiles/trial/agentweave.db`) after confirming no listener held :8010 and no `.py` under `hub/hub` or `src` was newer than the process start. Fresh project `proj-cca6cd55e14e` (`%TEMP%\aw-drive-codex-cache`). This machine's real `$CODEX_HOME/models_cache.json` (`client_version 0.146.0`, `fetched_at 2026-09-23T10:10:51.560427200Z`) declares three `visibility: list` models — `gpt-5.6-terra` (priority 7), `gpt-5.6-luna` (8), `gpt-5.5` (12) — plus two `hide` models (`gpt-reserve`, `codex-auto-review`) correctly absent from every response below.

- **PASS, task 3.1.** `GET /api/v1/model-catalog`'s `codex` provider entry lists exactly `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.5` (in that priority order, `gpt-5.6-terra` marked `default: true`) with `source: {"kind": "cli_cache", "fetched_at": "2026-09-23T10:10:51.560427200Z", "client_version": "0.146.0", "reason": null}` — recorded verbatim, matching design D1/D2 exactly. The `claude` provider's `source.kind` stayed `"built_in"` alongside it, unaffected.
- **PASS, task 3.2.** `POST /runners {"cli":"codex","model":"gpt-6-sol"}` on the fixture project answered **400**: `{"detail":"'gpt-6-sol' is not a model 'codex' declares; expected one of: gpt-5.6-terra, gpt-5.6-luna, gpt-5.5"}`. Seeded an existing runner directly on the trial database (`INSERT INTO runners ... model='gpt-6-sol'`, bypassing the API to simulate a runner created before this cache existed) — `GET /runners` on that project read `"model": "gpt-6-sol", "model_unrecognised": true` for it, while the two Hub-created default runners (`model: null`) both read `model_unrecognised: false`.
- **PASS, task 3.3.** Opened New Runner, chose CLI `codex` (`scripts/drive/d0928_codex_cache_source_line.py`, Chromium against the served bundle): the model select offered `GPT-5.6-Terra`, `GPT-5.6-Luna`, `GPT-5.5` in that order, and the line beneath it read, verbatim: **"As listed by your installed Codex CLI (0.146.0, fetched 23 Sep)"** — matching `catalogSourceLine`'s `cli_cache` branch exactly, including the fixed `en-US`-pinned month abbreviation the code comments call out.
- **Harness note, not a product defect.** The SQL seed for task 3.2 first inserted `flags='{}'` (an empty object) instead of `flags='[]'`, which crashed `GET /runners` with a `ResponseValidationError` (the schema expects a list) — a mistake in the seeding script's own SQL, not a Hub bug; corrected and re-verified before recording the PASS above.
- Teardown: `DELETE /projects/proj-cca6cd55e14e` (204); fixture directory removed. Checked for orphaned `claude.exe`/`codex.exe` processes before touching anything — two `claude.exe` found, both unrelated (this session's own host process and a separate interactive session's CLI invocation; confirmed via `Get-CimInstance Win32_Process` command lines), neither touched; no `codex.exe` running (no Codex spawn in this drive, per the standing "Codex is undrivable" rule). Trial Hub's uvicorn process (pid 17204, plus its `nohup`/`py.exe` wrapper chain) stopped; `netstat` afterward showed only `TIME_WAIT` entries on :8010, no `LISTENING`.

<!-- followed F460 in FINDINGS.md -->
## a-firing-is-counted-once-however-many-agents-it-starts drive, 2026-09-28 (fresh drive Hub :8051, profile `drive0928firing`, real `claude-haiku-4-5` turns) — no new finding

Task 3.1, `scripts/drive/d0928_firing_counted_once.py`, interactive session, on the uncommitted tree over `c1d7486` (the night window stopped at 07:00 with this change implemented but not committed). Hub started from `hub/` with `DATABASE_URL` naming a new profile; its startup line named `drive0928firing\agentweave.db` (existed before: False). Fresh project `proj-1134b9ac50bb`, one Haiku runner, agents `one` and `two`; an approved one-off document with two tasks seeded the flow's queue with two `pending` tasks.

- **PASS.** One `POST /jobs/{id}/run` started both agents (two `measured` `claude-haiku-4-5-20251001` turns). `GET /jobs/{id}` then read `run_count: 1` with two `completed` history rows sharing `fired_at 2026-09-28T08:05:44.101721Z`; a `mode=ro` read of the drive database tied them to conversations of `one` and `two`. Before this change the same firing read `run_count: 2` (F121's measurement shape).
- The history payload carries no agent field, so the per-row agent above came from the database, not the API. Not a finding: the design names `conversation_id` as the correlation.
- Teardown: job disabled and archived (`jobs left enabled []`); Hub pid 22424 stopped, `netstat` shows no listener on :8051. The fixture directory `testbed/scratch/firing-*` is scratch by testbed policy.

