# What to work on next (2026-08-17)

**Status:** A proposal for the operator, not a decision. Written by the autonomous session
(`autonomous/2026-08-17-archive-and-hub-app`, queue item A4) at the end of its run, per the
operator's own framing: "if there is still time you can work out some roadmap of things that we
should work on next." Nothing here has been acted on. Where a claim depends on something this
session did not itself measure, it says so rather than asserting it.

Ranked in four tiers: things that unblock other things (do first, mostly small), infra debts
(medium, no user-visible payoff but they're why iteration is slow or CI is untrustworthy), one
housekeeping item that's bigger than it looks, and forward architecture (already explored in depth
elsewhere — this section summarizes and points at it rather than re-deriving it).

---

## Tier 1 — unblocks other things

### 1. Judge the remaining taste-pass tasks
**Reason:** Six 2026-08-16 changes (`conversation-formatting-and-quick-nav`,
`delete-project-api`, `many-named-loops`, `spec-surface-legibility`, `the-board-scoped-by-document`,
`the-corpus-keeps-what-shipped`) are code-complete — every agent-verifiable task is ticked — but
none can archive until their human-only "does this read right" tasks are judged. `.claude/
TASTE-PASS-2026-08-17.md` (untracked, on this branch) has the full list: 21 tasks, 4 already judged
by the operator today, 9 blocked only on missing fixtures the doc says how to seed in under 20
minutes total (a throwaway project; a declaring document with tasks and evidence; a capability
document and a job with a loop), and 2 (`conversation-formatting` 6.2/6.3) that need a real, paid
agent turn — see `decisions_for_user` D2 in this branch's `STATE.json`.
**Size:** ~15 minutes to judge what's already unblocked, ~35 more to seed the rest, plus whatever a
live agent turn costs for the last two. No code.
**Depends on:** nothing. This is the highest-leverage next 15 minutes available.

### 2. Archive the six code-complete changes
**Reason:** Follows directly from #1. `openspec-archive-change` moves a finished change's deltas
into `openspec/specs/` and the change itself into `openspec/changes/archive/`. Until this happens,
the corpus under-reports what has actually shipped, and `2026-08-16-a-corpus-at-scale.md`'s own
navigability concern (explorations, dated 2026-08-16) keeps compounding with a growing pile of
finished-but-open changes.
**Size:** small, mechanical, one change at a time via the `openspec-archive-change` skill.
**Depends on:** #1 — do not archive a change with an un-judged or objected human-only task.

### 3. Decide what happens to this branch
**Reason:** `decisions_for_user` D1 in `STATE.json`, unresolved through six iterations. The branch
carries real, tested work (A1's archive confirmation, A2's archived-document visibility fix, A3's
global-instance/`--profile`/desktop-window slice) that master does not have. It was deliberately
kept disposable and never merged by the driver itself, per this run's own `limits`.
**Size:** small (a merge or cherry-pick decision), but it blocks every other in-flight thread from
building on this work.
**Depends on:** nothing — purely an operator call.

---

## Tier 2 — infra debts (no user-visible payoff, but they're why things are slow or untrustworthy)

### 4. Trace `pid_alive`'s POSIX callers
**Reason:** `openspec/explorations/2026-08-17-the-hub-suite-has-never-run-clean.md` (this
session did not re-derive this, it's citing that document) found `pid_alive()` uses `os.kill(pid,
0)`, which reads a SIGKILLed-but-unreaped zombie as alive on POSIX. Two tests fail on Linux for
this. Whether it's a real defect depends on whether anything besides the restart-reconciliation
path calls it — if so, the Docker image (which is Linux) could believe a process it just killed is
still running.
**Size:** small to trace, small-to-medium to fix (`waitpid(WNOHANG)` or a `/proc/<pid>/stat` zombie
check) if it's real.
**Depends on:** nothing, but needs a POSIX environment to verify — this session's driver is Windows
and could not check it, same as the exploration that found it.

### 5. Decide the `fastapi`/`starlette` version bound
**Reason:** same exploration — `hub/pyproject.toml` declares `fastapi>=0.110` with no upper bound;
CI silently resolved a major-version boundary (starlette 1.x) the developer machine never ran. The
product turned out to be compatible (verified: 16/16 genuine failures traced to route-introspection
shape, not `hub/hub/**` behavior, both versions produce the same 140 route paths) — so this is not
urgent — but shipping an unbounded range still means users get combinations nobody tested.
**Size:** small — pick a bound, document why.
**Depends on:** nothing.

### 6. Make CI prove it's testing a clean environment
**Reason:** same exploration again — the whole 37-test gap went unseen for three weeks because a
green local run and a red CI job looked like a CI problem, not a "CI is the only place testing the
real dependency resolution" problem. A build that fails when a test is skipped for a missing binary
CI was supposed to provide would have caught this on day one.
**Size:** small-medium — likely a CI-only assertion that skip counts match an expected baseline, or
that CI's dependency resolution is pinned/checked.
**Depends on:** nothing.

### 7. Fix the shared-connection test fixture, then session-scope it
**Reason:** two debts recorded in this branch's `STATE.json known_debts`, not newly found here.
First: the Hub test fixture's `StaticPool` shares one sqlite connection across every session in the
process, so concurrent sessions can roll back each other's writes — proven, 105/200 commits lost
under a concurrent poller vs. 0/200 without, and one test is `xfail`ed because of it. A file-backed
`DATABASE_URL` is not a drop-in fix (it hung the suite when tried; needs WAL + a busy timeout).
Second, separately: the suite is near-100% fixture overhead — `create_app()` plus `drop_all`/
`create_all` across 43 tables per test accounts for essentially all of its ~8-minute runtime.
Session-scoping the app and schema would likely take it to about a minute.
**Size:** medium for the correctness fix (WAL + busy timeout, then re-verify the concurrent-poller
case actually passes), medium for the session-scoping speedup, independently valuable and doable in
either order.
**Depends on:** nothing, but the correctness fix should land before trusting any test that exercises
concurrent writes — including future work on Proposal C below, if that ever schedules concurrent
loop firings.

---

## Tier 3 — housekeeping that's bigger than it looks

### 8. Reconcile or retire `2026-07-30-hub-native-experience`
**Reason:** this change has 48 of 188 tasks still unchecked — by far the largest open change in the
repo — spanning usage accounting (§9), a projects API (§10), composer rework (§11-12), agent
identity/charters (§13), and spec traceability (§14). Several of these areas now have shipped,
named features that did not exist when this change was written: `CLAUDE.md` already documents
Runner/Agent/Charter separation as shipped (which overlaps §13), and the spec document flow shipped
and has been driven end to end (which overlaps §14). It's likely this change is now a mix of
"actually still needed" and "superseded by later work under a different name," and nobody has gone
through it task by task to tell which is which since those later changes landed.
**Size:** medium — this is an audit pass (read each unchecked task, check it against
`openspec/specs/` and `CLAUDE.md` for what actually shipped, either re-scope the remaining tasks
into a smaller change or archive the superseded ones with a note pointing at what replaced them),
not an implementation pass.
**Depends on:** nothing structurally, but doing #2 first (archiving what's genuinely done) makes
the corpus this audit reads against more accurate.

### 9. Retro-cover 1.0.1 with a change
**Reason:** `decisions_for_user` D3. The 1.0.1 release (renderer colour, composer rework, cost
removal, ticket redesign, palette fix) was implemented directly, outside any openspec change —
under the repository's own convention (`CLAUDE.md`'s "AgentWeave takes new changes... authored in
the app" / openspec's proposal discipline) that should have been a change with tasks and specs.
It's real, tested, and released either way; this is about making the corpus match the code, not
about redoing the work.
**Size:** small-medium — mostly writing `specs/` deltas for what already shipped, not new
implementation.
**Depends on:** nothing.

### 10. Fix the loose `agentweave-hub` pin
**Reason:** `decisions_for_user` D4, found but not fixed during the 1.0.1 release. `pyproject.toml`
pins `agentweave-hub>=1.0.0`; since essentially all of 1.0.1's content lives in the hub package, `pip
install --upgrade agentweave-ai` can leave an existing `agentweave-hub==1.0.0` in place (already
satisfies the floor) and deliver none of the release — observed live during the 1.0.1 release
itself. A fresh install is unaffected; this only bites upgraders.
**Size:** small code change (track the release version rather than a floor) but requires an actual
release to ship, which is outward-facing and explicitly out of scope for an autonomous driver.
**Depends on:** an operator decision on whether "one product, one version" is the actual intent
before picking the pinning strategy.

---

## Tier 4 — forward architecture

`openspec/explorations/2026-08-17-architecture-proposals.md`, written earlier this session at the
operator's request ("start proposing ideas... and start thinking of architectures"), already covers
this in depth — summarized here rather than re-derived:

- **Proposal A — loops as a fourth roster citizen.** Give `Loop` (from `many-named-loops`) a
  `charter_id` like `Agent` has, and show it on the roster page instead of a separate jobs table.
  **Cheapest and most self-contained** — one migration column, one FK, one UI badge. The
  exploration recommends doing this first if any of the three are picked up.
- **Proposal B — a spec-drift verification loop.** A named loop whose queue is "does this capability
  document still match shipped behaviour," using `record_evidence` to surface drift without editing
  the document itself (content changes to a `current`-phase document stay an operator-authored
  merge). The exploration calls this **the highest-leverage next spec change** — it's what turns
  `the-corpus-keeps-what-shipped`'s `current` phase from "somewhere to put current behaviour" into
  "the corpus stays true."
- **Proposal C — retire `STATE.json`; run the autonomous session itself as a Loop.** The most
  consequential long-term (it would let the product's own development process prove the durability
  claim `2026-08-15-where-agentweave-fits.md` narrows AgentWeave's pitch to, on itself) and the
  least ready to spec — it needs an execution-path answer (how a `Loop` firing maps to "drive Claude
  Code through an implementation slice") that N3 deliberately left out of scope. The exploration's
  own recommendation: treat this as **the next exploration to deepen, not the next change to
  propose.**

None of Tier 4 is this document's recommendation to build immediately — it's forward context so
whoever picks the next queue knows it's already been thought through once.

---

## Suggested order, if picking one thread

1. Tier 1 in full (unblocks the corpus and the branch decision — cheap, does not compete with
   anything else).
2. Tier 2 item 7 (test fixture correctness) before anything that touches concurrent execution,
   including Proposal C.
3. Tier 3 item 8 (the stale change audit) once Tier 1's archival makes the corpus it's checked
   against trustworthy.
4. Proposal A, if the operator wants to build rather than continue auditing — it's small, and per
   the architecture exploration it's a prerequisite for Proposal B being legible.

This is a proposal, not a plan the next session should treat as pre-approved — in particular, Tier
1's taste-pass judgments are inherently the operator's own eye, not something an agent should
self-certify on the operator's behalf.
