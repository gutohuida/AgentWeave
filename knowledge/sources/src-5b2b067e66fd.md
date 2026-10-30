## F238 (C) — half of all budget changes are missing from the project's own activity history

**Status:** fixed (this commit) [Round 4, 2026-09-23] — `PUT /settings` records what it changed; see FIXED at the end of this entry. Was: open. Verified 2026-09-09: `PUT /settings` still only broadcasts
(`hub/hub/api/v1/projects.py:528-530`) with no `persist_event` beside it, so every setting that route
writes still leaves no record while the accounting route's writes do. [classified 2026-09-09, D-3]

Same two routes, a different consequence. `accounting.py:57` records the change:

```python
await persist_event(session, project_id, "accounting_budget_updated", event_payload)
await sse_manager.broadcast(project_id, "accounting_budget_updated", event_payload)
```

`projects.py:526-529` broadcasts without the first line, so nothing is written to `events` at all —
not `project_settings_updated`, not anything. Measured by comparing the newest history **rows**
(type *and* timestamp) either side of each write:

```
after PATCH /accounting/budget : [('accounting_budget_updated', '2026-09-01T11:49:54.887496+00:00')]
after PUT   /settings          : []
```

An operator asking "when did this project's budget change, and to what?" is answered for the
changes made in the Accounting panel and told nothing about the ones made in Settings. The same
hole covers every other setting that route writes — the checkpoint mode, the hop budget, the main
branch — each of which changes how the project behaves and none of which leaves a record.

**C.** Nothing misbehaves; the audit trail is simply half of one, and the half that is missing is
invisible rather than marked absent.

**Note on how this was measured, because the first attempt got it wrong.** Checking that *"the
newest history entry is an `accounting_budget_updated`"* passes on the **previous** write's row —
every budget change persists the same event type — and reported a pass for a route that had
persisted nothing. The timestamp is what makes the two distinguishable.

**Reproduction:** `scripts/drive/t_sweep_row14_accounting.py`, leg 3.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `update_project_settings` works out which fields changed before writing them, and when any did it
calls `persist_event(..., "project_settings_updated", {"changed": {field: {"was", "now"}},
"settings": ...})` beside the broadcast it already sent. A save that changes nothing records
nothing. Measured by `hub/tests/test_a_request_means_what_it_says.py`: two identical saves leave one event, naming `hop_budget` was/now. On the
old code there were none.

## F239 (C) — the per-conversation usage rollup answers "0 tokens" for a conversation that does not exist

**Status:** fixed (this commit) [Round 4, 2026-09-23] — an unknown or another project's conversation is a 404; see FIXED at the end of this entry. Was: open. Verified 2026-09-09: the route still passes the id straight to
`conversation_usage` (`hub/hub/api/v1/accounting.py:40`) with no existence check, so a typo, a
cross-project id and an unmeasured conversation are still one honest-looking zero. [classified 2026-09-09, D-3]

`GET /projects/{id}/accounting/conversations/{conversation_id}` (`accounting.py:33-40`) passes the
id straight to `conversation_usage`, which is an aggregate over a join. An aggregate over no rows
is a valid empty summary, so the route answers **200** with:

```json
{"input_tokens": null, "output_tokens": null, "total_tokens": null,
 "measured_turns": 0, "unavailable_turns": 0, "api_equivalent_usd_micros": null}
```

for `conv-does-not-exist`, and — driven with a real conversation created in a second project —
**the identical body** for a conversation that exists but belongs to somebody else.

The isolation itself holds: `usage_accounting.py:186-196` filters on `TurnUsage.project_id`, so no
figure leaks across the boundary. What is missing is the refusal. Three different situations —
a typo, a cross-project id, and a real conversation whose turns have not been measured — are
rendered by `useConversationAccounting` (`accounting.ts:66`) as the same honest-looking zero.

The same shape as **F216**, and the same one the sibling routes already get right: every other
conversation-scoped route in the Hub (`/checkpoints`, `/checkpoint`, `/continue`,
`/dismiss-checkpoint-warning`) answers 404 for an unknown id.

**C.** No wrong number reaches a decision, but "this conversation has cost nothing" and "there is
no such conversation" are not the same claim and are indistinguishable here.

**Reproduction:** `scripts/drive/t_sweep_row14_accounting.py`, leg 5.

**FIXED 2026-09-23 (interactive session, Round 4, group 4a).** `get_conversation_accounting` (`api/v1/accounting.py`) looks the conversation up with
`get_conversation_by_id` (not `session.get`, whose key is `sequence`) and answers `404 Conversation
not found` unless it is this project's, like the sibling conversation routes. A real conversation
with no measured turns still answers the zero. Measured by `hub/tests/test_an_unknown_name_is_not_an_empty_answer.py`: on the old code
`conv-does-not-exist` answered the zeroed body. `test_accounting_api.py`'s
`..._unknown_conversation_is_zero_not_404` asserted the old behaviour; it is reversed and renamed
`..._is_404_not_zero`. Its sibling now creates the `conv-many` row its runs point at. Shipped UI:
`useConversationAccounting` reads only `data`, so a 404 renders no usage line where it used to
render a zero. It is only ever asked about the open conversation's id.

## F240 (B) — with the budget exhausted and "spending is paused" on screen, the Hub spent $0.042 that reaches no total and no budget

**Status:** fixed 2026-10-16 (Tier 2, decision fix-D2 option C; slice A of D2, change `spec/changes/worker-spend-counts-against-the-budget`, re-authored from the openspec draft of the same name, folded into `usage-accounting` and `conversation-checkpoint`, archived). Migration 0129 gives every worker row a normalised `total_tokens` (backfilled) and the outcome `budget_exhausted`; worker totals join the project total and the budget as per-kind `workers` lines; an autonomous worker call is not spawned at exhaustion while an operator one runs; the automatic checkpoint triggers warn instead of generating; the titler answers in JSON and records a `conversation_title` row. Driven with `scripts/drive/d1016_f240_worker_spend.py` (Haiku): 5 of 11 failed at 13f77d8, ALL PASS after d01eb0d. Copilot credits on the worker lines (F665) are slice B. Opened before: open. Filed by the row-14 drive (`d68f39a`) and carried into the 2026-09-06 and
2026-09-07 research pages. F92 recorded the `worker_invocations` half as an operator question
rather than a defect; neither half has been repaired. [classified 2026-09-09, D-2]

`BudgetExhaustionNotice.tsx:12` is the product's own sentence for an exhausted budget:

> Autonomous turns are paused; operator messages can still run.

Driven, in that state — `token_budget` set to half of what the project had already spent, so
`GET /accounting` reported `{"limit_tokens": 17070, "used_tokens": 34140, "remaining_tokens": 0,
"exhausted": true}` — the operator took a checkpoint. Two real `claude-haiku-4-5` calls ran:

```
wrk-fb179e9d1a98  kind=checkpoint        outcome=ok  in=10  out=497  cost_usd_micros=21443
wrk-4ee9f38092ac  kind=checkpoint_probe  outcome=ok  in=10  out=215  cost_usd_micros=20714
```

**42,157 usd_micros — about $0.042 — over 732 tokens.** Measured immediately afterwards:
`GET /accounting`'s `project.total_tokens` unchanged, `budget.used_tokens` unchanged, and no
`turn_usage` row written. `accounting_snapshot` reads `TurnUsage` and only `TurnUsage`
(`usage_accounting.py:110-129`); `worker_invocations` is joined to no aggregate and read by no
budget.

**The conversation titler is the same hole without even the audit row.** With
`conversation_title_mode: generate`, a completed turn triggers `maybe_generate_title`
(`agent_trigger.py:2146`), which spawns a real model call — driven, and it produced the title
*"Agent outputs ROW14D as instructed"*. `conversation_titles.py` predates `worker_invocations` and
was never joined to it, so that call wrote **no `worker_invocations` row and no `turn_usage` row**.
Its cost is recorded nowhere at all. The only evidence it happened is the `conversation_titled`
event and the title itself.

Neither spender consults `project_budget_state`. Grepped: its two callers are
`turn_scheduler.py:136` and `inbound_queue.py:147`, both about agent turns.

**F92 recorded the `worker_invocations` half of this as a question for the operator rather than
driving it** — *"real model calls made on the operator's behalf [that] appear on no aggregate
surface and in no budget"*. This drives it, adds the titler, which F92 did not name and which is
worse because nothing records it, and adds the fact that makes it a defect rather than a design
question: **the gap is not bounded by the budget.** An operator who sets a budget specifically to
cap spending keeps spending, at a rate the product will not show them.

**B.** Money leaves at a number the operator cannot see, in the state where they have explicitly
asked for it to stop.

**The repair is a decision, and it is the operator's** — whether worker spend joins the project
total, sits beside it as its own line, or counts against `token_budget` is a question about what a
budget means. What is not a decision: the titler must write an invocation row like every other
worker, or its cost is unrecoverable.

**Recorded as passing, because a sweep that only reports defects is not a measurement:** the
per-turn accounting itself is sound and was driven end to end. One measured row per turn with the
runner, the model and a real token total; the project total is exactly the sum of the measured
rows; `measured_turns` counts them; every ended run has exactly one accounting outcome and no run
has two (F92's invariant, re-driven); an empty project reports `null` totals and
`preferred_display: {"kind": "unavailable"}` rather than `$0.00`; cross-project totals do not mix;
`remaining_tokens` clamps at zero instead of going negative; an operator message really does still
run with the budget exhausted, and its cost really is counted; both routes refuse an
unauthenticated caller and an unknown project is a 404. `preferred_display` surfaced genuine
rate-limit telemetry — `{"rateLimitType": "five_hour", "status": "allowed", "overageStatus":
"rejected", "overageDisabledReason": "out_of_credits"}` — which `accountingDisplayLabel` renders in
operator language rather than as raw JSON.

**Reproduction:** `scripts/drive/t_sweep_row14_accounting.py`, legs 6-8.

---

**Re-verified 2026-10-15** (full sweep, G6: Accounting & allowance, scratch Hub `:8036`): still reproduces. 28 checkpoint `worker_invocations` costing $0.52 appear in no total (the Hub reported $0.70 for the turns). G2 adds: both `conversation-titles` firings record `"usage": null` in `/manager/activity`, so a titler's spend is unmeasured too.

## F241 (B) — the conflict report is computed, correct, and read by nothing

**Status:** fixed (this commit) [UI-1, 2026-09-23] — the Worktrees panel reads `GET /worktrees/conflicts` and names each conflicting pair and its files; see FIXED at the end of this entry. Was: open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced. Its
only external mention is the 2026-09-01 review page. [classified 2026-09-09, D-2]

`hub/hub/worktrees.py:1014` `detect_conflicts` pairwise-merges every provisioned Hub-owned branch
with `git merge-tree`; `hub/hub/api/v1/worktrees.py:135` serves it as
`GET /projects/{p}/worktrees/conflicts`, with a docstring calling it *"the interface identifies
which agents diverged"* half of hub-native-runtime's **"Divergent changes surface as a conflict"**
scenario.

Measured, twice: **zero call sites.** No `.ts`/`.tsx` under `hub/ui/src` (tests excluded) contains
the string `worktrees/conflicts`, and it does not appear in the served bundle under
`hub/hub/static/ui/assets/` either — while `worktrees` (the *list* route, which
`WorktreesPanel.tsx` does call) is present in the same bundle. The Worktrees settings page renders
the list of checkouts and nothing else.

So in the drive above, the product knew that `alpha`'s and `beta`'s task branches conflicted on
`calc.py`, and there is no screen on which an operator could learn it. The requirement's own words
are *"surface as a conflict"*.

**B.** A shipped capability with no surface. Same family as F215 (every 9c route absent from the
bundle), and worth queueing with it: both are "the endpoint exists, the UI never asks".

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 5.

**FIXED 2026-09-23 (interactive session, UI-1).** New `useWorktreeConflicts()` (`hub/ui/src/api/workspace.ts`), keyed `['project', id, 'worktree-conflicts']` rather than under `'worktrees'`, because `useAgentWorkspace` keys an agent's checkout as `['worktrees', <agent>]` and an agent may be named `conflicts` (F248). `WorktreesPanel` renders what it returns under the list: `N conflicts`, each as `agent codex-1 and task task-…` (a main-branch side reads `the main branch (main)`, Round 3e's F245 check), both branch names, and the files. An empty answer reads `No conflicts: git finds nothing here that would stop a merge.` only when checkouts are listed; a failed check is an alert, never a clean result; a conflict on a retained task branch with no checkout (F246) still shows with an empty list. Not polled (every pair is a `git merge-tree`); refetch on events is F250's, in this round. Tests: `worktreesPanel.test.tsx` (six new, fixture in the route's order: main pairs first).

---

## F242 (B) — one PATCH moves an agent off isolation mid-task, and its next task-bound turn writes uncommitted into the operator's checkout

**Status:** fixed 50e6b16 (`isolation-does-not-change-under-held-work`, 2026-09-30: a change to where an agent works is refused while it has a running turn or an unfinished task, on `PATCH /agents/{name}` and `POST /session/sync`). The flip-independent residual (a read-only agent created that way and assigned a writing task) stays open as the design's Open Question 1 (d). Was: open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced. [classified 2026-09-09, D-2]

`hub/ui/src/components/agents/AgentSettingsPage.tsx:290` states, in writing, why the Isolation row
is display-only:

> Isolation itself is not editable here. It is a real stored setting (`config.read_only`) that
> nothing offers today, and giving it a control is a change of behaviour — flipping an agent with
> uncommitted work in its worktree to the shared checkout would strand that work somewhere the
> agent no longer looks. That belongs in its own change, with a decision about what happens to the
> existing worktree.

The panel keeps that promise. `PATCH /api/v1/projects/{p}/agents/{name}` does not. Driven, twice,
in this order:

```
PATCH /agents/beta {"config": {"read_only": true}}   -> 200, config {"read_only": true}
GET   /worktrees/beta                                -> isolated: false,
                                                        working_dir: <project root>,
                                                        task_checkouts: []   (was ["task-..."])
   ... while .agentweave/tasks/task-... is still on disk and still on GET /worktrees
POST  /agent/trigger {agent: beta, task_id: task-...} -> run completed
git status (project root)                             -> " M calc.py"
git show agentweave/task/task-...:calc.py             -> does NOT contain the turn's function
```

Three separate consequences, each measured:

1. **The agent's own settings page loses the work.** `get_agent_workspace`
   (`api/v1/worktrees.py:220`) returns early for a non-isolated agent, and that early return
   carries no `task_checkouts` — deliberately, and correctly for a read-only agent, but the flip
   makes an agent *holding a provisioned task checkout* take that branch. The directory is still
   there and the project-wide list still shows it; the panel an operator would open to find it
   does not.
2. **The turn ran in the project checkout.** `resolve_turn_workspace` (`worktrees.py:651`) gives
   `is_writing_agent` precedence over the task binding, by design and with the reasoning stated
   ("a task checkout it may not write to would be an empty gesture"). But nothing makes the agent
   read-only in any sense other than *where it works* — it is spawned with the same permissions —
   so it edited `calc.py` at the repo root.
3. **Nothing committed it.** No snapshot commit, no task branch movement. The board says
   `completed`; the only copy of the work is an uncommitted modification in the operator's own
   working tree, which integration cannot merge and which the next `git checkout` discards.

**Not rated A, and here is why:** no product surface sets `read_only` — the UI declines to, by the
comment above — so no operator reaches this state by using the app. The API is the only door, and
it is the operator's own API. The defect is that the door the UI deliberately left shut is
standing open next to it, with none of the protection the comment says the change would need.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 8.

---

## F243 (C) — a stored agent config cannot be cleared through the route that set it

**Status:** fixed (this commit) [Round 4, 2026-09-23] — `config: null` clears it, a null key removes that key, `{{}}` is refused; see FIXED at the end of this entry. Was: open. Both clears still answer 200 and change nothing, so *put it back the
way it was* still fails silently on this route -- the same shape the runner-model clear has, which is
what makes it a pattern rather than a slip. Named in no change. [classified 2026-09-09, D-3]

Immediately after the flip above, twice:

```
PATCH /agents/beta {"config": {}}                    -> 200, still {"read_only": true}, isolated false
PATCH /agents/beta {"config": null}                  -> 200, still {"read_only": true}, isolated false
PATCH /agents/beta {"config": {"read_only": false}}  -> 200, {"read_only": false},       isolated true
```

Both clears answer 200 and change nothing, so the obvious operator move — *put it back the way it
was* — silently fails, and only an explicit falsy value for the key you happen to remember
reverses it. This is **exactly F219's shape** on a different route (`PATCH` a runner with
`{"model": null}` answers 200 and never clears the model), which makes it a pattern rather than a
slip: on this API, "absent" and "empty" are the same thing, and nothing can be unset.

This harness lost a full run to it. Run 1's teardown leg cleared `beta`'s config with
`{"config": {}}`, the clear did nothing, and run 2's isolation assertions measured an agent that
was still un-isolated — which is how F242's third consequence was found at all.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 8; cross-reference `t_f219_runner_model_clear.py`.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `PATCH /agents/{name}` still merges `config` key by key; the UI never sends it. An explicit
`"config": null` now clears the whole config (F219's rule: explicit null clears). A key given as
`null` is removed from the merge result. `"config": {}` merges nothing, so it is **refused** with a
400 that names both working forms, instead of answering 200 over no change. A non-object is a
400. Measured by `hub/tests/test_a_request_means_what_it_says.py` (three legs); fails on the old code.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The review showed the merge was flat: a nested null was stored as a value, and a nested object
replaced its predecessor. It also argued, rightly, that the standard contract already makes both
null rules this entry chose. `config` is now an RFC 7396 merge patch, applied recursively
(`agents._merge_patch`): a null deletes at any depth, objects merge, and `{}` is the standard's
no-op (200), no longer refused. `"config": null` still clears everything. Measured by
`test_config_is_a_recursive_merge_patch`, which fails on the previous commit.

---

## F244 (C) — the roster listing carries no `config`, so the setting that decides where an agent works is invisible on it

**Status:** fixed (this commit) [Round 4, 2026-09-23] — the roster carries `config`; see FIXED at the end of this entry. Was: open. Verified 2026-09-09: `OperatorAgentResponse`
(`hub/hub/api/v1/agents.py:113-120`) still declares seven fields and no `config`, so an agent moved
off isolation is still indistinguishable from every other one on the roster. [classified 2026-09-09, D-3]

`OperatorAgentResponse` (`hub/hub/api/v1/agents.py:111`) declares `id`, `name`, `runner_id`,
`charter_id`, `color_index`, `contact_mode`, `self_registered` — and no `config`. Measured with
`beta` holding `{"read_only": true}` in the database:

```
GET /agents -> [{"name":"alpha","config":null},{"name":"beta","config":null},
                {"name":"conflicts","config":null},{"name":"readerbot","config":null}]
```

`readerbot` is self-registered with `{"read_only": true}` and reads the same. The only surfaces
that expose the flag are the response to the `PATCH` that set it and, indirectly,
`GET /worktrees/{agent}`'s `isolated`. An agent that has been moved off isolation is
indistinguishable from every other one on the roster.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 8.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `AgentSummary` gained `config`, filled by `GET /agents` from the row (empty for an agent with
none), **without `env_vars`**, whose values can be credentials. `_runner_summary` prints only their
names for the same reason. Measured by `hub/tests/test_a_request_means_what_it_says.py`, which also asserts a planted env value is absent from
the whole roster body; fails on the old code.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The roster's config is now an **allow-list** (`agents.ROSTER_CONFIG_KEYS`: `read_only`, `yolo`,
`runner`, `model`, `cli`, `hub_client`), no longer a deny-list of `env_vars`. `config` is an open
object any PATCH can fill, so a credential under `api_key`, or a token inside `mcp_servers`,
reached the roster. The test plants all three and asserts the value is nowhere in the roster body;
it fails on the previous commit.

---

## F245 (B) — the conflict check never compares a task branch against the branch it will merge into

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- each workspace is also checked against the project's main branch; see FIXED at the end of this entry. Was: open. Filed by the row-15 drive (`4488e8f`), never fixed and never specced. [classified 2026-09-09, D-2]

`detect_conflicts` (`worktrees.py:1014`) walks `list_workspace_branches` and pairs each
*provisioned Hub-owned checkout* with each other. The base branch is not a Hub-owned checkout, so
it is never one of the pair. Driven, twice: with an operator commit on `master` touching the same
region of `calc.py`,

```
git merge-tree --write-tree --name-only master agentweave/task/<alpha's task>  -> calc.py
git merge-tree --write-tree --name-only master agentweave/task/<beta's task>   -> calc.py
GET /worktrees/conflicts -> workspaces are only ["task-...","task-..."];  master is absent
```

The conflict an operator most needs — *this task's work will not merge* — is the one the endpoint
structurally cannot report, and it is the cheapest to compute: one extra `merge-tree` per
workspace against `Project.main_branch`, which `task_integration.detect_main_branch` already
resolves. Today the first time anyone learns of it is when integration fails at approval (the
territory of F155's conflict remedy).

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 6.

**FIXED 2026-09-23 (interactive session, Round 3, group 3e).** `detect_conflicts(repo_root,
main_branch=None)` now runs one `merge-tree` per workspace against *main_branch* before the pairwise
pass, reporting each hit with the base as its first workspace (`kind: "main"`,
`worktrees.MAIN_BRANCH_KIND`, `name` and `branch` the branch itself). `GET /worktrees/conflicts`
passes `Project.main_branch` -- the operator-accepted branch integration merges into, not
`detect_main_branch`'s suggestion; with none set, or one that does not resolve, nothing is checked
against it, because a conflict against a guessed base is not a fact. No UI reads this route today,
so no bundle. Tests (`test_worktrees.py`): `test_a_workspace_that_will_not_merge_into_main_is_reported`,
`test_no_main_branch_or_an_unresolvable_one_checks_nothing_against_it`,
`test_the_conflicts_route_checks_against_the_projects_main_branch` -- the route test fails on the old
code with `[]`, the finding's own measurement. Not re-driven with leg 6.

---

## F246 (C) — finishing a task takes its conflict off the report while the divergence remains

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- a released task branch with unmerged work stays in the conflict check unless the task was rejected; see FIXED at the end of this entry. Was: open. Releasing the checkout still takes the branch out of
`list_workspace_branches`, so a finished task's branch still stops being conflict-checked while the
Hub's own release event records unmerged commits on it. Named in no change. [classified 2026-09-09, D-3]

`release_task_workspace` (`task_transition_service.py:629`) removes the checkout on `approved` or
`rejected` and **keeps the branch**, deliberately: *"the branch is the record of what the task did,
and deleting it would destroy both the history an operator reads after the fact and the work a
reopened task resumes from."* `list_workspace_branches` (`worktrees.py:914`) excludes a branch with
no checkout. `detect_conflicts` walks that list. So the moment a task ends, its branch stops being
conflict-checked.

Measured, twice, within one leg:

```
before the release   GET /worktrees/conflicts -> [("task-alpha...","task-beta...")] on calc.py
PATCH task -> completed -> rejected
after  the release   git merge-tree(alpha's branch, beta's branch) -> ["calc.py"]   (still conflicts)
                     GET /worktrees/conflicts -> []                                 (silent)
```

The Hub knows the branch has work nobody has merged — the release event it writes in the same
transaction says `"unmerged_commits": ["0a05f57..."]` and is raised at severity `warn` for exactly
that reason. A `rejected` task's branch going quiet is arguable; `approved` uses the same path,
and `approved -> revision_needed` is a legal edge, so a reopened task resumes from a branch that
has been outside the conflict check for as long as it was closed.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 7.

**FIXED 2026-09-23 (interactive session, Round 3, group 3e).** New
`worktrees.retained_task_branches(repo_root, task_ids, main_branch)`: one `for-each-ref` over
`refs/heads/agentweave/task/`, kept where the task is one the caller names, the branch has no
checkout, and (when the main branch resolves) `rev-list main..branch` is non-empty -- work that has
not landed. `detect_conflicts` takes them as `retained`, so they meet every check, the main-branch
one included (F245). The route names every task in the project **except `rejected`**: the entry
calls a rejected branch going quiet "arguable", and keeping refused work in the report forever would
be noise the operator cannot clear; `approved` work waiting on integration, and a reopened task's
branch, stay visible -- the case the entry measured. Tests (`test_task_worktrees.py`):
`test_a_released_task_branch_with_unmerged_work_stays_in_the_conflict_check`,
`test_a_released_branch_whose_work_landed_or_was_not_asked_for_is_left_out`,
`test_the_conflicts_route_keeps_an_approved_tasks_branch_and_drops_a_rejected_one` -- the route test
fails on the old code with `[]`, the entry's "silent". Not re-driven with leg 7.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** With no main branch accepted, nothing could be called landed, so
every approved branch stayed in the check forever and reported its successors as conflicts, and
`detect_conflicts` ran a `merge-tree` per pair synchronously inside the async route. Now
`retained_task_branches` retains nothing without a resolvable main branch (F245's "no guessed base"
rule), and the route runs both git passes in `asyncio.to_thread`. The route test now accepts `main`
first; the unit test pins the no-main case.

---

## F247 (C) — `GET /worktrees/{agent}` invents a workspace for an agent that does not exist

**Status:** fixed (this commit) [Round 4, 2026-09-23] — the route refuses a name nothing is recorded under; see FIXED at the end of this entry. Was: open. The route still validates the name and never asks whether it belongs
to anything, so it still answers about a roster entry that was never created -- the third instance of
that shape in three days, and the others are unrepaired too. [classified 2026-09-09, D-3]

```
GET /projects/proj-a214ba696422/worktrees/ghostr15c
200 {"agent":"ghostr15c",
     "repo_root":"C:\\Users\\huida\\Documents\\aw-drive-row15",
     "working_dir":"...\\.agentweave\\worktrees\\ghostr15c",
     "isolated":true,"branch":"agentweave/ghostr15c","provisioned":false,"task_checkouts":[]}
```

There is no agent by that name. `get_agent_config` (`launchability.py:361`) merges three sources
and returns a usable dict when all three are empty, so the endpoint answers about a roster entry
that was never created. The route validates the *name* (`user` and `bad.name` are both 400) and
never checks that the name belongs to anything.

Third instance of this shape in three days — F216 (the drift candidate projects only database ids)
and F239 (the per-conversation rollup answers 200 with a zeroed summary for a conversation that
does not exist) are the same defect on different routes. Every sibling route on this project 404s
an unknown entity.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 2.

**FIXED 2026-09-23 (interactive session, Round 4, group 4a).** `get_agent_workspace` (`api/v1/worktrees.py`) calls `hub/hub/agent_roster.py` `require_known_agent` (new, Round 4a): 404 `"{agent} is not an agent in this project: it is not on the roster and nothing is recorded under that name. Correct the name, or create the agent in the Hub UI."` *Known* is the roster **or** any conversation, queue entry or run under that name, because session sync deletes a removed agent's roster row and keeps its history (a roster-only check would 404 that history; guarded by `test_a_removed_agent_s_history_stays_readable`). It runs after
`validate_agent_name`, so `user` and `bad.name` are still 400. Measured by `hub/tests/test_an_unknown_name_is_not_an_empty_answer.py`: on the old code
it answered the invented workspace. Seven older tests asked about agents they never created
(`vera`, `xan`, and `builder` in `test_task_worktrees.py`), and they now register them first.

---

## F248 (C) — an agent legally named `conflicts` can never have its workspace read

**Status:** fixed 2026-10-10 (new names only; `hub/hub/route_words.py`, d1021 3/3 on the committed tree, night iteration 37). Existing rows keep working. Earlier: verified 2026-09-09: `GET /worktrees/conflicts`
(`hub/hub/api/v1/worktrees.py:142`) is still declared before `GET /worktrees/{agent}` (`:231`), and
`AGENT_NAME_RE` still accepts `conflicts`, so an agent legally named that still cannot have its
workspace read. The repair is a namespace, not a reordering. [classified 2026-09-09, D-3]
2026-10-10: specified and built as `spec/changes/a-name-a-caller-chooses-reaches-its-own-resource`
(`spdoc-4e1fa307cd4e`, approved on `:8010`); the openspec copy is archived. Five words collide today
(`conflicts`, `settings`, `sessions`, `board`, `boards`), refused at creation only.

`AGENT_NAME_RE` accepts `conflicts`; `POST /projects/{p}/agents {"name": "conflicts"}` creates it,
201, and it appears on the roster like any other. `api/v1/worktrees.py` declares
`GET /worktrees/conflicts` before `GET /worktrees/{agent}` — with a comment saying so, because the
path parameter would otherwise claim it. Consequence, measured:

```
GET /projects/{p}/worktrees/conflicts   ->  200  []      (a list of ConflictInfo)
                                            not         {"agent":"conflicts", ...}
```

`useAgentWorkspace('conflicts')` therefore hands `AgentWorkspaceInfo`-typed code an array, and that
agent's settings page cannot render its working directory, its branch or its task checkouts. The
fix is a namespace, not a reordering: the sibling route needs to sit somewhere a legal agent name
cannot reach.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 2.

---

## F249 (D) — the worktrees list cannot say "this project is not a repository"

**Status:** fixed (this commit) [UI-1, 2026-09-23] — both list routes say whether the project is a repository, with the reason, and the panel shows it; see FIXED at the end of this entry. Was: open — moved to UI-1 with F250 on 2026-09-23 (Round 4c): saying "not a repository" changes the list routes' response shape, which the bundled Worktrees panel reads, so the route and the view ship together. Both list routes still `return []` for a project that is not a
repository, indistinguishably from a healthy one with no checkouts, while the per-agent route says so
and explains what would change it. [classified 2026-09-09, D-3]

For a project whose directory is not a git repository, `list_worktrees` and
`get_worktree_conflicts` both `return []` (`api/v1/worktrees.py:126` and `:150`) — the same answer
a healthy repository with no checkouts gives. Measured on `aw-drive-row15-nogit`: list `[]`,
conflicts `[]`.

`get_agent_workspace` gets this right and says why in its own docstring — it returns
`unavailable_reason: "<root> is not a git repository, so there is no isolated checkout..."`,
described as *"the only thing telling them `git init` would change it"*. The list has no field to
carry that, and `WorktreesPanel.tsx`'s empty state consequently promises something that will never
happen: *"Isolated checkouts appear here when an agent starts work that needs one."* In a
non-repository project no agent will ever start such work.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 3.

**FIXED 2026-09-23 (interactive session, UI-1).** `GET /worktrees` answers `WorktreeListing {repository, unavailable_reason, worktrees}` and `GET /worktrees/conflicts` answers `ConflictListing {repository, unavailable_reason, conflicts}` (both in `api/v1/worktrees.py`). For a directory that is not a git repository, `repository` is false and the reason reads *`<root>` is not a git repository, so agents here work in the project directory and no isolated checkout is made. Running `git init` there would give each writing agent its own.* A repository with no checkouts is `repository: true` and an empty list, so the two are no longer the same answer. Only the UI and tests read these routes (checked), so the shape change ships with the bundle, as ROUNDS planned. `WorktreesPanel` shows the reason under *Not a git repository* in place of the empty state that promised checkouts, and shows no conflict line. Tests: `test_a_project_that_is_not_a_repository_says_so_on_both_lists`, `test_a_repository_with_no_checkouts_is_still_a_repository` (`test_worktrees.py`), seven existing route assertions moved to the envelope, and `worktreesPanel.test.tsx`'s F249 case.

**Review follow-up 2026-09-23 (adversarial Opus review of UI-1).** Two corrections. *Only the UI and tests read these routes (checked)* was wrong: `scripts/drive/t_sweep_row15_worktrees.py` read them, coerced the envelope to `[]`, and would have failed falsely. It now unwraps the envelope, and its leg 3 checks `repository: false` with a reason. The sentence promised that `git init` alone would give each agent a checkout, but provisioning refuses a repository with no commit, and `is_git_repo` is also false when git is not on the Hub's PATH. It now names both: *(or git is not on the Hub's PATH)* and *A repository with at least one commit (`git init` and a first commit)*.

---

## F250 (D) — nothing invalidates the worktrees query, so the panel does not notice a checkout being created

**Status:** fixed (this commit) [UI-1, 2026-09-23] — run and task events refetch the Worktrees panel and its conflict check; see FIXED at the end of this entry. Was: open. Nothing invalidates the worktrees query and no SSE event reaches it,
so the panel still shows whatever was true at mount while agents provision checkouts behind it. [classified 2026-09-09, D-3]

`useWorktrees` (`hub/ui/src/api/workspace.ts:100`) keys on `['project', projectId, 'worktrees']`
with no `staleTime` override and no refetch interval. Measured: the string `'worktrees'` does not
appear anywhere under `hub/ui/src/hooks/`, so no SSE event invalidates it — and the drive
provisions two checkouts during a run that emits `run_started`, `queue_entry_delivered`,
`task_updated`, `run_completed` and `task_worktree_released`, none of which the panel hears.

An operator with the Worktrees page open while agents work sees whatever was true when the page
mounted, until a remount or a window refocus. Small, and the same omission that F237 found on the
budget surfaces from the other direction: there the server broadcast an event the client answered
with the wrong invalidation; here there is no event to answer.

**Reproduction:** `t_sweep_row15_worktrees.py`, leg 5.

**FIXED 2026-09-23 (interactive session, UI-1).** `useSSE` invalidates `['project', pid, 'worktrees']` (which also prefixes each agent's workspace key) and `['project', pid, 'worktree-conflicts']` on `task_created`/`task_updated` (approve and reject release a task's checkout) and on `run_started` and the four terminal run events (a turn's checkout is provisioned before `run_started` is sent, and its snapshot lands before the terminal event, which is what moves a conflict). Invalidation refetches only mounted queries, so the merge-tree check costs nothing while the panel is closed. Test: `useSSE.test.tsx` `refetches the worktrees panel when a run or a task moves a checkout (F250)`.

---

## F252 (B) — the Logs screen renders the oldest 500 events a project ever recorded, and can never show a newer one

**Status:** fixed (this commit) [UI-1, 2026-09-23] — the Logs route answers newest first and the screen pages back from the newest; see FIXED at the end of this entry. Was: open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced. [classified 2026-09-09, D-2]

`useLogs` (`hub/ui/src/api/logs.ts:34`) asks for `limit=500` and no offset. `list_logs`
(`hub/hub/api/v1/logs.py:66`) answers:

```python
q = q.order_by(EventLog.timestamp.asc()).offset(offset).limit(limit)
```

Ascending. So the window is events 1–500 of the project's whole history, and every event after the
five-hundredth is unreachable from `LogsView`, which passes no `since`, no `offset` and no `limit`
(`LogsView.tsx:123`). "Live" mode makes it worse rather than better: it invalidates on every SSE
event and refetches *the same 500 oldest rows*.

Measured on the fixture (1,270 events):

```
GET /projects/{p}/logs?limit=500   ->  500 rows, first `agent_created`, last `row16-bulk-133431`
                                       the newest event of the project: ABSENT
GET /projects/{p}/events/history?limit=100  ->  carries it  (events.py:44 orders .desc())
```

**Not a synthetic condition.** `proj-18e5d4e0` — a real project on this instance, 2,101 events,
which this drive did not create and only read:

```
its Logs screen's request ends at   2026-08-24 11:26:47
the project's newest event is       2026-08-27 04:15:43
```

Three days of its own history the screen cannot reach, growing by every event since. The same
table, through `/events/history`, returns the newest 100 correctly — so the two read routes over
`event_logs` disagree about which end of the log an operator wants, and the one wired to the Logs
page picked the wrong end. The volume strip on that page ("last 30m", `LogsView.tsx:73`) is drawn
from whatever half-hour happens to sit inside the first 500 rows.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 4.

**FIXED 2026-09-23 (interactive session, UI-1).** `list_logs` orders `timestamp DESC, id DESC`, and `offset` counts back from the newest, the order `/events/history` already used. `useLogs` is now a `useInfiniteQuery` over that route: its first page is the newest `limit` entries, `loadOlder` fetches the page before, and the pages are joined in time order and de-duplicated by id (an entry arriving between two requests shifts the offsets, so a page can repeat a row, never skip one). `LogsView` keeps its tail layout and gains *Load older entries* at the top while there is an older page. Two things came with it. First, `n11_query_error_surface.DECL_RE` matched only `useQuery`, so the switch made the Logs call site vanish from `test_surface_ceilings`' count while it still ignored its error; the pattern now matches `useInfiniteQuery`. Second, the site was repaired rather than hidden: a failed read renders `Could not read this project's log.` instead of *No log entries yet*, its MISREPORT row is retired, and the two ceilings drop 100 to 99 and 55 to 54. F255's malformed `since`, paired with this in ROUNDS, was closed in Round 4c. Tests: `test_the_logs_page_is_the_newest_and_pages_back` (`test_a_request_means_what_it_says.py`), `logsNewestFirst.test.tsx` (2), `logsVolumeStrip.test.tsx` (failure line, load-older).

**Review follow-up 2026-09-23 (adversarial Opus review of UI-1).** *Load older entries* made the older page flash as new arrivals; the arrival effect now counts an unseen row as new only when it is not older than the newest row already seen. The Refresh button invalidated `['logs']`, which matches no key, so it did nothing (predates the round); it now invalidates the project's logs key. The route test inserts rows with explicit timestamps: `EventLog.id` is random, and equal timestamps on a coarse clock would have left the order to chance.

---

## F253 (B) — a subscriber that falls behind loses events silently: 1,426 of 3,000, twice, with no gap on the wire and no disconnect

**Status:** fixed (2026-10-12, night ledger-sweep-2) by `a-live-view-that-fell-behind-is-told-and-catches-up` (archived 2026-09-26): `SSEManager` subscriber queues count `dropped` and tell the client; `useSSE.ts`, `ActivityLog.tsx` and `eventSummary.ts` handle `stream_gap`; `test_a_stream_that_fell_behind_is_told.py` passes. Older text kept below.

**Earlier status:** open. Filed by the row-16 drive (`00b5dd9`), never fixed and never specced. [classified 2026-09-09, D-2]

`SSEManager.broadcast` (`hub/hub/sse.py:93`, `:102`) drops on a full queue:

```python
try:  # noqa: SIM105
    q.put_nowait(event)
except asyncio.QueueFull:
    pass
```

The queue is 256 deep (`sse.py:43`, `:63`). Driven: one instance-stream subscriber that stops
reading (`SO_RCVBUF` 512, no `recv`), then 3,000 events pushed through `POST /logs`, then the
socket drained.

```
burst of 3000 events pushed in 15.2s
events of the burst the stalled subscriber eventually received:  1574/3000
run again on the state the first left:                           1574/3000
```

1,426 lost, deterministically, and **nothing anywhere says so**. The wire carries no `id:` field
(so `Last-Event-ID` cannot be used, and the server implements no replay), no sequence number and no
gap marker; the connection is never closed, so the one catch-up mechanism the client has —
`useSSE.ts:412`'s `onSseReconnect(() => queryClient.invalidateQueries())`, which fires on reconnect
— **never runs**. A client that has lost half the stream is in exactly the state of a client
watching an idle project.

The comment at the drop site reasons about the right thing ("slow consumer — drop event rather than
block") and the choice is defensible; what is missing is any signal that it happened. One counter
on the subscriber and a `stream_gap` frame on the next successful put would let the client do what
it already does on reconnect.

Scale note: 3,000 events in 15s is not an operator typing. It is one verbose agent turn —
`record_agent_output` writes and broadcasts per streamed chunk — reaching a browser tab that has
been backgrounded, throttled, or is on a slow link.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 6.

---

## F254 (C) — an SSE ticket outlives the project it names, and opens a stream for a project that no longer exists

**Status:** fixed (this commit) [Round 4, 2026-09-23] — the ticket path refuses a missing project, as the header path does; see FIXED at the end of this entry. Was: open. Verified 2026-09-09: `get_project_for_sse` still tolerates an empty
lookup (`hub/hub/auth.py:204`), so a minted ticket still opens a stream for a project the header path
refuses, for up to the ticket's TTL. [classified 2026-09-09, D-3]

`_verify_ticket` (`hub/hub/auth.py:66`) is an HMAC and an expiry check with no database in it, and
`get_project_for_sse` (`auth.py:191`) tolerates the lookup coming back empty:

```python
project = proj_result.scalar_one_or_none()
project_name = project.name if project else project_id
return project_id, project_name
```

Measured, in one leg, against the same deleted project:

```
GET /projects/{gone}/events/ticket                 ->  404   (cannot mint one)
GET /projects/{gone}/events?token=<minted before>  ->  200   stream opens, `connected` frame sent
GET /projects/{gone}/events   Authorization: ...   ->  404   (the header path refuses)
```

The two authentication paths onto the same route disagree about whether the project exists, for up
to the ticket's 300-second TTL (`config.py:34`). The stream is empty — nothing will ever broadcast
on a deleted project's channel — which makes it worse to hand a client than a refusal:
`SSEManager.subscribe` registers a queue under the dead id, and the client sits on a connection
indistinguishable from a quiet one.

Fourth instance of this shape in three days: F216 (drift candidates project only database ids),
F239 (per-conversation usage answers for a conversation that does not exist), F247
(`GET /worktrees/{agent}` invents a workspace). Here the entity was real and then deleted, which is
the harder half of the same rule.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 9.

**FIXED 2026-09-23 (interactive session, Round 4, group 4a).** `get_project_for_sse` (`hub/hub/auth.py`) now answers `404 Project not found` when the project
a valid ticket names is gone, the same answer the header path gives, and no longer returns
`(project_id, project_id)`. Measured by `hub/tests/test_an_unknown_name_is_not_an_empty_answer.py` `test_a_ticket_for_a_deleted_project_opens_no_stream`
with a ticket minted for a project that does not exist. On the old code the stream opened and the
test timed out at 10 s. On the new code it answers 404 at once. The ticket itself is unchanged: an
HMAC and an expiry, with no database in it.

---

## F255 (C) — a malformed `since` is silently ignored, and the route answers as though no filter was asked for

**Status:** fixed (this commit) [Round 4, 2026-09-23] — a malformed `since` is a 400; see FIXED at the end of this entry. Was: open. Verified 2026-09-09: `list_logs` still swallows a malformed `since`
(`hub/hub/api/v1/logs.py:62-65`) and answers the whole window as though no filter had been asked for.
A trap laid for the next caller rather than a live defect, which is when it is cheapest to repair. [classified 2026-09-09, D-3]

`list_logs` (`hub/hub/api/v1/logs.py:60`):

```python
try:
    since_dt = datetime.fromisoformat(since)
    q = q.where(EventLog.timestamp > since_dt)
except ValueError:
    pass
```

Measured:

```
GET /projects/{p}/logs?limit=500&since=not-a-timestamp     ->  200, 500 rows
GET /projects/{p}/logs?limit=500&since=2099-01-01T00:00:00 ->  200, 0 rows   (a valid one works)
```

A caller polling for "what happened since I last looked" and getting the format wrong is handed the
whole window instead of an error — the answer looks right and means something else.

Recorded as C rather than B because no shipped caller passes `since` today: `useLogs` accepts the
option and `LogsView` never sets it. That makes it a trap laid for the next caller rather than a
live defect, which is exactly when it is cheap to fix. Two things were checked and are **not**
wrong: an offset-aware and a naive spelling of the same instant return the same rows (500 vs 500),
and a `since` in the future correctly returns none.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 5.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `list_logs` answers `400 since 'not-a-timestamp' is not an ISO 8601 timestamp; send one like
2026-09-23T10:00:00+00:00` instead of dropping the filter. A valid `since` works as before. The
UI's Logs view sends no `since`, and the one UI poller that does (agent output) is a different
route. The newest-first paging half stays in UI-1 with F252. Measured by `hub/tests/test_a_request_means_what_it_says.py`; fails on the old code.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The example in the refusal was `...+00:00`, and an unencoded `+` in a query string arrives as
a space and is itself refused. The example is now `2026-09-23T10:00:00Z (a + must be sent as %2B)`,
and the test asserts the `Z` form is accepted.

---

## F256 (D) — the Logs screen's agent filter offers names that are on no roster

**Status:** fixed (this commit) [UI-1, 2026-09-23] — the Logs agent filter separates roster agents from names that are only in the log; see FIXED at the end of this entry. Was: open. The union of roster names with every string ever logged is still
deliberate and still undistinguished on screen, so the filter still offers names that are on no
roster. [classified 2026-09-09, D-3]

`POST /projects/{p}/logs` takes `agent` from the request body (`logs.py:71`, `LogEventCreate`) and
writes it to `EventLog.agent` unchecked. `GET /logs/agents` (`logs.py:20`) then unions the roster
with `SELECT DISTINCT agent FROM event_logs`, so any string that was ever logged becomes a filter
option:

```
POST /projects/{p}/logs {"event_type":"row16-ghost-133431","agent":"ghost-133431"}  ->  201
GET  /projects/{p}/logs/agents  ->  [..., "ghost-133431", ...]
```

The union is deliberate — an agent that has been deleted should still be selectable for its own
history — and the credential is the operator's, so this is not an identity hole of the kind
`agent_auth.py` guards. It is a naming one: the dropdown mixes "agents you have" with "strings
someone once logged", with nothing on screen distinguishing them.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 8.

**FIXED 2026-09-23 (interactive session, UI-1).** `LogsView` reads the whole roster (`useAgents('all')`, archived included, since their history is theirs) beside `/logs/agents` and renders two option groups: *Agents* and *Only in the log (not on the roster)*. The route's union stays as designed. Without the roster the list is one group labelled as such, not a guessed split. A failed `/logs/agents` read now says *Could not read the agent list*. That site was classified MISREPORT (PICKER) in `n11`; its row is retired and the two `test_surface_ceilings` ceilings drop to 98 and 53. Test: `logsVolumeStrip.test.tsx` (F256 case).

---

## F257 (D) — filtering by a severity that cannot exist answers 200 with an empty list

**Status:** fixed (this commit) [Round 4, 2026-09-23] — an unknown severity is a 400 on both readers; see FIXED at the end of this entry. Was: open. Both readers still apply an unvalidated severity while the write path
normalises an unknown one, so a typo still reads as *there are no events of that kind* on the screen
whose job is saying whether something happened. [classified 2026-09-09, D-3]

`list_logs` (`logs.py:57`) and `event_history` (`events.py:42`) both do
`if severity and severity != "all": q = q.where(EventLog.severity == severity)` with no membership
check, while the write path normalises an unknown severity to `warn` (`utils.py:59`,
`_KNOWN_SEVERITIES` — verified live: `severity=banana` on `POST /logs` stores `warn`).

```
GET /projects/{p}/logs?limit=10&severity=banana  ->  200  []
```

So a typo in a severity name reads as *"there are no events of that kind"* rather than *"there is
no such kind"* — on a screen whose entire job is telling an operator whether something happened.
The four legal values are already enumerated client-side (`LogsView.tsx:11`), and the server knows
them one import away.

**Reproduction:** `t_sweep_row16_logs_events_sse.py`, leg 8.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `logs.require_known_severity` (new) refuses a severity outside `utils.KNOWN_SEVERITIES` (made
public; the write path's normaliser reads the same set) with `400 Unknown severity 'banana';
expected one of all, debug, error, info, warn`. `GET /logs` and `GET /events/history` both call it.
Measured by `hub/tests/test_a_request_means_what_it_says.py` on both routes; fails on the old code.

---

## F258 (B) — every message the operator sends through `POST /messages` is born one hop past the budget, and waits there until somebody releases it by hand

**Status:** fixed (this commit) [Round 3, 2026-09-22], with F395 — an operator `POST /messages` is queued at depth 0 as `origin_type="operator"`; see FIXED at the end of this entry.

`create_message_for_actor` (`hub/hub/api/v1/messages.py:56`) opens with:

```python
hop_budget, _ = await project_limits(session, project_id)
hop_depth = hop_budget + 1          # messages.py:56-57
...
if run_id:                          # messages.py:58
    ...
    hop_depth = source_run.turn_depth + 1
```

The over-budget value is the **default**, corrected only when the caller supplies a live `run_id`.
Only a running agent has one — `agent_actions.py:203` fills it in from the bound actor. So every
call to the operator-plane route is created at `hop_budget + 1` by construction, and
`turn_scheduler.can_start` refuses a turn whose every entry is over budget.

Measured on a fixture whose `hop_budget` is the default 6:

```
POST /projects/{p}/messages {"from":"alpha","to":"bravo",...}   ->  201  msg-1333da76a0cf
entry-bd92f443eb13  agent=bravo  hop_depth=7  state=queued
event_logs: queue_chain_suspended (severity warn)
45s later: runs for bravo unchanged, entry still queued
```

It is not a race. Five such entries (sequences 329–333) were still `queued` at depth 7 after the
recipient had run **two** later turns for other entries — the depth filter in `schedule_agent`
selects only entries within budget, so a turn admitted by an agent-sent message steps over them
every time.

The operator is not left blind, but is told the wrong thing. `GET /queue/{agent}/status` answers:

```json
{"agent":"bravo","waiting_count":5,"running":false,"waiting_reason":"hop budget exhausted"}
```

*Exhausted* describes a chain that ran out of hops. Nothing hopped: this is the operator's own
first message, and it arrived spent. The entries themselves list as `origin_type: "agent"` with
`origin_agent` set to whatever the caller put in `from`, so the panel attributes the operator's
send to an agent as well.

There **is** a way out, and it works: `POST /queue/entries/{id}/release` re-bases the entry to
depth 0 (`inbound_queue.py:267`, "a bound with no exit is a wedge") and the recipient's turn starts
immediately — measured, twice, entry `delivered` and a new run for the recipient within the wait.
So the defect is not lost mail; it is that the documented send route needs an undocumented second
call before it does anything, and explains itself with a reason that is about somebody else's
runaway.

Nothing in the shipped UI calls `POST /messages` (see F260), so no operator reaches this through
the app today. `docs/reference/hub-api.md:25` does advertise it — *"`POST` `/messages` — Send a
message"* — and that table is also stale on the route shape, which is project-scoped.

**Reproduction:** `t_sweep_row17_messages.py`, legs 1 and 1b.

**FIXED 2026-09-22 (interactive session, Round 3, group 3a).** Re-verified first against HEAD `a9e934c`: `create_message_for_actor` still opened with `hop_depth = hop_budget + 1` (`messages.py:58`). That default dates from `de5c143` (Phase 6, 2026-08-01), when the CLI's HTTP transport still posted agent mail to this route and a runless send could not be trusted with a depth. Nothing does that now — agents post to `/agent-actions/messages`, where the bound actor always carries a `run_id` — so every runless call is the operator's. It is now queued exactly as the chat (`agent_trigger.py`) and answer (`questions.py`) routes queue operator input: `hop_depth=0`, `origin_type="operator"`, `origin_agent=None`, and a thread it opens has `origin="operator"`. The message row's sender is `"operator"` (`schemas/messages.py:OPERATOR_SENDER`), which `GET /agents`' activity fallback and `GET /status`'s `agents_active` both skip. A send with a `run_id` is unchanged: the run must be live and the sender's, and the entry is one hop past it. Tests: `hub/tests/test_messages.py` (`test_an_operator_message_is_queued_at_depth_zero_as_the_operators`, `..._opens_an_operator_conversation`, `test_an_agent_send_with_its_run_keeps_the_agents_origin_and_depth`), each failing on the old code. `t_sweep_row17_messages.py` legs 1 and 1b now verify the repair (not run live); `t_d0915_reachability.py` leg 5.4b, whose precondition *was* this defect, is retired as skipped rather than passed.

---

## F259 (B) — nothing in the product ever marks a message read, so the StatusBar's `N msgs` chip only ever counts up

**Status:** fixed (`a-loops-outstanding-mail-is-mail-not-yet-delivered`, 2026-09-30): no product decision reads `Message.read` any more. A loop's outstanding mail and `/status`'s `pending` are derived from each message's inbound entry (queued, or delivered into a creator turn still running); the flag stays as the messages API's own bookkeeping (design D1). Was: open in substance, with its headline struck. The amendment below (2026-09-02, D-5)
withdraws the consequence, not the finding: `StatusBar.tsx` is imported by nothing and absent from
the bundle, so no operator sees the chip. What survives is that nothing in the product ever marks a
message read while `GET /status` and `hub/hub/scheduler.py:420` both depend on the flag -- which is
where F264 picks it up. Read this entry as that sentence; the chip is gone. [classified 2026-09-09, D-2]

**Amended 2026-09-02 (D-5): the title's consequence is wrong, the finding is not.** `StatusBar.tsx`
is imported by nothing and is absent from the shipped bundle, measured by the reachability walk at
the end of this file, so the chip below is on no operator's screen. Everything measured here still
holds — nothing marks a message read, 82 are unread across ten days — and the consequence that
survives is `GET /status`'s `message_counts.pending` and `scheduler.py:420`, which is F264.

`msg.read = True` occurs exactly once in the entire Hub:

```python
# hub/hub/api/v1/messages.py:375, PATCH /messages/{id}/read
msg.read = True
msg.read_at = datetime.now(timezone.utc)
```

Its only caller is `useMarkRead` (`hub/ui/src/api/messages.ts:45`), used by `MessageCard`, used by
`MessagesFeed`, which is imported by nothing and is absent from the served bundle (F260). Delivery
does not mark read: an entry that reaches an agent, is delivered in a real turn and answered leaves
`messages.read = 0` — measured on the live turn in leg 7.

Two things depend on the flag. `GET /status` (`status.py:44`) counts unread as
`message_counts.pending`, and `StatusBar.tsx:25` renders it:

```tsx
const pendingMsgs = data?.message_counts?.pending ?? 0
...
<Icon name="chat" size={14} /> {pendingMsgs} <span>msgs</span>
```

That chip sits between `N tasks` (active only) and `N questions` (unanswered only), both of which
fall as the operator works. This one cannot. Measured across every pre-existing project on the
trial instance, read-only:

```
AgentWeave         36 messages,  0 read      oldest unread 2026-08-22 09:52
ledger-stress      34 messages,  0 read      oldest unread 2026-08-23 17:49
snakeGame          11 messages,  0 read      oldest unread 2026-08-22 11:40
drive3-2026-08-31   1 message,   0 read
```

82 messages, none ever read, across ten days of use. The only `read = 1` rows anywhere on the
instance are the ones this harness marked itself. The route works when something calls it — the
harness called it and watched `pending` fall by exactly one, `read_at` stamped, the message leave
the default listing — which is what makes this a missing caller rather than a broken endpoint.

The second consumer is `scheduler.py:420`, and it is worse there: see F264.

**Reproduction:** `t_sweep_row17_messages.py`, leg 2.

---

## F260 (C) — row 17's whole operator surface is unreachable: three routes, three hooks, three components, none of them in the shipped app

**Status:** fixed 2026-10-12 (night iteration 19): the subtree, `api/messages.ts`, the mock and the three DEAD rows are deleted; `UNHANDLED_SITE_CEILING` 95 -> 92 (measured), `MISREPORT_CEILING` stays 50 (DEAD rows were already excluded), `CLIENTLESS_ROUTE_CEILING` stays; drive `d1012_f260_messages_ui_deleted.py` 8/8. Original decision text: **decided 2026-09-24 (operator, daily review, bundle B10 D6.3): delete, as a no-spec round.** Delete `hub/ui/src/components/messages/` (`MessagesFeed`, `MessageCard`, `ConversationGroup`), `hub/ui/src/api/messages.ts` and the `@/api/messages` mock at `conversationShell.test.tsx:49`; remove `n11`'s three `DEAD` rows (`n11_query_error_surface.py:165-167`) and lower `MISREPORT_CEILING` and `UNHANDLED_SITE_CEILING` (`hub/tests/test_surface_ceilings.py`) by the drop `n11` measures; `CLIENTLESS_ROUTE_CEILING` does not move (the CLI transport still reaches the routes). Rebuild and commit the UI bundle with `hub/ui/src`. Full recipe: `spec-queue/tracks/B10.md` Final. Verified 2026-09-09: `MessagesFeed` is still named by no file outside
its own, so the subtree is still tree-shaken out and the cross-agent view is still absent. The
2026-09-02 reachability sweep found six more routes of this shape, and the note below records why six
is a floor -- a depth-1 symbol grep cannot see a whole unreachable subtree, and the walk it asks for
has still not been run. [classified 2026-09-09, D-3]

`api/v1/messages.py` exposes `POST /messages`, `GET /messages` and `PATCH /messages/{id}/read`.
`hub/ui/src/api/messages.ts` wraps two of them in `useMessages`, `useMessageHistory` and
`useMarkRead`. `components/messages/` implements the screen: `MessagesFeed` (163 lines),
`MessageCard` (155), `ConversationGroup` (40) — inbox/history toggle, per-agent chips, sort
control, group-by-conversation.

Measured: no file under `hub/ui/src` outside `components/messages/` names `MessagesFeed`,
`MessageCard` or `ConversationGroup`; no file outside that directory calls any of the three hooks;
there is no route and no sidebar entry. Vite therefore tree-shakes the lot, and the served bundle
confirms it:

```
served bundle does NOT contain 'Loading messages'
served bundle does NOT contain 'No message history'
served bundle does NOT contain 'Messages between agents will appear here.'
served bundle does NOT contain 'Group by conversation'
control: a StatusBar literal ('msgs')      IS in the bundle
control: a live event name ('agent_output') IS in the bundle
```

The controls matter: the same grep finds strings from screens that *are* shipped, so the misses
above are absence, not a broken search.

Peer mail itself is not invisible — a message delivered to an agent appears in that agent's
conversation, which is where the operator actually reads it. What is gone is the cross-agent view:
who wrote to whom, in what order, across the project. And with the screen went the only caller of
`PATCH /read` (F259) and the only caller of `GET /messages`'s filters (F262, F263), which is why
three separate route-level defects have sat undisturbed.

**Reproduction:** `t_sweep_row17_messages.py`, leg 3.

**2026-09-02, night window — six more instances of this shape, and a warning about how they were
counted.** A repo-wide sweep for R-1 (`scripts/drive/n10_route_reachability.py`, written up in
`spec-queue/DECISIONS.md` under R-1) found six further routes whose only client is a hook no
component outside its own file imports, all six tree-shaken out of the served bundle exactly as
this row's three were: `requestCompact` (`POST …/agents/{name}/compact`), `requestNewSession`
(`…/new-session`), `useJob` (`GET …/jobs/{job_id}`), `useRunnerLaunchability`
(`GET …/runners/launchability`), `useAgentLaunchability` (`GET …/agents/launchability`) and
`useDivergences` (`GET …/tasks/divergences/recent`). `useAgentLaunchability` is named by nine test
files, so unit tests do not notice.

**That sweep cannot have found this row, and would not find another like it.** It is depth-1: it
asks whether any file outside a hook's own names it, and this row's three hooks *are* named — by
`MessagesFeed`, which nothing imports. A whole unreachable subtree is invisible to a symbol grep,
so six is a floor. Sizing the class properly needs a reachability walk from `App.tsx`; nobody has
done one, and this note exists so the next person does not read six as the answer.

---

## F261 (C) — the recipient is checked against the roster and the sender is not, so a name nobody registered becomes a listed agent

**Status:** fixed (this commit) [Round 3, 2026-09-22] — without a `run_id` the sender can only be the operator; see FIXED at the end of this entry.

`POST /messages` resolves `body.recipient` against the `agents` table and refuses an unknown one
with a 404 and a persisted `agent_action_rejected` event (`messages.py:74-105`). `body.sender` is
a 64-character string that is never looked at:

```
POST /projects/{p}/messages {"from":"ghost-140008","to":"bravo",...}  ->  201
messages row: sender='ghost-140008'
SELECT name FROM agents WHERE project_id=...  ->  ['alpha','bravo','retired']   (no ghost)
```

The name does not stay in the row. `GET /status` reports it as an active agent
(`status.py:58` — distinct message senders in the last 24h). More consequentially, `GET /agents`
lists it on the **roster**:

```json
{"name":"ghost-140008","runner":"native","display_model":"Native","runner_id":null,
 "lifecycle":"open","message_count":1}
```

`list_agents` (`agents.py:275`) falls back to "names seen in 24 h of activity" — distinct message
senders among its sources — whenever there is no session config, which is every project now that
nothing writes one. A synthesised name has no `Agent` row, and the archive filter reads
`db_agents[name].lifecycle if name in db_agents else "open"`, so it is never filtered out. That
endpoint's own docstring lists what reads it: *"the rail, task assignment, the job form, peer
recipients, the new-conversation surface"*.

And then the two halves disagree:

```
GET  /projects/{p}/agents         ->  includes ghost-140008
POST /projects/{p}/messages {"to":"ghost-140008"}  ->  404 "no agent by that name is registered"
```

The roster offers a recipient the send route rejects. The same asymmetry writes an
`agent_action_rejected` event onto the timeline of an agent that does not exist — measured: the
refusal for an unknown recipient is stored with `agent='ghost-140008'`.

The credential is the operator's, so this is not an identity hole of the kind `agent_auth.py`
guards, and it is the same *shape* as F256 one route over. It is C rather than B because reaching
it needs a direct API call: no shipped UI posts a message (F260).

**Reproduction:** `t_sweep_row17_messages.py`, leg 4.

**FIXED 2026-09-22 (interactive session, Round 3, group 3a).** Chosen over "check `from` against the roster": a registered name is no better as an identity claim than a ghost's, and CLAUDE.md's rule is that identity is never accepted from a request body. So the operator route refuses with 422 any runless `from` other than `"operator"` (it may be omitted), naming the value and pointing an agent at `send_message`; with a `run_id` the sender must already equal the live run's agent. Nothing is written for a refused send, so no ghost reaches `GET /agents` or `GET /status`, and a refusal of an operator send is recorded with `agent=None` instead of on a made-up agent's timeline. The route's other refusal tests used `"from": "claude"` and would have passed on the sender check alone; they now omit `from` and assert the field they test. Tests: `test_a_sender_without_a_run_must_be_the_operator`, `test_the_operators_mail_does_not_list_the_operator_as_an_agent`. 11 existing tests that meant an agent send now pass a real `run_id` through a new `start_run` fixture (`hub/tests/conftest.py`). `t_sweep_row17_messages.py` leg 4 verifies the repair (not run live). **Left as it was:** the roster's activity fallback still admits any name from older message rows for 24 hours, and non-message sources (heartbeats, output, assignees) are untouched — they are not this finding.

---

## F262 (C) — `GET /messages?conversation=` means an agent pair, and a real conversation id is silently ignored

**Status:** fixed (this commit) [Round 3, 2026-09-22] — a `conversation` that is not `<agent>:<agent>` is refused 422; see FIXED at the end of this entry.

```python
# messages.py:349
if conversation:
    parts = conversation.split(":", 1)
    if len(parts) == 2:
        ...  # sender/recipient pair filter
```

No colon, no filter — and no refusal. Everywhere else in the product `conversation` is a thread id
(`conv-…`); here it is `"alpha:bravo"`. So the natural call answers 200 with the project's entire
mail:

```
GET /messages?history=true&limit=1000                                 ->  26
GET /messages?history=true&limit=1000&conversation=conv-cfb1ab8dd65b  ->  26   (unfiltered)
GET /messages?history=true&limit=1000&conversation=alpha:bravo        ->  18   (filtered)
GET /messages?history=true&limit=1000&conversation=zzz                ->  26   (unfiltered)
```

Same shape as F255 one row over: a filter the route cannot honour is dropped rather than refused,
so the answer reads as *"this is everything for that thread"*. `useMessageHistory` accepts a
`conversation` option and no shipped call site passes one (F260), so nothing hits it today.

**Reproduction:** `t_sweep_row17_messages.py`, leg 6.

**FIXED 2026-09-22 (interactive session, Round 3, group 3a).** Refused rather than taught thread ids: nothing ships a caller (F260), and a real `conv-` filter would have to join through the inbound entries to find the recipient-side thread. The 422 names the accepted shape and says where a thread's messages are. Empty halves (`alpha:`, `:bravo`) are refused too. Tests: `test_a_conversation_that_is_not_an_agent_pair_is_refused` (4 values), `test_an_agent_pair_filters_to_their_messages`. `t_sweep_row17_messages.py` leg 6 verifies the repair (not run live).

---

## F263 (D) — `sort` accepts any string and quietly means ascending, and the default page is the oldest 100 messages

**Status:** fixed (this commit) [Round 3, 2026-09-22] — `sort` is `Literal["asc", "desc"]`; see FIXED at the end of this entry.

```python
# messages.py:356
order_col = Message.timestamp.desc() if sort == "desc" else Message.timestamp.asc()
q = q.order_by(order_col).offset(offset).limit(limit)
```

Only the exact literal `"desc"` reverses anything. Measured — each of these answers 200 with the
same first row as `sort=asc`:

```
sort=DESC        sort=descending        sort=newest        sort=()
```

The default (`limit=100`, `sort=asc`, no offset) is therefore the **oldest** hundred messages a
project ever recorded, which is F252's shape on a second route: past a hundred, the page can never
show a recent one. `useMessageHistory` sends no limit, so the dead screen would have inherited it.

**Reproduction:** `t_sweep_row17_messages.py`, leg 6.

**FIXED 2026-09-22 (interactive session, Round 3, group 3a).** Any other value is now a 422. The default stays `asc`: the CLI transport's `get_pending_messages` reads the unread inbox oldest-first, so flipping it would change the one remaining caller's order. The oldest-page complaint is therefore answered by making `desc` the only way to ask for newest-first, not by changing the default. Tests: `test_a_sort_other_than_asc_or_desc_is_refused` (the four measured spellings), `test_desc_answers_newest_first`.

---

## F264 (B) — the query that decides what a loop is waiting on has no project filter, and the flag it depends on is never set

**Status:** fixed (this commit) [Round 3, 2026-09-22] — `_pending_loop_request`'s message query is project-scoped; see FIXED at the end of this entry. The dead `read` predicate is F259's and is untouched.

`_pending_loop_request` (`hub/hub/scheduler.py:415`) explains the loop's stall to the operator. Its
message branch is:

```python
select(Message).where(
    Message.sender == job.agent,
    Message.recipient == creator_agent,
    Message.read == False,
).order_by(Message.timestamp.desc())
```

There is no `Message.project_id ==` in it. Agent names are project-scoped and repeat freely across
projects — the seeded and conventional ones most of all — so the row this picks can belong to a
different project, and its `subject`/`content` is returned to the caller as the loop's `reason`,
truncated to 300 characters. Every neighbouring query in the same file is project-scoped; this one
is the exception, and the isolation this harness checked elsewhere held on every other axis (mail
listed per project, cross-project `PATCH /read` refused 404, a foreign `conversation_id` refused
404, a foreign `task_id` refused).

F259 sharpens it: because nothing ever marks a message read, `read == False` excludes nothing, so
the candidate set is *every message ever sent between those two names in any project on the
instance*, and "most recent" can be days old.

Measured by mirroring the exact SQL read-only, with the same two agent names present in two fixture
projects and one message sent in each:

```
scoped   (project_id = fixture)          -> rows all belong to the fixture
unfiltered (the query as written)        -> {'proj-e55bb7f8c913', 'proj-1af6c7ad7ecd'}
newest row it would pick                 -> msg-de443740f446 in proj-1af6c7ad7ecd (the OTHER project)
```

**Labelled honestly: mirrored, not driven.** Reaching the branch needs a loop whose
`created_by_run_id` resolves to an agent — that is, a loop created by an agent through
`create_loop`, not by the operator — which this harness does not build. What is measured is that
the query as written selects across projects and that the `read` predicate excludes nothing; what
is not measured is a live loop printing another project's message. The mirror was validated against
the project-scoped form of the same query on the fixture's own rows before being trusted.

**Reproduction:** `t_sweep_row17_messages.py`, leg 8.

### Second pass, 2026-09-01 16:41–16:50 — driven live; the branch fires, the leak did not reproduce

`scripts/drive/t_f264_live_loop_reason.py` builds the situation the mirror could not: two fixture
projects with the same two agent names, a **real `claude-haiku-4-5` turn** as `boss` in the victim
project calling `create_loop(agent="worker", stop_when_queue_empties=True)`, one unread
`worker -> boss` message in each project with the foreign one seeded last, the operator seeding and
then draining the loop's queue, and a manual `POST /jobs/{id}/run`. **48 passed / 7 failed.**

What is now driven rather than argued:

* the branch fires for real. `loop.created_by_run_id` resolved to the creating run, `creator_agent`
  came out as `boss`, the manual fire was answered `409 {"detail": "loop queue is empty"}` and
  emitted `loop_queue_exhausted` carrying a genuine
  `pending_request {"kind": "message", "to": "boss", "reason": <a message's subject>}`. The
  operator-facing reason **is** a message's text selected by this query — measured, not mirrored.
* it is reachable. `GET /loops/{id}` hands the whole payload to the caller and
  `GET /logs?event_type=loop_queue_exhausted` serves it too (8 rows), which is the route the shipped
  Logs screen reads (`LogLine.tsx:132` renders raw data on expand). Meanwhile **no shipped component
  reads `pending_request` at all**, the served bundle contains no reader, and the timeline's entire
  sentence for the event is ``loop ${data.loop_id ?? data.job_id} has no queued work left`` — the
  reason is dropped. Two routes serve the text; nothing explains it.
* F259's half: **28 `worker -> boss` messages instance-wide, 0 read**, so `read == False` excludes
  nothing in practice.

**The leak itself did not reproduce, and the run is inconclusive rather than negative.** The row the
product chose was the *victim's own* newest unread `worker -> boss` message —
`msg-80d3b11d35b7`, 15:49:24Z, subject *"Blocked: Need you to run grep searches from main
project"* — not the foreign fixture `msg-51cf45936ab0` at 15:46:25Z. The foreign row **was** the
newest when leg 2 seeded it (asserted, and it passed). Three minutes later a turn still in flight
from leg 1 — the orphan loop of F265 spending a real turn on an empty queue — had `worker` send
`boss` a genuine message in the victim project, which became the newest candidate anywhere. The
harness's own precondition caught it: `wait_idle` returned **1 busy run after 300 s** and leg 2
failed *before* the candidates were written, so the contamination is recorded rather than inferred.

So the selection behaved exactly as an unscoped "newest anywhere" query does; it simply happened
that the newest anywhere was in-project. The code fact is unchanged — `scheduler.py:415` still has
no `Message.project_id ==` and is still the only unscoped query in that file — and the two halves
the mirror measured (cross-project candidate set, inert `read` predicate) both held again live.

**Still to drive:** one more full pass in which the foreign row is the newest *at firing time*.
The cost is letting leg 1's orphan turn finish before leg 2 seeds; 300 s was not enough on this run.

**Reproduction:** `scripts/drive/t_f264_live_loop_reason.py` (the 7 failures are the six leak
assertions, which fail because the leak did not occur, plus the precondition that explains why).

**FIXED 2026-09-22 (interactive session, Round 3, group 3b).** `Message.project_id == job.project_id` added (`scheduler.py`). **The unit test reproduces what the live pass could not:** two same-named `executor -> creator` messages, the foreign one newer, and on the old query the loop's reason was `"another project's secret"`; now it is this project's. Test: `test_a_loops_pending_message_is_never_another_projects` (`test_scheduler.py`). That file's exhaustion tests only pass after an earlier test has created the schema (run alone they fail with `no such table`; the pre-existing `..._names_an_unread_message_to_the_creator` does too), so the pre-fix check was run as the `-k "pending or exhausted"` batch. `t_f264_live_loop_reason.py` now sends its candidate mail through real `worker` turns — F261's repair refuses the runless `from` it used to forge it with — and legs 4-6 expect the loop's own project's message (not run live).

## F265 (B) — an agent's `create_loop` with `initial_tasks` is refused 403 *after* the loop and job it refused have been committed and left enabled

**Status:** fixed (this commit) [Round 3, 2026-09-22] — the refusal is asked before any row exists; see FIXED at the end of this entry.

A real `claude-haiku-4-5` turn as `boss` called `create_loop` with `agent="worker"` and
`initial_tasks=[...]` — exactly as the tool's own docstring advertises. What came back to the agent:

```
Error calling tool 'create_loop': Hub rejected POST /jobs (403): Only this loop's creator,
or the operator, may add tasks to its queue directly. Use send_message to ask the ...
```

D8 collapses *"the loop's creator"* into `AIJob.agent` — the agent the loop **triggers** — so an
agent may never seed a loop it creates for anybody but itself, which is the ordinary case the
parameter exists for.

The refusal arrives **after the commit**, and this is the defect rather than the policy:

* `loop-0ebfbcc264e4` and `job-605126e6853a` exist. F54's rule — a refused call leaves no rows —
  is breached.
* the job is left **enabled**, with a next firing already stamped by the scheduler.
* its stop condition can never fire: `stop_when_queue_empties` means *drained*, and a queue that
  never filled is not drained. Measured: `POST /jobs/{id}/run` against it was **not** skipped, and
  it spent a real agent turn on a loop with nothing in its queue.

So the caller is told the call failed and has nothing to clean up by, while the operator acquires an
enabled cron loop nobody asked for that burns a real agent turn on every firing. (That turn is what
contaminated F264's second pass above — the defect is not hypothetical, it interfered with another
measurement in the same run.)

**Reproduction:** `scripts/drive/t_f264_live_loop_reason.py`, leg 2a (printed under LEG 1).

**FIXED 2026-09-22 (interactive session, Round 3, group 3b).** Re-verified first: `create_job` committed the job (`jobs.py:677`) and the loop (`:707`) and only then called `create_task_for_actor` for each seed, whose `_authorize_loop_task_creation` refused an agent that is not `AIJob.agent`. A comment beside the seeding claimed the gate was "satisfied for free". The same rule is now asked next to F54's check, before the job row: an agent caller (both identity headers present) seeding a loop whose `agent` is not itself gets a 403 that names the agent the loop runs, says nothing was created, and gives both ways on — create it without `initial_tasks` and `send_message` that agent, or `ask_user` the operator. D8 itself is unchanged (the operator's decision). The false comment is corrected. Test: `test_seeding_a_loop_that_runs_another_agent_is_refused_before_anything_exists` (`test_agent_actions_governed.py`) — no `AIJob`, `Loop` or `Task` row afterwards, and the same call without the seed succeeds; on the old code it fails on `left 1 AIJob row(s)`. `t_f264_live_loop_reason.py` leg 2a now verifies the repair (not run live).


# F190 phase 0 — the observation gate, driven 2026-09-01

`openspec/changes/a-turn-says-how-it-ended` was approved by the operator **conditionally**: observe
the defect live before a line is implemented. Four sittings of review had argued about it and none
had watched it happen. This is what was watched.

**The instrument.** `scripts/drive/f190_model.py` re-implements the six shipped predicates in
Python — `isSuccessCompletionEntry`, `groupIntoTurns`, `runStatusByRunId`, `lastRunSettled`,
`anotherRunIsUnderway`, `runVisiblyActive` — and feeds them from exactly the three HTTP routes the
components read, polled every 0.6 s. That is a faithful stand-in and not a browser, and the reason
it is faithful is measured rather than assumed: `useAgentChatHistory` performs **no optimistic
append** (`agentChat.ts:296-312`), so the component's `entries` are only ever what that route
returned. A poll therefore sees what the component sees, one refetch earlier at worst. Harnesses:
`t_f190_phase0_observe.py` (0.3, 0.4, and a first attempt at 0.2), `t_f190_phase0_stop.py` (0.2 and
0.5 properly).

**The rig.** Hub on **8011** — task 0.1 said 8010, which was a stale line and is corrected in the
tasks file; 8010 is the operator's trial instance. Started from `hub/` with uvicorn from source on
a database of its own (`%TEMP%/aw0901n/aw0901n.db`, migration head `0100`), never 8000. PID 32012,
created 23:23:59; `find hub/hub src -name '*.py' -newermt "2026-09-01 23:23:59"` returns **nothing**,
so no Python under observation moved after the process started. Fresh fixture project
`drive-0901-phase0` = `proj-83415a23d9d5`; neither protected project was opened. Agent `driver`,
runner `runner-4087b438d6e7`, every turn on `claude-haiku-4-5-20251001`.

## F266 (C, was B) — a post-commit `db.refresh` can fail a run that already succeeded, and the queue then runs the agent's turn a second time

**Status:** fixed `d9ad1e0` (2026-09-04, where the same shared connection was filed as F285): the suite left `:memory:` for a per-process file database, so `AsyncAdaptedQueuePool` replaced the one DBAPI connection the settled section below names, and `test_suite_database_isolation.py` asserts the pool is not a StaticPool; this entry's test passed on `48eede3` 2026-09-15 and in the whole-suite gate of `d16a76a` (4361 passed, 0 failed); harness only, and the product residual stays open as F273.

> **Settled 2026-09-03 (night window, iteration 8), by the experiments recorded under F272 — and the heading above is wrong in one word.** The run had *not* already succeeded: its output row was never committed. This is the in-memory test harness's single shared DBAPI connection, not a product defect, and no configuration the Hub ships in can produce it. See the addendum at the end of this entry.

**This is N-2's open question, settled**, and it is not a flake. `hub/tests/` reds on exactly one
test, `test_project_workspace_unavailable.py::test_relocate_repairs_and_redrains_queued_work`, and
only in a **full** run — reproduced twice with identical counts (`1 failed, 3835 passed, 84
skipped, 1 xpassed`, 2026-09-01 N-2 and 2026-09-02 N-6, 23:15 wall clock). No `.py` under
`hub/hub` or `src` changed between the two runs, so it is not attributable to
`runner-model-is-chosen-from-the-catalog`.

**The proximate cause is measured, not guessed.** The traceback is in the product, not the test:

```
ERROR [hub.api.v1.agent_trigger] Unhandled error in run run-a3151507034b for 'claude'
  agent_trigger.py:1959  in _execute_run   -> await _flush_line(raw_line)
  agent_trigger.py:1928  in _flush_line    -> await record_agent_output(...)
  output_recording.py:94 in record_agent_output -> await db.refresh(row)
sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<AgentOutput at 0x...>'
```

`record_agent_output` does `db.add(row)` → `await db.commit()` → `await db.refresh(row)`
(`hub/hub/output_recording.py:92-94`). **The write has already committed** when the refresh raises.
`_execute_run` catches it as an unhandled error and fails the run; the failure path calls
`return_run_entries`, which puts the queue entry back; a second run picks it up and settles. The
test asserts `len(runs) == 1` and sees `2 == 1`.

So the assertion failure is a *symptom*. The behaviour underneath it is: **a run whose output was
successfully written can still be marked failed and its turn re-run**, because of a refresh that
exists only to read `row.timestamp` for the SSE broadcast six lines later
(`output_recording.py:107`). Nothing about that recovery is wrong in itself — re-queueing a failed
run is correct — but the input to it is a false failure.

**What is measured, and what is not.** Measured: the traceback above, the doubling it causes, and
that it reproduces twice at full-suite scale. **Not** measured: that this fires in production. It
has only ever been seen under a 242-file test process, and no live drive has provoked it.

**Bisected 2026-09-02 (N-6), and the result is the interesting part** — all with `-p no:randomly`,
from `hub/`:

| Selection | Result |
|---|---|
| the file alone | **7 passed**, 3.86s |
| `test_conversation_contract.py` + this file — *the reproduction the test's own comment names* | **15 passed**, 6.89s |
| files 106–141 (the 35 immediately preceding it) | **749 passed**, 3:39 |
| files 1–141 (**every** file that precedes it in collection order) | **2253 passed**, 13:31 |
| files 141–242 (it, plus every file collected after it) | **1590 passed**, 8:49 |
| all 242 files | **RED**, 23:15 |

Both halves are green and the whole is red. Since `-p no:randomly` runs files in collection order,
files 142–242 cannot execute before it — and the 1–141 prefix contains everything that can. So the
cause is **not any one preceding file**; it is accumulated process state or load at full-suite
scale. That also fits the shape: the same 141 files take 13:31 as a prefix and considerably longer
inside the full run, so by the time it is reached the process is slower, which is what a race
loses to.

**The test's inline comment was misleading — CORRECTED 2026-09-02 (N-9), so this paragraph is now
history rather than an outstanding task.** The stale second paragraph was replaced in place with
the measurement below and a pointer to this finding; the first paragraph, which explains why the
`await` sits *inside* the patch, was kept because it is still true and still load-bearing. The pair
was re-measured before editing rather than taken from the previous entry's word: `pytest
tests/test_conversation_contract.py tests/test_project_workspace_unavailable.py -q -p no:randomly`
→ **15 passed in 6.99s**. What the comment used to say:
`test_project_workspace_unavailable.py:455-470` attributes this failure to F40's patch-scoping race
(the fake `PtySession.spawn` going out of scope before the background task spawns) and names
`test_conversation_contract.py` + this file as a deterministic reproduction. That race was fixed —
the fake spawn *worked* here, the run got as far as flushing a result line — and the pair it names
measures **green**. A future reader debugging this will otherwise re-derive an answer that is no
longer the answer.

**Reproduction:** `cd hub && py -3.11 -m pytest tests/ -q -p no:randomly`. Expensive — 23 minutes,
and nothing cheaper has been found. Narrowing it further is worth a session of its own; the six
selections above are the ones already spent, so start after them.

**Not proposed.** Needs the day window: the fix is a design question (drop the refresh and stamp
`timestamp` client-side, refresh defensively, or stop treating a post-commit recording error as a
run failure) and this window does not write proposals.

### SETTLED 2026-09-03 (night window, iteration 8) — the harness, and "already committed" was the wrong reading

**F272 is this finding again**, reached from a different test (`test_a_stopped_run_persists_its_terminal_status_line`, added by `a-turn-says-how-it-ended` phase 2) and settled there. The full measurement — a 2x2 over storage and pool, plus a matched-load flake comparison — is written up under **F272**; only what it changes about *this* entry is repeated here.

**The cause.** `conftest.py:19` runs the suite on `sqlite+aiosqlite:///:memory:` and `db/engine.py:34-38` passes no `poolclass`, so SQLAlchemy hands that URL a **`StaticPool`**: exactly one DBAPI connection, shared by every session in the process. When any other session `close()`s between this session's `INSERT` and its `COMMIT`, the `ROLLBACK` that close emits lands on the same connection and discards the insert. Forcing `StaticPool` onto a *file* URL reproduces it; the default file pool (`AsyncAdaptedQueuePool`) does not. It is the pool, not the storage, and the product never runs on that pool.

**The correction that matters for anyone reading this entry.** It says *"The write has already committed when the refresh raises"*. **It has not.** The `COMMIT` runs and commits an empty transaction, because what it was going to commit had already been rolled back. So `db.refresh(row)` is not an over-strict re-read of a row that is fine — it is the only thing in the process that notices the write was lost. That inverts the first of the three fixes this entry proposed: **dropping the refresh and stamping `timestamp` client-side would hide a lost write, not tolerate a harmless one.**

**What this explains about the bisection above.** "Not any one preceding file; accumulated process state or load at full-suite scale" is exactly what a shared-connection interleave looks like — the window is wider the slower the process is. It is also directly confirmed: running four pytest processes of one file concurrently took the rate from **0 in 20** on an idle machine to **5 in 24**, and the 23-minute full-suite reproduction is no longer needed to see it.

**Consequences.** Severity drops **B → C** — it costs suite time and credibility, not operator behaviour. The "Not proposed / needs the day window / the fix is a design question" note is superseded: the design question is a *harness* question (how to give the Hub suite per-session connections without weakening `assert_engine_is_disposable`), and the candidates measured so far are under F272. The one piece of genuinely product-side content that survives from either entry is filed as **F273**.

## F267 (B) — the model catalog is a compile-time literal behind a closed door, and it is already 28 days stale
**Status:** fixed `3b3563a` (2026-09-27). `scripts/check_model_catalog.py`/tests (2026-09-10, `bb08dc4`)
made the staleness visible only; `the-codex-models-offered-are-the-ones-its-cli-lists` closes the
underlying defect by having `model_catalog.py` read the installed CLI's own cache
(`$CODEX_HOME/models_cache.json`) at runtime rather than a literal behind a release, with the literal
kept only as a fallback. Confirmed live in the 2026-09-28 drive (`e94a4a3`): all four doors this
finding measured (`POST/PATCH runners`, `POST agents`, `POST agent/trigger`) now accept a Codex model
because it is offered from the cache, and a model the cache does not list is still refused, per
`GET /model-catalog`'s `source.kind: cli_cache`.

Found by the 2026-09-02 day window's D-1 drive
(`scripts/drive/t_d1_catalog_is_the_only_door.py`, **33 passed / 3 failed**), driving the served
bundle on `:8011` against fixture project `proj-30e5779191b6`. This is research candidate 1 of
`spec-queue/research/2026-09-02.md`, re-measured here independently rather than taken on the
research file's word.

**Two facts, each measured, that are only a problem together.**

*One — every operator-reachable route that sets a model is closed against anything the catalog does
not declare.* Four doors, all tried live, all refused:

```
POST   /projects/<p>/runners       {"cli":"claude","model":"claude-fable-5-1"}     -> 400
PATCH  /projects/<p>/runners/<r>   {"model":"claude-fable-5-1"}                    -> 400
POST   /projects/<p>/agents        {"provider":"claude","model":"claude-fable-5-1"} -> 400
POST   /projects/<p>/agent/trigger {"overrides":{"model":"claude-fable-5-1"}}      -> 400
      {"detail": "'claude-fable-5-1' is not a model 'claude' declares"}
```

and the screen offers no way to express one either — `RunnerForm`'s model field is now a `<select>`
carrying exactly `Provider default` + the catalog's models (measured for both providers), the
Add-agent dialog's Model select carries exactly the catalog's models, and the dialog holds **one**
text input, the Name field (`placeholder="e.g. Claude Opus"`). That is the shipped requirement
working: `runner-registry` — "no free-typed model field is presented". It is not a defect.

*Two — the catalog is a Python literal in `hub/hub/model_catalog.py`, last edited for Codex on
**2026-08-05** (`git log -S 'gpt-5.6-sol'` → `e7ed91e`), and Codex's own server-synced catalog has
moved since.* Read from the CLI's own cache, which is where `model_catalog.py`'s docstring says the
list came from:

```
~/.codex/models_cache.json   fetched_at 2026-08-29T10:33:58Z, client_version 0.146.0
  slugs: gpt-5.6-terra(list) gpt-5.6-luna(list) gpt-reserve(hide) gpt-5.5(list)
         gpt-5.4-mini(list) codex-auto-review(hide)
CATALOG["codex"]:
  gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna gpt-5.5 gpt-5.4 gpt-5.4-mini
```

**`gpt-5.6-sol` and `gpt-5.4` are absent from the cache entirely** — not `visibility: "hide"`,
absent. And `gpt-5.6-sol` is the entry the catalog marks `default=True`
(`hub/hub/model_catalog.py:212`).

**What that costs the operator, measured on screen.** `AgentCreateDialog.tsx:178` seeds the model
from `entry?.models.find((m) => m.default)?.id`, and `canSubmit` requires a model, so the operator
is *handed* the declared default. Driven:

```
preselected model per provider: {'claude': 'claude-sonnet-5', 'codex': 'gpt-5.6-sol'}
```

So an operator who opens Add agent, picks Codex and creates gets a runner bound to
`gpt-5.6-sol` — a model the Codex CLI installed on this machine does not list — and the only
models they can move it to are the other five the same stale literal declares.

**What is NOT measured, and is not claimed.** That a run on `gpt-5.6-sol` fails. Codex is not
driven here (operator directive, 2026-08-29 — Claude runners only), so the spawn's behaviour with
an unlisted model is **unverified**. The finding is the drift and the closed door, not a failed run.
It is severity B rather than A for exactly that reason; if the spawn does fail, it is A.

**One defect or a design gap?** A design gap. The catalog module's own docstring already names the
mechanism ("read directly from `~/.codex/models_cache.json`, the CLI's own server-synced catalog")
and then hard-codes the answer, so the file the docstring points at is authoritative and unread at
runtime. Nothing in the product refreshes it, no route exposes it, and the release that fixes a
drift is a Python edit. **Before the picker shipped this was a soft edge** — free text meant an
operator could type a newly released model and the Hub's `_reject_undeclared_model` was the only
obstacle. It is now the only obstacle *and* the only door. Closing the door was right; leaving the
list a literal is what makes it bite.

**Adjacent, already recorded, and now more consequential:** **F221** (open) — the Hub refuses a
model *alias* its own catalog declares. `claude --help` on this machine documents `--model` as
taking "an alias for the latest model (e.g. 'fable', 'opus', or 'sonnet') or a model's full name",
so an alias is precisely the mechanism that would track a provider's latest model **without** a
catalog edit, and it is the one thing this catalog serves to clients and then refuses. The Claude
half of the drift is **not locally measurable** — `claude --help` enumerates no model list — so the
research file's claim that `claude-fable-5-1` shipped 2026-09-01 stays labelled as its claim, not
as a measurement of mine.

**Reproduction:**

```bash
py -3.11 scripts/drive/t_d1_catalog_is_the_only_door.py     # 33 passed / 3 failed
```

The three reds are this finding (two) and F268 (one). The harness needs a Hub on `:8011` and the
fixture directory `~/Documents/drive-0902-d1`; it opens its own project and deletes it.

**Not proposed.** The day window's spec slot is held by the `a-turn-says-how-it-ended` repair. The
shape of a fix is a real design question — read the provider's cache at runtime, ship a catalog
refresh route, honour aliases (F221), or accept the literal and add a staleness check — and picking
between those is what a spec loop is for.

**The last of those four is now decided and built, 2026-09-10 — and it does not close this.** The
operator's R-3.4 verdict took *accept the literal and add a staleness check*, in the specific shape
of a `scripts/` tool rather than a test (*"a command that diffs catalog against cache has nothing to
skip in CI and is the shape that actually gets run when someone suspects the catalog is wrong"*).
`scripts/check_model_catalog.py` is that command, gated by `tests/test_model_catalog_drift.py`
(23 tests, seven script mutations each killed by a named test). **What that changes is that the
drift is now findable in one command; what it does not change is that the catalog is still a literal
behind a closed door, still stale, and still refreshed only by a Python edit and a release.** The
tool makes the staleness *visible*; F267 is about it being *unfixable without a release*, and no
line of that has moved. Both halves of the drift stay open — see F174's 2026-09-10 re-measurement.

## F268 (B) — the runner-binding select renders `name (cli)`, so the spec's own "second runner with a different model" is unpickable

**Status:** fixed `2b91c92` (2026-09-27) — `a-runner-choice-names-its-model` gave every
runner-choosing select a `runnerOptionLabel` helper naming the runner's model (catalog label,
provider default, or unrecognised id) alongside its name and provider; driven on the trial Hub
`:8010` the same night, two same-named `Twin` runners on different models render distinct labels.
Filed alongside F267 by the 2026-09-02 catalog drive (`7b7720d`). [classified 2026-09-09, D-2]

Fell out of F267's drive rather than being looked for. `RunnerCreate` puts no uniqueness on `name`
and `runners.__table_args__` carries `Index("ix_runners_project_name", ...)` — a plain index, not a
unique one (`hub/hub/db/models.py:328-331`) — so two runners of one provider may share a name. That
is not an accident: `openspec/specs/runner-registry/spec.md` blesses the shape outright.

> #### Scenario: Operator creates a custom runner variant
> - **WHEN** an operator creates a second `claude` runner with a different default model
> - **THEN** both runners are available for binding to any agent independently

They are available. They are not distinguishable. `RunnerPicker`
(`hub/ui/src/components/agents/AgentSettingsControls.tsx:242-246`) renders each option as
`{runner.name} ({runner.cli})` — **the model, the thing the second runner exists for, is not in the
option text and neither is the id.** Driven on screen, agent `d1binder`'s runner select:

```
['No runner',
 'Claude (default) (claude)', 'Codex (default) (codex)',
 'D1 Seed (claude)', 'D1 Seed (claude)',
 'Claude Code (claude)',            <- model claude-opus-5
 'Claude Code (claude)',            <- model claude-haiku-4-5-20251001
 'Claude Code — Sonnet 5 (claude)']
```

Both `Claude Code` rows were created through `POST /runners` with the same name and different
models, both accepted `201`. An operator binding one of them is choosing between two identical
strings, and the choice silently decides which model every subsequent turn runs on.

The last row is the tell: `Claude Code — Sonnet 5` is the runner the Hub *itself* provisions from
the Add-agent dialog's find-or-create path, which names it
`f"{provider_entry.label} — {model_entry.label}"` (`hub/hub/api/v1/agents.py:647`). **The Hub already
knows a runner's name should carry its model** — it just applies that only to the ones it names for
itself, and the operator-facing form neither suggests it nor renders it afterwards.

Severity B, not C: the refusal-legibility rule does not apply (nothing refuses), but the operator is
shown two options that differ in the only respect that matters and is given no way to tell them
apart. Also note the duplicate names are accepted with no warning at all — the create dialog says
nothing about a name already in use.

Whether the fix is a unique constraint, a model suffix in the option text, or both, is a design
question and is **not proposed** here.

**Reproduction:** section D of `scripts/drive/t_d1_catalog_is_the_only_door.py`, or by hand —
create two `claude` runners named the same with different models, then open any agent's
Settings → runner select.

**Re-verified 2026-10-15** (full sweep, G1: Runners & models): the label fix holds (the select reads "name — model (cli)"). Duplicate runner names are still accepted, which this entry's fix did not set out to change (the sweep report called F268 still open; that refers to the uniqueness, not the label).

## F269 (C) — RETIRED 2026-09-03 — a turn whose only agent output is a `status` row loses its "Worked for Xs" line, because the line renders inside the block that returns `null`

> **RETIRED 2026-09-03 (night window, iteration 13), with its severity argument overturned on the
> way out.** The fix is task 4.5a, and it is asserted by two mutation-killed component tests —
> reverting `<Fragment key={entry.id}>{durationLine}</Fragment>` to `null` kills both. The
> reachability paragraph below is now **wrong, and was wrong in the direction it warned about**:
> a stopped run *does* hit this shape, and after task 2.2 it is the ordinary shape of every
> stopped turn. Measured at three stop delays — two entries, the operator's message and the
> status row, no `thinking` row ahead of it. See the phase 7 write-up at the end of this file.

Found by round RA of `a-turn-says-how-it-ended` (2026-09-02) while re-deriving design D6, and
**measured against today's unmodified code** with two throwaway vitest probes rather than left as a
static read. The probes were deleted before commit — the day window does not implement.

`AgentTimeline`'s stat line ("Worked for 5s · 1,204 tokens") is not rendered beside the turn. It is
built per block and emitted only for one of them:

```tsx
const durationLine = statLine && blockId === firstAgentBlockId ? (<div data-testid="turn-worked-for">…</div>) : null
```

`firstAgentBlockId` (`hub/ui/src/components/agents/AgentTimeline.tsx:384-389`) is *the first block
that is a work block or carries an `agent_output` entry*. A `status` entry qualifies: it is neither
work nor a message — `RESULT_OUTPUT_KINDS` holds `status` (`agentTimelineModel.ts:9`) — so
`reduceTurnBlocks` gives it its own `entry` block. The `durationLine` is then rendered **inside that
block's fragment**, and the fragment for a success-completion entry is

```tsx
if (isSuccessCompletionEntry(entry)) return null   // :430
```

So when the status row is the turn's first (and only) agent output, the stat line is attached to a
block that draws nothing and disappears with it.

**Measured.** Rendering the real `AgentTimeline` with `run_started` and `run_stopped` five seconds
apart:

| turn's entries | `turn-worked-for` |
|---|---|
| text row, then the `status` row | present — "Worked for 5s" |
| the `status` row alone | **absent** |

A second probe against the shipped model functions confirmed the mechanism rather than inferring it:
`entryCategory(status)` is `result`, `reduceTurnBlocks` yields one `entry` block whose id is the
entry's, `firstAgentBlockId`'s own expression selects it — and a `thinking` row placed ahead of it
takes the slot instead, which is why nothing has shown this. 6 assertions, all passing.

**Severity C, and the reason is reachability, not harm.** Today the only turns shaped like this are
runs that emitted a `result` line and no assistant text at all — real but uncommon. A stopped or
failed run cannot hit it, because it has no `status` row in the first place (F190 phase 0: nine
output rows for the agent, three `status`, none of them the stopped run's).

**It stops being uncommon if `a-turn-says-how-it-ended` ships without task 4.5a.** That change's
task 2.2 persists a terminal `status` row for *every* run the finalize block reaches, and its task
4.5 gives a run whose spawn failed a duration for the first time — so exactly the turns that gain a
duration are the turns whose only agent output is the new row. The two halves of that change meet on
this case and no round through 3 named it. Task 4.5a is now written for it, with the fix stated as a
placement change (hoist the line out of the per-block fragment, or exclude success-completion
entries from `firstAgentBlockId`) and **not** as making the row visible.

Not proposed as standalone work: the change that makes it matter is already in flight and now
carries the task.

**Verified and narrowed by round RB, 2026-09-02.** RB reproduced the defect independently, adding
two cases RA did not run: the `status` row with **no operator message at all** (still no stat line),
and a `thinking` row placed ahead of it (stat line present — the negative control). 4 assertions,
all passing, on unmodified code.

**One of the two fixes offered above does not work, and RB found that by running them.** Excluding
success-completion entries from `firstAgentBlockId` leaves it `undefined` in exactly this case — the
`status` row is the turn's *only* `agent_output` block, so there is no later block to inherit the
slot — and `blockId === firstAgentBlockId` is then false for every block, leaving the stat line
absent. Measured: 2 of 6 assertions fail under it, and they are the two this fix exists to make
pass. The placement fix does work: have the success-completion branch return
`<Fragment key={entry.id}>{durationLine}</Fragment>` instead of `null`. Measured: 6 of 6 pass, the
status row itself stays unrendered, exactly one stat line is emitted when a text row precedes it,
and the 86 existing assertions in `workingIndicator`, `agentTimeline`, `agentTimelineModel` and
`agentHandoff` stay green. Task 4.5a now names that fix and withdraws the other.

**FIXED IN CODE 2026-09-03 (night iteration 6, task 4.5a); NOT YET DRIVEN.** The placement fix is
in `AgentTimeline.tsx`'s success-completion branch, and three assertions in
`timelineRunFacts.test.tsx` cover it — the stat line appears, the row itself still draws no card,
and exactly one stat line is emitted when a text row precedes the status row. All three are
mutation-checked: drawing the card from that branch kills the second, emitting the stat line
without the `firstAgentBlockId` gate kills the third, and reverting to `null` kills the first.

**RB's rejection of the other fix was re-measured against a different test set and stands.** The
`firstAgentBlockId` exclusion was implemented and run against these three assertions: 1 of 3 fails,
and it is *the one this finding exists to make pass* — the same verdict RB reached with 2 of their
6. This finding stays open until phase 6 watches the line appear against a running Hub; the
committed UI bundle is not rebuilt yet, so a live Hub still serves the old client.

---

## F270 (C) — signal 1 has never fired for a Codex run, so a *cleanly completed* Codex turn still shows the 2026-08-18 lingering counter

**Status:** fixed `3b1b8f0` (2026-09-03, `a-turn-says-how-it-ended` task 2.2), which is
the side effect this entry predicted rather than a repair aimed at it. Verified 2026-09-09: the
finalize block now writes the terminal `kind="status"` / `phase="completed"` row through
`record_agent_output` (`hub/hub/api/v1/agent_trigger.py:2353-2363`) for every run it reaches, on
either runner, so the client's first settled signal is no longer Claude-only. [classified 2026-09-09, D-3]

Found by round RB of `a-turn-says-how-it-ended` (2026-09-02) while re-deriving round RA's argument
against the code. RA identified the producer of `lastRunSettled`'s first signal correctly and then
generalised it to the product; it is Claude-only.

**The producer half, read.** `status_event("completed")` occurs **exactly once in the whole Hub**,
at `hub/hub/runner_parsing.py:356`, inside `parse_claude_line`. That parser is selected only for
`runner in ("claude", "claude_proxy", "native")` (`hub/hub/api/v1/agent_trigger.py:1867`); everything
else falls through to `parse_codex_line`, whose only `status_event` is `"plan"`
(`runner_parsing.py:574`). The Codex app-server transport is no different — its only `status_event`
is `"plan"` too (`hub/hub/codex_appserver.py:544`). `SUPPORTED_RUNNERS` is
`("claude", "claude_proxy", "native", "codex")` (`runner_commands.py:52`), so this is one of the two
wired runners, not a hypothetical. The finalize block's terminal status line is broadcast and never
persisted, for both runners alike. **So no Codex run of either transport has ever had a persisted
`kind="status"`/`phase="completed"` row — not a stopped one, and not one that finished cleanly.**

**The consequence half, measured.** `lastRunSettled` (`AgentTimeline.tsx:114-117`) is
`lastTurn.entries.some(isSuccessCompletionEntry) || TERMINAL_STATUSES.has(statusByRun[lastRunId])`.
Signal 2 costs a `useAgentTimeline` round trip; signal 1 is what closes that tail. Rendering the real
`AgentTimeline` with a completed turn and only `run_started` in `timelineEvents` — the pre-refetch
window:

| turn's entries (runner) | `timeline-working-indicator` |
|---|---|
| answer + the Claude parser's `phase="completed"` row | absent — settled at once |
| answer alone (**every Codex turn**) | **present** — counter running under a finished answer |
| answer + codex's own `phase="plan"` status row | **present** — the predicate is not satisfied |

3 assertions, all passing, on unmodified code. Probe deleted before commit — the day window does not
implement.

So the operator's 2026-08-18 complaint ("It still linger a little bit") was fixed for Claude and is
**still live for Codex on every turn, including a clean one**. Phase 0 of
`a-turn-says-how-it-ended` measured the single-run completed case releasing cleanly (task 0.3) — on
a Claude runner. There is no Codex baseline, and the design's *Round RA* section stated the Claude
result as if there were.

**Severity C, and the reason is exposure, not mechanism.** The mechanism is certain and the UI half
is measured; what is not driven is a live Codex turn, because Codex driving was cancelled on
2026-08-29 as undrivable on this machine. The visible symptom is a counter that lingers for one
timeline refetch rather than a wrong outcome, and it self-corrects.

Not proposed as standalone work: `a-turn-says-how-it-ended` task 2.2 fixes it as a side effect by
persisting the row for every run the finalize block reaches, on both runners. Tasks 2.1b and 4.7's
Codex bullet now assert it, so it cannot ship claiming a Claude-only result covers both.

---

## F271 (A) — a failed instructions load renders an empty editor with Save enabled, and one click destroys the project's instructions

**Status:** fixed `c7e615c` (the component), shipped in the served bundle by `676eba4`, driven in a
browser by `f664f45`. Change `openspec/changes/archive/2026-09-06-an-unread-editor-cannot-overwrite`.

Both destruction paths this section measured are closed, and they were closed on different evidence,
which is worth separating rather than reporting as one number:

| Path | How it is closed |
|---|---|
| **B1 / B2** — the failed load (dropped connection, and a 500) | **By measurement.** The harness's expectations were inverted to the requirement and it observes no editor, **Save gone rather than merely inert**, the failure stated in a `role="alert"` with a Retry beside it, **0 PUTs**, and the stored row byte-identical. |
| **D** — the read still in flight, the wider door of the two | **By measurement, against an expectation written before the fix existed.** Column D passes *unmodified*: the three assertions that failed on 2026-09-06 pre-fix now pass with their text untouched. |
| **C** — the cross-project variant | **By measurement, since 2026-09-07 — and the ground this row used to give was wrong.** It said *"this page offers no in-page project switcher (`'Switch project' controls on screen: 0`)"*. There is one; the harness asked for role `button` and it is a `<select>`, so that 0 measured the instrument (**F296**). Driven properly by `scripts/drive/t_d1_0907_cross_project_switch.py`, **20 passed / 0 failed**, mutation-checked at 17/3 against the pre-fix bundle. What actually closes the column is **navigation**: `App.tsx:602` sends the switch to `projectDestination(id)`, whose default tab is `'overview'`, so InstructionsPage unmounts — measured, `?project=B&tab=overview`, no textarea. A change that made the switcher preserve the current tab would put this column back in play. |

The measurement is mutation-checked, which is what makes it mean anything: the *same* inverted
harness re-run against the pre-change bundle (`git checkout 676eba4^ -- hub/hub/static/ui`, served
JS confirmed back to `index-BXA4wQsi.js` on the wire) gives **19 passed / 12 failed** against
**31 passed / 0 failed** post-fix, with the baseline column's two checks passing *identically* in
both runs — so the 12 are this fix and nothing else. Pre-fix the drive's own typing reached the
stored row (`'TYPED BY THE DRIVE'`), proving the instrument can see a write when there is one.

Retry was additionally driven by hand with no route interception at all
(`scripts/drive/t_d4_retry_by_hand.py`, 15 passed / 0 failed): a real uvicorn stopped and restarted
under a live browser, asserted **not** to heal on its own, then healed by one click on Retry.

**The operator question this section raised is still open and was deliberately not answered:** whether
a PUT that blanks non-empty stored content should confirm first. `hub/hub/api/v1/instructions.py` was
left alone — the empty string stays a legitimate value, and the client is now the only place the
distinction lives.

Found by driving, 2026-09-02 (day window, D-4). N-11 read this statically last night and
**deliberately filed no finding number**, on the correct ground that a static read cannot say what
the page renders. It reproduces, and it is worse than the static read claimed: the destruction takes
**one click on an unmodified page**, and nothing on screen says a load failed.

Driven by `scripts/drive/t_d4_instructions_failed_load.py` against the **served bundle** on `:8011`
— measured as this repo's committed bundle (`assets/index-x3nWU-L2.js`, stamp
`built_at 2026-09-01T23:40:44Z` from `5f47dd5`) with **no diff under `hub/ui/src` since that
commit**, so the source read below is the code that ran. 19 assertions, all passing. Two throwaway
fixture projects, both deleted.

**What an operator does.** Open a project's Instructions page while the Hub is restarting, or behind
any transport failure. React Query is configured `retry: 1` (`hub/ui/src/main.tsx:12`), so the GET
is attempted twice, ~6 s, and then the query settles into `error`.

**What the page then shows** — the same for a dropped connection and for a 500, measured
separately:

| | baseline (load succeeds) | GET aborted | GET answers 500 |
|---|---|---|---|
| skeleton | absent | absent | absent |
| textarea | present, **holds the stored text** | present, **empty** | present, **empty** |
| Save | enabled | **enabled** | **enabled** |
| `role="alert"` | none | **none** | **none** |

Nothing anywhere in the page's text says *error*, *failed*, *could not*, *unable* or *retry* — the
page is indistinguishable from a project that has no instructions set.

**The one click, measured end to end.** With the Hub reachable again and **nothing typed**:

```
stored before Save: 'ALPHA PROJECT RULES\n\n- Never force-push.\n- Every PR needs a test.\n'
stored after  Save: ''
```

`InstructionsPage.tsx:14-18` seeds the editor with `useEffect(() => { if (data) setContent(data.content) }, [data])`,
so a failed load never leaves `useState('')`. `isLoading` is false in the error state, so the
skeleton branch is not taken. `disabled` on Save is `saveMutation.isPending` alone — the query's
error state is not consulted. The PUT then sends `{"content": ""}`, and
`hub/hub/api/v1/instructions.py` accepts the empty string **deliberately**: its `InstructionsUpdate`
docstring records that the field was named precisely so no body could blank the row by accident. The
server-side guard exists and is intact; the client walks straight past it with a well-formed body.
There is no history, no undo and no confirmation — `put_instructions` overwrites `row.content` in
place.

**Why severity A and not B.** The empty editor is a misleading surface, but the operator *acts* on
it, and the act is irreversible. Project instructions are not decoration: they are prepended to
every agent's canonical turn context (`agents.py:1486-1490`, `## Project Instructions`) and to every
charter served by `get_charter_content` (`agents.py:2072-2078`). Blanking them silently removes the
operator's project-wide rules from every subsequent turn, with no error at the moment of loss and no
signal afterwards — the agents simply stop following rules the operator can still see themselves
having written.

**Not a family.** `if (data)` seeding an editor occurs at exactly one site in
`hub/ui/src/components` — this one. `ChartersPage` seeds its editor from an already-loaded list
(`charters = []` on failure), so a failed load leaves nothing editable rather than something
destructive.

**Not driven at the time — driven 2026-09-07, see F296; the paragraph below is left as written so the wrong ground stays visible. The cross-project variant.** The sharper shape — component stays mounted, selected
project changes, the *new* project's load fails, and `content` still holds the previous project's
text, so Save writes A's instructions into B — could not be reached from this page: the
environment tab renders no `ProjectHeader`, so there are **zero** "Switch project" controls on
screen (measured). It is unfalsified in either direction and is recorded, not asserted.

**Fix shape, for whoever specs it** — not implemented here; the day window does not implement. The
cheapest correct change is to consult the query's error state in both places the component already
consults `isLoading`: render the failure instead of an empty editor, and gate Save on it. Whether
the page should also refuse a PUT that would replace non-empty stored content with `""` without a
confirmation is a **product decision for the operator**, not a bug fix — the empty string is a
legitimate value the route accepts on purpose.

### Evidence added 2026-09-03 (D-6) — page or pattern? Five sites, and the answer is *page*

This is **evidence under F271, not a proposal and not a new finding.** The direction for the day
window was to establish how many sites share F271's shape, so that whoever specs it knows whether
they are repairing a page or a family. Harness: `scripts/drive/d6_seed_writeback_sweep.py`, one
command, no product code touched, no Hub started, no database read. It imports
`d5_reachability_walk.py` and `n11_query_error_surface.py` rather than restating them.

**The shape, written as three linked facts rather than as a page.** `S` a query's data seeds
component state; `W` that state is sent back to the server by a write; `G` nothing stops the write
while the load is failing.

**The count.** Of 163 query call sites, 153 in files reachable from `main.tsx`:

| | |
|---|---|
| sites where **S** holds | 7 |
| of those, **W-LINK** holds (the seeded state is what the write sends) | **5**, across 4 files |
| of those, **unguarded** — F271's shape | **2** |
| guarded | 3 |

The two unguarded are `InstructionsPage.tsx:9` (F271 itself, driven) and
`AgentOutputPanel.tsx:207` (the candidate this ledger already recorded above, still a static read
and still undriven — the drive that would settle it is unchanged). **So F271 is a page, not a
pattern**, and the "Not a family" paragraph above survives with a number behind it.

**Why the count is not simply D-5's rank table re-printed.** D-5 published `rank 1 = 2` from a
weaker test, and the four gaps were measured rather than assumed:

1. **It ranked one bucket.** `rank_sites` was called on `MISREPORT` alone. Of the 153 live sites,
   only **50** were ever tested for the shape; **103** were not.
2. **Its writer set required `useMutation` and a `use`-prefixed `export function`.** That set has
   38 members; the set of `api/` exports that actually reach a write has **58**. The 20 it cannot
   see include every `export async function`, `takeCheckpoint`, `cutOver`, `requestCompact`,
   `releaseConversationTask`, and all seven spec-document writers.
3. **Its writer set was `api/`-only**, so a component-local helper was invisible.
4. **Its rank-1 conjunction was file-level** — "this file seeds from that query" AND "this file
   names any writer" — never joined. D-5 said so itself about `AgentOutputPanel.tsx:207` ("in rank
   1 for the wrong reason"); the `W-LINK` test is that sentence turned into code.

**Four controls, and two of them failed on the first run.** The script asserts that it re-finds
`InstructionsPage` as S+W+G, `AgentOutputPanel.tsx:207` as S+W, and `AccountingPanel` and
`ProjectSettingsPanel` as guarded. It failed the middle two, and both failures were defects in this
script's method rather than in the tree:

- **A write does not have to go through the `api/` client.** `AgentOutputPanel.tsx:657`'s
  `postTrigger` builds a raw `fetch` with `method: 'POST'`, so no helper-name test could see it —
  and `api/projects.ts:168` says in a comment that `useDeleteProject` "bypasses `deleteJson`" for
  the same reason. Three such sites exist outside `api/`. This is a **fifth** gap in D-5's method,
  not on the list above, because D-6 inherited it before the control caught it.
- **The seeded state can reach the write through an alias.** `AccountingPanel` seeds `budgetInput`
  and writes `updateBudget.mutate(value)`, where `value` is `Number(budgetInput)` one line up. A
  literal-name test says the seeded state is never written back, which is false.

A third defect surfaced the same way: slicing a declaration's body to the next declaration
attributed `api/projects.ts`'s non-exported `useProjectPathMutation` (`:47`, `postJson` at `:51`)
to the read-only `useProjects` (`:32`), so a query hook read as a POST writer. Bodies are
brace-balanced now.

**The blind spot, counted rather than described.** 55 live sites bind no name the seed test can
follow — **54 of them are inside `api/`**, one hook calling another rather than a component site,
and the 55th is `AgentOutputPanel.tsx:152`, which binds `isLoading` alone and so has nothing to
seed from. The within-file scope has one real hole: a parent that fetches and hands `data` to a
child that seeds and saves is the same shape with a component boundary through it, and no query
site in the child to find it by. Running the same S and W-LINK tests over destructured **props**
returns 3 hits, and all three are hand-read as noise. Two are `AgentOutputPanel`, already a genuine
site by the query test. The third is `TaskDetailDrawer.tsx:137`, and the first draft of this
paragraph got its *reason* wrong while getting its verdict right — worth recording, because that is
this repository's named failure mode. The draft said the hit was an `onError` callback rather than
a payload; at `:432` it really is a payload (`blocked_reason: reason`, where `reason` is
`blockingReason.trim()` one line up). What makes it benign is something else: the effect at `:162`
is a **reset**, not a seed — it calls `setRefusal(null)` and `setBlockingReason(null)` on
`task?.id` — and `blockingReason` is filled by the operator typing into the block prompt, never
from server content. So no failed load can put stale stored content into that write. **The `S` test
cannot tell a reset from a seed**, which is a real limitation of the sweep and not of the tree. (The
`refusal` hit at `:301` is thinner still: the word appears in a *comment* inside the call's argument
span, because the argument text is taken verbatim.)

### The result that was not the question: F271 and F197 are one mechanism seen from two sides

**Every guarded site is guarded by an early return that N-11 had already classified as F197** —
`AccountingPanel.tsx:34` and `ProjectSettingsPanel.tsx:75`, which are `n11_query_error_surface.py`'s
lines 101 and 139 verbatim ("the skeleton is terminal — F197's shape exactly", "this site *is*
F197"). There is no third arrangement anywhere in the tree: a site that can write a failed load
back is either **F271** (no guard) or **F197** (a terminal skeleton).

So repairing F197 site by site — rendering the form instead of the terminal skeleton — **converts
each repaired site into an F271** unless the write is gated in the same change. Whoever specs
either finding needs the other in scope. That is a claim about two open findings and it is stated
here rather than acted on; the day window does not implement.

**The separating fact is the seeded state's initial value, not the guard.**
`ProjectSettingsPanel`'s `form` is `useState<ProjectSettings | null>(null)` — a sentinel a render
can test, which is why that file is defended twice over. `InstructionsPage`'s `content` starts
`''`, `AccountingPanel`'s `budgetInput` starts `''`, and `AgentOutputPanel`'s `pendingOverrides`
starts `{}`: all three indistinguishable from a legitimately empty stored value, and all three
therefore dependent on a guard alone.

**Not answered here, deliberately.** Whether the page should refuse a PUT that would blank non-empty
stored content is the operator's decision and is on the 2026-09-03 review page. Nothing in this
evidence bears on it either way.

---

### F271's second destruction path, reproduced 2026-09-06 (night window, task 4.1b) — the read only has to be *slow*

**Why this column had to be run before the fix, not after.** `t_d4_instructions_failed_load.py`'s
A/B/C columns all make the instructions GET *fail*. Column **D**, added tonight, makes it merely
**not finish** — the route is held open and never resolved, so the page sits on its loading
skeleton. That is not a contrived state: it is what every visit looks like for the length of the
round trip. Once `hub/hub/static/ui` holds the fixed page this column stops being a reproduction and
silently becomes a pass, so it was run first, against the **currently served pre-change bundle**.

**Instrument.** Fresh uvicorn from source on `8011` started from `hub/`
(`py -3.11 -m uvicorn hub.main:app`, never `agentweave --port`), fresh throwaway database
`…/Temp/aw0906n1/n1.db`, two throwaway fixture projects created and deleted by the harness. Nothing
on 8000; 8010 was not addressed. Staleness checked both before and after:
`find hub/hub src -name '*.py' -newermt <process start>` returned empty. The served bundle is
`ui-build-stamp.json` at `c063e28`, which is one commit stale — and the one commit
(`5a5e026`) touches `lib/eventSummary.ts` and its test only, so **the instructions page in the
served bundle is the pre-change component**, checked rather than assumed.

**What the browser showed.** 24 passed / 3 failed, and the three failures are the reproduction:

| Observation | Value |
|---|---|
| page state while the GET is in flight | `skeleton: true`, `textarea: false` — the editor has never held the stored text |
| Save | `save_visible: true`, `save_disabled: false` — **live, over a skeleton** |
| one click on it | **1 PUT issued** |
| stored content before / after | `'ALPHA PROJECT RULES\n\n- Never force-push.\n- Every PR needs a test.\n'` → `''` |

So the destruction does not need a dropped connection or a 500. It needs the operator to click Save
during the load, and the window in which that is possible opens on **every** visit to the page. B1's
column is the same blanking reached through a failure; D is the same blanking reached through
latency, and it is the wider door of the two.

**Why the three-branch render of task 1.2 does not close it by itself**, confirmed here rather than
only argued: `skeleton: true` and `save_visible: true` were observed *simultaneously*. Save is
`SettingsSection`'s `actions` prop, rendered in the heading — a sibling of the `{children}` the
skeleton lives inside — so gating the children leaves the button exactly where it is. Task 1.4 is
the task that closes this column.

**Column C is still not driven**, unchanged from 2026-09-02: `'Switch project' controls on screen: 0`
from this page, so the cross-project variant remains recorded rather than asserted. The change's
task 2.6 covers that shape at the unit level.
*(Superseded 2026-09-07 — that `0` is the harness asking for the wrong ARIA role, and column C is
now driven at 20/0. See **F296**. Left standing here because the wrong reading is the finding.)*

**One piece of instrument noise, so nobody chases it.** Playwright prints an
`asyncio.exceptions.CancelledError` traceback on stderr when the parked route is torn down at page
close. It is the held-open request being cancelled, not a failure — the PASS/FAIL lines are the
result. Noted in the harness at the handler.

**Status of F271 after *that* iteration (n1-repro, 2026-09-06): still open.** Nothing was fixed
there; that was the pre-fix measurement the fix would be checked against. It has since been checked
against it and passes unmodified — see the `**Status:**` block at the head of this section.

---

## F272 (C, was B) — the terminal status row phase 2 exists to persist is silently lost ~10% of the time, because `record_agent_output` cannot re-read the row it just committed

**Status:** fixed `d9ad1e0` (2026-09-04, where the same shared connection was filed as F285), the file-backed candidate the settled section below left standing, taken with `assert_engine_is_disposable` re-expressed as *inside the directory this process created* (`conftest.py:614`); re-measured 2026-09-15 on `48eede3` with this entry's own load arm, four concurrent processes of `test_a_turn_says_how_it_ended.py` for six rounds, **0 / 24** failed against the in-memory arm's 5 / 24; harness only, and the product residual stays open as F273.

Read with that line: `890cf40` (2026-09-05) later removed the `db.refresh(row)` this entry calls the only detector of a lost write, after measuring that it could not mask another defect. So the traceback above can no longer appear at all. A lost row would now show only as the test's own read-back of `[]`, and all 24 re-measured runs read the row back.

> **Settled 2026-09-03 (night window, iteration 8): this is the test harness, not the product.** The heading above is the shape as it was first seen and is kept for searchability; read the **SETTLED** section at the end of this entry before acting on anything above it. Severity dropped **B → C** on the measurement recorded there.

Found not by driving but by **this change's own test failing** — `test_a_turn_says_how_it_ended.py::test_a_stopped_run_persists_its_terminal_status_line`, in the whole-Hub-suite run of 2026-09-03 (night window, iteration 7). Filed now rather than dismissed as a flake because **the traceback was finally captured**, and it lands inside product code.

**Reproduction rate, measured.** 2 failures in **20** consecutive runs of that test **on its own** (`-k a_stopped_run_persists`), and 1 in 6 runs of the whole file. It is not cross-test interference: it fails alone. Two earlier sightings tonight were lost because the run was piped to `tail`, which is how it went three iterations unattributed.

**What happens.** `output_recording.py:92-94` is `db.add(row)` → `await db.commit()` → `await db.refresh(row)`. The refresh issues a primary-key SELECT and finds **no row**, so SQLAlchemy raises:

```
sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<AgentOutput at 0x...>'
  hub/hub/api/v1/agent_trigger.py:2146 in _execute_run  -> await record_agent_output(...)
  hub/hub/output_recording.py:94       in record_agent_output -> await db.refresh(row)
```

The exception escapes into `_execute_run`'s catch-all (`agent_trigger.py:2215`), which logs *"Unhandled error in run ... for 'phase2-stopped'"* and moves on. The run ends. **The row is not there** — the test reads the output route back and gets `[]`.

**Why it matters more than a flake.** That row *is* design D6: it is the only settled signal a stopped, failed or binding-conflicted run has ever had on either runner, the only one a Codex run has for any outcome, and the only carrier of the exit code once the SSE stream is gone. When this fires, the run is exactly the F190 shape again — a turn that ended with nothing saying so — and **nothing surfaces it to the operator**, because the failure is a log line inside a background task.

**Introduced by phase 2** of `a-turn-says-how-it-ended` (iteration 3, commit `3b1b8f0`): before it, the finalize block was a bare `sse_manager.broadcast` with no DB write and no such failure path. Iteration 3's whole-suite run reported 3848 passed — it got lucky.

**Mechanism: NOT established. Stated as hypothesis, deliberately.**

- The Hub suite runs `sqlite+aiosqlite:///:memory:` (`conftest.py:19`) with **no explicit `poolclass`** (`db/engine.py:34-38`), so the aiosqlite dialect uses a single shared connection for an in-memory URL. Several concurrent sessions — the stop request's, the background run's, the reader loop's — therefore interleave BEGIN/COMMIT/ROLLBACK on **one** DBAPI connection, which is a known way for one session's committed insert to be discarded by another's rollback. If that is the whole story, this is **test-harness-only** and production (a file or Postgres URL, one connection per session) is unaffected.
- Against that: it is *specifically* the stopped-run path that fails, and the stop path is the one that runs a request handler's session concurrently with the run's own. A real ordering defect there would be visible in production too.

**What the next window should do**, in this order, because the second is cheap and settles it:

1. Do **not** "fix" it by deleting the `db.refresh(row)`. The refresh is the messenger — the row is genuinely absent, and removing the read would convert a logged failure into a silent one. Only `row.timestamp` needs it, for the broadcast payload.
2. Re-run the same test against a **file-backed** SQLite URL with a normal pool. If it stops failing, the mechanism is the shared in-memory connection and the fix is the harness; if it still fails, it is a product race on the stop path and belongs in phase 2.
3. Either way, `_execute_run`'s catch-all swallowing a failed *terminal-status write* is its own weakness: the one write whose whole purpose is to survive the process should not be the one whose failure is invisible.

**Severity B, not A**, on one ground only: it has been observed **exclusively under the in-memory test harness**, never in a drive. If step 2 shows it reproduces on a real database, it is an A — it defeats the guarantee this entire change was approved to deliver.

### SETTLED 2026-09-03 (night window, iteration 8) — the harness, not the product

Step 2 of the list above was run, and then three more experiments that the list did not anticipate.
**The conclusion is that no production configuration can produce this**, so F272 drops to **C** and
the repair belongs in `hub/tests/`, not in `hub/hub/`. What follows is the measurement, in
increasing order of decisiveness; the last one also settles **F266**, which is the same defect seen
through a different test.

**1. The two configurations do not get the same connection pool.** `db/engine.py:34-38` passes no
`poolclass`, so SQLAlchemy's aiosqlite dialect picks one from the URL. Measured by constructing the
engine and reading `engine.pool.__class__.__name__`:

| URL | pool SQLAlchemy picks |
|---|---|
| `sqlite+aiosqlite:///:memory:` — what `conftest.py:19` sets | **`StaticPool`** — **one** DBAPI connection, shared by every session in the process, for the life of the engine |
| `sqlite+aiosqlite:///<file>` — what a native-mode Hub runs | `AsyncAdaptedQueuePool` — a connection per checked-out session |
| `sqlite+aiosqlite:///file:x?mode=memory&cache=shared&uri=true` | **`StaticPool`** — the dialect detects `mode=memory` too |

**2. The mechanism reproduces deterministically, and its signature is F272's, character for
character.** Two `AsyncSession`s on one engine, no product code involved: A `INSERT`s, B `close()`s
(which emits `ROLLBACK` on whatever connection B holds), A `COMMIT`s. If A and B share a connection,
B's `ROLLBACK` discards A's uncommitted `INSERT` and A's `COMMIT` commits nothing — so the row is
absent and the primary-key re-read raises. **A 2×2 over storage and pool isolates the pool as the
variable:**

| cell | pool | A and B share one DBAPI connection | row survives A's commit | A's `refresh(row)` |
|---|---|---|---|---|
| memory / default | `StaticPool` | **yes** | **no** | **`InvalidRequestError`** |
| memory shared-cache / default | `StaticPool` | **yes** | **no** | **`InvalidRequestError`** |
| **file / FORCED `StaticPool`** | `StaticPool` | **yes** | **no** | **`InvalidRequestError`** |
| file / default | `AsyncAdaptedQueuePool` | no | yes | ok |
| memory shared-cache / forced `AsyncAdaptedQueuePool` | `AsyncAdaptedQueuePool` | no | yes | ok |

Read the third row against the fourth: **same storage, opposite outcome.** It is not "in-memory
SQLite is weird"; it is *one shared connection*, which is a property of the pool alone. And there is
no configuration the product ships in that has it — a native-mode Hub is a file URL, Docker/Postgres
is `AsyncAdaptedQueuePool`, and only `conftest.py` asks for `:memory:`.

**3. The flake rate, matched-load, in-memory versus file-backed.** The single-run rate quoted in the
original entry is real but too low to compare against anything: re-measured at the start of this
iteration it was **0 failures in 20** consecutive single-test runs, against the **2 in 20** measured
the night before — the race is load-dependent, so an unloaded machine has almost no power to see it.
Running **four pytest processes of the whole file concurrently** raises it into a usable range. Six
alternating rounds, four processes each, `-p no:randomly`, every run captured to its own file with
`--tb=long`:

| arm | URL | failures |
|---|---|---|
| in-memory (today's harness) | `sqlite+aiosqlite:///:memory:` | **5 / 24** |
| file-backed | `sqlite+aiosqlite:///<temp>.db` | **0 / 24** |

Every one of the five is the identical traceback — `output_recording.py:94` → `db.refresh(row)` →
`InvalidRequestError: Could not refresh instance '<AgentOutput ...>'`, and the test then reads `[]`
back off the route. At the observed in-memory rate, seeing zero in 24 file-backed runs has
probability ≈ **0.004**, so the arms are separated at better than 1-in-200 by the statistics alone —
and experiment 2 is not statistical at all.

**A correction to what the original entry says, which also corrects F266.** Both entries describe
the write as having *already committed* when the refresh raises. **It has not.** The `COMMIT`
executes and commits an empty transaction, because the `INSERT` it was going to commit was already
rolled back on the shared connection. That is why the route reads back `[]`. `db.refresh(row)` is
therefore not an over-strict re-read of a row that is fine — it is the **only** thing in the process
that notices the write was lost, which is the standing reason not to delete it.

**What this does not excuse.** Item 3 of the original list stands unchanged and is now the only
*product* content in this finding: `_execute_run`'s catch-all (`agent_trigger.py:2215`) turns a
failed **terminal-status write** into a log line inside a background task. The `already_terminal`
branch is right about not relabelling the run — but the consequence is that the one write whose
entire purpose is to outlive the process is also the one whose failure nothing surfaces. Filed
separately as **F273** so it is not lost when this entry is read as "harness, closed".

**The repair, and why it is not applied here.** Two candidates, both measured:

- **File-backed temp database.** Works (0/24 above), but `assert_engine_is_disposable`
  (`conftest.py:47-64`) exists to refuse to `drop_all` anything that is not `:memory:`, and it was
  written after a real destroyed database. Re-expressing that guard as "a temp file this suite
  created" is a safety-critical edit, not a one-liner.
- **In-memory shared-cache URL with an explicit `poolclass=AsyncAdaptedQueuePool`** —
  `sqlite+aiosqlite:///file:<name>?mode=memory&cache=shared&uri=true`. Row 5 of the 2×2 shows it
  gives per-session connections while staying in memory, so it keeps the suite's speed *and* the
  `mode=memory` substring the guard can key on. **Refuted at suite scale, and this is why the
  mechanism probe is not sufficient on its own:** under the same 4-way load it failed **8 / 8**,
  every run with `OperationalError: database table is locked: sqlite_master` — the `app` fixture's
  `drop_all`/`create_all` collides with the other pooled connections that are now holding the shared
  cache open. The pool was the right fix for the *interleave*; it is the wrong fix for the *suite*,
  which drops every table before every test.

So the only candidate still standing is the file-backed one, and taking it means re-expressing a
guard whose stated purpose is to prevent destroying operator data. Queued as its own item rather
than decided inside this one. Two further options are dead ends and were measured rather than
argued: forcing `StaticPool` onto a file URL made the 14-test file take **259s** against 4s (one
connection to a file database serialises every transaction behind an fsync), and the shared-cache
URL *without* an explicit pool is not a change at all — SQLAlchemy still picks `StaticPool` for it
(row 2 of the 2x2).


## F273 (B) — the one write whose purpose is to outlive the process is the one whose failure nothing surfaces
**Status:** **closed, no product change** (DECIDED `F291-F273-run-facts`, B2 D11): the premise is obsolete, the run's row and its facts map carry status and exit code whatever the status-line write does; pinned by `an-undelivered-message-says-how-its-last-attempt-ended` task 1.8 (archived `26b98cb`, 2026-09-29). Ledger closed 2026-10-12 (night iteration 24): `test_a_turn_says_how_it_ended.py` passes, incl. `test_a_status_line_that_cannot_be_written_leaves_a_lock_the_outcome_intact`.

Split out of **F272** on 2026-09-03 (night window, iteration 8), because F272 itself turned out to be a test-harness artefact and this part of it is not. Nothing here has been observed in a drive; it is read from the code, and this entry says so rather than claiming a sighting.

`_execute_run` writes the run's terminal status line at `agent_trigger.py:2145-2156` — design **D6**, the only settled signal a stopped, failed or binding-conflicted run has on either runner, the only one a Codex run has for any outcome, and the only carrier of the exit code once the SSE stream has ended. If that `record_agent_output` call raises for any reason at all, the exception unwinds into the catch-all at `agent_trigger.py:2215`, which:

1. logs `"Unhandled error in run %s for %r"`, and
2. re-reads the `Run` row, finds it is **already terminal** (a stopped run was marked `stopped` before this line), sets `already_terminal = True`, and deliberately does **not** relabel it.

Step 2 is correct and its inline comment argues for it well — relabelling a run that already ended cleanly because some downstream bookkeeping failed is the worse bug. But the two together mean the outcome is: **the run ends, the operator sees a run that ended, and the row that was supposed to say *how* it ended is silently absent.** The only trace is a log line inside a background task, which is precisely the surface F190 was filed about.

**Why it is not merely theoretical.** The harness proved the failure path is reachable — under `StaticPool` it fired on 5 of 24 runs and produced exactly this outcome (`InvalidRequestError` out of `db.refresh`, run ends, output route returns `[]`). The *cause* there is harness-only, but the *handling* is product code and would behave identically for any real cause: a disk-full sqlite, a Postgres connection dropped between the commit and the refresh, a migration holding a lock.

**Severity B, not A.** It is a wrong/misleading surface that requires an independent failure to reach; it is not something an operator will act on today.

**Not proposed** — the fix shape is a design question (does a failed terminal-status write get retried, get its own error row, get surfaced as a run error, or get an operator-visible warning?), and this window does not write proposals. Related: **F272** (settled, harness), **F266** (settled, harness), **F190** (the general shape).

---

# `a-turn-says-how-it-ended` phase 6 — the built change, driven 2026-09-03

Tasks 6.1–6.5, against a Hub on **8011** started **02:56:24** from this branch's source
(`py -3.11 -m uvicorn hub.main:app` from `hub/`, beta profile database). Staleness was **measured,
not assumed**: the newest `.py` under `hub/hub` or `src` was `hub/hub/db/engine.py` at 02:49:37,
older than the process. Fixture project `proj-9e6825cdd64c` (`aturn-p6-0903`), created for this
drive and deleted at the end. Every turn bound `claude-haiku-4-5-20251001`.

**Harnesses added** — `scripts/drive/aturn_model.py`, `scripts/drive/setup_aturn_p6.py`,
`scripts/drive/t_aturn_p6.py`. `aturn_model.py` is the successor to `f190_model.py` and both are
kept: `f190_model.py` transcribes the UI as it stood at phase 0, and a transcription edited to match
the new code can no longer speak for the old one — phase 7 needs both baselines.

## F274 (A) - a turn's outcome is erased by work in the agent's *other* conversations

**Status:** **fixed** `272adce` (server) + `503a6ff` (client), driven 2026-09-09, by
`openspec/changes/2026-09-05-the-conversation-carries-its-own-run-facts`. The run facts now ride on
the chat response, which is bounded by the same entries the client renders, so a turn's terminal
label and its "Worked for Ns" no longer depend on an agent-scoped fifty-event window. **Both halves
of phase 0's reproduction were re-run in the browser on the same rows and both inverted** - see
*Phase 6* at the end of this entry. Filed 2026-09-03 by the day window's drive. This is **F190's original
symptom**, live, against the fix that closed F190 - reached by a route none of the three rounds
asked about.

**One correction to the analysis below, made by round 1 against the code.** The paragraph beginning
*"One defect or a design gap"* says the route is not in breach and that no requirement covers the
case. The first half is right and the second is not: *A run's terminal outcome is visible*
(`openspec/specs/agent-stream-events/spec.md:299`) is stated over **the conversation**, requires an
outcome for every run that ended, and permits none only for a run whose row genuinely cannot be
found. These runs have rows, so that requirement **is** breached. What misled the reading is the
requirement's own next sentence, which sends the reader to *The run facts cover every run the events
name* - a rule quantified over the runs a returned event names, which cannot forbid omitting a run
no returned event names. The proposal fixes the cross-reference as part of the change.

`AgentTimeline` reads a turn's terminal label and its "Worked for Ns" line out of the same map:
`runs[turn.runId]?.status` (`hub/ui/src/components/agents/AgentTimeline.tsx:237`) and
`runDurationSeconds(runs[turn.runId])` (`:280`). The map is `AgentTimeline.runs` from
`GET /projects/{p}/agents/{a}/timeline`, which sorts its merged events newest-first and truncates to
fifty - `hub/hub/api/v1/agents.py:802-803` - and then builds the map from the ids the **surviving
fifty** name (`:818-836`).

The turns are not bounded by that. They come from the conversation-scoped chat history
(`AgentOutputPanel.tsx:350`, `useAgentChatHistory(agent.name, currentConversationId)`), and the
timeline's fifty events are **agent-scoped**: every conversation that agent has ever had competes
for the same fifty slots. So an operator reading one conversation loses its outcomes as soon as the
agent does enough work *somewhere else*.

Measured, in this order, on one agent:

```
09:07  trigger a long turn in conv-f7870507f5c9, stop it after 6s
       GET .../agents/p6driver0903d1/timeline
         events=6   runs=1
         run-d8b98481b31b  status=stopped  exit=2
           started=2026-09-03T08:07:57.964994Z  ended=2026-09-03T08:08:04.178079Z
       browser, served bundle, that conversation:
         "Worked for 6s"
         "Turn stopped - 09:08"          <- correct, and this is what phase 6/7 verified
```

Then four ordinary triggers on the **same agent, in four other conversations** - nothing touching
the conversation above:

```
       GET .../agents/p6driver0903d1/timeline
         events=50 (the cap)   runs=10
         'run-d8b98481b31b' in runs  ->  False
       browser, the SAME conversation, reloaded:
         turn boundaries          1
         terminal labels          {'Turn failed': 0, 'Turn stopped': 0, 'Turn interrupted': 0}
         stat lines               0
```

The screenshot is one operator message on an empty page. Both halves of the change's deliverable are
gone at once - the label *and* the duration - which is precisely the sentence the proposal opens
with: *"A turn killed mid-sentence is indistinguishable from a turn that simply had nothing to
say."*

Reproduce:

```bash
AW_HUB=http://127.0.0.1:8011 AW_PROJECT=<pid> py -3.11 scripts/drive/setup_aturn_p6.py <dir>
AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_aturn_runs.py stop
AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_aturn_browser.py p6driver0903d1 "Turn stopped"
#   -> RESULT expected='Turn stopped' present=True
PATCH /projects/<pid>/agents/p6driver0903d1  {"runner_id": "<the bad-flag runner>"}
AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_aturn_window.py p6driver0903d1 3   # + one more
AW_HUB=... AW_PROJECT=... py -3.11 scripts/drive/d1_aturn_conv_browser.py \
        p6driver0903d1 "history of the bicycle"
#   -> terminal labels: {'Turn failed': 0, 'Turn stopped': 0, 'Turn interrupted': 0}
#      stat lines: 0
```

The rebind is a convenience, not part of the mechanism: it makes the four filler turns cost nothing.
Four ordinary Haiku turns reach the same cap - the eviction is driven by event count, not by
outcome.

**The same thing happens inside one conversation**, without any second conversation, once it holds
enough turns. `p6fail0903d1`, four triggers into `conv-f55ea58a6768`:

```
    timeline: events=50 (cap 50)   runs_in_map=10
    chat:     distinct run ids across turns on screen = 12
    turns whose run is NOT in the map = 2   ['run-d287dc866146', 'run-8039a5a50a5e']
  browser: turn boundaries 12 - terminal-label occurrences 10 - stat lines 10
```

Twelve turns, ten outcomes. The two oldest read as turns that ended with nothing to say.

**One defect or a design gap.** A design gap, and a specific one worth stating exactly, because the
route is **not** in breach. `openspec/specs/agent-stream-events/spec.md:363-366` says in as many
words: *"WHEN the agent has runs whose events fall entirely outside the returned event window THEN
the map contains no entries for them."* The route does that. `The run facts cover every run the
events name` (`:368`) is satisfied - every one of the ten is present. What no requirement says is
that **the events must cover the turns the client renders**, and the two are drawn by different
queries with different scopes and different bounds: fifty events across all conversations on one
side, a conversation's history on the other.

Rounds 1, 2 and 3 all argued about the run query - round 2 gave it a size bound, round 3 correctly
replaced that with a lookup by id, and `design.md:323-335` reasons carefully about
`reconcile_interrupted_runs` skewing recency. Every step of that is right. The argument is simply
bounded by the event window it inherited, and nobody asked what the client was rendering *outside*
it. Which is the round discipline's own lesson from 2026-08-28 in an unfamiliar shape: not an
argument that is wrong about the right things, but an argument that is right and short.

**Severity A, and why not B.** It is F190's own severity, and the population it hits is not a
corner: it is every turn an operator scrolls back to, which is when they ask "did that stop, or did
it just say nothing?" The degradation is silent - there is no "outcome unavailable", no dimmed
label - and the reload story the change built (`Worked for 6s` must read the same after a refresh)
inverts: refresh long enough after the fact and it reads differently.


### Reproduced 2026-09-09 (night window, iteration 14) — phase 0 of the change, on a clean instance

Phase 0 of `2026-09-05-the-conversation-carries-its-own-run-facts` is a gate: the 2026-09-05 drive
did **not** reproduce this at nine runs across six conversations, because those runs were short and
the cap is on *events*. So the volume was chosen deliberately this time, and counted in events.

Instance: a Hub on **`127.0.0.1:8012`**, its own profile database
(`~/.agentweave/hub/profiles/f274p0/agentweave.db`, created fresh, migrated `0000 → 0102`), started
from `hub/` with `py -3.11 -m uvicorn hub.main:app` at `2026-09-09T05:01:46.485+01:00`. No `.py`
under `hub/hub` or `src/` was newer than that process start (checked, count 0), so the served code
is the checkout. Fixture project `proj-9042770d2ae3` (`f274p0-050237`, `C:\Users\huida\aw-f274p0`),
one runner `claude` / `claude-haiku-4-5-20251001`, one agent `scribe050237`. Every turn below is a
real Haiku turn.

**The headline, cross-conversation (task 0.2).** Conversation A = `conv-16d76ddeb411` (titled
`ZEBRA-A`); one long turn stopped after 8s, `run-c663930f13c2`, `status=stopped exit=2`,
`04:03:19.420Z → 04:03:27.591Z`.

```
before, timeline: events=6  runs=1   A in runs -> True
before, browser (served bundle, that conversation):
   turn boundaries   1
   terminal labels   {'Turn failed': 0, 'Turn stopped': 1, 'Turn interrupted': 0}
   stat lines        ['Worked for 8s']
```

Then **eight ordinary turns, each in its own new conversation on the same agent**, nothing touching
A. An ordinary turn costs **7 timeline events** on this fixture (`run_triggered`,
`queue_entry_queued`, `queue_entry_delivered`, `run_started`, `run_completed`, and two
`context_warning`), so the fifty-event window moves in about seven turns:

```
after filler 2: events=27  runs=4  A in runs -> True
after filler 3: events=34  runs=5  A in runs -> True
after filler 4: events=41  runs=6  A in runs -> True
after filler 5: events=48  runs=7  A in runs -> True
after filler 6: events=50  runs=8  A in runs -> True     <- the cap is reached
after filler 7: events=50  runs=8  A in runs -> False    <- and A falls out of it
after, browser, the SAME conversation, reloaded:
   turn boundaries   1
   terminal labels   {'Turn failed': 0, 'Turn stopped': 0, 'Turn interrupted': 0}
   stat lines        0
```

Screenshots `testbed/scratch/f274p0/shot-0.2-before.png` and `shot-0.2-after.png` (uncommitted).
Both halves vanish together, exactly as on 2026-09-03. **The defect is live on this checkout.**

**The headline, single-conversation (task 0.3) — the half that proves no wider window fixes it.**
Conversation S = `conv-88b2481859f1` (`ZEBRA-S`), ten turns, one conversation, nothing else running:

```
chat     GET /agent/scribe050237/chat/conv-88b2481859f1   entries=50  distinct run ids=10
timeline GET /agents/scribe050237/timeline                events=50   runs=8
runs the chat names and the timeline map does not: 2

browser, that conversation:
   turn boundaries  10
   stat lines       10, of which the two oldest carry no duration at all:
     ['33,170 tokens',
      '33,445 tokens',
      'Worked for 8s · 33,724 tokens',
      'Worked for 7s · 34,000 tokens',  ... seven more, all with a duration]
```

Ten turns on screen, eight in the map, the two oldest presenting with a token count and no
"Worked for Ns" — the same shape as the 2026-09-03 measurement (twelve on screen, ten in the map).
The turns are conversation-scoped and unbounded; the map is agent-scoped and capped at fifty
events; **one conversation on its own overruns the window**, so widening the window buys turns, not
correctness.

**Task 0.4, the live half that was expected to already work — and does.** Conversation R =
`conv-e8f45ba33e67` (`ZEBRAR`), a long turn in flight, browser open on it, nobody touching the page:

```
05:13:49.663  browser attached to conversation R, turn running, no label
05:13:57.502  Hub hard-killed (Stop-Process -Force), so the run row stays `running`
05:14:02.447  new Hub: `Reconciled 1 orphaned run(s) to status=interrupted on Hub start`
05:14:03.982  new Hub answering /health
05:14:11.06   browser, with no reload and no click: 'Turn interrupted' x1, 'Worked for 26s'
```

**8.6 s after the row was written, 7.1 s after the Hub was serving again.** Seconds, not "never",
so design D8's premise holds and this is a no-regression baseline for task 6.3 rather than a defect.
**One confound, recorded rather than glossed:** 2 s before the label appeared, a second turn boundary
appeared — the interrupted run's queue entry was returned and re-delivered as `run-d7db8abcab80` —
so queue traffic the chat hooks *do* listen to was in the same window. This measurement establishes
"seconds", not "the reconnect invalidation is what did it". Task 3.5 still has to ask its own
question.

### The server half, inverted against the same rows — 2026-09-09, night window, iteration 15

Phase 1 (tasks 1.1-1.5) shipped and the phase-0 Hub was brought back on `:8012` against the **same
profile database and the same runs**, so this is a before/after on identical rows rather than on
new ones. Nothing but `agent_chat.py` changed; the timeline route is untouched and still answers
exactly as it did during phase 0.

| | phase 0 (05:0x) | after phase 1 |
|---|---|---|
| conversation A, `run-c663930f13c2` in the **timeline** map | absent (50 events, 8 runs) | **still absent** (50 events, 8 runs) |
| conversation A, that run in the **chat** response | *field did not exist* | **present** — `stopped`, exit 2, 04:03:19.420 → 04:03:27.591 |
| single conversation `conv-88b2481859f1`: distinct runs named / described | 10 / 8 | **10 / 10** |

The 8.17 s between that run's `started_at` and `ended_at` is the "Worked for 8s" phase 0 watched
disappear. **This is the API half only.** The served bundle still reads `timeline?.runs`, so the
screen has not changed yet — section 2 moves the client, and tasks 6.1/6.2 re-run these two
measurements *in the browser*, which is the measurement that closes the finding. Hub `:8012`
stopped again afterwards; `:8000` untouched throughout (PID 10556 before and after) and nothing
was listening on `:8010`.

### Phase 6 - the same rows, in the browser, and the defect is gone (2026-09-09, night window, iteration 17)

Same Hub (`127.0.0.1:8012`), same profile database, same project `proj-9042770d2ae3`, same agent
`scribe050237`, **same conversations and the same run ids phase 0 measured** - deliberately not torn
down, so this is a before/after rather than two unrelated measurements. Zero `.py` under `hub/hub`
or `src/` newer than the process start.

| | phase 0 (05:0x) | phase 6 (06:2x) |
|---|---|---|
| conversation A `conv-16d76ddeb411`, `run-c663930f13c2` in the **timeline** map | absent (50 events, 8 runs) | **still absent** (50 events, 8 runs) |
| conversation A, browser, turn boundaries | 1 | 1 |
| conversation A, browser, terminal labels | `{failed 0, stopped 0, interrupted 0}` | **`{failed 0, stopped 1, interrupted 0}`** |
| conversation A, browser, stat lines | 0 | **`['Worked for 8s']`** |
| single conversation `conv-88b2481859f1`: runs named by chat / present in the timeline map | 10 / 8 | 10 / **6** (the window has moved further) |
| that conversation, browser, turn boundaries | 10 | 10 |
| that conversation, browser, stat lines carrying a duration | **8 of 10** - the two oldest read `'33,170 tokens'`, `'33,445 tokens'` | **10 of 10**, every one `Worked for Ns - N tokens` |

The timeline map is *more* wrong than it was - four of the ten runs are outside it now rather than
two - and the screen is right anyway, which is the point: the client stopped reading that map.
`shot-6.1-after.png`, `shot-6.2.png` (uncommitted, `testbed/scratch/f274p0/`).

**A fixture defect found while re-running 0.2, worth recording.** Phase 0's browser watcher
(`watch_conv.py`) selected a conversation by clicking the first DOM node matching a *text* needle,
and conversations A and R were both opened with the same "history of the bicycle" prompt. Phase 0's
own measurement is sound - R did not exist yet when 0.2 ran - but the first phase-6 attempt silently
measured R instead of A and read `Turn interrupted`/`Worked for 26s`, which would have been recorded
as a pass for the wrong conversation. Phase 6 selects by id instead
(`data-testid="rail-conversation-<id>"`, `AgentTree.tsx:208/220`); the script is `watch_conv2.py`.

**Task 6.4, the recent view (no conversation selected)** - the other branch of the ternary:
`GET /agent/scribe050237/chat` returns 50 entries naming **11** distinct runs and a `runs` map of
**11**, nothing unlabelled; the pane renders 2 turn boundaries, both with stat lines, and the one
non-`completed` outcome in view carries its `Turn interrupted` label.

**Task 6.5, the added query's cost.** `GET /agent/{a}/chat/{cid}` on the largest fixture
conversation (50 entries, 10 distinct runs), n=50 each, same Hub and database, measured by swapping
`hub/hub/api/v1/agent_chat.py` for `272adce^`'s copy and restarting:

```
before   min 10.8  median 16.4  p90 30.2  max 39.6  mean 19.3   (ms, runs map absent)
after    min  6.5  median 16.2  p90 31.6  max 35.3  mean 18.9   (ms, runs map size 10)
```

**Below the noise floor** - the "after" median is 0.2 ms *faster*, which is the honest way to say the
extra lookup is not measurable here. Stated with its bound: 50 entries and 10 runs is the largest
conversation this fixture has, and it is not large.

**Task 6.7, the working indicator across stop-then-send (design D9), live.** Conversation
`conv-0c52d0358e1b`, indicator node polled directly
(`data-testid="timeline-working-indicator"`) rather than by substring:

```
06:25:50-58   Working - 11s ... 19s          run A, 1 boundary, 0 stat lines
06:25:58      POST stop, then POST trigger immediately -> run_id: null (queued, agent still busy)
06:25:59      Working - 0s   2 boundaries   Turn stopped x1   1 stat line
06:26:00-06   Working - 1s ... 7s
06:26:07      indicator gone; 06:26:08 the second stat line appears
```

**The indicator never goes dark**, and it re-bases to the new turn's first entry rather than
carrying A's elapsed forward. What covers the window is the *delivered queue entry*, not a key in
the run map: the new run was `run_id: null` at trigger time. Stated with its bound - the poll loop's
real cadence is ~1.0 s (250 ms sleep plus the DOM read), so this bounds any dark frame at under
~1.1 s rather than proving it is exactly zero. **The negative half:** conversation A on screen, a run
started and completed in another conversation on the same agent (`06:27:39`, `run-95ae0a5ed7b1`) -
over 45 s A's pane did not change once: indicator absent throughout, 1 boundary, `Turn stopped` 1,
1 stat line.

**Task 6.3, the no-regression check on the interrupted label.** Long turn in flight
(`run-85016a2b514c`), browser attached to `conv-4e39e46a5a8f`, nobody touching the page:

```
06:28:05.06  Hub hard-killed (Stop-Process -Force)
06:28:10.27  row written interrupted  (the run's own ended_at, 05:28:10.271901Z UTC)
06:28:11.82  new Hub answering /health   ("Reconciled 1 orphaned run(s)" on start)
06:28:21.3   browser, no reload: 'Turn interrupted' x1, 2 boundaries, 1 stat line
```

**11.0 s from the row to the label, 9.5 s from the Hub serving again**, against phase 0's 8.6 s and
7.1 s. Seconds, not "never" - the map move did not regress it. And the same confound phase 0
recorded is present again, so it was measured directly this time rather than left as a suspicion.

**Task 3.5's live half, which iteration 16 could only answer from code ordering.** A client
subscribed to `GET /api/v1/events` the way the browser is, across a kill and restart
(`sse_watch.py`, uncommitted):

```
06:30:45.76  Hub killed        stream #3 DROPPED ConnectionResetError
06:30:48     connect #4 OPEN
06:30:49     FRAME queue_entry_delivered {'agent': 'scribe050237', 'run_id': 'run-3d5e08c5d227'}
06:30:49     FRAME run_started          {'agent': 'scribe050237', 'run_id': 'run-3d5e08c5d227'}
             ... and no run_interrupted frame, at any point, on any of 11 connections
```

**D8 holds, and now as a measurement.** `reconcile_interrupted_runs()` broadcasts before uvicorn
serves, so no reconnecting client can receive it - confirmed by construction *and* observed. What
the reconnected stream does carry is the successor run's **queue** traffic, which the chat hooks
listen to. So phase 0's confound is the mechanism, not a coincidence: the label appears because a
queue frame (or the reconnect invalidation) refetches the chat, never because `run_interrupted`
reached the client.

**Teardown (6.6).** Project `proj-9042770d2ae3` on the `f274p0` profile database, port `8012`, left
in place so the review page can cite it; `GET /jobs` and `GET /loops` both `[]`, so nothing is
enabled. `:8000` untouched throughout (PID 10556 before and after); nothing was listening on `:8010`
at any point.

## F275 (C) - an abandoned operator message renders after the failures it caused

**Status:** fixed (this commit) [UI-1, 2026-09-23] — an abandoned message sits where it happened, among the turns; see FIXED at the end of this entry. Was: open. Filed 2026-09-03. A consequence of F87's fix, not an oversight in it. **Round 3d, 2026-09-23: deferred to a UI round.** The server order is not what decides the screen: `agentTimelineModel.groupIntoTurns` puts every non-delivered entry, abandoned or waiting, into `pending`, rendered after every turn -- so the repair is the UI placing an abandoned entry among the turns by its timestamp (with the route sorting it in, not appending it). That needs a bundle, and no bundle can be committed until `:8000` is restarted past `c18a87b` (the night window's group 5.4 gate, 2026-09-23).

`_queued_entries_for` returns entries that are still `queued` **and** entries the Hub gave up on
(`hub/hub/api/v1/agent_chat.py:249-280`), and both routes append its result **after** the timestamp
sort - `agent_chat.py:701-703` (`entries.sort(key=...)`, `entries = entries[-limit:]`,
`entries.extend(await _queued_entries_for(...))`) and `:634` for the conversation-scoped one.

For a still-queued entry that is right: it belongs to the turn that drains it next. For an
**abandoned** one it is not - that message is finished, it happened first, and putting it last
inverts cause and effect on screen. Measured:

```
GET /projects/<pid>/agent/p6fail0903d1/chat
  08:08:24.306  agent_output    run-d287dc866146  error: unknown option '--aw-p6-no-such-flag'
  08:08:24.500  agent_output    run-d287dc866146  Run failed (exit 1).
  08:08:27.899  agent_output    run-8039a5a50a5e  error: unknown option '--aw-p6-no-such-flag'
  08:08:28.090  agent_output    run-8039a5a50a5e  Run failed (exit 1).
  08:08:31.434  agent_output    run-086f573343b9  error: unknown option '--aw-p6-no-such-flag'
  08:08:31.647  agent_output    run-086f573343b9  Run failed (exit 1).
  08:08:20.830  operator_input  run-086f573343b9  Say hello.        <- earliest, returned last
```

The browser renders it in that order: three `Turn failed` turns, then `NOT DELIVERED - delivery
failed 3 times; the Hub stopped retrying` beside `Say hello.` at the bottom. An operator reading
top-to-bottom sees the agent fail three times before they said anything.

The `NOT DELIVERED` chip does rescue the meaning, which is why this is **C** and not B - the fact is
present, only its position lies. Worth noting beside F188, which is about the same three-attempt
abandonment reaching the operator at all.

**FIXED 2026-09-23 (interactive session, UI-1).** Both halves ROUNDS named. The route: new `agent_chat._split_undelivered` separates `_queued_entries_for`'s answer, and both chat routes sort abandoned entries in with the history by their own timestamp (`arrived_at`), appending only the still-waiting ones. The view: `groupIntoTurns` walks the entries in that order; an abandoned entry becomes a one-entry turn marked `abandoned`, in place, and `pending` holds only `queued` entries. `AgentTimeline` renders such a turn as the message with its *not delivered* chip and reason, outside `[data-turn-boundary]`, and computes the newest-run turn (`lastTurn`, which gates the working indicator) from run turns only. Tests: `test_an_abandoned_entry_sits_where_it_happened` (`test_agent_chat.py`, both routes; fails on the old route), and `agentTimelineModel.test.ts` (fixture in the route's new order).

**Review follow-up 2026-09-23 (adversarial Opus review of UI-1).** One consequence, now stated: the agent-wide recent view (`GET /agent/{name}/chat`) applies its `limit` after the abandoned entries are sorted in, so an abandoned entry older than that window drops out of the recent view, like any other entry of its age. It is still in its own conversation's view, which is F87's concern.

## F276 (C) - `agent_wide`'s documented example was never marked `agent_wide`, and no site sets both flags

**Status:** closed 2026-09-24 — **decided, no change** (operator, daily review, bundle B3 D10; `spec-queue/tracks/B3.md` Final). The no-such-agent refusal stays request-level and does not hold queued input: its only remaining producer is a job created in a project with an empty roster, and a job regenerates its input every firing, so nothing is lost. Follow-on candidate once `agents-no-longer-register-themselves` lands: the empty-roster exemption in `jobs._check_agent_exists` (`jobs.py:181-200`) loses its reason. Was: open. Filed 2026-09-04 (night window, phase 5 of
`a-blocked-agent-workspace-holds-its-input`). **The documentation half is fixed in the same commit
that filed this; the behaviour question below is what stays open.**

`TriggerAgentError.agent_wide`'s docstring (`hub/hub/api/v1/agent_trigger.py`) claimed, as its
illustration that the flags are independent axes:

> **Marked conservatively, and the two axes really do cross.** `:479` (no such agent) is
> request-level *and* agent-wide; ...

Measured by reading the raise sites rather than the prose:

| site | flags actually passed |
|---|---|
| `agent_row is None` - *"is not an agent in this project"* | `request_level=True` **only** |
| `runner_id is None` | `agent_wide=True` only |
| `lifecycle == "archived"` | `request_level=True` only |
| unsupported runner (501) | `request_level=True` only |
| `not probe["runnable"]` | `agent_wide=True` only |
| `runner_row is None` | `agent_wide=True` only |

`grep -n 'agent_wide=True' hub/hub/` returns **three** lines, and the no-such-agent raise is not
one of them. It never was: F114 (`8450831`) added the flag to exactly those three sites, and
`git log -S` shows the no-such-agent sentence has been edited once since (`96b54cd`, F33) without
gaining it. **No site in the Hub raises with both flags set**, so the sentence "the two axes really
do cross" had no instance behind it in the code it was documenting.

**Why this is a finding and not a typo.** The flag's own definition is *"does this refusal stop the
agent running at all, rather than blocking this input in particular"*, and an agent that does not
exist in the project cannot run at all - so by that definition the unmarked site qualifies. What
the missing mark costs: queued input for an agent whose row is absent (a name deleted after the
input was queued, or a job naming a mistyped agent) has a delivery attempt counted on every
schedule and is **withdrawn at the third**, with `abandoned_reason` claiming a delivery failed
three times. That is F114's exact scenario with a different repair - *create the agent, or correct
the name* instead of *bind a runner* - and F114's fix does not reach it.

Not fixed here, deliberately: `a-blocked-agent-workspace-holds-its-input` scopes itself to the
*workspace* refusal, its phase 5 is a reconcile-the-prose phase, and marking a fourth site
`agent_wide` is a behaviour change with its own scenario ("does the product hold input addressed to
a name that does not exist, or give up on it?") that deserves the round discipline rather than a
drive-by. It is also genuinely arguable in the other direction: `request_level=True` already tells
the caller *no*, and holding a message addressed to a name nobody ever registered may be worth less
than the queue slot.

What was fixed: the paragraph now states what the code does, points at the task arm of the
workspace `except` as the real environment-level-but-entry-specific example, and records this
measurement inline so the next reader does not re-derive it.

## F277 (C) - `restrict_spec_writes` omits `MultiEdit`, the one write tool that edits a file the same way the three it names do

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- `MultiEdit` added to the disallow list; the wider question stays open; see FIXED at the end of this entry. Was: open. Filed 2026-09-04 (night window, task 2.2c of
`a-write-outside-the-workspace-is-recorded`). **Filed, deliberately not fixed** - see the last
section.

`restrict_spec_writes` is the flag a turn triggered with a specification document open runs under
(F4/design D6 of `2026-08-17-authoring-rigor-and-scope`). It renders one argument
(`hub/hub/runner_commands.py:203`):

```python
cmd += ["--disallowedTools", "Edit,Write,NotebookEdit"]
```

`MultiEdit` is not in it, and `MultiEdit` is a file-writing tool by every other reckoning in this
product: `AgentTimeline.tsx`'s `WRITING_TOOLS` counts it, `lib/editDiff.ts` renders its diff, the
timeline has a test written against a real `MultiEdit`-shaped payload, and
`hub/hub/workspace_writes.py` (added in the same phase as this finding) counts it. Measured by
building the command rather than reading the flag:

| posture | `--disallowedTools` | `--allowedTools` | `MultiEdit` named anywhere |
|---|---|---|---|
| default (non-yolo, approver) | `Edit,Write,NotebookEdit` | `mcp__agentweave__*` | no |
| `yolo=True` | `Edit,Write,NotebookEdit` | *(absent)* | no |

So a spec-authoring agent can edit any file `MultiEdit` reaches, in either posture. Under yolo
there is nothing else in the way at all. Under the default posture the approver still runs, but
`_decide` checks *paths*, not tool names - a `MultiEdit` inside the run's own workspace is allowed,
which is exactly where the source files a spec-authoring agent is supposed to be describing rather
than changing live.

**What it is not.** This is not a sandbox escape, and calling it one would overstate it: `Bash` is
not in the disallow list either, so a run under this flag can already write through
`echo ... > file`, and the flag's own comment describes an axis ("which tools exist at all") rather
than a guarantee. The flag is a nudge that makes the *ordinary* way to edit a file unavailable, so
a model reaching for one gets a refusal and proposes instead. `MultiEdit`'s omission is a hole in
exactly that nudge: it is not a creative workaround a model has to think of, it is the tool Claude
picks by default for a multi-hunk edit, and a model that reaches for it succeeds silently and never
learns it was supposed to propose.

`git log -S` puts the line at `2a52fcd`, the change that introduced the flag; it has never been
edited since. The omission is almost certainly an oversight from enumerating Claude's write tools
from memory rather than a decision - nothing anywhere argues for excluding it.

**Not fixed here, and the reason matters more than the fix.** Round 2 of
`a-write-outside-the-workspace-is-recorded` proposed asserting that every tool
`workspace_writes.written_paths` calls a writer appears in this disallow list. That assertion is
false by construction for the Codex half - `--disallowedTools` is a Claude argument and can never
name `apply_patch` - and satisfying it would have forced `MultiEdit` *out* of the new writer list,
propagating this gap into the change rather than exposing it. Round 3 measured all three existing
statements of "which tools write", found they disagree, and reconciled against the UI's
`WRITING_TOOLS` instead (design D3).

`hub/tests/test_workspace_writes.py::test_restrict_spec_writes_is_not_the_definition_of_a_write_tool`
pins that reasoning: it asserts the disallow list and the writer set are **not** equal and that
`MultiEdit` is absent from the former, so the gap is measured on every run and closing it upstream
fails that test loudly rather than silently. Its message says to retire this finding, not the test.

The fix is one word in a string literal. What it is not is free: it is a behaviour change to how a
spec-authoring turn runs, it is `authoring-rigor-and-scope`'s scenario rather than this change's,
and the honest version of it asks the wider question this finding raises - whether a nudge that
`Bash` walks straight through should be enumerating tools at all, or whether that posture wants the
approver rather than a disallow list.

**FIXED 2026-09-23 (interactive session, Round 3, group 3f).** The one word, as `ROUNDS.md` placed
it: `--disallowedTools Edit,MultiEdit,Write,NotebookEdit` (`runner_commands.py`), with the reason
beside it. `test_spec_authoring_restriction.py`'s two literal assertions follow it, and
`test_restrict_spec_writes_is_not_the_definition_of_a_write_tool` keeps its point -- the Claude
disallow list is still not the definition of a write tool, since it can never name Codex's
`apply_patch` -- with its F277 line flipped to `"MultiEdit" in disallowed`, as its own message
asked. **The wider question is not answered here and stays open:** whether a restriction `Bash`
walks straight through should enumerate tools at all, or hand this posture to the approver. That is
`authoring-rigor-and-scope`'s question and a decision, not a repair.

---

## F278 (C) - a deep POSIX file path in a recorded transcript reads `<redacted>.py`, because `/` is inside the high-entropy class

**Status:** fixed ee6ba0f (`a-file-path-is-not-redacted-as-a-credential`, archived 2026-10-04): a
catch-all match of three or more ordinary-word segments is kept as a path, and a segment of 32+
characters, or 16+ holding a letter and a digit, is still redacted. Tests in
`hub/tests/test_operator_is_told_the_truth.py`: `test_a_posix_path_is_not_a_credential`,
`test_a_credential_used_as_a_path_segment_is_still_redacted`,
`test_a_short_token_in_a_path_is_still_redacted`, `test_a_base64_credential_with_slashes_is_still_redacted`,
`test_only_the_high_entropy_rule_can_keep_a_path`. Residual, stated in the change: a path with a
segment that is not an ordinary word (`Claude2`, `README`) is still redacted whole.
Filed 2026-09-04 (night window). Found while *measuring a claim rather than
asserting it* - phase 2b of `a-write-outside-the-workspace-is-recorded` wanted a comment saying
"the structured path may not survive redaction", and checking whether that was true turned up
this. **Filed, not fixed:** it is `redact_secrets`' scope, not that change's.

`_SECRET_VALUE_RE`'s third alternative is a bounded high-entropy catch-all,
`[A-Za-z0-9+/=]{32,}` (`hub/hub/runner_events.py`). `/` is a member - it has to be, base64 uses
it - and a POSIX path is mostly letters and slashes. So any 32-character run of a path that
happens to contain no `.`, `_` or `-` matches the rule for a credential and is replaced whole.
Measured against the module on 2026-09-04:

| path | stored as |
|---|---|
| `/Users/operator/code/agentweave/hub/main.py` | `<redacted>.py` |
| `src/services/user/repository/handler.py` | `<redacted>.py` |
| `/workspace/proj/.agentweave/worktrees/beta/src/app.py` | `/workspace/proj/.<redacted>.py` |
| `/workspace/my-project/src/app.py` | *(intact - the hyphen breaks the run)* |
| `/workspace/myproject/src/app.py` | *(intact - the run is 28 characters)* |

**This is F31's remainder, not a new rule gone wrong.** F31 narrowed the class by excluding `_`
and `-`, on the argument that "identifiers a human or the Hub composed are made of joined words and
carry one or the other". That argument holds for identifiers and does not transfer to paths: a path
is joined with `/`, which stayed in the class. F118 is the same family again, one dimension over -
`task-` ending in `sk-`. Three findings now, all from one regex, all of the form *a shape the rule
was not thinking about looks like base64 for long enough*.

**Windows is unaffected**, which is why this has gone unnoticed on the machine the product is
developed on: `\` is not in the class, so `C:\Users\huida\...\notes.py` survives intact. Every
Docker deployment - the shipped `hub/Dockerfile` and the documented self-host path - is Linux.

**Why C and not B.** It fires *conditionally*, on depth and on the absence of three characters, so
a transcript is not uniformly damaged the way F118's task ids were; a shallow path or one with a
hyphen reads fine. But the conditionality is its own cost: an operator sees `<redacted>` in some
tool inputs and not others, with no rule they can infer, and the marker positively suggests a
credential was caught. The path most reliably eaten is the one under `.agentweave/worktrees/`,
which is to say the agent's own checkout - the destination an operator reading a transcript is most
often trying to establish.

**Not fixed here.** The obvious narrowing - require the run to contain no `/`, or demand a `+` or
`=` - is a change to the credential rule itself, and getting it wrong in the other direction stores
a live key. That wants its own change with its own reproduction, weighed against the two prefixes
that already catch the credential shapes this product actually mints (`aw_live_`, `sk-`). What this
finding does establish is that the catch-all has now produced three false-positive families and
zero recorded true positives that the two prefixes would have missed.

**It does not affect `a-write-outside-the-workspace-is-recorded`, by construction.** That change
reads the path off the structured input *before* `redact_secrets` runs, for exactly this reason,
and `test_the_field_is_read_before_the_payload_is_redacted_and_truncated` pins the ordering. The
finding is why that test exists rather than something it blocks.

## F279 (C) - the two "a stopped run" tests fail about half the time, on an unmodified tree

**Status:** fixed 890cf40 (closed 2026-09-22: the call it failed in was removed by F287's repair, and 0 failures in 30 runs; see the foot). Was: open, and undiagnosed. `spec-queue/ROADMAP.md:93-99` separates it from the
CI flake it had been conflated with -- different exception, different locus, different latency,
different reproducibility -- and that separation is the only work it has had. Both tests still stand
and the concurrent-session reproduction this entry names has never been pursued. [classified 2026-09-09, D-3]

**Measured 2026-09-04 (night N-18), on `autonomous/2026-09-03-daily` at `e28bbdf`,** while running
the regression suites around phase 4 of `a-write-outside-the-workspace-is-recorded`. Two tests fail
intermittently, with no change to the tree at all:

- `tests/test_agent_trigger.py::test_codex_app_server_stop_signals_should_interrupt`
- `tests/test_a_turn_says_how_it_ended.py::test_a_stopped_run_persists_its_terminal_status_line`

Twelve runs of the pair, six with that iteration's change applied and six with the working tree
stashed: **7 failures in 12 without the change, 4 in 12 with it.** Both fail alone as readily as in
a full-file run, in 1.5 seconds, so it is not contention with the rest of the suite. Both belong to
the same family - trigger a run, poll until it registers as live, `POST .../stop`, then await the
background task - and both take the same shape when they fail: the run is torn down while
`record_agent_output`'s `db.refresh(row)` is in flight, and the awaited background task raises out
of `_await_background_run` rather than settling.

**Why it is worth a finding rather than a shrug.** A test that fails half the time on an unmodified
tree is indistinguishable, to the next iteration, from a test its own change broke - and the cost is
paid every time somebody runs the suite and has to prove the failure was already there. This
iteration paid it twice, once for each test, by stashing and re-running. It also means the *full*
suite has a coin-flip red in it that no gate can currently attribute, which is exactly the condition
under which a real regression gets waved through as "the flaky one again".

**Not the change under it.** Phase 4 adds one `await` to each execution path's `finally` (the
best-effort count flush) and one at run start, so the suspicion that it widened a teardown race was
the first thing checked - and the measurement points the other way: the failure rate is *lower* with
the change than without. Whatever the race is, it predates both.

**Not diagnosed.** Establishing which of the stop path's steps is unordered against the
`record_agent_output` in flight is its own investigation with its own reproduction; this records that
the flakiness is real, measured, pre-existing, and attributable to neither of the two changes on this
branch that touch these paths.

**Confirmed again 2026-09-04 (night N-19), and the shape of the race got sharper.**
`test_codex_app_server_stop_signals_should_interrupt` failed once in a five-file regression run and
then passed 3/3 alone immediately afterwards, on the same tree - the same coin flip, now costing a
re-run to attribute for the second night running.

What sharpened it is a failure met from the other direction. N-19's task 4.4c wanted to observe a
run's own row *while the run was still mid-turn*, and its first draft polled the database in a loop
while the run was writing. That intermittently broke the run itself, with exactly F279's signature:
`sqlalchemy.exc.InvalidRequestError: Could not refresh instance` raised out of
`record_agent_output`'s `db.refresh(row)` at `output_recording.py:94`, killing `_execute_run`. No
stop endpoint was involved and nothing was being torn down - only a second `async_session_factory()`
session reading the same SQLite database concurrently with the run's own writes.

That makes "the run is torn down while `db.refresh` is in flight" look like the wrong half of the
description. The *teardown* may be incidental; what both cases share is a **concurrent session
against the run's own in-flight transaction**, and `db.refresh` immediately after `db.commit` is
where it surfaces. A reproduction that does not involve stopping anything is now known to exist,
which is a much cheaper starting point for the investigation than the stop path.

The 4.4c test was rewritten to avoid the collision rather than to tolerate it: the fake process
signals a `threading.Event` at the moment it blocks, so the test reads the row only when the run is
quiescent. Twenty-two tests across the two files then passed 4/4 consecutive runs.

**Closed 2026-09-22 (interactive session).** Every failure recorded above raised `Could not refresh instance` from `record_agent_output`'s `db.refresh(row)` (`output_recording.py:94` then). `890cf40` (2026-09-05, F287, the day after this was measured) deleted that refresh as redundant: `expire_on_commit=False` means the committed row needs no reload. So the call that failed no longer exists. Nothing linked the two until now. **Measured on `8b44bc7`:** the pair run alone, 30 times, gave **0 failures** (each run `2 passed`), against the filed 7 in 12. The "concurrent session against the run's in-flight transaction" hypothesis is therefore moot for these tests. Any `database is locked` a concurrent session still causes is F349's and F292's territory, not this one.

## F280 (C) - an agent's recording response reports no footprint, so the recorder is the one party who cannot see what their evidence was attached to

**Status:** fixed `c063e28` (2026-09-04), in the iteration that filed it. Verified
2026-09-09: the agent's recording response carries `footprint` through the shared `footprint_view`
helper (`hub/hub/api/v1/agent_actions.py:1137`, `:1145`). The sweep this entry asks for at the end --
which other shipped requirements phrased around *the response* are implemented on the operator plane
only -- has not been run. [classified 2026-09-09, D-3]

**Found 2026-09-04 (night N-20)** while implementing phase 5 of
`a-write-outside-the-workspace-is-recorded`, and fixed in the same iteration.

`requirement-traceability` says: *"Where a footprint is captured, the response to the recording SHALL
report it, so the recorder can see what their evidence was attached to at the moment they can still
correct it."* That was implemented on the operator's route (`spec.py`'s `record_evidence`, the second
half of **F71**) and never on the agent's (`agent_actions.py`'s `record_evidence`), whose response
carried `id`, `identifier`, `review_state` and `digest` and nothing about the footprint.

**Why it matters more than the operator case it was fixed for.** An agent's footprint is the one that
is *routinely* not what the recorder would assume: it names the agent's own checkout at the commit
the turn started from, with the work still uncommitted, later corrected by `restamp_run_footprints`.
And phase 5 adds a field that can only ever be non-empty for a **run** - a footprint's
`outside_workspace_writes` says the tree this evidence names is missing part of the run's own work,
and the operator, having no run, can never see a non-null one on their own recording. So the fact
existed, was recorded, was reported... on the one response its cause never receives.

**Fixed here**: the agent's recording response carries `footprint`, through a `footprint_view` helper
extracted from `_evidence_view` so both responses shape a footprint the same way, and
`record_evidence`'s tool docstring tells the agent to read `outside_workspace_writes` and say so in
its summary while somebody can still act on it. Covered by
`test_evidence_footprint_root.py::test_the_recording_response_reports_that_the_run_wrote_outside`,
which mutation M8 (drop the key from the agent response) turns red.

**The general shape, which is the part worth keeping.** A requirement written about "the response to
the recording" was satisfied by fixing the response *one kind of recorder* receives. Both routes were
already there; nothing pointed out that the sentence covered both. Worth a sweep: which other
shipped requirements phrased around "the response" are implemented on the operator plane only?

## F281 (B) - a shell command's writes are never recorded, in any posture, and the boundary that refuses some of them is the only thing that ever sees one
**Status:** closed 2026-09-24 — **decided by design** (operator, daily review, B11): `agent-run-sandboxing` (`spec.md:413-418`) says the record is not a complete account and a shell command is out of scope. Remaining step (no-spec): reword `models.py:1214` to "no file tool wrote outside this run's boundary". Was: open (filed as explicitly out-of-scope for the archived a-write-outside-the-workspace-is-recorded change, 46b8e3e; not fixed by it)

**Found 2026-09-04 (night N-21)** doing task 8.1 of
`a-write-outside-the-workspace-is-recorded`. **Filed, not fixed** - it is named out of scope in that
change's proposal, and the label on the record it ships does not imply it.

`written_paths` (`hub/hub/workspace_writes.py`) answers *the declared path argument(s) of a
file-writing tool call*. A `Bash`/`shell` call declares no path: it carries a command string. So
`written_paths("Bash", {"command": ...})` returns `()` for every command there is, and
`OutsideWriteRecorder` - the whole of the new record - never sees a shell write at all. Measured:

| command | `written_paths("Bash", …)` | `_decide` under the default posture |
|---|---|---|
| `echo hi > C:/…/tmp…/stray.txt` | `()` | refused, naming the path |
| `echo hi > "$HOME/stray.txt"` | `()` | refused, on the fragment `'/stray.txt'` |
| `D=/tmp; echo hi > $D/stray.txt` | `()` | refused, on the fragment `'/tmp'` |

**The asymmetry is the finding.** The `workspace` posture's approver reads absolute paths out of the
command *text* (`mcp_server._decide`, the `command` branch) and says so of itself - *"This does not
make shell escape impossible … and is a boundary, not a sandbox."* So under the default posture the
boundary catches the literal-path case, and even over-refuses on a fragment that was never a
destination (`$D/stray.txt` refused for `/tmp`). Under the three postures where an outside write is
actually *possible* - `manual` approved, `acceptEdits`, full access - nothing checks the command and
nothing records it either. The record this change adds is blind to exactly the tool an agent reaches
for when a file tool has been refused.

**Why it is not fixed here, and what fixing it would take.** Recording a destination the run never
declared means either parsing shell (`>`, `>>`, `tee`, `cp`, `mv`, `install`, a heredoc, any of a
dozen more, in two shells) or watching the filesystem. The first invents coverage - the failure mode
`written_paths` is deliberately written against, returning empty for an unknown tool rather than
guessing from key names. The second is a different product decision (an OS-level sandbox, per the
change's own out-of-scope note). Neither belongs inside a parse-time path extractor.

**What a reader should take from it today.** `Run.outside_workspace_writes == []` means *no
file-tool write left the workspace*. It does not mean *nothing left the workspace*, and the run's
`Bash` calls are the gap. That is a narrower claim than the column's comment currently makes, and it
is the honest one.

## F282 (C) - a junction inside the workspace is correctly classified as outside and correctly refused; what is wrong is the path both of them then print

**Status:** fixed (this commit) [Round 4, 2026-09-23] — the refusal and the record name the resolved path beside the declared one; see FIXED at the end of this entry. Was: open. The declared path is still what both the refusal and the record print,
so the verdict still disagrees with the path beside it. `spec-queue/APPROVALS.md:511` carries it to
the operator as the day window's to take up; nothing has been taken up. [classified 2026-09-09, D-3]

**Found 2026-09-04 (night N-21)** doing task 8.2 of
`a-write-outside-the-workspace-is-recorded`. **The task's premise did not survive being measured**,
and the corrected finding is smaller and different in kind.

Task 8.2 says to file *"symlink traversal: a link inside the workspace pointing out reports a path
that is legitimately inside"*. Read as a detection gap, that is false. Both `classify`
(`workspace_writes.py`) and `_decide` (`mcp_server.py`) call `os.path.realpath` on the joined path
before comparing, which is the same reason `classify`'s docstring already gives for the two agreeing
about a link. Measured on this machine with a directory **junction** - `mklink /J`, the cousin of a
symlink that needs no elevation, which is what made the measurement possible where `os.symlink`
raised `WinError 1314`:

```
declared   C:\…\tmp\ws\link\x.py          (link -> C:\…\tmp\elsewhere)
realpath   C:\…\tmp\elsewhere\x.py
classify   WriteLocation(kind='project', name=None)     # the destination's real location
_decide    allow=False, "… is outside your workspace"   # refused under the default posture
```

So the link is followed, the write is classified where it really lands, and the default posture
refuses it. Nothing is fooled.

**What is actually wrong is the reporting.** Both the refusal reason and the recorded row name the
**declared** path - `…\ws\link\x.py`, which reads as unambiguously *inside* the workspace - while the
verdict beside it says outside. The recorder stores the first call's `tool` and `path` "raw and
exactly as the tool declared it" on purpose, so the durable record and the operator's notice cannot
describe different writes; the cost is that for a linked route they agree with each other and
disagree with the verdict. An operator reading *"alice wrote outside its workspace: Write →
C:/ws/link/x.py"* has no way to see why that path is outside anything.

**Not fixed here** (this change ships no path rewriting, and carrying a second resolved path is a
schema decision with its own argument). The cheap improvement, if it is ever wanted, is to record the
resolved path *beside* the declared one rather than instead of it - the declared path is what the
agent must be told about, the resolved path is what the operator must be shown.

**And the one thing genuinely undetectable:** a hard link. No path comparison of any kind can see
one, because there is no link to resolve - two names for one inode, both legitimately inside. That is
a real hole and it is unrelated to symlinks; it is recorded here so a later sweep does not
rediscover it and file it as the same thing.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** The shape this entry proposed: the resolved path is added **beside** the declared path, never in
its place.
- **Refusal:** `mcp_server._where` answers `is outside your workspace: it resolves to '<real
  path>'` when `abspath(declared) != realpath(declared)`, and the unchanged `_OUTSIDE` sentence
  otherwise. It stays stdlib-only, per the MCP rules.
- **Record and notice:** `workspace_writes.resolved_elsewhere` (new) gives the same answer. The
  recorder adds `resolved_path` to the destination's entry in `Run.outside_workspace_writes`, and
  to the `agent_wrote_outside_workspace` event, only when a link moved the write. It is a JSON
  column, so no migration.
- **Evidence:** `hub/tests/test_a_request_means_what_it_says.py` makes a real junction (`mklink /J`, as this entry was measured; a symlink
  elsewhere) and asserts both answers. A no-link path reads exactly as before. On the old code the
  new helper did not exist, so its legs fail on import. The refusal half was also checked directly
  against the old `mcp_server.py` with the same junction: `'is outside your workspace'`, with no
  target named.
- **Not fixed:** the hard-link hole this entry records is unrelated and untouched.

## F283 (B) - the Permissions pill sits on "Edit files" while the run it describes is spawned under "Workspace only"
**Status:** fixed 8d16d8f (`the-permissions-pill-shows-the-posture-the-run-gets`, 2026-09-30: one `posture_at_rest` read by the spawn, Copilot, the roster and both pills; Claude's catalog default is `workspace`). Was: open

**Found 2026-09-04 (night N-21)** while documenting the postures (task 7.1). **Filed, not fixed** -
it is outside `a-write-outside-the-workspace-is-recorded`, whose scope is observing writes, not
choosing postures.

There are two built-in defaults for one decision, in two modules, and they disagree:

- `model_catalog.py` - the `permission_mode` control declares `default="acceptEdits"` (and
  `DEFAULT_PERMISSION_MODE = "acceptEdits"` beside it, referenced by nothing else in the Hub).
- `runner_commands.py` - `DEFAULT_CLAUDE_PERMISSION_MODE = WORKSPACE_PERMISSION_MODE`, applied when
  the operator set no posture, spawning `--permission-mode manual --permission-prompt-tool
  mcp__agentweave__approve_tool_call`.

For an agent with no `default_permission_mode` (the column is nullable and NULL for every agent
nobody has configured), the composer sends no `permission_mode` override, so `AgentOutputPanel`
passes `EMPTY_CONTROLS` as `effectiveControls` and `ComposerModelControls` falls through
`effectiveValue ?? control.default ?? …` to the catalog default. The pill therefore reads **"Edit
files"** and the run is **"Workspace only"**.

**Why this is a B and not cosmetic.** The pill is the operator's statement of what the run will do,
and both sides of the wire already carry a comment saying so - `AgentOutputPanel.tsx`, *"without this
the pill would sit at the catalog default while the run went elsewhere"*, which fixed the
**agent-default** case and left the no-default case as it was; and `runner_commands.py`, calling the
composer appearing to work and changing nothing *"the worst available failure mode"*. This is the
same disagreement, in the case a fresh project is always in.

The direction is worth stating: the run is **stricter** than the pill claims, not looser. An
operator who reads "Edit files" and is told nothing is checked will see their agent refused for an
absolute path, which is a confusing refusal rather than an unsafe permission. The fix is a decision
about which default is the real one, not a patch: either the catalog's declared default becomes
`workspace` (and Codex's own row is looked at in the same breath), or the composer resolves its
at-rest display through the same fallback the spawn uses.

## F284 (C) - the permission card the operator answers gives them no way to see that the path leaves the run's workspace

**Status:** fixed 3967f83 (`an-ask-me-card-says-what-workspace-only-would-decide`, 2026-09-30: an "Ask me" card shows what "Workspace only" would decide, with its reason, for Claude, Codex and Copilot). Was: open. The card still names the tool and the absolute path and nothing
derived from the boundary the Hub itself computed. `spec-queue/APPROVALS.md:512-515` carries it with
the instruction that it be decided together with the posture finding beside it; neither has been
decided. [classified 2026-09-09, D-3]

**Carried forward 2026-09-04 (night N-24) out of F115's second section, which is retired around it.**
Not a new observation — it was measured live on 2026-08-30 (iteration 11) and has sat inside a
finding that is now retired, which is precisely how a live-driven observation gets lost.

Under the `workspace` posture the Hub answers each tool call itself and refuses a path outside the
run's workspace, so this does not arise. Under `manual` the **operator** answers, and the card they
answer with names the tool and the full absolute path and nothing else: no marker that this
particular path leaves the workspace, and no comparison against the boundary the Hub itself computed
a moment earlier to launch the run. Two runs of the same agent, same posture, same sentence, were
driven nine minutes apart; one card offered a path under
`\.agentweave\worktrees\asker\` and the other a path directly in the project root, and the two
cards were indistinguishable in every respect an operator can read.

**Why it survives `a-write-outside-the-workspace-is-recorded`.** That change records the write and
notifies once per destination — *after* the call. The operator approving the card is the last human
who could have stopped it, and they are the one party the record does not reach in time. The
classifier such a card would need already exists and is already reachable from the request path
(`hub/hub/outside_write_record.py`), so what is missing is a decision about the approval surface,
not a mechanism.

**Severity is C and the reason matters:** nothing is lost or misattributed — the write is now
recorded, named by destination, and surfaced to the operator in the activity log. What remains is
that `manual` is not the safer posture it reads as; it is the posture in which a human is asked to
make a judgement they have not been given the inputs for. Scope, if it is taken up, is the card's
payload and its rendering, and it should be decided together with **F283 (B)**, which is the other
place where the posture the operator believes they chose and the posture the run got come apart.

## F285 (B) - the hub suite's in-memory engine shares one connection across every session, so any request that finishes rolls back whatever a background run is midway through writing

**Status:** fixed `d9ad1e0` (2026-09-04, DECIDE session). The suite is file-backed in a
per-process temporary directory, so `AsyncAdaptedQueuePool` replaces the StaticPool and each
session holds its own connection. Fix chosen by the operator from the three below, after the other
two were measured and found not to work: `NullPool` on `:memory:` gives every session its own
*empty* database, a shared-cache memory URI dies with its last connection, and per-test engine
disposal does not touch a race that happens *inside* one test. Verified: the churn reproduction
below now passes, the three CI tests pass, and the full suite is 3961 passed / 0 failed. The move
cost 65 harness failures on the way -- connections outliving their event loop, a background run
outliving a test, and a teardown disposing a test double -- all fixed in the same commit, none of
them a product defect. `test_suite_database_isolation.py` now asserts the engine's pool is not a
StaticPool, which is the check that would have caught this before CI did.

**Found 2026-09-04 (day D-2)** triaging CI. This is the single cause of all three tests the
`hub-test` job has failed on every one of the 21 completed runs since `467dfea` (2026-09-04T00:03),
and therefore the only thing standing between two days of finished work and `master`.

**What CI reports.** Three tests, two files, three different-looking assertions:

| Test | Assertion CI prints |
|---|---|
| `tests/test_a_turn_says_how_it_ended.py::test_a_stopped_run_persists_its_terminal_status_line:362` | `assert 0 == 1` - no `phase="completed"` row |
| `tests/test_agent_trigger.py::test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped:1349` | `assert None is not None` - `queued_entry.delivered_in_run_id` |
| `tests/test_agent_trigger.py::test_codex_app_server_stop_signals_should_interrupt:2049` | the error propagates out of `_await_background_run()` |

All three carry the same traceback, two of them only in the captured log:

```
hub/output_recording.py:94: in record_agent_output
    await db.refresh(row)
sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<AgentOutput at 0x...>'
```

**The mechanism, measured rather than reasoned.** `hub/tests/conftest.py:19` pins the suite to
`sqlite+aiosqlite:///:memory:`. SQLAlchemy's aiosqlite dialect selects the pool from the URL:
in-memory gets a **StaticPool**, a file gets an `AsyncAdaptedQueuePool`. Measured on this machine:

```
sqlite+aiosqlite:///:memory:   pool=StaticPool
sqlite+aiosqlite:///<file>     pool=AsyncAdaptedQueuePool
```

A StaticPool hands *the same DBAPI connection* to every checkout, with no in-use tracking. So every
`AsyncSession` in the suite - the background run task's, and every HTTP request's `get_session`
dependency - shares one connection and therefore one transaction. Returning a connection to a pool
resets it, and reset means `ROLLBACK`. An HTTP request finishing is thus a rollback issued on the
transaction a background task has open.

`scripts/drive/staticpool_shared_connection.py` reduces it to nothing else - session A inserts and
has not committed, session B opens and closes, session A commits and refreshes:

```
sqlite+aiosqlite:///:memory:   -> InvalidRequestError: Could not refresh instance '<Row at ...>'
sqlite+aiosqlite:///<file>     -> no error; rows in db = ['r1']
```

**Reproduced inside the real suite, on this machine, with the exact CI error.**
`scripts/drive/churn_sessions_plugin.py` is an autouse fixture that churns short-lived sessions
during a test - it makes by demand the interleave CI hits by luck:

```
CHURN_DELAY=0.3 PYTHONPATH=scripts/drive py -3.11 -m pytest \
  hub/tests/test_a_turn_says_how_it_ended.py -p churn_sessions_plugin -k stopped_run_persists
```

-> `sqlalchemy.exc.InvalidRequestError: Could not refresh instance '<AgentOutput at 0x...>'`, at
`output_recording.py:94`, same class and same site as CI. It is still a race and not a switch: at
`CHURN_DELAY=0.3` this machine lands on that exact error, at `0.25`, `0.35` and `0.4` the churn is
coarser than CI's window and erases the stop path's own status write first, so the test fails on
`assert 'running' == 'stopped'` instead. Either way the test fails and the cause is the same
rollback. With no churn the three tests pass here every time, individually and by file -
which is exactly what "green on Windows, red on Linux" means: not a platform difference in the
product, a scheduling difference in when a request happens to finish.

**Verdict: a test-harness artefact, not a product defect.** Production is never in-memory.
`hub/hub/config.py:16` defaults the database to `~/.agentweave/hub/data/agentweave.db` and native
mode sets `DATABASE_URL` to a file before `Settings` is instantiated; `:memory:` appears in
`hub/hub/` only in two places that exist to *detect* it (`db/engine.py:76`,
`instance_identity.py:41`). On a file-backed engine every session holds its own connection, so
reset-on-return rolls back only its own transaction, and the demo above commits cleanly.

**What this does not excuse.** The suite is the merge gate's condition 3, and a harness whose
sessions cannot safely overlap makes every concurrent-path test in it non-deterministic rather than
just these three. The fix is a decision about the test engine - a StaticPool that is not shared, a
file-backed temporary database per test, or per-test engine disposal - and belongs to a window that
implements. See **F287** for the one line that turns this artefact into a crash rather than a
harmless extra query, and **F286** for the product gap the crash exposed.

## F286 (B) - an exception after a run reaches its terminal status leaves the input queued behind it undrained, and nothing is on a timer to notice

**Status:** fixed `1529d91` (2026-09-05, night window, change
`a-terminal-run-releases-the-queue-behind-it`, archived under
`openspec/changes/archive/2026-09-05-`). The release stopped asking whether the relabel happened:
the former handler body moved into `_record_run_failure_tail` (`agent_trigger.py:1777`), the
relabel stays gated on the row still being `running`, and `redrain_queued_agents` now runs
unconditionally after it. `_execute_codex_appserver_run` gained the handler it never had at all.
Only `1529d91` carries product code -- `ee6a8e7`, `ddcd07a`, `6b98bdc` and `57e1d2a` add tests, a
test-harness fix and the drive.

**Verified live, twice, as an A/B at one injection site** rather than by a green suite. Both drives
on 8011 from source with `AW_F286_INJECT=1`, a fresh database and fresh fixture project each, one
agent on `claude-haiku-4-5-20251001`. **Fixed** (`proj-b70dad75b4b7`): `run-16b449d4a80a` reached
`completed` / exit 0 / `error=None`, the tail raised, and `entry-8992a0c0b036` was delivered into
successor `run-9d0f885a67c4` **0.140s after the run boundary** with no operator action; the
successor ran a real turn and replied. **Control** -- the same checkout with the pre-F286 gate
restored and the same raise on the same line, so only the gate varies (`proj-5f386b6769de`): the
entry stayed `queued`, `delivered_in_run_id` null, attempts 0 across four polls over 2m06s, and
moved only when a settings save was made. Phase 0's stranding therefore reproduces at a second
in-window site, three statements earlier -- the window is skipped whole, not from the status write
onward. Run #1 kept its recorded outcome in both, which is the half of this finding that must not
regress in fixing the other half.

Five tests cover it: `test_a_run_that_ended_releases_its_queue_even_when_its_tail_raises`,
`test_an_app_server_run_that_ended_releases_its_queue_when_its_tail_raises`,
`test_an_app_server_turn_that_raises_before_its_terminal_write_is_not_a_wedge` and
`test_a_second_release_charges_a_refused_entry_at_most_twice` in `hub/tests/test_agent_trigger.py`,
and `test_a_holder_whose_tail_raises_still_releases_the_task_it_held` in
`hub/tests/test_task_turn_collision.py`. Each was watched to fail against the pre-F286 gate
restored in place, not merely watched to pass. The pre-existing
`test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` was **measured** not to cover
this -- it passes under the restored gate -- and now says so in its docstring.

**Two things this fix did not settle.** The app-server half is covered by tests and a code read
only; Codex is undrivable on this machine. And the ungated redrain registers a new background task
during the test fixture's own teardown gather, which broke ten unrelated tests until
`hub/tests/conftest.py` was made to settle to a fixed point instead of clearing once -- a harness
change, not a product one, and the reasoning for leaving the respawn alone is in the phase-4 log
entry.

**Found 2026-09-04 (day D-2)**, downstream of **F285** - the CI failure is what put a real exception
into that window, but the gap is in `hub/hub/api/v1/agent_trigger.py` and does not depend on how the
exception arose.

`_execute_run` writes the run's terminal status and commits at `agent_trigger.py:2174`, then does
its post-turn bookkeeping - `_report_abandoned_entries`, `_broadcast_run_lifecycle`,
`persist_event`, and the terminal status row at `:2235` - and only at **`:2281`** calls
`redrain_queued_agents(project_id)`, which is what picks up input that arrived while the run was
busy.

The exception handler at `:2287` computes `already_terminal` (`:2306`) by re-reading the run row and
asking whether it is still `running`. It uses that flag for two things. The first is correct and its
comment argues it well: do not relabel a run that already ended cleanly as `failed` just because
some later bookkeeping raised. The second is the redrain at **`:2358`**, which sits under
`if not already_terminal:` (`:2350`) - and its own comment says it is *"[u]nconditional, where this
was gated on `returned`"*, because "a run that fails releases the task checkout it held exactly as a
run that succeeds does".

So the redrain is skipped in precisely the case where the normal path's redrain was also skipped: an
exception raised **between `:2174` and `:2281`**, when the run is already terminal and `:2281` was
never reached. Nothing recovers it. `agent_trigger.py:1908` states the constraint plainly -
*"Nothing does on a timer: `redrain_queued_agents` is reachable only from project open, settings..."*

**Observed.** `test_stop_endpoint_marks_run_stopped_and_broadcasts_run_stopped` asserts
`queued_entry.delivered_in_run_id is not None` for an entry that arrived behind a run that was then
stopped, and CI reports `None`: the stopped run's `record_agent_output` raised at `:2235`, `:2281`
never ran, `already_terminal` was True, and the entry was never handed to a successor. The
operator-visible shape is a queued message that simply never runs.

`_execute_codex_appserver_run` has the same layout - terminal write, then bookkeeping, then
`redrain_queued_agents` at `:2872` - and reaches the same handler.

**Reproduction** is F285's, since that is what supplies the exception:
`CHURN_DELAY=0.3 PYTHONPATH=scripts/drive py -3.11 -m pytest hub/tests/test_agent_trigger.py -p churn_sessions_plugin -k stop_endpoint_marks_run_stopped`.
In production the exception has to come from somewhere else - a database error, a broadcast failure
- which is rarer, not unreachable, and the handler is indifferent to which.

**Severity B rather than A** because reaching it needs a second failure first. What makes it worth
fixing is the shape: the run is correctly terminal, correctly labelled, correctly broadcast, and the
work behind it is silently stranded with no surface saying so.

**Correction, 2026-09-04 (day D-4, spec R1).** The sentence above -- *"`_execute_codex_appserver_run`
has the same layout ... and reaches the same handler"* -- is **half wrong, and wrong in the
direction that makes it worse.** The layout is the same; the handler is not reached, because there
is no handler. `_execute_run` delegates to `_execute_codex_appserver_run` at `:1824`, **above** its
own `try:` at `:1846`, and returns; and `_execute_codex_appserver_run`'s outer construct is
`try: ... finally:` (`:2536` / `:2873`) with **no `except` clause** -- its only `except` is the
inner one covering spawn/connect at `:2692`. So on that path an exception after the spawn escapes
into a task whose only done-callback is `_background_runs.discard` (`:1231`), which never retrieves
it. After the terminal commit (`:2813`) that is F286 with not even an attempted redrain and no
`logger.exception`; **before** it, the `Run` row stays `running` with `error=None`, `schedule_agent`
refuses every later turn for that agent, and the only recovery is a Hub restart -- app-server runs
never set `Run.pid` (`:1937` is the sole assignment, on the PTY path), so
`reconcile_interrupted_runs` reconciles them to `interrupted` at the next start and only then.

Also corrected: the terminal commit on the normal path is `:2175`, not `:2174`; the handler begins
at `:2282`, not `:2287`; and `already_terminal` is computed across `:2305-2313`. And
`reconcile_interrupted_runs` does not recover the stranded entry even on restart -- it selects only
`Run.status == "running"` (`run_reconciliation.py:60`), and an F286 run is terminal.

Specced 2026-09-04 as `openspec/changes/a-terminal-run-releases-the-queue-behind-it` (R1).

**R2, 2026-09-04 -- F286 is not only a gap, it is a breach of a shipped requirement.** R1's proposal
argued that `agent-conversation-workspace`'s *Repeated delivery failure does not wedge an agent*
(`spec.md:1228`) does not reach this defect, because F286's entry is never *returned*. That holds
for the instance F286 was filed from -- a **stopped** run keeps its input, so nothing is returned --
and only for it. On the **failed** branch `return_run_entries` runs at `agent_trigger.py:2172`,
inside the same `try` and *before* the terminal commit at `:2175`, so an exception in the window
strands input the system had just handed back, and the shipped requirement says of exactly that:
*"Returning an input to the queue SHALL cause the system to attempt its delivery again without
requiring any further operator action."* So the code is in breach today for failed runs, and the
gap is only over never-delivered input and over a second agent parked behind the ended run's
checkout hold.

**R2 also narrowed the window's composition.** F286 and R1 both counted `maybe_generate_title` among
the calls that can raise between `:2175` and `:2281`. It cannot: it wraps its whole body in
`try/except Exception` and documents itself as *"Never raises, never delays a turn"*
(`conversation_titles.py:230-238`). Five calls can, all of them by doing uncaught database work --
`evaluate_run_end`, `_report_abandoned_entries`, `_broadcast_run_lifecycle`, the per-entry
`persist_event`, and `record_agent_output`. `consider_handover_from_run_end`
(`checkpoint_handover.py:301`) cannot raise either. The narrowing does not shrink the defect:
`maybe_generate_title` awaits a ~19s CLI spawn and `except Exception` does not catch
`CancelledError`, which this handler explicitly does -- so it remains the widest *cancellation*
window in the function while contributing nothing to the exception window.

**R3, 2026-09-04 -- two code corrections, one of which changes what a regression test would prove.**

*The `try` this finding names is the wrong one.* F286's paragraph above and R1's proposal both say
the app-server delegation at `:1824` sits above `_execute_run`'s "own `try:` at `:1846`".
`_execute_run` has **two** top-level `try` blocks: `:1846`, whose `except` is `:1870` and whose
failure branch returns at `:1911`, and `:1933`, which is the one paired with the handler at `:2282`
and the `finally` at `:2361`. The delegation returns at `:1842`, above both, so the conclusion --
nothing raised on the app-server path can reach `:2282` -- is unchanged and slightly stronger. The
number was wrong in R1 and confirmed wrong in R2; both rounds shipped it.

*Neither of the two injection points the proposal named is inside the window.* This matters because
a regression test written to them is green with or without the fix. `record_agent_output` is called
at `:2014`, once per streamed output event, and `_broadcast_run_lifecycle` at `:1939` as
`run_started` -- both before the terminal commit at `:2175`. A raise at either lands in the handler
with the row still `running`, so `already_terminal` is `False` and today's code already redrains. To
land in the window the injection has to be predicated: `record_agent_output` with `kind == "status"`
(`:2235` on the PTY path, `:2854` on the app-server one), or `_report_abandoned_entries`, whose
`:2195` call is the only one a run reaching the tail executes.

*And a measurement about the two paths, recorded here because it outlives this change.* Stripped of
comments and blank lines, the PTY success tail `:2169-2281` is 40 statements and the app-server one
`:2807-2872` is 41; `diff` returns a single hunk of a single line, the app-server broadcast's
`**_runtime_failure_fields(outcome, lifecycle_event)`. The two paths' post-turn tails are otherwise
identical text.

**Phase 0, 2026-09-04 (night) -- driven live, and it reproduces exactly as filed.**

Every claim above this line was read from code plus one CI failure. This one was watched. Hub on
**8011** from source (`hub/hub/api/v1/agent_trigger.py` carrying a temporary `AW_F286_INJECT`
guarded `raise RuntimeError` immediately before the in-window status write at `:2235` -- after the
terminal commit at `:2175`, before `redrain_queued_agents` at `:2286`; reverted with
`git checkout` before this entry was committed, never on a commit), a fresh database at
`C:/Users/huida/AppData/Local/Temp/aw-f286/f286.db`, a fresh fixture project
`proj-96849871dd06` at `.../aw-f286/fixture`, one agent `f286a230652` bound to
`claude-haiku-4-5-20251001`. Harness: `.../aw-f286/t_f286_phase0.py`.

| | |
|---|---|
| Run #1 | `run-3be49e8af2f2`, conversation `conv-d76f5e0cdddd`, started `22:07:46.864983Z` |
| Entry behind it | `entry-646cde350c96`, queued `23:07:50` local (`22:07:50Z`) while run #1 was `running` |
| Raise | once, `agent_trigger.py:2239`, logged `ERROR Unhandled error in run run-3be49e8af2f2 for 'f286a230652'` |
| Run #1 terminal | `completed`, exit `0`, `error=None`, `ended_at 22:08:27.734406Z` -- t+41.2s |
| Entry, 5s later | `state='queued'`, `delivered_in_run_id=None`, `delivery_attempts=0`, `waiting_reason=None` |
| Successor run | none. Runs for this agent: **1** |

**0.2 -- the defect as filed.** The run reached a terminal status and the input behind it was left
`queued` with `delivered_in_run_id` null and nothing scheduled. The traceback confirms the raise
landed in the handler at `:2282` with the row already `completed`, which is what makes
`already_terminal` True and skips the redrain at `:2363`.

**0.3 -- nothing recovers it, and "delivered by coincidence" is now a measurement.** The Hub was
left running and untouched and the entry was read every 30 seconds for **4 minutes 5 seconds**
(23:08:33 to 23:12:33 local): `queued`, `delivered_in_run_id=None`, `delivery_attempts=0`, every
single poll, no drift. Then one `PUT /api/v1/projects/proj-96849871dd06/settings` -- the settings
save, byte-identical to what `GET` had just returned, changing nothing -- and the entry was
`delivered` into `run-107d6f280ee2` **0.36 seconds later**. Runs for this agent before the save: 1.
After: 2. So the recovery is real, instant, and reachable only through an unrelated operator action
the operator has no reason to take.

**0.4 -- the fix is the ungating, not a relabel.** Run #1's recorded outcome is `completed` with
`error=None` and `exit_code=0` -- the outcome it actually reached. The `already_terminal` guard did
its first job correctly: an exception in downstream bookkeeping did not relabel a clean run as
`failed`. Only its second job, the redrain, is wrong. Task 1.1 is therefore confirmed as the whole
of the behavioural change on the PTY path: move the release out from under the flag, leave the
relabel exactly where it is.

**What the drive adds that the code read could not.** The stranded entry carries
`delivery_attempts=0` and `waiting_reason=None` -- so `GET /queue/{agent}/status` reports an entry
waiting for no stated reason, and the surface an operator would check to find out why their message
never ran says nothing at all. That is the operator-visible shape of F286, and no test asserted it
before this drive.

**Not driven.** The app-server half (requirement 2, tasks 3.4-3.5) was not driven: it needs Codex,
and Codex is undrivable on this machine. It stays a code-read claim until a test covers it.

**Phase 4.5, 2026-09-05 (night) -- re-driven after the fix, with a control, and the result inverts.**

Task 4.5 asked for phase 0 repeated against the implementing code, expecting the opposite result. It
was run twice: once on the fix, and once with the pre-F286 gate restored in the same checkout, at
the **same injection site**, so the difference between the two is the gate and not the site. Phase 0
raised at the in-window status write; this pair raises three statements earlier, immediately before
`_report_abandoned_entries` -- both sit between the terminal commit and `redrain_queued_agents`, but
they are not the same line, and an A/B at one site is worth more than a comparison across two.

Both drives: Hub on **8011** from `hub/` with uvicorn from source, `AW_F286_INJECT=1`, a fresh
database and a fresh fixture project each time, one agent on `claude-haiku-4-5-20251001`, harness
`scripts/drive/t_f286_phase0_observe.py` unchanged from phase 0. The guarded raise was reverted with
`git checkout` and never committed. Confirmed before believing either drive: no `.py` under
`hub/hub` or `src` was newer than the uvicorn process's start time (`agent_trigger.py` 01:26:04
against a process started 01:26:26; 01:29:33 against 01:29:40).

| | **fixed** (`proj-b70dad75b4b7`) | **control**, pre-F286 gate restored (`proj-5f386b6769de`) |
|---|---|---|
| Run #1 | `run-16b449d4a80a` | `run-262d0b6132ee` |
| Its outcome | `completed`, exit 0, `error=None` | `completed`, exit 0, `error=None` |
| `ended_at` | `00:27:34.803750Z` (t+40.1s) | `00:30:36.386410Z` (t+44.1s) |
| Raise | once, `agent_trigger.py:2290`, `ERROR Unhandled error in run …` | same |
| Entry behind it | `entry-8992a0c0b036`, arrived `00:26:58.040752Z` | `entry-5602402c96cd`, arrived while #1 ran |
| Entry, 5s after #1 ended | **`delivered`**, `run-9d0f885a67c4` | `queued`, `delivered_in_run_id=None`, attempts 0 |
| Delivered at | `00:27:34.943590Z` -- **0.140s after `ended_at`**, no operator action | only after a settings save |
| Left idle | 1 min, 2 polls, `delivered` throughout | **2 min 6s, 4 polls, `queued` every one, no drift** |
| Settings save | **no-op**: runs before 2, after 2 | delivered `0.14s` later into `run-1c8380d8b82c`; runs before 1, after 2 |
| Successor turn | real Haiku turn, `completed` `00:27:42.570573Z`, exit 0, replied `OK` | started by the save |

**0.2 inverted.** The run reaches a terminal status, the in-window tail raises, and the input behind
it is handed to a successor run by the run boundary itself, 140 milliseconds later.

**0.3 inverted.** There is nothing left for the coincidence to recover. The settings save changed
nothing because the entry was already delivered 66 seconds earlier; the harness's
`DELIVERED 0.01s after the settings save` line is an artefact of its phase-0 loop breaking on its
first poll, not a second delivery -- `runs before the save: 2   after: 2` is the line that says so.

**0.4 preserved, which was the point of keeping the relabel gated.** Run #1 is still recorded
`completed` with `error=None` and `exit_code=0` in both drives. The fix released the queue without
touching the outcome, exactly as task 1.1 scoped it.

**The operator-visible surface phase 0 called out is now empty.** Phase 0 found the stranded entry
reporting `delivery_attempts=0`, `waiting_reason=None` through `GET /queue/{agent}/status` -- an
entry waiting for no stated reason. Queried on the fixed drive after the boundary:
`{"waiting_count": 0, "running": false, "waiting_reason": null, "delivery_attempts": 0}`.

**Nothing here disproves anything previously recorded under F286.** The control reproduces phase 0's
measurement at a second injection site three statements earlier in the same window, which widens the
finding slightly rather than narrowing it: the window is skipped as a whole, not from one particular
line onward.

**Still not driven.** The app-server half (requirement 2) remains a code-read claim covered by tests
3.4 and 3.5 only -- it needs Codex, which is undrivable on this machine.

## F287 (C) - `record_agent_output` refreshes a row it has already fully populated, one extra SELECT per output line on the Hub's hottest write path

**Status:** fixed `890cf40` (2026-09-05, day window D-6, the playbook's no-spec repair carve-out).
The three lines are now `db.add(row)` / `await db.commit()` and a comment saying why there is no
third; `hub/hub/output_recording.py:92`.

The 2026-09-04 APPROVALS note had forbidden this fix on the grounds that deleting the refresh
"would very likely turn CI green on its own, by removing the one operation that makes the
shared-connection rollback loud. That is masking, not fixing." That premise was spent -- F285 was fixed at
`d9ad1e0` and the suite is file-backed -- but **F292**, filed the same morning, is a new
intermittent `database is locked` on the same suite, so the masking question was re-asked rather
than waved through, and **answered by measurement**: `scripts/drive/f287_does_the_refresh_hold_a_lock.py`
reproduces the fixture's conditions (file-backed `sqlite+aiosqlite`, WAL, `busy_timeout=30000`,
`expire_on_commit=False`, a session leaked across the boundary, then `dispose()` then
`drop_all`/`create_all`) and gets:

| leaked session | `session.in_transaction()` | `pool.checkedout()` | DDL |
|---|---|---|---|
| with the refresh | True | 1 | OK, 0.0s |
| without it | False | 0 | OK, 0.0s |
| **control: uncommitted write** | — | — | **`database is locked`, after 1.219s** |

The refresh does keep a SQLAlchemy transaction open and a connection checked out; it holds no
SQLite lock, because pysqlite issues no `BEGIN` for a `SELECT`. What reproduces F292's exact error
is an uncommitted *write* held open across the boundary, which a read after a commit is not. So the
fix cannot mask F292 — see F292's own entry, which that control narrows.

Two tests in `hub/tests/test_agent_output_stream.py`, each mutation-checked against the mutation it
exists to catch: `test_recording_an_output_row_issues_no_select_of_the_row_it_just_wrote` captures
emitted SQL and fails if the refresh is restored, and
`test_a_recorded_row_carries_its_timestamp_without_a_refresh` fails with exactly the predicted
`AttributeError: 'NoneType' object has no attribute 'isoformat'` when `default=_now` is dropped from
the column.

**Driven, not only tested.** 8011 restarted from this source on a fresh database and fresh project
`proj-f0caad877055`; one `claude-haiku-4-5` turn (`run-ab93602d5df7`) completed exit 0, error None,
in 8.0s; 4 SSE `agent_output` events each carrying a parsable aware timestamp, 8 persisted rows none
missing one, a real reply, and both terminal `kind="status"` rows from the two distinct call sites.
`scripts/drive/t_d6_output_timestamps_without_a_refresh.py` is the drive.

**Found 2026-09-04 (day D-2)** while triaging **F285**, which is the line's second cost.

`hub/hub/output_recording.py:92-94` ends every write with:

```python
db.add(row)
await db.commit()
await db.refresh(row)
```

Nothing needs the refresh. `async_session_factory` is built with `expire_on_commit=False`
(`hub/hub/db/engine.py:39`), so the commit does not expire the instance; and `AgentOutput` has no
server-side defaults - every column is set explicitly by the caller except `timestamp`, which is
`mapped_column(UTCDateTime(), default=_now, ...)` at `hub/hub/db/models.py:1247`, a **Python-side**
default already applied at flush. The only attribute the broadcast below reads that the caller did
not set is `row.timestamp`, and it is populated before the refresh runs.

The cost is one extra `SELECT` by primary key for **every** agent output row - every streamed line
of every turn, on both runners, through the one function both the self-report endpoint and the
Hub's own spawn loop funnel into.

The second cost is that a redundant query is the only reason F285 is a crash. A refresh is the one
operation that fails loudly when the row it expects is not there; without it the harness artefact
would have been an invisible no-op. That is an argument for deleting the line and *not* an argument
for keeping it as a canary - a canary in the hot path that fires only under a pool the product never
uses is not detection, it is noise.

**Reproduction:** read the three lines. `scripts/drive/staticpool_shared_connection.py` shows the
failure the refresh converts a harmless rollback into.

---

# F227/F228 revisited, 2026-09-04 — a second surface, and one measurement that was scoped too narrowly

Not a new finding. Row 11 was re-driven from scratch on 2026-09-04 by a day window whose
`next_action` sent it to an already-closed row (see the coverage map in `SURVEY.md`), and the drive
independently rediscovered `F227` and `F228` line for line — `q-bfb4a0f5b5ed` declined at
`08:40:58.221` and answered at `08:40:58.248`, then a re-answer of a completed two-question batch
(`qbatch-11edf6108da4`) producing `entry-1c7f4f14a179` and a real spawned run `run-d8c7d4a9b8d4`.
Both findings reproduce at HEAD. The duplicated work is recorded in the log rather than as new
ledger rows, and two things came out of it that the originals do not carry.

**One measurement in F228 is scoped too narrowly, and the correction cuts against it.** F228 says
*"no component anywhere reads a question's `declined` flag — measured across `hub/ui/src/components`,
0 hits"*. That is true of `components/` and it misses `hub/ui/src/lib/pendingQuestions.ts:26`, which
filters exactly this:

```ts
.filter((q) => q.from_agent === agent && !q.answered && !q.declined)
```

So the agent panel's question card **does** drop a declined question, and F228's "forever" applies
to `QuestionsPanel` — the Questions page — rather than to every surface. The finding stands; its
reach is one page, not the whole app.

**The second surface reaches F227 by a different door: a race, not a persistent form.** Because the
card disappears once either resolution lands, an operator can only produce the declined-and-answered
row there by resolving twice before the first request returns — and the card's own guards make that
asymmetric. In `AgentQuestionCard.tsx`:

| control | line | disabled while |
|---|---|---|
| decline (`×`) | `:99` | `isResponding \|\| isDeclining` |
| option buttons | `:127` | `isResponding` |
| number-key shortcut | `:47` | `isResponding` |

The decline button is held during an in-flight answer; nothing holds the answer path during an
in-flight decline. Press `×`, then a number key before the round trip completes, and both land —
`declined: true, answered: true`, and on a completed batch, a spent turn. The fix F227 already
needs (a `declined` guard on `PATCH /questions/{id}`) closes this door too, which is the argument
for fixing it in the Hub rather than in either component.

**Also re-measured, and unchanged:** `answer_labels` is written by the UI
(`api/questions.ts:69-73`) and read by nothing — 0 occurrences in the served bundle, 1 in
`hub/ui/src` and that one is the field's own declaration at `api/questions.ts:22`. Control needles
beside it in the same grep: `multi_select` 5/13, `asker_waiting` 4/23, `batch_size` 1/15. Too small
to be worth a row of its own; recorded here so the next reader of F227's neighbourhood knows the
structured half of an answer currently reaches no reader.

**What held, re-confirmed with real `claude-haiku-4-5` turns** (19 assertions, 0 failures): a turn
told to ask two questions in one `ask_user` call produced two rows on one `batch_id`, `batch_size 2`,
both blocking, and the run stayed `running` the whole time they were outstanding; answering the
first woke nobody (`queue_entry_queued` 8 → 8) and left the second outstanding; answering the second
released the turn, which completed `exit 0` in 23 seconds with the agent's own reply reading
`colour=red size=large` — the evidence that the answers returned through the tool call rather than
the queue; and `asker_waiting` was `true` for both rows while the run lived and `false` for both
once it ended.

---

## F288 (B) - a Hub restart ends a run without releasing anything but that run's own agent, so an agent parked on the crashed run's task checkout is stranded

**Status:** fixed (this commit) [Round 3, 2026-09-23] — reconciliation re-evaluates every agent with queued input in each project a run was interrupted in; see FIXED at the end of this entry. Was: open. Filed 2026-09-05 by the day window's D-1 drive, driving F286's seam independently
of the night window's own A/B harness. No change in `openspec/changes/` covers it.

**This is a breach of a requirement that shipped last night, not an unspecified gap.**
`openspec/specs/agent-conversation-workspace/spec.md:2217`, *A run that has ended releases the queue
behind it*, synced from F286's change nine hours before this drive:

> The system SHALL re-evaluate **every agent holding queued input in a project** whenever a run in
> that project reaches a terminal status, and SHALL do so regardless of whether the bookkeeping that
> follows the terminal status succeeds.

`reconcile_interrupted_runs` writes a terminal status (`interrupted`) to a run in a project and
re-evaluates one agent -- the interrupted run's own. Its third scenario, *An agent parked behind an
ended run's hold is re-evaluated*, is exactly the case measured below. The requirement mentions
restart reconciliation once, and only to say it cannot *recover* input stranded by the other paths
(`:2245-2247`); nothing in it exempts reconciliation from being a terminal-status site of its own.
The change's three rounds read `_execute_run`'s endings, wrote a requirement quantified over every
run in the project, and did not go looking for the third site that ends one.

**The same defect F286 and F90 each closed, at the third site that ends a run.** Every ending inside
`_execute_run` and `_execute_codex_appserver_run` now calls `redrain_queued_agents(project_id)` --
*every* agent with anything queued -- at `agent_trigger.py:1864` (the shared failure tail F286 added),
`:2009`, `:2371`, `:2779` and `:2916`. `run_reconciliation.reconcile_interrupted_runs` ends runs too:
it flips every orphaned row to `interrupted` (`run_reconciliation.py:65`) and then releases only the
interrupted run's **own** agent -- `agents_to_schedule.add((run.project_id, run.agent))` at `:88`,
handed to `_schedule_now`, which calls `schedule_agent(project_id, agent)` for those agents and
nobody else (`:158-162`). An agent parked on the *interrupted run's* task checkout (design D8) is not
among them, and nothing else is on a timer.

The comment at `agent_trigger.py:2360-2371` states the invariant this site does not keep: *"a run
ending frees whatever it held, and the task checkout is only today's instance of that; scoping to
the task would be correct now and silently incomplete for the next hold anyone adds."*

**One crash hides it, which is why it has survived two fixes of the same shape.** The interrupted
run's entry goes back to the queue (`return_run_entries`), its agent *is* rescheduled, that
replacement turn ends normally, and *its* ordinary completion re-drains the project and releases
whoever was parked. Measured here: A interrupted at 08:15:36, A's replacement `run-3a85414acc85`
completed 08:16:16.75, B's entry delivered into `run-fcb115c4ff54` at 08:16:17.03 -- **0.28s**, by
the completion path, not by reconciliation.

**The mask comes off at `inbound_queue.DELIVERY_ATTEMPT_LIMIT` (3).** The third crash withdraws the
interrupted agent's entry, so that agent has nothing to schedule, so no run of its own ever ends, so
nothing ever re-drains -- while the task checkout the parked agent is waiting for is free.

Measured on 8011 from source on `autonomous/2026-09-04-daily` at `e6997e9`, fresh database
(`aw0905.db`), fresh project `proj-aab643e8a931`, two agents on `claude-haiku-4-5-20251001`, task
`task-edd780098418`:

```
08:17:05  d1a running on the task; d1b triggered on the same task -> 200 queued,
          waiting_reason "d1a090658 is already running a turn on task task-edd780098418"
08:17:14  crash 1 -> run-a6c250b82bc0 interrupted; d1a's entry back to queued, attempts 1
08:17:18  crash 2 -> run-329750f61d12 interrupted; attempts 2
08:17:24  crash 3 -> run-7e35d688a50a interrupted; attempts 3
                     entry-ca8f985545 state=withdrawn
                     "delivery failed 3 times; the Hub stopped retrying"
          d1a: waiting_count 0, running false      <- nothing left to schedule
          d1b: waiting_count 1, entry-6318dbfc7dd6 queued, delivery_attempts 0
          no run on task-edd780098418 in any status but `interrupted`
08:18:55  first look; then 240s of polling every 5s -- d1b has NO new run
08:23:39  PATCH /projects/{p}/queue/settings {"hop_budget":6,"turn_delivery_cap":9}
          -> delivered 2.87s later into run-8021881b0f2f
```

**Stranded 6m15s, cleared by a settings save that has nothing to do with it.** That is the exact
signature of F90 and F286: the hold outlives the holder, and only an unrelated operator action
re-drains.

Reproduce:

```bash
export AW_HUB=http://127.0.0.1:8011 AW_PROJECT=<fresh pid> AW_A=<agent A> AW_B=<agent B>
export AW_DB=C:/Users/huida/AppData/Local/Temp/aw0905/aw0905.db
py -3.11 scripts/drive/setup_d1_0905.py <fresh dir>            # project + two Haiku agents
py -3.11 scripts/drive/t_d1_0905_reconcile_strand.py setup     # prints AW_TASK
for n in 1 2 3; do
  bash scripts/drive/d1_0905_restart_hub.sh                    # kill the tree, start from source
  curl -s -H "Authorization: Bearer $AW_KEY" $AW_HUB/api/v1/projects >/dev/null  # drains deferred
  py -3.11 scripts/drive/t_d1_0905_reconcile_strand.py await-running
done
py -3.11 scripts/drive/t_d1_0905_reconcile_strand.py watch      # 240s, no run for B
```

Three crashes is not exotic on the machine this product is developed on: every Hub code change
restarts the process, which is the first line of this repository's own "Still prohibited" table.

The fix is one line in shape -- `redrain_queued_agents(project_id)` per distinct project in
`_schedule_now`, or in place of it -- but it is **not** the D-6 carve-out, whose first condition is
that the change touches no requirement in `openspec/specs/`. This one is a breach of a named
requirement. Whether the existing requirement already covers it and only the code is wrong, or the
requirement needs a scenario naming reconciliation so a test can be written against it, is the spec
loop's question rather than this finding's.

**FIXED 2026-09-23 (interactive session, Round 3, group 3d).** A repair, not a spec track: the
requirement is quantified over every run that reaches a terminal status, `interrupted` is one, and
nothing in it exempts reconciliation — so the code was wrong and the requirement already right.
`reconcile_interrupted_runs` now adds, after its commit, every `(project_id, agent)` with `queued`
entries in each project it interrupted a run in (`_queued_agents_in`, the multi-project form of
`redrain_queued_agents`' query), and hands the union to `schedule_or_defer` as before — so the
pre-address deferral still applies and the parked agent is covered on the deferred path too, which a
direct `redrain_queued_agents` call would have bypassed. Read after the commit, so entries
`return_run_entries` put back count. Scoped to the affected projects, as the requirement is. Tests
(`test_run_reconciliation.py`): `test_reconciliation_redrains_every_queued_agent_in_the_interrupted_runs_project`
and `test_a_deferred_reconciliation_redrain_still_covers_the_parked_agent` — both fail on the old
code (the parked agent is never scheduled). Not driven live: `t_d1_0905_reconcile_strand.py` is the
harness that would show the 6m15s strand closing.

---

## F289 (C) - the queue status route repeats a refusal's own sentence as the current reason long after it stopped being true

**Status:** fixed 2988870 (driven live 2026-09-26, drive Hub :8035: a live holder is named; a stored sentence with no holder reads "the last delivery attempt was refused: ..."). Filed as follows: Filed 2026-09-05 by the day window's D-1 drive, alongside F288 and found by it.

`GET /projects/{p}/queue/{agent}/status` answers with a `waiting_reason`. When none of its live,
read-only checks finds anything, it falls back to the stored refusal of the last delivery attempt
(`inbound_queue.py:183`). That fallback is deliberate and its comment says why -- it is what stopped
"1 waiting" with no explanation at all (F97) -- and the comment even concedes the reason is *"a
record of the last attempt, which a repair since then may already have cleared"*.

What the route never asks is whether the specific, checkable claim in that stored sentence is still
true. Measured during F288's reproduction, for **6m15s** while `d1a090658` was running nothing at all
and every run on the task was `interrupted`:

```
GET /projects/proj-aab643e8a931/queue/d1b090658/status
  {"agent":"d1b090658","waiting_count":1,"running":false,
   "waiting_reason":"d1a090658 is already running a turn on task task-edd780098418;
                     a task's checkout takes one writing turn at a time.",
   "delivery_attempts":0}
```

`d1a090658`'s own status route, at the same moment, answered `waiting_count 0, running false`. So the
Hub simultaneously told the operator that d1a was running a turn and that d1a was running nothing.

**Why this is worse than a stale field.** It is the only diagnosis the operator gets, it names a
holder and a task, and it is checkable -- so it reads as a live measurement rather than a memory. An
operator following it goes to look at d1a, finds it idle, and has nowhere else to go. It is what
makes F288 invisible: the strand presents as a plausible, ordinary wait.

The live branch immediately above (`inbound_queue.py:139`) already asks whether *this* agent is
running. Nobody asks whether the *named* agent is. `tasks_held_by_a_running_turn` is the same
function the refusal was raised from (`agent_trigger.py:900`) and is a read -- so the route could
re-derive this particular reason rather than remember it. Whether the general answer is
re-derivation, an expiry, or clearing the reason when the entry is next re-evaluated is a design
question, not this finding's.

Reproduce: F288's reproduction, above; the route is queried at every step by
`t_d1_0905_reconcile_strand.py`.

**What held in the same drive, measured rather than assumed** — the independent check of F286 that
D-1 was queued for. All on 8011 from source at `e6997e9`, fresh database and fresh project
`proj-aab643e8a931`, two agents on `claude-haiku-4-5-20251001`, **no injected exception and no A/B**:
the night window's harness was deliberately not re-run, because a fix tested by its own author's
harness is what the independent drive exists to check.

| seam | measured |
|---|---|
| a run **completes** with two entries queued behind it, each in its own conversation | released one per turn, `0.17s` and `0.16s` after each run boundary; every entry ended `delivered` with a `delivered_in_run_id` |
| a run is **stopped** by `POST /agent/{a}/stop` with an entry queued behind it | run `stopped` exit 2 at 08:09:42.89, successor started 08:09:43.02 — `0.12s` |
| an agent **parked on another agent's task checkout** (design D8) | `run-f3f3e2e3d2e2` completed 08:11:53.25, `d1b`'s entry delivered into `run-5b1ad56fbd42` at 08:11:53.52 — `0.27s`. The night window recorded this half as tested, not driven; it is now driven. |
| the same, after **one** Hub crash | released, but by the *replacement* turn's ordinary completion (`0.28s` after it ended), not by reconciliation — see **F288**, which is what that mask hides |
| a turn's own outcome after the release | at the timeline's fifty-event cap, all 9 runs across 6 conversations were still in the run-facts map and every conversation's chat named a run the map could label. **F274's eviction did not reproduce at this volume**; these turns are short, and F274's own reproduction stands unchanged |
| a message the Hub gave up delivering | shows in its conversation as `delivery_state: "abandoned"` with the run that last tried, not silently absent (F87 holds) |

Harnesses: `scripts/drive/setup_d1_0905.py`, `t_d1_0905_release.py` (`complete`/`stop`),
`t_d1_0905_checkout_hold.py`, `t_d1_0905_reconcile_hold.py`, `t_d1_0905_reconcile_strand.py`,
`t_d1_0905_released_outcome.py`, and `d1_0905_restart_hub.sh`.

## F290 (RETRACTED, was B) - a run interrupted at Hub restart broadcasts its outcome to nobody, and the client refetches anyway

**Status:** **retracted 2026-09-05 by the day window's D-4/R3 spec round -- this is not a defect.**
Filed the same day by D-3/R2 off a code reading, and refuted by a code reading of the layer above the
one it examined. Kept rather than deleted: the premise it establishes is correct and load-bearing for
the change that cites it, and a finding that was wrong is worth more in the record than out of it.

**Why it is wrong.** The entry below reasons over `onSseReconnect` and notes that `useAgentOutput`
subscribes to it, then concludes nothing covers the chat or timeline queries. **`useSSE` itself
subscribes**, and invalidates everything:

```ts
// hub/ui/src/hooks/useSSE.ts:404-412
useEffect(() => {
  return onSseReconnect(() => {
    queryClient.invalidateQueries()
  })
}, [queryClient])
```

`invalidateQueries()` with no filter matches every query in the cache and refetches every mounted
one (React Query v5, `refetchType: 'active'` by default -- `hub/ui/package.json` pins `^5.62.16`).
`useSSE()` is mounted unconditionally at `App.tsx:216`. The reconnect fires only after a `fetch` to
`/api/v1/events` has succeeded (`useSSE.ts:315-317`), which cannot happen before the new Hub process
serves -- by which time `reconcile_interrupted_runs()` has already written `interrupted`, since it is
awaited before `yield`. So the turn labels itself within one reconnect cycle of the Hub coming back,
with no reload. The behaviour is already pinned by a test: `useSSE-lifecycle.test.tsx:229`,
*"invalidates all queries once the stream actually reconnects (not on the initial connect)"*.

**Still true, and still worth having read for:** everything the entry says about the broadcast
reaching nobody. That is why `run_interrupted` in `eventTargetsAgent` cannot serve the restart case,
which is what sent R3 looking for the case that *does* justify the four terminal events -- **F291**.

**Not driven either way.** Task 0.4 of `2026-09-05-the-conversation-carries-its-own-run-facts` still
measures it, and is now written to expect seconds rather than "never"; if it reads "never", this
retraction is what is wrong and design D8 goes with it.

---

**The original entry, unedited, follows.**

`reconcile_interrupted_runs()` is awaited inside the FastAPI lifespan at `hub/hub/main.py:350`. A
lifespan startup runs to completion **before uvicorn serves a single request**, so at the moment it
calls `sse_manager.broadcast(run.project_id, "run_interrupted", payload)`
(`hub/hub/run_reconciliation.py:117`) there cannot be an SSE subscriber: the browser's stream died
with the previous process and its reconnect cannot succeed until startup finishes.
`SSEManager.broadcast` pushes into the per-project subscriber queues and returns
(`hub/hub/sse.py:86-103`) -- there is no buffer, no replay and no `Last-Event-ID`. The event is not
delayed; it does not exist for that client.

Downstream, `useAgentTimeline` invalidates on `run_interrupted` (`agents.ts:389-407`), so the run
facts map that carries the turn's terminal label is refetched **on an event that never arrives**.
Nothing else covers the gap: the query sets no `staleTime` and no `refetchInterval`
(`agents.ts:420-425`), and the app disables focus refetching globally
(`main.tsx:11`, `refetchOnWindowFocus: false`). `useSSE` does expose `onSseReconnect`
(`useSSE.ts:132`) and `useAgentOutput` subscribes to it for exactly this shape of gap
(`agents.ts:557`, "a one-shot reconciliation poll after the stream was down (M21)") -- but that
reconciles the raw output line buffer, and an interrupted run writes no terminal status line at all,
which the corpus states as a deliberate carve-out
(`openspec/specs/agent-stream-events/spec.md:393-400`). So there is no line to poll and no event to
receive.

The visible consequence is one turn that stays presented as unfinished, in a conversation the
operator is looking at, until they reload the page or some unrelated event for that agent lands.
This is distinct from **F274**: F274 is the map missing a run it should contain; F290 is the map
never being re-read. Both surface as a turn with no outcome, which is presumably why the second hid
behind the first.

Where it is being handled *(superseded by the retraction above: D8 now adds no subscription, and
task 3.4 says so)*: `2026-09-05-the-conversation-carries-its-own-run-facts` design D8 and
task 3.4 add a reconnect-triggered invalidation to both chat hooks, and its second ADDED requirement
is stated over the reconnect rather than over the event so a client cannot satisfy the letter while
failing this case. That change does **not** repair `useAgentTimeline`, whose own invalidation on
`run_interrupted` stays dead -- acceptable only because after that change nothing reads the timeline
route's run facts map (design D5). If that map ever regains a consumer, this finding is live again
for it.

Reproduce (not yet run): task 0.4 -- conversation open in a browser, restart the Hub while a run is
`running`, touch nothing, and time how long the turn stays unlabelled. Task 3.5 is the narrower
check: watch the reconnected stream for a `run_interrupted` frame and confirm none arrives.

## F291 (C) - a run that fails before its process spawns tells the conversation nothing, and the one path where that is total leaves the turn silent

**Status:** **fixed** by `an-undelivered-message-says-how-its-last-attempt-ended` (archived `26b98cb`, 2026-09-29, driven live; DECISIONS `F291-F273-run-facts`): the abandoned turn renders the run's own `error` beneath the Hub's reason, and `queue_entry_abandoned` reaches the chat hooks. Ledger closed 2026-10-12 (night iteration 24): `test_an_undelivered_message_says_why.py` passes. Superseded text: **still open** after `2026-09-05-the-conversation-carries-its-own-run-facts` shipped,
and that change's own task 7.1 - which instructs the implementer to mark this `fixed` - is wrong.
Re-driven 2026-09-09 against the built code: the run facts for the failing runs **are** now in the
chat response, and the screen is unchanged, because `groupIntoTurns` partitions on
`delivery_state === 'delivered'` and an abandoned entry never becomes a turn there is nothing to
label. See *Phase 6* at the end of this entry. Corrected once before, on 2026-09-09 by the drive its
own `Reproduce` line asked for: the mechanism is confirmed to the letter - no output row,
`run_failed` unheard by the chat hooks - and the *symptom* stated in the heading and below is wrong:
there is no silent turn, because on this path there is no turn at all. Read both sections at the end
of this entry before acting on the rest of it; the reproduce recipe below is also wrong and one of
them says why. Filed 2026-09-05 by the day window's D-4/R3 spec round, while re-deriving why the
`2026-09-05-the-conversation-carries-its-own-run-facts` change adds four run-terminal events to the
chat hooks' SSE predicate. **Derived from the code, not yet driven** -- every line below is a
citation on this checkout; task 0.5 of that change is written to measure it.

`useAgentChatHistory` and `useAgentRecentChat` refetch on `message_created`, `agent_output` and five
queue events (`hub/ui/src/api/agentChat.ts:272-290`). They do not listen to the run lifecycle events,
which is fine for every run whose process actually started: the terminal status row is written by
`record_agent_output` (`agent_trigger.py:2325`) **after** the run row's own commit (`:2265`), so the
`agent_output` that row broadcasts triggers a refetch that reads a run which has already ended.

A run that fails **before** the spawn has no such row. The pre-spawn `except` block
(`agent_trigger.py:1960-2010`) sets `run.status = "failed"`, commits, broadcasts `run_failed`, and
calls `record_agent_output` nowhere -- all four call sites in that file (`:2104`, `:2325`, `:2645`,
`:2898`) are after the spawn. Its remaining broadcasts are `queue_entry_queued` for each entry
`return_run_entries` hands back, and `queue_entry_abandoned` for each one it gives up on. The first
is in `QUEUE_EVENT_TYPES` and would refetch the conversation; the second is not.

So the gap is exactly the case where nothing is handed back: an entry at `DELIVERY_ATTEMPT_LIMIT` is
abandoned rather than requeued (`inbound_queue.py:222-235`), and if every entry the run carried is at
the limit, `requeued` is empty. The only two events that fire are then `run_failed` and
`queue_entry_abandoned`, neither of which the chat hooks hear. The operator is left with a turn
holding a delivered message, no outcome and no explanation, until unrelated traffic for that agent
arrives, the SSE stream reconnects, or they reload.

Two smaller things fall out of the same reading, recorded rather than filed separately:

- `queue_entry_abandoned` is absent from `QUEUE_EVENT_TYPES` while the response it changes is the
  chat response -- `_queued_entries_for` returns abandoned entries deliberately (F87,
  `agent_chat.py`'s own docstring: *"a dropped input and a delivered one left the conversation
  looking identical"*). Adding `run_failed` closes the pre-spawn case; it does not close an
  abandonment that happens on any other path.
- `useSSE`'s own handler *does* invalidate on these events, but at `['project', pid, 'queue', agent]`
  and `['project', pid, 'agents']` -- never the chat key.

Where it is being handled: task 3.1 of `2026-09-05-the-conversation-carries-its-own-run-facts` adds
`run_failed` (with `run_completed`, `run_stopped`, `run_interrupted`) to `eventTargetsAgent`, which
closes the case above. The `queue_entry_abandoned` omission is left open by that change.

Reproduce (not yet run): task 0.5 -- bind an agent to a runner whose binary does not exist, deliver a
message whose entry is already at `DELIVERY_ATTEMPT_LIMIT`, and watch the conversation with nothing
else touching it.

### Driven 2026-09-09 (night window, iteration 14) — and the predicted symptom is wrong

Task 0.5 of `2026-09-05-the-conversation-carries-its-own-run-facts` said to reproduce this by
binding an agent to *a runner whose binary does not exist*. **That recipe cannot work**, and finding
out why is the first result: `probe_agent` refuses a CLI missing from PATH at
`agent_trigger.py:665`, before a `Run` row exists, so no run fails and there is nothing to observe.
The pre-spawn `except` block is reached by the **other** branch of the probe — a *pinned* CLI, where
`present = os.path.isfile(x) and os.access(x, os.X_OK)` (`launchability.py:83`) and `X_OK` is true
on Windows for any file that exists. Pinning an agent's CLI at an ordinary text file therefore
passes the probe and fails at the spawn, which is the exact case the `except` block's own comment
names. Agent `ghost050237`, CLI pinned at `C:\Users\huida\aw-f274p0\README.md` (pinned through
`POST /session/sync`, which is not an operator surface — see the caveat at the end).

The mechanism is confirmed, in full:

```
run-7bf1a981de5c, run-b00de2d65b9b, run-f39ebe679836   three attempts, all `failed`,
                                                        the whole cycle inside 3 seconds
run_failed summary   "Run failed: %1 is not a valid Win32 application."   (WinError 193)
run_failed data      {"agent": "ghost050237", "run_id": ..., "conversation_id": ...}
GET /agents/ghost050237/output                          0 rows
entry-ca2727228db7   delivery_state="abandoned"
                     abandoned_reason="delivery failed 3 times; the Hub stopped retrying"
```

Zero output rows: `record_agent_output` really is never called on this path, and `run_failed` really
does carry `agent`, which is separately what task 3.2 of that change asks someone to confirm.

**And then the symptom this entry predicts does not appear, because the thing it predicts it for
does not exist.** This entry says the operator is left with *"a turn holding a delivered message, no
outcome and no explanation"*. Watched in the served bundle, conversation open, nothing touching the
page for 75 s:

```
t=0.0s   turn boundaries 0   labels {failed 0, stopped 0, interrupted 0, completed 0}
         ... and it never changes for the whole watch
05:18:32 a second message sent into the same conversation (run-14aa9f390ec4)
final page, no reload: two blocks, each reading
         "NOT DELIVERED / delivery failed 3 times; the Hub stopped retrying"
         turn boundaries still 0
```

**There is no turn.** An abandoned entry comes back from `_queued_entries_for`, and
`groupIntoTurns` puts undelivered entries in `pending`, not in a turn — so on this path `run_failed`
has nothing to label. The operator is *not* left with silence either: the second failure's
NOT DELIVERED block appeared **live, with no reload**, because the three delivery attempts each
broadcast `queue_entry_queued` and `queue_entry_delivered`, both of which the chat hooks do listen
to, and the last refetch reads the entry in its final abandoned state.

So this finding is **corrected, not retired**. What is true: the pre-spawn path writes no output row
and the chat hooks do not hear `run_failed`. What is false: that this leaves an unlabelled turn.
**Task 3.1 of that change is still probably right to add the four terminal events — the map is
moving onto the chat response and has to be refreshed by something — but the reason written into
its task text, and into this entry, is falsified as stated, and phase 1 must not transcribe it into
a source comment.** Re-derive the reason before writing it.

Two caveats on the fixture, stated because an unstated one is how a measurement becomes folklore:

- the CLI pin was applied through `POST /session/sync`, whose own module docstring says its callers
  are gone and it is reached today "chiefly the test suite". There is no operator-facing way to pin
  a runner CLI — `OperatorAgentCreate` has no `config` field and `Runner.cli` is the runner *kind*.
  So this reproduction is reachable in the product only by a path an operator does not have.
- after that sync, `ghost050237`'s composer rendered **`Model: Sonnet 5`** while its bound `Runner`
  is `claude-haiku-4-5-20251001`. Not filed: the sync is the contamination, and no clean-fixture
  measurement was taken. Worth one minute on a clean fixture before anyone trusts the composer's
  model line.


### Phase 6 - the change shipped, and this finding is untouched (2026-09-09, night window, iteration 17)

Task 6.3 of `2026-09-05-the-conversation-carries-its-own-run-facts` calls the 0.5 re-run "a
before/after, and 3.1 is what changes it". It is a before/after and **nothing changed.**

Same fixture, agent `ghost050237`, CLI still pinned at `C:\Users\huida\aw-f274p0\README.md`. Two
messages, `06:32:16` and `06:33:12`, each burning its three delivery attempts inside a second. The
**server** half did change, exactly as designed:

```
GET /projects/<pid>/agent/ghost050237/chat/conv-f1a8c58f1fb9
  entries 2, both carrying a run_id
  runs {"run-2792ffd0ccb0": {"status": "failed", ...},
        "run-94b577775443": {"status": "failed", ...}}     <- absent entirely before the change
```

The **screen** did not. Browser attached for 80 s with the second message sent live at `06:33:12`,
nothing else touched:

```
t=0.00s  boundaries 0   labels {failed 0, stopped 0, interrupted 0}   ... and never changes
final page, reopened: two "NOT DELIVERED / delivery failed 3 times; the Hub stopped retrying"
                      blocks, 0 turn boundaries, 0 terminal labels
```

**Why, in one line of the client, read rather than inferred.** `groupIntoTurns`
(`hub/ui/src/lib/agentTimelineModel.ts:45-62`) splits on `delivery_state === 'delivered'` and puts
everything else in `pending`. It never looks at `run_id`. An abandoned entry carries a run id, and a
run row now describes that run as `failed`, and neither fact can reach the screen because the entry
is not in a turn. Adding the four run-terminal events to `eventTargetsAgent` (task 3.1) refreshes a
map that has no renderer on this path.

So the correction stands and is now sharper: **this finding cannot be closed by anything that
improves the run-facts map.** Closing it means either rendering `pending` entries as turns, or
carrying the failure onto the NOT DELIVERED block itself - a product decision, not a repair. What
the operator gets today is the abandonment banner, live, with no reload; what they do not get is the
run's own outcome, and that is unchanged from 2026-09-05.

### Re-driven 2026-09-09 (day window, D-1) — both halves of the open question confirmed, and one citation was wrong

Asked from the operator's side this time, on a Hub carrying all three of the night's changes at
once, with a fresh project and a fresh pinned-CLI agent. Three deliveries, three `failed` runs
inside 0.1 s each, all three entries `abandoned`.

**The chat response carries the run facts and the screen still shows no turn.** `GET
/agent/<agent>/chat` returned `entries=3 runs=3`, every run `status: failed` — F274's server half
doing exactly what it was built to do. The served bundle on the same conversation: **0 turn
boundaries, 0 stat lines, 0 terminal labels, and 1 `NOT DELIVERED` block.** So the facts are in the
payload and nothing renders them, which is the claim, measured rather than argued.

**The two code citations, checked line by line.** `groupIntoTurns` partitions on
`delivery_state === 'delivered'` at its first two statements and reads `run_id` only *inside* the
delivered branch, as a grouping key — an abandoned entry cannot reach the turn list at all.
`agent_trigger.py`'s pre-spawn `except` runs `return_run_entries` → `db.commit()` →
`_report_abandoned_entries` → `_broadcast_run_lifecycle(..., "run_failed")`, in that order, so the
commit does precede the broadcast.

**One citation carried in the ledger and in three state files is wrong.** The model is at
`hub/ui/src/lib/agentTimelineModel.ts:45-62`, not `hub/ui/src/components/agents/`. The line
numbers are right and the directory is not; anyone opening the stated path finds nothing and has to
go looking. Corrected here rather than in the older paragraphs, which are dated.

**Still open, and still for the reason the night gave:** the symptom in this entry's heading is
wrong (there is no silent turn, because there is no turn), and the operator *is* told, by the
banner, through queue events the chat hooks already listen to. What remains unbuilt is whether an
abandoned entry should become a labelled turn at all — a product question, and not one with an
obvious fix.



---

## F292 (B) - the fix for F285 traded a deterministic rollback for an intermittent lock, and the mitigation written for it did not hold

**Status:** fixed b630252 — **0 F292 in 16 consecutive completed post-fix `ci.yml` runs** (`b630252` through `6c0a467`, 2026-09-21 22:58Z to 2026-09-22 09:09Z), past the 11-run bar; at the 22.6% pre-fix rate that is p ≈ 0.017 (0.774^16). 15 green; the 16th (`45d769f`) was red, but from an F394 hang, not a lock (no `database is locked` in its log). Tally at the foot of this entry (2026-09-22 interactive). Before it: still reproducing on the mitigated tree — re-measured 2026-09-15 (night `ledger-conflicts`) over every `ci.yml` run created after 2026-09-13T02:50Z, where the table at the foot of this entry stops: **19 of 84 completed runs** (22.6%) errored at setup with `database is locked` on `BEGIN IMMEDIATE`, one of them on `master` at `f28bc31` (run `34822760456`), and the mitigation `af69a27` is an ancestor of every sha measured; still the same three tests in `test_reviewer_is_not_the_author.py` and `test_flow_fires_a_review_turn.py`, and `hub/tests/conftest.py` is unchanged since 2026-09-12. The other 4 red runs in that window are F314's event-loop `RuntimeError` and nothing else; 3 of the 19 carried it as well.

**Re-measured 2026-09-20 (interactive session, at the operator's request for a verification scan) —
the rate escalated far past 22.6%, and the consequence is now structural.** Over the `ci.yml` runs
on `autonomous/2026-09-17-daily`: green through `7811bf4` (2026-09-19T22:03Z), then **16 of 16
completed runs failed, from `3b7718d` (22:18Z) to `aa9983f` (2026-09-20T14:13Z)** — 20 hours, 14
pushes. Four spanning that range were opened and read (`3b7718d`, `a93f95d`, `14f8dae`, `aa9983f`);
**all four carry `sqlite3.OperationalError: database is locked` at *setup*, and nothing else
explains `3b7718d`** — it predates the F392 regression, and the summary lines read
`4439 passed, 20 skipped, 1 error` and `4450 passed, 20 skipped, 2 errors` with **no `FAILED`
line at all**. Still the same two files this entry already names. The run on `09237f6`
(2026-09-20T14:21Z) then went **green**, so the failure is not deterministic — but a flake that
takes 16 consecutive runs is not a flake the loop can ride out.

**Why this is worse than a red badge, and why it belongs at the top of a plan rather than in a
queue.** The day window's `d7-gate` merges to `master` only on CI success for the exact HEAD sha.
For 20 hours no sha had one, so the gate could not open under any circumstances, and **`master` sat
38 commits behind** while nine night commits and five day commits were pushed onto a tree that CI
could not pass. Nothing in either window reads CI — `night-window.md` step 3 checks the suite
**locally**, where it is green — so the loop is *structurally blind* to this: it cannot notice, and
it did not. The 2026-09-19 gate's recorded reason (*"CI never concluded in time"*, `STATE-day.json`
`d5`) is a different and now-superseded explanation for the same stuck gate.

**Status as written 2026-09-11:** **mitigated 2026-09-10, and as of 2026-09-11 the mitigation is measured and
REFUTED AS A FIX: F292 reproduced on the mitigated tree at `f51ec21`, and again at `8d227de`
(run 34583319728, 2026-09-11 09:16Z). The classified rate was 1 in 17 runs with the mitigation
against 11 in 41 without, which iteration 2 reported as disfavouring "it changed nothing" at
one-sided p ~ 0.036; **the second reproduction takes it to 2 in 18, and the rate half of this
measurement should now be read as consistent with no effect.** Iteration 5 recomputed both by
**Fisher exact, one-sided** and got p = 0.069 for 1/17 and p = 0.159 for 2/18 — so even the first
number was weaker than recorded under this test, and the second is not evidence of anything.
Iteration 2 did not state which test produced 0.036; its figure is left standing rather than
overwritten, because the disagreement is about method and the arithmetic of only one of them is on
the record. **Either way the conclusion is the one the section below reaches on other grounds**, and
it does not rest on the rate. What the second
reproduction does add is a repeat, not a rate: it is the **same test file** as the first
(`test_reviewer_is_not_the_author.py`, `ERROR at setup`, `4041 passed, 18 skipped, 1 error`), on a
**documentation-only commit** whose diff touches no Python at all — so nothing about the tree under
test explains it, and the fixture pair is the same one both times. The useful result is not the rate: the holder arrives BEFORE the
schema reset begins, which is what surviving `BEGIN IMMEDIATE` means. See the last section, *"The
rate, measured 2026-09-11"*.** Read
*"The reset was never one transaction"* at the foot of this entry before any other part of it: the
`app` fixture's `async with engine.begin()` was **never one transaction**, the ~90 `DROP`s ran in
autocommit, and a competing writer taking the write lock between two of them reproduces CI's exact
signature with no dead worker thread and nothing holding the file for 30 seconds. Fixed by
`BEGIN IMMEDIATE`, gated and mutation-checked. That section also records **two hypotheses tested and
refuted** (a second synchronous engine; `SQLITE_BUSY_SNAPSHOT`) so nobody pays for them again, and
notes that this entry has been carrying **two different failure modes under one heading** — an
unbounded hang with no `busy_timeout` involved, and a `database is locked` that *is* a busy-timeout
expiry. The paragraph below describes the first; CI fails with the second.

Root cause not fixed, but the mechanism now has a concrete, code-level, forced-
reproduction-backed candidate: an `aiosqlite` connection's dedicated worker thread crashes (and dies
permanently) if it tries to report a result back to an event loop that has already closed, and any
later reuse of that same connection then awaits a `Future` nothing will ever resolve -- unbounded, no
`busy_timeout` involved. Traced to a real, un-awaited background-task call site
(`agent_trigger.py:1190`) reachable from both of F292's historically-failing test files, and to a gap
in the teardown safety net meant to prevent exactly this. See the entry's most recent section for the
full chain. Not fixed this session -- it is a run-cancellation design issue, not a one-line patch.
The standing (main-engine registry) mechanism was recorded here as **falsified for all four
occurrences that carried the instrument**; that reading is **narrowed as of 2026-09-08 (day d1a,
n=5 negatives)**. The registry is emptied on SQLAlchemy's `close` event, which fires *before* the
close is attempted and unconditionally (`pool/base.py:877-886`), and the close failure is swallowed
into the `sqlalchemy.pool` logger -- so a product-engine connection still holding the file is
*guaranteed* to print `no connection checked out`. The negative is structural, not evidence.
Narrowed rather than retracted: it does still rule out a connection the pool believes is checked
out, which is exactly the state the mitigation at `conftest.py:464` was written for, and the one
state never once observed at a failure. The alembic-engine half of H1 is separately measured and
**ruled out as a general mechanism** (it cannot explain an occurrence in a test file collected before
`test_migrations.py` ever runs) -- two real, independent defects in `hub/hub/migrations/env.py` were
fixed anyway (a 6x-shorter busy timeout than the main engine; a dispose skipped on any migration
failure), covered by two new tests, but they are not this finding's fix, and are unrelated to the new
hang. Filed 2026-09-05 by the day window's D-5 while reading this branch's CI for the review page.
**Superseding reading, 2026-09-10 (occurrences #13-15, n=3 unanimous):** the per-stage census fired
for the first time and its early stages came back **empty**, which is the branch `d1c` called the
strong result. The dispose-before-drop mitigation is confirmed working and cannot be the fix; the
child-process candidate is demoted (neither erroring file mentions `subprocess`); and the un-awaited
`asyncio.create_task(_execute_run(...))` at `agent_trigger.py:1190` is promoted to the candidate the
evidence points at, because all three predecessors are flow-fires-a-review tests. Read the last
section of this entry before any other part of it.
**A 2026-09-06 occurrence hung for 3.5 hours instead of failing** -- every occurrence before it, and
every one this entry originally described, failed within 8-14.5 minutes; "bounded failure only" is
now a stale characterization. The night N-1 checkout registry **has fired in CI five times and
returned an identical negative every time** (the eighth occurrence, 2026-09-08, run `34164645184`,
is the first on `master`). That is consistent with the new mechanism -- but it is equally consistent
with a product-engine connection SQLAlchemy silently gave up on, so it discriminates between them
not at all. **A second instrument shipped 2026-09-08 (day d1b)** to close that blind spot; see the
section at the end of this entry. It is an instrument, **not a fix**, and the finding stays open. Read the sections in order -- each narrowing is
superseded by the one that follows it, and the most recent section supersedes the "no hangs" framing
of everything before it. **Measured 2026-09-08 (day `d2`), the number this entry never had: 11
failures in 54 completed `ci.yml` runs across all branches, 2026-09-07T00:00Z -> 2026-09-08T08:26Z
= 20.4%, and every one of those 11 is this defect -- CI redness currently has exactly one cause.
The occurrence count is corrected from 8 to at least 22, earliest 2026-09-04T22:02Z. Method,
denominators and the per-run classification are in the final section.**
**The instrument fired 2026-09-08 (occurrence #9, run `34205295463`, sha `66861a4`) and both new
halves came back negative: `sqlalchemy.pool` logged no error all session, and the single connection
still holding an open sqlite3 handle at failure was the one that had just attempted the DROP -- the
victim, not the holder. That kills d1a's silent-discard hypothesis. It does NOT establish that no
suite connection held the file, because `_f292_ever_seen()` is sampled once at report time, thirty
seconds (a whole `busy_timeout`) after the DROP began; the holder had that long to close and be
collected. Read the last two sections: the next step is to sample ever-seen at every stage, not to
conclude from this one.**
**That hole is closed as of 2026-09-08 (day `d1c`): the census is now taken inside
`_f292_snapshot()`, so `[before dispose]` and `[before drop_all]` carry one too, and a holder that
releases during the busy-timeout wait can no longer hide behind the sampling time. Mutation-checked
against the pre-change conftest -- the two throwaway tests fail on it and pass on this -- and
measured on the green path at 76 us per snapshot, ~0.6 s across the suite. Still an instrument,
still not a fix: the holder remains unnamed and the entry stays open. The next occurrence's report
is the first one whose silence would mean something.**

**Corrected 2026-09-08 (day `d5`), by two occurrences that concluded after the paragraph above was
written.** #10 (`34205968391`, sha `8868088`) and #11 (`34206652706`, sha `a84e608`) both printed
`sqlalchemy.pool` ERROR records -- 1 and 3 of them, every one the same `Exception during reset or
similar` ending in `asyncio.exceptions.CancelledError` raised inside aiosqlite's `rollback`. So
**#9's silence was a property of that session, not of the mechanism, and "that kills d1a's
silent-discard hypothesis" above is too strong.** There is now a measured way for a product-engine
connection to be abandoned with its transaction unresolved: a rollback cancelled mid-flight in
`_finalize_fairy`, followed by an `invalidate()` whose terminate only *queues* the real close. It is
a mechanism that fits, not the holder named -- both runs still show one `idle` handle at failure and
both are late-only censuses. Read the section at the end of this entry.

**Narrowed 2026-09-05 (day D-6), by a control run for a different finding.** Still open, still not
reproduced from the suite itself, but the space of mechanisms is smaller than it was this morning.
`scripts/drive/f287_does_the_refresh_hold_a_lock.py` rebuilds the `app` fixture's conditions
exactly -- file-backed `sqlite+aiosqlite`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=30000`,
`expire_on_commit=False`, a session left un-closed by a notional previous test, then
`await engine.dispose()`, then `drop_all`/`create_all` on a fresh connection -- and varies only what
the leaked session did last:

- leaked session that **committed** (with or without a following `refresh`): `drop_all` succeeds in
  **0.0s**. A leaked read, and a leaked idle connection, do not block the reset. In WAL a reader
  never blocks a writer, and pysqlite emits no `BEGIN` for a `SELECT` at all.
- leaked session holding an **uncommitted write** (`flush()`, no `commit()`): `drop_all` fails with
  `OperationalError: (sqlite3.OperationalError) database is locked`, after the DDL connection's busy
  timeout expires — **byte-for-byte the error CI reports, at the same statement.**

So F292's leaker is a session that **wrote and did not commit**, held across the test boundary — not
merely a connection left open, and not a reader. That is consistent with the entry's own
fire-and-forget-task hypothesis and rules out the milder shapes of it. It also explains why
`be6a70d`'s `dispose()` did not hold: `dispose()` closes a pool's *idle* connections and cannot
reclaim one a running task has checked out mid-transaction, which is precisely the only case that
locks. **The diagnostic this entry asks for should therefore log the pool's checked-out count *and*
whether any connection is in a transaction, immediately before the `drop_all`.**

**Instrumented 2026-09-05 (night N-1) -- and the diagnostic this entry asked for is blind.** Still
open, still not reproduced from the suite. What follows is measurement; the mechanism sentence at
the bottom of this entry is still a hypothesis.

*The asked-for measurement could never have named the holder.* The paragraph above asks for "the
pool's checked-out count immediately before the `drop_all`". `AsyncEngine.dispose()` does not empty
the pool, it **replaces** it -- the pool object's identity changes and the new pool's counters start
at zero, while a connection checked out from the old one stays open and keeps holding the file.
Measured directly: after a dispose with one connection still out, `pool.status()` reads
`Current Checked out connections: 0`. In the forced reproduction below it read `0` even *before* the
fixture's own dispose, because the previous test's autouse teardown had already disposed once. So at
that line the count is zero in precisely the situation being diagnosed.

*What is in the tree instead.* `hub/tests/conftest.py` now keeps its own registry of checked-out
connections, fed by `checkout`/`checkin`/`close` listeners registered on the **engine** rather than
the pool -- measured to survive the replacement in both directions: SQLAlchemy re-applies
engine-level pool listeners to the new pool, and a connection checked out from the old pool still
dispatches its checkin to the old pool's copy of them. For every connection still out it records the
nodeid of the test that checked it out, the asyncio task and its coroutine's qualified name, up to
six frames of the call site from this repository, and a weakref to the `_ConnectionRecord` so the
transaction state can be read later. It is printed to stderr **only when the schema reset raises**,
so a green run is byte-for-byte as quiet as before, and it changes nothing about what the fixture
does. This is not the DEC-1 repair and does not pre-empt it.

Three implementation facts, recorded so the next attempt does not re-derive them:

- The DBAPI connection object is **not weakref-able** -- SQLAlchemy's `AdaptedConnection` uses
  `__slots__` with no `__weakref__`. The `_ConnectionRecord` is, and reaches the connection.
- `aiosqlite.Connection.in_transaction` is a plain forward to `sqlite3.Connection.in_transaction`.
  It schedules nothing on the connection's worker thread and touches no event loop, so it is safe to
  read from the fixture after the loop that created the connection is gone.
- SQLAlchemy runs the synchronous half of every async call **inside a greenlet**, and a greenlet's
  frame chain ends at its own entry point. Walking `f_back` from a pool event therefore reaches the
  pool and stops, with the code that opened the session unreachable on the parent greenlet's stack.
  Without a hop to `greenlet.getcurrent().parent.gr_frame` the origin names only the listener itself.

*The instrument is proven, on a forced reproduction.* A throwaway two-test file -- written, run and
deleted inside this iteration -- leaked exactly the shape D-6's control established (a session that
wrote and did not commit, held across the test boundary). The next test's `app` fixture then failed
with **the error CI reports, at the same kind of statement**:
`sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked` on
`DROP TABLE requirement_drift`, `ERROR at setup`, 34.87s. The diagnostic printed:

```
F292 DIAGNOSTIC: the schema reset failed. Who was holding the database:
  [before dispose] pool.status()='... Current Checked out connections: 0'
  [before dispose] held by tests/test_zz_f292_diagnostic_probe.py::test_one_leaks_an_uncommitted_write
                   [task: Task-7 running test_one_leaks_an_uncommitted_write] -> IN TRANSACTION
  [before dispose]     at test_zz_f292_diagnostic_probe.py:22 test_one_leaks_an_uncommitted_write
  ... same at [before drop_all] and [at failure] ...
```

Culprit test, task, source line and transaction state -- against a failure reported at the victim.

*Negative result, and it is evidence.* **F292 does not reproduce locally from the two files CI
blamed, and there is no contention in them at all.** 15 consecutive runs of
`tests/test_flow_fires_a_review_turn.py tests/test_reviewer_is_not_the_author.py` under `py -3.11`:
`21 passed` every time, 13.46s-14.87s. Then the same pair with `busy_timeout` temporarily lowered
from 30000 ms to **50 ms** -- which turns any contention, however brief, from a wait into an
immediate failure -- passed again. Sub-millisecond contention inside those two files is therefore
ruled out, not merely unobserved. Whatever holds the file runs **before** them in full-suite order.

That also disposes of one cheap explanation. CI runs plain `pytest tests/ -v` from `hub/` with no
`pytest-randomly` installed and no `-n`, so the order is deterministic run to run: the intermittency
is **timing**, not ordering, which is what a fire-and-forget task would look like and what a
different test file's leak would not.

**The whole suite at `busy_timeout=50`, 2026-09-06 (night N-1b) -- a clean negative, and a large
one.** The obvious next step after the two-file control was the same 600x reduction applied to
*every* test, so that any contention anywhere in the suite fails instead of waiting. It was run
detached (WMI `Win32_Process Create`, so it survived the iteration boundary that killed the first
attempt) with the pragma forced by a scratch pytest plugin rather than an edit to
`hub/tests/conftest.py`, whose behaviour DEC-1 has not authorised anyone to touch.

```
3968 passed, 86 skipped, 249 warnings in 1054.76s (0:17:34)   EXIT=0
```

Zero `database is locked`, zero `ERROR at setup`, zero `OperationalError`, and the failure-path
diagnostic added above never printed -- because the schema reset never raised.

*The override was in force, not merely announced.* The plugin prints a banner, which proves only
that it attached. Measured separately by reading the pragma back from a real session inside the
`app` fixture: **30000 without the plugin, 50 with it.** So for a full pass, no connection anywhere
in the Hub suite held the database file long enough for the next test's `drop_all` to wait even
50 ms.

**Two cautions, both load-bearing.**

1. *This is not a green check.* The pragma is not the shipped one, and a pass here says the suite
   has no contention on **this machine, at this moment**, not that CI has none. The finding stays
   open; the merge gate's condition 3 is unchanged.
2. *Nothing was attributed, because nothing failed.* The instruction anticipated that one failed
   schema reset cascades into tests that are only its victims, and that only the FIRST failure may
   be blamed. That caution never had to be applied.

*What it costs the hypothesis.* The mechanism sentence at the bottom of this entry -- one test's
connection still holding the file when the next test's `drop_all` runs -- now has to explain why a
600x-shortened patience window did not expose it once in 3,968 tests. Ordinary in-suite contention
between two test connections is the reading this most damages: it is no longer merely unobserved,
it is measurably absent from a full pass. What survives is something that does **not** run on the
suite's own schedule -- a fire-and-forget task, a spawned process, or a worker thread outliving the
loop that made it -- which is also the only reading consistent with the intermittency being timing
rather than ordering.

*Two things this run does not tell you.* The suite was collected at 23:51 on the pre-N-3 tree, so
it did not include that iteration's two new cutover tests. And a single pass is one sample of an
intermittent failure whose observed CI rate is far below one in a run; a negative at n=1 bounds
nothing about frequency, only about mechanism.


**The instrument fired in CI, 2026-09-06 (day D-1) -- and it returned a negative. The standing
mechanism is falsified for both occurrences.** Read from `gh run view <id> --log-failed` directly,
not from a summary. Two runs, both overnight, both the `hub-test` job on Linux with every other job
green, and in each the only error in the suite:

| CI run | sha | Result | Errored at setup of |
|---|---|---|---|
| 33998517779 | `2da52ce` | 3966 passed, 18 skipped, 1 error in 488.37s | `test_a_wedged_review_is_restaffed_to_a_real_reviewer` |
| 33998598976 | `3a96ddb` | 3966 passed, 18 skipped, 1 error in 741.71s | `test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |

Both carried the N-1 registry (`6693d1d`), both printed the diagnostic, and the two printouts are
**identical line for line** apart from the timestamps:

```
F292 DIAGNOSTIC: the schema reset failed. Who was holding the database:
  [before dispose] pool.status()='Pool size: 5  Connections in pool: 0 Current Overflow: -5 Current Checked out connections: 0'
  [before dispose] registry: no connection checked out
  [before drop_all] pool.status()='Pool size: 5  Connections in pool: 0 Current Overflow: -5 Current Checked out connections: 0'
  [before drop_all] registry: no connection checked out
  [at failure] pool.status()='Pool size: 5  Connections in pool: 1 Current Overflow: -4 Current Checked out connections: 0'
  [at failure] registry: no connection checked out
```

*This is a result, not a miss.* The instrument is not blind -- N-1 proved it on a forced
reproduction, where it named the culprit test, its asyncio task, the source line and the transaction
state, against a failure reported at the victim. So **the holder was not a connection checked out
from `hub.db.engine.engine`.** That falsifies two things stated above as this entry's leading
reading:

- D-6's narrowing -- *"a session that wrote and did not commit, held across the test boundary"* --
  is **exactly** the shape the registry catches, and it caught it in the forced reproduction. It was
  not that here.
- `hub/tests/conftest.py`'s own mitigation comment, which blames *"a test that leaves a live
  `JobScheduler` ... still holding a checked-out connection when the next test starts"*. Not that
  either, on the same evidence. The entry already doubted this on reading; it is now measured.

*A sharper localisation, which is new.* Both overnight failures are in the **same module and one
test apart**, at the same point in a deterministic run. In the progress stream of both logs the
module occupies the same lines at `[ 66%]`; in `2da52ce` the error is
`test_a_wedged_review_is_restaffed_to_a_real_reviewer` and the test after it passes, in `3a96ddb`
that test passes and `test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` errors
instead. Five recorded failures now sit in two files, and the failing setup is in both cases
adjacent to the tests that call this module's `_fire()` helper
(`hub/tests/test_reviewer_is_not_the_author.py:190-196`). The window slides by one test between
runs, which is what a timing-dependent holder looks like and not what a particular test's leak looks
like.

*What remains possible.* Each of these is a **hypothesis**; none is measured to be the cause.

- **H1 -- another `Engine` on the same file, in this process.** Measured: the Hub creates exactly
  three engines, `hub/hub/db/engine.py:34` (the product engine, the only one the registry watches),
  `hub/hub/migrations/env.py:51`, and `hub/hub/scheduler.py:2367`.
  - APScheduler's synchronous engine (`JobScheduler._get_sync_engine`, `scheduler.py:2354-2367`) is
    **eliminated for the test suite, by measurement** -- and it had to be checked rather than
    assumed away, because it is a *documented* cause of exactly this error elsewhere in the product
    (`hub/hub/api/v1/jobs.py:497-517`: "a separate synchronous engine pointed at the same SQLite
    file ... cannot take the write lock and raises `database is locked`"). It is not live here:
    `JobScheduler.__init__` is inert (`scheduler.py:2317-2319`), `_get_sync_engine` is reached only
    from `start()`, the only assignments to `_scheduler_instance` are in
    `scheduler.py:3243-3254`, the suite's only reference sets it to `None`
    (`hub/tests/test_runtime_diagnostics.py:75`), and `hub/tests/conftest.py:468` records that
    ASGITransport does not trigger the FastAPI lifespan -- so nothing starts a scheduler.
  - Alembic's engine (`migrations/env.py:51`) is **not eliminated.** `_run_alembic_upgrade`
    (`hub/hub/db/engine.py:54-107`) runs `command.upgrade` **in a worker thread** precisely because
    `env.py` drives its own async engine with its own `asyncio.run`; that engine is built from the
    same `settings.database_url` and is invisible to engine-level pool listeners by construction.
    The thread comes from `loop.run_in_executor(None, ...)` (`engine.py:104`) -- the loop's *default*
    executor, whose threads outlive the coroutine and the loop that queued the work.
    The `app` fixture monkeypatches it to a no-op, but deliberately **per test**, and that patch's
    own comment (`conftest.py:440-449`) names
    `test_migrations.py::test_init_db_runs_alembic_for_file_db` as a test that does not take the
    fixture and runs the real thing. `env.py` does `await connectable.dispose()`, so this is a
    hypothesis about that disposal not being complete or not being reached, not about a missing
    one.
- **H2 -- a writer that is not SQLAlchemy.** Weakest of the three: there is no `sqlite3.connect(`
  anywhere under `hub/hub/`, so a raw connection would have to come from a dependency rather than
  this codebase.
- **H3 -- a separate process, or a worker thread outliving the loop that made it.** This is what
  N-1b's whole-suite `busy_timeout=50` negative already pointed at, and the registry negative is
  consistent with it for the same structural reason: a thread or process holding the file through
  its own connection cannot appear in engine-level pool events. H1's alembic path is a concrete
  instance of the thread half, which is why it is worth checking first.

*What the registry structurally cannot see, so the negative is not read as broader than it is.* It
records connections **checked out** from the product engine. A connection of that engine sitting
idle *in the pool* while still holding a lock would also print "no connection checked out" -- but
the fixture disposes the engine between the first and second probe, and `dispose()` closes the old
pool's idle connections, so that reading is weak rather than dead. The `Connections in pool: 1` at
failure is the `drop_all` attempt's own connection on the replacement pool, not a survivor.

*Two cautions.* Two occurrences with a negative each falsify the mechanism **for those two**; the
three earlier runs in the table ran before the instrument existed and are not covered. And nothing
here was reproduced -- this is CI evidence plus code read in this repository, with no local run.

F285 was the Hub suite sharing one DBAPI connection across every `AsyncSession`, because an
in-memory SQLite URL gets a `StaticPool`. It was fixed on 2026-09-04 by moving the suite to a
file-backed temporary database per process (`d9ad1e0`), which gets an `AsyncAdaptedQueuePool` -- one
connection per session, the pool production uses. That fix is correct and this finding does not ask
for it to be reverted.

What it bought instead is file locking, which `:memory:` did not have. `hub/tests/conftest.py:109-111`
sets `journal_mode=WAL` and `busy_timeout=30000`, and the client fixture drops and recreates the
schema before every test. `drop_all` is a schema change, and SQLite will not make one while another
connection holds the database, so it waits out the 30s busy timeout and raises. The failure lands at
the **setup** of whichever test is next, which is not the test that caused it.

This was already seen once and mitigated: `be6a70d`, *"empty the pool before the schema reset, not
only after the test"*, adds `await _REAL_ENGINE.dispose()` before the `drop_all`
(`hub/tests/conftest.py:298`), and its comment names the run it was written for (33913450471) and the
test that failed there (`test_a_wedged_review_is_restaffed_to_a_real_reviewer`).

**The mitigation is in the tree at all three failures below, and one of them is the test it names.**
Measured against `git show <sha>:hub/tests/conftest.py` for each: all three carry the dispose.

| CI run | sha | Test that errored at setup |
|---|---|---|
| 33923797344 (2026-09-04T22:02Z) | `770cda5` | `test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer` |
| 33953849160 (2026-09-05T07:55Z) | `0b8aaf5` | `test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` |
| 33955870588 (2026-09-05T08:39Z) | `acd7ea8` | `test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |
| 33998517779 (2026-09-05T23:31Z) | `2da52ce` | `test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer` |
| 33998598976 (2026-09-05T23:37Z) | `3a96ddb` | `test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |

All three are `sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked`, all
three are `ERROR at setup`, all three are the `hub-test` job on Linux with every other job green, and
in each run it is the only error in the suite. **Three of the sixteen CI runs on
`autonomous/2026-09-04-daily` failed this way -- the sixteenth was still in progress at 10:14 -- and
no run on this branch has failed in any other way.** *(Corrected 2026-09-06, day D-1: the last two
rows were added that morning. The count is now **five**, and the two newest are the branch's two
most recent completed runs, which is why the merge gate's condition 3 cannot pass. "No run on this
branch has failed in any other way" still holds.)* Green runs
bracket each failure on the neighbouring commits, so it is intermittent rather than a property of any
one sha, and it is the sole thing standing between this branch and the merge gate's condition 3.

Both failing files construct `JobScheduler` (`test_reviewer_is_not_the_author.py:191`,
`test_flow_fires_a_review_turn.py:137` and seven more), which is what the mitigation's comment
blames. **But the comment's mechanism does not obviously fit these**, and saying so is the point of
filing this rather than re-applying the same remedy: `_fire_job_internal` is awaited directly with an
explicit session in both files, so no background scheduler loop is started, and `dispose()` closes a
pool's *idle* connections -- it cannot reclaim one that a still-running task has checked out. The
surviving writer is more likely a fire-and-forget `asyncio` task created during the previous test
than the scheduler object itself. **That sentence is a hypothesis and has not been measured.**

Reproduce -- **run 2026-09-05 (night N-1), both halves, and neither reproduced**: 15 loops of
`hub/tests/test_flow_fires_a_review_turn.py` and `hub/tests/test_reviewer_is_not_the_author.py`
under `py -3.11`, then the same pair at `busy_timeout=50`. See the instrumented section above for
what that rules out and for the whole-suite loud run. The diagnostic that section asked for is now
in the tree, so **the next occurrence in CI names its cause instead of its victim** -- the checkout
registry prints under "Captured stderr setup" on the erroring test.

Not a D-6 repair. The carve-out requires a fix smaller than the argument for it, and here the
argument is unfinished: the mechanism is not established, and the last change made to this file on
this evidence did not work.

**A sixth occurrence, 2026-09-06 09:10-09:25 (day D-6, while the review page was being written), and
it is the first one inside a day window.** CI run `34021133812`, sha `8902e53`, `hub-test` on Linux,
every other job green, the only error in the suite: `3966 passed, 18 skipped, 228 warnings, 1 error
in 870.39s`, `ERROR at setup of
test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted`.
Read first-hand with `gh run view 34021133812 --log-failed`.

Three things it adds, and one it does not:

- **The N-1 diagnostic printed a third identical negative.** All six registry lines match the two
  overnight printouts character for character -- `no connection checked out` at every probe point,
  the same `Current Overflow: -5` before and `-4` at failure. So the falsification recorded above is
  now n=3, not n=2, and it is not an artefact of the overnight environment.
- **The errored test is a repeat, not a new one.** It is the same test as `33998598976` (`3a96ddb`),
  in the same module, at the same 66% progress marker as `33998517779`'s different test. Three
  occurrences, two distinct tests, one module. D-1's reading -- *a sliding timing window, not a
  particular test's leak* -- survives, and the repeat is what you expect from a window that lands in
  the same place twice, not evidence for that test in particular.
- **The run was the slowest of the three** (870.39s against 741.71s and 488.37s), all three of them
  failures. The five completed runs on this branch today that *passed* are not directly comparable
  from this data alone -- their durations were not read -- so this is an observation, not a
  correlation. Named so a later run can test it cheaply.

What it does **not** add: it does not change the surviving lead (alembic's own async engine, driven
from a default-executor worker thread), and it does not make this a D-6 repair -- the paragraph above
still holds.

**The rate today, measured, because it is what the merge gate turns on.** Eight CI runs were queued on
this branch between 07:55 and 08:52 UTC; six had completed by 10:00 local. **One failed, five passed**
-- and the three completed runs immediately after the failure (`6f58c27`, `cf9045e`, `5891d5a`) were
all green. So condition 3 is *satisfiable*, just not reliably: on today's sample the gate has roughly
a five-in-six chance of finding a green run at any given HEAD, and no way to distinguish a red one
from a real regression without reading the log.

**The alembic-engine half of H1 is measured now, not just reasoned about -- and it is ruled out as
*this* mechanism, though two real defects in it are fixed regardless.** 2026-09-06, at the operator's
explicit go-ahead ("let's fix the CI flake"), which also answers DEC-1 (`STATE-night.json`): yes, a
second attempt at this evidence was authorised. This is a fresh investigation of H1's alembic half,
not a repeat of the day's own reading of it.

*First, a correction to H1 as written above.* "`test_init_db_runs_alembic_for_file_db`... is the one
test that does not take the fixture and runs the real thing" is the wrong test to hang H1 on: it runs
alembic against its own isolated `tmp_path` file (`hub/tests/test_migrations.py:516-518`), never the
shared `TEST_DATABASE_URL` every other test's `drop_all` targets, so it structurally cannot lock the
shared file. The test that actually matters and was never named is
**`test_init_db_creates_no_project_even_with_the_legacy_bootstrap_env_set`**
(`test_migrations.py:471-494`) -- it takes no `app` fixture, so it is not monkeypatched, and it calls
`await init_db()` directly on the module-level `engine`/`settings.database_url`, which conftest.py
binds to `TEST_DATABASE_URL` at import time. This is the **only** place in the whole suite where the
real, un-monkeypatched `_run_alembic_upgrade()` runs against the shared file.

*Two real defects in `hub/hub/migrations/env.py`'s `run_async_migrations`, found by reading the code
and confirmed by forcing them:*

1. `connectable`'s connect_args were empty, so on SQLite it ran at the aiosqlite/sqlite3 driver's
   default busy timeout -- **measured at 5000ms** -- while the main engine (`hub/tests/conftest.py`'s
   pragma listener) waits 30000ms. Six times shorter patience for exactly the kind of writer
   contention this entry's own D-6 control proved locks a schema reset.
2. `await connectable.dispose()` sat **after** the `async with connectable.connect()` block, not in a
   `finally`. A migration failure propagates straight past it, leaking the engine (and its one
   checked-out-then-rolled-back connection) until Python's garbage collector reclaims it.
   `_run_alembic_upgrade` (`hub/hub/db/engine.py`) swallows the resulting exception, so nothing
   surfaced but the leak.

*Forced reproduction, standalone asyncio script, not pytest.* A task held an uncommitted write on the
main engine for 6s while `_run_alembic_upgrade()` ran concurrently against the same file. **Before the
fix:** alembic's connectable raised `OperationalError: database is locked` at 5.64s (its own 5000ms
default), the warning fired exactly as `_run_alembic_upgrade`'s docstring describes, and the
`connectable.dispose()` line was skipped. **After the fix** (busy_timeout raised to 30000ms to match):
alembic waited out the holder and completed all 101 migrations at 6.20s -- the exact race is closed.

*But the leaked connection did not go on to block a later write in this reproduction.* Immediately
after the holder released, a fresh `drop_all` on the shared engine succeeded in 0.05s, with the failed
`connectable` never explicitly disposed and not yet garbage-collected. Reading why: `async with
connectable.connect() as connection:` calls `connection.close()` on exit regardless of exception, and
SQLAlchemy's `close()` rolls back any open transaction before returning the connection to the pool --
so the *individual connection* is released cleanly even when `connectable.dispose()` (the *pool*) is
skipped. The leak is real (an engine, a pool, one idle connection, and the executor thread that ran
`command.upgrade`, all held until GC) but this reproduction did not show it as the thing that holds a
file lock past the point of failure. **This is a negative result on the locking question specifically,
not a clean bill of health on the leak** -- it was tested with the failure landing on the very first
DDL statement (`CREATE TABLE alembic_version`); a failure partway through the 101-migration sequence,
after earlier statements have already run, was not tried and could behave differently.

**Decisive negative evidence, from the very next CI occurrence.** `34029310406` (`7a6c782`, pushed
this session before the fix), the **seventh** occurrence: `ERROR at setup of
test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`
-- a repeat of `0b8aaf5`'s failure, not a new test. Read with `gh run view 34029310406 --log-failed`.
The registry printed its **fourth character-for-character identical negative** (`no connection checked
out`, at all three probes) -- the falsification of the main-engine hypothesis is now n=4.

*And it rules out alembic as this occurrence's cause, by collection order, measured, not assumed:*
`pytest tests/ --collect-only -q` places `test_flow_fires_a_review_turn.py` at line **1386** and
`test_migrations.py` (the file containing the one real-alembic-on-shared-DB test) at line **1780**.
Pytest collects and runs test files in that order with no randomisation on this branch (no
`pytest-randomly`, no `-n`) -- so **`test_migrations.py` had not run yet** when this failure occurred.
Whatever held the database for this occurrence, it was not alembic. (`test_reviewer_is_not_the_author.py`,
where three of the six earlier occurrences landed, collects at line 2721, *after* `test_migrations.py`
-- so H1 remains structurally possible for those three specifically. It is now ruled out for at least
one of the seven, which is different from being ruled out for all of them.)

**Net effect on H1: the alembic engine is no longer a live suspect for a general mechanism**, since
F292 demonstrably reproduces in a file collected before it ever runs. The two defects fixed in
`env.py` are real and worth having independently of F292 (a shorter, needless timeout; a genuine
resource leak on any alembic failure, not only this one) -- but they are **not F292's fix**, and this
entry's status stays **open**. H3 (a fire-and-forget task or a worker thread outliving the loop that
made it, general form -- not the alembic-specific instance of it) is what survives: something that can
occur in the early files of a run, independent of alembic, invisible to the main-engine registry, and
does not reproduce under any local condition tried so far including a 600x-shortened busy_timeout
across the whole suite. The next occurrence's registry output is still the best available instrument;
nothing this round added can name the holder.

**Fixed, and covered:** `hub/hub/migrations/env.py`'s two defects, at `<pending commit>`.
`hub/tests/test_migrations.py::test_run_async_migrations_uses_the_same_busy_timeout_as_the_main_engine`
and `::test_run_async_migrations_disposes_its_engine_even_when_a_migration_raises`, both mutation-
checked (reverting the fix fails both; restoring it passes both). Full `hub/tests/test_migrations.py`
run clean: 85 passed, 1 skipped.

**A qualitatively new occurrence, 2026-09-06, changed the shape of what this finding is: F292 can
hang, not only fail.** CI run `34030001741` (sha `1c0bb2b`) sat `in_progress` in the `hub-test` job
for **3.5 hours** -- started `11:21:41Z`, still running at `14:47:56Z`, manually cancelled. Every
prior occurrence in this entry fails within 8-14.5 minutes (`busy_timeout` expires, pytest reports
the error, the run ends); none had ever hung. GitHub cannot serve logs for a still-running job (the
REST logs endpoint 404s with `BlobNotFound`), so there is no log evidence of where -- only the
wall-clock fact that it exceeded every historical bound by 10x+ and never self-resolved. `1c0bb2b`
carries no product or test code (`spec-queue/DIRECTION.md` only), so the hang is not caused by
anything in this entry's own fix and was not introduced by it.

**This changed the question from "what holds a connection a bit too long" to "is there a path with
no timeout at all" -- and there is one, general and not specific to alembic, found by tracing a
warning this session's own full-suite run produced as a side effect:**

`hub/tests/test_migrations.py`'s local run (85 tests, this entry's two new ones included) was clean,
but the **full** `hub/tests/` run (3972 passed, 86 skipped, 1033s) printed one
`PytestUnhandledThreadExceptionWarning`, from `aiosqlite/core.py` (installed 0.22.1, the current
latest -- not a version this repo is behind on):

```
File ".../aiosqlite/core.py", line 66, in _connection_worker_thread
    future.get_loop().call_soon_threadsafe(set_result, future, result)
...
RuntimeError: Event loop is closed
During handling of the above exception, another exception occurred:
File ".../aiosqlite/core.py", line 75, in _connection_worker_thread
    future.get_loop().call_soon_threadsafe(set_exception, future, e)
...
RuntimeError: Event loop is closed
```

Reading `aiosqlite/core.py`'s `_connection_worker_thread` (its whole body is 28 lines): every
aiosqlite `Connection` runs one dedicated OS thread that pulls `(future, function)` off a
`SimpleQueue` forever, runs `function()` synchronously, and reports back via
`future.get_loop().call_soon_threadsafe(...)`. **If the coroutine that queued the work has moved on
and its event loop has already closed by the time the thread finishes, `call_soon_threadsafe` raises
-- and the `except` branch's own attempt to report *that* failure makes the identical call and raises
again, uncaught. The worker thread's `while True` loop terminates. The thread is now permanently
dead**, and nothing else in aiosqlite notices.

*Forced reproduction, standalone, with a hard timeout so the repro script itself could not hang
forever:* a coroutine connects, queues a 1s operation via `_execute` without awaiting it (fire-and-
forget), and returns; `asyncio.run()` then closes its loop while that operation is still running in
the worker thread.

```
worker thread alive? False
uncaught thread exceptions captured: 1    RuntimeError: Event loop is closed
reusing the same connection from a fresh loop: TIMED OUT (hung) after 5s
```

**The crash reproduces byte-for-byte identical to the warning the real suite produced, and reusing
the same connection object afterward hangs -- unboundedly; `asyncio.wait_for(..., timeout=5.0)` is
the only reason this script did not hang forever too.** No SQLite `busy_timeout` governs this at all:
the failure is that nothing is left alive to ever resolve the `Future` a later `_execute` call
awaits. This is the general, no-timeout hang mechanism the coordinator asked whether `_run_alembic_
upgrade`'s `run_in_executor` specifically could produce -- it is not that call site, but the same
class of bug, sitting one layer down in the driver every `AsyncSession` in this codebase uses.

**Traced to a concrete, real call site: `agent_trigger.py`'s background run task, reachable from the
exact two test files F292 has always failed in.** `hub/hub/api/v1/agent_trigger.py:1190` creates
`task = asyncio.create_task(_execute_run(...))` and does not await it -- deliberately, so the
triggering call returns while the run continues. It is tracked in a module-level `_background_runs`
set with a `done_callback` to discard itself (`:1230-1231`), and dozens of tests across the suite
explicitly drain that set before finishing. `hub/tests/conftest.py:317-367` is the general-purpose
safety net for tests that do not drain it themselves: on teardown, it cancels every task still in
`_background_runs`, `gather`s them with `return_exceptions=True` in a loop until the set is empty
(handling the case where cancellation itself schedules a successor), *then* disposes the shared
engine -- a fixture whose own comments already record one prior incident from getting this ordering
wrong (`test_the_timeline_reports_what_a_run_wrote_outside_its_workspace`, 2026-09-05).

**That safety net closes the asyncio-level race and does not close this one.** `task.cancel()` +
`gather` waits only for the *coroutine* to unwind -- which can return as soon as the `Future` it is
awaiting inside aiosqlite's `_execute` is marked cancelled. It does not, and structurally cannot,
wait for the *worker thread* to finish whatever synchronous SQLite call is already in flight, because
that thread is not asyncio-aware and does not observe the cancellation at all. If that call is still
running when the fixture's loop settles, disposes the engine, and the test's event loop later closes,
the worker thread finishes into exactly the crash above -- and the underlying `sqlite3.Connection` is
never reached by any `close()` call, because the crash happens inside the `try/except` wrapped around
`function()` itself, before control could reach anything that would close it. **That connection then
sits open indefinitely, its thread dead, invisible to `hub/tests/conftest.py`'s N-1 checkout registry
(which watches SQLAlchemy's own checkout/checkin events on the engine, not aiosqlite's internal
thread lifecycle) -- consistent with the registry's four-for-four identical negative.**

*Why this fits both symptoms.* If nothing later tries to use that specific dead connection again, it
is a quiet leak that may or may not hold a lock depending on exactly what SQL it was mid-executing --
a plausible source of the historical **bounded** failures (something eventually times out at 30s and
`drop_all` reports the error). If SQLAlchemy's pool instead considers the connection still checked-in
and hands it back out for real use, any operation on it awaits a `Future` that will never resolve --
**unbounded**, matching the newly observed 3.5-hour hang exactly.

*Why the two historically-failing files fit.* Both `test_reviewer_is_not_the_author.py` and
`test_flow_fires_a_review_turn.py` fire a job via a `_fire(job_id)` helper that awaits
`scheduler._fire_job_internal` -> `_do_fire_job` -> `turn_scheduler.schedule_agent` ->
`agent_trigger.trigger_agent_directly` end-to-end -- but `trigger_agent_directly` itself does not
await the `_execute_run` task it creates; it returns once the task is registered. So `_fire()`
returning to the test proves the *trigger* completed, not that the *run* did. Traced by reading
`hub/hub/scheduler.py:_do_fire_job` (calls `schedule_agent`) and `hub/hub/turn_scheduler.py:252-322`
(calls `trigger_agent_directly`), not assumed.

**Not fixed. This is a design-level asyncio/threading correctness issue in how a cancelled run's
worker-thread-backed DB operations are waited for**, not a one-line patch, and it touches core
run-execution/cancellation semantics this repository's own round discipline would want three
independent passes on before changing. Recorded here as the most concrete, best-evidenced lead to
date -- the next step is establishing whether `_execute_run`'s own database work can be made to
either (a) genuinely await the underlying thread instead of only the coroutine on cancellation, or
(b) run on a connection whose worker thread's lifetime is decoupled from any single test's event
loop. Not attempted this session: it needs its own dedicated investigation, and this session's
authorisation was for chasing F292's cause, not for changing run-cancellation behaviour.

**An eighth occurrence, 2026-09-07 22:03Z — the first on `master` — and a correction to this entry's
own leading conclusion.** (2026-09-08 day window, `d1a`. Full derivation in
`.claude/autonomous/2026-09-08-day-log.md`, iteration 2.) CI run `34164645184`, sha `15ce482`, read
first-hand with `gh run view --log-failed`: `hub-test` the only failing job, `3968 passed, 18
skipped, 230 warnings, 1 error in 657.72s`, `ERROR at setup of
test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`
on `DROP TABLE requirement_drift` at `tests/conftest.py:473`. Being on `master` removes the last
reading in which this could be a property of the cycle branches' trees. Two new numbers: the failure
is at progress `[33%]`, not the `[66%]` of the `test_reviewer_is_not_the_author.py` occurrences, so
the sliding window is not confined to one region; and the preceding test passed at `21:56:02.822`
against an error reported at `21:56:33.556` — **30.7 s**, the whole `busy_timeout`, so the holder held
for the entire window rather than losing a brief race.

*The correction, and it matters more than the occurrence.* This entry's leading claim — that the
main-engine registry's identical negatives **falsify** a product-engine connection as the holder,
"n=4" (now n=5) — **is too strong, and SQLAlchemy 2.0.50's own source says why.**
`_ConnectionRecord.__close()` fires `pool.dispatch.close` **before** attempting the close and
unconditionally (`pool/base.py:877-886`); `Pool._close_connection` then swallows any `Exception` from
`do_close`/`do_terminate`, logging it only to the `sqlalchemy.pool` logger and nulling
`dbapi_connection` regardless (`pool/base.py:371-384`); `_finalize_fairy` does the same for a failed
reset (`pool/base.py:1006-1011`). **So on every path where SQLAlchemy gives up on a connection whose
OS-level handle survives, the registry's entry is removed first and the failure is written only to a
logger pytest discards for a passing test.** The five negatives are *consistent with* a product-engine
connection holding the file; they falsify only the narrower claim *no connection was checked out and
still tracked at the probe points*. The wrong inference here is the shape `CLAUDE.md`'s round
discipline names: the argument was wrong while every measurement under it was right.

*A silent leak path that fits the printout exactly.* `SQLiteDialect_aiosqlite` sets `has_terminate =
True` (aiosqlite 0.22.1 has `stop`), so `_finalize_fairy`'s discard path calls
`_close_connection(terminate=True)` → `_terminate_force_close` → `aiosqlite.Connection.stop()`, which
merely **queues** `close_and_stop` — the only thing that ever calls the real
`sqlite3.Connection.close()` — onto the connection's worker thread and returns a future nobody awaits
(`aiosqlite/core.py:116-132`). If that thread is not draining its queue, the handle is never closed,
its transaction never rolled back, its locks persist, and **nothing raises**, so not even the
`sqlalchemy.pool` ERROR is emitted. A terminate on this dialect is structurally incapable of failing
loudly.

*But F295's loud signature is absent from both readable CI occurrences, which is the sharpest new
constraint.* `34164645184` and `34029310406` each contain **zero**
`PytestUnhandledThreadExceptionWarning`, zero `RuntimeError: Event loop is closed`, and zero
`_finalize_fairy` GC "non-checked-in connection" warnings. `hub/pyproject.toml` sets no
`filterwarnings`, so nothing was suppressed and the warnings summaries were read whole. In the two
occurrences whose logs exist, **the aiosqlite worker thread did not visibly crash.** This is measured
support for `DIRECTION`'s standing instruction not to expect
`a-dead-connection-is-never-handed-back-out` to close F292; F295 still fits the one 3.5-hour hang,
which is also the one occurrence with no log.

*Why `be6a70d`'s mitigation cannot hold, stated precisely.* Beyond `dispose()` being unable to
reclaim a checked-out connection: **the state its comment blames — a live `JobScheduler` holding a
checked-out connection — has never once been observed at a failure**, across five instrumented
occurrences. Strengthening it (another dispose, a longer timeout, a retry around `drop_all`) is the
move already measured to fail.

*F279 is **not** the same class, answered explicitly.* Different exception (`InvalidRequestError:
Could not refresh instance`, ORM session state, vs an OS-level file lock), different locus (inside
the run at `output_recording.py:94` vs the next test's fixture), different latency (~1.5 s vs the
full 30 s timeout), and opposite reproducibility (F279 fails 7/12 and 4/12 locally; F292 survived 15
local runs of the blamed pair and a whole suite at `busy_timeout=50`). What they share is a cause of
opportunity — both sit downstream of `agent_trigger.py:1190`'s un-awaited `_execute_run` task — so a
repair that makes a run's DB work genuinely settle before its caller moves on could reduce both. That
is a reason to build F295's change, not evidence that it fixes either.

*The instrument the next occurrence needs* is not a stronger dispose: it is a session-scoped handler
retaining `sqlalchemy.pool` ERROR records printed inside `_f292_report`, plus, for every connection
the registry has **ever** seen, whether its aiosqlite worker thread is alive and whether
`sqlite3.Connection.in_transaction` is set. Both are fixture-level. If both stay silent at the next
occurrence, that is also a result: it puts the holder outside SQLAlchemy's bookkeeping entirely — and
the in-repo second-engine candidates are already eliminated for this file by collection order
(`test_flow_fires_a_review_turn.py` at 1386; every test-suite `create_async_engine`,
`sqlite3.connect` and `aiosqlite.connect` lives in `test_migrations.py`,
`test_project_persistence.py`, `test_runner_charter_models.py` and `test_task_workspace_scheme.py`,
all collected after it — checked 2026-09-08; prior rounds had enumerated engines only under
`hub/hub/`).

### The instrument d1a asked for, shipped and mutation-checked (2026-09-08, day d1b)

`hub/tests/conftest.py`, fixture-level only -- no `hub/hub/` change, and a green run is exactly as
quiet as before. Two additions, one per silent path:

1. **`_PoolErrorRecorder`**, a bounded `logging.Handler` on the `sqlalchemy.pool` logger retaining
   ERROR records with their tracebacks, printed inside `_f292_report`. That logger is the single
   place every silent give-up path writes to, and pytest discards the log of a *passing* test --
   which is the test that makes the leak; the failure lands in the *next* test's setup, which logged
   nothing.
2. **`_EVER_SEEN`**, every connection the registry has *ever* seen rather than only those still
   checked out, reporting whether the `sqlite3` handle is still open, whether the aiosqlite worker
   thread is alive, whether the connection is in a transaction, and whether `stop()` was called
   without the queued close ever running.

**The leak signature is exact, and that is the point.** `aiosqlite.Connection.stop()` sets
`_running = False` *immediately* and then queues the only real `sqlite3.Connection.close()` onto its
worker thread (`aiosqlite/core.py:116-132`). So `_running == False` while `_connection is not None`
means the close was queued and never ran and the file lock is still held. Measured on the installed
0.22.1: a stop whose worker thread *is* draining leaves thread dead, `_running` False and
`_connection` None within milliseconds. The two outcomes are distinguishable.

**Four weakref facts, measured against SQLAlchemy 2.0.50 / aiosqlite 0.22.1 rather than assumed** --
and they correct the entry's earlier N-1 note, which said only that "the DBAPI connection is not
weakref-able but `_ConnectionRecord` is":

| Layer | Weakref-able |
|---|---|
| `_ConnectionRecord` | yes |
| `AsyncAdapt_aiosqlite_connection` (the DBAPI adapter) | **no** |
| `sqlite3.Connection` | **no** |
| `aiosqlite.Connection` | **yes** |

The last row is what makes the instrument possible: the aiosqlite `Connection` is the one layer that
both carries the leak signature and can be weakly referenced. The record alone would not do --
SQLAlchemy sets `record.dbapi_connection = None` when it closes one, so the object holding the file
becomes unreachable from the record at exactly the moment it becomes interesting.

**Mutation-checked, both halves, against forced reproductions** (a throwaway two-test file, run and
deleted inside the iteration; a diagnostic that has never fired is not evidence). The decisive one
simulates the mechanism d1a identified -- SQLAlchemy discards the connection while `stop()` only sets
`_running = False`, as it does when the worker thread is not draining:

```
  [before dispose] registry: no connection checked out
  [before drop_all] registry: no connection checked out
  [at failure] registry: no connection checked out
  ever-seen: 2 connection(s) recorded, 0 already collected, 2 with an OPEN sqlite3 handle
  ever-seen: last checked out by ...::test_a_leaks_a_silently_discarded_connection
  ever-seen:     sqlite3 handle OPEN, IN TRANSACTION, worker thread alive, _running=False
                 <-- stop() was called and the close never ran: THIS ONE LEAKED
```

The old registry printed the CI negative three times -- **the exact printout of all five instrumented
occurrences** -- while the new section named the holder, its test, and its transaction state. A second
reproduction, with the terminate raising, captured the real `sqlalchemy.pool` ERROR and its full
traceback through `_close_connection` -> `do_terminate` -> `_terminate_force_close`, proving the
first half on the real path too.

**Version-robustness, which d1a flagged as an open caveat.** `hub/pyproject.toml` pins neither
(`sqlalchemy[asyncio]>=2.0`, `aiosqlite>=0.20`), so CI resolves its own. The instrument does not
depend on the `pool/base.py` line numbers the diagnosis cites: it keys on the logger name
`sqlalchemy.pool` (stable across 2.x) and on aiosqlite attribute reads that are each wrapped so any
failure becomes a string in the report rather than an exception replacing the error being diagnosed.

Verified this iteration: `ruff check src/ hub/ tests/` and
`black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` clean;
`test_flow_fires_a_review_turn.py` 8 passed with the report correctly silent; `test_migrations.py`,
`test_project_persistence.py`, `test_runner_charter_models.py`, `test_task_workspace_scheme.py` --
the four files that create their own engines -- 109 passed, 1 skipped. The
`PytestUnhandledThreadExceptionWarning` / `Event loop is closed` that
`test_flow_fires_a_review_turn.py` emits locally was **confirmed to pre-date this change** by
re-running the file with the diff stashed (12 matching lines either way); it is F295's signature, not
a regression from the instrument.


### Measured 2026-09-08 (day `d2`): the rate, its denominator, its window and its method

The entry has carried occurrence *anecdotes* since it was filed and has never carried a **rate**.
This section is that number, derived independently rather than copied from
`.claude/handoffs/DEAD-ENDS.md`'s 2026-09-08 line.

**Method.** `gh run list --workflow ci.yml --limit 300 --json headSha,conclusion,createdAt,status,databaseId,headBranch`
(297 completed runs, 2026-08-19 → 2026-09-08T08:26Z), then, for **every** failure in the windows
below, `gh run view <id> --json jobs` to confirm `hub-test` was the only failing job, and
`gh run view <id> --log-failed` to confirm the error is this defect —
`sqlite3.OperationalError: database is locked` on `DROP TABLE requirement_drift` at
`conftest.py:473` — and not something else. No failure is counted as F292 on the strength of being
red.

**The headline rate, with its denominator:**

| Population | Runs | Failures | Rate |
|---|---|---|---|
| All branches, 2026-09-07T00:00Z → 2026-09-08T08:26Z | 54 | **11, every one F292** | **20.4 %** |
| `master` only, since 2026-09-06T00:00Z | 20 | 5, every one F292 | 25.0 % |
| `master` only, whole 119-run sample since 2026-08-19 | 119 | 16, of which 5 F292 | 13.4 % overall, **4.2 % F292** |

The third row is the one that dates the defect: over the full three-week sample F292 accounts for
5 of 16 `master` failures, and **all five are after 2026-09-06T15:35Z**. The other eleven are real
test failures and two `test (ubuntu-latest, 3.11)` failures from 2026-08-25. F292 is recent and
concentrated, not chronic — which is why any rate quoted over a long window understates it.

**The sharpest single fact, and it is new:** in the 54-run window since 2026-09-07T00:00Z,
**every red CI run is F292 — 11 of 11, zero other causes.** CI redness on this project currently has
exactly one cause, and it is this finding. The merge gate is being held shut by one defect.

**Occurrence count corrected: at least 22, not 8.** The entry's count is 8 because it counted the
occurrences somebody happened to read. Every failure in 2026-09-04T22:02Z → 2026-09-08T07:55Z was
classified by log signature this iteration, and **22** carry it:

- `autonomous/2026-09-04-daily` (10): `33923797344` `33953849160` `33955870588` `33997304616`
  `33998517779` `33998598976` `34021133812` `34029310406` `34062482611` `34062963728`
- `master` (5): `34042787904` `34164645184` `34171697507` `34174610762` `34175711842`
- `autonomous/2026-09-07-daily` (2): `34106986818` `34111041237`
- `autonomous/2026-09-07-sidequest` (4): `34137445128` `34140570366` `34141780252` `34153909037`
- `autonomous/2026-09-08-daily` (1): `34201752603`

Earliest confirmed is `33923797344`, 2026-09-04T22:02Z — one day *before* the entry was filed, so
the defect predates its own discovery, as expected. 22 is a floor, not a ceiling: runs before
2026-09-04T22:02Z were not classified, and the 2026-09-03/04 failure spike (36 failures on
`autonomous/2026-09-03-daily`) is a separately-broken tree that was deliberately excluded rather
than swept in — `33808108594` from it was checked and is **F279's** signature
(`test_a_stopped_run_persists_it`), not this one.

**Three tests, two files, and one run that errored at two of them.** Across the 22:
`test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` (7 of the 16 logs still
retained), `test_a_wedged_review_is_restaffed_to_a_real_reviewer` (6),
`test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` (4) — in
`hub/tests/test_flow_fires_a_review_turn.py` and `hub/tests/test_reviewer_is_not_the_author.py`,
which confirms the entry's "the two test files F292 has always failed in" against a 22-run sample
rather than against the handful read so far. Run `34140570366` errored at setup of **two** of them
in one run, which no prior occurrence had shown.

**Agreement with `DEAD-ENDS.md`, and the caveat that matters.** That file records *"4 failures in
the last 20 `ci.yml` runs, ~22%"*. This measurement gives 5/20 = 25 % on the nearest comparable cut
(`master`, last 20) and 20.4 % all-branch. **The two agree** — same magnitude, same direction, and
both are materially worse than the "~1 in 6" (16.7 %) previously on record. They cannot be
reconciled run-by-run because the DEAD-ENDS line records a rate without its population or its date
range; 4/20 is 20 %, not 22 %, so its denominator was probably not 20 either. **Lesson, and it is
the reusable one: a flake rate without its denominator, its window and its classification method is
not a measurement.** That is why this section states all three.

**A methodological hole this count does *not* close.** A rate keyed on "`hub-test` was the only
failing job" cannot see a *hang*. Run `34041037112` (2026-09-06T15:02Z) is the proof: its `hub-test`
job ran 15:02:24 → 21:02:40 — **exactly six hours, GitHub's job ceiling** — and was `cancelled`,
while the run's `failure` conclusion came from `test (ubuntu-latest, 3.11)`. Classified strictly it
is *not* an F292 failure, and it is excluded from the 22 above; but the entry's own "hung for 3.5
hours instead of failing" section says this mode exists. **Any future rate for this finding must
count cancelled-after-timeout `hub-test` jobs separately, or it will undercount the worst
occurrences.**

**Not measured, and deliberately.** Whether the instrument shipped at `66861a4` has fired: as of
this iteration CI for `66861a4` was still `in_progress`, and the two commits after it had not
started. The first instrumented occurrence is still ahead, and reading it outranks re-deriving this
rate.

### Ninth occurrence — the instrument fired, and it named the victim rather than the holder

`34205295463` / job `101993257049`, sha `66861a4` (the instrument's own commit), branch
`autonomous/2026-09-08-daily`, 2026-09-08T08:50:07Z. `hub-test` the only failing job; same test
(`test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`), same statement
(`DROP TABLE requirement_drift`), same `sqlite3.OperationalError: database is locked`. **The report
printed, in full, and both new halves came back negative.** Verbatim:

```
  [before dispose] pool.status()='Pool size: 5  Connections in pool: 0 Current Overflow: -5 Current Checked out connections: 0'
  [before dispose] registry: no connection checked out
  [before drop_all] pool.status()='Pool size: 5  Connections in pool: 0 Current Overflow: -5 Current Checked out connections: 0'
  [before drop_all] registry: no connection checked out
  [at failure] pool.status()='Pool size: 5  Connections in pool: 1 Current Overflow: -4 Current Checked out connections: 0'
  [at failure] registry: no connection checked out
  pool log: `sqlalchemy.pool` logged NO error this session.
  ever-seen: 506 connection(s) recorded, 495 already collected, 1 with an OPEN sqlite3 handle
  ever-seen: last checked out by tests/test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn [task: Task-24988 running _wrap_asyncgen_fixture.<locals>._asyncgen_fixture_wrapper.<locals>.setup]
  ever-seen:     sqlite3 handle OPEN, idle, worker thread alive, _running=True
```

**The single open connection is the one that attempted the DROP — the victim, not the holder.**
Three lines agree on this and none of them needed to be assumed: `pool.status()` at failure counts
one connection *in* the pool and none checked out; the registry is empty; and the label names the
current test's own fixture setup. The `except` block sits outside `async with engine.begin()`, so by
the time the report is written the failed transaction has rolled back and its connection has been
checked back in — open, idle, healthy. Nothing else this process opened still held the file.

**What that legitimately rules out.** The `sqlalchemy.pool` negative is *not* the structural kind
that narrowed the registry claim on 2026-09-08 (d1a). `_PoolErrorRecorder` records continuously from
import, keeps records across tests, and prints them only on the failure path — so "logged NO error
this session" rules out every path where SQLAlchemy gave up on a connection and left its SQLite
handle open: `_close_connection` (`pool/base.py:377`), `_finalize_fairy` (`:1008`, `:1031`). Nothing
else writes there. **d1a's hypothesis — the silent discard through aiosqlite's `has_terminate`
`stop()` — predicted an error on that logger or a `_running=False, _connection is not None`
signature, and neither appeared.** The 495-of-506 collected count says the pool's connections are in
fact being closed, and the closed ones are being reclaimed.

**One candidate eliminated by reading, cheaply.** `hub/hub/scheduler.py:2367` `_get_sync_engine()`
builds a **second, synchronous** engine (`sqlite://`, plain `sqlite3` driver) on the *same file* for
APScheduler's `SQLAlchemyJobStore` — a connection from it would be structurally invisible to this
instrument, which listens on `engine.sync_engine` only. (Checked rather than assumed: APScheduler
3.11.2's `SQLAlchemyJobStore.shutdown()` *is* `self.engine.dispose()`, and `BaseScheduler.shutdown()`
reaches it, so the engine is disposed on an orderly shutdown. An earlier draft of this paragraph
claimed it was never disposed; that was wrong.) It is not F292's holder in CI: nothing in `hub/tests/` calls `JobScheduler.start()` (the two
F292 files call `_fire_job_internal` directly), and `create_engine` opens nothing until used.
`ASGITransport` does not run the lifespan, so app startup does not reach it either. **It remains a
production concern and is filed as one; it is not this.**

### The limitation that blunts this negative — and this is the second time

`_f292_ever_seen()` is computed **once, at report time**. `_f292_snapshot()` carries only
`pool.status()` and the checked-out registry, so the `[before dispose]` and `[before drop_all]`
lines say nothing about connections that are no longer checked out. The report is written *after*
`PRAGMA busy_timeout=30000` has expired — so **the holder had a full 30 seconds to close its handle
and be garbage-collected before the only sampling that could have seen it.** A suite-engine
connection that held the file when the DROP began and closed during the wait produces exactly the
output above, indistinguishably from no holder at all.

So the honest statement of occurrence #9 is **"no holder thirty seconds after the fact"**, not "no
holder". The pool-log half is unaffected (it is continuous); the ever-seen half is sampled late.
This is the same shape of error as the one d1a found in the registry claim — an instrument's silence
read as a fact about the world when it was a fact about when the instrument looked — and it is worth
saying plainly that this entry has now made that mistake twice with two different instruments.

**The fix is small and is the next step: build the ever-seen line at every stage**, i.e. append
`_f292_ever_seen()` inside `_f292_snapshot()` (or take a second ever-seen string at `before dispose`
and `before drop_all` and print all three). Cost on the green path is unchanged — snapshots are
built only inside the `app` fixture's reset, and the report is written only on the failure path. It
must be mutation-checked like the first half was: a deliberately-held connection released during the
wait must be visible in the early stage and absent from the late one, or the new sampling proves
nothing.

**If the early sampling also comes back empty, that is the strong result**, and it points where the
conftest comment already said it would: outside SQLAlchemy's bookkeeping altogether. The candidate
class to look at first is **a child process**. `hub/tests/conftest.py` *assigns*
`os.environ["DATABASE_URL"] = TEST_DATABASE_URL` at import — into the real process environment, which
every subprocess inherits — and 45 files under `hub/tests/` mention `subprocess`. A child that opened
that database and outlived its test would hold the file, log nothing to `sqlalchemy.pool`, and never
appear in `_EVER_SEEN`. Nothing here shows one does; it is named as the next place to look, not as a
mechanism.

**Two smaller holes, recorded so they are not re-derived.** `_EVER_SEEN` is keyed by
`id(connection_record)`, and CPython reuses ids after collection — with 495 of 506 entries collected,
an aliased id would silently overwrite an older entry. And an `aiosqlite.Connection` that was itself
collected leaves no trace, which the entry's own comment argues is safe (its `sqlite3.Connection`
goes with it, and that object's finaliser closes the file) — true unless something else still
references the `sqlite3.Connection`, e.g. a closure sitting in a stalled worker thread's queue.

**Count.** This is occurrence **#9** by reading and takes the classified total to **at least 23**.
The rate measured earlier today (20.4 % all-branch over 54 runs) is not re-derived here.

### The census is now taken at every stage, so the next silence will mean something (day `d1c`, 2026-09-08)

The one-line change the section above asked for, done and mutation-checked. `_f292_ever_seen()` takes
a `stage` argument and is called from **inside** `_f292_snapshot()`, so all three stages -
`[before dispose]`, `[before drop_all]`, `[at failure]` - carry a census stamped with when it was
taken. The standalone call at the end of `_f292_report()` is gone: it was the *same* census as the
failure stage's, printed a second time without a stage label, which is exactly the ambiguity that
made occurrence #9 misread. `_f292_pool_errors()` deliberately stays outside the snapshots and
un-staged, because `_PoolErrorRecorder` records continuously from import - its silence is a fact
about the session, not about the moment it was read, and stamping it with a stage would claim
otherwise. `hub/tests/conftest.py` only; **no `hub/hub/` change**, the same scope guard `d1b` held.

**Mutation-checked, and the first attempt at the check was too weak.** A throwaway file (written,
run and deleted inside this iteration) opens a *pooled* connection, writes into a committed table
without committing so it holds SQLite's write lock, snapshots the two early stages, then races a
task that rolls back and closes at 0.6 s against a `DROP TABLE` whose own connection is set to
`PRAGMA busy_timeout=200`. The DROP fails with the real `OperationalError: database is locked`, the
holder releases during the wait, the connection is collected, and the late census is taken. This is
the scenario the section above described, not a stand-in for it.

The first draft asserted on `"IN TRANSACTION"` appearing in the early stage. That would have passed
against the *pre-change* conftest, because the checked-out registry line already says
`-> IN TRANSACTION` for a connection the pool knows about. Caught before it was believed; the
assertions are now on the census line specifically
(`  [before dispose] ever-seen:     sqlite3 handle OPEN, IN TRANSACTION`). Run against the stashed
pre-change `conftest.py`, **both tests fail**; against the change, both pass. That is the mutation
check - an instrument change asserted only against itself is not evidence.

What it printed, and it is worth reading beside occurrence #9's:

```
  [before dispose] ever-seen: 1 connection(s) recorded, 0 already collected, 1 with an OPEN sqlite3 handle
  [before dispose] ever-seen: last checked out by ...::test_the_early_stage_sees_a_holder... [task: Task-2 ...]
  [before dispose] ever-seen:     sqlite3 handle OPEN, IN TRANSACTION, worker thread alive, _running=True
  [before drop_all] ever-seen:     sqlite3 handle OPEN, IN TRANSACTION, worker thread alive, _running=True
  [at failure]     ever-seen: 2 connection(s) recorded, 1 already collected, 1 with an OPEN sqlite3 handle
  [at failure]     ever-seen:     sqlite3 handle OPEN, idle, worker thread alive, _running=True
```

The last two lines are **occurrence #9's printout, character for character in shape** - one open
handle, idle, healthy - produced by a scenario in which a holder demonstrably *did* hold the file.
That is the clearest possible statement of what the late-only census was worth.

**A caveat the reproduction exposed and the ledger should carry.** At the failure stage the surviving
open connection is labelled with the *same test nodeid* as the holder was, because the label is
`_CURRENT_TEST` and both belong to the same test. Label alone does not distinguish victim from
holder; **transaction state does** - the holder reads `IN TRANSACTION`, the victim `idle`. Occurrence
#9's `idle` was therefore already the victim's signature, and a future reading should not treat a
matching nodeid as identification.

**Green-path cost, measured rather than asserted.** The snapshots *are* built on the green path -
twice per test, in the `app` fixture's reset - so the earlier claim that "cost on the green path is
unchanged" was wrong, and this section says so rather than repeating it. At a full `_EVER_SEEN`
(512 entries, all collected - the CI shape, where 495 of 506 were): **76 us per snapshot**, i.e.
~0.6 s over a 4,000-test suite that takes 15-25 minutes. The cost is O(size of `_EVER_SEEN`), not
O(open connections), because a collected weakref still has to be dereferenced. Accepted; the number
is in the `_f292_snapshot` docstring so nobody has to re-measure it.

**Verified green and silent.** `ruff check src/ hub/ tests/` and
`black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/` clean over CI's exact paths.
Both historically-failing files under `py -3.11`: **21 passed**, and a grep for `F292 DIAGNOSTIC` and
`ever-seen` over the full output returns **0** - the report still fires only on the failure path.
The `PytestUnhandledThreadExceptionWarning` in that run is F295's pre-existing signature, confirmed
as such by `d1b`, not a regression from this.

**What this does and does not buy.** It buys one thing: the *next* occurrence's silence will be
informative where #9's was not. It names no holder, changes no product code, and does not lower the
20.4 % rate by a point. If the early census also comes back empty, the child-process candidate named
above becomes the live one.

### Occurrences #10 and #11 — the pool log is not silent, and #9's silence was a session, not a fact

**Read 2026-09-08 by `d5`, from two CI runs that concluded *after* the iteration which called this
hypothesis dead.** Both are F292 by signature, classified from their own logs rather than counted as
red, and both carry `d1b`'s instrument but not `d1c`'s per-stage census (they predate `b682176`).

| | #10 | #11 |
|---|---|---|
| Run / sha | `34205968391` / `8868088` | `34206652706` / `a84e608` |
| Failing job | `hub-test` only | `hub-test` only |
| Errored at setup of | `test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` | `test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |
| Reported | 08:57:25Z | 09:06:08Z |
| `sqlalchemy.pool` ERROR records | **1** | **3** |

**Every one of the four records is the same traceback**, and it is the path `d1a` argued for:

```
[sqlalchemy.pool.impl.AsyncAdaptedQueuePool] Exception during reset or similar
  pool/base.py:986   in _finalize_fairy        fairy._reset(
  pool/base.py:1441  in _reset                 pool._dialect.do_rollback(self)
  engine/default.py:712 in do_rollback         dbapi_connection.rollback()
  dialects/sqlite/aiosqlite.py:338 in rollback self.await_(self._connection.rollback())
  util/_concurrency_py3k.py:132 / :196         value = await result
  aiosqlite/core.py:197 in rollback            await self._execute(self._conn.rollback)
  aiosqlite/core.py:160 in _execute            return await future
asyncio.exceptions.CancelledError
```

**What this corrects.** Occurrence #9 printed *"`sqlalchemy.pool` logged NO error this session"*, and
that was read here as ruling out every path where SQLAlchemy gives up on a connection and leaves its
handle open — i.e. as killing `d1a`'s silent-discard mechanism outright. **Two runs later the same
instrument printed the error.** The recorder was working; #9 was simply a session in which no reset
failed. The negative was a fact about one session and was written down as a fact about the
mechanism — which is, for the third time in this entry, an instrument's silence being read as a
statement about the world. `d1a` made it about the registry, #9 made it about the census, and this
makes it about the pool log.

**What it adds, stated no more strongly than it supports.** There is now a *named, measured* way for
a connection of the product engine to be abandoned with its transaction unresolved: the rollback in
`_finalize_fairy` is **cancelled mid-flight** (`CancelledError` out of `aiosqlite`'s
`_execute`/`await future`, i.e. the awaiting task was cancelled while the worker thread held the
statement). `CancelledError` is a `BaseException`, so `_finalize_fairy`'s `except BaseException`
catches it, logs it here, and calls `invalidate()` → `__close()` → terminate → `stop()`, which on
this dialect only *queues* the real `sqlite3` close. A rollback that never completed leaves the write
lock held; a close that is only queued does not take it back.

**This is a mechanism that fits, not the holder named.** Two things it does not establish: that the
cancelled connection is the one holding the file at the DROP (the census is still late-only in both
runs, and both again print one `idle` handle — the victim's signature), and how many of the earlier
occurrences had the same records, since only occurrences #9 onward carried the recorder at all. The
per-stage census (`d1c`, `b682176`) has **not yet fired**: the six runs after it are green.

**Where the cancellation plausibly comes from, unverified.** `agent_trigger.py:1190`'s un-awaited
`asyncio.create_task(_execute_run(...))` is the entry's standing candidate for a task outliving its
test, and a task torn down at loop close is cancelled — which is exactly this signature. Nothing here
measures that link; it is named so the next occurrence's reader has a hypothesis to falsify rather
than a blank.

**Bearing on `2026-09-07-a-dead-connection-is-never-handed-back-out` (F295), first in tonight's
`ORDER:`.** `d1a` concluded *do not expect that change to close F292*, and this does not overturn it:
F295 is about a connection whose worker thread died being handed back out, and the connection here is
invalidated rather than reused. But the two now share more than a call site — both are about a run's
database work being abandoned rather than settled — so a night that builds F295 should record whether
the CI rate moves, and must not treat a movement as proof either way.

**Rate unchanged by this reading:** 20.4 % over the 54-run window to 2026-09-08T08:26Z stands; #10
and #11 fall after it. Occurrence floor rises from 9 read to **11 read**, against a classified floor
of 22.

### Occurrence #12 — 2026-09-09, and it is what is holding the merge gate shut now

CI run `34329305198`, commit `2b33a6e` on `autonomous/2026-09-08-daily`, `hub-test` **failure**.
`sqlite3.OperationalError: database is locked` on `DROP TABLE requirement_drift`, with
`asyncio.exceptions.CancelledError` in the pool log — the same shape as the earlier occurrences,
not the starlette defect the day window repaired an hour before it.

Two things follow, both worth keeping.

**F295 shipping did not stop it.** The note above asked a night that built F295 to record whether
the CI rate moves. This is the first occurrence read after `00d72a8`/`0f06bea` landed, and it says
the answer is *not obviously*. One occurrence is not a rate; it is recorded here so the next
window compares against something rather than re-deriving the question.

**And it is now the whole of what the gate is waiting on.** The commit before it, `630473f`,
concluded **success** — the first green CI on this branch, and the proof that the starlette repair
was the right one. The gate reads CI at `HEAD`'s sha, so the branch went from *deterministically
red for a reason nobody had read* to *intermittently red for a reason five windows have read*.

### Occurrences #13, #14 and #15 — 2026-09-10, and the per-stage census finally fired: three times, unanimously

`d1c` built the per-stage census and said *"the next occurrence's silence will be informative where
#9's was not"*, then noted the instrument had **not yet fired** — the six runs after it were green.
It has now fired three times in one day, on three consecutive CI runs of
`autonomous/2026-09-08-daily`, and all three printed the same thing.

| # | run | commit | erroring test | predecessor |
|---|---|---|---|---|
| 13 | `34423636080` | `bb08dc4` | `test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer` | `…::test_a_flow_staffing_its_own_review_is_not_refused` |
| 14 | `34424369060` | `4937ece` | same test, same file | same predecessor |
| 15 | `34452397977` | `6e1a054` | `test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` | `…::test_an_unstaffable_review_does_not_stop_the_flow_doing_other_work` |

Each: `4039 passed, 18 skipped, 1 error`, `sqlite3.OperationalError: database is locked` on
`DROP TABLE requirement_drift` at the `app` fixture's schema reset
(`hub/tests/conftest.py:713-716`), one `sqlalchemy.pool` ERROR record — `CancelledError` inside
`_finalize_fairy` → `_reset` → `do_rollback` → `aiosqlite.core.rollback`.

**The census result, identical in all three:**

```
  [before dispose]  ever-seen: N recorded, M collected, 0 with an OPEN sqlite3 handle
  [before drop_all] ever-seen: N recorded, M collected, 0 with an OPEN sqlite3 handle
  [at failure]      ever-seen: …, 1 with an OPEN sqlite3 handle
  [at failure]      ever-seen:     sqlite3 handle OPEN, idle, worker thread alive, _running=True
```

(`N/M` = 175/162, 168/156, 32/22 respectively.)

**Read it with `d1c`'s own criterion and it says one thing clearly.** `d1c`'s mutation check
established that *transaction state distinguishes victim from holder* — a holder reads
`IN TRANSACTION`, a victim reads `idle` — and that a matching nodeid identifies nothing. The single
late handle here reads **`idle`**, and its nodeid matches the erroring test's own fixture-setup task,
which is the task that ran `engine.begin()` for the DROP. So the late handle is the **victim** —
almost certainly the DROP's own connection, returned to the pool when the `async with` unwound
before the `except` block sampled (`Connections in pool: 1`, `Checked out: 0` at failure agrees).
It is not the holder and must not be read as one.

**Which means the early sampling came back empty — three times.** That is the branch `d1c` called
*"the strong result"*, and it is now measured rather than anticipated. Two consequences.

**The dispose-before-drop mitigation is doing its job and cannot be the fix.** `conftest.py:706`'s
`await _REAL_ENGINE.dispose()` was written for a previous test leaving a connection checked out.
At `[before drop_all]` — after the dispose, before the DROP — **zero** connections this process
opened hold an open handle, in all three runs. The file is clean at that instant and the holder
arrives afterwards. No amount of tidying earlier helps.

**But the child-process candidate does not survive the neighbourhood, and `d1c` expected it to.**
`d1c` named a lingering subprocess as *"the candidate class to look at first"* if the early census
came back empty. Measured now: `grep -c subprocess` over both erroring files returns **0 and 0**,
and in each of the three runs the immediate predecessor is a test **in the same file**, so no
subprocess is spawned anywhere in the failing neighbourhood. A child from an earlier test could
still linger — this does not rule the class out — but it is no longer where to look first.

**What the three predecessors share is the entry's other candidate.** All three are
flow-fires-a-review tests (`a_flow_staffing_its_own_review`, `an_unstaffable_review_…_other_work`),
and both erroring files are the scheduler-flow files. That is the shape of
`agent_trigger.py:1190`'s un-awaited `asyncio.create_task(_execute_run(...))` — a staffed review
fires a turn, the turn's task outlives its test, and a task torn down at loop close is cancelled,
which is exactly the `CancelledError` the pool log records. **This promotes that candidate from
"named so the next reader has a hypothesis" to "the one the evidence now points at"**, and demotes
the child process. It still names no holder: nothing here attributes the `CancelledError` to a
specific connection.

**The next instrument follows from the same limitation, for the third time.** Every sample is taken
either side of the wait, never during it, so a holder that acquires the lock after
`[before drop_all]` and releases inside the 30-second busy timeout is invisible at all three stages
— and that is precisely the profile the evidence now describes. Sampling around a wait cannot see a
holder that lives only inside it. What would: a **concurrent** snapshot taken from a separate task
while the DROP is blocked, and attributing each `sqlalchemy.pool` ERROR record to a connection
identity rather than logging it unattributed. Both are `hub/tests/conftest.py`-only.

**Bearing on the merge gate.** Occurrence #12 was recorded as *"what is holding the merge gate shut
now"*; three more in one day says that is not a passing state. Of the four CI runs concluded on this
branch across `6484de4..6e1a054`, **three are this finding** and one was cancelled. The day window's
gate condition 3 reads CI at `HEAD`'s exact sha, so on the present rate the gate is not merely
racing the window's own commits — the diagnosis iteration 1 reached — it is waiting on a run that is
more likely than not to conclude `failure` for a reason unrelated to anything either window built.
**That is now a release-process problem, not only a test-suite one**, and it is the strongest
argument yet for fixing F292 ahead of feature work.

**Count.** Occurrence floor rises from 11 read to **15 read**. The 20.4 % rate over the 54-run
window to 2026-09-08T08:26Z is *not* re-derived here, but three failures in three consecutive runs
sits well above it and a window that needs the real number should re-measure rather than quote it.

### The reset was never one transaction — measured 2026-09-10, and it removes the need for a holder that lives 30 seconds

**Every instrument in this entry has looked for a connection holding the file when the DROP runs,
and every one has assumed the DROP is inside a transaction. It is not.** Measured this session
against SQLAlchemy 2.0 / aiosqlite on the suite's own shape, three separate ways:

| measured | result |
|---|---|
| `driver_connection.in_transaction` immediately after the first `DROP` inside `async with engine.begin()` | **`False`** |
| `BEGIN` statements reaching the driver during that block | **none** |
| a foreign `sqlite3` connection asking for the write lock between two `DROP`s of one block | **it got it** |

SQLAlchemy's pysqlite/aiosqlite dialect emits no `BEGIN` until a **DML** statement, and `DROP TABLE`
is DDL. So `async with engine.begin()` around `Base.metadata.drop_all` provides **no mutual
exclusion at all**: the ~90 drops are ~90 independent autocommit write transactions, each taking and
releasing SQLite's write lock. Reproduced end to end in isolation — foreign writer takes the lock
mid-sequence, the next `DROP` fails `database is locked` after the full busy timeout. That is the CI
signature, produced without a dead worker thread, without a subprocess, and without anything holding
the file for thirty seconds.

**This explains the two things the entry has repeatedly called blind spots, and they were not blind
spots — they were the wrong model.**

- **Why `[before drop_all]`'s census is always empty.** It samples once, before the sequence starts.
  The vulnerable window opens **ninety times after that sample**, and a competing writer only has to
  win one of them. No sampling either side of the sequence can see it; the instrument was correct
  and the question was wrong.
- **Why the failure lands on `DROP TABLE requirement_drift` and not on the first table.** Under a
  one-transaction model that ordering is unexplained. Under ninety independent transactions it is
  the expected shape: the sequence runs until it loses a race, and where it loses is arbitrary.

**Fix, and it is one line** (`hub/tests/conftest.py`, the `app` fixture's reset): issue
`BEGIN IMMEDIATE` before `drop_all`, so the write lock is taken once and held for the whole reset.
Measured with the same foreign writer: it is **refused** the lock, and the remaining drops proceed
cleanly. One window instead of ninety.

Gated by `hub/tests/test_schema_reset_holds_the_write_lock.py` — two tests, **mutation-checked three
ways, and the first form of one test did not survive its own mutation.** Removing the line kills test
one; making the demonstration helper ignore its flag kills test two; **moving `BEGIN IMMEDIATE` to
after `drop_all` survived the original test**, because that test compared statement indices behind an
"if any DROP was seen" guard and on a fresh database `drop_all` emits no DROP at all. Replaced with a
per-statement `in_transaction` sample, which kills it. The residual gap — a first-`app`-test-of-
session cannot catch the line being *moved*, only deleted — is stated in the test's own docstring.

**What this does NOT claim.**

- **Not that F292 is fixed.** It was not reproduced in CI and a ~20-40 % race cannot be asserted by a
  test. What is established is that a race with this exact signature **exists**, is reachable on
  every reset, and is now closed. Whether it was *the* one shows up as a rate change, and the next
  window should measure the rate rather than assume the answer either way.
- **Not that the holder is named.** It removes the race competing writes have to win rather than
  identifying what writes. **If F292 survives this, that is informative**: it means the holder
  arrives *before* the reset rather than during it, which is a narrower finding than anything this
  entry has carried.
- **Not a refutation of the `agent_trigger.py:1190` candidate.** That call site remains an un-awaited
  background task and a real defect. Note though that the mechanism this entry's `**Status:**`
  paragraph describes is an **unbounded hang with no `busy_timeout` involved**, while CI's failure is
  `database is locked`, which *is* a busy-timeout expiry. Those are two different failure modes and
  the entry has been carrying them under one heading.

### Two hypotheses tested and refuted on the way, recorded so nobody pays for them twice

**1. A second engine — refuted.** `JobScheduler._get_sync_engine` (`hub/hub/scheduler.py:2354-2366`)
builds a **separate synchronous** engine on the same SQLite file for APScheduler's jobstore. Its
connections are in a different pool, so no `connect`/`checkout` event fires on the listened engine
and they are **invisible to `_EVER_SEEN` at all three census stages** — which would explain an empty
census perfectly. `hub/hub/api/v1/jobs.py:498-517` already documents the *mirror* of F292 on those
two engines in production: a request holding a transaction open makes the jobstore's own INSERT fail
`database is locked`. Same file, same two engines, same error string. **It is still wrong: no test
calls `JobScheduler.start()`**, which is the only caller of `_get_sync_engine`, so that engine is
never constructed during the suite. Verified by grep across `hub/tests/`.

**2. `SQLITE_BUSY_SNAPSHOT` — refuted for this code path, and worth knowing anyway.** In WAL, a
connection that has taken a read snapshot and then asks to upgrade to a write is refused
**immediately, with `busy_timeout` ignored and nothing holding the file** — SQLite returns
`database is locked` rather than risk deadlock. Measured: **0.000 s with `busy_timeout=30 s`
ignored**, against **2.234 s honoured** for a genuine holder. Had F292 been this, an empty census
would have been the *correct* reading rather than a blind spot, and no holder would ever have
existed to find. `drop_all(checkfirst=True)` does read before it drops (~90 `PRAGMA table_info`
calls), and `PRAGMA table_info` **does** take a snapshot in raw `sqlite3` — but through SQLAlchemy
those reads run in autocommit, so no snapshot is held and the mechanism cannot fire here. **The
discriminator is one number nobody has ever recorded: how long the failing `DROP` waited.** Under a
held-lock model it is ~30 s; sub-second would mean this entry is chasing a holder that does not
exist. Worth adding to the diagnostic regardless of the fix above.

### The rate, measured 2026-09-11 (day `D-1`) — and the mitigation is not a fix

`DIRECTION.md`'s 2026-09-11 section spent the day's drive slot on this instead of a scoped drive,
because the `BEGIN IMMEDIATE` mitigation (`af69a27`, 2026-09-10) shipped with **two** runs behind it
and was therefore unproven. **It has now failed one.** `F292` reproduced on the mitigated tree at
`f51ec21`, run `34576656234`, queued 2026-09-11T07:55Z and concluded 08:12Z:

```
ERROR tests/test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
===== 4041 passed, 18 skipped, 238 warnings, 1 error in 909.23s (0:15:09) ======
```

Same signature, same file, and a test already in this finding's pre-mitigation set. **The
`BEGIN IMMEDIATE` section above is confirmed as a mitigation and refuted as a fix.**

**That was the outcome that section itself named as informative.** It reads, in its list of what the
change is not: *"**If F292 survives this, that is informative**: it means the holder arrives
*before* the reset rather than during it, which is a narrower finding than anything this entry has
carried."* It has survived. Wrapping the ~90 `DROP`s in one transaction removes the window in which
a competing writer can take the lock *between* two of them; a writer that already holds the file
when the transaction opens is unaffected, and `BEGIN IMMEDIATE` will simply wait out its
`busy_timeout` and raise the same error. **The holder is present before the reset begins.** That is
the narrowing this measurement buys, and it is worth more than the rate.

**The rates, every red classified from its own log.**

| window | completed `ci.yml` runs | F292 | F314 | other | any red |
|---|---|---|---|---|---|
| **with the mitigation** — `af69a27`…`f51ec21`, 2026-09-10T12:55Z → 2026-09-11T08:12Z | **17** | **1 (5.9%)** | 0 | 0 | 1 |
| without it — `b3f4ba2`…`5da3d55`, 2026-09-09T08:11Z → 2026-09-10T10:17Z | 41 | **11 (26.8%)** | 2 (4.9%) | 2 (4.9%) | 15 (36.6%) |

**What that licenses, stated carefully, because 1 in 17 is a small number.** Under the
pre-mitigation rate, one or fewer failures in 17 runs has probability
`0.732^17 + 17 × 0.268 × 0.732^16 ≈ 0.036`. So *"the mitigation changed nothing"* is disfavoured at
one-sided **p ≈ 0.036** — suggestive, at the edge, and **not** a result to build on. In the other
direction the exact 95% interval on 1/17 runs from about **0.1% to 28.7%**, which contains the
pre-mitigation 26.8% outright. **Both readings are live: this is consistent with a real 4-5x
reduction and equally consistent with no reduction at all.** What is no longer live is "fixed".
Separating a halved rate from an unchanged one needs on the order of a hundred runs, which this
branch will not produce; the useful next step is the mechanism the paragraph above narrows to, not
more counting.

**Scope.** `af69a27` is on `autonomous/2026-09-08-daily` and **is not an ancestor of `master`**
(`git merge-base --is-ancestor af69a27 master` → no), so "runs carrying the mitigation" means
exactly this branch at or after that sha. `ci.yml` has **no path filter** — `on.push.branches` is
`[master, 'autonomous/**']` and nothing else — so a docs-only commit runs the full hub suite like
any other. Confirmed per-run rather than assumed: all 17 `hub-test` jobs ran to completion in
10–15 minutes, which is full-suite length. One `cancelled` run (`6484de4`) is excluded from both
rows. One run was still in flight at close (`6f7e486`, queued 08:03Z) and is excluded from both the
numerator and the denominator. The pre-mitigation window's lower edge is the 60-row listing limit,
not a chosen date.

**A method note that cost this measurement its first conclusion.** It was written up as
**16 of 16 green** and was wrong for about twenty minutes, because the mitigated window's two
in-flight runs had been excluded as *unknown* — correctly — and then one of them concluded `failure`
before the iteration committed. **An in-flight run is not a green and it is not a null; it is a
pending observation that can invert the finding.** Re-read `gh run list` immediately before writing
a rate down.

**Why the per-run classification is the whole point, stated as the numbers it changes.** An
unclassified count of the pre-mitigation window would have read **15 in 41 = 36.6%**, and `F314`
alone would have inflated the F292 figure by nearly a fifth. Each verdict below comes from that
run's own `short test summary info`:

| run | sha | signature | verdict |
|---|---|---|---|
| `34576656234` | `f51ec21` | `ERROR test_reviewer_is_not_the_author.py` — `database is locked` | **F292, mitigated tree** |
| `34457272005` | `09e189f` | `ERROR test_flow_fires_a_review_turn.py` — `database is locked` | F292 |
| `34455127011` | `f563815` | `ERROR test_reviewer_is_not_the_author.py` — `database is locked` | F292 |
| `34454842948` | `a779891` | `ERROR test_flow_fires_a_review_turn.py` — `database is locked` | F292 |
| `34452397977` | `6e1a054` | `ERROR test_flow_fires_a_review_turn.py` — `database is locked` | F292 |
| `34424369060` | `4937ece` | `ERROR test_reviewer_is_not_the_author.py` — `database is locked` | F292 |
| `34423636080` | `bb08dc4` | `ERROR test_reviewer_is_not_the_author.py` — `database is locked` | F292 |
| `34419532531` | `fc9001a` | `FAILED test_flow_holds_the_loop_requirements.py::test_a_wide_flows_state_is_still_one_call` — `RuntimeError: <asyncio.locks.Lock …> is bound to a different event loop` | **F314** |
| `34417742169` | `32fb7f4` | `ERROR test_flow_fires_a_review_turn.py` — `database is locked` | F292 |
| `34417119378` | `3aa43f1` | `ERROR test_reviewer_is_not_the_author.py` — `database is locked`, `[SQL: DROP TABLE requirement_drift]` | F292 |
| `34415761664` | `cd78e17` | both files — `database is locked` (2 errors) | F292 |
| `34414764597` | `e6da0a0` | `FAILED …::test_a_wide_flows_state_is_still_one_call` — same `RuntimeError` | **F314** |
| `34409508004` | `54ed088` | `ERROR test_flow_fires_a_review_turn.py` — `database is locked` | F292 |
| `34329305198` | `2b33a6e` | both files — `database is locked` (2 errors) | F292 |
| `34328330013` | `ed7d3ef` | `FAILED test_mcp_adapter_online.py::…_is_one_the_app_mounts` — `AssertionError` on `create_app().routes` | **starlette, deterministic** |
| `34327744562` | `b3f4ba2` | same | **starlette, deterministic** |

Three things fall out of that table that no aggregate rate would have carried:

- **`F314` has a CI signature, and it is not an assertion.** That entry filed it as an order
  dependence measured *locally* at ~1 in 8, with two affected tests named. Both CI occurrences are
  one of those two — `test_a_wide_flows_state_is_still_one_call` — and both present as
  `RuntimeError: <asyncio.locks.Lock object …> is bound to a different event loop`, not as the
  failed assertion the name suggests. So `F314` is identifiable in a log at a glance, it does fire
  on Linux CI and not only on this machine, and its CI rate here (2/41 = 4.9%) is lower than the
  local ~12.5% rather than equal to it. That last comparison is weak — 2 events — but it is the
  first CI measurement that entry has.
- **The two `test_mcp_adapter_online.py` reds are not flakes at all.** They are consecutive
  (`b3f4ba2` 08:11Z, `ed7d3ef` 08:17Z) and the very next run is green at `630473f`, *"fix(ci): the
  route was mounted all along; the test was reading a structure starlette deleted"*. A deterministic
  defect present at two shas and fixed at the third. They stay in the denominator — the suite ran to
  the end in both, so F292 had its chance — and out of the numerator.
- **F292's occurrences are narrower than "the flow family".** All 12, the mitigated one included,
  land in exactly **two files and three tests**:
  `test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`
  (7 runs), `test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer`
  (5), and `…::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` (2, one of
  them the mitigated-tree occurrence). 14 error rows across 12 runs. Every one of the three is a
  flow-fires-a-review test, which is the same neighbourhood the `agent_trigger.py:1190` candidate
  was promoted from.

**One control this measurement does not have.** `master`'s newest `ci.yml` run is `5d928f5` at
2026-09-10T09:46Z, *before* the mitigation, so there is **no unmitigated run anywhere in the
mitigated window**. Nothing here separates the mitigation's effect from a concurrent change in the
hosted runners. Recorded rather than argued away; the next `master` run is the control, whenever one
happens.

**Method**, so it can be repeated without re-deriving it:

```bash
gh run list --branch autonomous/2026-09-08-daily --workflow ci.yml --limit 60 \
  --json headSha,conclusion,status,createdAt,databaseId \
  --jq '.[] | [.createdAt, .headSha[0:7], .status, .conclusion, (.databaseId|tostring)] | @tsv'
# then, for every run whose conclusion is `failure` -- and only those, never one still in progress:
gh run view <id> --log-failed | awk '/short test summary info/{f=1} f' | grep -E '(FAILED|ERROR) '
```



### A third reproduction the same day, and the statement that fails is the mitigation's own

Recorded at `D-6` while checking the merge gate, so the denominator above is not re-derived here —
only the event and the one thing about it that is new.

`7970930` is the day window's `D-5` commit and it touches **nothing but documentation**: the review
page, `APPROVALS.md`, this file, the state file and the log. Its CI run `34586826361` concluded
`failure` at 2026-09-11 10:13Z on the familiar signature, in the familiar file:

```
ERROR tests/test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer
  sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
  [SQL: BEGIN IMMEDIATE]
```

Two things this adds to the section above, neither of them a rate.

**The failing statement is `BEGIN IMMEDIATE` itself.** The section above reasoned its way to this —
surviving the mitigation *had* to mean the holder arrives before the reset rather than during it —
but reasoned it from which test failed and when. Here the traceback names the mitigation's own
statement as the one that cannot acquire. That is the same conclusion arriving as direct evidence
instead of inference, and it retires the remaining reading in which the mitigation fires correctly
and something later in the fixture is the loser.

**All three of today's reproductions are in one test file.** `f51ec21`, `8d227de` and now `7970930`
each failed in `tests/test_reviewer_is_not_the_author.py`, and two of the three commits changed no
code at all. A fault that is genuinely a global race should not concentrate like that. Whether the
concentration is the fixture's (what that file's setup holds open, and for how long) or merely its
position in the run order is **unmeasured** — but it is a far cheaper thing to look at than another
week of rate estimation, and it is the first lead this finding has had that points at a place rather
than at a probability.

### The 2026-09-12/13 night window: 7 of 18, every one on `BEGIN IMMEDIATE` (recorded at `w-final`)

Recorded while writing the night window's closing entry, rather than re-deriving the table above.
The method is the one above, on branch `autonomous/2026-09-12-daily`, which **does** carry the
mitigation (`git merge-base --is-ancestor af69a27 HEAD` → yes). The window ran from `c12a7d3`
(21:55Z) to `fa07089` (02:48Z). **18 runs completed. 7 were red, all 7 F292 and nothing else:**
setup-time `database is locked`, `1 error`, and `[SQL: BEGIN IMMEDIATE]` in every one.

| run | sha | errored at setup of |
|---|---|---|
| `34721761782` | `45d9de4` | `test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer` |
| `34722726736` | `00a5569` | same |
| `34724236621` | `5b6f393` | `…::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |
| `34727910846` | `39b6be3` | `…::test_a_wedged_review_is_restaffed_to_a_real_reviewer` |
| `34728358869` | `f492261` | `test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` |
| `34729890812` | `6ebcd9f` | `test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted` |
| `34733956679` | `fa07089` | `test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn` |

What this adds:

- **7 in 18 is 38.9%, on the mitigated tree.** That is above the unmitigated window's 26.8%. With
  the 1 in 17 above, the mitigated count is now 8 in 35. The table's reading, *"consistent with no
  reduction at all"*, is no longer a tie. **The rate gives no support to the mitigation now.**
- **Six of the seven shas carry no product change.** Only `6ebcd9f` touched `hub/hub/`, and its
  successor `997ff5d` changed the same file and went green. The tree under test does not explain
  these errors.
- **Still the same three tests in two files**, five of the seven in
  `test_reviewer_is_not_the_author.py`. The concentration lead above holds and is still
  unmeasured.
- Two runs (`1b3d52c`, `44879bb`) were in flight at the time of writing and are excluded from both
  counts, per the method note above.

### 2026-09-21 night (`f292-impl-1`): each test gets its own database file — landed, not yet measured on CI

Taken as the operator's "cheap shape" (APPROVALS 2026-09-21 item 3: *give them their own
database*), timeboxed to two firings, and deliberately **not** another attempt to name the holder.
Every section above agrees on one fact: the holder is present *before* the reset and `dispose()`
cannot reach it. So the reset no longer shares a file with it. `hub/tests/conftest.py` adds a
`do_connect` listener that opens `_current_test_db_file` rather than the URL's path, and the `app`
fixture moves that to a fresh `hub-test-<n>.db` in `_TEST_DB_DIR` right after its `dispose()`,
best-effort deleting the previous file and its `-wal`/`-shm` (an unlink succeeds on Linux even
while a leaked connection holds the file; on Windows it fails silently and the directory goes at
session end). `engine.url` is unchanged, so `assert_engine_is_disposable` and every guard on it
still see `_TEST_DB_DIR`. Tests that do not take `app` keep seeing the last `app` test's file,
exactly as they saw its tables before.

**Measured locally**, `hub/tests/test_each_test_gets_its_own_database.py`: a raw `sqlite3`
connection holding `BEGIN IMMEDIATE` plus an uncommitted write on the current file, then the
fixture's own sequence — the reset completes. **Control:** the same test with the file move deleted
fails after 30 s with `database is locked` on `BEGIN IMMEDIATE`, CI's signature statement for
statement. Removing the move from the fixture fails the file-identity test. What this does **not**
show: that the CI holder is a connection on the old *file* rather than something that would follow
the test to the new one. Only CI can say, and the pre-fix baseline tonight is **2 of 4 completed
runs red, both F292** (`3e06634` run `35659893420`, `1fd204d` run `35660385419`, both
`test_a_wedged_review_is_restaffed_to_a_real_reviewer`, `1 error`; `85efe66` and `5bb9e6c` green).
Full local hub suite with the fix: 4478 passed, 86 skipped. The ledger's own method note
applies: the rate on this sha onward is recorded in the night log per push. Zero F292 in 11
completed runs is what puts a 25% rate below p = 0.05 (0.75^11 ≈ 0.042).

**`f292-impl-2` (2026-09-21 night, second and last timeboxed firing): 1 of 1 post-fix run green,
which is not a rate.** `b630252` (the fix commit), run `35665344029`: every job green, hub-test
`4471 passed, 20 skipped` in 11 min, no `database is locked` in its log. Every run on this
branch: pre-fix 2 of 4 red (both F292), post-fix 0 of 1. At the 25% baseline, one clean run
happens 75% of the time by chance, so this says nothing yet. The timebox is spent and nothing
further was built. The tally carries on over later pushes (the night log records each one), and
F292 stays **open** until 11 consecutive post-fix completed runs show no F292, or one shows it.
If one does, the per-file move did not reach the holder. The next lead is then the one above:
the holder follows the test, so it is not a connection on the old file.

**Closed 2026-09-22 (interactive, after the night and day windows): 0 F292 in 16 completed
post-fix runs.** `gh run list --branch autonomous/2026-09-21-daily --workflow ci.yml`, every
completed run from the fix commit on: `b630252` `3d9e2e4` `69f1531` `90ef2b1` `a5e5a49` `bda6130`
`4875f53` `58f773f` `04226a4` `dac9891` `518ea3f` `f430584` `90a5d27` `921384f` `6c0a467`, all
**success**; `45d769f` (run `35667708908`) **failure**, and `grep -c 'database is locked'` over its
failed log is **0**: it is an F394 hang (see F394's foot), not F292. The night log's iteration 10
left that run out of the tally because it was the tests-first commit, assuming the 43 rows written
to fail were what turned it red. That was wrong: the run never reached them. It was killed at 9%.
Counting it as a non-F292 run, the post-fix tally is 0 of 16, and it is past the 11-run bar either way.
Pre-fix on the same branch: 2 of 4 red, both F292. What is still not shown is the mechanism,
namely that the CI holder was a connection on the old file. That is the reading the result fits, and it was never observed.


---

## F293 (B) — the F126 guard is on the predecessor's lifecycle, so following the refusal's own advice mints the duplicate successor it was built to prevent

**Status:** fixed (2026-09-25) by `1f79ee8` + `35fe156` (`a-checkpoint-is-handed-over-once-and-says-where-it-went`, archived 2026-09-25); driven 2026-09-25 on a fresh trial Hub (8026, `drive0925morning`, Haiku): `t_d2_cutover_guard.py` 21/21, probe 1's third press 409 naming the successor.
**Status when filed:** open. Found 2026-09-06 (day D-2) by driving the night's guard (`3142a91`)
independently, on a fresh Hub on 8011 with a fresh database and a throwaway project. The guard is
real and the night's own three-press drive reproduces exactly as recorded — this is a **different
route to the same rows**, not a retraction of the fix.

`cut_over` refuses when `predecessor.lifecycle == "archived"`
(`hub/hub/checkpoint_cutover.py:97`), and the refusal it raises ends with:

> …if this one was cut over already, its successor holds the work, and if it was archived by
> hand, **unarchive it first**.

`POST /projects/{p}/agent/{a}/conversations/{c}/unarchive`
(`hub/hub/api/v1/agent_chat.py:549`) is *"Never refused — reopening obstructs nothing."* It sets
`lifecycle = "open"` and nothing else. So an operator who reads the 409, follows the sentence it
ends with, and presses again gets **F126 back, in full**: the same spent checkpoint mints a second
successor, delivers it the same rendered checkpoint, and the second delivery is a whole billed turn
spent rediscovering that the work is done.

The refusal cannot tell the two cases apart, because nothing in the schema records that this
checkpoint was already handed over — which is precisely the `cut_over_to_conversation_id` column
F126 recommended as shape (2) and the night deferred as needing a migration. The guard that shipped
is a *proxy* for "this checkpoint is spent", and the proxy is erasable by a route that is
documented as never refusing.

**Reproduced live**, `scripts/drive/t_d2_cutover_guard.py` probe 1, twice on two separate fresh
databases:

```
POST .../checkpoints/ckpt-9476f5dc1d25/cutover                 200  successor conv-d4609d88f98f
POST .../checkpoints/ckpt-9476f5dc1d25/cutover                 409  "...unarchive it first."
POST .../agent/delta/conversations/conv-d2-unarchive/unarchive 200  lifecycle: open
POST .../checkpoints/ckpt-9476f5dc1d25/cutover                 200  successor conv-7b9118e2c2f7
```

Rows afterwards — two successors of one predecessor, two undelivered checkpoint entries:

```
conv-d4609d88f98f  handoff  open  lineage conv-d2-unarchive  "Continued: Ship the parser"
conv-7b9118e2c2f7  handoff  open  lineage conv-d2-unarchive  "Continued: Ship the parser"
entry-3ce5ff1eb8fe  checkpoint  conv-d4609d88f98f
entry-9b7ebcb1dd0c  checkpoint  conv-7b9118e2c2f7
```

`GET /projects/{p}/conversations?lifecycle=all` returns both, identically titled and both `open`,
so the operator sees two continuations of one conversation in the navigation tree with nothing to
choose between them. Same `lineage_id` — the fork that
`conversation-checkpoint`'s *"Lineage is recorded and participation is derived"* says cannot happen.

Rated **B** to match F126, whose outcome this is, rather than argued up to A on the strength of
"the product's own error message routes the operator into it".

### Shapes

1. **Shape (2) from F126, now with a second reason.** `Checkpoint.cut_over_to_conversation_id`,
   set in the same commit as the successor, refused when set. Unarchiving cannot erase it, and the
   refusal can then say *where* the checkpoint went instead of guessing between two cases. One
   migration.
2. **Cheaper, and only half.** Keep the lifecycle guard and also refuse when a `handoff`
   conversation already exists in this lineage. Closes this route without a migration, but it is
   still a proxy: it refuses a legitimate re-handover of a conversation that was archived by hand
   and never cut over, and it cannot name the successor for *this* checkpoint because the link
   still does not exist.
3. **Change the sentence, not the code.** Drop "unarchive it first" from the refusal. Cheapest,
   and wrong: the hole stays, and the operator who finds `unarchive` in the UI — where it is a
   button — walks into it without being told.

Recommendation: (1), the same recommendation F126 made, now blocking two routes rather than one.

---

## F294 (B) — two cutover presses at the same instant both succeed: the guard reads the lifecycle it is about to write, with nothing serialising the two

**Status:** fixed (2026-09-25) by `1f79ee8` + `35fe156` (`a-checkpoint-is-handed-over-once-and-says-where-it-went`, archived 2026-09-25); driven 2026-09-25 on a fresh trial Hub (8026, `drive0925morning`, Haiku): two simultaneous presses gave one 200 and one 409.
**Status when filed:** open. Found 2026-09-06 (day D-2), same drive as F293. This is the case F126's own
section named as how the defect reaches an operator in the wild — *"a second browser tab, a reload
between the 201 and the cutover, a retried request after a network timeout, or any non-UI client"* —
and it is the one the `3142a91` guard does not close, because every one of those is **concurrent**,
not sequential.

`cut_over` reads `predecessor.lifecycle` at `hub/hub/checkpoint_cutover.py:97` and writes it at
`:144`, committing at `:145`. Between the two it awaits `archivable`, creates the successor and
builds the queue entry. Two requests arriving inside that window each get their own
`AsyncSession`, each read `open`, and each go on to mint a successor. There is no row claim (unlike
`take_checkpoint`, which holds `_checkpoint_claims` at `hub/hub/api/v1/checkpoints.py:27` for the
*cheaper* half of the same pair), no `SELECT … FOR UPDATE`, and no uniqueness constraint that a
second insert could violate.

**Reproduced live**, `scripts/drive/t_d2_cutover_guard.py` probe 2 — two threads, one unspent
checkpoint, both presses issued without waiting for the other, twice on two separate fresh
databases:

```
press 0  200  successor conv-52fc8929e0fd  entry-21a198de0def
press 1  200  successor conv-f29dbde784d8  entry-0865f3946f88
```

Two `200`s, no `409`, no `500`. Rows afterwards: two `handoff` successors of `conv-d2-race`, both
`open`, both titled `"Continued: Ship the tokenizer"`, both on `lineage conv-d2-race`, and two
undelivered `checkpoint` queue entries — the second of which is a billed turn whenever the agent
next runs.

The predecessor is archived twice, which is harmless (`archive()` is idempotent in effect), so
nothing downstream errors and nothing surfaces. **The duplicate is silent.**

Note what this does *not* say: shape (2) alone does not fix it either. A
`cut_over_to_conversation_id` column read at `:97` and written at `:145` races in exactly the same
window. The fix has to be a claim or a constraint, not another field to read.

### Shapes

1. **A uniqueness constraint that the database enforces.** With shape (2)'s column in place, a
   partial unique index on the successor side — one `handoff` conversation per predecessor per
   lineage — turns the second commit into an `IntegrityError` the route can render as the same 409
   it already returns. The only shape where the guarantee does not depend on timing.
2. **An in-process claim, like `take_checkpoint`'s.** `_checkpoint_claims` already exists three
   files away and is the Hub's own established answer to this question. Cheap, no migration,
   and honest about its limit: it is per-process, so it is a guarantee only while the Hub is one
   process.
3. **`SELECT … FOR UPDATE` on the predecessor row.** Standard, and a no-op on SQLite, which is the
   deployment this is driven on. Not sufficient alone here.

Recommendation: (2) now — it is the pattern the file next door already uses, it needs no migration,
and it closes the retry-and-second-tab case that actually happens — with (1) recorded as what makes
it durable once shape (2)'s column exists.

### What held, and is worth recording as a negative

The same drive checked that the guard does **not** over-refuse. A legitimate chain still works:
cut over `conv-d2-chain`, let its successor's checkpoint entry be consumed, take a checkpoint on
the successor, cut *that* over — `200`, a two-hop chain, first hop `archived` and second `open`,
one `lineage_id` throughout, and no `"Continued: Continued:"` in either title. The widening the
night flagged (a conversation archived by hand can no longer be handed over) is real but does not
touch the chain, which is the feature. 12 of 20 verdicts held; the 8 that did not are F293 and this
finding, and nothing else.

## F295 (A) - a cancelled or superseded run's background task can leave a permanently dead worker thread, and any later reuse of its connection hangs forever

**Status:** **fixed** `00d72a8` (the pool guard) and `0f06bea` (the shutdown settle), specced,
tested `2d399c7`/`9a0fdde`/`2046c4e`, archived as
`2026-09-07-a-dead-connection-is-never-handed-back-out`, and **driven 2026-09-09** against a real
Hub process on 8011 with a real Haiku turn in flight — see *"The drive"* at the very end of this
entry. **Retired under the stricter definition**, which is the one this file adopted 2026-09-06:
fixed, tested, archived *and* driven. It no longer sits where F142 sits.

Read *"The change that fixed it"* below before acting on anything above it; three rounds corrected
the trigger this heading names.
Split out from F292's entry 2026-09-06, where it was found
while chasing F292's alembic hypothesis — it is a distinct, more general and more severe defect than
the CI flake it was discovered underneath, so it gets its own number rather than staying folded into
an entry framed around test-suite intermittency. Read `scripts/drive/FINDINGS.md`'s F292 entry, the
section starting *"A qualitatively new occurrence, 2026-09-06, changed the shape of what this finding
is"*, for the full derivation — this entry is the summary, not a replacement.

**The mechanism, measured with a standalone forced reproduction, not merely reasoned about.** Every
`aiosqlite.Connection` runs one dedicated OS worker thread that pulls `(future, function)` off a
queue forever and reports results back via `future.get_loop().call_soon_threadsafe(...)`
(`aiosqlite/core.py:_connection_worker_thread`, installed 0.22.1, current latest). If the coroutine
that queued the work has moved on and its event loop has already closed by the time the thread
finishes, that call raises `RuntimeError: Event loop is closed` — and the `except` branch's own
attempt to report *that* failure makes the identical call and raises again, uncaught. **The worker
thread's loop terminates and the thread is permanently dead**, with no SQLite `busy_timeout`
governing any of it. A forced standalone reproduction (fire-and-forget a 1s operation, close the
loop while it is still running) crashes byte-for-byte identically to the warning the real suite
produced, and reusing the same connection afterward hangs unboundedly — only an explicit
`asyncio.wait_for` kept the repro script itself from hanging forever.

**The real call site: `hub/hub/api/v1/agent_trigger.py:1190`.** `trigger_agent_directly` creates
`task = asyncio.create_task(_execute_run(...))` and deliberately does not await it, so the triggering
call can return while the run continues in the background. `hub/tests/conftest.py:317-367`'s teardown
safety net cancels every such task and `gather`s them before disposing the shared engine — but
`task.cancel()` + `gather` only waits for the **coroutine** to unwind, which can return as soon as
the `Future` it awaits inside aiosqlite is marked cancelled. It does not, and structurally cannot,
wait for the **worker thread** to finish whatever synchronous SQLite call is already in flight,
because that thread is not asyncio-aware and never observes the cancellation. If the fixture's loop
closes while that call is still running, the thread dies into the crash above, and the underlying
`sqlite3.Connection` is never reached by any `close()` — the crash happens inside `_execute_run`'s own
`try/except`, before control could reach anything that would close it.

**Why this is a production concern, not only a test-fixture one.** Nothing about the mechanism is
test-specific — it is `agent_trigger.py` and aiosqlite's own driver, both of which run in production.
Anything that cancels, times out, or otherwise moves on from a run while its background DB write is
still in flight (a superseded turn, an operator-cancelled run, a process shutdown) can leave the same
dead thread and the same permanently un-resolvable connection behind it. **Depending on whether
SQLAlchemy's pool still considers the connection checked-in and hands it back out**, the visible
symptom is either a quiet leak (bounded — something else eventually times out and reports a
downstream error) or an **unbounded hang** on whatever next tries to use that connection. Both shapes
are consistent with F292's own history: the CI occurrences that fail in 8-14.5 minutes, and the one
that sat for 3.5 hours before being cancelled by hand.

**Why F292's own instrumentation could never have named this.** `hub/tests/conftest.py`'s checkout
registry watches SQLAlchemy's engine-level `checkout`/`checkin`/`close` events — it is blind to
aiosqlite's internal worker-thread lifecycle by construction, which is exactly why it printed an
identical negative on all four instrumented F292 occurrences.

**Not fixed, and not attempted.** This is a design-level asyncio/threading correctness issue in how a
cancelled run's worker-thread-backed DB operations are waited for, not a one-line patch — it touches
core run-execution/cancellation semantics, which this repository's round discipline (explore/propose
→ review → review) should get three independent passes on before anything changes. The next step is
establishing whether `_execute_run`'s database work can be made to either (a) genuinely await the
underlying thread on cancellation rather than only the coroutine, or (b) run on a connection whose
worker-thread lifetime is decoupled from any single caller's event loop. Queued in
`spec-queue/DIRECTION.md` for the day window's spec loop rather than repaired ad hoc.


### The change that fixed it — what three rounds and the build corrected in the account above

**Appended 2026-09-09 (night, iteration 7) by
`openspec/changes/2026-09-07-a-dead-connection-is-never-handed-back-out`.** Everything above this
heading is the entry as it was written on 2026-09-06 and is left exactly as written, including the
parts the rounds went on to correct — a correction is only legible against what it corrected. Read
the change's `proposal.md` for the full derivation; this is the summary the next reader of *this
file* needs.

**R1 corrected the trigger, by measurement.** The entry above says a **cancelled** run's background
task leaves the dead thread. Cancellation on its own is benign, and the two shapes were run side by
side (`testbed/scratch/f295/probe_cancel.py`, `aiosqlite 0.22.1`): coroutine cancelled with the loop
**alive** → worker alive, connection reuse **succeeds**; coroutine cancelled with the loop
**closed** under the in-flight call → worker dead, reuse **hangs**. The reason is two lines up from
the crash the entry quotes: the worker reports through `set_result`, which is
`if not fut.done(): fut.set_result(...)` (`aiosqlite/core.py:32-34`), and a cancelled future is
already `done()`, so the report is a no-op and the thread returns to `tx.get()`. **Loop closure is
the precondition; cancellation is only how a run gets abandoned mid-write.** The accurate statement
of the defect is *a pooled connection can outlive the event loop that last queued work on it, and
nothing anywhere notices*.

**R2 and R3 both narrowed the severity, on facts R1 did not have. Neither overturned the severity
question itself** — R2 reproduced the mechanism independently rather than quoting R1's numbers, and
left whether `F295` stays an A to the review page. Taken in order:

- The Hub's only loop close is **process exit**, so what production gets today is an uncaught
  worker-thread traceback on a process that is leaving anyway. R2 attacked "leaving anyway" — an
  `aiosqlite` worker is non-daemon (`core.py:90`) and should block `threading._shutdown` — and it
  held: SQLAlchemy's dialect sets `connection._thread.daemon = True` at connect
  (`sqlalchemy/dialects/sqlite/aiosqlite.py:412`, 2.0.50), measured through an engine of
  `hub/hub/db/engine.py`'s shape which exited in 0.35s with the engine never disposed.
- The entry's larger blast radius — the **test suite**, which closes a loop per test — is **one
  path, not two**. `conftest.py` disposes the engine after every test, so the pooled-reuse
  precondition is not routinely reachable; the single way past it is the settle's own pass cap,
  whose `for…else: raise` (`:364-368`) fires *before* `await _REAL_ENGINE.dispose()` (`:369`). The
  other candidate path was measured away by R3: a checked-out connection is detached rather than
  closed, but `dispose()` ends with `self.pool = self.pool.recreate()`, so it belongs to a pool the
  engine no longer references and can never be handed out again (`probe_r3_dispose_pool.py`).
- R3 sharpened *what the hazard is*, which changes how the entry above should be read: it is **the
  dead worker thread**, not the outlived loop. A connection left **idle** in the pool while its
  creating loop closes, then used from a second loop, **completes normally** — the guard fired zero
  times (`probe_r3_idle_carryover.py`). `aiosqlite` builds each call's future on the *calling* loop
  and its work queue is a thread-safe `SimpleQueue`, so nothing in a connection is bound to its
  creating loop except a call **in flight**. The guard's condition is therefore necessary *and*
  sufficient — and `conftest.py:293`'s stated mechanism ("bound to a loop that no longer exists") is
  not by itself enough to fail.
- R3 narrowed the production consequence once more, from a direction nobody had looked: **the
  product's own stop command never reaches this shutdown at all.** `agentweave stop` on Windows runs
  `taskkill /PID <pid> /F` with no signal first (`src/agentweave/cli.py:534-535`, despite a docstring
  promising "graceful SIGTERM, then forced"), and measured, that runs no lifespan teardown. Filed
  separately as **`F297`**.

**R3 also moved the fix, and this is the correction that mattered most.** A checkout-only guard —
the obvious repair, and what R1 proposed — would have made things **strictly worse**:
`engine.dispose()` never dispatches `checkout`, so the guard cannot see the connection it is
closing, and dispose on a dead-worker connection idle in the pool hangs forever (measured to a
40-second kill, `probe_r3_dispose_hang.py`). The neutralisation therefore lives on the **`close`**
pool event, which SQLAlchemy dispatches before every close — checkout invalidation, `dispose()`,
checkin close and retry-exhausted abandon alike — and the checkout listener only detects. That is
what shipped.

### Two things measured while building it, both of which cost time and neither of which is in the proposal

**1. `asyncio.wait_for` does not bound `engine.dispose()`.** The proposal establishes that a timeout
does not rescue a hung *statement*; the same is true of dispose, and it is worth stating separately
because a test author reaches for `wait_for` as a safety net and it silently is not one. Measured
(`testbed/scratch/f295/probe_310_wait_for_bound.py`, uncommitted): with the `close` listener
reverted, a 5-second bound around `await engine.dispose()` **had not fired 60 seconds later**. The
dispose reaches aiosqlite through SQLAlchemy's greenlet bridge, and the cancellation `wait_for`
issues has to unwind through it. The *same* `wait_for` **does** bound the checkout/execute path.
The practical consequence is written into `hub/tests/test_dead_worker_connection.py`'s module
docstring: a regression in the `close` listener costs one named test failure **and then a stuck CI
job**, because `conftest.py`'s per-test dispose hangs and no assertion in that file can bound it.
Confirmed as mutation 4 of 14 — one named failure, then a hang killed at 180s, exit 124.

**2. `caplog` does not survive a lifespan startup.** A test that asserts on a teardown warning
cannot use `caplog` if it drove the real `lifespan()`: startup runs `init_db`, which runs Alembic,
whose `fileConfig` **replaces the root logger's handlers** with a single `StreamHandler`, so
pytest's capture handler is gone by the time the teardown logs. The warning is emitted and the
assertion fails with an empty record list, which reads exactly like the product not logging.
Attaching a recorder to the `hub.main` logger itself survives, which is what that file's
`_warnings_from()` does.

### The gap this change ships with, stated rather than left to be discovered

Fourteen mutations were run against the nine tests (11 named a victim; every shipped test is named
by at least one). Three named nobody, and two of those are not gaps — the non-aiosqlite `getattr`
guard covers a state that cannot occur here, and the `close_detached` listener is unreachable, as
its own docstring says. **The third is a real gap: moving `_settle_background_runs()` to *before*
`terminate_all_active_runs()` and `shutdown_scheduler()` fails nothing.** That ordering is argued at
length in the change's task 2.4 and is held by a comment in `hub/hub/main.py`, not by a test. The
tests pin that the settle happens before `engine.dispose()` — a `_DisposeProbe` samples `task.done()`
at the instant dispose is entered — and they do not pin its position relative to the two teardown
steps above it. A future edit that reorders those is free to do so silently.

### The drive — 2026-09-09, a real Hub process, a real turn, and the stop that actually reaches the teardown

Three rounds and fourteen mutations checked the *argument*. This checks the *product*, and it is the
half this entry was missing. `scripts/drive/f295_shutdown_drive.py` starts the Hub **from source**
(`cd hub`, `py -3.11 -m uvicorn hub.main:app --port 8011`) against a throwaway database under the
temp tree, on a fresh project, with a Haiku runner — then stops it while a turn is genuinely still
running. Never 8000, never 8010's database, and the script refuses to start if 8011 is already
listening. It confirms **0 `.py` under `hub/hub` or `src/` is newer than the process start** before
measuring anything, so the drive is not of stale code.

**The stop under test is `CTRL_BREAK_EVENT`, not `agentweave stop`.** The product's own stop is
`taskkill /F` and runs no teardown at all (`F297`), so driving it would have measured nothing about
this change. uvicorn installs `handle_exit` for `SIGBREAK` on Windows (`uvicorn/server.py`,
0.41.0), so a Ctrl-Break to a child started in its own process group is the Ctrl-C path.

| | run in flight | shutdown | teardown completed | settle-bound WARNING | dead-worker WARNING | `Event loop is closed` |
|---|---|---|---|---|---|---|
| measurement | **yes** (run row `ended_at IS NULL` at the instant of the break) | **0.42 s** | yes | absent | absent | absent |
| control (`--no-run`) | no | **0.22 s** | yes | absent | absent | absent |

**The hang this finding is about does not happen.** The process exits in under half a second with
`Application shutdown complete`, which is the line printed *after* `_settle_background_runs()` and
`await engine.dispose()` have both returned — so the settle reached its fixed point and the pool
was released, with a run cancelled mid-`pty.read` and its connection in the pool. Reproduced three
times; the control says the in-flight case costs about 0.2 s more than an idle one, not that it
costs a timeout.

**"In flight" is read from the run row, not from the roster, and that correction cost a run.** The
first attempt used *"count slowly from 1 to 40"* and asserted in-flight from output lines having
arrived. Haiku finished it in 10 s, the break landed on an idle Hub, and the drive reported a clean
6/6 for a shutdown that had nothing to settle. Output lines prove a run **started**; only
`runs.ended_at IS NULL`, sampled in the same breath as the break, proves it is still going. The
script now blocks the turn on a real `time.sleep(120)` child and re-checks the row immediately
before signalling. This is the same class of error as `F296` — an assertion that could not fail
reported as evidence — caught this time by the numbers being suspiciously identical to the control.

### Two things the drive found that no test and no round had looked at

**1. A deliberate stop logs `ERROR ... Unhandled error in run` with a traceback.** Every in-flight
stop prints, at ERROR level:

```
ERROR [hub.api.v1.agent_trigger] Unhandled error in run run-05b2b6fe5ef5 for 'f295020814'
Traceback (most recent call last):
  File "...\hub\hubpi
1gent_trigger.py", line 2132, in _execute_run
    chunk = await loop.run_in_executor(None, pty.read)
asyncio.exceptions.CancelledError
```

This is the handler at `agent_trigger.py:2372-2394` doing exactly what its own comment says it was
written for — catching a teardown cancellation so the `Run` row cannot be stranded at `running`
forever — so the *behaviour* is correct and this is **not** a regression from this change. What is
wrong is the *report*: an operator who presses Ctrl-C on a healthy Hub is shown an ERROR and a
traceback describing their own intended stop as an unhandled error. Filed as **`F298`**.

**2. The stop leaves one `Run` row at `running`, and the next start repairs it.** Measured on all
three in-flight runs, identically: cancelling the in-flight run makes its failure tail hand the
input back, that release schedules a **successor** turn, and the settle's second pass cancels the
successor before it has run a single step — so the successor never enters its own `try`, nothing
marks its row, and it is left `('run-29411934268e', 'running', None)`. This is precisely the
"cancelled before its first await" behaviour the change's own task 3.6 had already found in a test.

It is **not** a wedge, and that was measured rather than assumed
(`scripts/drive/f295_restart_reconciles.py`): restarting against the same database logs
`WARNI [hub.run_reconciliation] Reconciled 1 orphaned run(s) to status=interrupted on Hub start`,
the row moves to `interrupted` with an `ended_at`, **zero rows remain `running`**, the agent reports
`idle`, and a fresh trigger runs to `completed`. The row only ever matters to a running Hub, and a
running Hub has reconciled it before it can read it. Recorded because "the stop leaves a `running`
row behind" is alarming on its own and would otherwise be re-discovered as a defect.

**No orphan processes.** `terminate_all_active_runs()` takes the PTY tree with it — after each stop,
nothing matching the drive's temp path or its `time.sleep(120)` child survives.

**Not claimed by this drive.** The `4 → 10` `PytestUnhandledThreadExceptionWarning` count from the
full suite is untouched by it; that is `F292`'s traceback-at-loop-close, which this change explicitly
does not fix, and it still wants a third sample.


## F296 (C, harness) - a drive assertion that can never be non-zero was reported as evidence about the product

**Status:** fixed 40e9efa (2026-09-22; see the foot). Was: open

`t_d4_instructions_failed_load.py:316` counts F271's cross-project switcher with

```python
switch = page.get_by_role("button", name="Switch project")
```

`ProjectHeader.tsx:48` renders it as `<select aria-label="Switch project">`, whose implicit ARIA
role is **`combobox`**. The locator therefore returns 0 whatever the page renders. The repo already
knew the right role: `App-mount.test.tsx:214` reaches the same control with
`getByRole('combobox', { name: 'Switch project' })`.

That 0 was not treated as an instrument reading. It was carried into `FINDINGS.md` twice as a
statement about the product - *"this page offers no in-page project switcher (`'Switch project'
controls on screen: 0`, unchanged since 2026-09-02)"* - and used as the ground for closing F271's
column C **by construction** rather than driving it. Two windows (2026-09-02 day, 2026-09-06 night)
repeated the number without ever asking whether the locator could return anything else.

**Measured 2026-09-07 (day, D-1)** by `scripts/drive/t_d1_0907_cross_project_switch.py`, on a fresh
Hub on `:8011` from this branch's code, fresh database, two fixture projects, both deleted:

```
role=button:'Switch project'   -> 0     <- the night's locator, reproduced
role=combobox:'Switch project' -> 1     <- the same control, its real role
[data-testid=project-switcher-select] -> 1
options: ['d1-0907-bravo', 'd1-0907-alpha']
```

The switcher **is on screen on the Instructions page**, offering both projects. F190's lesson in a
drive harness rather than a unit test: an assertion that cannot fail is not evidence.

**Not a product defect.** The severity is C because nothing a user does is broken by it; what was
damaged is the record. It is filed so the next window does not inherit "0 controls on screen" as a
fact about the page.

**Reproduce:**

```
AW_HUB=http://127.0.0.1:8011 AW_KEY=<operator key> \
  py -3.11 scripts/drive/t_d1_0907_cross_project_switch.py
```

**The fix is one word** in `t_d4_instructions_failed_load.py:316` (`"button"` -> `"combobox"`), and
it is deliberately **not applied here** - the day window does not implement, and column C's own
conclusion now rests on a measurement rather than on that line, so changing it repairs the record's
future rather than its past. Whoever next touches that harness should also delete the surrounding
`NOT DRIVEN` print, which is now false.

### What the corrected drive found - F271's column C, closed by measurement

The conclusion the wrong locator was propping up **survives**, for a different reason, and the
difference matters because it is the reason a future change could break it:

| | the night's ground | what is measured |
|---|---|---|
| why column C is unreachable | "no in-page project switcher exists" | **false** - one exists, role `combobox` |
| what actually closes it | - | `App.tsx:602` wires `onSelectProject` to `navigateTo(projectDestination(id))`, and `projectDestination`'s default tab is `'overview'` (`lib/navigation.ts:55`), so **the switch navigates away from `tab=environment` and InstructionsPage unmounts** |

Driven, not argued (`?project=A&tab=environment&section=instructions` -> select B in the switcher):

```
after the switch: ?project=proj-2865656a8676&tab=overview   textarea on screen: false
```

So a change that made the project switcher preserve the current tab - a perfectly reasonable UX
improvement - would put column C back in play. That is a fact worth having written down, and the
"no switcher exists" version of the record would have hidden it completely.

The hazard itself was then driven as far as it is reachable: A loaded with its own text, switch to
B, navigate back to B's Instructions with B's GET aborted on the wire. **20 passed / 0 failed.** No
editor is offered under B's failed load, the failure is stated in a `role="alert"`, interacting with
everything on screen issues **0 PUTs**, and both projects' stored rows are byte-identical afterwards.

**Mutation-checked**, which is what makes those numbers mean anything - the same harness re-run with
the served bundle reverted to pre-fix (`git checkout 676eba4^ -- hub/hub/static/ui`, served JS
confirmed back to `index-BXA4wQsi.js` on the wire) gives **17 passed / 3 failed**, and the three
name themselves:

```
FAILED: in fact no editor is offered at all under B's failed load
FAILED: the failure is stated instead (0 alert(s))
FAILED: no PUT was issued by any interaction (1)
```

Pre-fix the drive's own typing reached the wire as a real PUT, so the instrument can see a write
when there is one. **One honest caveat on that run:** the two "stored content is byte-identical"
assertions passed in *both* runs, because this harness aborts PUTs at the route rather than letting
them land - so those two rows are not evidence of the fix. The **PUT counter** is.

**A correction to column C's own claim, incidentally.** F271 stated the cross-project hazard as
*"Save writes A's instructions into B"*. Pre-fix, on the reachable path, it does not: the editor
under B holds `''`, not A's text, because reaching B's Instructions page remounts the component and
`content` returns to its `useState('')` initial. The pre-fix hazard under B is the **blanking** one
that column B already covers, arriving by a second route. The text-carry variant needs the component
to stay mounted across the project change, and nothing in the current app does that.

### F271's unit tests - the night's "6 of 8 mutation-checked", closed

Re-measured 2026-09-07. Against the pre-fix component (`git show c7e615c^`), the eight tests in
`instructionsUnreadEditor.test.tsx` give **6 failed / 2 passed** - the night's figure, reproduced
exactly. The two that pass were left unexplained, and they are not the same kind of thing:

| test | passes pre-fix because |
|---|---|
| `still loads, edits, saves and confirms on the success path` | it is the **baseline**. It must pass in both, by design; a baseline that flipped would mean something other than this fix moved. |
| `keeps a loaded editor and its edits when a background refetch fails` | it guards the **branch order**, not the branch. The old page always rendered an editor, so the pre-fix component satisfies it accidentally. |

The second was checked against the mutation it actually guards - `data`-first swapped to
`isError`-first in the `{children}` chain, the exact inversion the component's doc comment warns
about - and it **fails**: 4 passed / 4 failed. So the honest statement is **7 of 8 are
mutation-checked** (six against the pre-fix component, one against the branch-order inversion) and
the eighth is a baseline that must pass in both. Restored, the file is 8/8 green.

**Fixed 2026-09-22, `40e9efa`, and the column it gated has now been driven.** The locator is `get_by_role("combobox", name="Switch project")`. The branch it unlocked had never run: it clicked the `<select>` and then an `<option>`, which Playwright cannot do, so it now reads the options and calls `select_option`. Its fixture directories also no longer existed, and opening a project now refuses a missing directory (409 `project_workspace_missing`), so they are temp dirs. **Driven on a throwaway `:8031` Hub with a fresh database: 31 passed, 0 failed.** For column C the switcher lists `['d4-bravo', 'd4-alpha']`. Selecting bravo leaves the instructions page for bravo's Overview (screenshot `d4-07-c-on-b.png`), which unmounts the editor. F271 column C's cross-project leak therefore cannot be reached through the switcher. That is now measured, where before it was inferred from a locator that could only return 0.

**Follow-up 2026-09-22.** Column C now reads navigation from the URL (`section=instructions`) instead of from whether an editor exists. B's load is made to fail, and a correct page for a failed load has no editor either. Re-driven on `:8031`: after the switch the URL is `/?project=<bravo>&tab=overview`, and 31 passed. The fixture directories are now removed at the end, and the script refuses `:8010` as well as `:8000`. Still true, and pre-existing: its two not-driven branches record `check(True, ...)`, so a pass count includes those no-op passes.

---

## F297 (B) — `agentweave stop` on Windows force-kills the Hub, so nothing the shutdown sequence does ever runs

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- Windows stop sends CTRL_BREAK into the Hub's console and waits 10 s before forcing; see FIXED at the end of this entry. Was: open

`src/agentweave/cli.py:528-545`, `_hub_kill_pid`, the one thing `cmd_stop` calls once it has
confirmed a native Hub is serving the recorded port:

```python
def _hub_kill_pid(pid: int) -> None:
    """Terminate a native Hub process by PID (graceful SIGTERM, then forced)."""
    ...
    if sys.platform == "win32":
        _sp.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=15)
    else:
        os.kill(pid, 15)  # SIGTERM
        ... wait up to 10s ...
        os.kill(pid, 9)   # SIGKILL fallback
```

The POSIX branch does what the docstring says. **The win32 branch goes straight to `/F`** —
`TerminateProcess`, which no process can intercept. There is no `taskkill` without `/F` first, no
`CTRL_BREAK_EVENT`, and no wait.

**Measured 2026-09-07 (day, D-4)**, on this machine, with a uvicorn app whose lifespan writes a
marker file on teardown (`testbed/scratch/f295/probe_r3_taskkill_app.py`):

```
uvicorn pid from lifespan: 3028
{"ok":true}                                     <- served a request, so the app was fully up
SUCCESS: The process with PID 3028 has been terminated.
marker exists after taskkill /F: NO
---log tail---
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
INFO:     127.0.0.1:55203 - "GET /health HTTP/1.1" 200 OK
```

No marker, and no `Shutting down` line in uvicorn's own log. **The ASGI lifespan shutdown does not
run.**

### Why this is a B rather than a nit

`hub/hub/main.py`'s `lifespan` teardown is `await terminate_all_active_runs()` then
`await shutdown_scheduler()`. Neither executes on this path. The shipped `app-lifecycle`
requirement *Status, stop, and reset act on the local instance* says, in its own scenario:

> **WHEN** the user runs `agentweave stop`
> **THEN** active runs across projects are terminated through normal shutdown
> **AND** the one runtime process stops

The second clause holds. **The first cannot**, on Windows, because the function that terminates
active runs is never called. What happens to the run processes themselves after their parent is
terminated is **not measured here** — Windows does not kill a process tree with the parent, and
whether the Hub's spawns are in a job object was not checked. That is the open question this
finding leaves for whoever fixes it; the measured part is that the Hub's own termination path is
skipped.

### Where it was found

Not by a drive. By `D-4`, the third spec-loop round on
`openspec/changes/2026-09-07-a-dead-connection-is-never-handed-back-out`, asking the round's
assigned question — *what does the surface actually do?* — of a change whose first requirement is
about what an instance does **while shutting down**. The answer on the operator's own platform is
that the product's own stop command gives it no shutting-down to do.

That change now scopes its requirement to a shutdown that runs at all, and explicitly does **not**
take this on: making `agentweave stop` graceful is CLI work against a different, already-shipped
requirement, and folding it in would have made a self-contained change into two.

### Reproduce

```
cd testbed/scratch/f295
PROBE_MARK=tk.marker py -3.11 -m uvicorn probe_r3_taskkill_app:app --port 8099 --host 127.0.0.1 &
# wait for tk.marker.started, then
taskkill /PID <pid from tk.marker.started> /F
# tk.marker is absent
```

### What a fix has to be careful about

- Windows has no SIGTERM. The graceful equivalent for a *detached* uvicorn is
  `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)`, which requires the child to have been created
  with `CREATE_NEW_PROCESS_GROUP` — so the fix touches `_hub_native_start` as well as
  `_hub_kill_pid`, and a Hub already running was not started that way.
  **That mechanism is now measured, not just proposed** (2026-09-09,
  `scripts/drive/f295_shutdown_drive.py`): a uvicorn started with `CREATE_NEW_PROCESS_GROUP` and
  sent `CTRL_BREAK_EVENT` runs the full lifespan teardown and exits in **0.22 s** idle / **0.42 s**
  with a turn in flight. So the graceful path a fix would take works on this machine, and the 10-second
  backstop below is a backstop rather than the expected case.
- A graceful stop has to stay bounded. The POSIX branch waits 10 seconds and then `SIGKILL`s; the
  Windows one needs the same backstop, and — see the change above — the shutdown sequence it would
  now be running contains a dispose that can itself block if `F295`'s guard is not in place. The
  two are worth landing in that order.
- The docstring is currently false on Windows and should stop claiming a SIGTERM that is not sent,
  whatever else is done.

**FIXED 2026-09-23 (interactive session, Round 3, group 3d).** `_hub_native_start` needed no change:
it already spawns the detached Hub with `CREATE_NEW_PROCESS_GROUP` (added with F341's
`CREATE_NO_WINDOW`), so every Hub `cmd_hub_start` launches today can take the graceful path. The one
obstacle left was that `GenerateConsoleCtrlEvent` only reaches processes sharing the caller's
console, and the Hub has its own hidden one. New `_hub_break_windows(pid)` runs a stdlib-only helper
process (`_CTRL_BREAK_HELPER`: `FreeConsole`, `AttachConsole(pid)`, ignore the event itself,
`GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)`) and then waits up to
`_HUB_GRACEFUL_STOP_SECONDS` (10, the POSIX branch's figure) on a `SYNCHRONIZE` handle.
`_hub_kill_pid` falls back to `taskkill /F` only when that fails -- a Hub started some other way, or
one whose shutdown hangs -- so the bound holds. Docstring corrected. Measured first with a probe
launched with `cmd_hub_start`'s exact flags: the helper exits 0, uvicorn runs the lifespan teardown
and exits. What happens to run processes on the old forced path stays unmeasured, and no longer
matters for a graceful stop: `terminate_all_active_runs` now runs. Tests
(`tests/test_hub_graceful_stop.py`): two platform-independent tests of the fallback, and
`test_a_hub_detached_as_cmd_start_does_it_runs_its_shutdown_when_stopped` (Windows only, real
processes, through `_hub_kill_pid`) -- on the old code it fails with "stopped without running its
lifespan shutdown". Not driven against a real Hub with a turn in flight; 2026-09-09's
`f295_shutdown_drive.py` measured that case at 0.42 s with the same signal.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** `OpenProcess` failing was read as "already gone"; only
`ERROR_INVALID_PARAMETER` means that now -- access denied falls through to the forced kill instead of
printing "stopped" over a live Hub. The helper's comment was corrected (`SetConsoleCtrlHandler(None,
True)` ignores Ctrl+C only; the helper is outside the target group anyway). **Open, not measured:**
uvicorn runs lifespan teardown only after in-flight requests finish, so a request held longer than
`_HUB_GRACEFUL_STOP_SECONDS` (10 s) still ends in `taskkill /F` -- the probe had no client connected.
The review also could not confirm `uvicorn>=0.27` (the declared floor) handles SIGBREAK; 0.41 does, and
without it CTRL_BREAK is no worse than the old hard kill.

---

## F298 (C) — stopping the Hub normally reports the operator's own stop as an `ERROR ... Unhandled error in run`, with a traceback

**Status:** **fixed** `0a0aec3`, driven 2026-09-09 (day window, D-6) — see *The fix* at the
end of this entry. Filed 2026-09-09 by the `F295` drive
(`scripts/drive/f295_shutdown_drive.py`), reproduced on all three in-flight stops. **Cosmetic** —
nothing behaves wrongly, and the code doing it is deliberate — but it is cosmetic in the one place
an operator looks when deciding whether a stop went cleanly.

**What happens.** Stop a Hub that has a turn in flight, by the path that actually reaches the
lifespan teardown (Ctrl-C / `CTRL_BREAK_EVENT`; **not** `agentweave stop`, which reaches nothing —
`F297`). Between `Waiting for application shutdown.` and `Application shutdown complete.`, the log
gets one of these per in-flight run:

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
ERROR [hub.api.v1.agent_trigger] Unhandled error in run run-05b2b6fe5ef5 for 'f295020814'
Traceback (most recent call last):
  File "...\hub\hubpi
1gent_trigger.py", line 2132, in _execute_run
    chunk = await loop.run_in_executor(None, pty.read)
asyncio.exceptions.CancelledError
INFO:     Application shutdown complete.
```

**Why the code is right and the message is wrong.** `_execute_run`'s
`except (Exception, asyncio.CancelledError)` at `agent_trigger.py:2372` exists *for exactly this
cancellation*: its comment (`:2385-2393`) names "event-loop teardown cancelling an orphaned
background task" as the case it was added to catch, and without it the `Run` row would stay
`running` forever and `turn_scheduler.schedule_agent` would refuse the agent every future turn. The
handler must stay, the row must be marked, and the `CancelledError` must be re-raised. The defect is
that the one path it was *written* for is reported in the vocabulary of the paths it was not:
`logger.exception("Unhandled error in run %s for %r")` at ERROR, with a stack trace, for an event
the operator caused on purpose and the Hub handled correctly.

**The consequence is real even though the behaviour is not.** An operator stopping a Hub sees red
ERROR text and a traceback and has no way to tell it apart from a genuine crash; and a log scraper
or a CI job that greps for `ERROR` on a clean shutdown gets a false positive on every stop with a
turn open. It also inverts the signal for the next person driving `F295`: the drive script's
`no traceback after the break` check FAILs on a shutdown that is, in every other respect, perfect
(0.42 s, teardown complete, no hang, no dead-worker warning, no `Event loop is closed`).

**Shape of a fix, not decided.** The cancellation is distinguishable from a real failure at the
point it is caught — `isinstance(exc, asyncio.CancelledError)` is already tested six lines below, to
decide whether to re-raise. Logging that branch at INFO or WARNING with wording that says what it is
("run cancelled by shutdown"), and keeping `logger.exception` for `Exception`, would leave the row
marking and the re-raise untouched. Whether a cancellation that is *not* from shutdown deserves the
louder message is the open question — nothing distinguishes the two at that point today, and
inventing a flag to do so may be more machinery than a log line is worth.

**Reproduce**

```
py -3.11 scripts/drive/f295_shutdown_drive.py
# the run must still be in flight at the break: the script prints
#   "run row unfinished immediately before the break: True"
# and the ERROR appears between "Waiting for application shutdown." and "Application shutdown complete."
```

**The fix, 2026-09-09.** `_log_abnormal_run_end` (`agent_trigger.py:1805`) — the report split off
the two handlers, since one of the things they catch is not an error. A `CancelledError` is logged
at WARNING with no stack trace and wording that says what happened; everything else keeps
`logger.exception` and the exact message it always had. The wording deliberately does **not** say
*shutdown*, which is how the open question above is answered rather than decided: nothing at that
point distinguishes a teardown cancellation from any other, and a cancellation is a deliberate act
either way, so no flag was invented. Row marking, the failure tail and the re-raise are untouched.
Applied to `_execute_codex_appserver_run` (`:2986`) as well — the same two lines, the same falsehood
— though only the Claude path was driven, Codex being undrivable on this machine.

**Driven, which is the half that matters here.** `py -3.11 scripts/drive/f295_shutdown_drive.py`
with a real Haiku turn in flight (`run row unfinished immediately before the break: True`):
**all six checks PASS**, where *"no traceback after the break"* was the one FAIL this morning on the
same script. The log between the two shutdown lines now reads, in full:

```
INFO:     Waiting for application shutdown.
WARNI [hub.api.v1.agent_trigger] The run run-8f02111bdb43 for 'f295110952' was cancelled before
      it finished; marking it failed and re-raising the cancellation
INFO:     Application shutdown complete.
```

and the run row is still `failed` with an `ended_at` — the report changed, the behaviour did not.
Shutdown took 0.38 s. Covered by `hub/tests/test_a_cancelled_run_is_not_reported_as_a_crash.py`
(3 tests), mutation-checked three ways: dropping the branch, logging the cancellation with
`logger.exception`, and demoting the real failure to `warning` each fail a named test.


---

## F300 (A) — the Hub's own workspace approver denies every shell command containing a URL, including the one its own notice instructs

**Status:** fixed `612b9c9` by `a-url-is-not-a-path` (tasks §2: the reader, and D4's run's-own-Hub
test), driven `f492261` (tasks §6.2, ask 1; night 2026-09-12, Windows, Haiku, default posture, Hub
from source at `39b6be3`). The instructed request now goes through: *"Ask 1 (`run-cb819f7613b4`)
created `task-03dd81bf6fec` with `created_by_run_id` = `run-cb819f7613b4`, and no
`permission_denied` for that run."* Its tool input was
`curl -s -X POST "$HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer $AW_RUN_TOKEN" …`.
The pre-fix tree, driven the same night (§6.1, `run-826a458f6bc6`), still answered
`Denied: '/api/v1/agent-actions/tasks' is outside your workspace.` Only the run's own Hub is
recognised. Any other address is refused as a network address, as the verdict required (F312).

Filed: driven 2026-09-09 by the night window, tasks §6.3/§6.4 of
`openspec/changes/2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`, against the trial Hub
on `127.0.0.1:8010` running from this checkout. Fixture `proj-08e61dec0192` at
`C:\Users\huida\aw-c2verify`, agent `mcpagent`, runner `claude` / `claude-haiku-4-5-20251001`.
Raw run in `testbed/scratch/c2verify/driveC.json` (uncommitted).

**What was asked.** A run under the default `workspace` posture, told to POST to
`$HUB_URL/api/v1/agent-actions/tasks` with `Authorization: Bearer $AW_RUN_TOKEN` using a shell
command — the exact request `access_path_notice`'s non-MCP branch instructs.

**What happened.** Both shell tools, one denial:

```
Denied: '/api/v1/agent-actions/tasks' is outside your workspace.
```

**The mechanism is ours, and it is one regex.** `hub/hub/mcp_server.py:936`:

```python
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'|;&><)]*")
```

`_decide` extracts every absolute-looking path out of a shell command's text and refuses any that
does not resolve inside `AW_WORKSPACE_DIR`. A URL's path component is absolute-looking: in
`curl "$HUB_URL/api/v1/agent-actions/tasks"` the regex matches from the `/` after `$HUB_URL` and
hands `/api/v1/agent-actions/tasks` to `os.path.realpath`, which resolves it against the drive root.
That is outside the workspace, so the command is denied.

**This is not specific to the capability plane.** Any URL in any shell command is denied the same
way under `workspace`: `https://example.com/x` yields the candidate `//example.com/x`. An agent on
the posture this repository chose as its default (`DEFAULT_CLAUDE_PERMISSION_MODE`,
`runner_commands.py:63`) cannot `curl` anything at all, and is told the reason in the vocabulary of
the filesystem — which is why the model in the drive concluded *"the endpoint path is being blocked
as outside the workspace security boundary"* and stopped.

> **Corrected 2026-09-13** (night window, `a-url-is-not-a-path` §9.1). *"Any URL in any shell
> command is denied"* was too wide in three ways, and the candidate was misread.
> - A URL with no `/` in it was always allowed: `curl -s example.com` gives the regex nothing to
>   match (`design.md` D2, row N4).
> - On POSIX, a scheme URL was **allowed**, not denied. The regex's drive-letter arm matches
>   `s://example.com/x`, which is relative there, so it resolved inside the workspace (**F331**,
>   measured under WSL). The sentence held on Windows only.
> - The candidate for `https://example.com/x` is `s://example.com/x`, not `//example.com/x`: the
>   drive-letter arm matches first (F312's table, first row).
>
> The instructed request, `$HUB_URL/…`, was refused on both platforms, because its `/api/…` is
> absolute everywhere. So this finding's own claim stands as measured.

**Why the change did not find this and the tests could not.** `_decide` is tested with filesystem
paths, which is what its docstring says it is for. Nothing tested it with a URL, because until §1 of
this change the notice never told an agent to make a request. The change made the instruction true;
the approver has refused it since long before.

**What it costs.** §1's notice is honest about the contract and unusable by the agent that reads it
*on this posture*. The plane really is reachable from inside the run — the same environment, on the
same socket, is what `mcp_server.py` itself uses (see below) — but the run's own tools cannot get
there.

**Not fixed here.** The fix is a real decision: whether `_decide` should recognise a URL and let it
through (widening the shell boundary to network egress, which the workspace posture deliberately
does not permit today), or whether the plane alone should be exempted by address. Both move
containment, which `agent-capability-plane` reserves for the operator. See F301, which is the same
wall from the other side.

### Confirmed by the same session — the grounds mechanism works end to end

The positive half, and the first time §4's mechanism has run outside an in-process test.
`testbed/scratch/c2verify/driveB1.json`, `driveB2.json`.

- **Run 1 of a fresh agent** (`run-7f94b90838b5`): the Hub injected `--mcp-config`, the harness
  honoured it, the spawned `hub/hub/mcp_server.py` posted
  `POST /api/v1/agent-actions/mcp-adapter-online` **before serving** — `204 No Content` in the Hub's
  access log — and `runs.mcp_adapter_online_at` was stamped `2026-09-09 03:37:54`. The run was
  *told* the HTTP form (no grounds yet) while its MCP tools were in fact present; it found
  `mcp__agentweave__create_task` anyway and used it, `201`. The one-turn bootstrap cost the design
  predicted, observed and survived.
- **Run 2 of the same agent** (`run-14ba2fb78e0e`), asked to quote its own notice verbatim, replied:
  *"[AgentWeave] Tool access: the `agentweave` MCP tools are available — call send_message /
  create_task / update_task / ask_user directly."* The grounds earned on run 1 moved the description
  on run 2, live.

This also settles §6.3's two source-only claims, by the strongest witness available: the adapter is a
child process of the run, it read `HUB_URL` and `AW_RUN_TOKEN` out of that process environment, and
the Hub resolved the request to *that run's* row and stamped it. So `HUB_URL` names an address the
child can reach, and the token in the child's environment is the one whose digest the run row holds.
What is **not** established is that the model's own tools can do the same — F300 and F301 are exactly
that gap.

---

## F302 (B) — an agent's *first* turn is told "no MCP tools this turn" while it is holding them, and one measured turn believed it

**Status:** fixed `802a8c7`. Found 2026-09-09 by the day window's D-1 drive, on a Hub carrying all
three of the night's changes at once. This is **not** the F299/F300/F301 deployment: the harness
here honours MCP perfectly. It is the ordinary local one, and the misdescription lands on the first
turn of every agent created in it.

> **2026-09-20, implemented: both false sentences are gone, and that is all that is claimed.**
> `802a8c7`, under change `a-first-turn-is-not-told-it-has-nothing` (R1+R2+R3). The defect lived at
> **two** sites fed by the same `described_path`, not one — R1's proposal named only the first:
>
> | where | was | is |
> |---|---|---|
> | `access_path_notice` (`hub/hub/launchability.py`) | `Tool access: no MCP tools this turn — but the AgentWeave capability plane is reachable over HTTP…` | `Tool access: the AgentWeave capability plane is reachable over HTTP…` |
> | `_tool_surface_lines` (`hub/hub/api/v1/agents.py`) | `No AgentWeave tools are injected this turn, so each capability below is one HTTP request instead. Send it…` | `Each capability below is one HTTP request. Send it…` |
>
> Both reach a brand-new agent's first turn, the second by `--append-system-prompt-file`. Each half
> is pinned by a test that fails when only that half regresses (mutation-checked: restoring the
> denial in `launchability.py` → 4 failed / 92 passed; in `agents.py` only → 1 failed / 53 passed).
>
> **What is NOT claimed.** The *measured behaviour* is not closed. Removing the falsehood is
> necessary; it is not shown to be sufficient. The Architect kept to `curl` and payload files for
> ten runs **after** the notice healed
> (`openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`), and the honest baseline
> there is **n=1**, not the "4 of 4" an earlier draft of this ledger implied — four agents were
> *told* the sentence; only the Architect's behaviour was read. Design **D2** of the change records
> R2's dissent (that the declined one-text alternative is the better change) and the operator's
> answer — *"ship this shape, then measure"*. **Group 7 of that change is the measurement, and the
> change is barred from archive until task 7.4 carries counts.** Whatever it finds is appended here.
>
> **`harness_has_honoured_mcp`'s permanent-positive latch (F340) is untouched.** This change removes
> two assertions; it grants nothing on trust, and `described_access_path`, `resolve_access_path` and
> the MCP branch of the notice are all byte-identical.
>
> **`DECISIONS.md` 1d's second verdict — *"change the notice to instruct the `python -c` shape
> now"* — is superseded, not skipped.** 1d chose `python -c` because it was then the only shape
> `_decide` allowed: a `$HUB_URL` word was refused because `_judge_word`'s rule 2 trusts it only
> when the approver's own process carries `HUB_URL`, and `python -c` names no such word. The durable
> half of the F299/F300 verdict has since shipped, and the `curl` shape the notice already instructs
> is now **allowed in both the Bash and PowerShell renderings** — re-measured by R2 at `d7f2694`
> with `HUB_URL` and `AW_WORKSPACE_DIR` set as the Hub sets them, while a foreign address is still
> refused `_NETWORK` and `../outside.txt` still `_OUTSIDE`. So 1d's remedy addressed a constraint
> that no longer exists; the notice needs no rewrite to the `python -c` shape.

> **2026-09-21, group 7 measured: 3 of 3 fresh first turns reached for MCP, none shelled out.**
> Throwaway Hub on `:8091` (never `:8000`/`:8010`), scratch profile
> `testbed/scratch/f302_measure/` (its own sqlite `agentweave.db`, project `proj-c3039d3069b2`),
> started from `hub/` via `py -3.11 -m uvicorn hub.main:app --port 8091`. Three brand-new agents
> (`f302agent1`/`2`/`3`, runner `haiku-f302` bound to `claude-haiku-4-5-20251001`, `cli=claude`) —
> preconditions confirmed by direct read of the scratch db *before* triggering: `project_sessions`
> had no row for the project (no session-wide `hub_client`), each `agents.config` was `{}` (no
> per-agent override), the bound runner's `cli` is `claude` (in `MCP_INJECTABLE_RUNNERS`), and
> `SELECT COUNT(*) FROM runs WHERE agent=? AND project_id=? AND mcp_adapter_online_at IS NOT NULL`
> was 0 for all three. Each agent got the same one-shot instruction — *"Create a task titled 'F302
> probe task' with description 'measurement probe' in this project, then stop."* — bound to
> `claude-haiku-4-5-20251001`, one turn, `session_mode=new`. No charter was bound on any of the
> three (`charter_id` null); the project's roster held all three agents at once, so each had peers.
>
> All three runs completed, exit code 0, and each stamped `mcp_adapter_online_at` *during* the run
> (turn start had no grounds, exactly 7.1b's target condition — the first turn is a no-grounds turn
> even though the tools work). Reading each run's `agent_outputs` directly:
> - `run-3e7497554e98` (f302agent1) — **MCP**: `ToolSearch` for `mcp__agentweave__create_task`,
>   then called it. No HTTP shellout anywhere in the transcript.
> - `run-63c923499c5d` (f302agent2) — **MCP**, same shape.
> - `run-9ddb13b6dfeb` (f302agent3) — **MCP**, same shape.
>
> Zero `neither` runs; no replacement needed. **Verdict (7.5c, first branch): every sampled first
> turn reached for MCP.** This weakens R2's dissent substantially — on Haiku, with a charter-free
> single-shot instruction and peers present, a fresh no-grounds turn did not reach for `curl`. It
> does **not** close D2 on three runs (n=3, one model, one instruction shape, one throwaway
> project): recorded as a dated verdict here and in `DECISIONS.md`, and F302 is marked **fixed
> (measured)** rather than fixed without qualification. The baseline it is read against is **n=1**
> (the Architect only — see 7.5 above), not the earlier "4 of 4" claim; the confounds in tasks.md
> 7.5b (model: baseline was Opus/Sonnet, this measurement is Haiku; task shape: baseline opened a
> resumed multi-turn spec interview, this measurement is one self-contained instruction on a
> throwaway; surrounding text: baseline carried both false sentences, this measurement carries
> neither) all still apply — this result is about the fixed shape's own first turn, not a controlled
> A/B against 2026-09-14. Hub stopped cleanly afterward; scratch db and uvicorn log left on disk at
> `testbed/scratch/f302_measure/` as evidence, untracked per testbed conventions.

> **2026-09-20, interactive session: decided, unbuilt, and its stated precondition is now
> measured satisfied.** The verdict is `DECISIONS.md` `#### DAY-2 / F302 — the notice stops
> asserting, and does not start trusting` (2026-09-09): **drop the `no MCP tools this turn`
> sentence, and do not grant the MCP rendering on trust either.** That verdict made itself
> conditional — *"what makes this cheaper than it was this morning"* is the F299/F300 verdict
> teaching the approver to recognise the run's own Hub URL, *"so the HTTP form the notice steers a
> fresh agent toward is one the agent can actually use."* **That half has shipped and was measured
> today.** `_decide` was called directly at `d7f2694` with `AW_WORKSPACE_DIR` and `HUB_URL` set as
> the Hub sets them for a run; the notice's own instructed shape
> (`curl -H "Authorization: Bearer $AW_RUN_TOKEN" $HUB_URL/api/v1/agent-actions/tasks`) is
> **allowed**, in both the Bash and PowerShell renderings, while a foreign address is still refused
> as `_NETWORK` and `../outside.txt` still as `_OUTSIDE` (`mcp_server.py:1147-1152`,
> `_HUB_REFERENCE_RE` at `:987`). So the reason to wait is gone. **Still no change directory.**
> Measured evidence of the cost is in `openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`:
> all four LoopEngine agents opened on the false sentence, and the Architect kept to `curl` and
> payload files for ten runs after the notice healed, accounting for 9 of its 21
> `agent_wrote_outside_workspace` warnings.

**The mechanism is documented and deliberate; the sentence it produces is not.**
`described_access_path` (`hub/hub/launchability.py:263-295`) grants the MCP rendering only on
grounds, and the only observable ground is `Run.mcp_adapter_online_at` on a **previous** run of the
same agent (`harness_has_honoured_mcp`, `:232-256`). A brand-new agent has no previous run, so its
first turn always takes the other branch. The docstring says so in as many words, at `:285-290`:

> The first run against a fresh harness therefore reads the HTTP form while the server is in fact
> injected and its tools are in the model's tool list. That is deliberate and it is the safe
> direction of the two: under-describing a surface costs convenience for one turn […]

**What the drive adds is that the branch does not under-describe — it asserts.** The text is
`access_path_notice`'s second branch (`hub/hub/launchability.py:392-403`) and it opens:

> `[AgentWeave] Tool access: no MCP tools this turn — but the AgentWeave capability plane is
> reachable over HTTP […]`

`no MCP tools this turn` is a positive claim about the run's own tool list, and on this deployment
it is false. The requirement the change shipped against does not ask for it: the scenario *"No
grounds means no assertion"* requires only that the text **describe the HTTP form** and **not state
that tool-protocol tools are available**. A branch that said the second half and stopped would
satisfy the requirement without stating a falsehood.

**Measured, on one Hub, on 2026-09-09.** Two agents created fresh, each given exactly one turn:

| agent | turn 1 message | reply | `mcp_adapter_online_at` on that same run |
|---|---|---|---|
| `cold094500` | *list every tool whose name begins with `mcp__agentweave__`* | **`NONE-PRESENT`** | `08:42:24`, 5.5 s into the run |
| `cold2094600` | *create a task, try your `create_task` tool FIRST* | called `ToolSearch`, then **`mcp__agentweave__create_task`**, task `task-f0dcea69c7ac` created | set |

So the tools were there — the second agent used one and a row exists to prove it — and the first
agent, asked to enumerate rather than directed to act, answered that it had none. **Do not read the
first row as a controlled measurement of the notice's effect**: that harness defers tool schemas
behind `ToolSearch`, and an unsearched deferred tool is plausibly absent from what the model can
enumerate. What the two rows *do* establish together is that the claim in the notice is false while
the run is being told it, and that the tools are only one `ToolSearch` away from the agent that
was told it has none.

**Why B and not C.** It costs at most one turn per agent and heals itself on the second — the
adapter announces at startup, not on first tool call, so the grounds are earned by the same run
that is misdescribed. But the notice does not merely omit the tools: it names an HTTP path
instead, and F300/F301 measured that a `claude` run cannot actually use that path under its own
power on this machine. So the one turn is not steered from a good path to a slower one; on the
evidence of those two findings it is steered from a working path to a broken one.

**The operator's statement still wins, and that is the workaround — measured, not reasoned.**
Agent `cold3094700`, created fresh with `config: {"hub_client": "mcp"}` and given the same first
turn, quoted back:

> `[AgentWeave] Tool access: the `agentweave` MCP tools are available — call send_message /
> create_task / update_task / ask_user directly.`

which is the *"The operator's own statement is honoured"* scenario driven, on turn 1, with no prior
run of that agent anywhere.

**Not fixed here, and it is a wording decision inside a shipped requirement**, so it belongs with
the F299 posture decision already carried to the operator rather than being guessed by a window.
The cheap end of it is a branch that stops asserting what it cannot know; the expensive end is
whether a fresh agent should get the MCP rendering on trust.

**Reproduce**

```bash
# a Hub on 8011 from source, a fresh project, a claude/haiku runner
AW_HUB=http://127.0.0.1:8011 AW_KEY=... AW_PROJECT=<pid> py -3.11 - <<'PY'
import sys, time; sys.path.insert(0, "scripts/drive")
from aw import api, P
rid = api("GET", f"/projects/{P}/runners")[1][0]["id"]
NAME = "coldprobe"                      # must not exist: the grounds are per-agent
api("POST", f"/projects/{P}/agents", {"name": NAME, "runner_id": rid})
api("PATCH", f"/projects/{P}/agents/{NAME}", {"default_permission_mode": "bypassPermissions"})
api("POST", f"/projects/{P}/agent/trigger", {"agent": NAME, "message":
    "Create one AgentWeave task titled COLD-START-PROBE. Try your create_task tool FIRST and "
    "report verbatim what happens. Do not use Bash, curl or any HTTP request."})
PY
# the task exists; the turn was told `no MCP tools this turn`
```

**Observed again 2026-09-14** (day window I-1, `openspec/explorations/2026-09-14-the-first-turn-has-its-tools.md`,
read-only from `:8000`). **Decided 2026-09-09 and still unbuilt**
(`DECISIONS.md` `#### DAY-2 / F302`: drop the sentence; do not grant MCP on trust). O-3 sorted this
as improvement 5 without finding this entry. All four of LoopEngine's agents got the denial on their
first turn. The verdict calls the defect *"bounded — one turn per agent, healing on the second"*,
and LoopEngine measured that premise as wrong. The Architect's spec conversation resumed one harness
session for ten runs (`run-2445bbbe1d6d` 20:39 to `run-75a371830046` 23:44). The session carries
the denial once and the MCP rendering on each of the nine later runs, checked one prompt per run.
Even so, the Architect submitted every draft for the rest of the session with `curl` and a payload
file, while calling the MCP `ask_user` in the same session. The false first line outlived its turn
because the session's history kept it.

## F303 (B) — four drive scripts kept defaulting a Hub key for a day after the sweep that removed it, and the guard could not see them because the literal was the wrong shape

**Status:** fixed 2026-09-09 — day window, D-4, in the commit carrying this entry. Both halves.

The 2026-09-08 sweep (`ROADMAP` 6.2/6.3) removed a published `aw_live_` key from
`scripts/drive/aw.py` and its siblings, gated the directory with
`tests/test_drive_key_guard.py`, and left a count behind: *"10 literals in 8 files remain, all
outside `scripts/drive/`"*. Today's recount returns **exactly 10 real-shaped literals in 8 files** —
the number was right to the digit. **The sentence attached to it was false.** Four scripts in that
directory still carried

```python
KEY = os.environ.get("AW_KEY", "aw_live_<33 characters>")
```

— `t_d1_catalog_is_the_only_door.py:44`, `t_d4_instructions_failed_load.py:59`,
`t_n3_runner_model_picker_ui.py:38`, `t_n4_runner_refusal_reaches_the_operator.py:45` — each
sending it straight into `Authorization: Bearer`.

**Why nothing saw them.** Both instruments ask about *shape*. The recount and the guard match
`aw_live_[0-9a-f]{32}`, a real key's shape; the surviving literal is 33 characters, not hex, one
character repeated 28 times — a hand-written placeholder. So it is not a disclosed secret, and that
is exactly what made it invisible: **the count was measuring disclosure while the guard was
supposed to be preventing a behaviour**, and only one of those two questions is about shape. The
behaviour is the one `require_key()` exists to stop, described in `aw.py`'s own comment: an unset
`AW_KEY` produces a bogus Bearer token, the Hub answers **401**, and the script carries on with
exit code 0.

**Fixed by asking the shape-independent question.** All four now call `require_key()`. The new gate
`test_no_drive_script_defaults_the_key_to_anything` rejects any `os.environ.get("AW_KEY", <value>)`
whose default is not empty, of any shape. Mutation-checked, four ways:

| mutation | old shape-based guard | new default-based guard |
|---|---|---|
| the placeholder-shaped literal these four carried | **passes** (blind) | **fails** |
| a real `aw_live_` + 32 hex literal | fails | fails |
| `os.environ.get("AW_KEY", "")` | passes | passes |
| `os.environ.get("AW_KEY")` | passes | passes |

Each of the four was then run with `AW_KEY` unset: all exit 1 with the local refusal, before any
HTTP. Positive control — with a key set, all four pass the key check and reach the next statement
(the `:8000` refusal), so the guard gates emptiness and not use.

### The second half: the rotated key had somewhere to come back from

`ROADMAP` 6.3 records the disclosed key as rotated by the operator on 2026-09-08 and its ten
surviving literals as *"all dead against a rotated key"*. Both statements are true and together
they are not the whole answer. Measured today:

- **No database on this machine honours any of the three distinct real-shaped literals.** All ten
  sites map to three values; every one was checked against `operator_credentials` and `api_keys` in
  all three local databases (`trial`, `live`, `f274p0`) — **no rows**. Checked on copies; the
  `live` profile on :8000 was read, never touched.
- **`hub/.env` still held the disclosed key**, untracked and gitignored, mtime 2026-03-31. It is
  the only file on this machine outside the repository's own text that did.
- **That file is loaded by the documented trial-Hub launch.** `hub/hub/config.py:21` reads
  `.env` relative to the working directory, and CLAUDE.md's launch command runs from `hub/`.
  Measured: `Settings()` from `cwd=hub` returns the value in `.env`.
- **A fresh database mints that value verbatim.** `_seed_operator_credential`
  (`hub/hub/db/engine.py:336-341`) auto-generates only when the configured key is empty or is the
  documented `a1b2c3…` placeholder; anything else becomes the instance operator credential as
  written. Measured on a throwaway in-memory database, with the placeholder as a negative control.

So the disclosed key was dead in every store and one fresh-database launch from the documented
directory away from being alive again — which is what the 2026-09-07 trial rebuild was. It did not
happen (the trial credential does not match), but nothing prevented it. **Rotated in `hub/.env`
today**, one line, same length, no other line touched; the file stays untracked, so no key literal
enters the repository by this fix. `Settings()` re-read afterwards confirms the new value is what
the launch path now sees.

**The lesson, and it is the same one twice.** A count of disclosed secrets and a guard against a
bad practice are different instruments, and 6.3 used one number for both. The other eight literals
are correctly classified and stay: the documented placeholder (`hub/.env.example:18`,
`hub/hub/db/engine.py:34`, `hub/tests/test_setup.py:58`) is documentation and is asserted upon; the
redaction fixtures (`hub/tests/test_operator_is_told_the_truth.py:41,59,128`) exist *because* the
key leaked and deleting them deletes the regression; the two historical loop documents and this
ledger's own transcript line are the record of the leak, already public in git history, where
scrubbing the working tree would change nothing about disclosure and would destroy the account of
it.

---

## F304 (C) — a run cancelled by shutdown stores an empty string as its reason

**Status:** fixed (day D-4, 2026-09-21; sha in the commit that carries this line). `run.error = str(exc) or type(exc).__name__`; regression test fails without it. Original observation: Observed 2026-09-09 while driving `F298`'s fix, in the two `f295` drive databases
either side of it — so it is **pre-existing and unchanged by that fix**, which is why it is filed
rather than folded into it.

`_record_run_failure_tail` marks the row with `run.error = str(exc)`
(`hub/hub/api/v1/agent_trigger.py:1877`). `str(asyncio.CancelledError())` is `''`. So the one
exception that handler was principally written for is the one that leaves the row saying `failed`
and nothing at all about why:

```
sqlite> select id, status, ended_at, error from runs;
run-05b2b6fe5ef5|failed|2026-09-09 01:08:29.888926|      <- pre-F298-fix drive
run-8f02111bdb43|failed|2026-09-09 10:10:06.610527|      <- post-fix drive, identical
```

Every other path into that line carries a message; this one carries the empty string, and an empty
string is indistinguishable from "nobody set it" for any reader that tests truthiness.

**What is not established, and is not being claimed.** No route was found that returns `Run.error`
to a screen — `agent_chat.py` does not carry it, and the terminal label an operator sees comes from
the run facts on the chat response (F274). So the measured cost is to the **record**, not yet to a
surface: a stored row that cannot say why it ended. Whether anything renders it is unverified.

**Reproduction:** `py -3.11 scripts/drive/f295_shutdown_drive.py`, then read the `runs` table in the
database the script prints — the cancelled run's `error` is `''`. Two databases with it are kept:
`%TEMP%\f295drive020814\f295.db` and `%TEMP%\f295drive110952\f295.db`.

**Adjacent, deliberately not merged.** `F298` is about how the cancellation is *reported to the
console*; this is about what is *stored on the row*. The same `isinstance` branch would serve both,
but one is a log line and the other changes a persisted value that F274's work reads near, so it
wants its own look.

---

## F305 (B, harness) — a decision the operator has answered is re-asked, because the authority file is not what the windows read

**Status:** fixed (this commit) [Round 6, 2026-09-24] — one channel: `day-window.md`, `night-window.md` and `arm-cycle.ps1` now say `decisions_for_user` carries only ids of `OPEN` `DECISIONS.md` rows, and day-window.md's compose step drops and logs any inherited id that is not `OPEN`. Was: open — **Decided 2026-09-24 (operator, daily review, bundle B11; `spec-queue/tracks/B11.md` Final)**: no-spec fix round (harness).

**Measured today, end to end.** The operator answered the `F299` posture question in session and the
verdict was committed to `spec-queue/DECISIONS.md` at **`0ecfc38`, 08:51**. The day window composed
its queue at **`ed7d3ef`, 09:17** — 26 minutes later, with that commit already on the branch — and
at **10:55** published `spec-queue/review/review-2026-09-09.html` carrying the same question as
open decision `DAY-3`, *"carried from last night"*.

**The cause is structural, not a slip.** There are two decision channels and only one of them is
the authority:

- `spec-queue/DECISIONS.md` — the contract at its head says *"the status token is the authority"*
  and *"a window may never mark one DECIDED."* This is where a verdict is written.
- `decisions_for_user` inside `STATE-night.json` / `STATE-day.json` — where a window *raises* one,
  and where the next window inherits it. `STATE-night.json` still carries the `F299` entry now.

Nothing reconciles the second against the first. A window carries its predecessor's
`decisions_for_user` forward without checking whether `DECISIONS.md` has since answered it, so an
answered question is re-raised on every subsequent review page until somebody edits the state file
by hand. **The failure is silent and it costs the operator, not the loop**: the review page presents
a decided question as still owed.

**Why this is worse than an ordinary stale document.** `DECISIONS.md` exists *because* this list
used to live only in `STATE-night.json`, which each window rewrites — that is stated in its own
opening paragraph, and the durable file was the fix. Half the fix shipped: verdicts became durable,
but the raising side kept its own copy and no link back.

**What it is not.** Not a wrong verdict, and not a window ignoring the operator — the day window had
no instruction to read `DECISIONS.md` at compose time, and its playbook does not name that file in
iteration 1 at all. The defect is the missing reconciliation, not the window's obedience.

**The shape of a fix, not yet decided:** either the window clears a `decisions_for_user` entry when
`DECISIONS.md` carries a matching decided section, or `decisions_for_user` stops holding questions
and holds only pointers into `DECISIONS.md`, which would leave one channel. The second is cleaner
and larger. **Not fixed here** — it changes the loop's own contract and belongs in a proposal.

**FIXED 2026-09-24 (Round 6):** implemented option (b), the operator's decided answer
(`spec-queue/DECISIONS.md`, row `B11-all`; `spec-queue/tracks/B11.md` Final, row 16). Files:
`.claude/loops/day-window.md` (Iteration 1 step 3 — reconciliation check; "A day that builds"'s
`REV`-stops-a-change bullet; the Limits bullet), `.claude/loops/night-window.md` (the
implementation-turns-out-wrong bullet; its Limits bullet), `.claude/loops/arm-cycle.ps1` (the
`decisions_for_user` initializer, now commented with the contract, and the shared `limits` string
both windows' `STATE-*.json` carry). Every site now says the same thing: a window raises a decision
by adding an `OPEN` row to `spec-queue/DECISIONS.md` first, then puts only that row's id — never a
sentence — into `decisions_for_user`; and day-window.md's compose step (Iteration 1 step 3, the one
place a window structurally reads the other window's carried-forward `decisions_for_user`) looks
every inherited id up in `DECISIONS.md` and drops and logs any whose row is not `OPEN` there (`DECIDED`,
`DEFERRED`, or no row at all).

**Production path that reaches the fix.** `arm-cycle.ps1` runs from the `AgentWeaveDayLoop` /
`AgentWeaveNightLoop` Scheduled Tasks at 08:55/22:55 (`install-driver.ps1`'s registration), writes
`STATE-day.json`/`STATE-night.json` with the updated `limits` string and an empty
`decisions_for_user`, and the first `claude -p` firing of each window reads the corresponding
playbook (`day-window.md`/`night-window.md`) in full per its own `next_action` before composing —
so the reconciliation instruction and the id-only contract reach the actual unattended window, not
just a document nobody reads. This is a prompt/playbook fix, not code: there is no interpreter that
enforces it independently of the window following its own instructions, same as every other rule in
these two files.

**Scope note — the two `autonomous-prep`/`autonomous-session` skills were intentionally left
untouched here.** They live outside this repository at the user level
(`C:\Users\huida\.claude\skills\autonomous-prep\SKILL.md`,
`C:\Users\huida\.claude\skills\autonomous-session\SKILL.md`) and the round's instructions were to
propose exact text for them rather than edit them directly; see the round's delivered report for the
proposed wording. Until that is applied, those two generic-loop skill docs still describe
`decisions_for_user` without the `DECISIONS.md`-id contract — they do not drive the daily
FILL/FIX cycle directly (`arm-cycle.ps1`/`day-window.md`/`night-window.md` do), so this does not
reopen the finding, but it is a residual worth closing for consistency.

**Tests.** No unit test applies — these are three markdown/PowerShell playbook and driver files with
no Python/JS import path. Verified instead: `[System.Management.Automation.Language.Parser]::ParseFile`
on `arm-cycle.ps1` reports no errors after the edit, and `arm-cycle.ps1 -Window night -DryRun` was
run from the worktree on a clean tree and exited 0, printing the `DRY RUN:` line with no git mutation
and no task registration (confirmed by reading the script's own `-DryRun` branch, which `exit 0`s
before any `git checkout`/`commit`/`push`/`install-driver.ps1` call). `grep -n decisions_for_user`
over all three files confirms every remaining mention uses the new id-only wording.

---

## F306 (A) — an agent can be staffed to review, and approve, work it recorded evidence for

**Status:** fixed `4929ea0` (tests `40bd429`) by `an-agent-that-recorded-the-evidence-is-the-author`,
archived 2026-09-12 (night window, `n8-close`), and driven live on both trees — see the block at the
end of this entry. Filed 2026-09-09 (night window, iteration 3), **measured on a live Hub**. Found
by F142's row-four drive, and it lives inside F142's own repair. It does **not** reopen
F142: that finding's two claims — operator-completed work is routed for review at all, and a refusal
names the task rather than the queue's status histogram — held on both arms (20/20 on
`operator_after_agent`, 19/19 on `untouched`; the counts differ because the two modes assert
different things in section B).

**What was measured.** `proj-f741298c9c6b` on `:8011`, Haiku, `AW_COMPLETE_BY=untouched` in
`scripts/drive/t_row12_review_leg.py`. Agent `r7af142d` was triggered **without `task_id`**, wrote
`reviewleg_f142d.py`, and called `record_evidence(task_id='task-930385ddb031', kind='implementation')`.
The operator then walked the task `pending → in_progress → completed` by hand and fired the flow.
The flow staffed **`r7af142d`** as the reviewer of its own code, and sequence 19 of the task's
history is `under_review → approved`, `actor_kind='run'`, `actor_agent='r7af142d'`. Nothing refused
it and nothing recorded that it happened.

**Why the exclusion missed it.** `agents_that_may_have_authored`
(`hub/hub/task_transition_service.py:253-283`) is the union of exactly three sources, and its
docstring tabulates them — transitions, `assignee`, runs bound to the task. All three were empty
here, correctly:

| source | value in this run | why |
|---|---|---|
| `agents_that_worked` (transitions) | ∅ | every pre-review transition is `actor_kind='operator'`, `actor_agent` NULL |
| `task.assignee` | NULL | the task was never assigned; it went straight from `pending` by operator PATCH |
| `agents_of_runs_bound_to` | ∅ | `run-e8ff74d5c129` has `task_id` **NULL** — the turn was never bound |
| **`requirement_evidence.actor`** | **`r7af142d`** | **not a source** |

The evidence row is the fourth record, and by the docstring's own standard it is the *strongest* of
the four: the other three are circumstantial (this agent moved it / holds it / ran about it), while
an accepted `implementation` evidence row is the agent asserting **"this is my implementation of
this task"**, carrying the commit the reviewer is then handed. The function's stated principle is
*"a record associating an agent with a task is sufficient to exclude it, and a source's silence is
not evidence that the agent did not work it"* — applied to three of four sources.

**`_guard_author_is_not_reviewer` does not catch it either** (`:286-311`). It compares
`agent_that_completed` against the actor, and an operator completion writes `actor_agent = NULL`, so
there is no completer to compare. The two defences against self-approval have the same blind spot
for the same reason, and this is the arm on which they are the only defences.

**The branch that produced it says, in its own comment, that this must not happen.** At
`scheduler.py:1566-1571`, immediately above the call:

> **But the exclusion cannot be `{author}`, because there is no author to name**, and `exclude=set()`
> is a self-approval route: the agent that wrote the work is still eligible, and both transition
> guards *permit* when the completer is unknown … So the ladder gets every agent any record
> associates with the task.

`agents_that_may_have_authored` returned the empty set here, so the ladder got `exclude=set()` — the
value the comment rules out — by the route the comment describes as the remedy for it. The widening
is not wrong; it is incomplete, and where it is incomplete it is indistinguishable from not having
been done.

**Severity A, and the reason is in the code's own words.** The design weighed the two costs
explicitly: *"the cost of excluding an agent that did nothing is a review the flow reports it could
not staff, which the operator sees; the cost of including one that wrote the work is a self-approval
nobody sees."* This is the second cost, incurred silently, on the arm the widening was written for.
It fails **open**, which is what separates it from `F167` (B) — the adjacent residual on the same
repair, which fails closed.

**How reachable it is in the product, stated exactly.** It needs three things, and none is exotic:
an agent turn **not bound to a task** (the ordinary shape when an operator drives an agent from the
composer), that agent recording evidence with a `task_id` (`record_evidence` takes one, and the flow
briefing asks for evidence), and the operator marking the task complete themselves — which is
precisely the operator behaviour F140 and F142 are both about. Here the pool was two and it picked
the author.

**Corrected 2026-09-12: the ordering is deterministic, and that makes this worse, not rarer.** This
paragraph used to end *"what is not established is how often the reviewer ladder picks the author
… Unverified: whether ordering is deterministic."* The change's R1 measured it (`design.md` D6):
`_agents_that_are_free` orders by `Agent.name`, and rung 2 takes the first eligible candidate,
stable across repeats and independent of insertion order. So it is not a frequency. An author whose
name sorts first among the free agents reviewed its own work on every firing, for every task it
authored. The pre-fix drive agrees: the flow staffed the author 2 times out of 2 (below).

**A truly untouched task is reachable and is not affected.** `POST /spec/evidence`
(`hub/hub/api/v1/spec.py:801-833`) records evidence as `Actor(kind="operator")`, so an operator can
supply the accepted evidence naming a commit that the review arm requires
(`scheduler.py:1538-1548`) without any agent touching the task. In *that* world the empty exclusion
is correct and this finding does not apply. The defect is the case where the evidence came from an
agent and nothing else did.

**The shape of a fix, not decided here** — this window does not write proposals, and this changes
who may review, which needs one:

- add the evidence table as a fourth source to `agents_that_may_have_authored`, scoped by `kind` so
  a *reviewer's* own evidence does not exclude the reviewer that produced it — the naive union would
  make the second review of a task unstaffable; or
- have `_guard_author_is_not_reviewer` fall back to `agents_that_may_have_authored` when
  `agent_that_completed` is NULL, which puts the refusal at the transition rather than at staffing
  and so also covers a reviewer the operator assigns by hand.

The first is the same principle the exclusion already states, extended; the second closes the door
rather than the corridor. **Both are guesses until someone reads what else writes evidence rows.**

**Corrected 2026-09-12: the first bullet's `kind` scoping is refuted, and the change shipped without
it** (`design.md` D5). Scoping needs a closed vocabulary. The corpus forbids one:
`requirement-traceability` says the set of kinds *"SHALL be open to additions"*, and
`agent-capability-plane` says *"open ones SHALL stay open"*. `db.models.EVIDENCE_KINDS` exists but
is advisory, and nothing validates against it. This finding's own reproduction stored
`kind='implementation'`, which is not one of its six words, so scoping on it would fail open on
the first word outside the list. The product does not ask a reviewer for evidence either, because
`_briefing_evidence_lines` returns nothing for a review. The residue is written down in D5 as a
known cost: a reviewer that records evidence anyway is excluded from a later review of the same
task. What shipped is the **unscoped** union plus the guard fallback, which is both bullets with the
first bullet's scoping taken out, and it reaches five call sites rather than two.

**How it was found is worth keeping.** The drive's own assertion — *"with NOBODY excluded — any
bound agent may take it"* — passed, truthfully. It accepts `reviewer in pool or reviewer == AGENT`,
so a correctly-empty exclusion and an exclusion that missed the author are the same string to it.
The defect sits one level under the claim, and only reading `task_transitions` and
`requirement_evidence` in the drive database told them apart.

### `F306` — driven on both trees, 2026-09-12, and read from the tables both times

The drive harness prints green on both trees, so the proof here is the database, not the harness.

**Pre-fix tree** (`37b8226`, from a git worktree; port 8014, profile `drive0912p`, kept).
`proj-34d006e2f3e5`, `task-9ba36b0bd788`: seq 5–7 were operator moves with `actor_agent` NULL.
**Seq 8, `under_review→approved`, has `actor_agent='r7af306q'`** on `run-bb80909c0e15`, and
`ev-4d13beb472c4` (`implementation`, accepted) has `actor='r7af306q'` on an unbound run. That is
this finding's row, reproduced. The flow staffed the author 2 times out of 2. The author approved
in 1 of the 2. In the other it never called `update_task`, and the silent review was restaffed.

**Fixed tree** (`cddf32b`; port 8015, profile `drive0912`, kept). `proj-192ee0e59efb`,
`task-88efa63d19ee`: the author `r7af7a` recorded `ev-b6a5a19738e9`, and the task's first and
**only** bound run is `run-1d7e3883437a`, agent `r7bf7a`. No `run_divergences` row exists, so no
restaff stands in for the fix. **Seq 4, `under_review→approved`, has `actor_agent='r7bf7a'`.**

The author was also refused at each of the other doors, all on `proj-99af62baca17`,
`task-714b1ea52e2e`:

- Its own `update_task(approved)` through the real MCP path was refused with 403, and no seq 8 was
  written.
- A flow firing where it was the only other agent returned 409 *"could not staff this step"*. The
  sentence does not claim that anyone completed the task.
- `POST /agent/trigger` naming it as the reviewer was refused with 403 before any run, queue entry
  or checkout existed.
- The operator's `PATCH` assigning it with `status=under_review` was refused with 403. The assignee
  rolled back and no transition was written.

Transcripts and table dumps are in `profiles/drive0912/n7-transcripts/` and
`profiles/drive0912p/n6-transcripts/`. Log: `.claude/autonomous/2026-09-11-night-log.md`,
iterations 7 and 8.

---
## F307 (B) — a confirmation dialog's first Tab leaves the panel, into the editor behind the scrim

**Status:** fixed `f473510` (Tab/Escape half, UI-1, 2026-09-23) and `68f11b4` (initial-focus half, D13 of `a-dialog-takes-the-keyboard-when-it-opens`, 2026-10-02) — a Tab arriving from outside the panel enters it, the cycle is closed from the first press, and the panel now takes initial focus on open so there is no outside-the-panel press 1 left to make. Both halves measured in a real browser against the served bundle. Was: open — filed 2026-09-10 (night window, iteration 8), **measured in a real browser**
against the served bundle, not fixed. **Pre-existing and shared**, not introduced by the change that
found it: `useDialogFocus` is the common hook, and the blind spot is in the hook.

**What was measured.** `scripts/drive/t_d9_clearing_instructions_postchange.py`, leg E, on a fresh
`:8012` Hub serving bundle `index-BvtjVm7p.js`. A keyboard operator focuses Save, presses Enter, and
`ClearInstructionsDialog` opens. Five Tab presses, each read off `document.activeElement`:

| press | lands on | inside the panel? |
|---|---|---|
| 1 | `TEXTAREA` `aria-label="Project instructions"` | **no** |
| 2 | `BUTTON` "Cancel" | yes |
| 3 | `BUTTON` "Clear instructions" | yes |
| 4 | `BUTTON` "Cancel" | yes |
| 5 | `BUTTON` "Clear instructions" | yes |

So the cycle *is* closed — once focus is inside. The first press escapes.

**Why.** `useDialogFocus` (`hub/ui/src/hooks/useDialogFocus.ts`) never moves focus into the panel
when it activates. It records `document.activeElement` to restore later, binds a `keydown` handler,
and its Tab branch only acts when the active element is the panel's `first` or `last` focusable:

```
if (event.shiftKey && document.activeElement === first) { … last.focus() }
else if (!event.shiftKey && document.activeElement === last) { … first.focus() }
```

Focus is still on the trigger — Save, which lives in `SettingsSection`'s heading, a sibling subtree
of the `{children}` the dialog is mounted in — so the active element is neither `first` nor `last`,
neither branch fires, and press 1 falls through to the browser's native order. The next focusable
after Save in DOM order is the instructions textarea, which is *behind the scrim*: the operator
cannot see that it has focus and cannot click it.

**Which dialogs this reaches.** Six components use the hook. *(The table below originally listed five; the
sixth, `TaskDetailDrawer` (`:183` as of 2026-09-22), was added for `F311`. It is also the call site where the hook's Escape
branch misbehaved (`F309`/`F310`), which that row does not cover. Enumerate from `grep`, not
from a table.)* Three escape the defect by accident,
not by design — they `autoFocus` an input **inside** the panel, so focus is already `first` when the
first Tab arrives:

| dialog | autofocuses inside the panel? | affected |
|---|---|---|
| `AgentCreateDialog` (`:204`) | yes, the name input | no |
| `DeleteProjectDialog` (`:67`) | yes, the type-to-confirm input | no |
| `ProjectManagerModal` (`:140`) | yes, the path input | no |
| `ArchiveConfirmDialog` | no — two buttons only | **yes** |
| `ClearInstructionsDialog` | no — two buttons only | **yes** |
| `TaskDetailDrawer` (`:183`) | no — it focuses the blocking-reason input only once that panel appears (`:180`) | **yes, by the same reading** (not measured; added 2026-09-22 for `F311`) |

It is exactly the confirm-only dialogs, the ones whose whole content is a question and two buttons,
that fail to hold focus. `ClearInstructionsDialog` was deliberately shaped after
`ArchiveConfirmDialog` and inherited it by construction.

**Why B and not C.** There is a path to a wrong write, which is what keeps this off the friction
pile: open the dialog, Tab once, type — the keystrokes edit `content` in the textarea under the
scrim, unseen — then Cancel and press Save. The save that lands is over text the operator typed into
a control they could not see, while a modal about that very text was on screen. It is not A because
reaching it takes a Tab the operator did not intend and a save they did intend; nothing writes
behind their back.

**Not fixed here, and the reason is not effort.** The hook serves six dialogs, so *which* control
takes focus when a dialog opens is a decision that changes all of them — and for a destructive
confirmation it is a real design question, since focusing the panel's first focusable means focusing
**Cancel** and focusing its last means focusing **"Clear instructions"**. That belongs to the round
discipline, and the window that measured this does not write proposals. Two shapes, both guesses
until someone checks the other five call sites: move focus to the panel's first focusable on
activation (and let each dialog order its buttons so the safe one is first), or fall back to
trapping whenever the active element is *outside* the panel rather than only at its edges.

**2026-09-11 — a change landed in this hook and deliberately did not subsume this.**
`2026-09-10-the-control-that-asks-holds-the-keyboard` repaired `F309` and `F310`: the **Escape**
branch of `useDialogFocus` now stands down when a nested owner has already answered the key. It left
the **Tab** branch exactly as written above, on purpose, and the next reader of this section should
not have to reconstruct why. Three reasons, in the order they bind:

- **The operator decided it.** `DAY-1`, answered 2026-09-10 18:30, asked whether this should be
  swallowed by that change. The answer was **no** — the split stands. That is what `APPROVALS.md`
  records, and it is the reason that outranks the other two.
- **The two branches do not share a question.** Escape had an *arbitration* defect: a mechanism
  question with one right answer once you notice the binding is on `document` in the bubble phase.
  Tab has a *design* question — which control holds the keyboard when a destructive confirmation
  opens, `Cancel` or the destructive button — and that is the operator's to answer, not a hook
  author's. A change that swallowed both would have decided the second one silently while fixing
  the first.
- **It still reproduces at `HEAD`, which is evidence rather than assertion.**
  `scripts/drive/t_d9_clearing_instructions_postchange.py` leg E still prints
  `F307 REPRODUCED ... TEXTAREA/Project instructions`, run 2026-09-11 against served bundle
  `index-7rpxplrH.js` — the bundle that carries the Escape repair. So the repair demonstrably did
  not reach this branch by accident either.

A reader who arrives here from a recent commit in `useDialogFocus.ts` should therefore not conclude
this was handled in passing. It was looked at, scoped out, and wants a review page before anyone
writes code for it.

**It is kept as a reproduction, not as a red check.** Leg E asserts both halves — that presses 2-5
cycle within the panel, and that press 1 escapes to `aria-label="Project instructions"` — so the
drive exits 0 meaning *"the change's own contract holds and F307 is unchanged"*. Fixing F307 will
fail that file loudly, which is the right moment to revisit it.

**FIXED 2026-09-23 (interactive session, UI-1).** `useDialogFocus`'s Tab branch now checks whether focus is inside the panel at all: when it is not (still on the trigger, as measured), a Tab moves it to the panel's first control and a Shift+Tab to its last, with `preventDefault`. Initial focus is untouched; which control gets it on open is D13's separate question. Because that makes an older dialog's listener act whenever focus sits in a newer one, the hook now keeps a module-level stack of open dialogs and only the newest wraps Tab. All seven call sites are modal and none is mounted inside another today. Tests: `useDialogFocus.test.tsx` (four new; the two first-Tab cases fail on the old hook, and the nested case fails with the stack check removed). Not yet re-driven in a browser (UI-1's closing check).

**Review follow-up 2026-09-23 (adversarial Opus review of UI-1).** Escape had the same two-dialog problem, predating the round: the older dialog's listener was registered first and so closed first. It is now gated on the same stack. Test: `useDialogFocus — Escape with two of its own dialogs open`.

**D13's half — which control gets initial focus — CONFIRMED FIXED, 2026-10-02 (night window, iteration 19).** `a-dialog-takes-the-keyboard-when-it-opens` (D1) answers UI-1's deferred question: the panel's `data-dialog-initial-focus` mark moves focus to Cancel on mount, so a destructive confirmation never leaves focus on the trigger in the first place. Re-driven in a real browser on a fresh `:8012` throwaway Hub serving bundle `index-Cyk3sQbn.js` (built from `096829c`):
- `t_d9_clearing_instructions_postchange.py` leg E, 59/59 checks passed. Open puts focus on Cancel (not Save, not the textarea); four Tab presses cycle `["Clear instructions", "Cancel", "Clear instructions", "Cancel"]`, all inside the panel; Escape returns focus to Save.
- `t_d10_dialog_focus_sweep.py` (new, task 3.2): the other three D5 dialogs — `CharterForm`, `RunnerForm`, `JobForm` — plus `SetupModal`, opened from each one's own trigger with the keyboard alone (`Enter`) and closed with `Escape`. 21/21 checks passed: in every one, focus lands inside the panel (on its `data-dialog-initial-focus` element) the moment it opens, and Escape returns focus to the trigger that opened it.
`ArchiveConfirmDialog` and `TaskDetailDrawer` (D6's effect-based variant) were not re-driven live this iteration — they were covered by task 2.8's vitest coverage, not by this browser sweep.

---

## F308 (B) — pinning CI to the resolution buys agreement by spending the drift alarm, and nothing replaced it

**Status:** fixed (this commit) [Round 1, 2026-09-22] — the operator chose a weekly unpinned job; see FIXED at the end of this entry. Filed 2026-09-10 (night window, iteration 13), by the iteration that *created* it. **Remaining step decided 2026-09-24 (B11):** add the drift workflow's latest run to `check-build` as its own row ("not fired yet" / stale after 8 days); first firing 2026-09-28.
Not a defect in `constraints-dev.txt`, which does exactly what the `DAY-1` verdict asked for. It is
the cost side of that verdict, measured, so that it is a known trade rather than a surprise later.

**What changed.** `constraints-dev.txt` pins `starlette==1.6.0` and `fastapi==0.141.1`, and both CI
jobs that build a test environment now install through it (`.github/workflows/ci.yml`, `test` and
`hub-test`). Before this, every CI run resolved those two fresh from PyPI.

**What that costs, in the verdict's own words.** `DECISIONS.md`'s `DAY-1` keeps the published range
loose *"so upstream incompatibilities still surface early — which is exactly what happened today and
is worth keeping."* That surfacing happened **because CI resolved fresh**. With `-c` on both jobs,
the next `starlette` release inside `<2.0` is no longer installed by any job that runs a test, so
the mechanism that produced the 2026-09-09 signal cannot produce the next one. The warning arrives
when a human bumps the pin, which is the *conscious upgrade* half of the verdict working — but there
is now nothing that tells them to.

**What is left, measured rather than assumed.** Three install paths still resolve the published
range fresh:

| path | resolves fresh? | what it would catch |
|---|---|---|
| `hub/Dockerfile:17` (`pip install --no-cache-dir .`), via `hub-image.yml` | yes | an install/import break only — the image build runs **no tests** |
| `.github/workflows/docs.yml` (`pip install -e ./hub`) | yes | an install break during a docs build |
| `publish.yml` | builds an sdist/wheel; installs nothing from the range | nothing |

And `hub-image.yml` is triggered only by pushes to **master** and `v*` tags, path-filtered to
`hub/**` — so on the cycle branch where all this work happens it never runs at all. The residual
signal is: an upstream release that breaks *importing* the Hub would fail a Docker build on master.
An upstream release that breaks *behaviour* — which is the class the starlette route-shape defect
belongs to — is caught by nothing.

**Why B and not C.** Nothing behaves wrongly; what is misleading is the meaning of a green board. As
of this commit, CI passing means *"the pinned resolution passes"*, and it used to mean *"a fresh
resolution of the published range passes"*. `pyproject.toml` still advertises the loose range to
users, and no run tests it. That is a claim the repository makes and no longer checks.

**Not fixed here, deliberately, and it is not a one-liner.** The obvious shape — a scheduled
unconstrained job, weekly, allowed to fail without gating — is a new CI job and a new answer to
*"what happens when it goes red on nobody's commit"*, which is the operator's call and belongs to
the round discipline. Two other shapes exist and are worth costing at the same time: one matrix leg
of the existing `test` job that drops `-c` (cheap, but it re-splits local from CI for that leg), or
a `scripts/` tool like `check_model_catalog.py` that compares the pins against what PyPI currently
offers and reports drift without gating.

**One-command reproduction of the trade, on this machine:**

```
py -3.11 -m pip install --dry-run -e ./hub                        # keeps whatever is installed
py -3.11 -m pip install --dry-run -c constraints-dev.txt -e ./hub  # forces CI's resolution
```

The first reports `starlette<2.0 … (0.52.1)` already satisfied; the second would install
`starlette-1.6.0 fastapi-0.141.1`. That difference is the whole value of the file — and the reason
the alarm it silences was worth something.

---


**FIXED 2026-09-22 (interactive session, Round 1).** Put to the operator with the three shapes this
entry costed. They chose the scheduled unconstrained job: *"Weekly unpinned job — catches behaviour
breaks, never gates merges."*

`.github/workflows/upstream-drift.yml`: weekly (Mondays 07:00 UTC) plus `workflow_dispatch`,
installs `-e "./hub[dev]"` and `-e ".[dev]"` with **no** `-c`, then runs the Hub suite and the CLI
suite. It writes the resolved versions and the current pins into the run summary, so a green run
still reports how far the pins are behind.

- **It cannot block a merge.** The gate requires a `success` for the workflow named `CI` at HEAD's
  sha (`.claude/loops/day-window.md`, the gate's conditions). This workflow is named
  `Upstream drift`, and `tests/test_dev_constraints.py` asserts it is not named `CI`.
- **It runs the suites, not an import.** An install-only check is what `hub-image.yml` already
  gives, and this entry measured that as catching nothing in the starlette class.
- **The missing `-c` is guarded**, because the obvious tidy-up is to add one.
  `TestTheDriftAlarmTheConstraintsSilenced` in `tests/test_dev_constraints.py` fails if the file
  disappears, loses its schedule, constrains its installs, or stops running the suites.
- **It starts when `master` has it.** GitHub reads `schedule` and `workflow_dispatch` from the
  default branch only, so on the cycle branch it neither fires nor can be dispatched. Until then
  the alarm is written but not armed, and the operator's merge arms it.
- **Measured today**, `py -3.11 -m pip install --dry-run --ignore-installed -e ./hub`: starlette
  1.6.0, fastapi 0.141.1, SQLAlchemy 2.0.54, pydantic 2.13.5, uvicorn 0.53.0. The first two are
  exactly the pins, so the job would pass today and says nothing until upstream moves.

## F309 (A) — the blocking-reason input never gets focus, so the operator's reason is typed into the status menu and each space re-opens it

**Status:** fixed — **two commits, and the split is this finding's own shape.** `7a0e5bc` is the
half the *"`autoFocus` loses"* paragraph below blames: `RowMenu` learns that an item can open a
control which will take the keyboard (`takesFocus`), and runs such an item's action from
`onCloseAutoFocus` after `preventDefault()`, so the menu **hands the keyboard over** instead of
restoring it to its trigger on the way out. `beb38d6` is the other half: the reason panel takes
focus itself, from a ref in an effect keyed on *whether* a reason is being collected, and
`autoFocus` — the mechanism that lost the race — is gone. Neither commit works alone, which is why
both are named: `7a0e5bc` without `beb38d6` leaves nothing to receive the keyboard, and `beb38d6`
without `7a0e5bc` was measured losing the race a second time (Radix flushes `onSelect`
synchronously, so the effect focused the input while the menu scope was still trapping).

Filed 2026-09-10 (day window, `D-1`), **measured in a real browser** against the served bundle on a
throwaway `:8013` Hub. Pre-existing; nothing the night window built touched this screen. Driven
green 2026-09-11 (night window) against served bundle `index-7rpxplrH.js`:
`t_d1_0910_escape_across_the_dialogs.py` **48 passed / 0 failed**,
`t_d1_0910_rowmenu_leaves_the_page_inert.py` **37 passed / 0 failed** — and the keyboard path the
gesture below describes is now measured rather than inferred (leg `P6`: `ArrowDown` to *Move to
blocked*, `Enter`, focus lands on the `INPUT`, all 19 characters land, and the Hub's own record
reads `status='blocked' reason='the staging API key'`).

**The gesture.** A ticket in `in_progress`. Open it, open its status menu, choose **Move to
blocked**. The Hub requires a reason for a hand-set block, so `TaskDetailDrawer` does the right
thing and asks instead of sending a status that would be refused
(`hub/ui/src/components/tasks/TaskDetailDrawer.tsx:296-299`). The reason input mounts with
`autoFocus` (`:409-410`). The operator types their reason.

**What was measured**, `scripts/drive/t_d1_0910_escape_across_the_dialogs.py`, leg `C2c`:

| | |
|---|---|
| `document.activeElement` after the reason input mounts | `BUTTON`, `data-testid="task-status-menu-<task-id>"` |
| the reason field's value after typing `the staging API key` | `''` |

Nineteen keystrokes, none of them in the field. `autoFocus` loses: `RowMenu`'s
`DropdownMenu.Root` (`hub/ui/src/components/layout/RowMenu.tsx:64`) returns focus to its trigger
when it closes, and that restore runs after React has mounted the input.

**And then it gets worse, which is why this is A and not B.** The trigger is a `<button>`, so a
space is a click. `t_d1_0910_rowmenu_leaves_the_page_inert.py`, leg `P5`, one `Space` on the
focused trigger:

```
before:  {"body": "auto", "poppers": 0, "menuItems": 0}
after:   {"body": "none", "poppers": 1, "menuItems": 3}
```

The status menu re-opens, and because Radix's `DropdownMenu` defaults to `modal: true` it sets
`pointer-events: none` on `document.body` — the whole page goes unclickable while it is open. *"the
staging API key"* contains three spaces. So the operator types a sentence into nothing, and their
own sentence opens and closes the menu they had just finished with, three times, dimming and
un-dimming the page under their hands.

**Why A.** The reason is mandatory — it is the entire justification for asking rather than sending —
and the ordinary keyboard path to supplying it does not work at all. Nothing is written wrongly
(leg `C3` measured zero task writes across the whole sequence), but the operator cannot complete a
first-class action by the means the screen invites, and the failure is silent: the field stays empty
and the confirm button stays disabled with no explanation.

**The mouse path is fine and the control is fine.** Leg `C2d` clicks into the input and types the
same nineteen characters: the field holds `'the staging API key'` and `document.activeElement` is
the `INPUT`. This is a focus defect, not a broken control — worth stating precisely, because it
narrows the fix to *when* focus is taken.

**Reproduction:**

```
py -3.11 scripts/drive/t_d1_0910_escape_across_the_dialogs.py     # leg C2c
py -3.11 scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py # leg P5
```

**One measurement that is worth keeping even though it exonerates the code.** Legs `P1`-`P4` were
built on the hypothesis that the inert page *persisted* — `body: none` with an orphaned popper was
read once, 1.4 s after the selection, and looked like a leak. Sampled on a clock at
0/0.5/1/2/5/10 s, across an ordinary move, the blocked move, Escape-with-the-menu-open, and the
whole eight-gesture sequence replayed, `body` recovers at **+0 ms every time**. Radix cleans up
correctly. The single sample was reading the menu that the operator's own spaces had just re-opened.
A severity filed on that first reading would have been filed against the wrong component.

---

## F310 (B) — one Escape dismisses two things: the ticket closes out from under the control the operator was actually cancelling

**Status:** fixed — **two commits again, and again neither is sufficient.** `9ed1d6d` gives the hook
the arbitration it never had: `useDialogFocus`'s Escape branch returns without closing when
`event.defaultPrevented` is already set. That flag is enough — and not merely present — because the
listener is on `document` in the **bubble** phase, structurally the last handler in the propagation
path, so every React handler and every capture-phase listener has already run by the time it is
read. `beb38d6` gives the nested owner something to say: `TaskDetailDrawer.tsx`'s reason input now
calls `preventDefault()` before `setBlockingReason(null)`, so the line written for *"Escape cancels
the reason"* — the one the table below records as never once observable — is observable.

**The two gestures needed different amounts of that.** After `9ed1d6d` alone the escape harness went
**30/6 → 31/5**: the menu-open gesture flipped, because Radix answers Escape with its own
`preventDefault()` and so had always been saying *"handled"* to a hook that was not listening. The
reason-input gesture could not flip there and did not — its handler had nothing to say until
`beb38d6`. Filed 2026-09-10 (day window, `D-1`); driven green 2026-09-11 (night window), both
gestures, against served bundle `index-7rpxplrH.js`.

Same hook as [`F307`], different branch — `F307` is the Tab branch, this is the Escape branch, and
the Tab branch was deliberately left standing (see the note in `F307`).

**`useDialogFocus` binds Escape on `document`** (`hub/ui/src/hooks/useDialogFocus.ts:23-27`), calls
`onClose()` and returns. It does not ask whether something nearer the keystroke has already handled
it. React 18 delegates `onKeyDown` at the root container, which is a *descendant* of `document`, so
a nested handler and the hook both fire on one keystroke unless someone stops propagation, and
nobody does. `TaskDetailDrawer` is the only call site that mounts controls owning Escape themselves,
and it does so twice.

**Both were driven.**

| gesture | what the nested owner does | what the hook also does | leg |
|---|---|---|---|
| Escape with the status menu open | Radix closes the menu | closes **the ticket** | `C2` |
| Escape in the blocking-reason input | `:413-414` cancels the reason | closes **the ticket** | `C3` |

```
C2   menu closed: True   ticket survived: False
C3   reason cancelled: True   drawer closed too: True
```

The second is the sharper one. `TaskDetailDrawer.tsx:413-414` is
`onKeyDown={(e) => { if (e.key === 'Escape') setBlockingReason(null) }}` — a line written for no
other purpose than *"Escape cancels the reason"*. It does cancel it, and it has never once been
observable, because the panel containing it is unmounted by the same keystroke.

**Why B and not A.** Nothing is written: leg `C3` counted zero `PATCH`/`PUT` on `/tasks/` across the
whole sequence. What is lost is the operator's place and any reason they had managed to get into the
field, and the recovery is to re-open the ticket and start again. It is also, per `F309`, a field
they probably could not have typed into anyway — the two findings compound and should be fixed
together.

**Not a `RowMenu` leak.** Escape-with-the-menu-open was suspected of leaving the page inert as well;
`t_d1_0910_rowmenu_leaves_the_page_inert.py` leg `P3` sampled `pointer-events` at 0/0.5/1/2/5/10 s
after it and `body` recovers at **+0 ms**. The only defect in that gesture is that the ticket closes.

**Reproduction:** `py -3.11 scripts/drive/t_d1_0910_escape_across_the_dialogs.py`, legs `C2` and
`C3`. Both were asserted in the direction of the *correct* behaviour, ~~so the file exits non-zero
today and will go green when this is fixed~~ — **and that is what happened**: the file exited
non-zero on 2026-09-10 and exits 0 on 2026-09-11, 48 passed / 0 failed. It stays as a regression
check, not as a reproduction.

**Shape of the fix, taken.** ~~Unproposed.~~ Two shapes were offered here — the hook ignores Escape
when the active element is inside a control that has declared it owns the key, or the two nested
handlers call `stopPropagation()`. **The first was chosen**, and the round discipline changed its
signal on the way through: not *"is the active element inside such a control"*, which the hook would
have to compute, but *"has the event's default already been prevented"*, which the control itself
asserts. That inverts who knows the answer — the nested owner does, and it is the only party that
can — and it costs the hook one condition instead of a DOM containment test at every call site. The
second shape was rejected for the reason stated here: it leaves the next nested control to
rediscover the trap.

---

## F311 (C, bookkeeping) — `F307`'s table of affected dialogs is missing the call site where the hook actually misbehaves

**Status:** fixed 2026-09-22 (bookkeeping, see the foot). Was: open — filed 2026-09-10 (day window, `D-1`).

`F307` says *"Six components use the hook"* and then tabulates **five**:
`AgentCreateDialog`, `DeleteProjectDialog`, `ProjectManagerModal`, `ArchiveConfirmDialog`,
`ClearInstructionsDialog`. `grep -rn useDialogFocus hub/ui/src --include=*.tsx` returns six call
sites; the missing one is `TaskDetailDrawer.tsx:167`.

It is the one that matters. The other five are confirm-shaped panels whose entire content is a
question and some buttons; `TaskDetailDrawer` is a working surface with a status menu, a select, an
input and its own Escape handler — and it is where `F309` and `F310` both live. `F307`'s conclusion
(*"it is exactly the confirm-only dialogs … that fail to hold focus"*) was drawn from a population
that excluded the counter-example.

Not a defect in the product. Filed because `F307`'s table is what a fix proposal will enumerate from,
and enumerating five call sites for a six-call-site hook is how the sixth gets a fix that was never
checked against it.

**Fixed 2026-09-22, bookkeeping only.** `F307`'s table now has a sixth row for `TaskDetailDrawer` (`:183` today, `useDialogFocus(open, panelRef, onClose)`). The drawer moves focus into its panel only when the blocking-reason input appears (`:180`), not on open, so by `F307`'s own reading it is affected. That row is a reading, not a measurement. `grep -rn 'useDialogFocus(' hub/ui/src --include=*.tsx` still gives exactly six call sites. `F307` itself stays open.

---

## F312 (A) — the default posture forbids every network request a shell command can make, and calls it a filesystem escape

**Status:** fixed `612b9c9` by `a-url-is-not-a-path` (tasks §2: rule 1's network rule and D5's
network text), driven `f492261` (tasks §6.2, ask 3; night 2026-09-12, Windows, Haiku, default
posture). It is fixed by giving the refusal its true reason, not by permitting egress. Measured
on `run-f729c2de5139`, whose tool input was `curl -s https://example.com/`: *"Ask 3 was answered
`Denied: 'https://example.com/' is a network address. Under this posture a shell command may name
only this run's own Hub ($HUB_URL); if the task needs another address, ask the operator with
ask_user.`"* The `permission_denied` row `evt-12f9a4705b4a` carries the same reason, with
`tool_name='Bash'`. Pre-fix (§6.1, `run-bb7c55057449`), the same ask was
refused as `'s://example.com/' is outside your workspace`. The one widening, N3
(`curl -s example.com/x`, now allowed), is the operator's open item in tasks §7.3.

Filed 2026-09-10 by a RESUME session, **measured**, not inferred. Found while
reading F299/F300/F301 together for an operator verdict; it is the general form of F300's mechanism
and is deliberately **not** folded into it (see *"Why this is not F300"* below).

**The claim.** On `workspace` — `DEFAULT_CLAUDE_PERMISSION_MODE` (`hub/hub/runner_commands.py:63`),
the posture this repository chose as its default and the one every ordinary run gets — a `claude`
run cannot make **any** network request from a shell command. Not `curl`, not `pip install` from a
URL, not `gh api`, not fetching a schema. And the reason it is given names the filesystem.

> **Corrected 2026-09-13** (night window, `a-url-is-not-a-path` §9.1). *"Cannot make **any**
> network request from a shell command"* was never true.
> - `curl -s example.com`, which has no `/`, gives the regex nothing to match, and it was always
>   allowed (`design.md` D2, row N4). So were `python -c` requests (this finding's own last row).
> - On POSIX, every scheme URL in this finding's table was **allowed**. The `s://…` candidate is
>   relative there, and it resolves inside the workspace (**F331**, measured under WSL). The
>   Docker deployment and CI are Linux.
>
> So the claim held on Windows only, and only for an address written with a `/` or a scheme.
> What stands is the defect this finding names: a refusal given for a false, filesystem reason.

**The mechanism is one regex doing a job it was never given.** `_ABSOLUTE_PATH_RE`
(`hub/hub/mcp_server.py:936`) reads absolute-looking paths out of a shell command's text so `_decide`
can check them against `AW_WORKSPACE_DIR`:

```python
_ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'|;&><)]*")
```

A URL is absolute-looking, and the regex has no concept of a scheme. Measured against `_decide`
directly, with `AW_WORKSPACE_DIR` set to a real directory:

| command | `_decide` | reason returned |
|---|---|---|
| `curl -s -X POST http://127.0.0.1:9/api/v1/agent-actions/tasks` | **deny** | `'p://127.0.0.1:9/api/v1/agent-actions/tasks' is outside your workspace` |
| `curl -s -X POST "$HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer $AW_RUN_TOKEN"` | **deny** | `'/api/v1/agent-actions/tasks' is outside your workspace` |
| `curl.exe -s -X POST "$env:HUB_URL/api/v1/..." -H "..."` | **deny** | `'/api/v1/agent-actions/tasks' is outside your workspace` |
| `python -c "import os,urllib.request; ..."` | **allow** | `inside your workspace` |

**Read the first row's reason.** The candidate is `p://127.0.0.1:9/...` — the regex's
`[A-Za-z]:[\\/]` arm matched the `p:` of `http:` as a Windows drive letter and swallowed the rest.
`os.path.realpath` then resolved it against a `p:` drive, `commonpath` raised `ValueError` for
"different drives", and the run was told its request was outside its workspace. **The message names
a containment boundary that was never consulted about network access, because the boundary has no
term for network access.**

**The last row is the whole shape of it.** `python -c "import os,urllib.request; ..."` makes the
identical request to the identical address and is **allowed**, because it puts no absolute path in
the command text. So the posture does not forbid egress — it forbids *writing a URL down where the
regex can see it*. Two commands with the same effect get opposite answers on a syntactic accident.
Whatever containment this is, it is not the one the comment above the constant describes.

**This is not a theory about severity, it is the posture's own stated purpose.**
`runner_commands.py:62-65` argues `workspace` is the right default because *"each request is checked
against the run's own workspace by `_decide`"* and it *"permits the execution an agent needs to
produce evidence about its own work."* An agent that cannot fetch anything cannot produce evidence
about work that involves a network — and it is not told that; it is told its machine's filesystem
refused.

### Why this is not F300, and must not be closed by F300's fix

F300 is this mechanism seen at one address: the run's own Hub URL. Its verdict
(`spec-queue/DECISIONS.md`, 2026-09-09, narrowed 2026-09-10) is explicit that the fix **must not**
make the approver permissive about URLs in general — *"The recognised case is the run's own Hub base
URL… Anything broader is a second decision and is not covered by this verdict."*

So F300's fix **cannot** close this finding, by that verdict's own construction: after it ships,
`curl https://example.com/x` is still denied, still for a filesystem reason. Folding the two would
produce a change that closes a finding it does not fix — which is the failure the 2026-09-10 archive
commit `fc9001a` already recorded in its own subject (*"it closes none of the findings it names"*).

### What this does NOT claim

- **Not that the posture should permit egress.** It may well be right to forbid it — a contained run
  reaching the network is a real decision and it belongs to the operator, as
  `agent-capability-plane` reserves it. The defect is that the posture forbids egress **by accident,
  through a path regex**, and reports it in a vocabulary that sends the model and the operator
  looking at the filesystem. A posture entitled to say no is not entitled to say no for a false
  reason.
- **Not that `_decide` is wrong about paths.** It is doing its documented job. Its docstring and the
  comment at the `command` branch both say it reads *paths* out of shell text and that it is *"a
  boundary, not a sandbox"*. Nothing there claims to govern network access, in either direction.
- **Not measured end to end through a live Hub.** The `_decide` column above is the function driven
  directly with a real `AW_WORKSPACE_DIR`; F300's live drive on `:8010` is the end-to-end evidence
  for the same mechanism at one address, and this finding generalises the mechanism, not the drive.

**Reproduce** — no Hub, no network, no credential:

```bash
cd hub && py -3.11 -c "
import os, importlib.util
os.environ['AW_WORKSPACE_DIR'] = os.getcwd()
spec = importlib.util.spec_from_file_location('m', 'hub/mcp_server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for c in ['curl -s http://127.0.0.1:9/a', 'curl -s https://example.com/x', 'python -c \"import urllib.request\"']:
    print(c, '->', m._decide('Bash', {'command': c}))
"
```

**Related:** F300 (the same mechanism at the Hub's own address), F301 (the other access path, where
the block is the absent answerer rather than this regex), F299 (the blocked-harness case). The three
were read together on 2026-09-10 and their verdicts are in `spec-queue/DECISIONS.md`,
*"The access path, re-decided 2026-09-10"*. **This finding was the part of that reading that no
verdict covered**, and the operator's instruction on it was to file it rather than fold it.

---

## F313 (C, harness) — the table recording a wrong verdict was read as making it, and six of the ledger's eight conflicts were false

**Status:** fixed dee508c (2026-09-10) — the rule and its test are in that commit

Found 2026-09-10 (day window, D-6) by reading the **evidence behind** every `CONFLICT` rather than
the count of them. `scripts/classify_findings.py` reported eight. Seven were false, and six of the
seven had one cause.

**The mechanism.** The script's cross-section arm scans every line *outside* a finding's own
section for that finding's number standing near a verdict word, and treats a hit as a lead that the
finding was resolved somewhere else. A line naming *several* findings satisfies that test for every
number on it. So a line of bookkeeping **about** the ledger was read as a verdict **in** it.

**The sharpest instance is self-inflicted.** Blind spot 5 (2026-09-08) ended by writing a
corrections table into this file, recording the seven verdicts it had just found were wrong. One row:

| | Was | Now | It had been reading |
|---|---|---|---|
| **F65** | RESOLVED | **OPEN** | F67's resolution |

The row records a verdict that had been **wrong**. The scanner read the row as making it: the
"Was" column is a claim being withdrawn, and it was counted as a claim being made. Four sections
were flagged as conflicting by the one table in this file that says they are open, and two more by
a list of heading formats and a sentence about how one verdict word had been used. The instrument's
own confession was its next false positive.

**What moved, measured over 312 sections:**

| | before | after |
|---|---|---|
| `CONFLICT` | 8 | **2** |
| `OPEN` | 150 | **156** |
| `RESOLVED` | 148 | 148 |
| `RESOLVED_ELSEWHERE` | 6 | **1** |
| `UNCLASSIFIED` | 0 | **5** |

Eleven verdicts move and **not one becomes resolved** — 148 is unchanged. Six go from conflicting
to open; five stop being leads and become unclassified, which in this script means *nobody has read
this*, the conservative reading.

**The corroboration is that the ledger already knew the answers.** For five of the eleven, the
"Now" column of that same corrections table states the verdict this fix produces — open for three
of them, unclassified for two. The instrument now agrees with the record of its own correction.

**Reproduce** — no Hub, no network:

```bash
py -3.11 -c "
import importlib.util, subprocess, collections
def mod(src, name):
    p = '.aw-tmp-' + name + '.py'
    open(p, 'w', encoding='utf-8').write(src)
    s = importlib.util.spec_from_file_location(name, p); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m
old = mod(subprocess.run(['git','show','6351c09:scripts/classify_findings.py'],
                         capture_output=True, text=True, encoding='utf-8').stdout, 'old')
new = mod(open('scripts/classify_findings.py', encoding='utf-8').read(), 'new')
lines = old.load('scripts/drive/FINDINGS.md')
A = {r['num']: r['verdict'] for r in old.classify(lines)}
B = {r['num']: r['verdict'] for r in new.classify(lines)}
print(sorted((n, A[n], B[n]) for n in A if A[n] != B[n]))
print(collections.Counter(A.values()), collections.Counter(B.values()))
"
```

**Not** a defect in the corrections table, which is accurate history and stays as written. The
defect is an instrument that cannot tell a sentence *making* a claim from one *reporting* that the
claim was withdrawn — which is blind spot 3 again, at a granularity `dequote()` cannot see, because
a table cell is neither a quotation nor a strike-through.

**The two conflicts that survive are the two that should.** Both hang on a line naming one finding:
the summary row at the top of this file, and a sentence contrasting a finding with an unrelated fix.
Those are for a human, and this fix leaves them flagged.

**Writing this entry reproduced the defect once, which is the strongest evidence in it.** The first
draft of the paragraph four above said *"a record that F65 was wrongly read as resolved"* — one
finding number, one verdict word, one line — and re-running the classifier showed F65 back at
`CONFLICT`, this time on the sentence *describing* the fix. The multi-number rule did not fire
because the sentence names only one. So the rule is a floor and not a cure: **prose about a single
finding's past verdict is still indistinguishable from prose about its present one**, and the only
defence is the one used here — re-run the instrument after appending to the file it reads, and
require that no existing verdict moves. That check is cheap, it caught this in one run, and it is
the check no previous entry in this ledger has performed.

**Related:** blind spot 3 (quotation is not assertion) and blind spot 5 (the table this defect ate).
The generalisation worth carrying: **a ledger that records its own corrections becomes an input to
the instrument that made them**, so every self-describing line is a line the instrument must be
tested against. Filed and fixed in the same window; `tests/test_classify_findings.py` gained the
guard and a narrowness pin, both mutation-checked in both directions.

---

## F314 (B) — `test_flow_holds_the_loop_requirements.py` fails about one run in eight under random ordering, on an unmodified tree

**Status:** fixed 416f6e8 (closed 2026-09-22 by measurement: 0 failures in 40 random-order runs; see the foot) — filed 2026-09-10, **measured, on an unmodified tree**, and separate from F292.
Found while establishing whether F292's `BEGIN IMMEDIATE` mitigation caused a regression; it did
not, and this is what the control measurement found instead.

**What was measured.** A five-file flow subset — `test_flow_holds_the_loop_requirements.py`,
`test_flow_fires_a_review_turn.py`, `test_flow_chain_end_to_end.py`, `test_flow_width.py`,
`test_a_review_nobody_is_doing.py`, 63 tests — run repeatedly under `pytest-randomly`'s default
random ordering, on this machine, Python 3.11.

| tree | runs | failures |
|---|---|---|
| **unmodified (no `BEGIN IMMEDIATE`)** | 12 | **1** |
| with F292's mitigation | 8 | **1** |

**~1 in 8, and the same rate on both trees** — which is the finding twice over: the flakiness is
pre-existing, and F292's fix neither causes nor cures it. Two different tests failed across the two
observed failures, both in the same file:

- `test_one_turn_finishing_answers_for_itself_and_not_for_its_siblings`
- `test_a_wide_flows_state_is_still_one_call`

**Both pass when run alone**, deterministically. So this is order dependence, not a broken
assertion.

**Why it matters more than a 1-in-8 flake usually would.** The full Hub suite's CI failures have
been attributed to F292 essentially wholesale — *"every red CI run is F292 — 11 of 11"* was this
ledger's standing claim until 2026-09-10, when a deterministic starlette resolution defect retired
it. **This is a second non-F292 source of red**, in the same file family F292's occurrences cluster
in (`test_flow_fires_a_review_turn.py` is occurrence #15's erroring file), which is precisely the
neighbourhood where a misattribution is most likely. **Any future F292 rate measurement must
classify a flow-file failure from its own log before counting it**, or it will fold this in.

**Not diagnosed.** No hypothesis is offered here and none should be inferred from the file's name.
What is established is the rate, the two affected tests, the order dependence, and the independence
from F292's mitigation. The obvious next step is to find the seed and bisect the ordering, which is
bounded work and was not done because it is not what this session was doing.

**Reproduce** (expect roughly one failure in eight):

```bash
for i in $(seq 1 8); do
  py -3.11 -m pytest hub/tests/test_flow_holds_the_loop_requirements.py \
    hub/tests/test_flow_fires_a_review_turn.py hub/tests/test_flow_chain_end_to_end.py \
    hub/tests/test_flow_width.py hub/tests/test_a_review_nobody_is_doing.py -q \
    | grep -E '^[0-9]+ (passed|failed)'
done
```

**It has a CI signature, measured 2026-09-11** (F292's day-`D-1` rate measurement, which had to
classify this out to count that one). Two of the 41 pre-mitigation `ci.yml` runs on
`autonomous/2026-09-08-daily` are this finding — `fc9001a` (run `34419532531`) and `e6da0a0` (run
`34414764597`) — **2/41 = 4.9%**, against the ~12.5% measured locally. Both are
`test_a_wide_flows_state_is_still_one_call`, one of the two tests named above, and **both present as
`RuntimeError: <asyncio.locks.Lock object ...> is bound to a different event loop`, not as a failed
assertion** — so this is identifiable in a CI log at a glance, and it is not confined to this
machine. Two events is too few to call the CI/local difference real.

**Related:** F292 (the schema-reset lock, same file family, different mechanism), F279 (a different
pair of order-dependent failures, also undiagnosed — *"the two 'a stopped run' tests fail about half
the time, on an unmodified tree"*). **F279 and this are the same species and neither has been
bisected**; whoever takes one should take both.

**Closed 2026-09-22 (interactive session), by measurement.** F314's CI signature, `RuntimeError: <asyncio.locks.Lock …> is bound to a different event loop`, is exactly F383 symptom A, fixed on 2026-09-18 in `416f6e8` (conftest's `_module_level_async_primitives_are_per_test` clears `turn_scheduler._agent_locks` around every test; its docstring even names `test_one_turn_finishing_answers_for_itself_and_not_for_its_siblings`). Nothing had linked the two. Re-measured on `279a126` with this entry's own five-file reproduction (63 tests) under `pytest-randomly` 5.0.0: **0 failures in 40 runs**. 16 runs did not record their seeds (`-q` hid them); the other 24 did (3104368094, 218346123, 860016805, 1346691169, 656298806, 1549053170, 146412733, 3425891771, 274946881, 1447479909, 1920463807, 2108882614, 39772209, 1324716365, 2473063116, 449141113, 2445017193, 1382697312, 2645146391, 2086654349, 3778274435, 2690323790, 2693405714, 1204260887). At the filed ~1-in-8 rate, 40 clean runs happen by chance with p ≈ 0.005. **Environment note:** `pytest-randomly` is no longer installed for `py -3.11`, and CI has never used it. It was installed with `pip --target` into a scratch directory and put on `PYTHONPATH` for these runs only, so no other run on this machine had its order randomised. **F279** ("same species") was not re-measured.

---

## F315 (C) — the button that blocks a ticket says nothing for the two seconds it takes, and a second press writes the move again

**Status:** fixed (this commit) [UI-1, 2026-09-23] — Mark waiting says it is working and refuses a second press until the write and refetch finish; see FIXED at the end of this entry. Was: open — filed 2026-09-11, measured on both the keyboard and the mouse path.
**Pre-existing and outside `2026-09-10-the-control-that-asks-holds-the-keyboard`**, which is why it
is filed rather than fixed: that change moves the keyboard into this panel and does not touch the
mutation behind it. Found by §7.6's drive, when a fixed 1.5s wait turned out not to be long enough
for an assertion that had nothing to do with focus.

**What was measured.** Two throwaway probes against the trial Hub on `:8013` serving bundle
`index-7rpxplrH.js`, a local SQLite database, one ticket, no load. Type `the staging API key` into
the blocking-reason panel and press **Mark waiting** (`TaskDetailDrawer.tsx:450-474`), then sample
the drawer on a clock:

| after the press | reason panel | drawer's Status field |
|---|---|---|
| +0ms | still mounted | In Progress |
| +300ms | still mounted | In Progress |
| +700ms | still mounted | In Progress |
| +1500ms | still mounted | In Progress |
| **+3000ms** | gone | **Blocked** |

Between **1.5s and 3s on an idle local Hub, nothing on screen changes at all** — and the same timing
on the keyboard path (arrow, Enter, type, Tab, Enter), so this is the round trip and the refetch
behind it, not an artefact of how the button was pressed. Note the panel is still mounted at +400ms
**after the PATCH has already come back 200**, so the wait is the invalidation, not the write.

**What a second press does.** During that window the button is still enabled and still reads
`Mark waiting`: `disabled={!blockingReason.trim()}` is the only condition on it and
`updateTask.isPending` is not consulted. A second press at +400ms is accepted, and the network log
shows **two identical `PATCH … {"status":"blocked","blocked_reason":"the staging API key"}`
requests**. The Hub answers the second **200**, not a refusal — `blocked → blocked` is not rejected
the way an illegal move would be — so `task-status-refusal-<id>` stays empty and the operator sees
nothing wrong. *(An earlier draft of this entry predicted a refusal on the second press. It was an
inference, it was measured, and it was wrong: the cost is a duplicate write, not a spurious error.)*

**So the severity is what it is.** No data is corrupted and no operator is misled — the ticket ends
blocked with the right reason either way. What is missing is any acknowledgement that a press was
received, on the one control in this panel whose whole job is to answer a question the product
asked.

**Not fixed here, deliberately.** The shape is obvious — consult the mutation's pending state for
the label and the `disabled` — but every other status move in the same menu has the same gap, and
fixing it for this one button would leave the inconsistency it is an instance of. It belongs with
whatever change owns optimistic feedback for task mutations.

**Reproduce.** Open a ticket in `in_progress`, choose *Move to blocked*, type any reason, press
*Mark waiting*, and watch. Or read the timing off `P6` in
`scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py`, which prints
`the reason panel goes at: <ms>` because a fixed sleep there was a guess.

**Related:** `F309` (the focus defect in the same panel, fixed by the change whose drive found
this), `F310`.

**FIXED 2026-09-23 (interactive session, UI-1).** The confirm button is disabled while `updateTask.isPending` (it used to consult only whether a reason was typed), carries `aria-busy`, and reads `Marking waiting…`. `useUpdateTask`'s `onSuccess` returns the invalidation promise, so `isPending` holds through the refetch that was the measured 1.5-3s of silence, not only through the PATCH. Test: `taskApprovalReportAndPending.test.tsx` (F315 case).

**Review follow-up 2026-09-23 (adversarial Opus review of UI-1).** Precision: `useUpdateTask`'s `onSuccess` already returned the invalidation promise before this round, and the change here is the `disabled`/`aria-busy`/label on the button, which relies on it.

---

## F316 (A) — the reviewer resolved after a *silent* review excludes only the completer, so on operator-completed work it can pick the author

**Status:** fixed `4929ea0` (tests `40bd429`) by `an-agent-that-recorded-the-evidence-is-the-author`
**task 2.4**, which gives `run_divergence._answer_failed_review` the same two-branch derivation as the
other call sites: `completion_attribution`, then `agents_that_may_have_authored` where no agent
completed the work. Task 2.4a adds the `excluded_because='has worked on this task'` reason on the
operator-completed branch. The change was archived 2026-09-12 (night window, `n8-close`).
Filed 2026-09-11 (day window, iteration 4, spec-loop R2 on `F306`).
**REPRODUCED 2026-09-11** (iteration 5, spec-loop R3) at unit level against the tree at `8d227de`;
it was filed as derived-from-the-code and the reachability argument is no longer unverified.

**What proves it, and what does not.** The unit legs are 4.10 and 4.10a in
`hub/tests/test_the_evidence_names_the_author.py`. Each **failed** under its own mutation:
removing 2.4, and dropping the `excluded_because` reason (night log 2026-09-11, iteration 4). With
2.4 in place, the silent review is `surfaced`, the assignee stays on the silent reviewer, and
nothing is queued. The restaff path itself was **not** driven on the fixed tree. On the fixed
tree the flow's first staffing already excludes the author, so a live restaff onto the author needs
a firing that picks the author, and after the fix none does. What was driven on the fixed tree is
the operator-facing half: a firing with no eligible reviewer says *"has worked on this task"* and
does not say *"completed"* (§5.3, 409 on `proj-99af62baca17`). The pre-fix drive **did** exercise
the restaff path: attempt 1's silent author review was restaffed onto the other agent
(`div-c524b3378859`). But there the silent reviewer **was** the author, so it was barred for having
said nothing, and this finding's failure could not show. Nobody has driven a live Hub through a
non-author going silent on an author's operator-completed task. The unit legs cover that route.

**The reproduction.** An operator-completed task (`in_progress` and `completed` both taken by
`operator()`), agent `aa-author` associated with it by a **bound run only** — named on no
transition, never its assignee — and reviewer `critic` staffed and ending its turn with no verdict.
`evaluate_run_end` recorded the divergence `outcome='restaffed'`, moved `task.assignee` from
`critic` to `aa-author`, and queued `aa-author` a `divergence` entry carrying the review checkout:
**the agent that worked the task made the reviewer of its own work.** No evidence row was involved,
so this is reachable today, independently of `F306`. The same fixture against a prototype of
`F306`'s change records `outcome='surfaced'`, leaves the assignee on `critic` and queues nothing —
which is the evidence that `an-agent-that-recorded-the-evidence-is-the-author` task 2.4 closes it.

**Where.** `run_divergence._answer_failed_review` (`hub/hub/run_divergence.py:374-421`) is the third
place in the Hub that resolves a reviewer, and the only one `F142`'s widening never reached. It
builds the exclusion itself and hands it to the shared ladder:

```python
author = await agent_that_completed(session, task.id)
barred = await _reviewers_that_gave_no_verdict(session, task)
barred.add(run.agent)
if author:
    barred.add(author)

choice = await resolve_reviewer(session, task, project_id=run.project_id, exclude=barred)
```

`agent_that_completed` returns `None` for an operator completion, so `if author:` is false and
`barred` holds **only the agents that reviewed and said nothing**. The agent that *produced* the
work is not among them.

**The other two call sites do not compose it this way, and one of them says so.**
`task_is_claimable_by` (`scheduler.py:615-625`) and the review-staffing arm (`scheduler.py:1567-1574`)
both branch on `completion_attribution` and fall back to `agents_that_may_have_authored` where no
agent completed the work. `task_is_claimable_by`'s own comment is explicit about why that matters:

> **The same set the review arm excludes, called rather than recomposed** — two compositions of the
> same three terms are free to drift, and the two walks disagreeing about one task is the failure
> this function's whole docstring is about.

There are three compositions, not two. This is the third, and it is the one that drifted.

**The route, stated exactly.** An operator-completed task is staffed for review by the flow, which
correctly excludes every agent any record associates with the task. That reviewer's turn ends
without recording a verdict. `_answer_failed_review` then resolves a replacement, barring only the
silent reviewer — so an agent that worked the task, is named on its transitions or by a bound run,
and was excluded from the *first* resolution for exactly that reason, is eligible for the second.
It is then reassigned the task and dispatched. `_guard_author_is_not_reviewer` permits its approval,
because no agent is recorded as completing the work. Self-approval, silently, on a path whose first
step did the exclusion correctly.

**Not the same finding as `F306`, and not fixed by fixing it.** `F306` is a missing *source* in the
union (`requirement_evidence.actor`); this is a call site that does not use the union at all. Adding
a fourth source to `agents_that_may_have_authored` changes nothing here, because nothing here calls
it. `F306`'s fix makes this worse rather than better: once the guard refuses an evidence author, a
replacement reviewer resolved from `barred` can be an agent whose verdict is then refused on
arrival — which is precisely what `agent-flows` already forbids the Hub to resolve:

> **The Hub SHALL NOT resolve, as a task's reviewer, an agent that could not record a verdict on
> it.** … the resolution SHALL exclude it rather than discover the refusal afterwards.
> (`openspec/specs/agent-flows/spec.md:221-224`)

**Its own docstring states the invariant this breaks.** Four lines above the code:

> D6's problem — an escalation target that authored the work is a guaranteed 403 from
> `agent_that_completed` — cannot arise here at all, because the resolver already excludes the
> author by construction.

The resolver excludes what its caller passes. On the operator-completed arm this caller passes
nothing about the author, so the sentence is true only where an agent is *recorded* as completing
the task — the same blind spot `F142` was filed for and `F306` found again one source over. Three
findings, one shape: **a rule keyed on the recorded completer is silent wherever the operator
finished the work.**

**Shape of a fix, not decided here.** The obvious one is to give this call site the same two-branch
derivation the other two use — `completion_attribution`, then `agents_that_may_have_authored` where
no agent completed — which would also pick up `F306`'s fourth source for free, since it would then
be calling the union rather than recomposing it. The round writing `F306`'s proposal folded this in
on that argument (`openspec/changes/an-agent-that-recorded-the-evidence-is-the-author/`, R2). That
change shipped the obvious fix as task 2.4. The commit is on the Status line.

**Related:** `F306` (the same blind spot, one source over), `F142` (the widening that did not reach
this call site), `F167`.

---


## F317 (B) — the finding classifier reads a domain verb in a section's own title as a status verdict, and prints the open severity-A count one short

**Status:** fixed `cb7c86b` (day window, `D-6`, driven 2026-09-11 over this file) — filed earlier
the same day (day window, `D-5`), found while computing the open severity-A count for the review
page instead of copying the night's. Mutation-checked; the cause is proved and is one word. The
repair is the first of the three shapes below, narrowed further than that sketch: four positions
rather than three, each one taken from a heading that really is in this file. **It does not on its
own restore the count to six** — a second and independent defect, `F318 (B)`, holds the section at
`CONFLICT` instead. See the block at the end of this entry.

**The measurement.** `py -3.11 scripts/classify_findings.py` prints `severity A: OPEN=5` and names
five sections. `F316 (A)` was filed earlier the same day, carries an explicit open status marker on
the line below its own title, and is in none of them. Its record reads `verdict=RESOLVED` on
evidence the script labels "own heading", quoting the title itself.

**The cause.** `EXT_WORD` (line 101) matches seven resolution words case-insensitively — the five
upper-case ones this file uses to retire a section, plus the two lower-case participles:

> `EXT_WORD = re.compile(r"\b(RETIRED|RETRACTED|FIXED|SUPERSEDED|WITHDRAWN|closed|resolved)\b", re.I)`

The own-heading arm at lines 284–290 searches it against the first line of every range belonging to
the finding. `F316`'s title is "the reviewer resolved after a silent review excludes only the
completer" — and there the participle is the **domain verb for picking a reviewer**, the same word
`scheduler.resolve_reviewer` is named for. It is the subject of the defect, not a claim about the
defect's state. The verdict block at lines 307–314 then reads `if in_res: v = "RESOLVED"`
**unconditionally**, so an in-section marker outranks the section's own status line without even
producing the `CONFLICT` that blind spot 4 exists to put in front of a human.

**Mutation check.** Replacing that one participle with "chosen" in that one title, in memory, with
nothing else changed: the verdict moves to open on its own status-line evidence, and the severity-A
set comes back as six. Restoring the word restores five. Nothing else in the file moves.

**Blast radius, measured over the whole file.** Five sections take their verdict from the
own-heading arm. Four are true positives: two titles end in a literal status token (lines 12102 and
12207) and two are the continuation headings the arm was written for, which its own code comment
names. `F316` is the only false positive, and it is the only severity-A one.

**Why this is a B and not a C.** The number this arm corrupted is the number both scheduled windows
steer by. The night window's default queue is *open findings, severity A before B before C*, and the
day window's spec-loop order is drawn from the same list; a finding invisible to the census is
queued by neither. `F316` stayed safe today only because a hand-written paragraph names it four
lines above the census — which is exactly the hand-maintained list this instrument was built to
replace, and the reason its header insists the numbers be computed in the sentence that states them.

**Shape of a fix, not decided here, and two of the three shapes are worse than they look.**
Narrowing the heading arm's vocabulary to *structurally* status-shaped forms — a trailing token
after an em dash, a leading token, an "is …" predicate — keeps both true-positive families and drops
this one; the arm already justifies itself as structural evidence, so demanding structure is in
character. Routing to `CONFLICT` when a section carries both this evidence and an explicit status
line would surface it to a human rather than silently deciding, but it changes the verdict of every
self-narrating section and wants its own measurement first. Banning the word from titles is not a
fix at all: it turns the instrument's blind spot into a rule for the people it measures, which is
the failure `F313` is about.

**This entry is written around its own finding.** Every literal status token above sits inside a
quotation or a blockquote, because `dequote()` blanks those before matching and nothing else would
stop this section from classifying itself as done. The first draft did not: it printed the
alternation above as ordinary prose, and promptly took a done verdict from the first upper-case
token in it — found, reproduced and repaired inside ten minutes, inside the entry that describes the
defect.

**Related:** `F313`.

---

### `F317` repaired — what the drive produced, which is not quite what the entry predicted

The repair went in at `cb7c86b` as the first shape above: the own-heading arm now requires its token
to sit in a structurally status-shaped position rather than merely to occur anywhere in the title.
Four positions, each taken from a heading that really is in this file — a trailing declaration after
a dash or comma, a leading one straight after the reference, one inside the reference's own
parenthetical where severity lives, and a copula whose subject is the finding itself.

**Driven over this file, not merely tested.** The whole census was captured before and after, and
the requirement was exactly the movement this entry predicted and nothing else. What actually
happened, verbatim from the two runs:

> severity A: total  56   CONFLICT=1  OPEN=5  RESOLVED=50   *(before)*
> severity A: total  56   CONFLICT=2  OPEN=5  RESOLVED=49   *(after)*

The B, C, D and `?` lines are byte-identical across the two runs. All four true positives of the
own-heading arm survive and still take their verdict from it — the two titles ending in a status
token and the two continuation headings its code comment names. The one false positive is gone.

**The prediction was still wrong, and the gap is a second defect.** This entry expected the count to
come back as six. It did not: the section left a done verdict as designed and stopped at `CONFLICT`
rather than `OPEN`, because a second and independent arm is also wrong about it. That is `F318 (B)`,
filed rather than folded in — it has a different cause, a different fix, and a hazard that today's
green run structurally cannot see. The census reading of record is now the paragraph in the index,
which states the set and says which bucket the sixth is printed under.

**Two tests, both mutation-checked.** One asserts a prose verb in a heading is not a verdict; one
asserts a trailing status token still is, which is the guard against over-correction rather than
under. Reverting the narrowing kills the first and only the first; deleting the trailing-declaration
rule kills the second and only the second.

---

## F318 (B) — the cross-section arm strips quotation one line at a time, so a quotation that wraps is read as prose

**Status:** fixed `92c1481` (day window, `D-6`, driven 2026-09-12). The cross-section arm now
reads a dequote computed per paragraph, with blank lines and headings as the block boundaries,
the bound this entry proposed below. Replayed over this file as it stood at `cb7c86b`, the old
code reproduces the census below and the fix gives the predicted one, with every other severity
line unchanged. Two tests and four mutations, each mutation killed by its intended test. Filed
2026-09-11 (day window, `D-6`), found by driving `F317`'s repair over the
real ledger and requiring the exact movement that entry predicted. The movement did not arrive, and
the gap was the finding. Not argued: this is the difference between two captured census runs.

**The measurement.** After `cb7c86b` the severity-A census line reads
`total 56  CONFLICT=2  OPEN=5  RESOLVED=49`, against `CONFLICT=1  OPEN=5  RESOLVED=50` before it.
The B, C, D and `?` lines did not move at all. The section that moved was expected to land on an
open verdict on the strength of its own status line; it landed on `CONFLICT`, on one piece of
external evidence, and the script names the line the evidence sits on.

**The cause.** `dequote()` blanks blockquotes and quoted spans, and three of its four patterns carry
`re.S` — they are written to span lines. Every own-section arm honours that, calling it once over a
whole joined body. The cross-section arm does not. It calls it inside the per-line loop:

> `cln = dequote(ln)`

A quotation that wraps therefore reaches the vocabulary check with its two quote marks on different
lines, where nothing can pair them, and the continuation line is read as an ordinary sentence.

**The live instance is in this file, one entry above.** `F317`'s body quotes the title of the
finding it is about; the quotation wraps; and the second line of it names one finding number and
carries a lower-case participle. That is indistinguishable, to this arm, from a verdict.

**Why this is not simply `F313` again.** `F313` is about a line that genuinely is prose, where no
convention could have helped the author. This one is about a line the author *did* mark as
quotation, using the convention the script itself implements and honours everywhere else. The
evidence was correctly formatted and the reader's scope was wrong — which is the better kind of
defect to have, because it is fixable in the instrument rather than in the prose of everyone who
writes here.

**Measured shape of a fix, and why it was not taken at `D-6`.** Dequoting the whole document once
and indexing that result by line moves **exactly one verdict** in this ledger — the expected one —
giving `severity A: total 56  CONFLICT=1  OPEN=6  RESOLVED=49` with every other severity line
unchanged. That is the predicted census, out of a one-line change, and it was measured before this
entry was written. It was still not taken, for a reason that green run structurally cannot see: the
third quotation pattern pairs any two quote characters within 600 characters of each other, and at
document scope that pairing crosses section boundaries. Whether it swallows a real status
declaration depends on the quote parity of the whole file, which changes every time a finding is
appended — so a clean run today is weak evidence about tomorrow, and this instrument's entire
history is of changes that were clean on the day. A bounded window, or pairing that refuses to cross
a blank line, is the likelier shape. It wants its own round, which is why this is filed rather than
finished.

**Direction of the error is the safe one.** This defect suppresses nothing and invents evidence, so
it can only move a section toward a done verdict or toward `CONFLICT`, never away from one. It costs
reads rather than missed defects — except in the case that produced it, where it lands on `CONFLICT`
and the consumer reads only `OPEN`.

**Related:** `F313`, `F317`.

---

## F319 (A) — a review refused on the scheduler path leaves the refused reviewer holding the task

**Status:** fixed `6ebcd9f` by `a-refused-review-leaves-nothing-behind` (tasks §2: the scheduler
rolls back the refused dispatch's transaction before it records the refusal, then re-reads its
entries by id and `state == 'queued'`), driven `1b3d52c` (tasks §5.3; night 2026-09-13, Windows,
Haiku, Hub from this checkout at `fa07089`, project `proj-f85df4264704`). Measured, each leg's task
read back from the drive database: **B1** `task-18316bdb30b7` answered the same `409` as before,
and stayed *"`("completed", None)` with 2 transitions, before and after. `revr8f` has no run"*;
**D9** *"`revcr8f` was answered with the commit refusal, not 'already under review'"*; **B2**
`task-6077efcaeecd` *"`409`, `("completed", None)` with 2 transitions. `revbr8f` has no run"*;
**A** `task-bf0e7cd8ad2c` *"was `("completed", None)`, 2 transitions, after every pass"*, its entry
`entry-0e76e7492ed3` carrying the guard's sentence at attempts 1, 2 and 3, then `withdrawn`. The
pre-fix tree, driven the same night (§5.2, `r7q`, `proj-a9dad9b9fc33`), left B1
`task-a6c1743d81d3` at `("under_review", "revr7q")` with a new transition row, refused a second
reviewer with *"already under review by 'revr7q'"*, left B2 `task-4704b6fc04d7` at
`("under_review", "revbr7q")`, and left A `task-1799a95e0375` at `("completed", "authr7q")`. What
the fix leaves open is filed beside it: F326 (the checkout), F327 (a flow's staging, decided out of
scope in `DECISIONS.md` `F327-scope`), F328 (narrowed, not fixed), F334 (the guard's words), and
F335 (the escaped broadcast).

Raised from B to **A** 2026-09-12 (day window, D-1): both unverified legs were reached live through `POST /agent/trigger` on a correct tree, and the after-staging leg leaves a task `under_review`, held, with no turn. Filed 2026-09-12 (night window, iteration 4), measured at unit level on the tree at `40bd429`.

**Measured live, 2026-09-12 (day window, D-1).** Drive Hub on **8016**, from `hub/` with uvicorn
from source at `50bd12e`, a fresh profile `drive0912d`, fresh fixture project `proj-e594aacf615a`
(a git repository under `testbed/scratch/d0912d/fixture`), agents on `claude-haiku-4-5-20251001`.
No `.py` under `hub/hub` or `src` was newer than the process start. Harness
`scripts/drive/t_d1_0912_f319_reach.py`; every row below is read back from the drive database
(`tasks`, `task_transitions`, `runs`, `inbound_queue_entries`), not from a response.

| leg | how it is reached, operator-side only | operator is told | the task afterwards |
|---|---|---|---|
| **B1** after staging | operator evidence names a commit on a side branch; the task is walked to `completed`; the branch is deleted and `git gc --prune=now` removes the commit; a non-author is dispatched | `409` "commit … is not present in this repository, so there is nothing to check out for review" | `under_review`, assignee the refused reviewer, a `completed -> under_review` transition row (seq 3, `actor_kind` **operator**), no run |
| **B2** after staging | the reviewer's `.agentweave/reviews/<agent>` is a plain directory, not a registered worktree | `409` "could not prepare …'s review checkout: refusing existing path …" | the same: `under_review`, held by the refused reviewer, transition row seq 6, no run |
| **A** the entry guard, no drift | a review is queued for agent X on an operator-completed task **while X's own turn runs**; the route asks `review_dispatch_refusal` then, and X is not yet an author; X's turn then records evidence for that task (`awaiting`) | `200 queued`, `waiting_reason: "agent is already running"` | after X's turn ends the entry is retried and refused by the entry guard; the task reads `("completed", X)`, no transition, no second run |

So both bullets below that said **unverified** are now answered:

- `ReviewTurnRefused` **does** survive the route's check. The route asks `commit_for_task_review`,
  which reads the database; three of `prepare_review_turn`'s refusals read the *repository* — the
  commit is absent (`review_turn.py:212-218`), the project is not a git repository (`:201-205`), the
  checkout path is obstructed (`worktrees.py:599-604`) — and none of them is asked before
  `enter_selected_task` stages the task. `turn_scheduler.py:349` commits that staging. The operator
  reads a correct refusal; the board says a review is in progress.
- A public route **does** reach the entry guard on the scheduler path without the two drifting: the
  gap is time, not logic. `review_dispatch_refusal` is asked when the entry is queued, the entry
  guard when it is delivered, and an entry queued behind a running turn is delivered later.

**The stranded state blocks its own recovery.** Dispatching the same reviewer again answers the same
`409`, measured; by the code it passes the route's D9 check (the holder *is* that reviewer), is
staged again and committed again. Dispatching a **different** reviewer is
refused by D9: *"Task … is already under review by 'revb2'. Reassign the task if 'revcb2' should
take it over"* — a review that never started is now the reason no other review can.

**The transition is attributed to the operator.** Seq 3 and seq 6 read `actor_kind='operator'`,
`origin='actor'`: the append-only history says the operator moved the task into review, when what
happened is that a refused dispatch did.

**The last unverified bullet, answered:** the still-`queued` entry *is* retried on every scheduling
pass. Leg A's entry reached `delivery_attempts=3` within 30 s (the author's run ending, then two
passes triggered by another agent's run ending and a divergence), and was then abandoned
(`state='withdrawn'`, `abandoned_reason` "delivery failed 3 times (…); the Hub stopped retrying").
Each attempt takes the same staging-then-commit path (read from the code; the table state was the
same after the first attempt and after the third). Abandoning the entry does not release the task:
it still reads `("completed", X)`. And the pass that abandoned it left the entry queued behind
it undelivered, which is **F320**.

**What the operator sees** (served bundle on 8016, Chromium, `scripts/drive/t_d1_0912_f319_ui.py`,
08:32 UTC, ten minutes after the refusals). The Tasks board shows B1 and B2 in **Under Review** as
`Under Review · Medium · @revb2 · Idle` and `… · @revbb2 · Idle`, exactly the card an ordinary
review in progress gets, with no marker of any kind. Task A shows under **Completed** with
`@autha1`, the agent whose review of it was refused. The `409` the operator received is the only
record that no review happened, and it is gone once they look away. (The route's answer is seen
only by whoever made the request; the drive made it through the API, so what the UI's own dispatch
control renders for the `409` was not captured.)

**4.6 and 4.5 of the F306/F316 change, live, as a side effect.** Leg A is 4.6 driven: X's evidence
was `awaiting`, never accepted, and it still refused X the review. Leg C (a task whose only evidence
is operator-kind, reviewed by a fresh agent) is 4.5 driven: the review was staffed and a real Haiku
review run bound to the task ran (`run-1a4df5c4750d`).

**How it surfaced.** The night's mutation table for `an-agent-that-recorded-the-evidence-is-the-author`
removed the dispatch route's evidence refusal and ran the dispatch leg. `POST /agent/trigger` still
answered `403`, with the entry guard's sentence naming the evidence, and nothing was provisioned.
The leg failed on one assertion only — the task read back `("completed", "ev-author")`. A refusal
had written the refused reviewer into `assignee`.

**The mechanism.** `trigger_agent_directly` stages a review by calling `enter_selected_task`, which
writes `task.assignee = agent` *before* its transition (`agent_trigger.py:835-845`). When the entry
guard refuses that transition, `TriggerAgentError` propagates. The comment above it
(`agent_trigger.py:788-793`) says the staffing is pending state in the dispatch's transaction, so a
refusal abandons it. That holds only for a caller that discards the session. `turn_scheduler`
catches the error, writes its detail onto each entry's `waiting_reason`, and calls
`await db.commit()` on **the same session** (`turn_scheduler.py:349`) — committing the assignee
write alongside the reason.

**Measured on the unmodified tree** with a scratch test, run once and not kept: an operator-completed
task with one agent-authored evidence row, an operator queue entry for that author carrying
`review_task_id`, then `schedule_agent`. Result: `ScheduleResult.waiting_reason` is the entry
guard's sentence; the entry stays `queued` with that sentence as its `waiting_reason`;
`prepare_review_turn` was not called; the task reads back `("completed", "ev-author")` — a finished
task, held by the agent whose review of it was just refused.

**Reach — what is established and what is not.**

- Through `POST /agent/trigger` on the current tree: **not reached** for the refusals the route
  asks first. `review_dispatch_refusal` restates the entry guard, and the dispatch leg asserts the
  holder stays empty. It **is** reached the moment the two drift, and the operator then sees a
  correct-looking `403` while the task is left held — which is what the mutation was.
- The other producers of review entries (`run_divergence.py:266`, `:467`; `scheduler.py:2864`,
  `:3194`) pick their reviewer through the resolver or staff it before scheduling. None is shown to
  reach a refused `enter_selected_task`. **Unverified either way.**
- A refusal raised *after* `enter_selected_task` succeeds — `ReviewTurnRefused` from
  `prepare_review_turn` (`agent_trigger.py:855-858`) — would, on this path, commit the whole staging,
  the `under_review` transition included: a task in review, held, with no turn. **Unverified**: not
  driven, and whether any `ReviewTurnRefused` condition survives the route's `commit_for_task_review`
  check is not established. If it does, this is severity A.
- Whether the still-`queued` entry is retried on every scheduling pass is not measured.

**The test that looked like it covered this does not.**
`test_the_direct_dispatch_refuses_the_evidence_author_before_the_checkout` asserts the holder is
empty after `trigger_agent_directly` refuses — true only because that test's session closes without a
commit. It proves the refusal lands before provisioning, not that the product's path discards the
staging. Its docstring now says so.

**Shape of a repair, not proposed:** roll back before recording `waiting_reason`, or stage the review
inside a savepoint that a refusal releases. Either has to keep the reason durable, which is the
reason that commit exists (F97).

**R1 of `a-refused-review-leaves-nothing-behind` found two more reaches of the same mechanism
(2026-09-12).** Measured at unit level on `87dfbf4`, with one `schedule_agent` per leg, in
`testbed/scratch/r1f319/test_zz_r1f319_scratch.py`. **B0** is a project that is not a git
repository (`review_turn.py:201-205`). It leaves `('under_review', reviewer)`, one new
transition, and no run. **T** is a *transient* refusal raised after the staging: the Hub does not
yet know its own address (`agent_trigger.py:1146`). It leaves `('under_review', reviewer)`, one
new transition, and the entry still `queued` at 0 attempts. So a deferral commits the staging
too. In the prototype of that change's D1, the scheduler rolls back before it records the
refusal. With that in place, every leg (B0, B1, B2, A and T) leaves the task as it was, and the
entry keeps the refusal's sentence as its `waiting_reason`.

**R2 of that change measured the reach bullet above that said "unverified either way" for the
flow's own producers (2026-09-12).** A flow firing whose staffed review is refused on dispatch (B1,
B2) is left `under_review`, held by the refused reviewer, with no run: F319's end state through a
different door, and not reached by the rollback, because the firing committed its staging before
the dispatch began. Filed separately as **F327**, measured in
`testbed/scratch/r2f319/test_zz_r2f319_flow.py`.

---

## F320 (B) — the scheduling pass that abandons a refused head returns, and the entry queued behind it is never delivered

**Status:** fixed `997ff5d` by `a-refused-review-leaves-nothing-behind` (tasks §3: `schedule_agent`
loops while an attempt gave up on its head, bounded by the entries queued at the pass's start, and
counts each entry at most once per pass), driven `1b3d52c` (tasks §5.3, leg F; night 2026-09-13,
Windows, Haiku, Hub from this checkout at `fa07089`, project `proj-f85df4264704`). Measured: *"H
`entry-b087e9dc3dc9` was withdrawn by the 2nd `continue` at 02:54:04.493. M `entry-304f78c1af8a`
was queued at 0 before that pass and delivered into `run-54144cbb80c4` at 02:54:04.607, by the same
request (`started_conversation_id` = M's conversation)"*. The pre-fix tree, driven the same night
(§5.2, `r7q`), withdrew H `entry-66a52bdb22f2` on its 2nd `continue`, which answered
`started: false`, and left *"M `entry-f512a2aacfcd` `queued` at 0, no run"*, still so at 03:46.

Filed 2026-09-12 (day window, D-1), measured live on the drive Hub (8016, `50bd12e`, profile `drive0912d`, project `proj-e594aacf615a`).

**2026-09-13 (night r9-close).** The same `continue` that delivered M answered the operator
*"this conversation had nothing queued"* of the conversation whose input its pass had just given
up. That answer is the fix's interaction with `checkpoints.py`, filed as **F333 (B)**; F320's
delivery is right and F333's wording is not.

**How it surfaced.** Found while driving F319, and not what that drive was looking for. Leg C
dispatched a fresh reviewer (`revca1`) to an operator-completed task; the Haiku review turn ended
without a verdict, and the divergence response restaffed the review, as designed, to the one
eligible agent left: `autha1`, which at that moment had F319's stranded review entry at the head of
its queue. `run_divergence.py:458` wrote `task.assignee = 'autha1'`, `_queue_response` queued a
`divergence` entry for it with `review_task_id` set, and `:840` called `schedule_agent`.

**What the tables say** (`event_logs`, `inbound_queue_entries`, `tasks`, `runs`):

| time (UTC) | what happened |
|---|---|
| 08:21:37 | `autha1`'s own run ends; F319's entry (`entry-8354ef8d5d17`, older, another conversation) is tried: attempt 1, refused by the entry guard |
| 08:22:06.441 | divergence: task `task-103b7a6fbad7` reassigned to `autha1`, `entry-e22b0a4d1454` queued (`origin_type='divergence'`) |
| 08:22:06.447 | `run_diverged`, `outcome: restaffed`, `response_agent: autha1` |
| 08:22:06.503 | `run_completed` for `revca1` |
| 08:22:06.558 | `queue_entry_abandoned` for F319's entry, `attempts: 3` |
| after | `entry-e22b0a4d1454` stays `queued`, `delivery_attempts=0`, `waiting_reason=NULL`; the task stays `under_review`, assignee `autha1`, `assignee_status: idle`; no run for `autha1` |

**The mechanism.** `schedule_agent` builds its turn from the oldest eligible entry
(`turn_scheduler.py:272`) and selects only entries of that entry's conversation (`:293-303`). When
that head is refused non-transiently, the refusal branch counts the attempt, abandons the head at
`DELIVERY_ATTEMPT_LIMIT` (`inbound_queue.py:178`, `turn_scheduler.py:460-471`), and **returns**
(`:512`). It never asks again. The comment above that branch gives abandonment's purpose as *"so a
permanently wrong entry stops wedging the whole queue"*, but the pass that abandons the head is the
last pass anything makes, and there is no tick (`agent_trigger.py:2433`: *"There is no tick"*). The
entries behind the head are released in principle and wait in practice, until some unrelated event
calls `schedule_agent` for that agent.

Which two passes at 08:22:06 made attempts 2 and 3 (the divergence's own `schedule_agent`, the
run-end re-drain, or both) is inferred from the event order, not measured. That the last of them
abandoned the head and left the divergence entry undelivered is measured.

**What the operator sees.** `GET /queue/autha1/status` answers
`{"waiting_count": 1, "running": false, "waiting_reason": null, "delivery_attempts": 0}`: an entry
waiting for no stated reason, on an idle agent. The task card says a review by `autha1` is in
progress. The one event that names anything is `queue_entry_abandoned`, and it is about the *other*
entry.

**Reach.** The trigger here was F319's stranded head, but the mechanism does not need F319. Any
head refused non-transiently three times (a review target with no commit, an archived agent, a task
the project no longer has, the F56 list) leaves the entry behind it undelivered after the abandoning
pass. How long it waits depends on what happens next for that agent. A divergence restaff is the
bad case, because the restaffed task is already held by the agent the entry is waiting for.

**How long it waits, measured as far as the drive went:** still `queued` with no run at 08:31:58,
9 min 52 s after it was queued, and still `queued` after the served UI was loaded and the Tasks board
opened at 08:32 (loading the page does not re-drain). On that board, task C is the only card of the
four carrying a marker, **Stalled**, and that comes from `has_open_divergence`, not from the entry.
Nothing says a review turn is owed and not coming. **Not measured:** whether an explicit project
open, a settings save or a relocate (the `projects.py` callers of `redrain_queued_agents`; the
others are run-end paths in `agent_trigger.py`, which need some *other* agent's run to end) delivers
it, or how long it would otherwise wait.

**Shape of a repair, not proposed:** after abandoning, loop back and schedule again (the head is
gone, so the next pass selects the next entry); or have the abandonment branch fall through to the
next conversation's entries in the same pass.

---

## F321 (A) — under the default posture, a shell command naming a file in a subdirectory of its own workspace is refused as outside the workspace

**Status:** fixed `612b9c9` by `a-url-is-not-a-path` (tasks §2: the reader, rule 5, which joins
a relative word to the workspace), driven `f492261` (tasks §6.2, ask 2; night 2026-09-12, Windows,
Haiku, default posture). Measured: *"Ask 2 (`run-ec291fb33231`) returned `hello from sub`"*, for
the tool input `python sub/hello.py`. The pre-fix tree, driven the same night (§6.1,
`run-32066fa85347`), answered `Denied: '/hello.py' is outside your workspace.` The `Content-Type:
application/json` header (row 5 below) is H1's, and ask 1 carried it through.

Filed 2026-09-12 by the day window's D-2, while writing R1 of
`openspec/changes/a-url-is-not-a-path`, which proposes to close it along with F300 and F312. It is
**measured live**, not inferred.

**The claim.** Under `workspace` (`DEFAULT_CLAUDE_PERMISSION_MODE`, `runner_commands.py:66`), a
`claude` run cannot run a shell command that names a path in a subdirectory of its own workspace.
`python sub/hello.py`, `git add src/x.py`, `pytest tests/test_x.py::test_a` and
`git diff origin/main...HEAD` are all refused. The reason given names a path the command never
wrote, and it says that path is outside the workspace.

**Live, one Haiku turn, no Hub.** The argv came from `runner_commands.build_command`, the Hub's own
builder, so the flags are the ones a default-posture run gets: `--mcp-config` naming
`hub/hub/mcp_server.py`, `--permission-prompt-tool mcp__agentweave__approve_tool_call`, and
`--permission-mode manual`. The model was `claude-haiku-4-5-20251001` on `claude` **2.1.269**.
`AW_WORKSPACE_DIR` was a scratch directory holding `sub/hello.py`. The harness is
`testbed/scratch/r1f300/live_probe.py` (scratch, uncommitted), and the raw stream is beside it in
`live_probe.jsonl`.

| command, one tool call each | tool result |
|---|---|
| `ls sub/` | `hello.py` |
| `python sub/hello.py` | **`Denied: '/hello.py' is outside your workspace.`** |
| `python -c "print(2)"` | `2` |

`_decide` would have refused `ls sub/` too, because the regex reads `/` out of it, and that resolves
to the drive root. So its result shows that the harness does not ask the approver about a command it
classes as read-only. **Reading works. Running, staging and testing a named file do not.**

**The mechanism.** `_ABSOLUTE_PATH_RE` (`hub/hub/mcp_server.py:936`) begins a candidate at *any*
`/`, including one in the middle of a word. `sub/hello.py` yields `/hello.py`, and `os.path.realpath`
resolves that against the drive root, so the path is outside the workspace. The comment above the
call says the opposite: *"Relative paths are left alone: they resolve against the run's cwd, which is
the workspace"* (`:969-971`). That holds only for a relative path with no `/` in it.

**Measured at `_decide` directly**, with `AW_WORKSPACE_DIR` a real directory:

| command | `_decide` today | reason |
|---|---|---|
| `git add sub/hello.py` | deny | `'/hello.py' is outside your workspace` |
| `pytest sub/test_x.py::test_a` | deny | `'/test_x.py::test_a' is outside your workspace` |
| `git diff origin/main...HEAD` | deny | `'/main...HEAD' is outside your workspace` |
| `python sub/../hello.py` (resolves inside) | deny | `'/../hello.py' is outside your workspace` |
| `curl … -H "Content-Type: application/json" …` | deny | `'/json' is outside your workspace` |

The last row matters most, because it is F300's instructed request. FastAPI 0.136.3 parses a body
as JSON only when the content type is `application/json` or absent (`fastapi/routing.py`, read
2026-09-12), and `curl -d` sends `application/x-www-form-urlencoded`. So the ordinary form of the
request needs that header, and **that header alone is enough to refuse the command**, whatever is
done about the URL.

**It breaches a shipped requirement.** `agent-run-sandboxing`, *"A posture exists in which the
workspace boundary is enforced per tool call"*, scenario *"Work inside the workspace proceeds"*. It
also undercuts the reason `workspace` became the default (`runner_commands.py:62-65`): it *"permits
the execution an agent needs to produce evidence about its own work."*

**Why it is not a separate change.** F300 and F312 are about where in a word the regex may begin.
Any reading that stops it matching inside `https://…` and `$HUB_URL/…` also stops it matching inside
`sub/hello.py`. So this row changes answer whether anyone decides it or not. And a fix that removes
only URLs cannot deliver F300's verdict, because the `Content-Type` header is still refused (row 5).
R1 therefore folds it in and decides it. See the change's `design.md`.

**Not measured:** how many past default-posture runs were refused this way. `F10`'s recorded
reason, `'/builder' is outside your workspace`, has the shape this mechanism produces, but the
command that produced it is not recorded there. Nothing here says it was this.

**Reproduce**, with no Hub, no network and no credential:

```bash
cd hub && py -3.11 -B -c "
import os, importlib.util
os.environ['AW_WORKSPACE_DIR'] = os.getcwd()
spec = importlib.util.spec_from_file_location('m', 'hub/mcp_server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m._decide('Bash', {'command': 'python hub/mcp_server.py'}))
"
```

---

## F323 (A) — on Windows, a traversal written in double quotes passes the default posture and writes outside the workspace

**Status:** fixed `612b9c9` by `a-url-is-not-a-path` (tasks §2: the Bash tool's command is lexed
as bash lexes it, so a `\` inside double quotes survives and is read as a Windows separator; and
rule 6's backstop opens a candidate at a bare `\`, `design.md` R3), driven `f492261`
(tasks §6.2, asks 4 and 5; night 2026-09-12, Windows, Haiku, default posture). Measured:
*"Ask 4 (`run-7d9fd8579e1c`) was answered `Denied: '..\\stray.txt' is outside your workspace.`
Ask 5 (`run-e1831f34f07d`) was answered `Denied: '\\out.txt' is outside your workspace.` No
`stray.txt` or `out.txt` exists anywhere under the fixture, `.agentweave/worktrees/` included, or
beside it."* The tool inputs were exactly `echo hi > "..\stray.txt"` and
`sort -o"..\out.txt" notes.md`. The pre-fix tree, driven the same night (§6.1), **allowed** both
(`run-c264a82f2819`, `run-7d8b1603f75b`), and wrote `stray.txt` and `out.txt` into
`<fixture>\.agentweave\worktrees\`, the parent of the agent's workspace. The PowerShell tool's
dialect (X1c) is tested, not driven.

Filed 2026-09-12 by the day window's D-3, while writing R2 of
`openspec/changes/a-url-is-not-a-path`, which now proposes to close it (`design.md` D1 and D2, row
X1b). It is **measured live**, not inferred.

**The claim.** Under `workspace` (`DEFAULT_CLAUDE_PERMISSION_MODE`, `runner_commands.py:66`), on
Windows, a `claude` run's Bash tool can write outside its workspace with
`echo hi > "..\stray.txt"`. The approver allows it as *inside your workspace*. This breaches the
shipped scenario *"Traversal and links cannot escape"* (`agent-run-sandboxing`, *"A posture exists
in which the workspace boundary is enforced per tool call"*).

**Live, one Haiku turn, no Hub.** The argv came from `runner_commands.build_command`, so the flags
were a default-posture run's: `--mcp-config` naming `hub/hub/mcp_server.py`, and
`--permission-prompt-tool mcp__agentweave__approve_tool_call`. The model was
`claude-haiku-4-5-20251001` on `claude` **2.1.269**. `AW_WORKSPACE_DIR` was `live/ws`. A local
listener stood in for the Hub at `HUB_URL`, so every decision `_report_decision` posted could be
read. The harness is `testbed/scratch/r2f300/live_probe.py` (scratch, uncommitted), with the raw
stream beside it.

| command, one tool call each | tool result | decision the approver posted | file written |
|---|---|---|---|
| `echo hi > "..\stray_x1b.txt"` | completed | `tool_name: "Bash"`, allowed, *inside your workspace* | **`live/stray_x1b.txt`, outside** |
| `echo hi > ..\stray_x1a.txt` | completed | `Bash`, allowed | `live/ws/..stray_x1a.txt`, inside |
| `echo hi > '.'./stray_e1.txt` | `Denied: '/stray_e1.txt' is outside your workspace.` | `Bash`, refused | none |

**The mechanism.** `_ABSOLUTE_PATH_RE` (`hub/hub/mcp_server.py:936`) knows `\` only after a drive
letter, so `"..\stray_x1b.txt"` yields no candidate and `_decide` allows it. Git Bash keeps a
backslash inside double quotes, and MSYS then reads it as a separator. The unquoted form does not
escape, because bash removes the backslash (row 2). So whether a backslash is a separator depends
on the shell's quoting, which the regex does not read. The same commands run in Git Bash directly
gave the same files (`design.md` D1).

**Scope.** This is Windows only: on POSIX `\` is not a separator. It is the Bash tool only, as
measured. The PowerShell tool was not probed, and `..\stray.txt` there is D2's row X1c, read, not
run. Like R8 (`cd .. && …`), this is an escape that the regex never saw. Unlike R8, it is a single
path in a single command, which is what the scenario says is refused.

**Related:** F321 (the same regex, the opposite error), F300 and F312. It is closed by
`a-url-is-not-a-path` once built and driven (tasks §6.1 ask 4, §6.2).

---

## F324 (C) — four form feeds in F304's body shift every line number the classifier prints after it

**Status:** fixed `8f9e5d1`. Both repairs: `load()` splits on `\n` alone, and the two kept
database paths quoted below have their backslashes back. Filed 2026-09-12 (day window, `D-6`),
found while repairing `F318`: the classifier reported that finding's live instance at line 25591,
and an editor shows it at 25587. A plausible origin, unverified: during the repair, a doubled
backslash sent through the Bash tool arrived as a single one, even inside single quotes, so
`b"\\f"` in a Python heredoc wrote U+000C again.

**Reproduction.** `scripts/drive/FINDINGS.md:24612` (editor numbering) sits inside `F304`'s section
and carries four `U+000C` form feeds. The line was written with `%TEMP%` followed by a backslash
and `f295drive020814`, and the backslash-`f` became a control character. It arrived in `5e942ec`
(2026-09-09). `scripts/classify_findings.py:255`, `load()`, reads the file with
`str.splitlines()`, which splits on `U+000C` as well as `\n`:

    py -3.11 -c "t=open('scripts/drive/FINDINGS.md',encoding='utf-8').read(); print(len(t.splitlines()), len(t.split(chr(10))))"

This prints two counts four apart, excluding the trailing empty string that `split` returns. Every
`F<n>@<line>` and every evidence line number the script prints for a line below 24612 is four
higher than the line an editor or `Read` shows. That covers `F304` onward, including four of
the seven open severity-A findings: F312, F319, F321 and F323. Verdicts are unaffected: no fragment the split produces
begins with `#` or `>`, measured on today's ledger.

**Two defects, one repair each.** The reader should split on `\n` only, so that a control
character in a finding cannot move the numbering again. The ledger should get its path back: the
kept databases exist at `%TEMP%` + backslash + `f295drive020814` + backslash + `f295.db` and
`…f295drive110952…`, both listed 2026-09-12. As the line reads now, the path cannot be copied.
Neither repair needs a spec.

**Related:** F304, F318.

---

## F326 (D) — a review turn refused after its checkout is provisioned leaves the checkout registered

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- a review checkout this call provisioned is released when the call ends without a started run; see FIXED at the end of this entry. Was: open. Filed 2026-09-12 by R1 of `a-refused-review-leaves-nothing-behind`, and measured at unit level on `87dfbf4`. It is outside that change's verdict, which is about the task and not the checkout, and nothing proposes a fix.

**The claim.** Where a review turn is refused *after* `prepare_review_turn` has provisioned
`.agentweave/reviews/<reviewer>`, the refusal leaves that checkout on disk and registered with git.
That breaches the main scenario `task-lifecycle-governance` *"A refused review leaves no checkout
behind"*: *"WHEN a review is requested and refused for any reason THEN no checkout has been
created for the reviewer"*. It also breaches design D10 of
`2026-08-28-a-review-started-by-hand-can-finish`: *"a request which is going to be refused SHALL
NOT leave a workspace behind"*.

**The mechanism (read).** `trigger_agent_directly` calls `prepare_review_turn`
(`agent_trigger.py:848`). That call provisions through `worktrees.ensure_review_checkout`
(`review_turn.py:213`, `worktrees.py:580-617`). Three refusals come after it, and none releases the
checkout:
- the canonical context cannot be written (`agent_trigger.py:1049`, `OSError`);
- `UnsupportedRunnerError` (`:1105`);
- the Hub does not know its own address (`:1146`, transient).

**Measured.** `testbed/scratch/r1f319/test_zz_r1f319_ckout.py` sets up a `tmp_path` repository
and an operator-completed task whose evidence names `HEAD`. It restores the real
`ensure_review_checkout`, deletes `HUB_URL`, makes `bound_address.get()` return `None`, and calls
`schedule_agent` once. The refusal is transient. `.agentweave/reviews/rv-reviewer` exists, and
`existing_review_checkout` finds it registered. (The task also reads
`('under_review', 'rv-reviewer')`. That is F319's defect, which the same change addresses.)

**Reach, and why D.** `:1146` fires at the startup re-drain, before any request has been served
(`agent_trigger.py:1152-1157`). There the refusal is a deferral, and the checkout it leaves is
the one the retry will re-point (`worktrees.py:599-605`), so it costs nothing in practice. `:1049`
needs a filesystem failure. `:1105` is probably unreachable behind the `SUPPORTED_RUNNERS` check at
`:678`; that is inferred and not driven. The directory is disposable, one per reviewer, and bounded
by the roster. It waits for that reviewer's next review. It is filed because the spec says *"for
any reason"*, and the ledger should record where that is not true.

**A possible repair, not proposed.** Move the address check and `build_command` above the review
block, since neither depends on the review checkout (inferred). Or release the review checkout on
a non-transient refusal raised after provisioning.

**FIXED 2026-09-23 (interactive session, Round 3, group 3e).** Neither of the entry's two repairs:
moving the address check and `build_command` above the review block covers two of the three sites
and none added later, and releasing only on a *non-transient* refusal leaves the transient one --
the site R1 measured -- still breaching "for any reason". Instead `trigger_agent_directly` is now a
thin wrapper over `_trigger_agent_directly` holding a `_ReviewCheckoutClaim`: the inner function
marks it right after `prepare_review_turn` succeeds and marks it handed off right after the run's
task is registered, and the wrapper releases the checkout (`worktrees.release_review_checkout`) if
the call raises anything in between. Every refusal after provisioning is covered, including ones not
yet written. Only a checkout *this call* provisioned is released -- a refusal ahead of provisioning
("already running a turn") may be looking at one a live review stands in. The transient case now
costs a re-provision on retry, which is what the spec's "for any reason" asks. The name stays on
the wrapper, so `turn_scheduler` and every test patch are unchanged, and
`test_trigger_agent_directly_has_one_caller` still passes. Test:
`test_leg_t_leaves_no_review_checkout_behind` (`test_a_refused_review_leaves_nothing_behind.py`) --
R1's measurement as a test, with the real `ensure_review_checkout`; on the old code the checkout is
still registered.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** Two residuals, not changed: the release is awaited inside
`except BaseException`, so a second cancellation during it skips it; and anything raising after
delivery commits but before the run's task is created would release the checkout under a `running`
Run with no process -- a strand that predates this round.

---

## F327 (B) — a review a flow staffed and whose dispatch is then refused leaves the flow's reviewer holding the task, reported as in flight until the input is given up

**Status:** fixed 2026-10-07 by `a-flow-stages-its-review-in-the-dispatch` (D1, D2, D5): the dispatch stages a flow's review under its rollback; a refused one leaves the task `completed` with its holder and is surfaced with the refusal; the operator's other reviewer is no longer refused. Driven on `:8010` (`d1007_review_staged_drive.py`, 6/11 before, 12/12 after).

**The claim.** F319 is the dispatch's own staging committed by the scheduler. This is the same end
state reached by a different door. A flow firing stages its review **before** the dispatch, in the
commit that queues the review turn (`scheduler.py:2794`, committed at `:2891`), as `agent-flows`
*"A dispatched review leaves the reviewable pool"* requires. When that turn's dispatch is then
refused, nothing undoes the firing's staging, because it was never the dispatch's. The task is left
`under_review`, held by a reviewer that never ran. `task-lifecycle-governance` *"Dispatching a
review staffs the task, whichever path dispatched it"* says staffing SHALL hold *"for every path"*
and that *"a request that is never delivered leaves no task held by a reviewer that never ran"*; the
two main specs already disagree, and this is where.

**Measured.** `testbed/scratch/r2f319/test_zz_r2f319_flow.py`, copied into `hub/tests`, run once
and deleted. A flow (`_flow` from `test_flow_fires_a_review_turn.py`) with one completed task
authored by `builder`, fired once through `JobScheduler._fire_job_internal`; the ladder staffs
`critic`. Two legs, the real `ensure_review_checkout`:

| step | B1: evidence names a commit the repository lacks | B2: `.agentweave/reviews/critic` is a plain directory |
|---|---|---|
| before | `('completed', None, 1 transition)` | same |
| firing 1 | task `('under_review', 'critic', 2)`; entry `queued`, 1 attempt, `waiting_reason` the refusal; `JobRun` **failed** with the refusal; no run | same, with the checkout sentence |
| `decide_firing` | **`in_flight`**, `stall_reason` empty, `_cannot_staff` = `(task-1, critic)` | same |
| two more `schedule_agent("critic")` | entry `withdrawn` at 3, `queue_entry_abandoned`; task unchanged | same |
| `decide_firing` | `stalled`: *"critic is named on task-1 … and is not reviewing it … Ask critic again, review it yourself, or send it back with revision_needed."* | same |
| firing 2 | `JobRun` skipped with that sentence, `review_unstaffed` emitted; task unchanged | same |
| operator dispatches `other` | **`409` "Task task-1 is already under review by 'critic' … or let the review in flight finish."** | same |
| operator dispatches `critic` again | `409`, the commit sentence; task unchanged | — |

**What the operator is told, and when.** Once at once: the job card's failed run carries the
refusal. Then the flow calls the task **in flight** for as long as the refused entry is still
queued, which is until two more passes are made for that reviewer, and on a quiet project nothing
makes them (F320's *"There is no tick"*). Only after the entry is given up does the firing name the
wedge. Throughout, sending a different reviewer is refused with *"let the review in flight
finish"*, about a review that never started — F319's D9 symptom, on the flow path.

**Reach.** B1 needs a commit pruned after the evidence named it; B2 an obstructed checkout path;
both are repository states `decide_firing`'s up-front check (`commit_for_task_review`, a database
read) does not ask. The transient refusal (the Hub's address unknown) also lands here, but a
deferral that clears starts the review the flow staffed, which is correct. The entry guard (leg A)
needs the ladder and the dispatch to drift. `_fire_additional_selection` (`scheduler.py:3156`) and a
divergence restaff (`run_divergence.py:458`, committed before `schedule_agent` at `:840`) stage the
same way before the dispatch; they are read, not measured.

**Why B and not A.** Unlike F319 the operator is told at the moment of the refusal (the failed job
run) and, after the input is given up, told again in words that name the remedy. It is severity B
because in between the flow says the review is in flight and refuses every other reviewer.

**Shapes of a repair, not proposed:** stage the flow's review in the dispatch instead of before it,
keeping it out of the reviewable pool by the pending entry rather than by the status (a change to
`agent-flows`); or return a flow-staged task to where it was on a refused dispatch, which needs an
edge the lifecycle does not declare and leaves two transition rows.

---

## F328 (D) — input the operator withdraws while its turn is being dispatched is counted, given up on, and announced as dropped by the Hub

**Status:** fixed `a5cb384` (day window `d6-repair`, 2026-09-13). Driven live, before and after: see the dated note at the end of this entry. **The repair covers both sides.** The repair the paragraph below names, a counting write conditioned on `state = 'queued'`, was half of it: the operator's withdrawal had the same check-then-write. Delivery's own check-then-write is not covered,
and is filed as F338.

**Original status:** open. Filed 2026-09-12 by R3 of `a-refused-review-leaves-nothing-behind`, measured at unit level on `895aad9`. That change's task 2.1 (as R3 amended it) **narrows it and does not retire it** — corrected 2026-09-12 evening by the pre-approval Opus review. The `state == "queued"` re-read catches a withdrawal that commits before the rollback. But a review dispatch holds the database write lock while it records the reviewer, so an operator's withdrawal waits on that lock and commits *after* the re-read. Test O2 (`testbed/scratch/opusf319/test_zz_opusf319.py`, delay 0.3 s) measured the DELETE succeeding and the entry still ending `('withdrawn', 3)`, with the Hub's "delivery failed 3 times" reason and one `queue_entry_abandoned`. The result was identical on the unmodified tree. The durable repair is a counting write conditioned on `state = 'queued'`, or a re-read inside the same write transaction.

**The claim.** `schedule_agent` loads the entries of a turn, calls `trigger_agent_directly`, and on
a refusal writes `waiting_reason`, counts the attempt and gives up at the limit
(`turn_scheduler.py:347-492`). It never asks whether each entry is still `queued`. An entry the
operator withdraws through `DELETE …/queue/entries/{entry_id}` (`api/v1/inbound_queue.py:257-265`,
calling `withdraw_entry`, `inbound_queue.py:297-306`) while the dispatch runs (a review checkout's `git worktree add` takes
seconds) is then counted, and at the limit gets `abandoned_reason` *"delivery failed 3 times (…); the
Hub stopped retrying"* and a `queue_entry_abandoned` event. The operator withdrew it, and the record
and the event both say the Hub gave up on it.

**Measured.** `testbed/scratch/r3f319/test_zz_r3f319.py::test_withdrawn_during_dispatch`, copied
into `hub/tests`, run once and deleted. One entry at `DELIVERY_ATTEMPT_LIMIT - 1`; the patched
trigger withdraws it through `withdraw_entry` in a session of its own, then raises a request-level
refusal. Unmodified tree: `state=withdrawn attempts=3 abandoned_reason='delivery failed 3 times
(refused); the Hub stopped…' queue_entry_abandoned=1`. R2's prototype of that change (rollback,
re-read by id): the same. The prototype with the re-read filtered to `state == "queued"`:
`attempts=2 abandoned_reason='' queue_entry_abandoned=0`.

**Why D.** It needs the operator to withdraw input in the seconds its turn is being dispatched, and
that turn to be refused. What it costs is one false event and a wrong reason on input the operator
already chose to drop. Nothing is lost that was wanted.

**2026-09-13 (night r9-close): narrowed by `6ebcd9f`, still open.** That commit's re-read by id and
`state == 'queued'` (`a-refused-review-leaves-nothing-behind` §2.1) stops counting a withdrawal
that commits before the rollback, pinned by that change's test 1.8b. A withdrawal that waits on a
review dispatch's write lock still commits after the re-read (test O2 above), so the repair named
in the Status line is still owed.

**2026-09-13 (day `d6-repair`): fixed `a5cb384`.** The D-6 carve-out held. No requirement changes:
`agent-conversation-workspace` already says a pass that finds *"every input it carried was withdrawn
while the attempt was being made"* gave up on nothing. There is no migration and no API or schema
change. `turn_scheduler.py` and `inbound_queue.py` are outside `an-absent-approver-is-not-named`'s
blast radius. F326 was the other candidate and was not taken, because its three refusals are in
`agent_trigger.py`, which that change edits.

- **Both writers checked, then wrote by key, and the entry above only named one.** Test O2 re-run
  on `7b8a33f`: delay 0.3 gave `withdrew: True`, the entry `('withdrawn', 3)`, the Hub's reason,
  and one `queue_entry_abandoned`. That end state also arises from the *operator's* write landing
  last. `withdraw_entry` read the row as queued before the lock, and its unconditional `UPDATE` ran
  after the Hub's give-up had committed. So a counting write conditioned on `queued` alone would not
  have fixed O2's interleaving. The Hub would still have won, and the `DELETE` would still have
  said `200`.
- **The repair: the check is the `UPDATE`'s own condition, on every writer that takes an entry out
  of `queued` without delivering it.**
  - `inbound_queue._withdraw_if_queued` serves `withdraw_entry` and `withdraw_refused_entry`. It
    commits on both branches, because a rollback would expire the caller's rows, and it re-reads
    with `populate_existing`.
  - The scheduler's count-and-give-up is one conditional `UPDATE` per entry, in the batch's one
    transaction. It mirrors onto the session's copy with `set_committed_value`, because a rider
    carried by the pass's next turn has its count stated by `format_turn_prompt`.
  - Whoever writes first wins. The loser matches no row: the `DELETE` answers `409`, or the pass
    counts nothing.
- **Tests.** `hub/tests/test_a_withdrawal_and_a_give_up_do_not_both_win.py` has three, and all three
  fail on `7b8a33f`.
  - The scheduler's side is pinned deterministically, through the awaited
    `other_input_would_have_run_elsewhere` seam.
  - The withdrawal's side is pinned deterministically, through a session holding a copy read as
    queued before the give-up.
  - The route interleaving is pinned with a flushed write holding the lock and a concurrent real
    `DELETE`. It asserts that the answer and the record name the same winner.
  - Mutations: dropping the scheduler's condition fails test 1. Dropping the withdrawal's condition
    fails tests 2 and 3. Dropping the `set_committed_value` loop fails
    `test_failed_run_returns_input.py::test_a_terminal_pre_spawn_refusal_abandons_the_entry_after_the_limit`.
  - The 30 test files that touch the queue: 465 passed.
- **Driven**, `scripts/drive/t_d6_0913_f328_withdraw_race.py`, real routes, no row inserts, one
  Haiku turn per Hub. N reviews of tasks whose evidence names a pruned commit (F319's B1) are queued
  behind the reviewer's own slow turn. At every attempt-2 head, `POST …/continue` and
  `DELETE …/queue/entries/{head}` are fired together, at offsets 0–250 ms.
  - **Pre-fix Hub**, a `7b8a33f` worktree on port 8025, profile `drive0913v`: **3 of 8 samples
    inconsistent**. Each was `DELETE 200`, the entry at 3 attempts with *"delivery failed 3 times
    (commit …"*, and **both** `queue_entry_abandoned` and `queue_entry_withdrawn` for one entry.
  - **Fixed Hub**, port 8024, profile `drive0913w`: **0 of 24 inconsistent**, over two runs.
    Seven samples went to the operator (`200`, 2 attempts, no reason, no abandoned event) and 17 to
    the Hub (`409`, 3 attempts, its reason, one abandoned event). 20 of the 24 `DELETE`s overlapped
    their pass, the longest waiting 198 ms.
- **What the operator now sees when the Hub wins:** the `DELETE` is answered `409` *"Queue entry is
  absent or has already been delivered/withdrawn"*, which is the route's existing sentence and now
  true. The queue card leaves on `queue_entry_abandoned`, as before.

---

## F329 (A) — a first `agentweave` start builds a database no conversation can be written to

**Status:** fixed for every database built from now on, by `hub/hub/migrations/env.py`; **open for a database already built this way**, which nothing repairs. Filed 2026-09-12 from the operator's own first start in `LoopEngine` (PyPI 1.1.0 Hub, this checkout's CLI): every send in the composer failed with *"Could not start the conversation"*.

**The claim.** `_hub_native_start` (`src/agentweave/cli.py`) runs `alembic upgrade head` in the CLI process before it spawns the server, and the Docker image does the same (`hub/Dockerfile`: `alembic … upgrade head && uvicorn`). `init_db`, which the server runs next, does `create_all` and *then* the upgrade. The chain cannot build a database on its own. No migration creates `projects`; `create_all` always has. So every migration that recreates a table guards on `projects` and returns early, trusting that "`create_all` builds the rest from the model". Run alone on an empty file, the chain creates `conversations` in its `0017` shape and skips `0035`, `0058`, `0073` and `0091`. `create_all` then leaves the existing table alone. The database is stamped head without `conversations.title`, and every conversation insert fails: `sqlite3.OperationalError: table conversations has no column named title`, returned to the UI as a bare 500.

**Measured.** At this checkout's head, 28 schema objects differ between the two orders. Missing columns on three tables: `conversations.{sequence,title,title_set_by_operator,origin}`, `inbound_queue_entries.divergence_source_run_id` and `evidence_reviews.sequence`. Five missing indexes, among them the unique `uq_projects_path_key`. Foreign keys differ on `agents`, `runs`, `agent_outputs` and `inbound_queue_entries`. The other 17 tables have the same columns in a different shape: order, server defaults, constraints. PyPI 1.1.0 shows the same defect, with `0081` as its head. The operator's `live` profile has no drift, because it was not built through this path.

**Why nothing caught it.** Every migration test builds with `create_all` first, and every CLI test mocks `_hub_run_migrations`. The only path a fresh install takes was the one path no test ran.

**The fix.** `env.py` builds an *empty* database migrated to *head* from the models before running the chain. That is `init_db`'s order, at the one place every door shares: the CLI, Docker, and a hand-typed `alembic upgrade head`. A database built up to an older revision is still built by the chain, because it is a test constructing history. A command with no destination (`alembic current`) touches nothing. Compared clause by clause, the two orders now give the same schema: 164 objects, no differences. Tests: `test_an_empty_database_migrated_alone_gets_the_schema_init_db_builds` (fails without the fix), `…_built_to_an_older_revision_keeps_that_revisions_schema`, `test_a_read_only_command_leaves_an_empty_database_empty`, and, at the CLI's boundary with the real step unmocked, `test_first_start_migrations_leave_a_database_that_can_hold_a_conversation`, which fails without the fix on the operator's exact error. Driven: `_hub_native_start` on an empty file, port 8013, then the composer's two calls. The trigger returned `200`, and a Haiku run completed with exit code 0 on a titled conversation.

**What stays open.** A database that a first start has already built is stamped head. `env.py` leaves it alone because it is not empty, and no migration re-applies what the skipped ones would have done. Its conversation, queue and evidence-review tables are necessarily empty, since every insert into them failed. The rest of the drift is indexes and foreign keys. The remedy today is to delete the database and start again. A repair migration is the durable one, and it is not written.

---

## F330 (C) — every refused send from the exploring composer leaves an empty specification document behind

**Status:** fixed (Tier 0, 2026-10-08, `bd32b9b`): the composer deletes the document it created through F532's `DELETE /project/documents/{path}` when the trigger is refused or never reaches the Hub (`newConversationSurface.test.tsx`, 2 red before). Drive `scripts/drive/d1008_findings_drive.py f330`: in Chromium on `:8010` the Hub log shows the document created (201), the trigger refused (409), the document deleted (200); none left in the list or on disk. Its unbuilt openspec change `a-refused-first-send-leaves-no-exploration-behind` (server-side, archive-not-delete, D-B12-1) was archived as superseded the same day; the operator kept the delete. Was: open. Filed 2026-09-12 alongside F329, which produced eight of these in `LoopEngine/spec/changes/`.

**The claim.** `NewConversationSurface.tsx` creates the exploring document *before* it posts the turn. That order is deliberate: the first turn has to carry the document. But when `/agent/trigger` then refuses, nothing removes the document, so each retry mints another placeholder (`emerald-fenrir`, `silver-thunderbird`, …), each an empty `exploring` change spec. The operator is left with one orphan per attempt, in the repository and in the spec list, for turns that never ran.

**A possible repair, not proposed.** Let `/agent/trigger` create the document inside the same request that queues the turn, so a refusal rolls both back. Or have the composer withdraw the document it created when the trigger fails.

## F331 (A) — on POSIX, the default posture allows any scheme URL in a shell command, and `curl -T x file:///…` writes outside the workspace

**Status:** fixed `612b9c9` by `a-url-is-not-a-path` (tasks §2: rule 1 judges a `file:` URL's
path as a path, and every other scheme under the network rule). **Tested on Linux, not driven
on POSIX.** Both of the change's drives were on Windows. The evidence is CI's `hub-test` job on
`ubuntu-24.04`:
- **Pre-fix.** At `00a5569`, the pin, before §2, run `34722726736` reported
  `test_the_decided_table[F331]`, `[N7]`, `[R10]` and `[N1]` **XFAIL**, each strict. That job's one
  error was F292's `database is locked`, in `test_reviewer_is_not_the_author.py`.
- **Fixed.** At `612b9c9`, run `34723993806` reported `[F331]`, `[N7]`, `[R10]`, `[N1]`, `[N2]`,
  `[H5]`, `[H6]`, `[H7]`, `[H13]` and `[H14]` **PASSED**, with no xfail left in the file.
  The job summary was `4187 passed, 18 skipped`.

The Windows drive (`f492261`, §6.2 ask 3) shows the network rule's refusal text end to end. That
it fires the same way on a POSIX host through a live run is inferred from the table, not driven.

Filed 2026-09-12 by the night window, while pinning `a-url-is-not-a-path` §1 (queue
item `u1-pin`). **Measured on Linux, not through a live run.** `_decide` was called directly, from
`hub/hub/mcp_server.py` at `c12a7d3`, under WSL Ubuntu with Python 3.12.3. curl was run in the
same shell.

**The claim.** Under `workspace` (`DEFAULT_CLAUDE_PERMISSION_MODE`), on POSIX, `_decide` allows
every shell command whose only absolute-looking text is a scheme URL:

| command | `_decide` on Linux | on Windows |
|---|---|---|
| `curl -s https://example.com/x` | **allow**, *inside your workspace* | deny, `'s://example.com/x'` |
| `curl -s http://169.254.169.254/latest/meta-data/` | **allow** | deny |
| `pip install https://example.com/pkg.tar.gz` | **allow** | deny |
| `curl file:///etc/passwd` | **allow** | deny, `'e:///etc/passwd'` |
| `curl -T notes.md file:///tmp/f331_stray.txt` | **allow** | deny |

The last command, run in the same WSL shell with curl 8.5.0, exited 0 and **wrote
`/tmp/f331_stray.txt`**, a path outside the workspace. That breaches the shipped scenario
*"Traversal and links cannot escape"* (`agent-run-sandboxing`, *"A posture exists in which the
workspace boundary is enforced per tool call"*). The `file:///etc/passwd` row is the same escape as
a read. A `Read` of `/etc/passwd` is refused by the same function.

**The mechanism.** `_ABSOLUTE_PATH_RE` (`mcp_server.py:936`) opens a candidate at a drive letter
followed by a separator. So in `https://…` it matches `s://example.com/x`, and in `file:///…` it
matches `e:///…`. On Windows that is a rooted path on drive `S:` or `E:`, so it is outside, which
is the refusal F300 and F312 recorded. On POSIX `os.path.isabs("s://example.com/x")` is `False`.
The candidate is joined to the workspace, `realpath` collapses `//`, and it resolves inside.

**What this corrects.** F300 says *"`https://example.com/x` yields the candidate
`//example.com/x`"*. F312 says *"No agent on the default posture can make any network request from
a shell command"*. Both statements are true on Windows only. The shipped Docker deployment
(`hub/Dockerfile`) is Linux, and so is CI. There, every URL-bearing refusal those findings record
is an allow. The exception is where another absolute path in the same command is found first, as
with `$HUB_URL/…`, where `/api/…` is the candidate.

**Closed by** `a-url-is-not-a-path` once built and driven. Rule 1 judges a `file:` URL's path as a
path, and every other scheme under the network rule. The rows are pinned in
`hub/tests/test_permission_approver.py::test_the_decided_table`:
- `F331`, the `-T` upload, and `N7`: refused as outside;
- `R10`, `N1`, `N2`, `H5`–`H7`, `H13` and `H14`: refused as network addresses.

On Linux each is a strict xfail today that fails on its **answer**. So CI's Linux job is where the
fix is seen to land.

**Reproduce:** `testbed/scratch/night0912/f331_posix.py`, run in WSL from `hub/` (scratch,
uncommitted). The table's per-row cause is in `testbed/scratch/night0912/why_each_row.py`.

**Related:** F323 (the Windows twin: an escape the regex never saw), F300, F312.

## F332 (A) — on POSIX, bash's ANSI-C quoting writes a traversal no reader of the command text sees

**Status:** fixed `0e52ad4` (the decoder + `_PLAIN_RELATIVE_RE` fix; pinning and mutation
verification in `23fd706`, the wire-shape test in `09146c6`), re-driven live `5a85863`,
archived 2026-09-15. **Mechanism: §2 of `a-quote-can-spell-a-slash`** — `_lex` now decodes a
bash `$'...'` ANSI-C string itself (both a C-locale and a UTF-8 reading, refusing if either
would escape), so the six rules judge the word bash actually produces instead of its
undecoded text. **Evidence:** the live Windows drive (§5.2) refused
`echo hi > $'..\x2fstray.txt'` as `Denied: '../stray.txt' is outside your workspace` and
correctly allowed the previously-over-refused inside path `cat $'sub\x2fhello.py'` (row I1).
The POSIX flip — the actual escape this finding names — is **tested on Linux, not driven**:
CI's `hub-test` job (`ubuntu-latest`) passing at HEAD (run `35024356136`, job `hub-test`,
`https://github.com/gutohuida/AgentWeave/actions/runs/35024356136`) carries every row of
design.md's D2/D6 tables — G1–G10, D1, I1, L1, N1–N5, P1–P7, Q1–Q4, S1–S3, T1–T2 — pinned
and passing against the real, unmutated tree, on the platform this escape actually needs;
the drive itself is Windows and cannot show the POSIX write.

**Filed 2026-09-12** by the night window, while implementing `a-url-is-not-a-path` §2 (queue
item `u2-reader`). **Measured under WSL Ubuntu, not through a live run** (original filing).
Nothing was driven at filing time: `_decide` was called directly, and bash was run on its own
in the same WSL.

**The claim.** In bash, `$'…'` decodes backslash escapes, so `$'..\x2fstray.txt'` is the word
`../stray.txt`. The command text contains no `/`. Run from `/tmp/ansic/ws` in bash 5.2.21,
`echo hi > $'..\x2fansic_stray.txt'` exited 0 and **wrote `/tmp/ansic/ansic_stray.txt`**, in the
workspace's parent. Each of these readers allows it on Linux:
- the whole-command regex (`c12a7d3`);
- `a-url-is-not-a-path`'s reader, measured by `testbed/scratch/night0912/d11a_check.py` under WSL;
- R2's and R3's design aids, by inspection, because neither decodes `$'…'`.

That breaches *"Traversal and links cannot escape"* (`agent-run-sandboxing`), on the Docker
deployment's platform. Octal (`\057`), `/` and `\U0000002f` are the same mechanism, and
were not run.

On Windows the escape is refused: `\` is a separator there, so the word `$..\x2fstray.txt` holds
a `$` and a separator, and rule 3 refuses it. That was measured through the reader, not through
Git Bash.

**Not closed by `a-url-is-not-a-path`.** That change neither opens this nor closes it (design
D11a, *"Found, not fixed"*). There is a clean repair: the lexer can decode `$'…'` as bash does,
and then judge the decoded word. It needs its own rows, because it touches every escape bash
supports, so it is left for a proposal.

**Reproduce:** `wsl -d Ubuntu -- bash testbed/scratch/night0912/ansic.sh` (scratch, uncommitted),
which cleans up after itself.

**Related:** F331 (the same class of POSIX-only escape), F323.

**R1 note (2026-09-13, spec loop, proposed `a-quote-can-spell-a-slash`).** Reproduced and mapped
the class by measurement. `ansic.sh` under WSL (bash 5.2.21): `echo hi > $'..\x2fansic_stray.txt'`
from `/tmp/ansic/ws` exited 0 and wrote `/tmp/ansic/ansic_stray.txt` in the parent. `_decide`
called directly under WSL Ubuntu (Python 3.12.3) returns `allow`. The full class, measured with
`testbed/scratch/r1f332/forms.sh` (bash truth) and `reader_forms.py` (today's reader, both
platforms): the ANSI-C separator decodings — `\x2f` hex, `\057` octal, the 4- and 8-hex unicode
escapes, the fully-spelled `$'\x2e\x2e\x2f…'`, the split-quote and adjacent forms, and the same in
`tee`/`cp` argument position — all write outside and are all allowed on POSIX today; a literal-`$`
spelling (`$'\x24HUB_URL\x2f..\x2f..\x2fx'`, the ANSI-C analog of E20–E22) is likewise allowed. On
**Windows** every one is already refused today (the literal `\` the reader keeps is a separator
there, so with the `$` it trips rule 3, for the false reason *cannot be checked*) — so this escape
is **POSIX-only**, exactly as F331 was. Measured *not* escaping: `$"…"` locale strings (write a
literal-backslash name inside the workspace), brace expansion (cannot both produce and hide a
separator), tilde and glob (already accounted for). **No new escaping form found beyond the ANSI-C
class; no new finding filed.** The repair (lexer decodes `$'…'` as bash does, produced literal `$`
becomes the sentinel, bash dialect only) was prototyped (`testbed/scratch/r1f332/prototype.py`) and
flips all ten POSIX rows to refused while keeping inside ANSI-C paths and `$"…"` allowed; it also
corrects a Windows over-refusal of an inside ANSI-C path (`cat $'sub\x2fhello.py'`). POSIX evidence
route is CI's Linux `hub-test` (strict XFAIL→PASS) plus WSL, per the change's design D4; the night
drive is Windows and cannot show the flip. R2 and R3 to follow.

**R2 note (2026-09-13, spec loop, reviewed `a-quote-can-spell-a-slash`).** Re-derived the decode
set against bash 5.2.21 (WSL) and re-ran R1's prototype decoder on both Windows and POSIX
(`testbed/scratch/r2f332/`). R1's *mechanism* is sound (decode `$'…'`, judge the decoded word) and
its quote-state guard, `_LITERAL_DOLLAR` sentinel, command-sub recursion, `$"…"` non-decoding,
octal wrap and branch placement all check out. But R1's **decoder** had two defects, both measured
and both fixed in the proposal (not shipped): (1) it dropped the backslash on a *digitless*
`\x`/`\u`/`\U`, so `$'..\x'` — which bash keeps as `..\x`, a traversal on Windows — would flip from
*deny* (today) to *allow* on Windows, opening an escape; the fix keeps the backslash, matching
bash. (2) it called `chr()` unguarded on `\uHHHH`/`\UHHHHHHHH`, so an overrange codepoint
(`$'\U110000'`, `$'\Uffffffff'`) raised `ValueError`/`OverflowError` out of `_decide`, breaking its
*pure and total* contract on both platforms; the fix produces no character above `U+10FFFF` (never a
separator) and never raises. Added table rows **N2** and **N3**, tasks §2.2 decode rules, mutations
§4.6/§4.7, and drive §5.2 steps. These are defects in the proposed fix, in scope, so fixed in the
proposal — no separate finding filed. Design D1's claim that a digitless escape's rendering "does
not affect the decision" was the wrong argument (true on POSIX, false on Windows), and D5's
totality argument omitted overrange codepoints — both corrected. R3 to follow.

**R3 note (2026-09-13, spec loop, reviewed `a-quote-can-spell-a-slash`).** Status unchanged (open;
closed only when built and driven). Re-derived the decode against **real Git Bash 5.2.37 on Windows**
(not only a Python model) and against WSL bash under several locales, and re-ran R1's, R2's and a
corrected decoder through the real `_decide` on both platforms (`testbed/scratch/r3f332/`:
`unicode_probe.sh`/`gen_probe.py` bash truth per locale, `quote_lexing.py` escaped-quote lexing,
`three_decoders.py` R1 vs R2 vs R3 through `_decide`). R1's mechanism and R2's two fixes hold, but
**two more escapes of the same class R2 opened were found — both Windows-only, both fixed in the
proposal (not shipped), no separate finding filed:**
- **Finding 1 (`\u`/`\U` above 0xFF).** bash's decode of a codepoint above 0xFF is *locale-dependent*:
  the **C locale Git Bash uses by default for a non-login `bash -c`** keeps the escape literal,
  backslash and all (`$'..\u0100'` → `..\u0100`), while a UTF-8 login shell decodes it. R1 and R2
  both decode it to one character (R2 returns `""` above U+10FFFF), dropping the backslash; on Windows
  that backslash is a separator, so `$'..\u0100'`…`$'..\U00110000x'` would flip from *deny* (today) to
  *allow* — an escape the change would introduce. Measured through `_decide` (R2 column allows; R3
  column denies). R2's N3 argument ("bash emits high bytes, none a separator") was true of the bytes
  but false about the literal backslash — an argument wrong while its Linux/UTF-8 outcome is right.
- **Finding 2 (`\c` before the closing quote).** bash keeps `\c` literal when nothing follows it in
  the body (`$'..\c'` → `..\c`); R1's and R2's one-phase decoders read the closing `'` as `\c`'s
  control target, over-run the string and drop the backslash, flipping `$'..\c'` from *deny* to
  *allow* on Windows. Measured through `_decide`.
**Fix (one invariant, replacing the per-escape arguments):** decode an escape to a character only when
it is determined and locale-independent (simple escapes; `\x`/octal byte escapes; `\u`/`\U` ≤ 0xFF;
`\cX` with a real body char); otherwise keep the backslash literal. This closes both findings, and
because `\u`/`\U` above 0xFF is never passed to `chr()` it also removes R2's overflow guard while
keeping totality (a codepoint above U+10FFFF can no longer reach `chr()`). **Linux/Docker is sound
with either decoder** — `\` is not a separator there and these escapes never decode to `/` — so this
is a Windows-only regression the change would otherwise introduce, and finding 1 additionally depends
on the agent Bash tool's (unguaranteed) locale; the decoder is made safe under both. Added table rows
**N4**, **N5**, reshaped **N3** (Windows now *deny outside*, not allow), tasks §2.2 rules, mutations
§4.7 (decode above 0xFF via `chr`) and §4.8 (consume the closing quote for `\c`), and drive §5.2 steps.
Checks that found nothing: escaped-quote lexing (`\'`/`\\` match bash), `\x`/octal locale-independence,
`\cX`-symbol mis-decode is separator-safe (cosmetic only), `_where` totality over every emittable char
(now only U+0000–U+00FF), `\U`≥0x80000000 (benign over-refusal on Windows, not a regression),
spec-delta integrity, PowerShell dialect untouched.

**Night note (2026-09-13, f332-s2, implementation STOPPED).** Status unchanged: **open**. The
proposal's fix opens a Windows escape of its own. It was built exactly to tasks §2.2, measured, and
not committed. R3's invariant ("never emit *fewer* separators than bash") misses the other
direction: on Windows a backslash the decoder keeps and bash does not keep is a **phantom directory
level**, and a following `..` climbs out of it. Two consequences, both measured through the built
`_decide` and through real Git Bash 5.2.37, with the workspace at `a\work`
(`testbed/scratch/night0913/s2/depth_probe2.py`):
- `mkdir A`, then `echo hi > $'A\Uffffffff/../../esc2.txt'`: **allowed**, and bash wrote
  `a\esc2.txt`, **outside**. bash emits nothing for `\U` ≥ 0x80000000 in every locale, so the
  literal the rule keeps adds a level that is not there. This is exactly the case R3's checklist
  cleared as "benign over-refusal, not a regression"; that holds only at the start of a word, with no
  `..` after it.
- Under `LANG=C.UTF-8` or `en_US.UTF-8`, `mkdir -p $'A\u0100'`, then
  `echo hi > $'A\u0100/../../x'`: **allowed**, and bash wrote outside. A UTF-8 locale encodes
  `\u0100` with no backslash.
- At `1ebff15` (today's lexer) both are **refused**, so the built change would be a regression.
  Windows only: on POSIX a backslash is not a separator.

Git Bash's rendering, all four locales (C, unset, C.UTF-8, en_US.UTF-8), from
`s2/render_probe.sh`: `\u0100` through `\U7fffffff` is kept literal under C and under an unset `LANG`, and
encoded under both UTF-8 locales; `\U80000000` and `\Uffffffff` are empty in all four; `\cA`, `\c/`
and `\c` + é give `01`, `0f` and `03 a9` in all four (bash's `TOCTRL` masks with 0x1F; R3's reference
decoder XORs with 0x40 and so gives `o` for `\c/`, which is harmless for separators). The fault was found
by fuzzing the built `_lex` against R3's reference decoder (`s2/fuzz.py`, 200,000 commands). Every
divergence was a `\c` escape; following one of them led to the phantom-level class. Handed back to the
day window through `spec-queue/DECISIONS.md` (*a-quote-can-spell-a-slash stopped at §2*). The
stopped implementation is at `testbed/scratch/night0913/s2/s2-stopped.patch`.

**Implementation and drive note (2026-09-15).** The design went through five more adversarial
rounds this day (Round 4 replaced the phantom-component invariant above with a dual-reading rule;
Rounds 6-9 found and fixed a separate, pre-existing rule-5/6 fallthrough over-refusal the decoder
newly made reachable -- see `design.md`'s D1 and D6), then was implemented in full: the ANSI-C
decoder and the `_PLAIN_RELATIVE_RE` broadening both landed in `hub/hub/mcp_server.py`. Every row
of design.md's D2/D6 tables is pinned in `hub/tests/test_permission_approver.py` and verified on
both Windows and real POSIX (WSL Ubuntu bash); all 13 mutation checks (Section 4) confirmed
load-bearing; the whole Hub suite is green (4397 passed, 0 failed). Driven live on Windows against
a real `claude-haiku-4-5` agent, pre-fix and post-fix (tasks.md Section 5): 27 of 28 checks matched
the predicted table exactly, including the traversal refusal, the `I1` over-refusal correction, and
`N3`'s real allow-flip with a file actually created.

**One row's live drive evidence is the model's own behavior, not the fix.** `N4`
(`echo hi > $'..\u0100'`, a `\uHHHH` escape above 0xFF that should keep its backslash and be
refused as a Windows traversal) was never denied in the drive -- because Haiku resolved the
`\uHHHH` text into the actual Unicode character before ever constructing its own Bash tool call,
reproduced twice, including with an explicit instruction not to. Ruled out as a transport or
`mcp_server.py` defect: a controlled JSON-RPC probe sending the literal six-character escape text
through a correct `json.dumps`/`json.loads` round trip denies exactly as `N4`'s unit test predicts
(`Denied: '..\u0100' is outside your workspace.`). The resolution happens in the model's own text
generation, before the escape ever reaches this repo's code. Not a defect in this fix --
`_decide` and the real spawned server were already verified directly against the literal escape
text at the unit and wire level, both platforms -- and arguably a narrowing of the exploit surface
in practice: a compliant agent tends to self-decode this escape class rather than reproduce it
verbatim for an attacker to rely on. No F-number filed for this; recorded here as the reason `N4`'s
only evidence is the unit/wire-level tests, not the live turn.

## F333 (B) — a `continue` whose pass gives up its conversation's input answers that the conversation "had nothing queued"

**Status:** fixed (this commit) [Round 3, 2026-09-22] — the answer is taken from the entries the pass gave up, with their refusal; see FIXED at the end of this entry.

**Rendered (d1-drive, 2026-09-13).** Leg F rebuilt through real routes, with Haiku as X. H is
queued at 2 attempts, refused by the author guard. Then **Continue was pressed in the UI** on H's
conversation (`data-testid="conversation-continue"`). One `POST …/continue` returned 200. H went
to `withdrawn` at 3, and M was delivered. `data-testid="session-continuity"` read, verbatim:
*"Not started — this conversation had nothing queued. Reply with the single word pong. Call no
tool. started instead."* The label is M's conversation title, which is its first message. That
follows the "labelled by title" rule, and it reads badly here. The guard's sentence is not in the
notice. It is in the conversation's timeline, one row above, as H's NOT DELIVERED line. So the
screen contradicts itself. Screenshot: `%TEMP%\d1_0913\render\shots\f-094433-2-after-continue.png`.
Harness: `scripts/drive/t_d1_0913_render.py F`.

**The claim.** `POST /conversations/<H's>/continue` was sent while that conversation held
review H (`entry-b087e9dc3dc9`, `queued` at 2 attempts, refused by the guard). Its pass gave H up
(`withdrawn` at 3) and then went on to start M, the input behind H in another conversation. That
is exactly what F320's fix intends. The answer was:
`{"started": false, "started_conversation_id": "conv-1c194f349562", "waiting_reason": "this conversation had nothing queued"}`.
The conversation had input queued when the request arrived. The pass had just given up on that
input, and the refusal it gave up over is not in the answer.

**Why.** `checkpoints.py:289-307` replaces the scheduler's `waiting_reason` whenever a turn
started in another conversation. It picks the wording by asking `queued_entries` about the named
conversation **after** the pass, and by then H is `withdrawn`. So the answer reads the
conversation's state after the pass, while the shipped scenario (*"The named conversation had
nothing queued"*, under *"A start is reported only to the input it is about"*,
`agent-conversation-workspace`) is about a request naming a conversation that *has* no input
queued. Before the fix, the give-up pass stopped. `started_conversation_id` was null, so the
route passed the guard's sentence through (r7's leg F: `started: false`,
`started_conversation_id: null`, the guard's sentence as the reason).

**What the operator sees.** `AgentOutputPanel.tsx:759-769` renders *"Not started — this
conversation had nothing queued. <M's conversation> started instead."* So an operator who pressed
Continue on a review they were waiting for is told nothing was ever there. The give-up itself is
recorded on the entry (`abandoned_reason`) and as `queue_entry_abandoned`.

**A possible repair, not proposed.** Take the answer's wording from the entries the pass gave up,
which the scheduler already knows, rather than from `queued_entries` after the pass. Where the
named conversation's input was given up in this pass, say that, with its refusal.

**Reproduce:** leg F of `scripts/drive/t_d1_0912_f319_reach.py` with `AW_EXPECT=fixed`. Line 81
of `~/.agentweave/hub/profiles/drive0913s/r8-fixed-transcripts/r8f-drive.out` has the answer.

**Related:** F320 (the pass going on), F131 (the other-conversation answer).

**FIXED 2026-09-22 (interactive session, Round 3, group 3c).** The finding's own suggested repair. `continue_conversation` records the conversation's queued entry ids before the pass. When a turn starts elsewhere and none of this conversation's input is still queued, but some was before, the answer is `"this conversation's input was given up: <abandoned_reason>"` (read fresh, `populate_existing`, since the scheduler wrote those rows in its own session), or a plain "taken out of the queue" when no reason was recorded. The trailing full stop of the quoted refusal is dropped because `AgentOutputPanel` appends its own. "had nothing queued" now means only that. Test: `test_input_the_pass_gave_up_is_reported_as_given_up_with_its_reason` (`test_a_start_is_reported_to_its_own_input.py`), which gives the entry up inside the real `schedule_agent` pass; on the old code it answers "had nothing queued". Not rendered in a browser.

## F334 (B) — the author guard's refusal of a dispatched review names an assignment the rollback discarded

**Status:** fixed `4515728` + `7343200` (`a-refusal-names-a-remedy-that-works` groups 4a-4b),
archived `b29c096` 2026-09-16. Filed 2026-09-13 by the night window, from the same drive as F333
(§5.3, leg A). **Measured on a live Hub, then driven live again against the fix** (task 5.3,
`:8011`, profile `drive0916`, below and under F353). This is a new consequence of F319's fix, and
was out of that change's scope.

**The claim.** A review queued for agent X behind X's own turn, during which X records evidence,
is refused at every delivery by `_guard_evidence_author_not_reviewer`
(`task_transition_service.py:454-464`). On the fixed tree, the entry's `waiting_reason`, and
then its `abandoned_reason`, read *"Cannot move task task-bf0e7cd8ad2c to 'under_review': it is
assigned to 'authr8f', which recorded evidence for this task … Assign a different reviewer, or
clear the assignee to review it yourself."* The task is `("completed", None)`, before the
dispatch and after every pass. **It is not assigned to anyone.**

**Why.** `enter_selected_task` writes the reviewer into `assignee` before it transitions (F70), so
the guard judges a *staged* assignee. Design D1 of `a-refused-review-leaves-nothing-behind` says
so, and says the refusal is correct, which it is. The sentence was written for an operator's
`PATCH` of a task that really is assigned. Before F319's fix the staged assignee was committed,
so the sentence happened to be true (r7: `("completed", "authr7q")`). Now the rollback discards
it, and the words describe a state nobody can see. *"Clear the assignee"* is advice with nothing
to act on. *"Assign a different reviewer"* is still right.

**Where it shows.** Measured: the queued entry's reason, and the give-up's `abandoned_reason`.
Possibly also a route `409` for an idle author, if that path stages before the guard answers. That
was neither read nor measured, and the route's own pre-check (`review_dispatch_refusal`) may
answer first, in its own words.

**A possible repair, not proposed.** Word the dispatch-time refusal from the reviewer being
entered (*"'authr8f' recorded evidence for this task, so it cannot review it"*), or let
`_guard_evidence_author_not_reviewer` say "being assigned" when the assignee is uncommitted. The
guard's decision is unchanged either way. §6.2 of that change (is the reason enough?) is the
human judgement this finding feeds.

**Reproduce:** leg A of `scripts/drive/t_d1_0912_f319_reach.py` with `AW_EXPECT=fixed`, in lines
49-61 of the same output file.

**Related:** F319, F70.

## F335 (D) — a review refused on dispatch still broadcasts that it resolved the task's open divergence

**Status:** fixed in code (2026-09-25, night iteration 7) by `an-event-is-announced-only-once-its-write-is-committed` — `resolve_divergences_for_task` now announces through `defer_broadcast`, published from the session's `after_commit` listener, so a refused review publishes nothing (`hub/tests/test_an_event_is_announced_after_commit.py`; mutation to a staging-time `publish` fails three tests). F251's coupling is released: admitting the kind to the allowlist no longer surfaces a false line. Not driven on a live Hub yet (night-drive).

**Earlier status (superseded by the fixed line above; `test_an_event_is_announced_after_commit.py` passes 2026-10-12):** open, latent behind F251 — re-read 2026-09-15 (night `ledger-conflicts`): `resolve_divergences_for_task` still broadcasts at staging time (`hub/hub/run_divergence.py:104`, before its caller commits), and `SSE_EVENT_TYPES` (`hub/ui/src/hooks/useSSE.ts:21`) still omits the kind, so the false event is on the wire and in no UI surface; F251 has no fix either.

**Narrowed by the 2026-09-13 day drive: the false broadcast is real on the wire,
and no UI surface renders it today.** The live activity feed drops `run_divergence_resolved` before
any listener (F251, `hub/ui/src/hooks/useSSE.ts:21-68`, checked at `:335`), so the feed line this
finding predicts cannot appear in the served bundle. It is **latent behind F251**. Fixing F251
alone would make the false line render. Fix this one first, or with it. Filed 2026-09-13 by the
night window (r9-close of `a-refused-review-leaves-nothing-behind`, task 8.5), as that change's
`design.md` D8 said it would be once §2 landed. Measured at unit level on the fixed tree at
`1b3d52c`, then driven live (below).

**Driven (d1-drive, 2026-09-13, live Hub at `4521625`, Chromium on the served bundle).** Harness:
`scripts/drive/t_d1_0913_render.py D` and `Q`, then `scripts/drive/t_d1_0913_feed_probe.py`.
- **The operator route never reaches it.** A review of a completed task carrying an open
  divergence, whose evidence names a pruned commit, was dispatched to an idle reviewer. The answer
  was `409` *"commit … is not present in this repository, so there is nothing to check out for
  review"*. It came from `review_dispatch_refusal` (`api/v1/agent_trigger.py:1461`), **before
  anything is staged**. No broadcast, no feed line, the divergence stayed open, and the task row
  was unchanged.
- **Delivery reaches it, and the broadcast is real.** A review queued behind the reviewer's own
  running turn, while the commit still existed, was answered `200 queued`. The commit was then
  pruned. The run-end re-drain staged it (`enter_selected_task`, `:845`), and then
  `prepare_review_turn` refused it (`:856`): `waiting_reason` *"commit … is not present …"*. One
  more `continue` re-staged it, with `curl -N` on `/api/v1/events`, the stream the UI reads. The
  wire carried `event: run_divergence_resolved` /
  `data: {"task_id":"task-1275228c05dd","count":1,"project_id":"proj-0ace0a0911e3"}`. The
  divergence stayed open, and 0 `run_divergence_resolved` rows were written.
- **The feed does not render it.** The Activity tab was open through the delivery, and it showed
  no "open divergence … resolved" line (`q-…-1-activity-after-delivery-refusal.png`). Then a
  **true** resolution: an operator `PATCH` of the same task to `under_review`, with the page open.
  The feed rendered the live `task_updated … → under_review` line, and still no resolution line,
  although the wire carried `run_divergence_resolved` for it too. So the kind is dropped, true or
  false. The cause is F251's allowlist.
- **Where F335 can reach an operator, then:** nowhere in the UI today. An SSE consumer other than
  `useSSE` would see a false event. A review refused *at delivery* (queued behind a running turn,
  or flow-staffed) is the only path that broadcasts one. A review refused *on the route* does not.

**The claim.** Entering review resolves the task's open divergences: `apply_transition` calls
`resolve_divergences_for_task` (`run_divergence.py:66`), which stages the `resolved_at` write and
a `run_divergence_resolved` event row, and **broadcasts** `run_divergence_resolved` over SSE at
once (`:103`). When the dispatch is then refused, F319's fix (`6ebcd9f`) rolls the scheduler's
transaction back, so the divergence stays open and the event row is never written. The broadcast
has already gone. The live activity feed renders it as *"1 open divergence on T resolved"*
(`hub/ui/src/lib/eventSummary.ts:142`). That line is false, and a reload drops it, because the
event row it would be reloaded from was rolled back.

**Measured.** A scratch test (`testbed/scratch/night0913/r9/test_zz_r9_broadcast_scratch.py`,
copied into `hub/tests`, run once and deleted) drives 1.8a's own leg
(`_divergence_leg` in `hub/tests/test_a_refused_review_leaves_nothing_behind.py`): a completed task
whose run ended with an open divergence, built through `bind_run_to_task` and `evaluate_run_end`,
then a B1-refused review through `schedule_agent`, with `sse_manager.broadcast` spied. Result:
broadcasts `['run_divergence_resolved']`; the divergence's `resolved_at` is `None`; 0
`run_divergence_resolved` event rows; the task equals its before-dispatch snapshot.

**Why D.** It needs a completed task carrying an open divergence (a bound run that ended without
moving its task, then the operator completing it), and a review of it refused on dispatch. What it
costs is one false line in a live feed, gone on reload; the database, the board and every durable
record tell the truth (test 1.8a pins that). Before F319's fix the same broadcast was true only
because the defective staging was committed with it.

**A possible repair, not proposed.** Defer the broadcast until the transaction commits — collect
it on the session and send it after `commit()`, as the event row already is — rather than sending
it at staging time. That is a change to `run_divergence.py`, which `a-refused-review-leaves-nothing-behind`
kept out of its file set on purpose (its tasks 7.4).

**Reproduce:** test 1.8a, `test_a_refused_review_does_not_close_an_open_divergence`, which already
captures `broadcasts` for this record; assert `"run_divergence_resolved" in broadcasts` to see it.

**Related:** F319 (the fix that made it real), F326 (the other thing a rollback cannot take back).

## F337 (C) — a refusal's path or command is recorded and never shown, and its activity line says the agent did the refusing

**Status:** fixed (this commit) [UI-1, 2026-09-23] — a refusal's line says the agent was refused, and shows the bounded detail it was aimed at; see FIXED at the end of this entry. Was: open. Filed 2026-09-13 by the day window's `d3-r2` (F299's round 2). **Read from the
source. Not rendered in a browser.**

**The claim.** Every `permission_denied` row reaches the activity through `EventRow`, which shows
the event type and `summaryForEvent`'s sentence (`hub/ui/src/components/activity/EventRow.tsx:56`).
For this kind that sentence is `` `${agent} refused ${tool_name}: ${reason}` ``
(`hub/ui/src/lib/eventSummary.ts:114`). It never reads `detail`.

- **The path or command is recorded and not shown.** Codex's refusals put the path or command in
  `detail` (`hub/hub/api/v1/agent_trigger.py:2771-2786`). Their `reason` is often only *"outside
  `<agent>`'s workspace"*. So the operator reads that `Write` was refused, and not what it was
  aimed at. The only way to see the path is the row's copy button, which copies the JSON.
- **The sentence names the wrong actor.** *"`<agent>` refused Write"* reads as the agent refusing
  something. The runtime, the Hub or the operator refused the agent.

**Why now.** `openspec/changes/an-absent-approver-is-not-named` (D6) records Claude's
harness-decided refusals in the same shape, so every refusal it adds inherits both problems. That
change is Python-only and does not fix them. Its D7 and test guide now say what the line shows.

**A possible repair, not proposed.** Append `detail`, bounded, to the sentence, and reword it to
*"`<agent>` was refused `<tool>`"*. This touches `hub/ui` and the committed bundle. The sentence
wording has a test (`hub/ui/src/__tests__/eventSummary.test.ts:30-45`).

**Reproduce:** read the two lines cited above. Or trigger any Codex refusal outside a workspace and
compare the activity line with the row's copied JSON.

**FIXED 2026-09-23 (interactive session, UI-1).** `summaryForEvent('permission_denied', …)` now reads `<agent> was refused <tool>: <reason> — <detail>`: the agent is the one refused, never the one refusing, and `detail` (Codex's path or command, `agent_trigger.py`) is shown, cut at 120 characters. The existing two sentences in `eventSummary.test.ts` moved to the new wording; two new cases cover the detail and its bound. Passive rather than naming a decider, because the three emitters (runtime, harness, operator) do not all carry `decided_by`.

---

## F338 (D) — delivery reads an entry as queued and then marks it delivered by key, so a withdrawal that lands in between is answered 200 and delivered anyway

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- measured first (it reached), then delivery claimed with a conditional `UPDATE`; see FIXED at the end of this entry. Was: open, still read from the source only — re-read 2026-09-15 (night `ledger-conflicts`): `deliver_entries_with_run` is unchanged in shape, now at `hub/hub/inbound_queue.py:133-170` (moved by `98385cd`), selecting `state == "queued"` at `:142-152` before the `Run` is added at `:160`, then setting `delivered` on those objects at `:161-164`; still not measured and not driven.

Filed 2026-09-13 by the day window's `d6-repair`, while fixing F328. **Read from
the source. Not measured, and not driven.**

**The claim.** F328's repair makes every write that takes an entry out of `queued` *without
delivering it* one conditional statement (`inbound_queue._withdraw_if_queued`, and the scheduler's
counting write). Delivery was left as it was. `deliver_entries_with_run`
(`hub/hub/inbound_queue.py:125-162`) selects the entries `state == 'queued'`, then sets `delivered`
on those objects, which the commit writes by primary key. An operator's
`DELETE …/queue/entries/{id}` whose `UPDATE` commits after that select and before that commit
matches its row, is answered `200`, and has its `withdrawn` overwritten by `delivered`. The run
starts with input the operator was told they withdrew.

**Why it may not reach, and what is not established.** SQLite takes the write lock at a write, not
at a read. For a **review** dispatch, the session already wrote the reviewer's staging in the same
transaction, so the select runs under the lock and the window is closed. For a **plain** turn,
nothing ahead of the select is written, as far as `agent_trigger.py:1190-1241` shows. There,
`bind_run_to_task` and `record_response_run` stage writes only for a bound or delegated run. So the
select would run outside a write transaction. What has not been checked is whether an autoflush
before the select closes the window anyway. The window is also narrow: between two statements on
one connection, with no `await` of anything else in between.

**Why D.** It needs the operator to withdraw input within milliseconds of its delivery. A run then
does what the operator had asked it to do in the first place.

**A possible repair, not proposed.** The same shape as F328's. Deliver with
`UPDATE … WHERE id IN (…) AND state = 'queued'` and compare the matched count with the ids. Or take
the write lock first (write the `Run` row) and read after it. Measure first. F328's drive
(`scripts/drive/t_d6_0913_f328_withdraw_race.py`) is the pattern, with a plain turn in place of a
refused review.


**FIXED 2026-09-23 (interactive session, Round 3, group 3d).** **Measured first, and it reaches.** A
test commits an operator withdrawal from inside the window -- right after delivery's `SELECT`, on a
second session -- and on the old code `deliver_entries_with_run` did not raise: the entry ended
`delivered` over the committed `withdrawn`, with the run committed. So the autoflush question the
entry left open does not close the window on a plain turn. Repaired as F328 was, and as the entry's
own "possible repair" named: the run is added and flushed, then the entries are claimed with one
`UPDATE ... WHERE id IN (...) AND state = 'queued'`, and a matched count short of the ids rolls the
whole delivery back (claimed rows, the run, and the task binding the caller staged ahead of it) and
raises the existing `"queue changed before atomic delivery"` -- the same error the pre-write check
already raised, so the one caller's contract is unchanged. The returned objects are brought in line
with `set_committed_value`, so nothing is written back by primary key. Test:
`test_a_withdrawal_that_lands_between_delivery_read_and_write_is_not_overwritten`
(`test_a_withdrawal_and_a_give_up_do_not_both_win.py`, beside F328's two sides) -- on the old code
it fails with `DID NOT RAISE`. Not driven through the route.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** The lost claim surfaced as a bare `RuntimeError`, which
`turn_scheduler._attempt_turn` does not catch: `POST /messages` answered 500 after committing the
message, and `redrain_queued_agents`/reconciliation stopped at the first agent raising. Now
`inbound_queue.QueueChangedError` (both mismatch sites) and the trigger's one delivery call turns it
into a **transient** `TriggerAgentError`, so the scheduler re-reads what is still queued and counts
nothing. Test: `test_a_delivery_that_loses_its_claim_is_a_transient_refusal_to_the_scheduler` --
on the pre-follow-up code the error escapes `schedule_agent`.

---

## F341 (A) — every message to a Claude agent opens a Windows Terminal window, and it stays open

**Status:** fixed — `ensure_windowless_console()` before every ConPTY spawn, and the CLI starts the
Hub with `CREATE_NO_WINDOW` instead of `DETACHED_PROCESS`. Reported by the operator 2026-09-13
from real use: *"For every new message I sent the agent it's opening a new terminal window. It
flashes on the screen and the terminal remains open."*

**Mechanism.** `_hub_native_start` launched uvicorn with `DETACHED_PROCESS`, so the Hub had no
console. A Claude turn spawns through `PtySession.spawn` → `winpty.PtyProcess.spawn`, and
pywinpty's ConPTY backend opens every spawn with `AllocConsole()` then
`ShowWindow(GetConsoleWindow(), SW_HIDE)` "in case ConPTY is running in a GUI application"
(winpty-rs `src/pty/conpty/pty_impl.rs:92-96`). With the Windows 11 default-terminal setting
("Let Windows decide", `HKCU\Console\%%Startup` empty), `AllocConsole` hands the new console to
Windows Terminal — `svchost` starts `OpenConsole.exe -Embedding` — and the handle `SW_HIDE` is aimed
at is not the visible window. pywinpty `FreeConsole`s on teardown (`pty_impl.rs:694-696`), so the
next turn is console-less again and repeats it: one window per message.

**Measured on the operator's live Hub (PID 3488, port 8000), read-only.** 16 orphaned `conhost`
children of the Hub, each paired with an `OpenConsole.exe -Embedding` created in the same second as
one of 16 Architect runs' start times. Again at 15:18:05 on 2026-09-13: the Hub's winpty
`OpenConsole --headless` (a turn starting) and a `svchost`-parented `-Embedding` in the same second.

**Why `CREATE_NO_WINDOW` alone was not enough.** Every other spawn in `hub/hub/` already passed
`no_console_kwargs()` (Q6, `9a51d9c`), and `subprocess_windows.py`'s docstring said the ConPTY spawn
"already handled this". It did not: pywinpty makes that `CreateProcess` itself and takes no flags,
and `test_no_console_flash.py` only looked for `subprocess`/`asyncio` calls.

**The fix.** A console already attached makes pywinpty's `AllocConsole` fail harmlessly, and it
then frees nothing because it frees only what it allocated. `ensure_windowless_console()` borrows
the console of a `CREATE_NO_WINDOW` helper (`cmd.exe`, because `sys.executable` may be `pythonw`,
for which the flag is ignored) with `AttachConsole`, and keeps it. The CLI change makes the ordinary
launch hold one from birth; the helper covers any other launch (a bare `pythonw` uvicorn).

**Driven.** A `DETACHED_PROCESS` probe running the fixed code: no console before, a windowless one
after (38 ms, `GetConsoleWindow()` = 0), three real ConPTY spawns all returning their output, the
console still held at the end, and **no** `-Embedding` process created during it — against the
live Hub's same-second pairs above. Pinned by `hub/tests/test_windowless_console.py` (a real
console-less child, Windows-only), `test_pty_runner.py` (console before spawn, every platform),
`test_no_console_flash.py` (every `PtyProcess.spawn` scope calls it) and `test_hub_commands.py`
(the CLI's flags).

**Not yet on the operator's instance.** The live Hub loaded its Python at 2026-09-12 21:35; the fix
reaches it on the operator's next restart. The 16 lingering windows are leftovers and can be closed.

**Independent test (2026-09-13, separate Opus session, trial Hub): PASS.** Three launch shapes —
`python` + `DETACHED_PROCESS` (the old CLI), `python` + `CREATE_NO_WINDOW` (the new CLI) and
`pythonw` + `CREATE_NO_WINDOW` (the desktop shortcut) — across 8 real Haiku turns including two
concurrent pairs: 0 `-Embedding` processes, 0 new visible windows, 0 new conhost children, the
console never dropped between turns, and the agent's MCP tools worked in every turn. It measured
one thing the builder had not: **for the `pythonw` shape the CLI change does nothing** —
`CREATE_NO_WINDOW` is ignored for a GUI-subsystem program — so on the shortcut's path it is the
Hub-side `ensure_windowless_console()` that fixes F341, which is why both halves are kept. It also
found the guard failed silently: if `AttachConsole` never succeeded, or `cmd.exe` could not be
started, it returned with no console and no trace. It now logs a warning naming F341 in both cases,
and a helper that cannot start no longer propagates into the agent's spawn
(`test_no_console_to_borrow_is_logged_and_does_not_stop_the_spawn`).

## F342 (B) — typing "..." in the composer shows the first dot vanish, while the message sends all three

**Status:** fixed — `textarea, input, [contenteditable] { font-variant-ligatures: none; }` in
`hub/ui/src/index.css`. Reported by the operator 2026-09-13: *"When I type '...' it behaves very
weirdly. The third dot makes the first one disappears but when I hit enter it's on the message."*

**Mechanism.** Not React: the composer is a plain controlled `<textarea>` and its value is always
right. The field is set in JetBrains Mono (`@fontsource/jetbrains-mono`), whose contextual
alternates draw `..` and `...` as a ligature spread over blank placeholder glyphs. Chrome re-shapes
only the edited run of an editable field and reuses the rest, so the third dot left a mix of the
old `..` shaping and the new `...` one on screen: `Wait...` rendered `Wait ..`, `x...y` rendered
`x   .y`. Static text shapes correctly, and only a full re-shape (a zoom change) repaired a field.
A `contenteditable` breaks the same way, so switching element would not have helped.

**Driven** in the real composer (headless Chromium, typing with the keyboard): the committed bundle
before the fix showed `Wait ..` with value `Wait...`; the rebuilt one shows `Wait...` and computes
`font-variant-ligatures: none`. Read-only code keeps its ligatures.

## F343 (B) — the desktop window has no right-click menu, so a misspelt word can be underlined and never corrected

**Status:** fixed — `_enable_default_context_menus` (`src/agentweave/cli.py`). Reported by the
operator 2026-09-13: *"The red underline appears showing that the word is wrong but the correct
with right click does not work."*

**Mechanism.** Not the composer. The operator uses the pywebview window the desktop shortcut opens
(the live Hub's parent, PID 2800, is the CLI holding `webview.start()`), and pywebview 6.2.1's
WebView2 backend writes `settings.AreDefaultContextMenusEnabled = _state['debug']`
(`webview/platforms/edgechromium.py:288`). No debug, no context menu — and the context menu is the
only route to a spelling suggestion. WebView2's spellchecker still runs, hence the underline. An
investigation of the React composer found nothing, correctly: it is a plain controlled `<textarea>`.

**The fix, and the measurement that changed it.** The first version set the menu on in
`before_load`, which pywebview fires from `on_navigation_completed`. Measured with WebView2's own
`ContextMenuRequested` event: the setting read back `True` and **no menu was ever requested** — a
change after the first navigation does not reach the page, and a single-page app never navigates
again. The shipped version subscribes to `CoreWebView2InitializationCompleted` from `before_show`
(fired synchronously once the form exists, before initialisation completes), so it runs straight
after pywebview's own handler and before the first `NavigationStarting`. `debug=True` was rejected:
it also brings DevTools, "Inspect" and the browser accelerator keys.

**Driven** with a real WebView2 window placed off-screen (`scratchpad` probe; a first on-screen
attempt was abandoned), right-click synthesised over CDP and the menu read from
`ContextMenuRequested` — the positive control (`debug=True`) is what showed the instrument can see a
menu at all:

| variant | menu requested | spelling items on a misspelt word | `inspectElement` |
|---|---|---|---|
| pywebview default | none | — | — |
| `debug=True` (control) | yes | 3 | yes |
| fixed, `before_load` (first attempt) | **none**, setting reads `True` | — | — |
| fixed, shipped | yes | 3 | **no** |

**Not driven:** *choosing* a suggestion. Executing the spellcheck command from inside
`ContextMenuRequested` closed the CDP session. Replacement is Chromium's own `insertReplacementText`
into a controlled textarea, which React's `onChange` receives like typing.

**Also not covered:** a browser tab or `--app` window never had this — both give Chromium's own menu.

## F344 (B) — nothing in the desktop window can be selected, so an agent's answer cannot be copied

**Status:** fixed — `webview.create_window(..., text_select=True)`. Reported by the operator
2026-09-13: *"I can't copy a text from the agent answer. I hover over and I can't select and copy
anything."*

**Mechanism.** pywebview's `text_select` defaults to `False`, and `webview/js/customize.js` then
injects `body { user-select: none; cursor: default }` into every page it loads. So every non-input
element in the app — the whole transcript — refused selection.

**Driven** in a real WebView2 window: with pywebview's defaults `getComputedStyle(body).userSelect`
is `none` and a mouse drag across a paragraph selects `""`; with `text_select=True` it is `auto` and
the same drag selects the whole sentence. Pinned by `tests/test_cli.py`
(`test_native_window_lets_text_be_selected`).

**Two more places selection failed, found in a browser, where the window's cause does not apply.**
An investigation driving the bundles in headless Chromium found the answer text itself selectable,
and two real blockers elsewhere — both fixed in the same commit as F342/F345:
- *An expanded work row.* `WorkRow` (`AgentTimeline.tsx`) rendered its whole expanded body — the
  command, the tool's output, a diff — **inside** the row's `<button>`. Chrome will not start a
  selection inside a button, and the mouseup that ended the attempt clicked it and folded the row.
  Only the header is the button now; pinned by `agentTimeline.test.tsx` ("keeps the command and its
  output outside the button"), which fails on the old structure.
- *A leaked drag style.* `PaneResizer` sets `body { user-select: none }` for a drag and cleared it
  only in its own pointerup — so a divider unmounted mid-drag, or one whose capture was taken away,
  left every page unselectable. It now clears on unmount and on `lostpointercapture`; pinned in
  `PaneResizer.test.tsx`.

## F345 (B) — a pending question grows without bound in the composer's column, squeezing the conversation to nothing and pushing the composer off screen

**Status:** fixed — the question and permission cards float in a tray over the conversation's foot
(`AgentOutputPanel.tsx`, `.conversation-interject-tray` in `index.css`). Reported by the operator
2026-09-13: *"When I have a agent using ask user the question box is kind of hard stuck. It eats
the screen away with a big black rectangle. It would be nice to have it floating on top of the
agent conversation but we should be able also to scroll to the end of the conversations. I know
that T3 has that model of floating on top but then you can't see the last messages."*

**Mechanism.** Both cards were stacked inside `.conversation-composer-fade`, a `shrink-0` flex
child, above the composer. `.conversation-interject` had no height limit, and `ask_user` puts no
limit on a question's length or on eight options with descriptions. The conversation area
(`min-h-0 flex-1`) gave up all its height to make room, and once the header plus that column
exceeded the panel, the composer was pushed past the panel's `overflow-hidden` bottom edge. The
"black rectangle" is the dark theme's `--surface-2`, drawn tall. Identical in 1.1.0.

**The design, and the operator's T3 point.** The cards now sit in an absolutely positioned tray
over the bottom of the conversation, directly above the composer: capped at
`min(28rem, 60%)` of the conversation's height, scrolling inside itself with the question's header
pinned, and foldable to one line that keeps the question's text (`AgentQuestionCard`, keyed by
question so the next one arrives open; number-key shortcuts are off while folded). What answers
the operator's objection to T3 is the inset: the tray's measured height is reserved by a spacer
below the newest entry, and subtracted from the room that pins the newest turn to the top, so
scrolled to the end the last message sits *above* the tray rather than under it.

**Driven** against the trial Hub with a long 8-option question from `httpagent` over a 50-entry
conversation, 1280x800, headless Chromium, before (committed bundle) and after (rebuilt bundle):

| | before | after, open | after, folded |
|---|---|---|---|
| conversation height | **44 px** | 477 px | 477 px |
| composer on screen | **no** (top at 828 of 800) | yes | yes |
| newest turn's foot clear of the card | — | yes (298 < 319) | yes (535 < 557) |
| card | 641 px in flow | capped, scrolls inside | 44 px |

Light and dark both checked by screenshot. Pinned by `interjectTray.test.tsx` (tray placement,
no tray for another agent, and the inset arithmetic: 600 − 208 − 120 − 24 = 248) and
`agentQuestionCard.test.tsx` (folding).

**Not done:** the permission card is not foldable. It is the one with a timeout, its detail is
already capped at 10rem, and the tray's cap and scroll bound a stack of them.

**Independent test (2026-09-13, separate Opus session): PARTIAL — the first version hid the
question in narrow windows.** At 768px wide and up it held (real two-question `ask_user` batch
answered through the composer while folded; two real permission requests beside a long question;
scrolled-up reader not moved; no gap after dismissal). Below 768px the project rail stacks above the
panel and the conversation shrinks to tens of pixels, and the floating column's `60%` cap went with
it: 26px at 700×720, 41px at 560×800, **0px at 420/500×560 with the fold control unreachable**.

**Second version.** The tray floats only when the conversation has at least 240px (where 60% gives
the 144px the inline placement tops out at); below that it sits inline in the composer column with
its `max-height` set to the room the conversation had, between 72px (its header and first line)
and 144px. Taking the conversation's room and not the composer's is the point: the send button is
what confirms a chosen option, so a question that pushes it off the panel cannot be answered. The
room is computed from sizes the tray does not move — panel height, less header, less the composer
area with an inline tray taken back out — because reading the conversation body's own height
either flips (floating measures room, inline measures less) or sticks (inline, the body bottoms
out at its padding and the shortfall disappears); a mutation computing it from the body alone fails
`floats again once the window gives the conversation room`. Driven on the rebuilt bundle:

| viewport | placement | question visible | send on screen |
|---|---|---|---|
| 1280×800 / 1280×600 / 768×800 | float | 281 / 161 / 214 px | yes |
| 700×720, 640×800, 560×800 | inline | 72 px, fold reachable | **yes** |
| 500×560, 420×560 | inline | 72 px, fold reachable | no — nor with no question at all (F350) |

A live page resized across the threshold five times settled on the first measurement each time.

**The build stamp committed with `e9f71c0` was stale on arrival**, also found by the independent
pass: `ui_source_fingerprint` enumerated tracked files only, and `pendingPermissions.ts` was stamped
before it was `git add`ed. The fingerprint now lists what a build reads — tracked files still on
disk plus untracked files `.gitignore` does not exclude — so a stamp recorded before `git add` of a
new file, or of a deletion, still holds after the commit (three tests in
`test_ui_build_stamp.py`). The bundle is re-stamped, and `AW_CHECK_UI_BUNDLE=1` passes.

## F346 (C) — the route-reachability instrument lets a sibling route's literal satisfy a `{param}` slot, so it undercounts clientless routes by one

**Status:** fixed 40e9efa (2026-09-22; see the foot). Was: open. Filed 2026-09-13 by a DECIDE session. The defect was first noticed in handoff 0120
(2026-09-11) and carried unfiled through two handoffs. **Measured**, not only read.

`segment_match` in `scripts/drive/n10_route_reachability.py:201-210` returns `"exact"` as soon as the
**route** segment is a path parameter (`:202-203`), before it looks at the URL segment at all. So a
client URL whose segment at that position is a *literal* (`…/runners/launchability`) is counted as
reaching the parameterised sibling (`…/runners/{runner_id}`), and that route leaves the "no client
anywhere" list even though nothing calls it.

**Reproduction.** Run `py -3.11 scripts/drive/n10_route_reachability.py`. It reports **35** under
*"no client anywhere in the repo"*. Import the module, replace `segment_match` with one that answers
a `{param}` route segment only for a URL segment that is a whole placeholder (`*`) or equal text,
and call `main()`. It then reports **36**, and the one route added is
`GET /api/v1/projects/{project_id}/runners/{runner_id}`. Both lists were compared line by line
(2026-09-13), and no other route moved.

**Why it matters.** 35 is the figure quoted as R-1's *"35 clientless routes"* (`spec-queue/DECISIONS.md`
R-1 and the scope verdict) and in handoff 0120's capability assessment (*"36 have no client
anywhere"* was the corrected figure there). A ratchet built on this instrument would freeze a count
that is one short, and would stay green while that route stays clientless.

**Shape of a fix (a sketch, not verified beyond the measurement above):** a parameter segment
matches a placeholder or `~`-glued URL segment, never a bare literal that a sibling route declares.

**Fixed 2026-09-22, `40e9efa`.** `segment_match` fills a `{param}` route segment only from a whole (`*`) or glued (`~`) interpolation, never from a bare literal. Output diffed before and after: exactly one route moved, `GET /api/v1/projects/{project_id}/runners/{runner_id}`, into *no client anywhere*. **The figures are 34 → 35 today, not 35 → 36**, because routes have been removed since 2026-09-13 (today's `PATCH /queue/settings`, F196). The 35 quoted in `spec-queue/DECISIONS.md` R-1 was one short at the time; the true count then was 36.

**Note (Opus review, 2026-09-22).** The rule is stricter than the sketch above: it refuses *any* bare literal, not only one a sibling route declares. Against today's clients that costs nothing, because every literal it stopped matching has a literal sibling route. A future client that hardcodes a real value for a parameter would read as clientless.

## F347 (B) — a project whose repository has no commit yet refuses every agent turn with git's plumbing error, including the message asking the agent to fix it

**Status:** fixed (this commit) [Round 2, 2026-09-22] — option (a) built; see FIXED at the end of
this entry. The decision's second half (the held message) was left to a later round and stays open
there. Filed 2026-09-13 by a DECIDE session, from the operator's own day-to-day use on
their `:8000` Hub (project `LoopEngine`, `proj-03b9c6a6c37a`). **Seen live, not driven by a
harness.** The evidence was read from that Hub's database read-only, and the repository was
inspected with `git`.

**What happened.** A project that started as a plain directory had its Architect agent run
`git init` in it at 16:42 on 2026-09-13, and nothing was committed. `main` was unborn. From the next
turn on, every one of that agent's turns was refused before it spawned. The queue entry's waiting
reason read:

> Could not prepare Architect's own workspace: git worktree add -b agentweave/Architect
> C:\Users\huida\Documents\projects\LoopEngine\.agentweave\worktrees\Architect HEAD failed (128):
> fatal: invalid reference: HEAD

The operator's message asking the agent to repair it (*"invalid reference (head) upon trying to
create a git tree"*) queued behind the same refusal. The agent could not fix what blocked it, and
the operator had to leave the product to make a first commit.

**Where.** `ensure_worktree` (`hub/hub/worktrees.py:361-362`) runs `git worktree add -b <branch>
<path> HEAD` with no check that `HEAD` resolves. `IsolationUnavailableError` carries git's own
message (`worktrees.py:80`), and `agent_trigger.py:970` prefixes it with *"Could not prepare
{agent}'s own workspace"*. No code path in `hub/hub` handles an unborn `HEAD`. A search for
`unborn`, `no commits` and `invalid reference` finds nothing in `hub/hub` or this ledger.

**Why B.** It is the ordinary first day of a project that becomes a repository. Every turn of every
agent that needs isolation is refused. The sentence names git's plumbing rather than what the
operator would change, which breaks the rule `worktrees.py`'s own docstring states: *"this module
is where the operator-facing sentence is written."*

**Reproduce.** Make a fresh directory and register it as a project. Run one agent turn, which runs
un-isolated because there is no repository. Run `git init` in the directory without committing, then
send the agent any message. The entry stays `queued` with the reason above. **Workaround, applied
2026-09-13:** one commit in the project (`4c56590 Initial commit`, `spec/` only). After it, `HEAD`
resolves and `.agentweave/worktrees/` is empty, so the next attempt can provision the checkout.
That the queued turns then delivered was **not yet observed** when this was filed.
*Observed at 17:44 the same day, read-only from the live database:* entry 23 went `delivered`, and
the Architect's newest run (`run-113f7e6b75f7`) `completed` with `workspace_dir` set to
`.agentweave/worktrees/Architect`. The operator's own message about the error, entry 24, went
`withdrawn`; this session did not withdraw it.

**Shape of a fix (a sketch, not verified).** The choice between these is a product decision:
- **(a)** Refuse with a sentence that names the repair: *"<project> is a git repository with no
  commit yet. Make a first commit, and the turn will start."* This fits `repo_hygiene.py`'s stance
  that the Hub does not create commits in the operator's repository.
- **(b)** Provision the worktree on an orphan branch when `HEAD` is unborn.

Either way, the pass that refuses should not hold the operator's message behind a condition only
the operator can clear without saying so.

**DECIDED 2026-09-13 ~22:45, by the operator, in session: option (a).** Refuse, with a sentence that
names the repair, and create no commit and no orphan branch. See `spec-queue/DECISIONS.md`
`### F347, decided 2026-09-13 evening`. It is now a decided B, and no spec loop has taken it yet.


**FIXED 2026-09-22 (interactive session, Round 2).** Re-verified first, against HEAD `2c99b15`: a
`git init`-ed directory with nothing committed still raised `GitCommandError: git worktree add ...
failed (128): fatal: invalid reference: HEAD`, exactly as filed.

- **`worktrees._refuse_an_unborn_head`** asks `git rev-parse --verify --quiet HEAD`
  (`_has_a_commit`) before provisioning, and raises `IsolationUnavailableError` with the sentence
  the verdict asked for: *"<project> is a git repository with no commit yet. Make a first commit in
  <path>, and the turn will start."* No commit is written and no orphan branch is created, which is
  option (b), rejected.
- **The task checkout had the same hole, and this entry did not record it.** Measured while fixing:
  `ensure_task_worktree` raised `fatal: invalid reference: main` on the same repository, because
  `base` cannot resolve either when nothing is committed. Both entry points now call the guard.
- **The sentence names no agent and no task, deliberately.** Both callers are already wrapped by a
  prefix that names the scope (`api/v1/agent_trigger.py:963-981`: *"Could not prepare {agent}'s own
  workspace: ..."* and *"Could not prepare the checkout for task {id}: ..."*), so naming it again
  would stutter. The tests assert that absence rather than leaving it to taste.
- **Tests:** four in `hub/tests/test_a_blocked_workspace_refusal_states_its_remedy.py`, the file
  whose subject is "each obstruction states its own remedy, and the remedy is true". Following that
  file's discipline, each performs the operator's half — one commit — and then calls the real
  function again, so the promise *"and the turn will start"* is measured, not trusted. One asserts
  the refusal leaves no commit, no branch and no `.agentweave/worktrees/` behind. **All four fail at
  `2c99b15`** with git's plumbing error; 7 passed, 2 skipped (symlinks, Windows) after the fix.
- **Still open, and not this commit's business:** the refusing pass holds the operator's own message
  behind a condition only they can clear, without saying so. `DECISIONS.md` left that half to a
  later round, and it is the reason this entry's last paragraph still stands.

**Opus review, applied the same session.** The reviewer confirmed the guard's placement (no other
caller can reach `git worktree add` with an unresolvable ref: `ensure_review_checkout` refuses
earlier through `resolve_review_commit`, and the idempotent early-returns need a prior successful
provision), that the refusal reaches the operator with the caller's prefix and no stutter, and that
no commit or branch is left behind. It also found the guard asking the wrong question:

- **An unborn `HEAD` is not "no commit in the repository".** `git checkout --orphan` leaves `HEAD`
  unborn while other branches carry commits, and `git worktree add <path> <branch>` still succeeds
  there — so reprovisioning an agent whose branch already existed used to work and was now refused,
  with a sentence telling the operator to make a first commit they had already made.
- **The guard now asks about the ref the call actually uses**: the agent's branch when it is being
  reused and `HEAD` when it is being created; the task's branch when it is being resumed and `base`
  when it is being cut. `base` is a parameter and can name a deleted branch, which is a third state
  again — it gets its own sentence, because another commit would not fix it.
- **Two refusals, two repairs.** "No commit anywhere" (asked of `rev-list -n 1 --all`, not of
  `HEAD`) keeps the original sentence. A ref that does not resolve in a repository that *has*
  commits names the ref instead. Two tests pin exactly these: an orphan-branch repository whose
  agent branch provisions cleanly, and a deleted `base` that is told so.
- **The reordering broke a promise the existing test caught**: moving the guard below
  `path.parent.mkdir` left an empty `.agentweave/worktrees/` behind on a refusal, which
  `test_the_refusal_creates_no_commit_and_no_branch` asserts against. The `mkdir` now follows the
  guard on both paths.
- Also fixed from the review: the sentence began with a space for a project at a drive root
  (`Path("C:/").name` is `""`); it falls back to the full path.

## F348 (B) — following switches itself off during every running turn, so the newest text drifts below the fold (and under the question tray)

**Status:** fixed (this commit) [UI-1, 2026-09-23] — the tail spacer leaves room for everything below the newest turn, the working indicator included; see FIXED at the end of this entry. Was: open. Found 2026-09-13 by the independent test pass over F341–F345; it predates them.

**Measured.** While a reply streams, the view settles 43–84px short of the bottom — over the 40px
threshold in `handleScroll` (`AgentOutputPanel.tsx`, `atBottom = … < 40`) — so `autoscroll` turns
itself off and "Jump to newest" appears: 13 of 17 samples during one streamed reply, with no tray
at all. With the F345 tray open, the newest text then sits under the tray until the operator jumps;
after a jump it is clear (indicator foot 357, tray top 377).

**Suspected mechanism, not yet confirmed by a probe.** The working indicator renders at the foot
of the timeline but outside `[data-turn-boundary]`, so `measureTail`'s arithmetic (viewport − newest
turn − gap) does not count it: pinning the newest turn's top leaves the indicator's height of
content below the bottom, which reads as "the operator scrolled up". A repair would either measure
the indicator into the turn, or count it in the spacer; it has to keep the 2026-08-20/21
"bouncing scroll" regressions in `conversationControls.test.tsx` green.

**FIXED 2026-09-23 (interactive session, UI-1).** The suspected mechanism, confirmed by the arithmetic: with the newest turn pinned, the distance from the bottom was `8` (top padding) `+ 22` (the scroller's bottom padding) `- 24` (the spacer's gap) `+ 21 + 16` (the indicator and its column gap) `= 43px`, over `handleScroll`'s 40; without the indicator it is 6px. New `tailHeight(newest)` in `AgentOutputPanel.tsx` measures the newest turn plus every rendered sibling after it in the timeline column (indicator, queued entries, the waiting line), each with the column's `row-gap`; `measureTail` sizes the spacer from it. The ResizeObserver also watches the column, because the indicator appearing or going resizes the column and not the turn. The 2026-08-20/21 bouncing-scroll tests in `conversationControls.test.tsx` and `interjectTray.test.tsx` stay green. Test: `leaves room for the working indicator below the newest turn, not only for the turn` (spacer 440px; 456px on the old code). **Not yet confirmed in a browser**: that is UI-1's closing browser check.

## F349 (B) — two agent triggers at the same moment can answer 500 "database is locked" while the message is delivered anyway

**Status:** fixed 2026-10-13 (build window, iterations 5-7; Tier 2). fef65d4 (2026-09-22): the measured 500 on `UPDATE projects SET last_seen_at` cannot happen now. Slice 1 of the remainder built 2026-10-13 (iteration 5): `POST /agent/trigger` now writes its post-commit event through `persist_accepted_event` and starts the turn through `schedule_accepted`, so a locked database after the entry commit answers 200 `queued` (or `running` when a run had already taken the input), the Hub retries at 1 s, 5 s, 30 s for a transient error only, and the deferred-schedule set is the backstop; `hub/tests/test_accepted_input_is_answered_as_accepted.py`, 10 tests, 6 red on the unguarded route. Slice 2 built 2026-10-13 (iteration 6): the six other post-commit sites (`messages.py`, `agents.py` request and runner rebind, `questions.py`'s `announce_queued_answer` plus the answer/decline routes' own events, `inbound_queue.py` release, `accounting.py` budget; design D4) use `schedule_accepted` and `persist_accepted_event`; 11 parametrised tests in the same file, 10 red before (the request route already caught its schedule), and `scripts/drive/d1013_f349_sites.py` 12/12 on a scratch Hub with one Haiku turn. Slice 3 built 2026-10-13 (iteration 7): the firing path (`scheduler.py` `_do_fire_job`, `_start_additional_turns`, `_stage_selection`, the loop-edit audit; design D6) starts turns through `schedule_accepted` and writes every post-commit event through `persist_accepted_event`, and a raise after the entry commit leaves the `JobRun` `in_progress` instead of `failed`; 6 more tests in the same file, 5 red before (the terminal refusal control green), and `scripts/drive/d1013_f349_firing.py` 10/10 on a scratch Hub with one Haiku turn. Not driven: a real lock between commit and schedule (SQLite's 30 s busy wait absorbs one; the lock is injected in tests). The change is archived; its spec deltas were not applied to `spec/capabilities/` (loop-firing-accountability, runtime-diagnostics, agent-conversation-workspace). Found 2026-09-13 by the independent test pass (trial Hub); it predates F341–F345.

**Measured.** Two `POST …/agent/trigger` requests fired together: one returned **500** with
`database is locked`, raised from the autoflushed `UPDATE projects SET last_seen_at`; the message
was nonetheless delivered ten seconds later as `run-75e901d71e7c`. So the operator is told the send
failed for a send that happened — the F108 shape (a route's status disagreeing with its effect). A
repair needs to decide whether the `last_seen_at` write belongs inside the trigger's transaction at
all, and must answer with what actually happened to the message. See DEAD-ENDS on the two
`database is locked` mechanisms before assuming a holder exists.

**Observed again 2026-09-14** (day window O-3, LoopEngine on `:8000`, read-only). The same error
also ends runs, not just trigger requests. `run-539bd1d44ea1` (35 minutes, 304 outputs),
`run-d5f4b2972125` and `run-7695d6f7b4b4` each failed on `(sqlite3.OperationalError) database is
locked` raised by `INSERT INTO agent_outputs`. What the Hub then does with such a run is **F359**.

**Partially fixed 2026-09-22 (interactive session), `fef65d4`.** The measured failure was `resolve_project_workspace` stamping `project.last_seen_at = now` on every call. The trigger route resolves twice, and its next query autoflushed the UPDATE, starting SQLite's write transaction there and holding the lock through the rest of the route (including the synchronous `worktrees.is_git_repo` subprocess) until the entry's commit. The resolver no longer writes `last_seen_at`. Nothing reads it but the projects API, and open/relocate still stamp it via `project_lifecycle._observe`. So the trigger route's first write is now its entry commit. **The suite could not have caught it:** `_default_project_workspace` fakes the resolver in every test. `test_resolving_a_workspace_writes_nothing.py` restores the real one. Before the fix it saw the project modified and recorded **two** `UPDATE projects` per trigger; after, none. 41 resolver-related files: 630 passed, 5 skipped. **Not done:**
- **A failure after `trigger_agent`'s entry commit (`agent_trigger.py` ~1515) still answers 500 for input that is queued.** `persist_event` and `schedule_agent` both run after it. Answering `queued` instead is only true if something will drain the entry, and nothing on a timer does (see `_execute_run`'s spawn-failure comment on `redrain_queued_agents`). That needs its own design, not a one-line catch.
- **The 500 itself was never reproduced in a test**, only the write that caused it. Concurrent `database is locked` from other writers (the run-output INSERTs in the 2026-09-14 observation) is F359's and F292's.
- Not driven live.

**Re-verified 2026-10-15** (full sweep, G7: Resilience, scratch Hub `:8037`): fix holds. 6 concurrent triggers on a running agent all returned 200 `queued`, each with its own entry, none 500. An external lock on the database still gives a bare 500 on every route (F627, not this finding).

## F351 (A) — the scheduler's job store shares the SQLite file and is driven synchronously on the event loop, so one lock collision loses a new job — or stops every job for good

**Status:** fixed — the job store is APScheduler's `MemoryJobStore` (`JobScheduler.start`), and driven. Reported by the operator 2026-09-13: *"An agent created a
flow with a loop it should fire every 5 minutes but it didn't fire at all. I had to manually run
it."*

**The live state (operator's Hub, port 8000, read-only).** `job-79fdadb95db9` (`loopengine-build`,
`*/5 * * * *`, enabled, created by agent `dev` in `run-113f7e6b75f7` via `create_flow`) at
16:38:02.92 UTC with loop `loop-103ecb8aeb89`. Its first slot, 16:40, produced nothing; the only
`job_runs` row is the operator's manual run at 16:44:56. **`apscheduler_jobs` holds 0 rows** — the
job never reached the scheduler. The tell is in `event_logs`: `job_created`, persisted immediately
after `_hand_job_to_scheduler`, landed at **16:38:09.21 — 6.3 s** after the row, and pysqlite's
default busy timeout is 5 s. The Hub's stdout goes to `DEVNULL`, so the error it logged is gone.

**Mechanism.** `JobScheduler` uses APScheduler's `SQLAlchemyJobStore` on a *second, synchronous*
engine pointed at the same file (journal mode `delete`), and calls it on the event loop:
`JobScheduler.add_job` → `AsyncIOScheduler.add_job` → an INSERT. If any other coroutine has a write
transaction open at that instant — it inserted, and needs one more `await` to commit — that commit
can never run, because the loop is blocked inside the INSERT waiting for its lock. The INSERT gives
up after 5 s with `database is locked`; `add_job` logs and returns `False`; the job stays `enabled`
in `ai_jobs` and absent from the scheduler until a restart. `_hand_job_to_scheduler`'s commit-first
fix (`0757be5`, 2026-08-28) removed the request deadlocking *itself*; it cannot help when another
session holds the lock, which an agent streaming its turn — the very agent calling `create_flow` —
makes likely.

**The worse half.** APScheduler 3.11.2's `_process_jobs` also writes the store on every firing
(`jobstore.update_job(job)`, unguarded, `schedulers/base.py` ~L1227). A collision there raises out
of `AsyncIOScheduler.wakeup`, `_start_timer` is never re-armed, and **the scheduler stops waking for
every job** until something else calls `wakeup()`.

**Reproduced** (`scratchpad/f351/`, throwaway databases, the Hub's own code):

| experiment | result |
|---|---|
| `_hand_job_to_scheduler` while another async session holds an uncommitted insert (1 s, and even 0 s) | 5.49 s / 5.52 s, `database is locked`, `apscheduler_jobs` empty |
| same, no concurrent writer (control) | 0.01 s, row present |
| `AsyncIOScheduler` + `SQLAlchemyJobStore`, 2 s interval, one writer across one firing | fired **once**, then `Exception in callback AsyncIOScheduler.wakeup` — never again in 20 s |
| same with `MemoryJobStore` | fired every 2 s, 10/10 |

**The repair.** Replace the SQLAlchemy job store with APScheduler's
`MemoryJobStore`. The persistent store is redundant: `ai_jobs` is already the source of truth and
`JobScheduler.start` re-registers every enabled job from it at startup, so nothing is lost but
APScheduler's own catch-up of a firing missed while the Hub was down (≤ `misfire_grace_time`, 60 s).
It takes every scheduler read and write off the database, so neither half can recur, and removes
`_get_sync_engine` with it. No test depends on `apscheduler_jobs`.

**Pinned** by `hub/tests/test_scheduler_store_is_in_memory.py`, which drives the real
`JobScheduler.start()` against the suite's file-backed database with a real concurrent writer — the
stand-in in `test_job_reaches_the_scheduler.py` takes no lock, which is how this got past it. With
the old store put back, the lock test fails *"the job never reached the scheduler"* and the store
test fails; with the fix, registration under the held lock takes < 1 s.

**Driven** on the trial Hub (fixed code, stdout captured): Haiku `mcpagent`, mid-turn
(`run-666b110563c2`), called `create_loop` for an every-minute loop. Job row → `job_created` event:
**0.05 s** (the operator's Hub: 6.3 s). Scheduled firings at **17:37:00, 17:38:00, 17:39:00**, each a
completed turn; nothing matching `Failed to add job` / `database is locked` in the Hub's log.
Stopping the loop at 17:39:29 unregistered it — no firing at 17:40:00. Test project settings
restored afterwards.

**On the operator's Hub:** the job registers on the next restart, which also loads this fix.

**Also seen:** one run of the job/loop/flow/scheduler subset had a single failure,
`test_flow_holds_the_loop_requirements.py::test_one_turn_finishing_answers_for_itself_and_not_for_its_siblings`;
it passed alone four times and in a full re-run of the subset (455 passed). Its output was not
captured, so it is recorded as an intermittent rather than classified. The conftest's own note that
"a test that leaves a live `JobScheduler`" can hold a connection into the next test's reset referred
to the database store this removes; whether that thins the F292 flake is not measured.

**The second half, caught live, and the restart that cleared it (2026-09-13, operator's Hub).** After
the investigation the job did reach the scheduler once (a 17:25 scheduled firing, `dev`, working
until 17:35:21); 17:30 and 17:35 were correctly silent with that turn in flight. Then nothing: no
firing at 17:40 or 17:45 with nothing running — the operator's own manual firing at 17:46 started a
review immediately, so a live scheduler would have too — nor at 18:05 or 18:10. The heartbeat
settles it: `ai_jobs.next_run` advances on *every* scheduled firing, including the in-flight branch
that records no `job_runs` row, and it stood at **17:50** (the manual run's value) from 17:46 until
the restart. The scheduler's timer had died, most likely on the 17:30 or 17:35 firing's store write
while `dev` was writing.

Restarted at the operator's request at 18:15 UTC, via the desktop shortcut through Explorer (Hub PID
12480 under `pythonw -m agentweave` 19512, parent `explorer`), with no run in flight. The 18:20 and
18:25 slots fired on schedule and `next_run` moved to 18:25 then 18:30. The flow did no work because
its first task is `under_review` with a reviewer whose turn ended undecided — it said so on each
firing (`review_unstaffed`, and a `skipped` row naming the three ways out). That is the flow waiting
on the operator, not this finding.

## F352 (A) — a flow counts an agent busy for holding any live task anywhere in the project, so backlog outside the flow starves it of reviewers — and the reason it gives names nobody

**Status:** **both halves fixed.** The definition half is fixed `4b59ee0`
(`a-task-nothing-will-move-holds-nobody`, driven and archived 2026-09-15). The visibility half is
fixed by `an-unstaffed-review-names-its-holders` (rung 3's five-clause reason, groups 1-6,
2026-09-23), driven live D-6: the reason now names every booked/held agent and what it holds,
instead of "either running a turn, already holding active work, or is the one that completed this
task." The operator's flow was unblocked by hand at the time. Reported by the operator 2026-09-13:
*"The loop got stuck because of task assignment."* [checked 2026-09-22, D-4: `4b59ee0` fixed the
definition half only, visibility still open. Closed 2026-09-23 by the change named above.]

**Measured on the operator's Hub (LoopEngine, `loop-103ecb8aeb89`).** Fourteen firings, 21:20 to
22:30 UTC, each recorded `review_unstaffed` for the two finished tasks the rest of the flow waited on
(`task-611ae46fe0fb` by `dev`, `task-c8d4a3d70c19` by `Architect`): *"could not staff this step: no
agent is free to take it. Every agent on the roster is either running a turn, already holding active
work, or is the one that completed this task and so may not review it."* No turn was running. What
held every agent, all of it outside the flow except the first:

| agent | held |
|---|---|
| Architect | `task-9e89a55ccc84` `under_review` — a review waiting on an operator decision (Copilot) |
| dev | two `in_progress` follow-ups with no turn running, one `pending` — `loop_id` NULL |
| dev_2 | five `pending` follow-ups, three of them duplicates — `loop_id` NULL |
| tester | `task-5420e60359c1` `in_progress` — superseded; its replacement says so in its description |

**Mechanism.** `_agents_that_are_free` (`scheduler.py` ~L977) is *not running* **and** *not the
assignee of any task in `LIVE_STATUSES`* (`pending`, `assigned`, `in_progress`, `revision_needed`,
`under_review`) **project-wide**. Rung 2 of `resolve_reviewer` and every selection past the job's
default agent draw only from it. A task outside the flow is never worked by the flow — `loop_id` is
write-once — so an agent assigned one is withdrawn from the flow's pool until something else moves
that task; a `pending` row is a reservation, not work, and an `in_progress` row with no turn is a
record, not evidence of one (F154's own sentence). Agents create exactly these rows as follow-ups.

**Why nobody could see it.** The sentence names no agent and no task. The reviewing agent,
asked to diagnose, blamed finished tasks staying assigned to their authors — `completed` is not a
live status and holds nobody — and told the operator to reassign, which the product does not offer
(F353). An hour of a stalled flow, diagnosed wrongly by the agent and not at all by the product.

**Unblocked at the operator's request (22:33 UTC):** `POST …/tasks/task-611ae46fe0fb/land` and
`…/task-c8d4a3d70c19/land` (both approved; merged `166cc78`, `79296eb` into the project's `main`),
and `task-5420e60359c1` → `rejected` as superseded, which freed tester. The 22:35 firing started
`dev` on `task-49b0567ce119` and `tester` on `task-c9787d4be5e1` in parallel.

**Still true, so it will recur:** Architect stays held by the Copilot review until the operator
decides it, and dev_2 by five tasks nothing will start. With two agents in the pool, the flow can
cross-review only while dev and tester finish at compatible times.

**What a repair has to decide, not proposed.** Whether "free" is scoped to the flow (or to loops)
rather than the project; whether `pending`-with-assignee counts as holding; whether an `in_progress`
row with no running or queued turn does; and, whatever else changes, the unstaffed sentence has to
name the holdings — agent → task — because it is the whole of what the operator is shown.

**Observed again 2026-09-14** (day window O-3, `spec-queue/observations/2026-09-14-LoopEngine.md`,
read-only from `:8000`). The same sentence was recorded **180** times between 2026-09-13 17:25 and
2026-09-14 08:40 UTC, not fourteen, and it kept recurring after the 22:33 unblocking. `dev_2` has
not run since 23:50 UTC, and it holds four `pending` tasks with no `loop_id` that nothing will
start (`task-62b60f9dba50`, `task-88eff732b7f5`, `task-7673e4f80905`, `task-a7c2a75726a2`). Two of
them describe the same change by title. F352's shape is the flow's largest single stall on this
project. It is built on 2026-09-14 together with F353, because both repairs rewrite the same
unstaffed sentence.

**Split by R1, 2026-09-14** (`openspec/changes/an-unstaffed-review-names-its-holders`).
- **The visibility half is taken into that change,** with F353, F334 and the new F365. It covers
  the sentence naming each agent and its holdings, a remedy that exists, and one record per task.
  **That half is fixed** — `a-refusal-names-a-remedy-that-works`, `b29c096`, archived 2026-09-16;
  see F353's and F334's and F365's own Status lines.
- **The definition of "free" is not taken.** `agent-flows` states the project-wide rule, and its
  design rejected *not running* alone on the operator's own pile-up objection. So which holdings
  count is an **OPERATOR QUESTION**, laid out with five options and a recommendation in that
  change's `proposal.md`.
- **This finding stays open** for the rung-3 half only, until the question above is answered and
  built.

**Stopped at REV, 2026-09-14.** The adversarial review read DIRECTION's *"the change stops after
REV, unbuilt"* as covering the change, because R1 found the operator's question. It also found
that the rung-3 half is written against today's definition of free: under the recommended (d), the
sentence would name holdings that are not reasons. Nothing is built. REV recommends a split to the
operator: build the F353 half as its own change after one verification round, and hold the rung-3
naming for the answer (`decisions_for_user`, `F352-split`).

**Definition half fixed and driven, 2026-09-15** (`a-task-nothing-will-move-holds-nobody`, fix
`4b59ee0`, archived with this note). The operator set the direction on 2026-09-14 at 23:30 as a sixth
option, **(f) reachability**: an assigned task holds its assignee only while its loop has neither
ended nor been archived, or while a turn within the hop budget is queued for that agent naming it.
Driven on a fresh drive Hub (`:8013`, `profiles/drive0915`, project `proj-4297ab5fd02c`, Haiku
throughout; harness `scripts/drive/t_d0915_reachability.py`):

| lane | staging | answer |
|---|---|---|
| LoopEngine's shape | `alpha` authored the task in a real turn with evidence naming a commit; `beta` `in_progress` and `gamma` `pending` on tasks from `POST /tasks` with an assignee and no loop | **200**, review staffed with `beta`, a real Haiku review turn, **no `review_unstaffed`** |
| control | both holding tasks in a second **live** loop | **409**, today's rung-3 sentence, one `review_unstaffed` |
| paused | that loop's job disabled | **409**, the same sentence (design D2: a pause holds) |
| ended | that loop stopped (`ending_state: stopped`) | **200**, staffed |
| archived | a third live loop, archived through `POST /jobs/{id}/archive` without a stop; `ending_state` still null | **409** before the archive, **200** and staffed after |
| past the budget | `POST /messages` naming `beta`'s out-of-loop task: `hop_depth` 7, budget 6, `queued` | **200**, still staffed with `beta` |
| D8 | an empty loop on `alpha`, Run pressed while `alpha`'s real turn ran and `beta`/`gamma` were idle | **409** *"alpha is already running a turn, and this loop's queue holds no open task for another agent to take. Nothing was started."*; no job entry, no history |

**Still open here: the visibility half.** The sentence still names nobody, as the control and paused
rows show. That is `an-unstaffed-review-names-its-holders`, and its rung-3 half must be re-derived
against (f) before it is built: it would now name only reachable holdings. The drive also found
**F374**, below.

## F353 (B) — the product tells the operator to "clear the assignee", and nothing in the app can; the one action that would work, "Land it", is never named

**Status:** fixed `4515728` + `7343200` (`a-refusal-names-a-remedy-that-works` groups 4a-4b),
archived `b29c096` 2026-09-16, driven live at `:8011` (task 5.3, below) before archiving. Found
2026-09-13 unblocking F352.

The task drawer renders **Assignee** read-only (`TaskDetailDrawer.tsx` ~L380). The operator's
`PATCH …/tasks/{id}` accepts `assignee` (F78), but no control sends it, and the agents'
`update_task` tool has no assignee field. The review guard's refusal
(`agent_trigger.py` ~L500) says *"Dispatch a different reviewer, or clear the assignee to review it
yourself"* — the first also has no control (F336). Meanwhile F163's **Land it** button, which
releases the author's hold and approves in one step, sits in that same drawer for `completed`
tasks, and neither this refusal nor the flow's `review_unstaffed` sentence points to it. Measured:
the operator asked the reviewing agent three times how to reassign; it concluded *"neither you nor
any agent has a way to do that"* and handed the operator hand-written PowerShell against a path the
Hub does not serve (`/tasks/<id>`, no project, no auth). One `land` call per task did it.

**Observed again 2026-09-14** (day window O-3, LoopEngine, read-only). The agents met the guard's
refusal eight times: the Architect six, and `tester` at 23:07 on `task-49b0567ce119` and at 03:59 on
`task-0ff93faef4ba`. Each refusal followed a *"Cannot move a task from 'completed' to …"* refusal.
The Architect put the gap to the operator through `ask_user` at 16:32. It later ended several
autonomous turns asking in prose for tasks to be reassigned. The agents' saved notes record that no
agent can reassign. The task stayed `completed` each time, and the verdict landed only through
evidence decisions.

**Specced 2026-09-14, unbuilt** (`openspec/changes/an-unstaffed-review-names-its-holders`, stopped at
REV with F352). REV found two more places with this finding's shape, code-read:
- The D9 refusal, *"Reassign the task if 'x' should take it over"* (`agent_trigger.py:494, 840`),
  names a control the operator does not have, and `under_review` has no edge that hands a review
  over (`task_transitions.py:138-142`).
- The one request that *does* change the holder, the operator's assignee-and-status PATCH, queues
  no turn, so in a flow it leaves F154's wedge. A remedy that names it replaces this finding's
  defect with F154's.

The change's remedy is now Land it, or a review dispatch (`POST /agent/trigger` with
`review_task_id`).

**DRIVE, 2026-09-16 (`a-refusal-names-a-remedy-that-works`, task 5.3, `:8011`, profile
`drive0916`).** Built, unit-tested, and archived at 5.4 (`b29c096`, above) — this drive is task 5.3's own live check of
D1/D4, the fix this finding names, against a real Hub, a real Chromium session and a real Haiku
turn (`scripts/drive/t_d0916_refusal_remedy.py`). Population: one task authored, worked and
completed by a real Haiku agent (`dev`) through the ordinary flow route, so `agent_that_completed`
(the guard's own read of `TaskTransition.actor_agent`) genuinely names `dev` — not an
operator-walked completion, which F167 already shows this guard cannot recognise as authored.

CHECK 2 (real Chromium against the served bundle, `hub/hub/static/ui`, not a transcription): the
drawer's status menu still offers `Move to under review` from `completed` — the transition map does
not know who authored what — and clicking it renders, at `task-status-refusal-{id}`, verbatim:
*"Cannot move task task-63648ee4f3cb to 'under_review' with 'dev' as its holder: it is the agent
recorded as completing this task, so the move would claim its own author is reviewing it. Land it,
on the task, to review it yourself, or dispatch a different agent's review turn (POST /agent/trigger
with review_task_id)."* — beside a visible, enabled `Land it` button (`task-land-{id}`) in the same
field. F353's whole complaint (a remedy naming a control the app does not have, with the one action
that would work never named) is answered on screen: the sentence names Land it, and Land it sits
right beside it.

CHECK 3 (a real Haiku turn, not a guess): the same agent, in a fresh conversation, asked through a
plain prompt to call `update_task` on the very task it holds. Its own `update_task` tool result
(read off `GET /agent/dev/chat/{conversation_id}`, `output_kind == "tool_result"`) came back:
*"Error calling tool 'update_task': Hub rejected PATCH /tasks/task-63648ee4f3cb (403): Cannot move
task task-63648ee4f3cb to 'under_review' with 'dev' as its holder: it is the agent recorded as
completing this task, so the move would claim its own author is reviewing it. None of the task
tools you are offered reassigns a task; the operator can move it on."* — the agent remedy, not the
operator's, exactly as D4 specifies by actor. The agent's own next turn-text correctly summarised
this back in prose without being told to.

Nothing here disproves what groups 1 and 4 claimed; both remedies fired for real, for the actor
they are supposed to fire for, in the two surfaces (browser, agent tool result) a unit test cannot
reach.

## F354 (B) — the operator's live agents launch the MCP server from the development working tree, so an unattended loop's uncommitted edits reach them mid-edit

**Status:** fixed (2026-09-25) by `06e0cec` (`an-agents-tool-server-is-the-one-its-hub-loaded`, archived 2026-09-25); driven 2026-09-25 on a fresh trial Hub (8026, `drive0925morning`, Haiku): turns spawn `~/.agentweave/hub/tool-server/<digest>/mcp_server.py`, and an edit to the checkout's copy did not change the pinned bytes. **Takes effect on `:8000` only after its next restart.** The startup-log line is not emitted (F449).
**Status when filed:** open. Found 2026-09-13 on the operator's Hub.

Port 8000 runs this checkout (CLAUDE.md), and every agent turn spawns its tool server fresh from
the working tree (`agent_trigger.py` ~L1086, `canonical_server = … / "mcp_server.py"`). CLAUDE.md
lists what that arrangement costs — Python on restart, migrations on restart, the UI bundle on
reload — and this is a fourth, worse than the bundle: **uncommitted** and with no restart in
between. At 22:31 UTC the night window had uncommitted edits to `hub/hub/mcp_server.py` (and
`test_permission_approver.py`) while the operator's flow was firing a turn every five minutes; they
were gone from the tree minutes later. Nothing was measured to break, and no turn was checked
against that window. A repair could pin the server the Hub loaded — copy `mcp_server.py` aside at
startup and spawn the copy — so an agent's tool surface changes when the Hub restarts, like the rest
of its Python.

## F355 (B) — a run that fails on the provider's session limit is re-delivered into the same exhausted allowance, and then its input is given up

**Status:** fixed c8e3bbd — `a-spent-allowance-holds-the-queue`, built in three commits (`98385cd`,
`e1eca5b`, `c8e3bbd`), driven live 2026-09-14 (*DRIVE part A* and *part B* below, with a refusing
stub standing in for the provider), and archived the same day. A turn the provider's allowance
refused is not counted, keeps its session and is never withdrawn; the agent's queue is held until
the provider's reset and resumes on its own. Filed 2026-09-14 by the day window's O-3, from the
operator's real use (LoopEngine on `:8000`, read-only; `spec-queue/observations/2026-09-14-LoopEngine.md`).

**What happened.** The provider's session limit was hit three times: 21:00–21:05, 01:19–02:05 and
06:57–07:02 UTC. At least 66 runs failed on them (51 of `dev`'s and 15 of `tester`'s, plus the
Architect's). Each failed in 6–10 s with the harness's session-limit notice and
`Run failed (exit 1).` Of `dev`'s 51, 48 used 0 tokens. A traced example,
`entry-3203bb7ad4e0` at 01:25, went like this:
1. It was delivered, the run failed, and it was re-queued and re-delivered about 10 s later.
2. The second delivery resumed the failed session. The third started a new one (`run-42cae48b5e1f`,
   `run-895a732851b8`, `run-9f6ddd243259`).
3. Then the entry was withdrawn: *"delivery failed 3 times; the Hub stopped retrying"*.

25 entries ended that way: job steps, reviews and peer messages. The Architect's review of
`task-9e89a55ccc84` was one of them, and it was never delivered again. The flow then recorded 64
times that the Architect *"is named on … as its reviewer and is not reviewing it"*.

**Where.** `return_run_entries` (`hub/hub/inbound_queue.py:181-235`) treats every failed run alike:
- it clears the provider session at `RESUME_RETRY_LIMIT = 2` (`:170`);
- it withdraws the entry at `DELIVERY_ATTEMPT_LIMIT = 3` (`:178`, `:222-230`).

Those limits were written for a session that cannot be resumed (the docstring, `:184-189`), not for
an allowance that is exhausted until a known time. The harness reports the allowance:
`rate_limit_event` is parsed and kept only as an accounting sample
(`hub/hub/runner_parsing.py:364-369`). The session-limit notice states when the limit resets.
`grep -in "session limit\|usage limit\|quota" hub/hub` finds no code that reads either for
scheduling.

**Why B.** The failure attempts cost almost nothing. What does cost is **lost coordination**: a
peer message or a review given up at 01:25 is gone, and no agent is told. The flow re-creates its
own job steps on the next tick, but nothing re-creates a dropped message.

**Shape of a fix (a sketch, not verified).** Recognise a provider-limit failure, and do not count it
as a delivery attempt. Instead, hold the agent's queue until the reset time the provider gave, and
say so on the entry. Whether a held queue should also hold the flow's job is for R1 to decide.

**Proposed by R1, 2026-09-14** (`openspec/changes/a-spent-allowance-holds-the-queue`).
- **The signal is structured, and it separates the cases perfectly on this corpus** (measured,
  `mode=ro`). All 69 refused runs carry `turn_usage.allowance.status == "rejected"` with an epoch
  `resetsAt` (21:10, 02:10 and 07:10 UTC, the notices' Lisbon times). None of the 205 completed
  runs does. The prose is not parsed.
- **The session was sound.** The refused session `2a0bb6e2…`'s transcript holds the prompt and the
  notice, and the second delivery resumed it. `RESUME_RETRY_LIMIT` discarded it anyway.
- **The shape:**
  - a refusal is not counted, keeps the session, and is never withdrawn;
  - the hold is derived from the agent's newest informative `TurnUsage` row, with a 60 s floor;
  - new operator input probes once;
  - a date job wakes the queue at the reset, and is re-armed at start;
  - loops refuse, and plain jobs coalesce;
  - one migration, `0103`, adds `allowance_refusals`.
- **No OPERATOR QUESTION.** R1 argues that hold-vs-drop and the flow's job are both settled by
  shipped decisions: F96's "hold until repaired", and loop D4 composed through flow D12. It names
  plain-job coalescing (D7) as the one choice open to challenge, and severable.

**R2, 2026-09-14** (code-read, not driven; `design.md` *Round 2*). The conclusion stands, and there
is still no OPERATOR QUESTION. One leg of the argument was wrong, and three outcomes were fixed:
- **Flows do not compose the hold through D12.** The busy guard covers only the job's agent, and
  lets a firing through when anyone is free. `decide_firing` then reads its own `running` set
  (`hub/hub/scheduler.py:1299`), so it re-briefs a held assignee on every tick (`:1421-1435`). The
  repair reads running-or-held there and in `_agents_that_are_free`'s running half. It adds a new
  `agent-flows` delta. The general form of the pile-up is filed as F368.
- **A hold could have no wake:** R1 armed the wake only for a `failed` run.
- **A held firing read `failed`:** at its own refused run's end (`agent_trigger.py:2348`), and at a
  restart (`run_reconciliation.py:189-226`). New D10.
- **The hold sentence was stored on entries, where it outlives the hold.** It is now derived only.

**R3, 2026-09-14** (code-read, not driven; `design.md` *Round 3*). Still no OPERATOR QUESTION: the
`_agents_that_are_free` half is the running half, whose stated reason a hold shares, and the one
open operator call D6 reaches (F128) is applied, not decided. Four disagreements, fixed:
- **R2's D6 breached `agent-loops` *A task reported as in flight is one an agent is actually
  working*.** Putting held agents into `running` made a held assignee's task in flight on its
  assignment alone. A held assignee is now in flight only while input naming the task is queued
  (`on_it`); otherwise it is briefed once.
- **Pressing Run on a held loop answered falsely either way** (`hub/hub/api/v1/jobs.py:1287-1321`):
  *"already being worked … nothing is wrong"*, or 500 *"Failed to fire job"*, which is F127 lasting
  as long as the hold. New D11 re-asks the busy guard first. It retires F127 unless REV narrows it.
- **The ADDED `agent-flows` requirement contradicted the shipped reviewer-availability sentence.**
  That requirement is now MODIFIED.
- **Rung 3's reason became false** (*"every agent … is either running a turn, already holding active
  work, or …"*). It now names the hold when a hold is why.

Test construction: a module clock (`provider_allowance._utcnow`) for the tests that must end a hold,
a mutation for 1.2b, and fixtures for 3.4b and 3.4c that can tell their mutations apart.

**REV, 2026-09-14** (adversarial Opus review, code-read, not driven; `design.md` *Round 4 — REV*).
**PROCEED.** No OPERATOR QUESTION. F128's reach was misargued: it already covers any documentless
loop with two startable tasks, and D6 adds only the single-task case. D7 is settled, not severable.
D11 is kept whole and retires F127. The window re-read each finding at its line before applying it:
- **The MODIFIED `agent-loops` SHALL was false for every flow.** The guard lets a firing through
  when anyone is free. The shipped running sentence is now verbatim, and the hold is conditioned on
  nobody else being free.
- **The loops board read *"stalled: no claimable task"* for the whole hold** (`jobs.py:339-340` →
  `scheduler.py:1802`). A stalled decision the guard would refuse now carries the guard's reason.
  REV's broader form, asking the guard for every loop, was narrowed. It would have labelled every
  working single-agent loop `stalled`.
- **`run_job` answered from, and stamped, a row its firing did not write.** Filed as F369, and
  retired by this change.
- Smaller: `on_it.get(task.id) == agent`; a refusal needs a recorded reading and a future
  `resetsAt`, or it is counted; the D10 invariant is already false today; the Python informative
  check; test 2.4's mutation.

**DRIVE part A, 2026-09-14 16:50–17:05 BST (tasks 6.1–6.4, driven live).** Built at `b5b6baf`, drive
Hub from source on `127.0.0.1:8013`, fresh `profiles/drive0914/` (migrated to `0103` on launch),
project `proj-16a57b5e4e24`, agents `held` and `peer` on one Haiku runner. **The refusal came from a
stub**, not the provider: `claude.cmd` first on the Hub's `PATH`, an npm-shaped shim the Hub itself
unwraps (`pty_runner._unwrap_cmd_shim`) to a compiled `claudestub.exe`
(`scripts/drive/f355_refusing_claude_stub.cs`). With a flag file present and
`AW_AGENT_IDENTITY == held` it prints 2.4's four lines — the init session id echoing `--resume`,
`resetsAt` 120 s ahead — and exits 1; otherwise it passes the raw command line to the real
`claude.exe`. Every other turn was a real Haiku turn. Observed (drive db read `mode=ro`, stub argv
log, the status route):
- **6.1b** `run-8aa89050c16a` completed, provider session `c7a55611`, reply `PONG`.
- **6.2** One refused run, `run-8e299ef54af1` (`failed`, exit 1, `TurnUsage.allowance.status`
  `rejected`). Its entry stayed `queued` with `delivery_attempts 0`, `allowance_refusals 1`. A
  `queue_agent_held` event named `hold_until 15:56:23Z` and the entry. `GET …/queue/held/status`:
  *"held's provider refused its last turn: its five-hour usage limit is spent until 15:56 UTC
  (2026-09-14T15:56:23+00:00). The Hub holds its queue until then …"*. A plain job's firing
  (`Run`) queued an entry and **did not spawn**; its `JobRun` stayed `in_progress` through the hold
  (D10) and read `completed` after. A second `Run` answered **409** *"held's provider usage limit is
  spent until 15:56 UTC, and this job's earlier firing is still queued for it. This firing adds
  nothing."* and wrote a `skipped` row (D7).
- **6.3** Flag removed at 15:54:45. At **15:56:23, the reset to the second**, `run-cb47e0c3559d`
  started with no request, resumed `c7a55611`, carried *"Operator (hop 0) — delivery attempt 2; an
  earlier attempt was cut off before it finished"*, and answered `PING`. The job's entry ran next
  on its own conversation.
- **6.4** Flag re-raised. Operator message → fresh refusal `run-ffa7b6dbfa6c`, hold to 15:59:45.
  A second operator message → **exactly one probe spawn** `run-1721796a3561`, refused, carrying both
  operator entries (refusals now 2 and 1, attempts 0 and 0), hold renewed to **16:00:01**, and the
  status route named the renewed time. While held, a **real** peer turn (`run-bde28d90f1c7`, Haiku,
  over the HTTP plane) sent `held` *"ACK please."*: queued, no spawn. At 16:00:01 one resumed turn
  (`run-f1cf614f7dad`) carried *"delivery attempt 3"* and *"delivery attempt 2"*, then the peer's
  entry ran. Ten runs in all: eight for `held`, three of them refused, and no `held` spawn between a
  refusal and its reset except the one probe.
- **A drive artefact, not a finding:** the first "peer message", posted with the operator key and
  no `run_id`, queued at `hop_depth = hop_budget + 1` and was suspended (`messages.py:57-58`, by
  design), so it proved nothing about the hold. 6.4's real peer turn is the peer evidence.
- 6.5 and 6.6 were driven in part B, below.

**DRIVE part B, 2026-09-14 17:07–17:13 BST (tasks 6.5–6.6, driven live).** Built at `ac6bff6`. The
same drive Hub was relaunched on `127.0.0.1:8013`, on the same profile, project and stub. The flag
stayed raised throughout, so each reset delivered into another refusal and renewed the hold, and no
`held` turn reached the provider. Both cases were reached, one after the other, on the same loop
`job-cdff75d9c531` (`loop-778dd34db171`, `*/1`, purpose set, one seeded task
`task-4d2724a2ce27`):
- **No free agent (3.4, and 3.4c's running half).** `peer`'s runner was unbound, which takes it off
  the free list (`_agents_that_are_free`). An operator message was a fresh refusal
  (`run-e9c0ce22261e`, hold to 16:09:29 UTC), and the loop was created enabled at 16:07:35 with its
  task `pending` and unassigned. `held` held no task, so without 3.4c it would have been "free" and
  let the firing through. The **16:08 and 16:09 firings wrote no `JobRun` and no entry**: the job
  read `last_run NULL`, `run_count 0`. **Run** at 16:09:10 answered **409** *"held is held until
  16:09 UTC by its provider's usage limit, and no other agent is free to take this loop's work.
  Nothing was started."* The board's summary read `queue {pending: 1}` and **`stall_reason` *"held
  is held until 16:09 UTC by its provider's usage limit"***, not *"no claimable task"* (3.4e's
  stalled case).
- **A free agent (3.4b).** At the 16:09:29 reset the queued message was delivered into another
  refusal (`run-1b05a38b42e9`), which renewed the hold to 16:11:32. The task was then assigned to
  `held`, which queued nothing, and `peer`'s runner was re-bound, so `peer` was free (bound, not
  running, holding nothing). The **16:10 firing passed the guard and queued exactly one briefing**
  for `held` (`entry-b6e670147ceb`, `task_id` the task) with one `JobRun` (`run-35418b24c780`,
  `in_progress`), and spawned nothing. The 16:11 and 16:12 firings added **no entry and no
  `JobRun`** (`run_count` stayed 1): the task read in flight on the queued briefing (`on_it`). That
  is Round 3's form, briefed once, not R1's every tick and not R2's never. **Run** at 16:12:10
  answered **409** *"Every task on this loop's queue is staffed, but held is held until 16:13 UTC by
  its provider's usage limit. The queued input is delivered at the reset. Nothing was started."*
  It did not read *"already being worked"*, *"nothing is wrong"* or 500. The summary read
  `stall_reason null`, with `current_tasks[0].agent_capacity "held"`. An in-flight decision is not
  labelled stalled.
- Between 16:07 and the Hub's stop, the only runs were `held`'s three refused deliveries (16:07:26,
  16:09:29, 16:11:32), each at a reset or the operator's message. `peer` ran nothing.
- **6.6:** both jobs disabled (`plain-f355`, `loop-f355`) and no run `running`. The drive Hub was
  stopped (8013 free; `:8000` untouched), and the flag was removed after the stop.

## F356 (B) — an answer given after `ask_user`'s wait ended, while the asking run is still alive, is delivered to nobody

**Status:** fixed d16a76a (`a-late-answer-is-delivered`, 2026-09-15; driven live on `:8014`, 22/22). Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).

**Residual, left in place deliberately (design D5; the operator chooses whether it needs a receipt
stamp).** This fix closes the loss that cost the operator on 09-13, and the fourth loss Round 4
found. It does **not** close these routes, and nobody should read the line above as closing them:

| Route | After this fix |
|---|---|
| 1. The tool's expiry report is lost, **or its write was rolled back** (`agent_actions.py`, the release's `except`), and the answer arrives later in the run's life | lost |
| 2. The question timeout is lengthened mid-run, so the report is refused | lost |
| 3. An answer commits inside the wait, and the run dies before the tool's next poll (up to 2 s) | lost — pre-existing |
| 4. (candidate, read, not measured) The runner's MCP client abandons the tool call before the tool's own deadline, so no report is sent. Plausible for Codex, which is undrivable | as route 1 |

A receipt stamp (a migration, plus a write when `get_own_question` serves a resolved row to its run)
closes all four at the run's end. A no-migration run-end delivery closes 1 and 2, leaves 3, and
duplicates a grace-window answer. Both are follow-ons; see the design's D5 table.

**What happened.** The Architect asked 22 questions in 9 `ask_user` calls. Three batches were
answered **after** the 240 s wait had ended:
- 09-12 23:26: the wait ended at 23:30, and the answers came at 23:43–23:44;
- 09-13 14:38: three of the four questions;
- 09-13 16:50.

No later prompt carries those question ids, and the Architect never called `get_answer` on them. The
operator's answers went into a store nobody read.

**Where.** `answer_question` decides whether to queue the answer as a new turn from
`asker_still_waiting = question.blocking and not await _asking_run_has_ended(...)`
(`hub/hub/api/v1/questions.py:346`). `_asking_run_has_ended` (`:29-45`) is true only once the run
has stopped. But `ask_user`'s tool call returns at the wait's expiry, and the run carries on. So
between the expiry and the run's end, the answer is treated as received by a tool call that has
already returned, and `_deliver_batch_if_complete` (`:359-362`) is skipped. `Question.wait_expires_at`
exists (`hub/hub/db/models.py:993`) and is not read anywhere in `questions.py`.

**Why B.** The operator's decision is silently lost, and both parties believe the other has it.

**Reproduce (sketch).** Have a Haiku agent ask a blocking question with a short
`AW_QUESTION_TIMEOUT` and then keep working, say a long `sleep`. Answer after the wait and before the
run ends. No queue entry is created, and no later turn carries the answer.

**Correction, 2026-09-14 (f356-R1, `:8000` read with `mode=ro`).** The mechanism above is right.
But **only one of the three batches was lost.**
- **23:26, delivered.** The asking run ended 23:31:37, before the answers came at 23:43:47–23:44:14,
  and `entry-7f953e7a11b4` delivered them at 23:44:14.
- **16:50, delivered.** The run ended 16:56:17, the answers came 16:56:57–16:57:26, and
  `entry-563536954359` delivered them at 16:57:26.

  Both are the shipped run-has-ended path working.
- **14:38, lost.** `q-cab59299c48e` and `q-477c3005a5b3` were reported expired at 14:42:56.37 and
  answered at 14:43:10 and 14:43:25. The run lived until 14:57:08. No `Architect` entry exists
  between 14:42 and 15:08. The other two questions in the batch were answered before the deadline,
  and the tool returned them.

The tool's expiry report landed on **21 of 21** expired waits, 0.06–1.2 s after the deadline. That
is why the fix reads `wait_ended_at`, not `wait_expires_at`.

Proposal: `openspec/changes/a-late-answer-is-delivered/`.

**Note, 2026-09-14 (f356-R3, code read).** A second writer of `wait_ended_at` shares the
pre-existing decline race that R2 found in the report, and the answer has a third way to be lost.
- **The run-end sweep** (`run_divergence.py:730-733`) loads the question, then assigns
  `wait_ended_at` to it. A decline committed in between is stamped as "Proceeded without your
  answer".

  The change now routes both writers through one guarded `UPDATE` (task 2.10). On `aiosqlite`
  it measured `rowcount = 0` against the Hub's `Question` model, with `synchronize_session=False`
  required.
- **A third route to a lost answer, which the change does not close.** An answer commits inside the
  wait, then the run dies before the tool's next poll, up to 2 s later. That answer is lost today and
  stays lost after the change. Only a receipt stamp, which needs a migration, closes it. Design D5
  has the route table.

**Note, 2026-09-14 (f356-REV, code read).** The adversarial pre-approval review did not stop the
change. It found three problems, and each is fixed in the proposal:
- **A fourth way to lose an answer, inside the change's scope.** A late answer's sibling is
  declined while the report is running. Its guarded stamp returns 0, and `_completed_batch` then
  judges completeness on the stale sibling from the identity map. Both writers decline. Task 2.11
  gives `_completed_batch` `populate_existing`.
- **The sweep rewrite has a trap.** `question = None` must not depend on the helper's result, or
  the task is parked on a declined question (task 2.10).
- **The "a declined question never carries `wait_ended_at`" comments are false in shipped code.**
  A decline *after* the report keeps the stamp. The guard encodes the narrower rule, and task 1.6
  corrects `models.py:1003-1007` and `tasks.py:447-449`.

**Fixed d16a76a, 2026-09-15 (night iteration 8).** Implemented as proposed: 31 tasks and one addition
(Round 4 F-H, below). Every tick carries a mutation that fails a named test. The whole hub suite ran
4361 passed, 86 skipped, 16 xfailed, 0 failed.

**Driven live** on `:8014` (fresh `profiles/drive0915b`, `proj-4b7ded73f250`, Haiku
`claude-haiku-4-5-20251001`, harness `scripts/drive/t_d0915b_late_answer.py`): **22/22**.

| Step | Observed |
|---|---|
| 5.2 Two questions, 10 s wait, then an 85 s shell wait | The tool's report stamped both 0.07 s after the Hub's deadline. The run was `running`, and the list and detail routes both read `asker_waiting: false` for each |
| 5.3 Both answered while the run lived | **One** entry carrying both answers, `queued` behind the live run. Delivered into a new turn 0.21 s after the asking run ended (the run-end re-drain), which replied *"the banner should be blue and large"*. Nothing else was queued |
| 5.4 Control: answered inside the wait | The tool returned `pear`. No `wait_ended_at`, and no entry |
| 5.5 Answered 0.32 s after the Hub's deadline | **The grace window was not hit.** The report had landed at +0.04 s, before the answer, so the answer route read the wait as ended and queued it (1.2's path, not the report's). The agent said nobody answered, then the next turn got `two`. Where the tool *returns* a grace-window answer, that is covered by unit test 1.3 only |
| 5.7 | No run left `running`, no job exists, and the drive Hub is stopped |

- **The report-delivers-it path (2.2, 2.3, 2.9) was not driven.** It needs an answer committed in
  the ~1 s between the tool's last poll and its report, which cannot be hit reliably by hand. Unit
  tests cover it through the real routes, interleaved inside the report.
- **The drive Hub started before the F-H line below was written.** That line runs only after a
  release raises, which the drive never provoked. So the drive exercised the committed code on
  every path it took.

**Round 4 F-H, completed in d16a76a.** The design recorded it as pre-existing and unverified, and
asked the rewrite to read `run.id` into a local. That was done, but `release_block_for_expired_wait`
still reads `run.id` and `run.agent`. A probe measured the consequence: after one question's release
raised and rolled back, the next question's release raised `MissingGreenlet` on the expired run,
and it too was not accepted. One failed release in a report took every later one with it. Fixed by
re-loading the run after the rollback. Test:
`test_one_failed_release_in_a_report_does_not_fail_the_next`, whose mutation fails it.

## F357 (B) — a flow's review turn tells its reviewer to approve, and says nothing about the evidence gate that will refuse it

**Status:** fixed (this commit) [Round 5, 2026-09-23] -- both review channels now name the evidence gate beside the verdict; see FIXED at the end of this entry. Was: open. Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).

**What happened.**
- **Five of the Architect's approvals were refused** (`49d507bb` 18:00, `0682583f` 19:41,
  `712ab8e3` 19:52, `37dd5b7a` 20:11, `8b72ca10` 20:32), each with *"This task's work has been
  recorded and nobody has judged it … To land it, accept the evidence, or grant an agent the
  capability to accept it — both are the operator's"*. At 18:00 it had already told `dev` the task
  was approved, and had to send a correction.
- **`dev_2`'s approval of `task-715470b41119` was refused twice** (19:50, 19:55). It messaged `dev`
  that the task was approved regardless. Earlier, at 17:23, the flow had staffed it to review
  `task-b8e8b7f3beca`, and its three `decide_evidence` calls were refused with *"accepting evidence
  is the operator's, or an agent the operator has granted it."*

The operator then granted `tester` `can_accept_evidence`, and every evidence decision was routed
through `tester`, which lengthened every Architect↔`tester` thread.

**Where.** Both channels give the same instruction: *"End the review with a verdict, using
`update_task`. The task is `under_review`: set it to `approved` if the work is right"*
(`hub/hub/scheduler.py:2065-2085`, `hub/hub/api/v1/agents.py:1642-1646`). Neither mentions that
approval is refused while the task's evidence is `awaiting`, which is the gate
`approval-refuses-unaccepted-evidence` added after that wording (F45). The context channel does say
*"You cannot decide evidence"* (`agents.py:1909-1913`), but nothing connects that sentence to the
verdict. `resolve_reviewer` (`scheduler.py:1043`) does not consult the grant: `can_accept_evidence`
is read only at `requirement_evidence.py:674` and in `agents.py`.

**Why B.** The review turns were genuine and the verdicts were right. Each one hit a refusal that the
briefing had set up, and the agents misreported the result to their peers.

**FIXED 2026-09-23 (interactive session, Round 5).** Re-verified first: both channels still gave the
verdict instruction alone (`scheduler._briefing_verdict_lines`, `agents.py` review block), and the
gate's refusal (`requirement_gate._check_unaccepted`) was unchanged. One sentence,
`review_turn.verdict_evidence_sentence`, now follows the verdict on **both** channels, so they
cannot disagree. It is keyed on what is waiting now, from the gate's own source
(`task_integration.awaiting_targets`): a task with nothing awaiting -- every documentless loop -- is
told nothing new. It names each waiting piece (requirement and commit), says `approved` *can* be
refused until it is accepted (not "is": the gate's mixed case lets approval through when something
else would merge), and says `revision_needed` is unaffected. Then, by the reviewer's own
`can_accept_evidence` grant: a granted reviewer is told to decide with `decide_evidence` first, then
approve; an ungranted one is told the decision is the operator's, that a refused approval recorded
no verdict, to send the verdict as a message, and **not to tell anyone the task is approved** -- the
misreport this finding measured. `_compose_loop_briefing` gained a required `agent=` keyword (no
default, like `is_review`) so the briefing can read the reviewer's grant. `resolve_reviewer` still
does not prefer a granted agent; that is staffing, not copy, and is left to S1/D9.
Test: `hub/tests/test_review_briefing_names_the_evidence_gate.py` (4), built on the gate's own
awaiting-evidence fixture; three fail with the sentence disabled.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 5).** Five changes. (1) The
ungranted remedy was "send the verdict as a message", but `send_message` reaches only agents, and
none of them can decide evidence. It is now `ask_user`, the one channel from an agent to the
operator, followed by approving once the evidence is accepted. Not claimed: that an unanswered
question parks the task, since `under_review` has no edge to `blocked`. (2) The sentence is
suppressed where evidence does not govern the merge (`evidence_governs`). A loop with
`work_needs_evidence` false merges the branch tip, and its awaiting rows are only advisory there.
(3) Each piece names its evidence id, which `decide_evidence` takes, and names the recording task
where that is another task on a shared requirement, as the gate's own detail does. (4) A test now
goes through a real firing (`test_flow_fires_a_review_turn.py`
`test_a_flow_review_briefing_reads_the_reviewers_own_grant`). There the reviewer is granted and the
job's agent is not, and passing `job.agent` at the call sites fails it. (5) Two new tests: nothing
is said where evidence does not govern, and nothing once the evidence is decided. **Residual:** once
an unanswered question times out, the row falls to F154's sentence ("Ask X again"). That sentence
does not name the awaiting evidence as the real blocker. It is filed nowhere new, because it is
F374/D9's divergence-reason question.

## F358 (B) — evidence can be decided while the run that recorded it is still live, so the reviewer judges a commit the Hub is about to replace

**Status:** fixed 6268b0e (driven live 2026-09-26, drive Hub :8041, `d0926_evidence_waits.py`: operator mid-turn decide 409 `recording_run_live`, after the run ended 200; a granted second agent refused mid-turn, woken after with the `evidence` note in the same conversation, decision recorded). Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).

**What happened.** `dev`'s `run-13096fbb3cc8` ran from 05:35:45 to 05:53:05. During it, `dev`
messaged `tester` to re-check the rework. `tester` woke at 05:51:59 (`run-9f7ae8cfe645`) and read
the new rows' footprint, `d4f5eda`. At 05:53:05 the Hub re-pointed the rows to the snapshot
`880f47c`. At 05:53:11–17 `tester` rejected all three (`ev-c7b3dce37a88`, `ev-be17d387cd74`,
`ev-b3a0392cf76a`) as unverifiable on `d4f5eda`. The stored rows now name `880f47c`, so each
rejection's reason contradicts the row it sits on. One review round was lost.

There were two more costs:
- **A remedy that contradicts the briefing.** Three times `dev` re-recorded after revising in the
  same turn, and was refused with *"… if the work has moved on, commit it first so the new evidence
  names the commit it demonstrates."* The briefing says the opposite: *"You do not need to `git
  commit` your own changes"* (`launchability.py:423-428`).
- **Rows an agent cannot retire.** The duplicate refusal offers only *"say so on that piece"*. Five
  of `tester`'s rejections existed only to retire a superseded row that its author could not
  withdraw.

**Where.** `decide` (`hub/hub/requirement_evidence.py:677-737`) checks the grant and self-acceptance,
and nothing about whether the recording run is still running. The footprint is re-pointed only when
the run ends (`restamp_run_footprints`, `:894`; `agent_trigger.py:2304-2315`). The duplicate remedy
is at `requirement_evidence.py:146-152`. `record_evidence`'s description calls the returned
footprint *"the branch and commit your evidence has been attached to. Read it."*
(`mcp_server.py:1727-1731`). That file is not edited on 2026-09-14 (F354).

**Why B.** Of `tester`'s 34 rejections, 3 are this race. Each one costs a review round and leaves a
recorded reason that disagrees with the row.

## F359 (B) — a run killed by the Hub's own write is marked failed without the snapshot or re-point a finished run gets

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- a locked bookkeeping write no longer ends the run, and a run that does fail no longer leaves its process running; see FIXED at the end of this entry. Was: open. Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).
F349 is the same lock seen from a trigger request.

**What happened.** Three runs ended on `(sqlite3.OperationalError) database is locked` raised by
`INSERT INTO agent_outputs` (`run-539bd1d44ea1` after 35 minutes and 304 outputs;
`run-d5f4b2972125`; `run-7695d6f7b4b4`). `run-d5f4b2972125` had recorded `ev-85be48ba74a2`, and
failed at 04:03:24. The next run in the same session committed the work at 04:05:58 as `d97aef5`,
but that run's re-point covers only its own rows. `ev-85be48ba74a2` still names `c78d35d`, which does
not contain the code, and that is one of the reasons `tester` gave for rejecting it at 04:23.

**Where.** Every output line is written by `record_agent_output` inside the read loop, with no guard
(`hub/hub/api/v1/agent_trigger.py:2190-2204`). A lock error there propagates to the run's `except`
(`:2461-2491`). That path marks the run failed through `_record_run_failure_tail`. It does neither
`snapshot_worktree` nor `restamp_run_footprints`, both of which a normal end does (`:2248-2315`).

**Why B.** A run can die on the Hub's own bookkeeping, not on the agent's work. When it does, the
work is left uncommitted in the worktree, and any evidence the run recorded names a commit that does
not hold it.

**Open to R1.** Whether the harness process is stopped when the read loop raises, or runs on
unobserved, is not verified.

**FIXED 2026-09-23 (interactive session, Round 3, group 3d).** The open question first, answered
from the code: **it runs on, unobserved.** The `except` marks the run failed and `finally` drops the
session from `active_ptys`; nothing terminates the process. So the finding's own evidence is the
orphan finishing the work -- and the failure tail re-drains the queue, so the next turn can start in
the same worktree beside it. That ruled out the finding's suggested repair (snapshot on the failure
path): it would race a live agent. Two changes instead, in `agent_trigger.py`:

1. **A bookkeeping write cannot end the run.** New `_record_observation(write, run_id=, what=)` runs
   an observational write on a fresh session; `OperationalError` "database is locked" is retried
   after each of `OBSERVATION_RETRY_DELAYS` (0.5 s, 2 s -- each attempt already waits out the 5 s
   `busy_timeout`) and then dropped with a warning. Anything else still raises: a defect must stay
   loud. Applied to every streamed output row and context-usage reading on **both** transports
   (`_flush_line`, and the app-server path's `_on_event`/`_on_usage`), and to the closing
   `"Run <status> (exit N)."` status row, which is written after the terminal commit and is the only
   settled marker a stopped, failed or Codex run has. With the lock no longer fatal, the run reaches
   its normal end, which snapshots the worktree and re-points the evidence -- the two steps the
   finding says were skipped.
2. **A run recorded as failed stops its process.** The PTY run's `except` now terminates the process
   (`pty.terminate(force=True)`, the stop route's call) when it is still alive, best-effort, before
   the failure tail releases the queue. The app-server path needed nothing: `run_turn`'s own
   `finally` closes its subprocess.

Tests (`test_agent_trigger.py`): `test_a_locked_output_write_does_not_fail_the_run` (every event
attempted three times, run `completed`), `test_a_lock_that_clears_on_retry_still_records_the_row`,
`test_a_run_failed_by_its_read_loop_does_not_leave_its_process_running`. All three fail on the old
code for the stated reason (run `failed` on "database is locked"; `terminate` never called). Not
driven live: reproducing the lock needs a second writer holding SQLite past `busy_timeout`.

**Review follow-up 2026-09-23 (adversarial Opus pass over Round 3, applied in the next commit).** The provider session binding in `_flush_line` -- the first write
of every run, its most contended moment -- was left unguarded, so a lock there still failed the run
and the new terminate killed it mid-work. It now goes through `_record_observation(..., drop=False)`:
retried like every streamed row, each attempt starting from the same state, and re-raised (never
dropped) if the lock outlasts the retries, since the binding decides which provider session is
resumed. Test: `test_a_lock_on_the_session_binding_is_retried_not_fatal` -- on the
pre-follow-up code the run fails on "database is locked". The Codex app-server path still has no
process terminate on failure (its `run_turn` closes the subprocess); not pursued while Codex is
undrivable.

## F360 (B) — the checkpoint probe asks for the tasks "assigned to this agent" while a loop checkpoint lists the loop's whole queue, so half of a flow's checkpoints are marked failed

**Status:** fixed (this commit) [Round 3, 2026-09-23] -- the probe asks for the tasks the grader checks; reproduced and verified live on Haiku; see FIXED at the end of this entry. Was: open. Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).

**Measured.** All 14 of the project's checkpoints were loop-scoped, and each envelope carried 32
tasks. 7 passed and 7 failed. **Every failure was the `task_ids` dimension, with all 32 missing and
none invented.** No other dimension ever failed. The probe reader (Haiku) either listed every id or
listed none.

**Where.** The probe prompt's rule is *"List the id of every task the checkpoint says is assigned to
this agent"* (`hub/hub/checkpoint_generation.py:157`). For a loop, though, the envelope and the
rendered `## Tasks` section are the loop's whole queue at every status (`checkpoints.py:257-283`,
`:375-378`), under a note that says so. A reader that follows the rule literally finds no
assignments stated, and returns an empty list. `grade_probe` compares the answer against every item
(`checkpoint_generation.py:385-399`), fails it, and sets the checkpoint `failed` (`:627-630`). The
successor then reads *"This checkpoint's written summary failed its probe … disagreed with it"*
(`:336-345`). The written summary disagreed with nothing: the reader was asked a question that the
Hub's own list does not answer.

**Why B.** It is a coin toss on every loop checkpoint. It reports half of a flow's checkpoints as
failed, and it tells their successors to distrust a summary that has nothing wrong with it.

**FIXED 2026-09-23 (interactive session, Round 3, group 3f).** The probe's task rule now asks for
what `grade_probe` compares against: *"List the id of every task listed under the checkpoint's Tasks
heading, whatever its status."* Scope-neutral, so it is right for the agent-scoped list and the
loop-scoped one alike, and it names the heading `render_checkpoint` writes. `PROBE_PROMPT_VERSION`
is `checkpoint-probe/2`, so every `WorkerInvocation` says which rule produced it. **Reproduced and
verified live, not only reasoned:** `scripts/drive/t_f360_probe_task_rule.py` has Haiku (the probe's
model) read a 32-task loop checkpoint whose written summary is in the agent's voice -- the old rule
recovered **0/32 on three reads of three**, the finding's exact signature, and the new rule **32/32
on three of three**. (A five-task version with a neutral summary recovered 5/5 under both rules: the
failure needs the loop note plus a summary that names the agent's own work, which is what real loop
checkpoints have.) Test: `test_the_probe_asks_for_the_tasks_the_grader_checks_not_an_assignment`
(`test_checkpoint_generation.py`) -- the wording and the version, since a unit test cannot run the
model; the drive script is the behavioural check. Checkpoints already marked `failed` by the old
rule keep their status.

## F361 (B) — a peer message past the hop budget is suspended with no reason on its entry, and its sender is told it was sent

**Status:** fixed 2988870 in code (unit tests; D1 hop-budget note NOT driven live — needs a chain past the budget; the UI half is unchecked). Filed as follows: Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).
It is distinct from F258: these are agent chains that really did reach the budget, not operator
messages born past it.

**What happened.** 21 peer chains reached hop 7 against a budget of 6 and were suspended. One was
released at 06:10. **The other 20 were still `queued` 2–13 hours later, and every one had an empty
`waiting_reason`.** The Architect sent 8 of them. All 78 of its `send_message` calls returned
`{"success": true, "message_id": …}`, and no later briefing mentioned the suspensions.

**Where.**
- `create_message` queues the entry and emits a `queue_chain_suspended` event, and returns the
  message as usual (`hub/hub/api/v1/messages.py:288-308`).
- The scheduler returns `waiting_reason="hop budget exhausted"` (`turn_scheduler.py:336-337`,
  `:371-372`). It never writes that to the entry; only `:459` writes `entry.waiting_reason`.
- The agent's tool builds its own reply, `{"success": True, "message_id": …}`
  (`mcp_server.py:244`), and that file is not edited on 2026-09-14 (F354).

**Why B.** Coordination stopped for up to 13 hours. The sender believed the message was delivered,
and the operator was shown no reason on the entry. Whether the UI shows the suspension any other way
is left to R1.


### Reproduced 2026-09-17 on a second project, unchanged

`LoopEngine_2` (`proj-f90d219dd68c`), same Hub, three days after filing. **6 entries suspended at
`hop_depth 7` against `hop_budget 6`** between 18:10:55 and 18:19:40 — 3 addressed to `Developer`,
3 to `Teste`. Every one still `state='queued'` with `waiting_reason` NULL and `abandoned_reason`
NULL when read at 22:53. Each sender's `send_message` returned success; no later briefing mentioned
a suspension. `inbound_queue.can_start` (`any(entry.hop_depth <= hop_budget)`) then started no turn
for either agent, and the collaboration ended silently with all 21 runs `completed`, `exit_code 0`.

**One entry makes the cost concrete.** `entry-f510b9edb0f4`, suspended 18:17:09, carried
*"Teste accepted all six evidence rows and ran the suite itself, 39/39 … then start t-create."*
That is the message that would have started the next task. Nothing anywhere said it had not
arrived.

This run reached hop 7 in **one unbroken chain off a single operator message** because no flow
existed to reset it (F376). The two findings compound: F376 is why the chain never resets, F361 is
why its exhaustion is invisible.

## F362 (B) — on Windows, the workspace guard reads the tail of any relative word that contains a `/` as an absolute path

**Status:** fixed d9f4843 (`the-shell-judge-reads-a-word-whole` D2, task 1.1: rule 6 judges a word's
path-shaped pieces instead of reading an embedded `/` as an absolute tail; rows in
`hub/tests/test_the_shell_judge_reads_a_word_whole.py`; change archived 2026-10-04).
Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).
This is not F321 or F323, which are fixed (`612b9c9`).

**Measured.** The guard refused 262 tool calls on this project. The causes that this mechanism
explains:
- **45 globs.** `test/*.test.js` was refused as `'/*.test.js'`.
- **68 `/`-rooted fragments** inside Bash words.
- **Regex fragments.** `'/script'` came from a `<script` pattern and `'/\\1'` from a
  back-reference. Of the 45 refusals that were regex or `$VAR`, it explains the regex ones.
- **15 `2>/dev/null`**, refused even after a `cd`.

Each refusal cost a retry. The agents' shared notes describe the rule wrongly, as following the
shell's current directory. `_decide` resolves relative words against the workspace root and never
sees a `cd` (`mcp_server.py:1308-1311`).

**Where.** `_PLAIN_RELATIVE_RE` does not admit `*` (`hub/hub/mcp_server.py:966`). The word then
falls to the backstop, `_ABSOLUTE_PATH_RE`. On Windows that opens a candidate at any `[\\/]`
(`:957-960`), so the tail after the first `/` of a relative word is read as a POSIX-absolute path.

**Why B.** It is the largest source of refusals under the default posture. It pushes agents into
workarounds, such as throwaway scripts written into the checkout, that are worse than what they
were refused. **Not built on 2026-09-14**, because the repair is in `mcp_server.py` (F354).

## F363 (B) — `read_spec_document` cannot return a real specification in one tool result, and it refuses the document id the other tools take

**Status:** fixed (Tier 1, `a-specification-is-read-in-results-that-fit`, `f30326a`, 2026-10-07) -- a read is answered inline only within 25,000 characters; a larger one is written to `<run workspace>/.agentweave/reads/` and answered with `written_to` (D7); the bounded read with continuation remains the fallback; an `spdoc-` id is accepted. Driven on `:8010` with real Haiku turns on `agent-conversation-workspace` (47 requirements): over MCP, 1 call, 0 spills; over `aw-tool` in PowerShell, 1 call, 0 spills, the file read with one Read. The first drive, on the 40,000 bound, spilled on the `aw-tool` path (shell output spills above 30,000), which is what D7 answers. `list_tasks`' spill filed as F523. Was: open. Filed 2026-09-14 by the day window's O-3, from LoopEngine on `:8000` (read-only).

**Measured.** Every one of the project's 57 `read_spec_document` results, across all four agents,
was too large for the harness. Each was saved to a `tool-results/` file of 80–180 KB on a single
JSON line, and `list_tasks` spilled 24 times as well. That spill file lies outside the workspace,
so 85 guard refusals named it.
- Agents recovered the content with repeated `Grep` calls, and once with a whole subagent.
- Their notes settled on reading the committed `spec.html` instead, the opposite of what the tool
  description says.
- `dev` read the 64 k-character spec whole into its context in 11 sessions.

Separately, `read_spec_document` refused `spdoc-97d90a3506f5` with *"path must begin with
'spec/'"* (the Architect at 03:49, `tester` at 19:08 and 19:19). `list_evidence` accepts that id.

**Where.** The tool offers no filter narrower than `requirements` or `full`
(`hub/hub/mcp_server.py:1666-1670`). Its description says *"Use this before writing code against a
document"* and *"you almost certainly cannot open it as a file"* (`:1673-1676`). The id refusal is
raised by `spec_manifest.py:72`.

**Why B.** The one route the product names for reading the approved specification cannot deliver
it. **Not built on 2026-09-14**, because the tool is in `mcp_server.py` (F354).


### Reproduced 2026-09-17 on a second project, unchanged

`LoopEngine_2` (`proj-f90d219dd68c`), three days after filing. **6 oversized `read_spec_document`
results** across `Developer` and `Teste`, at **180,097** and **143,746** characters. Each was
spilled to `~/.claude/projects/C--Users-huida-Documents-projects-LoopEngine-2/<session>/tool-results/
mcp-agentweave-read_spec_document-*.txt`, and the agents' follow-up `Read` of that path was refused
by the workspace guard every time:

```
17:38:35  read_spec_document -> "Error: result exceeds maximum allowed tokens. Output saved to ...txt"
17:38:49  Read that file     -> "Denied: '...tool-results\...txt' is outside your workspace."
17:39:00  Read that file     -> "Denied: ..."
```

The spec is the approved document the whole build was working from. `Developer`'s turn that
followed recorded **16,104,082 input tokens**, the largest of the run.

**The two mechanisms are each behaving as designed and the combination is unusable**: the harness
spills an oversized tool result outside the project directory, and the workspace guard exists to
refuse exactly that path. Neither side is wrong on its own, which is why this will not be fixed by
tightening either one.

## F364 (C) — `submit_checkpoint_notes` enforces caps its description never states, and the refusal names neither the entry nor the overshoot

**Status:** fixed (this commit) [Round 3, 2026-09-22] — the refusal names the entry and the overshoot, and the tool description states the caps; see FIXED at the end of this entry.

**Measured.** `dev` made 36 calls and 23 failed:
- 9 were pydantic's *"Input should be a valid list"*;
- 14 were *"suspicions: each entry must be at most 400 characters"*, or the same for `warnings`.

It happened in 11 sessions, and each took two to five calls to get one note through. At 02:44
(`317bc32c`), after four refusals, `dev` wrote a script into its worktree to count characters.

**Where.** The caps are 1,500 characters for `intent`, 8 entries per list, and 400 characters per
entry (`hub/hub/api/v1/agent_actions.py:337-346`). The message at `:346` names neither which entry
failed nor its length. The tool description says *"a few hundred words in total is right"* and
states none of the caps (`mcp_server.py:511-535`), and that half is not edited on 2026-09-14 (F354).

**FIXED 2026-09-22 (interactive session, Round 3, group 3c).** Caps named once (`agent_actions.NOTE_INTENT_MAX_CHARS`, `NOTE_LIST_MAX_ENTRIES`, `NOTE_ENTRY_MAX_CHARS`). An overlong entry now reads e.g. *"suspicions[1] is 412 characters, 12 over the 400 each entry may have; shorten that entry or split it in two (at most 8 entries)"*. `mcp_server.submit_checkpoint_notes`'s description states all three caps and says to pass the lists as lists even for one entry (the 9 *"Input should be a valid list"* refusals); `mcp_server.py` may import nothing from the Hub, so `test_the_tool_states_the_caps_the_hub_enforces` checks the restated numbers against the constants. This file is respawned per agent turn on `:8000`, so the description reaches the operator's agents on their next turn. The list-count and `intent` refusals are pydantic's own, which already state the limit. Test: `test_an_overlong_entry_is_refused_by_name_and_overshoot`.

## F365 (B) — a loop with two stuck reviews records both on every firing, because "unchanged" is judged against the loop's newest record rather than the task's

**Status:** fixed `cf93ab6` (`a-refusal-names-a-remedy-that-works` group 3), archived `b29c096`
2026-09-16 — see iteration 3 of `.claude/autonomous/2026-09-15-night-log.md` for the live-fired
`POST /jobs/{id}/run` verification: two unstaffable tasks over 5 firings recorded exactly 1
`review_unstaffed` each. Filed 2026-09-14 by the day window's `f352-r1`, from LoopEngine on `:8000`
(read-only, mode=ro, `%TEMP%\f352\q1.py`). **Measured.** Taken into
`an-unstaffed-review-names-its-holders`, then split out and built as
`a-refusal-names-a-remedy-that-works` (group 3).

**What happened.** `review_unstaffed` fired **357** times on `loop-103ecb8aeb89`. **347** of those
repeat their own task's previous reason word for word. `agent-loops` *"A surfaced step is recorded
once, not once per tick"* requires one record per task while the reason is unchanged. From 22:35
to 22:55 UTC, only one task was unstaffed, and it recorded once, as designed. Every other stretch
held two or more.

**Why.** `_review_unstaffed_already_stands` (`hub/hub/scheduler.py:1913-1941`) selects the **loop's**
newest `review_unstaffed`, then compares its `task_id` and `reason`. With two tasks, their events
alternate, the newest is always the other task's, and the check never matches. The docstring says
*"the newest `review_unstaffed` for this task"*. The query does not filter on the task. The
existing test (`test_an_unchanged_wedge_is_recorded_once_not_once_per_tick`) stages exactly one
task, so it passes against this code.

## F366 (C) — an agent can set any task's assignee over HTTP, a field its MCP tool does not carry

**Status:** fixed `52e156b` (2026-09-29, ORDER 5/23 `an-agent-updates-a-task-with-what-its-tool-carries`, driven live then). Ledger closed 2026-10-12 night: `update_task_for_actor` refuses `assignee`, `priority` and `description` from any non-operator actor before any write (`hub/hub/api/v1/tasks.py:1541-1551`, 403); `hub/tests/test_an_agent_updates_a_task_with_what_its_tool_carries.py` 10 passed under py -3.11 through the agent route. Was: open. Filed 2026-09-14 by the day window's `f352-r1`. **Code read, not driven.**

`PATCH /api/v1/agent-actions/tasks/{id}` (`hub/hub/api/v1/agent_actions.py:276-289`) takes the
operator's `TaskUpdate`, and `assignee` is on it (`hub/hub/schemas/tasks.py:129`).
`update_task_for_actor` writes it for any actor, with no actor check
(`hub/hub/api/v1/tasks.py:1266-1275`). MCP `update_task` carries only `status` and `notes`
(`mcp_server.py:307`). By reading, then, an agent using the documented HTTP form can unassign
another agent's work, or name itself on a completed task and send it to review in one request.
`agent-capability-plane` forbids the two surfaces from differing in what they accept, and
`agent_actions.py:101-103` states that rule for task creation. Whether the agent's HTTP route is
meant to take `assignee` at all is the question. Neither direction of the difference has been
driven.

## F367 (B) — a stall reason longer than 500 characters is stored, and then the job's run history answers 500

**Status:** fixed `a2b947a` (`a-refusal-names-a-remedy-that-works` groups 1-2), archived `b29c096`
2026-09-16, driven live at `:8011` (task 5.3, CHECK 1, below) before archiving. Filed 2026-09-14 by
the day window's `f352-r2`. Taken into `an-unstaffed-review-names-its-holders` (design D2), then
split out and built as `a-refusal-names-a-remedy-that-works`.

**The mechanism, proven.** `JobRun.error_summary` is `String(500)` (`hub/hub/db/models.py:1349`),
which SQLite does not enforce. `JobRunResponse.error_summary` is `Field(max_length=500)`
(`hub/hub/schemas/jobs.py:88`), and `GET /jobs/{job_id}/history` answers `List[JobRunResponse]`
(`hub/hub/api/v1/jobs.py:1197`). With the real schema class in a `response_model=List[...]` route,
500 characters answer 200 and 501 answer **500** (`%TEMP%\f352r2\route.py`, `py -3.11`). One long
row therefore fails the whole history for as long as it is among the rows returned.

**A reason that already passes 500, computed.** `_wedged_review_reason`
(`hub/hub/scheduler.py:1744-1748`) reaches `error_summary` through F64's promotion (`:1655`) and the
stall write (`:2762`). It quotes the task title with `!r` in about 230 characters of fixed prose,
and names the reviewer twice. With a 32-character reviewer, the sentence passes 500 once the title
reaches 206 characters. At the 256-character limit it is 551 characters, and 807 when the title is
256 backslashes, which `repr` doubles.

**Unbounded by construction:** `schedule_result.waiting_reason` at `:2923` and `:3062` is the
`detail` of any non-transient `TriggerAgentError`. Several embed exception text, including git's
stderr and two absolute paths (`hub/hub/api/v1/agent_trigger.py:966, 970`).

**Observed so far:** nothing has failed. The `:8000` database's longest `error_summary` is 276
characters over 43 rows, and the trial Hub's 3 rows are empty (mode=ro, `%TEMP%\f352r2\len.py`).

**DRIVE, 2026-09-16 (`a-refusal-names-a-remedy-that-works`, task 5.3, `:8011`, profile
`drive0916`).** Fixed and archived at 5.4 (`b29c096`, above) — this drive is task 5.3's own
verification that the built D2 repair actually works live, not a unit test's
transcription of it. `scripts/drive/t_d0916_refusal_remedy.py`, CHECK 1: a loop's one task, seeded
at 256 characters — `TaskCreate.title`'s own maximum, confirmed live (`POST /jobs` with a 306-char
`initial_tasks` title answered **422**, `string_too_long`, before this drive's first attempt could
even build the population — so 256 is the worst case the product can ever hand this code, matching
what task 2.4's own unit test used) — wedged by hand to `under_review` under a non-author reviewer,
no turn ever run. Firing the job answered `409` naming the task and the reviewer, and
`GET /jobs/{job_id}/history` answered **200** afterward, carrying one `JobRun` whose
`error_summary` measured 486 characters — under the 500-char column and not itself truncated with
`…`. **One caveat on what this does and does not prove:** the reviewer name used here (`rev`, 3
characters) keeps the assembled sentence under 500 without the trim loop (`hub/hub/scheduler.py`'s
`_wedged_review_reason`) ever having to act, so this drive proves the *outcome* D2 exists for
(200, not 500, a clamped column) but does not itself exercise the trim path — that is exactly what
task 2.4's unit test already covers directly, at the real worst case (32-char reviewer, 256-char
title, 552 characters unmutated). Nothing here disproves group 2's claims; it confirms the
end-to-end behaviour the unit tests inferred, through the real route, for the population the
product can actually produce.

**Related:** F108 (a route's return, not read by the rounds), F154 (the wedged-review sentence).

## F368 (B) — a flow re-briefs an assigned, idle agent on every tick while that agent's queued turn cannot start

**Status:** fixed 9fbfb96 (driven live 2026-09-26, drive0926 :8031: an idle assignee whose head was refused is surfaced with the refusal's words and the remedy, 3 presses added no entry, and withdrawing the entry then pressing bound a new run to the task). Was: open. Filed 2026-09-14 by the day window's `f355-r2`. **Code read, not driven.** The held
instance is repaired by `a-spent-allowance-holds-the-queue` (design D6). The rest is not.

**The mechanism.** In `decide_firing`, the ordinary-work arm re-selects an already-assigned task
for its assignee whenever `agent not in running` (`hub/hub/scheduler.py:1421-1435`). `running`
counts `Run` rows in `running` (`:1299`). `held` counts only running turns too (`:1303`). `on_it`
also counts a turn that is staffed and still queued (`:1310`), but only the review arm reads it
(`:1378`). So an assignee that is idle **because its queued turn cannot start** is briefed again on
every firing. Each briefing is one more queued entry on a new conversation (`:2837-2848`), all
delivered as separate turns once the turn can start.

**An instance, by reading.** The project's token budget is exhausted. `_attempt_turn` refuses
autonomous input with *"token budget exhausted"* (`hub/hub/turn_scheduler.py:377-379`), using the
default `terminal_failure=True`. So each firing's `JobRun` also reads `failed`
(`scheduler.py:2918-2924`), while its entry stays queued. The firing reaches the walk because
`_loop_flow_busy_reason` refuses only a **running** job agent (`:295-300`).

**What would repair it (sketch).** Read `on_it` in the resumption arm. A task with a turn already
queued for it is in flight, not resumable. That changes flow behaviour for every waiting reason at
once, including hop-budget parking, so it wants its own proposal.

**Related:** F355 (the held instance), F154 (`on_it`'s origin).

## F369 (C) — pressing Run stamps the requester onto an earlier firing's record when the firing wrote none

**Status:** fixed c8e3bbd — `a-spent-allowance-holds-the-queue` design D11, task 4.4, archived
2026-09-14. `run_job` stamps `requested_by_run_id` only on a row its own firing wrote; a press whose
firing wrote none leaves an earlier firing's requester as it was (test: an earlier `"run-a"` stays
`"run-a"`). Filed 2026-09-14 by the day window's `f355-rev`, code read.

**The mechanism.** `run_job` (`hub/hub/api/v1/jobs.py:1270-1285`) fires the job, then reads the
job's newest `JobRun` and sets `requested_by_run_id = run_identity` on it. A firing that declines
without recording anything writes no row. That covers the busy guard and F23's in-flight decision.
So the stamped row is some **earlier** firing's. For an operator `run_identity` is `None`, which
erases an agent's attribution on that row. For an agent it claims an earlier firing as its own.

**Why it matters now.** Under that change's D10, a firing whose turn the provider refused stays
`in_progress` for the length of the hold. It is the newest row, and it is the one a Run press
during the hold would re-stamp.

**The repair.** Read the newest id before the firing and again after it. Stamp only a row the
firing wrote. The same comparison tells the route which row is this firing's answer.

**Related:** F127, F48 (the in-flight re-derivation that records nothing), F355.

## F370 (B) — a held assignee is re-briefed every firing when input for an agent whose name sorts first also names its task

**Status:** fixed 9fbfb96 (driven live 2026-09-26, drive0926 :8031: held assignee with a peer entry queued first, 3 presses, dev's job entries stayed 1; before the change 4 by R1's measurement). Was: open. Filed 2026-09-15 by the night window's `a-task-nothing-will-move-holds-nobody-r2`.
**The helper's answer is measured. The consequence at the arm is by reading, not driven.**

**The mechanism.** `run_task_binding.tasks_with_a_turn_pending_or_running`
(`hub/hub/run_task_binding.py:267-309`) answers `task_id -> one agent`. It builds its pending half
with `pending.setdefault(candidate, agent)` over a select with no `ORDER BY`, so where input naming
one task is queued for two agents, it keeps whichever row comes back first. The held-resume arm of
`decide_firing` (`hub/hub/scheduler.py:1506`, `a-spent-allowance-holds-the-queue` D6, shipped
`c8e3bbd` on 2026-09-14) asks `on_it.get(task.id) == agent`: *is this held assignee's briefing
already queued?* When the map kept the other agent, the answer is no. So the assignee is briefed
again, on every firing, for the length of the hold. That is F368's held instance, which D6 was
built to repair, returning through the map.

**Measured** with a throwaway test against the real helper. Staged: a task assigned to `dev`, a job
entry for `dev` naming it at hop 0, and a peer entry for a second agent naming it at hop 7. Both
insertion orders were run.

| second agent | helper's answer, either order |
|---|---|
| `alpha` | `{'task-probe': 'alpha'}` (the assignee's own entry is hidden) |
| `zeta` | `{'task-probe': 'dev'}` |

The rows come back in agent-name order. An agent reporting on its own task to an `architect`, or any
peer message naming the task sent to an agent whose name sorts before the assignee's, is enough.
F361's suspended peer chains (hop 7, never delivered without a release) make it permanent for as
long as the message sits there.

**Why the shipped tests did not catch it.**
`test_a_held_agent_is_busy.py::test_another_agents_entry_naming_the_task_does_not_put_it_in_flight`
queues only the other agent's entry, never both. Its names, `held-dev` and `held-other`, also sort
the assignee first.

**The repair (sketch).** Read pairs, not a map. `a-task-nothing-will-move-holds-nobody` adds
`task_agent_pairs_with_a_turn_queued` (its task 1.1a). That function is bounded by the hop budget,
which is right for its question and wrong for this arm's. A suspended copy of a briefing is still a
copy, because a release delivers it. So the arm wants the same pairs **without** the budget bound:
one parameter or a sibling function, and one line at `:1506`. Test: both entries, the other agent
sorting first, in both insertion orders.

**Related:** F368, F355, F154 (the helper's origin), F371, F361.

## F371 (C) — a review nobody is doing reads as attended while any agent has input naming the task, including input nothing will deliver

**Status:** fixed 9fbfb96 in code and by 25 tests through the real firing; NOT driven live (the review arm needs a wedged under_review flow). Was: open. Filed 2026-09-15 by the night window's `a-task-nothing-will-move-holds-nobody-r2`.
**Code read, not driven.**

**The mechanism.** F154's repair records an `under_review` task as *"a review nobody is doing"*
only when `task.id not in on_it` (`hub/hub/scheduler.py:1454`). `on_it` counts a queued entry naming
the task for **any** agent, at **any** hop depth. So either of these reads as attendance, and the
wedge is not surfaced:
- a peer message to a third agent that merely mentions the task (`send_message` carries an
  optional `task_id`, `mcp_server.py:209`, and `create_message` copies it onto the entry,
  `messages.py:263-267`);
- a message to the reviewer that is suspended past the hop budget. `_attempt_turn` never selects
  such an entry (`turn_scheduler.py:361-371`). Only `release_entry` delivers it.

F154's own docstring argues that `withdrawn` stops counting so that *"the answer decays correctly
rather than hiding the wedge forever"*. A suspended entry never decays: F361 measured 20 still
queued 2–13 hours later.

**Why C.** The review has to be wedged already, and a third party's input has to name it. The
operator still sees the task in flight with its reviewer named, just not the sentence F154 added.
The shape is the one F154 exists to remove.

**Repair (sketch).** Ask the question F154 means, which is whether the reviewer is on it, over
deliverable input: the pairs from `a-task-nothing-will-move-holds-nobody`'s task 1.1a, keyed to
`task.assignee`. That changes F154's shipped answer, so it wants its own round.

**Related:** F154, F370, F361.

## F372 (B) — a loop whose agent is mid-turn queues a briefing for it on every firing when its queue is empty and another agent is free

**Status:** fixed `4b59ee0` (`a-task-nothing-will-move-holds-nobody` design D8, archived 2026-09-15).
Tests 3b.2-3b.6, each with a mutation reproducing the measurement below. **Driven** on the drive Hub
on 2026-09-15: Run on an empty loop while its agent's real turn ran and two agents were idle answered
**409** *"alpha is already running a turn, and this loop's queue holds no open task for another agent
to take. Nothing was started."*, with no job entry and no history row. Filed 2026-09-15 by the night
window's `a-task-nothing-will-move-holds-nobody-r3`, which folds the repair into that change (its
design D8). **Measured** with a throwaway test through
the real firing and the real Run route, deleted before the commit.

**The mechanism.** `_loop_flow_busy_reason` (`hub/hub/scheduler.py:282-308`) refuses a firing only
when the job's agent is busy **and** `_agents_that_are_free` is empty. That second half stands in for
*"the walk could staff somebody else"*, and it is wrong in one case that matters. When the loop holds
no open task, `decide_firing` answers `DECISION_PROCEED_EMPTY` (`:1716-1720`), and the firing then
briefs **the job's own agent** to fill the queue (`:2926-3002`, `acting_agent = job.agent`). That
agent is the busy one. `schedule_agent` answers *"agent is already running"*, which is not terminal,
so the entry waits and the `JobRun` reads `in_progress`. The next tick does it again.

**Measured**, on a loop with no tasks, its job agent mid-turn, and one roster agent with a runner:

| the other agent holds | three scheduled firings | `POST /jobs/{id}/run` |
|---|---|---|
| nothing | 3 entries queued for the busy agent, 3 `JobRun`s, each firing returned `True` | **200** `{"success": true}`, and one more entry |
| one task outside any loop | refused: 0 entries, 0 `JobRun`s | (not driven) |

This breaches `agent-loops`' *"A firing is refused while its loop's agent is already running"*.
Its scenarios say *"no inbound queue entry is created for that agent"* and *"Repeated firings during
one turn do not accumulate work"*. The requirement carves out only *which agent a firing staffs*
when another is free. It does not carve out queuing for the busy agent. It is the pile-up
`loop-notices-and-reacts` D4 was built to stop, which returned through `loop-becomes-a-flow` D12. It
reaches every multi-agent project with an unencumbered agent. The held form (a job agent held by a
provider refusal) takes the same path.

**Why it is filed now.** `a-task-nothing-will-move-holds-nobody` frees agents that hold only
out-of-loop tasks. So the second row of the table turns into the first: the change would extend this
pile-up to exactly the LoopEngine-shaped projects it exists for.

**The repair** (that change's D8). The guard also refuses when the loop holds no open task. The test
is the same predicate `_stall_reason_from_walk` uses to answer `DECISION_PROCEED_EMPTY`, because
nobody else can be staffed from an empty queue. The Run route's 409 then names the running agent and
does not say *"no other agent is free"*.

**Related:** F128 (the same guard, the substitution half), F127 (the route's busy 409), F368.

## F373 (B) — pressing Run on a loop whose work is in flight answers with an earlier firing's stall reason

**Status:** fixed (2026-09-25) by `8c6cb54` (`pressing-run-names-the-reason-that-held`, archived 2026-09-25); driven 2026-09-25 on a fresh trial Hub (8026, `drive0925morning`, Haiku): the staged case answers 409 "Every task on this loop's queue is already being worked. Nothing was started, and nothing is wrong…", no JobRun row written; MCP `run_job` returns the same words.
**Status when filed:** open. Filed 2026-09-15 by the night window's `a-task-nothing-will-move-holds-nobody-r3`.
**Measured** with a throwaway test through the real Run route, deleted before the commit. Not
repaired by that change.

**The mechanism.** `run_job` (`hub/hub/api/v1/jobs.py:1338-1401`) handles a firing that returned
`False` in this order:
1. Where the firing wrote no row, ask the busy guard.
2. Then `if latest_run and latest_run.status == "skipped"`, answer 409 with that row's
   `error_summary`.
3. Only then ask whether the decision was `DECISION_IN_FLIGHT`.

Step 2 is not gated on `wrote_row`. It is right for a **continuing** stall, which counts into the
earlier row and discards its own. It is wrong for an in-flight decline, which writes nothing at all
(F23). The newest row is then some earlier firing's skipped row.

**Measured.** The staging:
- the job agent is mid-turn on the loop's only task (`in_progress`, assigned to it);
- another roster agent is free, so the guard passes;
- the newest `JobRun` is an earlier firing's `skipped` row reading *"loop queue is stalled: 1 still
  awaiting a prerequisite's approval"*.

`decide_firing` answered `in_flight`. The route answered **409** with that stale sentence. The
operator is told the queue waits on a prerequisite while its only task is being worked.

This breaches `agent-loops`' *"Pressing Run on a loop that declines names why it declined"*: *"The
route SHALL answer from a firing record only when the manual firing wrote that record."* A counted
stall arguably did write to that row, and an in-flight decline did not. The route cannot tell the two
apart today, because it compares row ids and a counted stall keeps the id.

**Reach.** Any project where the guard passes while the job agent is busy, meaning any multi-agent
project with a free agent. `a-task-nothing-will-move-holds-nobody` widens that set (its design D3,
Round 3), the same way it widens F128's.

**The repair (sketch).** Before firing, read the newest row's `tick_count` together with its id.
Answer from that row only where it is new, or where its `tick_count` moved. Otherwise fall through to
the in-flight question. Route-only.

**Related:** F369 (the same comparison, for stamping), F48, F23, F127.

**Note, 2026-09-15 (`a-task-nothing-will-move-holds-nobody` archived, fix `4b59ee0`, design D3
Round 3).** That change widens this finding's reach. The in-flight decline was already reachable
wherever a free agent existed. It now also reaches projects where the only free agents hold nothing
but out-of-loop tasks, because those agents are now free. Not repaired there, and still open.

**Note, 2026-09-23 (D-3b, R2 of `pressing-run-names-the-reason-that-held`).** Two more instances of
the same shape, measured through the route. A firing that **raises before its row exists** writes
nothing (`_do_fire_job`'s `except` guards on `"run" in locals()`), and was answered 409 with an
hour-old stall. A firing that **raises after its turn started** writes `failed`, and the route
re-decided the loop before reading it: 409 *"already being worked … nothing is wrong"*. Both folded
into that change's D3 (tasks 1.12, 1.13).

## F374 (B) — a review refused by the evidence gate is re-staffed to a second reviewer, who meets the same gate, and the surfaced reason blames staffing

**Status:** fixed a8a0b32, driven live 2026-09-26 (drive Hub :8033, profile drive0926b, real Haiku: beta reviewed, was refused by the gate, no entry for gamma, task stayed with beta, run_diverged `surfaced` with the gate's sentence, flow card said approval waits on the operator; accepting the evidence then approving worked). Filed 2026-09-15 by the night window's drive of
`a-task-nothing-will-move-holds-nobody` (drive Hub `:8013`, `profiles/drive0915`, project
`proj-4297ab5fd02c`, task `task-f3bb989a5b1c`). **Measured live, twice** (the control and archived
lanes), in real Haiku turns. Not caused by that change; it widens the reach (below).

**What happened.** A flow's task was completed by `alpha`, with evidence naming a commit left
`awaiting`, because the drive never accepted it. `beta` was staffed for the review, read the spec,
verified the file, and called `update_task(status="approved")` three times. Each was refused 409 by
the shipped gate: *"This task's work has been recorded and nobody has judged it: FR-1 at 0000dd23c0e0.
… both are the operator's, so an agent reading this has to ask for one rather than take it."* `beta`
then did what F152's drive says it should: it stopped, and messaged `alpha` that the review was
complete. The turn ended with the task still `under_review`, so it was divergent, and the review
policy (`run_divergence.py:430-471`) **re-staffed it to `gamma`** (`run_diverged`: `outcome:
restaffed`, `response_agent: gamma`). `gamma` read the spec, verified, called
`update_task(approved)`, got the identical 409, and stopped. Its divergence was surfaced with:

> could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task and so may not
> review it.

**Three things wrong at that seam:**
1. **A second review turn is spent on a refusal that no reviewer can clear.** The gate names a
   remedy that belongs only to the operator. The re-staff never asks why the first review ended
   without a verdict.
2. **The surfaced reason is false for this task.** `beta` was idle, and holding only an out-of-loop
   task. It was barred as a reviewer that gave no verdict (`_reviewers_that_gave_no_verdict`, `:430`),
   which the sentence does not list. The blocker is unjudged evidence, and the sentence does not name
   it.
3. **The operator is told about staffing, not about the evidence waiting for them.** What would
   move the task is accepting the evidence.

**Why this change widens it.** Under the old rule, `gamma` held a `pending` out-of-loop task and
counted as busy, so the re-staff would have been surfaced at once. Under reachability, `gamma` is
free, so the wasted turn happens. That matters in the week the rate-limit window counts.

**A repair has to decide, not proposed:** whether a review turn whose approval the evidence gate
refused counts as *"ended without a verdict"* at all, or as a verdict the reviewer could not record.
If the second, the divergence would surface the gate's own sentence to the operator, and not
re-staff.

**Also seen, and correct as designed:** in a project with several documents, `record_evidence` without a
document answers 422 *"FR-1 is declared by more than one document in this project. Name the document
it belongs to."* The reviewer did not retry with a document, and nothing required it to.

**Reproduce:** `scripts/drive/t_d0915_reachability.py`, the `control` lane with its evidence left
`awaiting`. Then `GET /projects/{P}/logs?event_type=run_diverged`.

**Related:** F152 (the gate's sentence reaches the agent), F154/F167 (a review with no verdict),
F352 (the rung-3 sentence names nobody), F316 (the re-staff's exclusion set).

## F375 (A) — a bare `..` argument has no separator, so rule 4 calls it "not a path" and never checks it

**Status:** fixed a5e5a49. Filed 2026-09-15, found by an adversarial verification round measuring
`a-quote-can-spell-a-slash`'s candidate correction against real Git Bash — unrelated to that
change's own ANSI-C question, and not fixed by it. Fixed by
`a-word-without-a-separator-can-still-leave`: rule 4 now checks a bare `..`, a colon-joined value,
a glued short-option value, and a leading `~`, verified against real Git Bash and PowerShell
(tasks 3.1-3.2).

**The mechanism.** `_judge_word` (`hub/hub/mcp_server.py:1129-1155`) checks six rules in order
against each word of a shell command, and rule 4 reads:

```python
has_separator = any(separator in word for separator in _SEPARATORS)
...
if not has_separator:  # 4: not a path
    return None
```

`..` contains no `/` or `\`, so `has_separator` is `False`, and rule 4 waves it through with no
call to `_where` at all — no resolution against the workspace root, no `commonpath` check,
nothing. Every other rule that could catch a traversal (5, the plain-relative path judge; 6, the
backstop regex) is gated behind `has_separator`, so none of them ever see a bare `..`.

**Measured** (real Git Bash, workspace a subdirectory with `notes.md` inside): `cp notes.md ..`
is answered **allow, "inside your workspace"**, and the copy lands one level above the workspace
root — outside, on every platform, with no escape, no quoting, and no locale dependency. `mv`,
`cat >>`, and any other tool that takes a bare `..` as a path argument have the identical hole,
since they all route through the same `_judge_word`.

**Confirmed live 2026-09-22**, through the real `approve_tool_call` pipeline rather than the
unit suite or a standalone shell probe: fresh Hub on port 8011, database
`~/.agentweave/hub/profiles/drive0922/agentweave.db`, project `proj-7a2c8bbaaa50`, agent
`F375Agent` bound to `claude/claude-haiku-4-5-20251001`, `permission_mode: workspace` (the
posture that routes through `_decide`, not the operator). Two real turns
(`run-1c656060c523`, `run-bff134d520df`) issued the Bash tool with the four attack shapes and two
false-positive controls; the transcript shows each `tool_result` and the agent's own read of it:

- `cp notes.md ..` (bare `..`) → `tool failed`, *"Denied: '..' is outside your workspace."*
- `cp notes.md ~` (leading `~`) → `tool failed`, *"Denied: '~' contains a variable, '~' or a
  command substitution ... cannot be checked ..."*
- `cp -t.. notes.md` (glued short-option) → `tool failed`, *"Denied: '-t..' is outside your
  workspace."*
- `dotnet publish -o:..` (colon-joined option value) → `tool failed`, *"Denied: '-o:..' is
  outside your workspace."*
- False-positive controls, all `tool completed` with no denial: `mkdir -p sub && cp notes.md
  sub/copy.md`, `cp notes.md ./local-copy.md`, `cp -t sub notes.md`.

All seven land exactly as `a-word-without-a-separator-can-still-leave`'s tasks.md claims. Project
cleaned via `e2e.py clean`; the drive Hub process was stopped afterward (no job left enabled, no
credential left minted). This closes the "driven, not merely unit-tested, through the live agent
tool-call path" gap the fix's own record noted it hadn't covered.

**Why this was not caught by four rounds of `a-quote-can-spell-a-slash` review.** That change's
whole argument is about what an *escape sequence* can decode to; a literal, unescaped `..` with
no separator character was never a form any of its test rows constructed, because the change's
own scope is ANSI-C decoding, not the six-rule judge's separator gate. The verification round
that found this was adversarially testing the *ANSI-C* correction's compound-path cases and
constructed `cp notes.md $'..\x00x'` as one of them; the NUL only mattered because it truncates
the word down to `..` — the truncation exposed a hole in rule 4 itself that has nothing to do with
NUL, ANSI-C, or the escape decoder. **Do not fix this inside `a-quote-can-spell-a-slash`** — that
change should pin the truncated-word row as evidence the hole exists, but the repair belongs to
rule 4 itself: a bare `..` (and, by the same gap, a bare `.`, and any word that is *only* `.`/`..`
segments joined by nothing, though only `..` moves the boundary) needs to be judged by resolving
it against the workspace root exactly as rule 5 already does, not exempted as "not a path".

**Reach.** Every project, every runner, every tool that accepts a bare `..` as an argument —
`cp`, `mv`, `cat`, `tee`, any shell redirect target. No special crafting needed; this is the
plainest possible traversal and the sandbox does not check it at all today.

**Related:** F332 (the ANSI-C decode question this was found alongside, and does not fix this).



**Note, 2026-09-23 (day window, D-2b R1).** Proposed as `openspec/changes/pressing-run-names-the-reason-that-held` (design D3), with F400. Re-measured on `dcdf723`: still reproduces. **The repair sketch above has a trap, measured.** `run_job` passes its own session to `_fire_job_internal`, the factory is `expire_on_commit=False`, and `_stall_run_to_increment` returns the very object the route read before firing (`same_object=True`, `tick_count` 1→2 in place). So `tick_count` must be copied to an `int` before the firing, or the comparison is always "unchanged".
---

## F376 (A) — `create_flow` is refused for a setting the operator was never asked about, and the refusal promises an approval that is never requested

**Status:** fixed 229a708 (with the review fixes `24f3655` and `a4d0976`, and its prerequisite F386 in `6ab4a4a`), by `a-refused-capability-reaches-the-operator`, archived 2026-09-22 (interactive, with the operator). An agent refused scheduled work now gets an honest 403 naming `allow_agent_jobs`, and the operator gets a non-blocking question of record, at most two per project, kept out of agent trays. **Driven live** on a fresh `:8095` Hub with Haiku (`scripts/drive/d_0922_f376_refused_capability.py`, 16 ok / 0 bad). After the operator enabled the setting and answered, the woken agent re-created the flow itself. An adversarial Opus review returned SHIP WITH FIXES, and they were applied. Full hub suite on the final tree: 4568 passed, 86 skipped. CI green at `2bc2e7a`. **On `:8000` it takes effect only at the next restart.** Filed 2026-09-17 by an interactive session, from `LoopEngine_2`
(`proj-f90d219dd68c`) on `:8000`, read-only.

**Source:** drive — found by exercising the product and reading what it actually recorded.
**Theme:** Flows & loops

**What happened.** At 17:36 the operator told the Architect *"spec approved is the flow ready? If
it's not please create it and send distribute the tasks and start the development. I'm leaving for
a little bit."* The Architect called `create_flow` at **17:37:45** and was refused:

```
Error calling tool 'create_flow': Hub rejected POST /jobs (403):
Scheduled work from agents requires operator approval or an enabled allowance
```

**Thirty-seven seconds later** it sent the first of what became 20 hand-driven `send_message`
calls, because a message is the only dispatch left to an agent that cannot create a job.

**The refusal names an approval path that does not exist.** `permission_requests` holds **zero
rows** for this project. No card reached Needs-you, no event was broadcast, and the operator —
who had just said they were leaving — had nothing waiting for them on return. The refusal exists
only inside the Architect's own transcript, where nothing reads it.

**The cause is `projects.allow_agent_jobs`, default `0`.** It is `1` on the operator's older
`LoopEngine` project, so this is specifically what a *new* project gets.

**What it cost, measured on the same database.** Everything below follows from those 37 seconds:

- `loops` and `ai_jobs` hold **0 rows** for the project. No flow ever existed.
- A flow firing enters the queue at `hop_depth=0` (`scheduler.py:3111`, `:3443`), so each firing
  resets the hop chain. Hand-driven messages inherit `+1` and never reset. The whole build ran as
  one chain off the operator's 17:36 message and died at hop 7 against a budget of 6 — **6 entries
  suspended**, including *"Teste accepted all six evidence rows … then start t-create"*, the one
  message that would have advanced the build.
- Only a flow dispatch writes a reviewer into `assignee` and enters a task at `under_review`
  (`scheduler.py:838-849`). Reviews arriving as messages move no task state, so `t-package` stayed
  `completed`, `_guard_reviewer_is_not_the_author` then refused every `completed → under_review`
  move **including the operator's**, and `dependency_gate.MET_STATUS = "approved"` froze all 31
  remaining tasks behind it. The ledger deadlocked at **17:56**, 23 minutes into a 2h22m session.
- **0 of 32 tasks reached `approved`.** $26.81 of API-equivalent spend across 21 runs.

**Where.**
- `hub/hub/api/v1/agents.py` — the `POST /jobs` allowance check that raises the 403.
- `hub/hub/db/models.py:Project.allow_agent_jobs` — `default=False, server_default="0"`.
- `hub/ui/src/components/environment/ProjectSettingsPanel.tsx:146` — the only control that sets
  it, row 6 of 16 in one flat list, in the 8th of 8 Environment sections, and Environment is not
  one of the five project tabs (`lib/navigation.ts:26`).

**Two repairs, and they are not the same repair.** Either the 403 writes a `permission_requests`
row so the sentence becomes true, or its wording stops promising an approval and instead names the
setting and where it lives. Doing neither leaves a refusal that sends the operator looking for an
approval that was never going to arrive.

**Related:** F377 (no operator surface creates a flow at all), F379 (the setting's invisibility),
F361 and F363 (both reproduced by this same run).

---

## F377 (B) — no operator surface creates a flow, and the one loop form cannot name a specification document

**Status:** fixed `72d2e8b` (2026-09-27, interactive). `a-flow-is-configured-from-its-own-tab` (`45e84fd`) shipped the Start a flow dialog, flow link and loop settings tab; `a-document-says-how-it-will-be-built-and-approval-starts-it` (`72d2e8b`) makes approval start the flow the document's delivery declares. Driven 2026-09-27 ("r1b drive"). Filed 2026-09-17 by an interactive session, alongside F376.

**Source:** operator — the operator asked for this in session; it is a requested improvement, not a defect found by driving.
**Theme:** Flows & loops

**Measured against `hub/ui/src`.** `create_flow` — the tool that decomposes an approved
specification document and staffs every task whose prerequisites are met — appears in
`hub/hub/mcp_server.py`, `hub/hub/scheduler.py` and `hub/hub/api/v1/agents.py`, and in **no UI
component**. The only operator-facing surface that creates a loop is the *"Make this a loop"*
section of `components/jobs/JobForm.tsx`, collapsed by default, inside a cron-job form — and
`JobForm.tsx` contains **no `spec_document` field of any kind**, so a loop an operator creates
cannot be bound to the document it implements.

On the spec page itself, `components/spec/LoopTab.tsx` and `LoopsIndexTab.tsx` only *display*
loops. Neither carries a create action.

**Consequence.** From an approved specification document — the one place a flow obviously belongs —
the operator's only route to start one is to ask an agent to call `create_flow`. That is exactly
what happened in F376, and it was refused by a setting with no visible state.

**Related:** F376, F206 and F211 (the same shape for the spec flow's own routes), F28.

---

## F378 (B) — `request_agent` reads templates from a table no surface writes, and it is empty in every project on this Hub

**Status:** fixed (2026-10-12, night ledger-sweep-2) by `request-agent-models-the-new-agent-on-one-the-operator-made` (archived 2026-09-29; template = an existing open agent): `request_agent` reads an `Agent` row; `test_request_agent_models_an_existing_agent.py` passes. Older text kept below.

**Earlier status:** open. Filed 2026-09-17 by an interactive session, from `LoopEngine_2` on `:8000`.

**Source:** drive — found by exercising the product and reading what it actually recorded.
**Theme:** Agents & runners

**What happened.** At 16:34 the operator asked the Architect *"Okay two developers set what else?"*
The Architect called `request_agent` at **16:35:39**:

```
Error calling tool 'request_agent': Hub rejected POST /agents/request (400):
Agent template 'developer' is not pre-approved for this project
```

The operator created `Developer_2` by hand instead, at 16:34:13.

**Why it can never succeed.** `hub/hub/api/v1/agents.py:2051-2058` reads templates from
`_get_session_data(project_id)`, backed by the `project_sessions` table. No route under
`hub/ui/src` writes that table, and:

```
select count(*) from project_sessions;                     -> 0
select count(*) from project_sessions where project_id=?;  -> 0
```

**Zero rows across the entire Hub**, not merely this project. `templates.get(body.template)` is
therefore `None` for every template name, on every project that exists, so the 400 is the only
answer this route can give. The tool is described to agents in `agents.py` as *"Request a new agent
from a pre-approved template under the project agent budget"* and is shipped in the MCP surface.

**This is not the same defect as F377.** That one is a missing control for a working backend; this
one is a working tool whose only input has no producer.

**Related:** F376, F377, F3 (which mentions `request_agent` for a different reason).

---

## F379 (B) — the five settings that decide whether a collaboration can run are indistinguishable from the ones that pick a title style

**Status:** fixed (this commit) by `the-settings-that-gate-collaboration-are-on-the-project-page` (R2, 2026-10-08, interactive with the operator): the Overview gains a Collaboration block (live values, the flows switch in place) and per-agent grant chips, flags and collapsed details; Settings is grouped. Acceptance drive `scripts/drive/d1008_project_page_settings.py` 10/10 on the built bundle. Two side findings filed: F557 (agent budget label), F558 (evidence retention applies nothing). Was: open. Filed 2026-09-17 by an interactive session, from `LoopEngine_2` on `:8000`.

**Source:** operator — the operator asked for this in session; it is a requested improvement, not a defect found by driving.
**Theme:** Operator surfaces

**The measurement.** `ProjectSettingsPanel.tsx` renders **16 `SettingsRow`s under one heading**,
`"Settings"`, in one undifferentiated flat list with no grouping. Five of those rows decide whether
agents can collaborate at all; ten are preferences. They are rendered identically.

| row | field | default | what it gates |
|---|---|---|---|
| 2 | `hop_budget` | `6` | agent-to-agent chain length; one build + one review round + one follow-up is six |
| 3 | `turn_delivery_cap` | `10` | how much of a frozen backlog clears per turn |
| 4 | `agent_budget` | `8` | parallelism ceiling a flow can use |
| 5 | `token_budget` | `null` | **uncapped by default** |
| 6 | `allow_agent_jobs` | **`0`** | whether any agent may create a flow at all (F376) |

Reaching them: Environment is **not** one of the five project tabs
(`PROJECT_TABS = ['overview','tasks','spec','jobs','activity']`, `lib/navigation.ts:26`); it is a
sidebar rail destination, and `settings` is the **8th of 8** `ENVIRONMENT_SECTIONS`.

**The per-agent half is worse, because it varies silently between agents.** `can_accept_evidence`,
`can_read_checkpoints` and `can_recall` all default to closed and live in `Access`, the **6th of 7**
`AGENT_SETTINGS_SECTIONS`. Measured on this project:

```
Architect     0  0  0        charter: charter-a10e3ea6d59c
Developer     0  0  0        charter: charter-c6943c48d0a7
Developer_2   0  0  0        charter: charter-c6943c48d0a7
Teste         1  1  1        charter: NULL
```

Only Teste could decide evidence, so **every** evidence decision round-tripped to Teste — and each
round trip spent two of the six hops F376 describes. Teste also ran the entire review programme
with no charter while both developers had one. Nothing on the roster, the overview or the agent
list shows either fact.

**Not the same as F237**, which is about two controls writing `token_budget` through different
routes and leaving surfaces stale. This is about where the controls sit and that their state is
invisible until opened.

**Shape of the repair, for the proposal to argue with.** Surface the five project-level controls
and the per-agent grants on the project's own page **as live values rather than as fields** — `Off`
is legible at a glance, an empty input is not — and leave them editable where they already are.

**Related:** F376, F377, F378, F237, F39, F88.


---

## F381 (C) — a question nobody is waiting on outranks one an agent is blocked on, in that agent's own tray

**Status:** fixed a4d0976 for the agent tray (2026-09-22; see the foot, which also names the surfaces this does not cover). Was: open. Filed 2026-09-18 by the day window's R3 round for
`a-refused-capability-reaches-the-operator`, from reading the code rather than from a drive.

**Source:** code — found by reading, while re-deriving a proposal against the implementation.
**Theme:** Operator surfaces

**The measurement.** `activeQuestionFor` (`hub/ui/src/lib/pendingQuestions.ts:24-46`) chooses the one
question shown in an agent's conversation tray. It filters `from_agent === agent && !answered &&
!declined` — **no `blocking` filter** — and sorts `asker_waiting !== false` first (`:38`), explicitly
so that *"Questions someone is actually waiting on come first"*, then `batch_index`, then oldest
`created_at`.

But `asker_waiting` is not a fact about waiting when the asker is unknown. `_with_asker_state`
computes `wait_ended_at is None and created_by_run_id not in ended`
(`hub/hub/api/v1/questions.py:333-344`), documented as *"Unknown asker → presumed waiting"*. For any
question with **no run** — every one posted through the operator route, which passes
`created_by_run_id=None` (`questions.py:293`) — that expression is **always `True`**.

So a question nobody is waiting on sorts with the genuine waiters, and if it is the older of the two
it is the one the tray shows while the agent is really blocked on the newer one. That is the exact
defect the sort was written to prevent, arriving through the field it sorts on rather than through
the order.

**Not yet observed live**, and deliberately labelled: it needs an operator-posted question and a
blocking one outstanding for the same agent at once. The ordering above is read, not driven.

**Shape of the repair, for a proposal to argue with.** Either `asker_waiting` stops presuming for a
question that is **not blocking** (nothing is waiting on a note, by definition — `_asker_still_waiting`
already reads `blocking` for exactly this reason, `questions.py:48-73`), or the tray's sort reads
`blocking` itself. The first is one expression and fixes every reader; the second is local but leaves
the field lying.

**Why it is filed now.** `a-refused-capability-reaches-the-operator` opens a non-blocking question
with no run, so it inherits this (that change's design **D14**): the change records the cost and
deliberately does not repair it from inside one refusal's blast radius, because the behaviour belongs
to every run-less question and not to that record.

**Related:** F376 (the change that surfaced it), F14 (attention state reported about a run that is
not waiting).

**Fixed 2026-09-22 for the tray this entry is about, by `a4d0976`, an F376 commit that did not name it.** `activeQuestionFor` (`hub/ui/src/lib/pendingQuestions.ts`) keeps any question with `created_by_run_id === null` out of the agent tray. Every question posted through the operator route has that null, so none can outrank a live one there. That is the second, tray-local repair shape above. `24f3655` (`isWaitedOn` also requires `blocking`) is **not** enough by itself. The new test `refusalRecordTray.test.ts` *"does not let an older question posted through the operator route outrank a live one (F381)"* uses a **blocking**, runless, older question and a newer live one, both `asker_waiting: true`. It passes at HEAD and fails against `24f3655`'s own `pendingQuestions.ts` (`expected 'q-posted' to be 'q-live'`), as well as on `24f3655^`. **Not fixed, and the same defect: the other surfaces.** The Hub still presumes an unknown asker is waiting (`_with_asker_state`), and the operator route accepts `blocking: true` with no run. So a blocking operator-posted question still ranks as *waiting* on the Overview card (`QuestionInterruptCard.tsx`, "X is waiting") and under *Blocking - agents are waiting for your answer* in `QuestionsPanel.tsx`, with the urgency timer. This is reachable only through the API today. It belongs with F146 (operator-posted blocking questions, D13), and the first repair shape above (the Hub stops presuming) would fix all three. Found by the Opus review of this session.

---

## F383 (C) — the CI branch's own commits fail on a genuine flaky test, not only on the docs-only commits noted earlier

**Status:** fixed b630252 (symptom B, as F292) and 2026-09-18 (symptom A). Closed 2026-09-22 by
the interactive session (Round 1): symptom B was F292's failure under a second number, and F292's
fix covers it. See CLOSED at the end of this section. Filed 2026-09-18 by the day window, from CI
history.
**Source:** audit
**Theme:** Harness & CI

**Where noticed:** iteration 20's D-0 gate check (2026-09-18 ~10:25 UTC), reading `gh run list` and
`gh run view --log-failed` over the branch's own recent CI history while measuring condition 3, not
from a drive.

**What the run shows.** The gate's `decisions_for_user['merge-gate-cadence']` entry and this file's
own notes had, until now, only two failures on record — `a392e9b` and `798b2a5`, both flagged as
"docs/state only" commits, with nobody having looked at why. A third failure now sits alongside
them: `5b29c2f` (iteration 15's retry commit, also state-only — it only touches `STATE-day.json` and
the log), run `35332995674`, concluded `failure` at `10:23:10Z` after `16m48s`. Its `hub-test` job's
own tail is a real, specific error, not a docs-lint or generic exit:

```
ERROR tests/test_reviewer_is_not_the_author.py::test_a_wedged_review_is_restaffed_to_a_real_reviewer
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[SQL: BEGIN IMMEDIATE]
===== 4432 passed, 20 skipped, 248 warnings, 1 error in 968.07s (0:16:08) ======
```

One error out of 4432+20 collected, on a `BEGIN IMMEDIATE` against a locked sqlite file — the shape
of two connections racing for a write lock, not a logic bug in the test's assertions. The suite
otherwise ran clean.

**Why this matters to the open decision.** `decisions_for_user['merge-gate-cadence']` frames the
gate's problem as purely a *timing* one (CI takes 13+ minutes, firings are closer together than
that) plus an unexplained pair of docs-only failures assumed unrelated. This finding shows a third,
non-docs-content commit failing CI for an entirely different, concrete reason: a flaky sqlite lock in
one specific test. That test's own name (`test_a_wedged_review_is_restaffed_to_a_real_reviewer`)
implies concurrent DB access is exactly what it exercises, which is a plausible self-contention
source independent of anything this branch's commits touch. This does not resolve the docs-only
pair's cause (still unlooked-at), but it does mean the operator's merge-gate-cadence decision is
being asked against an incomplete picture: even a firing that waits out the full CI run (option (b))
could still see this branch's gate fail on an intermittent test-suite flake unrelated to timing.

**Not investigated further this iteration:** whether `a392e9b`/`798b2a5` show the same
`database is locked` failure (their own job logs were not re-pulled here — this file's earlier notes
already labelled them "docs/state only" without a log excerpt); whether the flake is reproducible
locally; whether it is specific to `test_reviewer_is_not_the_author.py`'s fixtures or a broader
sqlite-under-CI contention issue. Filed from reading CI history, not from a drive; no code changed.

**UPDATE, iteration 22 (2026-09-18 ~10:30 UTC):** a second, independent instance landed while
retrying D-0's gate. `c0070c0` (iteration 18's retry commit, also state-only), run `35333364732`,
concluded `failure` at `10:27:15Z` after `952.38s` (15m52s) — same file, a *different* test:

```
ERROR tests/test_reviewer_is_not_the_author.py::test_assigning_a_reviewer_and_sending_to_review_in_one_patch_is_accepted
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[SQL: BEGIN IMMEDIATE]
===== 4432 passed, 20 skipped, 248 warnings, 1 error in 952.38s (0:15:52) ======
```

Two different tests in `test_reviewer_is_not_the_author.py`, both erroring on the same `BEGIN
IMMEDIATE` lock, across two different state-only commits (`5b29c2f`, `c0070c0`) — this is no longer
a single anomalous run. The shape now points at the file's own fixtures (shared sqlite handle, or a
review-staffing helper that opens a write transaction without retry/backoff) rather than a one-off
CI scheduling fluke. Still not investigated further: reading that test file's setup/teardown to find
the shared resource. Filed from reading CI history during the routine D-0 check, not from a drive;
no code changed.

**Related:** F382 (a different, unreproduced pytest stall, on this machine rather than in CI — not
obviously the same mechanism, but both are unexplained sqlite/test-run timing issues surfacing
around this branch's own test runs).

**UPDATE, iteration 24 (2026-09-18 ~10:37 UTC):** a third instance landed, and it changes the shape
of the finding. `6fbcf10` (iteration 17's retry commit, also state-only), run `35333792012`,
concluded `failure` at `10:33:25Z` after `1027.32s` (17m07s):

```
FAILED tests/test_flow_holds_the_loop_requirements.py::test_one_turn_finishing_answers_for_itself_and_not_for_its_siblings
  - RuntimeError: <asyncio.locks.Lock object at 0x7f8bc79ce0d0 [locked]> is bound to a different event loop
ERROR tests/test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[SQL: BEGIN IMMEDIATE]
= 1 failed, 4431 passed, 20 skipped, 248 warnings, 1 error in 1027.32s (0:17:07) =
```

This is no longer confined to `test_reviewer_is_not_the_author.py`: the same `BEGIN IMMEDIATE`
lock error now also hit `test_flow_fires_a_review_turn.py`, a different file entirely, and this run
additionally carries a second, distinct failure mode never seen before — a locked `asyncio.Lock`
bound to the wrong event loop, in `test_flow_holds_the_loop_requirements.py`. Both symptoms read as
cross-test interference under whatever parallelism/ordering the CI job uses (a lock or connection
created in one test's event loop reused in another's), not as a defect isolated to one file's
fixtures as the iteration-22 update suggested. This broadens, not narrows, what the operator's
merge-gate-cadence decision is weighing: the CI flake is not one file's problem, and waiting out a
conclusion (option (b)) does not bound how often a green run happens. Not investigated further:
whether this is xdist-style worker reuse, a module-scoped fixture holding a connection/lock across
tests, or something in `conftest.py`'s event-loop handling. Filed from reading CI history during the
routine D-0 check, not from a drive; no code changed.

**UPDATE, iteration 27 (2026-09-18 ~10:56 UTC):** a fourth instance, caught only because this run
took unusually long to conclude — `4dc2d72` (iteration 23's retry commit, also state-only), run
`35335492002`, sat `in_progress` through iterations 24, 25 and 26's checks before finally concluding
`failure` at (per `gh run view`) roughly `10:52:38Z`, over 16 minutes after its `10:35:58Z` creation:

```
ERROR tests/test_flow_fires_a_review_turn.py::test_a_flow_fired_reviewer_reads_a_file_that_is_not_on_main
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
[pool log:     asyncio.exceptions.CancelledError]
```

Same `BEGIN IMMEDIATE`-shaped lock, same file as one of iteration 24's two failures
(`test_flow_fires_a_review_turn.py`), but a third distinct test name within it. Four instances now,
three different files, at least three different test names, one shared `database is locked`
mechanism plus the one wrong-event-loop outlier from iteration 24 — reinforcing iteration 24's read
that this is cross-test interference under the CI job's own concurrency, not a single file's fixture
bug, and that it recurs often enough (4 of the last ~10 runs on this branch) that option (b) of the
operator's still-open `merge-gate-cadence` decision (wait out a conclusion) would not reliably land
green either. Filed from reading CI history during the routine D-0 check, not from a drive; no code
changed.

**UPDATE, iteration 29 (2026-09-18 ~11:08 UTC):** a fifth instance, and it closes the "unexplained
docs-only failures" question this file has carried since the first two entries. `cc12402` ("backlog:
regenerate for F381-F383 and the drain at 2" — a backlog-page/state commit, touching no test or
application code), run `35337170276`, concluded `failure` at `11:08:55Z` after `714.28s` (11m54s):

```
ERROR tests/test_flow_fires_a_review_turn.py::test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn
  - sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) database is locked
===== 4432 passed, 20 skipped, 248 warnings, 1 error in 714.28s (0:11:54) ======
```

Same `BEGIN IMMEDIATE`-shaped lock, same file as two earlier instances
(`test_flow_fires_a_review_turn.py`), a fourth distinct test name within it — and this time on a
commit that could not plausibly have introduced a code-level race, since it changes only
`spec-queue/BACKLOG.html` and `.md` sources. This confirms the mechanism is genuinely commit-content-
independent: the two "unexplained docs-only" failures this file originally flagged (`a392e9b`,
`798b2a5`) were very likely the same flake, not a separate unlooked-at cause as previously assumed.
Five instances now, at a rate of roughly 1 in 2 of this branch's recent CI runs — strengthening the
read that `merge-gate-cadence` option (b) (wait out a conclusion) is not a reliable fix, since the
failure rate is too high for "wait longer" to help. Filed from reading CI history during the routine
D-0 check, not from a drive; no code changed.

**ROOT CAUSE, 2026-09-18 ~12:40 (interactive session, at the operator's instruction "how can we
correct the flakiness of the tests").** All five instances were re-read from the CI logs together
rather than one at a time, and they are **one mechanism with two symptoms**, not the "cross-test
interference under CI's parallelism" the entries above concluded.

**Two corrections to what is written above first**, both measured, because the wrong reading was
steering the `merge-gate-cadence` decision:

1. **There is no parallelism.** `.github/workflows/ci.yml:136` runs `pytest tests/ -v` with no
   `-n`. `xdist` is installed and never invoked; the run is sequential. Anything above that reasons
   from "CI's parallelism/ordering" is reasoning from a property the job does not have.
2. **Every one of the four `database is locked` failures dies on `BEGIN IMMEDIATE`, never on a
   `DROP`.** That is precisely, and in writing, what `hub/tests/conftest.py:737-740` predicted when
   it added that statement: *"If F292 survives this, the holder arrives before the reset rather than
   during it, which is a different finding and a much narrower one."* F383 **is** that finding. It
   is a successor to F292, not a recurrence of it.

**The mechanism.** `conftest.py`'s autouse `_no_connection_outlives_its_event_loop` cancels every
still-registered background run at the end of every test (`:591-597`) — the normal path, not a
fallback. When a cancel lands inside `turn_scheduler.py:283`:

```python
async with _lock_for(project_id, agent), async_session_factory() as db:
```

two things leak, and each is one of the observed symptoms:

- **Symptom A, the lock.** `_lock_for` (`turn_scheduler.py:66`) caches an `asyncio.Lock` per
  `(project_id, agent)` in a module-level dict `_agent_locks` (`:32`) that nothing cleared. The
  cancelled task never releases it and the loop closes, so the next test asking for the same key —
  and `proj-test`/`dev` repeat constantly — gets a lock still marked `[locked]` and bound to a dead
  loop. `6fbcf10`'s failure is exactly this, with `[locked]` in the repr.
- **Symptom B, the transaction.** The same cancel catches the connection on its way back to the
  pool. Three of the four runs carry one `sqlalchemy.pool` ERROR for the entire session:
  `_finalize_fairy` -> `do_rollback` -> aiosqlite `rollback` -> `asyncio.exceptions.CancelledError`.
  The rollback never completes, so a write transaction stays open and the next test's
  `BEGIN IMMEDIATE` — the first statement in the suite to demand the write lock up front — waits
  out its busy timeout and fails at *setup*, blast radius exactly one test.

**Symptom A is fixed** (this commit): `conftest.py` gained autouse
`_module_level_async_primitives_are_per_test`, which rebuilds `_agent_locks` and the four other
module-level `asyncio` primitives on both sides of every test.
`hub/tests/test_module_level_async_state_is_per_test.py` is the regression test, and it was
**verified to fail with the fixture removed** — reproducing `<asyncio.locks.Lock object at 0x...
[locked]>` surviving into the next test locally, the same signature as the CI traceback — rather
than only verified to pass with it present.

**Symptom B is NOT fixed, and three things now constrain whoever takes it:**

1. **A retry/backoff around the schema reset is not the fix, and would have looked like one.**
   `conftest.py:115` already sets `PRAGMA busy_timeout=30000`. The holder therefore survives a full
   **30 seconds**, so a short retry cannot clear it — while still being long enough to make a green
   local run and read as a success. This was the first fix considered here and it was discarded on
   this measurement.
2. **The holder is invisible to the existing census, and the census has a structural blind spot.**
   `_EVER_SEEN` is keyed by `id(connection_record)` (`conftest.py:333,347`), and CPython reuses an
   `id` once an object is collected. Across the 187-359 connections a run churns through, a later
   record can silently overwrite a leaked one's entry. "0 with an OPEN sqlite3 handle" is therefore
   weaker evidence than it reads as, and it should not be taken as proof the holder is outside
   SQLAlchemy's bookkeeping.
3. **The path is reproducible locally without CI.** Running the three affected files on this machine
   emits `PytestUnhandledThreadExceptionWarning` from `aiosqlite/core.py:75`
   `_connection_worker_thread` -> `future.get_loop().call_soon_threadsafe(...)` ->
   `RuntimeError: Event loop is closed`: an aiosqlite operation still in flight on the worker thread
   when the test's loop closed, which is the same "result can never be delivered" shape as the
   cancelled rollback. CI is not special here; it just loses the race more often.

**Where.** `hub/tests/conftest.py:591-597` (the cancel), `:713-752` (the reset that pays for it),
`:115` (the 30s timeout), `:333,347` (the id-reuse blind spot); `hub/hub/turn_scheduler.py:32,66,283`.
Runs: `35333792012` (`6fbcf10`, symptom A + B), `35335492002` (`4dc2d72`), `35333364732` (`c0070c0`),
`35332995674` (`5b29c2f`), `35337170276` (`cc12402`).

**Severity is left at (C) deliberately** — by this file's own taxonomy it is test-harness friction,
not product behaviour — but it has cost a full day's merge gate and ~$9 of retries, so raising it is
worth the operator's call rather than mine.

**CLOSED 2026-09-22 (interactive session, Round 1 of `spec-queue/ROUNDS.md`).** Symptom B is not a
separate defect. It is F292 under a second number: the same tests
(`test_reviewer_is_not_the_author.py`, `test_flow_fires_a_review_turn.py`), the same
`database is locked` on the schema reset's `BEGIN IMMEDIATE` at setup, the same F292 diagnostic
printed under it. F292 was fixed by `b630252` (2026-09-21 22:58Z), which gives every `app` test its
own database file. A write transaction leaked on the previous test's file, whatever leaked it, now
holds a file nobody opens again. So the mechanism described above no longer needs to be found to
stop the failure.

Measured, not argued:

- **Before the fix.** Every failed `ci.yml` run since 2026-09-18 was read (`gh run view
  --log-failed`). 28 carry `database is locked` or the wrong-loop `RuntimeError`, from `6fbcf10`
  (09-18 10:15Z) to `1fd204d` (run `35660385419`, 09-21 22:00Z). That last one is 58 minutes
  before `b630252`, and its F292 diagnostic shows the shared file.
- **After the fix.** 61 `ci.yml` runs from `b630252` to `4824150`. `hub-test` ran to completion in
  59 of them: 54 green, and 5 red only from the `claude`-not-on-PATH tests. The other 2 were F394
  timeouts. **None of the 59 has a lock error.** At F292's pre-fix rate of 22.6%, that is
  p ≈ 0.774^59 ≈ 3×10⁻⁷.

**Residual, recorded rather than filed.** The leak itself still happens. The same two files on this
machine still emit `PytestUnhandledThreadExceptionWarning` from `aiosqlite/core.py`
(`call_soon_threadsafe` -> `Event loop is closed`), at the setup of exactly the tests CI used to
fail: `test_a_review_that_cannot_be_prepared_does_not_become_an_ordinary_turn`,
`test_a_flow_fired_reviewer_reads_a_file_that_is_not_on_main` and
`test_a_plain_job_with_no_loop_still_fires`. It was reproduced 2026-09-22 with
`-W error::pytest.PytestUnhandledThreadExceptionWarning`. An aiosqlite worker from the previous
test finishes a call after that test's loop has closed, and its thread dies with the sqlite handle
still open. Since `b630252` that costs one unclosed handle on a dead file, and on Windows a file
`_move_to_a_fresh_database_file` cannot delete until `pytest_sessionfinish`. It no longer costs a
test. Worth taking only if the warning count starts to matter.

## F384 (B) — `submit_spec_document`'s validator reports one missing field at a time, not all of them

**Status:** fixed 3f8887f. `validate_payload` (`hub/hub/spec_payload.py:241-246`) now joins every
error from `exc.errors()`, not just the first, into `PayloadError`'s message — the field path
still names the first, for callers that key off `PayloadError.field`. Unit test
`test_multiple_missing_fields_are_all_named_in_one_refusal` (`hub/tests/test_spec_payload.py`)
added and mutation-checked (fails against the pre-fix code, passes against the fix). Confirmed
live: a fresh throwaway drive Hub (`:8021`, deleted after) + throwaway project, `PUT
.../content` with an `acceptance_criteria` item missing `given`/`when`/`then` returned all three
in one `422` (`"acceptance_criteria[0].given: Field required; ...when: Field required;
...then: Field required"`), not one at a time. Filed 2026-09-19 by the day window's D-1
full-surface sweep drive.
**Source:** driving
**Theme:** Spec flow

**What happened, live.** A fresh Haiku 4.5 agent (`builder`, on a fresh drive Hub/project outside
this repo) was asked to add one requirement with one acceptance criterion to a spec document. It
submitted `acceptance_criteria` with an incomplete item and got back one `422` naming exactly one
missing field (`acceptance_criteria[0].key`). It supplied `key` and resubmitted — got back a new
`422` naming the *next* missing field (`.requirement`), then `.given`, then `.when`, then `.then`.
**Five submissions to discover a five-field object**, on top of two earlier failed submissions
caused by a separate, correct refusal (a `capability` document cannot be agent-written). Full
transcript: `agent_outputs` for `run-3af2a3fb7439` in
`profiles/drive0919/agentweave.db` — see the tool_result payloads with `is_error: true`.

**Root cause, verified independently of the transcript.** `hub/hub/spec_payload.py:241-245`:

```python
try:
    payload = SpecPayload.model_validate(raw)
except ValidationError as exc:
    first = exc.errors()[0]
    raise PayloadError(first["msg"], field=_field_path(first["loc"])) from exc
```

Pydantic's `ValidationError.errors()` already collects every failing field in one pass. Confirmed
directly, bypassing the agent and the HTTP layer:

```
>>> sp.SpecPayload.model_validate({'schema_version':1,'kind':'change-spec','title':'verify',
...   'requirements':[{'key':'r1','statement':'x','modal':'MUST'}], 'acceptance_criteria':[{}]})
pydantic saw 5 errors:
 - ('acceptance_criteria', 0, 'key') Field required
 - ('acceptance_criteria', 0, 'requirement') Field required
 - ('acceptance_criteria', 0, 'given') Field required
 - ('acceptance_criteria', 0, 'when') Field required
 - ('acceptance_criteria', 0, 'then') Field required
```

`errors()[0]` throws away the other four before `PayloadError` — and therefore the `422` body the
agent sees — is built. The same narrowing applies to every list-of-objects field this module
validates (`requirements`, `tasks`, `algorithms`, `open_questions`), not only
`acceptance_criteria`.

**Why this is a real defect and not just a model-capability gap.** The tool's own docstring
(`hub/hub/mcp_server.py:1728-1731`) states the full five-field shape of an acceptance criterion up
front — the agent's mistake was submitting an incomplete object, not a documentation gap. But this
module's own header comment (`spec_payload.py:1-7,46-51`) states the reason the per-field error
exists at all: *"a refusal the author cannot act on produces a retry loop, which is the failure
mode the prose contract had."* Reporting only the first of several simultaneous errors reintroduces
exactly that retry loop when a caller's mistake spans more than one field at once — which is the
common case for a freshly-invented multi-field object, not a rare one. This is the same class of
cost `F35` measured for a related but distinct cause (that one was an `Any`-typed field silently
accepting a wrong shape; this one is a fully-typed, fully-documented field whose validator still
serializes what should be a batch of errors into a sequence of round trips).

**Cost, this instance.** 5 wasted agent turns' worth of tool calls (one per missing field) plus 2
more for the unrelated `capability`-vs-`change-spec` confusion — 7 failed `submit_spec_document`
calls out of 11 total in one turn. Cheap in isolation on Haiku; multiplies across every agent that
invents a multi-field object without re-reading the docstring first, which zero-trust review
charters and time pressure both encourage.

**Fix shape (not yet decided or implemented):** collect and report all of `exc.errors()`, not just
the first — e.g. join every `_field_path`/`msg` pair into one message, or return a `blocking`-style
list the way `submit_spec_document`'s own docstring already frames refusals ("what would refuse a
proposal right now"). No spec or API surface changes shape beyond the error message's content, so
this may be a same-day repair candidate rather than something needing a spec round — the operator's
call, since D-1/D-2 folded today and no-spec repairs are explicitly in scope for tomorrow's D-2 slot
if not today's.

**What held.** The `capability`-vs-`change-spec` authority boundary itself is correctly enforced and
legibly explained (`"capability documents are written by the operator"`,
`"this document is 'capability'; a submission cannot change what a document is"`) — the agent
understood both messages immediately and did not retry blindly against that gate. The referential
check (`acceptance_criteria[].requirement` must name a real requirement key) is unaffected by this
bug since it is checked in a separate loop, after `model_validate` already succeeded.


## F386 (B) — the Overview question card tells the operator an agent "is waiting" for questions nobody is waiting on, and keeps showing declined ones

**Status:** fixed (the commit that follows this line, 2026-09-22, interactive with the operator). It was fixed at the card, not at `list_questions`: the card drops `declined` rows, and says `is waiting` only when `blocking` holds and `asker_waiting !== false`, the rule the Questions panel already uses. Otherwise it says `<agent> is asking`, the phrasing `AgentQuestionCard` uses. `GET /questions?answered=false` is unchanged for every other reader. `hub/ui/src/__tests__/questionInterruptCard.test.tsx` has 6 tests: 4 failed on the old card and all 6 pass now. The full vitest run is 150 files, 1552 passed, and lint is clean. The bundle was refreshed and the only new behaviour it carries is this fix. No browser drive: none is available on this machine. The unfiltered route order it relies on (`created_at` ascending, declined included) was read from `questions.py:322-325`, and the test fixture uses that order. Filed 2026-09-19 by the adversarial Opus review of
`a-refused-capability-reaches-the-operator` (the review the operator commissioned before approving
it); confirmed against the code by the session that commissioned it.
**Source:** review
**Theme:** Operator surfaces

**What happened.** `QuestionInterruptCard` is the amber card on a project's Overview tab, and it is
the only route from the dashboard to an unanswered question (see `F387`). It states, in its heading
and its accessible label, that the asking agent **is waiting** — for every question it renders,
unconditionally.

**Where.**
- `hub/ui/src/components/questions/QuestionInterruptCard.tsx:35` — `{first.from_agent} is waiting`.
- `:24` — `aria-label={`${first.from_agent} is waiting for an answer`}`, so a screen reader gets the
  same claim.
- The card is fed by `hub/ui/src/components/overview/OverviewPage.tsx:80`, `useQuestions(false)` →
  `GET /questions?answered=false`, and `hub/hub/api/v1/questions.py:315-318` filters on `answered`
  **only**.

**Two defects, one file, both with the data already in hand.**

1. **`blocking` is ignored.** `Question.blocking` exists on the model
   (`hub/hub/db/models.py:936`) and on the wire type the card consumes
   (`hub/ui/src/api/questions.ts:16`). A non-blocking question is by construction one whose asker
   did **not** wait — `_asker_still_waiting` short-circuits on it (`questions.py:71-75`) — so the
   card states the opposite of the field it is holding. Today every `ask_user` call is blocking, so
   the defect is latent rather than firing; it becomes live the moment any non-blocking question is
   written, which is exactly what `a-refused-capability-reaches-the-operator` proposes to do.
2. **`declined` is ignored.** `Question.declined` is deliberately a separate column from `answered`
   (`models.py:987-990`, and the change `2026-08-11-declining-a-question` D1 that made it so:
   *"Collapsing the two would make every reader of `answered` treat a decline as an answer"*).
   `list_questions` does not filter it and neither does the card, so a question the operator
   explicitly closed without answering keeps rendering as an agent waiting on them, indefinitely.
   The card's own dismiss control is `useState` (`QuestionInterruptCard.tsx:15`) and so does not
   survive a reload.

**Why this is filed separately from the change that found it.** The review found it while checking
`a-refused-capability-reaches-the-operator`'s claim that its record would reach the operator without
any surface reporting a false wait — that change's own ADDED requirement
(`specs/agent-capability-plane/spec.md:17-20`) forbids exactly this sentence. But the defect is in
shipped code, predates the change, fires for declined questions **today** with no new code at all,
and lives in `hub/ui/src/components/`, which that change's blast-radius claim
(`proposal.md:123,125`) says it does not touch. It outlives whatever the operator decides about
that change.

**Fix shape (not decided).** Both halves read a field the card already receives. The copy needs a
non-waiting form for `blocking === false` — the review's suggestion was *"<agent> asked about this
project"* versus *"<agent> is waiting"* — and declined questions need filtering, at the card, at
`list_questions`, or both. Whether `GET /questions?answered=false` should exclude declined rows for
**every** caller is the one real decision here: `hub/hub/api/v1/questions.py:315-318` is shared, and
other readers may be relying on a decline still appearing.

**Related:** `F387` (same card, ordering), `F381` (the same class of defect in the conversation
tray), `a-refused-capability-reaches-the-operator` (the change whose review found it).


## F387 (B) — the Overview question card shows one question, oldest first, so a non-urgent question hides a blocking one

**Status:** fixed 6ab4a4a (closed 2026-09-22, found fixed by F386's card work). Filed 2026-09-19 by the adversarial Opus review of
`a-refused-capability-reaches-the-operator`; confirmed against the code by the session that
commissioned it.
**Source:** review
**Theme:** Operator surfaces

**What happened.** The amber card on Overview renders exactly one question — the first of the list
it is given — and the list arrives oldest-first, with no regard for whether anything is blocked.
So the question most likely to be costing the operator time is the one most likely to be hidden.

**Where.**
- `hub/ui/src/components/questions/QuestionInterruptCard.tsx:16-18` — `visible[0]`; everything after
  it is rendered only as a count, not as a row.
- `hub/hub/api/v1/questions.py:318` — `list_questions` orders by `created_at` ascending.
- No sort is applied between the two: `hub/ui/src/components/overview/OverviewPage.tsx:80` passes
  the response through.

**The failure.** An agent genuinely parked on a blocking question — one that has a task parked
behind it (`Question.blocked_task_id`, `models.py:978`) — sits behind any older unanswered
question, including one nobody is waiting on. The operator's landing page shows the wrong one, and
the count beside it does not say that a blocking question is among the rest.

**Why it is worth filing now.** It is latent today, in the same way `F386`'s first half is: every
current question is blocking, so oldest-first is merely arbitrary rather than harmful. Introducing
any non-blocking question makes it harmful, and
`a-refused-capability-reaches-the-operator` proposes to introduce a durable, deliberately
non-blocking, deliberately long-lived one — whose whole purpose is to be waiting when the operator
returns. That record would outlive and therefore outrank every blocking question asked after it.

**Fix shape (not decided).** The deterministic floor is blocking first, then newest — both fields
are already on the wire type (`hub/ui/src/api/questions.ts:16,30`), so it is a sort, not a schema
change. Whether it belongs in the card or in `list_questions`' `order_by` is the open question;
the card is the narrower blast radius, the route fixes every reader at once.

**The operator's own framing, 2026-09-19:** they like the card and want the ordering solved either
by newest-first or by `R5`'s manager agent deciding the order. Recorded here so the fix is not
chosen without it — but see `R5`'s note that a nondeterministic orderer must sit **on top of** a
correct deterministic floor, not replace it, since its failure mode is this exact defect.

**Related:** `F386` (same card, copy and declined filtering), `F381`, `R5`.

---

**Closed 2026-09-22.** F386's fix (`6ab4a4a`, extended in `24f3655`) changed `QuestionInterruptCard.tsx` to show `visible.find(isWaitedOn) ?? visible[0]`, so a question someone is waiting on is shown ahead of older ones nobody waits on, and declined rows are dropped. `questionInterruptCard.test.tsx` pins it ("still surfaces a later blocking question someone is waiting on"). The route's oldest-first order is unchanged by design (DIRECTION 09-20: fix at the card). The "count beside it" half is moot: the card renders no count. Never seen in a browser.

## F388 (A) — a Hub started from source silently opens the operator's live database, and the code comment says it cannot

**Status:** fixed 85b4b28 — built across groups 1-5 (`hub/hub/config.py`'s
`HubNotToldWhichDatabase` refusal, `hub/hub/main.py`'s pre-open database-naming line, the CLI-drift
fix, and the spec delta applied into `openspec/specs/app-lifecycle/spec.md`) and driven live 2026-09-23 (D-5, below) — the refusal, the named-database startup line (both
existed-before states), and the PID kill all observed against a real process on port 8093, never
`:8000`/`:8010`. See D-5 for the drive narrative.

**R2, 2026-09-20 — every R1 decision survived an independent re-derivation; five claims did not.**
Driven, not reasoned: two throwaway Hubs from source (8093/8094, fresh profiles, killed by exact
PID) settled D5 — 104 `alembic` `INFO` lines appeared and **zero** `hub.*` `INFO` lines did, so (b)
must be `WARNING`; and at the site (b) is going to, the line prints **bare** (no level, no logger
name), because `logging.lastResort` has no formatter. Corrected: (1) the **CLI** suite breaks too
(`tests/test_hub_commands.py:707`'s bare `import hub.config`) — exactly one new failure, measured;
(2) `scripts/drive/n10_route_reachability.py` is a second caller, surviving today only on the
gitignored `hub/.env`; (3) R1's task to absolutize `hub/.env.example` **would have broken Docker** —
that value is the container's path (`WORKDIR /app` + the `hub-data` volume at `/app/data`) and the
task now comments it instead; (4) "no dependency edge between `agentweave-ai` and `agentweave-hub`"
is false (`pyproject.toml:34`) — D4's conclusion holds and the true premise argues it harder;
(5) two delta scenarios were falsified by the code being right, and are narrowed. **D9's question is
answered: no launch still reaches the live database with no `DATABASE_URL`** — and the sharpest form
of the route is that `hub/.env` is gitignored, so on a clean checkout the launch `CLAUDE.md` itself
prescribes lands on the home default.
Filed 2026-09-19 by the interactive DECIDE session, at the operator's explicit instruction
("Yeah becomes a finding"), after the 2026-09-19 day window hit it against the real `:8000`
database.
**Source:** operator
**Theme:** Operator surfaces

**What happened.** The 2026-09-19 day window started a throwaway Hub from `hub/` to drive the
product. It set `DATABASE_URL` to a trial profile, but the variable did not survive a
`kill` + `rm` + restart sequence inside one Bash tool call. The process fell back to the default
and attached to `~/.agentweave/hub/data/agentweave.db` — **the operator's live `:8000` database,
348 runs and 12,500 event logs of real work.** The window noticed, stopped itself mid-window, and
ran `taskkill /IM python.exe /T`, which also killed the operator's running app. Its scheduler
heartbeat stops at `2026-09-19 09:40:00.704` UTC and does not resume.

**Where.**
- `hub/hub/config.py:9-18` — `_default_database_url()` returns
  `Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"`. No guard, no marker file, no
  refusal.
- `hub/hub/config.py:24` — `database_url: str = Field(default_factory=_default_database_url)`.
  A missing environment variable is indistinguishable from a deliberate choice of that path.
- `hub/hub/config.py:12-15` — the docstring asserts the default is *"Only consulted by callers that
  skip the CLI (direct `uvicorn hub.main:app`, or any future embedder)"* and that *"this default
  never fires there"*. **Direct `uvicorn hub.main:app` is exactly what this repository's own
  `CLAUDE.md` instructs an agent to run for the trial Hub.** The comment describes the dangerous
  path as the safe one.

**The failure.** There are three distinct losses, and the third is the one that makes this an A:

1. **Silent attachment.** Nothing in the startup output names the file. The only tell is indirect —
   a fresh database logs the whole `0065→0103` migration chain, an existing one logs only
   `Application startup complete` — and reading an absence is not a safeguard.
2. **Uncontrolled migration.** A source checkout ahead of the live instance runs its migrations
   against the operator's real data on attach. This is the exact hazard `CLAUDE.md` forbids in
   prose (*"Never restart it, migrate it, call it, or write to its database"*) with no mechanism
   behind the prose.
3. **The recovery is worse than the fault.** An agent that discovers it is on the live database has
   no safe way to detach: `taskkill /IM python.exe /T` matched the operator's app as well. The
   operator's Hub was down for roughly three hours until they restarted it by hand.

**Why it is worth filing now.** It has already fired once, against real data, and nothing has
changed since — the next window that backgrounds a server the same way lands on the same file.
The blast radius is the operator's only production instance, and the failure is silent on the way
in. `CLAUDE.md` and `DEAD-ENDS.md` both now describe the trap; neither can stop it, because both
are read by an agent that has already decided it set the variable correctly.

**Fix shape (not decided).** Options, cheapest first, and they compose:

- **(a) Refuse the implicit default.** Make `database_url` required when the process was not started
  by the CLI — no `default_factory`, so a direct `uvicorn` with no `DATABASE_URL` fails to boot
  with a message naming the two ways to set it. Cost: breaks any embedder relying on the default,
  of which there are none in this repository.
- **(b) Name the file at startup, unconditionally.** Log the resolved absolute database path and
  whether it existed before this process opened it, at INFO, as the first line. Does not prevent
  anything; makes every occurrence visible in one line instead of inferred from a missing
  migration chain. Cheapest, and worth doing whatever else is chosen.
- **(c) Mark the live profile.** A sentinel row or file (`instance_role = "primary"`) that a Hub
  started from a source checkout refuses to open unless `AW_ALLOW_PRIMARY=1`. Strongest, and the
  only option that survives an agent that believes it set the variable.
- **(d) Fix the docstring regardless.** It currently tells the reader the opposite of the truth.

The operator has not chosen. Note that (a) alone would have prevented the 2026-09-19 incident,
since the variable's absence was the whole cause.

**Related:** `DEAD-ENDS.md` §*Starting a Hub from source can land on the operator's real database*
and §*Telling whether the operator's `:8000` app is running, without touching it* (both 2026-09-19);
`F380` (the other way a window fails silently and leaves nothing to read).

## F390 (C) -- `DELETE /runners/{id}` refuses with the same unfindable name F185 refuses with

**Status:** fixed 861429d -- `delete_runner` now selects `Agent.lifecycle` alongside `Agent.name`
and qualifies each archived holder inline (`"name (archived)"`), appending the "listed under Agents
with the archived filter" clause only when at least one holder is archived; an open-only refusal is
unchanged. Reproduced through HTTP for the first time (group 5's own R1/R2/R3 note this had never
been driven, only read): `test_delete_runner_bound_to_only_archived_agent_names_it_archived` and
`test_delete_runner_bound_to_mixed_holders_qualifies_only_the_archived_one` in
`hub/tests/test_runners_api.py`, both via real `POST .../archive` + `DELETE /runners/{id}` calls,
not direct DB mutation. Mutation-tested (dropping the lifecycle column fails both, leaves the
pre-existing only-open case green). The underlying design choice this finding is downstream of --
`runner_id` staying bound through archival -- is unchanged (D3/D4); this fix answers by naming the
archived holder, not by releasing the binding, per R2/R3's reasoning below (kept for the design
history, not because the code snippet is current).

Specced 2026-09-20 in `openspec/changes/an-archived-agent-holds-nothing-and-is-offered-nowhere`,
group 5 -- originally that change's declared cut line. **R2, 2026-09-20:** that cut is not free and
is not the deferral of an unrelated site -- group 5 exists *because* the change chooses to keep
`Agent.runner_id` bound through archival (its `design.md` D3/D4). If archival released the runner
binding too, this finding would close by construction. Found **by reading** during that change's
R1, not by a drive, and not reproduced through HTTP until group 5 (above). **R3, 2026-09-20:**
re-derived D3 independently and confirmed keeping `runner_id` for a third time -- and strengthened
it, by measuring that `create_agent` writes `config={}` (`agents.py:673`), so a cleared `runner_id`
would make an archived agent's row report `runner: "native"` / `"Native"` -- a false value rather
than a missing one. This finding is answered by naming rather than by releasing.

Pre-fix, `hub/hub/api/v1/runners.py:175-183` was `hub/hub/api/v1/charters.py:95-98` with one word
changed:

```python
bound = await session.execute(
    select(Agent.name).where(Agent.project_id == project_id, Agent.runner_id == runner_id)
)
...
detail=f"Runner is bound to agent(s): {', '.join(bound_names)}. Unbind before deleting.",
```

No `Agent.lifecycle` predicate. A runner bound only to an archived agent therefore could not be
deleted, and the refusal named an agent `GET /agents` does not show -- F185's wall, one route
over. **Severity C rather than B** because, unlike a charter, a runner is not a record the
operator authored: an unused runner left undeleted costs a row, where the blocked charter deletion
blocks a document someone wrote.

It is answered differently from F185 on purpose. F185's remedy releases the charter binding at
archive; the runner binding is deliberately **kept** (an archived agent's configuration still
displays what it ran with -- `agents.py:518`, `:568-569`), so this site is closed by naming the
holder as archived and saying where an archived agent is found, not by releasing anything. The
reasoning is `design.md` D3/D4 of that change, and D3 is the part to attack if this looks wrong.

## F391 (C) -- archiving an agent persists no event and broadcasts nothing, so the transition leaves no trace

**Status:** fixed 06161a7 -- `archive_agent`/`unarchive_agent` now call `persist_event` then
`sse_manager.broadcast` for `agent_archived`/`agent_unarchived`, matching `agent_created`'s order,
with `released_charter_id` carried unconditionally on archive (never on unarchive). Verified
through `GET /events/history` with a heartbeat positive control, mutation-checked both ways. **The
display half is untouched** -- `hub/ui/src/hooks/useSSE.ts` still allow-lists kinds at `:31` and
switches per kind at `:460` with no entry for either new kind, so the new events are durable and
queryable but not shown on any screen; that is a later change, not this one. Found **by reading**
on 2026-09-20 during R3 of
`openspec/changes/an-archived-agent-holds-nothing-and-is-offered-nowhere`, recorded in that
change's `design.md` D10. **Not specced, and deliberately not folded into that change** -- it is
true today with no charter release at all, so it is a standing defect of archival rather than
something that change introduces. **Reproduced through the API** the same day on `00a3878`, in a
throwaway test against the suite's ASGI app (written, run, deleted -- no test file was added), with
a positive control so that the empty result is the absence of an event and not a broken endpoint:

```
BEFORE          : []
AFTER ARCHIVE   : []
AFTER UNARCHIVE : []
ARCHIVE RESPONSE: {'name': 'f391', 'lifecycle': 'archived'}
NEW EVENTS      : []
AFTER HEARTBEAT : ['agent_heartbeat']        <- control: this route does persist one
```

`GET /events/history` is unchanged by an archive and by an unarchive, and records the very next
heartbeat on the same agent.

**Where.** `hub/hub/api/v1/agents.py:2602-2644` (`archive_agent`) and `:2648-2660`
(`unarchive_agent`). Both end identically -- mutate the row, `commit`, `refresh`, `return` -- with
no `persist_event` and no `sse_manager.broadcast`. There is no `agent_archived` or
`agent_unarchived` event kind anywhere in the tree:

```
$ grep -rn "agent_archived|agent_unarchived" hub/ src/     # alternation escaped for grep
(no matches)
```

Every neighbouring agent route has one: `agent_created` (`agents.py:689`), `agent_requested`
(`:2133`), `agent_heartbeat` (`:2682`). Archival is the one agent lifecycle transition that records
nothing.

**Severity C**, on two counts that are each small and one that is not:

1. A second open client's roster is not told. The acting client self-invalidates in
   `useArchiveAgent`'s `onSuccess` (`hub/ui/src/api/agents.ts:230-240`); nothing informs the others,
   so another window shows an archived agent as open until something else refetches.
2. The project's own event history cannot answer *when was this agent archived* --
   `Agent.archived_at` carries the timestamp, but nothing records the transition itself.
3. **The one that matters, and the reason this was found now.** The change specced above adds a
   `released_charter_id` to the archive response. With no event, that response is the *only* place
   the released charter's identity ever exists, and its only client discards the body -- its
   `onSuccess` takes no argument (that change's `design.md` D9). So the fact is irrecoverable from
   the Hub the moment the request returns.

**Why it is its own finding rather than a task on that change.** The remedy is server-side and
cheap -- `persist_event(session, project_id, "agent_archived", {...})` needs no `hub/ui/src` change
and therefore no bundle refresh -- which makes it the only route to that change's operator rider
(*"unarchive must then say the bindings are gone"*) that does not reach the live `:8000` app. That
change's D2 rejected *remembering* the binding, correctly, because an `archived_charter_id` column
re-creates the live state it exists to remove; an event does not, because it records that something
happened rather than that something is bound. Neither R1 nor R2 drew that distinction.

**What the remedy would not do.** Rendering it is still a UI change:
`hub/ui/src/hooks/useSSE.ts` allow-lists event kinds at `:31` and switches per kind at `:460`, so a
new kind would be durable and queryable but not displayed until that file learns it. Durable is not
displayed.

## F392 (B) -- a change's "what must not move" group ticked a full-suite run whose evidence was never written down, and the regression it would have caught was real

**Status:** fixed (this commit) [Round 1, 2026-09-22]. Both halves are now a rule with a check;
see FIXED at the end of this entry. The red tests this was found through were repaired 2026-09-20.

**Found** 2026-09-20 afternoon, by an operator-requested live check of the 2026-09-19 night
window's claims, not by any window's own verification. **Reproducible at `14f8dae`:**

```
$ py -3.11 -m pytest hub/tests/test_a_task_nothing_will_move_holds_nobody.py -q
FAILED ::test_the_guard_agrees_with_the_walk                          (3.3)
FAILED ::test_run_staffs_the_bookmark_holder_and_answers_success      (3.4)
FAILED ::test_the_board_does_not_read_the_busy_sentence               (3.5)
3 failed, 27 passed
```

**The regression.** `a-loop-staffs-the-agent-it-names` task 3.3 (`831ac16`) repointed
`_loop_flow_busy_reason`'s pool read at `_agents_a_loop_may_staff` (`hub/hub/scheduler.py:350`),
which returns `[]` for a loop with no `spec_document_id` (design D2). That file's `_guard_case`
built a documentless loop, so the guard collapses to *busy, full stop* whatever any other agent
holds, and all three cases assert it does not. The two changes' rules contradicted each other on
that fixture. Those tests arrived with `4b59ee0` (2026-09-15), which **is an ancestor of `master`**
-- so this was a merge blocker, not a branch-local annoyance, and `d7-gate`'s `--ff-only` merge
would have been sitting on a red suite.

**Why every guard that existed missed it.**

1. Group 6.1's measured set is five files and never included this one. **No artifact of
   `a-loop-staffs-the-agent-it-names` names that file anywhere** -- `grep` over the whole change
   directory returns nothing. It is the *sibling* change's regression guard, and the sibling's own
   `tasks.md:76` calls it exactly that.
2. Group 6.2 is `pytest hub/tests/ -q` in full. It is ticked `[x]` reading *"full suite green --
   see log entry for the exact count and duration (command ran past the 600s foreground timeout and
   was moved to background; result recorded there rather than here to avoid a stale placeholder)."*
   **`.claude/autonomous/2026-09-19-night-log.md` contains no full-suite run at all.** That
   process died before writing its log entry; the reconciling iteration 7 re-ran only the same five
   files and marked the item done from the commit. The tick therefore rests on a number nobody
   recorded, and the deferral that produced it -- *record it in the log, not here* -- is precisely
   what made it unfalsifiable when the log never got written.
3. The change's own R4-7 triage rule classifies it correctly on sight: *"a newly red test whose
   loop leaves `spec_document_id` `None` is the change firing, and is expected only where a task
   above says so."* No task said so. The rule was right; nothing ever ran the command that would
   have handed it the input.

**Fixed, by restaging rather than by weakening either rule** (operator's call, 2026-09-20).
`_guard_case` now declares a `SpecDocument` and sets `loop.spec_document_id`, as 3.1 and 3.2 in the
same file already do -- the question those cases ask, *does a bookmark cost the project an agent*,
is a flow's question. `_make_loop_job` in `test_loop_busy_guard.py` is shared with the alsn
baseline and was not touched. File alone: **30 passed**, 13.4s. The restaging did not cost the
tests their teeth: forcing `reachable` true in `_agents_that_are_free`'s projection
(`scheduler.py:1232`) fails all three plus 14 others; reverted. Recorded as task 6.8 in
`a-loop-staffs-the-agent-it-names/tasks.md`, with 6.2 re-opened as `6.2-REDO`.

**What is still open, and why this is B and not C.** Two things, neither addressed:

1. **A tick whose evidence lives "in the log" can outlive the log.** Three artifacts
   (`tasks.md`, the window log, `STATE-*.json`) each deferred the measurement to another, and the
   one that was supposed to hold it was never written. A measurement recorded nowhere reads
   identically to a measurement that passed.
2. **A change's regression set is chosen from its own artifacts**, so it is structurally blind to
   a sibling change's guard file -- exactly where two in-flight changes collide. Nothing computes
   the union of the files the *other* open changes name as guards.

**Not proposed.** The cheap half is a rule that a group-6-style full-suite tick must carry its own
count inline or stay unticked. The harder half is deriving the regression set from every open
change's named guard files rather than only this one's.

---

**A second instance of point 2, measured 2026-09-21** (night window, `i-6.2-redo`). Re-running
6.2-REDO at branch HEAD `8508377` collects **4560** tests against **4545** at `09237f6`, the tree
6.2-REDO's own number was measured on. A `git diff` for added `def test_` over `hub/tests/` finds
only **14**. The fifteenth is
`test_no_console_flash.py::test_every_spawn_reaches_console_suppression[0105_clear_archived_agent_charter_bindings.py]`
-- not a test anyone wrote, but a **parameter generated from the new migration file** that
`an-archived-agent-holds-nothing-and-is-offered-nowhere` group 3 added. That change names
`test_no_console_flash.py` nowhere, exactly as `a-loop-staffs-the-agent-it-names` named
`test_a_task_nothing_will_move_holds_nobody.py` nowhere. It passed, so this instance cost nothing;
it is recorded because it shows the blindness is not only "a sibling change's guard file" but
**any test that parametrizes over source files a change adds** -- a set no artifact of the change
can enumerate, and which only the full suite reaches.

**The full run behind that number, completed 2026-09-21 02:53** (the collection count above was
measured first; this is the suite itself, not `--collect-only`): `py -3.11 -m pytest hub/tests/ -q`
at `8508377` gave **4474 passed, 86 skipped, 266 warnings, 2857.30s (47:37)**, exit code 0, zero
failures and zero errors. `4474 + 86 = 4560` closes the arithmetic: the generated case is in the
*passing* set, not skipped past. Written into
`openspec/changes/a-loop-staffs-the-agent-it-names/tasks.md` task 6.2-REDO in the same commit, which
is where F392 says a count belongs.


**FIXED 2026-09-22 (interactive session, Round 1).** Both halves reduce to one rule: *a "what must
not move" task runs the full suite, and is ticked only with its count on the task line.* Only the
full suite reaches a sibling's guard file or a test parametrised over a file this change adds, and
only a count on the tick survives a log that never gets written. Where it lives, so that it does
not depend on anyone reading prose:

- **The check.** `tests/test_openspec_task_evidence.py` fails CI on any `- [x]` task in an
  in-flight change (`openspec/changes/*/tasks.md`, not the archive) that runs a suite (a `pytest`
  over `hub/tests/` or `tests/`, or the words "full suite") and has no `N passed` on the task.
  `test_the_check_reads_what_f392_ticked` pins the detector on this entry's own tick (flagged), on
  its 6.2-REDO repair (clean), on a single-file run (clean) and on an unticked task (clean). The
  two in-flight changes pass today. Over the archive the same detector flags 63 ticks, which is how
  common this was. The archive is deliberately not checked.
- **The authoring rule.** `openspec/config.yaml` `rules.tasks` gains both halves. That is the text
  openspec shows whoever writes a `tasks.md`.
- **The tick step.** `.claude/skills/openspec-apply-change/SKILL.md` step 6 says it where the
  checkbox is ticked. The skill mirrors were re-synced.
- **Not done: computing the union of every open change's guard files.** That was the harder half
  this entry named. The full-suite rule makes it unnecessary rather than solving it, because it
  reaches every guard file without knowing which files they are.


**Opus review, applied the same session.** The reviewer probed the detector directly and found it
full of holes; every case below is now in `UNCOUNTED` or `CLEAN` in the test:

- **Missed:** a flag with a value (`pytest -n 8 hub/tests/`), `./hub/tests/` and `hub	ests\`,
  "Full test suite green" and "the whole suite passes", `- [X]`, `* [x]`, and indented subtasks —
  the corpus has 37 of those, and one under an unticked parent was folded into the parent's block
  and never checked.
- **Wrongly accepted:** any `N passed` in the block, including a baseline quoted from before the
  change, a run with failures, and a one-file run's count sitting next to a full-suite claim.

The detector now reads each `pytest` command rather than the block as one string, attributes a
count to the command written before it, rejects baselines and non-zero failures, and treats a
narrowed run (`-k`, a node id) as not the suite. Over the archive it flags 73 ticks where the first
version flagged 63; both in-flight changes stay clean. **One deliberate false positive:** a ticked
task that merely quotes a suite command in prose is flagged, because nothing tells that apart from
a claim to have run it.

**Known gap, not closed:** CI only ever sees the pushed HEAD, so a tick and the change's archive
move landing in the same push are never checked in flight.

## F393 (B) -- three runner registries disagree, the two that lie are the ones a reader finds first, and nothing marks them legacy

**Status:** fixed f228962 (2026-09-22; the first half was 4bd966e): `launchability.py`'s two registries are marked DEAD; `RUNNER_CONFIGS` is not (see the foot). **Found 2026-09-20** in an interactive session, by being taken in by it: the
session read `RUNNER_CLI` in `hub/hub/launchability.py`, concluded that five of nine registered
runners fall to the approver-less `cli` path by construction, and built an architectural argument
on it — that `resolve_access_path`'s three-questions-one-boolean coupling was actively breaking
most runners and had to be fixed before GitHub Copilot support landed. **The operator caught it**
(*"beware that I think you might be reading legacy code"*), and the argument collapsed on one grep.
No proposal was written, so the measured cost is one session's reasoning; the cost if it had not
been caught was a spec loop re-architecting a live seam to fix runners that cannot be created.

**The three registries.**

| where | entries | what it actually governs |
|---|---|---|
| `src/agentweave/constants.py:133` `RUNNER_CONFIGS` | 9 — `claude`, `native`, `claude_proxy`, `kimi`, `opencode`, `codex`, `codex_mcp`, `manual`, `copilot` | the CLI's own table |
| `hub/hub/launchability.py:20-30` `RUNNER_CLI` | the same 9 | CLI-binary resolution and probing |
| `hub/hub/db/models.py:300` `RUNNER_CLIS` | **2 — `("claude", "codex")`** | **everything that can create a runner** |

**The two-entry one is the gate, and it is enforced.** `hub/hub/schemas/runners.py:22-23` raises
`cli must be one of ('claude', 'codex')` on any other value, so no `Runner` row with `copilot`,
`kimi` or `opencode` can be created through the API at all. `hub/ui/src/api/runners.ts:5` declares
`type RunnerCli = 'claude' | 'codex'` and `hub/ui/src/components/runners/RunnersPage.tsx:19` offers
exactly those two. `db/engine.py:253` and `project_lifecycle.py:283` seed from the same two.

**Why the misreading was reasonable, which is the finding.** `RUNNER_CLI` lives in the module
named for launchability, sits eight lines from `MCP_INJECTABLE_RUNNERS` (`:210`), and carries a
comment (*"Mirrors the `cli` field of RUNNER_CONFIGS in agentweave.constants"*) that points at the
**other** nine-entry registry rather than at the two-entry one that decides anything. Read together,
`RUNNER_CLI` minus `MCP_INJECTABLE_RUNNERS` computes a five-runner set that looks like a live
population and is empty. Nothing in either file says the extra seven are legacy.

**What is actually true today:** both creatable runners (`claude`, `codex`) are in
`MCP_INJECTABLE_RUNNERS`, so every runner an operator can make gets the Hub's MCP server injected
and keeps the `workspace` posture with its approver. The approver-less path is reached only by a
harness that refuses the injected server (F299's case, real on machines whose policy blocks MCP —
the operator reports their work PC is one) or by `hub_client: "cli"`, which no UI sets.

**Why B rather than C.** It is a wrong surface, like F339, and wrong surfaces here cost decisions,
not words: F339's four false texts were the stated reason an option was rejected, and this one
nearly produced a proposal. It will also recur — the registries are three files apart, the
misleading two are the discoverable ones, and GitHub Copilot support is planned, which is exactly
when someone will read `RUNNER_CONFIGS`'s `copilot` entry (`constants.py:210-221`, including a live
`mcp_add_cmd`) and believe it is wired up.

**Not proposed, and deliberately not "delete the legacy entries".** Whether the seven extra keys
should go, be annotated, or become the basis of a real per-runner capability descriptor is a design
question that belongs with GitHub Copilot support rather than ahead of it. The cheap half is that
nothing in the code says which registry is authoritative. An annotation pass over dead paths was
started the same afternoon.

**Reproduce:** `grep -n "RUNNER_CLI\b" hub/hub/launchability.py`, then
`grep -rn "RUNNER_CLIS" hub/hub/`, and note that only the second set reaches a validator.

**Partially fixed, found by the 2026-09-22 stale-ledger sweep.** `4bd966e` (2026-09-20, the annotation pass this entry mentions) put `DEAD` blocks on `RUNNER_CLI` (`launchability.py:19-28`) and `MCP_INJECTABLE_RUNNERS` (`:220-227`). Each names `RUNNER_CLIS` (`db/models.py:311`) as "the only registry that binds", which answers this entry's "nothing marks them legacy" for those two. **Still open:** `RUNNER_CONFIGS` (`src/agentweave/constants.py:153`) carries no marker, and its comment still says "Used by watchdog" (deleted). It is not dead: the CLI's `doctor` reads it (`diagnostics.py:212, 808`). Its `copilot` entry with a live `mcp_add_cmd` is therefore still the trap this entry predicts for GitHub Copilot support. The cheap close is a comment on `RUNNER_CONFIGS` saying it governs CLI diagnostics only and that the Hub creates runners from `RUNNER_CLIS` alone.

**Fixed 2026-09-22, `f228962`.** `RUNNER_CONFIGS` now opens with a block saying it is not the Hub's runner registry: the Hub never imports `agentweave.constants`, only `RUNNER_CLIS` binds, the CLI's `doctor` is its reader, and the `copilot` entry describes no runner the Hub can make. The false "Used by watchdog" line is gone. All three registries now say which one is authoritative. Deleting or restructuring the extra entries stays with GitHub Copilot support, as this entry decided.

---

**Foot 2026-10-01 (`each-runner-cli-is-one-adapter` task 6.2).** The Hub's runner registries are now the
adapter table: `ADAPTERS` in `hub/hub/runner_adapters/__init__.py` holds `claude`, `codex` and (task 3.7)
`copilot`, and `tests/test_runner_adapters_conformance.py` fails unless `tuple(ADAPTERS) == RUNNER_CLIS
== tuple(CATALOG)` equals the database's `ck_runners_cli` set. `RUNNER_CLI` is renamed
`LEGACY_RUNNER_CLI` and keeps only legacy strings plus `claude`/`codex` for `probe_agent`'s
no-adapter path. The `copilot` row this note was to remove in slice 2 is already absent (read
2026-10-01, `launchability.py:46-55`). `MCP_INJECTABLE_RUNNERS` and `resolve_access_path` are deleted
(task 3.2, F474).

## F394 (A) -- `hub-test` does not error on `master`, it HANGS: three runs stopped dead at 13% and were killed by GitHub's 6-hour job timeout

**Status:** fixed f9e6dee (root cause, 2026-09-22): the hang was the tests' own wait, not the product. `_await_background_run`'s `while set: for task in list(set): await task` never yields on a finished task, and a spawn-failure retry that finishes behind the waiter leaves exactly that — see the foot. Earlier: 3491580 (mitigation, 2026-09-21): `hub-test` now runs `pytest tests/ -v --timeout=300 --timeout-method=thread` and `pytest-timeout` is in `hub/pyproject.toml` dev extras. Verified locally that a sleeping test is killed with a stack. **Now verified on CI once (2026-09-22): run `35667708908` (`45d769f`) hung, was killed after 300 s instead of 6 h, and dumped a stack naming `test_agent_trigger.py::test_spawn_failure_marks_run_failed` blocked in `_await_background_run` — see the foot.** The root cause of the hang is still unknown. **Found 2026-09-20** in an interactive session, while doing nothing more than
checking whether CI was green enough to merge. It is filed separately from **F292** on purpose:
F292 is an `ERROR at setup` that ends the run in ~15 minutes with a summary line, and every
statement in this repository about CI's cost — the 22.6% rate, the 16-in-a-row escalation, the
`night-window.md` step-3 rule, the whole **O2** objective on the week scorecard — is written about
*that* shape. This one produces **no summary line, no `FAILED`, no error, and no conclusion for six
hours.** Whether the two share a mechanism is an inference and is **not** measured here.

**The measurement.** Of the last five `ci.yml` runs on `master`, **three hung in `hub-test`**:

| run | sha / message | started | hub-test |
|---|---|---|---|
| `35218523888` | `fix(openspec): actually stage the synced spec and 7.2 done-note` | 2026-09-17T11:58Z | **cancelled at 6h00m31s** by the job timeout |
| `35518372695` | `day(2026-09-20): note the concurrent operator session on this branch` | 2026-09-20T15:03Z | still `in_progress` at 20:43Z (**5h40m**) |
| `35519549858` | `dead-ends: five entries from sharing the tree with a live window` (`45d4576`, master HEAD) | 2026-09-20T15:25Z | still `in_progress` at 20:43Z (**5h18m**) |

The other two master runs (2026-09-16 `13m30s`, 2026-09-19 `12m59s`) were ordinary and green. Every
other job in all three hung runs — `ui-test`, all six `test` matrix cells, `build` — finished
normally in one to three minutes.

**Where it stops, exactly.** `35218523888` is the only one whose log can be read (a job still
running will not serve one). Its `hub-test` output ends at
`2026-09-17T12:02:09.3044770Z tests/test_agent_trigger.py::test_a_second_release_charges_a_refused_entry_at_most_twice PASSED [ 13%]`
and then emits **nothing at all** until `17:58:57`, when the runner's teardown reports
`Terminate orphan process: pid (2463) (pytest)`. The next test in file order is
`test_spawn_failure_marks_run_failed` (`hub/tests/test_agent_trigger.py:1674`). So pytest was alive
and produced no output for **5h56m48s**; it did not crash, it blocked.

**Why this is severity A and not a duplicate of F292.**

1. **It defeats the merge gate more completely than F292 does.** `d7-gate` merges on CI *success*
   for the exact HEAD sha. A red run at least concludes, so the gate can be told why it is shut and
   a re-run costs 15 minutes. A hung run never concludes at all, and `master` HEAD `45d4576` has
   now carried **no CI verdict of any kind for over five hours**.
2. **It burns 6 hours of a runner per occurrence**, against ~15 minutes for a red one.
3. **Nothing in the loop distinguishes "still running" from "wedged".** `night-window.md` step 3 and
   `check-build` both read a *conclusion*; an `in_progress` run has none, and the rules written in
   `a09e4a2` for **O1** do not say what a window should do when the sha it inherits has a run that
   has been in flight for five hours. A window firing now would read "no conclusion yet" and wait.
4. **The error shape is concurrently alive on the branch and behaves completely differently.** Runs
   `35533586928` (`4bd966e`) and `35534558164` (`82106af`) both failed the classic F292 way the same
   evening — `4451 passed, 20 skipped, 1 error`, `database is locked` on `BEGIN IMMEDIATE`, in
   `test_flow_fires_a_review_turn.py` and `test_reviewer_is_not_the_author.py` respectively — and
   both concluded inside 16 minutes. Same workflow, same tree, two different failure modes.

**What is NOT claimed.** That this is F292's lock blocking instead of raising is the obvious guess
and it is **not evidence**: no stack, no `faulthandler` dump, and no log past the last `PASSED`
line. It is also **not** established that this is master-specific — the three hangs are all on
`master`, but nothing in `ci.yml` branches on the ref (no `concurrency:` block, no `if:` on the ref
for `hub-test`), so a sample of three on the busier-at-that-hour ref is as consistent with chance as
with a cause. Both questions need the *next* occurrence instrumented, not argued about.

**The cheap instrumentation, for whoever picks this up.** `hub-test`'s pytest invocation
(`ci.yml:136`) is a bare `pytest tests/ -v`. Adding `--timeout=120 --timeout-method=thread` (or
`-p faulthandler --faulthandler-timeout=120`) would convert the next hang from six silent hours into
a dumped stack naming the blocked call, at no cost to a healthy run. That turns the inference above
into a measurement, and it is a prerequisite for O2 being able to claim anything about the week's
green rate — a hung run is neither green nor red, and `gh run list` counts it as neither.

**Reproduce:** `gh run list --branch master --limit 10`, then
`gh run view 35218523888 --json jobs -q '.jobs[] | .name + ": " + .conclusion + " " + .startedAt + " -> " + .completedAt'`
and `gh run view 35218523888 --log | grep '^hub-test' | tail -30`.

**First instrumented occurrence, 2026-09-22 (found in an interactive session while closing F292).**
Run `35667708908` on `45d769f` (`autonomous/2026-09-21-daily`, not `master`, so the hang is not
master-specific). `hub-test` stopped at **9%** and `pytest-timeout` fired after 300 s, so the
mitigation works on CI: the run ended in about 6 minutes instead of 6 hours. The dump names
`tests/test_agent_trigger.py::test_spawn_failure_marks_run_failed`, main thread at
`test_agent_trigger.py:1701` `await _await_background_run()`, then `:47` `await task`. The
background run task started by `/agent/trigger`, with `PtySession.spawn` patched to raise
`FileNotFoundError`, never finished. The other threads are idle aiosqlite
`_connection_worker_thread`s and a `concurrent.futures` worker. None is shown blocked inside a
statement, so this dump gives no support to the "F292's lock blocking" guess. The thread-method dump shows threads, not
asyncio tasks, so *where* the background task is parked is still unmeasured. The next step is an
asyncio task dump (`asyncio.all_tasks()` + `task.get_stack()`) on timeout. This same test is the
one F109 carried as intermittent (see F109). **Reproduce:**
`gh run view 35667708908 --log-failed | grep -A12 'line 1701'`.

**Second instrumented occurrence, 2026-09-22 11:15Z: a different test with the same shape.** Run
`35719649675` on `a4d0976` (same branch). `hub-test` was killed at **13%** by the 300 s timeout in
`test_agent_trigger.py::test_an_unexpectedly_failed_run_still_gets_an_accounting_outcome`, main
thread at `:1876` `await _await_background_run()` → `:47` `await task`. **Both instrumented hangs
are tests that patch `PtySession.spawn` to raise** (`FileNotFoundError` in the first,
`RuntimeError` in this one) and then await the background run task that `/agent/trigger` started.
The task never finishes. That points at the spawn-failure path of the background run, or at how the
test awaits it, rather than at any one test. It is still inference: no dump shows where the task
is parked. Unrelated to the commit it ran on, whose `hub-test` changes are in
`test_refused_capability.py` only. The two earlier runs of the same change passed `hub-test`
(`229a708`, `24f3655`). **Reproduce:** `gh run view 35719649675 --log-failed | grep -A6 'line 1876'`.

**Root cause, 2026-09-22 (interactive session): the waiting test spins; nothing in the product is stuck.**
Both dumps show the main thread's stack *running* the test coroutine — `_run_once` → `handle._run` →
`test_…:1701` → `:47 await task`. A coroutine that was genuinely waiting on a pending task leaves the
thread parked in the selector with no test frames on it, so the coroutine was executing at the moment of
the dump. `await` on an already-finished task returns without yielding, and the helper was
`while _background_runs: for task in list(_background_runs): await task`. `_execute_run`'s
spawn-failure branch ends in `redrain_queued_agents`, which starts the retry run B as the failing run
A's last action. When B finishes in the loop pass right after A, the ready queue is `discard(A)`,
*wake test*, `discard(B)`. The test wakes, finds B done and still registered, awaits it without
yielding, and loops for ever; `discard(B)` never runs. That is why only spawn-failure tests hung (their
retry chain is fast enough), and why it was intermittent (it needs B's last step in that exact pass).
Reproduced in isolation (the old loop never returns). The CI occurrence itself is **not** reproduced
locally: the mechanism is inferred from the stack shape plus the isolated reproduction, and it matches both dumps.
**Fix `f9e6dee`:** one shared helper, `hub/tests/_background_runs.py`, that gathers and then removes
what it awaited from the set itself, so every pass progresses. It replaces six local copies and four
inline `while` loops. Single-pass `for` loops (e.g. `test_scheduler.py`) are bounded and left alone.
No product code has the pattern. `test_background_runs_helper.py` pins the ordering in a thread; it
fails against the old loop. Affected files: 268 passed, 1 skipped. **Proof on CI is the absence
of further `hub-test` timeouts at `_await_background_run`**; the `--timeout=300` mitigation stays.
F109's intermittent `test_spawn_failure_marks_run_failed` is plausibly the same thing (not checked).

## F395 (B) -- `POST /messages` treats every operator-sent message as if it were the deepest possible agent hop, and mislabels its origin

**Source: found by driving** (e2e-loop SWEEP, 2026-09-21, port 8030, `proj-05c8aa160921`).

**Status:** fixed (this commit) [Round 3, 2026-09-22], with F258 — see FIXED at the end of F258. The entry is labelled `origin_type="operator"` with no `origin_agent`, and the `queue_entry_queued` payload reports the entry's own origin rather than a literal `"agent"`.

**What happens.** The one route that injects a message into an agent's inbound queue —
`POST /projects/{id}/messages`, body `{"from": ..., "to": ..., "content": ...}` — is used both by
an agent's `send_message` tool (which always supplies `run_id`, so `hop_depth` is computed from the
sending run's real `turn_depth`) and by an operator sending a message directly with no `run_id`
(`hub/hub/api/v1/messages.py:56-71`). For the no-`run_id` case the code does not treat the message
as hop 0 (an operator's message from outside the chain, having consumed none of the hop budget). It
falls through to `hop_depth = hop_budget + 1` — a value written to always exceed the project's own
`hop_budget` — so the entry is queued already over budget and immediately suspended
(`queue_chain_suspended`), needing a manual `POST /queue/entries/{id}/release` before the agent ever
sees it. Separately, the entry this produces is stamped `"origin_type": "agent"` unconditionally,
even though `origin_agent` correctly says `"operator"` — so the record a reviewer would use to
diagnose *why* an entry is suspended says the wrong thing about who sent it.

**Evidence.** Sent as the operator (Bearer = the Hub's own API key, `from: "operator"`, no
`run_id`) to agent `reviewer`, project hop_budget 6:

```
POST /projects/proj-05c8aa160921/messages {"to":"reviewer","from":"operator","content":"operator injected note: hold for now"}
-> 201 {"id":"msg-ed378c68d2ad", ...}
```//not shown in queue GET directly; queue entry:
```
GET /projects/proj-05c8aa160921/queue/reviewer
-> {"id":"entry-304fc29eea8e","agent":"reviewer","origin_type":"agent","origin_agent":"operator",
    "content":"operator injected note: hold for now","hop_depth":7,"state":"queued", ...}
```
`event_logs` row (read directly from `profiles/drive0920/agentweave.db`):
```
('queue_chain_suspended', '{"entry_id": "entry-304fc29eea8e", "agent": "reviewer", "hop_depth": 7, "hop_budget": 6}')
```
7 = `hop_budget(6) + 1`, confirming the fallback branch fired rather than any real chain depth. In
the same batch, a same-endpoint agent-to-agent message (`alpha` -> `reviewer`, sent from inside a
real run so `run_id` was present) got `hop_depth: 1` and delivered normally — the bug is specific to
the no-`run_id` path, i.e. specific to how an operator's own send lands.

**One defect or a design gap?** One defect (a missing `is_operator` / no-`run_id` branch that should
assign `hop_depth: 0` and `origin_type: "operator"`), not a symptom of something broader — the
agent-to-agent path in the same function is correct.

**Does an existing openspec change cover it?** No hit for `hop_depth`, `origin_type`, or
`queue_chain_suspended` combined with "operator" in `openspec/specs/` (checked
`agent-conversation-workspace`, `agent-flows`, `agent-tool-surface`, `local-project-workspace`,
`run-task-binding` — the five specs that mention hops at all). This looks like new news, not a
known gap.

**Severity: B** (wrong/misleading) rather than A: the operator's message is not lost — `release`
recovers it, and withdrawal also works cleanly (verified: `DELETE /queue/entries/{id}` moved it to
`state: "withdrawn"`) — but every operator-authored queue injection is silently held back and
mislabeled as agent-originated until the operator separately discovers and clears the suspension,
which nothing in the response to the original POST surfaces (the 201 body has no `hop_depth` or
suspension warning at all).

**FIXED 2026-09-22 (interactive session, Round 3, group 3a)** together with F258, one change. Both halves are covered by `test_an_operator_message_is_queued_at_depth_zero_as_the_operators`: depth 0, `origin_type == "operator"`, `origin_agent is None`, no `queue_chain_suspended` event, and a `waiting_reason` that does not blame the hop budget.

## F396 (B) -- the MISREPORT ratchet is keyed by file:line, was already decayed on the day its ceiling was measured, and its own warning tells the next reader to make the decay permanent

**Source:** audit

**Status:** fixed (this commit) [Round 1, 2026-09-22]. Re-keyed on (file, hook, occurrence); see FIXED at the end of this entry. **Found 2026-09-21** by the night window, while deciding whether to act on a
chore the same window's iteration 8 had noticed and not converted ("`MISREPORT_CEILING` reports the
live count dropped to 49 from a ceiling of 52 -- the constant should be lowered to hold the new
floor, but that is a separate, unscoped chore"). Acting on it would have been wrong.

**The instrument.** `hub/tests/test_surface_ceilings.py:35` freezes `MISREPORT_CEILING = 52`
("Measured 2026-09-10") and `test_no_new_misreporting_surface` ratchets
`len(n11.operator_reachable_misreports(n11.unhandled_sites()))` against it. `_ratchet` (`:59-64`)
warns when the count *shrinks*: *"Lower the constant in test_surface_ceilings.py so the ratchet
holds the new floor."* The live count today is **49**.

**The drop is not repair. It is the classification table falling off its own keys.**
`operator_reachable_misreports` (`scripts/drive/n11_query_error_surface.py:395-406`) looks each
unhandled site up in `RENDERS` by `(file, line)`; a miss silently returns `UNCLASSIFIED`, which is
not counted. So a line shift *anywhere above* a classified site demotes it to invisible. Measured,
by asking how many `MISREPORT`-and-not-`DEAD` keys match no live unhandled site at all:

| tree | MISREPORT non-DEAD keys | stale keys | counted |
|---|---|---|---|
| `6484de4` (the commit that froze the ceiling, 2026-09-10) | 57 | **5** | 52 |
| `8508377` (today) | 57 | **8** | 49 |

`57 - 5 = 52` and `57 - 8 = 49` exactly. **The three-surface "improvement" is three more
classifications going stale, and zero surfaces were fixed.** All three are in
`AgentOutputPanel.tsx` (keys `319`, `330`, `346`), whose only commits since 2026-09-10 are
`e9f71c0` and `1731522` (2026-09-13) -- the F341/F342/F344/F345 fixes, which repaired *other*
findings and shifted lines past these ones.

**The surfaces are still there.** 18 live unhandled sites are `UNCLASSIFIED` today, and six of them
are the stale keys' own hooks at new line numbers, still reported by `unhandled_sites()` (i.e. the
call site still never binds and uses its query's error):

| stale key | `why` recorded for it | live today, unclassified |
|---|---|---|
| `AgentActivityTab.tsx:24` | "same feed, same sentence (:112)" | `:26` `useAgentTimeline` |
| `AgentOutputPanel.tsx:207` | "`conversations = []` drives the list" | `:256` `useAgentConversations` |
| `AgentOutputPanel.tsx:319` | "`roster = []` ... the agent's own row missing" | `:368` `useAgents` |
| `AgentOutputPanel.tsx:346` | "`workspacePaths={[]}` (:1152)" | `:394` `useWorkspacePaths` |
| `AgentOutputPanel.tsx:347` | "`timelineEntries = chat.data?.entries ?? []`" | `:395` `useAgentChatHistory` |
| `AgentOutputPanel.tsx:348` | "the same `chat` when no conversation is selected" | `:396` `useAgentRecentChat` |

**Read that table as a reconstruction, not a measurement.** The dead keys carry no hook name, so
nothing machine-checkable links a stale key to the live site it became; the pairs above are read
off the `why` strings the table recorded. What *is* measured is the part the severity rests on:
**8** `MISREPORT` keys match no live site, **18** live unhandled sites carry no classification, and
`unhandled_sites()` still reports every site in the right-hand column -- so those six surfaces
still never bind their query's error, whichever key each one used to be.

**It was born decayed, which is the part worth keeping.** At `6484de4` itself, keys `346`/`347`/`348`
pointed at `const recentChat = useAgentRecentChat(...)`, `const chat = ...` and
`const timelineEntries = ...`, while the `why` string filed under key *N* describes the code at
*N+1*. `6484de4` touched no `.tsx` file (its diffstat is two `scripts/drive/` reports, two test
files and two loop-state files) and `6484de4^` has the identical lines, so the table was authored
against a revision older than the one it shipped in and **never matched the tree it was committed
with**. The ceiling has never been a measurement of 52 live misreporting surfaces.

**The sibling ratchet is intact and already names this hazard.** `UNHANDLED_SITE_CEILING = 100` is
exactly met today (100 live), and `test_no_new_query_call_site_ignores_its_error`'s docstring says
outright that it *"reads no classification at all, which also makes it immune to the line shifts
that silently re-key that table."* The hazard it names is real and has now fired twice.

**What must not happen:** lowering `MISREPORT_CEILING` to 49. That is what `_ratchet`'s warning
text asks for on every run, and what this window's iteration 8 wrote down as a chore. It would
freeze a floor that eight dead dictionary keys produced.

**The fix is re-keying, not re-numbering** -- anchor `RENDERS` to something a line shift cannot move
(the `(file, hook)` pair, or the site's own text) and re-measure from there; the 18 `UNCLASSIFIED`
sites then need triage, not just the 6 that were classified before. **Not done in this firing**:
that is a change, and the night window does not write proposals. Queued as an operator decision
instead.

**Severity B**, not C: the instrument exists to stop new operator-visible lies from landing, it has
silently stopped seeing at least six it had already identified, the loss reads as progress in the
one number anyone looks at, and its own warning instructs the action that makes the loss permanent.
It is not A -- no product behaviour regressed, and the underlying `UNHANDLED_SITE_CEILING = 100`
ratchet still catches a genuinely *new* offender.

**Independently re-derived 2026-09-21 by the next iteration**, before committing the filing above,
because the whole finding turns on two counts and the round that wrote them died before it could
commit. At HEAD `8508377`: 100 live unhandled sites, **49** `operator_reachable_misreports`, 57
`MISREPORT` non-`DEAD` keys, **8** stale, **18** live `UNCLASSIFIED`. In a throwaway worktree at
`6484de4` (`git worktree add --detach`, removed afterwards): 100 live unhandled, **52** misreports,
the same 57 keys, **5** stale. The three keys that went stale in between are exactly
`AgentOutputPanel.tsx` `319`, `330`, `346`, as claimed. Every number above reproduces.

**And the warning fired in tonight's full suite run**, which is what makes this urgent rather than
theoretical: `hub/tests/test_surface_ceilings.py:103: UserWarning: operator-reachable MISREPORT
surfaces dropped to 49 from a ceiling of 52. Lower the constant in test_surface_ceilings.py so the
ratchet holds the new floor.` A reader who does what that sentence says freezes eight dead keys as
the floor. It is emitted on every green run, so it will keep asking.


**FIXED 2026-09-22 (interactive session, Round 1).** Re-keyed, re-measured, and the decay made a
test failure:

- **Mechanically re-keyed, not by reading `why` strings.** All 101 rows were written in `894b48e`
  (2026-09-02, `git log -S`). `n11`'s own `call_sites()` was run over that tree's `hub/ui/src`, and
  **every one of the 101 line keys landed on a real call site there**, and every `why` describes
  the hook on its line. So the table was right when it was written and drifted afterwards. The
  "born decayed at `6484de4`" reading above is about the commit that froze the ceiling, not the
  one that wrote the table. Each row now names `(path, hook, occurrence)`: the `occurrence`-th call
  of that hook in that file, in source order. A line shift cannot move that.
- **What the re-key found.**
  - The finding's 6-row reconstruction was right, pair for pair.
  - 19 rows were stale in all classes, not the 8 MISREPORT rows this entry counted. 17 of them
    relocate to the 17 old sites among the 18 `UNCLASSIFIED`.
  - **One row was worse than stale.** `TaskDetailDrawer.tsx:150` was written for `useAgents`
    (`BLANK`), and at HEAD line 150 is `useAllowedTransitions`. The table was applying one hook's
    classification to a different hook.
  - Two rows were real repairs, and are removed. `AgentOutputPanel` no longer calls
    `useAgentTimeline`. `InstructionsPage` now binds and uses `isError` from `useInstructions`
    (`cd78e17`/`1492069`).
  - One site is genuinely new: `InstructionsPage` `useProjects`. It is classified `BLANK`, because
    the clear dialog's name falls back to "this project".
- **Re-measured.** 100 unhandled sites: 0 unclassified, 0 stale. **55** operator-reachable
  MISREPORT surfaces, which is 49 plus the six. `MISREPORT_CEILING` goes 52 -> 55, the one
  deliberate raise, with the reason stated beside the constant. `UNHANDLED_SITE_CEILING` stays 100.
- **Decay is now a failure, not a warning.**
  - `n11.stale_classifications()` lists every row that names no unhandled site.
    `test_no_new_misreporting_surface` refuses to read the count while any row is stale, so a
    repaired site has to take its row with it before the drop can show.
  - `test_the_misreport_count_does_not_move_when_lines_do` shifts every site by 40 lines and
    requires the same count. On HEAD's line-keyed table it gives 49 -> 0, and it passes here.
  - `test_a_repaired_site_leaves_its_row_stale_rather_than_uncounted` removes one live MISREPORT
    site and requires exactly its key back.
- **Not changed:** `_ratchet`'s "lower the constant" warning. With stale rows now forbidden, a drop
  can only come from a row deleted with its repair, and that is the case the warning was written
  for.


**Opus review, applied the same session.** The reviewer re-derived the re-key independently — all
101 old keys resolve at `894b48e`, the mapping reproduces the new table exactly, and 55 is right —
and found one hole left open:

- **A new *unhandled* call of a hook, inserted above a classified call of the same hook, takes over
  that row's `occurrence`.** The row still matches a site, so neither the count nor the stale check
  moves; the real misreporting site becomes `UNCLASSIFIED`, which nothing asserted on. Only
  `UNHANDLED_SITE_CEILING` caught it, and only because it sits at exactly 100/100.
  `n11.unclassified_sites()` now exists, and `test_no_new_misreporting_surface` refuses to read
  the count while any site is unclassified.
  `test_a_new_call_above_a_classified_one_is_refused_not_absorbed` performs that exact insert on a
  copy of `hub/ui/src` and requires the refusal.
- **The line-shift test proved nothing.** It only edited `line` in the site dicts, and `site_key`
  never reads `line`, so it could fail only if the key went back to lines. It now writes 40 blank
  lines into every file of a copied `hub/ui/src`, re-scans from disk, and requires the same count.

## F397 (D) -- archiving an already-archived agent is a 200 that re-stamps `archived_at` and writes a second `agent_archived` event

**Source:** drive

**Status:** fixed (this commit) [Round 4, 2026-09-23] — re-archiving is a no-op 200; see FIXED at the end of this entry. Was: open. **Found 2026-09-21** by the day window's D-1 drive of
`an-archived-agent-holds-nothing-and-is-offered-nowhere` (`scripts/drive/d1_0921_archived_agent_drive.py`).

**Repro.** Fresh project, agents `aa`, `bb`, a charter bound to both. `POST /agents/bb/archive`
twice. Both return 200 (the second with `released_charter_id: None`). `GET /events/history` then
lists `agent_created` x3 and `agent_archived` x3 (aa, bb, bb): the no-op second call is
indistinguishable in the log from a real archival. `agent_lifecycle.archive`
(`hub/hub/agent_lifecycle.py:73-75`) assigns `archived_at = now()` unconditionally, so the original
archival time is also lost.

**Why D.** Nothing reads `archived_at` or the event today (design D10 says nothing renders these),
so no operator sees it. It matters only once the event is displayed or `archived_at` is shown.
Suggested fix when it does: `archive_agent` returns early (still 200) when `lifecycle == "archived"`
and writes no event.

**What held (same drive, 16 of 17 checks):** charter wall (F185) clears at archive and names the
released charter; re-bind to an archived agent 409s naming "Unarchive it first"; runner wall (F390)
tags archived holders and points at the archived filter; launchability omits archived agents and
`POST /agent/trigger` refuses them (F181); unarchive returns the standing sentence and the agent
runs a real Haiku turn charterless. The one BAD line was the script's wrong expectation: archiving
mid-turn is refused 409 "cc has a run in progress. Wait for it to finish, or stop it first." --
a gate that held and says what to do.

**FIXED 2026-09-23 (interactive session, Round 4, group 4c).** `archive_agent` returns early when the agent is already archived: 200, `lifecycle: archived`,
`released_charter_id: null`, `message: "<name> was already archived; nothing changed."`. It writes no
event and leaves `archived_at` unchanged. Measured by `hub/tests/test_a_request_means_what_it_says.py` (the second call leaves one
`agent_archived` event and the first `archived_at`); fails on the old code.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The mirror case: `unarchive_agent` on an open agent wrote and broadcast a second
`agent_unarchived`. It now returns early too (200, `"<name> was not archived; nothing
changed."`, no event). `test_unarchiving_an_open_agent_changes_nothing` fails on the previous
commit.

## F398 (C) -- `dismiss-checkpoint-warning` accepts a conversation that was never warned, and the pre-emptive dismissal silences its first warning for good

**Source:** drive

**Status:** fixed (this commit) [Round 3, 2026-09-22], with F233 — `dismiss-checkpoint-warning` requires a showing (`due`) warning; see FIXED at the end of this entry.

**Repro.** Conversation `conv-5317a4b4f3a9`, `checkpoint_warning` null, threshold not yet crossed.
`POST /conversations/{id}/dismiss-checkpoint-warning` -> **200**, `checkpoint_warning: "dismissed"`.
Lower the threshold and run another turn so it crosses: the warning stays `'dismissed'` -- the first
warning is never shown. The route (`hub/hub/api/v1/checkpoints.py:~244`) refuses only `final`; it
writes `dismissed` from any other state, including none.

**Why C.** The app only shows the dismiss button on a warned conversation, so an operator does not
reach this from the UI; an API caller or a stale tab does, and the cost is a conversation that grows
to the provider's compaction with no warning ever raised. Suggested fix: 409 (or a 200 no-op) unless
the current state is `due`.

**FIXED 2026-09-22 (interactive session, Round 3, group 3c)**, the guard this entry suggested. `due` → `dismissed` as before; `final` → the existing 409; already `dismissed` → 200, unchanged (a repeated dismissal is not an error); never warned (`None`) → 409 *"This conversation has no checkpoint warning to dismiss: it has not reached its threshold…"*, state untouched. The UI only offers Dismiss on a `due` banner, so nothing shipped is refused. Tests: `test_a_warning_that_is_not_showing_cannot_be_dismissed` (fails on the old code), `test_dismissing_twice_is_not_an_error`.

## F399 (D) -- taking a checkpoint does not clear a `dismissed` warning, so the conversation is never offered another

**Source:** drive

**Status:** retired 2026-09-22 as a duplicate of F234: same line (`checkpoints.py:190` clears only `due`/`final`), same defect, re-checked today. The fix is tracked under F234 (Round 4 of `spec-queue/ROUNDS.md`). Was: open. **Found 2026-09-21**, same drive as F398, legs 4 and 12.

**Repro.** Warn -> dismiss -> operator takes the checkpoint. `checkpoint_warning` stays `'dismissed'`
(`checkpoints.py:190` clears only `due` and `final`), and one turn later it is still `'dismissed'`. The
control conversation, never dismissed, is cleared to null on taking and offered `'due'` again on the
next crossing -- the two conversations diverge only by whether the operator once said "not yet".

**Why D.** A normal cutover archives the predecessor, so the stale state rarely lives on a
conversation that continues; it bites only a conversation kept running after its checkpoint.

**Not filed:** leg 8's "second checkpoint took a note written before the first" (1 fail) -- the
script's expectation about which notes a second checkpoint should consume is unverified against the
consumption rule; read `checkpoint` note selection before treating it as a defect.

**What held (same drive):** 70 checks including the agent plane grants, visibility, 404 shapes,
cutover, and the served UI bundle agreeing with source.

## F400 (B) -- Run on a documentless loop whose agent is busy answers "no other agent is free" while another agent is free

**Status:** fixed (2026-09-25) by `8c6cb54` (`pressing-run-names-the-reason-that-held`, archived 2026-09-25); driven 2026-09-25 on a fresh trial Hub (8026, `drive0925morning`, Haiku): 409 "author is already running a turn, and this loop's work goes only to author, the agent its job names. Nothing was started."
**Status when filed:** open. Filed 2026-09-21 by an interactive session, **by operator decision**: this is
`a-loop-staffs-the-agent-it-names` §5 (tasks 5.1-5.5, design D4), moved out of that change so the
rest of it can be driven and archived (`spec-queue/DECISIONS.md`, `### 2026-09-21 evening`). §5 was
never approved: its requirement (`agent-loops` *"Pressing Run on a loop that declines names why it
declined"*, the `:1471` MODIFIED block) was rewritten in R4 and no round re-derived it, and design
Open Question 2 (`_stall_reason_from_walk`'s exact current sentence) was never read.
**Source:** review
**Theme:** Flows & loops
**Related:** F127, F128

**What happens.** `run_job`'s busy-guard branch (`hub/hub/api/v1/jobs.py:1347-1361`) builds its 409
as `f"{busy_reason}, and {why}. Nothing was started."`, where `why` is either *"no other agent is free
to take this loop's work"* or *"this loop's queue holds no open task for another agent to take"*.
Since `a-loop-staffs-the-agent-it-names` §1/§3, a loop that declares no specification document is
refused whenever its own agent is busy **regardless of who else is free** -- so for that loop the
first clause can be false (another agent *is* free, and freeing one more changes nothing) and the
second clause's *"for another agent to take"* describes something the loop would never do. F127's
shape: a true-sounding sentence that tells the operator to do something useless.

**What the fix needs (from the moved §5, not re-derived).** Split `why` so a documentless loop is
told it runs only the agent its job names; drop *"for another agent to take"* for a loop; change the
`:1471` requirement's *"which of those two held"* to cover the third condition in the same edit
(R4-2: a three-way answer does not fit a two-way SHALL); and test the absence of each false clause,
not only the presence of the true one. Read `_stall_reason_from_walk`'s current sentence before
asserting what `jobs.py:355` replaces on the board (5.4). **Needs its own proposal and rounds.**


**Note, 2026-09-23 (day window, D-2b R1).** Proposed as `openspec/changes/pressing-run-names-the-reason-that-held`, together with F373 (same branch of `run_job`, same requirement). Re-measured on `dcdf723` through the real route (`scripts/drive/d2b_0923_run_answer_probe.py`). The archived change's Open Question 2 is answered by measurement: the board already reads the busy sentence (`jobs.py:357`), so only the route is wrong. R1 also found two existing assertions (`test_board_agent_role.py:385`, `:420`) that pin *"no other agent is free"* on documentless loops. The change moves them on purpose.
---

## F401 (B) -- a bare variable or command substitution names a directory the shell judge never checks

**Status:** fixed f73ae13..de74c2a (change `a-drive-or-a-home-variable-names-a-directory-by-itself`, 2026-10-07; driven in real PowerShell 5.1 and Git Bash, tasks 3.1). Was: open. Filed 2026-09-21 by an interactive session, **by operator decision**
(`DECISIONS.md` `### 2026-09-21 late evening`), as non-goal D5 of
`a-word-without-a-separator-can-still-leave` (F375).
**Source:** review
**Theme:** Workspace & permissions
**Related:** F375, F402, F403

**What happens.** `cp notes.md $HOME` and `cp notes.md $(dirname $PWD)` are answered **allow,
"inside your workspace"** by `_decide` (measured 2026-09-21), and both land outside. Rule 3 of
`_judge_word` (`hub/hub/mcp_server.py:1156`) refuses a word that expands only when it also contains a
separator, and a bare `$HOME` does not. **Why it was not fixed with F375:** refusing every
separator-less word containing `$` would refuse `echo $x`, `for f in $files` and most ordinary shell,
and `_decide`'s docstring already disclaims paths built at run time (`:1448-1449`). The fix needs its
own trade-off: for example, refuse a bare expansion only in an argument position a known file tool
reads as a destination, or accept the disclaimer and close this as documented.

---

## F402 (B) -- a PowerShell drive-qualified word (`Z:`) reaches the judge with its colon trimmed

**Status:** fixed f73ae13..de74c2a (change `a-drive-or-a-home-variable-names-a-directory-by-itself`, 2026-10-07; driven in real PowerShell 5.1 and Git Bash, tasks 3.1). Was: open. Filed 2026-09-21 by an interactive session, **by operator decision**, as non-goal
D6 of `a-word-without-a-separator-can-still-leave` (F375).
**Source:** review
**Theme:** Workspace & permissions
**Related:** F375, F401

**What happens.** `Copy-Item notes.md Z:` is allowed (measured): `_WORD_TRIM` includes `:`
(`mcp_server.py:981`) and `_words` strips it from both ends (`:1396`), so rule 4 judges `Z`. In
PowerShell, `Z:` is drive Z's current location, which is outside a workspace on another drive; PS 7's
`Temp:` drive is the multi-letter form. **Constraints any fix must meet (measured):** Git Bash writes
a file literally named `C:`, so the fix is PowerShell-only; and it must not refuse
`git show HEAD:README.md`.

---

## F403 (B) -- bash brace expansion assembles `..` that no rule sees

**Status:** fixed 065bfc9 (`the-shell-judge-reads-a-word-whole` D1, tasks 1.2 and 1.3, with the
inner-shell brace reading in e1fe7c1; change archived 2026-10-04).
Filed 2026-09-21 by an interactive session, **by operator decision**, from R2 of
`a-word-without-a-separator-can-still-leave` (F375), design Open Question 1.
**Source:** review
**Theme:** Workspace & permissions
**Related:** F375, F401

**What happens.** `cp notes.md .{,.}` and `cp notes.md {.,.}.` land in the parent directory in Git Bash
5.2.37 (R2, measured) and are allowed by the judge, before and after F375's change: `_lex` does not
model brace expansion for any rule. `..$x` with `x` unset lands there too (a bare `$` word, F401's
shape). The fix belongs in the lexer, or in a rule that refuses a separator-less word whose braces
could expand to `..`.

---

## F404 (C) -- `from agentweave.templates import *` raises: `__all__` names a constant nothing defines

**Status:** fixed 542418e -- the name is removed and `tests/test_package_exports.py` walks every
module's `__all__` in the package (mutation-checked: it fails with the name restored).
**Source:** review
**Theme:** Harness & CI
**Related:** the dead-code annotation pass `4bd966e` (handoff 0134), which found it.

**What happens.** `src/agentweave/templates/__init__.py`'s `__all__` listed `SKILL_REFERENCES_DIR`,
which the module never defines. `from agentweave.templates import *` raised
`AttributeError: module 'agentweave.templates' has no attribute 'SKILL_REFERENCES_DIR'` (re-measured
2026-09-21) in the published `agentweave-ai` package. Filed 2026-09-21 by operator decision, after
being offered across four sessions.

---

## F405 (C) -- both `examples/*.py` raise `ImportError` on their first line, and no CI job runs them

**Status:** fixed 542418e -- both files deleted; `examples/README.md` now says nothing in the
directory works with the current product. `examples/cli_session.sh` and `.bat` remain and still call
removed commands (`agentweave init`, `task`, `msg`); deleting the whole directory is the operator's
call (the wider deletion was held for approval).
**Source:** review
**Theme:** Harness & CI
**Related:** F404.

**What happens.** `examples/basic_workflow.py` and `examples/parallel_workflow.py` did
`from agentweave import ... Message ...`, the messaging API deleted when the Hub took over execution,
and both died with `ImportError: cannot import name 'Message' from 'agentweave'` (re-measured
2026-09-21). The README pointed new users at them as the "Learning Path". Filed 2026-09-21 by
operator decision.

---

## F406 (D) -- an auto-loaded agent rule guarantees every save passes through `validator.py`, which nothing imports

**Status:** fixed 542418e -- `.claude/rules/cli.md` now says the module is dead and the Hub's
pydantic schemas validate writes.
**Source:** review
**Theme:** Harness & CI
**Related:** F404; `src/agentweave/validator.py`'s own `# DEAD (2026-09-20)` header, which asked for
this correction.

**What happens.** `.claude/rules/cli.md:17` stated *"ALL saves pass through `validator.py` sanitize
functions."* The only importer of `validator.py` is `tests/test_validator.py`. The rule loads into
every session that reads a file under `src/agentweave/`, so it steered agents toward a dead module.
Filed 2026-09-21 by operator decision.

## F407 (D) -- a review-dispatch refusal on an `under_review` task starts a sentence in lowercase

**Status:** fixed 6961cc4 [D-6, 2026-09-22]
**Source:** review
**Theme:** Flows & loops
**Related:** `an-unstaffed-review-names-its-holders` design.md R8-3 (which noted it as "worth a
finding" and did not file it) and R9; the archived sibling that shipped `review_dispatch_refusal`.

**What happens.** `own_review_remedy` (`hub/hub/scheduler.py:1991-2020`) returns
`"decide it yourself: approve, reject, or send it back with revision_needed."` for an
`under_review` task -- lowercase, because it was written to follow a colon or semicolon. The shipped
callers place it after a full stop: `review_dispatch_refusal` (`hub/hub/api/v1/agent_trigger.py:503,
511, 521`) and `trigger_agent_directly`'s in-flight refusal (`:848`). The operator's 409 for a task
already under review therefore reads *"… Let the review in flight finish. decide it yourself: …"*.
Read from source 2026-09-22 (day window, R9); not yet observed on a live Hub. The rung-3 reason in
the unbuilt change capitalises at its own join (task 2.3, `capitalize_first`) and does not change
the helper; the same treatment at these four sites, or a helper that returns a capitalised
sentence and a lowercase caller where one exists (none today), would close it.

**Fix, `6961cc4`.** `own_review_remedy`'s `under_review` branch now returns
`"Decide it yourself: ..."`. Checked all four call sites first: every one places it after a full
stop, and no caller anywhere needs the lowercase form, so the one-word change at the source closes
all four without touching `agent_trigger.py`. `hub/tests/test_a_refusal_names_a_remedy_that_works.py`
updated (the `own_review_remedy` unit assertion plus two `.count("Decide it yourself")` dispatch
tests) -- mutation-checked by hand: `git stash` on `scheduler.py` alone turned 3 of 18 tests in that
file red (`assert 0 == 1` against a live-rendered lowercase sentence), restoring it turned them
green again. `ruff check src/ hub/ tests/` and `black --check --target-version py311 ...` both
clean.

**Driven, not just tested.** Fresh scratch Hub on port 8013
(`~/.agentweave/hub/profiles/drive0922c/agentweave.db`), started from `hub/` source.
`scripts/drive/d6_0922_f407_capitalization.py`: one real Haiku turn (`f407-author`, project
`proj-844073d6cbc4`, never `proj-5e960453`/`proj-18e5d4e0`) authors a file and completes its task
with recorded evidence naming a commit -- required because the public dispatch route
(`agent_trigger.py:1455`, `commit_for_task_review`) gates on it before ever reaching
`review_dispatch_refusal`. An operator PATCH then wedges that task `under_review` under a second
agent, and a third agent is dispatched naming `review_task_id`: real `POST /agent/trigger` answers
`409 "Task task-28028c60dfc9 is already under review by 'f407-rev-a'. Let the review in flight
finish. Decide it yourself: approve, reject, or send it back with revision_needed."` -- capitalised,
no stray duplicate, the old `"finish. decide it yourself"` fragment gone. This exercises
`review_dispatch_refusal` (the site of three of the four callers, 503/511/521, all the same
function call); site 848 (`trigger_agent_directly`'s own in-flight check, reached only through the
scheduler's internal dispatch) was not independently reached live -- a cold `POST /jobs/{id}/run`
against a wedged review hits `_wedged_review_reason`'s unrelated stall detector first (F154's own
message), a pre-existing scheduler behaviour this fix does not touch. Not a gap in the fix itself:
`own_review_remedy` is a pure function called identically at all four sites, so one live call
confirms the source-level change; the case that could differ per-caller (whether the join is a full
stop) was checked by reading all four sites, not assumed. 11/11 checks passed. Cleanup: all three
scratch projects from this session deleted (`DELETE /projects/{id}`, including two from earlier
attempts that hit different guards before the final script version), the job disabled and confirmed
absent from `GET /jobs?include_archived=true`, the Hub's uvicorn process stopped and confirmed no
`LISTENING` socket remained on 8013 afterward (only `TIME_WAIT`).

## F408 (C) -- a CLI thread-race test reads a slow runner as a lock that lost its loser

**Status:** fixed (this commit) [Round 1, 2026-09-22]
**Source:** audit
**Theme:** Harness & CI

**What happened.** CI run `35753872487` (`77d39f9`) went red on one job,
`test (windows-latest, 3.12)`:
`tests/test_locking.py::test_concurrent_threads_exactly_one_wins` got `[True]` where it expected
`[False, True]`. The run raised no exception and logged no `PytestUnhandledThreadExceptionWarning`,
so the losing thread had not crashed. It was still running when both `join(timeout=3.0)` calls
expired. `acquire_lock(..., timeout=0.3)` bounds how long a thread *tries* the lock. It does not
bound when a shared runner schedules that thread. The assertion then reported a wrong answer from
the lock when the lock had not answered yet.

**How often.** Once in 311 failed `ci.yml` runs since 2026-03-13, all searched for
`FAILED tests/test_locking.py`. That makes it rare, but a single occurrence is enough to fail a
push. It is in Round 1 because that round makes CI's red mean something.

**Fix.** The three thread-race tests in `tests/test_locking.py` join through `_join_all`, which
waits up to `JOIN_TIMEOUT = 30.0` and asserts every thread finished before any result is read.
A hung thread now fails as "did not return within 30s", not as a wrong result. The proof is an
injected stall: a 4 s sleep in the first caller of `acquire_lock`, run through the real test
function. It fails at HEAD with CI's exact message (`got [True]`) and passes with the fix
(4.34 s). The full CLI suite gives 538 passed and 3 skipped, the same as before.

**Opus review, applied the same session.** The reviewer confirmed the slow-thread diagnosis (the
failing test ran 3.05 s and the log carries no warnings summary, so a thread that had raised would
have ended it in under 0.5 s) and raised two gaps, both now closed:

- **A thread that raises still printed as a wrong result.** `_run_concurrently` replaces
  `_join_all`: it captures each thread's exception and re-raises it on the test's thread. This is a
  live path on Windows, where `acquire_lock` catches only `FileExistsError` while a delete-pending
  file makes `open(..., "x")` raise `PermissionError` (`locking.py:36-41`).
- **The sibling test had the same race.** `test_lock_held_blocks_other_thread_with_short_timeout`
  had T1 hold for a fixed 0.5 s; a T2 descheduled longer than that would acquire the lock and fail
  the assertion. T1 now holds until T2 has finished trying.

Each is pinned by an injected fault run against both trees: a 4 s stall, a `PermissionError` in one
thread, and a T2 delayed 1 s. All three fail at `4824150` and pass here.

## F409 (A) -- another agent's text can make a Claude turn read any file, before any tool call, past every posture

**Status:** fixed 945005d (archived as `openspec/changes/archive/2026-09-27-an-at-mention-an-agent-wrote-reads-no-file`; driven live 2026-09-27)
**Source:** drive
**Theme:** Workspace & permissions

**What happens.** The `claude` CLI expands an `@path` token in its `-p` prompt into an attached file
before the model runs, with no tool call. `format_turn_prompt` (`hub/hub/inbound_queue.py:129`)
puts every queued entry's content into that prompt verbatim: a peer's `send_message`, a job or loop
briefing (task title, description, acceptance criteria, prior checkpoint), a checkpoint delivery,
a delegation task, and (inside an operator-origin entry) the agent's own `ask_user` question
(`questions.py:229`, `:233`). `runner_commands.py:283` passes it as `-p`. So one agent can make
another agent's turn read any file the Hub's user can read, and neither `--disallowedTools` nor the
default "Workspace only" posture sees it, because the Hub's `--permission-prompt-tool` is only asked
about tool calls. Nothing records the read. Boundary escapes are graded A in this ledger
(F321, F323, F331).

**Measured on this machine, 2026-09-23, `claude` 2.1.280** (first by the research routine, then
independently in the day window's D-2 round, which is this filing). The prompt had the Hub's exact
queue shape, and every file tool was disallowed. It returned a marker from a file outside the
working directory with **0 tool calls**, and the CLI's session transcript holds
`"attachment":{"type":"file"}`. `@../x`, `@"<abs>"`, a backslash path, and an at-sign after a
newline, tab, U+00A0, U+3000, U+2028 or **U+FEFF**, inside a code fence, or after `> ` all expand
the same way. A backslash immediately before the at-sign stops it. Full table and probe:
`scripts/drive/d2_0923_at_mention_tokeniser.py` and the change's `design.md`.

**Why the upstream opt-out is not the fix.** `client_composed: true` on a stream-json user frame
(claude-agent-sdk-python #1269) stops the read, but it was measured dropping the deferred-tools and
MCP-instructions attachments. With the Hub's own `--mcp-config`, the model could name **none** of
the 27 `mcp__agentweave__*` tools.

**Not yet driven through a live Hub.** The measured link is the CLI's behaviour on the exact prompt
shape. The Hub's path to that prompt was read, not driven. The change's task 4.1 drives it end to end.

**R2 widened it (2026-09-23): the Hub's one-shot workers expand too.** The checkpoint worker
(`worker.py:139`) and the conversation titler (`conversation_titles.py:71`) put recorded text on
`claude -p`. That text is the conversation transcript, the agent's notes and the opening exchange,
and neither worker has any permission posture. Measured with argv built by the Hub's own
`build_generation_prompt`, `build_worker_command` and `build_title_command`
(`scripts/drive/d3_0923_worker_at_mention.py`), run twice on fresh markers: both attach an agent's
`@<outside path>`. **The checkpoint worker's JSON reply carried the file's contents**, so they reach
the stored checkpoint, which the operator reads and the successor agent is given. The agent turn's
`--append-system-prompt-file` context was measured as a control and does **not** expand. The change's
design D7 covers the workers.

**R3 found one more vector (2026-09-23), read and not driven: the board's Start work.**
`useStartWorkOnTask` (`hub/ui/src/api/tasks.ts:455`) posts `Work on task <id>: <title>` as an
*operator* message, and an agent can write the title (`create_task`). Operator entries are passed
through untouched, so a task an agent titled with an `@<outside path>` makes the next agent the
operator starts on it attach the file. The change's design D8 covers it (the title is escaped where
the browser builds the message).

---

## F410 (C) -- a checkpoint or divergence delivery reaches the agent labelled `Agent "None"`

**Status:** fixed (this commit) [Round 6, 2026-09-24] — `format_turn_prompt` now labels `checkpoint` and `divergence` entries explicitly instead of falling into the `Agent "{origin_agent}"` branch. Was: open
**Source:** review
**Theme:** Agents & runners
**Related:** F409's R2, which read `format_turn_prompt` line by line and found this.

**What happens.** `format_turn_prompt` (`hub/hub/inbound_queue.py:101-130`) labels a block
`Operator` for `operator`, `Scheduled job` for `job`, and `f'Agent "{entry.origin_agent}"'` for
anything else. `new_entry` forbids `origin_agent` on every origin except `agent` (`:45-46`), so the
`checkpoint` entries (`checkpoint_cutover.py:133-141`, `checkpoint_trigger.py:240-248`) and the
`divergence` entry (`run_divergence.py:259-268`) are always stored with `origin_agent=None`. The
agent reads `Agent "None" (hop 0):` above a checkpoint handed to a successor, above the Hub's
request for checkpoint notes, and above a divergence response. That credits Hub text to an agent
named "None". **Read, not driven.** No test asserts the label for these two origins (`grep` of
`hub/tests` for `format_turn_prompt` finds only `operator`, `agent` and `job` rows).

**FIXED 2026-09-24 (Round 6):** `hub/hub/inbound_queue.py`'s `format_turn_prompt` gained two more
`elif` branches before the catch-all: `entry.origin_type == "checkpoint"` renders `Checkpoint`,
`entry.origin_type == "divergence"` renders `Divergence`. The catch-all (`f'Agent "{entry.origin_agent}"'`)
is now reached only by `origin_type == "agent"`, the one origin `new_entry` requires `origin_agent`
for — so it can no longer see a `None`. Production path: `turn_scheduler.schedule_agent`
(`hub/hub/turn_scheduler.py:411`) calls `format_turn_prompt(selected)` on every entry a turn
delivers, including the `checkpoint` entries `checkpoint_cutover.cutover` and
`checkpoint_trigger.check_and_maybe_checkpoint` queue and the `divergence` entry
`run_divergence.queue_divergence_response` queues — none of the three pass `origin_agent`, so
before this fix every one of them rendered `Agent "None"`. Tests added to
`hub/tests/test_inbound_queue.py`: `test_checkpoint_and_divergence_origins_are_labelled_not_none`
(builds a `checkpoint` and a `divergence` entry via `new_entry` exactly as production does, with no
`origin_agent`, and asserts the formatted prompt contains no `"None"` and shows `Checkpoint (hop 0):`
/ `Divergence (hop 0):`) and `test_agent_to_agent_label_unchanged_by_checkpoint_divergence_fix`
(an `origin_type="agent"` entry still formats as `Agent "user" (hop 1):\npeer message`, byte for
byte). `py -3.11 -m pytest hub/tests/test_inbound_queue.py hub/tests/test_delivery_attempts.py
hub/tests/test_failed_run_returns_input.py -q` — 50 passed (the latter two import
`format_turn_prompt` too and were run because they import the changed module). `hub/hub/mcp_server.py`
was not touched. Not a spec-track change — no `openspec/specs/` promise describes these labels.

---

## F411 (B) -- the Jobs page's Run button discards the Hub's answer, so a declined Run shows the operator nothing

**Status:** fixed 8937006 (2026-10-11 night, Tier 0). `JobsPage` routes Run through `handleRun`, which sets the same alert Archive uses (`actionError`, `errorDetail` with a per-action fallback and a string-only `detail`); bundle rebuilt and committed with the source. Test `hub/ui/src/__tests__/jobRunRefusal.test.tsx` (3, failed before the fix); browser drive `scripts/drive/d1011_f411_run_refusal_ui.py` 7/7: an agent with no runner bound, Run answers 500 and the page shows "No runner is bound to this agent...".
**Source:** review
**Theme:** Operator surfaces
**Related:** F400, F373, F127, F48. Found by D-2b's R1 on 2026-09-23 (day window), while reading
who consumes the sentences F400 and F373 are about.

**What happens.** `JobCard`'s Run button (`hub/ui/src/components/jobs/JobCard.tsx:482`) calls
`onRun(job.id)`. `JobsPage` passes `onRun={runJob.mutate}` (`hub/ui/src/components/jobs/JobsPage.tsx:157`)
with no `onError`. `useRunJob` (`hub/ui/src/api/jobs.ts:247-257`) has no `onError` either, and the
`QueryClient` (`hub/ui/src/main.tsx:8-15`) has no `MutationCache` handler. So every non-2xx answer
from `POST /jobs/{id}/run` is dropped: the 409 that names the busy agent, the empty queue, the hold,
or the in-flight work, and the 500 as well. The operator presses Run and nothing visible happens.
Archive, on the same page, does surface its refusal (`errorDetail`, `JobsPage.tsx:18-25, 50`), so the
pattern exists one handler away.

`agent-loops`' *"Pressing Run on a loop that declines names why it declined"* requires the Hub to
**answer** with the reason, and the route does. But the only reader of that sentence today is an
agent calling MCP `run_job` (`hub/hub/mcp_server.py:929-937`) or a raw API client. Every round spent
making the 409 true (F48, F127, F369, F373, F400) has been spent on text the operator's own button
never displays.

**Read, not driven.** No UI test covers a failed Run (`grep` of `hub/ui/src/__tests__` for
`useRunJob` finds only `jobSchedulePresentation.test.tsx:32`, which stubs it idle).

**Why it is not in F400's change.** That change (`pressing-run-names-the-reason-that-held`) is
route-only. This fix needs a UI bundle refresh, and today's first spec loop
(`an-at-mention-an-agent-wrote-reads-no-file`) already rebuilds the bundle. The day playbook forbids
two same-day proposals sharing a file. That change's Open Question 1 offers folding this in.

---

## F412 (B) -- pressing Run answers `200 {"success": true}` when no turn began

**Status:** fixed 5f46cb6 (2026-10-11 night, Tier 0). `_do_fire_job` now returns `False` when `schedule_agent` reports a terminal failure, after still emitting its events and starting extra selections; the route's existing failed-row branch answers 500 with the row's reason. Which reasons are terminal was not decided: the row already called them failed, and the answer now agrees with it. F108's dishonest defaults stay open as their own item. Line numbers above are stale. Test `test_a_press_whose_turn_cannot_begin_is_not_answered_success` (fails with the return reverted); drive `scripts/drive/d1011_f412_run_answer.py` 7/7 (an agent with no runner bound: was 200).
**Source:** drive
**Theme:** Operator surfaces
**Related:** F108 (the class: a permanently refused request answering 200), F411, F400, F373. Found by
D-3b's R2 on 2026-09-23 (day window), measuring every way `run_job` can end.

**What happens.** `_do_fire_job` queues the entry and calls `schedule_agent`. Where the result is
`waiting_reason` with `terminal_failure` (`hub/hub/scheduler.py:3399-3406`), it marks the firing's
`JobRun` `failed` with that reason, commits, and **carries on to `return True`** (`:3440`). So
`run_job` (`hub/hub/api/v1/jobs.py:1372-1383`) takes its success branch and answers
`200 {"success": true, "job_id": …, "run_id": …}`. The row it names reads `failed`.

**Measured** (route, `schedule_agent` patched to return
`ScheduleResult(waiting_reason="r2 probe: runner refused", terminal_failure=True)`; probe
`scripts/drive/d2b_0923_run_answer_probe.py`, `test_r2_a_terminal_schedule_failure`):

```
POST /jobs/job-busy-r2term/run -> 200 {"success":true,"job_id":"job-busy-r2term","run_id":"run-b21d515e223f"}
JobRun rows: [("failed", "r2 probe: runner refused")]
```

An agent calling MCP `run_job` is told the job fired. The operator's Run button shows nothing either
way (F411).

**Why it is not in `pressing-run-names-the-reason-that-held`.** That change edits only the route's
`not success` branch. This needs either the firing to return `False` here or the route to read the
row on success, and `terminal_failure` has known dishonest defaults (F108's section: six early
returns claim it without meaning it), so which reasons are truly terminal needs its own look first.
That change's Open Question 3 offers folding it in.

## F413 (B) -- a firing that fails with no row left behind is invisible, and Run calls it "nothing is wrong"

**Status:** fixed 2026-10-13 (Tier 0, night iteration 17): `_do_fire_job`'s `except` builds a `failed` `JobRun` (with its `job_run_failed` event) wherever the firing has no row in the session -- raised before building one, or after discarding it as a decline -- so a press answers 500 with the reason through `run_job`'s existing D3 read, and a cron crash is visible. A crash recurring with the same summary counts into the newest `failed` row (`_stall_run_to_increment(..., status="failed")`), one event, no new rows. The staged-edit announcement after a failure no longer raises out of the handler. Five tests in `test_pressing_run_names_the_reason.py` failed first (incl. 1.12, which encoded the no-row behaviour), pass now. Drive: the D-2b probe's r3raise/r3busy/r3disc now answer `500 "r3 probe: ..."`, each with one `failed` row the event names; r3tick unchanged (409). Not driven against a live Hub.
**Source:** drive
**Theme:** Operator surfaces
**Related:** F373, F412, F23. Found by D-4b's R3 of `pressing-run-names-the-reason-that-held` on
2026-09-23 (day window), measuring what `run_job` answers when `_do_fire_job` raises.

**What happens.** `_do_fire_job` has one `try`. Its `except` (`hub/hub/scheduler.py:3442-3465`) marks
`run` failed and persists `job_run_failed` only `if "run" in locals()`. Two ways out leave no row:

1. **Raised before `run` exists** (`:2942-2998`: the resume lookup, the loop read, the busy guard).
   Nothing is written and no event is persisted. The failure exists only in the Hub's log. On the cron
   path the product shows nothing at all.
2. **Raised after `run` was discarded.** The in-flight and counted-stall branches call
   `_discard_unused_run` and commit, then emit the staged loop edit (`:3202-3203`, `:3236-3237`). If
   that raises, `run` is still a local, so the `except` persists a `job_run_failed` event naming a
   run id that does not exist, and sets `failed` on an object no longer in the database.

Because nothing was written, `run_job` cannot tell either from a healthy decline that also wrote
nothing. It re-decides the loop and answers with that decision.

**Measured** (route; probe `scripts/drive/d2b_0923_run_answer_probe.py`, R3 cases):

```
r3raise  flow, work in flight, resume lookup raises
         -> 409 "Every task on this loop's queue is already being worked. Nothing was started, and nothing is wrong ..."
         rows=[]  job_run_failed=[]
r3busy   documentless loop, owner mid-turn, resume lookup raises (before the firing's own guard)
         -> 409 "probe-owner is already running a turn, and no other agent is free ..."
         rows=[]  job_run_failed=[]
r3disc   flow, work in flight, a staged loop edit whose audit emit raises
         -> 409 "... already being worked. Nothing was started, and nothing is wrong ..."
         rows=[]  job_run_failed=[{... 'run_id': 'run-a0d474043a0d', 'error_summary': 'r3 probe: edit audit failed'}]
```

In `r3disc` the event log says the firing failed, names a run that does not exist, and the route says
nothing is wrong.

**Repair sketch (unverified).** Make every failed firing leave a `failed` row: where the `except`
finds no `run` in the session (never built, or discarded), build one. Then
`pressing-run-names-the-reason-that-held`'s D3 ("the row this press wrote is its answer, whatever
its status") answers all three cases as 500 with the reason, with no further route edit. Needs its
own look at a crash that recurs every tick: the rows would count against `_prune_job_history`'s
100-row window, which is why the healthy declines record nothing. Counting into a matching `failed`
row, as a stall does, is one answer.

**Why it is not in that change.** It changes what the firing writes, which that change's non-goals
exclude. It also changes the cron path, not just the route. That change's Open Question 4 offers
folding it in.

## F414 (B) — `create_loop` with `initial_tasks` still commits the loop and job before a task can be refused

**Status:** fixed (this commit) [Round 4, 2026-09-23] — every `initial_tasks` entry is checked before the job is committed; see FIXED at the end of this entry. Was: open. Filed 2026-09-23 by the adversarial review of Round 3 (read from the source, not
driven). F265's repair (Round 3b) refuses the *authorisation* failure before any row is written, but
`hub/hub/api/v1/jobs.py:700-755` still commits the job and loop, enabled, and then creates each
initial task through `create_task_for_actor`, which can refuse per task: `guard_entry_status` on the
body's status and `resolve_identifiers` (422 for an unknown requirement id, `tasks.py:~731-748`).
Tasks are committed one at a time, so a refusal on the second leaves the first. The comment there
("the F265 check above already refused every caller it would refuse") holds only for the
authorisation gate, and D2's "validated up front" covers only the schema. The same half-created loop
F265 described, through a different refusal. Repair shape: validate every initial task (status,
identifiers) before the first commit, or create the job, loop and tasks in one transaction.

**FIXED 2026-09-23 (interactive session, Round 4, group 4e).** The first repair shape. `tasks.py` has
a new `check_task_create(session, project_id, body)` that runs every refusal a create makes from its
body (`resolve_identifiers`, and an id already on the board) without writing anything.
`create_task_for_actor` calls it in place of its own inline resolution, so the two cannot drift, and
its docstring says a new refusal belongs there. `create_job` calls `_check_initial_tasks` inside the
loop branch, before the job row, and that also refuses two entries naming the same id. Every refusal
names the entry (`initial_tasks[1] ('Second task'): ...`) and ends "Nothing was created." The schema
refusal's detail does too. **Correction to this entry:** the entry-status half never half-created.
`TaskCreate`'s own validator refuses a non-entry status at D2's up-front parse, as a 422, before any
row exists; `guard_entry_status` inside `create_task_for_actor` could not fire for an initial task.
Measured, not argued: `hub/tests/test_a_refused_initial_task_leaves_no_loop.py` puts the refused task
*second*. On the old code the unknown-requirement, duplicate-id and id-already-taken cases each left
a job, a loop and the first task (1/1/1, and 1/1/2 over the pre-existing task), and the recovery case
counted two jobs. The status case answered 422 with nothing written, but without naming the entry. On
the new code all six pass. Residual, not fixed: the job and loop are still two commits, so a lost race
for the spec document between `_check_spec_document_conflict` and the loop's commit still leaves the
job. The pre-check makes this a race only, as it was before.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The `create_job` comment claimed none of `create_task_for_actor`'s refusals could fire after
the commit. It now says what remains: a race between the checks and the commit (a task id taken
meanwhile, or the calling agent archived mid-call, which `agent_archivable` makes unlikely while
its run is live).

## F415 (C) — `operator` is not a reserved agent name, and Round 3a gave it a meaning

**Status:** fixed (this commit) [Round 4, 2026-09-23] — `operator` is reserved beside `user` in the Hub and the CLI; see FIXED at the end of this entry. Was: open. Filed 2026-09-23 by the adversarial review of Round 3. F261's repair (Round 3a) made
`"operator"` the runless sender of `POST /messages` and skips it in `GET /agents`' activity fallback and
`GET /status`'s `agents_active`. `validate_agent_name` (`worktrees.py`) reserves only `user`, so an agent
can be named `operator`: it would be hidden from the roster fallback and the active count, and its
messages would collide with `OPERATOR_SENDER`. Repair shape: reserve `operator` beside `user` in
`validate_agent_name` and `AGENT_NAME_RE`'s callers (CLAUDE.md: the CLI and Hub restatements change
together), with a refusal naming why.

**FIXED 2026-09-23 (interactive session, Round 4, group 4e).** `hub/hub/worktrees.py` has
`_RESERVED_AGENT_NAMES`, a map from each reserved name to why it is reserved. `validate_agent_name`
now refuses `operator` (compared case-insensitively, as `user` was) with `reserved agent name
'operator': the Hub sends the operator's own messages as 'operator' and leaves that name out of the
agent roster; choose another name`. A malformed name gets its own message, no longer "invalid or
reserved". The CLI's `RESERVED_AGENT_NAMES` (`src/agentweave/constants.py`) adds `operator`, and
CLAUDE.md's agent-name rule names both restatements. This reaches every route that already called
`validate_agent_name`: session sync, `POST /agents/register`, `request_agent`, the trigger and
worktree routes. No existing agent is stranded: a read-only query of `:8000`'s and the trial Hub's
databases found no agent named `operator` or `user`.
`hub/tests/test_operator_is_a_reserved_agent_name.py`: on the old code, session sync and
`/agents/register` accepted `operator` (200) and `validate_agent_name` did not raise. A fifth test
compares the CLI's set, read from its source with `ast`, to the Hub's. Every one of these passes on
the new code. `test_the_evidence_names_the_author.py`'s 4.5 test rostered an agent named `operator`
through session sync to make the `actor_kind` filter observable. It now inserts that agent as a row
created before this change, the only way one can exist now, and still fails with the filter dropped
(checked: `{'operator'} == set()`). CLI `tests/test_config.py` refuses `operator` in `agentweave.yml`.

**Review follow-up 2026-09-23 (adversarial Opus review of Round 4).** The first repair missed `POST /agents`, the Add-agent dialog's own route. It checked only the
name pattern, and the review created `operator`, `Operator` and `user` through it (201 each), agents
that could then never run a turn. `create_operator_agent` now calls `validate_agent_name` first
and answers a 400 with the sentence. It is a 400 rather than a validator's 422 because the dialog
renders `detail` as text. `test_the_create_dialog_route_refuses_a_reserved_name` fails on the
previous commit (the agents were created) and passes now.

## F416 (C) — `list_evidence` ignores `document` when no `identifier` is given

**Status:** fixed (this commit) [Round 6, 2026-09-24] — `list_evidence_for_agent` now filters by
the named document's requirements when `document` is given without `identifier`. Was: open. Filed
2026-09-24 (daily review, operator-accepted), surfaced by the B12 R1 round…

while re-verifying F363. `GET /spec/evidence` (`hub/hub/api/v1/agent_actions.py`,
`list_evidence_for_agent`) reads `document` only inside the `if identifier:` branch, where it
disambiguates the requirement. With no `identifier`, the query is scoped to the whole project and
`document` is silently dropped. An agent that passes a document id to see that document's evidence
gets every document's evidence and a 200, so the call "succeeds" by not doing what it was asked.
Repair shape: filter by the document's requirements when `document` is given alone (or refuse it with
a sentence), plus a test that a two-document project returns only the named document's rows.

**FIXED 2026-09-24 (Round 6):** `hub/hub/api/v1/agent_actions.py` —
`list_evidence_for_agent` (`GET /agent-actions/spec/evidence`) gains an `elif document:` branch
between the existing `identifier` and whole-project branches: it resolves `document` (a path) to a
`SpecDocument` via `spec_lifecycle.get_document` — 404 if none — then joins `RequirementEvidence` to
`SpecRequirement` on `requirement_id` and filters on `SpecRequirement.document_id == document_row.id`
(plus `RequirementEvidence.project_id`, matching the other two branches' scoping). `identifier`
still wins when both are given, unchanged. **`hub/hub/mcp_server.py` was not touched** — its
`list_evidence` tool already forwards `document` (or `None`) as a query param unconditionally
(`hub/hub/mcp_server.py:1988-2009`), so no MCP-side change was needed for the fix to reach it; the
bug was entirely in the route the tool calls, not in the tool itself. **Production path:** the MCP
tool `list_evidence` → `_hub_request("GET", "/spec/evidence", params={..., "document": ...})` → the
Hub's agent-bound router mounts this at `/api/v1/agent-actions/spec/evidence` →
`list_evidence_for_agent`, which is the function changed. Verified by calling the route directly
with the exact parameter shape the MCP tool sends (`identifier`, `document`, `review_state`, all
optionally `None`/absent). **Aside, not fixed here (out of scope for F416, which names only the
agent route):** `hub/hub/api/v1/spec.py`'s operator-facing `list_evidence` (`GET
/projects/{id}/spec/evidence`, lines 863-889) has the identical defect — `document` is read only
inside `if identifier:` there too — but F416 as filed and as scoped by this round's brief covers
only `list_evidence_for_agent`; the operator route is a separate finding if the operator wants it
tracked. **Tests:** `hub/tests/test_agent_evidence_plane.py` —
`test_reading_narrowed_to_a_document_alone_excludes_the_other_document` (new: two documents, each
declaring its own `FR-1`, with evidence recorded against each; `document` alone on each returns only
that document's row) and `test_reading_narrowed_to_an_unknown_document_is_refused` (new: 404 for an
unknown path, matching `_resolve_requirement`'s existing behaviour for the `identifier` case).
16/16 in `test_agent_evidence_plane.py`, plus 313/313 across every other test file that touches
evidence, requirements, task integration/release, or the MCP surface
(`test_approval_refuses_unaccepted_evidence.py`, `test_conflict_refusal_names_what_clears_it.py`,
`test_duplicate_evidence.py`, `test_evidence_footprint_root.py`,
`test_evidence_latest_review_signal.py`, `test_evidence_restamp.py`, `test_loop_lands_its_work.py`,
`test_requirement_coverage.py`, `test_requirement_drift.py`, `test_requirement_evidence.py`,
`test_requirement_gate.py`, `test_task_integration.py`, `test_task_rejected_evidence_signal.py`,
`test_task_release.py`, `test_the_evidence_names_the_author.py`, `test_mcp_server.py`,
`test_mcp_adapter_online.py`), all green.

**Review addendum 2026-09-24 (Round 6 Opus review):** the MCP tool's docstring
(`hub/hub/mcp_server.py` `list_evidence`, "Only needed when the same identifier exists in more than
one document") is now stale, since `document` alone narrows the list. Left for when `mcp_server.py`
edits are allowed again, after `an-agents-tool-server-is-the-one-its-hub-loaded` lands and `:8000`
restarts.

## F418 (C) — the loop tab fetches the loop's event history and shows none of it

**Status:** fixed `ba1027e` (2026-10-10, Tier 1 loop-history page, F570). Ledger closed 2026-10-12 night: `LoopTab.tsx:487` renders `loop.events` as a History section (`data-testid="loop-tab-events"`); `hub/ui/src/__tests__/loopHistory.test.tsx` 3 passed. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B10 rounds.
`LoopTab` reads `LoopDetail.events`, the loop's audit trail, and renders none of it. Once B10's
`a-loop-is-stopped-archived-and-delegated-from-its-own-tab` writes `loop_stopped` / `loop_archived`
against the loop, those rows are readable only through the API. Repair shape: a short history list in
the loop tab (newest first, from the field already fetched), or stop fetching it.

## F419 (B) — the Overview tab's activity strip shows every project's events, and its warning dot never fires for the Hub's warnings

**Status:** fixed 61f9bc1 (2026-10-11 night, Tier 0). `OverviewPage.tsx` filters the buffer by `data.project_id === selectedProjectId` as `ActivityLog.tsx` does, and tests `severity === 'warn'`. Tests `overviewActivityStrip.test.tsx` (3; all failed before); drive `scripts/drive/d1011_f419_overview_strip.py` 12/12 in a real browser with two projects. Not fixed, observed: the strip re-reads the buffer only when the agents/tasks/questions queries move (the page's own comment says so), so an event alone does not repaint it. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B9 rounds
(`spec-queue/tracks/B9.md` Final) and re-checked in session. `components/overview/OverviewPage.tsx:101`
renders `getBufferedEvents().slice(-10)`, the instance-wide buffer the operator stream fills
(`useSSE.ts`), with no `project_id` filter, on a single project's Overview tab. It is the only live
consumer without `ActivityLog`'s filter, and `agent_output` chunks from any project will usually fill
all ten pills. Its amber dot tests `event.severity === 'warning'` (`:209`), but the Hub writes
`"warn"` (21 `severity="warn"` sites in `hub/hub`), so only `context_warning` ever shows amber. It gets
more visible once B9's F251 lets 18 more event kinds through and F253 adds `stream_gap` (`"warn"`).
Repair shape: filter by the page's project id (as `ActivityLog` does) and test `"warn"`, and add a test
that fails if a foreign project's event reaches the strip.

## F420 (B) — the checkpoint and probe worker runs `claude -p` with every default tool enabled, on untrusted transcript text

**Status:** fixed (this commit) [Round 6, 2026-09-24] — the Claude worker argv now carries `--tools ""`, pinned whole in a test. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B7 rounds (`spec-queue/tracks/B7.md` Final); re-checked in session. `build_worker_command` (`hub/hub/worker.py:120-146`)
builds `claude --output-format json [--model M] -p <prompt>` for Claude, with no `--tools ""`, while
Codex gets `--ephemeral --sandbox read-only`. The prompt carries conversation transcript text, which
is untrusted: anything an agent read or a user pasted can steer a worker that holds the default tool
set. F195 closed this same gap for the titler. Repair shape: pass `--tools ""` (as the titler does)
for every JSON-mode worker call, with a test that fails if the flag is dropped.

**FIXED 2026-09-24 (Round 6):** `hub/hub/worker.py` `build_worker_command` now builds
`claude --tools "" --output-format json [--model M] -p <prompt>` — the same `[cli, "--tools", ""]`
head `conversation_titles.build_title_command` uses since F195; Codex is unchanged
(`--ephemeral --sandbox read-only`). Neither worker prompt needs a tool: `_GENERATION_PROMPT` and
`_PROBE_PROMPT` (`checkpoint_generation.py`) each ask only for a JSON object written from the text
they carry. Production path: `generate_checkpoint` → `run_worker(kind="checkpoint")` and
`probe_checkpoint` → `run_worker(kind="checkpoint_probe")` → `build_worker_command` → `_run_worker_process`.
Live check (Haiku, temp directory, the exact argv through `resolve_executable`): exit 0, envelope
parsed, and asked to list its tools the model named no built-in tool. **Residual, not fixed here:**
it still listed the account's claude.ai connector tools (`mcp__claude_ai_Claude_Docs__*`), which
`--tools ""` does not remove — the titler shares this; a candidate finding. Tests:
`hub/tests/test_worker.py::test_the_claude_command_asks_for_json_and_is_not_an_agent_turn` pins the
whole argv with and without a model.

## F421 (B) — an `unwritten` checkpoint becomes the next checkpoint's anchor

**Status:** fixed (Tier 0, 2026-10-07) -- `latest_checkpoint` skips `unwritten` rows, so the next checkpoint anchors on the last written one and covers the failed span. `latest_checkpoint_for_loop` left unfiltered on purpose: the loop briefing renders the envelope (`render_checkpoint`), which an `unwritten` checkpoint still carries and which is the newest. Test: `test_checkpoint_record.py::test_an_unwritten_checkpoint_is_not_the_next_ones_anchor` (anchored on the unwritten one before). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B7 rounds (`spec-queue/tracks/B7.md` Final); re-checked in session. `latest_checkpoint` (`hub/hub/checkpoints.py:95-108`)
orders by `sequence` with no status filter, so a checkpoint whose generation failed or timed out
(`unwritten`) anchors the next one. The next transcript starts at the unwritten checkpoint's
`created_at` with no predecessor body, and the failed span drops out of the chain. `latest_checkpoint_for_loop`
also briefs from it. Any worker timeout or failure does this today. Repair shape: anchor on the latest
*written* checkpoint (or read through an unwritten one, as F130's fix did for an empty span), with a
test over a chain holding an unwritten middle checkpoint.

## F422 (C) — the titler pays again for the same title after every turn

**Status:** fixed (this commit) [Round 6, 2026-09-24] — a conversation already titled from the same excerpt is skipped before any runner is resolved or spawned. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B7 rounds (`spec-queue/tracks/B7.md` Final). `generate_conversation_title` (`hub/hub/conversation_titles.py:175-233`)
checks only `title_set_by_operator` and the mode, and is called at `agent_trigger.py:2630` and `:3219`
on the same excerpt after each turn. Each call is a billed model invocation producing the title the
conversation already has. Repair shape: skip when a generated title exists and the excerpt it was made
from has not changed (or title once per conversation unless asked), with a test counting invocations.

**FIXED 2026-09-24 (Round 6):** `hub/hub/conversation_titles.py`. The `conversation_titled` event
`generate_conversation_title` already writes now also carries `excerpt_digest` (sha256 of the
excerpt the title was made from); before resolving a runner, the function reads the latest
`conversation_titled` event for this conversation (`EventLog.data["conversation_id"]`, same project)
and returns None with no spawn when its digest equals the current excerpt's. No migration: the
event log is never pruned. Why it re-titled: both callers — `agent_trigger.py` `_execute_run`
(:2630) and `_execute_codex_appserver_run` (:3219), via `maybe_generate_title` — run after
every completed turn, and `_excerpt` reads only the first message and first text reply, so the input
is fixed after turn one. No legitimate retitle path exists (spec `conversation-lifecycle`: generation
"SHALL run after the agent's first response", replaces only a non-operator title; the only other
title writer is the operator rename). The digest, rather than "any generated title", keeps one real
case: a first turn with no text reply is titled from the opening message alone, and the reply a later
turn writes earns exactly one more call. A failed generation writes no event, so it is retried next
turn; a conversation titled before this fix (event without a digest) is titled once more, then stops.
Consistent with `worker-spend-counts-against-the-budget` D4: the skip sits before runner resolution,
so it is not one of the "exits after the runner is resolved" that change records, and D4's
"one row per turn" note becomes one row per distinct excerpt. Tests (`hub/tests/test_title_generation.py`):
`test_a_second_turn_on_a_titled_conversation_makes_no_model_call` (three `maybe_generate_title`
calls, one spawn), `test_a_first_reply_arriving_later_is_worth_one_more_title`,
`test_a_failed_generation_is_retried_on_the_next_turn`,
`test_another_conversations_title_does_not_count_as_this_ones`; the first, second and fourth fail on
the pre-fix code.

**Review addendum 2026-09-24 (Round 6 Opus review):** the digest guard alone did not hold,
because `_excerpt` ordered the first reply by `AgentOutput.sequence`, which restarts at 0 on every run
(measured read-only on `:8000`: 73 of 85 multi-run conversations had a later run's text sorting
first, so 114 of 307 text turns would still have paid). Fixed in the same round: the reply is ordered
by `timestamp`, then `sequence`, then `id`, and
`test_a_later_runs_text_does_not_become_the_first_reply` fails on the previous ordering. Residuals, LOW:
two turns finishing within one titling spawn can both pass the check before the event is written and
pay twice; the lookup scans the project's event log through `ix_event_logs_project_ts` (about 16k
rows on `:8000`, roughly 1 ms today, and growing).

## F423 (C) — a declined handover's note never reaches that task's reviewer

**Status:** fixed (Tier 0, 2026-10-13, night iteration 18): a note is tied to its task by `checkpoints.notes_about_task` (its run is in the task's transition history, or the queue entry that started its conversation named the task; derived, no migration). `consider_handover` takes only the completed task's note, and the review briefing (`_compose_loop_briefing`) carries the task's still-unconsumed note under "What the author left for you". Tests `hub/tests/test_handover_briefs_the_reviewer.py` (3 new, all failed before; 1132 passed across 41 checkpoint/briefing files). Not driven against a live Hub or a real reviewer turn; the briefing composer and handover were run on the real schema. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B7 rounds (`spec-queue/tracks/B7.md` Final) (found by R3). `_briefing_checkpoint` falls back to the loop's latest
checkpoint; later, `_authors_pending_note` carries only the author's newest note, possibly into a
later task's checkpoint. So the note written for a declined handover can land beside the wrong task, or
nowhere. Today this happens when no checkpoint runner is set; with B7's
`worker-spend-counts-against-the-budget` (D7.1) it also happens at budget exhaustion. Repair shape:
key the pending note to its task and deliver it with that task's review briefing.

## F424 (B) — when the approval gate's git calls raise, every approval surface answers a bare 500

**Status:** fixed (Tier 0, 2026-10-08, `e152b0c`): `task_transition_service.evaluate_approval` turns `TimeoutExpired`/`OSError` from the gate into `GitUnavailableError` (409, "The Hub could not ask git whether this task's work would merge (...), so it was not approved"); the transition and the land route (which called `evaluate` directly) both ask through it (`hub/tests/test_a_git_that_cannot_be_asked_refuses_approval.py`, 3 red before). Not driven: a missing project directory makes the gate skip git rather than raise, so only fault injection at `_git` reaches it. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B5 rounds (`spec-queue/tracks/B5.md` Final); re-checked in session. `task_integration._git`
(`hub/hub/task_integration.py:136-145`) is a bare `subprocess.run(..., timeout=60, check=False)`, and
`is_repository`, `branch_exists`, `task_branch_tip` and `would_conflict` all call it from the gate's
`evaluate`. A `TimeoutExpired` or `OSError` is not a `TransitionRefusedError` or `TaskBindingError`,
the only kinds the app maps (`main.py:532-553`). So operator `PATCH /tasks/{id}`, the agent plane and
MCP answer 500 after up to a minute per call, with nothing committed. **Recommended repair (operator,
2026-09-24): refuse the approval with a stated "could not ask git: <reason>" refusal.** The gate
exists so that nothing is approved that might not merge, and the operator can retry. Add a test that
patches `_git` to raise `TimeoutExpired` and asserts a refusal, not a 500, on each surface.

## F425 (B) — a read-only agent assigned a writing task writes into the operator's checkout

**Status:** fixed 2026-10-07 by `a-read-only-agent-holds-no-task-work` (Tier 1, authored and approved in the app on `:8010`, `spdoc-e7299e2e30ce`): one predicate (`launchability.is_read_only_agent`) at four doors -- the dispatch refuses a read-only agent's task-work turn before any workspace (409, request-level, the guarantee); task create and a PATCH outside a review status refuse it as assignee (422); its run's claim is refused (403); a flow's ordinary-work pick skips it (pool and job default), the reviewer ladder does not. Tests: `hub/tests/test_a_read_only_agent_holds_no_task_work.py` (7 of 10 failed on HEAD; 3 controls). Driven on `:8010` (`d1007_read_only_drive.py`, real Haiku): 1/6 before -- the turn started and wrote `NOTES.md` into the project's checkout -- 6/6 after. Reconciled into `run-task-binding` (`reconcile_f425.py`). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B5 rounds (`spec-queue/tracks/B5.md` Final); re-checked in session. `takes_task_workspace`
(`hub/hub/worktrees.py:763-773`) returns True only for a writing agent, so a `read_only` agent's turn
on a task runs in the shared (operator's) checkout, and nothing snapshots a turn that is not isolated.
Nothing in the app sets `read_only` today, so it is reachable through the API and `POST
/agents/register` only. Recommended repair: refuse to assign a writing task to a read-only agent (or
refuse the setting when the app ever offers it). B5's `isolation-does-not-change-under-held-work`
covers only the setting *changing* under held work, not this case.

**Re-verified 2026-09-24 (Round 6), handed on as a spec track, not fixed.** The launch path
(`agent_trigger.py` → `worktrees.resolve_turn_workspace`; `takes_task_workspace` requires
`is_writing_agent`) gives a `read_only` agent's task-bound turn the project directory, and
`read_only` drives no runner flag or sandbox, so the finding stands. But
`agent-run-sandboxing` already names a read-only agent's run as working in the project
directory, and `operator-agent-creation` scopes the checkout promise to a writing agent, so no
spec is violated. The recommended repair is a new `run-task-binding` requirement, "A read-only
agent does not hold a task's work": refuse a work assignment or binding to a `read_only` agent
in one service function every assigning door calls; keep review bindings; grandfather held work.
Collides with `isolation-does-not-change-under-held-work`, which touches `read_only`.

## F426 (B) — an evidence decision whose merge then fails answers a bare 500 after the decision is saved

**Status:** fixed 6268b0e (unit tests only; the merge-failure 500 was NOT driven live); **carried by B5's `evidence-is-decided-after-the-run-that-recorded-it` (its D6),
approved 2026-09-24.** Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B5 rounds (`spec-queue/tracks/B5.md` Final); measured by R3. With an approved task waiting and `retry_integration`
raising, the wrapper rolls back (`task_integration.py:702-707`), which expires every loaded row. The
route then reads `evidence`/`review` to build its answer and raises `MissingGreenlet` (`spec.py:926`
→ `:1110`): a bare 500, with the decision already committed (`accepted`). The agent plane
(`agent_actions.py:1354-1357`) fails the same way. The repair is to build both routes' responses
before integrating. The test's stub must load the task through the session, or it opens no transaction
and passes today.

## F427 (B) — a footprint watches the whole tree, so one commit raises a drift candidate for every piece of evidence

**Status:** fixed (Tier 2, `drift-watches-the-files-its-evidence-is-about`, `c954bb9`, 2026-10-07) -- a footprint watches the files its evidence is about (locator words in the tree, the named commit, or the branch's changes), not the whole tree; an unrelated commit raises nothing (leg 1). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 1). Measured by R1: evidence on `ledger.py`, then a commit to `other.py`, gave one candidate. The footprint's `entries` hold the whole tree (`requirement_evidence.py:539`, `:969`). **Carried by B6's `drift-watches-the-files-its-evidence-is-about`** (approved 2026-09-24).


## F428 (C) — rejecting a proposal in the app leaves it on screen

**Status:** fixed 2f120b4 (`a-pending-proposal-can-be-withdrawn`, 2026-09-30: reject broadcasts and the decision invalidates the proposals list, so every open window drops the row; driven with a Haiku agent and two browser windows on `:8038`). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 2). There is no broadcast, and the mutation invalidates nothing (`spec.py:669-694`, `api/spec.ts:244-256`). **Carried by B6's `a-pending-proposal-can-be-withdrawn`.**


## F429 (C) — the app records every rigor change with an empty reason

**Status:** fixed 536b6d8 (`a-documents-rigor-history-and-retired-requirements-are-on-screen`, 2026-09-30: a rigor change is confirmed inline with a reason box; lowering it cannot be confirmed without one, and the reason is recorded and shown in the history). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 3). `SpecPhaseBar.tsx:62-70` sends an empty reason, but the spec requires the reason to be recorded. **Carried by B6's `a-documents-rigor-history-and-retired-requirements-are-on-screen`.**


## F430 (B) — a drift candidate can be answered twice, and the second answer overwrites the first

**Status:** fixed (Tier 1, `drift-is-scanned-and-answered-on-the-document`, `0cf3a60`, 2026-10-07) -- a second answer is refused 409 `drift_not_open`. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 4). `resolve_drift` has no state check. **Carried by B6's `drift-is-scanned-and-answered-on-the-document`** (it answers once; a second answer is a 409).


## F431 (C) — an accept refused as stale commits `stale` and leaves the row on screen

**Status:** fixed 2f120b4 (`a-pending-proposal-can-be-withdrawn`, 2026-09-30: accept broadcasts after its stale-refusal commit and the decision invalidates the list on settle; driven with a Haiku agent and two browser windows on `:8038`). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 9). Found by R2 (`spec.py:642-649`). **Carried by B6's `a-pending-proposal-can-be-withdrawn`.**


## F432 (C) — evidence with no footprint row is never scanned and never reported

**Status:** fixed (Tier 2, `drift-watches-the-files-its-evidence-is-about`, `c954bb9`, 2026-10-07) -- evidence with no footprint is listed as `no_footprint` in `GET /spec/drift`'s `unwatched`. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 10). Found by R2. **Carried by B6's `drift-watches-the-files-its-evidence-is-about`** (listed as unwatched, reason `no_footprint`).


## F434 (B) — reindex and arrange write files before the database commit, so an `OSError` leaves files written and digests rolled back

**Status:** fixed (Tier 1, carried by `the-corpus-is-indexed-arranged-and-adopted-from-the-app` D6, `8d6e5bb`, 2026-10-07) -- `write_index` is atomic (temp file + `os.replace`); reindex answers 200 with `index_write_failed` and still commits the requirement index; a document's failed re-render is a `write_failed` skip; arrange refuses with a sentence before placing anything. Tests: `test_spec_index_writer.py` (four failed on HEAD). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 6). `spec.py:1255-1265`, `:1375-1379`. Not carried. Repair shape: write after the commit, or delete what was written on failure, answering a sentence and not a bare 500.


## F435 (C) — a drift candidate is never superseded when its requirement is reworded, although the model says it is

**Status:** fixed (Tier 0, 2026-10-08, `d801def`): `spec_index.reindex_document` sets open drift candidates of a reworded or retired requirement to `superseded`; `GET /spec/drift` accepts that state (`hub/tests/test_a_reworded_requirement_supersedes_its_drift.py`, 2 red before). Drive `scripts/drive/d1008_findings_drive.py f435`: `['candidate']` before, `['superseded']` after on `:8010`. Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 7). `models.py:2643-2644` documents supersession that no code performs. Not carried.


## F436 (B) — any drift answer silences that exact change forever, whether or not the answer was true

**Status:** fixed (Tier 1, `drift-is-scanned-and-answered-on-the-document`, `0cf3a60`, 2026-10-07) -- *Code corrected* stores no fingerprint, so the same change still there is asked again (driven). Was: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B6 rounds (`spec-queue/tracks/B6.md` Final, candidate 11). Found by R3. For example, pressing *Code corrected* before the code is actually reverted stops the candidate from ever returning (`requirement_evidence.py:1221`, `:1160-1163`). Not carried. B6's change 2 words its buttons as past-tense facts. Repair shape: re-check that the answer holds on the next scan, or scope the silence to the answered commit.

## F437 (B) — an operator's review request queued for a busy reviewer leaves a flow's completed task in the pool, so a second review can be staffed

**Status:** fixed 2026-10-07 by `a-flow-stages-its-review-in-the-dispatch` (D2, D4): a waiting review turn takes the task out of the pool (in flight, on a flow and on a documentless loop) and books its reviewer. Tests 1.13, 1.14, 1.7.


## F438 (C) — the holder check's "Let the review in flight finish" is false for a silent holder whose review ended without a verdict

**Status:** fixed 2026-10-12 (night iteration 27, Tier 0): `holder_refusal` (`agent_trigger.py`) writes the refusal once for both sites and says "Let the review in flight finish" only when `task_attendance(...).attends(task, holder)`; otherwise it says the holder has no turn running or queued on the task, so no review is in flight, and the remedy stays. Route test failed before (2), `d1012_f438_holder_refusal` 8/8 on a fresh source Hub. Earlier status: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B1 rounds (`spec-queue/tracks/B1.md` Final); found by R1. The sentence tells the operator to wait on a review that is no longer in flight. S13's option (ii) holder check changes who may be replaced; its wording should stop claiming a review is in flight when none is.


## F439 (C) — input in a closed conversation counts as queued, so after the attended change such a task reads as in flight

**Status:** fixed 2026-10-13 (night iteration 19, Tier 0): `task_attendance` (`run_task_binding.py`) leaves out queued input whose conversation is not open (the reason `_attempt_turn` answers "conversation is unavailable"), so such a task is no pair, not attended, and has no turn. Two tests in `test_a_task_is_attended_only_by_a_turn_that_will_reach_it.py` failed before (archived conversation read as `queued`), pass after; 933 passed across the 38 attendance/queue-status test files. Not driven on a live Hub. Earlier status: open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B1 rounds (`spec-queue/tracks/B1.md` Final); found by R1. The old seam, `turn_scheduler.py:344-350`, counted queued input in a closed conversation. Once `a-task-is-attended-only-by-a-turn-that-will-reach-it` lands, such a task would read as attended by a turn that can never reach it.


## F440 (B) — a decided task's queued review entry is never released; it is refused up to three times, then withdrawn

**Status:** fixed 2026-10-07 by `a-decided-task-withdraws-its-waiting-reviews` (authored and approved in the app on `:8010`, `spdoc-3b1585810681`): a verdict (approved, rejected, revision_needed; PATCH or land) withdraws the task's queued review entries in its own transaction and announces them. Driven on `:8010` (`d1007_verdict_withdraws_review.py`): 4/8 before (the entry stayed queued and was delivered into a refusal at the reviewer's run end), 8/8 after. Reconciled into `run-task-binding`.


## F441 (C) — after the attended change, Run can say "already being worked" for an idle assignee whose queued turn cannot start

**Status:** fixed 2026-10-13 (night window iteration 20, Tier 0). `_held_in_flight_reasons` (`hub/hub/api/v1/jobs.py`) now also names a spent project token budget (`_token_budget_holds`: the agent is idle, its queued turn carries no operator input, the budget is exhausted -- the scheduler's own refusal conditions). Test `hub/tests/test_run_names_a_spent_token_budget.py`: the budget case failed before ("already being worked ... nothing is wrong"), passes after; an operator's queued input is not named as held. The closed-conversation half is F439's: input in a non-open conversation no longer counts as attending, so such a task is not declined as in flight. Driven through the real `POST /jobs/{id}/run` route in-process, not on a live Hub.

**Earlier status:** open. Filed 2026-09-24 (daily review, operator-accepted), surfaced by the B1 rounds (`spec-queue/tracks/B1.md` Final); found by R2. Only a provider hold is qualified. A token-budget hold or a closed conversation also keeps the queued turn from starting, but the Run press would still report the task as being worked.


## F444 (B) — a worktree's shared dependency links make ordinary reads through them refused

**Status:** fixed 2026-10-19 (night window iteration 17, Tier 0). `_judge_resolved` (`hub/hub/mcp_server.py`) now reads a path beneath a shared dependency link as inside: `_in_shared_dependency` accepts `root/<name>` (`node_modules`, `.venv`, `venv`) when it is a link to a directory of the same name, and only for a path at or beneath that target. A `..` out of the link, a link to a directory of another name, and any other name stay outside. Not a *read*-through exemption as filed: the judge has no read/write classification (every path word is judged alike), so a write beneath the link is also inside; `npm install` already wrote through the link with no path word to judge. Test `hub/tests/test_a_shared_dependency_link_reads_as_inside_the_workspace.py`: 9 read rows red before, green after; the `..` and look-alike controls stay refused. Drive: a real git worktree with a junction as the link (this account cannot make the symlink, F22): `ls node_modules`, `grep -r foo --exclude-dir=node_modules .`, `grep foo *` refused before, allowed after; `cp n node_modules/../a.txt` refused both ways. Original filing: Filed 2026-09-24 (operator decision `B4-dep-links`), surfaced by B4's R4 and R5.
**Prerequisite for registering a JavaScript project** (noted 2026-10-04 when
`the-shell-judge-reads-a-word-whole` was archived, its task 4.1: that change extends these refusals to
globs and bare names through the links).
Task and agent worktrees link `node_modules`, `.venv` and `venv` to the project checkout, which is
outside the workspace. Paths through those links are refused by the shell judge today; B4's two
changes extend that to globs and bare names, so in a JavaScript worktree `ls *`, `grep foo *` and
`grep --exclude-dir=node_modules` would be refused. No worktree on this machine holds such a link
today. **Must be fixed before a JavaScript project is registered.** The repair shape (a read-through
exemption for the known shared-dependency links, or not linking them) is open.

## F446 (C) — a plain path word with a colon in a later component is refused on Windows

**Status:** fixed 2026-10-12 (night window iteration 6, Tier 0). Rule 5 (`_judge_word`, `hub/hub/mcp_server.py`) now divides a plain word at its colons on a drive-letter host (`_colon_segments`, after a leading drive) and judges each part, as `_judge_whole_value` does. Test `hub/tests/test_a_path_word_with_a_later_colon_is_judged_by_its_names.py`: 5 allow cases failed before, 11 pass after; the escape cases (`src/a:../../x`, `src/a:/..`, `../a:1`) stay refused. Drive through the real stdio MCP server (`approve_tool_call`): `rg foo src/a:1` denied before, allowed after; `src/a:../../x` denied both ways. Original filing: Filed 2026-09-24 (operator decision `B4-approve`), measured by R8 of B4
(`spec-queue/tracks/B4.md` `## R8`). On a drive-letter host, today's rule 5 judges a plain word such as
`src/a:1` (as in `rg foo src/a:1`) through `ntpath.realpath`, which on Python 3.11 reads any component
whose second character is `:` as a drive and drops everything before it, so the word lands outside and
is refused. A false refusal, not an escape. Change 1 (`the-shell-judge-reads-a-word-whole`) avoids the
same misreading in its new whole-value pass by splitting at colons, since a Windows name cannot hold
one; the same split in rule 5 is the likely repair shape.

## F447 (B) — `--tools ""` leaves the account's claude.ai connector tools on the worker and titler

**Status:** fixed (this commit) [Round 6, 2026-09-24] — both argvs carry `--strict-mcp-config`. Was:
open. Filed 2026-09-24 (Round 6), measured by the F420 fix. With `--tools ""` (now on
both the checkpoint/probe worker, `hub/hub/worker.py` `build_worker_command`, and the titler,
`hub/hub/conversation_titles.py` `build_title_command`), a live Haiku `claude -p` turn named no built-in
tool but did list the account's claude.ai connector tools (`mcp__claude_ai_Claude_Docs__*`, including
create, update and delete). Both runs read untrusted transcript text, so a prompt injection could
still reach a connector that writes outside the machine. Candidate repair: add
`--strict-mcp-config` (with no `--mcp-config`) to both argvs and pin it in the argv tests; not yet
measured, because the worktree sandbox refused the probe. Sibling of F420.

**FIXED 2026-09-24 (Round 6):** `--strict-mcp-config` added after `--tools ""` in
`hub/hub/worker.py` `build_worker_command` and `hub/hub/conversation_titles.py` `build_title_command`;
the argv pins in `hub/tests/test_worker.py` and `hub/tests/test_title_generation.py` include it.
Measured with Haiku `claude -p` in a scratch directory: without the flag the model called
`mcp__claude_ai_Claude_Docs__read` (denied by the default permission mode, two attempts); with it the
turn had no tool at all (one turn, no denials), and a `CLAUDE.md` codeword was still read, so the
titler keeps the project memory F195 runs it there for. Production path: `run_worker` and
`maybe_generate_title` spawn exactly these argvs.

## F448 (C) — the operator's `GET /spec/evidence` ignores `document` when no `identifier` is given

**Status:** fixed (this commit) [Round 6, 2026-09-24] — the operator twin of F416. Was: found by the
F416 fix in Round 6. `list_evidence` (`hub/hub/api/v1/spec.py`) dropped `document` without an
`identifier` and returned the whole project's evidence with a 200.

**FIXED 2026-09-24 (Round 6):** `document` alone now resolves the document through
`spec_lifecycle.get_document` (404 when unknown, as `list_requirements` does) and joins
`SpecRequirement` on `document_id`. Test:
`hub/tests/test_agent_evidence_plane.py::test_the_operator_read_narrowed_to_a_document_alone_excludes_the_other`,
which fails on the previous route. No UI code calls the route with `document` today, so the reach is the
API and scripts.

## F449 (C) — the tool-server pin's startup line is never printed: `hub.*` INFO is below the root level

**Status:** fixed (Tier 0, 2026-10-12): `main.py`'s lifespan logs the pin and the prune at WARNING, like its sibling `_log_database_before_opening` (the narrow candidate; a Hub logging configuration was not built). Test `hub/tests/test_the_tool_server_pin_is_named_at_startup.py` launches a real `uvicorn hub.main:app` with a fake home and reads stderr; red before the fix. Driven on a throwaway Hub (port 8583, own DB and home): stderr shows `WARNI [hub.main] Tool server pinned at ...	ool-server\<digest>\mcp_server.py`. Was: open. Found 2026-09-25 driving `an-agents-tool-server-is-the-one-its-hub-loaded` task 3.1 on a fresh trial Hub (8026).
**Source:** drive
**Theme:** Hub plumbing
**Source:** drive
**Theme:** Runners & runtime

`main.py`'s lifespan logs `logger.info("Tool server pinned at %s", ...)` and `logger.info("Pruned stale tool server %s", ...)`. Neither appears in the Hub's output: zero hits over the whole startup log while the pin demonstrably ran (the file exists at the digest path and the spawned `--mcp-config` names it). Cause, already recorded in `main.py`'s own comment beside the database-path line (measured 2026-09-20): the root logger is WARN after `init_db()`'s alembic `fileConfig` (`alembic.ini`, `migrations/env.py:28`), and nothing lowers it, so every `hub.*` `logger.info` is dropped for the life of the process. Design D1's "the startup log names that path" is false as shipped; an operator cannot see which tool-server copy their Hub pinned without reading the process list. Fix candidates: log the pin at WARNING like its sibling, or give the Hub its own logging configuration so INFO reaches the operator (wider — it changes every `hub.*` INFO line).

## F450 (B) — an agent can claim and finish a task assigned to a different agent; `assignee` is not an authorization boundary

**Status:** fixed 2026-10-07 by `a-run-claims-only-its-agents-or-nobodys-work` (Tier 2, authored and approved in the app on `:8010`, `spdoc-02d1259eea94`): `_guard_run_holds_the_task` refuses an unbound run's claim of a task assigned to another agent (403 naming the assignee and the operator's remedy), and a claim of an unassigned task makes the claimer its assignee. Tests: `hub/tests/test_a_run_claims_only_its_agents_or_nobodys_work.py` (2 of 5 failed on HEAD; 3 controls). Driven on `:8010` (`d1007_claim_boundary_drive.py`, real Haiku beta): 0/3 before (beta took alpha's task to completed), 3/3 after. Reconciled into `run-task-binding` (`reconcile_f450.py`). Was: open. Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 7.
**Source:** drive
**Theme:** Task ledger

**What happened.** `task-bdb51ddeea1c` was created `assignee: alpha, status: assigned` and never started. A real Haiku turn on the idle agent `beta` called `update_task(…, in_progress)` then `update_task(…, completed)`: both 200. `task_transitions` records `assigned→in_progress` and `in_progress→completed`, both `actor_kind=run, actor_agent=beta`; `tasks.assignee` is still `alpha`, so the board and timeline name the wrong holder.
**Where.** `task_transition_service.py:475-537` `_guard_run_holds_the_task`: a run holding nothing takes any task (`run.task_id is None` → bind); nothing compares the run's agent with `task.assignee`.
**Related:** F27 (fixed; the unbound-completion half this guard closed). The self-review and self-approval guards held in the same row — `agents_that_may_have_authored` reads transitions, so `beta` is correctly barred from reviewing it.

## F451 (B) — `spec_document_id` on a loop or flow takes a document's path or its id, unvalidated: the path form orphans the flow and slips past the one-loop-per-document check

**Status:** fixed (Tier 0, 2026-10-07) -- `jobs._document_id_for` resolves a `spec/` path to its document id on create and on `PATCH`, so the loop stores the id tasks carry (adoption and the one-loop-per-document 409 both work by path); a `spec/` path naming no document is a 422. Not done: refusing an unknown *id* (about 30 tests across the suite build flows on made-up ids; that is a contract change, not this fix). Tests: `test_jobs.py::test_a_flow_named_by_its_documents_path_adopts_the_documents_tasks`, `::test_a_path_that_names_no_document_is_refused`, `::test_a_loop_given_its_document_by_path_later_stores_the_id` (all three failed before). **The drive caught what the tests missed:** on `:8010` a real path (99 characters) was refused 422 `string_too_long` by the request schema's `max_length=64` before the resolver ran, because the tests used short paths. `JobCreate`/`JobUpdate`/the agent `create_flow` body now take 255 (the path column); a non-path value over 64 is refused by the resolver. Re-driven: the F510 document's path answered 409 "document 'spdoc-eeaf6a633f2d' is already claimed by loop 'loop-ec88f6101755'"; a path naming nothing answered the 422 sentence. Was: open. Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 12.
**Source:** drive
**Theme:** Flows & loops

**What happened.** `POST /jobs` with `spec_document_id: "spec/changes/ivory-kirin/spec.html"` (the path, the form every spec tool takes) → 201, and the flow's queue stayed `{}` for good: tasks store `spdoc-0e47c7ae3226`, and `_adopt_document_tasks` compares strings. A second flow with `spdoc-0e47c7ae3226` on the same document, the first still live → 201, no 409. A third with the same id → 409 as designed (`job-54f432806846`, `job-49f2608e35fc`).
**Where.** `api/v1/jobs.py:143-178` `_check_spec_document_conflict` and `:259-265` compare the raw string; nothing checks it names a document. MCP `create_flow(spec_document_id: str)` (`mcp_server.py:766`) says only "the specification document this flow decomposes", and an agent knows documents by path.
**Related:** F53 (archived loops keep the document), F28.

## F452 (B) — `read_spec_document` returns acceptance criteria nested per requirement, `submit_spec_document` takes them flat: an agent's read-then-resubmit silently deletes every criterion

**Status:** fixed (Tier 0, 2026-10-08, `ebec9e8`): `validate_payload` lifts the read view's nested criteria into the flat list under their requirement's key, drops the Hub's `identifier`/`state`/`anchor` and retired requirements, refuses a contradicting nested criterion and a `section_truncated` requirement; items not shaped like criteria stay nested so F502's explanation still fires (`hub/tests/test_a_read_document_resubmits_without_loss.py`, 4 red before). Drive `scripts/drive/d1008_findings_drive.py f452`: a real Haiku read-then-resubmit on `:8010` stored 0 criteria plus the Hub's read fields before, both criteria and no read fields after. Was: open. Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 9.
**Source:** drive
**Theme:** Spec & requirements

**What happened.** Asked to resolve its own open question by resubmitting the document, `builder` read it (`include="full"`: `requirements[].acceptance_criteria` plus Hub-assigned `identifier`/`state`) and resubmitted that shape: top-level `acceptance_criteria: null`, the nested fields accepted and ignored. The document's acceptance section vanished, and `propose` then blocked on `requirement_without_criterion`, which reads as if none were ever written (`conv-d09510ccdf8b`, call `toolu_01Vf1qsAB79S5ZhQe6R8mXRV`).
**Where.** The two tools' shapes in `mcp_server.py`; the submit schema ignores unknown nested keys rather than refusing them.

## F453 (C) — under `manual` posture, commands Claude Code pre-approves as trivial never reach the operator, and nothing says so

**Status:** fixed 2026-10-16 (Tier 0, UI batch, f78419e): "Ask me" on a Claude runner says Claude Code still runs read-only commands unasked; with a test that failed before. Earlier status: open. Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 14.
**Source:** drive
**Theme:** Workspace & permissions

**What happened.** A `manual` turn asked to run `echo checkpoint-one/two/three` ran all three in ~13 s: 0 `permission_requests` rows, no event (`run-4e613a3491fb`). The next turn's `Write` calls each opened a card within a second. The cause is Claude Code's own pre-approval of read-only commands before `--permission-prompt-tool` is consulted, so it is not a Hub defect, but the pill and settings still promise "Ask me" for everything.
**Related:** F52 (an allow is unobservable). Approve, deny and the 120 s expiry all held in the same row.

**Re-verified 2026-10-15** (full sweep, G2: Agent environment, scratch Hub `:8032`): still bites. Under `manual`, `git status --short` and `echo hello` ran with no card; only the Python write reached the operator (`perm-c25b8d8bd805`).

## F454 (B) — a Hub-launched agent can load the operator's personal Claude Code skills; a loop firing ran `e2e-loop` and started new loops and commits nobody asked for

**Status:** fixed 2026-10-15 (Tier 2, `spec/changes/a-hub-agent-runs-with-the-projects-settings`). Every Claude agent argv passes `--setting-sources project,local` (`runner_commands._build_claude_command`), and a runner's flags may not carry it (`runner_flag_rules`). Hand-measured first: the flag drops the operator's ~/.claude skills and plugin skills and keeps the project's CLAUDE.md and .claude/skills. Acceptance drive `scripts/drive/d1015_f454_user_skills.py` committed failing (the agent listed e2e-loop, handoff, resume) and passes after; the 52 Claude argv goldens differ by the flag pair alone. Codex and Copilot user configuration are not covered. Opened before: Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 11.
**Source:** drive
**Theme:** Agents & runners

**What happened.** A scratch loop left enabled (empty queue, message "placeholder", a descriptive `purpose`) fired twice. Both times `builder` read the purpose as a directive and invoked the operator's own `e2e-loop` skill from `~/.claude/skills`. It then tried the trial Hub twice (`curl http://127.0.0.1:8010/health`, denied by the shell judge: "a shell command may name only this run's own Hub"), called `create_loop` and `toggle_job`, wrote an unrequested report and committed it to the project's `master` (conversation `conv-fc2dbb291cc5`; jobs `job-88075aa4fe95`, `job-7cac48f7ca02` created by the agent).
**Why B.** The operator's user-level skills include ones that register Windows scheduled tasks (`autonomous-session`), and agents run with them available. The shell judge held on the network half; nothing scopes which skills a run sees.
**Related:** F195 (setting sources), F284.

**Re-verified 2026-10-15** (full sweep, G2: Agent environment, scratch Hub `:8032`): still bites. A Hub-launched Haiku listed e2e-loop, handoff, resume and about 17 more of the operator's personal skills, and the operator's personal `Stop` hook ("Chime: response finished") ran inside the agent's session. Downstream symptom (not filed separately): the composer's `$skill` menu lists only the project's `.claude/skills/` (`lib/composerTriggerSources.ts:5`) and showed "No matches" while the same agent loads about 20 skills; fixing this finding removes the mismatch.

## F455 (C) — `agentweave doctor --port N` without `--profile` checks the default profile's database and reports it accessible

**Status:** fixed 2026-10-12 (night window, Tier 0). `cmd_doctor` now recovers the profile from the live `hub-<profile>-<port>.pid` file when `--port` is given and the profile is the default (`_hub_profile_serving_port`, `src/agentweave/cli.py`). Test `tests/test_doctor_port_names_its_profile.py` goes through `cli.main`, because the global `--profile` defaults to `"default"` and a hand-built Namespace hid that (first version passed while the fix could not fire). Drive: real `agentweave.cli doctor` process, redirected home, live pid file `hub-drive455-8030.pid`: `--port 8030` checked `profiles\drive455\agentweave.db`; no port and `--port 8031` kept `data\agentweave.db`. A Hub with no pid file (started by hand) is still not recognised: the default database is checked as before.
**Found:** the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), CLI.
**Source:** drive
**Theme:** Hub plumbing

**What happened.** `doctor --port 8030` → `[OK] ~/.agentweave/hub/data/agentweave.db: The native database is accessible.` although `:8030` serves `profiles/sweep0925`; with `--profile sweep0925` it checks the right file. Nothing warns that the database checked is not the one behind the port. This is the `doctor` half of F34's own description; F34's `--port` fix (`6b1013f`) holds.
**Related:** F34.

## F456 (D) — a budget-exhausted project runs an operator's trigger without saying the budget was passed over

**Status:** fixed (Tier 0, 2026-10-13) -- `POST /agent/trigger` reads the project's budget before scheduling; when it was already spent and the operator's turn runs, the response carries `budget_note` and a `token_budget_passed_over` warn event is persisted for the agent. The scheduler's deliberate asymmetry is unchanged. Test: `hub/tests/test_a_budget_passed_over_is_said.py` (through the real route; the spent-budget case failed before at `budget_note`; an under-budget trigger carries neither). Not driven on a live Hub; the UI does not yet render the new event or field. Was: open. Found the 2026-09-25 full-surface sweep (Hub `:8030`, profile `sweep0925`, HEAD `c9873c4`, Haiku), row 18.
**Source:** drive
**Theme:** Operator surfaces

**What happened.** With `token_budget` below `used_tokens` (`exhausted: true`), `POST /agent/trigger` → 200 and the turn ran (`run-ff2da3eff08c`); a peer-triggered turn was held with "token budget exhausted" and drained the moment the budget lifted. The asymmetry is deliberate (`turn_scheduler.py:364` gates `initiator == "autonomous"` only), and neither response nor the timeline says so.

**Re-verified 2026-10-15** (full sweep, G6: Accounting & allowance, scratch Hub `:8036`): fix holds at the API (an operator turn on a spent budget carried `budget_note` and a `token_budget_passed_over` event); the `budget_note` is still not rendered on the conversation screen, as this entry's status says.

## F457 (C) — a firing that loaded its loop before an edit was staged clears that edit's marker, and the edit is stranded

**Status:** fixed (Tier 0, 2026-10-13) -- `_stage_pending_loop_edit` clears the pending fields in memory as committed values (so the ORM flushes no stale NULLs) and `_release_staged_edit` clears the row with `UPDATE loops ... WHERE id = ? AND pending_edit_at = <value loaded>`; an edit staged since stays staged (and the loop's pending attributes are re-read). Both firing paths go through `_stage_and_release_loop_edit`. Test: `hub/tests/test_a_late_staged_edit_survives_a_firing.py` (two sessions; failed before at `pending_edit_at is not None`). Not fixed: `pending_edit_actor` is still one value per edit, so a later edit by another actor takes the credit for fields staged earlier (the review's second half). Not driven on a live Hub. Was: open. Filed 2026-09-25 by an interactive session, from the Opus review of request R1's changes (`spec-queue/tracks/reviews/R1-2026-09-25.md`, change 1 finding 8). Read in code, not driven.
**Source:** code — found by reading code, not by driving.
**Theme:** Flows & loops

**What happens.** A firing loads the `Loop` row, then a `PATCH /jobs/{id}` stages an edit (`pending_*` plus `pending_edit_at`). When the firing commits, `_stage_pending_loop_edit`'s clear writes `pending_edit_at = NULL` from its stale copy, and SQLAlchemy writes only the columns it changed. The staged values stay in `pending_*` behind a NULL marker: never applied, never shown as pending, and silently applied by whatever edit is staged next. `pending_edit_actor` is also last-writer-wins, so a later agent edit to `purpose` takes the credit for an operator's staged change.
**Why C.** Needs an edit to land inside a firing's window. Today it affects purpose and stop condition. `a-flow-is-configured-from-its-own-tab` adds the default agent to the staged fields and applies edits earlier (its D2a), which widens the window a little.
**Cure (suggested by the review).** Clear the marker with a conditional `UPDATE … WHERE pending_edit_at = <the value loaded>`, and record the actor per field or refuse to merge edits from different actors.
**Related:** `a-flow-is-configured-from-its-own-tab` (design, Risks).

## F21 addendum, 2026-09-25 sweep — the looping agent faked a success, and the workaround stamps the wrong commit

Reproduced in row 10: `builder` re-loaded `record_evidence`'s schema six times, then printed an invented "Recording evidence…" success block through PowerShell and ended `completed` with no evidence row. The prescribed focused retry worked at once, but it ran unbound to the task, so `ev-6da671ce9ee7`'s `footprint.commit_sha` is the project's initial commit, which does not contain the work its summary describes; `outside_workspace_writes` stayed `[]`.

## F458 (B) — the surfaced reason for an operator-held review says "still running the turn ... this clears itself" after the turn has ended

**Status:** fixed (Tier 0, 2026-10-07) -- `approval_held_for_operator` takes `acting_run_id`, and all three `run_divergence` calls pass the ending run, so the gate's live-turn arm no longer counts the turn being judged. Test: `test_a_review_no_reviewer_can_approve_goes_to_the_operator.py::test_the_hold_reason_does_not_count_the_ending_review_as_a_live_turn` (reproduced the sentence verbatim before). Was: open. Filed 2026-09-26, found driving `a-review-no-reviewer-can-approve-goes-to-the-operator` (`scripts/drive/d0926_review_hold.py`, real Haiku). The `run_diverged` reason for beta's ended review appends the gate's drift arm (`requirement_gate.py:324`): "beta is still running the turn that produces this task's work ... Approve once the turn has ended: this clears itself, with nothing for anyone to do." It is written at run end, while the run row still reads running, so it contradicts its own first half ("no reviewer can approve it until you act"). The flow card's stall_reason is correct. Not caused by the change; the change now surfaces the gate's text verbatim. A repair should decide whether the gate ignores the calling run when evaluating at run end.

## F409 drive, 2026-09-27 (live Hub :8041, profile drive0927, Haiku, `claude` 2.1.280) -- tasks 4.1-4.2c of an-at-mention-an-agent-wrote-reads-no-file

Signal: the CLI session transcript holds `"attachment":{"type":"file"` exactly when the harness read a file at prompt time. Harness: `scripts/drive/d9_0927_at_mention_live.py` (stages setup/41/42); the 4.2a-4.2c legs were ad hoc scripts in `testbed/scratch/` (untracked).

- **4.1 PASS.** agenta `send_message` to agentb with an at-sign path outside the workspace: agentb's transcript has 0 file-attach records and 0 marker occurrences. (agenta's own transcript has 1: the operator's trigger text carried the at-sign path, which is operator text and is not neutralised by design.)
- **4.2 PASS (trigger route).** Operator text with an at-sign path inside the workspace to agentb: 1 attach record naming it.
- **4.2a PASS.** Project checkpoint mode automatic, tokens threshold 1000, agentb replied with an at-sign path; the checkpoint became `ready`, probe `passed`, body has no marker; both worker transcripts (checkpoint worker and titler): 0 attach records, 0 marker occurrences, the path present once each, escaped.
- **4.2b PASS.** Task with an at-sign path in its title, Start work pressed in Chromium on the served bundle, agentb assigned: the task run's transcript has 0 attach records and 0 marker occurrences; its prompt reads `Work on task <id>: Inspect <backslash>@C:...`, and the conversation title shows the same escaped form. The board card shows the title as stored (unescaped), by design.
- **4.2c PASS on the signal, one leg not asserted.** agentb `ask_user` blocking=false with an option labelled `Use @<outside path>`; clicked in Chromium (option button text shows the label as offered). The answer is stored raw; the delivered next-turn prompt reads `Answer: Use <backslash>@C:...` (escaped); the transcript has 0 attach records. NOT asserted: the chat echo's DOM text (the later DOM scrape found neither form, the view had moved on). Only the delivered prompt was read.
- **Caveats, honestly.** (1) In 4.2c, after the escaped answer, agentb read the file with a Read tool call (marker in a `tool_result`), because these turns ran with `bypassPermissions` (my trigger override) and the model chose to. That is a tool call under the operator-set posture, not the prompt-time expansion this change closes; the default Workspace-only posture was not re-driven for it. (2) My 4.2c trigger text embedded the at-sign path literally, so that turn's own transcript has one attach record; operator text, expected. (3) The automatic checkpoint cut agentb over into a continued conversation whose first blocking `ask_user` stalled the queue; I declined it through the API to let the drive proceed.
- Teardown: Hub PID 26020 stopped; the scratch project directories under `~/Documents/drive-0927-atm-*` were left in place (no deletion under the night window's limits).

## F459 (B) — `a-runner-choice-names-its-model`'s `RunnerPicker` wiring added a second, unhandled `useModelCatalog()` call site

**Status:** fixed same-night, in the commit implementing `an-estimate-that-misses-turns-says-so`. Found running that unrelated change's own task 2.3 (`py -3.11 -m pytest hub/tests/ -q`, full suite, F392 rule 1/2 gate): `test_surface_ceilings.py`'s four ratchet tests all failed — `AgentSettingsControls.tsx:228`'s `RunnerPicker` (added earlier this same night, commit `2b91c92`, archived `ff961b1`) calls `useModelCatalog()` a second time in that file to feed `runnerOptionLabel`, without binding or using its `error`, and without a row in `scripts/drive/n11_query_error_surface.py`'s `CLASSIFIED`. The gap is real: that change's own verification (iteration 3 of the 2026-09-27 night log) ran `hub/tests/` at compose, *before* the change existed, then reasoned the change was "UI-only" and skipped a fresh Python run after implementing it — so this guard file, which scans `hub/ui/src` from `hub/tests/`, never ran against the code it was checking. Neither `an-estimate-that-misses-turns-says-so`'s own guard-file union (F392 rule 2: `test_a_refused_first_send_leaves_no_exploration.py`, `test_failed_run_returns_input.py`) nor `a-runner-choice-names-its-model`'s named it either — it surfaced only because task 2.3's own instruction is to run the *full* `hub/tests/` suite, not just the union. Fixed by binding `error: catalogError` in `RunnerPicker` and rendering it (same pattern as the existing `launchabilityError` notice in the same component), which makes the site `HANDLED` rather than unhandled — no ceiling raised, no new `CLASSIFIED` row needed. Re-run: `test_surface_ceilings.py` 6 passed; full `hub/tests/` 5086 passed, 86 skipped, 0:30:31.

## F460 (B) — `a-model-alias-is-a-model-choice`'s two agent-creation tests never mocked `shutil.which`, so they only ever passed with a real `claude` on PATH

**Status:** fixed same-night, in the commit implementing `the-codex-models-offered-are-the-ones-its-cli-lists`. Found running that unrelated change's own task 2.5 (`py -3.11 -m pytest hub/tests/ -q`, full suite, `claude` stripped from PATH, F392 rule 1 gate): `test_a_model_alias_is_a_model_choice.py::test_post_agents_accepts_the_alias_and_stores_it_as_written` and `::test_an_alias_created_runner_is_named_for_the_alias_not_its_target` both failed `AssertionError: {"detail":"Runner CLI 'claude' was not found in PATH."}` / `assert 409 == 201`. Confirmed this was not new: CI (`gh run list --branch autonomous/2026-09-27-daily`) had been red on the exact same two tests on every commit since `63d9f34` (the alias change's own impl commit, archived same night in `8e75486`) through the current head `46072e3` — a 4-commit streak nobody had triaged, because the machine driving the night window has `claude` on PATH and the failure only shows with it stripped or on CI's runners, which don't. Every sibling test in the file (and everywhere else in the suite that calls `POST /agents`) wraps the call in `with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):`; these two were the only ones that skipped it, so they measured nothing about the alias feature on CI — only whether the ambient machine happened to have `claude` installed. Fixed by adding the same patch around both calls (`hub/tests/test_a_model_alias_is_a_model_choice.py`). Re-run: file 10/10 passing with `claude` stripped; full `hub/tests/` 5109 passed, 86 skipped, 0:29:59 (up from 5107, the fix adding no new tests, only correcting two existing ones).

## F461 (B) — a Codex agent's configured question wait never reaches `ask_user`; above 240 s the wait ends early and its report is refused

**Status:** fixed 2026-10-13 (night window, Tier 0): `AW_QUESTION_TIMEOUT` added to `CODEX_MCP_ENV_NAMES` (`runner_commands.py`), the one tuple both the `exec` `-c mcp_servers.agentweave.env_vars=` arg and the app-server `thread/start` config read; `argv_golden.json` re-captured for it. Tests `test_codex_mcp_server_whitelists_run_identity_environment` and `test_mcp_command_is_registered_in_thread_start_config` assert the name in each transport and failed before the fix. Driven in-process via `build_command` only (Codex undrivable); `AW_DECISION_TIMEOUT` is likewise not forwarded -- not this finding's scope. Originally: open, filed 2026-09-28 from code (not driven: Codex is undrivable here). Found in `each-runner-cli-is-one-adapter`'s R3 (open question 4) and sharpened by its Opus review (`spec-queue/tracks/reviews/ghcp-s1-2026-09-28.md`).

The trigger puts the agent's `question_timeout_seconds` into the run env as `AW_QUESTION_TIMEOUT` (`hub/hub/api/v1/agent_trigger.py:1262`), and the tool server reads it with a 240 s default (`hub/hub/mcp_server.py:1005`). But Codex filters the environment its stdio MCP servers inherit, and both Codex allow-lists forward only `AW_RUN_TOKEN`, `AW_AGENT_IDENTITY`, `AW_RUN_ID`, `AW_TURN_DEPTH` and `HUB_URL` (`runner_commands.py:322-328` for `exec`, `codex_appserver.py:973-979` for app-server). So a Codex agent's `ask_user` always waits 240 s, while the Hub records the configured deadline. Configured above 240 s: the tool stops at 240 s and its `wait-ended` report is refused because the Hub's own deadline has not passed (`agent_actions.py`, `report_wait_ended`), so the question stays waiting until the run-end sweep. Configured below 240 s: the tool waits past the Hub's deadline. Claude is unaffected (its tool server inherits the env).

Fix: add `AW_QUESTION_TIMEOUT` to both lists (slice 1 moves them into one `CODEX_MCP_ENV_NAMES` in `runner_commands.py`). Test: the rendered Codex config forwards it.

## F462 (B) — a specification turn on Codex app-server keeps its write tools

**Status:** fixed (Tier 2, 2026-10-07, change `a-codex-app-server-spec-turn-keeps-no-write-tools`, `spdoc-4e84aebf7712`, operator approved). Two breaks, not one: `CodexAppServerTransport.run_turn` dropped the flag, **and** `trigger_agent_directly`'s `_execute_run` call never passed it, so the RPC executor always got `False` -- the dispatch-seam test caught the second after the transport fix alone went green. A spec turn's thread now starts `read-only` (`on-request`, or `untrusted` under Ask me; never `never`), its file changes and sandbox escapes are declined (Ask me still carries a command to the operator) and Full access grants no permissions, except the Hub's own call (`mcp_server._hub_own_call`: a calls-root `.json` file, one `aw-tool` invocation), which a shim-told spec turn needs to submit its document. Test: `test_a_codex_app_server_spec_turn_keeps_no_write_tools.py` (20 of 20 failed before). **Not driven:** Codex is undrivable here; what a real binary does with the policy is unobserved.
Originally: open, filed 2026-09-28 from code (not driven). Found in `each-runner-cli-is-one-adapter` R2 (design D11) and confirmed by its Opus review.

F4's rule — a turn triggered with a specification document open loses file-write tools, "regardless of phase, rigor or permission posture" — is applied by passing `restrict_spec_writes=bool(spec_document)` to `build_command` (`agent_trigger.py:1227`). For Codex app-server, the default Codex transport (`uses_app_server`, `agent_trigger.py:1210`), that argv is unused: the turn goes through `codex_appserver.run_turn`, which receives neither `restrict_spec_writes` nor the runner's flags (`codex_appserver.py` has no such parameter). So a Codex agent on a spec turn can write files; only `codex exec` honours the restriction (`runner_commands.py:336`).

Fix: carry `restrict_spec_writes` on the RPC turn request and apply it in the app-server thread's sandbox/tool config (slice 1 adds the field; this finding tracks the behaviour). Test: a spec-turn app-server request carries the restriction.

## F463 (C) — the provider quota hold picks the "newest" usage reading by wall clock, so a clock step back picks an old reading

**Status:** fixed 2026-10-08 (night window, Tier 0). `provider_allowance._newest_informative` now orders by `turn_usage.rowid DESC` (insertion), `observed_at` stays display only; tests `test_the_later_inserted_reading_wins_when_the_clock_stepped_back` and `test_a_refusal_inserted_after_a_clock_step_back_holds` (both red before). Driven on a migrated throwaway DB through the real writer `record_turn_usage` with a 2h clock step back: before the fix `provider_hold` still held the agent after an allowed reading, after it returns None. Filed 2026-09-28 from code. Found while applying the Opus review of `a-copilot-run-shows-its-credits` (review finding 3, `spec-queue/tracks/reviews/ghcp-s4-2026-09-28.md`), which fixed the same pattern in its own credit baseline.

`provider_allowance._newest_informative` orders `TurnUsage` by `observed_at DESC` (`hub/hub/provider_allowance.py:122-131`). `observed_at` is the Hub's wall clock at write time. After the clock steps back (NTP correction, DST misconfiguration, a VM restore), a newer reading sorts below an older one, so the Claude allowance hold and `last_refusal` can read a stale allowance: hold an agent that is no longer refused, or release one that is. The credits change orders its baseline by `rowid DESC`, as `api/v1/spec.py` already does.

Fix: order by insertion (`rowid`/id sequence), with `observed_at` only as display. Test: two readings inserted with the later one carrying an earlier `observed_at`; the hold reads the later-inserted one.

## F464 (C) — `_where` resolves a UNC path over the network before deciding, stalling the deciding process ~21 s per path word

**Status:** fixed 2026-10-08 (night window, Tier 0). `_where`, `_inside_hub_calls_root` and `_read_call_args` refuse a doubled-separator (UNC / `\?\` / `\.\`) path on a drive-letter host before any `realpath` (`hub/hub/mcp_server.py`, `_names_a_network_path`; tests `test_a_network_path_is_refused_before_it_is_resolved.py`, 16 of 18 red before). The first fix, in `_where` alone, did NOT fire: driven through `_decide`, an Edit of an unreachable UNC path still took 21.03 s because `_hub_own_call` -> `_inside_hub_calls_root` resolves the path first; after guarding it, 0.0 s (fresh unreachable IPs each run, Windows caches the failure). A UNC workspace root is left to the old route. Filed 2026-09-28. Measured by the Opus review of `a-copilot-agent-runs-over-acp` (`spec-queue/tracks/reviews/ghcp-s2-2026-09-28.md`, finding 7): `os.path.realpath(r"\10.255.255.1\share\x")` took 21.06 s on this machine.

`mcp_server._where` calls `os.path.realpath` on every path and path-like shell word before comparing it to the workspace (`hub/hub/mcp_server.py:1113-1133`). A model-written permission request naming an unreachable UNC path (an edit path, a `path` input, or one word of a command) blocks for ~21 s per word and opens an SMB connection to that host. Today this runs in the per-run MCP tool server, so the stall is per run; slice 2 moves `_decide` into the Hub process, where it would freeze every project (slice 2 now runs it via `asyncio.to_thread`). The path is refused in the end anyway, as outside the workspace.

Fix: refuse `\`, `//`, `\?\` and `\.\` paths before `realpath`, so no network I/O happens. Test: a patched `realpath` that fails the test if called for a UNC path.

## F465 (C) — archived agents keep counting against the agent budget, so a project at its budget can only raise it

**Status:** fixed 2026-10-13 (build window, Tier 0), taking the recommended answer to the question below: the budget counts **open** agents only (`hub/hub/api/v1/agents.py`, `request_agent`; the 409 now reads `(open/budget)`), the taken-name check still counts archived rows. Tests `test_an_archived_agent_does_not_count_against_the_budget` and `test_the_budget_counts_open_agents_and_says_so` in `test_request_agent_models_an_existing_agent.py`, both red before the fix; the name-stays-taken test passes before and after. Exercised through the ASGI app on the real route, not a live Hub. Operator row `build-1013-1` (OPEN) asks to confirm or reverse. Filed 2026-09-29. Found by driving `request-agent-models-the-new-agent-on-one-the-operator-made` (task 3.2, second run) on the trial Hub: `request_agent` answered `409 Project agent budget exhausted (8/8)` for a project with **5 open and 3 archived** agents (measured read-only on the trial database), right after the drive had archived its own agents.

`request_agent` counts every agent row, including archived ones, against `Project.agent_budget` (`hub/hub/api/v1/agents.py:2290-2298`, `existing_names = set(rows_by_name)`). The taken-name check counts archived rows on purpose, since a name is never reused (design D5 of that change). The budget reuses the same set, and nothing says the budget should count them too. The count predates the change: the old code counted the same rows. Agents cannot be deleted, only archived. So once a project reaches its budget, an agent can never again request one, however many are retired, unless the operator raises the budget. `agent-tool-surface` says only that the budget "SHALL be counted over the project's agents alone".

Question for the operator: should the budget count **open** agents only (archiving frees a slot), or is it a lifetime cap on how many agents a project has ever had? Test either way: a project at its budget with one agent archived, then a request, asserting the chosen answer.

## F468 (C) — an agent can message itself, and the message starts a new autonomous turn

**Status:** fixed 2026-10-08 (night window, Tier 0), narrowed: `POST /agent-actions/messages` refuses a self-send that names no conversation, or names the sender's own current one, with a 400 naming the reply, `update_task` notes and `ask_user`, before any Message, queue entry or run exists (`hub/hub/api/v1/messages.py`; tests `test_a_message_to_oneself.py`, red before the fix). A self-send naming a DIFFERENT conversation of the agent still goes through: item 10 of the operator's twelve (2026-08-20) asked for it and `test_an_agent_can_message_its_own_other_conversation` locks it; `test_a_self_send_is_bounded_by_the_hop_budget` now sends to a second conversation. Driven over real HTTP on a throwaway Hub (`testbed/f468/drive.py`): self-send 400, no message, no new run; peer send 201. Not driven with a real agent turn. Filed 2026-09-30. Found by driving `a-copilot-agent-runs-over-acp` 11.2 on a drive Hub (`:8031`, `drive0930`). Not Copilot-specific: the path is the Hub's `send_message`.

Asked to "send me a one-line message with agentweave-send_message", a Copilot agent called `send_message(to_agent="cop-1", …)`, addressing itself. The operator is not a message recipient (the tool's own docstring says so), so the model picked the nearest name it had. The Hub accepted it: the message was queued as input to `cop-1` (`origin_type='agent'`, `origin_agent='cop-1'`) and immediately started a second turn, `initiator='autonomous'`, in a new conversation. That turn spent one more model call (a Free-plan premium request) acknowledging its own message. The hop budget bounds a chain, so this is not unbounded, but every self-message costs a turn and splits the work across conversations.

Question for the operator: should `send_message` refuse `to_agent` equal to the caller (a 400 naming the reply as the way to reach the operator), or is messaging yourself a legitimate way to schedule follow-up work? Test either way: an agent run's `send_message` to itself, asserting the chosen answer and that no turn starts if refused.

**Operator answered 2026-09-30 (AskUserQuestion, handoff-0158 resume):** refuse it. `send_message` with `to_agent` equal to the caller returns a 400 naming the reply as the way to reach the operator, and no turn starts. Ready to propose.

