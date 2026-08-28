# Tasks — A delivery attempt means a delivery

Round discipline: this file is written in round 1. **Rounds 2 and 3 revise it**, and implementation
starts only after round 3. Nothing here is closed by a plan existing.

**Round 1 was written on the night of 2026-08-28 by the run that found F114.** It has not been
reviewed by anybody, and its author also wrote the change it depends on — which is the situation the
rounds exist for.

## 1. Review rounds

- [ ] 1.1 **Round 2** — re-derive from the code without re-reading round 1's reasoning. The three
      files are `hub/hub/turn_scheduler.py` (the refusal branch, `:141-231`),
      `hub/hub/inbound_queue.py` (`return_run_entries`, `:181-235`), and
      `hub/hub/api/v1/agent_trigger.py`'s `TriggerAgentError` (`:239`).
- [ ] 1.2 **Round 2** — verify D3's load-bearing claim by reading, not by recall: that every
      condition this change stops counting is **agent-wide**, so nothing is starving behind the
      entry it protects. The list to check is the sites *not* marked `request_level` in
      `2026-08-28-a-refused-request-says-so`: `:441`, `:461`, `:480`, `:507`, `:517`, `:535`,
      `:737`, `:756`, `:817`, `:912`. **If any one of them is entry-specific rather than
      agent-wide, D3 is wrong and the change needs a different gate.**
- [ ] 1.3 **Round 2** — enumerate every test that reaches `DELIVERY_ATTEMPT_LIMIT` through the
      *refusal* path rather than through a failed run, and write them into this file as explicit
      items. Start with `test_delivery_attempts.py` and `test_runner_binding_redrain.py`.
      A behaviour change discovered as a test failure is a behaviour change nobody decided — and
      the sibling change made exactly that mistake by answering this question for only half the
      population (see its 1.2f).
- [ ] 1.4 **Round 3** — independent second comparison against the code, including round 2's
      changes. Check specifically against *Repeated delivery failure does not wedge an agent*
      (`agent-conversation-workspace`), whose sentence about retrying without limit this change
      walks into deliberately (D4).
- [ ] 1.5 **Round 3** — verify D4's escape route empirically rather than by argument: read what
      `GET /queue/{agent}/status` and the conversation view actually show for an entry that has
      been waiting a long time. If "waiting" is not distinguishable from "stuck" on those surfaces,
      this change needs the companion D6 describes and should not ship alone.
- [ ] 1.6 **Round 3** — confirm the delta's requirement is falsifiable by a test that does not
      restate the implementation.

## 2. The counter counts deliveries

- [ ] 2.1 In `schedule_agent`'s `except TriggerAgentError` branch, count a delivery attempt only
      when the refusal is request-level. Document the reason at the line, the way the transient
      branch beside it already is.
- [ ] 2.2 Test: an environment-level refusal leaves `delivery_attempts` unchanged, however many
      times the agent is scheduled.
- [ ] 2.3 Test: the F114 reproduction — five messages to an agent with no runner bound leave five
      entries queued and none withdrawn.
- [ ] 2.4 Test: `POST /conversations/{id}/continue`, pressed repeatedly, does not consume the entry
      it offers to start.
- [ ] 2.5 Test: a request-level refusal still counts, and still abandons at the limit.
- [ ] 2.6 Test: an entry delivered to a run that fails still counts through `return_run_entries`
      and is unaffected by this change.
- [ ] 2.7 Mutation-check each: restore the unconditional increment and confirm 2.2–2.4 fail while
      2.5 and 2.6 pass.

## 3. Verification

- [ ] 3.1 Full hub suite **with `claude` stripped from PATH**.
- [ ] 3.2 CLI suite, UI suite, `ruff` / `black` / `mypy` / `npm run lint` / `tsc --noEmit`.
- [ ] 3.3 `npx openspec validate --specs --strict`.
- [ ] 3.4 **Drive it live** against the trial Hub: repeat `scripts/drive/t_queue_attrition.py` and
      `scripts/drive/t_continue_burns_attempts.py`, which are the measurements that produced this
      change, and confirm both now leave the input intact.
- [ ] 3.5 Sync the delta into `openspec/specs/agent-conversation-workspace/spec.md`, archive with
      `--skip-specs`, and fix the doubled date prefix.
- [ ] 3.6 Update `scripts/drive/FINDINGS.md`: F114 closed, with the live re-measurement.
