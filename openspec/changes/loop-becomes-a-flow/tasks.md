# Tasks — the loop becomes a flow

**Order matters more than usual here.** Groups 1–2 change no behaviour and are the safety net for
everything after: a flow with one agent must remain indistinguishable from today's loop, and the
existing loop suite passing unmodified is what proves it.

**Depends on `task-dependencies`** (the graph, the gate, and the reviewer field) and, in practice,
on `loop-notices-and-reacts` for the shared firing decision this change adds an answer to.

## 1. The set-valued claim, behaviour unchanged

- [x] 1.1 Test: the whole existing loop suite passes unmodified. This is the bar for the entire
      group — a set of one must be indistinguishable from one.
      **Baseline measured before any change: 141 passed, 3 skipped** across
      `test_conversation_loop_marker`, `test_jobs`, `test_jobs_crud`, `test_loop_archival`,
      `test_loop_claim_dependency_gate`, `test_loop_continuity_warning`, `test_scheduler`. After
      the group: **147 passed, 3 skipped** — the same 141 plus this group's 6.
      **Caveat, stated rather than buried:** "unmodified" held for every *behavioural* test, but
      11 call sites poke the private `_claim_loop_task` directly and 1.3 changes its signature, so
      those were edited. Each goes through a `_claim_one` unwrap helper that leaves the assertion
      itself character-identical, and three assertions on `LoopSummary.current_task` became
      `current_tasks[0]` per 1.5. No test's *meaning* changed.
- [x] 1.2 Test: `_claim_loop_task` returning a set of one produces the same claim, the same briefing
      and the same `JobRun` as today, for each of the pending, resuming and empty cases.
      `hub/tests/test_loop_claim_is_set_valued.py` — 6 tests, **all 6 confirmed failing before
      1.3 and passing after**. Covers pending, resuming (status untouched), empty (`[]`, never
      `None`), a many-candidate queue still claiming one, determinism across repeated calls, and
      the briefing composed from a collection of one.
- [x] 1.3 Change `_claim_loop_task` to return a set, still selecting exactly one member.
      Returns `list[Task]`, `[]` when nothing is claimable. **A list, not a Python `set`** — the
      reasoning is in the docstring: iteration over a `set` of ORM rows follows identity hashes,
      which would make a width-2 flow pair tasks with agents nondeterministically, and the
      proposal requires a firing to select "a task and an agent, both deterministically".
      `_do_fire_job` unwraps at the boundary so the firing keeps its single-task shape until
      group 5.
- [x] 1.4 Update `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py`) to read the set, still rendering
      one current item. Import the derivation; do not restate it.
      The board *was* restating it — its own comment said it "mirrors"
      `_first_startable_candidate`'s rule. Extracted that rule as
      `scheduler.candidate_is_startable`, now the single statement both call. The query could not
      be shared: the board computes every job's block in six fixed queries (design D7) and cannot
      call the per-loop walker, so what is shared is the per-candidate rule, not the traversal.
      `test_the_board_summary_agrees_with_the_firing_for_a_gated_queue` (human-only check 13.1's
      automated half) still passes.
- [x] 1.5 Update `LoopSummary` and any response schema so current items are a list, and confirm the
      UI reads a list of one without visible change.
      `LoopSummary.current_task: Optional[Dict]` → `current_tasks: List[Dict]`, defaulting to `[]`
      rather than null so "nothing current" and "several current" share a type. `jobs.ts`,
      `JobCard.tsx` and `LoopTab.tsx` read `current_tasks[0]`; the `loop-tab-current-task` test id
      is preserved so the browser test still targets it. **UI suite: 138 files, 1376 tests passed
      — identical to the pre-change baseline**, which is the "no visible change" evidence.

## 2. The agent becomes a per-selection value

- [x] 2.1 Test: a loop with no document fires `AIJob.agent` on every firing, unchanged.
      `test_a_loop_with_no_document_selects_the_jobs_own_agent` plus the empty-queue case, in
      `hub/tests/test_loop_selection_carries_its_agent.py`. The whole loop suite is the wider bar
      and still passes: **150 passed, 3 skipped** (141 baseline + group 1's 6 + this group's 3).
- [x] 2.2 Test: a selection carrying an explicit agent fires that agent, and the run, conversation,
      queue entry and credential all attribute to it.
      `test_a_selection_naming_another_agent_is_who_actually_gets_fired` drives a real firing with
      the job owned by `job-owner` and the selection naming `other-agent`, then asserts the `Run`,
      the `Conversation`, the `InboundQueueEntry` **and** `Task.assignee` all read `other-agent`.
      The credential needs no separate assertion: `agent_auth` derives its `AgentActor` from the
      run row (`agent_auth.py:80`), so `Run.agent` is the credential's identity.
- [x] 2.3 Carry an agent alongside each selected task through `_do_fire_job`, defaulting to
      `AIJob.agent` (design D2). Leave the column `NOT NULL`.
      `LoopSelection(task, agent)` — frozen, because a selection is a decision already taken — and
      `_select_for_firing(session, loop, *, default_agent)`, the seam between *which tasks* (group
      1's claim) and *who works them* (group 4's ladder). `_do_fire_job` holds an `acting_agent`
      that starts as `job.agent`, so a job with no loop is untouched. Column left `NOT NULL`.
      **One thing this exposed:** `_job_agent_skip_reason` and the resume-conversation lookup both
      run *before* the claim and both take `job.agent`, so they answer about the wrong agent the
      moment a selection diverges. Restructuring that region is `loop-notices-and-reacts`' firing
      decision, not this group's — so group 2 guards it instead: a selection naming another agent
      drops the pre-claim conversation and resume id rather than putting one agent's turn in
      another agent's thread. Recorded here because group 4 must not assume it away.
- [x] 2.4 Confirm nothing reads `job.agent` downstream of the selection where the selection's agent
      is what is meant — a source scan, not a reading.
      Scan done across `hub/hub/`. Downstream of the selection, `scheduler.py` had 12 reads and now
      has 2 — both inside the stall-skip branch, which is reached only when *nothing* was selected,
      so the job's agent is what is meant there. Outside the scheduler, three sites read
      `AIJob.agent` and **all three are correct as they are**:
      - `tasks.py:586` (`_authorize_loop_task_creation`) — this looks like a site that needs the
        selection's agent and is precisely one that must not. It asks who may *extend* the queue
        (`agent-loops` §178, the loop's creator). A reviewer the flow staffs is not the creator and
        must not inherit that right by being fired once.
      - `jobs.py:148/449` (`LoopSummary.agent`) — the loop's owner, which is a job-level fact.
        Imprecise for a flow staffing several agents, but that is task 9.3's job, not this one.
      - `agent_actions.py:96`, `schemas/tasks.py:56` — comments restating the §178 gate above.
      One stale **comment** was corrected: `run_task_binding.py:242` asserted the claim sets
      `assignee = job.agent`, which stopped being true in 2.3.

## 3. Actor-aware claimability

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** D3's two premises hold: `_agent_that_completed` is where the design says it is
(`task_transition_service.py:108`), read by `_guard_author_is_not_reviewer` at `:153`, and it keys
on **agent** rather than run, which is what makes 3.2's correctness property expressible at all.
D4's rung 1 (`review_turn.resolve_declared_reviewer`) and D9's `ReviewTurnRefused` both exist.

Three things the spec does not say, each of which would ship a defect if implemented literally:

1. **`candidate_is_startable` asks the wrong question of a `completed` candidate.** It exempts
   `in_progress` and `blocked` from the dependency gate on the stated grounds that nothing is about
   to transition them, and gates everything else because it is "one `apply_transition` away from
   `in_progress` — the same edge `dependency_gate.evaluate` guards". A `completed` task claimed for
   review is not about to reach `in_progress`; it is about to reach a review outcome. Gating it on
   the `-> in_progress` edge would silently skip a finished task from review because *its own*
   prerequisite is unapproved, which has nothing to do with whether the work may be looked at. It
   needs the same exemption, for the same reason, or the correct edge.
2. **A `completed` task with no recorded completer is claimable by anyone**, because
   `_agent_that_completed` returns `None` and the guard treats `None` as permitting. That is the
   right answer — it is what makes 3.2's property hold in both directions — but it changes the
   premise of `loop-notices-and-reacts`' shipped stall tests, which construct `completed` tasks
   directly and therefore without history. Those tests assert a queue of completed work *stalls*;
   under this group it becomes reviewable. They need history, not deletion — a task that reached
   `completed` through `apply_transition` always has a completer, so giving them one makes them
   more faithful rather than less.
3. **`_loop_queue_order` already sorts a `completed` task ahead of pending work** (non-pending
   first, by `updated` descending). So review preempts new work by default, which is probably right
   and is certainly undeclared. Whatever it should be, it should be stated rather than inherited.

**Sequencing, which is the operator's call and not recorded anywhere.** Landing group 3 alone puts
a half-state in the live firing path: a `completed` task becomes claimable, the firing claims it and
leaves the status untouched, and `_compose_loop_briefing` — which knows nothing about review until
group 4b — briefs that agent to *work* finished work, in its own checkout without the author's
commits. That is finding F10's exact shape, which group 4b exists to prevent. Groups 3, 4 and 4b
look like one landing rather than three.

- [x] 3.1 Test: a `completed` task is offered to an agent that did not complete it, and not to the
      one that did.
      `hub/tests/test_actor_aware_claimability.py`, four tests: offered to a non-author, refused to
      the author, both answers taken from one queue at one instant so nothing about the *task*
      decides it, and the no-recorded-completer case below.
      **The fixture is the load-bearing part.** `_completed_by` walks the task to `completed`
      *through `apply_transition`* as a named agent. Constructing the row at `completed` directly —
      which is what most of the older loop tests do — leaves no `TaskTransition`, so
      `_agent_that_completed` answers `None` and every test in the file would have passed for the
      wrong reason.
- [x] 3.2 Test the correctness property directly — every task the flow offers an agent can be moved
      by that agent to a review outcome without author/reviewer separation refusing it. Assert this
      rather than inferring it from the cases above (design D3).
      `test_every_offered_task_can_be_carried_to_a_review_outcome` drives it end to end: the offer
      comes from `_claim_loop_task`, the permission from `apply_transition` either raising or not.
      Deliberately not a comparison of two functions' return values — a reimplementation of either
      side has to keep them agreeing to pass this.
      `test_the_agent_the_queue_refuses_is_the_agent_the_guard_refuses` is the other half, and is
      the one that catches drift in either direction: the author is refused by the queue and by the
      guard, from the same row.
- [x] 3.3 Test: `CLAIMABLE_LOOP_TASK_STATUSES` does **not** gain `completed`. Widening the tuple is
      the obvious wrong fix and it is actor-blind.
      Asserted, along with the two sets being disjoint, plus `blocked` as the control: it is also
      outside the claimable tuple and must *not* have acquired an actor-dependent answer, because
      the person holding the unanswered question is who unblocks it and no agent is a candidate.
      `test_task_lifecycle_bands.py` carries the vocabulary half —
      `test_the_two_statuses_that_are_current_without_being_claimable_differ_in_kind` states why
      `blocked` and `completed` sit in the same set difference for opposite reasons.
- [x] 3.4 Implement claimability as a question about `(task, agent)`, using `_agent_that_completed`
      rather than a second implementation of the same question.
      `scheduler.task_is_claimable_by`, plus `REVIEWABLE_STATUSES` derived from
      `BAND_AWAITING_HANDOFF` — the band the previous change created, which already said "finished
      by its author and waiting for somebody else to take it up". Group 3 is that sentence becoming
      executable, and needed no new band.
      The actor is threaded through `_first_startable_candidate`, `_claim_loop_task`,
      `_loop_stall_reason` and `decide_firing`; every production caller already goes through
      `decide_firing`, which had the agent as `default_agent` since group 2, so no call site outside
      tests changed.
      **An unclaimable-by-you candidate is skipped, not recorded as gated.** Gating is a statement
      about prerequisites; this is a statement about who is asking. Putting it in `gated` would make
      the stall reason say the queue was waiting on an approval when it is waiting on a second agent.
- [x] 3.5 Confirm the board's derivation and the firing's agree for a queue holding a `completed`
      task — the same 13.1 property, now with an actor in it.
      `test_the_board_and_the_firing_agree_about_a_completed_task`. **And it was not agreement that
      needed the work — it was the board's query.** The board takes both answers from
      `decide_firing` already, so it became actor-aware for free; but `CURRENT_ITEM_TASK_STATUSES`
      gates which rows its candidate query can return at all, and `completed` was outside it. A
      firing reviewing a completed task would have shown **no current item**, which is the
      2026-08-21 blocked defect exactly, mirrored. `completed` therefore joins current-item without
      joining the claim — the second status to do so, for the opposite reason to the first.
      The test asserts both directions: with the job's agent as the author the board shows nothing
      claimable, and with it as a non-author the board names the task the firing takes.

## 4. Reviewer resolution

- [x] 4.1 Test each rung of design D4 independently: a declared reviewer that resolves; one that does
      **not** resolve, which is surfaced and never substituted (amended 2026-08-24 — this said
      "falling back to availability", which contradicted shipped behaviour); no declaration at all,
      falling back to availability; and nobody eligible.
      `hub/tests/test_reviewer_ladder.py`, one test per rung. Each rung-1 test puts a *free,
      eligible* agent on the roster that must not be chosen, so "the declaration was honoured" is
      distinguishable from "there was only one candidate".
      **A fourth case not in the task text: a declaration that resolves to the author.** Rung 1b,
      not rung 2 — the document named somebody who may not do it, which is a fact about the
      document rather than about availability, and substituting is what 1b refuses. Left to fall
      through, it would have been the most plausible-looking wrong behaviour in the ladder.
- [x] 4.2 Test: an agent that is running, or that holds a task in an active status, is not selected
      while another eligible agent exists.
      Both halves, each with the ineligible agent sorting *first* by name so that picking the right
      one is the rule working rather than the ordering. Plus the case that would deadlock a
      two-agent project if it went the other way: holding a `completed` task does **not** make an
      agent busy, or the first agent to finish anything would stop being able to review for as long
      as its own work sat unapproved. Plus determinism — two calls, same order — because the
      proposal requires a firing to select an agent deterministically.
- [x] 4.3 Test: an agent with no runner bound is not selected, and is treated as unavailable rather
      than failing the firing.
      Implemented in `_agents_that_are_free` alongside the archived-agent exclusion, because they
      are the same kind of fact: `trigger_agent_directly` refuses to spawn either, so selecting one
      turns a staffing question into a launch failure one step later. A firing that says "could not
      staff this step" gives the operator something to act on; one that dies in the spawn path does
      not. Tested with the runnerless agent alphabetically first, so it would be picked if
      eligibility did not exclude it.
- [x] 4.4 Test: a single-agent project reaches rung 3 by the general rule, with no special-case code
      path — assert the path, not only the outcome.
      `test_a_single_agent_project_reaches_rung_3_with_no_special_case`. The rung is asserted, and
      so is the fact that the author *is* free by every measure except being the author — so the
      exclusion doing the work is the general one, not a branch about project size.
      **The path is asserted by construction rather than by inspection:** adding one more agent to
      the same project, changing nothing else, produces a staffed review from the same call. That
      cannot follow if a single-agent branch exists.
- [x] 4.5 **Decide how a declared reviewer resolves** — against charter names, agent names, or both —
      and record it in design D4. `task-dependencies` D11 deliberately left this here.
      **Answered 2026-08-24 without a decision being needed: agent names.**
      `a-reviewer-can-see-the-work` shipped `review_turn.resolve_declared_reviewer` first, matching
      the declared string against roster `Agent.name` for the project and treating an archived agent
      as unresolved. Recorded in D4. The flow reuses that function rather than writing a second
      resolution — so 4.6 implements the ladder *around* it, not a replacement for it.
- [x] 4.6 Implement the ladder, **calling `review_turn.resolve_declared_reviewer` for rung 1 rather
      than resolving the declaration again.** Two implementations of "who did the document name" is
      the drift shape this repo has been bitten by three times.
      `scheduler.resolve_reviewer`, returning a `ReviewerChoice` that carries **which rung
      answered** rather than only the answer. That is not bookkeeping: rungs 1b and 3 both produce
      "no agent" and mean opposite things to an operator — *a name was given and it is wrong* versus
      *nobody was named and nobody is free* — and a bare `Optional[str]` would collapse them,
      leaving the surfacing D4 asks for with nothing to say.
      Wired into `decide_firing`, and **the ladder decides for every reviewable task, always** —
      not "the job's agent if it happens to be eligible". A declaration that resolves outranks the
      job's own agent, or it would be advisory.
- [x] 4.7 Implement rung 3's surfacing, following the event and SSE pattern the stop path uses.
      Confirm it leaves the job enabled and scheduled.
      `_emit_review_unstaffed`, persisted and broadcast as `review_unstaffed`. Asserted: the job
      stays `enabled`, the loop takes no `stop_reason`, and nothing is queued for anybody.
      **Two decisions inside this that the task text does not contain.**
      *Surfaced whatever else the firing does.* A review nobody can take is a fact about the queue
      rather than about this tick, so the event is emitted even when the firing goes on to claim
      other work — otherwise a flow that quietly did something else would leave the operator with a
      queue that never finishes and no indication why.
      *The walk continues past it.* D4 says surface **the step**, not stop the flow. A queue holding
      an unstaffable review ahead of ordinary work — and review does sort ahead, design D10 — does
      the ordinary work and surfaces the review. Sitting still would let one unreviewable task halt
      a flow indefinitely. Both are asserted.

## 4b. The review turn — a reviewer must see the work

**Added 2026-08-24 (design D9).** `a-reviewer-can-see-the-work` shipped after this change was
written. Without this group a flow fires the reviewer into its own working checkout, where the
author's unmerged work does not exist — reproducing finding F10, which that change existed to fix.

- [x] 4b.1 Test: a flow firing an agent for a `completed` task produces a queue entry carrying
      `review_task_id`, and the resulting turn is a review turn.
      `hub/tests/test_flow_fires_a_review_turn.py`. Asserts the entry belongs to the **reviewer**
      and not the job's agent, and that nothing at all was queued for the author.
- [x] 4b.2 Test the property that matters rather than the plumbing: the reviewing agent's workspace
      contains a commit that exists only on the author's branch. This is F10's own assertion, and
      task 5.5 of `a-reviewer-can-see-the-work` is the pattern to copy.
      `test_a_flow_fired_reviewer_reads_a_file_that_is_not_on_main` — deliberately the same
      assertion `test_review_turn.py` makes about a manual trigger, reached through a flow firing.
      Same property, different door, and the door is what this group adds. **Confirmed failing**
      with `review_task_id` forced to `None`: the reviewer is spawned in its own working checkout
      and the file is not there.
- [x] 4b.3 Test: a review turn that cannot be prepared surfaces `ReviewTurnRefused`'s stated reason
      and does **not** fire the agent with an ordinary turn instead.
      `test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`. Driven with a
      completed task carrying no evidence, which is the ordinary way to reach it: nothing names a
      commit, so there is nothing to check out.
      **The property is structural, and the test says so rather than merely observing it.**
      `trigger_agent_directly` raises `TriggerAgentError(409)` from the `ReviewTurnRefused` handler
      *before* a workspace is chosen, so the downgrade this task forbids is unreachable rather than
      merely not taken — there is no branch in which a refused review continues into
      `resolve_agent_workspace`. Asserted from the outside: no agent is spawned at all, and the
      reason travels unchanged from the resolver.
- [x] 4b.4 Test: a firing that staffs ordinary (non-review) work still carries no `review_task_id`,
      so nothing that is not a review acquires a checkout.
      Plus the path that has no selection at all: a plain scheduled job with no loop. It is not a
      hypothetical — `selection` was bound only inside the loop branch while the queue entry that
      reads it is outside, so a plain job raised `NameError` until it was bound before the branch.
      The test pins it.
- [x] 4b.5 Pass `review_task_id` from the selection through `new_entry` in `_do_fire_job`
      (`hub/hub/scheduler.py:1187`). This is the one-argument gap D9 names.
      Carried on `LoopSelection.is_review` rather than re-derived from the task's status at the
      point of use: by then the status may have moved, and the consumer is three call layers from
      the decision.
- [x] 4b.6 Confirm the reviewer resolved by 4.6 is the agent the checkout is built for — review
      isolation is per agent, so a mismatch here builds the right checkout for the wrong agent.
      `test_the_checkout_belongs_to_the_agent_the_ladder_resolved`, driven with **three distinct
      names** — the job's agent, an alphabetically-first idle agent, and a declared reviewer — which
      is the only arrangement where picking the wrong one is visible. Availability alone would pick
      the idle agent; the job's own agent would pick neither.

## 5. Width

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** D5's premises hold where they can be checked: `_loop_candidates` is a single ordered
walk both walkers share, `candidate_is_startable` is the one startability rule, and `token_budget`
and `stop_at` (5.6) already bound a wide firing from outside it — `stop_at` refuses the whole firing
in `_loop_stop_reason` before any selection is made, and `token_budget` is enforced per turn inside
`schedule_agent` (`turn_scheduler.py:79`), so every additional agent a wide firing starts is checked
against the project total independently. Neither needs changing; 5.6 is a test, not work.

Four things the spec does not say, in descending order of how much they change this group:

1. **The busy guard refuses the whole firing, so width is unreachable after the first tick.**
   `_do_fire_job` calls `_loop_agent_busy_reason(..., job.agent)` and returns *before*
   `decide_firing` runs. Its docstring justifies itself with "a loop's agent runs one turn at a
   time" — true of a loop, false of a flow, where `job.agent` is only D2's default. The moment a
   flow staffs the job's own agent, every tick for the length of that turn refuses to staff any
   *other* free agent on any *other* independent task. D5's "starts every task ... for which an
   agent resolved" is then reachable only inside a single tick that happens to find the job's agent
   idle — the one shape a flow is least likely to be in. The guard has to become per-selection: a
   busy agent is excluded from *resolution*, not a reason to abandon the firing.
   `_job_agent_skip_reason` is the same shape one step later, and `decide_firing`'s own comment
   already records that both "answer about the wrong agent whenever a selection diverges".
2. **Ordinary work has no agent rule beyond `default_agent`, so D6 caps its width at one.**
   `decide_firing` pairs every non-reviewable candidate with `default_agent`. Widen the walk
   literally and D6 ("one agent, one task, per firing") drops all but one of them — a flow with
   three independent pending tasks and three free agents starts one. D4's ladder is explicitly the
   *reviewer* ladder. 5.1 requires two agents to start two tasks, so this group needs a stated rule
   for who works the second ordinary task, and neither D5 nor D6 has one.
3. **Resumption overwrites the assignee, and width is where that becomes wrong.**
   `claimed_task.assignee = selection.agent` is unconditional, and an ordinary selection always
   carries `default_agent`. A single-agent loop makes that benign. Under width, a task already
   `in_progress` under another agent is re-selected next tick as ordinary work, reassigned to the
   job's agent and briefed to them — while its actual worker may still be running. This is
   `design.md`'s own open question ("does a flow ever fire the same agent for a task it is already
   working?"), landing here exactly where handoff 0081 predicted. The rule that closes it is one
   line — a candidate that already has an assignee resumes with that assignee — and it is also what
   5.2's "leaving the others' status and assignee untouched" implies from the other side.
4. **`JobRun` is 1:1 with a conversation, and nothing says what a wide firing records.** The tail of
   `_do_fire_job` is singular throughout: one `run_id`, one `run.conversation_id`, one `entry`, one
   `schedule_agent`, one `job.run_count += 1`. `finalize_job_run_for_conversation` correlates a
   `JobRun` back to its `Run` **only** by `conversation_id`, and rests on "at most one `JobRun`
   in_progress for a given `conversation_id`". N selections mean either N `JobRun`s — correlation
   preserved, but `_prune_job_history`'s 100-row window fills N times faster and the last-ten-runs
   view changes shape — or one `JobRun` spanning N conversations, which breaks the only correlation
   there is. This decides how much of `_do_fire_job` this group rewrites, and it is operator-visible
   either way.

**All four are now decided.** 1 and 3 here — per-selection busy exclusion, and assignee wins on
resumption; each has one safe answer and the other ships a defect. 2 and 4 by the operator on
2026-08-24, before 5.5 was written: ordinary work takes the job's agent first and then the next free
agent from `_agents_that_are_free`, and a wide firing records one `JobRun` per selection. Written up
as **design D12 and D13**, which also close `design.md`'s "does a flow ever fire the same agent for a
task it is already working?".


- [x] 5.1 Test: two startable tasks and two eligible agents start both.
      `hub/tests/test_flow_width.py::test_two_startable_tasks_and_two_eligible_agents_start_both`,
      plus `test_the_pairing_is_deterministic_across_reruns` — the proposal requires a firing to
      select "a task and an agent, both deterministically", and two free agents against two tasks is
      the smallest case where a set-valued walk could answer differently twice.
- [x] 5.2 Test: three startable tasks and one eligible agent start one, leaving the others' status
      and assignee untouched.
      `test_three_startable_tasks_and_one_agent_start_one_and_touch_nothing_else`, driven through a
      real `_fire_job_internal` rather than through `decide_firing`, because the property is about
      what the *firing* wrote. Asserting the assignee as well as the status is the load-bearing
      half: a widening that marked the leftovers `assigned` to have them "ready for next time" would
      put three tasks on one agent, which is D4 rung 2's pile-up reached from the other end.
      **This test passes against the pre-widening code too**, and is kept deliberately — it is the
      regression guard for the bound, not a demonstration of the feature.
- [x] 5.3 Test: a dependent task does not start alongside its prerequisite.
      `test_a_dependent_task_does_not_start_alongside_its_prerequisite`. Two agents are free on
      purpose: without the gate the walk would staff the second one here, which is the failure mode
      a naive widening ships — parallelism that ignores the ordering the decomposition encoded.
      Also asserts the skipped task is neither `deferred` nor `unstaffed`, since an unmet
      prerequisite belongs in the stall reason's vocabulary rather than D6's.
- [x] 5.4 Test: one agent resolving for two tasks is started for one only (design D6), and the
      dropped selection is visible rather than silent.
      `test_one_agent_resolving_for_two_tasks_is_started_for_one_only` and
      `test_a_deferred_selection_names_no_remedy_because_there_is_none`. Visibility is
      `FiringDecision.deferred` and a debug log, **not** an event — see the field's own comment: a
      flow with more ready work than agents defers on every tick by design, so an event would bury
      `review_unstaffed`, the one that genuinely needs the operator, under the healthy case. That is
      `loop-notices-and-reacts` design D6's burying problem, and this is the second place it would
      have appeared.
      **A third place, found while writing this and fixed here.**
      `test_a_review_left_over_after_the_agents_are_taken_is_deferred_not_unstaffed`: when a firing
      staffed every free agent on earlier selections, `resolve_reviewer`'s rung 2 ran out of
      candidates and fell to rung 3, whose message asks the operator to add an agent or fix a name.
      Neither applies — the agents exist and are merely spoken for by this same tick — so a wide
      firing would have raised `review_unstaffed` most often on exactly the flows working hardest.
      Rung 2 now distinguishes "excluded" from "taken" and returns `deferred` for the second.
      Confirmed failing against a planted `only_taken = False`.
- [x] 5.5 Implement multi-selection, bounded by the graph and by available agents. No configured cap
      (design D5).
      `decide_firing` walks to the end of the queue and accumulates instead of returning on the
      first staffable candidate; `taken` enforces D6. Three supporting changes, each its own
      finding from the review above: `_loop_flow_busy_reason` narrows the whole-firing busy refusal
      to "the job's agent is busy **and** nobody else is free" (D12), ordinary work resolves an
      agent via D12 rather than always taking the job's, and `_fire_additional_selection` stages
      selections 2..N with a `JobRun` and conversation each (D13). A failure staging one extra
      selection is caught and contained rather than allowed to reach the firing's own handler,
      which would mark the *primary* run failed after it had already been queued and scheduled —
      each selection stands or falls alone, which is the same independence D13 gives them a row
      each for. Covered by
      `test_an_assigned_task_resumes_with_its_own_assignee_not_the_jobs_default`,
      `test_a_busy_agent_does_not_stop_the_firing_from_staffing_a_free_one`,
      `test_a_single_agent_loop_whose_agent_is_busy_still_records_nothing` and
      `test_a_wide_firing_records_one_job_run_per_selection`.
      **One correction found by the suite rather than by reasoning.** The first implementation
      required the job's own agent to be in `_agents_that_are_free`, which additionally demands a
      roster row with a bound runner and no active work. That is the right bar for an agent the flow
      recruits and the wrong one for the agent the operator already chose, and it made a loop whose
      agent holds any active task resolve nobody —
      `test_the_board_summary_agrees_with_the_firing_for_a_gated_queue` caught it, because the
      dependency board derives its current item from this same walk. The default is now tested
      against "running a turn" only; D12 records the asymmetry and why.
- [x] 5.6 Confirm `token_budget` and `stop_at` still bound a flow that is running several agents.
      Confirmed, and neither needed changing. `stop_at` is checked in `_loop_stop_reason` above the
      decision, so it refuses a wide firing whole —
      `test_stop_at_refuses_a_wide_firing_before_any_selection_is_made`. `token_budget` is enforced
      per turn inside `schedule_agent` (`turn_scheduler.py:79`), which every selection passes
      through — the primary one on the firing's own path, each extra one in
      `_fire_additional_selection` — so a wide firing meets the same check N times:
      `test_an_exhausted_token_budget_starts_no_turn_for_any_selection`. The entries stay *queued*
      rather than being discarded, which is `test_accounting_budget.py`'s shipped behaviour for an
      autonomous turn; what the test asserts is that no `Run` starts.

## 6. The checkpoint lineage

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** D7's premise holds: `latest_checkpoint_for_loop` retrieves by `Checkpoint.loop_id`
across every conversation a loop has fired into, exactly as `agent-loops` §231 requires, and
`_compose_loop_briefing` already calls it. So 6.1 is a test of shipped behaviour rather than work,
and so is 6.2 — `render_checkpoint` already emits `Agent: {checkpoint.agent}` as its third line.

Three things the spec does not say:

1. **For a loop the lineage columns are not "single-agent" — they are structurally empty**, which
   makes 6.4 a bigger correction than it looks. `generate_checkpoint` anchors on
   `latest_checkpoint(db, conversation.id)`, which is *conversation*-scoped; a loop may not be
   resume-mode at all (`jobs.py` refuses it: *"this job is a loop; continuity is by checkpoint, not
   by resumed session"*), so every firing is a fresh conversation and every loop checkpoint has
   `previous_checkpoint_id=None` and founds its own `lineage_id`. A correction that only swapped the
   agent count would leave the next reader believing a loop's checkpoints form a chain they have
   never formed. What is true is narrower and more useful: the chain describes a *conversation*, and
   a loop's continuity is not the chain — it is `loop_id` plus `created_at`.
2. **The prior checkpoint reaches the next agent but not the next checkpoint's author.**
   `_ANCHOR_SECTION` — *"The previous checkpoint for this conversation is below. Carry forward what
   is still true"* — is included only when `anchor` is non-None, and by finding 1 that never happens
   for a loop. So the briefing carries checkpoint N into agent B's turn, but the worker that writes
   checkpoint N+1 sees only B's transcript and whatever B happened to restate. Across a flow that
   degrades: each checkpoint covers one firing, and anything A recorded survives only as far as B
   chose to repeat it. **Not fixed here** — nothing in group 6 or D7 asks for it, and changing the
   anchor to `latest_checkpoint_for_loop` also moves `_transcript_since`'s and `runs_to_cover`'s
   boundaries onto another conversation's timestamp, which needs deciding rather than assuming.
   Raised as an open question below.
3. **6.5's instruction is already correct in the place it appears to live, and wrong in the place
   it actually lives.** `_GENERATION_PROMPT` opens *"You are writing a checkpoint for a software
   conversation so that a different agent, who has never seen it, can pick the work up"* — D7's
   consequence, already satisfied, for the *worker*. The gap is `submit_checkpoint_notes`, the tool
   the agent itself calls: `warnings` mentions "a successor", but `intent` and `suspicions` are
   framed entirely self-referentially ("what you were in the middle of doing"), and nothing tells
   the agent the reader may be somebody else working a different task. That is precisely the
   "agents write notes to themselves and a reviewer inherits shorthand" D7 predicts.


- [x] 6.1 Test: a flow fires A, A checkpoints, the flow fires B, and B's briefing carries A's
      checkpoint content.
      `hub/tests/test_flow_checkpoint_lineage.py`, three tests: the carry itself, that two
      checkpoints from two agents brief the third firing from whichever came *last* rather than from
      the one belonging to the agent about to run, and that a second loop's checkpoint is not
      carried — `loop_id` scoping means "the newest checkpoint" must never come to mean "the newest
      in the project". Shipped behaviour; these are the regression guard D7's migration plan asks
      for.
      **The fixture is the load-bearing part.** `_checkpoint_by` writes each checkpoint into its own
      fresh conversation, because a loop may not be resume-mode and that is the only shape a loop's
      checkpoint ever has. Reusing one conversation across both agents would have tested a lineage
      the product cannot produce.
- [x] 6.2 Test: each checkpoint in a multi-agent lineage identifies its author.
      `test_every_checkpoint_in_a_multi_agent_lineage_names_its_author`. Already true —
      `render_checkpoint` emits `Agent: {checkpoint.agent}` as its third line — and asserted because
      group 6 is what makes it load-bearing: once a lineage holds two agents' work, an unattributed
      checkpoint is a handover whose reader cannot tell whether they are resuming their own
      reasoning or inheriting somebody else's.
- [x] 6.3 Test: a document-less loop's lineage behaves exactly as before.
      `test_a_document_less_single_agent_loop_is_unchanged`, driven through a real
      `_fire_job_internal` rather than through the composer, so it covers the path a loop actually
      takes — including that `_fire_additional_selection` never runs for it and the entry carries no
      `review_task_id`. This is D7's migration bar: *"The behaviour of a flow with one agent is
      today's behaviour."*
- [x] 6.4 Correct the `Checkpoint` model comment — *"Linear, single-agent chain"* — to say what is
      now true, and say why it changed. The comment is the artefact that disagreed with §231
      (design D7).
      Corrected, and **not** in the direction the task expected. "Single-agent becomes multi-agent"
      would still have been wrong: by finding 1 of the review above, a loop's `previous_checkpoint_id`
      is *always* `None` and its `lineage_id` always itself, because the anchor is conversation-scoped
      and a loop may not be resume-mode. The comment now says the chain belongs to a conversation,
      that a loop's continuity is `loop_id` plus `created_at`, and why the disagreement went
      unnoticed. `test_a_loops_checkpoints_do_not_chain_and_that_is_the_point` pins it so a later
      reader cannot correct it back.
- [x] 6.5 Change the instruction an agent is given when writing a checkpoint so it addresses whoever
      continues the work, not itself. Without this, agents write shorthand a reviewer inherits.
      Changed in `submit_checkpoint_notes`, which is where the gap actually was — see finding 3.
      `_GENERATION_PROMPT` already opened *"so that a different agent, who has never seen it, can
      pick the work up"*, so the worker was already told; the agent was not. The tool now opens
      "Write for somebody else", names the reviewer case explicitly, and its three field
      descriptions were rewritten out of the second person ("what you were in the middle of doing"
      → "what was in the middle of being done") so the framing does not undo the instruction one
      line later.

## 7. The tool surface

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** D1's premise holds — `Loop.spec_document_id` is `nullable=True, unique=True` and the
Hub stores all three tiers in one row — so `create_flow` is a naming tool over an existing route,
not new storage. Four things the spec does not say:

1. **`create_loop` already accepts `spec_document_id`, so 7.2 withdraws a shipped capability rather
   than closing a gap**, and a shipped test exercises it:
   `test_create_loop_sends_the_widened_governed_jobs_payload` passes `spec_document_id="doc-1"` and
   asserts the whole posted body. That test moves to `create_flow` rather than being deleted — the
   payload assertion is what keeps the tool and the route it posts to in step, and losing it to a
   rename would cost more than the refusal gains.
2. **The refusal must keep the parameter.**
   `test_create_loop_offers_exactly_the_fields_the_route_it_posts_to_accepts` asserts
   `create_loop`'s property set equals `AgentJobCreate`'s minus two, and that invariant exists
   because "a field on one schema but not the other silently drops the caller's intent". Removing
   `spec_document_id` from the signature would break it for exactly the reason it was written. So
   7.2 is a call-time refusal with the parameter retained, which is what 7.5 already prescribes
   ("in the style that file already uses for a loop with no stop condition").
3. **The tiers should differ in the schema, not only in the function body.** `create_flow` declares
   `spec_document_id: str` — no `Optional`, no default — so the MCP schema itself carries the
   requirement and a caller's client refuses before a request is made. 7.1's client-side check then
   covers what a schema cannot: the empty string, and `None` reaching a tool whose declared type
   says otherwise. Worth stating so a later reader does not mistake the check for the whole
   enforcement, or delete it as redundant with the annotation.
4. **Nothing on the Hub distinguishes a flow from a loop**, which is D1 working as designed: both
   tools post a byte-identical body to `/agent-actions/jobs`, and the whole distinction is what the
   caller was made to say. That makes 7.3 the load-bearing test of D1 rather than a formality — if
   the two bodies ever diverge, a `Flow` table has grown in all but name.


- [x] 7.1 Test: `create_flow` without a document is refused, stating why.
      `test_create_flow_without_a_document_is_refused_before_any_hub_call`, over both `""` and
      `None`, asserting no HTTP call was made and that the message names `create_loop` as the thing
      to call instead. Plus `test_create_flow_still_needs_a_stop_condition`: a flow keeps every
      respect of a loop except its queue behaviour, and *"a loop that cannot stop is not created"*
      is one of them.
      **Not redundant with the `str` annotation**, which is finding 3 of the review above: the
      annotation is what a well-behaved client enforces before calling, and this is what catches the
      empty string and a `None` from a client that did not.
- [x] 7.2 Test: `create_loop` with a document is refused and names `create_flow`.
      `test_create_loop_with_a_document_is_refused_and_names_create_flow`. The parameter is
      **retained** in the signature rather than removed — see finding 2: the schema test asserts
      `create_loop` offers exactly the fields the route accepts, an invariant that exists so a
      caller's intent is never silently dropped, and an unexpected-argument `TypeError` would tell
      the caller nothing about what to do instead.
- [x] 7.3 Test: both tools produce a job and a loop record, differing only in the declared document.
      Three tests. `test_create_flow_sends_the_same_payload_a_loop_does_plus_the_document` is the
      shipped `create_loop` payload assertion **moved** rather than deleted (finding 1) — it is what
      keeps the tool and the route it posts to in step. `test_create_loop_sends_...` keeps the loop
      half with `spec_document_id` now `None`. And
      `test_the_two_tools_post_bodies_that_differ_only_in_the_document` asserts D1 directly rather
      than leaving it inferable from two tests that could drift apart one edit at a time without
      either failing.
- [x] 7.4 Add `create_flow` to `hub/hub/mcp_server.py`. **Stdlib and fastmcp only** — anything it
      needs from the Hub is restated there, with a test asserting the two agree.
      Added. Imports nothing new; the body is `create_loop`'s with the document required, which is
      design D1 holding — one route, one row, and the whole distinction in what the caller was made
      to say. The agreement test is
      `test_create_flow_offers_the_same_fields_and_requires_the_document`, which checks the property
      set against `AgentJobCreate` exactly as the `create_loop` one does **and** that the two tools
      differ in `required` alone: `spec_document_id` required on the flow, absent from the loop's
      required set, everything else identical.
      The docstring is the agent-facing statement of what a flow *is* — width, review by a non-author,
      the ladder, `agent` as default rather than mandate, and the checkpoint being the flow's. That is
      the one place an agent reliably reads, which is the same argument design D8 makes for the
      briefing.
- [x] 7.5 Add the refusal to `create_loop`, in the style that file already uses for a loop with no
      stop condition.
      Done — a client-side `HubAPIError(400, ...)` before any HTTP call, beside the existing
      stop-condition refusal. `create_loop`'s docstring now opens by naming the tier boundary
      ("One agent, one task at a time. Use create_flow instead when...") so the refusal is
      avoidable rather than only recoverable.

## 8. The briefing

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** Three findings, and the first two narrow this group considerably.

1. **A reviewer is already told it is reviewing — in the canonical context, not the briefing.**
   `api/v1/agents.py:1102` renders *"**This is a review turn. You are reviewing someone else's work,
   not doing your own**"*, the task under review, the commit, the branch, and the rule that an agent
   editing the work has reviewed its own work. It is gated on `review=review_context`, which
   `agent_trigger.py` sets from the queue entry's `review_task_id` — the argument group 4b started
   passing. Its own comment states the failure it exists to prevent: *"A reviewer that is not told
   it is reviewing will helpfully fix the bug itself and report the work as verified."*
   So the earlier reading of this group — that a flow-staffed reviewer is briefed with the author's
   task framing and would redo the work — is **true of the briefing and false of the turn**. What is
   actually missing is only what D8 asks for: the *tier*, and that finishing means stopping.
2. **§257 does not bound what this group adds.** Its fixed bound is on *prior checkpoint content*
   (`_LOOP_BRIEFING_CHECKPOINT_CHARS = 4_000`), and its SHALL is a *shall-include* list, not a
   shall-only-include one. So 8.3's "it competes for room with the checkpoint and the task" is not
   the constraint it sounds like: two or three lines take room from nothing. The real constraint is
   narrower — the statement must sit outside the truncated region, or an oversized checkpoint would
   silently eat it.
3. **The tier is a naming distinction with no behavioural boundary, which makes 8.1/8.2's split
   partly false.** Nothing in `decide_firing`, `task_is_claimable_by` or `resolve_reviewer` consults
   `Loop.spec_document_id`; width and review-by-a-non-author apply to *every* loop, and rung 2 of
   the ladder is explicitly written to work "with nothing configured". So a document-less loop in a
   project with three agents already gets exactly what a flow gets. 8.1 as written is satisfiable,
   but 8.2 — "a loop's briefing does not claim that anything will route its work onward" — cannot
   be read as "a loop routes nothing", because it does.
   Implemented on the true split rather than the stated one: **every** loop is told to finish and
   stop, since that is true of all of them, and only a **flow** is told that its work comes from a
   document and that finished work is reviewed by somebody else. A single-agent loop is therefore
   never told that somebody will review its work, which is the false claim 8.2 exists to prevent.
   **The underlying inconsistency is the operator's** and is recorded as a design open question:
   either the tier gates behaviour, or the tier is presentation and D1's three tiers are two.


- [x] 8.1 Test: a flow's briefing states that the flow routes the work onward.
      `test_a_flows_briefing_says_the_flow_routes_the_work_onward`. The statement leads the
      briefing and carries the three things an agent inside a flow cannot infer: that the queue came
      from a document, that finished work is claimed for review by somebody else, and that finishing
      is the end of its job — "routing is the flow's job, and the next firing decides who does
      what".
- [x] 8.2 Test: a loop's briefing does not claim that anything will route its work onward.
      `test_a_loops_briefing_never_claims_someone_will_review_the_work`, which asserts the words
      "review" and "flow" are absent entirely rather than checking for a particular alternative
      phrasing — the failure to guard against is a false promise, and a test that names the right
      wording would pass for any other wrong one.
      Implemented on the true split rather than the stated one (finding 3): every loop is told to
      finish and stop, because that is true of every loop, and only a flow is told about the
      document and the review. See the review block above, and `design.md`'s new open question.
- [x] 8.3 Implement it in `_compose_loop_briefing`, within the bound `agent-loops` §257 sets — it
      competes for room with the checkpoint and the task.
      Implemented, and the bound turned out not to apply (finding 2): §257 bounds *prior checkpoint
      content*, and its SHALL is a shall-include rather than a shall-only-include, so a few lines
      take room from nothing. The real constraint is placement — the statement **leads** the
      briefing, above the checkpoint, because §257 truncates the checkpoint in place and anything
      after it would survive or not depending on how much the previous agent happened to write.
      `test_the_tier_statement_survives_an_oversized_checkpoint` pins that with a body twice the
      bound, asserting both that the statement is present and that it precedes the checkpoint
      section.

## 9. Presentation

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** 9.3 stopped being speculative when group 5 landed: `_batch_loop_summaries` took
`decision.selections[0]`, so a flow working three tasks reported one. Two findings shaped 9.1 and
9.2, and one shaped 9.3:

1. **The agent-change break matters in exactly one of the two call sites.** `AgentTree` groups a
   list already scoped to one agent (`byAgent.get(agent.name)`), so no run there can span agents.
   `RecencyView` is project-wide and colour-codes by agent, and it is where a flow's firings for
   three agents land consecutively. The guard belongs in `groupConsecutiveFirings` rather than at
   the call site that needs it, so the two cannot drift.
2. **`LoopFiringGroup` takes a single `agentName` and `agentColor` for the whole row**, which is why
   breaking the run is the fix rather than rendering several agents inside one group. A run spanning
   agents would have labelled three agents' work with whichever fired first.
3. **The blocked-task rule had to give up exclusivity, not ordering.**
   `test_a_blocked_task_outranks_a_pending_one` asserted the blocked task was the *only* current
   item. §85 requires an ordering; the exclusivity was a consequence of the board reporting one
   item, which this change's own delta replaces ("current items are a set rather than a single
   value"). Both facts are true at once — the loop waits on the operator for one and would claim the
   other next firing — so both are reported, blocked first. The assertion moved; the ordering did
   not.

- [x] 9.1 Test: a change of agent breaks a collapsed run of consecutive firings.
      `hub/ui/src/__tests__/loopGrouping.test.ts`, four tests: two agents of one flow yield two
      groups, three single firings stay three plain rows (`MIN_FIRINGS_TO_GROUP` still applies per
      run), a run that is one agent throughout still collapses — the regression guard for every loop
      that exists today — and the order is unchanged whichever way a run is broken.
- [x] 9.2 Implement that break, and confirm collapsing still does not reorder.
      One clause in `groupConsecutiveFirings`'s run-extension condition. Order is asserted directly
      in `never reorders, whichever way the run is broken`, over a list mixing operator
      conversations, two agents of one loop, and a second loop.
- [x] 9.3 Show several current items where a flow is staffing several tasks, each naming its agent.
      `_batch_loop_summaries` now collects every selection rather than `selections[0]`, keyed by task
      so the candidate walk can answer "would the firing claim this, and by whom" per row. The walk
      appends every match instead of stopping at the first, in `_loop_queue_order`'s order, so the
      card lists them the way the firing considered them. `agent` is the selection's agent, or a
      blocked task's own assignee, and is **omitted rather than blank** when neither exists.
      Backend: four tests in `test_flow_width.py` — the wide case, the single-agent regression bar,
      the omitted key, and a blocked task carrying its assignee (the agent whose work an answer
      unblocks). UI: `JobCard` renders the list with a muted trailing agent label, `LoopTab`
      switches its heading between "Current item" and "Current items"; two tests in
      `jobCard.test.tsx`, one asserting `textContent` exactly so a stray blank cannot pass.
- [x] 9.4 **Decide what the dependency board shows for concurrent work** — per card, per layer, or a
      flow header — and record it. Open question in the design.
      **Decided by the operator 2026-08-24: several current items on the loop's card, each naming
      its agent.** Recorded as design D15, with the two rejected shapes and why. The design's open
      question is struck through.
- [x] 9.5 `make ui` after `npm run build`; commit `hub/ui/src` and `hub/hub/static/ui` together.
      `npm run build` then `py -3.11 scripts/refresh_ui_bundle.py` **from the repo root** — the
      script refuses to work from `hub/ui`, and the Bash tool's cwd persists between calls, which is
      the trap recorded in earlier handoffs. Bundle `index-S_JuGAvs.js` → `index-C10cTKzU.js`, with
      `index.html` and `ui-build-stamp.json`. `AW_CHECK_UI_BUNDLE=1 pytest hub/tests/test_ui_build_stamp.py`
      passes, which is the stricter assertion that the bundle matches the source it claims.

## 10. Verification an agent can do

**Reviewed against the shipped code 2026-08-24, before implementing, per the operator's standing
instruction.** Two findings, one about this list and one about the product.

1. **10.1's premise is wrong about the interpreter.** It expects "the three pre-existing
   `test_pty_runner` environment failures". There are none under `py -3.11`; the three are an
   artefact of a bare `python`, which resolves to a different venv on this machine. Every run this
   session has been `py -3.11` and every one has been zero-failure, so the qualification is dropped
   rather than carried.
2. **A flow's own claim is attributed to the operator.** `_do_fire_job` calls
   `apply_transition(..., "assigned", operator())`, so the recorded history says a human assigned
   every task any loop ever claimed. 10.5 asks for a chain with "no operator action at any point",
   and it is the first requirement that reads `actor_kind` — which is why a defect predating this
   change surfaced here. Not fixed: `Actor` has two kinds, a third is a migration plus a change to
   an audit trail the operator reads, and it affects every loop rather than only flows. Recorded as
   a design open question, and pinned by a test so that fixing it cannot pass unnoticed.


- [x] 10.1 `pytest hub/tests/ -q` passes, with the three pre-existing `test_pty_runner` environment
      failures unchanged and no new failures.
      **Zero failures, not three** — see finding 1. Measured at every commit boundary this session
      against a baseline taken on the unmodified tree: 2995 → 3008 (group 5) → 3023 (groups 6–8) →
      3027 (group 9), every increment exactly accounted for by the tests added. The `1 xpassed` is
      the documented `strict=False` xfail over a StaticPool fixture defect, present in the baseline
      and every run since.
- [x] 10.2 `pytest tests/ -q` passes.
      **412 passed, 3 skipped, 0 failed.** The CLI suite is untouched by this change — nothing here
      reaches `src/agentweave/` — so this is a guard against having reached it by accident rather
      than a check of new behaviour.
- [x] 10.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files;
      `cd hub/ui && npm run lint`.
      `ruff` and `black` clean across `hub/` (421 files); `tsc --noEmit` and `npm run lint` clean;
      `npx vitest run` 1391 passed. **Run tree-wide, not per file** — checking individual source
      files let two findings into this session's own test files and past two commits before the
      tree-wide run caught them.
- [x] 10.4 `openspec validate loop-becomes-a-flow` reports valid.
      `npx openspec validate --changes --strict` — both changes valid, re-run after every edit to
      either.
- [x] 10.5 The whole chain: a document declares A → B, a flow runs A with one agent, a second agent
      reviews and approves it, and B then starts — with no operator action at any point.
      **The reviewer must reach its verdict from the checkout, not by asking the author** (design
      D9); a chain that completes because the two agents talked has not demonstrated this.
      `hub/tests/test_flow_chain_end_to_end.py`, five tests. The chain runs: firing 1 staffs CRITIC
      to review A while the gate still refuses B, the verdict lands, firing 2 starts B.
      **What is real and what is simulated is stated in the module docstring**, because the
      difference is the whole value of the test: real are the firing decision, the ladder, the
      claim, the dependency gate, the entry, the `review_task_id` and the git checkout; simulated
      are the two *judgements* a model would make, since there is no model in a test.
      D9's qualification is covered from both sides —
      `test_the_reviewer_reaches_its_verdict_from_the_checkout` asserts `ledger.py` is absent from
      the project and present in the reviewer's own workspace (with the real
      `ensure_review_checkout` restored, or the assertion would be vacuous), and
      `test_the_flow_never_relays_anything_between_the_two_agents` asserts zero `Message` rows,
      since design D3's review mechanism is claimability rather than a handover the author must
      remember to send. A fifth test guards the fixture itself: if `_author_commit` ever committed
      to `main`, every other assertion here would still pass and none would mean anything.
      The operator-action claim is narrowed to what the record supports — see finding 2 — and
      asserts that no *judgement* was the operator's, with the flow's own misattributed claim pinned
      explicitly.
- [x] 10.6 Confirm the 20 `agent-loops` requirements this change does not modify still hold, by
      running their scenarios against the flow implementation rather than assuming.
      **24, not 20.** `agent-loops` holds 27 requirements today and this change's delta modifies
      three — current items, consecutive firings, and what a firing claims. The count in this task
      was written when the capability was smaller.
      `hub/tests/test_flow_holds_the_loop_requirements.py` re-runs, **against a real flow** (declared
      document, three roster agents, three ready tasks), the four whose mechanics could bend under
      width: §449 (a firing in progress is distinguishable from one that has finished), §429 (a
      loop's history is answerable for that loop alone), §110 (a stop condition only ever prevents a
      firing that was going to happen), and §85 (a loop surfaces its state without a caller
      assembling it). The selection is deliberate and the file says so: a requirement about archival
      refusing to delete a row cannot break because three agents are running, and re-running all 24
      would restate the existing suite at length while hiding the four that actually needed asking.
      The remaining 20 are covered by the loop suite unchanged, which is design D7's own stated
      regression bar — *"the behaviour of a flow with one agent is today's behaviour"* — and
      `test_a_document_less_single_agent_loop_is_unchanged` plus
      `test_the_board_still_reports_one_item_for_a_single_agent_loop` are that bar asserted
      directly.
      **This task found a real defect, which is what it is for.** §449 is unanswerable with one
      `JobRun` per firing, so asserting it under width exposed that
      `_fire_additional_selection` staged each extra selection *and started its turn* in a loop that
      ran after the primary turn was already away. A turn that ends calls
      `finalize_job_run_for_conversation`, which writes `job_runs` — so a fast turn interleaved with
      the staging of the third selection and raised
      `StaleDataError: UPDATE ... expected to update 1 row(s); 0 were matched`, and the third
      selection was **silently dropped**: the firing did less than it had decided to, with nothing
      recorded. Two changes fixed it, and both are properties rather than patches:
      staging now runs in its own session (the caller's held the primary conversation the background
      turn was concurrently rewriting), and **every row a firing writes is written before any turn
      is started** — `_stage_additional_selections` then `_start_additional_turns`. The guard that
      hid the drop now logs; a guard that returns silently is how a wide firing quietly narrows.

## 11. Verification only a human can do

**Driven live 2026-08-24 against the trial Hub on 8010, project `ledger-stress`
(`proj-18e5d4e0`), with three real Claude agents.** Nothing below is ticked — every one of these is
a judgement, and the judgement is the operator's. What the drive did was remove the setup cost and
gather the evidence, so each check is now *read this* rather than *build this and then read it*.

Six firings, ~3.5M tokens (builder +2.45M, critic +1.04M, relay +41k). The flow is left **disabled**
so nothing keeps spending; re-enable `job-bdea22bb0308` to carry on.

| Check | What the drive established | What is left to judge |
|---|---|---|
| 11.1 | Not exercised — the drive ran three agents throughout. | Run one with the other two archived. |
| 11.2 | A handover happened with **no message between agents**: builder completed `task-23a0986e7fe9`, and the next firing queued a turn for `critic` carrying `review_task_id` for it. Zero `Message` rows. | Whether the *conversation list* makes that obvious. |
| 11.3 | **Blocked by finding F43, 2026-08-25 — and the check inverts.** No checkpoint was generated because none *can* be: notes are consumed only by checkpoint generation for the author's own conversation, and generation fires only on a context threshold or an operator button, neither of which a `session_mode: new` flow firing reaches. Measured live: 3 of 3 notes unconsumed, 0 of 6 checkpoints carrying a `loop_id`. But the notes themselves are good — `note-e8cf4afcb4b1` names the task, the file and the line for a reader who is not its author, so **task 6.5 worked**. | Nothing, until F43 and F44 are decided. Delivery is a defect, not a judgement. |
| 11.3b | **Confirmed.** `.agentweave/reviews/critic` was checked out detached at `f10d198`, the head of `agentweave/builder`. `master` still contains SEEDED DEFECT 2; the reviewer's copy contains builder's fix. F10 closed with real agents. | Nothing — but worth seeing once yourself. |
| 11.4 | Rung 3 fired once, live: *"could not staff this step: no agent is free to take it. Every agent on the roster is either running a turn, already holding active work, or is the one that completed this task."* It named all three causes rather than only the one needing action. | Whether that reads as staffing or as breakage. |
| 11.5 | One firing staffed **three agents at once** — three `JobRun` rows, three conversations, three turns. And it surfaced **finding F23**, below. | Whether three lines of "task — agent" is comprehension or noise. |
| 11.6 | **Confirmed visible.** One call returns the project total and a per-agent breakdown; no reconstruction from runs. | Whether the number arrives early enough to act on. |

**The drive earned its cost by finding F23** (`scripts/drive/FINDINGS.md`), which every one of the
3037 passing tests missed: while all three agents were mid-turn, the board reported
`current_tasks: []` and `"loop queue is stalled"`. A flow read as dead at its busiest. Fixed, with
four regression tests confirmed failing against the unfixed code, and the fix re-verified live —
the same query now returns `stall_reason: None` and both current items with their agents.


**Staged 2026-08-25 — `group-11-runbook.md` has the commands**, in the order to run them, every
route checked against the live instance. `group-11-staging.md` is its companion and records where
the trial Hub actually stands for each check below: which three cost nothing and can be read now
(11.6, 11.3b, 11.2), which need one firing and what the queue is staged to produce (11.5, 11.4),
which needs real setup (11.1), and why 11.3 is blocked.

**Read §2 of the runbook before re-enabling the flow** — finding F45 means the next firing re-runs
a review `critic` has already done, on every tick, with no stop condition able to end it.

- [ ] 11.1 **A flow with one agent is indistinguishable from a loop.** Run one. If anything reads
      differently, D2 has leaked.
- [x] 11.2 **The handover is legible.** Watch an implementer finish and a reviewer start. It should
      be obvious from the conversation list that a handover happened and to whom.
      **Judged 2026-08-26 by the operator: FAILS.** The routing itself is correct — eight review
      handovers carry a `review_task_id` and one is `withdrawn`, which is F45's fix working — but
      the *legibility* the check asks about is absent. Eleven conversations on `proj-18e5d4e0` are
      all titled `Ledger flow`, across three agents and two roles, with nothing distinguishing a
      review turn from a work turn; the night's drive nearly doubled that count from six. And
      `review_task_id` is exposed on **no** API — `QueueEntryResponse` carries `origin_type` and
      `origin_agent` but not the field that makes an entry a review — so an operator cannot tell a
      review from a work entry without reading the database. Recorded as **F61**; the operator's
      chosen fix is to title a flow conversation by its agent and role. Ticked as *judged*, not as
      *passed*: the judgement is complete and its outcome is a finding.
- [x] 11.3 **The reviewer arrives briefed.** Read what the reviewer was given. If the implementer's
      checkpoint reads as notes-to-self, task 6.5 did not work.
      **Judged 2026-08-26 by the operator: PASSES.** `group-11-runbook.md` section 4 says this
      check "cannot pass, and that is finding F43" — **that line is now stale**, written before
      F43 was fixed on 2026-08-25 and before the overnight drive exercised the run-boundary hook.
      Its own diagnostic expected `3 / 3 / 6 / 0` and now measures **6 notes / 3 unconsumed /
      9 checkpoints / 3 carrying a `loop_id`**: delivery happens.
      The content is not notes-to-self. `ckpt-a545dd785d8d` (builder, probe passed) names the file
      and lines (`ledger/book.py` 20-21), states the decision and why the alternative was rejected,
      and flags a contradiction *for its successor* — that the conversation claims pytest and git
      ran while showing no tool outputs, against predecessor notes saying permission restrictions
      prevent exactly those. That is written for a reader who is not its author, which is what 6.5
      asked for.
      Also verified live in the same pass: `ckpt-9cba6c0e8e40` (critic) **failed its probe** — its
      body claims "work committed and evidence recorded" where the Hub's computed record disagreed
      — and `render_checkpoint` was called against the real row to confirm F50's fix fires on it,
      emitting `Status: failed`, `Probe: failed`, and the paragraph telling the reviewer the
      written half disagreed with the computed half. So the probe caught an over-claiming agent and
      the reviewer is told, rather than being handed it silently.
- [x] 11.3b **The reviewer is looking at the work.** Open the reviewer's workspace during a review
      firing and confirm the author's changes are in it. This is the human half of 4b.2, and it is
      the check that would have caught F10.
      **Judged 2026-08-26 by the operator: PASSES.** Four worktrees live on `aw-stress`, two of
      them reviews (`.agentweave/reviews/critic` at `f10d198`, `.agentweave/reviews/relay` at
      `d8c4355`), each a detached checkout separate from both master and the author's own tree.
      Isolation shown on commits that are *not* reachable from master (`d8c4355`, `f58f6ae`) —
      the runbook's original example `f10d198` is now on master too, because the night's drive
      correctly approved and merged that task, so the demonstration moved to a commit that has not
      yet landed. The mechanism is unchanged and holds.
- [ ] 11.4 **Rung 3 reads as staffing, not breakage.** With no eligible agent, confirm the notice
      says the flow needs someone rather than that it failed.
- [x] 11.5 **Concurrent work is comprehensible.** With a flow running three agents, judge whether the
      board says what is happening or merely that a lot is.
      **Judged 2026-08-26 by the operator: FAILS.** Driven live on the `Width bench` flow
      (`job-f632ee565238`), fired once with its cron parked at `0 4 1 1 *` and restored to disabled
      afterwards. One firing staffed two turns — two `JobRun` rows on one tick, which is correct by
      design since each turn succeeds or fails on its own — and the card listed both with task,
      agent and role.
      Two fixes were confirmed working in the same firing: **F49** (`agent_role` reached `working`,
      which that finding said it never could) and **F56** (the review turn that could not be given a
      commit failed with a stated reason — *"task task-bb86d53a94d5 has no recorded evidence, so
      there is no commit to review"* — instead of wedging the agent's queue silently; all three
      agent queues confirmed unwedged afterwards).
      **What fails the check:** after the firing, `task-bb86d53a94d5` still read `agent_role:
      working` with **zero non-terminal runs in the database** — its review run had *failed*.
      Nobody was mid-turn on it. The board was not merely vague about concurrency; it asserted
      something untrue about it, which is worse than saying nothing. Recorded as **F63**. The
      operator's chosen fix is a third role — `working` only when a run genuinely exists, `held`
      when a reviewer owns the task but nothing is running, `next` otherwise — which also gives
      F23's "a stall the operator can see" a name of its own.
- [x] 11.6 **The spend is visible.** Run a wide flow and confirm you can tell what it cost without
      reconstructing it.
      **Judged 2026-08-26 by the operator: PASSES, with the mixed-CLI gap recorded.** One call to
      `GET /projects/{id}/accounting` returns the project total and a per-agent breakdown with no
      reconstruction from runs — measured after the overnight drive at 34,717,146 tokens over 65
      measured turns (1 unavailable), ≈$7.83, split builder 21.85M / critic 12.55M / relay 322k.
      The gap the operator chose to record rather than block on: `relay` reports tokens but
      `api_equivalent_usd_micros: null`, because the dollar figure comes from the CLI's own report
      (`total_cost_usd` for Claude, `cost` for Codex — `runner_parsing.py:339,641`) and the Codex
      CLI sends none. So a mixed-CLI flow tells you its tokens in full and its money in part.
      Recorded as **F62**. Tokens being complete and per-agent is what the check actually asks for,
      which is why this is a pass with a finding rather than a fail.

## 12. User test guide

- [x] 12.1 Write the operator-facing guide: declaring a decomposition with an order and a reviewer,
      creating a flow over it, and watching it run to fulfilled without relaying anything by hand.
      `openspec/changes/loop-becomes-a-flow/test-guide.md`. Six walkthroughs, each carrying the
      group 11 check it exists to support, so the operator runs one sequence rather than a guide and
      a checklist. Section 4 is the handover and states its three checks **in priority order**, with
      the reviewer's workspace named as the one most likely to be skipped and most costly to skip —
      a review conducted by asking the author is not a review, and it is finding F10 returning.
- [x] 12.2 Cover the three staffing outcomes and how to tell them apart — a step running, a step
      waiting for a busy agent, and a step nobody can take.
      Section 5, as a table of *what you see → what it means → what to do*, and it says which of the
      three asks anything of the operator: only the third raises a notice, because a flow with more
      ready work than agents is in the second state on nearly every tick and a notice for that would
      bury the one that needs them. Both of the quiet states are produced deliberately in the
      walkthrough rather than described, since the failure to guard against is a working flow read
      as a stuck one.
- [x] 12.3 Lead with 11.1. A flow that behaves differently from a loop for a single agent is the
      failure that would undermine confidence in everything else here.
      Section 1, before anything else, and it says to stop if it fails rather than continuing down
      the guide. It also names the setup that makes it a real test — archiving the other agents, so
      the single-agent case is genuinely single-agent rather than incidentally so.

## 13. Finding F45 — a dispatched review leaves the reviewable pool

Found 2026-08-25 while staging group 11, and fixed in the same change for the reason F41's
disposition records: it is a defect in *this change's own delivery*, the change is not archived, and
it is the one thing standing between a supervised flow and one that can be left running.

- [x] 13.1 **Enter a review at `under_review`, in the same commit that queues the turn.**
      `scheduler._enter_selected_task` — one statement of "move the task into the status its
      selection implies", shared by both dispatch sites. Ordinary work keeps `pending -> assigned`
      untouched; a review moves `completed -> under_review`, which takes it out of
      `REVIEWABLE_STATUSES` and therefore out of the ladder's reach.
      Extracted rather than written twice: `_do_fire_job` and `_stage_selection` are ~330 lines
      apart and each carried its own copy of the `pending -> assigned` move, so adding the review
      half to one and not the other is exactly the drift that produces the next F45.
- [x] 13.2 **A task a reviewer holds is in-flight on the board, not absent from it.**
      `WITH_REVIEWER_STATUSES` joins `CURRENT_ITEM_STATUSES` and `_loop_candidates`, and
      `decide_firing` gained an explicit branch recording it as `in_flight`.
      Two defects avoided, both measured rather than reasoned. Without the candidate widening a
      queue holding one dispatched review returned `stalled` with *"no claimable task among 1 open
      (1 under_review)"* — finding F23 one band over. Without the explicit branch the walk fell into
      the **ordinary-work** arm, found the reviewer in `assignee`, and re-fired the review with no
      `is_review` and therefore no checkout of the commit under review — finding F10 by a new route,
      which is worse than the loop this task closes.
- [x] 13.3 **`under_review` bypasses the dependency gate**, for the reason `completed` already does
      one step earlier: it is not one `apply_transition` from `in_progress`, it is one from
      `approved` or `revision_needed`, so the gate has no question to answer and asking produces an
      unactionable stall.
- [x] 13.4 **The review turn is told how to end.** `agents.py`'s review context named
      `revision_needed` — an edge `TRANSITIONS` does not offer from `completed` — and said nothing
      at all about work that is *correct*. A reviewer following the instruction was refused; one
      finding no fault had no stated exit. Measured across the trial Hub's whole history: **no
      flow-dispatched review had ever recorded a transition.** Both verdict edges are now named,
      and 13.1 is what makes them legal.
- [x] 13.5 Regression tests: `hub/tests/test_review_leaves_the_pool.py`, 9 tests, **5 confirmed
      failing against the unfixed code** — the four that still pass are the set-shape assertions and
      the ordinary-work path, which is the correct split.
- [x] 13.6 **Re-verified live against the trial Hub**, 2026-08-25, on `job-bdea22bb0308`
      (`ledger-stress`). Not closed by unit tests: F41 is this change's own precedent for a fix that
      passed six of them and could never fire.
      One firing moved both staged tasks `completed -> under_review` and the queue went
      `{completed: 2, rejected: 1}` -> `{under_review: 2, rejected: 1}`. A **second** firing staffed
      nothing — which is the assertion — and `stall_reason` stayed `None` rather than reporting the
      flow dead. The job is back to `enabled: False` on its original `*/5` cron.
      **The live drive earned its keep twice over**, finding two defects no unit test had: F48, a
      500 on the second firing, and F49, an `agent_role` branch that had never once fired in
      production. Both are below.

- [x] 13.7 **F48 — a manual Run on an all-in-flight loop said "Failed to fire job".**
      `DECISION_IN_FLIGHT` records nothing by design (F23), so the route read an *earlier* `JobRun`
      and reported a 500 about a healthy flow. Pre-existing; F45 made it the common case, and the
      runbook written the same day tells the operator to press Run. Now 409 with a sentence,
      answered by re-deciding rather than by guessing from a row.
- [x] 13.8 **F49 — `agent_role` could never be `working`.** F26's fix built its lookup as
      `set(decision.in_flight)`, a set of `(task_id, agent)` **tuples**, and tested membership with
      a bare `task.id`. The line above it gets the same conversion right. Green because **no Python
      test for `agent_role` existed at all** — the five vitest cases feed the renderer a value the
      fixture invents. F41's pattern a third time, in this same change.
      `hub/tests/test_board_agent_role.py` is the missing half: both roles, both causally confirmed
      failing against the unfixed code, and both re-verified live.


## 14. Findings F43 and F44 - the reviewer's briefing is generated, and it is the author's

Found 2026-08-25 while staging group 11's task 11.3, which handoff 0086 had recorded as "not
answerable from this drive: no checkpoint was generated." It is not answerable because it *cannot*
be. Same disposition as groups 13 and F41 before it: a defect in this change's own delivery, the
change unarchived, so it is fixed here. Design D17.

- [x] 14.1 **Generate the author's checkpoint at the run boundary.**
      New `hub/hub/checkpoint_handover.py`. The flow instructs every agent to brief its reviewer via
      `submit_checkpoint_notes` and no path delivered it: `generate_checkpoint` had two callers, a
      context threshold and an operator button, and a flow conversation reaches neither. Measured
      live: 3 of 3 notes unconsumed, 0 of 6 checkpoints carrying a `loop_id`.
      Dispatched off the boundary, never awaited on it - generation is a blocking ~19s CLI spawn,
      and the reasoning is `checkpoint_trigger`'s, restated because the failure mode is identical.
- [x] 14.2 **Both runners reach it.** Wired beside `evaluate_run_end` at both call sites in
      `api/v1/agent_trigger.py`, for the reason that check's own comment gives: the boundary is
      AgentWeave's, not either agent's. Wiring one and not the other is the drift 13.1 warns about.
- [x] 14.3 **Gated on the agent having actually left notes** - the operator's decision, 2026-08-25.
      A handover with nothing recorded has nothing to deliver, so it spends nothing. The cost is
      stated rather than discovered later: an agent that ignores the instruction produces no
      briefing, and its reviewer is no worse off than before this group.
- [x] 14.4 **F44 - a review turn is briefed by the author, not by whoever finished last.**
      `checkpoints.checkpoint_by_task_author` resolves through the transition history;
      `scheduler._briefing_checkpoint` is the one place both firing paths ask the question, and
      `is_review` is the whole difference between the two. An ordinary continuation turn still uses
      `latest_checkpoint_for_loop`, which was never wrong for the question it was written for.
      Had F43 shipped alone, the live notes show **two firings in three** would have briefed the
      reviewer with an unrelated agent's account of a different task.
- [x] 14.5 Regression tests: `hub/tests/test_handover_briefs_the_reviewer.py`, 10 tests.
      **Causally confirmed both halves**: disabling the F43 trigger fails 5 of 10 (the five that
      require a checkpoint to exist); disabling the F44 selector fails exactly 1 (the wiring
      assertion, while the selector's own test correctly still passes).
      The module **never inserts a `Checkpoint` for an F43 assertion** - it drives `consider_handover`
      and asserts on what that produced. Writing it the convenient way is precisely how F43 stayed
      green: `test_scheduler.py`'s existing briefing test inserts a row with `loop_id` already set
      and asserts the briefing renders it, so it never exercised anything that produced one.
- [x] 14.5b **Measured the first implementation against the live database, and it could not have
      fired.** Two gates each fatal: `run.task_id` required but NULL on 6 of 10 live runs that
      completed a task, and notes looked for in the completing conversation when 0 of 4 live notes
      are there (`session_mode: new` gives every firing its own conversation). Both passed ten green
      tests. The fixture now matches production on both counts, and narrowing either gate back fails
      5 of 10. Caught before push — the first of this change's four dead-fix instances that was.
- [x] 14.6 **Re-verified live against the trial Hub**, 2026-08-25, on `ledger-stress`
      (`loop-e4b864459808`), with `checkpoint_runner_id` set to the project's `Haiku cheap` runner.
      Not closed by unit tests - F41, F45 and F49 are this change's own three precedents for a fix
      that passed its tests and could not fire.
      **The counterfactual was measured first, read-only, across all 156 runs in the live database:
      the first implementation fires 0 times, the corrected one fires 2.** Then driven for real:
      both produced a checkpoint carrying the author's note, including `note-e8cf4afcb4b1` - the
      exact note F43's own write-up cites as written for `critic` about `task-23a0986e7fe9`.
      Checkpoints with a `loop_id` went **0 of 6 -> 2**, and unconsumed notes **4 -> 2** (the
      remaining two belong to `relay`, whose runs completed no task).
- [x] 14.7 **F50 - decide what a reviewer is shown when a checkpoint fails its probe.** Found by
      14.6's drive and caused by F43 becoming real: 1 of the 2 generated checkpoints was graded
      `failed` against the Hub's own envelope, and `render_checkpoint` surfaces neither `status` nor
      `probe_status`, so it briefs identically to one that passed. The operator's call between
      skipping it, rendering the failure, and leaving it.

      **Resolved 2026-08-26 (pre-authorised by the operator during prep, option 2 — render the
      failure, don't skip it):** `render_checkpoint` (`hub/hub/checkpoint_generation.py`) now
      states `Status: <status>` and, when set, `Probe: <probe_status>` in the header, and — only
      when `status == "failed"` — a stated warning ahead of the written body explaining that the
      summary disagreed with the Hub's own computed envelope and that the computed sections above
      remain accurate regardless. Two new tests in `test_checkpoint_generation.py`
      (`test_a_ready_checkpoint_states_its_status_without_a_failure_warning`,
      `test_a_checkpoint_that_failed_its_probe_states_the_failure_instead_of_hiding_it`).
      Mutation-checked: reverting the render change made both new tests fail exactly as predicted
      (`assert "Status: failed" in rendered` on the unmodified, pre-fix render). Verified LIVE:
      restarted the trial Hub onto this fix and fetched
      `GET /projects/proj-18e5d4e0/checkpoints/ckpt-9cba6c0e8e40/rendered` over real HTTP — Q4's
      original failed checkpoint, unchanged since 2026-08-25. The response now reads
      `Status: failed`, `Probe: failed`, and the stated warning ahead of the written body, exactly
      as the unit tests predict. The sibling `ready` checkpoint (`ckpt-a545dd785d8d`) was not
      re-fetched in this pass; the negative-case unit test covers that shape instead.
