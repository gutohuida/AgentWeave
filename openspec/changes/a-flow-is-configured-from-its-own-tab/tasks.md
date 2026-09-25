## 0. Rounds and decision

- [x] 0.0 R1: interactive explore with the operator (2026-09-25; decisions marked *(operator)* in design.md) and this proposal
- [ ] 0.1 R2: independent re-derivation against `schemas/jobs.py`, `api/v1/jobs.py` (PATCH, `LoopSummary`, `_pending_loop_edit`), `scheduler.py` (`_stage_pending_loop_edit`, busy guard, `decide_firing`), `LoopTab.tsx`, `SpecPhaseBar.tsx`, `api/jobs.ts`, `api/loops.ts`
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-flow-is-configured-from-its-own-tab --strict` passes
- [ ] 0.3 Build only after B10's `a-loop-is-stopped-archived-and-delegated-from-its-own-tab` is in the tree (design, Risks); stop and log if it is not

## 1. Tests first — `hub/tests/test_a_flow_is_configured_from_its_own_tab.py`

- [ ] 1.1 PATCH `{"agent": "B"}` on a loop whose job names A: 200, `job.agent` still `A`, `loop.pending_agent == "B"`, `pending_edit.agent == "B"`, a `loop_edit_staged` event whose `changes` include `agent`. FAILS today (422)
- [ ] 1.2 The next firing applies it: after `_stage_pending_loop_edit`, `job.agent == "B"`, `pending_agent` is null, `loop_edit_applied` carries `agent`. FAILS today
- [ ] 1.3 While `pending_agent` is set and A's firing is running, `POST /jobs/{id}/run` is refused busy (the guard still asks about A). Mutation: apply the agent immediately in the PATCH and watch this test fail
- [ ] 1.4 Unknown and archived agents: 400 with `_check_agent_exists`'s sentence, nothing staged
- [ ] 1.5 Plain resume-mode job with `last_session_id` set: PATCH `{"agent": "B"}` applies at once and clears `last_session_id`. FAILS today (422)
- [ ] 1.6 Tasks assigned to A and inbound entries queued for A are unchanged after the agent change is applied; `Checkpoint.loop_id` rows unchanged
- [ ] 1.7 `GET /loops` and `GET /loops/{id}` carry `spec_document_id` (a flow: its document; a plain loop: null). FAILS today
- [ ] 1.8 Migration test: upgrade adds nullable `loops.pending_agent` with rows preserved; downgrade removes it. Seed from a copy of `:8000`'s real `loops` DDL (read `mode=ro`)

## 2. Backend

- [ ] 2.1 `JobUpdate.agent`; in `update_job`, `_check_agent_exists`; staged on a loop (`pending_agent`, `pending_edit_actor/at`, event `changes`), immediate on a plain job with `last_session_id = None`
- [ ] 2.2 `Loop.pending_agent` + migration (next free number, `recreate="never"`, add-column only; follow `.claude/rules/` migration checklist)
- [ ] 2.3 `_stage_pending_loop_edit` applies `pending_agent` to the job; `loop_edit_applied` carries it; `_pending_loop_edit` reports it
- [ ] 2.4 `LoopSummary.spec_document_id` in `_batch_loop_summaries` and the detail view

## 3. UI

- [ ] 3.1 Establish how the spec page opens a loop tab (`ConversationView.tsx:360-373` is the loops index's route). Reuse it; do not add a second navigation. Record what you found in this task line
- [ ] 3.2 `useUpdateLoopSettings(jobId)` in `api/loops.ts`, invalidating loops and jobs; `LoopSummary.spec_document_id` in the TS type; `JobCreate.spec_document_id` in `api/jobs.ts`; `useSSE.ts` invalidates loops on `job_updated`
- [ ] 3.3 `LoopTab.tsx` Settings section (design D1): read view including default agent; Edit/Save sending changed fields only; read-only when ended or archived; the "creator control follows the agent" note when `control == "creator"`; the route's `detail` shown on a refusal
- [ ] 3.4 `StartFlowDialog.tsx` (design D5) and `SpecPhaseBar.tsx` Flow link / Start a flow… (design D4), approved change documents only
- [ ] 3.5 Vitest: Settings sends only changed fields (assert on the request body); an agent edit shows as pending, not as in force; the dialog's POST body has `spec_document_id` and `stop_when_queue_empties: true` and no `work_needs_evidence`; the phase bar shows the link when a loop in the `useLoops()` list (in the order `GET /loops` returns it) declares the document, and the button when only an archived one does
- [ ] 3.6 `npm run lint`, `npm test`; `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together, in the same commit as section 2 (the bundle needs the new fields)

## 4. Verify

- [ ] 4.1 Full `hub/tests/` with `claude` stripped from PATH; the CLAUDE.md lint block
- [ ] 4.2 Drive on a throwaway Hub (fresh profile, free port, never `:8000`/`:8010`, Haiku on any real turn, no job left enabled): start a flow from an approved document, change its cadence and agent from the tab, see the agent pending, let one firing apply it, see it in force
- [ ] 4.3 Tell the operator about the `:8000` skew (design, Risks) before the bundle commit; sync deltas and archive
