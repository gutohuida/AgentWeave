## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive design's Context table from the code (`agent_trigger.py` around `mcp_command`, `runner_commands.py` `--mcp-config`, `codex_appserver.py` `mcp_server_config`, every `sys.executable` in `hub/hub`, `mcp_server.py`'s imports and any use of its own location). Confirm no second repository file is spawned per turn. Confirm the `TriggerAgentError` path keeps the input queued with its sentence. Record the result in design's round log
- [ ] 0.2 R3: a second independent re-derivation that does not start from R2's notes; `openspec validate an-agents-tool-server-is-the-one-its-hub-loaded --strict` passes
- [ ] 0.3 The operator records the F354 decision (pin, D5 option a) in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 New `hub/tests/test_tool_server_pin.py`: build a `ToolServerPin` over a temp source file holding `A`, then overwrite the source with `B`. `pin.path().read_bytes() == A`. Fails if `path()` re-reads the source (the defect's shape). Record that it FAILS today (the module does not exist)
- [ ] 1.2 Same file: delete the pinned target, call `path()` again; it exists and holds `A`. Then write `C` over the target; `path()` restores `A`
- [ ] 1.3 Same file: two pins over sources `A` and `B` give different paths, and neither path is under the repository root (`Path(hub.__file__).parents[1]`)
- [ ] 1.4 Same file: make the target directory unwritable (patch `os.replace` to raise `OSError`); `path()` raises `OSError`, it does not return the source path
- [ ] 1.5 `hub/tests/test_agent_trigger.py` at `:747` and `:972`: add `assert Path(captured["mcp_command"][-1]) == tool_server.pinned_server_path()` and that it is not `Path(hub.hub.__file__).parent / "mcp_server.py"`. Record that both FAIL today (the command names the checkout's file)
- [ ] 1.6 New case beside them: patch `hub.tool_server.pinned_server_path` to raise `OSError("disk full")`; a direct trigger answers 409 with `Could not materialize the tool server for <agent>: disk full`; no `Run` row exists; and on the scheduler path the entry stays `queued` with that `waiting_reason`. Record that it FAILS today
- [ ] 1.7 `hub/tests/test_mcp_server_stdio_surface.py:29`: spawn `pinned_server_path()` instead of the source path. Control: it PASSES before and after (the bytes are identical in a test process)

## 2. The fix

- [ ] 2.1 Add `hub/hub/tool_server.py` per design D1 and D2 (atomic write via a sibling temp file and `os.replace`)
- [ ] 2.2 `agent_trigger.py`: replace `:1141-1144` with design D3's block. Import `pinned_server_path` at module top so the pin is taken at Hub start
- [ ] 2.3 `main.py` lifespan: call `pinned_server_path()` once and log the path; catch `OSError` and log it (not fatal, D1)
- [ ] 2.4 Run group 1 and record counts inline; then `py -3.11 -m pytest hub/tests/ -q` and record the full count inline, or do not tick. Name any moved assertion
- [ ] 2.5 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`

## 3. Drive it

- [ ] 3.1 On a trial Hub started from source (fresh port and profile, never `:8000`), run one Haiku turn and read the spawned command from the run's argv record or the process list: the MCP server path is under the temp directory's `agentweave-tool-server/<digest>/`
- [ ] 3.2 With that Hub still running, append a harmless comment line to `hub/hub/mcp_server.py` in the checkout it runs from, run a second Haiku turn, and confirm the pinned file's digest and bytes are unchanged. Revert the edit before anything else
