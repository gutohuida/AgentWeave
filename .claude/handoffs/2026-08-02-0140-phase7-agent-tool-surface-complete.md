# Handoff: Phase 7 governed agent tool surface complete

**Date:** 2026-08-02T01:40:28+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `d241d38`
**Agent:** Codex (GPT-5.6)
**Previous handoff:** `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md`
**Status:** chunk complete

## Goal

Ship the `hub-native-experience` OpenSpec change in
`openspec/changes/2026-07-30-hub-native-experience/`. This chunk completed Phase 7 so agents receive
one automatically configured, identity-bound outbound surface whose messages, requests, questions,
tasks, and scheduled work obey Hub queueing, attribution, budgets, and operator governance.

## Current state

Phase 7 tasks 7.1-7.6 are implemented and committed in `d279d22`. The Hub MCP module is now the sole
surface implementation; the CLI module only re-exports it. The registered surface has twelve tools:
`send_message`, task create/list/get/update, operator ask/poll, budgeted `request_agent`, and four
governed job mutations. Inbox/config/context/status/roster/heartbeat/self-registration bypasses are
absent. `save_checkpoint` was retired from the tool surface while the ordinary checkpoint command
remains.

Claude and Codex receive the canonical stdio server configuration per spawned Run, including bound
agent and Run identity. Global MCP setup is no longer needed: `agentweave mcp setup` and activation
perform no client mutation. Command equivalents use the same REST endpoints and forward bound
identity headers. `agentweave agent request` uses the same project budget and pre-approved template
policy as the MCP tool. Agent-originated job mutations require a matching live Run plus the project
allowance; operator calls remain available. Operator answers now enter the durable typed queue.

Migration 0015 adds project `agent_budget` and `allow_agent_jobs`. The full CLI and Hub suites passed,
as did independent command-only Phase 7 integrations. Task 7.7 is checked and the completed Phase 7
ledger is committed in `d241d38`.

## Files touched

- `README.md` — documents automatic governed tools and command parity. Finished.
- `docs/getting-started/alternative-modes.md` — removes global MCP ceremony and explains paths. Finished.
- `docs/getting-started/installation.md` — removes obsolete MCP setup instruction. Finished.
- `docs/getting-started/migration.md` — updates migration guidance for the canonical surface. Finished.
- `docs/guides/adding-new-agents.md` — documents budgeted template-based agent requests. Finished.
- `docs/guides/faq.md` — updates tool-access guidance. Finished.
- `docs/guides/logging-guide.md` — removes obsolete setup wording. Finished.
- `docs/guides/opencode-agents.md` — documents command-path behavior. Finished.
- `docs/guides/opencode-models.md` — updates command/tool setup guidance. Finished.
- `docs/index.md` — updates the Hub-native tool description. Finished.
- `docs/reference/cli-commands.md` — documents `agentweave agent request`. Finished.
- `docs/reference/mcp-tools.md` — replaces the old bypass-heavy reference with the canonical surface. Finished.
- `hub/hub/api/v1/agent_trigger.py` — injects canonical per-Run MCP configuration and bound environment. Finished.
- `hub/hub/api/v1/agents.py` — adds governed, budgeted template-based agent requests and context guidance. Finished.
- `hub/hub/api/v1/inbound_queue.py` — exposes/persists agent budget and job allowance settings. Finished.
- `hub/hub/api/v1/jobs.py` — gates agent-originated job mutations by live identity and project allowance. Finished.
- `hub/hub/api/v1/questions.py` — queues operator answers as typed operator input. Finished.
- `hub/hub/db/models.py` — adds project agent-governance fields. Finished.
- `hub/hub/launchability.py` — selects automatic injected or command paths without global registration. Finished.
- `hub/hub/mcp_server.py` — becomes the canonical identity-bound twelve-tool implementation. Finished.
- `hub/hub/migrations/versions/0015_add_agent_governance.py` — migrates budget and allowance columns. Finished.
- `hub/hub/runner_commands.py` — injects Claude and Codex MCP configuration per Run. Finished.
- `hub/tests/test_agent_tool_surface_phase7.py` — covers surface, identity, injection, budgets, jobs, and command-only flow. Finished.
- `hub/tests/test_agent_trigger.py` — verifies injected tool configuration. Finished.
- `hub/tests/test_agents_self_registered.py` — updates removed self-registration expectations. Finished.
- `hub/tests/test_inbound_queue.py` — covers new project queue/governance settings. Finished.
- `hub/tests/test_launchability.py` — verifies automatic access-path selection. Finished.
- `hub/tests/test_mcp_server.py` — replaces legacy tool tests with canonical outbound-surface tests. Finished.
- `hub/tests/test_migrations.py` — covers migration 0015. Finished.
- `hub/tests/test_questions.py` — verifies operator answers enter the queue. Finished.
- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — records evidence for 7.1-7.7 and the handoff path. Finished.
- `pyproject.toml` — removes the duplicate standalone `agentweave-mcp` console script. Finished.
- `src/agentweave/cli.py` — adds `agent request`; retires setup/activation mutation behavior. Finished.
- `src/agentweave/context_builder.py` — describes delivered inbound state and outbound-only capabilities. Finished.
- `src/agentweave/mcp/server.py` — reduces the CLI server to a canonical Hub re-export shim. Finished.
- `src/agentweave/templates/ai_context.md` — updates generated operating guidance. Finished.
- `src/agentweave/templates/claude_context.md` — removes inbox/setup assumptions. Finished.
- `src/agentweave/templates/collab_protocol.md` — replaces polling protocol with queue-delivered turn protocol. Finished.
- `src/agentweave/templates/kimi_context.md` — removes inbox/setup assumptions. Finished.
- `src/agentweave/templates/skills/aw-checkpoint.md` — points checkpoints to the ordinary command. Finished.
- `src/agentweave/templates/skills/aw-collab-start.md` — removes inbound retrieval guidance. Finished.
- `src/agentweave/tool_surface.py` — makes watchdog/local paths command-native and removes setup dependence. Finished.
- `src/agentweave/transport/http.py` — forwards bound agent and Run identity headers. Finished.
- `tests/test_activate.py` — verifies activation does not mutate global MCP configuration. Finished.
- `tests/test_agent_tool_surface_phase7.py` — covers CLI request, headers, command paths, and setup no-op. Finished.
- `tests/test_cli.py` — covers `agentweave agent request` and updated help/setup behavior. Finished.
- `tests/test_context_builder.py` — updates generated-context assertions. Finished.
- `tests/test_mcp_server.py` — verifies the re-export-only compatibility shim. Finished.
- `tests/test_watchdog_session.py` — verifies command-path instructions. Finished.
- `.claude/handoffs/2026-08-02-0140-phase7-agent-tool-surface-complete.md` — this handoff. Finished.
- `.claude/handoffs/LATEST.md` — points at this handoff; deliberately not part of implementation commits.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-30-0004-agentweave-strategy-discussion-resolved.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-07-31-2112-hub-native-phase1-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2038-phase4-identity-access-path-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2151-phase5-workspace-isolation-complete.md` — pre-existing untracked handoff; untouched.
- `.claude/handoffs/2026-08-01-2239-phase6-inbound-queue-complete.md` — previous untracked handoff; read, not modified.
- `.claude/skills/aw-spec-reindex/` — pre-existing untracked skill directory; untouched.

## Key decisions

1. **The Hub MCP server is canonical; the CLI module is only a compatibility import.** Maintaining two
   registrations had already produced divergent authority and bypasses. A shim preserves imports without
   preserving a second behavior source.
2. **Tools are outbound effects, not an alternate state-reading channel.** Inbox, context, config,
   status, roster, heartbeat, and self-registration tools were rejected because the Hub now assembles
   authoritative inbound state before each turn. Task reads survive because the task ledger is shared
   application state, not hidden coordination input.
3. **`save_checkpoint` leaves the protocol surface.** Checkpointing remains available as
   `agentweave checkpoint`; duplicating it only in one MCP implementation would violate surface parity.
4. **Tool configuration is per Run.** Claude receives `--mcp-config`; Codex receives
   `mcp_servers.agentweave` overrides. Global client registration and probes were rejected because they
   leak across projects and make launchability depend on workstation ceremony.
5. **Agent requests copy only pre-approved templates and consume a persisted project budget.** Arbitrary
   caller-supplied runner configuration was rejected. The live source Run supplies requester identity and
   hop depth, preventing spoofed delegation.
6. **Agent job mutations require both bound identity and explicit project allowance.** Silent autonomous
   scheduling was rejected; calls without agent identity remain operator actions, while disallowed agent
   calls return approval-required behavior.
7. **Command and tool paths converge on REST endpoints and bound headers.** A separate command-side
   implementation was rejected because it would bypass queue attribution and governance when MCP is off.

## Constraints and user directives (verbatim)

- "$resume Review the changes of phase 5 and execute phase 6"
- "Yeah and always commit the changes."
- "After every threshold of implementation you must run the skill `/handoff`"
- "Only stop if there is actually a blocking issue... don't need to be conservative on the changes...
  if there is genuinely a best approach you can scrap anything that already exists. Also apply these
  new rules when creating handoffs. Do a little bit less handoffs then previously but still do them."
- Repository instruction: "Files to Never Commit" includes runtime `.agentweave/` state.
- The task-ledger protocol requires re-reading the proposal, design, and affected spec; scenario
  verification; and one handoff at each phase boundary.

## Dead ends

- A combined pytest invocation over root `tests/` and `hub/tests/` hit an import-file mismatch because
  both packages intentionally contain `test_agent_tool_surface_phase7.py`. Running each suite from its
  own root passed (5 CLI and 8 Hub); do not treat the combined collector failure as a product failure.
- The first format/lint command used nonexistent `tests/test_activate_mcp.py`; the real file is
  `tests/test_activate.py`. The corrected Black and Ruff checks passed.
- Focused mypy over large existing Hub endpoint modules reported 24 existing missing-return annotations
  and one older nullable `session_data` warning. The two changed MCP modules pass focused mypy. Do not
  expand Phase 8 into repository-wide Hub typing cleanup unless the spec requires it.
- `mkdocs` is not installed, so strict docs build verification was unavailable.
- Global setup code remains physically below an early-return compatibility notice in `cmd_mcp_setup`
  and `_activate_mcp`. It is unreachable behavioral debt, not a second active surface; remove later only
  if doing so is useful and covered, rather than broadening Phase 8 automatically.

## Verification

Ran and passed:

- `.venv\Scripts\python.exe -m pytest tests -q` — **971 passed, 4 skipped**.
- `cd hub; ..\.venv\Scripts\python.exe -m pytest tests -q` — **383 passed, 4 skipped**, five warnings.
- `.venv\Scripts\python.exe -m pytest tests\test_agent_tool_surface_phase7.py -q` — **5 passed**.
- `cd hub; ..\.venv\Scripts\python.exe -m pytest tests\test_agent_tool_surface_phase7.py -q` — **8 passed**.
- `.venv\Scripts\python.exe -m black --check` over all 29 touched Python files — passed.
- `.venv\Scripts\python.exe -m ruff check` over all 29 touched Python files — passed.
- `.venv\Scripts\python.exe -m mypy --follow-imports skip --ignore-missing-imports hub\hub\mcp_server.py src\agentweave\mcp\server.py` — passed.
- Canonical registration inspection returned exactly the twelve intended tools.
- `git diff --cached --check` immediately before `d279d22` — passed.

Not tested:

- No real external Claude/Codex child process was launched against a live Hub. Runner-command,
  environment, identity, queue, and command-only integration tests cover the behavior in-process.
- `mkdocs build --strict` was not run because `mkdocs` is unavailable.
- The full Hub modules do not pass repository-wide mypy because of pre-existing endpoint typing debt.
- No browser work was needed or performed in Phase 7; Phase 8 introduces the UI work.

## Git state

- Branch: `hub-native-experience`.
- HEAD: `d241d38 Checkpoint Phase 7 agent tool surface`.
- Implementation and ledger tasks 7.1-7.7 are committed. No Phase 7 source changes are uncommitted.
- No usable upstream comparison was returned for this branch.
- Tracked `.claude/handoffs/LATEST.md` is dirty; this handoff, several older handoffs, and
  `.claude/skills/aw-spec-reindex/` are untracked session/tooling artifacts. Do not stage them.

## Next steps

1. Read Phase 8 in `openspec/changes/2026-07-30-hub-native-experience/tasks.md`, the complete
   `specs/agent-conversation-timeline/spec.md`, and the Phase 8-related decisions in `design.md`; then
   inspect `hub/hub/api/v1/agent_chat.py`, Agent/Run/message/queue models, and the agent-chat React
   components before implementing task 8.1's persisted stable agent colour index and migration.
2. Implement Phase 8 tasks 8.1-8.11 as one coherent timeline/read-model/UI chunk, rebuilding the
   production Hub UI assets and verifying light/dark rendering plus stopped, suspended, queued, and
   structured-result states.
3. Run `/handoff` once at the Phase 8 boundary (task 8.12), then check and commit that ledger item.

## Open questions for the user

None.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md`
- `openspec/changes/2026-07-30-hub-native-experience/design.md`
- `openspec/changes/2026-07-30-hub-native-experience/specs/agent-conversation-timeline/spec.md`
- `hub/hub/api/v1/agent_chat.py`
- `hub/hub/db/models.py`
- `hub/ui/src/components/agents/AgentPromptPanel.tsx`
