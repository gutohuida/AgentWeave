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
| `exploring` | creation | `approved` (Approve, operator only); `archived` only if it produced no requirements and no tasks |
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
| `facts` | Optional. The vault facts the requirement rests on, by id (`fct-` and 12 hex characters). Left out when nothing in the vault backs it. Raises no warning when empty. |

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
- `criteria_unconfirmed`: an acceptance criterion with no current confirmation (see below);
- a payload that does not validate.

**Gaps** are listed, and *approve anyway* records them as overridden:

- a MUST or SHALL requirement with no criterion;
- `criterion_without_check`, a criterion with no `how_to_check` and no `checked_by`;
- `no_acceptance_drive`, where the first task is not a failing end-to-end check;
- a requirement no task serves and no accepted evidence verifies;
- `steps_skipped`, empty non-goals, unresolved questions, unreviewed amendments;
- `pre_mortem_unanswered`: the newest written pre-mortem has findings nobody answered. A document with
  no pre-mortem, or with every finding answered, does not report it, and the save's
  `ready_to_approve` is false while it stands.

A gap can be **acknowledged** with a reason (`acknowledge_spec_gap`, or from the approval
refusal). The record holds `code`, `where`, `reason`, who and when, and lasts only while a gap with
the same `code` and `where` is still reported. It is shown apart from the open gaps and counts as
handled for readiness. `amendments_unreviewed` and `vault_warning` are the operator's to clear and
are never acknowledged by an agent.

## Pre-mortem

A manager job (**Project settings → Manager → Pre-mortem**) that reads a change's drafted
requirements and criteria and the code, assumes the change shipped and failed, and records how.
Each firing ends *written*, *nothing to do*, or *failed*, and one per document runs at a time.

- Automatic firing happens only for a document with no completed firing (written, or nothing to do),
  when it leaves the acceptance step (`acceptance`, or `requirements-and-acceptance`). After that,
  only **Run a pre-mortem** runs it.
- The findings of the newest written firing are the ones to answer. The author answers one finding,
  or all unanswered, with a required note (`answer_pre_mortem`); the answer names the firing, and an
  answer for any other firing, or from a profile that did not write the document, is refused.
- It is shown at the end of the **Document** tab and on the spec page, never in the Builds tab.

## Possible backing facts

The spec vault check names, in the same call that finds conflicts, the facts that possibly back each
requirement. The newest firing for a document is its current list, and an entry is not shown once
its requirement's statement differs from the one it was judged against. The full spec page shows
them as possible and not confirmed; the conversation's side panel does not. They never raise a
cited-fact warning and never count as a fact the requirement lists.

## Criterion confirmations

Each acceptance criterion needs a current confirmation before approval (`criteria_unconfirmed`).
`confirm_acceptance_criteria` records one per criterion as `new` or `guard`, and the kind must agree
with the criterion's `guard` flag. A confirmation is tied to the criterion's text and flag, so
rewording it or changing the flag voids it. Confirming is allowed while the document is exploring,
and is refused on an approved document until you reopen it. It is all or none: one refused entry
records nothing.

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
