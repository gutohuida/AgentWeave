## 0. Rounds and decision

- [x] 0.0 R1: interactive explore with the operator (2026-09-25; decisions marked *(operator)*) and this proposal
- [ ] 0.1 R2: independent re-derivation against `spec_payload.py`, `spec_completeness.py`, `spec_service.py` (propose, save, rerender), `spec_lifecycle.py`, `api/v1/spec.py` (`set_phase`, `GET`), `spec_tasks.py`, `api/v1/jobs.py` (`create_job`), `launchability.py`, `api/v1/agents.py` (duties, open-document block, tool prose), `mcp_server.py` (`submit_spec_document`)
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-document-says-how-it-will-be-built-and-approval-starts-it --strict` passes
- [ ] 0.3 The operator confirms or replaces D5b (approve-time agent choice for a stale delivery)
- [ ] 0.4 Build only after `a-flow-is-configured-from-its-own-tab`, `a-document-moves-forward-only-through-its-checks` and `a-loop-that-is-gone-lets-go-of-its-document` are in the tree; stop and log if not

## 1. Tests first — `hub/tests/test_a_document_says_how_it_will_be_built.py`

- [ ] 1.1 Payload: `delivery` absent validates (old documents); `{"mode": "flow", ...}` and `{"mode": "none"}` validate; `mode: "maybe"` and an unparseable `cron` are refused
- [ ] 1.2 Propose a change-spec with no `delivery`: refused, `delivery_unanswered` in `blocking`. FAILS today (proposes). A flow without agent, and one without a stop condition: `delivery_flow_incomplete`. `{"mode": "none"}`: proposes
- [ ] 1.3 Approve a document proposed with no `delivery` (fixture seeded the old way): approved, tasks created, no loop, report says "No delivery was declared". With B5 landed this is the test that fails if D4's approval-time exclusion is missing
- [ ] 1.4 Approve with a flow delivery: one `AIJob` + `Loop` with `spec_document_id` = the document, `agent` from delivery, name = title, the document's tasks carry `loop_id`, `next_run` is the next cron boundary, and no run was started. `allow_agent_jobs` is 0 in the fixture. FAILS today
- [ ] 1.5 Approve with an archived delivery agent and no override: document `approved`, tasks created, no loop, report carries the 400 sentence. With `delivery_agent: "dev"`: loop names dev, the file's `delivery.agent` is unchanged, the report records the replacement. With `delivery_agent: ""`: no flow
- [ ] 1.6 Approve when another unarchived loop already claims the document: approved, report carries the 409 claim sentence
- [ ] 1.7 Board failure: patch `materialise` to raise after a flush; approval still commits, report `failed` is set. Mutation: remove the savepoint and watch this test fail (500 or rollback)
- [ ] 1.8 Report content: `already_served` keys and an unresolvable `depends_on` appear; `GET /spec` returns `approval_outcome`; `set_phase` returns it
- [ ] 1.9 `GET /spec` `delivery_status`: ok / stale-archived / stale-unknown / none / absent; not computed for approved documents; the file's digest is unchanged by reads
- [ ] 1.10 `create_job_record` extraction: every `POST /jobs` refusal keeps its status and detail (run the existing jobs tests unchanged; add one asserting the operator path still skips `allow_agent_jobs`)
- [ ] 1.11 Interview text: a new pin in `test_spec_turn_notice.py` and `test_exploring_interview_medium.py` for the delivery question; the existing pins still pass. The open-document block lists open agents in a single-agent project. FAILS today
- [ ] 1.12 `submit_spec_document(delivery=...)` round-trips through MCP and through the HTTP route; `test_tool_surface_matches_server.py` passes

## 2. Backend

- [ ] 2.1 `Delivery` model and `SpecPayload.delivery` (D1)
- [ ] 2.2 Completeness codes (D4); the approval-time exclusion in B5's `phase_blockers`
- [ ] 2.3 Interview text and roster line (D2); `mcp_server.submit_spec_document` + HTTP prose (D3), following `.claude/rules/mcp-server.md`
- [ ] 2.4 `spec_render` Delivery section; `GET /spec` `delivery_status` (D5)
- [ ] 2.5 `jobs_service.create_job_record` + `JobCreateRefused`, the route rewired to it (D6)
- [ ] 2.6 `materialise_quietly` savepoint + `MaterialiseOutcome` (D7)
- [ ] 2.7 `set_phase`: `PhaseRequest.delivery_agent`; flow in a savepoint; report event; scheduler hand-off after commit; `approval_outcome` in the response and in `GET /spec` (D6, D7)

## 3. UI

- [ ] 3.1 `api/spec.ts` types: `delivery_status`, `approval_outcome`, `delivery_agent` on the phase mutation
- [ ] 3.2 `SpecPhaseBar.tsx`: stale strip with the agent/No flow select, sent with Approve (D5, D5b)
- [ ] 3.3 `SpecApprovalReport.tsx` in `SpecDocumentPanel.tsx`; renders nothing when `approval_outcome` is absent (the `:8000` skew); offers change 1's Start a flow… when no flow was made
- [ ] 3.4 Vitest: the strip appears only for `stale`; Approve sends the chosen `delivery_agent`; the report lists problems and shows Start a flow… only when no flow exists
- [ ] 3.5 `npm run lint`, `npm test`; `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together, with section 2

## 4. Verify

- [ ] 4.1 Full `hub/tests/` with `claude` stripped from PATH; the CLAUDE.md lint block
- [ ] 4.2 Drive on a throwaway Hub (fresh profile, free port, Haiku on real turns, never `:8000`/`:8010`, no job left enabled): explore a small document with a real Haiku author and check that it asks how the work will be built; propose; archive the named agent and see STALE; approve choosing another agent; see the flow, its next run, and the report
- [ ] 4.3 Reconcile the three deltas into `openspec/specs/`; archive
