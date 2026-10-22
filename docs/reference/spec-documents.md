---
description: Specification document kinds, phases, rigor levels, coverage states, gaps and refusals — the exact vocabulary.
---

# Specification documents

The reference companion to the [Specifications guide](../guides/specifications.md).

## Kinds

| Kind | Created by | Notes |
|---|---|---|
| `change-spec` | operator or agent | The default for agents. Has requirements, acceptance criteria, tasks and a delivery. |
| `roadmap` | operator or agent | Ordered slices, each a change. Carries no requirements or tasks of its own. |
| `capability` | operator | Current behaviour. Created directly in phase `current`. Its content changes only by folding a change into it. |
| `system-map` | operator | Orientation and area maps. |

An agent may create only `change-spec` or `roadmap`. A document's kind is fixed at creation.

## Phases

| Phase | Reached by | Moves on to |
|---|---|---|
| `exploring` | creation | `proposed` (Propose); `archived` only if it produced no requirements and no tasks |
| `proposed` | Propose | `approved` (Approve); `exploring` (Reopen); `archived` as above |
| `approved` | Approve, operator only | `exploring` (Reopen for changes); `archived` (Archive, operator only) |
| `current` | creating a capability | `archived` (Retire, operator only, with a reason) |
| `archived` | Archive or Retire | nothing: archiving is permanent |

The phase lives in the Hub's database, not in the file, so editing the file cannot change it.

Archiving an approved change is refused while any task it declared is still open, and until it has
been folded into a capability. To archive without folding, state *no capability change* and give a
reason. Retiring a capability is refused while open tasks still serve its requirements.

## Journey steps and sizes

| Size | Steps |
|---|---|
| `fix` | intake → tasks → delivery |
| `small` | intake → requirements-and-acceptance → tasks → delivery |
| `large` | intake → requirements → acceptance → approach → tasks → delivery |

A project can define its own steps in a tracked `spec/journey.json`, or under **Project settings →
General → Spec steps**. Moving between steps is never refused for missing content. Skipped steps
show up as a gap at approval.

## Rigor

| Rigor | Agent edits | Task approval |
|---|---|---|
| `sketch` (default) | applied at once | not gated, except that rejected evidence always blocks |
| `contract` | pending proposals, one per requirement changed | unverified requirements reported |
| `gate` | pending proposals | refused while a served requirement is not `verified` |

Only the operator sets rigor. Raising it is refused for a document with missing, duplicate or
unparseable requirement identifiers. Lowering it is always allowed, needs a reason, and keeps all
links and evidence. Partial evidence (`covers: partial`) never verifies: `gate` refuses it, and
`contract` reports it.

## Requirements

| Field | Meaning |
|---|---|
| `key` | The author's own key, such as `tax-half-up-per-region`. |
| identifier | `FR-n`, minted by the Hub, stable across edits, never reused. Kept in the document's `aw_identity` block. |
| `modal` | `MUST`, `SHALL`, `SHOULD` or `MAY`. |
| `statement` | The requirement itself. |
| `rationale`, `party` | Why, and who it serves. |

**Acceptance criteria** are Given / When / Then scenarios that point at a requirement key. They can
carry `how_to_check` and `checked_by` (`agent` or `operator`).

## Coverage states

In precedence order. A requirement shows the first state that applies.

| State | Meaning |
|---|---|
| `drifting` | Files its accepted evidence watches have changed. |
| `amendment_unreviewed` | A tester changed one of its criteria, and the change is not yet reviewed. |
| `stale` | Evidence exists only for an earlier wording. |
| `evidence_awaiting_review` | Evidence recorded, not decided. |
| `verified` | Accepted evidence for the current wording. |
| `rejected` | Its evidence was rejected. |
| `in_progress` | A task serving it has started. |
| `not_started` | A task serves it, but has not started. |
| `unserved` | Nothing serves it. |
| `retired` | Removed from the document, with no linked work. |

Each coverage entry also carries **integration**: `integrated`, `not_integrated`, `unknown` or
`not_applicable`. It says whether verified work has reached the main branch.

## What approval checks

**Refusals** block approval even with *approve anyway*:

- `depends_on_unresolved`, `dependency_cycle`, `unknown_field`;
- `roadmap_not_approved`, `roadmap_slice_unknown`, `roadmap_without_slices`;
- a payload that does not validate.

**Gaps** are listed, and *approve anyway* records them as overridden:

- a MUST or SHALL requirement with no criterion;
- `criterion_without_check`, a criterion with no `how_to_check` and no `checked_by`;
- `no_acceptance_drive`, where the first task is not a failing end-to-end check;
- a requirement no task serves and no accepted evidence verifies;
- `steps_skipped`, empty non-goals, unresolved questions, unreviewed amendments.

## Evidence review states

| State | Meaning |
|---|---|
| `awaiting` | Recorded by an agent, not decided. |
| `accepted` | Accepted by the reviewer's approval, by you, or by a granted agent (never the recorder). |
| `rejected` | Rejected, with a reason. Blocks approval of tasks serving that requirement. |

Operator-recorded evidence is accepted on arrival. Only the operator can overturn a decided piece,
and must give a reason. Nobody can decide evidence while the run that recorded it is still live.

## Drift resolutions

A drift candidate is resolved by the operator as **specification updated**, **implementation
corrected**, or **no change required**.
