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
| **0.1** | ~~Write a `## 2026-09-08` section redirecting the day window off the spec loop.~~ **DONE 2026-09-08 00:35.** The section is written: no spec loop, D-1/D-2 take F292, D-3 takes hygiene. Confirmed the night of 2026-09-07 built nothing — `AgentWeaveArmNight` was disabled and there is no `2026-09-07-night-log.md` — so there was nothing to drive either. | `spec-queue/DIRECTION.md` |
| **0.2** | ~~Write four verdict tokens.~~ **DONE 2026-09-08 — all four APPROVED** by the operator in session, after three review rounds. All four rows are restated under `## 2026-09-08` because only the newest dated section is read. | `spec-queue/APPROVALS.md` |
| **0.3** | **Write the `ORDER:` line.** ~~Three of the four touch `hub/ui` and the committed bundle… Only one is bundle-free.~~ **Corrected by the second review, 2026-09-08: two are bundle-free, not one.** `an-agent-without-mcp` names no `hub/ui` file anywhere and declares its own exemption at its `tasks.md:7`; `a-dead-connection` is Python-only. Only the two UI changes touch the bundle, and they share **no source file** — their sole collision is the generated `hub/hub/static/ui`. | `spec-queue/APPROVALS.md` |
| **0.4** | **Decide the night arm — STILL OPEN, and it is now the only thing between the approvals and a build.** `Enable-ScheduledTask -TaskName AgentWeaveArmNight` (fires 22:55) or leave it off. It is **DISABLED**, so as things stand the four approved changes sit unbuilt. | Task Scheduler |

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

Still open, both small, both a week old: **R-2** (should `openspec archive` refuse a colliding
delta — a tooling call) and **R-3** (four small product calls, each closable in a sentence).

---

## Stage 4 — the severity-A tail (after R-1, because R-1 may absorb some of it)

| Finding | What it actually needs |
|---|---|
| **F52** | **Close it — bookkeeping only.** Its operator-visibility half shipped (`68459ea`), `0cda570` disproved its central inference, and `57eb92b` drove a full live turn that committed. Its own row says a new git refusal would be a *new* finding. It is counted as open because nobody retired it. |
| **F140 + F142** | **One decision, not two.** F142 changes which of F140's two defensible repairs is worth building, so deciding F140 alone produces the wrong answer. Operator call → one spec loop → one build. |
| **F60** | Fix already chosen by the operator, not implemented, and **blocked on F14's task-state half**, which is itself an undecided fix shape. Decide F14 or F60 cannot start. |
| **F274, F295** | Already specced — they are Stage 2. |

After F52 is retired and F274/F295 are built, the open severity-A count goes from six to two
(F140/F142 as one, F60), both blocked on operator decisions rather than on work.

---

## Stage 5 — the two orphan repositories

Both live outside this checkout, both have **no remote**, both exist on exactly one disk.

**`continuity-kit`** — 7 commits, an unvalidated prototype by its own README, and the only item in
the whole inventory with no downside. Give it a remote and push it.

*Price it honestly first.* This repo's own cross-agent port of the same contract already drifted:
`.agents/skills/` and `~/.codex/skills/` carry `handoff` and `resume` copies that are 73 and 9 lines
behind and mention `DEAD-ENDS.md` **zero** times — they predate the ledger entirely. The claim to
ship is "a file contract two agents can read", and the evidence on this disk is that keeping two
agents in sync needs a check nobody wrote. See Stage 6.1.

**`witness`** — 4 commits, blocked entirely on **OV-1** (*may Witness read the local Claude Code
transcript corpus at all?*). OV-2…OV-6 are all downstream of it; if OV-1 is "no", the other five are
moot.

**This one is time-sensitive.** The corpus rolls off on a measured ~29-day window with a hard cliff
— 2,084 files, oldest 2026-08-09 — while ≥51 earlier sessions are evidenced by committed handoffs
and already gone. **Answer OV-1 this week or shelve `witness` explicitly.** Carrying it open costs
data every day. Its phase 6 (W-2, W-3, W-6) is real work but none of it starts before OV-1.

---

## Stage 6 — hygiene (one window; every item is small)

| # | Item | Detail |
|---|---|---|
| **6.1** | **Run `scripts/sync_skills.py`, then gate it.** Last run immediately before `a38caee` — the commit that introduced the ledger. Stale: `handoff` (341→268), `resume` (127→118), `daily-review` (absent). It is a hand-run mirror with no check; a ~15-line test diffing the trees would have caught this on 2026-09-04. |
| **6.2** | **`scripts/drive/aw.py:16` promises a guard that does not exist.** The comment says *"an unset key fails loudly below"*. It does not — `KEY` is empty-string-defaulted and used directly as `"Bearer " + KEY`, which yields a 401 from the Hub, not a local failure. Add the check or fix the comment. |
| **6.3** | **Rotate the disclosed `aw_live_` key.** It is in public git history. Carried unaddressed across several handoffs. |
| **6.4** | **`.claude/handoffs/LATEST.md` names the wrong handoff** — it does not point at `handoff-0113`. Found by continuity-kit's own checker. |

The 35 client-less routes are **not** listed here on purpose: they are R-1's evidence, and picking
them off one at a time is exactly the behaviour R-1 exists to decide about.

---

## Honest arithmetic

| Stage | Whose time | Cost |
|---|---|---|
| 0 | Operator | ~40 min, **expires 08:55 tomorrow** |
| 1 | One night | 1 window |
| 2 | Nights | 5–6 windows |
| 3 | Operator | ~1 hour, resizes everything after it |
| 4 | Operator + nights | 1 decision + ~2 changes |
| 5 | Operator | ~15 min (`continuity-kit`) + 1 decision (`OV-1`, **this week**) |
| 6 | One window | 1 window |

**Total, if R-1 answers "enforce": roughly three to four weeks of nights.**
**If R-1 answers "repair": roughly eight to ten.**

Both numbers assume the day window stops producing new changes. **If it does not, the backlog grows
faster than it drains and neither number is real** — that is Stage 0.1, and it is why 0.1 is first.

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
