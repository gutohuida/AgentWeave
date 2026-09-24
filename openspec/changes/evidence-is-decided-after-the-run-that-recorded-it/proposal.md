# Proposal — evidence is decided after the run that recorded it

**Round 1, 2026-09-24** (bundle B5, spec track S12). Finding: **F358 (B)**. Re-verified on HEAD
`404c7d5` (worktree `ce086b6`): still open. Nothing here is implemented.

## Why

An agent records evidence **during** its turn. At that moment its work is uncommitted, so the
footprint names the commit the turn started from. The Hub corrects it when the run ends:
`snapshot_worktree` commits the work and `restamp_run_footprints`
(`hub/hub/requirement_evidence.py:905-997`) re-points every row the run recorded, inside the same
finalize transaction that marks the run ended (`hub/hub/api/v1/agent_trigger.py`, the `if run:`
block that calls `_restamp_evidence_footprints`, `:1769-1801`).

`decide` (`requirement_evidence.py:677-737`) checks the decision value, the grant and self-acceptance.
It does not check whether the recording run is still running. So a reviewer can judge a row whose
commit the Hub is about to replace. F358 measured this on LoopEngine: `tester` rejected three rows
as unverifiable on the turn-start commit `d4f5eda`; six seconds later the rows named the snapshot
`880f47c`, and every rejection's reason now contradicts the row it sits on. One review round lost.

F358 names two more costs, both from the same window:

- **The duplicate refusal contradicts the briefing.** An agent that revises its work and re-records
  in the same turn meets `duplicate_of` (`requirement_evidence.py:194-245`): same requirement, task,
  actor and — because nothing is committed yet — the same turn-start commit. The refusal
  (`:146-152`) says *"if the work has moved on, commit it first"*. The briefing says *"You do not
  need to `git commit` your own changes"* (`hub/hub/launchability.py:441`). Measured three times.
- **A superseded row its author cannot retire.** The refusal's other remedy is *"say so on that
  piece"*, which an author cannot do. Reviewers spent rejections retiring rows.

## What Changes

- **A decision waits for the recording run** (design D1). `decide` refuses, with a new code
  `recording_run_live` and HTTP 409, while `run_liveness.run_is_live(evidence.run_id)` is true. The
  sentence names the run and says the refusal clears itself when the run ends, because that is when
  the footprint is final. Both decision routes (`api/v1/spec.py:892`, `api/v1/agent_actions.py:1309`)
  already map `exc.http_status`; they need no new branch.
- **A re-record in the same live run revises the undecided row** (design D2). Where a matching row
  recorded **by the same run** exists (looked up by run, not taken from `duplicate_of`'s oldest match), `record` updates that row's `kind`, `locator` and
  `summary` in place and re-reads its footprint, and answers with the same id and `revised: true`,
  instead of refusing. Under D1 such a row cannot have been decided, so nothing judged is rewritten.
- **The cross-run duplicate refusal stops telling an agent to commit** (design D3). For an agent the
  remedy names what does clear it: record again after the work has changed, because the Hub commits
  a changed checkout when the turn ends. The operator's sentence is unchanged.
- **The views say a row is still being recorded** (design D4). `_evidence_view` gains
  `recording_run_live: bool`, so a screen can hold its decision controls instead of learning from a
  409.
- **A changed checkout in a new turn is not a duplicate** (design D5, R2). On the duplicate path only,
  an agent whose run's own task or agent checkout holds uncommitted changes records a new row, which
  the end-of-turn snapshot re-points at a new commit. Review checkouts and the project checkout keep
  the refusal.
- **An agent held from a decision is woken when the run ends** (design D7, operator review
  2026-09-24, decision 2). `decide` remembers each agent it refuses `recording_run_live`; right after
  the run's registry entry is popped, the Hub queues each one a short note (new queue origin
  `evidence`, one migration) in the conversation it was refused in. The refusal also names stopping
  the run as a remedy, and a same-run revision bumps `produced_at`.
- **A decision is answered as recorded when the merge after it fails** (design D6, R3; **F426**). Both decision
  routes answer **500** today when integration waiting on the evidence raises — the wrapper's
  rollback expires the rows the response is built from (measured). They build the response first.

## Out of scope

- Retiring a superseded row from an **earlier** run (F358's third cost, cross-run). It needs a
  withdrawn state that coverage would have to learn; recorded as design Open Question 1.
- The operator screen for deciding (F215) — `the-coverage-bar-takes-the-evidence-decision-it-asks-for`,
  which renders this change's refusal and field.
- F359 (a failed run's footprints) is fixed; this change relies on its finalize path, not on it.

## Impact

- `hub/hub/requirement_evidence.py` (`decide`, `record`, `duplicate_of`'s caller)
- `hub/hub/api/v1/spec.py` (`_evidence_view`), `hub/hub/api/v1/agent_actions.py` (record response)
- `hub/hub/mcp_server.py` (`record_evidence` and `decide_evidence` docstrings) — loads
  `.claude/rules/mcp-server.md`
- `hub/hub/run_liveness.py` (the waiter notes), `hub/hub/api/v1/agent_trigger.py` (the wake after
  both registry releases), `hub/hub/inbound_queue.py` (the `evidence` origin)
- `hub/hub/db/models.py` and one migration at the next free revision (`evidence` in both queue-origin
  CHECK constraints) — loads `.claude/rules/db-migrations.md`
- `openspec/specs/requirement-traceability` (three ADDED requirements, one of them D7's)
- No UI change in this change.
