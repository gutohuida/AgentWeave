# Roadmap — finish what is open, start nothing new

**Written 2026-09-07 by a DECIDE session, at the operator's instruction: *"a plan for nothing new
but to finish everything that we have open."*** Inventory measured against the tree at `af329f5`,
not copied from handoffs — several figures the chain was carrying forward were wrong.

This file is a **plan**, not an authority. It cannot approve a change or decide a rule: those are
`APPROVALS.md` and `DECISIONS.md`, and the tokens there remain the only authority. Where this plan
says "the operator writes a verdict", it is describing work, not performing it.

---

## The one fact that reorders everything

**The pipeline is not starved of building capacity. It is starved of verdicts.**

Four changes are fully specced — three review rounds each, every round non-empty — and **not one
carries an approval token.** The FIX window builds roughly one change a night and has been handed
nothing to build. The queue did not grow because building is slow; it grew because the DECIDE step
between the two windows has not run since 2026-09-06.

**And it is about to grow again.** `AgentWeaveArmDay` is `Ready` and fires at **08:55 tomorrow**.
`DIRECTION.md`'s newest section is dated 2026-09-07, so tomorrow has none — and the contract says
*"no section for today means compose the queue as usual"*. The default day queue is
`D-2/D-3/D-4 = spec R1/R2/R3`, which is **one new proposal**. Left alone, the day window adds a
fifth change tomorrow morning.

That is the arithmetic behind everything below. FILL produces one change per day. FIX consumes one
change per one-to-two nights. **The two windows are structurally mismatched, and no amount of
discipline closes a gap that is a rate difference.** Finishing what is open requires the day window
to stop proposing for the duration — not to try harder.

---

## Stage 0 — tonight, before 08:55 (operator, ~40 minutes)

Nothing below this line can move until these are done, and item 1 expires in the morning.

| # | Action | File |
|---|---|---|
| **0.1** | ~~Write a `## 2026-09-08` section redirecting the day window off the spec loop.~~ **DONE 2026-09-08 00:35.** The section is written: no spec loop, D-1/D-2 take F292, D-3 takes hygiene. Confirmed the night of 2026-09-07 built nothing — `AgentWeaveArmNight` was disabled and there is no `2026-09-07-night-log.md` — so there was nothing to drive either. **Superseded 2026-09-08 01:40 by a standing gate** — the dated section covers one day and expired at midnight; `.claude/loops/day-window.md` step 6 now counts unbuilt specced changes and runs no spec loop at 2 or more. | `spec-queue/DIRECTION.md`, `.claude/loops/day-window.md` |
| **0.2** | ~~Write four verdict tokens.~~ **DONE 2026-09-08 — all four APPROVED** by the operator in session, after three review rounds. All four rows are restated under `## 2026-09-08` because only the newest dated section is read. | `spec-queue/APPROVALS.md` |
| **0.3** | **Write the `ORDER:` line.** ~~Three of the four touch `hub/ui` and the committed bundle… Only one is bundle-free.~~ **Corrected by the second review, 2026-09-08: two are bundle-free, not one.** `an-agent-without-mcp` names no `hub/ui` file anywhere and declares its own exemption at its `tasks.md:7`; `a-dead-connection` is Python-only. Only the two UI changes touch the bundle, and they share **no source file** — their sole collision is the generated `hub/hub/static/ui`. | `spec-queue/APPROVALS.md` |
| **0.4** | ~~Decide the night arm — the only thing between the approvals and a build.~~ **RESOLVED — measured 2026-09-08 10:05: `AgentWeaveArmNight` is `Ready`, not disabled**, `LastTaskResult=0`, last fired 2026-09-06 22:55, **next 2026-09-08 22:55.** So Stage 0 is closed in all four rows and **tonight is the first build night** the four approvals have ever had. The roadmap carried this as the single blocker for a day after it had stopped being one. | Task Scheduler |

### The four changes awaiting a token

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
passed. Every change in Stage 2 will be verified by a suite that is wrong roughly half the time.

Related and probably the same class: **F279** (the two "a stopped run" tests fail about half the
time on an unmodified tree).

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

## Stage 5 — the two orphan repositories

Both live outside this checkout, both have **no remote**, both exist on exactly one disk.

**`continuity-kit`** — 7 commits, an unvalidated prototype by its own README, and the only item in
the whole inventory with no downside. Give it a remote and push it.

*Price it honestly first.* This repo's own cross-agent port of the same contract already drifted:
`.agents/skills/` and `~/.codex/skills/` carry `handoff` and `resume` copies that are 73 and 9 lines
behind and mention `DEAD-ENDS.md` **zero** times — they predate the ledger entirely. The claim to
ship is "a file contract two agents can read", and the evidence on this disk is that keeping two
agents in sync needs a check nobody wrote — **written 2026-09-08**, `tests/test_skill_sync.py`;
see Stage 6.1, and note it found three more drifted skills than this paragraph names.

**`witness`** — 4 commits. **OV-1 is DECIDED: yes, 2026-09-08, operator in session**
(`DECISIONS.md`). It is no longer blocked, and OV-2…OV-6 — downstream of it, and moot had the answer
been no — are now live decisions. Its phase 6 (W-2, W-3, W-6) is real work and may start.

~~**The deadline is closed; the loss is not.** … the corpus keeps rolling off … until something is
built or a snapshot is taken. A snapshot-first framing was offered and declined.~~

**Superseded 2026-09-08 — the snapshot was built the same day, and the roll-off has stopped.**
`scripts/snapshot-corpus.ps1` plus a `ClaudeCorpusSnapshot` scheduled task, daily 12:30, verified
from the scheduler (`LastTaskResult=0`) and not only by hand. The full path-by-path
`Compare-Object` matched **2,598 = 2,598 files, identical total bytes, zero missing.** So the ~29-day
cliff is no longer live: what has already been lost (≥51 sessions evidenced by committed handoffs)
stays lost, but nothing new rolls off. This came out of **OV-6 + OV-3**, which split retention *out*
of Witness rather than choosing between two shapes of it.

**And every OV is now decided** (`DECISIONS.md`, 2026-09-08): OV-1 yes, OV-2 redact at write, OV-4
the operator only, OV-6+OV-3 split. **OV-5 — does the name `witness` survive a collision check? — is
the only one still open**, and it is blocked on a web search nobody has run, not on a judgement.

**What this stage still owes.** OV-2's *redact at write* and OV-6's *batch reader* are verdicts with
no implementation, and no stage schedules them either. Witness phase 6 (W-2, W-3, W-6) is real work
and may start; it has not.

**Two signals to watch on the snapshot, both currently expected-but-unproven.**
`kept_beyond_source` is **0** and will stay 0 until the corpus ages past the window — correct today,
a **failure signal** later. And **the restore path has never been exercised**: copying was verified,
reading a transcript back out of the archive was not.

---

## Stage 6 — hygiene (one window; every item is small)

| # | Item | Detail |
|---|---|---|
| **6.1** | ~~Run `scripts/sync_skills.py`, then gate it.~~ **DONE — 2026-09-08, day window iteration 7.** Synced; gated by `tests/test_skill_sync.py`, mutation-checked against four deliberately-stale shapes. **The staleness was wider than this row said:** five skills differed, not two — `autonomous-prep`, `autonomous-session` and `e2e-loop` (`install-driver.ps1` 230→182, `run-iteration.ps1` 266→181, `e2e.py` 411→385) drifted alongside `handoff` and `resume`, and the two `.ps1` files are the autonomous driver itself. The row's own numbers were right; its *inventory* was not, because it was assembled from what a reader noticed rather than from a diff. The gate now does the diffing. Two sub-findings: the sync copied `__pycache__` (fixed, `IGNORED` in the script), and the gate **skips** a destination it cannot find — both trees are untracked and absent on a CI runner, so it ratchets developer machines, not CI. |
| **6.2** | ~~`scripts/drive/aw.py:16` promises a guard that does not exist.~~ **DONE — 2026-09-08, day window iteration 8.** The guard was added rather than the comment weakened. `require_key()` raises `SystemExit` — deliberately not `RuntimeError`, because this directory is full of bare `except Exception` and `api()` swallows one into `(0, "...")`. Measured against the live Hub on 8010: HEAD's code with `AW_KEY` unset returned **401 with exit code 0**; the guard fails locally with exit 1 and a urlopen tripwire proves no request reaches the network. The 200 and the real-401 paths are unchanged. Gated by `tests/test_drive_key_guard.py`, mutation-checked against three defects (the HEAD file; a reintroduced key literal; a blanket refusal) — and one mutation it deliberately does **not** catch, recorded in the test. **Wider than this row said:** the same file family carried the key-literal defect 6.3 describes, and the fix removed all of it — see 6.3. |
| **6.3** | ~~Rotate the disclosed `aw_live_` key.~~ **DONE — the operator rotated it, stated in session 2026-09-08 09:20.** Closes the day window's `day1` question (*"may the loop rotate keys itself?"*), which is now moot for this key and was never answered in the general case. **Residual, largely cleared 2026-09-08 by 6.2:** the classification found 18 real-shaped 32-character `aw_live_` literals in **16 tracked files**. The nine `scripts/drive/` scripts among them (this row said eight; the test counts nine) now call `require_key()` instead of defaulting a key, and `tests/test_drive_key_guard.py` fails if one comes back — **10 literals in 8 files remain**, all outside `scripts/drive/` except `FINDINGS.md`'s own transcript: the documented `a1b2c3…` placeholder (`hub/.env.example`, `hub/hub/db/engine.py`, `hub/tests/test_setup.py`), the redaction fixtures in `hub/tests/test_operator_is_told_the_truth.py` that exist *because* the key leaked, and four historical documents. All are dead against a rotated key. What is not dead is the practice that produced them; a rotation is final only if nothing commits a live key again. Classified by shape without printing any value. |
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
| 5 | Operator | ~15 min (`continuity-kit`); **`OV-1` decided 2026-09-08**, `OV-2`…`OV-6` now live |
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
  behind the continuity kit, not an overseer beyond what `witness` already is.
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
**6.1 closed 2026-09-08** — and it
closed with a correction: the mirror was stale in **five** skills, not the two this section
re-verified. Re-verifying the recorded numbers confirmed they were right and did not ask whether the
list was complete; it was not. A diff would have said so in one second, which is the whole argument
for gating it.

### 2. What the plan does not schedule — decided work with no owner

This is the real gap, and it is new since the plan was written. **2026-09-08 produced eleven verdicts
and no stage owns their implementation.**

| Work | From | Status |
|---|---|---|
| Thread F209's `reason` through, or delete the field | R-3 | decided, unqueued |
| **Remove** `PATCH /queue/settings` | R-3 | decided, unqueued |
| A bare `uvicorn hub.main:app` from `hub/` must refuse to start | R-3 | decided, unqueued |
| Model-catalog check as a `scripts/` tool | R-3 | decided, unqueued |
| Archive-collision check as a repo script | R-2 | decided, unqueued |
| Redact-at-write | OV-2 | decided, unqueued |
| Witness as a batch reader (phase 6: W-2, W-3, W-6) | OV-6 + OV-3 | decided, unqueued |
| The three R-1 ratchet checks | R-1 | decided, named Stage 6 work, unqueued |

**A verdict is not an implementation, and this plan has no stage between the two.** That is the
structural hole the audit found. Entry 19 in particular changes whether a command works and needs the
scripts relying on the relative-default database found *before* it is built.

### 3. What the plan excludes on purpose — and what that costs

The plan covers **severity A** plus hygiene. `scripts/drive/FINDINGS.md` holds **271 findings**: 41
A, 107 B, 90 C, 20 D. Classified mechanically by their own status lines — with the negation guard the
2026-09-06 recount learned the hard way, since a substring test for `fixed` reads *"not fixed"* as
fixed — **roughly 147 sections below severity A carry no resolution marker at all.**

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
classification has now been run. 147 was wrong; the figure is 111.** See below.

---

## The classification, run 2026-09-08 — `scripts/classify_findings.py`

The operator's instruction was *"confirm everything that it needs, double check things."* The
instrument was therefore built, then **attacked until it failed**, then fixed. Full method and error
rates are in `FINDINGS.md`'s third 2026-09-08 revision; this is the result.

| Verdict | N | Trust |
|---|---|---|
| `RESOLVED`, strong marker | **97** | 9 of 9 sampled correct |
| `RESOLVED`, `NOT A DEFECT` prose | **17** | **≥1 known wrong** (F187) |
| `RESOLVED_ELSEWHERE` | **5** | **3 of 5 hand-checked FALSE** — a lead only |
| `CONFLICT` | **5** | F52, F274, F295 (A); F273, F292 (B) |
| `OPEN` | **36** | F142 (A); 18 B; 17 C |
| `UNCLASSIFIED` | **111** | 41 B, 56 C, 14 D — **the real unknown** |
| | **271** | |

**Three defects in the instrument, each found by measurement, not review.** Its heading regex
demanded exactly `(A)`…`(D)` and hid **13 sections** — that is the whole 147→111 correction, and it
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
- **111 findings have no resolution language anywhere** and have never been read by anybody. Four
  sampled at random were four-for-four real. That is not a projection onto 111; it is a statement
  that the population cannot be assumed empty.
- **17 more rest on `NOT A DEFECT` prose and 5 on a cross-reference**, and both arms are measurably
  unreliable. Roughly **22 findings currently counted as resolved are not confirmed resolved.**

### The next move, priced

Reading 111 sections is a window's work and needs no decision. It is mechanical, it changes no code,
and today has shown four times over what it produces — F140, F154, F155 retired and 13 sections found
that no census had ever seen. **Until it is done this plan's totals silently assume 111 zeroes**, and
the four that were sampled say that assumption is false.
