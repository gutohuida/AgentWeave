> **Moved to the app 2026-10-16, archived.** Successor: `spec/changes/a-call-mode-turn-starts-with-an-empty-calls-directory/spec.json` (built 6fdf5ff; folded into `agent-run-sandboxing` and `agent-tool-surface`). D1-D4 were built as written. wpc4-b (warn and proceed) was taken as recommended; wpc4-c and wpc4-e stay open.

# Proposal — A call-mode turn starts with an empty calls directory and is told to name each file afresh

Round 1, 2026-10-12; verified by Round 2 the same day. Findings WPC-4 and WPC-5 from `.claude/work-pc/handoff-0162-2026-10-12-copilot-drive.md`.
Written against HEAD `6208e9a5`. Nothing here is implemented yet.

## Why

In call mode (the "shim"), a run reaches the Hub by writing a JSON arguments file under
`.agentweave/calls/` and running `aw-tool <tool> <file>`. Both texts that describe this give the same
example name. The turn-start notice (`hub/hub/launchability.py:454-475`) says "for example
`aw-tool create_task .agentweave/calls/1.json`". The context preamble (`hub/hub/api/v1/agents.py:1789-1806`)
says to write "a `.json` file inside `.agentweave/calls/`".

`prepare_calls_dir` (`hub/hub/api/v1/agent_trigger.py:250-279`) makes the directory real at turn
start. It removes a link found in its place and ends with `os.makedirs(..., exist_ok=True)`, but it
never removes a file. The comment at its call site (`:1440`) says the directory is "made fresh", and
that is not true. Design D14 of the archived `2026-10-02-a-run-reaches-the-hub-without-mcp` decided
this on purpose: "The files are not deleted by the shim, because the agent may reuse them. They are
the agent's scratch." The drive shows what that decision costs.

The trial database for the work-PC drive (`profiles/workpc-drive/agentweave.db`, read-only) has four
shim runs. All are by agent `cop-1` in its own worktree
`…\proj-1012-095734\.agentweave\worktrees\cop-1`, and none is bound to a task.

| Run | Conversation | What the args-file write did | Total tokens |
|---|---|---|---|
| `run-08d33fa23f8e` | new | `create` of `calls\1.json` succeeded | 74,682 |
| `run-a8245d9b1a1b` | **new** | `create` failed "Path already exists" (seq 4); `edit` failed "No match found" (seq 6); read the leftover file (seq 9); `edit` succeeded (seq 11) | 152,481 |
| `run-335903d6e932` | same as the first | the agent chose `2.json` and succeeded | 98,625 |
| `run-6a6a40f3ae69` | **new**, spec turn | "Disabled tools: edit" (seq 3); `create` of `calls\1.json` failed **"Path already exists"** (seq 6–7); fell back to `Set-Content` (seq 8–9), which was allowed | 103,730 |

**WPC-4 is confirmed.** A new conversation does not know that `1.json` is already on disk. It follows
the example, and Copilot's `create` refuses to overwrite. The second run cost about twice the first.
Most of the extra was cache reads (135,048), so the premium-request count stayed at 1.0.

**Which runners pay it (R2).** Every runner can be told the shim path. The *tool* refusal is
Copilot's `create`, and also Claude Code's `Write` on Opus 4.6, Haiku 4.5 and older models, which
refuse to overwrite a file that has not been read, and OpenCode's `write` before about v1.17.9,
which refused an unread existing file (R3). Newer Claude models, Codex's add-file, Kimi's
`WriteFile` and current OpenCode's `write` overwrite. On those runners the leftover is still a stale file a model may call `aw-tool` on without
rewriting it: in `run-a8245d9b1a1b` it held another call's arguments (title `WORKPC-SHIM`). Emptying
the directory removes that hazard for every runner (design D2).

**WPC-5 as reported does not hold.** The handoff says that a Copilot spec turn loses `edit`, so the
first write failed. But `create` is deliberately kept on spec turns (`hub/hub/copilot_acp.py:136-142`).
The spec turn's failed call was `create` refusing the same leftover `1.json`, which is WPC-4 again.
What the spec turn does lack is a way to *replace* a file. `edit` is excluded there, so a name reused
within one spec turn leaves only `Set-Content`. That fallback already has standing in every posture
(`_hub_own_powershell_write`, `hub/hub/mcp_server.py:3388-3433`), and the drive shows it was allowed.

So both findings have one cause, the leftover file, and one residual, a name reused within a turn.
Neither needs a spec turn to gain a write tool.

## What Changes

- At turn start the Hub empties the calls directory **when the workspace is isolated**: the agent's
  own worktree, a task's checkout, or a review checkout. These are the cases where the trigger
  already sets `isolated_workspace`. Only this turn stands in an agent's own worktree or review
  checkout. A task checkout can be
  shared by two agents only through a pre-existing race in the one-turn-per-task refusal (design D1,
  open question wpc4-d). Links found inside the directory, including Windows junctions, are removed
  as links, without touching their targets.
- It does **not** empty a calls directory in a workspace several agents share. That covers the project
  directory, used by read-only agents and by projects that are not repositories, and an explicit
  `work_dir`. Emptying there could delete another agent's arguments file while that agent is still
  running (design D1). An explicit `work_dir` may also name another agent's worktree or checkout,
  which that agent's own turn *does* empty; that gap is open question wpc4-e (R3).
- If emptying fails, the Hub logs a warning and the turn proceeds. Failing to *make* the directory is
  still refused as it is today (design D3).
- Both shim texts tell the run to use a new file name for each call, and to write corrected arguments
  to a new file rather than editing an old one, because the file-writing tool may refuse to overwrite.
  The example `1.json` stays (design D2).
- Copilot's spec-turn exclusions are unchanged. `edit` stays excluded (design D4).
- The call-site comment and the `prepare_calls_dir` docstring are corrected. D14's "the agent may
  reuse them" is reversed, and this change says so.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing`: an ADDED requirement saying that a calls directory in a workspace only this
  turn occupies starts the turn empty.
- `agent-tool-surface`: an ADDED requirement saying that a run told the call command is told to name
  each arguments file afresh.

## Impact

- `hub/hub/api/v1/agent_trigger.py`: `prepare_calls_dir` gains a required keyword-only argument that
  says whether to empty the directory, and its call site passes `isolated_workspace is not None`.
- `hub/hub/launchability.py` and `hub/hub/api/v1/agents.py`: one added sentence in each shim text.
- `.github/workflows/ci.yml`: the new test file joins the `hub-judge-windows` job, so the junction
  case runs on Windows.
- Tests: a new `hub/tests/test_calls_dir_starts_clean.py`. The existing link tests at
  `test_agent_trigger.py:3566-3610` are parametrized over the new keyword. The existing pins should
  stay green, because none of them asserts the full text: `test_launchability.py:594-606`,
  `test_hub_own_call.py:521-541` (`NOTICE_FORM`), `test_agent_trigger.py:933`,
  `test_agent_facing_text.py`, `test_aw_tool_help.py` and
  `test_tool_surface_matches_server.py:463-489`.
- **No snapshot regenerates.** `test_copilot_context_split.py` renders `access_path="mcp"` only, and
  its fixture `context_split_claude_snapshot.md` contains no `aw-tool` or `calls` text.
- No migration, no UI change, no change to the approver. Nothing reads an earlier turn's call files:
  the UI never touches them, `repo_hygiene.py:76` git-excludes them, and the Hub's only readers are
  the call command (`_read_call_args`) and the approver, both within the current turn. The drive
  script `scripts/drive/d1001_shim_drive.py:126` lists a run's files after it ends, before any next
  turn empties them.
