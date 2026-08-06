# Tasks

## 1. MCP tool schemas advertise their valid values

- [ ] 1.1 Define `Literal` aliases in `hub/hub/mcp_server.py` for message type, task status, task
      priority, and job session mode, each asserted against the runtime list it mirrors
      (`hub/hub/schemas/messages.py:_MESSAGE_TYPES`, `hub/hub/schemas/tasks.py:_TASK_STATUSES`
      and `_PRIORITIES`) so drift fails a test instead of reintroducing the bug.
- [ ] 1.2 Apply them to `send_message.message_type`, `create_task.priority`, `update_task.status`,
      `create_job.session_mode`, and add a parameter description to each.
- [ ] 1.3 Reduce `HubAPIError`'s detail from a stringified list of Pydantic error dicts to the human
      `msg` sentence.
- [ ] 1.4 Add `direct_trigger` to `src/agentweave/constants.py`'s `MESSAGE_TYPES`.
- [ ] 1.5 Test: each tool's generated schema carries the enum.
- [ ] 1.6 Test: the alias and the runtime validator list agree, for all four.
- [ ] 1.7 Test: an invalid value is rejected, and the surfaced error is the human sentence.

## 2. Claude permission control and a working default

- [ ] 2.1 Add a `permission_mode` `ControlDescriptor` to `CATALOG["claude"].controls`
      (`hub/hub/model_catalog.py`) with explicit `ControlValue` labels — "Edit files", "Ask first",
      "Full access" — not `_enum`, whose derived labels would read "Acceptedits".
- [ ] 2.2 Default the descriptor to `acceptEdits`, and change `_build_claude_command`'s non-yolo
      branch from `manual` to `acceptEdits`.
- [ ] 2.3 Guard both the `--permission-mode` and `--dangerously-skip-permissions` branches so an
      override supplied through `control_args` is not overridden by the hardcoded flag appended later.
- [ ] 2.4 Update `runner_commands.py`'s module docstring, which documents the `manual` decision.
- [ ] 2.5 Test: default non-yolo argv carries `--permission-mode acceptEdits` exactly once.
- [ ] 2.6 Test: an override reaches argv and the hardcoded flag is suppressed.
- [ ] 2.7 Test: yolo still emits `--dangerously-skip-permissions`, and an override does not duplicate
      or contradict it.

## 3. Autoscroll, opening position, and a jump control

- [ ] 3.1 Re-key the scroll effect in `AgentOutputPanel.tsx` on the entries the timeline renders,
      not `lines`.
- [ ] 3.2 Scroll to the newest turn when a conversation is opened or switched, resetting `autoscroll`.
      Use an instant scroll so a long history does not animate.
- [ ] 3.3 Add a jump-to-bottom control, visible only while following is suspended. Do **not**
      reintroduce a pause/resume toggle — the spec forbids it.
- [ ] 3.4 Fix the existing autoscroll test, which drives content through `outputLines` and so cannot
      observe the defect.
- [ ] 3.5 Test: opening a conversation with history lands at the newest entry.
- [ ] 3.6 Test: the jump control appears only when suspended, and restores following.

## 4. Canonical context tells an agent where it is and what its tools accept

- [ ] 4.1 Thread `effective_work_dir` from `trigger_agent_directly` into
      `_render_hub_agent_context` rather than recomputing it.
- [ ] 4.2 Add a "Your workspace" section: absolute working directory, whether it is an isolated
      worktree (branch `agentweave/<agent>`, siblings invisible) or the shared repo root for a
      read-only agent, and that paths resolve against it.
- [ ] 4.3 Add a "Your tools" section generated from the same Literal aliases as §1, including the
      four job tools currently invisible to agents.
- [ ] 4.4 Delete the `Canonical runtime context: .agentweave/context/<agent>.md` line.
- [ ] 4.5 Test: context names the real working directory and the worktree branch.
- [ ] 4.6 Test: context lists each tool's constrained parameters with their valid values.
- [ ] 4.7 Test: context contains no pointer to its own context file.

## 5. Preamble and operator-facing text

- [ ] 5.1 Correct `access_path_notice`'s CLI-fallback branch (`hub/hub/launchability.py`), which
      names commands removed when the CLI was reduced to five.
- [ ] 5.2 Remove "Your principal" from `post_new_session_request` (`hub/hub/api/v1/agents.py`).
- [ ] 5.3 Correct `agent_status.py:STALLED_STATUS_MESSAGE`, which tells the operator to restart the
      removed watchdog.
- [ ] 5.4 Test: no shipped agent-facing string references a removed subsystem.

## 6. The seeded charters stop citing files that do not exist

- [ ] 6.1 Replace the shared `Read roles.json, protocol.md, shared/context.md` opener across
      `hub/hub/data/charters/` with what is true: roster, instructions, and charter arrive in the
      turn context; nothing needs reading to start.
- [ ] 6.2 Remove references to `agentweave.yml`, `agentweave status`, and "principal".
- [ ] 6.3 Remove the watchdog reference in `spec.md`.
- [ ] 6.4 Test: no seeded charter mentions a removed subsystem or a file the Hub never creates.

## 7. Verification

- [ ] 7.1 `pytest hub/tests/ -q` — baseline 777 passed / 9 skipped.
- [ ] 7.2 `cd hub/ui && npx vitest run` — baseline 462 passed.
- [ ] 7.3 `npx tsc --noEmit`; `ruff check` on every touched Python file.
- [ ] 7.4 `openspec validate --specs --strict` — 24 items.
- [ ] 7.5 `npm run build` and regenerate `hub/hub/static/ui`.
- [ ] 7.6 **Live:** ask a Claude agent to create a file — succeeds, no permission error.
- [ ] 7.7 **Live:** set the pill to "Ask first" and repeat — the refusal returns, proving the control
      reaches argv rather than being decorative.
- [ ] 7.8 **Live:** ask an agent where it is — it names its worktree, not the project root.
- [ ] 7.9 **Live:** a Codex agent's **first** `send_message` succeeds — no 422 in `agent_outputs`.
- [ ] 7.10 **Live:** a conversation with history opens at the newest entry; sending follows;
      scrolling up suspends and reveals the jump control.
- [ ] 7.11 **Live:** `GET /agents/agent-context` mentions no `roles.json`, `principal`, or
      `agentweave.yml`.
