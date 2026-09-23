# Design — evidence is decided after the run that recorded it

No operator decision governs this change. It is S12's F358 half; S12's F165/F166 half is
`a-footprint-names-the-line-of-work-its-commit-is-on`, which D12 does govern.

## What the code does today (HEAD `404c7d5`)

| Step | Where | What it does |
|---|---|---|
| record | `requirement_evidence.record`, `:97-191` | footprint read **before** the row (`_take_footprint`, `:248-296`), duplicate check (`duplicate_of`, `:194-245`), row written `awaiting` for an agent |
| decide | `requirement_evidence.decide`, `:677-737` | refuses a bad value (422), no grant (403), self-acceptance (403); otherwise appends `EvidenceReview` and sets `review_state` |
| re-point | `restamp_run_footprints`, `:905-997`, called from `_restamp_evidence_footprints` (`agent_trigger.py:1769-1801`) inside the finalize block that sets `run.status`/`ended_at` | every row the run recorded is re-pointed at the snapshot commit, **decided or not** (its docstring: "Every row of the run is re-pointed, whatever has since been decided about it") |
| liveness | `run_liveness.run_is_live`, `:69-71` | membership of `active_ptys`/`active_app_server_runs`; `_execute_run` pops its entry in a `finally` that runs **after** the finalize block (module docstring, `:22-28`) |

So the registry entry covers exactly the window in which a footprint can still change, and its
absence means the footprint is final. That is the same predicate the approval gate already uses for
the same reason (`requirement_gate._check_live_turn`, `:544-579`, F162).

## D1 — `decide` refuses while the recording run is live

```python
if evidence.run_id and run_liveness.run_is_live(evidence.run_id):
    raise EvidenceRefusedError(
        f"{evidence.id} was recorded by run {evidence.run_id}, which is still running. Its commit "
        "is re-pointed at the work when that run ends, so a decision now would judge a commit "
        "the Hub is about to replace. Decide once the run has ended.",
        code="recording_run_live",
        http_status=409,
    )
```

Placed **after** the value check and **before** the grant check: a malformed value is still 422,
and an ungranted agent is still told about the grant first (the grant does not clear with time; the
run does).

**Why refuse rather than accept and re-open.** The alternative is to let the decision stand and
reset it to `awaiting` if the re-point moves the commit. That rewrites a decision the append-only
rule (`requirement-traceability`: "Acceptance and rejection SHALL be recorded append-only") says is
never overwritten, and a reviewer who was told "accepted" would find it undone. Refusing costs a
wait that ends on its own.

**Registry, not `Run.status`.** A crashed Hub leaves `Run.status == "running"` until startup
reconciliation; reading the column would wedge decisions on every row that run recorded. The
registry fails open, as `run_liveness`'s docstring argues (`:8-13`).

**The operator is covered too.** The operator's decision is equally a judgement of a moving commit.
Both routes map `exc.http_status` already (`spec.py:916`, `agent_actions.py:1341`).

**What the routes return when a called function raises.** `decide` raising → 409 (this code), 403 or
422, nothing committed. After a successful decide, `integrate_what_was_waiting_for_this_evidence`
catches everything and rolls back (`task_integration.py:672-707`). Measured in R1 with a scratch
test that made `retry_integration` raise: `POST /spec/evidence/{id}/decision` answered **200** with
`review_state: accepted`, and the stored row read `accepted`. So a repository failure does not undo
or 500 the decision. Unchanged by this change.

## D2 — a re-record in the same run revises its own undecided row

In `record`, when `duplicate_of` returns a row `already` with `already.run_id == actor.run_id` and
`already.review_state == AWAITING`, update `already.kind`, `already.locator`, `already.summary`,
re-apply the footprint just taken (`_apply_footprint(session, already, taken, existing_footprint)`),
and return `already` with a `revised` marker for the route. Otherwise the refusal stands.

- Same run means same checkout, same task, same actor — and under D1 nobody can have decided it
  while the run is live. The `review_state == AWAITING` guard covers the one gap: a Hub restarted
  mid-run empties the registry, so a decision could have landed; such a row is refused as today.
- `digest` is **not** revised. If the requirement was reworded mid-turn, `duplicate_of` does not key
  on digest, so the row would move to a wording it was not recorded against. Instead: if
  `already.digest != requirement.digest`, do not revise — record a new row (the old one goes stale
  through the existing mechanism). R2 should check this against `requirement_coverage`'s staleness.
- Routes: `POST /agent-actions/spec/evidence` answers **200** (not 201) with the same body plus
  `"revised": true`. `POST /spec/evidence` (operator) never has a run, so never revises.

## D3 — the cross-run refusal names what clears it for an agent

For `actor.kind == "agent"` the last sentence becomes: *"If the work has changed since, record again
once it has: the Hub commits your changed checkout when this turn ends, and evidence recorded after a
change names the new commit."* Checked against the code, this is incomplete: a changed checkout still footprints
the turn-start commit **mid-turn**, so the second record in a *new* turn with uncommitted changes is
still a duplicate at record time. R1 does not have a clean answer for that sub-case; see Open
Question 2. The operator's sentence keeps *"commit it first"* — for them it is true.

## D4 — `recording_run_live` on the evidence view

`_evidence_view` (`spec.py:1108-1144`) gains `"recording_run_live": bool(evidence.run_id and
run_liveness.run_is_live(evidence.run_id))`. Registry lookup, no query. The operator routes that
return `_evidence_view` (requirement detail, list, record, decide) carry it. The agent-plane record
response (`agent_actions.py:1238-1245`) is its own dict and gains the same key; the agent-plane
list (`agent_actions.py:1247`) R2 should check.

## Open questions

1. **Retiring a superseded row across runs** (F358 cost 3). Options: (a) an author-only `withdraw`
   that appends a review with decision `withdrawn`, which coverage treats like `rejected` minus the
   "Rejected" wording; (b) leave it — the reviewer's rejection is the retire path. Recommended: (b)
   for this change; (a) as its own change if the operator sees it recur.
2. **The new-turn duplicate** (D3). A second turn with uncommitted changes meets the duplicate check
   at the turn-start commit, which the prior turn's evidence was re-pointed to. Options: (a) skip the
   duplicate check when the recording run's checkout is dirty (`task_integration.has_uncommitted_changes`
   on the footprint root) — the row will be re-pointed to a new commit anyway; (b) leave it. R1
   recommends (a), but has not checked whether a dirty checkout can be observed reliably from the
   record path on Windows (`_git` with a 15 s timeout per call). R2 decides.

## Round log

- **R1, 2026-09-24.** Re-verified F358 against `404c7d5`; measured the decide route's answer when
  integration raises (200, decision stands). Wrote D1-D4.
