## 1. Reproduce it first

- [ ] 1.1 Add `hub/tests/test_a_write_outside_the_workspace_is_recorded.py`. Build F115's shape from
  the parse side: feed `parse_claude_line` a real `assistant` line carrying a `tool_use` block for
  `Write` with an absolute `file_path` outside the workspace, and assert the current behaviour — the
  parsed events carry the path only inside `payload["input"]` as a stringified blob, and nothing
  anywhere says it was outside anything. Run it against unmodified code and confirm it passes. A
  reproduction that does not pass first is not a reproduction.
- [ ] 1.2 Add the record side: a `Run` with `workspace_dir` set to an agent worktree, and assert that
  after a turn containing that call the run carries no record of an outside write and no activity
  event mentions one. Confirm it passes against unmodified code.
- [ ] 1.3 Add the cross-worktree shape: the same call, but with the absolute path inside a *second*
  agent's worktree under the same project. Assert that today nothing distinguishes it from the
  previous case. This is the case whose whole meaning is the destination.
- [ ] 1.4 Pin the round-1 correction as a test rather than a claim: assert that `mcp_server._decide`
  **refuses** the same absolute path under the default posture, so the record of what the default
  posture does is in the suite and not only in this proposal. If it does not refuse, stop — the
  proposal's premise is wrong and rounds 2 and 3 need to know before anything is built.

## 2. Extract write paths at the parse point

- [ ] 2.1 Add `hub/hub/workspace_writes.py`: pure, stdlib-only, no session and no filesystem writes.
  It owns the two halves that must not drift apart — which tools write, and where a path belongs.
- [ ] 2.2 `written_paths(tool: str, input_data: Any) -> tuple[str, ...]` — the declared path
  argument(s) of a file-*writing* tool call, empty for everything else. Claude: `Write`, `Edit`,
  `MultiEdit`, `NotebookEdit`. Codex: `apply_patch`. Reads (`Read`, `Glob`, `Grep`, `LS`) return
  empty, per design D3. An unknown tool returns empty rather than guessing from key names: a
  detector that invents coverage is the failure mode this whole change is careful about.
- [ ] 2.3 Cover the multi-path case. `MultiEdit` and `NotebookEdit` must be read from their real
  input shapes, not assumed — round 2 owes an answer on whether one call can name more than one
  file, and this function returns a tuple so that it can.
- [ ] 2.4 Add `write_paths` to `ParsedLine` (`hub/hub/runner_parsing.py:51`), carrying tool name,
  call id and the raw path string — nothing else. Populate it in `parse_claude_line`'s `tool_use`
  branch from `block.get("input", {})`, **before** `tool_use_event` is called, because that
  constructor redacts, stringifies and truncates at 8 KiB and the structured path may not survive it
  (design D2).
- [ ] 2.5 Populate the same field on the Codex side for the `fileChange` item
  (`hub/hub/codex_appserver.py:449-459`). Verify the `changes` element's real shape from a recorded
  Codex item before writing the extractor; do not read it off `_file_change_summary`.
- [ ] 2.6 Assert the parser stays pure: no workspace argument, no filesystem access, no import of
  anything that touches the database. A test that imports `runner_parsing` in isolation is enough to
  keep this honest.

## 3. Classify a path against the run's workspace

- [ ] 3.1 In `workspace_writes.py`, add `classify(path, *, workspace_dir, project_root)` returning a
  workspace kind and name: `agent`/`task`/`review` from the layout helpers in `worktrees.py`
  (`worktree_path`, `task_worktree_path`, `review_path`), `project` for the project's own directory,
  `outside` for anything else. Kind-and-name, per design D4 and `workspace-isolation`'s existing
  requirement that a reported workspace says which namespace it belongs to.
- [ ] 3.2 Compare on `os.path.realpath` + `os.path.commonpath` + `os.path.normcase`, the same
  construction `mcp_server._decide` uses (`hub/hub/mcp_server.py:900-914`) and for the same stated
  reasons: `commonpath` compares components so `/work-other` does not read as inside `/work`, and
  realpath collapses `..` and symlinks before the comparison. Relative paths resolve against the
  workspace, which is the run's cwd.
- [ ] 3.3 Return "inside" for a path within the run's own workspace, and record nothing for it.
- [ ] 3.4 Return "unknown" — never "outside" — when `workspace_dir` is absent or `realpath` raises.
  Test it explicitly: an unresolvable workspace must not produce a record accusing the run of
  writing outside. This is the one place the design deliberately does not copy `_decide`, which
  refuses; see D4.
- [ ] 3.5 Test the Windows cross-drive case (`commonpath` raises `ValueError`) and the case-only
  difference case, both of which `_decide` already handles and both of which this must handle the
  same way or the two will disagree about the same path.

## 4. Record it against the run

- [ ] 4.1 Add `Run.outside_workspace_writes`, nullable JSON. `NULL` means *not observed*; `[]` means
  *observed, nothing left*. Do not backfill — migration `0096`'s own precedent for `workspace_dir`
  and `0043`'s for `snapshot_commit_sha`. A backfilled `[]` would claim every historical run was
  watched and found clean.
- [ ] 4.2 New migration in `hub/hub/migrations/versions/`, guarded for a missing table the way
  `0033`/`0034`/`0075`/`0095`/`0096` are. Bump the head assertions in
  `hub/tests/test_migrations.py` **and** `hub/tests/test_project_persistence.py`.
- [ ] 4.3 In `_flush_line` (`hub/hub/api/v1/agent_trigger.py:1877`), classify each of
  `parsed.write_paths` against `work_dir` and the project root, and append the outside ones to the
  run. `work_dir`, `AW_WORKSPACE_DIR` and `Run.workspace_dir` are all `effective_work_dir` — use the
  value already in scope, never a workspace recomputed from the agent's name (design D4).
- [ ] 4.4 Bound the list at 20 entries plus a total count. An unbounded column on a run that writes
  in a loop is a column nobody can read.
- [ ] 4.5 Emit `persist_event(..., "agent_wrote_outside_workspace", severity="warn")` naming the run,
  the agent, the tool, the path and the destination workspace — once per distinct destination per
  run, not once per call. Follow `turn_produced_nothing`
  (`hub/hub/run_divergence.py:622-635`) exactly; it is the shipped answer to "record it and surface
  it to the operator".
- [ ] 4.6 Recording must never be able to kill a turn. Wrap it the way `_report_decision` is wrapped:
  a failure here is observational, and a run that dies because a path could not be classified is a
  worse outcome than one that wrote outside unnoticed.
- [ ] 4.7 Expose the column on the run schema so a reader can see it, and flip tasks 1.2 and 1.3:
  the record exists, and the cross-worktree case names the *other* agent's workspace by kind and
  name.

## 5. Teach evidence footprinting about it

- [ ] 5.1 Add `outside_writes_for_run(session, run_id)` beside `recorded_workspace_dir`
  (`hub/hub/requirement_evidence.py:343`) — the same one-row read, on the same row.
- [ ] 5.2 Carry the fact onto `EvidenceFootprint` through `_apply_footprint`
  (`hub/hub/requirement_evidence.py:365`) and nowhere else, so capture and re-capture cannot come to
  disagree about what a footprint means. Column, migration and head bumps as in 4.2.
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
- [ ] 9.5 `openspec validate --strict` on the change, then sync all three deltas into
  `openspec/specs/` by verbatim header, then archive. `--strict` does not compare capabilities, so a
  missed delta validates clean — verify the sync by grep, not by exit code.
