# Proposal — a pending proposal can be withdrawn

**Round 1, 2026-09-24** (bundle B6, from ROUNDS.md's single-finding row). Finding: **F213 (D)**,
re-verified on `404c7d5`: `propose_edit` diffs a submission against the **stored** document only
(`spec_service.py:290-399`), never against pending proposals, and there is no route that takes a
proposal out of the queue except accept and reject (`spec.py:590-694`). R1 also found a stale-row
defect on the same list, carried here because it shares the fix. It is filed as **F428** (reject), and
R2's twin as **F431** (an accept refused as stale). The operator's review of 2026-09-24
(`spec-queue/tracks/reviews/B6-2026-09-24.md` §5) added a MODIFIED delta, a retraction rule, a
guard against lost updates, and a digest-aware twin marker. **Nothing here is implemented yet.**

## Why

At `contract`/`gate` rigor a submission becomes one pending proposal per changed unit. Submitting
the same edit twice — a retry after a timeout, a double click, an agent that re-submits — proposes it
twice, because the second submission is compared with the stored document, which the first did not
touch. F213 measured it: 2 units submitted twice → 4 pending, `{fr-1: 2, fr-2: 2}`. The operator's
list shows identical pairs with nothing to tell them apart, and the only way to clear a twin is to
**reject** it, which records a judgement — *this edit is wrong* — that nobody made. (Pressing
**Accept** on the twin after its pair was accepted also removes it, by failing: `proposal_stale`
409, `spec_service.py:521-528`. That is an error message used as housekeeping.)

The same stacking happens when an agent **revises** its edit: v1 and v2 of one requirement both sit
pending. And it happens after every accept, because accepting one unit changes the document's
digest, which makes every sibling from the same submission stale on its next accept
(`test_accepting_a_second_proposal_against_the_same_digest_is_refused_as_stale`,
`test_spec_edit_proposals.py:190-217`); the agent's resubmission then stacks beside the stale ones.

**Found in R1 on the same list:** rejecting a proposal in the app leaves it on screen.
`reject_proposal_route` broadcasts nothing (`spec.py:669-694`; accept does, `:656-658`), and
`useRejectSpecProposal` goes through `useSpecMutation`, whose `onSuccess` invalidates only `specs`
and `specDocuments` (`api/spec.ts:244-256`), not `specProposals`. With `refetchOnWindowFocus: false`
(`main.tsx:8-15`), the rejected row keeps its Accept and Reject buttons until something else
refetches; pressing either answers 409 `proposal_not_pending`. `useSpecEvents`' comment claims the
reject route emits `spec_updated` (`api/spec.ts:163-166`); it does not.

## What Changes

- **A repeat is not proposed again.** A unit whose proposed content, change kind and position are
  identical to a pending proposal **from the same proposer** against the same document digest
  creates nothing; the response names the existing proposal under a new `already_pending` list.
- **A revision supersedes.** A different edit to the same unit from the same proposer creates the
  new proposal and marks the proposer's earlier pending ones for that unit **`superseded`**, naming
  the proposal that replaced them. Proposals from different proposers are never superseded by each
  other: they are alternatives, and choosing between them is the operator's.
- **A unit the proposer takes back is superseded too** (operator review). A submission is the
  proposer's whole document, so a unit it leaves as stored, or no longer mentions, supersedes that
  proposer's pending proposal for it. Without this, v1's `remove FR-3` stays pending after v2 restores
  FR-3, and accepting it deletes a requirement its proposer brought back.
- **A proposal leaves `pending` once** (operator review). Accept, reject, withdraw, supersede and the
  stale mark each move the row with a conditional `UPDATE … WHERE status = 'pending'` and check the
  row count, so of two racing decisions exactly one lands.
- **The operator can withdraw.** `POST /documents/{path}/proposals/{id}/withdraw` marks a pending
  proposal **`withdrawn`**, with an optional note, recording no judgement about its content. The
  proposals panel gains **Withdraw** beside Accept and Reject, and marks a pending proposal that is
  identical to an earlier one still pending (twins created before this change, or by two proposers)
  as *"same as the one above"*.
- **Reject and withdraw refresh the list.** Both routes broadcast `spec_updated`; both mutations
  invalidate `specProposals`. So does an accept refused as stale, which commits the row's move to
  `stale` and today leaves it on screen with live buttons (added in R2). The false comment in `useSpecEvents` becomes true.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-document-authority` — adds *"A proposal leaves the queue without a judgement when it is
  repeated, revised or withdrawn"*; modifies *"A document at contract or gate rigor gates edits
  behind an operator-accepted proposal"* (a repeat of a pending proposal from the same proposer is
  not recorded again).

## Impact

- `hub/hub/spec_service.py` — `propose_edit`/`_create_proposal` (repeat, supersede, retraction),
  `ProposeResult.already_pending`, new `withdraw_proposal`, and `_leave_pending` for every move out
  of `pending`.
- `hub/hub/api/v1/spec.py` — the withdraw route; reject broadcasts; `write_document_content` and
  `merge_document` return `already_pending` beside `proposals`.
- `hub/hub/api/v1/agent_actions.py:1671-1680` — the agent's submission response carries
  `already_pending`. The MCP `submit_spec_document` passes the route's body through; its docstring
  (`mcp_server.py:1809-1812`, which also tells an agent *"Submitting repeatedly is normal and expected"*, `:1801`) names `proposals`/`unchanged` and gains `already_pending`.
- `hub/ui/src/api/spec.ts`, `SpecProposalsPanel.tsx`; bundle refresh.
- No migration: `SpecEditProposal.status` has no CHECK constraint by design (`models.py:2138-2141`, the model docstring).
