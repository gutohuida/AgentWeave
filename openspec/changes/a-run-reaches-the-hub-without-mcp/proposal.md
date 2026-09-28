# Proposal — a run reaches the Hub without MCP

**Depends on:** `each-runner-cli-is-one-adapter` (slice 1: the `RunnerAdapter` and the three-axis split of
`resolve_access_path` into `tool_surface` / `approvals` / `plane`) and `a-copilot-agent-runs-over-acp`
(slice 2: the Copilot adapter, its ACP transport and its `session/request_permission` handler). Both land
first (operator decision `ghcp-d5-order`: 1 → 2 → 3). It also lands after the 2026-09-27 night ORDER
(`spec-queue/APPROVALS.md`). Five of those changes edit sites this change edits, so R2 rebases every
`file:line` onto the tree they leave:
`a-claude-run-is-told-its-agentweave-tools-by-their-full-names` (the tool-surface preamble and the MCP branch
of `access_path_notice`), `an-ask-me-card-says-what-workspace-only-would-decide` (`_ask_operator`,
`approve_tool_call`), `a-run-records-that-its-calls-were-allowed` (decision reporting),
`the-permissions-pill-shows-the-posture-the-run-gets` (`posture_at_rest(provider, access_path, yolo)`) and
`a-runner-that-cannot-collaborate-says-so-where-it-is-bound`.

Slice 3 of 5 of `openspec/explorations/2026-09-27-copilot-as-a-full-runner.md`. Its primary input is
appendix C, `c-reaching-the-hub-without-mcp.md`. **R1, 2026-09-27; R2, 2026-09-28. Nothing here is implemented.**
R2 ran against master `ef55e6f`, where none of the five changes above and neither slice had landed. So every site
they move carries "rebase at IMPL" in `design.md`.

## Why

The fire test for Copilot is the operator's work PC: Copilot is available there and MCP servers are blocked
by company policy. A Copilot agent over ACP still streams, is approved by the Hub, cancels, resumes and has
its messages delivered in the prompt, because none of that is MCP. What it loses is every call the *model*
makes to the Hub: `send_message`, `create_task`, `update_task`, `ask_user`, `record_evidence`,
`submit_spec_document` and the rest. Hooks cannot add model-callable tools, and extensions are experimental
(appendix C §4).

Today's answer to "MCP is not there" is a notice that tells the run to make HTTP requests itself, with
`Authorization: Bearer $AW_RUN_TOKEN` (`hub/hub/launchability.py:402-438`). It was driven on Claude and no run
reached the plane under its own power (F300, since fixed; F301, open: fifteen attempts, zero requests). On
Copilot the same instruction has two further defects:

- The model has to put the credential into its command. Copilot stores every tool call's `rawInput` as an ACP
  event, which the Hub records. The token then sits in stored events, which is exactly the leak design D4 of
  `2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing` forbade, one layer down.
- Copilot's shell on Windows is PowerShell. Measured today on PowerShell 5.1: an argument that starts with `@`
  is a parse error (the splatting operator), and a JSON argument passed to a native command loses its inner
  double quotes (`{"recipient":"x"}` arrives as `{recipient:x}`). Any "pass JSON on the command line" design
  fails there.

And the Hub does not know which runs have MCP. The grounds it uses are positive-only and permanent (F340):
`harness_has_honoured_mcp` (`launchability.py:252-280`) is true once **any** run of the agent ever stamped
`mcp_adapter_online_at`. A policy that arrives after the first success is never noticed. Meanwhile each
harness reports the server's state on every run and the Hub parses none of it (`parse_claude_line`,
`hub/hub/runner_parsing.py:229`, has no `system` branch).

## What changes

1. **Per-run MCP detection replaces the permanent grounds (F340, every runner).**
   - Each run given the Hub's MCP server records a status, `connected` / `failed` / `absent`, in a new
     `Run.harness_mcp_status`. `connected` comes from the adapter's existing announce
     (`POST /mcp-adapter-online`). The negatives come from the runner: Claude's `system/init.mcp_servers`
     line (newly parsed), Copilot's announce timeout, and Codex app-server's own
     `mcpServer/startupStatus/updated` (already read for its `failed` case). A call through the call command is
     never a positive report.
   - What a run is told about the plane is decided from **the latest tested run** of the agent, not "any run
     ever". A status the Hub does not recognise counts as no grounds.
   - **A runner whose first prompt the Hub sends after the harness has started its MCP servers tests the
     run itself.** Copilot is such a runner. Measured today on Copilot 1.0.88, the stdio server passed with
     `--additional-mcp-config` is started inside `session/new`, before the Hub sends any prompt. So the Hub
     waits, bounded (15 s), for this run's announce after `session/new`, and composes the first prompt from
     the answer. The first turn knows the answer: no conditional wording and no guessing. The raw events
     (`session.mcp_servers_loaded`) arrive only with the first *model* prompt. Measured today: a `/mcp list`
     slash prompt produced none. They corroborate after the fact. When the announce does not come, one
     `/mcp list` slash prompt (no model call; measured at about 5 ms) records Copilot's own sentence about
     the server, shown verbatim and never keyed on.
2. **The call command `aw-tool`: the Hub's pinned tool-server program in a call mode.**
   - `aw-tool <tool> [<args.json>]` runs `hub/hub/mcp_server.py --call` from the copy the Hub pinned at start
     (`hub/hub/tool_server.py`). It calls the **same functions** the MCP tools are, so parity is structural.
     It reads `AW_RUN_TOKEN` and `HUB_URL` from its own environment only, never from argv or a file. It
     prints the result as JSON.
   - `ask_user` blocks and polls exactly as over MCP, including the wait-ended report. `archive_job` waits on
     the operator's direction, and a job tool refused for the allowance comes back as the same refusal.
   - In call mode the script does not import fastmcp. It uses a stdlib stand-in for the decorator: measured
     1.4 s per call with fastmcp and 0.1 s without.
   - A launcher pair, `aw-tool` (POSIX sh) and `aw-tool.cmd` (Windows), is written beside the pin and put
     first on each run's `PATH`.
   - It is called `aw-tool`, not `aw`, because **`aw` is already the `agentweave` console script**
     (`pyproject.toml:82`; measured today, `Get-Command aw` resolves to `Python311\Scripts\aw.exe`). Arguments
     are passed as a file under `.agentweave/calls/`, never inline, because of the PowerShell facts above.
3. **The Hub's own approver auto-approves the call command, exactly and no wider.**
   - A shell command that is exactly one invocation (`aw-tool`, a callable tool name, and at most one plain
     relative `.json` path inside `<workspace>/.agentweave/calls/`) is allowed in every posture. The same
     holds for a file write of a `.json` file inside that directory. That is the same standing the
     `mcp__agentweave__*` tools already have.
   - It is one predicate in `mcp_server.py`, used by `_decide`, by `approve_tool_call`'s operator branch and by
     slice 2's ACP permission handler. Codex's `decide_approval` is severable, and R2 recommends cutting it. Codex
     sends the command wrapped (`powershell -Command "…"`), and its shell probably has neither the token nor the
     network (design D8, open question 4).
   - "Exactly" is a character allow-list, not a list of refused syntax. R2 found a parenthesised path that the list
     approach let through.
   - A near miss (an operator, a redirection, a variable, a grouping, a second command, a path elsewhere) is not
     denied by this rule. It falls through to today's decision.
4. **The turn notice and `_tool_surface_lines` say which surface THIS run has**: the MCP tools, or `aw-tool`.
   The raw HTTP form is no longer described to runs. It stays the application contract (the equal-capability
   requirement), not an instruction an agent is given, because following it puts the credential into stored
   command text. A run without MCP sees a status event saying how it reached the Hub, and why.
5. **Claude parity, severable (task group 7).**
   - Claude runs pre-allow `Bash(aw-tool:*)` and `PowerShell(aw-tool:*)`, so the call command works where no
     approver answers (the `cli` path, and F299's condition A). That closes F301 for Claude **if the drive
     (task 9.x) confirms it**.
   - F299 stays open for Claude. File writes under a blocked approver still die, and that containment question
     is the operator's (`DECISIONS.md` 2026-09-13).

**Not a sixth `agentweave` subcommand** (CLAUDE.md: the CLI keeps five `cmd_*`), for four reasons:
- the installed `agentweave`/`aw` console script is a different version from the Hub that minted the run;
- the shim is the pinned program whose version matches the routes it calls (`agent-tool-surface`, *"The tool
  server a run is given is the one its Hub loaded"*);
- it shares `ask_user`'s protocol with the MCP adapter instead of duplicating it;
- the product direction reduced the CLI to instance management.

The shim is Hub-owned run tooling, like the MCP server (design D2).

## Findings

- **F340: closed for every runner** by (1).
- **F301: closed for Copilot** by (2) + (3). For Claude it closes by group 7 if its drive confirms.
- **F299: closed for Copilot by construction**: the ACP approver is not an MCP tool (slice 2). This slice
  gives it a plane. It stays open for Claude.
- **F339: unchanged.** It is a Claude posture fact, and its docs row is owed separately (B11).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `agent-capability-plane`:
  - MODIFIED *HTTP and MCP access have equal capability*: the CLI scenario reworded, and the call command
    named as the MCP adapter's program.
  - MODIFIED *A run whose harness cannot use MCP is told how to reach the plane*: told the call command, not
    raw HTTP.
  - MODIFIED *A run is told the access path it actually has*: grounds are the latest tested run; a runner
    that tests before its first prompt describes its own result.
  - ADDED *Whether a run's harness started the Hub's tool server is recorded per run*.
  - ADDED *The call command carries the run's authority without showing it*.
- `agent-tool-surface`:
  - ADDED *The call command is on the run's path and is the program its Hub loaded*.
  - ADDED *A run without the tool-protocol surface is told each tool's call-command form*.
- `agent-run-sandboxing`:
  - ADDED *The Hub's own call command is decided like the Hub's own tools*.
  - ADDED *A Claude run pre-allows the Hub's call command* (group 7; removed from this delta if group 7 is cut).
- `runtime-diagnostics`: ADDED *A run states how it reached the Hub*.

## Impact

- **Backend:**
  - `hub/hub/mcp_server.py`: call mode, the fastmcp guard and the predicate.
  - `hub/hub/tool_server.py`: the launchers.
  - `hub/hub/launchability.py`: the grounds, the notices, the latest-test query.
  - `hub/hub/api/v1/agents.py`: the call-command rendering.
  - `hub/hub/api/v1/agent_trigger.py`: `PATH`, the `.agentweave/calls/` directory, recording, the status
    event.
  - `hub/hub/api/v1/agent_actions.py`: the announce notifies waiters.
  - `hub/hub/runner_parsing.py`: Claude `system/init`.
  - `hub/hub/repo_hygiene.py`: `.agentweave/calls/` excluded.
  - `hub/hub/codex_appserver.py`: `startupStatus` recording (and the predicate, only if group 6 is kept).
  - Slice 2's Copilot adapter and ACP transport: wait, compose late, the `/mcp list` diagnostic, raw-event
    corroboration.
  - A new `hub/hub/mcp_announce.py`: in-process waiters.
- **One migration:** `runs.harness_mcp_status`, `runs.plane_surface`, with a backfill of `connected` where
  `mcp_adapter_online_at` is set.
- **API:** `RunFacts` (`hub/hub/schemas/agents.py:140`, served at `agents.py:898` and
  `agent_chat.py:341`) gains the two fields.
- **No UI change and no bundle refresh.** The run's status event renders with the existing `status` kind.
- **`src/agentweave/` is untouched.**
