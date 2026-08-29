# Tasks — A delivery attempt means a delivery

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

**Round 1 was written on the night of 2026-08-28 by the run that found F114.** It has not been
reviewed by anybody, and its author also wrote the change it depends on — which is the situation the
rounds exist for.

## 1. Review rounds

- [x] 1.1 **Round 2** — re-derive from the code without re-reading round 1's reasoning.
      **Round 1's central claim was falsified and the design changed** — see 1.2 and design D3a.
      D1's account of the two counter sites survives unchanged: `return_run_entries` counts a
      delivery that was attempted, `turn_scheduler` counts one that was not.
- [x] 1.2 **Round 2** — verify D3's load-bearing claim by reading, not by recall.
      **It is wrong, and the change needed a different gate.** Two of the unmarked sites are
      entry-specific:
  - [x] 1.2a `:756` "Could not prepare isolated worktree" — the workspace comes from
        `task_workspace.resolve_turn_workspace_inputs(…, task=binding.task)` and is the **task's**
        checkout whenever the turn names a task. So the same raise site is entry-specific or
        agent-wide depending on the entry, which no static per-site flag can express. Stopping the
        count there reintroduces F56's starvation: `schedule_agent` always takes the *oldest*
        eligible entry as `controlling` (`turn_scheduler.py:98`), so an entry whose checkout can
        never be prepared blocks every other conversation forever.
  - [x] 1.2b `:441` "Conversation is unavailable" — entry-specific, but not reachable from this
        path, because `schedule_agent` resolves the conversation itself and hands the trigger its
        id in the same session. Recorded rather than dismissed.
  - [x] 1.2c `:461`, `:480`, `:507` — confirmed agent-wide: all three are properties of the agent's
        own runner binding, and all three are the sites the F114 measurement went through.
  - [x] 1.2d `:517`, `:535`, `:737`, `:912` — agent-wide or project-wide, and all either transient
        already or unreachable from `schedule_agent` (which checks for a running run first).
  - [x] 1.2e `:817` "Could not materialize canonical context" — an `OSError` writing under the
        agent's own context directory. Agent-wide, but **left unmarked** by the revised gate,
        because "conservatively mark only what is certainly agent-wide" is the rule and an `OSError`
        could in principle be about a path this turn alone uses.
- [x] 1.3 **Round 2** — enumerate every test that reaches `DELIVERY_ATTEMPT_LIMIT` through the
      *refusal* path rather than through a failed run. Nine files mention the counter; **none
      reaches the limit through the refusal path.**
  - [x] 1.3a `test_delivery_attempts.py::test_the_third_failure_abandons_the_entry_with_a_reason`
        and `::test_an_abandoned_entry_stops_controlling_the_queue` — both drive
        `fail_a_delivery`, which marks the entry `delivered` and calls `return_run_entries`.
        Untouched site.
  - [x] 1.3b `test_review_divergence.py` (`:561-575`) — calls `return_run_entries` directly.
        Untouched site.
  - [x] 1.3c `test_task_turn_collision.py` (`:432-445`) — asserts `delivery_attempts == 0` after
        `DELIVERY_ATTEMPT_LIMIT + 1` iterations of the **transient** branch. Not only unaffected:
        it is the precedent this change's gate is modelled on.
  - [x] 1.3d `test_agent_chat.py` (`:595`) — sets the fields by hand to render an abandoned entry.
  - [x] 1.3e `test_runner_binding_redrain.py` — mentions the counter only in its docstring, as F96's
        symptom. This change makes that symptom rarer, so if it moves at all it moves toward
        passing.
  - [x] 1.3f **And the other half of the question, which the sibling change got wrong:** which
        tests reach a site the revised gate *marks*? `test_runtime_diagnostics.py` and
        `test_agent_trigger.py::test_unbound_agent_accumulates_queue_with_visible_reason` both
        trigger once and assert the first response, so neither reaches a second attempt.
        `test_spawn_failure_marks_run_failed` looks like a casualty and is not — its spawn is
        attempted and fails, so it counts through `return_run_entries` (and it is currently flaky
        for an unrelated reason, F109). **Implementation must confirm this by running them, not by
        citing this list.**
- [x] 1.4 **Round 3** — independent second comparison against the code, including round 2's
      changes. **The requirement does not cover this path**, which neither earlier round noticed:
      its scoping sentence is about *"a failed run's input"* and *"how many times a queued input has
      **failed to be delivered**"*, and this change touches only the path where no run existed and
      nothing was delivered. So the delta is correctly ADDED-only, no `MODIFIED` requirement is
      needed, and the behaviour F114 complains about turns out never to have been specified at
      all — `F56` added the second counting site without one. See D4a.
- [x] 1.5 **Round 3** — verify D4's escape route empirically. **It holds.** Driven on the trial
      Hub: `GET /queue/{agent}/status` returns `waiting_count`, `waiting_reason` and
      `delivery_attempts`, and the conversation view states the reason twice more — under the
      transcript and under the composer. Waiting is distinguishable from stuck.
      **The limit, recorded rather than glossed:** none of those surfaces shows *how long*, so an
      entry waiting three weeks renders exactly like one waiting three seconds. That is what D6's
      rejected alternative would add. And the sentence they all carry is itself wrong for an unbound
      agent (**F111**), which weakens this evidence in presentation though not in substance.
- [x] 1.6 **Round 3** — confirm the delta's requirement is falsifiable by a test that does not
      restate the implementation. **Half of it did restate it.** Three scenarios asserted "no
      delivery attempt is counted", which names the mechanism rather than anything a person can
      observe — a test written from them would pass by mirroring the code. Fixed by adding
      *The input is still there when the agent becomes able to run*, whose observable is the one
      that actually matters and the one F96 cares about: the operator performs the repair and gets
      **every** message they sent. The counter scenarios are kept beside it as the mechanism's own
      check, not as the requirement's only evidence.

## 2. The counter counts deliveries

- [x] 2.0 **Revised by round 2 (D3a).** Add an explicit *agent-wide* classification to
      `TriggerAgentError`, defaulting to `False`, documented the way `transient` and
      `request_level` are — including why it is a third question rather than a combination of the
      first two. Mark exactly three sites in `agent_trigger.py`:
  - [x] 2.0a `:461` no runner is bound
  - [x] 2.0b `:480` the bound runner's row no longer exists
  - [x] 2.0c `:507` the bound runner's CLI is not on PATH
      **Nothing else, and `:756` in particular stays unmarked** — see 1.2a.
- [x] 2.1 In `schedule_agent`'s `except TriggerAgentError` branch, count a delivery attempt except
      when the refusal is agent-wide. Document the reason at the line, the way the transient branch
      beside it already is.
- [x] 2.2 Test: an agent-wide refusal leaves `delivery_attempts` unchanged, however many times the
      agent is scheduled.
- [x] 2.2a Test: an **entry-specific** refusal still counts and still abandons at the limit — the
      case round 1 would have broken. Use `:756`'s shape: a turn bound to a task whose checkout
      cannot be prepared, with other input queued behind it, and assert the queue moves on.
- [x] 2.3 Test: the F114 reproduction — five messages to an agent with no runner bound leave five
      entries queued and none withdrawn.
- [x] 2.3a Test (round 3, 1.6): the **outcome**, not the counter — send several messages to an
      agent with no runner, press Continue, then bind a runner, and assert every message is
      delivered. This is the one a reader can check against the product rather than against the
      implementation.
- [x] 2.4 Test: `POST /conversations/{id}/continue`, pressed repeatedly, does not consume the entry
      it offers to start.
- [x] 2.5 Test: a request-level refusal still counts, and still abandons at the limit.
- [x] 2.6 Test: an entry delivered to a run that fails still counts through `return_run_entries`
      and is unaffected by this change.
- [x] 2.7 Mutation-check each. **Three, all caught:** the unconditional increment restored (the
      pre-F114 code) fails 2.2/2.3/2.4/2.3a while 2.2a and 2.5 keep passing; **round 1's rejected
      gate** — `request_level` instead of `agent_wide` — fails 2.2a, which is the starvation case
      round 2 found; and removing `agent_wide=True` from the no-runner raise site fails the
      end-to-end test.
- [x] 2.8 **Added during implementation, because 2.2–2.6 could not catch it.** Every one of those
      constructs `TriggerAgentError` itself, so all six would pass with the three raise sites never
      marked — the gate tested, wired to nothing.
      `test_the_real_unbound_agent_path_carries_the_flag` drives the real route with a real unbound
      agent, five triggers, no patching of the trigger at all.

## 3. Verification

- [x] 3.1 Full hub suite **with `claude` stripped from PATH**: **3,510 passed, 84 skipped,
      1 xfailed, 0 failed** (23m11s). Fully green — the F109 flake did not fire on this run.
- [x] 3.2 CLI suite, UI suite, `ruff` / `black` / `mypy` / `npm run lint` / `tsc --noEmit`.
- [x] 3.3 `npx openspec validate --specs --strict`.
- [x] 3.4 **Drive it live** against the trial Hub. Both re-measured on the fixed code:
      five messages to an unbound agent leave **5 queued, 0 withdrawn, 0 attempts** (message 1 used
      to be destroyed), and three Continue clicks leave the entry queued at 0 attempts (two used to
      be enough). Both scripts now mint a fresh agent name per run — reusing one mixed the previous
      run's withdrawn rows into the reading, which was misread once before being caught.
      **Not driven live: the delivery after the repair.** Binding a runner here spawns a real
      provider run and no token budget was agreed for the overnight session, so that outcome rests
      on `test_the_input_survives_until_the_agent_can_run`.
- [x] 3.5 Sync the delta into `openspec/specs/agent-conversation-workspace/spec.md`, archive with
      `--skip-specs`, and fix the doubled date prefix. Synced: 1 requirement, 7 scenarios, taking
      the capability to 62. `npx openspec validate --specs --strict` passes 42/42. Archived, and the
      prefix renamed — `openspec archive` stamped it `2026-08-29-2026-08-28-…`, which is the doubled
      form the dead-end note predicts, doubled across a date boundary this time.
- [x] 3.6 Update `scripts/drive/FINDINGS.md`: F114 closed, with the live re-measurement, and
      with what the three rounds changed — the fix the finding proposed is not the fix that
      shipped, which is worth recording where the next reader meets the finding.
