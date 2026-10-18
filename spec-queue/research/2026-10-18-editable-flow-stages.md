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

## Part 2 - the spike (driven, not read)

Tracer: branch `spike/2026-10-18-flow-stages` at `6a13a15` (pushed, never to be merged). About 80
lines across `spec_payload.py`, `db/models.py`, `review_turn.py`, `task_transition_service.py` and
`scheduler.py`, plus `hub/hub/flow_stages.py` and migration `0135`. The drive scripts and the
transition log are in `testbed/spike-flow-stages/` on that branch. Hub test suite **not run** on the
spike. It is a tracer, and which existing tests it breaks was not measured.

### What the tracer does

- `delivery.stages` on a change document: a list of `{key, agent, duty}`. Absent means today's
  flow, untouched. `[]` means dev only.
- `Task.stage_index` (new column) is the task's position in that list.
- The current stage's `agent` is the declared reviewer (`_declared_reviewer_name`), and its `duty`
  replaces the tester text in the review briefing ("This review is stage 1 of 2: `security`").
- An agent's `approved` on a non-final stage does not approve. It advances the stage, writes
  `under_review -> completed`, and skips the gate, the evidence decision and integration. The next
  firing staffs the next stage like any finished task.
- `revision_needed` from any stage goes back to the build author and restarts at stage 0.
- `stages: []`: the next firing lands a `completed` task with the Land button's composition.

### The drive

Scratch Hub `:8110`, run from the worktree (with `AW_REPO_ROOT` set, which avoids F749). Four agents
on `claude-haiku-4-5-20251001`: `dev` (Developer), `sec` (Security Engineer), `qa`, `rev` (Code
Reviewer). One project, three change documents with one small task each, all approved at 23:13:40.

| Variant | Stages declared | What happened | Reached master |
|---|---|---|---|
| a, `dev -> test` | none (`tester: qa`) | dev built (23:14:57), qa test-reviewed and approved (23:18:33). Unchanged behaviour. | yes, `a8d2c7f` |
| b, `dev` only | `[]` | dev built (23:17:00), and the next firing landed it (23:18:03). No reviewer turn. | yes, `0997ace` |
| c, `dev -> security -> test` | security: `sec`, test: `qa` | built by **qa** (23:15:27). sec sent it back with `revision_needed` (23:18:03). qa reworked it (23:20:04). sec approved, which advanced the task to stage 2 (23:21:04, `stage_index` 1, status `completed`). Stage 2 stalled: qa is the author. An operator hand-dispatched `rev`, which approved it, and the task landed. | yes, `6271eaa` (merges the reworked `6c1d159`, not the first `64ab55a`) |

The scratch Hub logged no tracebacks.

**The security stage earned its place on the first try.** sec found a real defect that the tests
passed over. `safe_join` used `os.path.abspath`, so a symlink inside `base` escaped it. sec named
the fix (`realpath`), qa applied it, and sec approved the second build. Measured once, with Haiku:
an anecdote, not a rate.

### Where the existing code resisted (each one is a design question the spec has to answer)

1. **The status machine has no edge for "this stage passed, next stage".** The tracer rewrote an
   agent's `approved` into `under_review -> completed` inside `apply_transition`, past
   `TRANSITIONS`. The agent asked for `approved` and got back `completed`. Haiku accepted it ("approved,
   with the task status showing as completed"), but the contract is now dishonest. The map's lean
   held: no new statuses were needed, only a position field and a stage-advance edge. The edge
   needs a name, a place in `TRANSITIONS`, and a tool result that says "passed stage 1 of 2".
2. **Authorship is read from "the latest move into `completed`"** (`completion_attribution`,
   `task_transition_service.py:190-207`). Without a filter, the security agent's stage advance would
   make *it* the author. The test stage would then exclude the wrong agent, and a test-stage
   `revision_needed` would go to sec instead of the builder. The tracer filters out
   `from_status = 'under_review'`. Its wrapper `agent_that_completed` has seven callers (its docstring, `:216`), so
   a real build must treat this as a contract change, not a one-line filter.
3. **Build staffing does not know the stages.** dev was busy, so the flow gave c's build to the
   first free pool agent: qa, the test-stage agent. Once qa was the author it could not test, and
   stage 2 hit rung 1b (`review_unstaffed`): *"this task names 'qa' as its reviewer, and that agent
   is the one that completed this task"*. The sentence says "reviewer", not "test stage". The
   options:
   - keep a stage's named agents out of the build pool;
   - pin the build to `delivery.agent`;
   - let a stage name a charter or a pool rather than one agent (the `security_engineer` charter
     exists, and nothing staffs by it, part 1).
4. **The operator's remedies are awkward.**
   - Re-pointing the stage at another agent was refused: an approved document is immutable (`422
     document_approved`), so changing it means reopening it.
   - A hand-dispatched review (`review_task_id`) worked, but its briefing carried **no stage
     line**. `rev` called itself the reviewer "ready for the next stage" when it was the last
     stage. Its approval still landed correctly, because `stage_index` was already the last. Which
     briefing path the hand dispatch takes was not traced: **unverified**.
5. **There is no Hub actor.** The dev-only land is recorded as `actor_kind = operator` on both
   edges, so the history says the operator approved work they never saw. It also runs inside
   `decide_firing`, a decision function that now writes. A real build needs an actor kind for
   "the flow, under its declared stages", and the land belongs in the dispatch.
   - The gate still ran on the dev-only land. At `sketch` rigor it was silent. The repository
     categories (merge, checks) still apply, which is presumably what the operator wants from
     "quick and dirty": no agent review, but no broken merge either.
6. **An operator approval skips the remaining stages.** The tracer advances only on an agent's
   verdict, so Land at stage 1 merges at once. Whether the operator may jump stages is question 4.
7. **Not exercised:**
   - a test-stage `revision_needed` after security passed. Under the tracer that re-runs security
     after the rework (reset to stage 0). Whether it should is question 4;
   - evidence at `contract` or `gate` rigor across stages (the tracer decides evidence only at the
     final approval);
   - a `command` stage (`project_checks`);
   - deploy.

### What this hands to `flow-stages-spec`

- **A stage = a named, review-shaped agent turn with its own duty** worked end to end with very
  little code. The duty text alone was enough to turn a generic reviewer into a security reviewer
  with a different verdict. Commands and deploy are separate kinds and can follow.
- **`delivery.stages` on the document** was enough for per-flow configuration. Agents never had to
  read it, because the Hub briefed them.
- **The hard parts are the contracts, not the plumbing.** They are the stage-advance edge (1),
  authorship (2), stage-aware build staffing (3), and an honest actor for an automatic land (5).
  Each is Tier 2 material: the task-lifecycle contract, a migration, and the
  `completion_attribution` callers.
- **Removing `test` is cheap to build and expensive to explain.** It works in one firing, but the
  history and the board have to say "landed without review" truthfully (question 3), and today
  they cannot.

## Part 3 - the change document

Authored on the trial Hub `:8010` (`proj-d85a82bf4216`) as `spec/changes/editable-flow-stages/spec.json`
(`spdoc-9e407ca6ffe8`), phase **`exploring`**: not proposed, not approved. It holds the problem in
the operator's words, options and a recommendation for each of the brief's seven questions plus an
eighth (stage staffing, from resistance point 3), a sketch of the acceptance drive, and the Tier 2
hazards. Four requirements are drafted, and only ones that hold under every option. The eight
questions are `OPEN` rows `flow-1018-1` to `flow-1018-8` in `spec-queue/DECISIONS.md`.
