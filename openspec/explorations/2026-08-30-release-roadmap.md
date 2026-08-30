# Exploration — Release roadmap: from a working machine to a product worth using

**Date:** 2026-08-30
**Status:** Proposed to the operator. Decision points are marked; nothing here is committed work.
**Purpose:** Answer one question — what stands between today's tree and a release — where
"released" means what the operator defined it to mean: **(1)** the product gives a stranger a
compelling reason to use it, and **(2)** the operator can develop AgentWeave with AgentWeave,
locally, for real.

Everything below is grounded in the findings ledger (`scripts/drive/FINDINGS.md`, F1–F151, all
found by driving the live product), the shipped spec corpus, and the state of `master` at
`c6cdf9e`.

---

## Where the product actually stands

The last three weeks produced 151 findings from live end-to-end drives. Roughly 110 are fixed,
closed by decision, or measured-and-clean; **about 37 remain open, two of them severity A**
(F140, F142). That ratio is the headline: the machinery works, and the drives now mostly find
seams rather than crashes. What was driven clean, live, with real agents:

- the whole spec flow — explore → propose → approve → tasks → evidence → coverage → archive;
- the review ladder — a non-author reviewer staffed by the flow, running in a detached checkout
  of the exact commit the evidence names, issuing a verdict (F142's third row);
- checkpoint chains, cutover, and context-budget parking;
- crash recovery — a hard Hub kill loses nothing (F145, F148, F150);
- `ask_user` and manual permissions on Claude; per-task isolated worktrees; hop budgets;
- requirement drift detection (the API half — F129);
- task↔run binding in two enforcement layers (F66, closed).

The open findings are not scattered. They cluster into a small number of arcs, and one of them
is release-defining.

## The release thesis

**The gap between "the machinery works" and "compelling" is that a flow's finished work cannot
reach the main branch in a default project.** Four findings are the same story told from four
sides:

- **F140 (A)** — a flow briefs an agent to "finish the task and stop" and never tells it, or the
  Hub, what finishing means; the task sits `in_progress` forever and later firings re-do the work.
- **F142 (A)** — the obvious operator remedy (mark it `completed` by hand) is the one completion
  the review ladder refuses to act on, silently — the operator's transition writes no
  `actor_agent`, so the review arm skips it forever.
- **F122 (B)** — a flow can drive a task all the way to `approved` and merge nothing, because no
  default agent holds `can_accept_evidence`; the one step between an approved task and merged
  work is the step no participant in a default flow can take.
- **F124 (B)** — a loop's tasks carry no requirement links, so evidence can never be recorded
  against them, so integration is not merely blocked but structurally impossible — and the card
  offers a "Try again" that cannot succeed.

Until this arc closes, dogfooding cannot leave its current stage — the prohibition on delegating
this repo's work through AgentWeave is *correct today*, because delegated work would complete,
be approved, and never land. The moment it closes, the dogfooding endgame becomes concrete:

> **The overnight autonomous-run machinery this repo already uses — a Windows Scheduled Task, a
> hand-rolled `STATE.json`, a PowerShell driver — is a hand-built prototype of exactly what an
> AgentWeave flow should provide.** The release-readiness test is to retire that driver: run one
> overnight iteration of AgentWeave's own development as an AgentWeave flow, with work landing
> on a branch through the product's own evidence → review → integration pipeline.

That is simultaneously the strongest compelling-reason demo the product could have, and the
operator's own stated definition of released.

---

## Phase 0 — Finish what is already decided

*Nothing here needs a new decision; the specs or decisions exist. This is the queue the 2026-08-30
run left behind, and it is sized for one to two more overnight runs.*

| Item | State | What remains |
|---|---|---|
| **F115** — a write outside the workspace is recorded | Spec complete, three rounds (`openspec/changes/a-write-outside-the-workspace-is-recorded`) | IMPL only |
| **F130** — empty-span checkpoint poisons the next one | Decided, queued | Full spec loop + IMPL |
| **F127** — Run on a busy loop's agent answers 500 | Decided, queued | Full spec loop + IMPL |
| **F111 + F3** — self-registration leaves the product | Decided 2026-08-29, queued | Full spec loop + IMPL |
| **F113** — `propose` omits one of its refusal checks | Decided, queued | Full spec loop + IMPL |
| **F61** — flow conversations all share one title | Fix chosen by the operator 2026-08-26 | IMPL only |
| **F129 + F132** — drift UI proposal | R1 only, per decision D4 | Operator reviews the proposal (feeds Phase 3) |

Also in this phase, two hygiene items that have each already cost real time:

- **Pin the FastAPI/Starlette resolution** (or add a CI job on the floor versions). The unbounded
  `fastapi>=0.110` has produced two CI-only failures through Starlette major bumps. *(Decision,
  small.)*
- ~~Confirm CI on `c6cdf9e`~~ — **done, green.** All nine jobs passed (run `33310555286`), plus
  the Docker image publish. The overnight run ended before its planned uncontended full-suite
  pass, so this CI run *is* the verification the F151 logging fix gets, and it holds.

**Exit criterion:** the decided queue is empty; nothing on `master` awaits an IMPL whose spec is
already approved.

## Phase 1 — The work-lands arc *(release-defining)*

One coherent spec arc — likely two or three related changes rather than one — whose requirement
can be stated in a sentence: **work a flow approves reaches the branch, and every actor's act is
recorded as its own.** It resolves F140, F142, F122, F124, F143, and the attribution residue
F47/F120 that F142 exposed as load-bearing (the flow's own transitions recorded as the
operator's, by nobody, is what breaks `agent_that_completed`).

Operator decisions this phase needs **before** round 1 — each was deliberately filed rather than
fixed because more than one repair is defensible:

1. **F122** — which of the three shapes: grant flow-resolved reviewers `can_accept_evidence` for
   their task; refuse approval on unaccepted evidence; or keep the machinery and surface
   "approved-but-unmerged" loudly.
2. **F140** — which repair defines "finishing" (the choice F142 was established to inform).
3. **Whether a third actor kind (`flow`) is added** so a flow's routing stops being recorded as
   the operator's (F47/F120/F142 all point at this; it is pinned by an existing test).
4. **F124** — whether loop tasks acquire requirement links, or loops get a non-evidence
   integration path, or loops are documented as never-merging.

**Exit criterion, driven not asserted:** a fresh default project, one flow, two tasks — both end
`approved` **and merged**, with no operator intervention beyond approving; a second firing finds
nothing to re-do. This becomes a permanent row in the drive TESTPLAN.

## Phase 2 — The operator is reachable, and the product tells the truth

The legibility-and-lifecycle cluster. All small-to-medium, all already reproduced with
harnesses, none blocking each other — good overnight-run material, roughly six to eight spec
loops:

- **F77** — an agent has no way to address the operator (the one missing communication edge, and
  the reason review verdicts have ended as prose). Pairs naturally with **F139** (agents reach
  for the host's `SendMessage` when AgentWeave's own tool fails them — needs its repair chosen).
- **F133** — the operator's own message erases the reason their agent is stalled.
- **F146** — the operator's question route accepts `blocking` and throws the answer away.
- **F126** — a spent checkpoint can be cut over twice, minting a duplicate successor that re-does
  the work. Idempotency guard.
- **F128** — a loop runs on an agent its job does not name whenever its own agent is busy.
- **F147 / F123** — a crashed firing's history reads `failed` forever even after the Hub itself
  recovered the work.
- **F134** — an empty charter injects as a bare heading and reports fully configured.
- **F136** — an agent with no runner is told to install a binary named after itself.
- **F117** — the untyped `PATCH /agents/{name}` accepts misspelled *safety* settings silently
  (the last of F116's three unmodelled routes once F111 deletes `register`).
- Smalls, batchable: F149, F121, F125, F141, F68, F20, F62; plus the queued Q4-SPEC pair
  (F53's orphaning half, F65's retry).

**Exit criterion:** an agent can tell the operator something and the operator can answer;
nothing in the timeline attributes an act to the wrong actor; re-pressing any button is safe.

## Phase 3 — Surface the differentiators

Per the product direction (2026-08-02), the compelling reasons *are* spec-driven development,
multi-agent collaboration, and governance — integrated, not assembled. Two of the three are now
real machinery that the app cannot show:

- **Requirement drift (F129 + F132)** — the whole loop works at the API and nothing can reach
  it: no UI surface calls detect or resolve, and the agent surface has no entrance, while the
  gate's refusal names an action no surface offers. Build the Detect/Resolve surfaces from the
  Phase 0 proposal (F132's constraint: Resolve ships with or before Detect).
- **The coverage story on screen** — evidence, integration outcome, and "what is this flow
  waiting on" are all computed and mostly rendered; this phase is an editorial pass that makes
  the spec-driven loop *legible to a newcomer*, not new machinery.
- **Charter/agent setup UX** — the first-run path (create project → bind runner → bind charter →
  first turn), smoothed by the F134/F136 fixes landing in Phase 2.

**Exit criterion:** a screen-recording of one spec-driven change — requirement to merged work to
drift detection when the code later moves — with no terminal visible except the agents' own.

## Phase 4 — Dogfooding, staged to full depth

Each stage gates on the phase before it; each amends CLAUDE.md's permitted/prohibited tables
explicitly, the way the 2026-08-16 amendment did.

- **Stage 2 — one delegated change.** Lift the delegation prohibition for exactly one
  self-contained change: author the spec in the trial Hub, let a roster agent implement it in a
  task worktree, a second agent review it, evidence accepted, work merged by the product to a
  branch of this repo, operator merges to `master` by hand. *Gate: Phase 1 shipped. Decision:
  the operator lifts the prohibition.*
- **Stage 3 — a flow runs the night.** Replace the Scheduled-Task driver for one overnight run:
  a flow with a queue of decided items, checkpoint cutovers instead of handoff files, `ask_user`
  instead of `decisions_for_user` JSON. The hand-rolled driver stays as fallback until a flow
  has done it twice cleanly.
- **Stage 4 — the corpus moves.** Migrate the ~30 `openspec/specs/` documents into AgentWeave
  capability documents (`current` phase — the mechanism has existed since 2026-08-16); openspec
  retires from this repo. *This is the operator's call, explicitly reserved in CLAUDE.md; the
  round discipline (spec loop) survives the migration as process regardless of tooling.*

**Exit criterion:** the operator's own bar — AgentWeave develops AgentWeave for a full week,
overnight runs included, with the old driver untouched.

## Phase 5 — Release hardening

- **Docs rewrite.** `docs/` was last touched 2026-08-19 and its nav has no flows, no evidence,
  no checkpoints, no drift, no permissions story — the product it describes is weeks behind the
  one that exists. Rewrite from the spec corpus (which is current by construction), not from
  memory.
- **The stranger's hour.** On a machine (or clean profile) that has never seen AgentWeave:
  `pip install agentweave-ai` → `agentweave` → first project → first flow → merged work, driven
  as a findings sweep with the same discipline as the e2e drives. Every stumble is a finding.
  `doctor` is the star witness here — "hard to use" was the original diagnosis.
- **Suite time.** The hub suite is ~14 minutes and the operator has already called it too long;
  F109 named the single-connection root. A time budget and a parallelization pass, before the
  suite doubles again.
- **The freeze.** Set the feature-freeze parameters (still unsettled), burn down to zero open
  A/B findings or explicit won't-fix decisions, version bump, release checklist
  (`/check-build`: PyPI, Docker image, docs deploy).

**Exit criterion = the release definition:** the stranger's hour drives clean, and Stage 3/4
dogfooding is the development process rather than an experiment.

---

## Decisions the operator owns, gathered in one place

| # | Decision | Blocks |
|---|---|---|
| 1 | F122's shape (grant / refuse / say it loudly) | Phase 1 R1 |
| 2 | F140's repair — what "finishing" means | Phase 1 R1 |
| 3 | Add a `flow` actor kind? | Phase 1 R1 |
| 4 | F124 — do loop tasks get requirement links? | Phase 1 R1 |
| 5 | Review the F129+F132 drift-UI proposal | Phase 3 |
| 6 | F139's repair shape | Phase 2 |
| 7 | Pin FastAPI / add floor-version CI job | Phase 0 |
| 8 | Feature-freeze parameters | Phase 5 |
| 9 | Lift the delegation prohibition (Stage 2) | Phase 4 |
| 10 | Corpus migration timing (Stage 4) | Phase 4 |

## What this roadmap deliberately does not include

- **Federation, multi-user, company hub** — deferred by the product direction, still deferred.
- **Codex** — cancelled 2026-08-29 ("let codex undrivable for now"); the Claude path is the
  release path.
- **Reviving the CLI as a collaboration surface** — the five commands are the product's CLI.
- **A backstop behind `ask_user`** — retired by the operator 2026-08-20; stays retired.
