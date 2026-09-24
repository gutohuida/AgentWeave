## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation against `hub/hub/spec_service.py` (`propose_edit`, `_create_proposal`, `accept_proposal`, `reject_proposal`, `merge_document`), `hub/hub/api/v1/spec.py` (the three proposal routes, `write_document_content`, `merge_document`), `hub/hub/api/v1/agent_actions.py` (`submit_spec_document`), `hub/hub/mcp_server.py` (`submit_spec_document`'s docstring — read `.claude/rules/mcp-server.md` first), `api/spec.ts`, `SpecProposalsPanel.tsx`, `main.tsx`. Confirm the reject-refresh defect by a UI test with a real `QueryClient` rather than by reading
- [x] 0.2 R3: a second independent re-derivation (design round log). `openspec validate a-pending-proposal-can-be-withdrawn --strict` passes
- [ ] 0.3 The operator answers Open Question 1 (W3 recommended); record in `spec-queue/DECISIONS.md`. The orchestrator files the reject-refresh defect as a finding (R1 cannot write FINDINGS.md). Filed 2026-09-24 as F428, with F431 for the stale-accept path
- [x] 0.3a Operator review fixes applied (`spec-queue/tracks/reviews/B6-2026-09-24.md` §5): the MODIFIED delta on *"A document at contract or gate rigor gates edits behind an operator-accepted proposal"*, D2's retraction, D7 (a proposal leaves `pending` once), D4's digest rule; tests 1.10b, 1.14–1.17

## 1. Tests first — each must fail on today's code unless marked as a control

In `hub/tests/test_spec_edit_proposals.py` (its `_gate_document`, `_document`, `run_headers`):

- [ ] 1.1 (D1, F213) Submit the same edit twice through `AGENT`; `GET …/proposals` lists exactly the first submission's proposals; the second response's `already_pending` names their ids and its `proposals` is `[]`. FAILS today (4 pending, measured by F213)
- [ ] 1.2 (D2) Submit an edit to `alpha`, then a different edit to `alpha` from the same run: one pending proposal for `alpha`, the second; the first reads `superseded` with `resolution_reason` naming the second's id (read the row from the database, since the list shows pending only). FAILS today (two pending)
- [ ] 1.3 (D2) A second agent run (a different agent name) submits a different edit to `alpha`: both proposals pending. Control on the proposer boundary — PASSES today and must keep passing
- [ ] 1.4 (D1) Accept the `alpha` proposal of a two-unit submission; resubmit the same whole document: the metadata unit's old proposal (now stale-in-waiting, older digest) is `superseded` and a fresh one is pending; `already_pending` is empty (the digest differs). FAILS today (the old one stays pending)
- [ ] 1.5 (D3) `POST …/proposals/{id}/withdraw` → 200, `status: withdrawn`, `resolution_reason` is the note; the live document is byte-identical; the proposal is gone from the pending list; a second withdraw → 409 `proposal_not_pending`; an unknown id → 404. FAILS today (route absent)
- [ ] 1.6 (D3) `withdraw_proposal` with an agent actor raises `withdraw_is_the_operators`. FAILS today
- [ ] 1.7 (D5) Patch `hub.api.v1.spec.sse_manager.broadcast`: reject broadcasts `spec_updated` once; withdraw broadcasts once. FAILS today for reject
- [ ] 1.13 (D5, R2) Patch `hub.api.v1.spec.sse_manager.broadcast`; accept a proposal made stale by a sibling's accept → 409 `proposal_stale`, and `spec_updated` is broadcast once after the stale mark is committed. FAILS today (no broadcast on the refusal path)
- [ ] 1.14 (D2, review MEDIUM) Retraction: the stored document has `alpha` and `beta`. Agent run A submits a version without `beta` → a pending `remove beta`. The same agent then submits a version with `beta` exactly as stored → no new proposal for `beta`, and the `remove beta` row reads `superseded` with the retraction reason. The pending list no longer holds it, and accepting it by id → 409 `proposal_not_pending`; `beta` is still in the live document. FAILS today (the `remove` stays pending, and accepting it deletes `beta`)
- [ ] 1.15 (D2) Retraction by omission: run A submits a version adding `gamma` (not stored) → a pending `add gamma`; A's next submission drops `gamma` → the `add gamma` row is `superseded`. The same for the metadata unit: A proposes a new summary, then resubmits the stored summary → the metadata proposal is `superseded`. A proposal from another agent on `gamma` is untouched. FAILS today (both stay pending)
- [ ] 1.16 (D7, review MEDIUM) Lost update: load a pending proposal in session S1 (so S1 holds it as `pending`); in session S2 accept it through `spec_service.accept_proposal` and commit; then, still in S1, call `spec_service.reject_proposal` on S1's object and commit. The reject raises `proposal_not_pending`, and a fresh session reads `accepted`. Repeat with `withdraw_proposal`. FAILS today for reject (S1's attribute write turns `accepted` into `rejected`). S1 must hold no open transaction across S2's commit (the suite's pysqlite driver opens none for a `SELECT`); if S1's write is instead refused `database is locked`, restage until the pre-fix run shows the overwrite, and record it
- [ ] 1.17 (D7) The same staging for supersession: S1 has loaded the proposer's pending proposal (so the identity map holds it as `pending`); S2 accepts it and commits; S1 runs `propose_edit` with a revision of that unit and commits. The accepted row stays `accepted`, and the new proposal is pending. Today there is no supersession, so this passes; it is the guard that fails if D2 is built as an attribute write. Also the accept claim: S1 accepts a proposal that S2 has withdrawn and committed → 409 `proposal_not_pending`, and the document file is byte-identical (no write before the claim)
- [ ] 1.8 Control: the file's existing tests (including `test_accepting_a_second_proposal_against_the_same_digest_is_refused_as_stale` and `test_an_unchanged_resubmission_creates_zero_proposals`) pass before and after; record the count

UI, `hub/ui/src/__tests__/specProposalsPanel.test.tsx`:

- [ ] 1.9 (D4) **Withdraw** calls the withdraw mutation with `{path, proposalId}`
- [ ] 1.10 (D4, F190) A fixture of three pending proposals **in the route's order** (`created_at` ascending), the first and third identical and all three on one `expected_digest`: only the third carries `same as the one above`. Reversing the fixture moves the marker to the other row, so a component comparing against *later* rows fails this
- [ ] 1.10b (D4, review LOW) Fixture in the route's order: two pending proposals with identical unit and payload, the first with `expected_digest: 'd1'` and the second with `'d2'`. Only the **first** carries the stale-twin marker (*"same as the one below … would be refused as stale"*), and the second carries none. With both on `'d1'`, only the second carries *"same as the one above"*. FAILS today (no `expected_digest` in the view, and the marker is not built)
- [ ] 1.10c (D4) Backend: `GET …/proposals` rows carry `expected_digest` equal to the digest stored on the row. FAILS today (`_proposal_view` omits it)
- [ ] 1.11 (D5) With a real `QueryClient` and the real `useRejectSpecProposal` (mock only `postJson`/`getJson`), rejecting refetches the proposals query and the rejected row disappears. FAILS today (the row stays — the defect R1 found)

## 2. The fix

- [ ] 2.1 (D1, D2) `propose_edit`: one pending-proposals read; sameness and supersession, including retraction (the proposer's pending proposals the submission neither created nor reported in `already_pending`); `ProposeResult.already_pending`
- [ ] 2.1a (D7) `_leave_pending` (a conditional `UPDATE` with the row count checked, then `refresh`), used by the stale mark, accept (claimed after `validate_payload`, before `_apply_and_write`), reject, withdraw and supersede
- [ ] 2.2 (D1) `already_pending` in the responses of `submit_spec_document` (agent), `write_document_content`, `merge_document`; the MCP docstring names it and says a repeat is recorded once
- [ ] 2.3 (D3) `withdraw_proposal`; the route; `ProposalWithdrawal`
- [ ] 2.4 (D5) reject broadcasts; accept broadcasts after its stale-refusal commit; mutations invalidate `specProposals` on settled
- [ ] 2.5 (D4) UI: `useWithdrawSpecProposal`, the button, the twin marker (with D4's digest rule), the status union, and `expected_digest` on the type; `_proposal_view` sends `expected_digest`
- [ ] 2.6 Run group 1; `py -3.11 -m pytest hub/tests/ -q` full count inline; `npm run lint`, `npx vitest run`, `ruff`, `black` clean. `test_mcp_tool_schemas.py` / `test_tool_surface_matches_server.py` pass (a docstring change only)
- [ ] 2.7 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit source and bundle together

## 3. Drive it

- [ ] 3.1 On a trial Hub from source (never `:8000`): a `gate` document; a Haiku agent submits an edit; the same agent submits it again — one set of proposals, the response names `already_pending`; the agent revises one requirement — the old proposal is superseded. In the app: withdraw one; reject another in one window while a second window shows the list — both windows drop it. Screenshot each step
