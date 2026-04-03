---
name: aw-checkpoint
description: Save a context checkpoint before compacting or ending a session. Usage — /aw-checkpoint [reason]
---

Save a context checkpoint to preserve your session state before compacting or handing off work.

**Project:** {project_name}
**Session:** {principal} is principal, agents: {agents_list}

Parse $ARGUMENTS as an optional reason string. Valid values: `token_threshold`, `phase_complete`, `pre_handoff`, `pre_sleep`, `manual` (default: `manual`).

Steps:

1. Determine your agent name from `.agentweave/roles.json` (`agent_assignments` key, find your name).

2. List your active tasks: if `list_tasks` MCP tool is available, call `list_tasks("<your-agent>")`. Otherwise run `agentweave task list` via Bash and filter by your name.

3. Review your session to collect the checkpoint data:
   - **Session intent:** What was this session trying to accomplish? (one paragraph)
   - **Files modified:** Every file you wrote or edited this session — no omissions. Format each as `"path/to/file — what changed"`
   - **Decisions made:** Every architectural or implementation decision you made, with rationale. Format: `"Decision — why"`. This is the most critical section — decisions are what get lost during compaction.
   - **Blockers:** Anything unresolved or deliberately deferred.
   - **Next steps:** The exact action to take immediately after resuming — not "continue work" but a specific, actionable step.
   - **Verification commands:** Shell commands that confirm the current state is correct.

4. Save the checkpoint:
   - **If `save_checkpoint` MCP tool is available:** Call it with the data collected above.
   - **If no MCP tools:** Run `agentweave checkpoint --agent <your-name> --reason <reason>` via Bash, then edit the generated file at `.agentweave/shared/checkpoints/` to fill in the qualitative sections.

5. Confirm the checkpoint was saved: verify the file exists at `.agentweave/shared/checkpoints/<your-agent>-*.md`.

6. Report the checkpoint file path.

After saving: you may now run `/compact` safely. When you resume, your first action must be to read your checkpoint file, then read `.agentweave/shared/context.md`, then resume from "Next Steps".
