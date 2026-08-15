# Design — the seams loop 7 found

## D1. The footprint is corrected after the turn, not deferred during it

`read_footprint` (`requirement_evidence.py:236`) does `git rev-parse HEAD` at record time. Inside a
turn the agent's work is dirty, so HEAD is the pre-turn commit. The commit that contains the work is
made by `worktrees.snapshot_worktree` after the process exits.

The window is structural. `record_evidence` is always called strictly between worktree provisioning
and the snapshot commit, so there is no moment at which the recording call could observe the right
sha. Two ways out:

- have the tool name a commit — impossible, the commit does not exist yet;
- correct the row once the commit does exist.

The second. `RequirementEvidence.run_id` is already written for every agent-recorded row from the run
credential, and is currently read by no query — a complete, unforgeable join key from a run to the
evidence it produced. At the snapshot site the sha, the worktree, the run id and a writable session
are all in scope simultaneously.

## D2. Every row of the run is re-stamped, whatever its review state

The pre-restamp footprint names a commit that provably does not contain the work.
`integration_targets` reads *accepted* footprints to choose the merge commit, so sparing accepted
rows means approval keeps merging the wrong commit — the live defect. It would also make correctness
depend on how quickly a reviewer clicked: two identical pieces of work, one corrected and one
permanently wrong, decided by reviewer latency. That is not a rule.

This does not re-open a decision. The footprint is a fact about the world; `EvidenceReview` is the
judgement, is append-only, and is untouched. `refresh_reachability` already mutates the footprints of
accepted rows post-hoc for the same reason.

Scope is `run_id` plus `actor_kind == "agent"`; operator evidence has no run and is footprinted from
a checkout nothing is about to commit to.

## D3. A `None` snapshot is not a skip

`snapshot_worktree` returns `None` when nothing was dirty. Two causes:

- the agent committed its own work mid-turn — the record-time footprint is **still** stale, because
  it was taken before that commit;
- the agent changed nothing — the footprint is correct.

A skip is wrong for the first and unnecessary for the second, so the re-stamp falls back to the
worktree's current `HEAD`. The second case then no-ops through the idempotence guard.

## D4. The re-stamp must be able to lower `reachable_from_main`

`refresh_reachability` is upgrade-only: it filters `reachable_from_main.is_not(True)` and only ever
raises the answer. That is right for its question — "has this commit reached main *yet*?" — because
the answer only travels one way for a fixed commit.

The re-stamp is answering about a **different commit**, so it must write a fresh answer, including
`False`. Reusing the upgrade-only rule would leave a re-stamped row holding a `True` that belonged to
the old sha, which is precisely the poison this change exists to remove.

## D5. The footprint is computed once per run, not once per row

Nine evidence rows from one turn share one worktree and one commit. Looping `capture_footprint`
would spend three git subprocesses per row. One `Footprint` is read and applied to every row.

`capture_footprint` and the re-stamp share `_apply_footprint`, so there is one place that maps a
`Footprint` onto a row and the two cannot come to disagree about what a footprint means.

The query is an **outer** join. Where `resolve_project_workspace` failed at record time
(`agent_actions.py:750-752`) the evidence row exists with no footprint at all, so the pass must be
able to create as well as update.

## D6. Retry lives in the transition service, not in a route

`_integrate` is private and reachable only from `apply_transition`, which cannot reach it when the
task is already approved because of the `to_status == from_status` early return. That early return is
correct and stays: restating a status must not manufacture a transition row.

So the retry is a second entry point to the same coroutine rather than a second path through the
transition. `retry_integration` holds the one rule — the task must be `approved` — so the operator
plane, the agent plane and the settings-save driver all get it without knowing it exists.

No refusal when the last outcome was already `merged`. `integrate` self-guards with
`ALREADY_INTEGRATED`, which asks reachability — a fact — rather than parsing the attempt log, which
records only what was tried. A retry after a merge honestly records one skip and merges nothing.

## D7. No MCP tool for retry, and the condition that would reverse that

Of the six skip reasons, five name a remediation only the operator can perform: the main branch is a
setting, and a dirty or elsewhere-parked checkout is the operator's own working copy. A tool for
those invites an agent to retry in a loop while nothing changes.

`NOTHING_TO_MERGE` is the exception — an agent *can* clear it, by having a granted peer accept
evidence, which `decide_evidence` already allows. If live use shows that happening, add
`retry_integration` to `mcp_server.py` and `src/agentweave/tool_surface.py`, and update
`test_tool_surface_matches_server.py` and `test_mcp_server_stdio_surface.py`. The HTTP route is
built now so the tool is a thin call away.

## D8. Setting the main branch retries only the skip that asked for it

`NO_MAIN_BRANCH` reads "choose one in the project's settings". Discharging that promise at the moment
the operator does it is what makes the sentence true; retrying anything else on a settings save would
merge for reasons unrelated to what the operator changed.

So: approved tasks whose **newest** integration row is `skipped` with that exact reason. Not
`CHECKOUT_DIRTY` or `CHECKOUT_ELSEWHERE` — naming a branch says nothing about the checkout's state.
Not `failed` — a merge that failed wants a person.

It runs after the settings commit and inside its own `try`/`except`, so a git failure cannot undo the
save. The operator changed a setting; that must succeed or fail on its own terms.

## D9. Diagnostics: three facts, one sentence

`AppServerError` is raised with a bare string, and the `run_failed` payload carries only
`{agent, run_id, error}`. Three facts are in scope and discarded:

- `self._proc.returncode`;
- `self._proc.stderr`, piped at `codex_appserver.py:547` and **read nowhere in the file** — which is
  a second live bug: an undrained pipe can fill and block the child;
- the in-flight JSON-RPC method, discarded because `request()` stores only the future.

All three are folded into the message so `str(exc)` alone carries them. That is what makes
`Run.error` useful with no schema change, and what lets an abandoned queue entry (D11) record a
reason worth reading.

The enriched error is used at **both** raise sites — the reader-loop `finally` and the loop-exit
check — because the second is the common path and today produces the bare string that reaches the UI.

`TurnOutcome` gains `exit_code`, but it is **not** fed into `Run.exit_code`: the synthetic `0`/`1`
there is load-bearing for the handoff detection in `AgentOutputPanel`.

`decide_approval` stays pure. All new state lives on `AppServerProcess` and in `run_turn`'s loop.

## D10. Why the wedge happens, and the one change that breaks it

`return_run_entries` resets a failed run's entries to `queued` and clears the delivery columns, but
never clears `conversation_id`. `turn_scheduler` picks the lowest-`sequence` queued entry as
`controlling` and adopts **its** conversation for the turn, filtering every other conversation out.
A requeued entry keeps its low sequence, so it always wins and always re-selects the same
conversation. Delivery then resumes rather than starts, because `agent_trigger.py:358-359` sets
`session_mode="resume"` whenever `conversation.provider_session_id` is set.

If that provider thread is unresumable, every delivery re-kills the runtime, and every new turn —
including one asking for a fresh conversation — queues behind the entry that is doing the killing.
Observed: four entries, four consecutive failures, no way through.

The single change that breaks the loop is clearing the conversation's `provider_session_id`, so the
next delivery is a `thread/start`. It is safe: the unique index permits multiple NULLs, and the next
turn re-binds the new thread id.

## D11. Reset at 2, abandon at 3

- **2** failures before discarding the provider thread. Not 1: a single failure is routinely a Hub
  restart or a transient spawn error, and discarding a live thread costs the agent its whole
  provider-side context irreversibly.
- **3** attempts before abandoning. Exactly one attempt on the original thread, one that trips the
  reset, and one on a fresh thread — the third is what distinguishes "the thread was poisoned" from
  "the input is poisoned". Fewer, and a Hub restart could discard an operator's message; more, and an
  agent is wedged across four failing turns before anyone is told.

All three requeue call sites count an attempt. The entry cannot tell why it failed and the poisoned
resume presents identically at all three; a one-off restart costs one of three and is invisible,
while a restart loop *caused by this entry* is exactly what the counter must catch.

## D12. Abandonment reuses `withdrawn`; nothing is orphaned

`state` is CHECK-constrained to `queued|delivered|withdrawn`. Rewriting a CHECK on SQLite means
`batch_alter_table` rebuilding a table whose autoincrement `sequence` the whole scheduler ordering
depends on — a bad trade to record a nuance a column can carry. `withdrawn` already means "this will
never be delivered", which is true of an abandoned entry; `abandoned_reason` records who gave up and
why. Every existing reader keeps working untouched.

`conversation_id` is **not** cleared. An entry without one is unschedulable — the scheduler reports
"queued entry has no conversation" and it wedges *silently, forever*, strictly worse than today.

`arrived_at` is **not** bumped. Ordering is by `sequence`, so bumping changes nothing about
scheduling and only hides how long the input has been stuck, which is the fact the operator needs.

Abandoned rows **keep** `delivered_in_run_id`: the breadcrumb from a dropped message to the run that
ate it.

## D13. `requirement_ids` returns identifiers, not row ids

`TaskCreate.requirement_ids` takes `FR-8`-style identifiers, resolved through
`requirement_links.resolve_identifiers`. Returning `SpecRequirement.id` primary keys would not
round-trip, which is worse than the field being absent.

Unresolved references are excluded. They already round-trip as `unresolved_requirements`, and
including them would make a GET→PATCH cycle resubmit a reference that already failed to resolve.

`TaskCreate`/`TaskUpdate` are `extra="forbid"`, so a client echoing a whole `TaskResponse` into a
PATCH would now 422. No shipped client does that — the UI sends only `status`, and MCP `update_task`
passes an explicit body.

## D14. The staleness stamp fingerprints content, not a commit

Recording the commit the bundle was verified against forces a two-commit dance: the source must be
committed before it can be named, and `--amend` cannot rescue it because amending rewrites the sha
the stamp names.

A content fingerprint of `hub/ui/src` goes into the **same** commit as the source change, and it also
catches an uncommitted edit sitting on a stale bundle, which a commit-date comparison cannot see at
all. It still gives an identical rebuild something to commit — the fingerprint moves whenever source
moves — which is the entire mechanism by which the warning becomes clearable.

The objection that content hashing cannot work, because a types-only edit changes source content
too, applies to *inferring* staleness from content. It does not apply here: the stamp is an
**assertion** — "this bundle was built from source state H" — and comparing H against the current
state answers "was this bundle built from what is here now?", which is the right question.

Where the stamp is absent the check falls through to today's date comparison byte for byte. That
compatibility property is what lets every existing staleness test stand unedited, and it keeps
installed packages and old checkouts behaving as they do.

The `lru_cache(maxsize=1)` becomes a 30-second TTL. Two git calls and a small file read is not worth
caching for the life of a process, and caching it for the life of a process is why a real rebuild
needs a Hub restart to clear the warning today.

**This is a promise, not a proof.** Someone who hand-writes the stamp without building gets a green
`/health` over a stale bundle — the very failure the check exists to catch, with a silencer fitted.
The mitigations are that only the script writes it, and that a wrong claim becomes a reviewable diff
rather than an invisible omission. The real proof is CI.

## D15. Landing order is forced

- **1 before 2** — the retry is the only surface that lets a corrected footprint reach main for work
  approved before the fix.
- **3 before 4** — they edit the same `except` block, and phase 4's "delivery failed 3 times" is
  undiagnosable without phase 3's enriched error.
- **6 last** — phases 2 and 5 touch `hub/ui/src` and should not be blocked on a rebuild workflow
  still being changed. The first UI change after phase 6 dogfoods it.
