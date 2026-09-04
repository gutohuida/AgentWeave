## 1. Reproduce it first

- [x] 1.1 Add `hub/tests/test_a_write_outside_the_workspace_is_recorded.py`. Build F115's shape from
  the parse side: feed `parse_claude_line` a real `assistant` line carrying a `tool_use` block for
  `Write` with an absolute `file_path` outside the workspace, and assert the current behaviour — the
  parsed events carry the path only inside `payload["input"]` as a stringified blob, and nothing
  anywhere says it was outside anything. Run it against unmodified code and confirm it passes. A
  reproduction that does not pass first is not a reproduction.
- [x] 1.2 Add the record side: a `Run` with `workspace_dir` set to an agent worktree, and assert that
  after a turn containing that call the run carries no record of an outside write and no activity
  event mentions one. Confirm it passes against unmodified code.
- [x] 1.3 Add the cross-worktree shape: the same call, but with the absolute path inside a *second*
  agent's worktree under the same project. Assert that today nothing distinguishes it from the
  previous case. This is the case whose whole meaning is the destination.
- [x] 1.4 Pin the round-1 correction as a test rather than a claim: assert that `mcp_server._decide`
  **refuses** the same absolute path under the default posture, so the record of what the default
  posture does is in the suite and not only in this proposal. If it does not refuse, stop — the
  proposal's premise is wrong and rounds 2 and 3 need to know before anything is built.

## 2. Extract write paths at the parse point

- [x] 2.1 Add `hub/hub/workspace_writes.py`: pure, stdlib-only, no session and no filesystem writes.
  It owns the two halves that must not drift apart — which tools write, and where a path belongs.
- [x] 2.2 `written_paths(tool: str, input_data: Any) -> tuple[str, ...]` — the declared path
  argument(s) of a file-*writing* tool call, empty for everything else. Claude: `Write`, `Edit`,
  `MultiEdit`, `NotebookEdit`. Codex: `apply_patch`. (`MultiEdit` is back: round 2 dropped it on the
  false ground that nothing else recognises it - see 2.2b.) Reads (`Read`, `Glob`, `Grep`, `LS`) return empty, per design
  D3. An unknown tool returns empty rather than guessing from key names: a detector that invents
  coverage is the failure mode this whole change is careful about. Return on the tool name **before**
  looking at the input, because that is what the function *is*: writers only, everything else empty.
  Not for cost. `tool_use_event` already runs `redact_secrets` and `json.dumps(sort_keys=True)` over
  every input unconditionally (`runner_events.py:142-143`), so a membership test is not measurable
  beside it (design D13).
- [x] 2.2b Reconcile the list against the source that shares its concept, per round 3's correction to
  D3. (Line numbers below re-measured 2026-09-04: `AgentTimeline.tsx` was `:573`, `mcp_server.py`
  was `:858`, `runner_commands.py` was `:210`.) The product states "which tools write" three times, not twice, and the match is
  `WRITING_TOOLS` in `hub/ui/src/components/agents/AgentTimeline.tsx:615` -
  `{Edit, MultiEdit, Write, NotebookEdit, apply_patch}` - both providers, already driving the "wrote
  to N files" summary an operator reads. Assert `written_paths`' writer set equals it.
  **Do not** assert against `runner_commands.py:203`: that is `restrict_spec_writes`, an F4/D6
  permissions flag scoping one kind of agent, Claude-only by construction, so the assertion round 2
  proposed is false for `apply_patch` and would force `MultiEdit` out for a reason that does not
  hold. Separately assert that the **Claude** path keys are a subset of `mcp_server.py:895`'s
  `_PATH_KEYS` (`MultiEdit` passes: its input is `{file_path, edits: [...]}`). Codex's
  `changes[].path` is nested and is deliberately not in `_PATH_KEYS`. `mcp_server.py` may import only
  stdlib plus fastmcp, so this is restate-and-assert, the shape `test_permission_approver.py` uses
  for `OPERATOR_POSTURE`.
- [x] 2.2c File, do not fix: `restrict_spec_writes` disallows `Edit,Write,NotebookEdit` and omits
  `MultiEdit`, which the UI counts as a write, so a spec-restricted agent may be able to write
  through it. Filed 2026-09-04 as **F277**, with both postures measured. Out of scope here, and
  this change must not inherit the gap by treating that flag as the definition of a write tool.
- [x] 2.3 Cover the multi-path case. `NotebookEdit` names one file under `notebook_path`; `Write`,
  `Edit` and `MultiEdit` name one under `file_path` - `MultiEdit`'s several edits all target that one
  file, so it stays one-element; Codex's `apply_patch` names several under `changes[].path`. The
  tuple return is load-bearing for the Codex side.
- [x] 2.4 Add `write_paths` to **`RunEvent`** (`hub/hub/runner_events.py:111-115`), not to
  `ParsedLine` — see round 2's correction to D2. Carry tool name, call id and the raw path string,
  nothing else, defaulting to `()`. Populate it inside `tool_use_event`
  (`hub/hub/runner_events.py:134`) from the `input_data` it is handed **before** it redacts,
  stringifies and truncates at 8 KiB, because the structured path may not survive that. One
  population site serves all three transports, and the field is never persisted:
  `record_agent_output` stores `kind` and `payload` only.
- [x] 2.5 Assert the field arrives on all three transports, since this is what round 1 got wrong.
  `parse_claude_line`'s `tool_use` branch (`runner_parsing.py:264-272`);
  `parse_codex_line`'s **`file_change`** branch (`runner_parsing.py:486-499`, snake_case — the Codex
  `exec` transport, which round 1 named nowhere); and `map_item_to_events`'s **`fileChange`** branch
  (`codex_appserver.py:448-459`, camelCase). All three call `tool_use_event`, so all three should
  need no change of their own — a test per transport is what proves it.
- [x] 2.5b Use F107's shape for the Codex `changes` element — `{"path": ..., "diff": ...}`,
  corroborated by `approval_subject` and `hub/tests/test_permission_approver.py:588-604`, which was
  written against a live item rather than off `_file_change_summary`. Copy its malformed-input cases
  verbatim: `None`, `{}`, `{"changes": "not-a-list"}`, `{"changes": [{"path": 1}, {}, None]}` — all
  extract nothing, none raise.
- [x] 2.5c **Answered in round 3; keep it as a regression test.** `kind="tool_use"` is constructed in
  exactly one place in `hub/hub` - `runner_events.py:154`, inside `tool_use_event`. Add a test that
  asserts it, so a future second constructor fails here rather than silently escaping detection. The
  one boundary to state in the test's docstring: `POST .../output` accepts a `tool_use` kind from an
  agent the Hub did not spawn, which has no `RunEvent` and no workspace to be checked against.
- [x] 2.6 Assert the parser stays pure: no workspace argument, no filesystem access, no import of
  anything that touches the database. A test that imports `runner_parsing` in isolation is enough to
  keep this honest.

## 3. Classify a path against the run's workspace

- [x] 3.1 In `workspace_writes.py`, add `classify(path, *, workspace_dir, project_root)` returning a
  workspace kind and name: `agent`/`task`/`review` from the layout helpers in `worktrees.py`
  (`worktree_path`, `task_worktree_path`, `review_path`), **`hub` for anything else under
  `<root>/.agentweave/`**, `project` for the project's own directory, `outside` for anything else. Kind-and-name, per design D4 and `workspace-isolation`'s existing
  requirement that a reported workspace says which namespace it belongs to.

  *Implemented 2026-09-04 (night N-16) as **restate-and-assert**, not as an import.* Task 2.6's
  purity test runs a fresh interpreter and requires `hub.workspace_writes` to pull in no other
  `hub` module; `worktrees` reaches `subprocess`, `shutil` and `repo_hygiene`, so importing the
  helpers would fail it. The layout is restated as `HUB_DIRECTORY` plus a
  `CHECKOUT_SEGMENTS = {worktrees: agent, tasks: task, reviews: review}` map -- the same shape
  `mcp_server.py` lives under -- and
  `test_the_restated_layout_is_the_one_the_worktree_helpers_use` asserts the three roots the
  classifier believes in are exactly `worktree_root`/`task_root`/`review_root`. Every other
  phase-3 test builds its paths by *calling* the helpers, so the helpers remain the source of
  truth for the layout and the restatement cannot drift silently.

  Two shapes decided while implementing, both asserted: `name` is `None` for `project`, `hub`,
  `inside`, `outside` and `unknown`, because there is exactly one of each per project and a name
  would only repeat the kind; and whatever sits directly under a checkout root is read as that
  checkout's name without a `stat`, because the path being classified has usually not been
  written yet. `WriteLocation` is a `NamedTuple` so task 4.4b can key its once-per-destination
  accounting on a whole location.
- [x] 3.1b The `hub` kind is round 3's correction and it is not cosmetic: the Hub seeds
  `.agentweave/worktrees|reviews|tasks|logs|evidence|context` into the repository's `info/exclude` on
  every turn (`repo_hygiene.py:59-80`, called first in `resolve_agent_workspace`), so that subtree is
  the one part of the project root git has been told to hide - while the requirement described
  `project` as the destination that "sits there visibly". Add a test that walks `EXCLUDE_PATTERNS`
  and asserts every `.agentweave/` pattern classifies as `agent`, `task`, `review` or `hub`, never
  `project`. The classifier still derives the three checkouts from the layout helpers, not from the
  exclude list - one source of truth - and this test is what keeps the two from drifting.
- [x] 3.2 **Join before resolving**, then compare on `os.path.realpath` + `os.path.commonpath` +
  `os.path.normcase` - `_decide`'s whole construction, including the first line rounds 1 and 2 both
  omitted (`mcp_server.py:901`):
  `absolute = candidate if os.path.isabs(candidate) else os.path.join(root, candidate)`.
  Round 1 asserted realpath alone would catch the `..` case. It will not: `realpath` resolves a
  relative path against the **calling process's** cwd. `_decide` gets away with it because it *is*
  the spawned MCP server, whose cwd is the run's workspace (its own shell-branch comment relies on
  exactly that), whereas this runs in the Hub process, which serves many projects from wherever
  uvicorn was started. Test a relative `../../x` explicitly and assert it classifies against the
  workspace, not the Hub's cwd - run the test from a cwd other than the fixture workspace, or it
  proves nothing. `commonpath` compares components so `/work-other` does not read as inside `/work`.
- [x] 3.3 Return "inside" for a path within the run's own workspace, and record nothing for it.
- [x] 3.4 Return "unknown" — never "outside" — when `workspace_dir` is absent or `realpath` raises.
  Test it explicitly: an unresolvable workspace must not produce a record accusing the run of
  writing outside. This is the one place the design deliberately does not copy `_decide`, which
  refuses; see D4.
- [x] 3.5 Test the Windows cross-drive case (`commonpath` raises `ValueError`) and the case-only
  difference case, both of which `_decide` already handles and both of which this must handle the
  same way or the two will disagree about the same path.

## 4. Record it against the run

- [x] 4.1 Add `Run.outside_workspace_writes`, nullable JSON. `NULL` means *not observed*; `[]` means
  *observed, nothing left*. Do not backfill — migration `0096`'s own precedent for `workspace_dir`
  and `0043`'s for `snapshot_commit_sha`. A backfilled `[]` would claim every historical run was
  watched and found clean.

  *Landed 2026-09-04 (night N-17)*, directly under `workspace_dir` so the two comments are read
  together — the one that says where the run started, then the one that says where it wrote. The
  comment carries D12's warning as well as D5's semantics, because `[]` is simultaneously true and
  the least informative sentence this product emits for a run whose workspace *is* the project
  root, and a reader arriving at the column is exactly who would otherwise read it as confinement.
- [x] 4.2 **One** migration `0101` for both this column and task 5.2's, guarded for a missing table
  the way `0033`/`0034`/`0075`/`0095`/`0096` are — design D10. Head today is `0100`
  (`0100_loop_work_needs_evidence.py`), so `down_revision = "0100"`. Bump
  `hub/tests/test_migrations.py`'s `HEAD_REVISION = "0100"` **and**
  `hub/tests/test_project_persistence.py:227` (`assert version == "0100"`) to `0101`.

  *Corrected 2026-09-02 (night N-7), verified against the tree rather than assumed.* This task was
  written when `0099` was head and named `0100` for itself;
  `a-loop-declares-whether-it-needs-evidence` has since landed `0100_loop_work_needs_evidence.py`
  (`revision = "0100"`, `down_revision = "0099"`), and both head assertions already read `0100`.
  Writing this change's migration as `0100` would collide on the revision identifier and give
  `0099` two children. If a further migration lands before this change is implemented, re-derive
  the number the same way instead of trusting this line.

  *Landed 2026-09-04 (night N-17)* as `0101_outside_workspace_writes.py`, `down_revision = "0100"`,
  after re-deriving all three anchors against the tree rather than trusting the paragraph above —
  they still held. Both head assertions bumped to `0101`.

  Two things decided while implementing. **The guards are per table, not one combined guard**:
  `runs` and `evidence_footprints` enter the schema at different points, so an upgrade can arrive
  with one and not the other, and `if not all(present): return` would silently skip the table that
  *is* there. `test_migration_0101_adds_the_column_to_whichever_table_is_present` is what holds
  that, and it fails under exactly that mutation.

  And a blind spot worth stating rather than leaving for a later reader to trip on: **a migration
  test built on `_create_all_at` cannot prove the migration did anything.** `create_all` builds
  both tables from the models, columns included, so `0101` is a no-op on that path — measured, by
  deleting `evidence_footprints` from `_TABLES` and watching the both-tables test stay green. Only
  the downgrade-and-back-up test reaches `op.add_column`. Both docstrings now say so. `0100`'s
  first test has the same property and does not say so.
- [ ] 4.3 **Pass the project root down first.** Round 3 measured it: `repo_root` occurs nowhere in
  `_execute_run` (lines 1720-2274) or `_execute_codex_appserver_run` (2389-2752). `work_dir`,
  `run_id`, `project_id` and `agent` are all in scope; the project root, which D4 needs to compute
  `worktree_path`/`task_worktree_path`/`review_path` and to tell `project` from `outside`, is not.
  Add it as a parameter to both, from the trigger body that already computes it. Do **not** re-read
  the project row inside the callback: that is a query per tool call to answer a question that is
  constant for the run.
- [ ] 4.3a In `_flush_line` (`hub/hub/api/v1/agent_trigger.py:1880`), classify each event's
  `write_paths` against `work_dir` and the project root, and append the outside ones to the run.
  `work_dir`, `AW_WORKSPACE_DIR` and `Run.workspace_dir` are all `effective_work_dir` — use the value
  already in scope, never a workspace recomputed from the agent's name (design D4).
- [ ] 4.3b Do the same in `_on_event` (`hub/hub/api/v1/agent_trigger.py:2474`), the Codex app-server
  sink, which never reaches `_flush_line` and now has the same five values in scope. Without this the
  change covers two of three transports; round 1 covered one. Factor the classify-and-record step so
  the two sinks call one function rather than growing two opinions about it.
- [ ] 4.4 Bound the list at 20 entries plus a total count. An unbounded column on a run that writes
  in a loop is a column nobody can read.

  **Decide the top-level JSON shape here, deliberately — it is not decided yet.** Noted while
  landing 4.1/4.2 (night N-17): D5, D12 and task 4.1 all spell the empty case `[]`, which makes the
  column's value a *list*, while this task's "plus a total count" wants a scalar beside the list.
  Both are satisfiable — a list whose entries each carry their own per-destination count, with the
  overflow beyond 20 recorded as a final sentinel entry, keeps `[]` literally true — but the two
  sentences as written do not pick one, and the wiring is where it has to be picked. Whatever is
  chosen, `[] == observed and nothing escaped` and `NULL == not observed` are fixed by the column's
  own comment and by 4.1, and must survive it. The migration constrains neither: `sa.JSON` holds
  any of them.
- [ ] 4.4b **Accumulate in the closure; write on first sight of each destination** (design D5, round
  3). Both bounds above and the once-per-destination rule in 4.5 are per-*run* facts, and the only
  sites that see the calls are per-*event* callbacks each opening their own session. Hold a `dict`
  keyed by destination as a `nonlocal`, the same shape `sequence` and `accounting_sample` already
  use in both functions and safe for the same reason (each sink is awaited serially within a run,
  and only one of the two runs for any given run). On the **first** sighting of a destination, one
  transaction writes the `Run` column and emits 4.5's event together; later writes to a destination
  already recorded touch the closure only.
- [ ] 4.4c Do **not** flush the column at the run boundary the way `turn_produced_nothing` does. That
  is the natural reading of D5 as round 2 wrote it and it loses the whole record for a run that is
  killed or whose Hub restarts - exactly the runs whose stray writes matter. Add a test that kills a
  run mid-turn after one outside write and asserts the destination and its first path survived. The
  exact per-destination call count is best-effort at the boundary and is the only field it is safe
  to lose.
- [ ] 4.5 Emit `persist_event(..., "agent_wrote_outside_workspace", severity="warn")` naming the run,
  the agent, the tool, the path and the destination workspace — once per distinct destination per
  run, not once per call, in the same transaction as 4.4b's first-sighting write. Follow
  `turn_produced_nothing`'s **payload and severity** (`hub/hub/run_divergence.py:622-635`); do not
  follow its *timing*, which is `evaluate_run_end` — see 4.4c. Round 3 checked what this is allowed
  to record: `persist_event` carries 44 distinct event types in the shipped Hub and one of them is a
  refusal, so `agent-run-sandboxing`'s *"Only refusals SHALL be recorded"* was never a constraint on
  this event (design D9).
- [ ] 4.6 Recording must never be able to kill a turn. Wrap it the way `_report_decision` is wrapped:
  a failure here is observational, and a run that dies because a path could not be classified is a
  worse outcome than one that wrote outside unnoticed.
- [ ] 4.7 Expose the column on the run schema so a reader can see it, and flip tasks 1.2 and 1.3:
  the record exists, and the cross-worktree case names the *other* agent's workspace by kind and
  name. **Task 1.1 is not in this list and does not need to be** — checked 2026-09-04 rather than
  assumed, when `write_paths` landed and turned 1.1 red on its `fields(RunEvent)` assertion. 1.1 is
  the parse side, so phase 2b flipped it in the same commit that broke it; 1.2 and 1.3 are the
  record side and are still red-free today because nothing is recorded yet.

## 5. Teach evidence footprinting about it

- [ ] 5.1 Add `outside_writes_for_run(session, run_id)` beside `recorded_workspace_dir`
  (`hub/hub/requirement_evidence.py:343`) — the same one-row read, on the same row.
- [ ] 5.2 Carry the fact onto `EvidenceFootprint` through `_apply_footprint`
  (`hub/hub/requirement_evidence.py:362`) and nowhere else, so capture and re-capture cannot come to
  disagree about what a footprint means. As an **explicit parameter**, not a field on `Footprint`:
  that value is built from git alone and this fact is database state on `Run`, so `Footprint` cannot
  derive it and `restamp_run_footprints` (`:845`, `_apply_footprint` at `:921`) would have to
  fabricate it — design D11. Both call sites (`:423`, `:921`) pass what they read from the run. The
  column rides migration `0101` from task 4.2; there is no second migration and no second head bump.

  *The column is named, so phase 5 does not have to guess.* It shipped with `0101` on 2026-09-04
  (night N-17) as **`EvidenceFootprint.outside_workspace_writes`** — deliberately the same name as
  the `Run` column, because it holds the same value with the same two readings and a second name
  would invite a reader to look for a second meaning. Nullable JSON, no server default: NULL is
  *not observed*, which is what `_apply_footprint`'s parameter defaults to and what
  `restamp_run_footprints` passes when it has nothing to pass.
- [ ] 5.3 Do **not** change which directory the footprint is taken from, and do **not** refuse the
  evidence. Design D7 rules both out; add a test that asserts the footprint root is unchanged for a
  run that wrote outside, so a later reader cannot "fix" this by moving it.
- [ ] 5.4 Report it in the response that already reports the captured footprint, since the shipped
  requirement is that the recorder can see which tree their evidence was attached to at the moment
  they can still correct it.
- [ ] 5.5 Correct `footprint_root`'s docstring — *"The directory whose HEAD is the work this evidence
  is about"* — which is true only when nothing escaped.

## 6. Say what the recorded directory means

- [ ] 6.1 Correct the comment on `Run.workspace_dir` (`hub/hub/db/models.py:1133-1148`): it records
  where the run started and is not a statement that the run's writes stayed there.
- [ ] 6.2 No behaviour change here and no migration — part (1) is a specification change (design D6).
  Grep for any other reader of `workspace_dir` that treats it as containment and correct or file it.

## 7. Document the postures

- [ ] 7.1 Document, per posture, whether a file write is checked against the run's workspace:
  `workspace` — checked by the Hub; `manual` — put to the operator; `acceptEdits` — not checked;
  full access — not checked. Docker mode confines at the mount whatever the posture.
- [ ] 7.2 Say plainly that a workspace is a working directory rather than a wall, that where no
  posture is checking the operator is the boundary, and that a write which leaves the workspace is
  recorded rather than prevented.
- [ ] 7.3 Do not write "native mode does not confine". It is false for the default posture — see the
  round-1 correction in `proposal.md`.

## 8. File what is out of scope

- [ ] 8.1 File a finding for shell-command writes: a `Bash`/`shell` call carries a command string, so
  `echo x > /abs/path` names no path this check can see.
- [ ] 8.2 File a finding for symlink traversal: a link inside the workspace pointing out reports a
  path that is legitimately inside.
- [ ] 8.3 Neither is fixed here, and neither is implied by this change's label. Check the label in
  the UI and in the event payload once written: it must read *wrote outside the workspace*, never
  *escaped*.

## 9. Gates

- [ ] 9.1 `pytest hub/tests/ -v` — full suite, in the background or in chunks; it exceeds the command
  cap. Attribute the test-count difference node by node against the baseline, not by totals.
- [ ] 9.2 `pytest tests/ -v` for the CLI, separately — collecting both together fails.
- [ ] 9.3 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`, `mypy src/`.
- [ ] 9.4 Drive it live against a Hub on 8011 confirmed to serve this code: a Haiku agent, an
  absolute-path `Write` outside its worktree, under a posture that permits it. Assert the run row and
  the activity event, not just the test. A passing suite is not proof of behaviour, and this change
  exists because a live drive found what the suite could not.
- [ ] 9.5 `openspec validate --strict` on the change, then sync every delta into `openspec/specs/`
  by verbatim header — the ADDED requirements in `agent-run-sandboxing` and `workspace-isolation`,
  the MODIFIED requirement in `requirement-traceability`, and the now-minimal MODIFIED requirement
  *A refusal is recorded wherever it is decided* in `agent-run-sandboxing` (design D9, as corrected
  in round 3: two words plus one sentence of scope, nothing more) — then archive. `--strict` does not
  compare capabilities, so a missed delta validates clean; verify the sync by grep, not by exit code.


## 10. What round 2 added

- [ ] 10.1 **Superseded by round 3.** Round 2 read *"Only refusals SHALL be recorded"* as a
  constraint on every durable event and modified the shipped requirement to accommodate this change.
  The premise is false — 44 distinct `persist_event` types ship today and one is a refusal — so the
  MODIFIED delta keeps only the two-word clarification (*"as refusals"*, which the requirement's own
  fourth scenario already says) plus one sentence naming its scope. The paragraph legislating
  "allowed actions that are not ordinary" is removed: it wrote this change's policy into a
  requirement about refusals. Design D9.
- [ ] 10.2 The scenario that pins it moves to this change's **own** ADDED requirement, where the fact
  lives: *The record is not a refusal*. Assert it against the event payload, so the label check in
  task 8.3 has something to fail against.
- [x] 10.4 Test the classification of a path under `<root>/.agentweave/` that is not a worktree, task
  or review checkout — `.agentweave/evidence/x` is the sharp case, being the Hub's own record-keeping
  about runs. It must classify as `hub`, never `project` (design D4, task 3.1b).
- [ ] 10.5 Test the run whose workspace **is** the project root (design D12): a read-only agent, or a
  project that is not a git repository. Writing anywhere in the project records nothing, including
  into another agent's worktree. Assert that, and assert the requirement's wording does not let the
  empty record read as confinement.
- [ ] 10.3 Test the review-turn case explicitly. A review run's workspace *is* the detached review
  checkout (`agent_trigger.py:824`), so a reviewer writing into its own agent worktree is a write
  outside its workspace and is recorded as one. That is correct and it should be a test rather than
  a surprise found later.
