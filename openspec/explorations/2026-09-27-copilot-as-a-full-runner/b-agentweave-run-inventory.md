# AgentWeave run-feature inventory (for Copilot CLI runner parity)

Researched 2026-09-27 at `8627adf` on master. Read-only. Paths are relative to the repo root; `hub/hub/` is abbreviated `hh/`.

**Specificity key:** **C** = claude-only · **X** = codex-only · **B≠** = both, but done differently per runner · **A** = runner-agnostic (a new runner gets it for free if it produces the shared inputs).

**Headline:** the runner seam is narrow and already well marked. The *orchestration* layers (queue, scheduler, loops/flows/jobs, checkpoints, reconciliation, divergence, worktrees, review turns, questions, ask-me cards, accounting aggregation, UI timeline/meter) are runner-agnostic. The per-runner work sits in **~12 modules**: `db/models.py:311`, `runner_commands.py`, `runner_parsing.py`, `codex_appserver.py` (a transport peer), `pty_runner.py` selection in `agent_trigger.py`, `launchability.py`, `model_catalog.py`, `workspace_writes.py`, `worker.py`, `conversation_titles.py`, `api/v1/agents.py`, and the UI's `RunnerCli`/`CLI_OPTIONS`/`Icon.tsx`. The **approval channel** is the deepest part. Claude uses an MCP permission-prompt tool plus `_decide`. Codex uses JSON-RPC approval requests plus `decide_approval`. Copilot needs a third mechanism, or it has to settle for static flags only.

---

## 0. Gates: where the runner set is closed

| # | Gate | Evidence | Spec. | Copilot action |
|---|---|---|---|---|
| 0.1 | `RUNNER_CLIS = ("claude","codex")`, the single source of truth for `Runner.cli` | `hh/db/models.py:311`; validated `hh/schemas/runners.py:22-23`; probed `hh/api/v1/runners.py:116-118` | B≠ | add `"copilot"` |
| 0.2 | `SUPPORTED_RUNNERS = ("claude","claude_proxy","native","codex")`; `build_command` dispatch; anything else raises `UnsupportedRunnerError`, which becomes HTTP 501 | `hh/runner_commands.py:60`, `:126-196` (branches `:164`, `:179`); 501 at `hh/api/v1/agent_trigger.py:1229-1232`; docstring says Copilot is out of scope (`runner_commands.py:7`, `agent_trigger.py:15`) | B≠ | new `_build_copilot_command` |
| 0.3 | `_CATALOG_PROVIDER_BY_RUNNER` maps a runner to its catalog key | `hh/runner_commands.py:110-119` | B≠ | add entry |
| 0.4 | `RUNNER_CLI` binary map. It already holds a dead `"copilot":"copilot"` entry and a dead Copilot auth branch (`COPILOT_GITHUB_TOKEN`/`GH_TOKEN`/`GITHUB_TOKEN`) | `hh/launchability.py:33-43`, `:116-126`; DEAD note `:21-30` | X/C (+ dead copilot) | revive, and re-verify the auth rule |
| 0.5 | `MCP_INJECTABLE_RUNNERS = {"claude","claude_proxy","native","codex"}`. `resolve_access_path` returns `"cli"` for any runner outside this set, which silently removes the tool server **and** the approver posture | `hh/launchability.py:230-249` | B≠ | add once injection is proven |
| 0.6 | `worker.SUPPORTED_CLIS`, `conversation_titles._SUPPORTED_CLIS` | `hh/worker.py:71`, `hh/conversation_titles.py:68`, `:251` | B≠ | add branches (see 7.x) |
| 0.7 | CLI-side registry (legacy, duplicated by design) | `src/agentweave/constants.py:97,150,237-249` (an old copilot entry: `--resume=<uuid>`, JSONL `result.sessionId`, `copilot mcp add`); `src/agentweave/config.py:657,719-723` | legacy | reference only; the Hub does not import it |
| 0.8 | Every literal runner branch in `hh/` (non-test) | `api/v1/agents.py:249,558-564,704`; `api/v1/agent_trigger.py:2345,2451,2574`; `codex_appserver.py:85`; `conversation_titles.py:86,91`; `launchability.py:34,39,190`; `model_catalog.py:164,236`; `runner_commands.py:111,114,164,179`; `worker.py:142,147,324,326,450` | — | each one needs a copilot arm |
| 0.9 | History: Copilot was once a watchdog runner (OTel context collector, PAT concurrency) | commits `1c6970d` (Copilot OTel context-usage collector), `7205a0b`, `3f1d594`; `src/agentweave/constants.py:29` `COPILOT_OTEL_DIR` | — | prior art to mine |

---

## 1. Agent tool surface (MCP) and authentication

### 1a. Tools served by `hh/mcp_server.py` (FastMCP `agentweave`; stdlib + fastmcp only)

Each tool is a thin adapter over `POST|GET|PATCH $HUB_URL/api/v1/agent-actions/...` (`_hub_request`, `hh/mcp_server.py:164-200`), with `Authorization: Bearer $AW_RUN_TOKEN`.

| Tool | Purpose | Def line | REST route (`hh/api/v1/agent_actions.py`) | Spec. |
|---|---|---|---|---|
| `send_message` | attributable message into recipient's durable inbound queue | 203 | `POST /messages` :203 | A |
| `create_task` | create task attributed to bound agent | 252 | `POST /tasks` :230 | A |
| `list_tasks` | read ledger, optional assignee filter | 299 | `GET /tasks` :247 | A |
| `get_task` | read one task | 320 | `GET /tasks/{id}` :269 | A |
| `task_history` | who moved a task when | 326 | `GET /tasks/{id}/transitions` :316 | A |
| `update_task` | status transition as bound agent (never `blocked`) | 343 | `PATCH /tasks/{id}` :282 | A |
| `ask_user` | ask operator 1..n questions, **blocks polling** up to `AW_QUESTION_TIMEOUT` (default 240s) | 360 (timeout :1005) | `POST /questions` :599, `/questions/batch` :624, `GET /questions/{id}` :816, `POST /questions/wait-ended` :682 | A (depends on the harness tolerating a long tool call) |
| `get_answer` | poll a previously asked question | 527 | `GET /questions/{id}` | A |
| `submit_checkpoint_notes` | notes for next checkpoint | 547 | `POST /checkpoint-notes` :390 | A |
| `list_checkpoints` / `read_checkpoint` | read own/granted checkpoints | 586 / 603 | `GET /checkpoints` :430, `/checkpoints/{id}` :444 | A |
| `recall` | fetch a cited recorded observation | 614 | `GET /recall/{id}` :486 | A |
| `request_agent` | request new agent from template under budget | 628 | `POST /agents/request` :832 | A |
| `create_job` / `create_loop` / `create_flow` | scheduled work, loop with stop condition, flow over approved spec | 640 / 681 / 766 | `POST /jobs` :845 | A |
| `archive_job` / `toggle_job` / `run_job` | lifecycle of jobs | 871 / 922 / 934 | `POST /jobs/{id}/archive` :892, `PATCH /jobs/{id}` :860, `POST /jobs/{id}/run` :916 | A |
| `create_spec_document` / `submit_spec_document` / `rename_spec_document` / `read_spec_document` | Hub-owned spec authoring | 1740 / 1768 / 1902 / 1925 | `POST /spec/documents/create` :1525, `POST /spec/documents` :1659, `/rename` :1592, `GET /spec/documents` :1415 | A |
| `record_evidence` / `list_evidence` / `decide_evidence` | requirement evidence | 1955 / 2009 / 2039 | `POST /spec/evidence` :1187, `GET` :1257, `POST /{id}/decision` :1339 | A |
| `approve_tool_call` | **Claude's `--permission-prompt-tool` endpoint**, not an agent capability. Must accept `tool_use_id`, return a JSON string, and have **no return annotation** | 1697 (contract notes :946-958) | `POST /permission-decisions` :971, `/permission-requests` :1024, `GET /permission-requests/{id}` :1065, `/expire` :1092 | **C** |
| (startup side effect) `_announce_adapter_online` | adapter reports that the harness actually started it, recorded as `Run.mcp_adapter_online_at` | 2073-2093 | `POST /mcp-adapter-online` :459 | A. It is the *measurement* that Copilot honours MCP |
| — | integration retry endpoints (not MCP tools) | — | `GET /tasks/{id}/integrations` :298, `POST .../retry` :335 | A |

### 1b. Authentication and identity

| Item | Evidence | Spec. | Notes |
|---|---|---|---|
| Run token `aw_run_<32>` minted per run, sha256 stored as `Run.capability_token_hash`; valid only while `Run.status=="running"` and the instance id matches | `hh/agent_auth.py:18-80` | A | identity is never taken from the body |
| Env injected into the spawned CLI: `AW_AGENT_IDENTITY`, `AW_RUN_ID`, `AW_RUN_TOKEN`, `AW_WORKSPACE_DIR`, `AW_PERMISSION_POSTURE` (operator), `AW_DECISION_TIMEOUT`, `AW_QUESTION_TIMEOUT`, `AW_TURN_DEPTH`, `HUB_URL`. `AW_BOOTSTRAP_API_KEY` and `AW_TICKET_SECRET` are stripped | `hh/api/v1/agent_trigger.py:1239-1304` | A | |
| **How the MCP server receives that env** | Claude: stdio server inherits the full env (`runner_commands.py:250-262`, no env key). Codex: explicit allow-list `env_vars=[AW_RUN_TOKEN, AW_AGENT_IDENTITY, AW_RUN_ID, AW_TURN_DEPTH, HUB_URL]` (`runner_commands.py:317-329`; `codex_appserver.py:969-980`) | B≠ | **Possible latent gap (unverified):** Codex's allow-list omits `AW_QUESTION_TIMEOUT`, `AW_DECISION_TIMEOUT`, `AW_WORKSPACE_DIR`, `AW_PERMISSION_POSTURE`, so the per-agent question-wait setting may not reach a Codex tool server. Copilot needs its own "which env reaches the MCP child" answer |
| Tool server binary is a content-addressed pinned copy, `~/.agentweave/hub/tool-server/<digest>/mcp_server.py`, run by `sys.executable` | `hh/tool_server.py:1-90`; used at `agent_trigger.py:1195-1203` | A | |
| **Non-MCP (HTTP) path exists and has equal capability.** A run whose harness is not given or not proven to honour MCP is told to call `$HUB_URL/api/v1/agent-actions/...` with `Bearer $AW_RUN_TOKEN` | `hh/launchability.py:200-310` (`resolve_access_path`, `harness_has_honoured_mcp`, `described_access_path`), `access_path_notice` :411-441; `_tool_surface_lines(access_path=...)` renders the HTTP form, `hh/api/v1/agents.py:1504`; spec `agent-capability-plane` "HTTP and MCP access have equal capability" (:107), "A run whose harness cannot use MCP is told how to reach the plane" (:185) | A | **Copilot fallback:** even without MCP, a Copilot agent can reach every capability by shell `curl`. It loses only the Hub-answered approval posture |

---

## 2. Instructions and context delivery

| Feature | Evidence | Spec. | Copilot mapping needed |
|---|---|---|---|
| Canonical context rendered per turn (`_render_hub_agent_context`). Sections: Runtime/Onboarding header, Project Operating Profile, Your workspace (worktree/branch/shared/read-only), Spec this task implements, Open spec document + phase duties, Team roster (`_runner_summary`), Quality Gates, evidence rights, Other agents' history, **Project Instructions**, Communication Mode, tool surface (`_tool_surface_lines`), Registration | `hh/api/v1/agents.py:1605-2130` (headers :1704-2124); charters via `get_charter_context` :2738 | A | none (text) |
| Context is written to `<work_dir>/.agentweave/context/<agent>.md` | `hh/api/v1/agent_trigger.py:1160-1168` | A | |
| **Claude receives it** through `--append-system-prompt-file <file>` | `hh/runner_commands.py:248-249` | C | need Copilot's system-prompt or instructions channel (flag? `AGENTS.md`/`.github/copilot-instructions.md`? a prompt prefix?) |
| **Codex receives it** through `-c model_instructions_file=<file>` (exec). App-server is presumably the same through thread config (not traced) | `hh/runner_commands.py:330-331` | X | |
| Turn-prompt notices prepended to the operator message: `access_path_notice`, `auto_snapshot_notice` (Hub commits the worktree, so don't `git commit`), `spec_turn_notice` (spec turn: no write tool, interview, `submit_spec_document`) | `hh/api/v1/agent_trigger.py:1170-1193`; texts `hh/launchability.py:313-470` | A | none |
| Tool surface text (one source, MCP or HTTP rendering). The test `test_tool_surface_matches_server.py` enforces parity with the server | `hh/api/v1/agents.py:1504-1530`, used :2122 | A (open change `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` makes it **C**: `mcp__agentweave__*` full names for Claude) | Copilot's tool-name prefixing convention must be known |
| `@path` file-mention neutralisation (Claude expands `@x` into an attachment) | `hh/file_mentions.py:1-28`; used in `spec_turn_notice`, worker/titles; spec `agent-run-sandboxing` :854 | C (applied to all) | check whether Copilot expands `@` |
| Project memory: Claude auto-reads `CLAUDE.md` in cwd (relied on by titling), Codex reads `AGENTS.md` natively. The Hub writes neither | `hh/conversation_titles.py:78-96` | B≠ (implicit) | Copilot auto-reads its own instructions files, which could double up instructions |

---

## 3. Permission postures and approvals

| Feature | Evidence | Spec. | Notes |
|---|---|---|---|
| Posture vocabulary: `acceptEdits` ("Edit files"), `workspace` (Hub decides), `manual` ("Ask me", operator decides), `bypassPermissions` ("Full access" / yolo). Both providers declare them as the `permission_mode` control | `hh/model_catalog.py:145-161`, claude control :210-233, codex control :261-273 (`style="none"`) | B≠ | Copilot declares the same 4 ids |
| `DEFAULT_PERMISSION_MODE=acceptEdits`, `permission_mode_values()` union | `hh/model_catalog.py:344-364` | A | |
| Claude default: `workspace` when a tool server is injected, else `acceptEdits` | `hh/runner_commands.py:62-81` | C | the `posture_at_rest` helper does **not exist yet**. It is in the approved change `the-permissions-pill-shows-the-posture-the-run-gets` |
| `APPROVER_PERMISSION_MODES = {workspace, manual}` | `hh/runner_commands.py:88-92` | B≠ | |
| **Claude translation:** `--permission-mode manual` + `--permission-prompt-tool mcp__agentweave__approve_tool_call` (workspace/manual); `--permission-mode acceptEdits`; yolo is `--dangerously-skip-permissions`; `--allowedTools mcp__agentweave__*` unless yolo; spec turn adds `--disallowedTools Edit,MultiEdit,Write,NotebookEdit` | `hh/runner_commands.py:199-288` | C | |
| **Codex exec translation:** `--sandbox workspace-write` / `read-only` (spec turn) / `--dangerously-bypass-approvals-and-sandbox` (yolo or full_access). No live approval channel | `hh/runner_commands.py:291-357` | X | |
| **Codex app-server:** `_thread_policy` gives `(sandbox, approvalPolicy)` at thread start (operator: `read-only`/`untrusted`; full: `danger-full-access`/`never`; default: `workspace-write`/`on-request`). `decide_approval` answers `mcpServer/elicitation/request` (own server only), command/file-change approvals (`_within` workspace), `item/permissions/requestApproval`; unknown requests are declined. `ASK_OPERATOR` opens a card | `hh/codex_appserver.py:194-300`, loop :1046-1090 | X | two layers: policy at start plus a per-request decision |
| `_decide`: the **shell judge** plus path judge (`AW_WORKSPACE_DIR`, realpath, bash/powershell lexing, `$'..'` two-pass, URL allowed only to own `HUB_URL`) | `hh/mcp_server.py:1008-1019`, `:1103-1592` | C (Codex has no shell-word judge; it relies on its sandbox) | Copilot either reuses `_decide` through an approval hook or leans on its own sandbox |
| `_ask_operator` / `_await_decision` (blocks up to `AW_DECISION_TIMEOUT`=120s, deny on timeout), `_report_decision`, `_report_wait_ended` | `hh/mcp_server.py:997`, `:1595-1695` | C (mechanism) | |
| Ask-me cards API: list, decide, dismiss expired; SSE `permission_decided`; `permission_denied` activity | `hh/api/v1/permissions.py:47-190`; `hh/permission_requests.py:21-37` (`expire_pending_for_run` at run end) | A | shared by Claude and Codex |
| `refused_capability.py`: a 403 from project state becomes a durable operator question | `hh/refused_capability.py:1-16` | A | |
| Outside-workspace write record (observability, every posture) | `hh/workspace_writes.py:34-55` (`CLAUDE_WRITE_TOOLS` Write/Edit/MultiEdit/NotebookEdit; `CODEX_WRITE_TOOL` apply_patch); `hh/outside_write_record.py:1-49`; sinks `_flush_line` (Claude, codex exec) and `_on_event` (app-server); watch at `agent_trigger.py:2447` | B≠ tables, A classifier | **Copilot write-tool names and path keys must be added**, or nothing is recorded (silently) |
| Review turn "where" (detached read-only checkout) is enforced only by the posture: `_decide` for Claude, the sandbox cwd for Codex | `hh/review_turn.py:1-20` | B≠ (implicit) | Copilot needs an equivalent confinement |
| Spec sandboxing requirements that name Claude | `openspec/specs/agent-run-sandboxing/spec.md:9` (explicit non-bypass mode), `:26` (MCP allowlist); also :42-854 posture requirements, mostly generic | C | Copilot counterparts |

---

## 4. Run lifecycle

| Feature | Evidence | Spec. | Notes |
|---|---|---|---|
| Transport selection: Claude uses `PtySession` (ConPTY/pexpect); Codex uses app-server JSON-RPC by default (`uses_app_server`, `--no-app-server` opt-out) or `PipeSession` (exec) | `hh/agent_trigger.py:2345-2353`, app-server path above it (~:2330-2342); `hh/codex_appserver.py:79-85`; `hh/pty_runner.py:218,307`; transport sentinels stripped `agent_trigger.py:1205-1211`; spec `runner-registry` "A runner's flags may select a transport" (:162) | B≠ | Copilot: PTY, pipe, or a new RPC peer. Copilot's ACP/server mode would be a `codex_appserver`-like module |
| Stop/cancel/interrupt: PTY and pipe use `terminate_process_tree` (taskkill /T, killpg); app-server sends `turn/interrupt` and then `close(force)` | `hh/pty_runner.py:184-213,303,394`; `hh/codex_appserver.py:1022-1028`, `:862-882` | B≠ | |
| Session resume through `Conversation.provider_session_id`: Claude `--resume <id>` (id from any line's `session_id`), Codex exec `resume <id>` subcommand (id from `thread.started.thread_id`), app-server `thread/resume` | `hh/db/models.py:433`; `agent_trigger.py:847-848`; `runner_commands.py:283-284,352-353`; `codex_appserver.py:984-989` | B≠ | Copilot `--resume=<uuid>` (legacy note 0.7) |
| Session-id capture | `hh/runner_parsing.py` docstring :6-9, :241/:285/:331 (claude), :440-442 (codex); app-server `on_thread_started` `codex_appserver.py:991-997` | B≠ | |
| Inbound queue: a durable per-agent queue; delivery is **always the next turn** (no mid-turn stdin or steer injection) | `hh/inbound_queue.py:25-118`; `hh/turn_scheduler.py:258-377` (refuses while a run is `running`, :310-318) | A | Copilot needs a one-shot `-p` per turn only |
| ask_user blocks inside the tool call (a long MCP call) and the answer is delivered live, or queued as a new turn if the asker stopped waiting | `hh/mcp_server.py:360-527`; `hh/api/v1/questions.py:39-80` | A (needs harness MCP timeout ≥ 240s) | verify Copilot's MCP tool-call timeout |
| turn_scheduler, scheduler.py (4112 lines, **no** runner literals), run_liveness, run_reconciliation (cli used only as a label), run_divergence | `hh/turn_scheduler.py`; `hh/scheduler.py`; `hh/run_liveness.py:90-121`; `hh/run_reconciliation.py:33-43`; `hh/run_divergence.py` | A | |
| Checkpoints: trigger (80% context, Claude auto-compacts ~95%), generation, handover, cutover (new conversation, not a resume) | `hh/checkpoint_policy.py:24-37`; `hh/checkpoint_trigger.py:142-153,311-324`; `hh/checkpoint_generation.py:506-652`; `hh/checkpoint_cutover.py:114-197` | A, but **depends on `worker.py`** (one-shot CLI) and on context-usage readings | Copilot needs a worker branch and a context meter, or checkpoints never trigger or generate |
| Compaction: no Hub-driven compaction. The legacy `POST /agents/{name}/compact` inbox message asks the agent to run `/compact` | `hh/api/v1/agents.py:2994-3030` | C-flavoured legacy | |
| Worktree auto-snapshot commit at end of every turn | `hh/worktrees.py` `snapshot_worktree`; notice `launchability.py:444-470` | A | |

---

## 5. Stream events, usage, context, UI rendering

| Feature | Evidence | Spec. | Notes |
|---|---|---|---|
| Closed kinds `text, thinking, tool_use, tool_result, status, diagnostic, error` and builders | `hh/runner_events.py:10-11,136-231` | A | |
| `redact_secrets` on payloads | `hh/runner_events.py:63` | A | |
| Claude parser (`stream-json --verbose`): text/thinking/tool_use blocks, `user.tool_result`, `result` becomes completed/error status, `rate_limit_event` becomes allowance, `result.modelUsage.<m>.contextWindow` | `hh/runner_parsing.py:229-370` | C | |
| Codex exec parser: `item.started/completed` for agent_message, reasoning, command_execution, file_change, mcp_tool_call, web_search; plan/todo_list become `status("plan")`; `turn.completed` usage; `turn.failed`/`error` | `hh/runner_parsing.py:424-612` | X | |
| Codex app-server mapper: `map_item_to_events` :390; `thread/tokenUsage/updated` → usage :372,:1116; `turn/completed|failed` :1122-1150; `turn/plan/updated` :1151; MCP startup-status failures reported once | `hh/codex_appserver.py` | X | |
| Unwired `parse_opencode_line` (precedent for a third parser) | `hh/runner_parsing.py:615-666` | — | template |
| Codex post-hoc rollout accounting from `$CODEX_HOME/sessions` | `hh/runner_parsing.py:669-707`; `agent_trigger.py:2574-2582` | X | Copilot: inline usage, or a session-state file? |
| Context meter: `ContextUsageSample`. Claude self-reports its window; Codex looks it up in `model_catalog` (unknown gives `unavailable`). `usable_context_reading` picks the row | `hh/runner_events.py:246-318`; `hh/runner_parsing.py:11-25,381-421`; `hh/context_readings.py`; `POST /agents/{name}/context-usage` `hh/api/v1/agents.py:2977` | B≠ | Copilot must self-report or declare windows in the catalog |
| Usage accounting (`TurnUsage` by runner/model; budget; snapshots) | `hh/usage_accounting.py`; `hh/api/v1/accounting.py` | A | the Copilot parser must fill `AccountingSample` |
| Provider allowance / rate-limit hold (`allowance.status=="rejected"`, `resetsAt`, `rateLimitType`) | `hh/provider_allowance.py:60-80`; produced only by the Claude parser :364-369 | **C in practice** (Codex never holds) | Copilot must synthesise it, or its queue never holds on a quota refusal |
| UI stream rendering, trace timeline, turn outcome, context indicator | `hub/ui/src/components/agents/ConversationView.tsx`, `AgentOutputPanel.tsx`, `lib/eventSummary.ts`, `components/context/ContextUsageIndicator.tsx`, `contextPresentation.ts`, `layout/StatusBar.tsx` | A | |
| Spec `agent-stream-events` "Supported runner normalization" (:75, names Claude and Codex), "Stream contract conformance tests" (:224) | openspec | B≠ | add Copilot fixtures |

---

## 6. Model and effort controls

| Feature | Evidence | Spec. | Notes |
|---|---|---|---|
| `CATALOG` `ProviderDescriptor` per provider: models (id, label, aliases, context_window, default) and controls (`effort`, `permission_mode`) with `ApplySpec(style=flag|config|none)` | `hh/model_catalog.py:163-276`; methodology docstring :1-63 | B≠ | Claude is a hand list, live-verified; Codex reads `~/.codex/models_cache.json` (`visibility=="list"`), and effort is the intersection of `supported_reasoning_levels` |
| `render_control_args` (argv) / `render_control_config` (app-server config dict); `validate_overrides` backstop | `hh/model_catalog.py:373-486` | A | |
| `GET /model-catalog` | `hh/api/v1/model_catalog.py:18-25` | A | |
| Aliases (`opus`, `sonnet`, …) | `hh/model_catalog.py` Claude entry; open change `a-model-alias-is-a-model-choice` | C | |
| `undeclared_model_reason` (worker refuses a model the catalog doesn't know) | `hh/worker.py:~440` | A | |
| UI model picker from the catalog: `ComposerModelControls.tsx:18`, `AgentCreateDialog.tsx`, `RunnersPage.tsx` | `hub/ui/src/...` | A | |

---

## 7. Workspace, env, subprocess, and out-of-band CLI calls

| Feature | Evidence | Spec. | Notes |
|---|---|---|---|
| Worktrees, task workspace, workspace paths, `ProjectWorkspace` | `hh/worktrees.py`, `hh/task_workspace.py`, `hh/workspace_paths.py`, `hh/project_workspace.py` (no runner text) | A | |
| `resolve_agent_env` (`*_VAR` indirection). **Claude-only:** strips ambient `ANTHROPIC_BASE_URL` unless configured | `hh/launchability.py:145-196` (`:190`) | C special case | Copilot equivalent: guard against an ambient `GH_TOKEN`/`COPILOT_GITHUB_TOKEN` leak |
| Windows exe resolution / npm shim unwrap | `hh/pty_runner.py:57-130`; `hh/subprocess_windows.py` | A | Copilot is npm-installed and benefits |
| Launchability probe (present, authorized, runnable, collaboration_ready), including the codex app-server note | `hh/launchability.py`; `hh/api/v1/agents.py:240-260` (`runner_row.cli == "codex"` collaboration reason) | B≠ | |
| **Worker** (one-shot JSON: checkpoint generation, probes). Claude `--tools "" --strict-mcp-config --output-format json -p`; Codex `exec --json --ephemeral --sandbox read-only --output-schema`; `stdin=DEVNULL`; envelope parsers | `hh/worker.py:71,123-155,318-330,445-456` | B≠ | Copilot needs a one-shot JSON mode with no tools |
| **Conversation titles** (one-shot, no tools) | `hh/conversation_titles.py:66-96,251` | B≠ | a missing branch returns `None` (no title) |
| Display names `_display_model` | `hh/api/v1/agents.py:556-564` | B≠ | add `"copilot"` |

---

## 8. Loops, flows, jobs, review, delegation

| Feature | Evidence | Spec. |
|---|---|---|
| Loops, flows, jobs (`scheduler.py`, `api/v1/loops.py`, `api/v1/jobs.py`), review turns (`review_turn.py`), `request_agent`, delegation messages, charters (`api/v1/charters.py`), instructions (`api/v1/instructions.py`), agent_lifecycle, agent_roster | grep-clean for runner literals | **A** (they reach runners only through `trigger_agent_directly`) |
| `request_agent` template and the model of the new agent (open change copies an operator-made agent's runner) | `hh/mcp_server.py:628`; `openspec/changes/request-agent-models-the-new-agent-on-one-the-operator-made` | A, but touches `runner_commands`/`launchability` |

---

## 9. UI surfaces with runner-specific content

| Surface | Evidence | Spec. | Copilot action |
|---|---|---|---|
| `RunnerCli = 'claude' | 'codex'` | `hub/ui/src/api/runners.ts:5` | B≠ | add |
| `CLI_OPTIONS`, default `'claude'` | `hub/ui/src/components/runners/RunnersPage.tsx:19,195` | B≠ | add |
| Provider marks (SVG) and `--provider-claude` colour; unknown providers fall back to initials | `hub/ui/src/components/common/Icon.tsx:230-284` | B≠ | add mark |
| Launchability banner / "cannot collaborate" | `AgentCard.tsx:73-81`, `AgentSettingsControls.tsx:224-263`, `AgentCreateDialog.tsx:28-212` | A (reads the backend verdict) | backend only |
| Permissions pill / default posture select | `AgentSettingsControls.tsx:190`, `AgentOutputPanel.tsx:393-394`, `Composer.tsx`, `NewConversationSurface.tsx` | A (catalog-driven) | catalog only |
| Context meter | `components/context/*`, `StatusBar.tsx`, `OverviewPage.tsx:209` | A | backend samples |
| Test fixture of the catalog | `hub/ui/src/__tests__/support/modelCatalogFixture.ts` | B≠ | add copilot fixture |

---

## 10. openspec requirements that name Claude or Codex (each needs a Copilot counterpart)

| Spec | Requirement(s) |
|---|---|
| `agent-capability-plane` | A run whose harness cannot use MCP is told how to reach the plane |
| `agent-composer` | Trigger result sources |
| `agent-context-usage` | Cache breakdowns are counted according to provider semantics; **Claude context mapping**; **Codex context mapping**; Auxiliary collectors are invocation and session bound; Context conformance and pipeline tests; A measured sample identifies the model it measured; Window metadata observed for a session persists…; Every model the catalog offers declares a context window… (this file already mentions copilot) |
| `agent-run-sandboxing` | A non-yolo Claude run's sandbox posture is set by the Hub…; A sandboxed non-yolo Claude agent can still use the Hub's own MCP tools; (implicitly Claude) Text the operator did not write reaches a run without a file mention its harness would expand (:854) |
| `agent-stream-events` | Supported runner normalization; Stream contract conformance tests |
| `opencode-config` | agentweave.yml accepts runner: opencode (legacy) |
| `runner-registry` | Runners are project-scoped Hub records; Built-in runners are seeded on first use; Runner management is available through the Hub UI (+ generic: A runner's flags may select a transport…, Launchability reports the runner that would actually be spawned) |
| `runtime-diagnostics` | Proxy credential diagnostics |
| `usage-accounting` | Supported runner telemetry normalizes to one accounting shape |

Mention counts: agent-context-usage 19, agent-run-sandboxing 12, agent-stream-events 6, agent-composer 5, usage-accounting 5, runner-registry 4, opencode-config 2, capability-plane 1, runtime-diagnostics 1.

---

## 11. Open openspec changes that collide with a runner-adapter refactor

All of these are **APPROVED in `spec-queue/APPROVALS.md` 2026-09-27 for tonight's aggressive night ORDER**, so they will land first unless the ORDER is changed. Task progress shows `[done/total]`.

| Change | Runner code touched (mention counts) | Collision |
|---|---|---|
| `a-claude-run-is-told-its-agentweave-tools-by-their-full-names` [3/19] | claude 47, agent_trigger 9, runner_commands 8, launchability 8 | **High.** Makes the tool surface per-runner (Claude `mcp__agentweave__*` names) |
| `the-permissions-pill-shows-the-posture-the-run-gets` [0/16] | runner_commands 11, launchability 11, model_catalog 7, codex_appserver 2 | **High.** Introduces `posture_at_rest`, changes the Claude catalog default to `workspace`, deletes a dead constant |
| `an-ask-me-card-says-what-workspace-only-would-decide` [0/18] | codex_appserver 8, mcp_server 6, agent_trigger 6 (migration) | **High.** Both approval paths |
| `a-run-records-that-its-calls-were-allowed` [0/21] | codex 15, codex_appserver 8, mcp_server 7 (migration) | **High.** Approval recording for both runners |
| `the-codex-models-offered-are-the-ones-its-cli-lists` [2/14] | model_catalog 24, runner_parsing 3 | **High.** Codex catalog source |
| `a-model-alias-is-a-model-choice` [2/16] | model_catalog 12, RunnersPage 4 | Medium. Catalog/alias model |
| `a-runner-choice-names-its-model` [2/10] | RunnersPage 3, runner-registry | Medium. Runner/model binding |
| `an-estimate-that-misses-turns-says-so` [2/9] | usage_accounting 9, runner_parsing 4, codex_appserver 3 | Medium. Per-runner usage completeness |
| `worker-spend-counts-against-the-budget` [2/20] (not in tonight's ORDER) | runner_parsing 5, usage_accounting 5 | Medium. Worker envelope accounting |
| `a-runner-that-cannot-collaborate-says-so-where-it-is-bound` [0/16] | launchability 27, codex 9 | **High.** Launchability/collaboration verdict |
| `agents-no-longer-register-themselves` [3/26] | launchability 31 | Medium. Launchability, AgentCard, migration |
| `request-agent-models-the-new-agent-on-one-the-operator-made` [3/23] | agent_trigger 16, runner_commands 5, launchability 4 | Medium |
| `stop-clears-a-run-an-earlier-hub-left-running` [2/21] (not in ORDER) | agent_trigger 13, pty_runner 3 | Medium. Stop path per transport |
| `the-shell-judge-reads-a-word-whole` [8/41] (not in ORDER) | mcp_server 10 | Medium. `_decide` |
| `a-refused-first-send-leaves-no-exploration-behind` [3/27], `an-agent-can-be-paused-and-keeps-its-input` [2/24], `isolation-does-not-change-under-held-work` [3/25], `a-retried-firing-records-how-its-work-ended`, `an-undelivered-message-says-how-its-last-attempt-ended`, `input-the-hub-accepted-is-answered-as-accepted`, `a-flow-stages-its-review-in-the-dispatch` | agent_trigger 10-17 each | Low to medium. Merge churn in `agent_trigger.py` (3531 lines), not a semantic clash |

Low or none: the UI-only, spec-corpus and doc changes (`a-dialog-takes-the-keyboard…`, `the-corpus-is-indexed…`, `a-documents-rigor-history…`, etc.).

---

## 12. Unverified or worth a follow-up

- Codex MCP `env_vars` allow-list omits `AW_QUESTION_TIMEOUT`/`AW_DECISION_TIMEOUT`/`AW_WORKSPACE_DIR`/`AW_PERMISSION_POSTURE` (`runner_commands.py:320-327`, `codex_appserver.py:973-979`). If Codex does not pass the parent env through, the per-agent ask_user wait is ignored for Codex runs. Not driven (Codex is undrivable).
- Codex app-server instructions channel (`model_instructions_file` in thread config?) not traced.
- Copilot facts to establish by live `--help` or a drive (not researched here): non-interactive JSON output mode; `--resume`; MCP injection per invocation (`--additional-mcp-config`?); approval hooks versus `--allow-tool`/`--deny-tool`/`--allow-all-tools`; system-prompt/instructions channel; `@` mention expansion; usage/context reporting; stdin behaviour; interrupt semantics; the model list source.
