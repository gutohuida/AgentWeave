# Test guide — a Copilot agent runs over ACP

## Agent-verifiable

1. **Before the fix.** Tasks 1.3–1.16, 1.18 and 1.19 fail on the code as it is before group 2
   starts. Task 1.17 passes and is a guard. It records that the Hub's MCP server answers
   `server/discover` with an error and keeps serving.
2. **Groups 2–9.** Their tests pass after the implementation, with this command:
   `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npx vitest run`
3. **CI parity** (task 8.5). All four checks are clean:
   - `ruff check src/ hub/ tests/`
   - `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`
   - `mypy src/`
   - `cd hub/ui && npm run lint`
4. **The Copilot tests do not depend on a local `claude`.** Run them again with `claude` removed from
   `PATH`.
5. **Fixtures are real.** `hub/tests/fixtures/copilot_acp/*.jsonl` are captured transcripts (tasks
   1.1 and 1.2), in wire order. No file contains `aw_run_`, `aw_live_`, `gho_` or `ghp_`.
6. **No secret on disk.** After a drive turn, no file under
   `~/.agentweave/hub/copilot-home/` contains `aw_run_`.
7. **No shim process.** Throughout a drive turn, the process tree under the Hub holds `copilot.exe`
   and no `node.exe` running `npm-loader.js`.
8. **A stop kills the whole tree.** After task 11.5's stop, `Get-Process copilot,powershell`
   shows no process whose parent was that run's `copilot.exe`.
9. **Drive records.** The records from tasks 11.2–11.4 are pasted verbatim into the Round log. They
   match design D10 (one text row per message; a tool row paired with its result; no replayed first
   turn on the resume).
10. **A Copilot turn is given the Hub's tools (R2).** During drive prompt 1, the spawned
    `copilot.exe` command line holds `--additional-mcp-config @…agentweave-mcp.json`, and `/agent/trigger`
    for a Copilot agent does not answer 501. Before this change it answers 501; with only the
    runner registry widened, it would spawn with no MCP server at all.
11. **One-shot calls have no tools (R2).** Any Copilot title or checkpoint spawned during the drive
    carries `--excluded-tools=builtin:*,mcp:*,custom:*` and no `--available-tools`, and its
    conversation title is prose, not JSON.
12. **The migration works in both directions.**
    - Up: on a copy of the trial database, `alembic upgrade head` succeeds, and a `copilot` runner row
      can be inserted.
    - Down: the downgrade refuses while that row exists.

## Human-only

1. **Creating a Copilot agent.** Open the Runners page and create a GitHub Copilot runner, then
   create an agent on it from the Add-agent dialog.
   - Does the provider read as GitHub Copilot, with its mark?
   - Does the model picker offer **Auto** first and preselected?
2. **Reading the timeline.** Talk to the Copilot agent under Workspace only. Is its timeline as
   readable as a Claude agent's?
   - messages as whole paragraphs;
   - tool rows you can open;
   - the context meter moving.

   On the Free plan, does the note saying Copilot ran a different model than you asked for make
   sense to you, or read as noise?
3. **The operator card.** Under Ask me, answer an operator card for a Copilot command.
   - Does the card say what the command is and where it runs, as clearly as a Claude card?
4. **Instructions in your repository.** Look at a Copilot agent's context in a repository with its
   own `CLAUDE.md`. Decide whether the precedence sentence is the behaviour you want: AgentWeave's
   context wins, and the repository's project facts still apply.
5. **The cost.** After the drive, check your Copilot Free allowance (`/usage` in an interactive
   `copilot`, or github.com settings). Is the spend of about six prompts, plus any titles, what you
   expected?
6. **Full access under a company policy** (work PC, optional). Choose Full access for a Copilot
   agent. If the organisation disables Copilot's allow-all mode, the run should say so and keep
   working inside its workspace. Does that sentence tell you what happened?
