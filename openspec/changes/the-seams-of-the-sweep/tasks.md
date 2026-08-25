## 1. A run may only finish what it holds (F27, severity A)

- [x] 1.1 Review this group's spec deltas against the current code before writing anything — the standing method. Confirm `completed` is still reachable only from `in_progress` in `hub/hub/task_transitions.py`
- [x] 1.2 Add the claim-binds condition to `apply_transition` (`hub/hub/task_transition_service.py`) on the `-> in_progress` edge for a `run` actor: bind when the run holds nothing, refuse when it holds another task
- [x] 1.3 Add the holder-only condition on the `-> completed` edge for a `run` actor, requiring `run.task_id == task.id`
- [x] 1.4 Write both refusals to the `refusal_detail` standard — name what the run is bound to, and what would work
- [x] 1.5 Confirm the operator actor is unaffected on both edges
- [x] 1.6 Test: reproduce F27 exactly — an unbound run completing a second, unrelated task is refused
- [x] 1.7 Test: the full claim → work → complete path an agent finding waiting work would take still passes
- [x] 1.8 Test: the runtime binding path (`bind_run_to_task`) still starts a task, arriving already bound
- [x] 1.9 Run `py -3.11 -m pytest hub/tests/ -q` and account for every delta from the 3041-passed baseline
- [x] 1.10 Commit

## 2. Nothing is scheduled that can only fail or idle (F28, F33)

- [x] 2.1 Review this group's spec deltas against `hub/hub/api/v1/jobs.py`, `hub/hub/spec_tasks.py` and `hub/hub/scheduler.py`
- [x] 2.2 Back-fill `loop_id` when a loop claims a document, at the create site beside `_check_spec_document_conflict`, restricted to tasks with `loop_id IS NULL`
- [x] 2.3 Apply the same adoption at the loop-update site where a document claim can change
- [x] 2.4 **Withdrawn — see design D3.** `scheduler._loop_stall_reason` documents "never filled -> fire; the agent's job is to fill it" as a decision, and F28's flow only took that branch because `loop_id` was null. Adoption closes both halves; changing the firing would break the create-then-populate order
- [x] 2.5 Add the roster check to job creation, beside the existing cron validation, refusing an agent that does not exist
- [x] 2.6 **No subject — `JobUpdate` has no `agent` field,** so an update cannot change which agent a job names (`hub/hub/schemas/jobs.py:45`). Nothing to check
- [x] 2.7 Correct the fire-time message so "does not exist" and "has no runner bound" are distinct
- [x] 2.8 **Decided: no migration.** Adoption runs on any claim, including a re-claim by PATCH, so an already-broken flow repairs itself the moment the operator re-declares its document — a one-line operator action against a bug that has existed for days, versus a migration that rewrites task ownership rows on every existing database. `aw-sweep` is the only known instance
- [x] 2.9 Not applicable — no migration was added (2.8)
- [x] 2.10 Test: a flow created after its document is approved has a populated queue
- [x] 2.11 Test: a flow created before approval is unchanged, and tasks owned by another loop are not taken
- [x] 2.12 **Withdrawn with 2.4.** The behaviour is correct as it stands and is already covered by `test_loop_whose_tasks_are_all_completed_but_unapproved_spins` and `test_a_stalled_loop_queue_is_neither_claimable_nor_drained`
- [x] 2.13 Test: a job naming a missing agent is refused at creation; one naming a real agent is created
- [x] 2.14 Run the Hub suite; commit

## 3. Agents can see their limits and reach their tools (F32, F38, F21)

- [x] 3.1 Review this group's spec deltas against `hub/hub/api/v1/agents.py` around the capability section at ~1321
- [x] 3.2 Emit the withheld-capability section for evidence decisions, stating who holds the authority and where to put a verdict instead
- [x] 3.3 Audited. `GRANT_FIELDS` holds three grants; only `can_accept_evidence` appears in context at all. `can_read_checkpoints` and `can_recall` are announced in **neither** direction — recorded as **F39**, not fixed here: two of the three gate tools, so the general remedy is F21's territory rather than three more hand-written sections
- [x] 3.4 Test: context for an ungranted agent states the limit; context for a granted agent is unchanged
- [x] 3.5 Investigated. **The planned remedy already ships** — `record_evidence(` is named in every agent's context, pinned by `test_the_tools_are_named_to_every_agent_regardless`, and the agent's narration shows it had the name. The cause is deferred tool-schema loading in the spawned CLI (`runner_commands.py:224-236` passes `--mcp-config` + `--allowedTools`), which is that harness's behaviour, not the Hub's. Recorded in FINDINGS.md
- [x] 3.6 **Already true**, and therefore not the fix — see 3.5. Left open with the cause named rather than closed with a change that would not have prevented it
- [x] 3.7 Already covered by `test_the_tools_are_named_to_every_agent_regardless`
- [x] 3.8 Implement the state-only non-outcome record for F38: terminal run + no question written + deliverable did not advance
- [x] 3.9 Surface that outcome to the operator on the run
- [x] 3.10 State the expectation in advance in canonical context — for an unwritten document, ending without submitting or asking is not a valid outcome
- [x] 3.11 Test: the four F38 scenarios, including that prose is never the evidence
- [x] 3.12 Confirm nothing added here inspects agent prose, and that migration `0082`'s retired backstop is not reintroduced
- [x] 3.13 Run the Hub suite; commit

## 4. The tool with the largest payload gets a real refusal (F35)

- [ ] 4.1 Review this group's spec delta against `hub/hub/mcp_server.py`
- [ ] 4.2 Shape the document-submission tool's validation failure: name the field, the expected shape, and one minimal example
- [ ] 4.3 Keep `mcp_server.py` importing **only stdlib + fastmcp** — restate what is needed rather than importing it
- [ ] 4.4 Add the test asserting the restatement and the Hub's own contract agree, following the existing convention
- [ ] 4.5 Confirm `approve_tool_call` still has no return annotation
- [ ] 4.6 Test: a wrong-typed field and a missing field each produce a refusal naming the field and an example
- [ ] 4.7 Run the Hub suite; commit

## 5. The operator is told the truth (F31, F30, F34)

- [ ] 5.1 Review this group's spec deltas against `hub/hub/runner_events.py`, `hub/hub/launchability.py` and `src/agentweave/cli.py`
- [ ] 5.2 Narrow `_SECRET_VALUE_RE`'s high-entropy alternative to exclude `_` and `-`, leaving both credential prefixes untouched
- [ ] 5.3 Test both directions: the Hub's own tool names and minted slugs survive; prefixed and unprefixed credentials still redact
- [ ] 5.4 Key the launchability runner merge on `runner_id` rather than on `self_registered` (`launchability.py:353`)
- [ ] 5.5 Test the real invariant: the probe and the spawn describe the same runner for a self-registered bound agent
- [ ] 5.6 Test: an agent with no runner bound is told so, and no CLI is named after the agent
- [ ] 5.7 Thread the global `--port` as the subcommand default, with an explicit subcommand flag winning
- [ ] 5.8 Report a natively started instance as native rather than Docker
- [ ] 5.9 Make `doctor` examine the instance the project is bound to, and report unreachability as a failure rather than omitting it
- [ ] 5.10 Keep the CLI's own code importing nothing outside the stdlib
- [ ] 5.11 Run `py -3.11 -m pytest tests/ -q` for the CLI and the Hub suite; commit

## 6. Approval attaches to bytes, not to a path (F29)

- [ ] 6.1 Review this group's spec delta against `hub/hub/spec_lifecycle.py` and `hub/hub/spec_service.py`
- [ ] 6.2 Call `divergence()` on the single-document read path and mark the result, without refusing the read
- [ ] 6.3 Mark divergence for an agent reading through the tool surface
- [ ] 6.4 Populate the listing route's existing `divergence`/`diverged` fields; measure the per-document file-read cost and bound or defer that half if it shows
- [ ] 6.5 Test: a tampered approved document is served marked; an unmodified one reports no divergence
- [ ] 6.6 Run the Hub suite; commit

## 7. Doors with more than one key (F36, F37)

- [ ] 7.1 Review this group's spec deltas against `hub/hub/spec_tasks.py` (~375), `hub/hub/api/v1/tasks.py` and `hub/hub/spec_lifecycle.py`
- [ ] 7.2 Extract the dependency writer so the document path and the operator path share one implementation
- [ ] 7.3 Accept operator-declared dependencies on the task surface, naming task ids
- [ ] 7.4 Reject cycles and missing tasks in the shared writer, so both paths get the check
- [ ] 7.5 Test: an operator-declared dependency gates the dependent task; a cycle and a missing task are each refused; the document path is unchanged
- [ ] 7.6 Open `exploring -> archived` and `proposed -> archived`, guarded on nothing having been materialised
- [ ] 7.7 Test: an orphan archives and its drift warning clears; a document with materialised tasks is refused, naming what depends on it
- [ ] 7.8 Run the Hub suite; commit

## 8. Verification and close-out

- [ ] 8.1 Run the full Hub suite and the CLI suite; account for every delta from baseline (3041 passed locally, 3037 in CI)
- [ ] 8.2 If any UI changed: `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`, and commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 8.3 `AW_CHECK_UI_BUNDLE=1 py -3.11 -m pytest hub/tests/test_ui_build_stamp.py -q`
- [ ] 8.4 `npx openspec validate the-seams-of-the-sweep --strict`
- [ ] 8.5 Confirm CI is green on the pushed branch
- [ ] 8.6 Re-drive the affected sweep areas against the trial Hub on **8010** — areas 3, 7, 8, 11, 12, 13 and the spec-integrity path — and confirm each finding no longer reproduces. `proj-bacb623ca9ba` holds a live F28 and F37 reproduction
- [ ] 8.7 Record each finding's outcome in `scripts/drive/FINDINGS.md`, including any that did not reproduce as expected
- [ ] 8.8 Reconcile the change's outcome into `openspec/specs/` and archive it
