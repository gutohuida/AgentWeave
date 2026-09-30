# Design — a pending proposal can be withdrawn

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B6-2026-09-24.md` §5) approved this change
with fixes, and the operator approved it with the fixes applied ("What the operator decided"):

- **HIGH — an existing SHALL was contradicted with no MODIFIED delta.** *"A document at contract or
  gate rigor gates edits behind an operator-accepted proposal"* requires *"one pending, individually
  addressable proposal per changed unit"*, and D1 records nothing for a repeat. That requirement is
  now MODIFIED: *"… unless an identical proposal from the same proposer is already pending against
  the same document digest"*, with a scenario.
- **MEDIUM — a retraction left the retracted proposal pending.** A unit the proposer's newest
  submission leaves as stored goes to `unchanged` (`spec_service.py:357-358`; the metadata unit at
  `:394-395`), and nothing supersedes. So v1's `remove FR-3` stayed pending after v2 restored FR-3,
  and accepting it would delete a requirement its proposer had brought back. **D2 is extended**
  (retraction), with tests 1.14 and 1.15.
- **MEDIUM — an update could be lost between supersede and accept.** Status is written as a plain
  attribute, so the later commit wins whatever it read. **New D7:** every move out of `pending` is a
  conditional `UPDATE … WHERE id = :id AND status = 'pending'` with its row count checked, the shape
  `questions.py:444-457` already uses. Tests 1.16 and 1.17.
- **LOW — the twin marker could point at the wrong row.** It compared without `expected_digest`.
  `_proposal_view` now sends `expected_digest`, and among twins made against different digests the
  row with the **older** digest is marked (D4, test 1.10b).
- The change closes **F213**, **F428** (a reject leaves the row on screen) and **F431** (an accept
  refused as stale leaves the row on screen).

**Built on R1's recommended shape for F213, which ROUNDS.md titles "a pending proposal can be
withdrawn" without choosing the mechanism:** stop the repeat at its source, let a revision supersede,
and give the operator a withdraw that records no judgement (option W3 below). If the operator
chooses W1 only, drop D1/D2 and keep D3–D5; if W2 only, drop D3 and the Withdraw button.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

On `404c7d5`:

- `propose_edit` (`spec_service.py:290-399`) keys stored requirements by `key`, and for each
  submitted unit creates an `add`/`modify`/`remove` proposal when it differs from **stored**; the
  metadata bundle is one unit. `_create_proposal` (`:402-437`) stamps
  `expected_digest=document.content_digest`, `proposer_actor_kind`, `proposer_actor_name`,
  `proposer_run_id`. Nothing reads other pending proposals.
- `accept_proposal` (`:485-559`) refuses a non-pending one (`proposal_not_pending`), marks a
  proposal whose `expected_digest` no longer matches `stale` and refuses (`:521-528`), else writes.
  `reject_proposal` (`:562-584`) is operator-only and sets `rejected` + `resolution_reason`.
- Routes: list (pending only, `created_at` ascending, `spec.py:590-603`), accept (`:615-666`,
  broadcasts), reject (`:669-694`, **no broadcast**). The operator's own `PUT …/content`
  (`:470-532`) and `merge` (`:1638-1714`) can also return a `ProposeResult`; the agent's submission
  is `agent_actions.py:1618-1686`.
- UI: `SpecProposalsPanel.tsx` renders the pending list in the route's order, with Accept and a
  two-step Reject. Its mutations go through `useSpecMutation` (`api/spec.ts:244-256`), which does
  not invalidate `specProposals`; `useSpecEvents` does, on `spec_updated` (`:164-167`).

### The options

| Option | What | Breaks | Releases |
|---|---|---|---|
| W1. De-duplicate at submission | A repeat from the same proposer creates nothing; a revision supersedes the proposer's earlier one | Nothing an operator relies on; one more read per submitted unit | Stops F213's cause, and the post-accept restack |
| W2. Withdraw | A non-judgement exit for any pending proposal | Nothing | Clears twins already in databases (`:8000` may hold some) and abandoned proposals |
| **W3. Both** (recommended) | W1 + W2 | — | W1 alone leaves existing twins and cross-proposer duplicates with only Reject; W2 alone keeps creating the twins it then asks the operator to clear |

## Decisions

### D1 — A repeat creates nothing and says which proposal already holds it

In `propose_edit`, before creating a unit's proposal, read the document's pending proposals once
(one query per submission, keyed by `(unit_kind, unit_key)`). A pending proposal is **the same** when
`proposer_actor_kind`, `proposer_actor_name`, `change_kind`, `position_after_key`,
`proposed_payload` and `expected_digest` all equal what would be created. Then: no row;
`ProposeResult.already_pending` gains `{id, unit_kind, unit_key, change_kind}` of the existing one.
Every route that returns `proposals`/`unchanged` also returns `already_pending` (`spec.py` content
and merge routes; `agent_actions.py:1671-1680`).

`expected_digest` is part of sameness on purpose: a repeat against a document that has since moved
is not a repeat — the earlier proposal will be refused as stale, and the new one is the live one
(D2 then supersedes the earlier).

### D2 — A revision supersedes the same proposer's earlier proposals for that unit

When a proposal is created for `(unit_kind, unit_key)`, every other **pending** proposal on the same
document for that unit **from the same proposer** (`proposer_actor_kind` and `proposer_actor_name`)
becomes `superseded`: `resolved_at` now, `resolved_by_actor_name` the proposer's name,
`resolution_reason` *"superseded by <new id>"*. A proposal from another proposer is untouched — two
agents proposing different wordings are alternatives, and the operator chooses.

**A retraction supersedes too (operator review, MEDIUM).** A submission is the proposer's whole
document (`propose_edit` diffs every unit of it against stored), so it is that proposer's current
word on every unit. After the units are compared, every pending proposal on the document from the
same proposer is superseded **unless** the submission just created it or reported it in
`already_pending`. That covers three cases:

- a revision (a new proposal for the unit, above);
- a unit the submission leaves equal to stored. Today it only reaches `unchanged`
  (`spec_service.py:357-358`, and the metadata unit at `:394-395`). Example: v1 omitted FR-3 and
  created `remove FR-3`, and v2 restores FR-3;
- a unit the submission no longer mentions: v1 added `FR-new`, which is not stored, and v2 drops it.

A proposal superseded by a revision reads `resolution_reason` *"superseded by <new id>"*. One
superseded by a retraction reads *"superseded: the proposer's latest submission leaves this unit as
stored"*. Both are `superseded`, not `withdrawn`. The proposer took the edit back, and the operator
made no decision. The pending-proposals read of D1 already has every row this needs, so the rule adds
no query.

This does not violate *"Accepting or rejecting one proposal SHALL NOT alter the status of any other
pending proposal"* (`spec-document-authority/spec.md:1082-1086`): supersession happens at
submission, not at accept or reject.

### D3 — Withdraw

`spec_service.withdraw_proposal(session, proposal, *, actor, note="")` — operator only
(`withdraw_is_the_operators`), pending only (`proposal_not_pending`); sets `withdrawn`,
`resolved_at`, `resolved_by_actor_name`, `resolution_reason = note`. Route
`POST /documents/{path}/proposals/{proposal_id}/withdraw`, body optional `{note}` (`ProposalDecision`
has the shape minus `expected_digest`; a new `ProposalWithdrawal` with `note: str = ""`,
`max_length=2000`), 404 unknown proposal, 409 on refusal, broadcasts `spec_updated {path}` after
commit, returns `{proposal: view}`.

Operator only, like accept and reject (*"Accepting or rejecting a proposal is reserved to the
operator"*). An agent withdrawing its own proposal is not offered: a revision (D2) already replaces
it, and adding an agent-plane route and MCP tool for the rest is not asked for by any finding.

### D4 — The panel: Withdraw, and twins marked

`SpecProposalsPanel` adds **Withdraw** (tooltip: *"Take it off the list without judging it — for
duplicates and proposals nobody is pursuing"*). A pending proposal whose `unit_kind`, `unit_key`,
`change_kind` and `proposed_payload` equal an **earlier** row in the list (the route's
`created_at` ascending order) carries *"same as the one above"* and its Withdraw is the emphasised
action. The comparison is in the route's order on purpose — "above" means earlier. Payloads are
compared by a key-sorted serialisation, not `JSON.stringify` as returned: the column is JSON, and
two equal objects need not arrive with the same key order (R2).

**Which twin is marked depends on the digest (operator review, LOW).** `_proposal_view`
(`spec.py:562-578`) gains `expected_digest`, and the TypeScript `SpecEditProposal` type gains it too.
Twins with the **same** `expected_digest` are true duplicates, and the later row is marked *"same as
the one above"*. Twins with **different** digests were made against different versions of the
document. The one with the older digest is refused as stale when accepted (`spec_service.py:521-528`),
so **it** is marked: *"same as the one below, which was made against a newer version — this one
would be refused as stale"*. A proposal's `expected_digest` is the document's digest when it was
created, and the list is `created_at` ascending, so the older digest is the earlier row. Marking the
later row would steer the operator to withdraw the live proposal and keep the dead one.

`SpecEditProposal['status']` gains `'withdrawn' | 'superseded'`.

### D5 — Reject, withdraw and a stale accept refresh every view

`reject_proposal_route` broadcasts `spec_updated {path}` after commit, as accept does. The reject,
accept and withdraw mutations invalidate `['project', pid, 'specProposals', path]` **on settled**, not
only on success, so the pressing tab does not wait for the SSE round-trip.

**Added in R2 — the same defect on accept's refusal path.** An accept refused as stale **commits** the
row's move to `stale` before answering 409 (`spec.py:642-649`), and broadcasts nothing. The list is
pending-only, so that row should leave; today it stays, with live buttons, in the pressing tab
(`useSpecMutation` invalidates on success only) and in every other tab. So the accept route also
broadcasts `spec_updated {path}` after that commit, and the mutations invalidate on settled. The comment at `api/spec.ts:164-166` is then true.

### D7 — A proposal leaves `pending` once (operator review, MEDIUM)

Today every status move is an attribute write on a row loaded earlier in the request: the stale
mark (`spec_service.py:521-524`), accept (`:552`), reject (`:582`), and D2's supersede and D3's
withdraw as first designed. So a supersede committed after an accept of the same proposal turns
`accepted` into `superseded`, and withdraw and accept race the same way.

One helper, `_leave_pending(session, proposal, *, status, resolved_by, reason) -> bool`, issues

```
update(SpecEditProposal)
  .where(SpecEditProposal.id == proposal.id, SpecEditProposal.status == "pending")
  .values(status=…, resolved_at=now, resolved_by_actor_name=…, resolution_reason=…)
  .execution_options(synchronize_session=False)
```

then refreshes `proposal`, and answers `rowcount == 1`. This is the shape `questions.py:444-457`
already uses for the same race.

- **reject, withdraw, the stale mark**: `False` → `ProposalRefusedError(proposal_not_pending)`, naming
  the status the refreshed row now has. The accept route's refusal branch still commits (it now
  commits nothing new) and answers 409.
- **accept**: the claim to `accepted` is made **after** `validate_payload` and **before**
  `_apply_and_write`, so a lost race writes no file. A `SaveRefusedError` from `_apply_and_write`
  is answered 422 without a commit, as today, and the claim is discarded with the rest of the
  transaction. `resolution_reason` goes in the same `UPDATE`.
- **supersede (D2)**: `False` means someone decided the proposal in between. It is skipped silently:
  the decision stands, and the submission still succeeds.

On SQLite a request that loses the race can also fail with `database is locked` when it tries to
upgrade its read to a write. That is a 500 before its commit, and it too overwrites nothing. It is
not made worse here.

### D6 — What each route answers when what it calls raises

- Every decision route: losing D7's race → 409 `proposal_not_pending`, having written nothing.
- `withdraw`: refusal → 409 before any write; unknown → 404; database error → 500 before commit, no
  broadcast.
- Submissions (agent route, `PUT …/content`, `merge`): the extra pending-proposals read happens inside
  `propose_edit`, before any row is added; an error there is a 500 before commit, as any other
  database error in that path today.

## Goals / Non-Goals

**Goals:** a retry does not stack; a revision replaces its predecessor; the operator can clear a
proposal without a false judgement; a decided row leaves the list.

**Non-Goals:** changing D5's whole-document compare-and-swap, which is why siblings go stale after one
accept (noted for the operator in the bundle record; not a defect this finding names); an agent-side
withdraw; showing withdrawn/superseded history in the panel (the list route returns pending only).

## Risks / Trade-offs

- **Sameness is exact JSON equality.** A resubmission that reorders keys inside a requirement object
  compares equal (Python dict equality ignores order); one that changes whitespace in a statement
  does not, and supersedes instead — the right outcome either way.

## Open Questions

1. **W3 (recommended), W1 or W2?**

## Round log

### Operator review fixes — 2026-09-24

Applied the review's §5 at HEAD `d2b9c32`: the MODIFIED delta, D2's retraction, D7, and D4's digest
rule. The review cited `unchanged` at `:354-356` and `:376-378`; at HEAD those lines are
`spec_service.py:357-358` and `:394-395`, and are cited that way here. Also re-read: the stale mark
and the status writes (`:521-524`, `:552`, `:582`), `_proposal_view` (`spec.py:562-578`, no
`expected_digest` today), and the conditional-claim precedent (`questions.py:444-457`).

### Round 3 — 2026-09-24 (B6 R3)

Re-derived the accept route's refusal path (`spec.py:643-650`: commits on **every** `ProposalRefusedError`, so D5's broadcast there fires for `proposal_not_pending` too — harmless, an extra refetch) and the reject route (no broadcast). `SpecEditProposal.status` has deliberately no `CheckConstraint` (`models.py:2138`), so `withdrawn`/`superseded` need no migration. Nothing disagreed.

### Round 2 — 2026-09-24 (B6 R2)

Re-derived: `propose_edit`/`_create_proposal` (`spec_service.py:290-437`: diffs against stored
only, reads no pending proposal; stamps `expected_digest` and the proposer), `reject_proposal`
(`:562-584`), the list/accept/reject routes (`spec.py:588-694`: list is pending-only, `created_at`
ascending; reject broadcasts nothing; accept's stale refusal commits then 409s), `_proposal_view`
(`:562-578`, carries every field D4 compares), the agent response (`agent_actions.py:1671-1680`),
the MCP docstring (`mcp_server.py:1801`, `:1809-1812`), `useSpecEvents` (`api/spec.ts:163-167`,
the false comment). All of R1's claims held. Added: accept's stale-refusal path to D5 (task 1.13),
on-settled invalidation, key-order-insensitive twin comparison. Editing `mcp_server.py` loads
`.claude/rules/` for that file at IMPL.

### Round 1 — 2026-09-24 (B6 R1)

F213 re-verified by reading `propose_edit` and the three proposal routes. The reject-refresh defect
found by reading `spec.py:669-694`, `api/spec.ts:244-256` and `main.tsx:8-15`; not driven. The panel
test mocks the mutation (`specProposalsPanel.test.tsx:17`), which is why no test saw it.
