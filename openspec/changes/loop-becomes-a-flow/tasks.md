# Tasks — the loop becomes a flow

**Order matters more than usual here.** Groups 1–2 change no behaviour and are the safety net for
everything after: a flow with one agent must remain indistinguishable from today's loop, and the
existing loop suite passing unmodified is what proves it.

**Depends on `task-dependencies`** (the graph, the gate, and the reviewer field) and, in practice,
on `loop-notices-and-reacts` for the shared firing decision this change adds an answer to.

## 1. The set-valued claim, behaviour unchanged

- [ ] 1.1 Test: the whole existing loop suite passes unmodified. This is the bar for the entire
      group — a set of one must be indistinguishable from one.
- [ ] 1.2 Test: `_claim_loop_task` returning a set of one produces the same claim, the same briefing
      and the same `JobRun` as today, for each of the pending, resuming and empty cases.
- [ ] 1.3 Change `_claim_loop_task` to return a set, still selecting exactly one member.
- [ ] 1.4 Update `_batch_loop_summaries` (`hub/hub/api/v1/jobs.py`) to read the set, still rendering
      one current item. Import the derivation; do not restate it.
- [ ] 1.5 Update `LoopSummary` and any response schema so current items are a list, and confirm the
      UI reads a list of one without visible change.

## 2. The agent becomes a per-selection value

- [ ] 2.1 Test: a loop with no document fires `AIJob.agent` on every firing, unchanged.
- [ ] 2.2 Test: a selection carrying an explicit agent fires that agent, and the run, conversation,
      queue entry and credential all attribute to it.
- [ ] 2.3 Carry an agent alongside each selected task through `_do_fire_job`, defaulting to
      `AIJob.agent` (design D2). Leave the column `NOT NULL`.
- [ ] 2.4 Confirm nothing reads `job.agent` downstream of the selection where the selection's agent
      is what is meant — a source scan, not a reading.

## 3. Actor-aware claimability

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
      not, falling back to availability; no declaration at all; and nobody eligible.
- [ ] 4.2 Test: an agent that is running, or that holds a task in an active status, is not selected
      while another eligible agent exists.
- [ ] 4.3 Test: an agent with no runner bound is not selected, and is treated as unavailable rather
      than failing the firing.
- [ ] 4.4 Test: a single-agent project reaches rung 3 by the general rule, with no special-case code
      path — assert the path, not only the outcome.
- [ ] 4.5 **Decide how a declared reviewer resolves** — against charter names, agent names, or both —
      and record it in design D4. `task-dependencies` D11 deliberately left this here.
- [ ] 4.6 Implement the ladder.
- [ ] 4.7 Implement rung 3's surfacing, following the event and SSE pattern the stop path uses.
      Confirm it leaves the job enabled and scheduled.

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
- [ ] 10.6 Confirm the 20 `agent-loops` requirements this change does not modify still hold, by
      running their scenarios against the flow implementation rather than assuming.

## 11. Verification only a human can do

- [ ] 11.1 **A flow with one agent is indistinguishable from a loop.** Run one. If anything reads
      differently, D2 has leaked.
- [ ] 11.2 **The handover is legible.** Watch an implementer finish and a reviewer start. It should
      be obvious from the conversation list that a handover happened and to whom.
- [ ] 11.3 **The reviewer arrives briefed.** Read what the reviewer was given. If the implementer's
      checkpoint reads as notes-to-self, task 6.5 did not work.
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
