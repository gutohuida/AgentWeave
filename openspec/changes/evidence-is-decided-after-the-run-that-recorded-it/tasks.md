## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R1: explore and propose (2026-09-24, bundle B5)
- [ ] 0.2 R2: an independent re-derivation against `requirement_evidence.py` (`record`, `duplicate_of`, `decide`, `restamp_run_footprints`), `run_liveness.py`, `agent_trigger.py`'s finalize order, both decision routes and both record routes. In particular: is the registry entry really popped only after the restamp commit (re-read `_execute_run` and the app-server path); does D2's digest guard agree with `requirement_coverage`'s staleness; answer design Open Question 2
- [ ] 0.3 R3: a second independent re-derivation, not starting from R2's notes. `openspec validate evidence-is-decided-after-the-run-that-recorded-it --strict` passes
- [ ] 0.4 The operator approves (APPROVALS.md)

## 1. Tests first — each fails on today's code unless marked as a control

New file `hub/tests/test_evidence_waits_for_its_run.py`. Stage liveness the way `test_approval_waits_for_the_turn.py:50-120` does (a stand-in session in `run_liveness.active_ptys`, popped in a finaliser). Reuse `builder`, `make_repo`, `make_document`, `record_as_agent` from `test_conflict_refusal_names_what_clears_it.py`.

- [ ] 1.1 (D1) An agent records evidence under a run registered live. The operator's `POST /spec/evidence/{id}/decision {"decision":"accepted"}` answers **409** with `code == "recording_run_live"` and the run id in the message; `GET /spec/evidence/{id}/reviews` is empty; `review_state` is `awaiting`. FAILS today (200, accepted)
- [ ] 1.2 (D1) The same on the agent plane: a second agent granted `can_accept_evidence` decides it → 409 `recording_run_live` (not 403). FAILS today
- [ ] 1.3 (D1) Pop the registry entry, decide again → 200 and one review. Control for the "clears by itself" half; passes before and after
- [ ] 1.4 (D1) Control: a run whose row says `running` but is not in the registry → the decision is recorded. Passes before and after (it is what every existing decision test stages)
- [ ] 1.5 (D1) Ordering: with the run live and an ungranted agent deciding → 403 `acceptance_not_granted`, not 409; with `decision: "maybe"` → 422. Pins D1's placement
- [ ] 1.6 (D4) `GET /spec/requirements/FR-1?document=…` while live: the evidence row has `recording_run_live: true`; after popping, `false`. FAILS today (key absent)
- [ ] 1.7 (D2) Record FR-1 twice from the same live run with different summaries and nothing committed between: the second answers **200** with the first's id, `revised: true`, and the second summary; exactly one `RequirementEvidence` row exists. FAILS today (409 `duplicate_evidence`)
- [ ] 1.8 (D2) Control: two different runs of the same agent at the same commit → the second is still refused `duplicate_evidence`. Passes before and after
- [ ] 1.9 (D2) Reword the requirement between the two records of 1.7 → the second creates a new row. FAILS today (duplicate refusal)
- [ ] 1.10 (D3) 1.8's refusal message does not contain `commit it first`; an operator-recorded duplicate's still does. FAILS today on the first half
- [ ] 1.11 Run `test_requirement_evidence.py`, `test_conflict_refusal_names_what_clears_it.py`, `test_approval_waits_for_the_turn.py`, `test_review_briefing_names_the_evidence_gate.py` before group 2 and record the counts

## 2. The fix

- [ ] 2.1 (D1) `requirement_evidence.decide`: the liveness refusal after the value check, before the grant check. Import `run_liveness` at module scope (it imports only `db.models` and `pty_runner`; confirm no cycle)
- [ ] 2.2 (D2) `record`: the same-run, awaiting, same-digest revise branch; return a marker the routes read (a `revised` attribute set on the instance, or a small result type — R2 picks)
- [ ] 2.3 (D2) `agent_actions.record_evidence`: 200 with `revised: true` when revised; still broadcasts `spec_updated`
- [ ] 2.4 (D3) The agent sentence in the duplicate refusal
- [ ] 2.5 (D4) `_evidence_view` and the agent-plane record response gain `recording_run_live`
- [ ] 2.6 `mcp_server.py`: `record_evidence` docstring says a same-turn re-record revises; `decide_evidence` docstring names `recording_run_live` and says to decide after the run ends. Read `.claude/rules/mcp-server.md` first (stdlib + fastmcp only)
- [ ] 2.7 Group 1 passes; the 1.11 counts are unchanged except the tests this change moved; ruff, black `--target-version py311`

## 3. Drive

- [ ] 3.1 On a trial Hub (`:8010`, from source), one Haiku turn records evidence and, mid-turn, the operator decides it through the route: record the 409 body verbatim. After the run ends, decide again: 200
