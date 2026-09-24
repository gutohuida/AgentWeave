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

Placed **after all three existing refusals** — value (422), grant (403), self-acceptance (403) —
immediately before the `EvidenceReview` is built (R2: R1 wrote "before the grant check", which would
answer an ungranted agent 409 and contradict R1's own reason and test 1.5). A malformed value is
still 422, and an ungranted or self-deciding agent is told the refusal that does not clear with time
first; only an otherwise-valid decision meets the wait.

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
re-apply the footprint just taken — `_apply_footprint(session, already, taken, existing_footprint,
outside_writes=await outside_writes_for_run(session, already.run_id))`. The `outside_writes`
argument is not optional here (R2): `_apply_footprint` writes the column on every mapping and `None`
means *not observed* (`requirement_evidence.py:392-429`), so omitting it would erase what
`capture_footprint` recorded at the first record (`:433-472`),
and return `already` with a `revised` marker for the route. Otherwise the refusal stands.

- Same run means same checkout, same task, same actor — and under D1 nobody can have decided it
  while the run is live. The `review_state == AWAITING` guard covers the one gap: a Hub restarted
  mid-run empties the registry, so a decision could have landed; such a row is refused as today.
- `digest` is **not** revised. If the requirement was reworded mid-turn, `duplicate_of` does not key
  on digest, so the row would move to a wording it was not recorded against. Instead: if
  `already.digest != requirement.digest`, do not revise — record a new row (the old one goes stale
  through the existing mechanism). R2 checked this against `requirement_coverage`: staleness is
exactly `item.digest == requirement.digest` (`requirement_coverage.py:192`, `:310`), so a revised row
keeping its old digest would still read stale, and one moved to the new digest would claim a wording
it was not recorded against — the guard is right.
- Routes: `POST /agent-actions/spec/evidence` (declared `status_code=201`, `agent_actions.py:1184`,
  so the revise branch returns a `JSONResponse(status_code=200)` explicitly) answers **200** (not 201) with the same body plus
  `"revised": true`. `POST /spec/evidence` (operator) never has a run, so never revises.

## D3 — the cross-run refusal names what clears it for an agent

For `actor.kind == "agent"` the last sentence becomes: *"If the work has changed since, record again
once it has: the Hub commits your changed checkout when this turn ends, and evidence recorded after a
change names the new commit."* R1 found this incomplete on its own: a changed checkout still footprints the turn-start commit
**mid-turn**, so a record in a *new* turn with uncommitted changes would still be a duplicate at
record time. **D5 closes that sub-case (R2)**, which makes the sentence true as written. The
operator's sentence keeps *"commit it first"* — for them it is true.

## D5 — an agent's changed checkout is not a duplicate of its committed state (R2, Open Question 2)

When `duplicate_of` finds a row and D2 does not revise it, and the actor is an agent, `record` asks
the footprint root once whether the checkout has uncommitted changes (`_git(root, "status",
"--porcelain")`, this module's own `_git`, 15 s timeout, `None` on failure). Changes present → no
refusal: the new row is recorded, and `restamp_run_footprints` re-points it at the snapshot the Hub
commits when the turn ends, which is a different commit from the earlier row's. Clean, or the
question fails → the refusal stands, as today.

- The git call runs **only on the duplicate path**, so an ordinary record costs nothing new.
- `requirement_evidence`'s own `_git` rather than a `task_integration` helper: `task_integration`
  imports this module, and the check is one command.
- **Only where the turn will be snapshotted.** `_execute_run` commits a dirty tree only for a run
  given an isolated workspace that is not a review checkout (`agent_trigger.py:1033`, `:1341`: a
  review turn and a turn in the project's own checkout pass `worktree=None`). Anywhere else the new
  row is never re-pointed and would be a real duplicate at the same commit — a reviewer's checkout
  dirtied by `.pyc` files is the observed case. So D5 applies only when the footprint root lies
  under `worktrees.task_root` or `worktrees.worktree_root` (`worktrees.py:153-188`), never
  `review_root` (`:207`) or the project root.
- Agents only. An operator's footprint may be a named commit (`_take_footprint`, F71), and their
  sentence still says to commit.
- Test 1.8 (the cross-run control) must stage a **clean** checkout; test 1.12 stages a dirty one.

## D4 — `recording_run_live` on the evidence view

`_evidence_view` (`spec.py:1108-1144`) gains `"recording_run_live": bool(evidence.run_id and
run_liveness.run_is_live(evidence.run_id))`. Registry lookup, no query. The operator routes that
return `_evidence_view` (requirement detail, list, record, decide) carry it. The agent-plane record
response (`agent_actions.py:1238-1245`) is its own dict and gains the same key; the agent-plane
list (`agent_actions.py:1248-1305`) spreads `_evidence_view` and inherits it.

## Risks

- **A reviewer that records its own evidence and then asks the operator to decide it** waits on
  `ask_user` while its own run is live, and the operator meets `recording_run_live` until the turn
  ends. The review briefing names only rows that exist when the turn starts
  (`review_turn.verdict_evidence_sentence`, `:178-235`), which were recorded by ended runs, so the
  product does not route anyone into this; D4's field lets a screen say why the decision is held.

## Open questions

1. **Retiring a superseded row across runs** (F358 cost 3). Options: (a) an author-only `withdraw`
   that appends a review with decision `withdrawn`, which coverage treats like `rejected` minus the
   "Rejected" wording; (b) leave it — the reviewer's rejection is the retire path. Recommended: (b)
   for this change; (a) as its own change if the operator sees it recur.
2. **The new-turn duplicate** — **decided by R2: (a), written as D5.** One `git status --porcelain`
   on the duplicate path only; a failed call keeps today's refusal, so the fallback is the safe one.

## Round log

- **R1, 2026-09-24.** Re-verified F358 against `404c7d5`; measured the decide route's answer when
  integration raises (200, decision stands). Wrote D1-D4.
- **R2, 2026-09-24.** Re-derived: the registry entry is popped after the restamp on both transports
  (`agent_trigger.py:2461` then `finally` `:2706`; `:3134` then `finally` `:3250`) — holds. Fixed D1's
  placement (after all three existing refusals), D2's footprint re-apply (must pass
  `outside_writes`), and answered Open Question 2 as D5. The agent-plane list already spreads
  `_evidence_view` (`agent_actions.py:1296`), so D4 reaches it with no extra edit.
