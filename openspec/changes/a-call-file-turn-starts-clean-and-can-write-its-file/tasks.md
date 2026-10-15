# Tasks — A call-mode turn starts with an empty calls directory and is told to name each file afresh

## 0. Rounds and decision

- [x] 0.1 R2: compare the proposal against the code independently. Done 2026-10-12 on the work PC;
  see the R2 round-log entry in `design.md`.
  - Trace every reader of `.agentweave/calls/` again: hub, CLI, UI, scripts.
    *R2: the Hub's two readers only. Nothing in `src/` or `hub/ui/src`. One script,
    `scripts/drive/d1001_shim_drive.py:126`, reads the run's own files after the run, which D1 does
    not affect.*
  - Confirm that every path into `_trigger_agent_directly` (the `/agent/trigger` route, `spec.py:880`,
    `turn_scheduler.py:379`) passes the one-run-per-agent guard (`agent_trigger.py:1000-1006`) before
    `prepare_calls_dir`.
    *R2: yes. The route (`:2039`) and `spec.py:879` both reach it through `schedule_agent`, and
    `turn_scheduler.py:379` is the only caller.*
  - Decide whether that guard is atomic against two concurrent triggers of the same agent. If it is
    not, D1's "nobody else stands in it" is false for the agent's own worktree.
    *R2: atomic within one Hub process, through `_lock_for(project, agent)` held across the trigger
    and its commit. Not atomic across two Hub processes on one database, which is out of scope. The
    D8 per-task refusal is **not** atomic across two different agents (wpc4-d).*
  - Confirm that `isolated_workspace` is set exactly for the agent's own worktree, a task checkout and
    a review checkout.
    *R2: yes (`:1238`, `:1318`). It is `None` at `:1229` and when the workspace is `repo_root`. It
    is not reassigned before `:1444`.*
- [x] 0.2 R3: re-derive the WPC-5 reframing independently. Done 2026-10-12 on the work PC; see the
  R3 round-log entry in `design.md`.
  - From the trial database (`run-6a6a40f3ae69` seq 6–7), confirm that the failed spec-turn write was
    `create` refusing an existing path, not a disabled tool.
    *R3: yes. Seq 6 is a `create` of `calls\1.json`; seq 7 is the tool's own "Path already exists",
    not a permission refusal.*
  - Confirm that `_standing_rules` allows a calls-root `create`, in its ACP shape, on a spec turn.
    *R3: yes, run directly. `decide_permission` on `kind` `edit`, `rawInput{path, file_text}`,
    `locations`, diff `content`, `spec_turn=True`: ALLOW for `<ws>/.agentweave/calls/2.json`, REJECT
    "a specification turn writes no file" for `<ws>/spec/x.html`, in all four postures.*
  - Re-check D2's runner table against the sources it cites. *R2 answered the original question
    (Claude's `Write` refuses an unread file on older models; Codex's add-file overwrites). R3
    should re-verify it, not take it on trust.*
    *R3: Claude and Codex re-checked against their sources and hold. Added Kimi (`WriteFile`
    overwrites) and OpenCode (overwrites now; refused an unread file before about v1.17.9).*
  - Run `npx openspec validate a-call-file-turn-starts-clean-and-can-write-its-file --strict`.
    *R3: valid.*
  - *R3 also confirmed:* the clear step is inside `schedule_agent`'s per-agent lock; every turn path
    (trigger route, reconcile, ask_user resume, scheduled and retried firings, task and review
    dispatch) reaches the one call site at `:1444`; and R2's realpath link test is correct for a
    junction directly in `calls`, inside a subdirectory, and dangling. `rmtree` does not follow a
    nested junction. Symlinks were not measurable here (no privilege). New open question wpc4-e.
- [ ] 0.3 The operator answers wpc4-a, wpc4-b, wpc4-c, wpc4-d, wpc4-e and wpc5-a (`design.md`, "Open
  questions"). Record the answers in `spec-queue/DECISIONS.md` and amend D1 to D4 to match before §1.

## 1. Tests first — each must fail on today's code unless marked as a control

A control pins behaviour D1 must not disturb. A control that passes `empty=` (1.2, 1.5) still fails
today, on the keyword alone; that is expected, and it is not evidence of the behaviour (R3). Only
1.7, 1.9, 1.10 and 1.11 pass on today's code.

All of these go in a new `hub/tests/test_calls_dir_starts_clean.py` unless another file is named.

- [ ] 1.1 `prepare_calls_dir(work, empty=True)` on a directory holding `calls/1.json` and
  `calls/sub/2.json` leaves `calls` an empty real directory. Fails today: the keyword does not exist,
  and the files survive.
- [ ] 1.2 Control. `prepare_calls_dir(work, empty=False)` keeps `calls/1.json`. This is the
  shared-workspace case.
- [ ] 1.3 Links inside `calls`, each pointing to a directory holding `keep.txt`. Use the `_link_dir`
  helper from `test_agent_trigger.py`, which makes a junction on `nt` and a symlink elsewhere. Two
  cases, parametrized:
  - (a) the link sits **directly** in `calls` (`calls/j`);
  - (b) the link sits inside a real subdirectory (`calls/sub/j`).

  In both, emptying leaves `calls` empty, and `keep.txt` survives. Case (a) is the one that matters.
  On Windows, an implementation that tests `os.path.islink` and sends a junction to `shutil.rmtree`
  raises, D3 swallows the error, and the junction survives, so the assertion that `calls` is empty
  fails (design D1, R2). Also assert that no warning is logged for case (a). This fails today only on
  the keyword; it pins D1's detection so a later rewrite cannot regress it. On Linux `_link_dir`
  makes a symlink, which every implementation handles, so **case (a) only bites on Windows**. Hub
  tests run on Windows CI only in the `hub-judge-windows` job (`.github/workflows/ci.yml:161-197`),
  which runs two named files, so task 2.6 adds this file to it.
- [ ] 1.4 Patch `os.unlink` to raise `PermissionError` for one file. `prepare_calls_dir(work,
  empty=True)` returns without raising, logs one warning naming the path, and removes the others.
  Add a real variant under `skipif(os.name != "nt")`: hold `calls/1.json` open with `open()` (which
  gives WinError 32 on unlink) and assert the same, plus that `calls/2.json` is gone.
  If wpc4-b is answered "refuse", assert the trigger's 409 instead.
- [ ] 1.5 Control. The existing link tests in `test_agent_trigger.py:3566-3610` call
  `prepare_calls_dir(str(work))` with no keyword. Since `empty` is required (2.1), they must change.
  Parametrize them over `empty` (`True`, `False`); do not copy them. They then assert, as before,
  that a linked `calls` or `.agentweave` is handled the same either way, and the link's target is
  kept.
- [ ] 1.6 Route-level. The autouse fixture `_no_real_worktree_provision`
  (`hub/tests/conftest.py:1034-1064`) stubs the workspace resolvers to return the repository root, so
  under it no trigger is isolated. Follow `test_writing_agent_worktree_exists_before_first_spawn`
  (`test_agent_trigger.py:396-427`) instead: a `tmp_path` git repository (`_init_repo`),
  `bind_project_workspace`, `monkeypatch.setattr(worktrees, "resolve_agent_workspace",
  _REAL_RESOLVE_AGENT_WORKSPACE)`, and `PtySession.spawn` patched. Make the agent's worktree first
  (trigger once, or call the worktree creator), seed `.agentweave/calls/1.json` and
  `.agentweave/calls/sub/2.json` in it, trigger through `trigger_agent_directly`, and assert from
  inside the patched spawn (its `cwd` kwarg) that the directory is empty at spawn time. Fails today.
- [ ] 1.7 Route-level control, with the same real-resolver setup. Do the same for a read-only agent,
  whose workspace is the project directory (as near `test_agent_trigger.py:518-541`). The seeded
  file survives. Passes today, since nothing empties; it guards against an implementation that
  empties every workspace.
- [ ] 1.8 `access_path_notice("shim", …)` and `_tool_surface_lines(access_path="shim", …)` both
  contain the D2 sentence: "a new file name for each call". Fails today. Add it beside
  `test_launchability.py:594-606`, and add the preamble half to the test that pins the preamble.
- [ ] 1.9 Control. `test_hub_own_call.py:521-541` (`NOTICE_FORM` in the notice, the preamble and the
  decode error, with the filled form having standing) passes unchanged. So does
  `test_agent_trigger.py:933`, which asserts the rendered prompt contains
  `aw-tool create_task .agentweave/calls/1.json`.
- [ ] 1.10 Control. Copilot's spec-turn argv still carries
  `--excluded-tools=apply_patch,edit,str_replace_editor`
  (`test_copilot_acp_run_turn.py:1613-1657`, `:3905-3907`). If wpc5-a is answered (a), this
  becomes a failing test for the new argv.
- [ ] 1.11 Control, in `test_copilot_acp_decide.py` beside `:1153-1171`. A spec-turn permission
  request in the shape the drive's `create` makes (`kind` `edit`, `rawInput{path, file_text}`,
  `locations[{path}]`, `content[{type: "diff", path, oldText: "", newText}]`) is ALLOWED for
  `<ws>/.agentweave/calls/2.json` and REJECTED for `<ws>/spec/x.html` in every posture, including
  `bypassPermissions`. Passes today (R3 ran it). The existing
  `test_an_args_file_edit_has_standing_with_an_absolute_path` and the refusal test after it already
  cover the workspace and `manual` postures with `rawInput.path`; this adds the full-access posture
  and the `create` shape with `file_text` and diff content. Do not use `changes[…]`: that is the
  mapper's derived `input_data`, not the request.

## 2. Implementation

- [ ] 2.1 `agent_trigger.prepare_calls_dir(work_dir, *, empty: bool)`, with `empty` keyword-only and
  without a default: after `makedirs`, when `empty` is true, remove each entry of `calls`.
  - A link or junction is detected with the function's own test,
    `normcase(realpath(entry)) != normcase(entry)`, **not** `os.path.islink`, which is `False` for a
    junction. It is removed as a link: `os.rmdir` on `nt` when it `isdir`, otherwise `os.unlink`.
    Factor the existing branch at `:268-274` into one helper that both uses share.
  - A file is unlinked.
  - A real directory is removed with `shutil.rmtree`.
  - Each removal is caught as `OSError` and logged as a warning.

  Update the docstring: D14's "may reuse" is reversed, and the reason is stated.
- [ ] 2.2 Call site (`agent_trigger.py:1440-1449`): pass `empty=isolated_workspace is not None`, and
  correct the "made fresh" comment so it says when the directory is emptied and why a shared one is
  not.
- [ ] 2.3 Add the D2 sentence to `launchability.access_path_notice` (shim) and to
  `agents._tool_surface_lines` (shim preamble). Keep every phrase the pins assert.
- [ ] 2.4 Run `pytest hub/tests/test_calls_dir_starts_clean.py hub/tests/test_agent_trigger.py
  hub/tests/test_hub_own_call.py hub/tests/test_launchability.py hub/tests/test_agent_facing_text.py
  hub/tests/test_aw_tool_help.py hub/tests/test_tool_surface_matches_server.py
  hub/tests/test_copilot_acp_decide.py hub/tests/test_copilot_acp_run_turn.py
  hub/tests/test_copilot_context_split.py -q`. Then run `ruff`, `black --check --target-version py311`
  and `mypy` as CI does.
- [ ] 2.5 Sync the two ADDED requirements into `openspec/specs/agent-run-sandboxing/spec.md` and
  `openspec/specs/agent-tool-surface/spec.md` when the change is archived.
- [ ] 2.6 Add `tests/test_calls_dir_starts_clean.py` to the `hub-judge-windows` job's pytest line in
  `.github/workflows/ci.yml`, so 1.3(a) and the held-file variant of 1.4 run on a Windows runner
  (R2).

## 3. Live verification

- [ ] 3.1 On a trial Hub (never `:8000`), with a Copilot agent in call mode in its own worktree, run a
  shim turn that calls `create_task`. Then, in a **new conversation**, run a second shim turn that
  calls `ask_user`. In `agent_outputs` for the second run, check that there is no "Path already
  exists" and no "No match found", and that the `create` and `aw-tool` steps succeeded. Its
  `turn_usage` total should be near the first run's, not about double.
- [ ] 3.2 In a new conversation, run a shim spec turn that submits a document. Check that the first
  `create` of the turn succeeds, with no `Set-Content` fallback needed, and that the diagnostic still
  reads "Disabled tools: edit".
- [ ] 3.3 Run a turn that makes two calls. Check that it uses two file names.
