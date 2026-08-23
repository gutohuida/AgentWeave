# Stress-test plan — driving AgentWeave as a real operator

**Target:** trial Hub `127.0.0.1:8010` (per CLAUDE.md; port 8000 is the operator's real usage and
is off limits). Cheap runners only: `Haiku (cheap)` = claude-haiku-4-5, `Codex Mini (cheap)` =
gpt-5.4-mini. Both CLIs probe `runnable: true`.

**Project under test:** `ledger` — a new, real Python repo at `C:\Users\huida\Documents\aw-stress`.
Real code, real pytest suite, and **three deliberately seeded defects** so review, evidence and
gates have genuine subject matter rather than make-work. A fixture with nothing at stake does not
exercise the parts of the product that decide whether work is good.

**Method:** every scenario is driven the way an operator would drive it — through the REST API and
the UI, never by inserting rows. A finding only counts when it is reproduced against a running
system; code-read suspicions (S1–S12 in `SURVEY.md`) are hypotheses until a scenario kills or
confirms them.

## Scenarios

| ID | What is driven | Targets | Kills/confirms |
|---|---|---|---|
| T-SPEC | Whole spec flow: create → explore → close → propose → approve → tasks materialise → evidence → coverage → archive | spec_service, spec_lifecycle, requirement_gate, spec_tasks | S11 |
| T-DEP | Dependency chain A→B→C, middle one rejected; then reopened | dependency_gate, task_transition_service | — |
| T-HOP | Agent→agent chain under `hop_budget=2`, then an operator message injected mid-chain | turn_scheduler, inbound_queue | **S1** |
| T-LOOP | A loop that actually fires: claims, works, drains, stops. Then re-enable the stopped job | scheduler, loops | **S6, S7, S9, S10** |
| T-CRON | Job at `0 0 1 * 1` (DOM **and** DOW restricted); compare stored `next_run` against APScheduler's own next fire | scheduler | **S4, S5** |
| T-QA | `ask_user` blocks a run; bound task parks to `blocked`; answer releases it. Then let one time out | questions, run_task_binding | — |
| T-PERM | `manual` posture: approve, deny, and let one expire | permission_requests, codex_appserver | — |
| T-STOP | Stop a run mid-flight | agent_trigger stop path, queue return | — |
| T-KILL | Kill the Hub with a run in flight; restart | run_reconciliation | — |
| T-CONC | Two concurrent triggers for one agent | turn_scheduler lock | — |
| T-VOL | Verbose run; measure output rows, commit cost, SSE behaviour | output_recording | **S2, S3** |
| T-WT | Two writing agents touching the same file in parallel worktrees | worktrees conflicts | — |
| T-DRIFT | Edit a spec document on disk behind the Hub's back | spec divergence | — |
| T-BUDGET | Set a token budget, exhaust it | usage_accounting, turn_scheduler | — |

## Rules for myself

1. **Evidence or it did not happen.** Every finding carries the request, the response, and the
   row/log that proves it.
2. **Do not fix while testing.** Findings go in the report; fixing mid-drive contaminates later
   scenarios and is a separate decision for the operator.
3. **Distinguish defect from design.** "It refused me" is usually the product working. The
   question is always whether the refusal is *legible* and whether the state it leaves behind is
   recoverable.
4. **Record friction, not just failure.** Something that works but takes six calls to discover is
   a finding about the product's usability, which is what the verdict at the end has to be based on.
