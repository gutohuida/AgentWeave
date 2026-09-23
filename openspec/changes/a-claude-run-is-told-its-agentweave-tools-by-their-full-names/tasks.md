## 0. Rounds and decision

- [ ] 0.1 R2: independent re-derivation against `agents.py:1460-1560` and `:1612-1700`, `agent_trigger.py:720-1090`, `runner_commands.py:120-270`; count every other bare tool name in rendered context and argue design D2's last paragraph
- [ ] 0.2 R3: second independent re-derivation; `openspec validate a-claude-run-is-told-its-agentweave-tools-by-their-full-names --strict` passes
- [ ] 0.3 The operator answers F139 (full names / disable the host tool); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first

- [ ] 1.1 `hub/tests/test_agent_facing_text.py`: `_render_hub_agent_context(..., runner="claude", access_path="mcp")` contains `` `mcp__agentweave__send_message( `` and `` `mcp__agentweave__record_evidence( ``, contains `SendMessage` in the disambiguating sentence, and does not contain `Names below are as injected`. FAILS today (no `runner` parameter; bare names)
- [ ] 1.2 Same file, control: `runner="codex"` renders bare names with today's preamble. PASSES today once the parameter exists
- [ ] 1.3 Same file: `GET /agents/agent-context?agent=x` renders bare names (no run, no runner). Control
- [ ] 1.4 `trigger_agent_directly` for a `claude` runner writes a context file containing `mcp__agentweave__send_message` (capture the file as `test_agent_trigger.py` captures the command). FAILS today
- [ ] 1.5 `test_tool_surface_matches_server.py` passes against both renderings (strip the prefix before comparing)
- [ ] 1.6 Unit: `build_command` routes exactly `CLAUDE_FAMILY_RUNNERS` to `_build_claude_command` (so the prefix set and the command builder cannot drift)

## 2. The fix

- [ ] 2.1 `CLAUDE_FAMILY_RUNNERS` in `runner_commands.py`, used at `:179`
- [ ] 2.2 `tool_prefix` through `_tool_surface_lines`/`_mcp_lines`; the new preamble sentence for prefixed renderings
- [ ] 2.3 `runner` parameter on `_render_hub_agent_context`, passed from `trigger_agent_directly`

## 3. Verify

- [ ] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Re-run `scripts/drive/t_row6_hop_chain.py` on a trial Hub at least five times (F139 was ~1 in 2) and read each triggering transcript for a host `SendMessage` call; record the count
- [ ] 3.3 Sync the delta and archive
