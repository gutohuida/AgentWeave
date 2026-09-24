## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `agents.py:1460-1560` and `:1612-1700`, `agent_trigger.py:720-1090`, `runner_commands.py:120-270`; count every other bare tool name in rendered context and argue design D2's last paragraph
- [x] 0.2 R3: second independent re-derivation; `openspec validate a-claude-run-is-told-its-agentweave-tools-by-their-full-names --strict` passes
- [x] 0.3 The operator answers F139 (full names / disable the host tool); recorded in `spec-queue/DECISIONS.md`. **Approved 2026-09-24** with the review's fixes (`spec-queue/tracks/reviews/B3-2026-09-24.md` §6): full names, host tool not disabled. Only the `DECISIONS.md` entry remains

## 1. Tests first

- [ ] 1.1 `hub/tests/test_agent_facing_text.py`: `_render_hub_agent_context(..., runner="claude", access_path="mcp")` contains `` `mcp__agentweave__send_message( `` and `` `mcp__agentweave__record_evidence( ``, contains `SendMessage` in the disambiguating sentence, and does not contain `Names below are as injected`. FAILS today (no `runner` parameter; bare names)
- [ ] 1.1a Same file (operator review): `_render_hub_agent_context(..., runner="claude", access_path="cli")` — a first run, described in the HTTP form — contains the host-`SendMessage` sentence and **no** `mcp__agentweave__` name; the same with `runner="codex"` contains neither. FAILS today (no `runner` parameter; no sentence)
- [ ] 1.2 Same file: `runner="codex"`, `access_path="mcp"` renders bare names (control) under the preamble *"Names below are as declared; your harness may show them with a prefix such as `mcp__agentweave__`."* and does not contain `they are prefixed` (operator review: aligned with the spec's "may"). FAILS today on the preamble wording
- [ ] 1.3 Same file: `GET /agents/agent-context?agent=x` renders bare names (no run, no runner). Control
- [ ] 1.4 `trigger_agent_directly` for a `claude` runner **whose run is described as MCP** (the agent's config has `hub_client: "mcp"`, or a prior `Run` of it has `mcp_adapter_online_at` set — design D2, R3) writes a context file containing `mcp__agentweave__send_message` (capture the file as `test_agent_trigger.py` captures the command). FAILS today. Control beside it: the same agent with no grounds (a first run) is written the HTTP form and no prefixed name, and (operator review) its context file does contain the host-`SendMessage` sentence
- [ ] 1.4a `launchability.access_path_notice("mcp", tool_prefix="mcp__agentweave__")` names `mcp__agentweave__send_message` and does not contain a bare ` send_message `; and the context file written by 1.4's trigger contains the prefixed notice. FAILS today (no parameter; notice is bare)
- [ ] 1.4b The prefixed preamble contains the "call it by the full name listed here" clause. FAILS today
- [ ] 1.5 `test_tool_surface_matches_server.py` passes against both renderings (strip the prefix before comparing)
- [ ] 1.6 Unit: `build_command` routes exactly `CLAUDE_FAMILY_RUNNERS` to `_build_claude_command` (so the prefix set and the command builder cannot drift)

## 2. The fix

- [ ] 2.1 `CLAUDE_FAMILY_RUNNERS` in `runner_commands.py`, used at `:179`
- [ ] 2.2 `tool_prefix` through `_tool_surface_lines`/`_mcp_lines`; the new preamble sentence for prefixed renderings; the host-`SendMessage` sentence after the preamble for every Claude-family run in either rendering (a `host_tools_note: bool` argument, set by `_render_hub_agent_context` from `runner in CLAUDE_FAMILY_RUNNERS`); the non-Claude MCP preamble reworded to "may" (design, *Operator review*)
- [ ] 2.3 `runner` parameter on `_render_hub_agent_context`, passed from `trigger_agent_directly`
- [ ] 2.4 `access_path_notice(access_path, tool_prefix="")` (`launchability.py:383-393`); `agent_trigger.py:1123` passes the prefix for Claude-family runs

## 3. Verify

- [ ] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Re-run `scripts/drive/t_row6_hop_chain.py` on a trial Hub at least five times (F139 was ~1 in 2) and read each triggering transcript for a host `SendMessage` call; record the count
- [ ] 3.3 Sync the delta and archive
