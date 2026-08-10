# Roadmap — the specification program and the surfaces it lands on

**Date:** 2026-08-10
**Status:** structure agreed 2026-08-10. Both **[DECIDE]** items below are now **resolved** — see
each section.
**Purpose:** replace four overlapping plans with one sequence, so the same territory stops being
planned in three vocabularies.

> **Read this section and the change table. The rest is detail you can come back to.**

---

## Why this document exists

Four documents currently plan the same work:

| Document | Scope | State |
|---|---|---|
| `explorations/2026-08-03-specification-authority-technical.md` | Four "children": authority/identity → traceability/evidence → rigor/gates → authoring | Its stated prerequisite (directory-backed projects) **has shipped**. Never decomposed into changes |
| `changes/2026-08-07-spec-execution-coordinator/` | Six sections, 29 tasks | Gated skeleton, 0 done. Cluster 1 of its exploration is answered in `2026-08-10-coordinator-terms-and-format.md` |
| Umbrella `2026-07-30-hub-native-experience` §14 | 19 tasks, specification traceability and authoring | Untouched since 2026-07-30 |
| Umbrella §15 | 4 tasks, approval gates in the conversation | Untouched |

They largely agree, which is the problem — the overlap is invisible because the vocabularies differ.
§14 maps onto the 2026-08-03 children almost one-to-one (14.1/14.17 → child 1; 14.2–14.8 → child 2;
14.9/14.10 → child 3; 14.11–14.16 → child 4). §15 is that document's own "later integration." The
coordinator re-derives children 2 and 3 under new names.

**And a fifth concern arrived from live use:** the Spec screen is a second, older application
surface. That is not cosmetic — see Program A.

---

## The three programs

| | Program | What it is | Depends on |
|---|---|---|---|
| **A** | **Surface unification** | Remove the duplicate chat/layout implementation; bring every screen onto the one shell | Nothing. Ships first |
| **B** | **Specification and governance** | The differentiator: requirement identity, traceability, evidence, gates, authoring, and the coordinator | A1 for its authoring surface |
| **C** | **Task screen** | *Not a program.* Deliberately split — see below | — |

**Program C is split on purpose.** How the task board *looks* is Program A. What it *knows* —
requirements served, verification state, why a gate refused a completion — is Program B, changes B3
and B4, because those fields do not exist yet. Designing the task screen's traceability surfaces
before B3 defines them would be guessing.

---

## The change sequence

| # | Change | Absorbs / supersedes | Notes |
|---|---|---|---|
| **A1** | **One chat surface, one shell** | — (closes a live defect) | Delete `SpecChatPane`; mount the real `Composer`; add the shared `PaneResizer`; bring `components/spec/` onto current tokens. **Safe to build now: nothing in B can invalidate a deletion** |
| **A2** | **Shell conformance audit** | Umbrella §10.3's unfinished half | Audit every screen against `mock-full.html`; fix what drifted. Scope discovered by the audit, not guessed now. Includes the task board's chrome |
| **B0** | **aw-spec honesty repair** | §14.15 | The seeded charter cites six absent skills and a discovery mechanism that does not exist. Rewrites it to carry the judgment guidance directly. Small, urgent, independent |
| **B1** | **Task transition machine** | Coordinator §2, part of §3 | **Absent from all four plans as its own unit.** No spec format, no AI. Closes self-approval |
| **B2** | **Portable spec authority and identity** | 2026-08-03 child 1; §14.1, §14.17 | HTML stays authoritative (operator decision, 2026-08-10). Stable requirement IDs, semantic digest, file indexer |
| **B3** | **Traceability, evidence, and drift** | Child 2; §14.2–§14.8; coordinator §5 (part) | Task↔requirement links replace `Task.requirements` JSON |
| **B4** | **Rigor and completion gates** | Child 3; §14.9–§14.10; coordinator §3 | The completion gate lands in B1's transition service, not beside it |
| **B5** | **Spec authoring workspace** | Child 4; §14.11–§14.14, §14.16; the Spec screen's information architecture | Where the deferred Spec-screen layout work belongs — as the archived mock-alignment change already said it did |
| **B6** | **AI augmentation at named decision points** | Coordinator §4 | Last. Over a machine that already exists |
| **B7** | **Approval gates in the conversation** | Umbrella §15; coordinator §6 | Needs stable proposal, evidence-review and gate-decision identities from B3/B4 |

### Why B1 exists, and why it is early

It is the one piece of the coordinator that is valuable entirely on its own, and **no existing
document contains it as a unit.** The coordinator buries it under an AI question it does not need.

It requires no specification format, no evidence model, and no model call. It closes the hole
recorded in `hub/hub/api/v1/tasks.py:183-184` — a bare `task.status = body.status` reachable from
`update_task` in MCP, so an agent can approve its own work in one tool call.

A finding from cluster 1 that changes its shape: run attribution exists but is **overwritten**.
`updated_by_run_id` is a single mutable column, so the schema cannot distinguish the run that
completed a task from the run that approved it. B1 must therefore add an **append-only transition
record**; author/reviewer separation is not a check that can be bolted onto the existing columns.

### Why A1 is first, and is not rework

The Spec chat pane is not merely old-looking. `SpecChatPane.tsx` does not import `Composer`; it has
its own run-triggering path. Grepping it for `permission|question|checkpoint|Banner` returns nothing.

So on the Spec screen there are no permission cards, no `ask_user` question cards, no checkpoint
warnings — and no `@path`, `#skill`, `/model`, model picker, or drafts. An agent that calls
`ask_user` there blocks with nothing rendered; a `manual`-posture run hangs waiting for a card that
surface cannot draw.

Program B's entire authoring story — an agent proposing a requirement change, asking the operator to
clarify, requesting approval on a gate — runs through that pane. If A1 waits, each of those is built
against a surface that structurally cannot do operator-in-the-loop, and then rebuilt. **Deferring A1
causes the double-build it appears to avoid.**

### What is *not* in A1

The Spec screen's information architecture — where evidence sits beside a requirement, how proposals
render in position, what the pane structure becomes. That depends on data B2/B3/B5 create. It is
change B5.

**No visual mock is planned** (operator decision, 2026-08-10). The identity already lives in code —
`Composer`, `BannerStack`, `Button`, `Icon`, the token set — and composing from those inherits it,
where a new mock would be a second description to reconcile. Navigation inside the document is
already built and working: `specBridge.ts` does outline extraction (`toc-ready`), scroll spy
(`active-section`), `postScrollTo`, and path-allowlisted link resolution.

**One page of design does come first**, in B5: the **bridge interaction contract**. The iframe is a
security boundary — `sandbox="allow-scripts"`, no `allow-same-origin`, and `SpecFrame.tsx` notes
*"Message identity replaces origin checking."* Every chat↔document interaction adds a message type
to that boundary. The message set should be decided deliberately, not accreted while iterating.

---

## Two decisions

### [DECIDE #1] — the 2026-08-07 coordinator change — **RESOLVED 2026-08-10: retired**

Folded into this roadmap. The change directory is **deleted, not archived** — it never described
shipped behaviour, and an archived change reads as shipped (the same rule applied to the reverted
context-window variants on 2026-08-10).

What survives, and where:

| Coordinator content | Now lives in |
|---|---|
| Cluster 1 findings (1.1–1.4) | `2026-08-10-coordinator-terms-and-format.md` |
| §2 deterministic state machine | **B1** |
| §3 gates and evidence | **B3**, **B4** |
| §4 AI augmentation | **B6** |
| §5 spec/evidence/gate tools | **B3**, **B4** |
| §6 conversation integration | **B7** |
| Unanswered questions 1.5–1.13 | `2026-08-10-authoring-flow-without-skills.md`, final section — **still open, next to explore** |

### [DECIDE #2] — the 24 packaged skill templates — **RESOLVED 2026-08-10: decompose, then delete**

Neither of the two options originally offered here. The reasoning is in
`2026-08-10-authoring-flow-without-skills.md`; in short:

**`.claude/skills/` is a Claude-only mechanism, and AgentWeave is a multi-runner product.** A Codex
agent cannot invoke `aw-spec-propose` under any circumstances. Installing the templates would deliver
the authoring flow to half the product's agents while the seeded charter — which both runners
receive — instructs all of them to use it.

A skill file is three separable things, and each has a better home:

| Skill content | Goes to | Change |
|---|---|---|
| Procedure ("explore, then propose, then apply") | The coordinator's phase machine | B1 / B6 |
| Format contract (`html-spec-conventions.md`, 541 lines) | A Hub parser that validates and refuses | B2 |
| Judgment guidance (how to interview, what makes a requirement testable) | The **charter** — already shipped, runner-agnostic, operator-editable | B0 |

The 24 template files are deleted once each part has landed in its home — not because the content is
worthless, but because a markdown file in a Claude-specific directory is the wrong container for all
three things it holds.

**Consequences already folded into the table above:** B0 grows to rewrite the seeded `spec` charter;
B6 is reframed as *how the authoring flow works* rather than an optional augmentation; B2 must not
freeze the parse contract until B3/B4 have stated their requirements on it.

---

## What happens to the four documents

| Document | Disposition |
|---|---|
| `2026-08-03-specification-authority-technical.md` | **Retained as the technical design source** for B2–B5. Not superseded — this roadmap sequences it. Its four children become B2, B3, B4, B5 |
| `changes/2026-08-07-spec-execution-coordinator/` | **Retired and deleted** 2026-08-10. Contents redistributed — see [DECIDE #1] |
| Umbrella §14 | Marked superseded by B2–B5, per the umbrella's existing reconciliation rule (checkboxes stay unchecked; the successor's task list is authoritative) |
| Umbrella §15 | Marked superseded by B7 |

Umbrella §16 (closeout) cannot complete until B2–B5 and B7 are archived. That is a change in
expectation worth stating: **the `2026-07-30-hub-native-experience` umbrella is now the last thing to
close, not a thing to close soon.**

---

## Sequencing note

This program is gated on the operator's decision (2026-08-10) that **1.0 ships with the
differentiator** — spec traceability and governance — rather than deferring it to 1.1. That makes
B2–B4 release-blocking rather than post-release, and makes the length of this sequence the length of
the road to 1.0.

Two consequences worth recording now:

1. **CI still does not run on this branch.** `ci.yml` triggers only on push or PR to `master`, so the
   3-OS × 5-Python test matrix has never seen any of these 317 commits. Over a program this long
   that risk compounds. A one-line branch trigger fixes it without touching `master`.
2. **A1, A2, B0 and B1 are all independently shippable** and none depends on the specification format
   question. If the program needs to show progress before B2 lands, that is where it comes from.
