# Autonomous run — the flow lands its work

**Branch:** `autonomous/2026-08-31-the-flow-lands-its-work`, cut from `master` at `3a274a2`
**Stop:** 2026-08-31T08:00:00+01:00 · **Runner:** claude (Opus 5) · **Posture:**
`unattended-full-access`

Newest entry at the **bottom**.

---

## Iteration 0 — 2026-08-30 22:45–23:05 (+01:00) — preparation, operator awake

### The operator's instruction, verbatim

> do an autonomos run untill 8AM. Drive everything untill you solve all the issues with the flow
> and things are wortking. Fix what you already know it's broken then test the flow fix again and
> go on untill done

Preceded, in the same session, by: *"Okay let's run a explore on who to fix once and for all the
flow. Let's explore the code base what we know that is wrong... potential fixes once and for all.
I want to get this done on the flow."*

So the target is not a list of findings closed. It is **a flow that lands its work, proven by
driving it.**

### What was done while the operator was awake

**A deep exploration of the flow machinery**, four parallel readers plus direct verification, now
committed as `openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md` (`3a274a2`).
This is the single most valuable thing in this run's inputs: it names seven breaks with
`file:line`, establishes which shipped requirements they breach, and records the traps. **Read it
first, every iteration.** Nothing in it needs re-deriving.

Its headline: *the flow's definition of "done" is the task lifecycle's definition of "decided", and
those are not the same thing.* `hub/hub/scheduler.py` contains **zero** references to integration,
so the module that decides a flow is finished has never heard of the module that decides whether
work landed.

**Two operator decisions were taken** rather than left for the run to guess:

- **D-A — approval is REFUSED while evidence sits unaccepted.** Chosen over seeding a granted agent
  per project, over a flow granting its own resolved reviewer, and over leaving the machinery alone
  while surfacing "approved but unmerged" (that last was rejected because it leaves
  `task-lifecycle-governance:638` breached). The consequence is deliberate: a default project's
  first flow will **stall loudly** instead of finishing silently wrong.
- **D-B — a loop declares at creation whether its work needs evidence.** This was not one of the
  four options offered; the operator wrote it themselves. It makes loops a real working mode rather
  than a structural dead end.

### The stall hunt

| Category | Found | Removed |
|---|---|---|
| Operator decisions | 2 blocking (evidence acceptance; what a loop is) | Both asked and answered before arming |
| Missing artifacts | The whole analysis existed only in a chat session | Written to `openspec/explorations/` and committed |
| Environment | 8010 and 8011 both healthy; `claude` on PATH; py 3.11.9 | Verified, not assumed. **8011 serves whatever code it was started from — the run must restart it from the branch before trusting a drive.** |
| Unstated constraints | — | 20 limits carried verbatim into `STATE.json` |
| Vague queue | — | 19 items, each written for a stranger with no memory of this session |

Seven further decisions the run may hit were **pre-authorised** with a default and a stated cost
(`decisions_for_user` D1–D7), the sharpest being D5: an evidence-free loop task must merge its
**task** branch, never an agent branch — merging an agent branch is finding F58 exactly, and F58 is
severity A.

### Queue shape, and why this order

Four changes, each a full spec loop (R1/R2/R3/IMPL, never collapsed), with drives interleaved:

```
A  a-flow-briefing-names-its-contract        F140, F143   ← cheapest, stops the waste loop
B  a-review-a-flow-cannot-staff-is-named     F142         ← enforcement of agent-flows:134
C  approval-refuses-unaccepted-evidence      F122         ← operator decision D-A
DRIVE-1  prove a flow lands work end to end               ← THE POINT OF THE RUN
D  a-loop-declares-whether-it-needs-evidence F124         ← operator decision D-B
DRIVE-2  both loop modes, and re-drive the flow
SUITE    full uncontended suite, push, do not merge
```

A, B and C together are what make a **flow** work; D is about **loops**, a separate mode. Hence
the drive between them: the flow is proven before the loop work starts, so stopping anywhere leaves
complete changes rather than half-written proposals.

An **05:30 rule** parks spec work at a clean boundary and hands the remaining time to whichever
drive is next — so the run ends having proven something.

### State at arming

- `master` = `3a274a2`, tree clean, nothing in flight.
- CI green on `c6cdf9e` (all nine jobs, run `33310555286`); the only commits since are docs.
- The full hub suite was **not** re-run at arming — ~14 minutes, and green at `894d5b2` with no
  product code moved since. It runs in the `SUITE` item, uncontended, before the branch is offered.
- One change already in flight and **not** this run's job:
  `openspec/changes/a-write-outside-the-workspace-is-recorded` (F115), proposed, unimplemented.

### Next

Iteration 1: read the exploration, cut the branch, begin `A-R1`.
