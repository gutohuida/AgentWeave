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

- [ ] 6.1 Test: a flow fires A, A checkpoints, the flow fires B, and B's briefing carries A's
      checkpoint content.
- [ ] 6.2 Test: each checkpoint in a multi-agent lineage identifies its author.
- [ ] 6.3 Test: a document-less loop's lineage behaves exactly as before.
- [ ] 6.4 Correct the `Checkpoint` model comment — *"Linear, single-agent chain"* — to say what is
      now true, and say why it changed. The comment is the artefact that disagreed with §231
      (design D7).
- [ ] 6.5 Change the instruction an agent is given when writing a checkpoint so it addresses whoever
      continues the work, not itself. Without this, agents write shorthand a reviewer inherits.

## 7. The tool surface

- [ ] 7.1 Test: `create_flow` without a document is refused, stating why.
- [ ] 7.2 Test: `create_loop` with a document is refused and names `create_flow`.
- [ ] 7.3 Test: both tools produce a job and a loop record, differing only in the declared document.
- [ ] 7.4 Add `create_flow` to `hub/hub/mcp_server.py`. **Stdlib and fastmcp only** — anything it
      needs from the Hub is restated there, with a test asserting the two agree.
- [ ] 7.5 Add the refusal to `create_loop`, in the style that file already uses for a loop with no
      stop condition.

## 8. The briefing

- [ ] 8.1 Test: a flow's briefing states that the flow routes the work onward.
- [ ] 8.2 Test: a loop's briefing does not claim that anything will route its work onward.
- [ ] 8.3 Implement it in `_compose_loop_briefing`, within the bound `agent-loops` §257 sets — it
      competes for room with the checkpoint and the task.

## 9. Presentation

**9.3 stopped being speculative when group 5 landed (2026-08-24).** `_batch_loop_summaries` takes
`decision.selections[0]` and renders one current item; as of group 5 a firing can genuinely staff
several, so the board now under-reports a working flow rather than merely being unprepared for one.
The field is already a list and the derivation is already shaped for it — what is missing is 9.4's
decision about *how* several are shown, which is why this was not widened along with the firing.

- [ ] 9.1 Test: a change of agent breaks a collapsed run of consecutive firings.
- [ ] 9.2 Implement that break, and confirm collapsing still does not reorder.
- [ ] 9.3 Show several current items where a flow is staffing several tasks, each naming its agent.
- [ ] 9.4 **Decide what the dependency board shows for concurrent work** — per card, per layer, or a
      flow header — and record it. Open question in the design.
- [ ] 9.5 `make ui` after `npm run build`; commit `hub/ui/src` and `hub/hub/static/ui` together.

## 10. Verification an agent can do

- [ ] 10.1 `pytest hub/tests/ -q` passes, with the three pre-existing `test_pty_runner` environment
      failures unchanged and no new failures.
- [ ] 10.2 `pytest tests/ -q` passes.
- [ ] 10.3 `ruff check hub/`, `black --check hub/`, `mypy hub/hub/` clean on touched files;
      `cd hub/ui && npm run lint`.
- [ ] 10.4 `openspec validate loop-becomes-a-flow` reports valid.
- [ ] 10.5 The whole chain: a document declares A → B, a flow runs A with one agent, a second agent
      reviews and approves it, and B then starts — with no operator action at any point.
      **The reviewer must reach its verdict from the checkout, not by asking the author** (design
      D9); a chain that completes because the two agents talked has not demonstrated this.
- [ ] 10.6 Confirm the 20 `agent-loops` requirements this change does not modify still hold, by
      running their scenarios against the flow implementation rather than assuming.

## 11. Verification only a human can do

- [ ] 11.1 **A flow with one agent is indistinguishable from a loop.** Run one. If anything reads
      differently, D2 has leaked.
- [ ] 11.2 **The handover is legible.** Watch an implementer finish and a reviewer start. It should
      be obvious from the conversation list that a handover happened and to whom.
- [ ] 11.3 **The reviewer arrives briefed.** Read what the reviewer was given. If the implementer's
      checkpoint reads as notes-to-self, task 6.5 did not work.
- [ ] 11.3b **The reviewer is looking at the work.** Open the reviewer's workspace during a review
      firing and confirm the author's changes are in it. This is the human half of 4b.2, and it is
      the check that would have caught F10.
- [ ] 11.4 **Rung 3 reads as staffing, not breakage.** With no eligible agent, confirm the notice
      says the flow needs someone rather than that it failed.
- [ ] 11.5 **Concurrent work is comprehensible.** With a flow running three agents, judge whether the
      board says what is happening or merely that a lot is.
- [ ] 11.6 **The spend is visible.** Run a wide flow and confirm you can tell what it cost without
      reconstructing it.

## 12. User test guide

- [ ] 12.1 Write the operator-facing guide: declaring a decomposition with an order and a reviewer,
      creating a flow over it, and watching it run to fulfilled without relaying anything by hand.
- [ ] 12.2 Cover the three staffing outcomes and how to tell them apart — a step running, a step
      waiting for a busy agent, and a step nobody can take.
- [ ] 12.3 Lead with 11.1. A flow that behaves differently from a loop for a single agent is the
      failure that would undermine confidence in everything else here.
