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

- [ ] 3.1 Test: a `completed` task is offered to an agent that did not complete it, and not to the
      one that did.
- [ ] 3.2 Test the correctness property directly — every task the flow offers an agent can be moved
      by that agent to a review outcome without author/reviewer separation refusing it. Assert this
      rather than inferring it from the cases above (design D3).
- [ ] 3.3 Test: `CLAIMABLE_LOOP_TASK_STATUSES` does **not** gain `completed`. Widening the tuple is
      the obvious wrong fix and it is actor-blind.
- [ ] 3.4 Implement claimability as a question about `(task, agent)`, using `_agent_that_completed`
      rather than a second implementation of the same question.
- [ ] 3.5 Confirm the board's derivation and the firing's agree for a queue holding a `completed`
      task — the same 13.1 property, now with an actor in it.

## 4. Reviewer resolution

- [ ] 4.1 Test each rung of design D4 independently: a declared reviewer that resolves; one that does
      **not** resolve, which is surfaced and never substituted (amended 2026-08-24 — this said
      "falling back to availability", which contradicted shipped behaviour); no declaration at all,
      falling back to availability; and nobody eligible.
- [ ] 4.2 Test: an agent that is running, or that holds a task in an active status, is not selected
      while another eligible agent exists.
- [ ] 4.3 Test: an agent with no runner bound is not selected, and is treated as unavailable rather
      than failing the firing.
- [ ] 4.4 Test: a single-agent project reaches rung 3 by the general rule, with no special-case code
      path — assert the path, not only the outcome.
- [x] 4.5 **Decide how a declared reviewer resolves** — against charter names, agent names, or both —
      and record it in design D4. `task-dependencies` D11 deliberately left this here.
      **Answered 2026-08-24 without a decision being needed: agent names.**
      `a-reviewer-can-see-the-work` shipped `review_turn.resolve_declared_reviewer` first, matching
      the declared string against roster `Agent.name` for the project and treating an archived agent
      as unresolved. Recorded in D4. The flow reuses that function rather than writing a second
      resolution — so 4.6 implements the ladder *around* it, not a replacement for it.
- [ ] 4.6 Implement the ladder, **calling `review_turn.resolve_declared_reviewer` for rung 1 rather
      than resolving the declaration again.** Two implementations of "who did the document name" is
      the drift shape this repo has been bitten by three times.
- [ ] 4.7 Implement rung 3's surfacing, following the event and SSE pattern the stop path uses.
      Confirm it leaves the job enabled and scheduled.

## 4b. The review turn — a reviewer must see the work

**Added 2026-08-24 (design D9).** `a-reviewer-can-see-the-work` shipped after this change was
written. Without this group a flow fires the reviewer into its own working checkout, where the
author's unmerged work does not exist — reproducing finding F10, which that change existed to fix.

- [ ] 4b.1 Test: a flow firing an agent for a `completed` task produces a queue entry carrying
      `review_task_id`, and the resulting turn is a review turn.
- [ ] 4b.2 Test the property that matters rather than the plumbing: the reviewing agent's workspace
      contains a commit that exists only on the author's branch. This is F10's own assertion, and
      task 5.5 of `a-reviewer-can-see-the-work` is the pattern to copy.
- [ ] 4b.3 Test: a review turn that cannot be prepared surfaces `ReviewTurnRefused`'s stated reason
      and does **not** fire the agent with an ordinary turn instead.
- [ ] 4b.4 Test: a firing that staffs ordinary (non-review) work still carries no `review_task_id`,
      so nothing that is not a review acquires a checkout.
- [ ] 4b.5 Pass `review_task_id` from the selection through `new_entry` in `_do_fire_job`
      (`hub/hub/scheduler.py:1187`). This is the one-argument gap D9 names.
- [ ] 4b.6 Confirm the reviewer resolved by 4.6 is the agent the checkout is built for — review
      isolation is per agent, so a mismatch here builds the right checkout for the wrong agent.

## 5. Width

- [ ] 5.1 Test: two startable tasks and two eligible agents start both.
- [ ] 5.2 Test: three startable tasks and one eligible agent start one, leaving the others' status
      and assignee untouched.
- [ ] 5.3 Test: a dependent task does not start alongside its prerequisite.
- [ ] 5.4 Test: one agent resolving for two tasks is started for one only (design D6), and the
      dropped selection is visible rather than silent.
- [ ] 5.5 Implement multi-selection, bounded by the graph and by available agents. No configured cap
      (design D5).
- [ ] 5.6 Confirm `token_budget` and `stop_at` still bound a flow that is running several agents.

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
