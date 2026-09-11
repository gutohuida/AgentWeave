# Roadmap — finish what is open, start nothing new

**Written 2026-09-07 by a DECIDE session, at the operator's instruction: *"a plan for nothing new
but to finish everything that we have open."*** Inventory measured against the tree at `af329f5`,
not copied from handoffs — several figures the chain was carrying forward were wrong.

**Revised 2026-09-10.** Stages 1, 2 and 4 and `## Honest arithmetic` were rewritten against the
tree and the classifier; every other section is older and dated where it stands. **What changed:
Stage 2 is closed, Stage 4's tail is six findings and not `F142 alone`, Stage 1 was diagnosed and
mitigated the same day (`FINDINGS.md` F292, *"The reset was never one transaction"*), and the
stage-shaped total is retired in favour of one built on the open
findings — which resolved to a scope question the operator answered the same morning
(`DECISIONS.md`, *"The scope of the drain"*: **drain A and B, ratchet C and D**).** Read
`## Honest arithmetic` first if you are here to decide something.

This file is a **plan**, not an authority. It cannot approve a change or decide a rule: those are
`APPROVALS.md` and `DECISIONS.md`, and the tokens there remain the only authority. Where this plan
says "the operator writes a verdict", it is describing work, not performing it.

---

## The one fact that reorders everything

**This section was true for 54 minutes and is now history. It is kept, struck through, because it
is the argument Stage 0 was built to answer — and because the day window inherited it as current
and was still repeating it eight hours after it stopped being so.** The live statement follows it.

~~**The pipeline is not starved of building capacity. It is starved of verdicts.**~~

~~Four changes are fully specced — three review rounds each, every round non-empty — and **not one
carries an approval token.** The FIX window builds roughly one change a night and has been handed
nothing to build. The queue did not grow because building is slow; it grew because the DECIDE step
between the two windows has not run since 2026-09-06.~~

~~**And it is about to grow again.** `AgentWeaveArmDay` is `Ready` and fires at **08:55 tomorrow**.
`DIRECTION.md`'s newest section is dated 2026-09-07, so tomorrow has none — and the contract says
*"no section for today means compose the queue as usual"*. The default day queue is
`D-2/D-3/D-4 = spec R1/R2/R3`, which is **one new proposal**. Left alone, the day window adds a
fifth change tomorrow morning.~~

**Superseded 2026-09-08. Both halves are closed, and neither closure was written *here*, where the
reader of this claim would meet it.**

- **The verdict starvation ended at 01:24**, when `0d82d6d` approved all four with an `ORDER:`
  line — 54 minutes after this file was written, and **7 h 31 m before the day window read it.**
  Stage 0.2 below records this; this heading did not, and a document that contradicts itself in
  two places is read at whichever place the reader reaches first.
- **The fifth proposal did not happen.** `AgentWeaveArmDay` fired 08:55 on 2026-09-08 and composed
  no spec loop, on two independent authorities: `DIRECTION.md`'s dated section, and the standing
  drain gate at `.claude/loops/day-window.md` step 6 that supersedes it from 2026-09-09 on.

**What is live is the rate mismatch, not the starvation.** FILL produces one change per day and FIX
consumes one per one-to-two nights, so the arithmetic below still holds — but the queue is now four
approved changes waiting on **build capacity**, which is the ordinary case this plan is a plan for,
not a stalled DECIDE step. Tonight, 22:55, is the first build night those approvals have ever had.

---

## Stage 0 — tonight, before 08:55 (operator, ~40 minutes)

Nothing below this line can move until these are done, and item 1 expires in the morning.

| # | Action | File |
|---|---|---|
| **0.1** | ~~Write a `## 2026-09-08` section redirecting the day window off the spec loop.~~ **DONE 2026-09-08 00:35.** The section is written: no spec loop, D-1/D-2 take F292, D-3 takes hygiene. Confirmed the night of 2026-09-07 built nothing — `AgentWeaveArmNight` was disabled and there is no `2026-09-07-night-log.md` — so there was nothing to drive either. **Superseded 2026-09-08 01:40 by a standing gate** — the dated section covers one day and expired at midnight; `.claude/loops/day-window.md` step 6 now counts unbuilt specced changes and runs no spec loop at 2 or more. | `spec-queue/DIRECTION.md`, `.claude/loops/day-window.md` |
| **0.2** | ~~Write four verdict tokens.~~ **DONE 2026-09-08 — all four APPROVED** by the operator in session, after three review rounds. All four rows are restated under `## 2026-09-08` because only the newest dated section is read. | `spec-queue/APPROVALS.md` |
| **0.3** | **Write the `ORDER:` line.** ~~Three of the four touch `hub/ui` and the committed bundle… Only one is bundle-free.~~ **Corrected by the second review, 2026-09-08: two are bundle-free, not one.** `an-agent-without-mcp` names no `hub/ui` file anywhere and declares its own exemption at its `tasks.md:7`; `a-dead-connection` is Python-only. Only the two UI changes touch the bundle, and they share **no source file** — their sole collision is the generated `hub/hub/static/ui`. | `spec-queue/APPROVALS.md` |
| **0.4** | ~~Decide the night arm — the only thing between the approvals and a build.~~ **RESOLVED — measured 2026-09-08 10:05: `AgentWeaveArmNight` is `Ready`, not disabled**, `LastTaskResult=0`, last fired 2026-09-06 22:55, **next 2026-09-08 22:55.** So Stage 0 is closed in all four rows and **tonight is the first build night** the four approvals have ever had. The roadmap carried this as the single blocker for a day after it had stopped being one. | Task Scheduler |

### The four changes ~~awaiting a token~~ **approved 2026-09-08 01:24 and awaiting a build**

| Change | Finding | Tasks | Touches UI / bundle |
|---|---|---|---|
| `2026-09-07-a-dead-connection-is-never-handed-back-out` | **F295 (A)** | 25 (1 ticked) | **No** — Python only |
| `2026-09-05-the-conversation-carries-its-own-run-facts` | **F274 (A)** | 44 | Yes |
| `2026-09-07-clearing-instructions-asks-first` | DAY-3 | 25 (1 ticked) | Yes |
| `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` | sidequest | 35 | **No** — corrected 2026-09-08 |

**129 tasks, 2 ticked, neither an implementation.** (Was 127; the third review added F295's 1.6 and
clearing-instructions' 1.4 — see `review/third-review-2026-09-08.md`.) Suggested `ORDER:` — `a-dead-connection` first
(highest severity, no bundle, so it can land beside anything and cannot conflict), then
`an-agent-without-mcp` (also bundle-free), then the **two** UI changes strictly one per night. All
four now have an `APPROVALS.md` row; the fourth got one on 2026-09-08, which is what makes it
approvable at all.

---

## Stage 1 — repair the instrument first (1 night) — **STILL OPEN 2026-09-10, and its headline claim is retired**

**F292 — `sqlite3.OperationalError: database is locked`.** This is not a backlog item; it is
actively lying to every verification below it. It **failed CI on `master` at `15ce482` today at
22:03**, in `hub-test`, and the next commit `af329f5` — the same tree plus one markdown file —
passed. ~~Every change in Stage 2 will be verified by a suite that is wrong roughly half the
time.~~ **Corrected 2026-09-08 by measurement — the rate is 20.4 %, not half**, and "half" was
F279's *local* rate borrowed for F292's *CI* rate. Measured over 54 runs since 2026-09-07T00:00Z,
every failure classified individually from its own log rather than counted as red: **11 failures,
all F292, 20.4 %**; `master`-only over the last 20 runs, 25 %. The sharper number is that in that
window ~~**every red CI run is F292 — 11 of 11**, so CI redness on this project currently has
exactly one cause~~ — **struck 2026-09-10, see the live block at the foot of this stage; CI redness
now has at least two causes and the sharper sentence was the first thing to go stale.** Method,
three denominators and the 22-occurrence table are in `FINDINGS.md`'s
F292 entry and in `.claude/autonomous/2026-09-08-day-log.md` iteration 4.

~~Related and probably the same class: **F279** (the two "a stopped run" tests fail about half the
time on an unmodified tree).~~ **Measured 2026-09-08 — not the same class**, and this row was
where the two findings' numbers got mixed. They differ on every axis checked: exception
(`sqlite3.OperationalError`, an OS file lock, vs `sqlalchemy.exc.InvalidRequestError`, ORM session
state), locus (the *next* test's fixture at `conftest.py:473` vs inside the run at
`output_recording.py:94`), latency (the full 30 s busy timeout vs ~1.5 s), and reproducibility
(F292 survived 15 local runs of the blamed pair and a whole-suite run at `busy_timeout=50`; F279
reproduces 7/12 and 4/12 locally). What they share is a *cause of opportunity* — both sit
downstream of the un-awaited `asyncio.create_task(_execute_run(...))` at `agent_trigger.py:1190`.
That is a reason to build F295's change, not evidence that it fixes either.

**Status of this stage, 2026-09-08: instrumented and measured, not repaired — so Stage 1 is
open.** The day window built a fixture-level diagnostic (`hub/tests/conftest.py`: a bounded
`sqlalchemy.pool` ERROR recorder, plus a census of every connection ever checked out, sampled at
every stage) and it has now fired twice. It **named the victim, not the holder**: the only open
connection at the failure is the `DROP TABLE`'s own. No product code changed, deliberately — a
`hub/hub/` repair is out of a day window's scope. The holder is still unnamed.

**And Stage 2 is not in fact gated on this, whatever the heading says.** The night window is
steered by `APPROVALS.md`'s `ORDER:` line, not by this file's stage numbering, and that line names
four changes with no stop token — so tonight builds Stage 2 with Stage 1 open. The consequence
worth carrying rather than the ordering argument: **a red CI on tonight's build is more likely
F292 than the change**, at a measured 20.4 %, and must be classified with
`gh run view <id> --log-failed` before anything is diagnosed as a regression.

`DIRECTION.md`'s 2026-09-07 section is explicit that F292 must **not** be conflated with F295 — the
F295 change may or may not resolve the flake, and assuming it will is how the flake survives. Treat
"did `a-dead-connection` fix F292?" as a measurement to make, not an outcome to expect. **Answered
2026-09-09: it did not.** F295's change shipped, was driven live and is `fixed`; F292 has fired
three more times since. Two findings that share a cause of opportunity, exactly as the 2026-09-08
measurement said.

### Live status, 2026-09-10 — one cause became two, and the instrument finally fired

**CI redness on this project no longer has exactly one cause, and that is the single most
load-bearing correction on this page.** A second, *deterministic* cause ran for most of 2026-09-09
and was repaired the same night: `hub/pyproject.toml` constrains only `fastapi>=0.110` and
`starlette<2.0`, so CI resolved starlette 1.6.0 / fastapi 0.141.1 against this machine's
0.52.1 / 0.136.3, and `{r.path for r in create_app().routes}` yields **161 paths on one and 7 on the
other**. A test that **could never pass on CI and never fail locally survived thirteen commits.**
Repaired by `4937ece` (night of 2026-09-09) with `constraints-dev.txt`, a `-c` on every documented
and CI install, and `tests/test_dev_constraints.py` gating that the `-c` stays. Read that file's
header before touching it — it is development-only and is deliberately **not** a second statement of
what the Hub supports.

**F292 itself: the per-stage census fired, three times in one day, unanimously.** Occurrences
**#13, #14 and #15** — CI runs on `bb08dc4`, `4937ece` and `6e1a054`, all on this branch, all
`4039 passed, 18 skipped, 1 error`, all `database is locked` on `DROP TABLE requirement_drift` at
the `app` fixture's schema reset. The census reads identically in all three, and by the census's own
mutation-established criterion (*transaction state distinguishes victim from holder*) the single
late handle is **`idle`** — the victim again, almost certainly the DROP's own connection. The
dispose-before-drop mitigation is confirmed working and therefore cannot be the fix; the
child-process candidate is demoted; the un-awaited `asyncio.create_task(_execute_run(...))` at
`agent_trigger.py:1190` is **promoted to the candidate the evidence points at**, because all three
predecessors are flow-fires-a-review tests. Full reading in `FINDINGS.md`'s F292 entry, written by
the day window of 2026-09-10 — **it supersedes every earlier part of that entry and says so at the
top.**

**The 20.4 % figure is stale and its replacement has not been computed.** Measured 2026-09-10 over
the last **21 concluded** CI runs on `autonomous/2026-09-08-daily`: **9 failures, 43 %.** That number
must not be quoted as F292's rate — **the reds in that window have at least two causes and have not
been classified individually**, which is the discipline this stage itself demands (`gh run view <id>
--log-failed` before diagnosing anything as a regression). Classifying them is open work; do it
before the next rate claim, not after.

**So Stage 1 is still open, and it is now the oldest open thing on this page.** Every other stage
has closed or moved. The holder is still unnamed after five windows have read it; what changed on
2026-09-10 is that the search space narrowed to one named line of product code, which a day window
may not repair (`hub/hub/` is out of its scope). **This is a night's work behind a proposal, and no
proposal exists.**

### Superseded the same afternoon — the reset was never one transaction

**Every reading above, and every instrument in F292's entry, assumed the failing `DROP` was inside a
transaction. It never was.** Measured 2026-09-10: SQLAlchemy's pysqlite/aiosqlite dialect emits no
`BEGIN` until a **DML** statement, and DDL is not DML — so `driver_connection.in_transaction` reads
**`False`** after the first `DROP` inside `async with engine.begin()`, and the ~90 drops in
`Base.metadata.drop_all` are **~90 independent autocommit write transactions**. A foreign connection
was measured **taking the write lock between two of them**, after which the next `DROP` failed
`database is locked` on the full busy timeout — CI's exact signature, reproduced in isolation, with
no dead worker thread, no subprocess, and nothing holding the file for thirty seconds.

That retires the two things this entry kept calling blind spots. **`[before drop_all]`'s census was
never blind** — it samples once, and the vulnerable window opens ninety times *after* it. And the
failure landing on `requirement_drift` rather than the first table, unexplained under a
one-transaction model, is the expected shape when the sequence runs until it loses a race.

**Mitigated by one line** — `BEGIN IMMEDIATE` before `drop_all`, so the lock is taken once and held;
the same foreign writer is then refused. Gated by
`hub/tests/test_schema_reset_holds_the_write_lock.py`, mutation-checked three ways, **and the first
version of that test failed its own mutation check and then failed the full suite** — both recorded
in the test rather than quietly fixed.

**Stage 1 is mitigated, not closed, and the distinction is the point.** F292 was not reproduced in
CI and a ~20–40 % race cannot be asserted by a test. What is closed is a race with this exact
signature that was reachable on every reset. **If F292 survives, that is itself informative**: the
holder would then arrive *before* the reset rather than during it, which is far narrower than
anything this entry has carried. The next window measures the rate; it does not assume the answer.

> **Measured 2026-09-11 (day `D-1`), and it survived.** F292 reproduced on the mitigated tree at
> `f51ec21` (run `34576656234`), same `database is locked` signature, same file. Classified rate:
> **1 red in 17 runs with the mitigation against 11 in 41 without** — one-sided `p ≈ 0.036` for "no
> change", with a 95% interval on 1/17 that still contains the old 26.8%. So the mitigation is
> **confirmed as a mitigation and refuted as a fix**, and the informative branch above is the one
> that fired: **the holder arrives before the reset begins.** Per-run classification, the F314 and
> starlette confounders counted out, and the caveats are in `FINDINGS.md`'s F292 entry, last
> section.

Two things fell out of the control measurement and are filed separately: **F314 (B)** — the flow
files fail about **one run in eight** under random ordering **on an unmodified tree**, at the same
rate with and without this fix, so it is a *second* non-F292 source of CI red in the very file
family F292 clusters in. And this entry has been carrying **two failure modes under one heading** —
an unbounded hang with no `busy_timeout` involved, and a `database is locked` that *is* a
busy-timeout expiry.

---

## Stage 2 — build the four approved changes ~~(5–6 nights)~~ — **DONE in two nights**

~~One change per night, in the `ORDER:` line's sequence. The 44-task change is likely two nights.~~

**CLOSED 2026-09-10.** All four are built, driven and archived, and `openspec/changes/` now contains
nothing but `archive/` — **the approved queue is empty for the first time in this sequence.** The
estimate was wrong by a factor of three, in the direction this file's audit says it is always wrong.

| Change | Finding | Tasks | Archived |
|---|---|---|---|
| `a-dead-connection-is-never-handed-back-out` | **F295 (A)** | 25 | `37007cd`, 2026-09-09 01:54 |
| `an-agent-without-mcp-is-not-told-it-has-nothing` | sidequest | 35 | `6557844`, 2026-09-09 04:57 |
| `the-conversation-carries-its-own-run-facts` | **F274 (A)** | 44 | `1b7a4cb`, 2026-09-09 06:48 |
| `clearing-instructions-asks-first` | DAY-3 | 25 | `fc9001a`, 2026-09-10 01:02 |

**129 tasks over two build nights** — three in the night of 2026-09-08, the fourth in the night of
2026-09-09. **F274 and F295 are both `fixed` and both driven live**, so the two severity-A findings
this stage owned are genuinely closed, not closed on a plan existing.

**The correction that matters is not the schedule — it is that draining produced findings.**
Building and driving these four filed **three new severity-A findings and one B**, every one of them
from a *drive*, none from a review:

| New | From |
|---|---|
| **F299 (A)** — a `claude` run whose harness has no MCP cannot write a file, and blames the operator's machine | driving `an-agent-without-mcp`, task §4.9 |
| **F300 (A)** — the workspace approver denies every shell command containing a URL, including the one its own notice instructs | same change, §6.3/§6.4 |
| **F301 (A)** — on the `cli` access path a `claude` run has no tool that can make the request it is told to make | same session as F300 |
| **F307 (B)** — a confirmation dialog's first Tab leaves the panel, into the editor behind the scrim | driving `clearing-instructions`, in the shared `useDialogFocus` hook |

Two of the four archive commits say this in their own subjects — *"the finding is half-retired"*,
*"it closes none of the findings it names"*. **A change reaching `archive/` is not a finding
reaching `RESOLVED`**, and a plan that counts archived changes as drained findings will read as
finished while the ledger grows. That is the mechanism behind the arithmetic at the foot of this
page, and it is why the totals there are built on findings and not on stages.

**The rules that mattered here, both held:** never mark a task complete on the strength of the plan
existing; and a UI change is not finished until `npm run build` and `make ui` have run and the
bundle is committed beside `hub/ui/src`.

---

## Stage 3 — ~~R-1~~ **DECIDED 2026-09-08.** R-2 and R-3 remain

**R-1 is settled: enforce, as a ratchet.** Decided by the operator in session, 2026-09-08 00:30;
written up in `DECISIONS.md`. The repo writes a check, and the check freezes today's count as a
ceiling that may shrink and may never grow — existing instances are **not** repaired before the
check may pass.

Three checks authorised, all promoting scripts that already exist and both of which reproduced their
2026-09-02 figures exactly when re-run on 2026-09-08:

| Check | From | Frozen ceiling |
|---|---|---|
| route reachability | `scripts/drive/n10_route_reachability.py` | **35** routes with no client |
| query error surface | `scripts/drive/n11_query_error_surface.py` | **51** operator-reachable MISREPORT sites |
| dependency ceilings agree | new, small | the three `fastmcp>=2.0,<4` declarations, `starlette<2.0` |

**This is why the total below resolves to three-to-four weeks rather than eight-to-ten.** ~20
findings stop being backlog and become bounded. The cost taken knowingly: those 35 routes and 51
misreports stay wrong, with a passing test blessing them, until something touches them on its own
merits.

**The three checks are Stage 6 work, not Stage 3 work** — they sit behind the four approved changes
and the F292 repair. Building them first would be starting something new.

~~Still open, both small, both a week old: **R-2** … and **R-3** ….~~ **Both DECIDED 2026-09-08**,
in the same session as R-1 (`DECISIONS.md`, `## Decided`). R-2: **a repo script**, with its weakness
recorded — a script only fires if whoever archives remembers to run it. R-3: **all four answered** —
thread F209's `reason` through; **remove** `PATCH /queue/settings`; a bare `uvicorn hub.main:app`
from `hub/` must **refuse to start**; check the model catalog with a `scripts/` tool, not a
CI-skipped test.

**So Stage 3 has no open decision left — but it has gained work nothing schedules.** R-2's script and
R-3's four are **verdicts, not implementations**, and no stage in this plan owns them. See the
completeness audit at the foot of this file.

**A trap this file helped create, found and fixed 2026-09-08.** `DECISIONS.md` carried **two copies
each** of R-1, R-2 and R-3 — one above `## Decided` and one below it. R-1's upper copy had been
rewritten to say DECIDED; **R-2's and R-3's still read `**OPEN.**`**, 108 and 123 lines above their
own verdicts. A window reading that file top-down, exactly as its contract says to (*"the status
token is the authority"*), would have found both open. Both upper copies now carry the verdict and
point down. This is the same defect class as an approval row that looks right and does nothing.

---

## Stage 4 — the severity-A tail ~~(after R-1, because R-1 may absorb some of it)~~ — **R-1 decided; the tail is four, not one**

| Finding | What it actually needs |
|---|---|
| **F52** | **Close it — bookkeeping only.** Its operator-visibility half shipped (`68459ea`), `0cda570` disproved its central inference, and `57eb92b` drove a full live turn that committed. Its own row says a new git refusal would be a *new* finding. It is counted as open because nobody retired it. |
| **F140** | ~~One decision with F142, not two.~~ **RETIRED 2026-09-08 — there was no decision here.** Repair 1 shipped `1b4c730` (2026-08-30) and was **driven live 2026-08-31**: both Haiku agents made the `update_task(..., status="completed")` call unprompted, both tasks reached `approved`, both commits verified ancestors of `master`. `_briefing_completion_lines` is byte-identical to the driven version, re-measured this session. The 2026-09-03 banner asked for a re-drive that already existed in `FINDINGS.md` two days earlier. |
| **F142** | ~~Not an operator decision — a missing drive.~~ **RESOLVED 2026-09-09 — the drive happened.** Driven on a live Hub by the night window: **20/20 on `operator_after_agent`, 19/19 on `untouched`.** Both claims held. The drive's *row four* — the operator completes a task no agent ever touched — is what found **F306** below; that does not reopen F142, it is a second defect inside the same repair. |
| **F14, F60** | ~~F60 not implemented, blocked on F14's undecided fix shape.~~ **Both `FIXED 2026-08-30`**, shipped together in `a-task-waits-while-its-run-waits`, and `FINDINGS.md` has said so since. Verified in code 2026-09-08: ask-time parking at `agent_actions.py:509-514`, `Question.wait_ended_at` at `models.py:1001`, migration `0099`, drive harness `t_f14_f60_wait_parks_the_task.py`. This table was simply wrong. |
| **F154** | ~~Archived change, never driven.~~ **RETIRED 2026-09-08 — the drive existed.** Fix `001a07d` (2026-08-31), driven the same day: `t_f154_wedged_review.py`, **18/18** on both the reviewer-wedged and author-wedged populations, re-driven 18/18 later. `run_task_binding.py` and `scheduler.py` are byte-identical `001a07d`→`HEAD`. |
| **F155** | ~~Archived change, never driven.~~ **RETIRED 2026-09-08 — the drive existed.** Fix `0373867` (2026-08-31), driven the same day: `t_f155_conflict_remedy.py`, **23/23**, the harness parsing the branch out of the refusal's own sentence, with the falsifying lane run deliberately. `requirement_gate.py` is byte-identical `0373867`→`HEAD`. Its drive filed **F165 (B)** and **F166 (C)**, which stay open. |
| **F274, F295** | ~~Already specced — they are Stage 2.~~ **Both `fixed` and driven; Stage 2 is closed.** |

### The live severity-A tail, 2026-09-10 — six open, and not one of them existed when this stage was written

**`F142 alone` is retired.** F142 resolved on 2026-09-09 and the tail was immediately replaced by
findings that the drives of Stages 2 and 4 produced. Measured with
`py -3.11 scripts/classify_findings.py`, not copied: **55 severity-A sections, 48 `RESOLVED`, 6
`OPEN`, 1 `CONFLICT`.**

> **This table was written at 09:30 saying four, and was wrong by 10:00.** F309 was filed by the day
> window and F312 by the session writing this section, both inside the same morning. **Do not read
> any count on this page as current** — the classifier is one command and it is the only authority.
> Recorded rather than quietly patched, because a stale count *in the direction of finished* is the
> specific failure this whole revision exists to correct, and it recurred within half an hour of
> being named.

| Finding | What it needs | Owner |
|---|---|---|
| **F299 (A)** | **Decided, unproposed.** Teach `_decide` that the run's own Hub URL is not a filesystem path (`DECISIONS.md`, 2026-09-09). Rejected there: falling back to `acceptEdits`. | R1/R2/R3 then a night |
| **F300 (A)** | **DECIDED 2026-09-09, narrowed 2026-09-10 to this finding alone** — teach `_decide` the run's own Hub address. The 2026-09-09 verdict named three findings and its mechanism reached only this one. **Ships with F312 as one change.** | R1/R2/R3 then a night |
| **F301 (A)** | **DECIDED 2026-09-10 — needs no containment decision.** Measurement overturned its stated mechanism: remove the approval gate and all five of its "refusal classes" execute, so they are reasons a command *needs approval*, not reasons it is forbidden. The `cli` path simply has no answerer. Closed by the notice change. | folds into the notice change |
| **F306 (A)** | **Undecided, and it is a governance hole.** An agent can be staffed to review, and approve, work it recorded evidence for. `requirement_evidence.actor` is not one of `agents_that_may_have_authored`'s three sources (`task_transition_service.py:253-283`), and `_guard_author_is_not_reviewer` (`:286-311`) compares against `agent_that_completed`, which is NULL on an operator completion. **Both defences share the blind spot.** **DECIDED 2026-09-10 evening: repair BOTH defences, and count EVERY evidence row regardless of `review_state`** — the function's own docstring principle, applied to the fourth source it omits. | R1/R2/R3 — **tomorrow's spec loop** |
| ~~**F309 (A)**~~ | **RESOLVED 2026-09-11.** Filed 2026-09-10 by the day window's `D-1` drive, proposed and approved the same day, built and driven the same night, archived as `2026-09-10-the-control-that-asks-holds-the-keyboard` — **filed to archived inside one cycle**, which no previous A on this page has managed. `F310 (B)` shipped with it. Both took two commits each; `FINDINGS.md` names which did which half. | done |
| **F312 (A)** | **DECIDED 2026-09-10 evening** — allow the run's own Hub URL, deny every other URL with a reason naming network access, not the filesystem. Settled by measurement: `python -c` already makes the identical request, so today's behaviour is a **syntax filter, not containment**. Explicitly **not** a claim that egress is now contained. | **one change with F300** |
| **F52 (A)** | `CONFLICT` — still the bookkeeping close described above. Unchanged since 2026-08-27. | ten minutes |

### 2026-09-11 — the first row of that table to close, and what it cost

`2026-09-10-the-control-that-asks-holds-the-keyboard` is **archived**. It carried two findings, not
one, and the night window was told to verify it as two: **F309 (A)** — the blocking-reason input
never gets focus, so the operator's reason is typed into the status menu and each space re-opens the
menu — and **F310 (B)** — one Escape dismisses two things, so the ticket closes out from under the
control the operator was actually cancelling.

**The severity-A tail is now five: F299, F300, F301, F306, F312.** Measured with
`py -3.11 scripts/classify_findings.py` over 315 sections at close-out, not copied from the table
above: **55 severity-A sections, 49 `RESOLVED`, 5 `OPEN`, 1 `CONFLICT`** (F52, the standing
bookkeeping close). None of the five is buildable unattended — four need a proposal and one is
`DIRECTION.md`'s spec loop for 2026-09-11 — so the night window that closed this had no successor
item, which is why it stood down rather than starting one.

**Three things this change establishes that outlast it.**

1. **A fix can span commits and the ledger has to say which did which.** Both findings took two
   commits, and in both cases either commit alone was measured *not* to work: `7a0e5bc` hands the
   keyboard over but `beb38d6` is what receives it; `9ed1d6d` lets the outer panel stand down but
   `beb38d6` is what tells it to. A single-sha `Status:` line would have been wrong twice.
2. **The drive found what three rounds and a green suite did not.** The first run against the
   implemented bundle was 45 passed / 2 failed and **the two survivors were the finding itself** —
   Radix flushes `onSelect` synchronously, so the reason panel's focus effect ran while the menu
   scope was still trapping. Two browser probes named it; the repair became a task (`§3.2a`) that no
   round had written.
3. **A change is allowed to leave its neighbour standing.** `F307` lives in the same hook, one
   branch over, and the operator answered `DAY-1` **no** on 2026-09-10 18:30: the split stands.
   `F307`'s section now carries a dated note saying so, with leg E of
   `t_d9_clearing_instructions_postchange.py` still reproducing it against the bundle that carries
   this change — evidence that the repair did not reach it by accident either.

**One new finding, deliberately not repaired here.** `F315 (C)`: the *Mark waiting* button gives no
feedback for the 1.5-3 s its mutation takes, stays enabled, and a second press writes the move again
(the Hub answers the duplicate `200`; the draft of that finding predicted a refusal and was measured
wrong, which the entry says). Every status move in that menu shares the gap, so it wants a change
that owns optimistic feedback for task mutations rather than a patch to one button.

**F299, F300 and F301 are one subject, not three.** All three are the access-path/approver posture
seen from three angles, all three were filed by the *same* drive on 2026-09-09, and answering them
separately is how a posture acquires three inconsistent special cases. **Put them to the operator
together.** — **Done 2026-09-10**, and reading them together is what found that the 2026-09-09
verdict named three findings and its mechanism could fire for only one. The grouping was right and
the answer was three different mechanisms, not one.

~~**Not one of the six is buildable unattended today**, because four need a verdict and the other two
need a proposal.~~ **Superseded 2026-09-10 evening: every open severity-A finding now has a
verdict** — the first time in this sequence. The tail is short of **proposals**, not decisions:

| | |
|---|---|
| ~~**F309**~~ | **built, driven and archived 2026-09-11** — the only row of this table that has moved |
| **F306** | decided; **tomorrow's spec loop** (`DIRECTION.md` `## 2026-09-11`) |
| **F300 + F312** | decided; **one change**, unproposed |
| **F299** | decided; unproposed |
| **F301** | decided; folds into the notice change, unproposed |
| **F52** | `CONFLICT`, bookkeeping only |

**At one proposal per day window that is four more days before the A-list can be empty**, and the
round discipline is not compressible. The order is fixed in `DIRECTION.md` so it is not re-decided
each morning. **Stage 0's shape is finally broken here** — this stage is short of neither capacity
nor decisions now, only of the three rounds each change owes.

~~**This whole table was stale, and in the direction that costs most.**~~ **It was stale again by
2026-09-10, and this time in the *opposite* direction — it read finished when four A-findings were
open.** Both directions have now been observed on this one table, which retires the comfortable
reading of the paragraph below: the documents do not lag the evidence *pessimistically*, they simply
lag it. The 2026-09-08 text is kept as written.

**This whole table was stale, and in the direction that costs most.** Three of its four original rows
described operator decisions that did not exist, which is how the severity-A tail read as
*blocked on the operator* when it was actually *one drive short*. Corrected 2026-09-08 by measuring
the code rather than re-reading the plan. Note the direction: `ROADMAP.md` was written 2026-09-08
00:30 and was stale on rows `FINDINGS.md` had had correct for nine days — **a newer document is not
a more current one.**

**Corrected again the same day, and the second correction is larger than the first.** The paragraph
here used to end *"F154 and F155 have not been re-checked the way F140 was, and that search is the
obvious next move."* The search was run on 2026-09-08 and **retired both**: each had a fix commit and
a same-day drive recorded in `FINDINGS.md`, twelve thousand lines below the banner that said no drive
existed. ~~So the open severity-A tail after F52 is retired and F274/F295 are built is **F142 alone** —
one finding, blocked on one drive, with no operator decision anywhere in it.~~ **Struck 2026-09-10.**
F142 resolved, F274 and F295 shipped, and the tail is **F299/F300/F301/F306, plus F309 and F312 filed
the same morning this was written** — six findings, four of them blocked on an operator decision,
which is the exact condition this sentence claimed was gone. It was true for about thirty hours. See
the live table above, and run the classifier rather than believing this number either.

**The arithmetic of this one day is the point.** The severity-A count went **six → five → three**
without a single line of product code being written. **And the full arc, three days on: six → five →
three → one → four → six**, the last step taken in the single morning this revision was written.
Reading retired three; building, driving and reading-for-a-verdict filed five more. Both halves are
real and the second is the one this plan had no term for — see `## Honest arithmetic`. Every one of those retirements was a document
catching up with evidence that had been on disk for a week. The failure was never capacity — it was
that three banners asked *"has anyone driven this?"* and nobody grepped this file for the finding's
own number. **Grep before believing a banner that says no drive exists**; it costs ten seconds and it
has now paid three times.

---

## Stage 5 — REMOVED 2026-09-08: not AgentWeave's work

This stage scheduled work in **two separate repositories** — `witness` and `continuity-kit` — and
has been removed at the operator's instruction: *"I want only things for agentweave here in this
repo."* Neither is a dependency of anything above; nothing in Stages 0-4 or 6 waits on them.

- **`witness`** — `C:\Users\huida\Documents\projects\witness`. Owns its own decisions now, in its
  own `DECISIONS.md`. The `OV-` series moved there with it.
- **`continuity-kit`** — parked by the operator 2026-09-08: *"Not yet. Let's leave that one aside,
  I'll come back to it when we finish with the fixes on agentweave."*

**What stayed here, because it is AgentWeave's:** `scripts/snapshot-corpus.ps1` and the
`ClaudeCorpusSnapshot` scheduled task. It archives this machine's Claude Code transcript corpus
daily at 12:30 and is unrelated to either repository's roadmap — the retention question was
deliberately answered *outside* Witness, with a plain file copy.

**Two signals on that snapshot, both currently expected-but-unproven.** `kept_beyond_source` is **0**
and will stay 0 until the corpus ages past the window — correct today, a **failure signal** later.
And **the restore path has never been exercised**: copying was verified, reading a transcript back
out of the archive was not.

---

## Stage 6 — hygiene (one window; every item is small)

| # | Item | Detail |
|---|---|---|
| **6.1** | ~~Run `scripts/sync_skills.py`, then gate it.~~ **DONE — 2026-09-08, day window iteration 7.** Synced; gated by `tests/test_skill_sync.py`, mutation-checked against four deliberately-stale shapes. **The staleness was wider than this row said:** five skills differed, not two — `autonomous-prep`, `autonomous-session` and `e2e-loop` (`install-driver.ps1` 230→182, `run-iteration.ps1` 266→181, `e2e.py` 411→385) drifted alongside `handoff` and `resume`, and the two `.ps1` files are the autonomous driver itself. The row's own numbers were right; its *inventory* was not, because it was assembled from what a reader noticed rather than from a diff. The gate now does the diffing. **Canonical count, reconciled 2026-09-08 because this row and the day log state it two different ways:** of 16 owned skills, **six were wrong at either destination** — `handoff`, `resume`, `autonomous-prep`, `autonomous-session`, `e2e-loop` differed, and `daily-review` was absent from both trees. This row's *“five differed, not two”* counts only the five that existed-and-differed against the two the row gave line numbers for; the log's *“six, not three”* counts absence as wrongness and the row's three named skills as named. Both are arithmetic on the same diff; **6 of 16 wrong, 3 of 6 named in advance** is the form to quote. Two sub-findings: the sync copied `__pycache__` (fixed, `IGNORED` in the script), and the gate **skips** a destination it cannot find — both trees are untracked and absent on a CI runner, so it ratchets developer machines, not CI. |
| **6.2** | ~~`scripts/drive/aw.py:16` promises a guard that does not exist.~~ **DONE — 2026-09-08, day window iteration 8.** The guard was added rather than the comment weakened. `require_key()` raises `SystemExit` — deliberately not `RuntimeError`, because this directory is full of bare `except Exception` and `api()` swallows one into `(0, "...")`. Measured against the live Hub on 8010: HEAD's code with `AW_KEY` unset returned **401 with exit code 0**; the guard fails locally with exit 1 and a urlopen tripwire proves no request reaches the network. The 200 and the real-401 paths are unchanged. Gated by `tests/test_drive_key_guard.py`, mutation-checked against three defects (the HEAD file; a reintroduced key literal; a blanket refusal) — and one mutation it deliberately does **not** catch, recorded in the test. **Wider than this row said:** the same file family carried the key-literal defect 6.3 describes, and the fix removed all of it — see 6.3. |
| **6.3** | ~~Rotate the disclosed `aw_live_` key.~~ **DONE — the operator rotated it, stated in session 2026-09-08 09:20.** Closes the day window's `day1` question (*"may the loop rotate keys itself?"*), which is now moot for this key and was never answered in the general case. **Residual, largely cleared 2026-09-08 by 6.2:** the classification found 18 real-shaped 32-character `aw_live_` literals in **16 tracked files**. The nine `scripts/drive/` scripts among them (this row said eight; the test counts nine) now call `require_key()` instead of defaulting a key, and `tests/test_drive_key_guard.py` fails if one comes back — **10 literals in 8 files remain**, all outside `scripts/drive/` except `FINDINGS.md`'s own transcript: the documented `a1b2c3…` placeholder (`hub/.env.example`, `hub/hub/db/engine.py`, `hub/tests/test_setup.py`), the redaction fixtures in `hub/tests/test_operator_is_told_the_truth.py` that exist *because* the key leaked, and four historical documents. All are dead against a rotated key. What is not dead is the practice that produced them; a rotation is final only if nothing commits a live key again. Classified by shape without printing any value. **RECOUNTED AND REOPENED, THEN CLOSED AGAIN — 2026-09-09, day window D-4 (`F303`).** The recount returned **exactly 10 real-shaped literals in 8 files**: the number above is right to the digit and the sentence attached to it was false. *All outside `scripts/drive/`* was wrong — four scripts there still defaulted a key into `Authorization: Bearer`, invisible to both the count and `tests/test_drive_key_guard.py` because the literal was placeholder-shaped (33 characters, not hex) rather than a real key's shape. A count of disclosed secrets and a guard against a bad practice are different questions, and only one of them is about shape. All four now call `require_key()`; the new gate `test_no_drive_script_defaults_the_key_to_anything` rejects a non-empty default of any shape and is mutation-checked four ways, including the exact literal the old gate walked past. *All are dead against a rotated key* was true of every database — measured, three local databases, all three distinct literals, no rows, the `live` profile read on a copy and never touched — and incomplete: **`hub/.env` still held the disclosed key**, untracked, and `hub/hub/config.py:21` loads `.env` from the working directory that CLAUDE.md's own trial-Hub launch command uses. `_seed_operator_credential` (`hub/hub/db/engine.py:336-341`) mints a configured bootstrap key verbatim unless it is empty or the documented placeholder — measured, with the placeholder as a negative control — so the next fresh-database launch from `hub/` would have re-minted it. Rotated there today. |
| **6.4** | ~~`.claude/handoffs/LATEST.md` names the wrong handoff.~~ **DONE — verified 2026-09-08 10:10.** It names `handoff-0116-…`, which is the highest-numbered file on disk. Whatever fixed it did not record itself here. |

The 35 client-less routes are **not** listed here on purpose: they are R-1's evidence, and picking
them off one at a time is exactly the behaviour R-1 exists to decide about.

---

## Honest arithmetic

### The stage-shaped total, kept and retired

| Stage | Whose time | Cost | Outcome |
|---|---|---|---|
| 0 | Operator | **done 2026-09-08 01:30** | closed |
| 1 | One night | 1 window | **still open 2026-09-10** — and the estimate was never tested, because no window has ever been given it |
| 2 | Nights | ~~5–6 windows~~ | **closed in 2** |
| 3 | Operator | ~1 hour | closed — all three decided 2026-09-08 |
| 4 | Nights | ~~**~1 drive**, F142 alone~~ | **the drive happened and the tail grew to four** |
| 5 | — | **REMOVED 2026-09-08** | not this repo's |
| 6 | One window | 1 window | closed 2026-09-08, re-closed 2026-09-09 |

~~**Total, if R-1 answers "enforce": roughly three to four weeks of nights.**~~ **RETIRED
2026-09-10.** Five of the seven rows have resolved and the total was wrong in both directions at
once: Stage 2 cost a third of its estimate, Stage 4 cost more than its estimate and *grew*, and the
whole figure was computed while assuming the 119 then-unclassified findings were zeroes. **They were
89–95 % live.** A stage-shaped total cannot survive that, so what follows replaces it.

### The finding-shaped total, 2026-09-10

Run `py -3.11 scripts/classify_findings.py` for current numbers — **do not quote these; they move
daily.** As measured this morning, over **308 sections**:

| | A | B | C | D | ? | total |
|---|---|---|---|---|---|---|
| **open** | 6 | 64 | 72 | 14 | 2 | **158** |
| conflict | 1 | 1 | 0 | 0 | 0 | 2 |
| resolved | 48 | 58 | 26 | 5 | 11 | 148 |
| unclassified | 0 | 1 | 3 | 1 | 0 | 5 |

**Measured four times in one day — 147 → 150 → 157 → 158 — and the moves have different
causes.** The first was real: F309, F310 and F312 were filed while this section was being written,
which is the source term this section exists to name. The last was real too — **F314, filed by the
control measurement of a fix, which is the source term again and from a new direction: not driving,
not reading, but *checking whether a repair broke anything*.** **The middle move changed no finding
at all.**
`dee508c` repaired `classify_findings.py` (a table recording a wrong verdict was being read as
*making* one), and the repair re-bucketed the ledger: `CONFLICT` fell 8 → 2, and **`UNCLASSIFIED`
returned to 5** after the 2026-09-09 milestone of zero.

**So a count on this page can go stale without anybody touching the ledger**, because the instrument
is under active repair too. That is the sharper reason not to quote any number here: not merely that
findings arrive, but that *what counts as open is itself being corrected*. `UNCLASSIFIED: 0` is no
longer true and the sections celebrating it below are dated accordingly.

**The two measured rates that price it.** Proposals: **one change per day window** — `D-2/D-3/D-4` is
R1/R2/R3 on a single change, and the round discipline forbids compressing it. Builds: **one to three
changes per night** (3 on 2026-09-08, 1 on 2026-09-09). **So the binding constraint is proposals, not
build capacity** — the opposite of the assumption this file opened with, and the reason "nights" was
the wrong unit all along. The unit is **days**.

| Scope | Open findings | At ~1 proposal/day |
|---|---|---|
| severity A only | **6** | ~a week — *but four are blocked on a verdict, not on a day* |
| A + B | **70** | ~10 weeks of unbroken daily cycles |
| everything open | **158** | **~5 months** |

**And every one of those figures assumes the ledger stops growing, which it measurably does not.**
Stage 2 closed two severity-A findings and filed three more plus a B — a **net severity-A drain of
minus one over the whole stage.** That is n=1 and must not be read as a law; what it does establish
is that *driving a change is also a defect-finding activity*, so the backlog has a source term this
plan never modelled. The honest form: **158 is a floor on the work, not an estimate of it** — and the
floor rose by three while this section was being written.

### The scope — **ANSWERED 2026-09-10: drain A and B; C and D are not proposed against**

**"Fix every open finding" was never a plan the operator had agreed to, and this file must not adopt
one by arithmetic.** It was put to them and answered the same morning.

**The verdict is in `DECISIONS.md`, `### The scope of the drain`, and that is the authority — this is
a pointer, not a second copy.** In short: **the open A and B findings are in scope** (70 as of late afternoon,
~10 weeks at one proposal per day window) and **the open C, D and unlabelled findings (88) are not
proposed against.**

> **The word "ratcheted" stood here for a day and was wrong — amended the evening of 2026-09-10.**
> The verdict originally cited R-1's model, and R-1 freezes *a count of one homogeneous, countable
> population*: 35 clientless routes, 52 MISREPORT surfaces. **The 88 are heterogeneous — there is no
> number to freeze and no check can assert them.** So there is no ceiling, and **nothing stops that
> population growing.** A count ceiling was considered and rejected: it would go red whenever a drive
> files a new low-severity finding, and a gate that punishes honest reporting gets worked around.

Rejected there: draining everything (~5 months, and dishonest unless the minus-one source term is
accepted), and draining A then re-measuring (defers the same question by a week while the day
windows keep proposing from wherever the ledger is read from).

**Read the cost before quoting the plan as finished, and it is larger under the amended wording.**
35 of the 75 low-severity findings read on 2026-09-09 are named nowhere outside `FINDINGS.md`. With
no ceiling behind them, **unscheduled is very close to forgotten** — that was put to the operator in
those words and accepted deliberately.

**Two things this verdict does not do.** It does not schedule the three R-1 ratchet checks — still
Stage 6, still unowned, and *a verdict is not an implementation* is this plan's oldest structural
hole. And it does not touch the **8 `CONFLICT`** findings, which need a hand read at any severity.

**The scope verdict does not unblock the front of the queue, and the blocker is not capacity:** F300, F301 and F306
need operator verdicts, F299 needs a proposal behind its verdict, and Stage 1 needs a proposal at
all. **Five items, none buildable unattended, all of them ahead of any total on this page.**

**Every total above assumes the day window produces changes at exactly the rate the nights consume
them, and that is now a governed quantity rather than a hope**: `.claude/loops/day-window.md` step 6
counts unbuilt specced changes and runs no spec loop at 2 or more, releasing itself when the nights
catch up (decided 2026-09-08, `DECISIONS.md`). Stage 0.1's dated `DIRECTION.md` section covered
2026-09-08 only and expired at midnight; the gate is what carries it from 2026-09-09 on.

**The gate has now released twice, and the first release had to be overridden by hand — which is a
measurement of what the gate cannot see.** On **2026-09-09** it released at a count of 1 and would
have produced a fifth proposal; the operator overrode it with a dated `DIRECTION.md` section, because
**the gate counts *specced* work and was blind to a 119-finding backlog that had no spec.** On
**2026-09-10** it released at 0 and was correctly left to run — `openspec/changes/` held nothing but
`archive/`, and the day window composed a spec loop without anybody having to remember to turn
proposing back on.

So the gate is sound for what it measures and **is not a scheduler**: it answers *are the nights
behind?*, never *is this the right change to propose?* From 2026-09-10 the proposal tap is open at
~1/day, and **nothing but the scope choice above decides where those proposals point.** Left
unanswered, the day windows will keep pointing them wherever the ledger happens to be read from.

---

## What this plan deliberately does not do

- **No new tools.** Not the loop dashboard (the Hub already ships ~1,030 lines of loop surface —
  `loops.py`, `LoopsIndexTab`, `LoopFiringGroup`, `LoopTab`, `AccountingPanel`), not a database
  behind the continuity kit, no overseer. **Both of those live in other repositories and are not
  this plan's to schedule** — see Stage 5.
- **No corpus migration.** `openspec/specs/` stays where it is; that call has not been made.
- **No sweeps.** The 17-row coverage sweep is complete (`scripts/drive/SURVEY.md:144`). New driving
  comes from open findings or from a change just built, never from resuming it.
- **No new findings hunted.** Driving still happens in Stage 2 — a change is not finished until it
  has been driven — but a drive that files something new adds to the half that is already
  oversupplied. File it; do not spec it until this plan is drained.

---

## Completeness audit — 2026-09-08, at the operator's question *"is the roadmap complete?"*

Measured against the code and the files, stage by stage, not re-read. **The honest answer is: this
plan is accurate about what it covers, and it is not a plan to a fully functioning AgentWeave.**
Those are different claims and the file did not previously distinguish them.

### 1. What was stale — five rows, all in the direction that hides progress

| Row | Said | Measured 2026-09-08 |
|---|---|---|
| **0.4** | night arm **DISABLED**, *"the only thing between the approvals and a build"* | **`Ready`.** Last fired 2026-09-06 with result 0; next **tonight 22:55**. Stage 0 is fully closed. |
| **3** | R-2 and R-3 *"still open, both small, both a week old"* | **Both DECIDED 2026-09-08**, in the same session as R-1 |
| **5** | *"a snapshot-first framing was offered and declined"*; corpus rolling off | **Snapshot built, scheduled, and verified from the scheduler.** Roll-off stopped |
| **6.4** | `LATEST.md` names the wrong handoff | **Correct** — it names `handoff-0116`, the newest on disk |
| **4** | (corrected earlier today) six open severity-A | **Three**, then **one** after Stage 2 lands |

Every one of these was stale *pessimistically*. The pattern is now three-for-three across this file
and `FINDINGS.md`: **the documents lag the evidence, and always in the direction that makes the
project look more blocked than it is.** Nothing found today was a nasty surprise; everything found
today was progress nobody had written down.

**Stage 6 is now closed.** **6.2 closed 2026-09-08** — and, like 6.1, it closed with the row
understating the defect: the comment that lied sat above a file family in which **nine** scripts
defaulted a key-shaped literal — eight of them the disclosed key itself, one a synthetic. The row
named one file because that is the one a reader had noticed. The grep that found the other eight
was written as a test, and it found seven of them *after* a hand grep in the same session had
already "checked" — that hand grep was truncated by `head -20`. 6.3's own classification said
eight `scripts/drive/` files; the machine-run count is nine.
**And nine was not the count either: 2026-09-09's recount found four more in the same
directory** (`F303`), placeholder-shaped and so invisible to a grep for a key's shape. Three
successive counts of one directory, each right about what it measured and each attached to a
sentence wider than it. **Stage 6 re-closed 2026-09-09** with the guard rewritten to ask about the
default rather than about the shape of what is defaulted.
**6.1 closed 2026-09-08** — and it
closed with a correction: the mirror was stale in **five** skills, not the two this section
re-verified. Re-verifying the recorded numbers confirmed they were right and did not ask whether the
list was complete; it was not. A diff would have said so in one second, which is the whole argument
for gating it.

### 2. What the plan does not schedule — decided work with no owner

This is the real gap, and it is new since the plan was written. **2026-09-08 produced eight AgentWeave verdicts
that are AgentWeave's, and no stage owns their implementation.** (It produced eleven; two were
another repository's and left with the `OV-` series on 2026-09-08.)

**All nine were re-verified against the code on 2026-09-08** at the operator's instruction — see
`DECISIONS.md`, *"Verification pass"*. **Seven of eight hold; entry 19 does not**, and R-3.2 holds with a side
effect the verdict missed. The `Status` column below reflects that pass, not the verdict alone.

| Work | From | Status after the 2026-09-08 verification | **Built?** (2026-09-10) |
|---|---|---|---|
| Thread F209's `reason` through, or delete the field | R-3 | **HOLDS exactly.** `accept` passes no `reason=`; `reject` three functions away passes it. Unqueued. | **No** |
| **Remove** `PATCH /queue/settings` | R-3 | **HOLDS, with a catch.** Route real, four columns confirmed, no client anywhere — **but it also reschedules every queued agent and the PUT does not.** Drop that knowingly or move it. Unqueued. | **No** — and the 2026-09-09 verdict makes the *order* binding: move the reschedule into the PUT first, then remove |
| A bare `uvicorn hub.main:app` from `hub/` must refuse to start | R-3 | **DOES NOT HOLD.** There is no relative default — fixed `44a1ae5`, 2026-08-17, three weeks before the verdict. **Re-decide narrowed or drop.** | **No** — re-decided narrowed 2026-09-09 (refuse when `DATABASE_URL` is *unset*), still unproposed |
| Model-catalog check as a `scripts/` tool | R-3 | **HOLDS.** No runtime read of `models_cache.json`; compile-time literal, cache 10 days stale. Unqueued. | **YES** — `bb08dc4`: `scripts/check_model_catalog.py` + `tests/test_model_catalog_drift.py` |
| Archive-collision check as a repo script | R-2 | **HOLDS — not built.** Unqueued. | **YES** — `c128019`: `scripts/check_openspec_collisions.py` + `tests/test_openspec_collisions.py` |
| The three R-1 ratchet checks | R-1 | **ALL THREE REPRODUCE EXACTLY** — 35 clientless routes of 187, 51 operator-reachable MISREPORTs, three `fastmcp` ceilings + `starlette<2.0`. Stage 6, unqueued. | **YES** — `6484de4`: `hub/tests/test_surface_ceilings.py` + `test_dependency_ceilings.py`. Note the ceilings **moved before they were frozen**: 187→188 routes and 51→52 MISREPORTs |

**Four of the six were built on the night of 2026-09-09 and this table said otherwise for a day.**
Recorded because the direction is the unusual one: every other staleness this file has caught made
the project look *more blocked than it was*, and so did this — but here the fix was **already on
disk with tests beside it**, and a reader planning work from this table would have queued three
things that exist. **Check `git log` for the row before queueing it**, exactly as the Stage 4
retirements taught.

**A verdict is not an implementation, and this plan has no stage between the two.** That is the
structural hole the audit found, and **it is now half-closed by practice rather than by structure**:
the four built items reached the night window through an `APPROVALS.md` `ORDER:` line naming work
that was *not a change* — the worked example is `APPROVALS.md`'s `## 2026-09-09` four-item block.
That is the missing stage, improvised. **It still has no home in this plan.**

**And the verification proves the hole has a cost**: entry 19 sat
as a decided-and-unbuilt item for a fix that had already shipped three weeks earlier, and nothing
would have caught it before somebody started building.

~~Entry 19 in particular changes whether a command works and needs the scripts relying on the
relative-default database found before it is built.~~ **Withdrawn by the same verification** — there
is no relative-default database to find scripts for. What a narrowed entry 19 would still have to
respect is `CLAUDE.md`'s own documented trial-Hub start command, which *is* a bare
`uvicorn hub.main:app` from `hub/`, with `DATABASE_URL` set explicitly.

### 3. What the plan excludes on purpose — and what that costs

The plan covers **severity A** plus hygiene. `scripts/drive/FINDINGS.md` holds **297 findings** —
49 A, 118 B, 97 C, 20 D, 13 unlabelled. Classified mechanically by their own status lines, with the
negation guard the 2026-09-06 recount learned the hard way (a substring test for `fixed` reads
*"not fixed"* as fixed), and with the section boundaries an adversarial review had to correct.
**119 sections carry no resolution marker at all**, and all but a handful are below severity A.

~~The breakdown that stood here read 41 A, 107 B, 90 C, 20 D — which sums to 258, beside a stated
total of 271.~~ **Struck 2026-09-08.** Neither number was right and the two contradicted each other
inside one sentence; the review that caught it also found the cause.

**Four were sampled at random to find out what that population actually is, because a count of
unclassified rows is not a count of open defects.** All four were real, unfixed, and none is anywhere
in this plan:

- **F237 (B)** — two controls write `Project.token_budget` through different routes and emit
  different events; the one in Settings leaves every surface displaying it stale.
- **F281 (B)** — a shell command's writes are never recorded in any posture; `written_paths` reads
  declared path arguments and a `Bash` call declares none.
- **F222 (B)** — an archived job can be switched back on with one PATCH, and an archived loop then
  works a real task — the state its own docstring calls *"the exact governance failure loops exist to
  make impossible"*.
- **F215 (B)** — the operator's screen says evidence is waiting and gives them nothing to press;
  every route in that row is absent from the served bundle, measured against the bytes.

**So: 4 for 4 real on a random sample of the excluded population.** That does not make all ~147 real
— many will be moot, duplicated, or already fixed without a status line — but it does mean the
excluded set cannot be treated as noise, and **nobody has ever classified it.**

### 4. The answer

**Is the roadmap complete?** As a plan to *drain what is approved and decided*, yes, once §2's
missing stage is added — and Stage 0 being closed means it can start tonight without anything
further from the operator.

**As a plan to a fully functioning AgentWeave, no**, and the gap is §3. ~~Every severity-A defect being
gone is a real milestone and is close: after Stage 2 and one drive, it is **zero**.~~ **Struck
2026-09-10 — Stage 2 shipped and the drive happened, and the count is four, not zero.** Stage 2's
own drives filed three of them. The rest of this answer stands and is sharpened by that: a plan that
priced only the A-list would have declared victory in the week the A-list grew. But a product
whose A-list is empty while ~147 unclassified B/C/D findings sit behind it — four of four sampled
being genuine, including a governance hole and two operator-facing dead ends — is not the same thing
as a product that works.

**The cheapest next move is not to build any of them.** It is to run the classification that has
never been run: bound each of the ~147 sections and record a status line, exactly as the 41
severity-A sections were bounded and scanned on 2026-09-04 and 2026-09-06. That is one window's work,
it is mechanical, and today has already shown three times over what it finds — **F140, F154 and F155
were retired with no code written, because somebody finally looked.** Until that scan exists, the
size of the remaining work is genuinely unknown, and this plan's totals silently assume it is zero.

~~**One caveat on this audit** … treat 147 as an upper bound …~~ **The caveat was justified and the
classification has now been run. 147 was wrong, and so was its replacement: the figure is **119 of 297**.** See below.

---

## The classification, run 2026-09-08 — `scripts/classify_findings.py`

The operator's instruction was *"confirm everything that it needs, double check things."* The
instrument was therefore built, then **attacked until it failed**, then fixed. Full method and error
rates are in `FINDINGS.md`'s third 2026-09-08 revision; this is the result.

**CORRECTED 2026-09-08 after an adversarial review.** The table first published here said 271
findings with 111 unclassified. **Both were wrong.** The instrument could not see 46 headings that
lack a parenthetical, so 26 findings had no section at all and 20 sections silently swallowed the
next finding's text. Fixed; re-run; figures below are the corrected ones.

| Verdict | N | Trust |
|---|---|---|
| `RESOLVED`, strong marker | **108** | **NOT fully trustworthy** — 4 strong-arm verdicts were reading another finding's marker |
| `RESOLVED`, `NOT A DEFECT` prose | **16** | **≥1 known wrong** (F187) |
| `RESOLVED_ELSEWHERE` | **9** | a lead only — hand-check each; several already known false |
| `CONFLICT` | **6** | |
| `OPEN` | **39** | F142 (A); 19 B; 19 C — **includes F77, which no census had ever counted** |
| `UNCLASSIFIED` | **119** | 42 B, 56 C, 15 D, 6 unlabelled — **the real unknown** |
| | **297** | not 271 |

**Do not copy these into `FINDINGS.md`.** That file is the tool's input: the first census was
published *into* it and thereby changed itself — measured, `c18cb6f` differs from `c18cb6f~1` on
four rows for no reason but the prose added between them. Run
`py -3.11 scripts/classify_findings.py` instead.

**Three defects in the instrument, each found by measurement, not review.** Its heading regex
demanded exactly `(A)`…`(D)` and hid **13 sections** — that was the 147→111 step, later superseded when a review found the parenthetical requirement hid 26 findings outright, and it
was found by a count mismatch against `grep`, not by reading the code. Its cross-section arm reused
`Status:`-anchored patterns and so **could not fire at all**, reporting a 0 that read as a result.
And it **read quoted history as current status** — a section withdrawing its own banner *quotes*
that banner, and `stays open` inside the quotation was matched as an assertion.

**The third was found only because a mutation test failed.** Had it passed, the instrument would
have shipped with an inflated open count and nothing would have contradicted it.

**Every error, in all three defects and all four hand-checked false positives, is one failure mode:
a sentence that mentions finding X while resolving finding Y.** Prose is not a status field.

### What it means for this plan

- **The severity-A tail is confirmed by an instrument that did not know today's answer.** F142 open;
  F52/F274/F295 in conflict, all three known and all three accounted for by Stage 0 and Stage 2.
- **119 findings have no resolution language anywhere** and have never been read by anybody. Of six
  since sampled, **four were real and unfixed, one (F281) was not in the population at all, and one
  (F109) was already fixed** by F285's change on 2026-09-04. So the population is neither noise
  nor uniformly live — it is unread, which is a different claim and the only one the evidence
  supports. **Plus F77, open and never counted by any census.**
- **17 more rest on `NOT A DEFECT` prose and 5 on a cross-reference**, and both arms are measurably
  unreliable. Roughly **22 findings currently counted as resolved are not confirmed resolved.**

### The next move, priced

Reading 119 sections is a window's work and needs no decision. It is mechanical, it changes no code,
and today has shown four times over what it produces — F140, F154, F155 retired and 13 sections found
that no census had ever seen. **Until it is done this plan's totals silently assume 119 zeroes**, and
the four that were sampled say that assumption is false.

### Done, part 1 — severity B is read, 2026-09-09 (day D-2)

**All 40 unclassified severity-B sections were read and now carry a machine-readable
`**Status:**` line as their first body line.** The instrument reports **0 unclassified B**, down
from 40; the population moved **38 to open, 2 to fixed**. The 75 that remain are severity C (55),
D (14) and unlabelled (6) — that is D-3's work.

**The sample's implication held, and got stronger.** The block above extrapolated from six sampled
findings that the population was *unread rather than noisy*. Read in full, **38 of 40 are live
defects that nobody had fixed**, and the two exceptions are both already-fixed rows that were never
given a status line:

| | |
|---|---|
| **F109** | fixed `d9ad1e0` by F285's change (2026-09-04). Its own text still said *"the fix is declined"* — a decision the operator **reversed** when CI forced it. `hub/tests/conftest.py:22-36` names F285 and the same three candidates F109 measured. |
| **F159** | fixed `eeab0d3` (2026-09-01) **in the change that introduced it** — it never shipped as a defect. Verified: `hub/hub/task_workspace.py:239-240` scopes the `approved` filter to `not evidence_governs`, guarded by two tests. |

**So the plan's totals were assuming zeroes for 38 real B defects.** No new severity-A or -B work is
created by this — every one of the 38 was already filed, most with a reproduction — but the count
this plan is priced against was wrong in the direction the sample predicted.

**Three things the full read found that sampling could not.** Sampling asks *is it real*; reading
asks *what is it now*, and four sections answered neither open nor fixed cleanly:

- **F119 and F138 are halves.** Each shipped one half of its repair and left a named residual.
  F119's Hub copy was deduplicated (`scheduler.py:57` calls `redact_secrets`) and the CLI's broad
  rule stands on an unanswered operator question. F138's three hard-wired harnesses were fixed in
  the filing commit and `aw.py`'s `KEY` default went on 2026-09-07 — but `HUB` still defaults to
  `8010`, the one instance a drive must not disturb. Both read `open`, and both are cheaper than
  the label suggests.
- **F259's headline is struck and its substance survives.** The 2026-09-02 amendment withdrew the
  consequence (`StatusBar.tsx` is in no bundle, so no operator sees the chip) without withdrawing
  the finding, which lands instead on F264. An entry can be wrong about its own harm and still be
  a defect.
- **F264 is half-driven.** Its code half is established; its live pass **fired the branch and did
  not reproduce the leak**, and it names the drive still owed. `open` overstates it; `unverified`
  would be the honest fourth verdict, and the instrument has no such bucket.

**Six statuses rest on a fresh code check rather than on the ledger**, taken 2026-09-09 and stated
at the line: F109 (conftest), F111 (`POST /agents/register` still live at `agents.py:2144`), F119
(`scheduler.py:57`), F129 (no `drift/detect` reference anywhere in `hub/ui/src`), F138 (`aw.py:18`),
F159 (`task_workspace.py:239-240`), and F178 — where the check **sharpened the finding**:
`useAgentLaunchability` has *no non-test caller* in `hub/ui/src`, so the report reaches no screen
and three `__tests__` files mock a hook no component renders.

**What produced the lines:** `scripts/drive/_d2_write_status.py`, kept so D-3 extends the same list
rather than inventing a second format. It refuses to write where a `**Status:**` line already leads
a section, so re-running it is a no-op rather than a duplicate. The classification in each line was
made by reading the section and its cross-references — openspec changes, `spec-queue/DECISIONS.md`,
the git log — not by the script.

**One collateral defect, found and fixed inside this task.** The first draft of F111's status line
put the word *"closed"* on the same line as a reference to `F3`, and F3 immediately flipped from
`OPEN` to `CONFLICT` — the cross-section arm reading a sentence about F111 as a resolution of F3.
That is precisely the failure mode `classify_findings.py`'s own header calls *the single failure
mode behind every error*: a sentence that mentions finding X while resolving finding Y. **Writing
into the ledger can corrupt the ledger's own census, and the only reason this was caught is that
every non-B bucket was diffed against the pre-edit run.** Do the same in D-3.

### Done, part 2 — C, D and the unlabelled are read, 2026-09-09 (day D-3)

**The ledger now reports `UNCLASSIFIED: 0`.** The remaining 75 sections — severity C (55), D (14)
and the 6 carrying no severity label — were read and given a machine-readable `**Status:**` line as
their first body line. **67 are open, 8 were already answered.** Nothing moved that was not touched:
every bucket was set-diffed against the pre-edit run by finding number, and 302 sections exist before
and after.

| | C | D | ? | total |
|---|---|---|---|---|
| **open** | 51 | 14 | 2 | **67** |
| **resolved** | 4 | 0 | 4 | **8** |

Whole-ledger position after both parts: **144 open, 143 resolved, 9 conflict, 6 resolved-elsewhere**,
across 302 sections.

**The C/D population is not the B population.** Part 1 found 95 % of severity B live, and the honest
summary of the low-severity half is different in two ways worth pricing.

- **89 % is live (67 of 75)** — a lower proportion than B, but the eight exceptions are all
  *records*, not repairs anybody owes.
- **35 of the 75 are named nowhere outside `FINDINGS.md`** — measured by a cross-reference sweep over
  `openspec/`, `spec-queue/`, `hub/`, `src/`, `scripts/` and `tests/`. These are the ones for which
  the ledger is the only copy.

### The eight that were already answered, and why no census had counted them

Four kinds, and only one of them is an ordinary repair:

| | |
|---|---|
| **F270** | fixed `3b1b8f0` by `a-turn-says-how-it-ended` task 2.2 — **the side effect the entry itself predicted**. The finalize block now persists the terminal `phase="completed"` row for every run on either runner, so the client's first settled signal is no longer Claude-only. |
| **F280** | fixed `c063e28` in the iteration that filed it; the agent's recording response carries `footprint` through the shared `footprint_view`. Named nowhere outside the ledger. |
| **F66**, **F131** | fixed 2026-08-30 by `every-run-knows-its-task` (`f5b46e9`) and `continue-starts-what-it-names` (`5958200`). Both were verified in code today rather than taken from their own prose. |
| **F137**, **F144**, **F145**, **F148** | **not product defects at all** — drive-harness records, each repaired in its filing commit. F145's is the sharpest: it was written expecting a hard Hub kill to orphan the CLI, and measured the opposite twice. |

That last row is a species the census had no name for. Four of the 75 were never claims about the
product, and counting them as unknown defects overstated the backlog by exactly as much as leaving
the eight uncounted understated the progress.

### The instrument cannot read the ledger's own strongest verdicts

**Two of the four already-fixed sections said so in their first body line and were still
`UNCLASSIFIED`.** `## F131` opens `**FIXED 2026-08-30**` and `## F66` opens
`**Status:** **closed 2026-08-30`. Neither matches: the strong pattern requires the literal
`Status:` before `FIXED`, and `closed` is in-section vocabulary nowhere — it is only recognised
*across* sections, which is exactly the arm the instrument's header says to treat as a lead.

This is not a defect in the verdicts (both were read by hand and are now correct); it is a
measurement of the gap between the ledger's prose and the instrument's vocabulary. Deliberately not
fixed inside this task: widening `STRONG_PAT` moves verdicts, and moving verdicts in the same pass
that writes 75 of them would make the bucket diff — the only thing that catches a self-inflicted
re-verdict — unreadable. Candidate for the instrument's next round, with the same
mutation-check discipline the seven existing guards got.

### Not "unread" — a decided-and-dropped tail

Severity C is where the plan's remedies go to be forgotten. Six of the 51 open C findings already
have a remedy chosen in writing and no implementation behind it: **F181** (`DECISIONS.md:536`,
*"already answered by something already written down"*, paired there with the severity-B F185),
**F195** and **F201**
(`:263-264`, sized at ~8 and 9 sites, with `:545` deciding the narrow repair and the sweep should
ship together), **F198** (`:825`, *remove the route*), **F209** (`:820` and `ROADMAP.md:337`, whose
R-3.1 re-check records *HOLDS, exactly*) and **F212** (`:527`). Reading the population does not
create work for these; it reveals that the decision was the easy half.

### Method notes

- **41 of the 67 open verdicts rest on a code check taken 2026-09-09**, stated at the line and
  citing file and line. The rest rest on the ledger plus the cross-reference sweep, and say so.
- **The placer now refuses to write a line that names another finding beside a resolution word.**
  That is D-2's collateral defect — F3 flipped `OPEN → CONFLICT` off one word in F111's new line —
  turned into a guard instead of a habit. It did not fire on this batch; the bucket diff was taken
  anyway, because a guard that has never fired has not been shown to work.
- **`NOT A DEFECT` is now a declaration as well as a phrase.** Four of the instrument's 25 verdicts
  on that weak marker are deliberate first-line declarations rather than prose it happened to match,
  which makes that count mean slightly less than it did — the arm still cannot tell the two apart.
- Counts live here. `FINDINGS.md` is the instrument's input, and publishing a census into it changes
  the census.
