# Test guide — a run reaches the Hub without MCP

## Agent-verifiable

1. Tasks 1.1–1.15 fail on the tree before their implementation task, and pass after it. Record the fail-before
   evidence through a scratch copy of the file, never `git stash` (DEAD-ENDS 2026-09-27).
2. `aw-tool --list`, run from the pinned copy in a directory that is not the package root, lists exactly the served
   tools minus `approve_tool_call` (task 1.3). With fastmcp made unimportable, it still works.
3. A call through the stub Hub carries the bearer from the environment. With no `AW_RUN_TOKEN` it makes no request
   at all (task 1.4).
4. The predicate table of task 1.6 holds in both dialects. Under "Ask me", no allowed row opens a card, and every
   near-miss row does.
5. On the trial Hub (group 9):
   - a Copilot run with MCP records `connected`/`mcp`;
   - the same agent with `--disable-mcp-server agentweave` records `absent`/`shim`, creates its task through
     `aw-tool` with no operator card, and has **zero** `aw_run_` occurrences in its stored events;
   - removing the flag returns it to `connected`/`mcp` on the next turn;
   - a Claude run under a `deniedMcpServers` `--settings` records `absent`. Its next turn records
     `plane_surface = shim`, and its `.agentweave/context/<agent>.md` holds the `aw-tool` tool section. The Hub
     stores no composed prompt, so that file and the run's facts are what can be read (R3).
6. The full Hub and CLI suites are green, and the lint and format gates pass (group 8).

## Human-only

These need the operator. Most need **the work PC**, where company policy blocks MCP and where no agent can run.
Before starting, update the Hub there to a build carrying slices 1–3.

1. **Before any turn** (no model call). In an interactive `copilot` session on the work PC, run `/env` and `/mcp
   list`, and note what they say about MCP policy (which source, and whether `agentweave` would be allowed).
   Note `copilot --version`: it must be 1.0.88 or newer for managed policy to apply under ACP.
2. **One tiny turn to a Copilot agent** through the Hub: *"Create an AgentWeave task titled WORKPC-1, then stop."*
   In the app, check:
   - the task exists;
   - the run's activity shows one line saying the MCP server did not start and the run was told to use
     `aw-tool`, quoting Copilot's own words about the server;
   - no permission card asked you about `aw-tool` or a file under `.agentweave/calls/`.
3. **If the task was not created**, open the run's activity and copy the first refusal verbatim. The likely causes,
   which only this machine can show, are:
   - the company blocks running a `.cmd` from the user profile (AppLocker/WDAC);
   - PowerShell's policy refuses the command;
   - Copilot asks about the command in a way the Hub did not recognise;
   - the machine's `cmd` `AutoRun` (`reg query "HKCU\Software\Microsoft\Command Processor" /v AutoRun`, and the
     same under `HKLM`) prints something, such as `Active code page: 65001`, ahead of the command's JSON output on
     every call. Note the value if one is set (design D3);
   - the args file was written by a bare `Set-Content` and holds non-ASCII text (the command then says to use
     `-Encoding utf8`).
4. **One question to you through the command.** *"Ask me, with ask_user, whether to proceed; then stop."* Answer it
   in the app within the wait. The agent should receive your answer. Say whether the agent's shell cut the command
   off before you answered (design D7).
5. **Reading the notice.** Open the agent's `.agentweave/context/<agent>.md` in its workspace after the turn, and
   read the "Your tools" section. The Hub stores no composed prompt. For the "Tool access" notice, ask the agent in a
   second tiny turn to quote the "Tool access" section it received. Would a colleague understand from them alone how the agent reaches the Hub, and that nothing about it
   needs the credential typed anywhere?
6. **A specification turn** (design D16). Open a specification document with the Copilot agent and ask it, in one
   tiny turn, to submit the document unchanged. It should write its arguments file and submit with no card, and
   write nothing else.
7. **On this machine, optional.** If you want to see the Claude side, give a Claude agent `hub_client: cli` and ask
   it to create a task. It should use `aw-tool` and succeed (group 7).
