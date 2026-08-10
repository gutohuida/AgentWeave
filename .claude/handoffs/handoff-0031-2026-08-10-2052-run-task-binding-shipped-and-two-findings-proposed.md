# Handoff: the run→task binding shipped, and two findings proposed as its successor

**Date:** 2026-08-10T20:52+01:00 · **Branch:** hub-native-experience · **HEAD:** `cebd7e7`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0030-2026-08-10-1850-b1-shipped-and-archived.md`
**Status:** **chunk complete.** The change is implemented, verified and committed; 3 human-only
checks remain and are now blocked on its successor. Working tree clean. **7 commits unpushed.**

## Goal

Handoff 0030 left B1 closed with no successor named. The operator picked **the run→task binding**
from the three candidates — the missing edge identified in
`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md` as tiers 1 and 2 of
enforcement.

The point: B1 made it impossible to record a *wrong* transition and can do nothing about a *missing*
one. An agent that does the work and never touches the ledger passes every check B1 introduced,
because it never asks for anything. B1 gives **validity**; this gives **liveness**. It is also B3's
prerequisite — evidence is produced *by a run*, about *a task*, and that edge did not exist.

## Current state

**Shipped and live on `:8010`** (Hub restarted this session, PID 9360, migrations `0053 → 0058`
applied to the real database).

A run now carries the one task it was started for. A delegation naming a task carries it through the
queue onto the receiving run; the operator can start a bound run from a board card. Binding moves
the task to `in_progress` by itself — the agent is never asked. At the run boundary, AgentWeave asks
whether that run actually moved its task; if not it records a divergence and applies the task's
policy: `surface` (default), `retry` once, or `escalate` to a named stronger agent, reassigning the
task.

**53 of 58 tasks done.** The 5 open: 6.6 (deliberately not done, reasoned in `tasks.md`) and 8.13–8.16,
of which 8.13 and 8.14 were answered this session, leaving **8.15 and 8.16 blocked on the successor
change** and 6.6 a standing offer.

### What is NOT done, and matters

- **Only the first run of a conversation is bound.** The composer's trigger sends no `task_id`
  (`AgentOutputPanel.tsx` `postTrigger`), and nothing propagates a binding across turns — not
  `turn_scheduler.py`, not `conversations.py`. So the check fires at the end of turn one, when an
  agent is most legitimately unfinished, and is silent for every later turn including the one where
  it actually stops. **This is the single most important thing to fix next.**
- **An agent that stops to ask a question is treated as having dropped the work.** The run ends, the
  task has not moved, a divergence is recorded, and under `retry` the agent is restarted while still
  blocked on the same unanswered question. Proposed fix is the `blocked` status; the narrower
  exemption was offered to the operator and **not taken**.

## Files touched

Working tree is **clean**. Everything below is committed across seven commits (`1cc0a36`, `a260386`,
`615aba1`, `0b71b47`, `3cb079f`, `98f8433`, `cebd7e7`) and **none are pushed**.

| path | what | done? |
|---|---|---|
| `hub/hub/run_task_binding.py` | **new.** Policy/outcome constants, `TaskBindingError`, `resolve_task_for_project`, `binding_from_entries`, `binding_for_delivery`, `bind_run_to_task`, `run_advanced_its_task`, `may_retry`. Inert — no spawning | yes |
| `hub/hub/run_divergence.py` | **new.** `resolve_divergences_for_task`, `_may_escalate`, `_decide`, `_response_prompt`, `_queue_response`, `_apply_policy`, `record_response_run`, `evaluate_run_end` | yes |
| `hub/hub/db/models.py` | `Run.task_id`, `Run.divergence_source_run_id`; `InboundQueueEntry.task_id`, `.divergence_source_run_id`; `Task.divergence_policy`, `.escalation_agent`; `TaskTransition.origin`; new `RunDivergence`; `divergence` added to both queue-origin CHECKs | yes |
| `hub/hub/migrations/versions/0054_add_run_task_binding.py` | **new.** Both `runs` columns + index, guarded | yes |
| `hub/hub/migrations/versions/0055_add_queue_entry_task.py` | **new.** `inbound_queue_entries.task_id`, guarded | yes |
| `hub/hub/migrations/versions/0056_add_divergence_policy_and_origin.py` | **new.** `tasks.divergence_policy`/`escalation_agent`, `task_transitions.origin`, server defaults, guarded | yes |
| `hub/hub/migrations/versions/0057_add_run_divergences.py` | **new.** `run_divergences` table, guarded on `tasks`+`projects` | yes |
| `hub/hub/migrations/versions/0058_add_divergence_queue_origin.py` | **new.** `divergence` queue origin + `divergence_source_run_id` on the entry, via `batch_alter_table(recreate="always")` like `0019`/`0035` | yes |
| `hub/hub/task_transition_service.py` | `ORIGIN_ACTOR`/`ORIGIN_RUNTIME`/`ORIGINS`; `apply_transition(..., origin=)`; resolves open divergences on an actor transition | yes |
| `hub/hub/inbound_queue.py` | `new_entry` takes `task_id` and `divergence_source_run_id`; `divergence` accepted as an origin | yes |
| `hub/hub/run_reconciliation.py` | evaluates divergence for bound runs after the commit, skipping ones whose input was returned | yes |
| `hub/hub/api/v1/agent_trigger.py` | `task_id` on `TriggerAgentRequest`; validated in the route; carried onto the operator's queue entry; binding resolved at the `Run(` site; `evaluate_run_end` on **both** runner end paths (lines ~1277 and ~1663); `record_response_run` | yes |
| `hub/hub/api/v1/messages.py` | validates a delegated `task_id`; carries it onto the queue entry | yes |
| `hub/hub/api/v1/tasks.py` | `_tasks_with_open_divergence`; `has_open_divergence` on list/get/patch; operator-only guard on policy fields; `GET /tasks/divergences/recent` | yes |
| `hub/hub/schemas/tasks.py` | `_DIVERGENCE_POLICIES`; `TaskUpdate.divergence_policy`/`escalation_agent` + validators; three new `TaskResponse` fields | yes |
| `hub/hub/main.py` | app-level `TaskBindingError` handler → 404 | yes |
| `hub/tests/test_run_task_binding.py` | **new.** 17 tests | yes |
| `hub/tests/test_run_divergence.py` | **new.** 18 tests | yes |
| `hub/tests/test_task_transition_service.py` | 5 origin tests appended | yes |
| `hub/tests/test_task_transitions.py` | actor-kinds test + the `origin='runtime'` source scan | yes |
| `hub/tests/test_agent_actions_coordination.py` | 6 tests: delegation carries the task, foreign task 404, `request_agent` grants no binding, 3 policy-guard tests | yes |
| `hub/tests/test_migrations.py` | head → `0058`; `origin` in the `0052` column set; 5 new per-migration tests | yes |
| `hub/tests/test_project_persistence.py` | head assertion → `0058` | yes |
| `hub/ui/src/api/tasks.ts` | `Task` fields, `DivergencePolicy`, `DIVERGENCE_POLICY_LABELS`, `useSetDivergenceHandling`, `useDivergences`, `useStartWorkOnTask` | yes |
| `hub/ui/src/components/tasks/TaskCard.tsx` | start-work menu, "Stalled" badge, policy buttons, escalation-agent select | yes |
| `hub/ui/src/components/layout/RowMenu.tsx` | `icon` prop, defaulting to `more_horiz` | yes |
| `hub/ui/src/lib/eventSummary.ts` | `run_diverged` rendered in words | yes |
| `hub/ui/src/__tests__/taskDivergenceControls.test.tsx` | **new.** 10 tests | yes |
| `hub/ui/src/__tests__/taskStatusControl.test.tsx`, `agentColorSurfaces.test.tsx` | fixtures gain the two required `Task` fields | yes |
| `hub/hub/static/ui/**` | rebuilt artefact, `diff -rq` identical | yes |
| `openspec/specs/run-task-binding/spec.md` | **new capability**, 10 requirements | yes |
| `openspec/specs/task-lifecycle-governance/spec.md` | transition cause recorded; system-as-cause; per-task policy | yes |
| `openspec/specs/agent-capability-plane/spec.md` | the hook rule; delegation-is-runtime-state | yes |
| `openspec/changes/2026-08-10-run-task-binding/` | proposal, design D1–D14, 3 delta specs, tasks 53/58 | yes |
| `openspec/changes/2026-08-10-blocked-and-conversation-binding/` | **new, NOT IMPLEMENTED.** proposal, design D1–D8, 3 delta specs, tasks 0/… | proposal only |

## Key decisions

Full rationale in `openspec/changes/2026-08-10-run-task-binding/design.md` (D1–D14). The ones that
will otherwise be re-litigated:

1. **D1 — one primary task per run**, a nullable column, not a join table. Rejected many-to-many:
   it makes "did the run's task move?" ambiguous, and an ambiguous check cannot drive a policy that
   spends tokens.
2. **D2 — the runtime binds; no agent-facing binding operation exists.** An agent able to bind
   itself is an agent able to never bind, and an unbound run is never divergent. Rejected an
   `adopt_task` tool for that reason.
3. **D4 — the auto-transition goes *through* `apply_transition`**, never around it. That function is
   the documented seam B3's evidence checks and B4's completion gates plug into; setting
   `task.status` directly would bypass every gate not yet written.
4. **D5 — transitions record an `origin` of `actor`/`runtime`, not a third actor kind.** Without it
   the change eats itself: the runtime's own auto-`in_progress` is a transition by that run on that
   task, so the divergence check would answer "yes it advanced" for every bound run. Rejected a
   `runtime` actor kind — it would force every edge to declare whether the runtime may take it.
5. **D8 — retry is bounded by construction, not a counter.** A response run carries
   `divergence_source_run_id` and never retries again. **Extended during implementation:** it may
   also only escalate if it was itself a *retry*, else `escalate → escalate` loops forever to the
   same agent. Read from the causing divergence's recorded outcome.
6. **D9 — escalation reassigns the task**, recording the previous assignee. Leaving the assignee on
   the agent that just dropped the work would make the board disagree with reality.
7. **D7 — `surface` is the default**, which is load-bearing: it is what every pre-existing task
   acquires, so shipping cannot start runs nobody asked for.
8. **No CHECK constraints on `origin` or `divergence_policy`** (tasks.md 1.6). A table-level CHECK
   naming a column makes that column undroppable in SQLite, which made `0056` irreversible. Also
   consistent — `actor_kind`, `tasks.status`, `tasks.priority` carry none. CHECKs on the *new*
   `run_divergences` table are kept, since a new table is dropped whole.
9. **A run whose delivered input was returned to the queue is not divergent.** That input is about
   to be handed to a new run bound to the same task, so nothing was dropped; under `retry` a
   divergence there would race the redelivery.
10. **`divergence` is its own queue origin** (`0058`). Borrowing `operator` would put the operator's
    name on work they did not ask for, in the queue they read — the argument `checkpoint` already
    makes in `models.py`.
11. **Successor design D3 — a block is observed, never asserted.** An agent that could declare
    itself blocked could claim to be waiting on a person it never asked, which is the one claim a
    completion gate would most reward. **Rejected the narrower fix** (exempting a run with an open
    question from the divergence check): an exemption suppresses the question the operator would
    have to answer anyway, where a status answers it on the board.
12. **Successor design D2 — `blocked → completed` is deliberately not an edge.** Work goes back
    through `in_progress` first, so no history says a task completed while still waiting on someone
    who never answered.

## Constraints and user directives (verbatim)

**From this session:**
- *"Do not call the AgentTool unless the user requested it"* / *"Do not use workflows or
  deep-research unless the user requested it"* — from the session environment. Honoured throughout.
- On 8.13: *"I think this changes with the phase of the project. So if a user is exploring things or
  want to go over the details starting via composer is the obvious choice but if it's a project that
  it's underway starting the task makes more sense because everything is in order already. Both are
  valid ad different cycles."*
- On 8.14: *"I don't know, what is a dropped task?"*
- On 8.15: *"Don't know, will only know after trying a couple of times. A question has surfaced now.
  What if an agent has a question about the implementation that was not foreseen... the task will
  remain unchanged after the turn is done. Maybe we need a blocked state waiting for something from
  the user."*
- On 8.16: *"Elaborate better."*
- *"Another question, does all of this also apply to codex? Since I believe codex doesn't use the
  headless run can we detect that he finished without completing the task?"*
- Divergence policy, chosen 2026-08-10: *"Can this be configured? The user decides on task level if
  it marks diverged and surface it, makes the agent goest at it again or if it scales do another
  agent to take a look (could be a task assigned to a weaker model and then it goes to a stronger
  model to solve the divergence)"*
- Chose: one primary task per run; runtime binds with auto-`in_progress`; escalation agent is a
  field on the task; retry once then fall through; default `surface`.
- Chose "Relabel → Stalled + tooltip" **only** (not the standalone question-exemption fix), and
  "Propose both, decide later" for the two lifecycle ideas.

**Carried and still binding:**
- **Handoff cadence:** only when asked, or when an openspec change is done. This one was asked for.
- **STANDING DIRECTIVE:** every change's `tasks.md` splits agent-verifiable from human-only and
  emits a user test guide. Both changes this session do.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — derive
  constants, do not tune them.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters); *"the charter
  exists to give instructions so I can use agentweave for more then developing."*
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; migrations guard for a missing table and bump **both** head
  assertions; `hub/hub/static/ui` refreshed and confirmed with `diff -rq`; never mark a task
  complete on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **A table-level CHECK constraint makes its column undroppable in SQLite.** The planned CHECKs on
  `task_transitions.origin` and `tasks.divergence_policy` made migration `0056` irreversible —
  caught by the *existing* `test_migration_0052_downgrade_drops_the_history`, not by inspection.
- **The naive divergence check fires on spawn failures and crashes that returned their input.**
  `return_run_entries` puts the input back on the queue; a divergence there misdescribes it and
  under `retry` races the redelivery. Hence the `input_returned` condition.
- **`escalate` loops without an escalation bound.** An escalated run that diverges finds the same
  policy and the same escalation agent still on the task. `may_retry` alone does not stop it,
  because escalation never consults it.
- **`RunDivergence.response_run_id` cannot be filled when the divergence is recorded** — the answer
  is *queued* and becomes a run in a later call. Hence `record_response_run`, called from the
  trigger path.
- **Git Bash `/tmp` is not what native Windows Python sees.** `cp x /tmp/y` then opening
  `/tmp/y` from `python.exe` silently creates an empty file. Use a repo-relative path.
- **`sed -i 's/0053/0058/g'` on the migration tests is safe *this time* but is a trap** — the file
  contains test names like `test_migration_0052_…`. Replace `== "00NN"` specifically.
- **`black` warns "Python 3.11 cannot parse code formatted for Python 3.12"** on this repo. It is a
  safety-check warning, not a failure; `--check` still reports files unchanged and ruff passes.
- **`pytest`/`npx` must run from the right cwd.** The Bash tool's cwd persists across calls — a
  `cd hub/ui` earlier in the session makes a later `cd hub/ui` fail and `hub/tests/` not found.

**Carried and still true:**
- **`hub/data/agentweave.db` is the live database**, not `~/.agentweave/hub/data/…`. Check
  `projects` before believing a database is the one in use.
- **Restarting the Hub: kill by exact PID and verify the new process bound.** Done correctly this
  session (25412 → 9360). A stale process holding the port produces a false pass.
- **Static UI updates without a restart; Python does not.**
- **`position: sticky` dies under an ancestor with `overflow-hidden`.**
- **`openspec` CLI rejects change names starting with a digit.** Create with a letter-initial name,
  then `mv` to the date convention. `openspec validate --changes --strict` works regardless.
- **There is no `openspec sync` command** — the skill applies deltas by hand.
- **`openspec … --json` prints a warning line before the JSON.** Strip with `sed -n '/^{/,$p'`.
- **PowerShell here-strings mangle a commit message in the Bash tool.** Use `git commit -F -` with a
  heredoc, or the Write tool + `git commit -F <file>`.
- **`cp -r dist/* static/ui/` merges rather than replaces** — `rm -rf` the destination first.
- **`npm run lint` does not work**; `npx tsc --noEmit` is the check.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. **The default `python`
  has no pytest** — use `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **`preview_snapshot` is unreliable**; **`preview_press` and `preview_resize` do not work.**

## Verification

**Ran, with real output:**
- `pytest hub/tests/ -q` — **1437 passed, 10 skipped** (1384 at this change's start).
- `pytest tests/ -q` — **372 passed, 3 skipped.**
- `cd hub/ui && npx vitest run` — **726 passed across 77 files.**
- `npx tsc --noEmit` — clean. `ruff check hub/` — clean. `black --check hub/` — 259 files unchanged.
- `npx openspec validate --specs --strict` — **29 passed**; `--changes --strict` — **7 passed**.
- `npm run build` + `rm -rf` + copy + `diff -rq` — identical.
- **Live:** Hub restarted by exact PID (25412 stopped, port confirmed free, new process **9360**
  confirmed bound). Migrations `0053 → 0058` applied to the real database; three stale `running`
  runs reconciled to `interrupted`. Serving process proved new **behaviourally** —
  `/openapi.json` publishes `/tasks/divergences/recent`, `divergence_policy` /`escalation_agent`/
  `has_open_divergence` on `TaskResponse`, and `task_id` on `TriggerAgentRequest`.
- **Live end-to-end against a *copy* of the operator's real database** (`proj-cddb0827`, real roster
  `claude-1`/`claude-test-1`/`codex-1`): bind set `run.task_id`; task `pending → in_progress` with
  `origin=runtime`; `run_advanced_its_task` correctly `False` despite that transition existing;
  divergence `policy=escalate outcome=escalated`; task reassigned `claude-1 → codex-1` with
  `previous_assignee` recorded; response queued for `codex-1` carrying task and source run. The copy
  was deleted; **the operator's live board was not written to.**

**Not verified, and deliberately:**
- **No agent process was ever spawned.** The whole end-to-end with a real Claude or Codex run is
  step 6 of the user test guide (`tasks.md` 8c) and has not been done.
- **The Codex path is wired but never live-exercised.** `evaluate_run_end` is on both runner end
  paths (`agent_trigger.py` ~1277 in `_execute_run`, ~1663 in `_execute_codex_appserver_run`), and
  the logic is runner-agnostic by construction because it sits at the Hub-owned run boundary. That
  is verified by reading both call sites and by unit tests over the shared logic — **not** by a live
  Codex run.
- **Nobody has looked at the new task card visually.** The controls are tested, not seen.
- **CI has still never run on this branch** — now **368 commits ahead of master**. `ci.yml` triggers
  only on push/PR to `master`. A **draft PR to master** would trigger the 3-OS × 5-Python matrix
  with no workflow edit. **Raised nine times.**
- **The permission defect is untouched** — `openspec/explorations/2026-08-10-operator-approval-not-honoured.md`.
- The four human-only items still blocking `hub-charcoal-visual-refresh` (8.8, 8.10, 8.11) and
  `hub-contextual-navigation` (7.7).

## Git state

Branch `hub-native-experience`, HEAD **`cebd7e7`**, working tree **clean**, **7 unpushed commits**
(`1cc0a36`, `a260386`, `615aba1`, `0b71b47`, `3cb079f`, `98f8433`, `cebd7e7`), **368 commits ahead
of master**.

## Next steps

1. **Ask the operator whether to implement `2026-08-10-blocked-and-conversation-binding`**, and if
   so settle its design Open Questions 1–5 first — in particular the edge set (D2) and D5's choice
   about how a blocked task escapes the divergence check. Do **not** start implementing without
   that: `hub/hub/task_transitions.py`'s `TRANSITIONS` is what B3 and B4 will be written against, so
   a status added now is cheap and added later is not. If they say go, task 1.1 is: add the ninth
   status and its four edges to `hub/hub/task_transitions.py` per design D2.
2. **Push the branch** (7 commits) if the operator wants it pushed — not done, not asked for.
3. **The permission defect** — still the highest-value untouched item. Reproduce in `testbed/` with
   the composer's Permissions pill on "Ask me"; four leads are listed in the exploration.
4. **Offer 6.6 again** — showing a run's bound task where runs are displayed. Not done because the
   UI has no surface that displays a run as an entity; the operator has not said whether they want
   one built.
5. **Remaining roadmap changes:** A2 (shell conformance audit), B0 (blocked on the charter-count
   decision), then B2–B7.

## Open questions for the user

1. **Implement the successor change, or return to the roadmap?** Blocking next-step 1.
2. **Its design Open Questions 1–5** — does a non-blocking question block the task (proposed: no);
   what happens when a blocking question times out; is `blocked` a ninth column or a treatment on
   `in_progress`; does the binding belong to the conversation or the agent; should an operator-set
   block name what it is waiting for.
3. **The `ci.yml` branch trigger** — **raised nine times**. A draft PR is the zero-edit alternative.
4. **Push the branch?**
5. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks archiving
   `hub-charcoal-visual-refresh` (8.11).
6. **How many charters, and which non-software domains?** Still blocks B0.
7. Carried: should `.claude/handoffs/` stay tracked (**117 files, confirmed not gitignored**); the two
   model-less runners on `proj-cddb0827` (`claude-1`, `codex-1`) — these will block the user test
   guide's later steps; `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.

## Read on resume

- **This file's "Dead ends" first** — the SQLite CHECK/drop-column trap and the returned-input
  condition both cost real time, and the Hub-restart trap is still live.
- `openspec/changes/2026-08-10-blocked-and-conversation-binding/design.md` — D1–D8 and the five
  open questions that gate next-step 1.
- `openspec/changes/2026-08-10-run-task-binding/design.md` — D1–D14, the reasoning behind everything
  shipped, including the two corrections found during implementation.
- `hub/hub/run_task_binding.py` and `hub/hub/run_divergence.py` — the two halves: what binds and
  what a dropped task costs.
- `hub/hub/task_transitions.py` — the map the successor change modifies, and why that is expensive
  after B3/B4 exist.
- `openspec/changes/2026-08-10-run-task-binding/tasks.md` — sections 8b/8c: the three open
  human-only checks and the user test guide, which is where the never-run live agent test lives.
