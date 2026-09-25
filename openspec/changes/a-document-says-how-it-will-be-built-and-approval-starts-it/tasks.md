## 0. Rounds and decision

- [x] 0.0 R1: interactive explore with the operator (2026-09-25; decisions marked *(operator)*) and this proposal
- [x] 0.1 R2 (2026-09-25; design.md "Round 2"): independent re-derivation against `spec_payload.py`, `spec_completeness.py`, `spec_service.py` (propose, save, rerender), `spec_lifecycle.py`, `api/v1/spec.py` (`set_phase`, `GET`), `spec_tasks.py`, `api/v1/jobs.py` (`create_job`), `launchability.py`, `api/v1/agents.py` (duties, open-document block, tool prose), `mcp_server.py` (`submit_spec_document`); savepoint behaviour measured on this machine's SQLAlchemy/aiosqlite
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-document-says-how-it-will-be-built-and-approval-starts-it --strict` passes
- [ ] 0.3 The operator confirms or replaces D5b (approve-time agent choice for a stale delivery), and R2's choice that a `stop_at` already past at approval creates no flow (D6)
- [ ] 0.4 Build only after `a-flow-is-configured-from-its-own-tab`, `a-document-moves-forward-only-through-its-checks` and `a-loop-that-is-gone-lets-go-of-its-document` are in the tree; stop and log if not

## 1. Tests first — `hub/tests/test_a_document_says_how_it_will_be_built.py`

- [ ] 1.1 Payload: `delivery` absent validates (old documents); `{"mode": "flow", ...}` and `{"mode": "none"}` validate; `mode: "maybe"`, an unparseable `cron` and a `stop_at` with no timezone are refused. A document with no `delivery` renders byte-identically to today (the Delivery section is conditional)
- [ ] 1.2 Propose a change-spec with no `delivery`: refused, `delivery_unanswered` in `blocking`. FAILS today (proposes). A flow without agent, and one without a stop condition: `delivery_flow_incomplete`. `{"mode": "none"}`: proposes. A `roadmap` payload with no `delivery` gets neither code
- [ ] 1.3 Approve a document proposed with no `delivery` (fixture seeded the old way): approved, tasks created, no loop, report says "No delivery was declared". With B5 landed this is the test that fails if D4's approval-time exclusion is missing
- [ ] 1.4 Approve with a flow delivery: one `AIJob` + `Loop` with `spec_document_id` = the document, `agent` from delivery, name = title, the document's tasks carry `loop_id`, `next_run` is the next cron boundary, and no run was started. `allow_agent_jobs` is 0 in the fixture. A `job_created` event is persisted. A 300-character title yields a 256-character name, not a failure. FAILS today
- [ ] 1.5 Approve with an archived delivery agent and no override: document `approved`, tasks created, no loop, report says the agent is archived. The same with a name the project does not have, **including on a project with no `Agent` rows, and on one whose legacy `ProjectSession` lists the name** (both of which `_check_agent_exists` accepts): no loop, report says it is not on the project. With `delivery_agent: "dev"`: loop names dev, the file's `delivery.agent` is unchanged, the report records the replacement. With `delivery_agent: ""`: no flow. A flow delivery with no stop condition, and one whose `stop_at` has passed: approved, no loop, reported
- [ ] 1.6 Re-approval: approve (flow F created), reopen, propose, approve again: exactly one unarchived loop, the new tasks carry F's `loop_id`, and the report names F as already building the document, not as a refusal. Race: make the existing-flow lookup miss so `build_flow_rows` hits the claim: approved, the report carries the 409 claim sentence, and the response is 200, not the `MissingGreenlet` 500 R2 measured (nothing adopted inside the rolled-back savepoint is read). `delivery_agent` with `to=exploring`, or on a `mode: none` document: 400, phase unchanged
- [ ] 1.7 Board failure, two ways: a flush inside `materialise` raises `IntegrityError`; `materialise` raises `RuntimeError` after its first `session.add`. Both: approval commits, report `failed` is set, and **no task row of this document exists**. Mutation: remove the savepoint and watch the first fail with a 500 (`PendingRollbackError`) and the second leave a partial board
- [ ] 1.8 Report content: `already_served` names the skipped declared entry's key and its requirements; an unresolvable `depends_on` appears with its reason; `GET /spec` returns `approval_outcome` (the newest `approval_report` event, after two approvals); `set_phase` returns it. Update `test_spec_documents_api.py:564` (one event per approval becomes two) and add `"delivery": {"mode": "none"}` to the proposed change-spec fixtures in the seven files design.md names
- [ ] 1.9 `GET /spec` `delivery_status`: ok / stale-archived / stale-unknown / none / absent; not computed for approved documents or other kinds; reads leave the file's digest unchanged. Stale-unknown also for a name only legacy `ProjectSession` data knows, the case approval must agree with (1.5)
- [ ] 1.10 `build_flow_rows` extraction: every `POST /jobs` refusal keeps its status and detail (run the existing jobs tests unchanged). Add: a loop insert that hits the claim index leaves **no** job row. FAILS today: the job is committed first (`jobs.py:734`)
- [ ] 1.11 Interview text: new pins for the delivery line in `test_spec_turn_notice.py` (`kind="change-spec"`: present; `kind="roadmap"` and `kind=None`: absent, with `kind=None` byte-identical to today) and in the canonical context (change-spec exploring: present; roadmap exploring: absent). The existing pins still pass. The open-document block lists open agents in a single-agent project, and `### Team` is still absent there. FAILS today
- [ ] 1.12 `submit_spec_document(delivery=...)` round-trips through MCP and through the HTTP route; `test_tool_surface_matches_server.py` passes; `test_mcp_tool_schemas.py`'s `wanted` map gains `delivery: object`

## 2. Backend

- [ ] 2.1 `Delivery` model and `SpecPayload.delivery` (D1)
- [ ] 2.2 Completeness codes, gated on `payload.kind == "change-spec"` (D4); both codes added to B5's `phase_blockers` exclusion at `APPROVED`
- [ ] 2.3 Interview line and roster line in the open-document block, change-spec only; `spec_turn_notice(kind=None)`, and `_spec_phase_for` returning kind (D2). `mcp_server.submit_spec_document` + HTTP prose (D3), following `.claude/rules/mcp-server.md`
- [ ] 2.4 `spec_render` Delivery section, only when present; `delivery_agent_state`; `GET /spec` `delivery_status` (D5)
- [ ] 2.5 `build_flow_rows` in `api/v1/jobs.py` (flushes, never commits, raises `HTTPException`), and the route rewired to commit once (D6)
- [ ] 2.6 `materialise_quietly` savepoint + `MaterialiseOutcome` of plain values; the nested-savepoint precondition in its docstring (D7)
- [ ] 2.7 `set_phase`: `PhaseRequest.delivery_agent` (400 before the transition where it cannot be honoured); the existing-flow lookup; the not-created cases; flow in a savepoint; nothing read from ORM rows touched inside it after a rollback; report event. After the commit: scheduler hand-off, `job_created` broadcast and `persist_event`. `approval_outcome` in the response and in `GET /spec` (D6, D7)

## 3. UI

- [ ] 3.1 `api/spec.ts` types: `delivery_status`, `approval_outcome`, and `delivery_agent` on the phase mutation (sent only when chosen); `useSetSpecPhase` invalidates loops and jobs on success. `useSSE.ts`: `job_created` invalidates loops; `agent_archived`, `agent_unarchived` and `agent_created` invalidate the `spec` prefix
- [ ] 3.2 `SpecPhaseBar.tsx`: stale strip with the agent/No flow select, sent with Approve (D5, D5b)
- [ ] 3.3 `SpecApprovalReport.tsx` in `SpecDocumentPanel.tsx`; renders nothing when `approval_outcome` is absent (the `:8000` skew); offers change 1's Start a flow… only while change 1's lookup finds no unarchived flow declaring the document
- [ ] 3.4 Vitest: the strip appears only for `stale`; Approve sends the chosen `delivery_agent`, and none without a choice; the report lists problems in the fixture's order, which is the Hub's declaration order; Start a flow… shows when `useLoops` holds no unarchived loop for the document and hides when it does (fixture shaped as `GET /loops` returns it, change 1 D3)
- [ ] 3.5 `npm run lint`, `npm test`; `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together, with section 2

## 4. Verify

- [ ] 4.1 Full `hub/tests/` with `claude` stripped from PATH; the CLAUDE.md lint block
- [ ] 4.2 Drive on a throwaway Hub (fresh profile, free port, Haiku on real turns, never `:8000`/`:8010`, no job left enabled): explore a small document with a real Haiku author and check that it asks how the work will be built; propose; archive the named agent and see STALE appear without reloading; approve choosing another agent; see the flow, its next run, and the report; confirm the phase bar shows the flow, not Start a flow…
- [ ] 4.3 Reconcile the three deltas into `openspec/specs/`; archive
