# Editable flow stages: how a flow runs today, and where a stage list would hook in

Night window 2026-10-18, queue items `flow-stages-map` (part 1), `flow-stages-spike` (part 2) and
`flow-stages-spec` (the change document). Brief: `spec-queue/APPROVALS.md` `## 2026-10-18`.

Operator (verbatim): "The way the flow executes is good and it isnt at the same time. It's good
because we have testing automatic but sometimes I want something built quick and dirty and sometime
I want to add for example a security step. Other steps. So I would like to make so the flow like
dev -> test -> deploy is edditable. The default is dev ->test but if I want to remove or add steps
to be possible"

## Part 1 - the map (read, not run)

Method: I read the code at the lines cited. Nothing was executed for part 1, and part 2 drives it.
Citations are against `8e07aa1`.

### In one paragraph

A flow has **two task-level stages**, and only one of them is a slot for an agent. The first is
**build**: one agent takes the task to `completed`. The second is **one review slot**: one non-author
agent takes the task `completed -> under_review -> approved | revision_needed`. That slot is filled
by a tester *or* a reviewer, never both in sequence. "Test" is not a stage of its own. It is spread
over three mechanisms: the reviewer's tester duty (an agent drives the product), the project's
`checks` (commands the Hub runs on the would-be merge commit), and the requirement/evidence gate at
`approved`. **Land** is not a stage either. It is a side effect of entering `approved`: the Hub
merges into `main_branch`. **Deploy** does not exist. So `dev -> security -> test` has no slot to go
in today. `dev` only half-exists: a documentless loop already skips review, but the operator must
still land each task by hand.

### What a flow is

- A flow is a `Loop` row that declares a spec document. There is no `Flow` table
  (`openspec/changes/archive/2026-08-26-loop-becomes-a-flow/design.md` D1;
  `hub/hub/db/models.py:1623` `Loop`, `:1668` `spec_document_id`).
- `create_flow` and `create_loop` share one payload (`hub/hub/mcp_server.py:913`).
- How the flow works its tasks is declared on the document, in `Delivery`
  (`hub/hub/spec_payload.py:196-234`). Its fields are `mode`, `agent`, `reviewer`, `tester`,
  `stop_when_queue_empties`, `stop_at` and `cron`. Approving the document creates the flow from it.
  **This is already per-flow configuration of the stages**, limited to who fills the review slot.

### Stage 1 - build (dev)

- **Nothing starts on assignment.** `update_task_for_actor` writes `assignee` and `status` only
  (`hub/hub/api/v1/tasks.py:1553`). Runs come from a loop firing, where `_do_fire_job` calls
  `decide_firing` (`hub/hub/scheduler.py:3851`, `:1720`). They also come from a trigger
  (`hub/hub/api/v1/agent_trigger.py:1021` `trigger_agent_directly`).
- **Who builds** (`decide_firing`'s work arm, `scheduler.py:2000-2085`):
  1. the task's assignee;
  2. otherwise the job's default agent;
  3. otherwise the first free agent in the flow's pool.

  A documentless loop's pool is empty, so only its own agent works (`scheduler.py:1366`
  `_agents_a_loop_may_staff`). Each agent takes one task per firing (design D6).
- **Entry:** `enter_selected_task` moves `pending -> assigned` (`scheduler.py:907-980`). The run
  binding moves it to `in_progress` (`hub/hub/run_task_binding.py:639`).
- **The prerequisite gate** fires on `-> in_progress`. Every prerequisite must be `approved`
  (`hub/hub/dependency_gate.py:39`, `:102`; called from `hub/hub/task_transition_service.py:776`).
- **Exit:** the builder calls MCP `update_task(status="completed")` (`mcp_server.py:423`), as its
  briefing instructs (`scheduler.py:3023` `_briefing_completion_lines`). Completing a task outside
  a turn schedules the project checks (`task_transition_service.py:883`). A turn ending on a
  completed task does the same (`agent_trigger.py:3610`, `:4635`).

### Stage 2 - review (the only other agent slot)

- **Trigger:** `decide_firing` finds a `completed` task, then calls `resolve_reviewer`
  (`scheduler.py:1526`, called at `:2228`). It appends a selection with `is_review=True` (`:2236`).
  `enter_selected_task` writes the reviewer into `task.assignee` and moves
  `completed -> under_review` (`scheduler.py:962-977`).
- **A documentless loop skips review entirely.** It parks the task in `awaiting_landing`
  (`scheduler.py:2137-2139`) and stalls with a sentence saying the operator must land it
  (`:2306-2317`).
- **Staffing ladder** (`resolve_reviewer`; declaration read in `hub/hub/review_turn.py:158-205`):
  1. the declared name, first found in this order: the task entry's `reviewer` (`:194-196`), then
     `delivery.tester` (`:199-202`), then `delivery.reviewer` (`:203-204`);
  2. a declared name that does not resolve is surfaced and never replaced (`review_turn.py:102-155`);
  3. with nothing declared, any free non-author agent with a runner (`scheduler.py:1623-1641`);
  4. otherwise "unstaffed" (`:1657`).

  The author is excluded: the agent that completed the task, and every author of its evidence
  (`scheduler.py:2201-2226`; guard `task_transition_service.py:393-446`).
- **Tester vs reviewer is a precedence, not a sequence.** `tester` wins over `reviewer`, and
  `tester: false` means "review only" (`spec_payload.py:218-221`). The tester's duty is briefing
  text added to the same review turn (`review_turn.py:208-242` `test_duty_lines`).
- **No charter-based selection.** `Agent.charter_id` exists, and a `security_engineer` charter ships
  (`hub/hub/data/charters/security_engineer.md`). Nothing in `resolve_reviewer` or `review_turn.py`
  reads a charter.
- **Verdict:** the same `update_task` tool, with `approved`, `revision_needed` or `rejected`
  (`mcp_server.py:434-441`). `revision_needed` hands the task back to its author
  (`task_transition_service.py:838-841`, `:911-943`). The next firing resumes it through
  `revision_needed -> in_progress`.

### Stage 3 - "test" (three mechanisms, none a stage)

1. **The tester duty**, described in stage 2: an agent drives the product inside the review turn.
2. **Project checks** (`hub/hub/project_checks.py`):
   - They are operator-defined commands (`Project.checks`, `db/models.py:127`; read at
     `project_checks.py:63`).
   - They run on the would-be merge commit, in a scratch worktree, with credentials scrubbed
     (`:4-6`, `:53-57`). Main is checked too, to detect failures that predate the task
     (`:498`).
   - This is the **only place the Hub executes project commands**. It is a flat list with no stage
     name.
3. **The requirement/evidence gate**, at `-> approved` only (`task_transition_service.py:792-818`;
   reason given at `hub/hub/requirement_gate.py:7-11`):
   - `GateRefusal.refuses` is true when any of eight categories is non-empty
     (`requirement_gate.py:194-205`): `blocking`, `diagnostics`, `unmergeable`, `unaccepted`,
     `unlanded`, `unfinished`, `checks`, `unmerged_prerequisites`.
   - Requirement strictness follows the document's `rigor`, which defaults to `sketch`
     (`hub/hub/spec_rigor.py:39`). `sketch` is silent except for rejected evidence, `contract`
     reports, and `gate` refuses (`requirement_gate.py:1073-1147`).
   - The repository categories (merge, unaccepted, unlanded, checks) apply at every rigor
     (`:1048-1050`).
   - The only override is the operator's `override_checks_reason`, and it clears failed checks
     only (`task_transition_service.py:798-802`). No setting turns the gate off.

### Stage 4 - land (a side effect of `approved`)

- Entering `approved` calls `integrate_task` (`task_transition_service.py:877`). It merges
  `--no-ff` into `Project.main_branch` in the project's checkout (`hub/hub/task_integration.py:680-691`).
  A skip or failure never reverses the approval (`task_transition_service.py:1096-1106`). The task
  checkout is released afterwards (`:899`).
- The operator's **Land** button is `POST /tasks/{id}/land` (`api/v1/tasks.py:1909`). It requires
  `completed` (`:1956`) and composes `completed -> under_review -> approved` as the operator
  (`:1995`). `completed -> approved` is deliberately not an edge.
- **Deploy: not found.** The lifecycle ends at a local merge.

### What is hard-wired

| Thing | Where | Cost of making it configurable |
|---|---|---|
| Nine statuses and their edges | `hub/hub/task_transitions.py:101-153` | Pinned three ways (`mcp_server.py:73-82`, `hub/hub/schemas/tasks.py`, `src/agentweave/constants.py:294`). `STATUS_BANDS` refuses an unclassified status at import (`:187`, `:218-228`). Each new status is a contract change for every agent prompt and UI column. |
| One review slot after build | `scheduler.py:907-980` (hard-coded `"under_review"`); `review_turn.py:158-205` (one name returned) | There is one `Task.assignee`, one verdict, and one `revision_needed` path back to the author. |
| Tester and reviewer are alternatives | `review_turn.py:199-204` | They would have to become a sequence. |
| Gates are placed on two edges only | `task_transition_service.py:776`, `:792` | A stage gate needs a third placement or a generalisation. |
| Land happens inside `approved` | `task_transition_service.py:877` | "Skip test" cannot reach a merge without going through `under_review -> approved`. |
| Reviewer picked by name, never by charter | `scheduler.py:1526-1657` | A "security" stage needs charter-or-name resolution. |

### What already flexes, and is the seed of a stage list

- **A per-project, tracked, editable step list already shipped, for spec authoring.**
  `spec/journey.json` is parsed and validated by `hub/hub/spec_journey.py:70-250` and edited through
  `GET/PUT /spec/journey` (`hub/hub/api/v1/spec.py:2919`, `:2945`) and the project page
  (`hub/ui/src/components/environment/SpecStepsSection.tsx`). It works like this:
  - built-ins are named by key, in a fixed order;
  - custom steps carry Markdown instructions and can sit anywhere;
  - any step can take an appended instruction;
  - a broken file is reported and the built-ins are used meanwhile;
  - steps are keyed by size, and the `fix` size skips most steps (`spec_journey.py:53-58`).

  This is the closest structural precedent (change `a-project-orders-its-own-spec-steps`, archived).
- **`Delivery` is per-flow already** (`spec_payload.py:196`). A `stages` field next to `reviewer`
  and `tester` is the natural declaration point for a flow.
- **"Quick and dirty" exists in pieces:**
  - a documentless loop skips review (`scheduler.py:2137`);
  - `tester: false` drops testing;
  - `sketch` rigor makes the requirement gate silent;
  - the Land button merges without an agent reviewer.

  What is missing is an automatic land for a flow with no review stage. Today that task stalls on
  the operator.
- **"Security" exists in pieces:** the `security_engineer` charter, and naming a security agent as
  `reviewer`. That replaces the test pass, though. It cannot follow it.

### Where a configurable stage would hook in

1. **Declaration:** a `stages` list on `Delivery` (per flow; `spec_payload.py:196`), with the
   project default as a tracked file shaped like `spec/journey.json`.
2. **Task position:** a stage field on `Task` (a migration), with `status` kept as the coarse band.
   The alternative is a status per stage, which hits the three-way status pinning above. The status
   machine then stays as it is. `completed` means "the current stage's author finished".
   `under_review` means "a stage agent has it". `approved` of the *last* stage alone triggers
   integration.
3. **Staffing:** generalise `resolve_reviewer` (`scheduler.py:1526`) into "resolve the agent for
   this stage". A stage names an agent, a charter, or nothing (rung 2). Keep its rules that an
   unresolved name is never substituted and that the author is excluded.
4. **Advancing:** in `apply_transition` (`task_transition_service.py:686`), a verdict of `approved`
   on a non-final stage advances the stage and returns the task to `completed` for the next stage.
   It does not integrate. `revision_needed` goes back to the build author, as today
   (`:911-943`).
5. **Gates per stage:**
   - the requirement/evidence gate stays on the final approval;
   - a "command" stage reuses `project_checks` (`project_checks.py:63`), with checks optionally
     named per stage;
   - a `dev`-only flow needs a defined "land without review" edge or an automatic Hub-actor Land
     (`api/v1/tasks.py:1909` composes one).
6. **Briefing:** per-stage duty text in the shape of `test_duty_lines` (`review_turn.py:208`) and
   `_briefing_verdict_lines` (`scheduler.py:3129`), taken from the stage's Markdown, as
   `spec_journey.duty` does for spec steps (`spec_journey.py:529`).
7. **Deploy:** after `integrate_task` (`task_transition_service.py:1096`), as a post-merge command
   or agent. Nothing exists there.

### Prior art

- **Little prior art exists on configurable execution stages.** There is no prior proposal for a
  quick mode.
- `openspec/explorations/2026-08-20-who-guarantees-the-review-handoff.md:147` and
  `openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md:242` treat "no reviews" as a hazard
  to announce, not as a mode.
- `openspec/explorations/2026-08-10-enforcing-the-development-cycle.md:83` argues against
  skippable bookkeeping. Read it before deciding question 3.
- `openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md` (around `:381`, `:541`)
  is the cost argument for a lighter path.
- `openspec/explorations/2026-08-21-a-review-is-a-task-not-a-message.md:67` names routing "a
  security review" to a security-charter agent as a motivation for charter-aware staffing. It was
  never built.

### Questions this hands to `flow-stages-spec`

These are the brief's seven, sharpened by the map:

1. Is a stage an agent+charter, a command (`project_checks`), a gate, or a mix?
2. Is the stage list per flow (`Delivery`), a project default file, a per-task override, or some
   combination?
3. Does `dev` only auto-land with a Hub-actor approval? What does it skip of the evidence gate?
   The repository categories (conflict, unlanded) presumably still apply. How is "landed without
   review" shown?
4. Are stages strictly sequential? Can a stage be optional? Does a stage's `revision_needed` always
   return to the build author?
5. Is deploy a post-merge command, an agent, or out of scope for v1?
6. A stage field on `Task` with statuses unchanged (recommended by the map), or new statuses?
7. Where is the editor: the project page beside Spec steps, the document's Delivery section, or
   both?
