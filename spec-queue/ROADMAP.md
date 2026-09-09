# Roadmap — finish what is open, start nothing new

**Written 2026-09-07 by a DECIDE session, at the operator's instruction: *"a plan for nothing new
but to finish everything that we have open."*** Inventory measured against the tree at `af329f5`,
not copied from handoffs — several figures the chain was carrying forward were wrong.

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

## Stage 1 — repair the instrument first (1 night)

**F292 — `sqlite3.OperationalError: database is locked`.** This is not a backlog item; it is
actively lying to every verification below it. It **failed CI on `master` at `15ce482` today at
22:03**, in `hub-test`, and the next commit `af329f5` — the same tree plus one markdown file —
passed. ~~Every change in Stage 2 will be verified by a suite that is wrong roughly half the
time.~~ **Corrected 2026-09-08 by measurement — the rate is 20.4 %, not half**, and "half" was
F279's *local* rate borrowed for F292's *CI* rate. Measured over 54 runs since 2026-09-07T00:00Z,
every failure classified individually from its own log rather than counted as red: **11 failures,
all F292, 20.4 %**; `master`-only over the last 20 runs, 25 %. The sharper number is that in that
window **every red CI run is F292 — 11 of 11**, so CI redness on this project currently has
exactly one cause. Method, three denominators and the 22-occurrence table are in `FINDINGS.md`'s
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
"did `a-dead-connection` fix F292?" as a measurement to make, not an outcome to expect.

---

## Stage 2 — build the four approved changes (5–6 nights)

One change per night, in the `ORDER:` line's sequence. The 44-task change is likely two nights.

Nothing in this stage needs a new decision. Each change has been through three rounds, and on the
last six outings not one round was a no-op — so these are the most-verified artifacts in the repo.

**The rule that matters here:** never mark a task complete on the strength of the plan existing.
And a UI change is not finished until `npm run build` and `make ui` have run and the bundle is
committed beside `hub/ui/src`.

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

## Stage 4 — the severity-A tail (after R-1, because R-1 may absorb some of it)

| Finding | What it actually needs |
|---|---|
| **F52** | **Close it — bookkeeping only.** Its operator-visibility half shipped (`68459ea`), `0cda570` disproved its central inference, and `57eb92b` drove a full live turn that committed. Its own row says a new git refusal would be a *new* finding. It is counted as open because nobody retired it. |
| **F140** | ~~One decision with F142, not two.~~ **RETIRED 2026-09-08 — there was no decision here.** Repair 1 shipped `1b4c730` (2026-08-30) and was **driven live 2026-08-31**: both Haiku agents made the `update_task(..., status="completed")` call unprompted, both tasks reached `approved`, both commits verified ancestors of `master`. `_briefing_completion_lines` is byte-identical to the driven version, re-measured this session. The 2026-09-03 banner asked for a re-drive that already existed in `FINDINGS.md` two days earlier. |
| **F142** | **Not an operator decision — a missing drive.** Its fix shipped `f3a778f` (2026-08-31): the bare `continue` is now three named arms and the operator-completed task is routed for review. Its own change document says group 7 was *"written, compiled, and **not driven**"* and deferred it to `DRIVE-1`, which has not happened. **Queue one drive**: `t_row12_review_leg.py` with `AW_COMPLETE_BY=operator` must reach a staffed review, plus its uncovered row four (the operator completes a task no agent ever touched). `F167` (B) is a known residual on the adjacent `wedged_review` path and does not reopen this. |
| **F14, F60** | ~~F60 not implemented, blocked on F14's undecided fix shape.~~ **Both `FIXED 2026-08-30`**, shipped together in `a-task-waits-while-its-run-waits`, and `FINDINGS.md` has said so since. Verified in code 2026-09-08: ask-time parking at `agent_actions.py:509-514`, `Question.wait_ended_at` at `models.py:1001`, migration `0099`, drive harness `t_f14_f60_wait_parks_the_task.py`. This table was simply wrong. |
| **F154** | ~~Archived change, never driven.~~ **RETIRED 2026-09-08 — the drive existed.** Fix `001a07d` (2026-08-31), driven the same day: `t_f154_wedged_review.py`, **18/18** on both the reviewer-wedged and author-wedged populations, re-driven 18/18 later. `run_task_binding.py` and `scheduler.py` are byte-identical `001a07d`→`HEAD`. |
| **F155** | ~~Archived change, never driven.~~ **RETIRED 2026-09-08 — the drive existed.** Fix `0373867` (2026-08-31), driven the same day: `t_f155_conflict_remedy.py`, **23/23**, the harness parsing the branch out of the refusal's own sentence, with the falsifying lane run deliberately. `requirement_gate.py` is byte-identical `0373867`→`HEAD`. Its drive filed **F165 (B)** and **F166 (C)**, which stay open. |
| **F274, F295** | Already specced — they are Stage 2. |

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
existed. So the open severity-A tail after F52 is retired and F274/F295 are built is **F142 alone** —
one finding, blocked on one drive, with no operator decision anywhere in it.

**The arithmetic of this one day is the point.** The severity-A count went **six → five → three**
without a single line of product code being written. Every one of those retirements was a document
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

| Stage | Whose time | Cost |
|---|---|---|
| 0 | Operator | **done 2026-09-08 01:30** |
| 1 | One night | 1 window |
| 2 | Nights | 5–6 windows |
| 3 | Operator | ~1 hour, resizes everything after it |
| 4 | Nights | **~1 drive.** No operator decision — F140/F154/F155 all retired 2026-09-08 on drives that already existed, leaving F142 alone |
| 5 | — | **REMOVED 2026-09-08** — it scheduled work in two other repositories. Not this plan's. |
| 6 | One window | 1 window |

**Total, if R-1 answers "enforce": roughly three to four weeks of nights.** R-1 answered *enforce*
(2026-09-08 00:30), so this is the live number.

Both numbers assume the day window stops producing new changes. **That assumption is now enforced by
the playbook rather than by an operator remembering**: `.claude/loops/day-window.md` step 6 counts
unbuilt specced changes and runs no spec loop at 2 or more, releasing itself when the nights catch
up (decided 2026-09-08, `DECISIONS.md`). Stage 0.1's dated `DIRECTION.md` section covered 2026-09-08
only and expired at midnight; the gate is what carries it from 2026-09-09 on.

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

| Work | From | Status after the 2026-09-08 verification |
|---|---|---|
| Thread F209's `reason` through, or delete the field | R-3 | **HOLDS exactly.** `accept` passes no `reason=`; `reject` three functions away passes it. Unqueued. |
| **Remove** `PATCH /queue/settings` | R-3 | **HOLDS, with a catch.** Route real, four columns confirmed, no client anywhere — **but it also reschedules every queued agent and the PUT does not.** Drop that knowingly or move it. Unqueued. |
| A bare `uvicorn hub.main:app` from `hub/` must refuse to start | R-3 | **DOES NOT HOLD.** There is no relative default — fixed `44a1ae5`, 2026-08-17, three weeks before the verdict. **Re-decide narrowed or drop.** |
| Model-catalog check as a `scripts/` tool | R-3 | **HOLDS.** No runtime read of `models_cache.json`; compile-time literal, cache 10 days stale. Unqueued. |
| Archive-collision check as a repo script | R-2 | **HOLDS — not built.** Unqueued. |
| The three R-1 ratchet checks | R-1 | **ALL THREE REPRODUCE EXACTLY** — 35 clientless routes of 187, 51 operator-reachable MISREPORTs, three `fastmcp` ceilings + `starlette<2.0`. Stage 6, unqueued. |

**A verdict is not an implementation, and this plan has no stage between the two.** That is the
structural hole the audit found. **And the verification proves the hole has a cost**: entry 19 sat
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

**As a plan to a fully functioning AgentWeave, no**, and the gap is §3. Every severity-A defect being
gone is a real milestone and is close: after Stage 2 and one drive, it is **zero**. But a product
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
