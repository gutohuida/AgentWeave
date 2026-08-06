# Tasks — Claude non-yolo permission mode

## 1. `_build_claude_command` sets an explicit permission mode

- [x] 1.1 Update the existing tests in `hub/tests/test_runner_parsing.py::TestBuildCommandClaude`
      that assert the exact full argv list or the permission flag's total absence for a non-yolo run
      (`test_new_session_minimal`, `test_claude_proxy_and_native_use_the_same_construction`) to expect
      `--permission-mode manual`. Add new tests: non-yolo run includes `--permission-mode manual`;
      yolo run does NOT include `--permission-mode manual` (still gets
      `--dangerously-skip-permissions` only, unchanged from today).
- [x] 1.2 In `_build_claude_command`, replace the current `if yolo: cmd += [...]` block (which adds
      nothing when `yolo` is false) with a branch that adds `--permission-mode manual` in the `else`.
- [x] 1.3 Run the updated and new tests; confirm they fail before 1.2 and pass after. Confirmed: 4
      tests failed pre-fix (`test_new_session_minimal`,
      `test_no_yolo_sets_explicit_manual_permission_mode`,
      `test_no_yolo_with_mcp_command_allowlists_agentweave_tools`,
      `test_claude_proxy_and_native_use_the_same_construction`), all pass post-fix.

## 2. `--allowedTools` for the Hub's own MCP server on non-yolo runs

- [x] 2.1 Add tests: a non-yolo run with `mcp_command` set includes
      `--allowedTools mcp__agentweave__*`; a non-yolo run with no `mcp_command` does NOT include
      `--allowedTools`; a yolo run with `mcp_command` set does NOT include `--allowedTools` (yolo
      already bypasses everything, the allowlist would be redundant argv).
- [x] 2.2 Add a test that fails if the `"agentweave"` mcpServers key and the `"mcp__agentweave__*"`
      allowlist pattern's server-name segment ever diverge — see design.md Decision 2's "no shared
      constant" risk. Implemented as `test_no_yolo_with_mcp_command_allowlists_agentweave_tools`:
      derives the expected allowlist string from the mcpServers key read out of the same command's
      own `--mcp-config` JSON, rather than hardcoding `"mcp__agentweave__*"` a second time in the
      test.
- [x] 2.3 In `_build_claude_command`'s existing `if mcp_command:` block, after the `--mcp-config` flag
      is appended, add `--allowedTools "mcp__agentweave__*"` when `not yolo`.
- [x] 2.4 Run the full `hub/tests/test_runner_parsing.py` file; confirm all tests pass, not just the
      new ones. 55 passed.

## 3. Full-suite and live verification

- [x] 3.1 Run the full `hub/tests/` suite. Confirm no other test asserted the old (missing-flag)
      non-yolo Claude command shape. `test_agent_tool_surface_phase7.py` and
      `test_runner_command_overrides.py` also call `build_command(runner="claude", ...)` but only
      assert index-based lookups or self-relative equality, not a full fixed argv list — unaffected.
      Full suite: 725 passed, 9 skipped (720 baseline + 5 new tests), zero failures.
- [x] 3.2 **Live:** spawned a real, non-yolo Claude agent (`live-verify-claude`, project
      `proj-de54b547`, runner `native`) through the actual running Hub (`127.0.0.1:8010`, restarted to
      pick up the fix) — not a standalone CLI probe. Two runs (`run-95a45321`, `run-bbf649cf`)
      confirmed both halves of the fix through the Hub's real spawn path: an unprompted built-in
      `Read` tool call (not an `agentweave` MCP tool) was refused with the exact undifferentiated
      message Decision 6 predicted (`"Claude requested permissions to read from ..., but you haven't
      granted it yet."`) — proof `--permission-mode manual` is real now, not silently overridden by
      this machine's own `bypassPermissions` setting as it was before the fix; `mcp__agentweave__list_tasks`
      and `mcp__agentweave__send_message` both succeeded (`is_error: false`) in the same runs — proof
      `--allowedTools "mcp__agentweave__*"` keeps the Hub's own tools usable under the now-real
      sandbox. The specific out-of-workspace `Write` scenario was not separately triggered: this
      project's own agent charter ("External Agent Rules") instructs the agent to take no file action
      until declared in `agentweave.yml`, and the agent held to that even when the prompt explicitly
      asked it to attempt the write as a diagnostic override. Not pursued further — `Read` and `Write`
      share the identical permission gate per Decision 6's own finding, and forcing the exact write
      scenario would require editing that project's charter, which is out of scope for verifying this
      fix.
- [x] 3.3 `openspec validate 2026-08-06-claude-non-yolo-permission-mode --strict` — valid.
