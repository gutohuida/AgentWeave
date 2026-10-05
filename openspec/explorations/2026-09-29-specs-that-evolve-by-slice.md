# Specs that evolve, one slice at a time

**Date:** 2026-09-29 · **Status:** exploration, nothing built, nothing decided beyond the operator's
answers recorded below · **Branch at writing:** `master` @ `688751f1`

Written by an interactive session after comparing AgentWeave against the operator's agentic-SDLC
market research (`AICollective/ResearchClub/agentic-sdlc-market/agentic-sdlc-full-findings.md`,
2026-09-28/29) and then questioning the operator one decision at a time. It is the companion to
[`2026-09-16-the-flow-costs-more-than-the-work.md`](2026-09-16-the-flow-costs-more-than-the-work.md),
which studied the flow's *execution* topology and left the spec-to-task layer explicitly out of scope
(its §11, question 4). This file is about that layer.

## What the operator said

Verbatim, 2026-09-29:

> I feel like we're too heavy on the specing. Altought it's really cool to see a huge flow being
> worked on there are two things that bothers me the most right now: 1 - Spec takes too long and it's
> too big generating a huge flow with so many tasks that take us right into number 2 seems that the
> work is very attomic. So we have a lot of tasks that feel small and then a reviewer on top wich
> makes things very slow, burns a lot of tokens and I donºt know if the results are justifying it.
> I'm not sure if bigger tasks that are one shotted and then a reviews and fix loop is better. Also
> once the spec is approved it leaves no space for it to evolve. I still like the spec but maybe it
> should be part of the development loop. Also I really like the flow screen being generated,
> knowing whatºs being worked on, the status of each task etc

> should we change the explore/propose instuctions to be able to generate more then 1 spec. For
> exaample generating 1 spec for each slit and then we can have also a link of specs on the order
> they should be built and we have also a spec dependency tree that shows how each document relates
> to each other.

> Take advantage of the html nature of the spec to indicate new changes untill they are approved,
> when they were created, why, and then when were approved by whom if there is specific reason, what
> changed. This will become also a evolving documentation of the project that I can check how it
> progressed and also send to another AI if I want to regenerate so it has some kind of background on
> the evolution of the project and can regenerate entire specs avoiding all the pitfalls

**What is kept, stated first so it is not lost:** the flow screen: what is being worked on and the
status of each task. The spec is kept too. What changes is its size, when it is written, and whether
it can move once approved.

## Why: three mechanisms and one run

The friction is not a feeling. It comes from three rules in the code and shows in the one real
product run on record.

**1. The document forces atomic tasks.** `hub/hub/spec_completeness.py:39` sets
`MAX_REQUIREMENTS_PER_TASK = 3`, and `:211-229` refuses a proposal where any task traces to no
requirement or to more than three. Task count therefore grows with requirement count: LoopEngine's 77
requirements became 32 tasks at approval. The ceiling's own rationale is sound. One approved ticket
carried 6 of 9 requirements on 42 words and hid a rejected FR-9 inside a task that read as done. But
that is a *visibility* problem. The same run still merged a commit while FR-11 was rejected
(`spec-queue/observations/2026-09-14-LoopEngine.md`, Architect §9), so small tasks did not solve it
either.

**2. Every task is reviewed.** A flow staffs a review for every completed task
(`openspec/specs/agent-flows/spec.md`, "A flow resolves a reviewer…", "An agent fired to review a
completed task…"). The staffing code in `hub/hub/scheduler.py` never reads rigor, so a `sketch`
document gets the same per-task review as a `gate` one.

**3. Approval freezes the document.** `hub/hub/spec_service.py:165-169` refuses every submission to an
approved document: *"this document is approved; reopen it before changing what was approved"*. The
only way back is `approved → exploring` (`spec_lifecycle.py:41-69`), which restarts the whole
propose/approve cycle. The per-requirement proposal machinery that could carry an evolution already
exists (`spec-document-authority`, "A document at contract or gate rigor gates edits behind an
operator-accepted proposal"). It never runs on an approved document, because the phase check fires
first.

**The one run (LoopEngine, `:8000`, 2026-09-12 → 09-14, read-only):**

| | |
|---|---|
| Spec phase | 31 operator turns in two sittings, 20 revisions → 77 requirements, 32 tasks |
| After ~14 h of build | 10 of 32 tasks approved, 12 completed and waiting for review, 23 pending |
| Spend | $281.75 API-equivalent, very roughly $28 per approved task |
| Review | 243 `review_unstaffed` stalls; 35 of 79 evidence rows rejected (44%); Architect↔`tester` chains hitting the hop budget |
| Rework | one task alone, $23.80 over three review rounds in the author's growing session |
| The spec wanted to move | the Architect opened **18 tasks that were not in the spec**; none was approved |

The caveats from the 09-16 file apply unchanged. There is one corpus, and a lot of the waste was
defects: quota walls, guard refusals, a spec too large for its read tool, and the F352 staffing gate.
The shape is still the one the operator describes.

## What the outside research says

From the market research (§3.3, §4, §6.4 of its Part I):

- SDD turns into waterfall when specs are big and written *before* any code, when
  requirements → design → tasks are sequential approval gates, and when the spec is the permanent
  source of truth. AgentWeave's change documents do the second and third.
- Böckeler's taxonomy: **spec-first** (write, use, discard) is the recommended default.
  **Spec-anchored** (kept and evolved with the code) is for long-lived, high-churn subsystems.
  AgentWeave already has both shapes: `change-spec` documents and `capability` documents
  (`db/models.py:1953`). The difference is that its change documents are handled as if they were
  anchored.
- *"Approve the slice, not each phase."* *"Right-size the ceremony."* *"Put rigor in executable
  checks, not documents."*
- Cognition: keep one coherent change in one agent's context and share traces, not messages. Atomic
  tasks spread one feature across several cold contexts.
- Measure first-pass acceptance, iterations per task and post-merge rework. If specs don't move those
  numbers, they are ceremony.

## The operator's decisions

Taken 2026-09-29, one question at a time. The alternatives that were offered and not chosen are listed
so they are not re-proposed without new evidence.

| # | Question | Decision | Not chosen |
|---|---|---|---|
| Q1 | Where the evolution history lives | **In the spec HTML.** The agents' normal read excludes it; a separate *export with history* includes it | Always in the agents' read (context cost); a companion document per spec; one project-wide changelog |
| Q2 | Unit of change | **An amendment:** a named group of edits with one *why*, accepted or rejected as a whole | Per-edit accept inside an amendment; per-requirement entries as today |
| Q3 | In-flight work when an amendment is accepted | **Nothing done is reopened.** Affected requirements show *verified against an older version*, and the amendment brings its own follow-up tasks | Brief in-progress tasks mid-flight; auto `revision_needed`; refuse while tasks are in progress |
| Q4 | Who proposes, and work outside the spec | **Any agent in the flow may propose an amendment. Inside a flow, new work arrives only as an amendment.** No loose tasks | Loose tasks shown as *off-spec*; only the author agent proposes; only the operator proposes |
| Q5 | When the operator is away | **By rigor.** At `sketch` an amendment applies immediately and is marked *unratified* in the HTML until ratified. At `contract`/`gate` it waits | Always wait; always apply-then-ratify; stop at the slice boundary |
| Q6 | Rejecting an unratified amendment already built | **Recorded. Unstarted tasks cancelled. Built work stays, and a *revert A5* amendment is proposed** for the operator to confirm | Leave it to the operator; auto-revert commits; hold unratified work off `main` |
| Q7 | Content of the regeneration export | **Spec + amendment history** (accepted, rejected, reverted, each with its why) **+ a distilled *lessons* section** from review rejections | History only; the full raw review log; spec plus a short narrative |
| Q8 | Who writes lessons, and when | **The reviewer writes a one-line lesson with each rejection. At slice archive an agent distils them and proposes which also belong in project instructions** | Generated once at archive; one-liners with no distillation; the operator writes them |
| Q9 | A ratified amendment in the HTML | **Inline markers go. A small *A3* badge stays on each changed requirement,** linking to an **Evolution** timeline at the end of the document | Nothing inline after ratification; permanent track-changes with a toggle; no inline markers even while pending |
| Q10 | An amendment that changes an earlier, finished slice | **Archived slice specs are frozen history. The amendment becomes a new small slice on the roadmap** (or goes into the current slice if tiny), linked back | Reopen the old slice; put it in the current slice with a cross-link; put it on the capability document |
| Q11 | How far ahead slices are fully specced | **Rolling: only the next slice.** When it is approved, the agent drafts the one after, informed by what was learned | Two ahead; all up front; per-roadmap choice |
| Q12 | Task size and review inside a slice | **A few big tasks per slice,** each one-shot by one agent with tests and lint run inside its loop. **One review at the end of the slice. Fixes run in a fresh session.** Per-requirement status stays visible | Review intensity by rigor; one task per slice; keep per-task review and loosen the cap |

## The model those answers describe

```
  EXPLORE ──► ROADMAP  (kind: roadmap)
               ordered slices: intent · definition of done · builds-after
               renders as the dependency tree; parent of every slice
                  │
                  ▼  rolling: only the next slice is detailed
               SLICE N  (kind: change-spec, child of the roadmap)
               requirements · a few slice-sized tasks · delivery
                  │  approved
                  ▼
               BUILD  one owner per task, tests/lint inside the loop
                  │                         │ discovery
                  │                         ▼
                  │                  AMENDMENT  (grouped edits + why)
                  │                   sketch: applies now, marked unratified
                  │                   contract/gate: waits for the operator
                  │                   brings its own follow-up tasks
                  ▼
               SLICE REVIEW  once, at the end; fix loop in a fresh session;
                  │          each rejection carries a one-line lesson
                  ▼
               ARCHIVE  frozen history · lessons distilled · the next slice is drafted
```

**What the rendered document shows.** Pending and unratified amendments appear inline as
track-changes: inserted text marked, removed text struck through, and a badge giving proposer, time
and why. Ratification removes the markers and leaves an `A3` badge on each changed requirement. The
document ends with an **Evolution** timeline covering every amendment: proposed by, when, why, the
edits, and accepted, rejected or reverted, by whom, when and with what reason. A requirement changed
after its evidence was accepted reads *verified against A2's version*. The history is in the file. It
is excluded from what `read_spec_document` returns to agents and included in *export with history*.

**What the flow screen gains.** One level above the task board: roadmap → slices (order, state,
builds-after) → a slice's tasks, each carrying a per-requirement checklist. Plus a lane for pending
and unratified amendments.

## What already exists to build on

| Needed | Already there | Gap |
|---|---|---|
| Attributed history | Every content or phase change is an append-only, attributed event (`spec-document-authority`, "Every change to a document is recorded…") | No *why* on a submission; rigor changes made in the app record blank reasons (F429, being fixed by `a-documents-rigor-history-and-retired-requirements-are-on-screen`) |
| Proposals | Per-unit proposals, found in position, one at a time, proposer and accepter recorded separately, stale proposals refused (`spec-document-authority` 1139–1233) | Not grouped; no why; never reached on an approved document |
| Retired requirements | Kept with their links and evidence (`spec_index.py:10`) | On no screen (same in-flight change as above) |
| Implementation → spec | "A changed implementation raises a candidate, never an edit" (`requirement-traceability`) | Nothing turns a candidate into an amendment |
| A plan document | `roadmap` is a document kind (`db/models.py:1953`) | The explore instructions write one change document; a change's delivery is asked about only for `change-spec` |
| A tree | Parent/child placement with a generated map of children (`spec-corpus-map`) | Operator-set hierarchy, not build order |
| Build order across documents | A task may import a task from another document (`task-dependencies`) | **Only from an approved document**, and only task to task. Slice 2 cannot be proposed depending on slice 1 until slice 1 is approved, and there is nothing to draw a document tree from |
| Criteria the gate can run | A materialised task carries its requirements' acceptance criteria (`a-materialised-task-carries-its-criteria`, built) | Nothing runs them as a gate (09-16 §12, item 1) |

## What would have to change

Listed as the specs and code a later change would touch. None of it is proposed here.

1. **`spec_service.py:165`.** A submission to an approved document becomes an amendment instead of a
   refusal. At `sketch` it applies and is marked unratified. At `contract`/`gate` it waits. The
   *document_approved* refusal survives for the path (`:670`), which is a different guarantee.
2. **Proposals gain a parent.** An amendment record with a name, a why, a proposer, a state
   (`pending`, `unratified`, `ratified`, `rejected`, `reverted`) and its member edits. It is accepted
   or rejected whole (Q2). A new migration.
3. **The meaning of *approved* changes** at `sketch`. It becomes *the approved baseline plus ratified
   amendments, with unratified ones visibly marked*. `spec-document-authority`'s approval
   requirements need that sentence.
4. **`create_task` inside a flow** is refused, with *"propose an amendment"* as the remedy (Q4).
   Tasks come only from materialisation, including an amendment's.
5. **Rejecting an unratified amendment** cancels its unstarted tasks and proposes a revert amendment
   (Q6).
6. **Review verdicts gain a one-line lesson** on rejection (Q8). Archive gains a distillation step
   that proposes edits to project instructions, which the operator approves like anything else.
7. **Rendering** (`spec_render.py`): inline markers, badges, and the Evolution timeline. The agent
   read route strips the history section. A new *export with history* route and a button.
8. **Explore instructions** produce a roadmap plus the first slice's change document. A document-level
   *builds after* edge between roadmap children may name an unapproved sibling. The task-level import
   rule is unchanged.
9. **`MAX_REQUIREMENTS_PER_TASK`** is raised, or scoped to what a slice needs. It is only acceptable if
   per-requirement status is on the task card **and a task cannot land while any of its requirements'
   evidence is rejected**. The second clause is what the ceiling was really protecting. R1 should
   check whether the FR-11 merge is still possible.
10. **Review staffing** moves from per task to per slice (Q12). This is where the file meets 09-16:
    that file's *iteration* (same owner, fresh context) and *gate* (runs the criteria, returns a
    verdict) are the execution half of this model. Its items 1–2 and
    `2026-09-14-rework-in-a-fresh-session.md` are prerequisites, not alternatives.

## A possible order

Chosen so that stopping after any step leaves something complete and useful:

1. **Amendments on approved documents** (items 1–3, 7). The core of *the spec evolves*.
   Self-contained, reuses the proposal machinery, and does not touch the flow topology.
2. **New work inside a flow is an amendment** (items 4–5). Depends on 1.
3. **Roadmap and slices** (item 8). The most direct answer to *the spec takes too long and is too
   big*.
4. **Slice-sized tasks and slice-end review** (items 9–10). Largest blast radius. Coordinate with
   09-16's order.
5. **Lessons and the regeneration export** (item 6 and the export half of 7). Needs 1 for the history
   and 4 for the reviews that produce lessons.

## Open questions

1. **Q11's timing.** Does the agent draft slice N+1 when slice N's *spec* is approved (in parallel
   with building N), or when slice N has *landed*? The answer said *"when it's approved… informed by
   what was learned"*, and both readings fit.
2. **The weaker guarantee.** At `sketch`, an approved document now changes without the operator, and
   the unratified markers are the only safeguard. Is that acceptable for every project, or should
   *apply now* be a per-project setting?
3. **Does a roadmap go through the phase machine?** Unverified whether `roadmap` documents are
   proposed and approved like change documents. If they are, is re-ordering slices itself an
   amendment?
4. **Slice-end review finds defects late.** One review per slice means a wrong turn in task 1 is
   found after task 3. Is the in-loop executable check enough to make that rare, or should a failed
   check inside a task still stop the slice?
5. **What remains of the 3-requirement ceiling?** Remove it, raise it, or make it per-slice?
6. **Measurement.** Which numbers decide whether this worked? The proposal: first-pass acceptance,
   review rounds per task, and cost per approved slice against LoopEngine's ~$28 per approved task,
   on a second project, since 09-16 §10 already notes that one corpus proves nothing general.

## What would falsify this

- **A second project where atomic tasks plus per-task review have higher first-pass acceptance and
  lower cost per landed requirement** than slice-sized tasks with one review. Then the ceremony is
  paying for itself, and the operator's feeling is the defects, not the design.
- **Amendments that nobody ratifies.** If unratified amendments pile up the way unanswered overnight
  questions did in LoopEngine, *apply now, ratify later* has become *apply now, never read*. The
  rendered markers are there to make that visible. Count them.
- **Author bias returning.** 09-16 §10's warning stands: moving review to the end of the slice is a
  change in how often review happens. Any version that removes the independent check instead of
  relocating it should be rejected.

## The decision, in one line

Approving this means a spec loop for **amendments on approved documents** (order item 1), with R1
answering open questions 1–3 first. Order items 3–4 follow only after 09-16's items 1–2 have landed.

**Superseded on 2026-10-05: see the next section.** The order is reversed, slices come first.

---

## 2026-10-05: re-grounded at `9dd11cc`, and the order reversed

This section was written by an interactive `openspec-explore` session with the operator present, and
the operator asked for "shorter spec runs". It was checked against the code at `9dd11cc`, 414 commits
after the file above. None of the spec-to-task files had changed except `spec_service.py` (`2f120b4`,
which lets a pending proposal be withdrawn). So the "What already exists" and "What would have to
change" tables above still hold.

### What the code and the data say now

- **Measured, read-only, from both Hub databases (`mode=ro`).** There have been only two real spec
  runs, both on `:8000` for LoopEngine. Each produced 77 requirements and 32 tasks.
  - The first took 19 h from creation to approval, of which 146 minutes were agent time. Authoring
    cost $39.65 against about $270 for delivery, and 12 of 47 tasks were approved.
  - In both documents, `proposed` lasted 3–5 seconds of operator clicks; the real review happened
    in chat. The document grew 5 → 9 → 19 → 77 requirements in one night, over 19 whole-document
    resubmissions.
  - 0 of the 15 tasks added after approval reached `approved`.
  - No `roadmap` document exists anywhere, and no rigor other than `sketch` has ever been set.
- **`roadmap` is vocabulary only.** It passes through the full completeness check, and approving one
  would materialise its `tasks[]` (`api/v1/spec.py:1829-1832`). Only the operator can create one
  (`api/v1/spec.py:1595-1621`); an agent can create only a `change-spec` (`agent_actions.py:1588`).
  Only the operator can set `parent` (`api/v1/spec.py:1473-1500`).
- **Slicing guidance reaches agents only through an optional charter** (`data/charters/spec.md:91-92`).
  The tool docs every authoring agent reads (`mcp_server.py` `create_spec_document`,
  `submit_spec_document`) and `SPEC_PHASE_DUTIES` (`api/v1/agents.py:1704-1729`) say nothing about
  size.
- **The guard behind the 3-requirement ceiling exists only at `gate`.** Rejected evidence blocks
  approval only under `gate` (`requirement_gate.py:654`, `:678-683`). `_enforced_requirements` drops
  `sketch` documents (`:344-364`). So the FR-11 incident (approval over a rejected requirement) is
  still possible on every real document.
- **Review is per task and ignores rigor** (`scheduler.py` `decide_firing`, `:2103-2111`). Criteria
  are never run, and there is no per-iteration budget (09-16 §12 items 1–2: neither has been built).
- **A task sent back for revision was reworked by its reviewer.** This is F495, fixed on
  2026-10-05 as a Tier-0 fix.

### The reversed order, and why

Problem ① (the spec is too long and too big) and problem ② (too many tiny tasks, each reviewed) share
one cause: **one document per change, written in full up front.** Rolling slices address both, and
small slices remove most of the pressure for amendments (③), because learning goes into the next
slice's draft. Bigger tasks also give most of "one review per slice" for free: a slice of about 8
requirements as 2–3 tasks means 2–3 per-task reviews, without building slice batching. Slice-end
review (order item 4) and amendments (order item 1) are deferred until C1's drives show they are
still needed.

### The operator's decisions (2026-10-05)

| # | Question | Decision | Not chosen |
|---|---|---|---|
| Q13 | Who drafts the next slice (open question 1) | **The agent drafts slice N+1 when slice N is approved; the operator approves each slice.** The roadmap and slice 1 are written in one sitting | The agent drafts and the slice starts building at `sketch` without the operator; all slices drafted up front |
| Q14 | Rejected evidence and approval | **Rejected evidence blocks task approval at every rigor** | Block at `contract` and `gate` only; leave as is |
| Q15 | `MAX_REQUIREMENTS_PER_TASK = 3` | **Removed.** A requirement with no task is still refused | Raise it to about 6; keep 3 |
| Q16 | The rework defect | **Filed as F495 and fixed as Tier 0 now** | Finding only; fold it into C1 |

### C1 (Tier 1): a spec is written one slice at a time

The next change, to propose with an acceptance drive written before the build:

- **Authoring guidance where every agent reads it.** Add it to `create_spec_document` and
  `submit_spec_document` docs and to `SPEC_PHASE_DUTIES`, not only in the charter:
  - a large request becomes a roadmap plus slice 1;
  - a slice is small (a size target to be set in R1);
  - later slices are recorded in the roadmap, not specified.
- **`roadmap` gets behaviour.**
  - An agent may create one.
  - It carries ordered slice entries (intent, done criteria, builds-after) and no tasks; it is
    never materialised.
  - Its slices are its children, and an agent may set that placement.
  - Approving slice N prompts the drafting of slice N+1 (Q13).
- **The rejected-evidence block at every rigor** (Q14). This is a behaviour change for `:8000`'s
  `sketch` documents on its next restart; the proposal must say so.
- **The ceiling removed** (Q15), with each task's requirement status visible on the card.
- **Acceptance drive.** On `:8010`, run a LoopEngine-sized request through explore. It must yield a
  roadmap plus a slice 1 within the size target, with a few tasks, and approving slice 1 must start
  the drafting of slice 2. A task whose requirement's evidence was rejected cannot be approved on a
  `sketch` document.
- **Open for R1.**
  - Q11's timing is now decided (Q13). Open question 2 is moot under Q13. Open question 3 is
    answered by Q13 plus the bullet above: a roadmap is approved by the operator like any document.
  - Still open:
    - the size target;
    - whether re-ordering slices needs re-approval;
    - how the drafting of slice N+1 is triggered (a turn queued to the authoring agent on approval,
      or a flow step).
