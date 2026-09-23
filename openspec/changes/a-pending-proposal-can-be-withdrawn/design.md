# Design — a pending proposal can be withdrawn

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
action. The comparison is in the route's order on purpose — "above" means earlier.

`SpecEditProposal['status']` gains `'withdrawn' | 'superseded'`.

### D5 — Reject and withdraw refresh every view

`reject_proposal_route` broadcasts `spec_updated {path}` after commit, as accept does. The reject,
accept and withdraw mutations invalidate `['project', pid, 'specProposals', path]` on success, so the
pressing tab does not wait for the SSE round-trip. The comment at `api/spec.ts:164-166` is then true.

### D6 — What each route answers when what it calls raises

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

### Round 1 — 2026-09-24 (B6 R1)

F213 re-verified by reading `propose_edit` and the three proposal routes. The reject-refresh defect
found by reading `spec.py:669-694`, `api/spec.ts:244-256` and `main.tsx:8-15`; not driven. The panel
test mocks the mutation (`specProposalsPanel.test.tsx:17`), which is why no test saw it.
